# app/services/chat_session.py
"""
Chat Session Persistence

Stores chat sessions in Redis (app:chat:session:* prefix) with short TTL for session recovery.
Anonymous users get a short session ID they can bookmark via URL param.

Key format: app:chat:session:{session_id}
TTL: 1 hour (refreshed on each interaction)
"""

import json
import uuid
from typing import Optional
from dataclasses import dataclass, field

from app.data.redis_client import redis_connection, app_key
from app.services import AgentLogger

_logger = AgentLogger("chat_session")

# 1 hour TTL — refreshed on each save
CHAT_SESSION_TTL = 3600


def _generate_short_id() -> str:
    """Generate an 8-char hex session ID."""
    return uuid.uuid4().hex[:8]


@dataclass
class ChatSession:
    """Serializable chat session for Redis storage."""

    session_id: str
    messages: list = field(default_factory=list)
    mode: str = "chat"
    filter_list: str = ""
    selected_lists: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "session_id": self.session_id,
                "messages": self.messages,
                "mode": self.mode,
                "filter_list": self.filter_list,
                "selected_lists": self.selected_lists,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, data: str) -> "ChatSession":
        d = json.loads(data)
        return cls(
            session_id=d["session_id"],
            messages=d.get("messages", []),
            mode=d.get("mode", "chat"),
            filter_list=d.get("filter_list", ""),
            selected_lists=d.get("selected_lists", []),
        )


def _redis_key(session_id: str) -> str:
    """Build the Redis key for a chat session."""
    return app_key(f"chat:session:{session_id}")


def save_chat_session(
    session_id: str,
    messages: list,
    mode: str = "chat",
    filter_list: str = "",
    selected_lists: list | None = None,
) -> bool:
    """
    Save chat session to Redis. Refreshes TTL on each call.

    Args:
        session_id: Short session ID (8-char hex)
        messages: List of message dicts (role, content, sources, etc.)
        mode: Chat mode ("chat" or "compare")
        filter_list: Active list filter key (single mode)
        selected_lists: Active list selections (compare mode)

    Returns:
        True if saved successfully
    """
    try:
        session = ChatSession(
            session_id=session_id,
            messages=messages,
            mode=mode,
            filter_list=filter_list,
            selected_lists=selected_lists or [],
        )
        key = _redis_key(session_id)

        with redis_connection() as r:
            r.setex(key, CHAT_SESSION_TTL, session.to_json())

        return True

    except Exception as e:
        _logger.error("CHAT_SESSION_SAVE_ERROR", session_id=session_id, error=str(e)[:100])
        return False


def load_chat_session(session_id: str) -> Optional[ChatSession]:
    """
    Load chat session from Redis. Refreshes TTL on access.

    Args:
        session_id: Short session ID (8-char hex)

    Returns:
        ChatSession if found, None otherwise
    """
    try:
        key = _redis_key(session_id)

        with redis_connection() as r:
            data = r.get(key)
            if data:
                # Refresh TTL on access
                r.expire(key, CHAT_SESSION_TTL)
                return ChatSession.from_json(data)

        return None

    except Exception as e:
        _logger.error("CHAT_SESSION_LOAD_ERROR", session_id=session_id, error=str(e)[:100])
        return None


def delete_chat_session(session_id: str) -> bool:
    """Delete a chat session from Redis."""
    try:
        key = _redis_key(session_id)
        with redis_connection() as r:
            r.delete(key)
        return True
    except Exception:
        return False


def generate_session_id() -> str:
    """Generate a new short session ID."""
    return _generate_short_id()
