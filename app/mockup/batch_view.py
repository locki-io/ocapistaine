# app/mockup/batch_view.py
"""
Batch Validation View

Streamlit UI component for batch testing contributions with Forseti.
Uses Framaforms contribution format (constat_factuel + idees_ameliorations).

Features:
- Load/generate mock contributions
- Batch validation with Forseti
- Store results in Redis (contribution_mockup:forseti461:charter)
- Export to Opik datasets for prompt optimization
"""

import time
from datetime import date
from typing import List, Optional, Callable

import streamlit as st

from app.i18n import _
from app.mockup.generator import (
    ContributionGenerator,
    MockContribution,
    load_contributions,
    save_contributions,
    generate_variations,
)
from app.mockup.levenshtein import levenshtein_ratio
from app.mockup.storage import (
    get_storage,
    ValidationRecord,
    MockupStorage,
)
from app.mockup.dataset import (
    get_dataset_manager,
    create_optimization_dataset,
    DATASET_TRAINING,
    DATASET_VALIDATION,
    DATASET_TEST,
)
from app.services import AgentLogger
from app.data.redis_client import health_check as redis_health_check

_logger = AgentLogger("batch_validation")


def batch_validation_view(user_id: str, validate_func: Callable) -> None:
    """
    Render the batch validation view.

    Args:
        user_id: Current user ID
        validate_func: Function to validate a contribution (title, body, category) -> dict
    """
    st.subheader("🧪 Batch Validation (Mockup)")
    st.markdown(
        "Test Forseti validation with mock contributions using Levenshtein-based variations. "
        "Contributions follow the Framaforms format: **Constat factuel** + **Vos idées d'améliorations**."
    )

    # Mode selection
    mode = st.radio(
        "Mode",
        options=["load_existing", "generate_new", "from_contribution", "storage_opik"],
        format_func=lambda x: {
            "load_existing": "📂 Load Existing Mockups",
            "generate_new": "🔧 Generate Variations",
            "from_contribution": "📝 Single Contribution Test",
            "storage_opik": "💾 Storage & Opik",
        }[x],
        horizontal=True,
        key="batch_mode",
    )

    st.markdown("---")

    if mode == "load_existing":
        _load_existing_view(user_id, validate_func)
    elif mode == "generate_new":
        _generate_new_view(user_id, validate_func)
    elif mode == "storage_opik":
        _storage_opik_view(user_id)
    else:
        _from_contribution_view(user_id, validate_func)


def _load_existing_view(user_id: str, validate_func: Callable) -> None:
    """Load and validate existing mockup contributions."""
    generator = load_contributions()

    if not generator.contributions:
        st.warning("No mockup contributions found. Use 'Generate Variations' to create some.")
        return

    st.success(f"Loaded **{len(generator.contributions)}** contributions")

    # Filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        source_filter = st.multiselect(
            "Source",
            options=["framaforms", "mock", "derived", "input"],
            default=["framaforms", "mock", "derived"],
            key="source_filter",
        )
    with col2:
        categories = list(set(c.category for c in generator.contributions if c.category))
        category_filter = st.multiselect(
            "Category",
            options=categories,
            default=[],
            key="category_filter",
        )
    with col3:
        validity_filter = st.selectbox(
            "Expected validity",
            options=["all", "valid", "invalid"],
            key="validity_filter",
        )

    # Filter contributions
    filtered = generator.contributions
    if source_filter:
        filtered = [c for c in filtered if c.source in source_filter]
    if category_filter:
        filtered = [c for c in filtered if c.category in category_filter]
    if validity_filter == "valid":
        filtered = [c for c in filtered if c.expected_valid is True]
    elif validity_filter == "invalid":
        filtered = [c for c in filtered if c.expected_valid is False]

    st.info(f"**{len(filtered)}** contributions match filters")

    # Display contributions
    _display_contributions_list(filtered, validate_func, user_id)


