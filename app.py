from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from chat_service import ChatService
from database import init_db
from repository import MessageRepository
from schemas import ChatRequest, ChatResponse

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="AI Chat")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

repo = MessageRepository()
chat_service = ChatService()


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def serve_chat_page():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/history")
def serve_history_page():
    return FileResponse(BASE_DIR / "static" / "history.html")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    session_id = req.session_id
    if session_id is None:
        session_id = repo.create_session()
    elif not repo.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session_id 不存在")

    context = repo.get_recent_context(session_id, limit=6)
    repo.add_message(session_id, "user", message)

    try:
        reply = chat_service.generate_reply(message, context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    repo.add_message(session_id, "assistant", reply)

    return ChatResponse(session_id=session_id, reply=reply, context_used=context)


@app.get("/messages")
def get_messages(session_id: Optional[int] = None, limit: int = Query(default=50, ge=1, le=200)):
    return {"items": repo.list_messages(session_id=session_id, limit=limit)}


@app.get("/sessions")
def get_sessions(limit: int = Query(default=30, ge=1, le=100)):
    return {"items": repo.list_sessions(limit=limit)}


@app.get("/sessions/{session_id}/context")
def get_session_context(session_id: int, limit: int = Query(default=6, ge=1, le=20)):
    if not repo.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session_id 不存在")
    return {"session_id": session_id, "context": repo.get_recent_context(session_id, limit=limit)}


@app.get("/health")
def health_check():
    return {"status": "ok", "provider": chat_service.provider, "model": chat_service.model}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
