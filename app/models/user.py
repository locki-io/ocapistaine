# models/user.py
"""
User and Session Models

Pydantic models for user identification and session management.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class UserSession(BaseModel):
    """
    User session model.

    Stored in Redis at key: session:{user_id}
    """
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    current_thread_id: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatMessage(BaseModel):
    """Single chat message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sources: list[str] = Field(default_factory=list)


class ChatThread(BaseModel):
    """
    Chat conversation thread.

    Stored in Redis at key: chat:{user_id}:{thread_id}
    """
    thread_id: str
    user_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
