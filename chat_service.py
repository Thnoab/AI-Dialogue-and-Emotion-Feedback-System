import json
import os
from pathlib import Path
from typing import Dict, List
from urllib import error, request


class ChatService:
    def __init__(self) -> None:
        self._load_local_env()
        self.provider = os.getenv("LLM_PROVIDER", "openai_compatible").strip().lower()
        self.model = os.getenv("LLM_MODEL", "deepseek-chat").strip()
        self.system_prompt = os.getenv(
            "LLM_SYSTEM_PROMPT",
            "你是一个专业、自然、直接的中文 AI 助手。回答要准确、简洁，并保持连续对话语境。",
        ).strip()
        self.timeout = int(os.getenv("LLM_TIMEOUT", "60"))

        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

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

    def generate_reply(self, user_message: str, context: List[Dict]) -> str:
        messages = self._build_messages(user_message, context)

        if self.provider == "ollama":
            return self._call_ollama(messages)

        if self.provider == "openai_compatible":
            return self._call_openai_compatible(messages)

        raise ValueError("不支持的 LLM_PROVIDER。可选值：openai_compatible、ollama")

    def _build_messages(self, user_message: str, context: List[Dict]) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
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
                "未配置 LLM_API_KEY。若接 DeepSeek，请设置 LLM_PROVIDER=openai_compatible、"
                "LLM_BASE_URL=https://api.deepseek.com/v1、LLM_MODEL=deepseek-chat、LLM_API_KEY=你的密钥"
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
            raise RuntimeError(f"模型接口调用失败：HTTP {exc.code}，{detail[:300]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"模型接口连接失败：{exc.reason}") from exc

        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型返回格式异常：{data}") from exc

        if not content:
            raise RuntimeError("模型返回了空内容")

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
            raise RuntimeError(f"Ollama 调用失败：HTTP {exc.code}，{detail[:300]}") from exc
        except error.URLError as exc:
            raise RuntimeError(
                "无法连接到 Ollama。请先启动 Ollama，并确认本机可访问 "
                f"{self.ollama_url}"
            ) from exc

        try:
            content = data["message"]["content"].strip()
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Ollama 返回格式异常：{data}") from exc

        if not content:
            raise RuntimeError("Ollama 返回了空内容")

        return content
