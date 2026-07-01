import os
import sqlite3
import bcrypt
from pathlib import Path
from datetime import datetime

# 数据根目录默认 /etc/freedom-vpn，可用 IVPN_DATA_DIR 覆盖（便于本地测试，生产不设即保持原行为）。
DATA_ROOT = Path(os.environ.get('IVPN_DATA_DIR', '/etc/freedom-vpn'))
DB_PATH = DATA_ROOT / 'web' / 'panel.db'
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

PROTOCOLS = [
    ('vless-reality', 'VLESS + REALITY + Vision', 'sing-box-vless', 'TCP'),
    ('hysteria2', 'Hysteria2', 'sing-box-hysteria2', 'UDP'),
    ('anytls', 'AnyTLS', 'sing-box-anytls', 'TCP'),
    ('grpc-reality', 'VLESS + gRPC + REALITY', 'sing-box-grpc-reality', 'TCP'),
    ('tuic', 'TUIC', 'sing-box-tuic', 'UDP'),
]


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    # WAL + busy_timeout 避免多标签轮询与操作并发时出现 "database is locked"。
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=5000')
    return con


def init_db():
    con = connect()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS protocols (id INTEGER PRIMARY KEY AUTOINCREMENT, protocol_key TEXT NOT NULL UNIQUE, protocol_name TEXT NOT NULL, service_name TEXT NOT NULL, config_path TEXT, info_path TEXT, port INTEGER, port_type TEXT, installed INTEGER DEFAULT 0, enabled INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, protocol_key TEXT NOT NULL, enabled INTEGER DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT, UNIQUE(username, protocol_key));
    CREATE TABLE IF NOT EXISTS operation_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target TEXT, result TEXT, message TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS login_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ip TEXT, success INTEGER, message TEXT, created_at TEXT NOT NULL);
    """)
    now = _now()
    for key, name, service, port_type in PROTOCOLS:
        cur.execute(
            'INSERT OR IGNORE INTO protocols (protocol_key,protocol_name,service_name,config_path,info_path,port_type,installed,enabled,created_at) VALUES (?,?,?,?,?,?,0,0,?)',
            (key, name, service, str(DATA_ROOT / 'protocols' / key / 'config.json'), str(DATA_ROOT / 'protocols' / key / 'info.json'), port_type, now),
        )
    con.commit()
    con.close()


def _hash_password(password):
    # bcrypt 只使用前 72 字节，超出部分静默忽略，这里显式截断以保持行为可预期。
    return bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('ascii')


def _check_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode('utf-8')[:72], password_hash.encode('ascii'))
    except (ValueError, TypeError):
        return False


def create_admin(username, password):
    """创建 / 重置管理员。仅安装阶段使用，单管理员模型。"""
    init_db()
    con = connect()
    now = _now()
    h = _hash_password(password)
    con.execute(
        'INSERT INTO admins (username,password_hash,created_at,updated_at) VALUES (?,?,?,?) '
        'ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, updated_at=excluded.updated_at',
        (username, h, now, now),
    )
    con.commit()
    con.close()


def update_admin_password(username, new_password):
    """仅更新指定管理员的密码，不改用户名，避免产生第二个管理员账号。"""
    con = connect()
    con.execute(
        'UPDATE admins SET password_hash=?, updated_at=? WHERE username=?',
        (_hash_password(new_password), _now(), username),
    )
    con.commit()
    con.close()


def verify_admin(username, password):
    con = connect()
    row = con.execute('SELECT * FROM admins WHERE username=?', (username,)).fetchone()
    con.close()
    return bool(row and _check_password(password, row['password_hash']))


def get_setting(key, default=None):
    con = connect()
    row = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    con.close()
    return row['value'] if row else default


def get_session_epoch():
    return int(get_setting('session_epoch', '0'))


def bump_session_epoch():
    """自增会话纪元，使所有已签发的会话立即失效（改密码时调用）。"""
    new_value = str(get_session_epoch() + 1)
    con = connect()
    con.execute(
        "INSERT INTO settings(key,value) VALUES('session_epoch',?) "
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (new_value,),
    )
    con.commit()
    con.close()
    return int(new_value)


def log_action(action, target='', result='ok', message=''):
    con = connect()
    con.execute(
        'INSERT INTO operation_logs(action,target,result,message,created_at) VALUES (?,?,?,?,?)',
        (action, target, result, message, _now()),
    )
    con.commit()
    con.close()
