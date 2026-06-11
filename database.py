import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ai_tavern.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'single_daily',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            speaker TEXT DEFAULT '',
            character_id TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )

    if not _has_column(cursor, 'sessions', 'mode'):
        cursor.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'single_daily'")

    if not _has_column(cursor, 'messages', 'speaker'):
        cursor.execute("ALTER TABLE messages ADD COLUMN speaker TEXT DEFAULT ''")

    if not _has_column(cursor, 'messages', 'character_id'):
        cursor.execute("ALTER TABLE messages ADD COLUMN character_id TEXT DEFAULT ''")

    conn.commit()
    conn.close()
