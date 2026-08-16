"""
Database layer. Stage 1 only needs to log searches, so this uses plain
sqlite3 (zero extra dependencies) rather than an ORM. The schema below
also sketches the Stage 5+ tables (users, notes, saved resources) so the
migration path to a real ORM (SQLAlchemy) + PostgreSQL is documented and
ready when auth/personalization land — see README "Next stages".
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "student_hub.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'mock',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query);

-- Stage 5+ tables (defined now, not yet wired into routes):
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    content TEXT,
    category TEXT,
    tags TEXT,
    pinned INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_notes_user ON user_notes(user_id);
CREATE TABLE IF NOT EXISTS saved_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT,
    url TEXT,
    resource_type TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_resources_user ON saved_resources(user_id);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def log_search(query: str, provider: str = "mock") -> None:
    """Best-effort logging — never let a DB hiccup break the search page."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO searches (query, provider, created_at) VALUES (?, ?, ?)",
            (query, provider, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass
