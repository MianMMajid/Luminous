"""Lightweight SQLite user profile store.

Persists user data (saved analyses, preferences) across sessions,
keyed by the email from Google OAuth via st.user.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "data" / "users.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT,
            picture TEXT,
            created_at TEXT,
            last_login TEXT,
            preferences TEXT DEFAULT '{}',
            saved_queries TEXT DEFAULT '[]'
        )"""
    )
    conn.commit()
    return conn


def upsert_user(email: str, name: str, picture: str | None = None) -> dict:
    """Create or update user on login. Returns the user row as dict."""
    conn = _get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO users (email, name, picture, created_at, last_login)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(email) DO UPDATE SET
             name = excluded.name,
             picture = COALESCE(excluded.picture, users.picture),
             last_login = excluded.last_login""",
        (email, name, picture, now, now),
    )
    conn.commit()
    return get_user(email)


def get_user(email: str) -> dict | None:
    """Fetch user profile by email."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT email, name, picture, created_at, last_login, preferences, saved_queries "
        "FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    if not row:
        return None
    return {
        "email": row[0],
        "name": row[1],
        "picture": row[2],
        "created_at": row[3],
        "last_login": row[4],
        "preferences": json.loads(row[5] or "{}"),
        "saved_queries": json.loads(row[6] or "[]"),
    }


def save_query(email: str, query_data: dict) -> None:
    """Append a query to the user's saved queries list."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT saved_queries FROM users WHERE email = ?", (email,)
    ).fetchone()
    if not row:
        return
    queries = json.loads(row[0] or "[]")
    query_data["saved_at"] = datetime.utcnow().isoformat()
    queries.append(query_data)
    # Keep last 50 queries
    queries = queries[-50:]
    conn.execute(
        "UPDATE users SET saved_queries = ? WHERE email = ?",
        (json.dumps(queries), email),
    )
    conn.commit()


def update_preferences(email: str, prefs: dict) -> None:
    """Update user preferences (merge with existing)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT preferences FROM users WHERE email = ?", (email,)
    ).fetchone()
    if not row:
        return
    existing = json.loads(row[0] or "{}")
    existing.update(prefs)
    conn.execute(
        "UPDATE users SET preferences = ? WHERE email = ?",
        (json.dumps(existing), email),
    )
    conn.commit()
