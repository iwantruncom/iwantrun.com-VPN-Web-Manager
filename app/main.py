import os,sys,io,time,secrets,hmac,re
from urllib.parse import quote
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI,Request,Form
from fastapi.responses import RedirectResponse,JSONResponse,StreamingResponse,PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer,BadSignature
import qrcode
from PIL import Image,ImageDraw,ImageFont
from .db import init_db,create_admin,verify_admin,connect,log_action
from . import system_ops,protocol_installer
BASE_DIR=Path(__file__).resolve().parent
SECRET_FILE=Path('/etc/freedom-vpn/web/session.secret'); SECRET_FILE.parent.mkdir(parents=True,exist_ok=True)
if not SECRET_FILE.exists(): SECRET_FILE.write_text(os.urandom(32).hex())
serializer=URLSafeSerializer(SECRET_FILE.read_text().strip(),salt='iwantrun-vpn-web')
app=FastAPI(title='iwantrun VPN Web Manager'); templates=Jinja2Templates(directory=str(BASE_DIR/'templates')); app.mount('/static',StaticFiles(directory=str(BASE_DIR/'static')),name='static')
SESSION_MAX_AGE=86400
LOGIN_WINDOW=600
LOGIN_MAX_FAILURES=8
USERNAME_RE=re.compile(r'^[A-Za-z0-9_]{1,32}$')
CAPTCHA_MAX_AGE=300
def current_session(request):
    c=request.cookies.get('ivpn_session')
    if not c: return None
    try: data=serializer.loads(c)
    except BadSignature: return None
    if int(time.time())-int(data.get('iat',0))>SESSION_MAX_AGE: return None
    return data
def current_user(request):
    data=current_session(request)
    return data.get('username') if data else None
def require_login(request): return RedirectResponse(login_url(),302) if not current_user(request) else None
def csrf_token(request):
    data=current_session(request) or {}
    return data.get('csrf','')
def csrf_ok(request,token):
    expected=csrf_token(request)
    return bool(expected and token and hmac.compare_digest(expected,token))
def csrf_redirect(request,token,path='/'):
    return None if csrf_ok(request,token) else RedirectResponse(path,302)
def login_blocked(ip):
    cutoff=datetime.fromtimestamp(time.time()-LOGIN_WINDOW).strftime('%Y-%m-%d %H:%M:%S')
    con=connect()
    count=con.execute('SELECT COUNT(*) FROM login_logs WHERE ip=? AND success=0 AND created_at>=?',(ip,cutoff)).fetchone()[0]
    con.close()
    return count>=LOGIN_MAX_FAILURES
