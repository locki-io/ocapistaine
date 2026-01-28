# front.py
"""
OCapistaine - Citizen Q&A Interface

Simplified Streamlit UI for civic transparency.
User identification via single UUID (cookie-based).
"""

import asyncio
import time

import requests
import streamlit as st

# MUST be first Streamlit command
st.set_page_config(
    page_title="Ò Capistaine - Civic Transparency",
    page_icon="🏛️",
    layout="wide",
)

# Authentication check (before loading any other content)
from app.auth import check_password
if not check_password():
    st.stop()

from app.sidebar import sidebar_setup, get_user_id, get_selected_provider, get_model_id
from app.agents.forseti import ForsetiAgent
from app.providers import get_provider
from app.i18n import _
from app.services import PresentationLogger, ServiceLogger, AgentLogger
from app.mockup.batch_view import batch_validation_view
from data.redis_client import get_redis_connection

# TODO: Import services when implemented
# from app.services.chat_service import ChatService
# from app.services.rag_service import RAGService

# Loggers for different concerns
_ui_logger = PresentationLogger("streamlit")
_svc_logger = ServiceLogger("chat")
_agent_logger = AgentLogger("forseti")


def get_forseti_agent():
    """Get or create Forseti agent instance based on sidebar selection."""
    provider_name = get_selected_provider()
    model_id = get_model_id()

    # Create cache key based on provider/model
    cache_key = f"forseti_{provider_name}_{model_id}"

    # Check if we have a cached agent for this config
    if cache_key not in st.session_state:
        try:
            provider = get_provider(provider_name, model=model_id, cache=False)
            st.session_state[cache_key] = ForsetiAgent(provider=provider)
            _agent_logger.info(
                "AGENT_INIT",
                provider=provider_name,
                model=model_id,
            )
        except Exception as e:
            st.error(_("forseti_init_error", provider=provider_name) + f": {e}")
            _agent_logger.error(
                "AGENT_INIT_FAILED",
                provider=provider_name,
                model=model_id,
                error=str(e),
            )
            # Fallback to default
            st.session_state[cache_key] = ForsetiAgent()

    return st.session_state[cache_key]


