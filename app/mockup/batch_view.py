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
- Floating overlay for action results (validate/classify/anonymize)
"""

import asyncio
import time
from datetime import date
from typing import List, Optional, Callable

import streamlit as st

from app.services.translations import _
from app.ui.floating_overlay import (
    init_floating_overlay,
    render_floating_overlay,
    add_to_overlay,
    clear_overlay,
)
from app.providers import get_provider
from app.agents.forseti import ForsetiAgent
from app.agents.forseti.features import AnonymizationFeature, TranslationFeature
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
from app.services.logging import MockupLogger
from app.data.redis_client import health_check as redis_health_check
from app.mockup.field_input import (
    list_audierne_docs,
    read_markdown_input,
    process_field_input_sync,
    FieldInputResult,
)
from app.agents.forseti import CATEGORIES

_logger = MockupLogger("batch_validation")

# Cached Forseti agent for classification
_forseti_agent = None


def _get_forseti_agent() -> ForsetiAgent:
    """Get or create cached Forseti agent."""
    global _forseti_agent
    if _forseti_agent is None:
        from app.providers.config import get_config

        config = get_config()
        provider = get_provider(config.default_provider)
        _forseti_agent = ForsetiAgent(provider)
    return _forseti_agent


def _classify_mockup_contribution(title: str, body: str, category: str | None) -> dict:
    """Classify a mockup contribution with Forseti agent."""
    try:
        agent = _get_forseti_agent()
        result = asyncio.run(
            agent.classify_category(title=title, body=body, category=category)
        )
        return {
            "success": True,
            "result_type": "classification",
            "category": result.category,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }
    except Exception as e:
        _logger.error("CLASSIFY_ERROR", error=str(e))
        return {"success": False, "result_type": "classification", "error": str(e)}


def _anonymize_mockup_contribution(title: str, body: str) -> dict:
    """Anonymize a mockup contribution with Forseti anonymization feature."""
    try:
        text = f"{title}\n\n{body}"
        from app.providers.config import get_config

        config = get_config()
        provider = get_provider(config.default_provider, cache=False)

        feature = AnonymizationFeature()
        result = asyncio.run(
            feature.execute(provider=provider, system_prompt="", text=text)
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
        _logger.error("ANONYMIZE_ERROR", error=str(e))
        return {"success": False, "result_type": "anonymization", "error": str(e)}


def _display_classification_result(result: dict):
    """Display Forseti classification result."""
    st.markdown(f"**📊 {_('forseti_classification_title')}**")

    if not result.get("success"):
        st.error(
            f"{_('forseti_error')}: {result.get('error', _('forseti_unknown_error'))}"
        )
        return

    category = result.get("category")
    if category:
        st.success(f"📁 {_('forseti_category')}: **{category.capitalize()}**")

    confidence = result.get("confidence", 0)
    st.progress(confidence, text=f"{_('forseti_confidence')}: {confidence:.0%}")

    with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
        st.markdown(result.get("reasoning", ""))


def _display_anonymization_result(result: dict):
    """Display Forseti anonymization result."""
    st.markdown(f"**🔒 {_('forseti_anonymization_title')}**")

    if not result.get("success"):
        st.error(
            f"{_('forseti_error')}: {result.get('error', _('forseti_unknown_error'))}"
        )
        return

    entities = result.get("entities", [])
    if entities:
        st.metric(_("forseti_entities_found"), len(entities))
        with st.expander("🔍 Entity mapping", expanded=False):
            for e in entities:
                st.markdown(f"- `{e['original']}` → `{e['anonymized']}` ({e['type']})")

    keywords = result.get("keywords_extracted", [])
    if keywords:
        st.markdown(f"**{_('forseti_keywords_extracted')}:** {', '.join(keywords)}")

    anonymized_text = result.get("anonymized_text", "")
    if anonymized_text:
        with st.expander(f"📄 {_('forseti_anonymized_preview')}", expanded=True):
            st.markdown(
                anonymized_text[:500] + ("..." if len(anonymized_text) > 500 else "")
            )

    reasoning = result.get("reasoning")
    if reasoning:
        with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
            st.markdown(reasoning)


def batch_validation_view(user_id: str, validate_func: Callable) -> None:
    """
    Render the batch validation view.

    Args:
        user_id: Current user ID
        validate_func: Function to validate a contribution (title, body, category) -> dict
    """
    # Initialize floating overlay for action results
    init_floating_overlay()

    st.subheader("🧪 Batch Validation (Mockup)")
    st.markdown(
        "Test Forseti validation with mock contributions using Levenshtein-based variations. "
        "Contributions follow the Framaforms format: **Constat factuel** + **Vos idées d'améliorations**."
    )

    # Mode selection
    mode = st.radio(
        "Mode",
        options=[
            "load_existing",
            "generate_new",
            "from_contribution",
            "field_input",
            "storage_opik",
        ],
        format_func=lambda x: {
            "load_existing": "📂 Load Existing Mockups",
            "generate_new": "🔧 Generate Variations",
            "from_contribution": "📝 Single Contribution Test",
            "field_input": "📋 Field Input (Reports/Docs)",
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
    elif mode == "field_input":
        _field_input_view(user_id, validate_func)
    elif mode == "storage_opik":
        _storage_opik_view(user_id)
    else:
        _from_contribution_view(user_id, validate_func)

    # Render floating overlay for action results
    render_floating_overlay()


def _load_contributions_with_redis_fallback() -> tuple[list, str]:
    """
    Load contributions from Redis first, fall back to JSON file.

    Returns:
        Tuple of (contributions list, source description)
    """
    # First try Redis storage
    try:
        storage = get_storage()
        redis_records = storage.get_latest_validations(limit=200)
        if redis_records:
            # Convert ValidationRecords to MockContribution-like format
            contributions = []
            for r in redis_records:
                contrib = MockContribution(
                    id=r.id,
                    category=r.category,
                    constat_factuel=r.constat_factuel,
                    idees_ameliorations=r.idees_ameliorations,
                    source=r.source,
                    expected_valid=r.expected_valid,
                    violations_injected=(
                        r.violations_injected if r.violations_injected else None
                    ),
                    parent_id=r.parent_id,
                    similarity_to_parent=r.similarity_to_parent,
                    distance_from_parent=r.distance_from_parent,
                )
                contributions.append(contrib)
            return contributions, "Redis"
    except Exception:
        pass  # Fall through to file fallback

    # Fall back to JSON file
    generator = load_contributions()
    return generator.contributions, "JSON file"


def _load_existing_view(user_id: str, validate_func: Callable) -> None:
    """Load and validate existing mockup contributions."""
    st.session_state["current_batch_view"] = "load_existing"

    # Cache contributions in session state to avoid reloading on every rerun
    if "cached_contributions" not in st.session_state or st.session_state.get(
        "reload_contributions"
    ):
        contributions, source = _load_contributions_with_redis_fallback()
        st.session_state["cached_contributions"] = contributions
        st.session_state["cached_contributions_source"] = source
        st.session_state["reload_contributions"] = False
    else:
        contributions = st.session_state["cached_contributions"]
        source = st.session_state.get("cached_contributions_source", "cache")

    if not contributions:
        st.warning(
            "No mockup contributions found. Use 'Generate Variations' to create some."
        )
        return

    col_info, col_reload = st.columns([4, 1])
    with col_info:
        st.success(f"Loaded **{len(contributions)}** contributions from {source}")
    with col_reload:
        if st.button("🔄", key="reload_contributions_btn", help="Reload from storage"):
            st.session_state["reload_contributions"] = True
            st.rerun()

    # Filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        source_filter = st.multiselect(
            "Source",
            options=["framaforms", "mock", "derived", "input"],
            default=["framaforms", "mock", "derived", "input"],
            key="source_filter",
        )
    with col2:
        categories = list(set(c.category for c in contributions if c.category))
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
    filtered = contributions
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
    """Generate new variations from base contributions using LLM."""
    st.session_state["current_batch_view"] = "generate_new"
    generator = load_contributions()

    # Get base contributions only (not derived)
    base_contributions = [
        c
        for c in generator.contributions
        if c.source in ["framaforms", "mock", "input"] and not c.parent_id
    ]

    if not base_contributions:
        st.warning("No base contributions found. Add some to contributions.json first.")
        return

    st.info(f"Found **{len(base_contributions)}** base contributions")

    # LLM provider from sidebar
    from app.services.session import get_session_provider, get_session_model

    session_provider = get_session_provider(user_id)
    session_model = get_session_model(user_id)

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
        st.caption(f"🤖 **{session_provider}**")
        st.caption(f"`{session_model or 'default'}`")

    # Select which bases to use
    base_options = {
        c.id: f"{c.category or 'N/A'}: {c.constat_factuel[:50]}..."
        for c in base_contributions
    }
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

        with st.spinner("Generating LLM variations..."):
            new_generator = ContributionGenerator()

            for base_id in selected_bases:
                base = next(c for c in base_contributions if c.id == base_id)
                new_generator.contributions.append(base)

                # Generate LLM variation series
                new_generator.generate_llm_variation_series(
                    parent=base,
                    num_variations=variations_per_base,
                    include_violations=include_violations,
                    provider_name=session_provider,
                    model=session_model,
                )

            # Save generated contributions
            save_contributions(new_generator)

            st.success(
                f"Generated **{len(new_generator.contributions)}** contributions (saved to file)"
            )
            st.rerun()


def _load_random_contribution(category: str | None, language: str) -> bool:
    """
    Load a random real contribution from GitHub issues.

    If language is 'en', translates the contribution to English using LLM.
    Directly updates session state keys used by text_area widgets.

    Returns:
        True if contribution was loaded successfully
    """
    import random
    from app.services.github_issues import fetch_issues

    try:
        # Fetch issues from GitHub
        result = fetch_issues(state="all", per_page=100)
        if not result.get("success") or not result.get("issues"):
            st.warning("Could not fetch contributions from GitHub")
            return False

        issues = result["issues"]

        # Filter by category if specified
        if category:
            issues = [i for i in issues if i.get("category") == category]
            if not issues:
                st.warning(f"No contributions found for category: {category}")
                return False

        # Pick a random issue
        issue = random.choice(issues)
        body = issue.get("body", "")

        # Parse body to extract constat and idees
        constat, idees = _parse_contribution_body(body)

        # Store French version
        st.session_state["loaded_contrib_constat_fr"] = constat
        st.session_state["loaded_contrib_idees_fr"] = idees

        # Translate if English
        if language == "en" and (constat or idees):
            translated_constat, translated_idees = _translate_contribution(
                constat, idees
            )
            if translated_constat != constat or translated_idees != idees:
                st.session_state["loaded_contrib_constat_en"] = translated_constat
                st.session_state["loaded_contrib_idees_en"] = translated_idees
                _logger.info("TRANSLATION_SUCCESS", language=language)
            else:
                st.session_state["loaded_contrib_constat_en"] = ""
                st.session_state["loaded_contrib_idees_en"] = ""
                _logger.warning("TRANSLATION_UNCHANGED", language=language)
        else:
            st.session_state["loaded_contrib_constat_en"] = ""
            st.session_state["loaded_contrib_idees_en"] = ""

        # Store loaded contribution info
        # GitHub API uses "number" for issue number, but some APIs use "id"
        issue_number = issue.get("number") or issue.get("id") or "?"
        st.session_state["loaded_contrib_issue"] = issue_number
        st.session_state["loaded_contrib_category"] = category
        # Use French for the main fields (used for generation)
        st.session_state["loaded_contrib_constat"] = constat
        st.session_state["loaded_contrib_idees"] = idees

        _logger.info(
            "RANDOM_CONTRIB_LOADED",
            issue=issue_number,
            category=category,
            translated=(language == "en"),
        )
        return True

    except Exception as e:
        _logger.error("RANDOM_CONTRIB_ERROR", error=str(e))
        st.error(f"Error loading contribution: {e}")
        return False


def _parse_contribution_body(body: str) -> tuple[str, str]:
    """
    Parse contribution body to extract constat factuel and idees.

    Framaforms format uses exact markers (always in this order):
    - "Constat factuel:"
    - "Vos idées d'améliorations:"
    """
    if not body:
        return "", ""

    constat = ""
    idees = ""

    # Exact markers from Framaforms
    constat_marker = "Constat factuel:"
    idees_marker = "Vos idées d'améliorations:"

    constat_start = body.find(constat_marker)
    idees_start = body.find(idees_marker)

    if constat_start != -1 and idees_start != -1:
        # Extract constat (between constat marker and idees marker)
        constat = body[constat_start + len(constat_marker) : idees_start].strip()
        # Extract idees (after idees marker)
        idees = body[idees_start + len(idees_marker) :].strip()
    elif constat_start != -1:
        # Only constat found
        constat = body[constat_start + len(constat_marker) :].strip()
    elif idees_start != -1:
        # Only idees found
        idees = body[idees_start + len(idees_marker) :].strip()
    else:
        # No markers - use entire body as constat
        constat = body.strip()

    return constat[:2000], idees[:2000]  # Limit length


def _translate_contribution(constat: str, idees: str) -> tuple[str, str]:
    """Translate contribution from French to English using Forseti TranslationFeature."""
    import asyncio
    from app.providers import get_provider

    try:
        # Use OpenAI for translation (more reliable, avoids Gemini rate limits)
        provider = get_provider("openai", cache=False)
        _logger.info("TRANSLATION_START", provider="openai")

        feature = TranslationFeature()
        result = asyncio.run(
            feature.execute(
                provider=provider,
                system_prompt="",
                constat=constat,
                idees=idees,
            )
        )

        if result.success:
            _logger.info("TRANSLATION_SUCCESS")
            return result.translated_constat, result.translated_idees
        else:
            _logger.warning("TRANSLATION_FAILED")
            return constat, idees

    except Exception as e:
        _logger.error("TRANSLATION_ERROR", error=str(e))
        st.warning(f"Translation failed: {e}")
        return constat, idees


def _from_contribution_view(user_id: str, validate_func: Callable) -> None:
    """Generate variations from a single contribution input."""
    from app.services.translations import get_language

    # Track current view for session persistence
    st.session_state["current_batch_view"] = "from_contribution"

    st.markdown("### Create variations from a contribution")
    st.caption("Enter a contribution in Framaforms format to generate variations.")

    # Default values
    default_constat = "Le parking du port est souvent plein en été, ce qui oblige les visiteurs à se garer loin ou de manière sauvage. Cela crée des problèmes de circulation et nuit à l'image de la commune."
    default_idees = "Créer un parking relais à l'entrée de la ville avec une navette gratuite vers le port. Mettre en place un système de stationnement payant pour les non-résidents afin de favoriser la rotation. Développer les pistes cyclables pour encourager les déplacements doux."

    # Initialize session state for this view if needed
    if "contrib_constat" not in st.session_state:
        st.session_state["contrib_constat"] = default_constat
    if "contrib_idees" not in st.session_state:
        st.session_state["contrib_idees"] = default_idees

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        category = st.selectbox(
            "Category",
            options=[
                None,
                "economie",
                "logement",
                "culture",
                "ecologie",
                "associations",
                "jeunesse",
                "alimentation-bien-etre-soins",
            ],
            format_func=lambda x: "-- Select --" if x is None else x.capitalize(),
            key="contrib_category",
        )

    with col2:
        if st.button(
            "🎲 Random",
            key="random_contrib_btn",
            help="Load a random real contribution",
        ):
            lang = get_language()
            spinner_msg = "Loading & translating..." if lang == "en" else "Loading..."
            with st.spinner(spinner_msg):
                if _load_random_contribution(category, lang):
                    # Update the text area values from loaded contribution
                    st.session_state["contrib_constat"] = st.session_state.get(
                        "loaded_contrib_constat", default_constat
                    )
                    st.session_state["contrib_idees"] = st.session_state.get(
                        "loaded_contrib_idees", default_idees
                    )
                    issue_num = st.session_state.get("loaded_contrib_issue", "?")
                    st.toast(f"Loaded #{issue_num}" + (" (EN)" if lang == "en" else ""))
                    st.rerun()

    # Show source info if loaded from random
    if st.session_state.get("loaded_contrib_issue"):
        st.caption(
            f"📋 Source: GitHub issue #{st.session_state['loaded_contrib_issue']}"
        )

    # Check if we have English translations to show side by side
    has_translation = bool(
        st.session_state.get("loaded_contrib_constat_en")
        or st.session_state.get("loaded_contrib_idees_en")
    )

    if has_translation:
        # Two-column layout: French | English
        col_fr, col_en = st.columns(2)

        with col_fr:
            st.markdown("**🇫🇷 Français (original)**")
            constat = st.text_area(
                "Constat factuel",
                height=100,
                key="contrib_constat",
            )
            idees = st.text_area(
                "Vos idées d'améliorations",
                height=100,
                key="contrib_idees",
            )

        with col_en:
            st.markdown("**🇬🇧 English (translated)**")
            st.text_area(
                "Factual observation",
                value=st.session_state.get("loaded_contrib_constat_en", ""),
                height=100,
                key="contrib_constat_en_display",
                disabled=True,
            )
            st.text_area(
                "Improvement ideas",
                value=st.session_state.get("loaded_contrib_idees_en", ""),
                height=100,
                key="contrib_idees_en_display",
                disabled=True,
            )
    else:
        # Single column: just French
        constat = st.text_area(
            "Constat factuel",
            height=100,
            key="contrib_constat",
        )
        idees = st.text_area(
            "Vos idées d'améliorations",
            height=100,
            key="contrib_idees",
        )

    # Mutation settings
    st.markdown("#### Mutation Settings")
    col1, col2, col3 = st.columns(3)
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
            "Include violations",
            value=True,
            key="input_inject_violations",
        )
    # LLM provider from sidebar
    from app.services.session import (
        get_session_provider,
        get_session_model,
        get_full_model_id,
    )

    session_provider = get_session_provider(user_id)
    session_model = get_session_model(user_id)
    full_model_id = get_full_model_id(session_provider, session_model)

    with col3:
        st.caption(f"🤖 **{session_provider}** / `{full_model_id}`")
        st.caption("Paraphrase, typos, violations...")

    if st.button("🧬 Generate Variations", type="primary", key="generate_single_btn"):
        if not constat.strip():
            st.error("Please enter a factual observation")
            return

        with st.spinner("Generating LLM variations..."):
            variations = generate_variations(
                constat_factuel=constat,
                idees_ameliorations=idees,
                category=category,
                use_llm=True,
                llm_provider=session_provider,
                llm_model=session_model,
                num_variations=num_variations,
                include_violations=inject_violations,
            )
            st.session_state["temp_variations"] = variations

            # Save to Redis
            saved_count = _save_variations_to_redis(variations)
            st.success(f"💾 Saved {saved_count} records")

    # Display generated variations
    if "temp_variations" in st.session_state:
        variations = st.session_state["temp_variations"]
        st.markdown(f"### Generated {len(variations)} variations")

        # Convert to MockContribution objects for display
        mock_contribs = [MockContribution.from_dict(v) for v in variations]
        _display_contributions_list(mock_contribs, validate_func, user_id)


def _field_input_view(user_id: str, validate_func: Callable) -> None:
    """Generate themed contributions from field input (reports, docs, speeches)."""
    st.session_state["current_batch_view"] = "field_input"
    st.markdown("### 📋 Field Input - Generate Themed Contributions")
    st.caption(
        "Generate mockup contributions from real field data (public hearing reports, "
        "mayor speeches, municipal documents). The LLM extracts themes and generates "
        "contributions across all 7 categories."
    )

    # Input source selection
    st.markdown("#### 1. Select Input Source")

    input_source = st.radio(
        "Input source",
        options=["audierne_docs", "paste_text", "upload_file"],
        format_func=lambda x: {
            "audierne_docs": "📚 Audierne2026 Docs",
            "paste_text": "📝 Paste Text",
            "upload_file": "📤 Upload File",
        }[x],
        horizontal=True,
        key="field_input_source",
    )

    input_text = ""
    source_file = None
    source_title = ""

    if input_source == "audierne_docs":
        # List available audierne2026 docs
        docs = list_audierne_docs()
        if docs:
            doc_options = {d["path"]: f"{d['title']} ({d['filename']})" for d in docs}
            selected_doc = st.selectbox(
                "Select document",
                options=list(doc_options.keys()),
                format_func=lambda x: doc_options[x],
                key="selected_audierne_doc",
            )
            if selected_doc:
                input_text = read_markdown_input(selected_doc)
                source_file = selected_doc
                source_title = doc_options[selected_doc]

                # Preview
                with st.expander("📖 Preview document", expanded=False):
                    st.markdown(
                        input_text[:2000] + ("..." if len(input_text) > 2000 else "")
                    )
        else:
            st.warning("No documents found in docs/docs/audierne2026/")

    elif input_source == "paste_text":
        source_title = st.text_input(
            "Source title (e.g., 'Voeux du maire 2026')",
            value="",
            key="paste_source_title",
        )
        input_text = st.text_area(
            "Paste your text here",
            value=st.session_state.get("paste_input_text", ""),
            height=300,
            key="paste_input_text",
            placeholder="Collez ici le contenu d'un rapport d'audience publique, "
            "d'un discours du maire, ou tout autre document municipal...",
        )
        if input_text:
            st.caption(f"Length: {len(input_text):,} characters")

    else:  # upload_file
        uploaded_file = st.file_uploader(
            "Upload a markdown or text file",
            type=["md", "txt"],
            key="upload_field_input",
        )
        if uploaded_file:
            # Cache file content in session_state (file can only be read once per upload)
            cache_key = f"uploaded_content_{uploaded_file.name}_{uploaded_file.size}"
            if cache_key not in st.session_state:
                st.session_state[cache_key] = uploaded_file.read().decode("utf-8")
                st.session_state["uploaded_file_name"] = uploaded_file.name

            input_text = st.session_state[cache_key]
            source_file = uploaded_file.name
            source_title = uploaded_file.name

            # Preview
            with st.expander("📖 Preview uploaded file", expanded=False):
                st.markdown(
                    input_text[:3000] + ("..." if len(input_text) > 2000 else "")
                )
                st.caption(f"Length: {len(input_text):,} characters")

    # Generation settings
    st.markdown("#### 2. Generation Settings")

    col1, col2 = st.columns(2)
    with col1:
        contributions_per_theme = st.slider(
            "Contributions per theme",
            min_value=1,
            max_value=5,
            value=2,
            key="field_contribs_per_theme",
        )
    with col2:
        include_violations = st.checkbox(
            "Include violations",
            value=True,
            key="field_include_violations",
            help="Generate subtle and aggressive violation examples",
        )

    # LLM Provider - use sidebar session settings
    st.markdown("#### 2b. LLM Provider")
    st.caption("Uses the provider/model selected in the sidebar.")

    from app.services.session import (
        get_session_provider,
        get_session_model,
        get_full_model_id,
    )

    # Get provider/model from sidebar session
    session_provider = get_session_provider(user_id)
    session_model = get_session_model(user_id)
    full_model_id = get_full_model_id(session_provider, session_model)

    # Display current provider/model
    provider_labels = {
        "openai": "🧠 OpenAI",
        "claude": "🤖 Claude",
        "gemini": "🌐 Gemini",
        "mistral": "🌬️ Mistral",
        "ollama": "💻 Ollama",
    }
    provider_label = provider_labels.get(session_provider, session_provider)
    st.info(f"📌 **{provider_label}** / `{full_model_id}`")

    # Experiment option
    st.markdown("#### 3. Options")

    run_experiment = st.checkbox(
        "📊 Run Opik Experiment",
        value=False,
        key="field_run_experiment",
        help="Run validation and report to Opik after generation",
    )

    # Provider status check
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔍 Check Provider", key="field_check_provider"):
            from app.providers import get_provider

            try:
                provider = get_provider(
                    session_provider, cache=False, model=full_model_id
                )
                st.success(f"✓ {session_provider} ({provider.model}) ready")
            except Exception as e:
                st.warning(f"✗ {session_provider}: {e}")

    # Generate button
    st.markdown("---")

    # Check if already processing (only lock for Ollama - local resource constraint)
    is_ollama = session_provider == "ollama"
    is_processing = is_ollama and st.session_state.get("ollama_processing", False)

    if is_processing:
        st.warning("⏳ Ollama is processing a request. Please wait for it to complete.")
        if st.button("🔄 Clear processing lock", key="clear_ollama_lock"):
            st.session_state["ollama_processing"] = False
            st.rerun()

    if st.button(
        "🚀 Generate Themed Contributions",
        type="primary",
        key="field_generate_btn",
        disabled=is_processing,
    ):
        if not input_text.strip():
            st.error("Please provide input text (upload a file or paste text first)")
            return

        # Set processing lock (only for Ollama - local resource constraint)
        if is_ollama:
            st.session_state["ollama_processing"] = True

        # Show input info for debugging
        st.info(
            f"Processing {len(input_text):,} characters from: {source_title or 'direct input'}"
        )

        # Use sidebar session provider
        spinner_text = f"Extracting themes from {len(input_text):,} chars using {session_provider}..."

        with st.spinner(spinner_text):
            try:
                result = process_field_input_sync(
                    input_text=input_text,
                    source_file=source_file,
                    source_title=source_title,
                    provider=session_provider,
                    model=full_model_id,
                    contributions_per_theme=contributions_per_theme,
                    include_violations=include_violations,
                )
                st.success(f"✓ Generated using {session_provider}")
            except Exception as e:
                st.error(f"Generation failed: {e}")
                if is_ollama:
                    st.session_state["ollama_processing"] = False
                return
            finally:
                # Clear processing lock (only for Ollama)
                if is_ollama:
                    st.session_state["ollama_processing"] = False

            st.session_state["field_input_result"] = result

            # Save to Redis
            if result.contributions_generated > 0:
                # Reload contributions and save to Redis
                generator = load_contributions()
                # Get only the newly generated ones (field_input source)
                new_contribs = [
                    c
                    for c in generator.contributions
                    if c.metadata
                    and c.metadata.get("field_input")
                    and c.metadata.get("generated_date") == date.today().isoformat()
                ]
                if new_contribs:
                    variations_dicts = [c.to_dict() for c in new_contribs]
                    saved = _save_variations_to_redis(variations_dicts)
                    st.success(f"💾 Saved {saved} records")

            # Run experiment if requested
            if run_experiment and result.contributions_generated > 0:
                st.info("📊 Running Opik experiment...")
                _run_field_experiment(validate_func, user_id)

    # Display results
    if "field_input_result" in st.session_state:
        result = st.session_state["field_input_result"]

        st.markdown("### 📊 Generation Results")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Themes Extracted", result.themes_extracted)
        with col2:
            st.metric("Contributions", result.contributions_generated)
        with col3:
            st.metric("Categories", len(result.categories_covered))
        with col4:
            st.metric("Input Length", f"{result.input_length:,}")

        # Show extracted themes
        if result.themes:
            st.markdown("#### Extracted Themes")
            for theme in result.themes:
                with st.expander(f"🏷️ {theme.category}: {theme.theme}"):
                    st.markdown(f"**Keywords:** {', '.join(theme.keywords)}")
                    st.markdown(f"**Context:** {theme.context[:300]}...")

        # Show generated contributions
        st.markdown("#### Generated Contributions")

        # Load and filter to show only today's field input contributions
        generator = load_contributions()
        field_contribs = [
            c
            for c in generator.contributions
            if c.metadata
            and c.metadata.get("field_input")
            and c.metadata.get("generated_date") == date.today().isoformat()
        ]

        if field_contribs:
            _display_contributions_list(field_contribs, validate_func, user_id)
        else:
            st.info("No field input contributions generated today")


def _run_field_experiment(validate_func: Callable, user_id: str) -> None:
    """Run validation on today's field input contributions and inform about scheduled evaluation."""
    try:
        # Get today's contributions
        generator = load_contributions()
        field_contribs = [
            c
            for c in generator.contributions
            if c.metadata
            and c.metadata.get("field_input")
            and c.metadata.get("generated_date") == date.today().isoformat()
        ]

        if not field_contribs:
            st.warning("No field contributions to validate")
            return

        # Run batch validation and save to Redis
        validation_count = _run_batch_validation(
            field_contribs, validate_func, user_id, save_to_redis=True
        )

        # Inform user about scheduled experiment
        if validation_count > 0:
            st.info(
                f"✅ Validated {validation_count} contributions. "
                f"Spans will appear in Opik in ~3 minutes. "
                f"Use **task_opik_evaluate** (runs every 2hours) to create dataset and run experiment."
            )

    except Exception as e:
        st.error(f"Experiment error: {e}")
        _logger.error("FIELD_EXPERIMENT_ERROR", error=str(e))


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
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        st.caption(
            "💡 Spans take ~3min to appear in Opik. Use **task_opik_evaluate** scheduled task to run experiments on recent spans."
        )

    with col2:
        if st.button("🚀 Validate All", type="primary", key="validate_all_btn"):
            _run_batch_validation(contributions, validate_func, user_id)

    with col3:
        if st.button("🗑️ Clear Results", key="clear_results_btn"):
            if "batch_results" in st.session_state:
                del st.session_state["batch_results"]
            st.rerun()

    with col4:
        if "batch_results" in st.session_state:
            results = st.session_state["batch_results"]
            valid_count = sum(1 for r in results.values() if r.get("is_valid"))
            matches = sum(
                1
                for cid, r in results.items()
                if _check_expected_match(cid, r, contributions)
            )
            st.markdown(
                f"**Results:** {valid_count}/{len(results)} valid • "
                f"{matches}/{len(results)} match expected"
            )

    st.markdown("---")

    # Display each contribution
    for i, contrib in enumerate(contributions):
        _display_contribution_card(contrib, validate_func, user_id, i)


