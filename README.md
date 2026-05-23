# 自由档案馆｜VPN 管理面板

基于 `sing-box` 的5种协议 VPN Web 管理面板，适合部署在个人 VPS 上。新手不用手写配置，通过网页即可完成协议安装、用户管理、链接/二维码生成、日志查看和日常维护。

## 📖 项目理念

在一个信息被高墙阻隔、真相被选择性遮蔽的时代，工具本身也可以成为一种微小但具体的抵抗。

所谓的“境外势力”，不应成为人们获取信息的恐惧来源；  
所谓的“盛世繁华”，也不应以封锁知识、限制言论为代价。

让更多被困在信息茧房中的人，拥有接触真实世界的可能。

感谢张狗剩同志 https://x.com/goshenggo 提供的建议和反馈。

## ✨ 项目优势

- 🚀 **小 VPS 可运行**：1 核 CPU、1GB 内存的基础 VPS 通常即可运行。
- 🧩 **多协议管理**：同一台 VPS 可同时运行多个 sing-box 协议。
- 🔌 **协议独立控制**：每个协议可单独安装、开启、关闭、重启。
- 👥 **多用户管理**：支持添加、删除、开启、关闭不同用户。
- 📱 **链接和二维码**：自动生成客户端导入链接和二维码。
- 📋 **日志管理**：集中查看全部日志，支持一键复制。
- 🔄 **内核更新**：可检测 sing-box 新版本并在线更新。
- 🛡️ **登录保护**：随机登录路径、验证码、登录失败限制。
- 🌐 **默认 80 端口**：减少新手放行随机端口的难度。

## 🧱 推荐配置

- CPU：1 核起
- 内存：1GB 起
- 硬盘：10GB 以上
- 系统：Ubuntu 22.04 / Ubuntu 24.04 / Debian 12
- 权限：root 用户

## 📦 支持协议

- VLESS + REALITY + Vision
- Hysteria2
- AnyTLS
- VLESS + gRPC + REALITY
- TUIC

不同客户端对协议支持不同，如果导入失败，可以换一个客户端测试。

## 🚀 安装方式一：一键远程安装（推荐）

适合不会使用 SSH 命令的新手。

访问在线安装页面：

[https://ssh.iwantrun.com/](https://ssh.iwantrun.com/)

使用方法：

1. 购买一台全新的 VPS，推荐 Ubuntu 22.04 或 Debian 12。
2. 在 VPS 服务商后台找到服务器 IP、SSH 用户名、SSH 密码或 SSH 私钥。
3. 打开在线安装页面，填写服务器信息。
4. 点击“立即安装到服务器”。
5. 页面会实时显示安装终端日志。
6. 安装完成后，页面会显示面板访问地址、管理员账号和管理员密码。
7. 如果访问地址打不开，请到 VPS 服务商后台防火墙或安全组确认 `80/TCP` 已放行。

## 🖥️ 安装方式二：自行安装

适合熟悉 SSH 的用户。

Windows 可以使用：

- Xshell
- FinalShell
- PuTTY
- Termius

macOS 可以使用系统自带“终端”：

```bash
ssh root@你的服务器IP
```

登录 VPS 后执行下面任意一个安装命令。

### 使用 wget 安装

```bash
wget -O install-webui.sh https://raw.githubusercontent.com/iwantruncom/iwantrun.com-VPN-Web-Manager/main/install-webui.sh && chmod +x install-webui.sh && bash install-webui.sh
```

### 使用 curl 安装

如果服务器没有 `wget`，可以使用：

```bash
curl -L -o install-webui.sh https://raw.githubusercontent.com/iwantruncom/iwantrun.com-VPN-Web-Manager/main/install-webui.sh && chmod +x install-webui.sh && bash install-webui.sh
```

安装完成后终端会显示：

```text
访问地址：http://服务器IP/login-随机字符
管理员账号：admin
管理员密码：随机生成密码
sing-box：sing-box version ...
请确认 VPS 后台防火墙 / 安全组已放行：80/TCP
```

请保存好访问地址、管理员账号和管理员密码。

## 🧭 面板功能

### 📊 面板信息

查看 CPU 使用率、协议数量、用户数量、sing-box 版本、实时网络流量、节点状态和当前开放端口。

### 🧩 协议管理

安装、开启、关闭、重启协议，查看端口和服务状态，复制用户链接，查看二维码，更新 sing-box 内核。

### 👥 用户管理

添加用户、选择协议、自定义密码或随机密码，单独开启/关闭用户，删除无效用户。

### 📋 日志管理

集中查看协议日志、系统日志和诊断信息，支持复制日志，方便反馈问题。

### ⚙️ 系统设置

修改管理员账号密码、修改 Web 面板端口、卸载 Web 面板、卸载全部服务。

## 🔥 防火墙提醒

安装脚本会尝试自动放行服务器系统内部防火墙端口，但很多 VPS 服务商还有独立防火墙或安全组。

如果无法访问面板或客户端无法连接，请检查：

- Web 面板端口：`80/TCP`
- 协议端口：在面板“端口状态”页面查看
- TCP 协议放行 TCP
- UDP 协议放行 UDP

## 📱 客户端建议

- iPhone / iPad：Shadowrocket、Streisand、Hiddify
- Android：v2rayNG、Hiddify、NekoBox
- Windows：v2rayNG、Hiddify、NekoRay
- macOS：v2rayNG、Hiddify、Streisand

## ❓ 常见问题

### 安装完成后网页打不开

检查 VPS 服务商后台防火墙或安全组是否放行 `80/TCP`。

### 客户端无法连接

检查协议端口是否放行、TCP/UDP 类型是否正确、协议服务是否运行、客户端是否支持该协议。

### sing-box 最新版本获取失败

服务器需要能访问 GitHub Release。可以在 VPS 上测试：

```bash
curl -4 -I https://github.com/SagerNet/sing-box/releases/latest
```

## 📁 目录说明

```text
app/                  Web 面板主程序
app/templates/        页面模板
app/static/           CSS 和 JavaScript 静态文件
install-webui.sh      一键安装脚本
requirements.txt      Python 依赖
```
