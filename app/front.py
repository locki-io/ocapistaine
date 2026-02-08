# front.py
"""
OCapistaine - Citizen Q&A Interface

Simplified Streamlit UI for civic transparency.
User identification via single UUID (cookie-based).
"""

import asyncio
import json
import os
import time

import requests
import streamlit as st

# MUST be first Streamlit command
st.set_page_config(
    page_title="Ò Capistaine - Civic Transparency",
    page_icon="🏛️",
    layout="wide",
)


@st.cache_resource
def _init_scheduler():
    """Initialize the APScheduler once per Streamlit server session.

    Disabled by default on cloud deployments (DISABLE_SCHEDULER=true)
    to reduce memory footprint on free tier instances.
    """
    # Skip scheduler on demo/cloud instances to save memory
    if os.getenv("DISABLE_SCHEDULER", "false").lower() == "true":
        return "disabled"

    try:
        from app.services.scheduler import start_scheduler, scheduler

        # Only start if not already running
        if scheduler is None or not scheduler.running:
            # Run the async start_scheduler in an event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(start_scheduler())

        # Return scheduler reference to keep it alive
        return scheduler
    except Exception as e:
        # Only log once (cache_resource ensures single call)
        print(f"Scheduler init skipped: {e}")
        return None


# Start scheduler on app load (cached - runs once per server session)
_scheduler = _init_scheduler()

# Authentication check (before loading any other content)
from app.auth import check_password

if not check_password():
    st.stop()

from app.sidebar import sidebar_setup, get_user_id, get_selected_provider, get_model_id
from app.agents.forseti import ForsetiAgent
from app.agents.forseti.features import AnonymizationFeature
from app.providers import get_provider
from app.services.translations import _
from app.services import PresentationLogger, ServiceLogger, AgentLogger
from app.mockup.batch_view import batch_validation_view
from app.auto_contribution import autocontribution_view
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
        "autocontrib": ("✨", "tab_autocontrib"),
        "documents": ("📄", "tab_documents"),
        "admin": ("⚙️", "tab_admin"),
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
    elif current_tab == "autocontrib":
        autocontribution_view(user_id)
    elif current_tab == "documents":
        documents_view(user_id)
    elif current_tab == "mockup":
        mockup_view(user_id)
    elif current_tab == "admin":
        from app.admin import scheduler_dashboard_view

        scheduler_dashboard_view(user_id)
    elif current_tab == "about":
        about_view()