def _check_expected_match(
    contrib_id: str, result: dict, contributions: List[MockContribution]
) -> bool:
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
    title_preview = (
        contrib.constat_factuel[:50] + "..."
        if len(contrib.constat_factuel) > 50
        else contrib.constat_factuel
    )
    header = f"{badge} [{contrib.category or 'N/A'}] {title_preview} {validity_indicator}{result_indicator}"

    with st.expander(header, expanded=False):
        # Metadata row
        meta_cols = st.columns(4)
        with meta_cols[0]:
            # Smart ID display: field_category_uuid → category_uuid, else first 8 chars
            display_id = contrib.id
            if display_id.startswith("field_"):
                # field_logement_abc123 → logement_abc123
                display_id = display_id[6:]  # Remove "field_" prefix
            else:
                display_id = display_id[:8]
            st.caption(f"**ID:** `{display_id}`")
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
            parent_display = (
                contrib.parent_id[6:]
                if contrib.parent_id.startswith("field_")
                else contrib.parent_id[:8]
            )
            st.caption(f"↳ Derived from `{parent_display}`")

        # Violations injected
        if contrib.violations_injected:
            st.warning(
                f"**Violations injected:** {', '.join(contrib.violations_injected)}"
            )

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

        # Action buttons row - use contrib.id for stable keys
        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 1])

        with btn_col1:
            if st.button("🔍 Validate", key=f"validate_{contrib.id}"):
                with st.spinner("Validating..."):
                    result = validate_func(
                        contrib.title, contrib.body, contrib.category
                    )
                    # Store in batch_results for summary display
                    if "batch_results" not in st.session_state:
                        st.session_state["batch_results"] = {}
                    st.session_state["batch_results"][contrib.id] = result
                    # Track last action and add to overlay
                    st.session_state["last_action_id"] = contrib.id
                    clear_overlay()
                    add_to_overlay(contrib.id, "validation", result)
                    st.toast(f"Validated {contrib.id[:8]}...")

        with btn_col2:
            if st.button("📂 Classify", key=f"classify_{contrib.id}"):
                with st.spinner("Classifying..."):
                    classify_result = _classify_mockup_contribution(
                        contrib.title, contrib.body, contrib.category
                    )
                    # Track last action and add to overlay
                    st.session_state["last_action_id"] = contrib.id
                    clear_overlay()
                    add_to_overlay(contrib.id, "classification", classify_result)
                    st.toast(f"Classified {contrib.id[:8]}...")

        with btn_col3:
            if st.button("🔒 Anonymize", key=f"anonymize_{contrib.id}"):
                with st.spinner("Anonymizing..."):
                    anon_result = _anonymize_mockup_contribution(
                        contrib.title, contrib.body
                    )
                    # Track last action and add to overlay
                    st.session_state["last_action_id"] = contrib.id
                    clear_overlay()
                    add_to_overlay(contrib.id, "anonymization", anon_result)
                    st.toast(f"Anonymized {contrib.id[:8]}...")

        with btn_col4:
            if st.button("🗑️ Delete", key=f"delete_{contrib.id}", type="secondary"):
                _delete_contribution(contrib.id)
                # Force reload contributions after delete
                st.session_state["reload_contributions"] = True
                st.rerun()