def main():
    """Main application entry point."""

    # Initialize sidebar and get user_id
    user_id = sidebar_setup()

    # Store in session for cross-component access
    st.session_state.user_id = user_id

    # Log page view (only once per session)
    if "page_view_logged" not in st.session_state:
        _ui_logger.log_page_view(page="main", user_id=user_id)
        st.session_state.page_view_logged = True

    # Clean up old session state if present
    if "active_tab" in st.session_state:
        del st.session_state["active_tab"]

    # Header
    st.title(f"🏛️ {_('app_title')}")
    st.markdown(f"**{_('app_header')}**")

    # Tab configuration: key -> (emoji, label_key)
    TAB_CONFIG = {
        "contributions": ("📝", "tab_contributions"),
        "mockup": ("🧪", "tab_mockup"),
        "questions": ("💬", "tab_questions"),
        "documents": ("📄", "tab_documents"),
        "about": ("ℹ️", "tab_about"),
    }
    TAB_KEYS = list(TAB_CONFIG.keys())

    # Get active tab from URL params (default: contributions)
    current_tab = st.query_params.get("tab", "contributions")
    if current_tab not in TAB_KEYS:
        current_tab = "contributions"

    # Build tab labels
    tab_labels = [f"{emoji} {_(label_key)}" for emoji, label_key in TAB_CONFIG.values()]

    # Create clickable tab buttons
    cols = st.columns(len(TAB_KEYS))
    for i, (key, (emoji, label_key)) in enumerate(TAB_CONFIG.items()):
        with cols[i]:
            is_active = key == current_tab
            label = f"{emoji} {_(label_key)}"
            if st.button(
                label,
                key=f"tab_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.query_params["tab"] = key
                st.rerun()

    st.markdown("---")

    # Render active tab content
    if current_tab == "contributions":
        contributions_view(user_id)
    elif current_tab == "questions":
        chat_view(user_id)
    elif current_tab == "documents":
        documents_view(user_id)
    elif current_tab == "mockup":
        mockup_view(user_id)
    elif current_tab == "about":
        about_view()


def chat_view(user_id: str):
    """Citizen Q&A chat interface."""

    r = get_redis_connection()
    thread_id = st.session_state.get("thread_id", f"{user_id}:default")

    # Load chat history from Redis
    history_key = f"chat:{user_id}:{thread_id}"
    # TODO: Load history when ChatService is implemented
    # history = ChatService.load_history(r, history_key)
    history = []  # Placeholder

    # Display chat history
    chat_container = st.container()
    with chat_container:
        if not history:
            st.info(f"👋 {_('chat_welcome')}")
        else:
            for msg in history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input(_("chat_input_placeholder")):
        # Log user message
        _svc_logger.log_request(
            user_id=user_id,
            operation="chat_message",
            query=prompt,
            thread_id=thread_id,
        )

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            start_time = time.time()
            with st.spinner(_("chat_searching")):
                # TODO: Replace with actual RAG call
                # response = RAGService.query(prompt, user_id)
                response = _placeholder_response(prompt)
                st.markdown(response)

            latency_ms = (time.time() - start_time) * 1000

        # Log response
        _svc_logger.log_response(
            user_id=user_id,
            operation="chat_message",
            success=True,
            latency_ms=latency_ms,
        )

        # TODO: Save to history when ChatService is implemented
        # ChatService.append_message(r, history_key, "user", prompt)
        # ChatService.append_message(r, history_key, "assistant", response)


def _placeholder_response(prompt: str) -> str:
    """Placeholder response until RAG is implemented."""
    return f"""
**🚧 {_('rag_placeholder_title')}**

{_('rag_placeholder_your_question')} : *"{prompt}"*

{_('rag_placeholder_coming_soon')}
- 🔍 {_('rag_placeholder_search')}
- 📄 {_('rag_placeholder_cite')}
- ✅ {_('rag_placeholder_verify')}

{_('rag_placeholder_meanwhile')}
"""


# N8N Webhook URL for fetching issues
N8N_ISSUES_WEBHOOK = "https://vaettir.locki.io/webhook/participons/issues"


# Available category labels in audierne2026/participons
CATEGORY_LABELS = [
    "",  # All (no filter)
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
    "conforme charte",
]


@st.cache_data(ttl=300)  # Cache for 5 minutes
def _fetch_issues(state: str = "open", labels: str = "", per_page: int = 50) -> dict:
    """Fetch issues from N8N workflow webhook."""
    start_time = time.time()
    try:
        payload = {"state": state, "per_page": per_page}
        if labels:  # Only add labels filter if specified
            payload["labels"] = labels
        response = requests.post(
            N8N_ISSUES_WEBHOOK,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        latency_ms = (time.time() - start_time) * 1000
        _ui_logger.log_webhook(
            source="n8n",
            event_type="fetch_issues",
            success=True,
        )
        _ui_logger.debug(
            "ISSUES_FETCHED",
            count=result.get("count", 0),
            state=state,
            labels=labels or "all",
            latency_ms=f"{latency_ms:.0f}",
        )

        return result
    except requests.RequestException as e:
        latency_ms = (time.time() - start_time) * 1000
        _ui_logger.log_webhook(
            source="n8n",
            event_type="fetch_issues",
            success=False,
            error=str(e),
        )
        return {"success": False, "error": str(e), "count": 0, "issues": []}


def _validate_with_forseti(
    title: str, body: str, category: str | None, user_id: str, issue_id: int
) -> dict:
    """Validate a contribution with Forseti agent."""
    start_time = time.time()

    _agent_logger.log_agent_start(
        task="validate_contribution",
        input_data=title,
    )

    try:
        agent = get_forseti_agent()
        result = asyncio.run(agent.validate(title=title, body=body, category=category))

        latency_ms = (time.time() - start_time) * 1000

        # Log validation result
        _agent_logger.log_validation(
            validator="forseti_charter",
            is_valid=result.is_valid,
            violations=result.violations,
            confidence=result.confidence,
        )

        _agent_logger.log_agent_complete(
            task="validate_contribution",
            success=True,
            latency_ms=latency_ms,
            output_summary=f"valid={result.is_valid}, confidence={result.confidence:.2f}",
        )

        return {
            "success": True,
            "is_valid": result.is_valid,
            "category": result.category,
            "original_category": result.original_category,
            "violations": result.violations,
            "encouraged_aspects": result.encouraged_aspects,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000

        _agent_logger.log_agent_complete(
            task="validate_contribution",
            success=False,
            latency_ms=latency_ms,
            output_summary=str(e)[:50],
        )

        return {"success": False, "error": str(e)}


def _display_forseti_result(result: dict):
    """Display Forseti validation result."""
    st.markdown("---")
    st.markdown(f"**🔍 {_('forseti_title')}**")

    if not result.get("success"):
        st.error(
            f"{_('forseti_error')}: {result.get('error', _('forseti_unknown_error'))}"
        )
        return

    # Validation status
    if result.get("is_valid"):
        st.success(f"✅ {_('forseti_compliant')}")
    else:
        st.warning(f"⚠️ {_('forseti_non_compliant')}")

    # Violations
    violations = result.get("violations", [])
    if violations:
        st.markdown(f"**{_('forseti_violations')}**")
        for v in violations:
            st.markdown(f"- ❌ {v}")

    # Encouraged aspects
    encouraged = result.get("encouraged_aspects", [])
    if encouraged:
        st.markdown(f"**{_('forseti_positive_points')}**")
        for e in encouraged:
            st.markdown(f"- ✨ {e}")

    # Category
    category = result.get("category")
    original = result.get("original_category")
    if category:
        cat_text = f"📁 {_('forseti_category')}: **{category}**"
        if original and original != category:
            cat_text += f" ({_('forseti_suggested')}: {original})"
        st.markdown(cat_text)

    # Confidence
    confidence = result.get("confidence", 0)
    st.progress(confidence, text=f"{_('forseti_confidence')}: {confidence:.0%}")

    # Reasoning (collapsed)
    with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
        st.markdown(result.get("reasoning", ""))


def contributions_view(user_id: str):
    """Display contributions from audierne2026/participons repository."""

    st.subheader(f"📝 {_('contributions_title')}")
    st.markdown(_("contributions_subtitle"))

    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        state_filter = st.selectbox(
            _("contributions_status"),
            options=["open", "closed", "all"],
            format_func=lambda x: {
                "open": f"🟢 {_('contributions_status_open')}",
                "closed": f"🔴 {_('contributions_status_closed')}",
                "all": f"📋 {_('contributions_status_all')}",
            }[x],
        )

    with col2:
        label_filter = st.selectbox(
            _("contributions_category"),
            options=CATEGORY_LABELS,
            format_func=lambda x: (
                f"📋 {_('contributions_category_all')}" if x == "" else x.capitalize()
            ),
        )

    with col3:
        if st.button(f"🔄 {_('contributions_refresh')}"):
            _ui_logger.log_user_action(
                action="refresh_contributions",
                user_id=user_id,
            )
            st.cache_data.clear()

    st.markdown("---")

    # Fetch issues
    with st.spinner(_("contributions_loading")):
        data = _fetch_issues(state=state_filter, labels=label_filter)

    if not data.get("success"):
        st.error(
            f"{_('contributions_error')} : {data.get('error', _('forseti_unknown_error'))}"
        )
        return

    issues = data.get("issues", [])
    count = data.get("count", 0)

    # Stats
    st.metric(_("contributions_found"), count)

    if not issues:
        st.info(_("contributions_none_found"))
        return

    # Category color mapping
    category_colors = {
        "economie": "🔵",
        "logement": "🟠",
        "culture": "🟣",
        "ecologie": "🟢",
        "associations": "🟡",
        "jeunesse": "🔴",
        "alimentation-bien-etre-soins": "🩷",
    }

    # Display issues
    for issue in issues:
        issue_id = issue.get("id")
        category = issue.get("category")
        category_icon = category_colors.get(category, "⚪")
        has_charte = issue.get("has_conforme_charte", False)
        charte_badge = "✅" if has_charte else ""

        with st.expander(
            f"{category_icon} {issue.get('title', 'Sans titre')} {charte_badge}",
            expanded=False,
        ):
            # Metadata row
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            with meta_col1:
                st.caption(
                    f"**#{issue_id}** {_('contributions_by')} {issue.get('user', 'inconnu')}"
                )
            with meta_col2:
                if category:
                    st.caption(f"📁 {category.capitalize()}")
            with meta_col3:
                if has_charte:
                    st.caption(f"✅ {_('contributions_charter_compliant')}")

            # Labels
            labels = issue.get("labels", [])
            if labels:
                st.markdown(" ".join([f"`{label}`" for label in labels]))

            # Body
            title = issue.get("title", "")
            body = issue.get("body", "")
            if body:
                st.markdown(body[:500] + ("..." if len(body) > 500 else ""))

            # Actions row
            action_col1, action_col2 = st.columns([1, 3])

            with action_col1:
                # Forseti validation button
                if st.button(
                    f"🔍 {_('contributions_verify_charter')}",
                    key=f"validate_{issue_id}",
                ):
                    _ui_logger.log_user_action(
                        action="validate_charter",
                        user_id=user_id,
                        details=f"issue_id={issue_id}",
                    )
                    with st.spinner(_("forseti_analyzing")):
                        result = _validate_with_forseti(
                            title, body, category, user_id, issue_id
                        )
                        st.session_state[f"forseti_result_{issue_id}"] = result

            with action_col2:
                # Link to GitHub
                html_url = issue.get("html_url")
                if html_url:
                    st.markdown(f"[{_('contributions_view_github')}]({html_url})")

            # Display Forseti result if available
            result_key = f"forseti_result_{issue_id}"
            if result_key in st.session_state:
                result = st.session_state[result_key]
                _display_forseti_result(result)


def documents_view(user_id: str):
    """Document corpus overview."""

    st.subheader(f"📄 {_('documents_title')}")

    # Document stats (placeholder)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            _("documents_arretes_identified"), "4,010", help=_("documents_arretes_help")
        )

    with col2:
        st.metric(
            _("documents_indexed"),
            "42",
            delta=f"🟡 {_('documents_indexed_status')}",
            help=_("documents_indexed_help"),
        )

    with col3:
        st.metric(_("documents_pipeline"), "🔴", help=_("documents_pipeline_help"))

    st.markdown("---")

    # Document sources table
    st.markdown(f"### {_('documents_sources_title')}")

    sources_data = {
        _("documents_source"): [
            _("documents_source_arretes"),
            _("documents_source_deliberations"),
            _("documents_source_commission"),
            _("documents_source_gwaien"),
        ],
        _("documents_url"): [
            "audierne.bzh/publications-arretes/",
            "audierne.bzh/deliberations-conseil-municipal/",
            "audierne.bzh/documentheque/",
            "OCR des bulletins PDF",
        ],
        _("sidebar_status"): [
            f"🔴 {_('documents_status_to_crawl')}",
            f"🔴 {_('documents_status_to_crawl')}",
            f"🔴 {_('documents_status_to_crawl')}",
            f"🟡 42 {_('documents_status_collected')}",
        ],
        _("documents_method"): [
            "Firecrawl + OCR",
            "Firecrawl + OCR",
            "Firecrawl + OCR",
            "OCR",
        ],
    }

    st.table(sources_data)

    # TODO: Add document search when implemented
    # st.text_input("🔍 Rechercher un document...", key="doc_search")


def mockup_view(user_id: str):
    """Mockup batch validation view."""

    # Wrapper for validate function that matches the expected signature
    def validate_wrapper(title: str, body: str, category: str | None) -> dict:
        return _validate_with_forseti(title, body, category, user_id, 0)

    batch_validation_view(user_id, validate_wrapper)


def about_view():
    """About page with project information."""

    st.subheader(f"ℹ️ {_('about_title')}")

    st.markdown(
        f"""
### {_('about_resolution_title')}

> *{_('about_resolution_quote')}*

{_('about_description')}

### {_('about_features_title')}

| {_('about_feature')} | {_('about_feature_description')} | {_('about_feature_status')} |
|----------------|-------------|--------|
| {_('about_feature_search')} | {_('about_feature_search_desc')} | 🔴 {_('about_status_in_dev')} |
| {_('about_feature_qa')} | {_('about_feature_qa_desc')} | 🔴 {_('about_status_in_dev')} |
| {_('about_feature_hallucination')} | {_('about_feature_hallucination_desc')} | 🟡 {_('about_status_planned')} |
| {_('about_feature_multichannel')} | {_('about_feature_multichannel_desc')} | 🟡 {_('about_status_planned')} |

### {_('about_links_title')}

- 🌐 [audierne2026.fr](https://audierne2026.fr) - {_('about_links_platform')}
- 📚 [docs.locki.io](https://docs.locki.io) - {_('about_links_docs')}
- 💻 [GitHub](https://github.com/locki-io/ocapistaine) - {_('about_links_source')}

---

*{_('about_conclusion')}*
    """
    )


if __name__ == "__main__":
    main()