def _generate_new_view(user_id: str, validate_func: Callable) -> None:
    """Generate new variations from base contributions."""
    generator = load_contributions()

    # Get base contributions only (not derived)
    base_contributions = [
        c for c in generator.contributions
        if c.source in ["framaforms", "mock", "input"] and not c.parent_id
    ]

    if not base_contributions:
        st.warning("No base contributions found. Add some to contributions.json first.")
        return

    st.info(f"Found **{len(base_contributions)}** base contributions")

    # Generation settings
    col1, col2, col3 = st.columns(3)
    with col1:
        variations_per_base = st.slider(
            "Variations per base",
            min_value=1,
            max_value=10,
            value=5,
            key="variations_count",
        )
    with col2:
        include_violations = st.checkbox(
            "Include progressive violations",
            value=True,
            key="include_violations",
        )
    with col3:
        max_distance = st.slider(
            "Max distance ratio",
            min_value=0.1,
            max_value=0.5,
            value=0.3,
            key="max_distance",
        )

    # Select which bases to use
    base_options = {c.id: f"{c.category or 'N/A'}: {c.constat_factuel[:50]}..." for c in base_contributions}
    selected_bases = st.multiselect(
        "Select base contributions to vary",
        options=list(base_options.keys()),
        format_func=lambda x: base_options[x],
        default=[base_contributions[0].id] if base_contributions else [],
        key="selected_bases",
    )

    if st.button("🔄 Generate Variations", type="primary", key="generate_btn"):
        if not selected_bases:
            st.error("Select at least one base contribution")
            return

        with st.spinner("Generating variations..."):
            new_generator = ContributionGenerator()

            for base_id in selected_bases:
                base = next(c for c in base_contributions if c.id == base_id)
                new_generator.contributions.append(base)

                # Generate variation series
                new_generator.generate_variation_series(
                    parent=base,
                    num_variations=variations_per_base,
                    max_distance_ratio=max_distance,
                    progressive_violations=include_violations,
                )

            # Save generated contributions
            save_contributions(new_generator)

            st.success(f"Generated **{len(new_generator.contributions)}** contributions (saved to file)")
            st.rerun()


def _from_contribution_view(user_id: str, validate_func: Callable) -> None:
    """Generate variations from a single contribution input."""

    st.markdown("### Create variations from a contribution")
    st.caption("Enter a contribution in Framaforms format to generate Levenshtein variations.")

    col1, col2 = st.columns([1, 3])
    with col1:
        category = st.selectbox(
            "Category",
            options=[
                None, "economie", "logement", "culture", "ecologie",
                "associations", "jeunesse", "alimentation-bien-etre-soins"
            ],
            format_func=lambda x: "-- Select --" if x is None else x.capitalize(),
            key="input_category",
        )

    constat = st.text_area(
        "Constat factuel",
        value="Le parking du port est souvent plein en été, ce qui oblige les visiteurs à se garer loin ou de manière sauvage. Cela crée des problèmes de circulation et nuit à l'image de la commune.",
        height=100,
        key="input_constat",
    )

    idees = st.text_area(
        "Vos idées d'améliorations",
        value="Créer un parking relais à l'entrée de la ville avec une navette gratuite vers le port. Mettre en place un système de stationnement payant pour les non-résidents afin de favoriser la rotation. Développer les pistes cyclables pour encourager les déplacements doux.",
        height=100,
        key="input_idees",
    )

    col1, col2 = st.columns(2)
    with col1:
        num_variations = st.slider(
            "Number of variations",
            min_value=2,
            max_value=10,
            value=5,
            key="input_num_variations",
        )
    with col2:
        inject_violations = st.checkbox(
            "Inject violations progressively",
            value=True,
            key="input_inject_violations",
        )

    if st.button("🧬 Generate Variations", type="primary", key="generate_single_btn"):
        if not constat.strip():
            st.error("Please enter a factual observation")
            return

        with st.spinner("Generating variations..."):
            variations = generate_variations(
                constat_factuel=constat,
                idees_ameliorations=idees,
                category=category,
                num_variations=num_variations,
                include_violations=inject_violations,
            )
            st.session_state["temp_variations"] = variations

    # Display generated variations
    if "temp_variations" in st.session_state:
        variations = st.session_state["temp_variations"]
        st.markdown(f"### Generated {len(variations)} variations")

        # Convert to MockContribution objects for display
        mock_contribs = [MockContribution.from_dict(v) for v in variations]
        _display_contributions_list(mock_contribs, validate_func, user_id)