def _delete_contribution(contrib_id: str) -> None:
    """
    Delete a contribution from all storage locations.

    Removes from:
    - Session state temp_variations (if present)
    - JSON file
    - Redis storage
    - Batch results (if present)
    """
    _logger.info("DELETE_CONTRIBUTION", id=contrib_id[:8])

    # Remove from session state temp_variations
    if "temp_variations" in st.session_state:
        st.session_state["temp_variations"] = [
            v for v in st.session_state["temp_variations"] if v.get("id") != contrib_id
        ]

    # Remove from batch results
    if (
        "batch_results" in st.session_state
        and contrib_id in st.session_state["batch_results"]
    ):
        del st.session_state["batch_results"][contrib_id]

    # Remove from JSON file
    try:
        generator = load_contributions()
        original_count = len(generator.contributions)
        generator.contributions = [
            c for c in generator.contributions if c.id != contrib_id
        ]
        if len(generator.contributions) < original_count:
            save_contributions(generator)
            _logger.info("JSON_DELETE", id=contrib_id[:8])
    except Exception as e:
        _logger.error("JSON_DELETE_ERROR", error=str(e))

    # Remove from Redis
    try:
        storage = get_storage()
        deleted = storage.delete_record(contrib_id)
        if deleted:
            _logger.info("REDIS_DELETE", id=contrib_id[:8])
    except Exception as e:
        _logger.error("REDIS_DELETE_ERROR", error=str(e))

    st.toast(f"Deleted contribution {contrib_id[:8]}...")


