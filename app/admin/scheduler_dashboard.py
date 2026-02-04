"""
Scheduler Monitoring Dashboard

Admin interface for monitoring and controlling scheduler tasks during development.
Features:
- Scheduler status display (running/stopped, job count)
- Today's task execution status
- Manual task triggers with data source configuration
- Redis key monitor with delete capability
- Live log viewer for all application logs
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from app.services.translations import _
from app.services.logging import LOG_DIR, DOMAINS


def scheduler_dashboard_view(user_id: str):
    """Main scheduler monitoring dashboard."""

    st.subheader(_("admin_scheduler_title"))

    # Two-column layout: controls on left, logs on right
    col_controls, col_logs = st.columns([3, 2])

    with col_controls:
        # 1. Scheduler Status Header
        _display_scheduler_status()

        st.markdown("---")

        # 2. Today's Tasks
        _display_todays_tasks()

        st.markdown("---")

        # 3. Manual Triggers
        _display_manual_triggers(user_id)

        st.markdown("---")

        # 4. Opik Judge Config
        _display_opik_judge_config()

        st.markdown("---")

        # 5. Experiment Runner
        _display_experiment_runner()

        st.markdown("---")

        # 6. Redis Key Monitor
        _display_redis_keys()

    with col_logs:
        # 6. Live Log Viewer
        _display_live_logs()


def _display_scheduler_status():
    """Show scheduler running status, job count, etc."""
    from app.services.scheduler import get_scheduler_status

    status = get_scheduler_status()
    col1, col2, col3 = st.columns(3)

    with col1:
        is_running = status["status"] == "running"
        st.metric(
            _("admin_status"),
            _("admin_scheduler_running") if is_running else _("admin_scheduler_stopped"),
        )

    with col2:
        st.metric(_("admin_registered_jobs"), status["job_count"])

    with col3:
        st.metric(_("admin_current_date"), datetime.now().strftime("%Y-%m-%d"))

    # Show job details in expander
    if status["jobs"]:
        with st.expander(_("admin_job_details"), expanded=False):
            for job in status["jobs"]:
                next_run = job.get("next_run", "N/A")
                if next_run and next_run != "N/A":
                    try:
                        next_dt = datetime.fromisoformat(next_run)
                        next_run = next_dt.strftime("%H:%M:%S")
                    except ValueError:
                        pass
                st.markdown(f"- **{job['id']}**: {_('admin_next_run')} {next_run}")


def _display_todays_tasks():
    """Show task completion status for today."""
    from app.services.scheduler.utils import get_scheduler_redis

    st.markdown(f"### {_('admin_todays_tasks')}")

    redis_conn = get_scheduler_redis()
    today = datetime.now().strftime("%Y%m%d")

    tasks = [
        ("task_contributions_analysis", _("admin_task_contributions")),
        ("task_opik_experiment", _("admin_task_opik")),
        ("task_opik_evaluate", _("admin_task_opik_evaluate")),
        ("task_firecrawl", _("admin_task_firecrawl")),
    ]

    for task_id, task_label in tasks:
        success_key = f"success:{task_id}:{today}"
        lock_key = f"lock:{task_id}:{today}"

        is_completed = redis_conn.exists(success_key)
        is_running = redis_conn.exists(lock_key)

        if is_completed:
            icon = "completed"
            status = _("admin_status_completed")
            ttl = redis_conn.ttl(success_key)
            if ttl > 0:
                hours = ttl // 3600
                mins = (ttl % 3600) // 60
                status += f" (TTL: {hours}h {mins}m)"
        elif is_running:
            icon = "running"
            status = _("admin_status_running")
        else:
            icon = "pending"
            status = _("admin_status_pending")

        col1, col2 = st.columns([3, 2])
        with col1:
            if icon == "completed":
                st.markdown(f"**{task_label}**")
            elif icon == "running":
                st.markdown(f"**{task_label}**")
            else:
                st.markdown(f"**{task_label}**")
        with col2:
            if icon == "completed":
                st.success(status)
            elif icon == "running":
                st.info(status)
            else:
                st.warning(status)


def _display_manual_triggers(user_id: str):
    """Render manual task trigger buttons with data source config."""

    st.markdown(f"### {_('admin_manual_triggers')}")

    # Task configurations
    task_configs = {
        "task_contributions_analysis": {
            "label": _("admin_task_contributions"),
            "source_type": "select",
            "sources": ["Mockup Queue", "GitHub Issues", "Both"],
            "has_provider": True,
            "has_source_config": True,
        },
        "task_opik_experiment": {
            "label": _("admin_task_opik"),
            "has_provider": True,
            "has_experiment_config": True,
        },
        "task_opik_evaluate": {
            "label": _("admin_task_opik_evaluate"),
            "has_provider": True,
            "has_experiment_config": True,
            "is_evaluate_task": True,  # Flag to show evaluate-specific options
        },
        "task_firecrawl": {
            "label": _("admin_task_firecrawl"),
            "source_type": "multiselect",
            "sources": ["mairie_arretes", "mairie_deliberations", "commission_controle"],
        },
    }

    for task_name, config in task_configs.items():
        with st.expander(f"**{config['label']}** ({task_name})", expanded=False):
            # Data source selection
            if "sources" in config:
                if config.get("source_type") == "multiselect":
                    st.multiselect(
                        _("admin_sources_to_crawl"),
                        config["sources"],
                        default=config["sources"][:1],
                        key=f"sources_{task_name}",
                    )
                else:
                    st.selectbox(
                        _("admin_data_source"),
                        config["sources"],
                        key=f"source_{task_name}",
                    )

            # Source configuration with date filter and counts
            if config.get("has_source_config"):
                _display_source_config(task_name)

            if "experiments" in config:
                st.selectbox(
                    _("admin_experiment"),
                    config["experiments"],
                    key=f"exp_{task_name}",
                )

            # Experiment configuration (for Opik experiments)
            if config.get("has_experiment_config"):
                from app.services.tasks import AGENT_FEATURE_REGISTRY

                st.markdown(f"**{_('admin_experiment_config')}**")

                # Experiment type - dynamically loaded from registry
                experiment_types = list(AGENT_FEATURE_REGISTRY.keys())
                st.selectbox(
                    _("admin_experiment_type"),
                    experiment_types,
                    key=f"exp_type_{task_name}",
                    help=_("admin_experiment_type_help"),
                    format_func=lambda x: f"{x} ({AGENT_FEATURE_REGISTRY[x]['agent']})",
                )

                exp_col1, exp_col2 = st.columns(2)
                with exp_col1:
                    # Max confidence threshold
                    st.slider(
                        _("admin_max_confidence"),
                        min_value=0.1,
                        max_value=1.0,
                        value=0.5,
                        step=0.05,
                        key=f"max_confidence_{task_name}",
                        help=_("admin_max_confidence_help"),
                    )
                with exp_col2:
                    # Max items to process
                    st.slider(
                        _("admin_max_items"),
                        min_value=5,
                        max_value=200,
                        value=50,
                        step=5,
                        key=f"max_items_{task_name}",
                        help=_("admin_max_items_help"),
                    )

                # Show candidate count
                _display_experiment_candidates(task_name)

            # Provider selection with failover
            if config.get("has_provider"):
                from app.providers import OLLAMA_MODELS
                from app.services.session import get_current_provider, get_current_model

                # Get session provider as default
                session_provider = get_current_provider()
                session_model = get_current_model()

                # Display session provider info
                st.info(f"📌 {_('admin_session_provider')}: **{session_provider}** ({session_model})")

                provider_options = ["ollama", "gemini", "claude", "mistral"]
                # Put session provider first
                if session_provider in provider_options:
                    provider_options.remove(session_provider)
                    provider_options.insert(0, session_provider)

                provider_col1, provider_col2 = st.columns(2)
                with provider_col1:
                    # Initialize with session provider if not already set
                    default_idx = 0
                    current_val = st.session_state.get(f"provider_{task_name}")
                    if current_val and current_val in provider_options:
                        default_idx = provider_options.index(current_val)

                    st.selectbox(
                        _("admin_provider"),
                        provider_options,
                        index=default_idx,
                        key=f"provider_{task_name}",
                    )
                with provider_col2:
                    st.checkbox(
                        _("admin_enable_failover"),
                        value=True,
                        key=f"failover_{task_name}",
                        help=_("admin_failover_help"),
                    )

                # Show Ollama model selection if ollama is selected
                current_provider = st.session_state.get(f"provider_{task_name}", "ollama")
                if current_provider == "ollama":
                    ollama_model_options = list(OLLAMA_MODELS.keys())
                    st.selectbox(
                        _("admin_ollama_model"),
                        ollama_model_options,
                        index=ollama_model_options.index("deepseek-r1:7b"),
                        key=f"ollama_model_{task_name}",
                        help=_("admin_ollama_model_help"),
                    )
                    # Show model info
                    selected_model = st.session_state.get(
                        f"ollama_model_{task_name}", "deepseek-r1:7b"
                    )
                    if selected_model in OLLAMA_MODELS:
                        model_info = OLLAMA_MODELS[selected_model]
                        st.caption(
                            f"{model_info['description']} | "
                            f"RAM: ~{model_info['ram_gb']}GB"
                        )

                    # Ollama sleep time to prevent CPU overload
                    st.slider(
                        _("admin_ollama_sleep"),
                        min_value=0.0,
                        max_value=10.0,
                        value=2.0,
                        step=0.5,
                        key=f"ollama_sleep_{task_name}",
                        help=_("admin_ollama_sleep_help"),
                    )

            # Get provider settings if available
            provider = None
            enable_failover = True
            ollama_model = None
            ollama_sleep = None
            if config.get("has_provider"):
                provider = st.session_state.get(f"provider_{task_name}", "ollama")
                enable_failover = st.session_state.get(f"failover_{task_name}", True)
                if provider == "ollama":
                    ollama_model = st.session_state.get(
                        f"ollama_model_{task_name}", "deepseek-r1:7b"
                    )
                    ollama_sleep = st.session_state.get(
                        f"ollama_sleep_{task_name}", 2.0
                    )

            # Get experiment settings if available
            experiment_config = None
            if config.get("has_experiment_config"):
                experiment_config = {
                    "experiment_type": st.session_state.get(f"exp_type_{task_name}", "charter_optimization"),
                    "max_confidence": st.session_state.get(f"max_confidence_{task_name}", 0.5),
                    "max_items": st.session_state.get(f"max_items_{task_name}", 50),
                }

            # Get source configuration if available
            source_config = None
            if config.get("has_source_config"):
                after_date_val = st.session_state.get(f"after_date_{task_name}")
                # Convert date to string if it's a date object
                if after_date_val and hasattr(after_date_val, "isoformat"):
                    after_date_str = after_date_val.isoformat()
                else:
                    after_date_str = str(after_date_val) if after_date_val else None

                source_config = {
                    "after_date": after_date_str,
                    "source": st.session_state.get(f"source_{task_name}", "Mockup Queue"),
                    "limit": st.session_state.get(f"limit_{task_name}", 100),
                }

            # Action buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(_("admin_run_now"), key=f"run_{task_name}"):
                    _run_task(task_name, user_id, provider, enable_failover, ollama_model, ollama_sleep, experiment_config, source_config)
            with col2:
                if st.button(_("admin_clear_and_run"), key=f"clear_run_{task_name}"):
                    _clear_and_run_task(task_name, user_id, provider, enable_failover, ollama_model, ollama_sleep, experiment_config, source_config)
            with col3:
                # Force revalidate only for contributions task
                if task_name == "task_contributions_analysis":
                    if st.button(_("admin_force_revalidate"), key=f"force_{task_name}"):
                        _force_revalidate_and_run(task_name, user_id, provider, enable_failover, ollama_model, ollama_sleep)


def _display_source_config(task_name: str):
    """Display source configuration with date filter and counts."""
    from datetime import date, timedelta

    st.markdown(f"**{_('admin_source_filter')}**")

    # Date filter
    col1, col2 = st.columns(2)
    with col1:
        # Default to 7 days ago
        default_date = date.today() - timedelta(days=7)
        after_date = st.date_input(
            _("admin_after_date"),
            value=default_date,
            key=f"after_date_{task_name}",
            help=_("admin_after_date_help"),
        )

    with col2:
        # Max items to process
        st.number_input(
            _("admin_max_items"),
            min_value=1,
            max_value=500,
            value=100,
            step=10,
            key=f"limit_{task_name}",
            help=_("admin_max_items_help"),
        )

    # Display source counts
    _display_source_counts(task_name, after_date.isoformat() if after_date else None)


def _display_source_counts(task_name: str, after_date: str | None = None):
    """Display counts of records by source (Mockup Queue + GitHub Issues)."""
    # Get current selected source
    selected_source = st.session_state.get(f"source_{task_name}", "Mockup Queue")

    # Display both sources in tabs
    mockup_tab, github_tab = st.tabs(["🧪 Mockup Queue", "🐙 GitHub Issues"])

    with mockup_tab:
        _display_mockup_counts(after_date, selected_source == "Mockup Queue")

    with github_tab:
        _display_github_counts(after_date, selected_source == "GitHub Issues")


def _display_mockup_counts(after_date: str | None, is_selected: bool):
    """Display Mockup Queue counts."""
    try:
        from app.mockup.storage import get_storage

        storage = get_storage()
        counts = storage.get_source_counts(after_date=after_date, pending_only=False)

        # Display summary
        total = counts.get("total", 0)
        pending = counts.get("pending", 0)
        validated = counts.get("validated", 0)

        if is_selected:
            st.success(f"✓ {_('admin_data_source')}")

        # Source breakdown in columns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(_("admin_total_records"), total)
        with col2:
            st.metric(_("admin_pending_validation"), pending)
        with col3:
            st.metric(_("admin_already_validated"), validated)

        # Show by source if we have data
        by_source = counts.get("by_source", {})
        pending_by_source = counts.get("pending_by_source", {})

        if by_source:
            st.caption(f"**{_('admin_by_source')}:**")
            source_text = []
            for source, count in sorted(by_source.items()):
                pending_count = pending_by_source.get(source, 0)
                source_text.append(f"• {source}: {count} ({pending_count} pending)")
            st.markdown("\n".join(source_text))

        # Show date range
        date_range = counts.get("date_range", {})
        if date_range.get("min") and date_range.get("max"):
            st.caption(
                f"📅 {_('admin_date_range')}: {date_range['min']} → {date_range['max']}"
            )

    except Exception as e:
        st.caption(f"⚠️ {_('admin_error_loading_counts')}: {str(e)[:50]}")


def _display_github_counts(after_date: str | None, is_selected: bool):
    """Display GitHub Issues counts."""
    try:
        from app.services.github_issues import get_issues_counts

        counts = get_issues_counts(after_date=after_date, pending_only=False)

        # Display summary
        total = counts.get("total", 0)
        pending = counts.get("pending", 0)
        validated = counts.get("validated", 0)

        if is_selected:
            st.success(f"✓ {_('admin_data_source')}")

        # Source breakdown in columns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(_("admin_total_records"), total)
        with col2:
            st.metric(_("admin_pending_validation"), pending)
        with col3:
            st.metric(_("admin_already_validated"), validated)

        # GitHub-specific info
        st.caption(f"**{_('admin_by_source')}:** audierne2026/participons")

        # Show date range
        date_range = counts.get("date_range", {})
        if date_range.get("min") and date_range.get("max"):
            st.caption(
                f"📅 {_('admin_date_range')}: {date_range['min']} → {date_range['max']}"
            )
        else:
            st.caption("📅 Date parsed from issue titles (French format)")

    except Exception as e:
        st.caption(f"⚠️ {_('admin_error_loading_counts')}: {str(e)[:50]}")


def _display_experiment_candidates(task_name: str):
    """Display candidates from Opik spans matching current experiment criteria."""
    from app.services.tasks import get_feature_config

    max_correctness = st.session_state.get(f"max_confidence_{task_name}", 0.5)
    experiment_type = st.session_state.get(f"exp_type_{task_name}", "charter_optimization")

    # Get feature config to know which span to query
    feature_config = get_feature_config(experiment_type)
    if not feature_config:
        st.caption("⚠️ Unknown experiment type")
        return

    span_name = feature_config["feature"]

    # Two tabs: Opik Spans vs Internal Storage
    tab_opik, tab_internal = st.tabs(["🔍 Opik Spans (Correctness)", "💾 Internal (Confidence)"])

    with tab_opik:
        _display_opik_span_stats(span_name, max_correctness)

    with tab_internal:
        _display_internal_confidence_stats(max_correctness)


def _display_opik_span_stats(span_name: str, max_correctness: float):
    """Display statistics from Opik spans with Correctness feedback."""
    try:
        from app.agents.tracing import get_tracer

        tracer = get_tracer()
        if not tracer.enabled:
            st.caption("⚠️ Opik not configured")
            return

        # Query spans with Correctness below threshold
        filter_low = f'name = "{span_name}" AND feedback_scores.Correctness < {max_correctness}'
        low_spans = tracer.search_spans(filter_string=filter_low, span_type="llm", max_results=500)

        # Query all spans of this type for total count
        filter_all = f'name = "{span_name}"'
        all_spans = tracer.search_spans(filter_string=filter_all, span_type="llm", max_results=500)

        total = len(all_spans)
        matching = len(low_spans)

        # Count already added to dataset
        already_added = 0
        correctness_values = []

        for span in low_spans:
            feedback_scores = span.get("feedback_scores", [])
            for score in feedback_scores:
                if score.get("name") == "added_to_dataset":
                    already_added += 1
                if score.get("name") == "Correctness":
                    correctness_values.append(score.get("value", 0))

        new_candidates = matching - already_added

        if correctness_values:
            avg_correctness = sum(correctness_values) / len(correctness_values)
            st.markdown(
                f"**{span_name}** spans:\n"
                f"- Total: {total}\n"
                f"- Correctness < {max_correctness}: **{matching}**\n"
                f"- Already in dataset: {already_added}\n"
                f"- New candidates: **{new_candidates}**\n"
                f"- Avg Correctness: **{avg_correctness:.2f}**"
            )
        else:
            st.caption(f"📊 No {span_name} spans with Correctness < {max_correctness}")

    except Exception as e:
        st.caption(f"⚠️ Opik query error: {str(e)[:50]}")


def _display_internal_confidence_stats(max_confidence: float):
    """Display statistics from internal MockupStorage confidence."""
    try:
        from app.mockup.storage import get_storage

        storage = get_storage()
        all_records = storage.get_latest_validations(limit=1000)

        # Filter by confidence threshold
        candidates = [
            r for r in all_records
            if r.confidence < max_confidence and r.confidence > 0
        ]

        total = len(all_records)
        matching = len(candidates)

        if matching > 0:
            avg_conf = sum(r.confidence for r in candidates) / matching
            st.markdown(
                f"**MockupStorage** records:\n"
                f"- Total: {total}\n"
                f"- Confidence < {max_confidence}: **{matching}**\n"
                f"- Avg Confidence: **{avg_conf:.2f}**"
            )
        else:
            st.caption(f"📊 No records with confidence < {max_confidence}")

    except Exception as e:
        st.caption(f"⚠️ Storage error: {str(e)[:50]}")


def _run_task(
    task_name: str,
    user_id: str,
    provider: str | None = None,
    enable_failover: bool = True,
    ollama_model: str | None = None,
    ollama_sleep: float | None = None,
    experiment_config: dict | None = None,
    source_config: dict | None = None,
):
    """Execute a task manually."""
    from app.services.scheduler import run_task_now

    with st.spinner(f"{_('admin_running_task')} {task_name}..."):
        try:
            result = run_task_now(
                task_name,
                provider=provider,
                enable_failover=enable_failover,
                ollama_model=ollama_model,
                ollama_sleep=ollama_sleep,
                experiment_config=experiment_config,
                source_config=source_config,
            )
            if result["status"] == "success":
                st.success(f"{task_name} {_('admin_completed_successfully')}")
            elif result["status"] == "skipped":
                reason = result.get("reason", "unknown")
                st.warning(f"{task_name} {_('admin_skipped')}: {reason}")
            else:
                errors = result.get("errors", [])
                st.error(f"{task_name} {_('admin_failed')}: {errors}")

            with st.expander(_("admin_task_result"), expanded=False):
                st.json(result)

        except Exception as e:
            st.error(f"{_('admin_error')}: {e}")


def _clear_and_run_task(
    task_name: str,
    user_id: str,
    provider: str | None = None,
    enable_failover: bool = True,
    ollama_model: str | None = None,
    ollama_sleep: float | None = None,
    experiment_config: dict | None = None,
    source_config: dict | None = None,
):
    """Clear success key and re-run task."""
    from app.services.scheduler.utils import get_scheduler_redis

    redis_conn = get_scheduler_redis()
    today = datetime.now().strftime("%Y%m%d")
    success_key = f"success:{task_name}:{today}"

    # Delete success key
    deleted = redis_conn.delete(success_key)
    if deleted:
        st.info(f"{_('admin_cleared_key')}: {success_key}")

    # Run task
    _run_task(task_name, user_id, provider, enable_failover, ollama_model, ollama_sleep, experiment_config, source_config)


def _force_revalidate_and_run(
    task_name: str,
    user_id: str,
    provider: str | None = None,
    enable_failover: bool = True,
    ollama_model: str | None = None,
    ollama_sleep: float | None = None,
):
    """Reset confidence on all records and force revalidation."""
    from app.services.scheduler.utils import get_scheduler_redis
    from app.mockup.storage import get_storage
    from datetime import date, timedelta

    # Step 1: Reset confidence on MockupStorage records
    storage = get_storage()
    reset_count = 0

    # Get records from last 7 days
    all_records = []
    for days_ago in range(7):
        check_date = date.today() - timedelta(days=days_ago)
        records = storage.get_validations_by_date(check_date.isoformat())
        all_records.extend(records)

    # Reset confidence to 0 (mark for revalidation)
    for record in all_records:
        record.confidence = 0.0
        reset_count += 1

    # Save updated records
    if all_records:
        storage.save_batch(all_records)
        st.info(f"{_('admin_reset_confidence')}: {reset_count} records")

    # Step 2: Clear success key
    redis_conn = get_scheduler_redis()
    today = datetime.now().strftime("%Y%m%d")
    success_key = f"success:{task_name}:{today}"
    redis_conn.delete(success_key)

    # Step 3: Run task
    _run_task(task_name, user_id, provider, enable_failover, ollama_model, ollama_sleep)


def _display_opik_judge_config():
    """Display and configure Opik judge LLM settings."""
    from app.services.opik_config import (
        get_opik_judge_config,
        set_opik_judge_config,
        reset_opik_judge_config,
        list_available_judge_models,
    )

    st.markdown("### 🔬 Opik Judge LLM")
    st.caption("LLM used for Opik metrics (Hallucination, Moderation, etc.)")

    # Get current config
    config = get_opik_judge_config()
    available_models = list_available_judge_models()

    # Provider selection
    col1, col2 = st.columns(2)

    with col1:
        provider_options = list(available_models.keys())
        current_provider_idx = provider_options.index(config["provider"]) if config["provider"] in provider_options else 0

        selected_provider = st.selectbox(
            "Provider",
            provider_options,
            index=current_provider_idx,
            key="opik_judge_provider",
        )

    with col2:
        # Model selection based on provider
        model_options = [m["id"] for m in available_models.get(selected_provider, [])]
        model_labels = {m["id"]: f"{m['name']} ({m['cost']})" for m in available_models.get(selected_provider, [])}

        current_model = config["model"]
        if current_model in model_options:
            current_model_idx = model_options.index(current_model)
        else:
            current_model_idx = 0

        selected_model = st.selectbox(
            "Model",
            model_options,
            index=current_model_idx,
            format_func=lambda x: model_labels.get(x, x),
            key="opik_judge_model",
        )

    # API Key status
    api_key_env = "OPENAI_API_KEY" if selected_provider == "openai" else "ANTHROPIC_API_KEY"
    api_key_configured = config.get("api_key_configured", False)

    if api_key_configured:
        st.success(f"✓ {api_key_env} configured")
    else:
        st.warning(f"⚠️ {api_key_env} not found in environment")

    # Save / Reset buttons
    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Save Config", key="save_opik_config"):
            set_opik_judge_config(
                provider=selected_provider,
                model=selected_model,
                api_key_env=api_key_env,
            )
            st.success("Opik judge config saved")
            st.rerun()

    with col2:
        if st.button("🔄 Reset to Default", key="reset_opik_config"):
            reset_opik_judge_config()
            st.info("Reset to OpenAI gpt-4o-mini")
            st.rerun()


def _display_experiment_runner():
    """Display experiment runner UI for running Opik evaluate() on datasets."""
    from app.processors.workflows import (
        list_datasets,
        list_experiment_types,
        list_available_metrics,
        OpikExperimentConfig,
        run_opik_experiment,
    )
    from app.services.session import get_current_provider

    st.markdown("### 🧪 Run Experiment")
    st.caption("Run Opik evaluate() on an existing dataset")

    # List available datasets
    datasets = list_datasets()
    if not datasets:
        st.info("No datasets found. Create one using the task_opik_experiment task above.")
        return

    # Dataset selection
    dataset_names = [d["name"] for d in datasets]
    selected_dataset = st.selectbox(
        "Dataset",
        dataset_names,
        key="exp_dataset",
        help="Select a dataset to evaluate",
    )

    # Show dataset info
    selected_info = next((d for d in datasets if d["name"] == selected_dataset), None)
    if selected_info:
        st.caption(f"📋 {selected_info.get('description', 'No description')}")

    # Experiment configuration
    col1, col2 = st.columns(2)

    with col1:
        # Experiment type (determines which task function to use)
        experiment_types = list_experiment_types()
        type_options = [t["type"] for t in experiment_types]
        type_labels = {t["type"]: f"{t['type']} ({t['agent']})" for t in experiment_types}

        selected_type = st.selectbox(
            "Experiment Type",
            type_options,
            key="exp_type_runner",
            format_func=lambda x: type_labels.get(x, x),
            help="Determines which evaluation task to run",
        )

    with col2:
        # Task provider (sidebar LLM for running Forseti)
        session_provider = get_current_provider()
        provider_options = ["gemini", "claude", "ollama", "mistral"]
        if session_provider in provider_options:
            provider_options.remove(session_provider)
            provider_options.insert(0, session_provider)

        task_provider = st.selectbox(
            "Task Provider",
            provider_options,
            key="exp_task_provider",
            help="LLM used to run Forseti validation (task LLM)",
        )

    # Metrics selection
    available_metrics = list_available_metrics()
    metric_options = [m["name"] for m in available_metrics]
    metric_labels = {m["name"]: f"{m['name']}: {m['description']}" for m in available_metrics}

    # Default metrics
    default_metrics = ["hallucination", "moderation"]
    default_idx = [metric_options.index(m) for m in default_metrics if m in metric_options]

    selected_metrics = st.multiselect(
        "Metrics",
        metric_options,
        default=[metric_options[i] for i in default_idx],
        key="exp_metrics",
        format_func=lambda x: metric_labels.get(x, x),
        help="Opik judge metrics to evaluate (uses judge LLM configured above)",
    )

    # Experiment name
    today = datetime.now().strftime("%Y%m%d")
    default_exp_name = f"{selected_type}-eval-{today}"
    experiment_name = st.text_input(
        "Experiment Name",
        value=default_exp_name,
        key="exp_name",
        help="Name for this experiment in Opik",
    )

    # Run button
    if st.button("🚀 Run Experiment", key="run_experiment"):
        if not selected_metrics:
            st.error("Select at least one metric")
            return

        with st.spinner(f"Running experiment '{experiment_name}'..."):
            try:
                config = OpikExperimentConfig(
                    experiment_name=experiment_name,
                    dataset_name=selected_dataset,
                    experiment_type=selected_type,
                    metrics=selected_metrics,
                    task_provider=task_provider,
                )

                st.info(f"📊 Config: {config.to_dict()}")

                result = run_opik_experiment(config)

                if result["status"] == "success":
                    st.success(f"✅ Experiment '{experiment_name}' completed!")
                    with st.expander("Results", expanded=True):
                        st.json(result.get("eval_results", {}))
                else:
                    st.error(f"❌ Experiment failed: {result.get('errors', [])}")

                with st.expander("Full Result", expanded=False):
                    st.json(result)

            except Exception as e:
                st.error(f"Error running experiment: {e}")
                import traceback
                st.code(traceback.format_exc())


def _display_redis_keys():
    """Show scheduler Redis keys with delete option."""
    from app.services.scheduler.utils import get_scheduler_redis

    st.markdown(f"### {_('admin_redis_keys')}")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button(_("admin_refresh_keys")):
            st.rerun()

    redis_conn = get_scheduler_redis()
    today = datetime.now().strftime("%Y%m%d")

    # Get all keys for today
    success_keys = list(redis_conn.keys(f"success:*:{today}"))
    lock_keys = list(redis_conn.keys(f"lock:*:{today}"))

    all_keys = success_keys + lock_keys

    if not all_keys:
        st.info(_("admin_no_keys_found"))
        return

    for key in sorted(all_keys):
        ttl = redis_conn.ttl(key)
        if ttl > 0:
            hours = ttl // 3600
            mins = (ttl % 3600) // 60
            ttl_str = f"{hours}h {mins}m"
        else:
            ttl_str = _("admin_no_ttl")

        key_type = "success" if key.startswith("success:") else "lock"

        col1, col2, col3 = st.columns([4, 2, 1])
        with col1:
            st.code(key, language=None)
        with col2:
            st.caption(f"{_('admin_key_type')}: {key_type} | TTL: {ttl_str}")
        with col3:
            if st.button(_("admin_delete"), key=f"del_{key}"):
                redis_conn.delete(key)
                st.rerun()


def _display_live_logs():
    """Display live logs from all application log files."""

    st.markdown(f"### {_('admin_live_logs')}")

    # Controls row
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 1])

    with ctrl_col1:
        # Domain filter
        domain_options = ["all"] + list(DOMAINS.keys())
        selected_domain = st.selectbox(
            _("admin_log_domain"),
            domain_options,
            key="log_domain_filter",
            label_visibility="collapsed",
        )

    with ctrl_col2:
        # Number of lines
        num_lines = st.selectbox(
            _("admin_log_lines"),
            [50, 100, 200, 500],
            index=1,
            key="log_num_lines",
            label_visibility="collapsed",
        )

    with ctrl_col3:
        if st.button(_("admin_refresh_logs"), key="refresh_logs"):
            st.rerun()

    # Auto-refresh toggle
    auto_refresh = st.checkbox(
        _("admin_auto_refresh"),
        value=False,
        key="log_auto_refresh",
        help=_("admin_auto_refresh_help"),
    )

    if auto_refresh:
        st.caption(_("admin_auto_refresh_active"))
        # Trigger rerun after 5 seconds
        import time
        time.sleep(0.1)  # Small delay to allow UI to render
        st.rerun()

    # Read and display logs
    logs = _read_combined_logs(selected_domain, num_lines)

    if not logs:
        st.info(_("admin_no_logs"))
    else:
        # Reverse order so newest logs appear first
        logs_reversed = list(reversed(logs))
        log_text = "\n".join(logs_reversed)
        st.code(log_text, language="log", line_numbers=False)


def _read_combined_logs(domain: str = "all", num_lines: int = 100) -> list[str]:
    """
    Read logs from specified domain(s), sorted by timestamp.

    Args:
        domain: Domain name or "all" for combined logs
        num_lines: Number of lines to return (most recent)

    Returns:
        List of log lines sorted by timestamp (oldest first, caller reverses for display)
    """
    log_files = []

    if domain == "all":
        # Collect all log files
        for domain_name, config in DOMAINS.items():
            log_file = LOG_DIR / config["log_file"]
            if log_file.exists():
                log_files.append(log_file)
    else:
        # Single domain
        if domain in DOMAINS:
            log_file = LOG_DIR / DOMAINS[domain]["log_file"]
            if log_file.exists():
                log_files.append(log_file)

    if not log_files:
        return []

    # Read all log entries with timestamps
    all_entries = []

    for log_file in log_files:
        try:
            # Read last N*2 lines from each file (we'll sort and trim later)
            lines = _tail_file(log_file, num_lines * 2)
            all_entries.extend(lines)
        except Exception:
            continue

    if not all_entries:
        return []

    # Sort by timestamp (logs start with "YYYY-MM-DD HH:MM:SS")
    # Entries without valid timestamp go to the end
    def sort_key(line: str) -> str:
        if len(line) >= 19 and line[4] == "-" and line[10] == " ":
            return line[:19]
        return "9999-99-99 99:99:99"

    all_entries.sort(key=sort_key)

    # Return only the last num_lines
    return all_entries[-num_lines:]


def _tail_file(filepath: Path, num_lines: int) -> list[str]:
    """
    Read the last N lines from a file efficiently.

    Args:
        filepath: Path to the file
        num_lines: Number of lines to read

    Returns:
        List of lines
    """
    try:
        with open(filepath, "rb") as f:
            # Seek to end
            f.seek(0, 2)
            file_size = f.tell()

            if file_size == 0:
                return []

            # Read in chunks from the end
            chunk_size = 8192
            lines = []
            position = file_size

            while position > 0 and len(lines) < num_lines + 1:
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size).decode("utf-8", errors="replace")

                # Split and prepend to lines
                chunk_lines = chunk.split("\n")

                if lines:
                    # Merge with existing first line
                    lines[0] = chunk_lines[-1] + lines[0]
                    chunk_lines = chunk_lines[:-1]

                lines = chunk_lines + lines

            # Filter empty lines and return last N
            lines = [line.strip() for line in lines if line.strip()]
            return lines[-num_lines:]

    except Exception:
        return []