def _display_contributions_list(
    contributions: List[MockContribution],
    validate_func: Callable,
    user_id: str,
) -> None:
    """Display contributions with validation controls."""

    if not contributions:
        st.info("No contributions to display")
        return

    # Batch validation controls
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🚀 Validate All", type="primary", key="validate_all_btn"):
            _run_batch_validation(contributions, validate_func, user_id)

    with col2:
        if st.button("🗑️ Clear Results", key="clear_results_btn"):
            if "batch_results" in st.session_state:
                del st.session_state["batch_results"]
            st.rerun()

    with col3:
        if "batch_results" in st.session_state:
            results = st.session_state["batch_results"]
            valid_count = sum(1 for r in results.values() if r.get("is_valid"))
            matches = sum(1 for cid, r in results.items() if _check_expected_match(cid, r, contributions))
            st.markdown(
                f"**Results:** {valid_count}/{len(results)} valid • "
                f"{matches}/{len(results)} match expected"
            )

    st.markdown("---")

    # Display each contribution
    for i, contrib in enumerate(contributions):
        _display_contribution_card(contrib, validate_func, user_id, i)


def _check_expected_match(contrib_id: str, result: dict, contributions: List[MockContribution]) -> bool:
    """Check if result matches expected validity."""
    contrib = next((c for c in contributions if c.id == contrib_id), None)
    if not contrib or contrib.expected_valid is None:
        return True
    return result.get("is_valid") == contrib.expected_valid


def _display_contribution_card(
    contrib: MockContribution,
    validate_func: Callable,
    user_id: str,
    index: int,
) -> None:
    """Display a single contribution card with validation."""

    # Source badges
    source_badges = {
        "framaforms": "📋",
        "mock": "🎭",
        "derived": "🔀",
        "input": "📝",
    }
    badge = source_badges.get(contrib.source, "📄")

    # Expected validity indicator
    validity_indicator = ""
    if contrib.expected_valid is True:
        validity_indicator = "✅"
    elif contrib.expected_valid is False:
        validity_indicator = "⚠️"

    # Check if we have validation results
    result = st.session_state.get("batch_results", {}).get(contrib.id)
    result_indicator = ""
    if result:
        if result.get("success"):
            result_indicator = "🟢" if result.get("is_valid") else "🔴"
        else:
            result_indicator = "❌"

    # Build header
    title_preview = contrib.constat_factuel[:50] + "..." if len(contrib.constat_factuel) > 50 else contrib.constat_factuel
    header = f"{badge} [{contrib.category or 'N/A'}] {title_preview} {validity_indicator}{result_indicator}"

    with st.expander(header, expanded=False):
        # Metadata row
        meta_cols = st.columns(4)
        with meta_cols[0]:
            st.caption(f"**ID:** `{contrib.id[:8]}`")
        with meta_cols[1]:
            st.caption(f"**Source:** {contrib.source}")
        with meta_cols[2]:
            if contrib.similarity_to_parent is not None:
                st.caption(f"**Similarity:** {contrib.similarity_to_parent:.1%}")
        with meta_cols[3]:
            if contrib.distance_from_parent is not None:
                st.caption(f"**Distance:** {contrib.distance_from_parent}")

        # Parent info for derived contributions
        if contrib.parent_id:
            st.caption(f"↳ Derived from `{contrib.parent_id[:8]}`")

        # Violations injected
        if contrib.violations_injected:
            st.warning(f"**Violations injected:** {', '.join(contrib.violations_injected)}")

        # Contribution content
        st.markdown("**Constat factuel:**")
        st.markdown(f"> {contrib.constat_factuel}")

        if contrib.idees_ameliorations:
            st.markdown("**Vos idées d'améliorations:**")
            st.markdown(f"> {contrib.idees_ameliorations}")

        # Validation result if available
        if result:
            st.markdown("---")
            _display_validation_result(result, contrib.expected_valid)

        # Individual validation button
        if st.button(f"🔍 Validate", key=f"validate_single_{contrib.id}_{index}"):
            with st.spinner("Validating..."):
                result = validate_func(contrib.title, contrib.body, contrib.category)
                if "batch_results" not in st.session_state:
                    st.session_state["batch_results"] = {}
                st.session_state["batch_results"][contrib.id] = result
                st.rerun()


