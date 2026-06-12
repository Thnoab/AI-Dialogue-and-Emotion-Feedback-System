import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from urllib import error, request


DEFAULT_SYSTEM_PROMPT = (
    "You are an AI tavern assistant. Reply in natural Chinese, keep answers concise, "
    "and use recent chat history to maintain conversation continuity."
)


class ChatService:
    def __init__(self) -> None:
        self._load_local_env()
        self.provider = self._get_env("LLM_PROVIDER", default="openai_compatible").strip().lower()
        self.model = self._get_env("LLM_MODEL", "DEEPSEEK_MODEL", default="deepseek-chat").strip()
        self.system_prompt = self._get_env("LLM_SYSTEM_PROMPT", default=DEFAULT_SYSTEM_PROMPT).strip()
        self.timeout = int(self._get_env("LLM_TIMEOUT", default="60"))
        self.base_url = self._get_env(
            "LLM_BASE_URL",
            "DEEPSEEK_API_BASE",
            default="https://api.deepseek.com/v1",
        ).rstrip("/")
        self.api_key = self._get_env("LLM_API_KEY", "DEEPSEEK_API_KEY", default="").strip()
        self.ollama_url = self._get_env(
            "OLLAMA_BASE_URL",
            default="http://127.0.0.1:11434",
        ).rstrip("/")

    def _load_local_env(self) -> None:
        env_path = Path(__file__).resolve().parent / ".env"
        if not env_path.exists():
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    def _get_env(self, *keys: str, default: str = "") -> str:
        for key in keys:
            value = os.getenv(key)
            if value:
                return value
        return default

    def generate_reply(
        self,
        user_message: str,
        context: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        messages = self._build_messages(user_message, context, system_prompt=system_prompt)

        if self.provider == "ollama":
            return self._call_ollama(messages)

        if self.provider == "openai_compatible":
            return self._call_openai_compatible(messages)

        raise ValueError("Unsupported LLM_PROVIDER. Use openai_compatible or ollama.")

    def _build_messages(
        self,
        user_message: str,
        context: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        base_prompt = (system_prompt or self.system_prompt).strip() or self.system_prompt
        messages: List[Dict[str, str]] = [{"role": "system", "content": base_prompt}]
        for item in context:
            role = item.get("role", "").strip()
            content = item.get("content", "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _call_openai_compatible(self, messages: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError(
                "Missing API key. Set LLM_API_KEY or DEEPSEEK_API_KEY in .env before starting."
            )

        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
            }
        ).encode("utf-8")

        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Model API failed, HTTP {exc.code}: {detail[:300]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Model API connection failed: {exc.reason}") from exc

        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected model response: {data}") from exc

        if not content:
            raise RuntimeError("Model returned an empty response")

        return content

    def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
        ).encode("utf-8")

        req = request.Request(
            url=f"{self.ollama_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama failed, HTTP {exc.code}: {detail[:300]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Cannot connect to Ollama at {self.ollama_url}") from exc

        try:
            content = data["message"]["content"].strip()
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Ollama response: {data}") from exc

        if not content:
            raise RuntimeError("Ollama returned an empty response")

        return content
