import os
import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

APP_NAME = "PIT LICENCAS"
DB_PATH = os.getenv("DATABASE_PATH", "data/licencas.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

app = FastAPI(title=APP_NAME, version="1.0.0")


@contextmanager
def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT UNIQUE NOT NULL,
                customer TEXT NOT NULL DEFAULT '',
                duration_days INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                device_id TEXT,
                activated_at TEXT,
                blocked INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen TEXT,
                FOREIGN KEY(license_id) REFERENCES licenses(id)
            )
        """)


@app.on_event("startup")
def startup():
    if not ADMIN_TOKEN:
        raise RuntimeError("Configure ADMIN_TOKEN nas variaveis de ambiente da Discloud.")
    init_db()


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def require_admin(token: str | None):
    if not ADMIN_TOKEN or not token or not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Acesso administrativo nao autorizado.")


class CreateLicense(BaseModel):
    customer: str = Field(default="", max_length=120)
    days: int = Field(ge=1, le=3650)


class ActivateLicense(BaseModel):
    license_key: str = Field(min_length=8, max_length=80)
    device_id: str = Field(min_length=8, max_length=160)


class ValidateLicense(BaseModel):
    token: str = Field(min_length=20, max_length=300)
    device_id: str = Field(min_length=8, max_length=160)


@app.get("/")
def home():
    return {"service": APP_NAME, "status": "online", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/admin/licenses")
def create_license(payload: CreateLicense, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    key = "PIT-" + "-".join(secrets.token_hex(3).upper() for _ in range(3))
    created = now_utc()
    with db() as conn:
        conn.execute(
            "INSERT INTO licenses (license_key, customer, duration_days, created_at) VALUES (?, ?, ?, ?)",
            (key, payload.customer.strip(), payload.days, iso(created)),
        )
    return {"license_key": key, "customer": payload.customer.strip(), "days": payload.days}


@app.post("/activate")
def activate(payload: ActivateLicense):
    current = now_utc()
    with db() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE license_key = ?", (payload.license_key.strip(),)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Licenca nao encontrada.")
        if row["blocked"]:
            raise HTTPException(status_code=403, detail="Licenca bloqueada.")
        if row["device_id"] and row["device_id"] != payload.device_id:
            raise HTTPException(status_code=409, detail="Licenca ja vinculada a outro dispositivo.")
        expires = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else current + timedelta(days=row["duration_days"])
        if current >= expires:
            raise HTTPException(status_code=403, detail="Licenca expirada.")
        conn.execute(
            "UPDATE licenses SET device_id = ?, activated_at = COALESCE(activated_at, ?), expires_at = COALESCE(expires_at, ?) WHERE id = ?",
            (payload.device_id, iso(current), iso(expires), row["id"]),
        )
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        conn.execute(
            "INSERT INTO activations (license_id, token_hash, created_at, last_seen) VALUES (?, ?, ?, ?)",
            (row["id"], token_hash, iso(current), iso(current)),
        )
    return {"ok": True, "token": token, "expires_at": iso(expires)}


@app.post("/validate")
def validate(payload: ValidateLicense):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    current = now_utc()
    with db() as conn:
        row = conn.execute("""
            SELECT l.id, l.expires_at, l.blocked, l.device_id
            FROM activations a JOIN licenses l ON l.id = a.license_id
            WHERE a.token_hash = ?
            ORDER BY a.id DESC LIMIT 1
        """, (token_hash,)).fetchone()
        if not row or row["blocked"] or row["device_id"] != payload.device_id:
            raise HTTPException(status_code=403, detail="Licenca invalida ou bloqueada.")
        expires = datetime.fromisoformat(row["expires_at"])
        if current >= expires:
            raise HTTPException(status_code=403, detail="Licenca expirada.")
        conn.execute("UPDATE activations SET last_seen = ? WHERE token_hash = ?", (iso(current), token_hash))
    return {"ok": True, "expires_at": iso(expires)}


@app.post("/admin/licenses/{license_key}/block")
def block_license(license_key: str, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    with db() as conn:
        cur = conn.execute("UPDATE licenses SET blocked = 1 WHERE license_key = ?", (license_key,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Licenca nao encontrada.")
    return {"ok": True, "blocked": True}


@app.get("/admin/licenses")
def list_licenses(x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    with db() as conn:
        rows = conn.execute("""
            SELECT license_key, customer, duration_days, created_at, expires_at, device_id, blocked
            FROM licenses ORDER BY id DESC
        """).fetchall()
    return {"licenses": [dict(row) for row in rows]}