def _run_batch_validation(
    contributions: List[MockContribution],
    validate_func: Callable,
    user_id: str,
    save_to_redis: bool = True,
) -> None:
    """Run validation on all contributions and optionally save to Redis."""

    _logger.info("BATCH_START", count=len(contributions), user_id=user_id[:8] if user_id else None)
    start_time = time.time()
    today = date.today().isoformat()

    results = {}
    records_to_save = []
    progress_bar = st.progress(0, text="Validating...")

    storage = get_storage() if save_to_redis else None

    for i, contrib in enumerate(contributions):
        progress = (i + 1) / len(contributions)
        progress_bar.progress(progress, text=f"Validating {i+1}/{len(contributions)}: {contrib.id[:8]}...")
        item_start = time.time()

        try:
            result = validate_func(contrib.title, contrib.body, contrib.category)
            results[contrib.id] = result

            # Create validation record for Redis storage
            if save_to_redis and result.get("success"):
                record = ValidationRecord(
                    id=contrib.id,
                    date=today,
                    title=contrib.title,
                    body=contrib.body,
                    category=contrib.category,
                    constat_factuel=contrib.constat_factuel,
                    idees_ameliorations=contrib.idees_ameliorations,
                    is_valid=result.get("is_valid", True),
                    violations=result.get("violations", []),
                    encouraged_aspects=result.get("encouraged_aspects", []),
                    confidence=result.get("confidence", 0.0),
                    reasoning=result.get("reasoning", ""),
                    suggested_category=result.get("category"),
                    category_confidence=result.get("category_confidence", 0.0),
                    category_reasoning=result.get("category_reasoning", ""),
                    source=contrib.source,
                    expected_valid=contrib.expected_valid,
                    parent_id=contrib.parent_id,
                    similarity_to_parent=contrib.similarity_to_parent,
                    distance_from_parent=contrib.distance_from_parent,
                    violations_injected=contrib.violations_injected or [],
                    execution_time_ms=int((time.time() - item_start) * 1000),
                    trace_id=result.get("trace_id"),
                )
                records_to_save.append(record)

        except Exception as e:
            results[contrib.id] = {"success": False, "error": str(e)}

    total_time = time.time() - start_time
    progress_bar.empty()

    # Save to Redis
    saved_count = 0
    if storage and records_to_save:
        saved_count = storage.save_batch(records_to_save)
        _logger.info("REDIS_SAVE", saved=saved_count)

    st.session_state["batch_results"] = results

    # Calculate summary
    successful = [r for r in results.values() if r.get("success")]
    valid_count = sum(1 for r in successful if r.get("is_valid"))
    matches_expected = sum(
        1 for cid, r in results.items()
        if _check_expected_match(cid, r, contributions)
    )

    _logger.info(
        "BATCH_COMPLETE",
        count=len(contributions),
        valid=valid_count,
        matches_expected=matches_expected,
        saved_to_redis=saved_count,
        total_time_ms=f"{total_time*1000:.0f}",
    )

    summary = (
        f"Validated **{len(contributions)}** contributions in **{total_time:.1f}s**\n\n"
        f"- ✅ Valid: {valid_count}/{len(successful)}\n"
        f"- 🎯 Matches expected: {matches_expected}/{len(contributions)}"
    )
    if saved_count:
        summary += f"\n- 💾 Saved to Redis: {saved_count} records"

    st.success(summary)


def _display_validation_result(result: dict, expected_valid: Optional[bool]) -> None:
    """Display validation result inline."""

    if not result.get("success"):
        st.error(f"❌ Validation error: {result.get('error', 'Unknown')}")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        if result.get("is_valid"):
            st.success("✅ Valid")
        else:
            st.warning("⚠️ Invalid")

    with col2:
        confidence = result.get("confidence", 0)
        st.metric("Confidence", f"{confidence:.0%}")

    with col3:
        if expected_valid is not None:
            matches = result.get("is_valid") == expected_valid
            if matches:
                st.success("🎯 Matches expected")
            else:
                st.error("❌ Mismatch!")

    # Violations
    violations = result.get("violations", [])
    if violations:
        st.markdown("**Violations detected:**")
        for v in violations[:5]:  # Limit display
            st.markdown(f"- ❌ {v}")
        if len(violations) > 5:
            st.caption(f"... and {len(violations) - 5} more")

    # Positive aspects
    encouraged = result.get("encouraged_aspects", [])
    if encouraged:
        st.markdown("**Positive aspects:**")
        for e in encouraged[:3]:
            st.markdown(f"- ✨ {e}")


