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

from app.providers.config import GEMINI_MODELS
from app.i18n import _, language_selector, get_language
from app.services import PresentationLogger

# TODO: Replace with actual Redis client when implemented
# from app.data.redis_client import get_redis_connection

# Sidebar logger
_logger = PresentationLogger("sidebar")

# Available LLM providers and their models
PROVIDERS = {
    "gemini": {
        "name_key": "provider_google_gemini",
        "models": {
            "flash-lite": "gemini-2.5-flash-lite (~1000 req/day)",
            "flash": "gemini-2.5-flash (~20 req/day)",
            # "pro": "gemini-2.5-pro-exp (~25 req/day)",
        },
        "default": "flash-lite",
    },
    "claude": {
        "name_key": "provider_anthropic_claude",
        "models": {
            "haiku": "claude-3-haiku (fast, cheap)",
            "sonnet": "claude-3.5-sonnet (balanced)",
        },
        "default": "haiku",
    },
    "mistral": {
        "name_key": "provider_mistral_ai",
        "models": {
            "small": "mistral-small-latest",
            "medium": "mistral-medium-latest",
        },
        "default": "small",
    },
    "ollama": {
        "name_key": "provider_ollama",
        "models": {
            "mistral": "mistral:latest",
            "llama3.2": "llama3.2:latest",
            "orca-mini": "orca-mini:latest",
        },
        "default": "mistral",
    },
}


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
        _logger.info("USER_RESTORED", user_id=user_id[:8], source="query_params")
        return user_id

    # Generate new user_id
    user_id = str(uuid.uuid4())
    st.session_state.user_id = user_id

    # Store in query params for persistence across reruns
    st.query_params["uid"] = user_id

    _logger.info("USER_CREATED", user_id=user_id[:8])
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
        st.markdown(f"## 🏛️ {_('app_title')}")
        st.caption(_("app_subtitle"))

        st.divider()

        # Language selector
        _display_language_selector(user_id)

        st.divider()

        # User session info
        st.markdown(f"### 👤 {_('sidebar_session')}")
        st.caption(_("sidebar_session_id", user_id=user_id[:8]))

        # New conversation button
        if st.button(f"🔄 {_('sidebar_new_conversation')}", use_container_width=True):
            _start_new_conversation(user_id)
            st.rerun()

        st.divider()

        # AI Provider/Model selection
        st.markdown(f"### 🤖 {_('sidebar_ai_model')}")
        _display_provider_selector(user_id)

        st.divider()

        # Quick links
        st.markdown(f"### 🔗 {_('sidebar_links')}")
        st.markdown(
            """
        - [audierne2026.fr](https://audierne2026.fr)
        - [Documentation](https://docs.locki.io)
        - [Contribuer](https://github.com/locki-io/ocapistaine)
        """
        )

        st.divider()

        # Status indicators
        st.markdown(f"### 📊 {_('sidebar_status')}")
        _display_status_indicators()

        # Footer
        st.divider()
        st.caption(_("sidebar_footer_hackathon"))
        st.caption(_("sidebar_footer_license"))

    return user_id


def _display_language_selector(user_id: str) -> None:
    """Display language selector with logging."""
    current_lang = get_language()
    language_selector()
    new_lang = get_language()

    # Log language change (detected on next rerun)
    if "prev_lang" in st.session_state and st.session_state.prev_lang != new_lang:
        _logger.log_user_action(
            action="change_language",
            user_id=user_id,
            details=f"{st.session_state.prev_lang} -> {new_lang}",
        )
    st.session_state.prev_lang = new_lang


def _start_new_conversation(user_id: str) -> None:
    """
    Start a new conversation thread.

    Creates a new thread_id and clears current chat state.
    Switches to the Questions tab automatically.
    """
    old_thread_id = st.session_state.get("thread_id")
    new_thread_id = f"{user_id}:{uuid.uuid4().hex[:8]}"
    st.session_state.thread_id = new_thread_id

    # Switch to Questions tab via URL parameter
    st.query_params["tab"] = "questions"

    _logger.log_user_action(
        action="new_conversation",
        user_id=user_id,
        details=f"thread={new_thread_id[:16]}",
    )

    # TODO: Clear chat history in Redis when implemented
    # r = get_redis_connection()
    # r.delete(f"chat:{user_id}:{old_thread_id}")


