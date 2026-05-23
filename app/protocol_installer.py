import json,secrets,uuid,re
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from .db import connect,log_action
from .system_ops import run_cmd,open_port
SB_BIN='/usr/local/bin/sing-box'; BASE=Path('/etc/freedom-vpn/protocols'); SNI='www.microsoft.com'
NAMES={'vless-reality':'VLESS + REALITY + Vision','hysteria2':'Hysteria2','anytls':'AnyTLS','grpc-reality':'VLESS + gRPC + REALITY','tuic':'TUIC'}
SERVICES={'vless-reality':'sing-box-vless','hysteria2':'sing-box-hysteria2','anytls':'sing-box-anytls','grpc-reality':'sing-box-grpc-reality','tuic':'sing-box-tuic'}
PORT_TYPES={'vless-reality':'TCP','hysteria2':'UDP','anytls':'TCP','grpc-reality':'TCP','tuic':'UDP'}
USERNAME_RE=re.compile(r'^[A-Za-z0-9_]{1,32}$')
def _cmd(cmd,timeout=30):
    code,out,err=run_cmd(cmd,timeout)
    if code!=0: raise RuntimeError(err or out or 'command failed')
    return out
def public_ip():
    code,out,_=run_cmd(['curl','-s4','--max-time','8','https://api.ipify.org'],10); return out.strip() if code==0 and out.strip() else 'SERVER_IP'
def port_free(p):
    code,out,_=run_cmd(['ss','-lntup'],10)
    if code!=0: return True
    return f':{p} ' not in out and f':{p}\n' not in out
def random_port():
    while True:
        p=secrets.randbelow(50000)+10000
        if port_free(p): return p
