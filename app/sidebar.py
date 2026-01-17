# sidebar.py
"""
O Capistaine - Simplified Sidebar

Single user identification via UUID (cookie-based).
Minimal session state - Redis handles persistence.
"""

import os
import uuid
import streamlit as st
from typing import Optional

# TODO: Replace with actual Redis client when implemented
# from app.data.redis_client import get_redis_connection


def get_user_id() -> str:
    """
    Get or create a unique user identifier.

    Strategy:
    1. Check session_state (current session)
    2. Check cookies (returning user)
    3. Generate new UUID (new user)

    Returns:
        str: Unique user identifier (UUID)
    """
    # Already in session?
    if "user_id" in st.session_state and st.session_state.user_id:
        return st.session_state.user_id

    # Try to load from cookie
    # TODO: Implement proper cookie handling
    # For now, use query params as fallback
    query_params = st.query_params
    if "uid" in query_params:
        user_id = query_params["uid"]
        st.session_state.user_id = user_id
        return user_id

    # Generate new user_id
    user_id = str(uuid.uuid4())
    st.session_state.user_id = user_id

    # Store in query params for persistence across reruns
    st.query_params["uid"] = user_id

    return user_id


def sidebar_setup() -> str:
    """
    Initialize sidebar with minimal controls.

    Returns:
        str: User ID for the current session
    """

    # Get or create user identity
    user_id = get_user_id()

    with st.sidebar:
        # Project branding
        st.markdown("## 🏛️ Ò Capistaine")
        st.caption("Transparence civique pour Audierne")

        st.divider()

        # User session info
        st.markdown("### 👤 Session")
        st.caption(f"ID: `{user_id[:8]}...`")

        # New conversation button
        if st.button("🔄 Nouvelle conversation", use_container_width=True):
            _start_new_conversation(user_id)
            st.rerun()

        st.divider()

        # Quick links
        st.markdown("### 🔗 Liens")
        st.markdown(
            """
        - [audierne2026.fr](https://audierne2026.fr)
        - [Documentation](https://docs.locki.io)
        - [Contribuer](https://github.com/locki-io/ocapistaine)
        """
        )

        st.divider()

        # Status indicators
        st.markdown("### 📊 Status")
        _display_status_indicators()

        # Footer
        st.divider()
        st.caption("Encode Hackathon 2026")
        st.caption("Apache 2.0 + ELv2")

    return user_id


def _start_new_conversation(user_id: str) -> None:
    """
    Start a new conversation thread.

    Creates a new thread_id and clears current chat state.
    """
    new_thread_id = f"{user_id}:{uuid.uuid4().hex[:8]}"
    st.session_state.thread_id = new_thread_id

    # TODO: Clear chat history in Redis when implemented
    # r = get_redis_connection()
    # r.delete(f"chat:{user_id}:{old_thread_id}")


def _display_status_indicators() -> None:
    """Display system status indicators."""

    # TODO: Replace with actual health checks
    status_items = [
        ("Redis", "🟢", "Connecté"),
        ("Firecrawl", "🔴", "Non configuré"),
        ("RAG", "🔴", "En développement"),
        ("Opik", "🟡", "Planifié"),
    ]

    for name, icon, tooltip in status_items:
        st.caption(f"{icon} {name}")


def init_session_state() -> None:
    """
    Initialize minimal session state.

    Only essential state is stored - Redis handles persistence.
    """
    defaults = {
        "user_id": None,
        "thread_id": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# Redis session management (placeholder until redis_client.py is implemented)
class SessionManager:
    """
    Manages user sessions in Redis.

    Redis Keys:
        session:{user_id} -> Hash with session data
        chat:{user_id}:{thread_id} -> List of chat messages
    """

    TTL_SESSION = 86400  # 24 hours
    TTL_CHAT = 604800  # 7 days

    @staticmethod
    def save_session(r, user_id: str, data: dict) -> None:
        """Save session data to Redis."""
        key = f"session:{user_id}"
        r.hset(key, mapping=data)
        r.expire(key, SessionManager.TTL_SESSION)

    @staticmethod
    def load_session(r, user_id: str) -> Optional[dict]:
        """Load session data from Redis."""
        key = f"session:{user_id}"
        data = r.hgetall(key)
        return data if data else None

    @staticmethod
    def save_chat_message(
        r, user_id: str, thread_id: str, role: str, content: str
    ) -> None:
        """Append a message to chat history."""
        import json

        key = f"chat:{user_id}:{thread_id}"
        message = json.dumps({"role": role, "content": content})
        r.rpush(key, message)
        r.expire(key, SessionManager.TTL_CHAT)

    @staticmethod
    def load_chat_history(r, user_id: str, thread_id: str) -> list:
        """Load chat history from Redis."""
        import json

        key = f"chat:{user_id}:{thread_id}"
        messages = r.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages] if messages else []