def _storage_opik_view(user_id: str) -> None:
    """Storage and Opik dataset management view."""

    st.markdown("### 💾 Redis Storage & Opik Datasets")
    st.caption(
        "Validation results are stored in Redis with key format: "
        "`contribution_mockup:forseti461:charter:{date}:{id}`"
    )

    # Check Redis connection
    redis_ok = redis_health_check()
    if redis_ok:
        st.success("🟢 Redis connected")
    else:
        st.error("🔴 Redis not connected")
        st.info("Start Redis or check your configuration (REDIS_PORT, REDIS_DB)")
        return

    storage = get_storage()
    manager = get_dataset_manager()

    # Tabs for different operations
    tab1, tab2, tab3 = st.tabs(["📊 Statistics", "📥 Load Data", "📤 Export to Opik"])

    with tab1:
        _render_statistics_tab(storage, manager)

    with tab2:
        _render_load_data_tab(storage)

    with tab3:
        _render_export_opik_tab(storage, manager)


def _render_statistics_tab(storage: MockupStorage, manager) -> None:
    """Render statistics tab content."""

    st.markdown("#### Validation Statistics")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Today's validations:**")
        today_stats = storage.get_statistics(date.today().isoformat())
        if today_stats.get("count", 0) > 0:
            st.metric("Total", today_stats["count"])
            st.metric("Valid", f"{today_stats['valid_count']} ({today_stats['valid_ratio']:.0%})")
            if today_stats.get("accuracy") is not None:
                st.metric("Accuracy", f"{today_stats['accuracy']:.0%}")
            st.caption(f"Sources: {today_stats.get('sources', {})}")
        else:
            st.info("No validations today. Run batch validation to populate.")

    with col2:
        st.markdown("**Latest validations (all dates):**")
        latest_stats = storage.get_statistics()
        if latest_stats.get("count", 0) > 0:
            st.metric("Cached", latest_stats["count"])
            st.metric("Avg Confidence", f"{latest_stats.get('avg_confidence', 0):.0%}")
            if latest_stats.get("with_expected", 0) > 0:
                st.caption(
                    f"With expected: {latest_stats['with_expected']} | "
                    f"Matches: {latest_stats['matches_expected']}"
                )
        else:
            st.info("No cached validations.")

    # Opik status
    st.markdown("---")
    st.markdown("#### Opik Integration")
    if manager.opik_enabled:
        st.success("🟢 Opik connected")
        st.caption(f"Datasets will be synced to Opik for prompt optimization")
    else:
        st.warning("🟡 Opik not configured")
        st.caption("Set OPIK_API_KEY to enable dataset sync")


def _render_load_data_tab(storage: MockupStorage) -> None:
    """Render load data tab content."""

    st.markdown("#### Load Validation Records")

    col1, col2 = st.columns(2)

    with col1:
        load_date = st.date_input(
            "Select date",
            value=date.today(),
            key="load_date",
        )

    with col2:
        load_limit = st.number_input(
            "Max records",
            min_value=10,
            max_value=1000,
            value=100,
            key="load_limit",
        )

    if st.button("📥 Load Records", key="load_records_btn"):
        date_str = load_date.isoformat()
        records = storage.get_validations_by_date(date_str)

        if records:
            st.success(f"Loaded **{len(records)}** records from {date_str}")

            # Display as table
            table_data = []
            for r in records[:load_limit]:
                table_data.append({
                    "ID": r.id[:8],
                    "Category": r.category or "N/A",
                    "Valid": "✅" if r.is_valid else "❌",
                    "Confidence": f"{r.confidence:.0%}",
                    "Source": r.source,
                    "Match": "🎯" if r.matches_expected() else ("❌" if r.matches_expected() is False else "-"),
                })

            st.dataframe(table_data, use_container_width=True)

            # Export option
            if st.button("📋 Copy as JSON", key="copy_json_btn"):
                import json
                json_data = [r.to_dict() for r in records]
                st.code(json.dumps(json_data[:5], indent=2), language="json")
                st.caption(f"Showing first 5 of {len(records)} records")
        else:
            st.info(f"No records found for {date_str}")

    # Clear data section
    st.markdown("---")
    st.markdown("#### Clear Data")

    clear_date = st.date_input(
        "Date to clear",
        value=date.today(),
        key="clear_date",
    )

    if st.button("🗑️ Clear Date", key="clear_date_btn", type="secondary"):
        deleted = storage.clear_date(clear_date.isoformat())
        if deleted > 0:
            st.success(f"Deleted **{deleted}** records from {clear_date.isoformat()}")
        else:
            st.info("No records to delete")


