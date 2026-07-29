"""
Auth service.

Each user gets their own SQLite database file (see services/database.py ::
get_database_path()), so data uploaded/connected by one account is never
visible to another — no per-table owner filtering needed, every existing
query/upload/RAG code path already goes through get_database_path().

The users themselves live in one small shared database, separate from any
business data.
"""

import logging
import sqlite3
import time
from contextvars import ContextVar
from pathlib import Path

import bcrypt
import jwt
from fastapi import Header, HTTPException

from config import DATA_DIR, JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET

logger = logging.getLogger(__name__)

AUTH_DB_PATH = str(DATA_DIR / "auth.db")

# Set by require_auth() for the duration of a request so every downstream
# service (database, vector_store, query_cache) can scope itself to the
# logged-in user without threading a user_id through every function call.
current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def _connection() -> sqlite3.Connection:
    Path(AUTH_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "email TEXT UNIQUE NOT NULL, "
        "password_hash TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    return conn


def register_user(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Enter a valid email address.")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    conn = _connection()
    try:
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise ValueError("An account with that email already exists.")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, datetime('now'))",
            (email, password_hash),
        )
        conn.commit()
        logger.info("New account registered: %s", email)
        return {"id": cursor.lastrowid, "email": email}
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    conn = _connection()
    try:
        row = conn.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row or not bcrypt.checkpw((password or "").encode(), row["password_hash"].encode()):
            raise ValueError("Invalid email or password.")
        return {"id": row["id"], "email": row["email"]}
    finally:
        conn.close()


def create_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "exp": int(time.time()) + JWT_EXPIRE_MINUTES * 60,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def require_auth(authorization: str | None = Header(default=None)) -> dict:
    """
    FastAPI dependency: validates the Bearer token and scopes this request
    to that user's own database/vector-index/cache for every downstream call.

    Must stay `async def`, not `def` — a sync dependency is run by Starlette
    in a worker thread, and a ContextVar.set() made in that thread does not
    propagate back to the request's own async task, so the user_id would be
    invisible to everything that runs after this dependency (silently
    falling back to the shared default database — a real cross-account data
    leak, not just a style nit).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

    user = {"id": int(payload["sub"]), "email": payload["email"]}
    current_user_id.set(user["id"])
    return user