# N8N Webhook URLs
N8N_ISSUES_WEBHOOK = "https://vaettir.locki.io/webhook/participons/issues"
N8N_CHARTER_VALID_WEBHOOK = "https://vaettir.locki.io/webhook/forseti/charter-valid"


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

        # Notify N8N to add label if valid
        n8n_action = None
        if result.is_valid and issue_id:
            try:
                label_response = requests.post(
                    N8N_CHARTER_VALID_WEBHOOK,
                    json={
                        "issueNumber": issue_id,
                        "is_valid": result.is_valid,
                        "category": result.category,
                        "confidence": result.confidence,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                if label_response.ok:
                    n8n_data = label_response.json()
                    # Handle array response from N8N
                    if isinstance(n8n_data, list) and len(n8n_data) > 0:
                        n8n_data = n8n_data[0]
                    n8n_action = {
                        "success": n8n_data.get("success", False),
                        "assigned_to_ocapistaine": n8n_data.get("success", False),
                        "reason": n8n_data.get("reason", ""),
                        "new_category": n8n_data.get("new_category"),
                        "category_labels": n8n_data.get("category_labels", []),
                    }
                    _ui_logger.log_webhook(
                        source="n8n",
                        event_type="charter_valid",
                        success=n8n_action["success"],
                    )
                    _agent_logger.info(
                        "N8N_CHARTER_ACTION",
                        issue_id=issue_id,
                        assigned=n8n_action["assigned_to_ocapistaine"],
                        reason=n8n_action["reason"],
                    )
                else:
                    n8n_action = {
                        "success": False,
                        "assigned_to_ocapistaine": False,
                        "reason": f"HTTP {label_response.status_code}",
                    }
            except json.JSONDecodeError as e:
                _agent_logger.warning(
                    "N8N_CHARTER_WEBHOOK_INVALID_JSON",
                    issue_id=issue_id,
                    error=str(e),
                )
                n8n_action = {
                    "success": False,
                    "assigned_to_ocapistaine": False,
                    "reason": "N8N returned invalid response",
                }
            except requests.RequestException as e:
                _agent_logger.warning(
                    "N8N_CHARTER_WEBHOOK_FAILED",
                    issue_id=issue_id,
                    error=str(e),
                )
                n8n_action = {
                    "success": False,
                    "assigned_to_ocapistaine": False,
                    "reason": str(e),
                }

        return {
            "success": True,
            "is_valid": result.is_valid,
            "category": result.category,
            "original_category": result.original_category,
            "violations": result.violations,
            "encouraged_aspects": result.encouraged_aspects,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
            "n8n_action": n8n_action,
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

    # N8N Action result (if available)
    n8n_action = result.get("n8n_action")
    if n8n_action:
        st.markdown("---")
        if n8n_action.get("assigned_to_ocapistaine"):
            st.success(f"🤖 {_('forseti_assigned_ocapistaine')}")
            if n8n_action.get("category_labels"):
                labels = ", ".join(n8n_action["category_labels"])
                st.caption(f"Labels: {labels}")
        else:
            reason = n8n_action.get("reason", "")
            st.info(f"ℹ️ {reason}")


def _classify_with_forseti(
    title: str, body: str, category: str | None, user_id: str
) -> dict:
    """Classify a contribution with Forseti agent."""
    start_time = time.time()

    _agent_logger.log_agent_start(
        task="classify_contribution",
        input_data=title,
    )

    try:
        agent = get_forseti_agent()
        result = asyncio.run(
            agent.classify_category(title=title, body=body, category=category)
        )

        latency_ms = (time.time() - start_time) * 1000

        _agent_logger.log_agent_complete(
            task="classify_contribution",
            success=True,
            latency_ms=latency_ms,
            output_summary=f"category={result.category}, confidence={result.confidence:.2f}",
        )

        return {
            "success": True,
            "result_type": "classification",
            "category": result.category,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000

        _agent_logger.log_agent_complete(
            task="classify_contribution",
            success=False,
            latency_ms=latency_ms,
            output_summary=str(e)[:50],
        )

        return {"success": False, "result_type": "classification", "error": str(e)}


def _anonymize_with_forseti(title: str, body: str, user_id: str) -> dict:
    """Anonymize a contribution with Forseti anonymization feature."""
    start_time = time.time()

    _agent_logger.log_agent_start(
        task="anonymize_contribution",
        input_data=title,
    )

    try:
        # Combine title and body for anonymization
        text = f"{title}\n\n{body}"

        # Get provider and run anonymization feature
        provider_name = get_selected_provider()
        model_id = get_model_id()
        provider = get_provider(provider_name, model=model_id, cache=False)

        feature = AnonymizationFeature()
        result = asyncio.run(
            feature.execute(provider=provider, system_prompt="", text=text)
        )

        latency_ms = (time.time() - start_time) * 1000

        _agent_logger.log_agent_complete(
            task="anonymize_contribution",
            success=True,
            latency_ms=latency_ms,
            output_summary=f"entities={len(result.entities)}, keywords={len(result.keywords_extracted)}",
        )

        return {
            "success": True,
            "result_type": "anonymization",
            "anonymized_text": result.anonymized_text,
            "entities": [
                {
                    "original": e.original,
                    "anonymized": e.anonymized,
                    "type": e.entity_type.value,
                }
                for e in result.entities
            ],
            "entity_mapping": result.entity_mapping,
            "keywords_extracted": result.keywords_extracted,
            "reasoning": result.reasoning,
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000

        _agent_logger.log_agent_complete(
            task="anonymize_contribution",
            success=False,
            latency_ms=latency_ms,
            output_summary=str(e)[:50],
        )

        return {"success": False, "result_type": "anonymization", "error": str(e)}


def _display_classification_result(result: dict):
    """Display Forseti classification result."""
    st.markdown("---")
    st.markdown(f"**📊 {_('forseti_classification_title')}**")

    if not result.get("success"):
        st.error(
            f"{_('forseti_error')}: {result.get('error', _('forseti_unknown_error'))}"
        )
        return

    # Category
    category = result.get("category")
    if category:
        st.success(f"📁 {_('forseti_category')}: **{category.capitalize()}**")

    # Confidence
    confidence = result.get("confidence", 0)
    st.progress(confidence, text=f"{_('forseti_confidence')}: {confidence:.0%}")

    # Reasoning (collapsed)
    with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
        st.markdown(result.get("reasoning", ""))


def _display_anonymization_result(result: dict):
    """Display Forseti anonymization result."""
    st.markdown("---")
    st.markdown(f"**🔒 {_('forseti_anonymization_title')}**")

    if not result.get("success"):
        st.error(
            f"{_('forseti_error')}: {result.get('error', _('forseti_unknown_error'))}"
        )
        return

    # Entities found
    entities = result.get("entities", [])
    if entities:
        st.metric(_("forseti_entities_found"), len(entities))
        with st.expander("🔍 Entity mapping", expanded=False):
            for e in entities:
                st.markdown(f"- `{e['original']}` → `{e['anonymized']}` ({e['type']})")

    # Keywords extracted
    keywords = result.get("keywords_extracted", [])
    if keywords:
        st.markdown(f"**{_('forseti_keywords_extracted')}:** {', '.join(keywords)}")

    # Anonymized preview
    anonymized_text = result.get("anonymized_text", "")
    if anonymized_text:
        with st.expander(f"📄 {_('forseti_anonymized_preview')}", expanded=True):
            st.markdown(
                anonymized_text[:500] + ("..." if len(anonymized_text) > 500 else "")
            )

    # Reasoning (collapsed)
    reasoning = result.get("reasoning")
    if reasoning:
        with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
            st.markdown(reasoning)


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

            # Actions row - Forseti features
            action_col1, action_col2, action_col3, action_col4 = st.columns(
                [1, 1, 1, 2]
            )

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
                # Forseti classification button
                if st.button(
                    f"📊 {_('contributions_classify')}",
                    key=f"classify_{issue_id}",
                ):
                    _ui_logger.log_user_action(
                        action="classify_contribution",
                        user_id=user_id,
                        details=f"issue_id={issue_id}",
                    )
                    with st.spinner(_("forseti_classifying")):
                        result = _classify_with_forseti(title, body, category, user_id)
                        st.session_state[f"classify_result_{issue_id}"] = result

            with action_col3:
                # Forseti anonymization button
                if st.button(
                    f"🔒 {_('contributions_anonymize')}",
                    key=f"anonymize_{issue_id}",
                ):
                    _ui_logger.log_user_action(
                        action="anonymize_contribution",
                        user_id=user_id,
                        details=f"issue_id={issue_id}",
                    )
                    with st.spinner(_("forseti_anonymizing")):
                        result = _anonymize_with_forseti(title, body, user_id)
                        st.session_state[f"anonymize_result_{issue_id}"] = result

            with action_col4:
                # Link to GitHub
                html_url = issue.get("html_url")
                if html_url:
                    st.markdown(f"[{_('contributions_view_github')}]({html_url})")

            # Display Forseti validation result if available
            result_key = f"forseti_result_{issue_id}"
            if result_key in st.session_state:
                result = st.session_state[result_key]
                _display_forseti_result(result)

            # Display classification result if available
            classify_key = f"classify_result_{issue_id}"
            if classify_key in st.session_state:
                result = st.session_state[classify_key]
                _display_classification_result(result)

            # Display anonymization result if available
            anonymize_key = f"anonymize_result_{issue_id}"
            if anonymize_key in st.session_state:
                result = st.session_state[anonymize_key]
                _display_anonymization_result(result)


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