def write_json(path,data): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def checked_replace_config(key,data):
    config_path=BASE/key/'config.json'
    tmp_path=BASE/key/f'.config.{secrets.token_hex(6)}.tmp'
    write_json(tmp_path,data)
    try:
        _cmd([SB_BIN,'check','-c',str(tmp_path)],20)
        tmp_path.replace(config_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
def cert_pair(d,name,ip):
    cert=d/f'{name}-cert.pem'; key=d/f'{name}-key.pem'
    if not cert.exists() or not key.exists(): _cmd(['openssl','req','-x509','-nodes','-newkey','rsa:2048','-keyout',str(key),'-out',str(cert),'-days','3650','-subj',f'/CN={ip}'],60)
    return cert,key
def reality_keys():
    out=_cmd([SB_BIN,'generate','reality-keypair'],10); priv=pub=''
    for line in out.splitlines():
        if 'Private' in line: priv=line.split()[-1]
        if 'Public' in line: pub=line.split()[-1]
    if not priv or not pub: raise RuntimeError('Reality 密钥生成失败')
    return priv,pub
def create_service(service,config_path):
    Path(f'/etc/systemd/system/{service}.service').write_text(f'''[Unit]\nDescription={service}\nAfter=network.target nss-lookup.target\n\n[Service]\nUser=root\nWorkingDirectory={config_path.parent}\nExecStart={SB_BIN} run -c {config_path}\nRestart=on-failure\nRestartSec=5\nLimitNOFILE=infinity\n\n[Install]\nWantedBy=multi-user.target\n''')
    _cmd(['systemctl','daemon-reload']); _cmd(['systemctl','enable',service])
def make_user(key,username,password=None):
    if not USERNAME_RE.match(username): raise RuntimeError('用户名只能包含英文、数字、下划线，最长 32 位')
    password=password.strip() if password else ''
    if key=='vless-reality': return {'name':username,'uuid':str(uuid.uuid4()),'flow':'xtls-rprx-vision'}
    if key=='grpc-reality': return {'name':username,'uuid':str(uuid.uuid4())}
    if key in ('hysteria2','anytls'): return {'name':username,'password':password or secrets.token_hex(16)}
    if key=='tuic': return {'name':username,'uuid':str(uuid.uuid4()),'password':password or secrets.token_hex(16)}
    raise RuntimeError('未知协议')
def install_protocol(key,username=None,password=None):
    if key not in NAMES: raise RuntimeError('未知协议')
    proto_dir=BASE/key; proto_dir.mkdir(parents=True,exist_ok=True); config_path=proto_dir/'config.json'; info_path=proto_dir/'info.json'
    username=(username or 'user_'+secrets.token_hex(3)).strip()
    first_user=make_user(key,username,password)
    ip=public_ip(); port=random_port(); service=SERVICES[key]; extra={}
    if key=='vless-reality':
        priv,pub=reality_keys(); sid=secrets.token_hex(8); users=[first_user]
        config={'log':{'level':'info','timestamp':True},'inbounds':[{'type':'vless','tag':'vless-reality-in','listen':'::','listen_port':port,'users':users,'tls':{'enabled':True,'server_name':SNI,'reality':{'enabled':True,'handshake':{'server':SNI,'server_port':443},'private_key':priv,'short_id':[sid]}}}],'outbounds':[{'type':'direct','tag':'direct'}]}; extra={'public_key':pub,'short_id':sid,'sni':SNI}
    elif key=='grpc-reality':
        priv,pub=reality_keys(); sid=secrets.token_hex(8); svc='grpc-service'; users=[first_user]
        config={'log':{'level':'info','timestamp':True},'inbounds':[{'type':'vless','tag':'vless-grpc-reality-in','listen':'::','listen_port':port,'users':users,'transport':{'type':'grpc','service_name':svc},'tls':{'enabled':True,'server_name':SNI,'reality':{'enabled':True,'handshake':{'server':SNI,'server_port':443},'private_key':priv,'short_id':[sid]}}}],'outbounds':[{'type':'direct','tag':'direct'}]}; extra={'public_key':pub,'short_id':sid,'sni':SNI,'grpc_service_name':svc}
    elif key=='hysteria2':
        cert,k=cert_pair(proto_dir,'hysteria2',ip); users=[first_user]
        config={'log':{'level':'info','timestamp':True},'inbounds':[{'type':'hysteria2','tag':'hysteria2-in','listen':'::','listen_port':port,'users':users,'tls':{'enabled':True,'certificate_path':str(cert),'key_path':str(k)}}],'outbounds':[{'type':'direct','tag':'direct'}]}
    elif key=='anytls':
        cert,k=cert_pair(proto_dir,'anytls',ip); users=[first_user]
        config={'log':{'level':'info','timestamp':True},'inbounds':[{'type':'anytls','tag':'anytls-in','listen':'::','listen_port':port,'users':users,'tls':{'enabled':True,'certificate_path':str(cert),'key_path':str(k)}}],'outbounds':[{'type':'direct','tag':'direct'}]}; extra={'sni':SNI}
    elif key=='tuic':
        cert,k=cert_pair(proto_dir,'tuic',ip); users=[first_user]
        config={'log':{'level':'info','timestamp':True},'inbounds':[{'type':'tuic','tag':'tuic-in','listen':'::','listen_port':port,'users':users,'congestion_control':'bbr','zero_rtt_handshake':False,'heartbeat':'10s','tls':{'enabled':True,'alpn':['h3'],'certificate_path':str(cert),'key_path':str(k)}}],'outbounds':[{'type':'direct','tag':'direct'}]}; extra={'alpn':'h3'}
    checked_replace_config(key,config); info={'protocol':key,'protocol_name':NAMES[key],'service':service,'server':ip,'port':port,'port_type':PORT_TYPES[key],'created_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),**extra}; write_json(info_path,info)
    create_service(service,config_path); open_port(port,'udp' if PORT_TYPES[key]=='UDP' else 'tcp'); _cmd(['systemctl','restart',service],20)
    con=connect(); now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'); con.execute('UPDATE protocols SET port=?,port_type=?,installed=1,enabled=1,config_path=?,info_path=?,updated_at=? WHERE protocol_key=?',(port,PORT_TYPES[key],str(config_path),str(info_path),now,key)); con.execute('INSERT OR IGNORE INTO users(username,protocol_key,enabled,created_at) VALUES (?,?,1,?)',(username,key,now)); con.commit(); con.close(); log_action('install protocol',key,'ok',f'{port}/{PORT_TYPES[key]}')
def load_info(key):
    p=BASE/key/'info.json'; return json.loads(p.read_text()) if p.exists() else None
def load_config(key):
    p=BASE/key/'config.json'; return json.loads(p.read_text()) if p.exists() else None
def disabled_path(key): return BASE/key/'disabled-users.json'
def load_disabled(key):
    p=disabled_path(key)
    return json.loads(p.read_text()) if p.exists() else {}
def save_disabled(key,data): write_json(disabled_path(key),data)
def restart_protocol_service(key):
    _cmd(['systemctl','restart',SERVICES[key]],20)
def generate_link(key,user):
    info=load_info(key); c=load_config(key)
    if not info or not c: return ''
    server=info.get('server'); port=info.get('port'); name=quote(user.get('name','user'))
    if key=='vless-reality': return f"vless://{user['uuid']}@{server}:{port}?encryption=none&flow=xtls-rprx-vision&security=reality&sni={info.get('sni',SNI)}&fp=chrome&pbk={info.get('public_key')}&sid={info.get('short_id')}&type=tcp#{name}"
    if key=='grpc-reality': return f"vless://{user['uuid']}@{server}:{port}?encryption=none&security=reality&sni={info.get('sni',SNI)}&fp=chrome&pbk={info.get('public_key')}&sid={info.get('short_id')}&type=grpc&serviceName={info.get('grpc_service_name','grpc-service')}#{name}"
    if key=='hysteria2': return f"hysteria2://{user['password']}@{server}:{port}?insecure=1#{name}"
    if key=='anytls': return f"anytls://{user['password']}@{server}:{port}/?sni={info.get('sni',SNI)}&insecure=1#{name}"
    if key=='tuic': return f"tuic://{user['uuid']}:{user['password']}@{server}:{port}?congestion_control=bbr&udp_relay_mode=native&alpn={info.get('alpn','h3')}&allow_insecure=1#{name}"
    return ''
def protocol_links(key):
    c=load_config(key)
    if not c: return []
    return [{'name':u.get('name','user'),'link':generate_link(key,u)} for u in c.get('inbounds',[{}])[0].get('users',[])]
def add_user_to_protocol(key,username,password=None):
    if key not in NAMES: raise RuntimeError('未知协议')
    if not USERNAME_RE.match(username): raise RuntimeError('用户名只能包含英文、数字、下划线，最长 32 位')
    c=load_config(key)
    if not c: raise RuntimeError('协议未安装')
    users=c['inbounds'][0].setdefault('users',[])
    if any(u.get('name')==username for u in users): raise RuntimeError('用户名已存在')
    users.append(make_user(key,username,password))
    checked_replace_config(key,c)
    restart_protocol_service(key)
    con=connect()
    con.execute('INSERT OR IGNORE INTO users(username,protocol_key,enabled,created_at) VALUES (?,?,1,?)',(username,key,datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    con.commit()
    con.close()
def set_user_enabled(key,username,enabled):
    if key not in NAMES: raise RuntimeError('未知协议')
    c=load_config(key)
    if not c: raise RuntimeError('协议未安装')
    users=c['inbounds'][0].setdefault('users',[])
    disabled=load_disabled(key)
    if enabled:
        if any(u.get('name')==username for u in users): raise RuntimeError('用户已经开启')
        user=disabled.pop(username,None)
        if not user: raise RuntimeError('未找到已关闭用户的配置')
        users.append(user)
    else:
        if len(users)<=1: raise RuntimeError('不能关闭最后一个开启中的用户')
        user=next((u for u in users if u.get('name')==username),None)
        if not user: raise RuntimeError('用户未开启或不存在')
        c['inbounds'][0]['users']=[u for u in users if u.get('name')!=username]
        disabled[username]=user
    checked_replace_config(key,c)
    save_disabled(key,disabled)
    restart_protocol_service(key)
    con=connect()
    con.execute('UPDATE users SET enabled=?,updated_at=? WHERE username=? AND protocol_key=?',(1 if enabled else 0,datetime.now().strftime('%Y-%m-%d %H:%M:%S'),username,key))
    con.commit()
    con.close()
def delete_user_from_protocol(key,username):
    if key not in NAMES: raise RuntimeError('未知协议')
    c=load_config(key)
    if not c: raise RuntimeError('协议未安装')
    users=c['inbounds'][0].get('users',[])
    disabled=load_disabled(key)
    if username in disabled:
        disabled.pop(username,None)
        save_disabled(key,disabled)
        con=connect()
        con.execute('DELETE FROM users WHERE username=? AND protocol_key=?',(username,key))
        con.commit()
        con.close()
        return
    if len(users)<=1: raise RuntimeError('不能删除最后一个开启中的用户')
    new_users=[u for u in users if u.get('name')!=username]
    if len(new_users)==len(users): raise RuntimeError('用户不存在')
    c['inbounds'][0]['users']=new_users
    checked_replace_config(key,c)
    save_disabled(key,disabled)
    restart_protocol_service(key)
    con=connect()
    con.execute('DELETE FROM users WHERE username=? AND protocol_key=?',(username,key))
    con.commit()
    con.close()
