import sqlite3
from pathlib import Path
from datetime import datetime
from passlib.hash import bcrypt
DB_PATH = Path('/etc/freedom-vpn/web/panel.db')
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
PROTOCOLS = [
 ('vless-reality','VLESS + REALITY + Vision','sing-box-vless','TCP'),
 ('hysteria2','Hysteria2','sing-box-hysteria2','UDP'),
 ('anytls','AnyTLS','sing-box-anytls','TCP'),
 ('grpc-reality','VLESS + gRPC + REALITY','sing-box-grpc-reality','TCP'),
 ('tuic','TUIC','sing-box-tuic','UDP'),
]
def connect():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; return con
def init_db():
    con=connect(); cur=con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS protocols (id INTEGER PRIMARY KEY AUTOINCREMENT, protocol_key TEXT NOT NULL UNIQUE, protocol_name TEXT NOT NULL, service_name TEXT NOT NULL, config_path TEXT, info_path TEXT, port INTEGER, port_type TEXT, installed INTEGER DEFAULT 0, enabled INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, protocol_key TEXT NOT NULL, enabled INTEGER DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT, UNIQUE(username, protocol_key));
    CREATE TABLE IF NOT EXISTS operation_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target TEXT, result TEXT, message TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS login_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ip TEXT, success INTEGER, message TEXT, created_at TEXT NOT NULL);
    """)
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for key,name,service,port_type in PROTOCOLS:
        cur.execute("""INSERT OR IGNORE INTO protocols (protocol_key,protocol_name,service_name,config_path,info_path,port_type,installed,enabled,created_at) VALUES (?,?,?,?,?,?,0,0,?)""",(key,name,service,f'/etc/freedom-vpn/protocols/{key}/config.json',f'/etc/freedom-vpn/protocols/{key}/info.json',port_type,now))
    con.commit(); con.close()
def create_admin(username,password):
    init_db(); con=connect(); now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'); h=bcrypt.hash(password[:72])
    con.execute("""INSERT OR REPLACE INTO admins (id,username,password_hash,created_at,updated_at) VALUES ((SELECT id FROM admins WHERE username=?),?,?,COALESCE((SELECT created_at FROM admins WHERE username=?),?),?)""",(username,username,h,username,now,now))
    con.commit(); con.close()
def verify_admin(username,password):
    con=connect(); row=con.execute('SELECT * FROM admins WHERE username=?',(username,)).fetchone(); con.close(); return bool(row and bcrypt.verify(password[:72],row['password_hash']))
def log_action(action,target='',result='ok',message=''):
    con=connect(); con.execute('INSERT INTO operation_logs(action,target,result,message,created_at) VALUES (?,?,?,?,?)',(action,target,result,message,datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); con.commit(); con.close()
