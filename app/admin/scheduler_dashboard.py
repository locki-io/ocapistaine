"""
Scheduler Monitoring Dashboard

Admin interface for monitoring and controlling scheduler tasks during development.
Features:
- Scheduler status display (running/stopped, job count)
- Today's task execution status
- Manual task triggers with data source configuration
- Redis key monitor with delete capability
"""

from datetime import datetime

import streamlit as st

from app.services.translations import _


def scheduler_dashboard_view(user_id: str):
    """Main scheduler monitoring dashboard."""

    st.subheader(_("admin_scheduler_title"))

    # 1. Scheduler Status Header
    _display_scheduler_status()

    st.markdown("---")

    # 2. Today's Tasks
    _display_todays_tasks()

    st.markdown("---")

    # 3. Manual Triggers
    _display_manual_triggers(user_id)

    st.markdown("---")

    # 4. Redis Key Monitor
    _display_redis_keys()


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
            "sources": ["GitHub Issues", "Mockup Queue", "Both"],
            "has_provider": True,
        },
        "task_opik_experiment": {
            "label": _("admin_task_opik"),
            "source_type": "select",
            "experiments": ["forseti_validation", "category_classification"],
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

            if "experiments" in config:
                st.selectbox(
                    _("admin_experiment"),
                    config["experiments"],
                    key=f"exp_{task_name}",
                )

            # Provider selection with failover
            if config.get("has_provider"):
                from app.providers import OLLAMA_MODELS

                provider_col1, provider_col2 = st.columns(2)
                with provider_col1:
                    st.selectbox(
                        _("admin_provider"),
                        ["gemini", "claude", "mistral", "ollama"],
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
                current_provider = st.session_state.get(f"provider_{task_name}", "gemini")
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

            # Get provider settings if available
            provider = None
            enable_failover = True
            ollama_model = None
            if config.get("has_provider"):
                provider = st.session_state.get(f"provider_{task_name}", "gemini")
                enable_failover = st.session_state.get(f"failover_{task_name}", True)
                if provider == "ollama":
                    ollama_model = st.session_state.get(
                        f"ollama_model_{task_name}", "deepseek-r1:7b"
                    )

            # Action buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(_("admin_run_now"), key=f"run_{task_name}"):
                    _run_task(task_name, user_id, provider, enable_failover, ollama_model)
            with col2:
                if st.button(_("admin_clear_and_run"), key=f"clear_run_{task_name}"):
                    _clear_and_run_task(task_name, user_id, provider, enable_failover, ollama_model)
            with col3:
                # Force revalidate only for contributions task
                if task_name == "task_contributions_analysis":
                    if st.button(_("admin_force_revalidate"), key=f"force_{task_name}"):
                        _force_revalidate_and_run(task_name, user_id, provider, enable_failover, ollama_model)


def _run_task(
    task_name: str,
    user_id: str,
    provider: str | None = None,
    enable_failover: bool = True,
    ollama_model: str | None = None,
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
    _run_task(task_name, user_id, provider, enable_failover, ollama_model)


def _force_revalidate_and_run(
    task_name: str,
    user_id: str,
    provider: str | None = None,
    enable_failover: bool = True,
    ollama_model: str | None = None,
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
    _run_task(task_name, user_id, provider, enable_failover, ollama_model)


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
