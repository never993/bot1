import sqlite3, os, secrets, string
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "licenses.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                key        TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                username   TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                active     INTEGER NOT NULL DEFAULT 1
            )
        """)
        c.commit()

def generate_key():
    chars = string.ascii_uppercase + string.digits
    return "SP-" + "".join(secrets.choice(chars) for _ in range(16))

def create_license(user_id: str, username: str, days: int | None) -> str:
    key = generate_key()
    now = datetime.utcnow().isoformat()
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat() if days else None
    with get_conn() as c:
        c.execute(
            "INSERT INTO licenses (key, user_id, username, created_at, expires_at, active) VALUES (?,?,?,?,?,1)",
            (key, user_id, username, now, expires)
        )
        c.commit()
    return key

def revoke_license(key: str) -> bool:
    with get_conn() as c:
        cur = c.execute("UPDATE licenses SET active=0 WHERE key=?", (key,))
        c.commit()
        return cur.rowcount > 0

def get_license(key: str):
    with get_conn() as c:
        return c.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()

def validate_license(key: str) -> dict:
    row = get_license(key)
    if not row:
        return {"valid": False, "reason": "Chave nao encontrada."}
    if not row["active"]:
        return {"valid": False, "reason": "Chave revogada."}
    if row["expires_at"]:
        exp = datetime.fromisoformat(row["expires_at"])
        if datetime.utcnow() > exp:
            return {"valid": False, "reason": "Chave expirada."}
    return {
        "valid":      True,
        "user_id":    row["user_id"],
        "username":   row["username"],
        "expires_at": row["expires_at"],
        "permanent":  row["expires_at"] is None
    }

init_db()