def _display_provider_selector(user_id: str) -> None:
    """Display provider and model selection dropdowns."""
    # Initialize defaults if not set
    if "llm_provider" not in st.session_state:
        st.session_state.llm_provider = "ollama"
    if "llm_model" not in st.session_state:
        st.session_state.llm_model = "mistral"

    # Provider selection
    provider_names = list(PROVIDERS.keys())
    current_provider = st.session_state.llm_provider

    selected_provider = st.selectbox(
        _("sidebar_provider"),
        options=provider_names,
        disabled=True,
        index=(
            provider_names.index(current_provider)
            if current_provider in provider_names
            else 0
        ),
        format_func=lambda x: _(PROVIDERS[x]["name_key"]),
        key="provider_select",
    )

    # Update provider if changed
    if selected_provider != st.session_state.llm_provider:
        old_provider = st.session_state.llm_provider
        st.session_state.llm_provider = selected_provider
        # Reset model to default for new provider
        st.session_state.llm_model = PROVIDERS[selected_provider]["default"]
        # Clear cached agent
        if "forseti_agent" in st.session_state:
            del st.session_state["forseti_agent"]

        _logger.log_user_action(
            action="change_provider",
            user_id=user_id,
            details=f"{old_provider} -> {selected_provider}",
        )
        st.rerun()

    # Model selection for current provider
    provider_config = PROVIDERS[selected_provider]
    model_keys = list(provider_config["models"].keys())
    current_model = st.session_state.llm_model

    # Ensure current model is valid for this provider
    if current_model not in model_keys:
        current_model = provider_config["default"]
        st.session_state.llm_model = current_model

    selected_model = st.selectbox(
        _("sidebar_model"),
        options=model_keys,
        index=model_keys.index(current_model) if current_model in model_keys else 0,
        format_func=lambda x: provider_config["models"][x],
        key="model_select",
    )

    # Update model if changed
    if selected_model != st.session_state.llm_model:
        old_model = st.session_state.llm_model
        st.session_state.llm_model = selected_model
        # Clear cached agent
        if "forseti_agent" in st.session_state:
            del st.session_state["forseti_agent"]

        _logger.log_user_action(
            action="change_model",
            user_id=user_id,
            details=f"{old_model} -> {selected_model}",
        )
        st.rerun()


def get_selected_provider() -> str:
    """Get the currently selected LLM provider name."""
    return st.session_state.get("llm_provider", "gemini")


def get_selected_model() -> str:
    """Get the currently selected model key."""
    return st.session_state.get("llm_model", "flash-lite")


def get_model_id() -> str:
    """Get the full model ID for the current selection."""
    provider = get_selected_provider()
    model_key = get_selected_model()

    if provider == "gemini":
        return GEMINI_MODELS.get(model_key, "gemini-2.0-flash-lite")
    elif provider == "claude":
        model_map = {
            "haiku": "claude-3-haiku-20240307",
            "sonnet": "claude-3-5-sonnet-20241022",
        }
        return model_map.get(model_key, "claude-3-haiku-20240307")
    elif provider == "mistral":
        model_map = {
            "small": "mistral-small-latest",
            "medium": "mistral-medium-latest",
        }
        return model_map.get(model_key, "mistral-small-latest")
    elif provider == "ollama":
        model_map = {
            "mistral": "mistral:latest",
            "llama3.2": "llama3.2:latest",
            "orca-mini": "orca-mini:latest",
        }
        return model_map.get(model_key, "mistral:latest")

    return "gemini-2.0-flash-lite"


def _display_status_indicators() -> None:
    """Display system status indicators."""

    # TODO: Replace with actual health checks
    status_items = [
        ("status_redis", "🟢", "status_connected"),
        ("status_firecrawl", "🔴", "status_not_configured"),
        ("status_rag", "🔴", "status_in_development"),
        ("status_opik", "🟡", "status_planned"),
    ]

    for name_key, icon, tooltip_key in status_items:
        st.caption(f"{icon} {_(name_key)}")


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
