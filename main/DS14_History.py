import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, PlainTextResponse


class HistoryRepository:
    """
    历史记录模块：
    直接读取主系统 Memory_ConverContent.db 的 memory 表。
    支持 user_id 隔离，只返回当前登录用户自己的历史记录。
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir).resolve()
        self.db_path = self._resolve_db_path()
        self.character_dir = self._resolve_character_dir()
        self.mode_labels = {
            "single_daily": "单人对话",
            "group_tavern": "多人酒馆",
            "group_trpg": "跑团模式",
            "normal": "单人对话",
        }
        self._ensure_schema()

    def _resolve_db_path(self) -> Path:
        configured = os.getenv("DS_MEMORY_DB_PATH", "").strip()
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = self.base_dir / candidate
            return candidate.resolve()
        return (self.base_dir / "Memory_ConverContent.db").resolve()

    def _resolve_character_dir(self) -> Path:
        configured = os.getenv("CHAT_CHARACTER_DIR", "").strip()
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = self.base_dir / candidate
            return candidate.resolve()
        return (self.base_dir / "characters").resolve()

    def db_exists(self) -> bool:
        return self.db_path.exists()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """
        不破坏原表，只在缺少字段时补字段。
        user_id 是整合登录系统后的用户隔离字段。
        """
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'guest',
                character_id TEXT DEFAULT 'single',
                mode TEXT DEFAULT 'normal',
                session_id TEXT DEFAULT 'default',
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
        existing = {row["name"] for row in cur.fetchall()}

        desired = {
            "user_id": "TEXT DEFAULT 'guest'",
            "character_id": "TEXT DEFAULT 'single'",
            "mode": "TEXT DEFAULT 'normal'",
            "session_id": "TEXT DEFAULT 'default'",
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

    def get_mode_label(self, mode: Optional[str]) -> str:
        if not mode:
            return "未标注模式"
        return self.mode_labels.get(mode, mode)

    def _format_session_name(self, session_id: Optional[str], mode: Optional[str] = None) -> str:
        if session_id is None or str(session_id).strip() == "":
            return "未命名会话"
        text = str(session_id).strip()
        if text.isdigit():
            prefix = "跑团记录" if mode == "group_trpg" else "会话"
            return f"{prefix} {text}"
        if len(text) > 24:
            return f"{text[:24]}..."
        return text

    def get_character_map(self) -> Dict[str, str]:
        result: Dict[str, str] = {}
        if not self.character_dir.exists():
            return result

        for path in sorted(self.character_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            character_id = str(data.get("character_id") or data.get("id") or "").strip()
            name = str(data.get("name") or "").strip()
            if character_id and name:
                result[character_id] = name
        return result

    def clean_visible_text(self, value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        compact = text.replace(" ", "")
        if compact and compact.count("?") >= 4 and compact.count("?") >= len(compact) * 0.6:
            return "这条旧记录的中文内容在早期命令行测试时发生编码损坏，原文已经无法还原。请以页面中新发送的记录为准。"
        return text

    def get_status(self, user_id: Optional[str] = None) -> Dict:
        status = {
            "db_path": str(self.db_path),
            "db_exists": self.db_exists(),
            "table_exists": False,
            "columns": [],
            "record_count": 0,
            "current_user_record_count": 0,
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

        if user_id and "user_id" in status["columns"]:
            cur.execute("SELECT COUNT(*) AS count FROM memory WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            status["current_user_record_count"] = row["count"] if row else 0

        conn.close()
        return status

    def list_filter_options(self, user_id: str) -> Dict:
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
                    "user": False,
                },
            }

        conn = self._get_connection()
        cur = conn.cursor()
        character_map = self.get_character_map()
        user_supported = "user_id" in columns

        def fetch_distinct(column: str) -> List[str]:
            if column not in columns:
                return []
            if user_supported:
                cur.execute(
                    f"""
                    SELECT DISTINCT {column}
                    FROM memory
                    WHERE user_id = ?
                    AND {column} IS NOT NULL
                    AND TRIM(CAST({column} AS TEXT)) != ''
                    ORDER BY {column}
                    """,
                    (user_id,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT DISTINCT {column}
                    FROM memory
                    WHERE {column} IS NOT NULL
                    AND TRIM(CAST({column} AS TEXT)) != ''
                    ORDER BY {column}
                    """
                )
            return [str(row[0]) for row in cur.fetchall()]

        character_ids = fetch_distinct("character_id")
        modes = fetch_distinct("mode")
        session_ids = fetch_distinct("session_id")

        session_modes: Dict[str, str] = {}
        if "session_id" in columns and "mode" in columns:
            if user_supported:
                cur.execute(
                    """
                    SELECT session_id, mode, MAX(id) AS latest_id
                    FROM memory
                    WHERE user_id = ?
                    AND session_id IS NOT NULL
                    AND TRIM(CAST(session_id AS TEXT)) != ''
                    GROUP BY session_id
                    ORDER BY latest_id DESC
                    """,
                    (user_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT session_id, mode, MAX(id) AS latest_id
                    FROM memory
                    WHERE session_id IS NOT NULL
                    AND TRIM(CAST(session_id AS TEXT)) != ''
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
                "user": user_supported,
            },
        }

    def filter_records(
        self,
        user_id: str,
        character_id: Optional[str] = None,
        mode: Optional[str] = None,
        session_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
    ) -> Dict:
        columns = self._memory_columns()
        if not columns:
            return {"items": [], "total": 0}

        selectable = [
            column for column in [
                "id",
                "user_id",
                "session_id",
                "character_id",
                "mode",
                "submit",
                "reply",
                "summary",
                "motto",
                "emotion",
                "history",
                "keywords",
            ]
            if column in columns
        ]

        if "id" not in selectable:
            return {"items": [], "total": 0}

        where_clauses = []
        params: List[str] = []

        if "user_id" in columns:
            where_clauses.append("user_id = ?")
            params.append(user_id)

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
            if "summary" in columns:
                search_parts.append("summary LIKE ?")
                params.append(f"%{keyword}%")
            if "motto" in columns:
                search_parts.append("motto LIKE ?")
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

        cur.execute(
            f"SELECT {select_sql} FROM memory {where_sql} ORDER BY id DESC LIMIT ?",
            params + [limit],
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()

        character_map = self.get_character_map()
        for row in rows:
            raw_character = str(row.get("character_id", "")).strip()
            row["character_name"] = character_map.get(raw_character, raw_character or "默认角色")
            row["mode_name"] = self.get_mode_label(row.get("mode"))
            row["session_name"] = self._format_session_name(row.get("session_id"), row.get("mode"))
            for field in ["submit", "reply", "summary", "motto", "emotion", "history"]:
                if field in row:
                    row[field] = self.clean_visible_text(row.get(field))

        return {"items": rows, "total": total}

    def latest_state(self, user_id: str) -> Dict:
        columns = self._memory_columns()
        if not columns:
            return {"history": None, "emotion": None, "source": "memory_table"}

        where = "WHERE user_id = ?" if "user_id" in columns else ""
        params = [user_id] if "user_id" in columns else []

        conn = self._get_connection()
        cur = conn.cursor()

        history_value = None
        emotion_value = None

        if "history" in columns:
            cur.execute(
                f"""
                SELECT history
                FROM memory
                {where}
                {'AND' if where else 'WHERE'} history IS NOT NULL
                AND TRIM(history) != ''
                ORDER BY id DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
            history_value = row["history"] if row else None

        if "emotion" in columns:
            cur.execute(
                f"""
                SELECT emotion
                FROM memory
                {where}
                {'AND' if where else 'WHERE'} emotion IS NOT NULL
                AND TRIM(emotion) != ''
                ORDER BY id DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
            emotion_value = row["emotion"] if row else None

        conn.close()
        return {"history": history_value, "emotion": emotion_value, "source": "memory_table"}

    def export_records_as_text(self, records: List[Dict], view: str) -> str:
        if not records:
            return "当前筛选结果为空。"

        blocks: List[str] = []
        for index, row in enumerate(records, start=1):
            character_name = row.get("character_name") or row.get("character_id") or "默认角色"
            mode_name = row.get("mode_name") or self.get_mode_label(row.get("mode"))
            session_name = row.get("session_name") or self._format_session_name(row.get("session_id"), row.get("mode"))

            header = (
                f"记录 {index}\n"
                f"角色：{character_name}\n"
                f"模式：{mode_name}\n"
                f"会话：{session_name}"
            )

            body_parts: List[str] = []

            if view in {"all", "mine"} and row.get("submit"):
                body_parts.append(f"我的发言：\n{row['submit']}")

            if view in {"all", "ai"} and row.get("reply"):
                body_parts.append(f"AI 回复：\n{row['reply']}")

            if not body_parts:
                body_parts.append("当前记录没有可导出的可见内容。")

            blocks.append(f"{header}\n\n" + "\n\n".join(body_parts))

        separator = "\n" + ("=" * 48) + "\n"
        return separator.join(blocks)


HISTORY_PAGE_HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <title>AI 酒馆 · 历史记录</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, sans-serif; background: #f3f4f6; color: #222; }
    .top { height: 64px; background: #d8dee8; border-bottom: 1px solid #b8c2cf; display: flex; align-items: center; justify-content: space-between; padding: 0 22px; }
    .top h1 { margin: 0; font-size: 22px; }
    .top a { text-decoration: none; color: #374151; margin-left: 14px; font-weight: 600; }
    .page { max-width: 1180px; margin: 24px auto; padding: 0 18px 40px; }
    .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 18px; box-shadow: 0 4px 14px rgba(0,0,0,0.05); margin-bottom: 18px; }
    .filters { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; }
    select, input, button { height: 40px; border: 1px solid #cfd7e3; border-radius: 10px; padding: 0 10px; font-size: 14px; background: #fff; }
    button { cursor: pointer; background: #4f46e5; color: white; border-color: #4f46e5; font-weight: 700; }
    button.secondary { background: #fff; color: #374151; border-color: #cfd7e3; }
    .record { border-top: 1px solid #edf0f5; padding: 16px 0; }
    .record:first-child { border-top: none; }
    .meta { color: #6b7280; font-size: 13px; margin-bottom: 8px; }
    .bubble { white-space: pre-wrap; line-height: 1.65; border-radius: 12px; padding: 12px 14px; margin: 8px 0; }
    .user { background: #d9f2ff; }
    .ai { background: #f8fafc; border: 1px solid #e5e7eb; }
    .summary { color: #475569; font-size: 14px; margin-top: 8px; }
    .empty { text-align: center; color: #6b7280; padding: 36px 0; }
    @media (max-width: 850px) { .filters { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="top">
    <h1>历史记录</h1>
    <div>
      <a href="/">返回酒馆</a>
      <a href="/profile">个人界面</a>
    </div>
  </div>

  <div class="page">
    <div class="card">
      <div class="filters">
        <select id="characterFilter"><option value="">全部角色</option></select>
        <select id="modeFilter"><option value="">全部模式</option></select>
        <select id="sessionFilter"><option value="">全部会话</option></select>
        <input id="keywordInput" placeholder="关键词搜索" />
        <button id="searchBtn">筛选</button>
      </div>
      <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
        <button class="secondary" id="exportAllBtn">导出全部可见内容</button>
        <button class="secondary" id="exportMineBtn">只导出我的发言</button>
        <button class="secondary" id="exportAiBtn">只导出 AI 回复</button>
      </div>
    </div>

    <div class="card">
      <div id="statusText" class="meta">正在读取历史记录……</div>
      <div id="records"></div>
    </div>
  </div>

<script>
const token = localStorage.getItem('tavern_token');
if (!token) { window.location.href = '/profile'; }

function authHeaders() { return { 'Authorization': `Bearer ${token}` }; }

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: authHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('tavern_token');
    window.location.href = '/profile';
    return null;
  }
  if (!res.ok) { throw new Error(await res.text()); }
  return await res.json();
}

async function loadOptions() {
  const data = await fetchJson('/api/history/options');
  if (!data) return;

  const characterSelect = document.getElementById('characterFilter');
  const modeSelect = document.getElementById('modeFilter');
  const sessionSelect = document.getElementById('sessionFilter');

  data.characters.forEach(item => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = item.name;
    characterSelect.appendChild(option);
  });

  data.modes.forEach(item => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = item.name;
    modeSelect.appendChild(option);
  });

  data.sessions.forEach(item => {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = item.name;
    sessionSelect.appendChild(option);
  });
}

function buildQuery(extra = {}) {
  const params = new URLSearchParams();

  const characterId = document.getElementById('characterFilter').value;
  const mode = document.getElementById('modeFilter').value;
  const sessionId = document.getElementById('sessionFilter').value;
  const keyword = document.getElementById('keywordInput').value.trim();

  if (characterId) params.set('character_id', characterId);
  if (mode) params.set('mode', mode);
  if (sessionId) params.set('session_id', sessionId);
  if (keyword) params.set('keyword', keyword);

  Object.entries(extra).forEach(([key, value]) => params.set(key, value));
  return params.toString();
}

async function loadRecords() {
  const query = buildQuery({ limit: 300 });
  const data = await fetchJson(`/api/history/records?${query}`);
  if (!data) return;

  const status = document.getElementById('statusText');
  const container = document.getElementById('records');

  status.textContent = `当前筛选结果：${data.total} 条`;
  container.innerHTML = '';

  if (!data.items || data.items.length === 0) {
    container.innerHTML = '<div class="empty">暂无历史记录</div>';
    return;
  }

  data.items.forEach(row => {
    const div = document.createElement('div');
    div.className = 'record';
    div.innerHTML = `
      <div class="meta">
        #${escapeHtml(row.id)} · ${escapeHtml(row.character_name)} · ${escapeHtml(row.mode_name)} · ${escapeHtml(row.session_name)}
      </div>
      ${row.submit ? `<div class="bubble user"><strong>我：</strong><br>${escapeHtml(row.submit)}</div>` : ''}
      ${row.reply ? `<div class="bubble ai"><strong>AI：</strong><br>${escapeHtml(row.reply)}</div>` : ''}
      ${(row.summary || row.motto) ? `<div class="summary">摘要：${escapeHtml(row.summary || '')} ${row.motto ? ' / ' + escapeHtml(row.motto) : ''}</div>` : ''}
      ${(row.emotion || row.history) ? `<div class="summary">状态：${escapeHtml(row.emotion || '')} ${row.history ? ' / ' + escapeHtml(row.history) : ''}</div>` : ''}
    `;
    container.appendChild(div);
  });
}

async function exportRecords(view) {
  const query = buildQuery({ view, limit: 1000 });
  const res = await fetch(`/api/history/export?${query}`, { headers: authHeaders() });
  if (!res.ok) {
    alert('导出失败');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'history_export.txt';
  a.click();
  URL.revokeObjectURL(url);
}

document.getElementById('searchBtn').addEventListener('click', loadRecords);
document.getElementById('exportAllBtn').addEventListener('click', () => exportRecords('all'));
document.getElementById('exportMineBtn').addEventListener('click', () => exportRecords('mine'));
document.getElementById('exportAiBtn').addEventListener('click', () => exportRecords('ai'));

(async function init() {
  try {
    await loadOptions();
    await loadRecords();
  } catch (error) {
    document.getElementById('statusText').textContent = '历史记录读取失败：' + error.message;
  }
})();
</script>
</body>
</html>
"""


def create_history_router(history_repo: HistoryRepository, auth_service):
    router = APIRouter(tags=["history"])

    @router.get("/history")
    @router.get("/memory")
    def serve_history_page():
        return HTMLResponse(HISTORY_PAGE_HTML)

    @router.get("/api/history/status")
    def history_status(user: dict = Depends(auth_service.get_current_user)):
        user_id = str(user["id"])
        return history_repo.get_status(user_id=user_id)

    @router.get("/api/history/options")
    def history_options(user: dict = Depends(auth_service.get_current_user)):
        user_id = str(user["id"])
        return history_repo.list_filter_options(user_id=user_id)

    @router.get("/api/history/records")
    def history_records(
        character_id: Optional[str] = None,
        mode: Optional[str] = None,
        session_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = Query(default=200, ge=1, le=500),
        user: dict = Depends(auth_service.get_current_user),
    ):
        user_id = str(user["id"])
        return history_repo.filter_records(
            user_id=user_id,
            character_id=character_id,
            mode=mode,
            session_id=session_id,
            keyword=keyword.strip() if keyword else None,
            limit=limit,
        )

    @router.get("/api/history/export")
    def export_history_records(
        view: str = Query(default="all", pattern="^(all|mine|ai)$"),
        character_id: Optional[str] = None,
        mode: Optional[str] = None,
        session_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = Query(default=500, ge=1, le=1000),
        user: dict = Depends(auth_service.get_current_user),
    ):
        user_id = str(user["id"])
        result = history_repo.filter_records(
            user_id=user_id,
            character_id=character_id,
            mode=mode,
            session_id=session_id,
            keyword=keyword.strip() if keyword else None,
            limit=limit,
        )
        content = history_repo.export_records_as_text(result["items"], view=view)
        headers = {"Content-Disposition": 'attachment; filename="history_export.txt"'}
        return PlainTextResponse(content, headers=headers)

    @router.get("/api/memory/status")
    def memory_status(user: dict = Depends(auth_service.get_current_user)):
        user_id = str(user["id"])
        return history_repo.get_status(user_id=user_id)

    @router.get("/api/memory/state")
    def memory_state(user: dict = Depends(auth_service.get_current_user)):
        user_id = str(user["id"])
        return history_repo.latest_state(user_id=user_id)

    return router


def mount_history_module(app, auth_service, base_dir: str):
    history_repo = HistoryRepository(base_dir=base_dir)
    app.include_router(create_history_router(history_repo, auth_service))
    return history_repo
