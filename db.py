import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "chat.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_chat(title, model):
    chat_id = uuid.uuid4().hex
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chats (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, title, model, now, now),
        )
    return chat_id


def touch_chat(chat_id):
    with get_conn() as conn:
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (_now(), chat_id))


def add_message(chat_id, role, content):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, _now()),
        )
    return cur.lastrowid


def delete_message(message_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))


def message_count(chat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM messages WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["n"]


def list_chats():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, model, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_chat(chat_id):
    with get_conn() as conn:
        chat = conn.execute("SELECT id, title, model FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if not chat:
            return None
        messages = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
        ).fetchall()
    return {"id": chat["id"], "title": chat["title"], "model": chat["model"], "messages": [dict(m) for m in messages]}


def get_history(chat_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_chat(chat_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def chat_exists(chat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)).fetchone()
    return row is not None
