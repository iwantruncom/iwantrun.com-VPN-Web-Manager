import subprocess,time,json,platform,tarfile,shutil,re
from pathlib import Path
from urllib.request import urlopen
import psutil
WEB_SETTINGS=Path('/etc/freedom-vpn/web/settings.json')
SERVICE_FILE=Path('/etc/systemd/system/iwantrun-vpn-web.service')
APP_DIR=Path('/opt/iwantrun-vpn-webui')
SB_BIN=Path('/usr/local/bin/sing-box')
DEFAULT_SB_VER='1.13.12'
def run_cmd(cmd,timeout=20):
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout); return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e: return 1,'',str(e)
def fmt_bytes(num):
    for u in ['B','KB','MB','GB','TB']:
        if num<1024: return f'{num:.1f} {u}'
        num/=1024
    return f'{num:.1f} PB'
def system_stats():
    cpu=psutil.cpu_percent(interval=0.2); mem=psutil.virtual_memory(); disk=psutil.disk_usage('/')
    return {'cpu_percent':round(cpu,1),'mem_used':fmt_bytes(mem.used),'mem_total':fmt_bytes(mem.total),'mem_percent':round(mem.percent,1),'disk_used':fmt_bytes(disk.used),'disk_total':fmt_bytes(disk.total),'disk_percent':round(disk.percent,1)}
_last={'t':time.time(),'sent':psutil.net_io_counters().bytes_sent,'recv':psutil.net_io_counters().bytes_recv}
def network_stats():
    global _last; now=time.time(); c=psutil.net_io_counters(); dt=max(now-_last['t'],0.1); up=max((c.bytes_sent-_last['sent'])/dt,0); down=max((c.bytes_recv-_last['recv'])/dt,0); _last={'t':now,'sent':c.bytes_sent,'recv':c.bytes_recv}; return {'up_speed':fmt_bytes(up)+'/s','down_speed':fmt_bytes(down)+'/s','total_sent':fmt_bytes(c.bytes_sent),'total_recv':fmt_bytes(c.bytes_recv)}
def service_status(s):
    code,out,_=run_cmd(['systemctl','is-active',s],5); return '运行中' if code==0 else '未运行'
def singbox_version():
    for p in ['/usr/local/bin/sing-box','sing-box']:
        code,out,_=run_cmd([p,'version'],5)
        if code==0 and out: return out.splitlines()[0]
    return '未安装'
def parse_singbox_version(text):
    m=re.search(r'(\d+\.\d+\.\d+)',text or '')
    return m.group(1) if m else ''
def version_tuple(ver):
    try: return tuple(int(x) for x in ver.split('.'))
    except Exception: return (0,0,0)
def safe_extract(tar,tmp):
    base=tmp.resolve()
    for member in tar.getmembers():
        target=(tmp/member.name).resolve()
        if base not in target.parents and target!=base:
            raise RuntimeError('压缩包包含不安全路径')
    tar.extractall(tmp)
def list_open_ports():
    code,out,_=run_cmd(['ss','-lntup'],10); ports=[]
    if code!=0: return ports
    for line in out.splitlines()[1:]:
        parts=line.split(); proto=parts[0].upper(); local=parts[4] if len(parts)>4 else ''
        if ':' in local:
            port=local.rsplit(':',1)[-1]
            if port.isdigit():
                item=f"{port}/{'UDP' if proto=='UDP' else 'TCP'}"
                if item not in ports: ports.append(item)
    return sorted(ports,key=lambda x:(int(x.split('/')[0]),x.split('/')[1]))
def _which(n):
    from shutil import which
    return which(n)
def open_port(port,proto):
    proto=proto.lower()
    if proto not in ('tcp','udp'): return False,'协议只能是 TCP 或 UDP'
    if port<1 or port>65535: return False,'端口范围必须是 1-65535'
    if _which('ufw'): run_cmd(['ufw','allow',f'{port}/{proto}'],15)
    if _which('firewall-cmd'): run_cmd(['firewall-cmd','--permanent',f'--add-port={port}/{proto}'],15); run_cmd(['firewall-cmd','--reload'],15)
    return True,f'已尝试放行 {port}/{proto.upper()}'
def panel_port():
    try: return int(json.loads(WEB_SETTINGS.read_text()).get('panel_port'))
    except Exception: return None
def web_settings():
    try: return json.loads(WEB_SETTINGS.read_text())
    except Exception: return {}
def login_path():
    path=str(web_settings().get('login_path','login')).strip().strip('/')
    return path or 'login'
def write_panel_settings(port):
    WEB_SETTINGS.parent.mkdir(parents=True,exist_ok=True)
    data={}
    if WEB_SETTINGS.exists():
        try: data=json.loads(WEB_SETTINGS.read_text())
        except Exception: data={}
    data['panel_port']=int(port); data.setdefault('login_path','login'); data.setdefault('panel_name','自由档案馆 VPN Web Manager')
    WEB_SETTINGS.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def write_panel_service(port):
    SERVICE_FILE.write_text(f'''[Unit]\nDescription=iwantrun VPN Web Manager\nAfter=network.target\n[Service]\nUser=root\nWorkingDirectory={APP_DIR}\nExecStart={APP_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port {port}\nRestart=on-failure\nRestartSec=3\n[Install]\nWantedBy=multi-user.target\n''')
def delayed_command(cmd):
    subprocess.Popen(['bash','-lc',f'sleep 1; {cmd}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def delayed_commands(commands):
    script='sleep 1\n'+'\n'.join(commands)
    subprocess.Popen(['bash','-lc',script],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def change_panel_port(port):
    if port<1 or port>65535: return False,'端口范围必须是 1-65535'
    if port==22: return False,'不能使用 SSH 端口 22'
    write_panel_settings(port); write_panel_service(port); open_port(port,'tcp')
    run_cmd(['systemctl','daemon-reload'],10); run_cmd(['systemctl','enable','iwantrun-vpn-web'],10)
    delayed_command('systemctl restart iwantrun-vpn-web')
    return True,f'Web 面板端口已修改为 {port}/TCP，服务正在重启'
def uninstall_web_panel():
    delayed_commands([
        'systemctl stop iwantrun-vpn-web 2>/dev/null || true',
        'systemctl disable iwantrun-vpn-web 2>/dev/null || true',
        'rm -f /etc/systemd/system/iwantrun-vpn-web.service',
        'systemctl daemon-reload',
        'rm -rf /opt/iwantrun-vpn-webui',
        'rm -rf /etc/freedom-vpn/web',
    ])
    return True,'Web 面板卸载任务已开始'
def uninstall_all_services():
    delayed_commands([
        'systemctl stop sing-box-vless sing-box-hysteria2 sing-box-anytls sing-box-grpc-reality sing-box-tuic 2>/dev/null || true',
        'systemctl disable sing-box-vless sing-box-hysteria2 sing-box-anytls sing-box-grpc-reality sing-box-tuic 2>/dev/null || true',
        'systemctl stop iwantrun-vpn-web 2>/dev/null || true',
        'systemctl disable iwantrun-vpn-web 2>/dev/null || true',
        'rm -f /etc/systemd/system/sing-box-vless.service /etc/systemd/system/sing-box-hysteria2.service /etc/systemd/system/sing-box-anytls.service /etc/systemd/system/sing-box-grpc-reality.service /etc/systemd/system/sing-box-tuic.service /etc/systemd/system/iwantrun-vpn-web.service',
        'systemctl daemon-reload',
        'rm -rf /opt/iwantrun-vpn-webui /etc/freedom-vpn',
        'rm -f /usr/local/bin/sing-box',
    ])
    return True,'全部服务卸载任务已开始'
def detect_arch():
    m=platform.machine().lower()
    if m in ('x86_64','amd64'): return 'amd64'
    if m in ('aarch64','arm64'): return 'arm64'
    raise RuntimeError(f'暂不支持当前架构：{m}')
def latest_singbox_version():
    try:
        with urlopen('https://api.github.com/repos/SagerNet/sing-box/releases/latest',timeout=10) as r:
            tag=json.loads(r.read().decode()).get('tag_name','')
            return tag.lstrip('v') or DEFAULT_SB_VER
    except Exception:
        return DEFAULT_SB_VER
def singbox_update_info():
    current_text=singbox_version()
    current=parse_singbox_version(current_text)
    latest=latest_singbox_version()
    available=bool(current and latest and version_tuple(latest)>version_tuple(current))
    return {'current_text':current_text,'current_version':current,'latest_version':latest,'update_available':available}
def update_singbox_core():
    info=singbox_update_info()
    if info['current_version'] and info['latest_version'] and not info['update_available']:
        return True,f"当前已是最新版本 v{info['current_version']}"
    arch=detect_arch(); ver=info['latest_version'] or latest_singbox_version(); url=f'https://github.com/SagerNet/sing-box/releases/download/v{ver}/sing-box-{ver}-linux-{arch}.tar.gz'
    tmp=Path('/tmp/sing-box-web-update'); shutil.rmtree(tmp,ignore_errors=True); tmp.mkdir(parents=True,exist_ok=True)
    archive=tmp/'sb.tar.gz'
    code,out,err=run_cmd(['curl','-4fL','--connect-timeout','15','--retry','3','-o',str(archive),url],120)
    if code!=0: return False,f'下载 sing-box 失败：{err or out}'
    try:
        with tarfile.open(archive,'r:gz') as t:
            safe_extract(t,tmp)
        found=next(tmp.rglob('sing-box'),None)
        if not found: return False,'解压后未找到 sing-box 可执行文件'
        test_bin=tmp/'sing-box'
        shutil.copy2(found,test_bin); test_bin.chmod(0o755)
        code,out,err=run_cmd([str(test_bin),'version'],10)
        if code!=0: return False,f'新 sing-box 无法运行：{err or out}'
        backup=None
        if SB_BIN.exists():
            backup=SB_BIN.with_name(f'sing-box.bak.{int(time.time())}')
            shutil.copy2(SB_BIN,backup)
        shutil.move(str(test_bin),str(SB_BIN)); SB_BIN.chmod(0o755)
        run_cmd(['systemctl','restart','sing-box-vless'],20); run_cmd(['systemctl','restart','sing-box-hysteria2'],20); run_cmd(['systemctl','restart','sing-box-anytls'],20); run_cmd(['systemctl','restart','sing-box-grpc-reality'],20); run_cmd(['systemctl','restart','sing-box-tuic'],20)
        return True,f'sing-box 已更新到 v{ver}' + (f'，旧版本已备份到 {backup}' if backup else '')
    finally:
        shutil.rmtree(tmp,ignore_errors=True)
def journal(service_name=None,lines=200):
    cmd=['journalctl','-n',str(lines),'--no-pager'] if not service_name else ['journalctl','-u',service_name,'-n',str(lines),'--no-pager']
    code,out,err=run_cmd(cmd,15); return out or err or '暂无日志'
def diagnostic(rows):
    _,osrel,_=run_cmd(['bash','-lc','cat /etc/os-release | head -n 6'],5)
    s=['===== iwantrun VPN 诊断信息 =====',osrel,'',f'sing-box 版本：{singbox_version()}','','===== 协议状态 =====']
    for p in rows: s.append(f"{p['protocol_name']} | service={p['service_name']} | port={p['port']}/{p['port_type']} | status={service_status(p['service_name'])}")
    s+=['','===== 开放端口 =====',', '.join(list_open_ports()),'','===== 系统最近日志 =====',journal(None,80)]
    return '\n'.join(s)
def all_logs(rows):
    s=[diagnostic(rows),'','===== Web 面板日志 =====',journal('iwantrun-vpn-web',120),'','===== 协议服务日志 =====']
    for p in rows:
        s.append(f"\n===== {p['protocol_name']} / {p['service_name']} =====")
        s.append(journal(p['service_name'],120))
    s+=['','===== 系统日志 =====',journal(None,120)]
    return '\n'.join(s)
