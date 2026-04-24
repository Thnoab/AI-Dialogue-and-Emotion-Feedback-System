from typing import Dict, List, Optional

from database import get_connection


class MessageRepository:
    def create_session(self, title: str = "默认会话") -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions(title) VALUES (?)", (title,))
        conn.commit()
        session_id = cursor.lastrowid
        conn.close()
        return session_id

    def session_exists(self, session_id: int) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def add_message(self, session_id: int, role: str, content: str) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        return message_id

    def list_sessions(self, limit: int = 30) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                s.id,
                s.title,
                s.created_at,
                (
                    SELECT content
                    FROM messages
                    WHERE session_id = s.id
                    ORDER BY id DESC
                    LIMIT 1
                ) AS last_message,
                (
                    SELECT created_at
                    FROM messages
                    WHERE session_id = s.id
                    ORDER BY id DESC
                    LIMIT 1
                ) AS last_message_at
            FROM sessions s
            ORDER BY COALESCE(last_message_at, s.created_at) DESC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def list_messages(self, session_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        if session_id is None:
            cursor.execute(
                "SELECT id, session_id, role, content, created_at FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor.execute(
                "SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        rows.reverse()
        return rows

    def get_recent_context(self, session_id: int, limit: int = 6) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        rows.reverse()
        return rows