def _run_batch_validation(
    contributions: List[MockContribution],
    validate_func: Callable,
    user_id: str,
    save_to_redis: bool = True,
) -> None:
    """Run validation on all contributions and optionally save to Redis."""

    _logger.info(
        "BATCH_START",
        count=len(contributions),
        user_id=user_id[:8] if user_id else None,
    )
    start_time = time.time()
    today = date.today().isoformat()

    results = {}
    records_to_save = []
    progress_bar = st.progress(0, text="Validating...")

    storage = get_storage() if save_to_redis else None

    for i, contrib in enumerate(contributions):
        progress = (i + 1) / len(contributions)
        progress_bar.progress(
            progress, text=f"Validating {i+1}/{len(contributions)}: {contrib.id[:8]}..."
        )
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
        1 for cid, r in results.items() if _check_expected_match(cid, r, contributions)
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

    # Return count for experiment workflow
    return len(successful)


def _run_experiment_after_validation(validation_count: int) -> None:
    """
    Create dataset from recent validation spans and run Opik experiment.

    This function:
    1. Searches for recent charter_validation/category_classification spans
    2. Creates a dataset from those spans
    3. Runs the Opik evaluate() experiment
    """
    from datetime import datetime
    from app.agents.tracing import get_tracer
    from app.processors.workflows import (
        OpikExperimentConfig,
        run_opik_experiment,
        list_available_metrics,
    )
    from app.services.session import get_current_provider

    st.info(f"📊 Creating dataset from {validation_count} validations...")

    tracer = get_tracer()
    if not tracer.enabled:
        st.warning("⚠️ Opik not configured - cannot run experiment")
        return

    # Search for recent spans (from this validation batch)
    # We search for spans created in the last few minutes
    experiment_type = "charter_optimization"  # Default to charter
    span_name = "charter_validation"

    # Search for recent spans
    filter_string = f'name = "{span_name}"'
    spans = tracer.search_spans(
        filter_string=filter_string,
        span_type="llm",
        max_results=validation_count + 10,  # Get a bit more than expected
    )

    if not spans:
        st.warning("⚠️ No spans found from validation - cannot create dataset")
        return

    # Take only the most recent spans (up to validation_count)
    recent_spans = spans[:validation_count]
    st.info(f"Found {len(recent_spans)} recent spans")

    # Generate dataset name
    today = datetime.now().strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%H%M%S")
    dataset_name = f"mockup-validation-{today}-{timestamp}"

    # Create dataset from spans
    success = tracer.create_dataset_from_spans(
        dataset_name=dataset_name,
        spans=recent_spans,
        description=f"Mockup validation batch ({len(recent_spans)} items)",
        mark_added=True,
    )

    if not success:
        st.error("❌ Failed to create dataset from spans")
        return

    st.success(f"✅ Created dataset: {dataset_name} ({len(recent_spans)} items)")

    # Run experiment
    st.info("🧪 Running Opik experiment...")

    try:
        # Get current provider from session
        task_provider = get_current_provider()

        config = OpikExperimentConfig(
            experiment_name=f"mockup-eval-{today}-{timestamp}",
            dataset_name=dataset_name,
            experiment_type=experiment_type,
            metrics=["hallucination", "moderation"],
            task_provider=task_provider,
        )

        result = run_opik_experiment(config)

        if result["status"] == "success":
            st.success(f"✅ Experiment complete: {config.experiment_name}")
            with st.expander("Experiment Results", expanded=True):
                st.json(result.get("eval_results", {}))
        else:
            st.error(f"❌ Experiment failed: {result.get('errors', [])}")

        # Store result in session
        st.session_state["last_experiment_result"] = result

    except Exception as e:
        st.error(f"❌ Experiment error: {e}")
        _logger.error("EXPERIMENT_ERROR", error=str(e))


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