def _render_export_opik_tab(storage: MockupStorage, manager) -> None:
    """Render Opik export tab content."""

    st.markdown("#### Export to Opik Dataset")
    st.caption(
        "Create datasets for prompt optimization. "
        "Datasets include input (title, body, category) and expected output (is_valid, violations, etc.)"
    )

    # Dataset name
    dataset_name = st.text_input(
        "Dataset name",
        value=f"forseti-charter-{date.today().isoformat()}",
        key="dataset_name",
    )

    # Source filters
    col1, col2 = st.columns(2)

    with col1:
        export_date = st.date_input(
            "From date (empty for all latest)",
            value=None,
            key="export_date",
        )
        source_filter = st.multiselect(
            "Source filter",
            options=["framaforms", "mock", "derived", "input"],
            default=[],
            key="export_source_filter",
        )

    with col2:
        valid_filter = st.selectbox(
            "Validity filter",
            options=["all", "valid_only", "invalid_only"],
            key="export_valid_filter",
        )

    # Export button
    if st.button("📤 Create Dataset", type="primary", key="export_opik_btn"):
        with st.spinner("Creating dataset..."):
            date_str = export_date.isoformat() if export_date else None
            valid_only = True if valid_filter == "valid_only" else (False if valid_filter == "invalid_only" else None)

            # Create dataset
            manager.create_charter_dataset(dataset_name, f"Charter validation dataset from {date_str or 'latest'}")

            # Add from Redis
            count = manager.add_from_redis(
                dataset_name=dataset_name,
                date_str=date_str,
                source_filter=source_filter if source_filter else None,
                valid_only=valid_only,
            )

            if count > 0:
                st.success(f"Created dataset **{dataset_name}** with **{count}** items")

                # Show stats
                stats = manager.get_dataset_stats(dataset_name)
                st.json(stats)

                # Sync to Opik
                if manager.opik_enabled:
                    synced = manager.sync_to_opik(dataset_name)
                    if synced:
                        st.success(f"Synced to Opik: {synced}")
            else:
                st.warning("No data to export. Run batch validation first.")

    # Train/Val/Test split
    st.markdown("---")
    st.markdown("#### Create Train/Val/Test Split")
    st.caption("Split data for proper optimization evaluation")

    col1, col2, col3 = st.columns(3)
    with col1:
        train_ratio = st.slider("Training %", 50, 80, 70, key="train_ratio") / 100
    with col2:
        val_ratio = st.slider("Validation %", 10, 30, 15, key="val_ratio") / 100
    with col3:
        test_ratio = 1.0 - train_ratio - val_ratio
        st.metric("Test %", f"{test_ratio:.0%}")

    if st.button("🔀 Create Split", key="create_split_btn"):
        with st.spinner("Creating split..."):
            split_date = export_date.isoformat() if export_date else None
            result = manager.create_train_val_test_split(
                source_date=split_date,
                train_ratio=train_ratio,
                val_ratio=val_ratio,
                test_ratio=test_ratio,
            )

            if sum(result.values()) > 0:
                st.success("Created datasets:")
                st.json(result)

                # Sync all
                if manager.opik_enabled:
                    for ds_name in [DATASET_TRAINING, DATASET_VALIDATION, DATASET_TEST]:
                        manager.sync_to_opik(ds_name)
                    st.success("Synced all datasets to Opik")
            else:
                st.warning("No data to split. Run batch validation first.")
