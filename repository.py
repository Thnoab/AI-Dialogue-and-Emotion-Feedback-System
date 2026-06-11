import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from character_store import CharacterStore
from database import get_connection


class MessageRepository:
    mode_labels = {
        "single_daily": "\u5355\u4eba\u5bf9\u8bdd",
        "group_tavern": "\u591a\u4eba\u9152\u9986",
        "group_trpg": "\u8dd1\u56e2\u6a21\u5f0f",
    }

    def create_session(self, title: str = "\u65b0\u5bf9\u8bdd", mode: str = "single_daily") -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions(title, mode) VALUES (?, ?)", (title, mode))
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

    def get_session(self, session_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, mode, created_at FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_session_title(self, session_id: int, title: str) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        conn.commit()
        conn.close()

    def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
        speaker: Optional[str] = None,
        character_id: Optional[str] = None,
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages(session_id, role, content, speaker, character_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, speaker or "", character_id or ""),
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
                s.mode,
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
        for row in rows:
            row["mode_name"] = self.mode_labels.get(row.get("mode"), row.get("mode") or "\u672a\u6807\u6ce8\u6a21\u5f0f")
        return rows

    def list_messages(self, session_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        if session_id is None:
            cursor.execute(
                "SELECT id, session_id, role, content, speaker, character_id, created_at FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor.execute(
                "SELECT id, session_id, role, content, speaker, character_id, created_at FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        rows.reverse()
        return rows

    def get_recent_context(self, session_id: int, limit: int = 8) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, speaker FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        rows.reverse()
        context: List[Dict] = []
        for row in rows:
            role = row.get("role")
            content = row.get("content") or ""
            speaker = row.get("speaker") or ""
            if role == "assistant" and speaker:
                context.append({"role": role, "content": f"{speaker}: {content}"})
            else:
                context.append({"role": role, "content": content})
        return context


class MemoryRepository:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.workspace_dir = self.base_dir.parent
        self.db_path = self._resolve_db_path()
        self.character_store = CharacterStore()
        self.mode_labels = {
            "single_daily": "\u5355\u4eba\u5bf9\u8bdd",
            "group_tavern": "\u591a\u4eba\u9152\u9986",
            "group_trpg": "\u8dd1\u56e2\u6a21\u5f0f",
            "normal": "\u5355\u4eba\u5bf9\u8bdd",
        }
        self._ensure_schema()

    def _resolve_db_path(self) -> Path:
        configured = os.getenv("DS_MEMORY_DB_PATH", "").strip()
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = self.workspace_dir / candidate
            return candidate

        candidates = [
            self.base_dir / "Memory_ConverContent.db",
            self.workspace_dir / "Memory_ConverContent.db",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def db_exists(self) -> bool:
        return self.db_path.exists()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id TEXT DEFAULT 'system',
                mode TEXT DEFAULT 'single_daily',
                session_id TEXT DEFAULT '',
                submit TEXT NOT NULL DEFAULT '',
                reply TEXT,
                summary TEXT NOT NULL DEFAULT '',
                motto TEXT,
                emotion TEXT,
                history TEXT,
                keywords TEXT DEFAULT '[]'
            )
            """
        )
        cur.execute("PRAGMA table_info(memory)")
        existing = {row[1] for row in cur.fetchall()}
        desired = {
            "character_id": "TEXT DEFAULT 'system'",
            "mode": "TEXT DEFAULT 'single_daily'",
            "session_id": "TEXT DEFAULT ''",
            "submit": "TEXT NOT NULL DEFAULT ''",
            "reply": "TEXT",
            "summary": "TEXT NOT NULL DEFAULT ''",
            "motto": "TEXT",
            "emotion": "TEXT",
            "history": "TEXT",
            "keywords": "TEXT DEFAULT '[]'",
        }
        for column, ddl in desired.items():
            if column not in existing:
                cur.execute(f"ALTER TABLE memory ADD COLUMN {column} {ddl}")
        conn.commit()
        conn.close()

    def _memory_columns(self) -> List[str]:
        if not self.db_exists():
            return []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory'")
        if cur.fetchone() is None:
            conn.close()
            return []
        cur.execute("PRAGMA table_info(memory)")
        columns = [row["name"] for row in cur.fetchall()]
        conn.close()
        return columns

    def _table_exists(self) -> bool:
        return "id" in self._memory_columns()

    def _available_select_columns(self, preferred: List[str]) -> List[str]:
        columns = set(self._memory_columns())
        return [column for column in preferred if column in columns]

    def get_status(self) -> Dict:
        status = {
            "db_path": str(self.db_path),
            "db_exists": self.db_exists(),
            "table_exists": False,
            "columns": [],
            "record_count": 0,
        }
        if not status["db_exists"]:
            return status

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory'")
        status["table_exists"] = cur.fetchone() is not None
        if not status["table_exists"]:
            conn.close()
            return status
        cur.execute("PRAGMA table_info(memory)")
        status["columns"] = [row["name"] for row in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS count FROM memory")
        row = cur.fetchone()
        status["record_count"] = row["count"] if row else 0
        conn.close()
        return status

    def write_record(
        self,
        session_id: str,
        character_id: str,
        mode: str,
        submit: str,
        reply: str,
        summary: str,
        motto: str,
        emotion: Optional[str] = None,
        history: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> int:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO memory(session_id, character_id, mode, submit, reply, summary, motto, emotion, history, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(session_id),
                character_id,
                mode,
                submit,
                reply,
                summary,
                motto,
                emotion,
                history,
                json.dumps(keywords or [], ensure_ascii=False),
            ),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def list_all(self, limit: int = 100) -> List[Dict]:
        if not self.db_exists() or not self._table_exists():
            return []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM memory ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def list_recent_dialogues(self, limit: int = 10) -> List[Dict]:
        rows = self.list_all(limit=limit)
        rows.reverse()
        return [
            {
                "id": row.get("id"),
                "submit": row.get("submit"),
                "reply": row.get("reply"),
                "mode": row.get("mode"),
                "character_id": row.get("character_id"),
                "session_id": row.get("session_id"),
            }
            for row in rows
        ]

    def list_older_summaries(self, recent_count: int = 5, limit: int = 20) -> List[Dict]:
        if not self.db_exists() or not self._table_exists():
            return []
        columns = self._memory_columns()
        if "summary" not in columns:
            return []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM memory WHERE id NOT IN (SELECT id FROM memory ORDER BY id DESC LIMIT ?) ORDER BY id DESC LIMIT ?",
            (recent_count, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return [{"id": row.get("id"), "summary": row.get("summary"), "motto": row.get("motto")} for row in rows]

    def latest_state(self) -> Dict:
        columns = self._memory_columns()
        if not columns:
            return {"history": None, "emotion": None}
        conn = self._get_connection()
        cur = conn.cursor()
        history_value = None
        emotion_value = None
        if "history" in columns:
            cur.execute("SELECT history FROM memory WHERE history IS NOT NULL AND TRIM(history) != '' ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            history_value = row["history"] if row else None
        if "emotion" in columns:
            cur.execute("SELECT emotion FROM memory WHERE emotion IS NOT NULL AND TRIM(emotion) != '' ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            emotion_value = row["emotion"] if row else None
        conn.close()
        return {"history": history_value, "emotion": emotion_value}

    def fallback_recent_context(self, n: int = 5) -> Dict:
        rows = self.list_all(limit=max(n, 1))
        recent_rows = list(reversed(rows[:n]))
        older = self.list_older_summaries(recent_count=n, limit=10)
        recent_dialogues = []
        for row in recent_rows:
            if row.get("submit"):
                recent_dialogues.append({"role": "user", "content": row.get("submit")})
            if row.get("reply"):
                recent_dialogues.append({"role": "assistant", "content": row.get("reply")})
        older_summaries = []
        for row in older:
            merged = " | ".join([part for part in [row.get("summary") or "", row.get("motto") or ""] if part])
            if merged:
                older_summaries.append(merged)
        return {
            "recent_dialogues": recent_dialogues,
            "older_summaries": older_summaries,
            "source": "sqlite_fallback",
        }

    def get_mode_label(self, mode: Optional[str]) -> str:
        if not mode:
            return "\u672a\u6807\u6ce8\u6a21\u5f0f"
        return self.mode_labels.get(mode, mode)

    def _format_session_name(self, session_id: Optional[str], mode: Optional[str] = None) -> str:
        if session_id is None or str(session_id).strip() == "":
            return "\u672a\u547d\u540d\u4f1a\u8bdd"
        text = str(session_id).strip()
        if text.isdigit():
            prefix = "\u8dd1\u56e2\u8bb0\u5f55" if mode == "group_trpg" else "\u4f1a\u8bdd"
            return f"{prefix} {text}"
        if len(text) > 18:
            return f"{text[:18]}..."
        return text

    def get_character_map(self) -> Dict[str, str]:
        return self.character_store.get_character_map()

    def clean_visible_text(self, value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        compact = text.replace(" ", "")
        if compact and compact.count("?") >= 4 and compact.count("?") >= len(compact) * 0.6:
            return '这条旧记录的中文内容在早期命令行测试时发生编码损坏，原文已经无法还原。请以页面中新发送的记录为准。'
        return text

    def list_filter_options(self) -> Dict:
        columns = self._memory_columns()
        if not columns:
            return {
                "characters": [],
                "modes": [],
                "sessions": [],
                "supports": {
                    "character": False,
                    "mode": False,
                    "session": False,
                    "search": False,
                },
            }

        conn = self._get_connection()
        cur = conn.cursor()
        character_map = self.get_character_map()

        def fetch_distinct(column: str) -> List[str]:
            if column not in columns:
                return []
            cur.execute(
                f"SELECT DISTINCT {column} FROM memory WHERE {column} IS NOT NULL AND TRIM(CAST({column} AS TEXT)) != '' ORDER BY {column}"
            )
            return [str(row[0]) for row in cur.fetchall()]

        character_ids = fetch_distinct("character_id")
        modes = fetch_distinct("mode")
        session_ids = fetch_distinct("session_id")
        session_modes: Dict[str, str] = {}
        if "session_id" in columns and "mode" in columns:
            cur.execute(
                """
                SELECT session_id, mode, MAX(id) AS latest_id
                FROM memory
                WHERE session_id IS NOT NULL AND TRIM(CAST(session_id AS TEXT)) != ''
                GROUP BY session_id
                ORDER BY latest_id DESC
                """
            )
            session_modes = {str(row["session_id"]): row["mode"] for row in cur.fetchall()}
        conn.close()

        return {
            "characters": [
                {"id": character_id, "name": character_map.get(character_id, character_id)}
                for character_id in character_ids
            ],
            "modes": [
                {"id": mode, "name": self.get_mode_label(mode)}
                for mode in modes
            ],
            "sessions": [
                {"id": session_id, "name": self._format_session_name(session_id, session_modes.get(session_id))}
                for session_id in session_ids
            ],
            "supports": {
                "character": "character_id" in columns,
                "mode": "mode" in columns,
                "session": "session_id" in columns,
                "search": "submit" in columns or "reply" in columns,
            },
        }

    def filter_records(
        self,
        character_id: Optional[str] = None,
        mode: Optional[str] = None,
        session_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
    ) -> Dict:
        columns = self._memory_columns()
        if not columns:
            return {"items": [], "total": 0}

        selectable = self._available_select_columns([
            "id",
            "session_id",
            "character_id",
            "mode",
            "submit",
            "reply",
            "summary",
            "motto",
            "emotion",
            "history",
        ])
        if "id" not in selectable:
            return {"items": [], "total": 0}

        where_clauses = []
        params: List[str] = []

        if character_id and "character_id" in columns:
            where_clauses.append("character_id = ?")
            params.append(character_id)
        if mode and "mode" in columns:
            where_clauses.append("mode = ?")
            params.append(mode)
        if session_id and "session_id" in columns:
            where_clauses.append("session_id = ?")
            params.append(session_id)
        if keyword:
            search_parts = []
            if "submit" in columns:
                search_parts.append("submit LIKE ?")
                params.append(f"%{keyword}%")
            if "reply" in columns:
                search_parts.append("reply LIKE ?")
                params.append(f"%{keyword}%")
            if search_parts:
                where_clauses.append(f"({' OR '.join(search_parts)})")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        select_sql = ", ".join(selectable)

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS count FROM memory {where_sql}", params)
        total_row = cur.fetchone()
        total = total_row["count"] if total_row else 0
        cur.execute(f"SELECT {select_sql} FROM memory {where_sql} ORDER BY id DESC LIMIT ?", params + [limit])
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()

        character_map = self.get_character_map()
        for row in rows:
            raw_character = str(row.get("character_id", "")).strip()
            row["character_name"] = character_map.get(raw_character, raw_character or "\u9ed8\u8ba4\u89d2\u8272")
            row["mode_name"] = self.get_mode_label(row.get("mode"))
            row["session_name"] = self._format_session_name(row.get("session_id"), row.get("mode"))
            for field in ["submit", "reply", "summary", "motto", "emotion", "history"]:
                if field in row:
                    row[field] = self.clean_visible_text(row.get(field))

        return {"items": rows, "total": total}

    def export_records_as_text(self, records: List[Dict], view: str) -> str:
        if not records:
            return "\u5f53\u524d\u7b5b\u9009\u7ed3\u679c\u4e3a\u7a7a\u3002"

        blocks: List[str] = []
        for index, row in enumerate(records, start=1):
            default_character = "\u9ed8\u8ba4\u89d2\u8272"
            character_name = row.get("character_name") or row.get("character_id") or default_character
            mode_name = row.get("mode_name") or self.get_mode_label(row.get("mode"))
            session_name = row.get("session_name") or self._format_session_name(
                row.get("session_id"),
                row.get("mode"),
            )
            header = (
                f"\u8bb0\u5f55 {index}\n"
                f"\u89d2\u8272\uff1a{character_name}\n"
                f"\u6a21\u5f0f\uff1a{mode_name}\n"
                f"\u4f1a\u8bdd\uff1a{session_name}"
            )
            body_parts: List[str] = []
            if view in {"all", "mine"} and row.get("submit"):
                body_parts.append(f"\u6211\u7684\u53d1\u8a00\uff1a\n{row['submit']}")
            if view in {"all", "ai"} and row.get("reply"):
                body_parts.append(f"AI \u56de\u590d\uff1a\n{row['reply']}")
            if not body_parts:
                body_parts.append("\u5f53\u524d\u8bb0\u5f55\u6ca1\u6709\u53ef\u5bfc\u51fa\u7684\u53ef\u89c1\u5185\u5bb9\u3002")
            blocks.append(f"{header}\n\n" + "\n\n".join(body_parts))

        separator = "\n" + ("=" * 48) + "\n"
        return separator.join(blocks)
