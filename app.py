import json
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from character_store import CharacterStore
from chat_service import ChatService
from database import init_db
from ds3_memory_adapter import DS3MemoryAdapter
from repository import MemoryRepository, MessageRepository
from schemas import (
    CharacterListResponse,
    CharacterResponse,
    ChatRequest,
    ConversationResponse,
    GroupChatRequest,
    MemoryContextResponse,
    MemoryRecordResponse,
    MemoryStateResponse,
    MemoryStatusResponse,
    ReplyItem,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="AI Tavern")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

chat_repo = MessageRepository()
memory_repo = MemoryRepository()
memory_adapter = DS3MemoryAdapter()
chat_service = ChatService()
character_store = CharacterStore()


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def serve_home_page():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/history")
@app.get("/memory")
def serve_history_page():
    return FileResponse(BASE_DIR / "static" / "history.html")


@app.get("/api/characters", response_model=CharacterListResponse)
def get_characters():
    items = [
        CharacterResponse(
            character_id=item["character_id"],
            name=item["name"],
            summary=item["summary"],
        )
        for item in character_store.list_characters()
    ]
    return {"items": items}


def summarize_text(text: str, limit: int = 60) -> str:
    clean = " ".join(text.strip().split())
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


def estimate_state(mode: str, speaker_name: str) -> tuple[str, str]:
    mode_name = memory_repo.get_mode_label(mode)
    emotion_text = f"\u6700\u8fd1\u4e00\u6b21\u4e92\u52a8\u8bed\u6c14\uff1a{speaker_name} \u7684\u56de\u590d\u6574\u4f53\u5e73\u7a33\u81ea\u7136"
    history_text = f"\u5f53\u524d\u7d2f\u8ba1\u4e92\u52a8\u72b6\u6001\uff1a\u672c\u8f6e\u8bb0\u5f55\u5df2\u7eb3\u5165{mode_name}\u5386\u53f2"
    return emotion_text, history_text


def ensure_session(session_id: Optional[int], mode: str, message: str) -> int:
    if session_id is None:
        title = summarize_text(message, limit=18) or "\u65b0\u5bf9\u8bdd"
        return chat_repo.create_session(title=title, mode=mode)

    session = chat_repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_id \u4e0d\u5b58\u5728")
    if session.get("mode") != mode:
        raise HTTPException(status_code=400, detail="\u5f53\u524d\u4f1a\u8bdd\u4e0e\u6240\u9009\u6a21\u5f0f\u4e0d\u4e00\u81f4\uff0c\u8bf7\u65b0\u5efa\u5bf9\u8bdd\u540e\u518d\u53d1\u9001")
    return session_id


def build_single_prompt(character: dict, mode: str) -> str:
    mode_name = memory_repo.get_mode_label(mode)
    return (
        f"{character['prompt']}\n"
        f"\u5f53\u524d\u573a\u666f\uff1aAI \u9152\u9986\u3002\n"
        f"\u5f53\u524d\u6a21\u5f0f\uff1a{mode_name}\u3002\n"
        f"\u8bf7\u59cb\u7ec8\u4f7f\u7528\u4e2d\u6587\uff0c\u4fdd\u6301\u89d2\u8272\u4e00\u81f4\uff0c\u56de\u590d\u81ea\u7136\uff0c\u907f\u514d\u8131\u79bb\u89d2\u8272\u8bbe\u5b9a\u3002"
    )


def run_character_reply(character: dict, message: str, context: List[dict], mode: str) -> str:
    prompt = build_single_prompt(character, mode)
    return chat_service.generate_reply(message, context, system_prompt=prompt)


def persist_turn(session_id: int, mode: str, user_message: str, replies: List[ReplyItem]) -> None:
    for item in replies:
        emotion_text, history_text = estimate_state(mode, item.name)
        memory_repo.write_record(
            session_id=str(session_id),
            character_id=item.character_id,
            mode=mode,
            submit=user_message,
            reply=item.reply,
            summary=summarize_text(user_message),
            motto=summarize_text(item.reply),
            emotion=emotion_text,
            history=history_text,
            keywords=[item.name, memory_repo.get_mode_label(mode)],
        )


@app.post("/chat", response_model=ConversationResponse)
def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message \u4e0d\u80fd\u4e3a\u7a7a")

    session_id = ensure_session(req.session_id, "single_daily", message)
    character = character_store.get_character(req.character_id)
    context = chat_repo.get_recent_context(session_id, limit=8)

    chat_repo.add_message(session_id, "user", message, speaker="\u6211")

    try:
        reply_text = run_character_reply(character, message, context, mode="single_daily")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    chat_repo.add_message(
        session_id,
        "assistant",
        reply_text,
        speaker=character["name"],
        character_id=character["character_id"],
    )

    replies = [ReplyItem(character_id=character["character_id"], name=character["name"], reply=reply_text)]
    persist_turn(session_id, "single_daily", message, replies)
    return ConversationResponse(
        session_id=session_id,
        mode="single_daily",
        reply=reply_text,
        replies=replies,
        context_used=context,
    )


