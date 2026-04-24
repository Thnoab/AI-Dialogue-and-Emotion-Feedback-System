from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: int
    reply: str
    context_used: List[Dict]


class MessageItem(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: str
