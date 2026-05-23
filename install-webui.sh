#!/bin/bash
set -e
REPO_ZIP_URL="https://github.com/HiJaychou/222/archive/refs/heads/main.zip"
APP_DIR="/opt/iwantrun-vpn-webui"
DATA_DIR="/etc/freedom-vpn/web"
SERVICE_NAME="iwantrun-vpn-web"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TMP_DIR="/tmp/iwantrun-vpn-webui-install"
SB_BIN="/usr/local/bin/sing-box"
DEFAULT_SB_VER="1.13.12"
PANEL_PORT="80"
PANEL_PORT_FALLBACK="0"
LOGIN_PATH="login-$(openssl rand -hex 4)"
ADMIN_PASS="$(openssl rand -base64 18 | tr -d '=+/')"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
echo_line(){ echo -e "${CYAN}============================================================${NC}"; }
die(){ echo -e "${RED}错误：$1${NC}"; exit 1; }
check_root(){
  if [[ "$EUID" -ne 0 ]]; then
    die "请使用 root 用户运行此脚本。"
  fi
}
detect_arch(){ case "$(uname -m)" in x86_64|amd64) echo "amd64" ;; aarch64|arm64) echo "arm64" ;; *) die "暂不支持当前架构：$(uname -m)" ;; esac; }
port_in_use(){
  ss -lntup 2>/dev/null | awk '{print $5}' | grep -Eq "[:.]${1}$"
}
choose_panel_port(){
  if port_in_use 80; then
    PANEL_PORT="$(shuf -i 20000-60000 -n 1)"
    PANEL_PORT_FALLBACK="1"
    echo -e "${YELLOW}检测到 80 端口已被占用，将改用随机端口：${PANEL_PORT}${NC}"
  else
    PANEL_PORT="80"
    PANEL_PORT_FALLBACK="0"
    echo -e "${GREEN}Web 面板将使用默认 80 端口。${NC}"
  fi
}
install_dependencies(){
  echo -e "${YELLOW}正在安装系统依赖...${NC}"
  if command -v apt >/dev/null 2>&1; then
    apt update -y
    apt install -y python3 python3-venv python3-pip curl wget jq openssl iproute2 unzip tar ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 python3-pip curl wget jq openssl iproute unzip tar ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip curl wget jq openssl iproute unzip tar ca-certificates
  else
    die "暂不支持当前系统。推荐 Ubuntu 22.04。"
  fi
}
check_dependencies_ready(){
  echo -e "${YELLOW}正在检测运行环境...${NC}"
  local missing=()
  for cmd in python3 curl wget jq openssl ip ss unzip tar; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if [[ "${#missing[@]}" -gt 0 ]]; then
    die "缺少必要命令：${missing[*]}。请检查系统源是否可用，推荐使用 Ubuntu 22.04。"
  fi
  python3 -m venv --help >/dev/null 2>&1 || die "Python venv 不可用，请确认 python3-venv 已正确安装。"
}
install_singbox_core(){
  local arch sb_ver url latest_headers
  if [[ -x "$SB_BIN" ]]; then echo -e "${GREEN}检测到 sing-box 已安装：$($SB_BIN version | head -n 1)${NC}"; return; fi
  echo -e "${YELLOW}未检测到 sing-box，正在安装 sing-box 最新版...${NC}"
  arch="$(detect_arch)"

  sb_ver="$(curl -4fsSL --connect-timeout 10 --retry 2 https://api.github.com/repos/SagerNet/sing-box/releases/latest 2>/dev/null | jq -r '.tag_name // empty' 2>/dev/null | sed 's/^v//' || true)"
  if [[ -z "$sb_ver" || "$sb_ver" == "null" ]]; then
    latest_headers="$(curl -4fsSLI --connect-timeout 10 --retry 2 https://github.com/SagerNet/sing-box/releases/latest 2>/dev/null || true)"
    sb_ver="$(echo "$latest_headers" | awk -F'/tag/v' 'tolower($1) ~ /^location:/ {print $2}' | tr -d '\r' | tail -n 1)"
  fi
  if [[ -z "$sb_ver" || "$sb_ver" == "null" ]]; then
    echo -e "${YELLOW}无法自动获取最新版，将使用稳定版本 v${DEFAULT_SB_VER}。${NC}"
    sb_ver="$DEFAULT_SB_VER"
  fi

  url="https://github.com/SagerNet/sing-box/releases/download/v${sb_ver}/sing-box-${sb_ver}-linux-${arch}.tar.gz"
  rm -rf /tmp/sing-box-install && mkdir -p /tmp/sing-box-install
  if ! curl -4fL --connect-timeout 15 --retry 3 -o /tmp/sing-box-install/sb.tar.gz "$url"; then
    echo -e "${RED}下载地址：${url}${NC}"
    echo -e "${YELLOW}请在服务器上检查：curl -4 -I https://github.com/SagerNet/sing-box/releases/latest${NC}"
    die "下载 sing-box 失败，请检查 VPS 是否能访问 GitHub Release。"
  fi
  tar -xzf /tmp/sing-box-install/sb.tar.gz -C /tmp/sing-box-install || die "解压 sing-box 失败。"
  find /tmp/sing-box-install -type f -name sing-box -exec mv {} "$SB_BIN" \;
  chmod +x "$SB_BIN"
  rm -rf /tmp/sing-box-install
  [[ ! -x "$SB_BIN" ]] && die "sing-box 安装失败。"
  echo -e "${GREEN}sing-box 安装完成：v${sb_ver}${NC}"
}
cleanup_old_install(){
  echo -e "${YELLOW}正在清理旧的 Web 面板安装文件...${NC}"
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "$SERVICE_FILE"
  systemctl daemon-reload || true
  rm -rf "$APP_DIR"
  mkdir -p "$APP_DIR" "$DATA_DIR"
}
download_project(){
  echo -e "${YELLOW}正在下载 Web 面板完整项目...${NC}"
  rm -rf "$TMP_DIR" && mkdir -p "$TMP_DIR"
  wget -O "$TMP_DIR/source.zip" "$REPO_ZIP_URL"
  unzip -q "$TMP_DIR/source.zip" -d "$TMP_DIR"
  SRC_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name '222-*' | head -n 1)"
  [[ -z "$SRC_DIR" ]] && die "没有找到解压后的项目目录。"
  [[ ! -d "$SRC_DIR/app" ]] && die "GitHub 仓库里没有 app 目录，请确认 app/ 已上传。"
  [[ ! -f "$SRC_DIR/requirements.txt" ]] && die "GitHub 仓库里没有 requirements.txt，请确认已上传。"
  cp -r "$SRC_DIR/app" "$APP_DIR/"
  cp "$SRC_DIR/requirements.txt" "$APP_DIR/"
}
install_python_env(){
  cd "$APP_DIR"
  python3 -m venv venv
  if [[ ! -x "$APP_DIR/venv/bin/pip" ]]; then
    "$APP_DIR/venv/bin/python" -m ensurepip --upgrade || true
  fi
  [[ ! -x "$APP_DIR/venv/bin/pip" ]] && die "Python 虚拟环境创建失败，未找到 pip。请确认 python3-venv / python3-pip 已正确安装。"
  "$APP_DIR/venv/bin/pip" install --upgrade pip
  "$APP_DIR/venv/bin/pip" install -r requirements.txt
}
init_settings_and_admin(){
  mkdir -p "$DATA_DIR"
  cat > "$DATA_DIR/settings.json" <<EOJ
{"panel_port": ${PANEL_PORT}, "login_path": "${LOGIN_PATH}", "panel_name": "自由档案馆 VPN Web Manager"}
EOJ
  "$APP_DIR/venv/bin/python" -m app.main --init-admin admin "$ADMIN_PASS"
}
create_service(){
  cat > "$SERVICE_FILE" <<EOS
[Unit]
Description=iwantrun VPN Web Manager
After=network.target
[Service]
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PANEL_PORT}
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOS
  systemctl daemon-reload; systemctl enable "$SERVICE_NAME" >/dev/null 2>&1; systemctl restart "$SERVICE_NAME"; sleep 2
  if ! systemctl is-active --quiet "$SERVICE_NAME"; then journalctl -u "$SERVICE_NAME" -n 100 --no-pager; exit 1; fi
}
open_firewall(){
  if command -v ufw >/dev/null 2>&1; then ufw allow "${PANEL_PORT}/tcp" >/dev/null 2>&1 || true; fi
  if command -v firewall-cmd >/dev/null 2>&1; then firewall-cmd --permanent --add-port="${PANEL_PORT}/tcp" >/dev/null 2>&1 || true; firewall-cmd --reload >/dev/null 2>&1 || true; fi
}
get_server_ip(){
  SERVER_IP="$(curl -s4 --max-time 6 https://api.ipify.org || true)"
  if [[ -z "$SERVER_IP" ]]; then
    SERVER_IP="$(hostname -I | awk '{print $1}')"
  fi
  if [[ -z "$SERVER_IP" ]]; then
    SERVER_IP="你的服务器IP"
  fi
}
print_result(){
  local url
  if [[ "$PANEL_PORT" == "80" ]]; then
    url="http://${SERVER_IP}/${LOGIN_PATH}"
  else
    url="http://${SERVER_IP}:${PANEL_PORT}/${LOGIN_PATH}"
  fi
  echo_line
  echo -e "${GREEN}自由档案馆｜VPN 管理面板安装完成${NC}"
  echo_line
  echo "访问地址：${url}"
  echo "管理员账号：admin"
  echo "管理员密码：${ADMIN_PASS}"
  echo "sing-box：$($SB_BIN version | head -n 1)"
  if [[ "$PANEL_PORT_FALLBACK" == "1" ]]; then
    echo -e "${YELLOW}80 端口已被占用，请到 VPS 后台防火墙 / 安全组手动放行：${PANEL_PORT}/TCP${NC}"
  else
    echo -e "${YELLOW}请确认 VPS 后台防火墙 / 安全组已放行：80/TCP${NC}"
  fi
}
main(){ check_root; echo_line; echo -e "${GREEN}自由档案馆 | iwantrun.com VPN Web Manager 安装脚本${NC}"; echo_line; install_dependencies; check_dependencies_ready; choose_panel_port; install_singbox_core; cleanup_old_install; download_project; install_python_env; init_settings_and_admin; create_service; open_firewall; get_server_ip; rm -rf "$TMP_DIR"; print_result; }
main "$@"