def record_login_failure(ip,message='login failed'):
    con=connect()
    con.execute('INSERT INTO login_logs(username,ip,success,message,created_at) VALUES (?,?,?,?,?)',('',ip,0,message,datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    con.commit()
    con.close()
def record_login(username,ip,success,message='login'):
    con=connect()
    con.execute('INSERT INTO login_logs(username,ip,success,message,created_at) VALUES (?,?,?,?,?)',(username,ip,1 if success else 0,message,datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    con.commit()
    con.close()
def protocol_rows():
    con=connect()
    rows=con.execute('SELECT * FROM protocols ORDER BY id').fetchall()
    con.close()
    return [dict(r) for r in rows]
def user_count():
    con=connect()
    count=con.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    con.close()
    return count
def redirect_with_message(path,msg='',error=''):
    params=[]
    if msg: params.append('msg='+quote(msg))
    if error: params.append('error='+quote(error))
    return RedirectResponse(path+('?'+'&'.join(params) if params else ''),302)
def login_url():
    return '/' + system_ops.login_path()
def captcha_text():
    alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(5))
def captcha_cookie(text):
    return serializer.dumps({'captcha':text.lower(),'iat':int(time.time())})
def captcha_from_cookie(request):
    c=request.cookies.get('ivpn_captcha')
    if not c: return ''
    try: data=serializer.loads(c)
    except BadSignature: return ''
    if int(time.time())-int(data.get('iat',0))>CAPTCHA_MAX_AGE: return ''
    return str(data.get('captcha','')).upper()
def captcha_ok(request,answer):
    c=request.cookies.get('ivpn_captcha')
    if not c or not answer: return False
    try: data=serializer.loads(c)
    except BadSignature: return False
    if int(time.time())-int(data.get('iat',0))>CAPTCHA_MAX_AGE: return False
    return hmac.compare_digest(str(data.get('captcha','')).lower(),answer.strip().lower())
def render_captcha(text):
    img=Image.new('RGB',(150,52),(248,250,252)); draw=ImageDraw.Draw(img)
    for _ in range(12):
        x1=secrets.randbelow(150); y1=secrets.randbelow(52); x2=secrets.randbelow(150); y2=secrets.randbelow(52)
        draw.line((x1,y1,x2,y2),fill=(203,213,225),width=1)
    try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',30)
    except Exception: font=ImageFont.load_default()
    for i,ch in enumerate(text):
        draw.text((16+i*24,secrets.randbelow(10)+8),ch,font=font,fill=(30,41,59))
    buf=io.BytesIO(); img.save(buf,format='PNG'); buf.seek(0); return buf
def login_template(request,error=''):
    text=captcha_text()
    resp=templates.TemplateResponse('login.html',{'request':request,'error':error,'login_path':login_url()})
    resp.set_cookie('ivpn_captcha',captcha_cookie(text),httponly=True,samesite='lax',max_age=CAPTCHA_MAX_AGE,secure=request.url.scheme=='https')
    resp.delete_cookie('ivpn_captcha_text')
    return resp
@app.on_event('startup')
def startup(): init_db()
@app.get('/login')
def old_login_page(): return PlainTextResponse('Not Found',404)
@app.get('/captcha.png')
def captcha_image(request:Request):
    text=captcha_from_cookie(request) or captcha_text()
    return StreamingResponse(render_captcha(text),media_type='image/png')
@app.get('/logout')
def logout(): resp=RedirectResponse(login_url(),302); resp.delete_cookie('ivpn_session'); return resp
@app.get('/api/dashboard')
def api_dashboard(request:Request):
    if not current_user(request): return JSONResponse({'error':'unauthorized'},401)
    protocols=[
        {**p,'runtime_status':system_ops.service_status(p['service_name'])}
        for p in protocol_rows()
    ]
    return {
        'stats':system_ops.system_stats(),
        'net':system_ops.network_stats(),
        'singbox_version':system_ops.singbox_version(),
        'open_ports':system_ops.list_open_ports(),
        'protocols':protocols,
    }
@app.get('/')
def dashboard(request:Request):
    auth=require_login(request)
    if auth: return auth
    protocols=protocol_rows()
    status={p['protocol_key']:system_ops.service_status(p['service_name']) for p in protocols}
    return templates.TemplateResponse('dashboard.html',{
        'request':request,
        'active':'home',
        'csrf_token':csrf_token(request),
        'stats':system_ops.system_stats(),
        'net':system_ops.network_stats(),
        'protocols':protocols,
        'status':status,
        'installed':[p for p in protocols if p['installed']],
        'user_count':user_count(),
        'singbox_version':system_ops.singbox_version(),
        'open_ports':system_ops.list_open_ports(),
    })
@app.get('/protocols')
def protocols_page(request:Request):
    auth=require_login(request)
    if auth: return auth
    protocols=protocol_rows()
    links={
        p['protocol_key']:protocol_installer.protocol_links(p['protocol_key']) if p['installed'] else []
        for p in protocols
    }
    status={p['protocol_key']:system_ops.service_status(p['service_name']) for p in protocols}
    return templates.TemplateResponse('protocols.html',{
        'request':request,
        'active':'protocols',
        'csrf_token':csrf_token(request),
        'protocols':protocols,
        'links':links,
        'status':status,
        'msg':request.query_params.get('msg',''),
        'error':request.query_params.get('error',''),
        'singbox_version':system_ops.singbox_version(),
        'singbox_update':system_ops.singbox_update_info(),
        'service_status':system_ops.service_status,
    })
@app.post('/protocols/core/update')
def update_core(request:Request,csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/protocols')
    if bad_csrf: return bad_csrf
    ok,msg=system_ops.update_singbox_core(); log_action('update sing-box core','sing-box','ok' if ok else 'error',msg)
    return redirect_with_message('/protocols',msg=msg if ok else '',error='' if ok else msg)
@app.post('/protocols/{protocol_key}/{action}')
def protocol_action(request:Request,protocol_key:str,action:str,csrf_token_value:str=Form(...,alias='csrf_token'),username:str=Form('',alias='username'),password:str=Form('',alias='password')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/protocols')
    if bad_csrf: return bad_csrf
    con=connect(); p=con.execute('SELECT * FROM protocols WHERE protocol_key=?',(protocol_key,)).fetchone(); con.close()
    if not p: return redirect_with_message('/protocols',error='协议不存在')
    try:
        if action=='install':
            protocol_installer.install_protocol(protocol_key,username,password)
            return redirect_with_message('/protocols',msg=f"{p['protocol_name']} 安装成功，已生成用户 {username}")
        elif action=='toggle':
            current=system_ops.service_status(p['service_name'])
            cmd='stop' if current=='运行中' else 'start'
            code,out,err=system_ops.run_cmd(['systemctl',cmd,p['service_name']],20)
            ok=code==0
            log_action(cmd,p['service_name'],'ok' if ok else 'error',out or err)
            if not ok: return redirect_with_message('/protocols',error=f"{p['protocol_name']} {'关闭' if cmd=='stop' else '开启'}失败：{err or out}")
            return redirect_with_message('/protocols',msg=f"{p['protocol_name']} 已{'关闭' if cmd=='stop' else '开启'}")
        elif action=='restart':
            code,out,err=system_ops.run_cmd(['systemctl','restart',p['service_name']],20)
            ok=code==0
            log_action(action,p['service_name'],'ok' if ok else 'error',out or err)
            if not ok: return redirect_with_message('/protocols',error=f"{p['protocol_name']} 重启失败：{err or out}")
            return redirect_with_message('/protocols',msg=f"{p['protocol_name']} 重启成功")
    except Exception as e:
        log_action(action,protocol_key,'error',str(e))
        return redirect_with_message('/protocols',error=f"{p['protocol_name']} 操作失败：{e}")
    return redirect_with_message('/protocols',error='未知操作')
@app.get('/protocols/{protocol_key}/qr/{username}')
def qr(request:Request,protocol_key:str,username:str):
    auth=require_login(request)
    if auth: return auth
    for item in protocol_installer.protocol_links(protocol_key):
        if item['name']==username:
            img=qrcode.make(item['link']); buf=io.BytesIO(); img.save(buf,format='PNG'); buf.seek(0); return StreamingResponse(buf,media_type='image/png')
    return JSONResponse({'error':'not found'},404)
@app.get('/users')
def users_page(request:Request):
    auth=require_login(request)
    if auth: return auth
    con=connect()
    users=con.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
    protocols=con.execute('SELECT * FROM protocols ORDER BY id').fetchall()
    con.close()
    return templates.TemplateResponse('users.html',{
        'request':request,
        'active':'users',
        'csrf_token':csrf_token(request),
        'users':users,
        'protocols':protocols,
        'msg':request.query_params.get('msg',''),
        'error':request.query_params.get('error',''),
    })
@app.post('/users/add')
def users_add(request:Request,username:str=Form(...),protocol_key:str=Form(...),password:str=Form('',alias='password'),csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/users')
    if bad_csrf: return bad_csrf
    if not USERNAME_RE.match(username):
        log_action('add user',f'{protocol_key}:{username}','error','invalid username')
        return RedirectResponse('/users',302)
    try:
        protocol_installer.add_user_to_protocol(protocol_key,username,password); log_action('add user',f'{protocol_key}:{username}')
        return redirect_with_message('/users',msg=f'用户 {username} 添加成功')
    except Exception as e:
        log_action('add user',f'{protocol_key}:{username}','error',str(e))
        return redirect_with_message('/users',error=f'添加用户失败：{e}')
@app.post('/users/{user_id}/toggle')
def users_toggle(request:Request,user_id:int,csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/users')
    if bad_csrf: return bad_csrf
    con=connect(); u=con.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); con.close()
    if not u: return redirect_with_message('/users',error='用户不存在')
    enable=not bool(u['enabled'])
    try:
        protocol_installer.set_user_enabled(u['protocol_key'],u['username'],enable); log_action('toggle user',f"{u['protocol_key']}:{u['username']}",'ok','enabled' if enable else 'disabled')
        return redirect_with_message('/users',msg=f"用户 {u['username']} 已{'开启' if enable else '关闭'}")
    except Exception as e:
        log_action('toggle user',str(user_id),'error',str(e))
        return redirect_with_message('/users',error=f"用户 {u['username']} {'开启' if enable else '关闭'}失败：{e}")
@app.post('/users/{user_id}/delete')
def users_delete(request:Request,user_id:int,csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/users')
    if bad_csrf: return bad_csrf
    con=connect(); u=con.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone(); con.close()
    if u:
        try:
            protocol_installer.delete_user_from_protocol(u['protocol_key'],u['username']); log_action('delete user',f"{u['protocol_key']}:{u['username']}")
            return redirect_with_message('/users',msg=f"用户 {u['username']} 已删除")
        except Exception as e:
            log_action('delete user',str(user_id),'error',str(e))
            return redirect_with_message('/users',error=f"删除用户失败：{e}")
    return redirect_with_message('/users',error='用户不存在')
@app.get('/firewall')
def firewall_page(request:Request):
    auth=require_login(request)
    if auth: return auth
    return templates.TemplateResponse('firewall.html',{
        'request':request,
        'active':'firewall',
        'csrf_token':csrf_token(request),
        'ports':system_ops.list_open_ports(),
        'protocols':protocol_rows(),
        'panel_port':system_ops.panel_port(),
    })
@app.get('/logs')
def logs_page(request:Request):
    auth=require_login(request)
    if auth: return auth
    protocols=protocol_rows()
    return templates.TemplateResponse('logs.html',{'request':request,'active':'logs','title':'全部日志','content':system_ops.all_logs(protocols)})
@app.get('/settings')
def settings_page(request:Request):
    auth=require_login(request)
    if auth: return auth
    return templates.TemplateResponse('settings.html',{
        'request':request,
        'active':'settings',
        'csrf_token':csrf_token(request),
        'panel_port':system_ops.panel_port(),
        'msg':request.query_params.get('msg',''),
        'error':request.query_params.get('error',''),
    })
@app.post('/settings/password')
def change_password(request:Request,username:str=Form(...),password:str=Form(...),csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/settings')
    if bad_csrf: return bad_csrf
    create_admin(username,password); return redirect_with_message('/settings',msg='管理员密码已更新')
@app.post('/settings/port')
def change_port(request:Request,port:int=Form(...),csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/settings')
    if bad_csrf: return bad_csrf
    ok,msg=system_ops.change_panel_port(port); log_action('change panel port',str(port),'ok' if ok else 'error',msg)
    return redirect_with_message('/settings',msg=msg if ok else '',error='' if ok else msg)
@app.post('/settings/uninstall-web')
def uninstall_web(request:Request,csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/settings')
    if bad_csrf: return bad_csrf
    ok,msg=system_ops.uninstall_web_panel()
    log_action('uninstall web panel','iwantrun-vpn-web','ok' if ok else 'error',msg)
    return templates.TemplateResponse('settings.html',{
        'request':request,
        'active':'settings',
        'csrf_token':csrf_token(request),
        'panel_port':system_ops.panel_port(),
        'msg':msg,
        'error':'' if ok else msg,
    })
@app.post('/settings/uninstall-all')
def uninstall_all(request:Request,csrf_token_value:str=Form(...,alias='csrf_token')):
    auth=require_login(request)
    if auth: return auth
    bad_csrf=csrf_redirect(request,csrf_token_value,'/settings')
    if bad_csrf: return bad_csrf
    ok,msg=system_ops.uninstall_all_services()
    log_action('uninstall all','all services','ok' if ok else 'error',msg)
    return templates.TemplateResponse('settings.html',{
        'request':request,
        'active':'settings',
        'csrf_token':csrf_token(request),
        'panel_port':system_ops.panel_port(),
        'msg':msg,
        'error':'' if ok else msg,
    })
@app.get('/{path_name}')
def login_page(request:Request,path_name:str):
    if path_name != system_ops.login_path(): return PlainTextResponse('Not Found',404)
    return login_template(request)
@app.post('/{path_name}')
def login(request:Request,path_name:str,username:str=Form(...),password:str=Form(...),captcha:str=Form(...)):
    if path_name != system_ops.login_path(): return PlainTextResponse('Not Found',404)
    ip=request.client.host if request.client else ''
    if login_blocked(ip):
        return login_template(request,'登录失败次数过多，请 10 分钟后再试')
    if not captcha_ok(request,captcha):
        record_login_failure(ip,'captcha failed')
        return login_template(request,'验证码错误，请重新输入')
    ok=verify_admin(username,password)
    record_login(username,ip,ok)
    if not ok:
        return login_template(request,'账号或密码错误')
    session=serializer.dumps({
        'username':username,
        'csrf':secrets.token_urlsafe(32),
        'iat':int(time.time()),
    })
    resp=RedirectResponse('/',302)
    resp.delete_cookie('ivpn_captcha')
    resp.delete_cookie('ivpn_captcha_text')
    resp.set_cookie(
        'ivpn_session',
        session,
        httponly=True,
        samesite='lax',
        max_age=SESSION_MAX_AGE,
        secure=request.url.scheme=='https',
    )
    return resp
if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--init-admin': create_admin(sys.argv[2],sys.argv[3]); print('admin initialized')
