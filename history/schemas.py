from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=4000)
    character_id: Optional[str] = None


class GroupChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=4000)
    active_characters: List[str] = Field(default_factory=list)


class CharacterResponse(BaseModel):
    character_id: str
    name: str
    summary: str


class CharacterListResponse(BaseModel):
    items: List[CharacterResponse]


class ReplyItem(BaseModel):
    character_id: str
    name: str
    reply: str


class ConversationResponse(BaseModel):
    session_id: int
    mode: str
    reply: Optional[str] = None
    replies: List[ReplyItem] = Field(default_factory=list)
    context_used: List[Dict[str, Any]] = Field(default_factory=list)


class MemoryStatusResponse(BaseModel):
    module_path: Optional[str] = None
    module_exists: bool
    repository: Dict[str, Any]


class MemoryRecordResponse(BaseModel):
    items: List[Dict[str, Any]]


class MemoryContextResponse(BaseModel):
    source: str
    module_used: Optional[str] = None
    raw: Optional[Any] = None
    recent_dialogues: Optional[List[Dict[str, Any]]] = None
    older_summaries: Optional[List[str]] = None


class MemoryStateResponse(BaseModel):
    history: Optional[str] = None
    emotion: Optional[str] = None
    source: str
