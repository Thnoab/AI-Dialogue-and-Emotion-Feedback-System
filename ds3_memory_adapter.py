import importlib.util
import os
from pathlib import Path
from typing import Dict, Optional

from repository import MemoryRepository


class DS3MemoryAdapter:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.workspace_dir = self.base_dir.parent
        self.module_path = self._resolve_module_path()
        self.repository = MemoryRepository()

    def _resolve_module_path(self) -> Optional[Path]:
        configured = os.getenv("DS_MEMORY_MODULE_PATH", "").strip()
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = self.workspace_dir / candidate
            return candidate

        candidates = [
            self.workspace_dir / "DS11_Memo.py",
            self.workspace_dir / "DS3_Memo.py",
            self.workspace_dir / "DS2_Memo.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _load_memorize(self):
        if not self.module_path or not self.module_path.exists():
            return None

        spec = importlib.util.spec_from_file_location("ds_memory_module", self.module_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        memorize_cls = getattr(module, "Memorize", None)
        if memorize_cls is None:
            return None
        return memorize_cls()

    def get_status(self) -> Dict:
        return {
            "module_path": str(self.module_path) if self.module_path else None,
            "module_exists": bool(self.module_path and self.module_path.exists()),
            "repository": self.repository.get_status(),
        }

    def all_records(self, limit: int = 100):
        return self.repository.list_all(limit=limit)

    def latest_records(self, limit: int = 10):
        return self.repository.list_recent_dialogues(limit=limit)

    def summary_records(self, recent_count: int = 5, limit: int = 20):
        return self.repository.list_older_summaries(recent_count=recent_count, limit=limit)

    def latest_state(self):
        status = self.repository.latest_state()
        status["source"] = "memory_table"
        return status

    def recent_context(self, n: int = 5):
        memo = self._load_memorize()
        if memo is None:
            fallback = self.repository.fallback_recent_context(n=n)
            fallback["module_used"] = None
            return fallback

        try:
            if hasattr(memo, "rappelez"):
                fallback = self.repository.fallback_recent_context(n=n)
                records = self.repository.filter_records(limit=max(n, 20))["items"]
                if records:
                    first = records[0]
                    session_id = first.get("session_id")
                    character_id = first.get("character_id")
                    try:
                        if session_id is not None and character_id:
                            result = memo.rappelez(session_id, character_id, n)
                            return {
                                "raw": result,
                                "source": "memo.rappelez",
                                "module_used": str(self.module_path),
                            }
                    except TypeError:
                        result = memo.rappelez(n)
                        return {
                            "raw": result,
                            "source": "memo.rappelez",
                            "module_used": str(self.module_path),
                        }
                return {
                    **fallback,
                    "module_used": str(self.module_path),
                }
        finally:
            if hasattr(memo, "close"):
                memo.close()

        fallback = self.repository.fallback_recent_context(n=n)
        fallback["module_used"] = str(self.module_path) if self.module_path else None
        return fallback