@app.post("/group_chat", response_model=ConversationResponse)
def group_chat(req: GroupChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message \u4e0d\u80fd\u4e3a\u7a7a")
    if len(req.active_characters) < 2:
        raise HTTPException(status_code=400, detail="\u591a\u4eba\u9152\u9986\u6a21\u5f0f\u81f3\u5c11\u9009\u62e9\u4e24\u4e2a\u89d2\u8272")

    session_id = ensure_session(req.session_id, "group_tavern", message)
    context = chat_repo.get_recent_context(session_id, limit=10)
    chat_repo.add_message(session_id, "user", message, speaker="\u6211")

    replies: List[ReplyItem] = []
    for character_id in req.active_characters[:3]:
        character = character_store.get_character(character_id)
        try:
            reply_text = run_character_reply(character, message, context, mode="group_tavern")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        chat_repo.add_message(
            session_id,
            "assistant",
            reply_text,
            speaker=character["name"],
            character_id=character["character_id"],
        )
        replies.append(ReplyItem(character_id=character["character_id"], name=character["name"], reply=reply_text))

    persist_turn(session_id, "group_tavern", message, replies)
    return ConversationResponse(
        session_id=session_id,
        mode="group_tavern",
        reply=replies[0].reply if replies else None,
        replies=replies,
        context_used=context,
    )


@app.post("/trpg_chat", response_model=ConversationResponse)
def trpg_chat(req: GroupChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message \u4e0d\u80fd\u4e3a\u7a7a")
    if len(req.active_characters) < 1:
        raise HTTPException(status_code=400, detail="\u8dd1\u56e2\u6a21\u5f0f\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u89d2\u8272")

    session_id = ensure_session(req.session_id, "group_trpg", message)
    context = chat_repo.get_recent_context(session_id, limit=12)
    chat_repo.add_message(session_id, "user", message, speaker="\u73a9\u5bb6")

    replies: List[ReplyItem] = []
    for character_id in req.active_characters[:3]:
        character = character_store.get_character(character_id)
        narrative_context = context + [{"role": "system", "content": "\u5f53\u524d\u662f\u8dd1\u56e2\u6a21\u5f0f\uff0c\u9700\u8981\u9002\u5f53\u63cf\u8ff0\u573a\u666f\u3001\u884c\u52a8\u548c\u6c1b\u56f4\u3002"}]
        try:
            reply_text = run_character_reply(character, message, narrative_context, mode="group_trpg")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        chat_repo.add_message(
            session_id,
            "assistant",
            reply_text,
            speaker=character["name"],
            character_id=character["character_id"],
        )
        replies.append(ReplyItem(character_id=character["character_id"], name=character["name"], reply=reply_text))

    persist_turn(session_id, "group_trpg", message, replies)
    return ConversationResponse(
        session_id=session_id,
        mode="group_trpg",
        reply=replies[0].reply if replies else None,
        replies=replies,
        context_used=context,
    )


@app.get("/messages")
def get_messages(session_id: Optional[int] = None, limit: int = Query(default=80, ge=1, le=300)):
    return {"items": chat_repo.list_messages(session_id=session_id, limit=limit)}


@app.get("/sessions")
def get_sessions(limit: int = Query(default=30, ge=1, le=100)):
    return {"items": chat_repo.list_sessions(limit=limit)}


@app.get("/sessions/{session_id}/context")
def get_session_context(session_id: int, limit: int = Query(default=6, ge=1, le=20)):
    if not chat_repo.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session_id \u4e0d\u5b58\u5728")
    return {"session_id": session_id, "context": chat_repo.get_recent_context(session_id, limit=limit)}


@app.get("/api/history/options")
def get_history_options():
    return memory_repo.list_filter_options()


@app.get("/api/history/records")
def get_history_records(
    character_id: Optional[str] = None,
    mode: Optional[str] = None,
    session_id: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
):
    return memory_repo.filter_records(
        character_id=character_id,
        mode=mode,
        session_id=session_id,
        keyword=keyword.strip() if keyword else None,
        limit=limit,
    )


@app.get("/api/history/export")
def export_history_records(
    view: str = Query(default="all", pattern="^(all|mine|ai)$"),
    character_id: Optional[str] = None,
    mode: Optional[str] = None,
    session_id: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=1000),
):
    result = memory_repo.filter_records(
        character_id=character_id,
        mode=mode,
        session_id=session_id,
        keyword=keyword.strip() if keyword else None,
        limit=limit,
    )
    content = memory_repo.export_records_as_text(result["items"], view=view)
    headers = {"Content-Disposition": 'attachment; filename="history_export.txt"'}
    return PlainTextResponse(content, headers=headers)


@app.get("/api/memory/status", response_model=MemoryStatusResponse)
def get_memory_status():
    return memory_adapter.get_status()


@app.get("/api/memory/all", response_model=MemoryRecordResponse)
def get_all_memory(limit: int = Query(default=100, ge=1, le=500)):
    return {"items": memory_adapter.all_records(limit=limit)}


@app.get("/api/memory/latest", response_model=MemoryRecordResponse)
def get_latest_memory(limit: int = Query(default=10, ge=1, le=50)):
    return {"items": memory_adapter.latest_records(limit=limit)}


@app.get("/api/memory/summaries", response_model=MemoryRecordResponse)
def get_memory_summaries(
    recent_count: int = Query(default=5, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=100),
):
    return {"items": memory_adapter.summary_records(recent_count=recent_count, limit=limit)}


@app.get("/api/memory/context", response_model=MemoryContextResponse)
def get_memory_context(n: int = Query(default=5, ge=1, le=30)):
    return memory_adapter.recent_context(n=n)


@app.get("/api/memory/state", response_model=MemoryStateResponse)
def get_memory_state():
    return memory_adapter.latest_state()


@app.get("/health")
def health_check():
    status = memory_adapter.get_status()
    return {
        "status": "ok",
        "service": "ai-tavern",
        "provider": chat_service.provider,
        "model": chat_service.model,
        "memory_module_exists": status["module_exists"],
        "memory_db_exists": status["repository"]["db_exists"],
        "memory_db_path": status["repository"]["db_path"],
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