def _save_variations_to_redis(variations: List[dict]) -> int:
    """
    Save generated variations to Redis.

    Args:
        variations: List of variation dictionaries

    Returns:
        Number of records saved
    """
    try:
        storage = get_storage()
        today = date.today().isoformat()
        records = []

        for var_dict in variations:
            contrib = MockContribution.from_dict(var_dict)

            record = ValidationRecord(
                id=contrib.id,
                date=today,
                title=contrib.title,
                body=contrib.body,
                category=contrib.category,
                constat_factuel=contrib.constat_factuel,
                idees_ameliorations=contrib.idees_ameliorations,
                is_valid=(
                    contrib.expected_valid
                    if contrib.expected_valid is not None
                    else True
                ),
                violations=[],
                encouraged_aspects=[],
                confidence=0.0,  # Not validated yet
                reasoning="Generated mockup - not yet validated",
                source=contrib.source,
                expected_valid=contrib.expected_valid,
                parent_id=contrib.parent_id,
                similarity_to_parent=contrib.similarity_to_parent,
                distance_from_parent=contrib.distance_from_parent,
                violations_injected=contrib.violations_injected or [],
            )
            records.append(record)

        saved = storage.save_batch(records)
        _logger.info("REDIS_SAVE_VARIATIONS", count=saved)
        return saved

    except Exception as e:
        _logger.error("REDIS_SAVE_ERROR", error=str(e))
        return 0


def _storage_opik_view(user_id: str) -> None:
    """Storage and Opik dataset management view."""
    st.session_state["current_batch_view"] = "storage_opik"

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
            st.metric(
                "Valid",
                f"{today_stats['valid_count']} ({today_stats['valid_ratio']:.0%})",
            )
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
                table_data.append(
                    {
                        "ID": r.id[:8],
                        "Category": r.category or "N/A",
                        "Valid": "✅" if r.is_valid else "❌",
                        "Confidence": f"{r.confidence:.0%}",
                        "Source": r.source,
                        "Match": (
                            "🎯"
                            if r.matches_expected()
                            else ("❌" if r.matches_expected() is False else "-")
                        ),
                    }
                )

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
            valid_only = (
                True
                if valid_filter == "valid_only"
                else (False if valid_filter == "invalid_only" else None)
            )

            # Create dataset
            manager.create_charter_dataset(
                dataset_name, f"Charter validation dataset from {date_str or 'latest'}"
            )

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
