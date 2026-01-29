# app/auto_contribution/views.py
"""
Auto-Contribution UI Views - 5-step Streamlit workflow.

Uses the workflow functions from app/processors/workflows/workflow_autocontribution.py

Step 1: Select Source     -> Document from Audierne2026 OR paste custom text
Step 2: Choose Category   -> One of 7 categories
Step 3: Get Inspired      -> AI generates draft contribution
Step 4: Edit Contribution -> User edits constat_factuel & idees_ameliorations
Step 5: Save              -> Validate with Forseti 461 and store to Redis
"""

import streamlit as st

from app.i18n import _, get_language
from app.agents.forseti import CATEGORIES
from app.sidebar import get_selected_provider, get_model_id

# Import workflow functions
from app.processors.workflows.workflow_autocontribution import (
    step_1_load_sources,
    load_source_content,
    step_3_generate_draft,
    step_5_validate_and_save,
    CATEGORY_DESCRIPTIONS,
)


# =============================================================================
# SESSION STATE MANAGEMENT
# =============================================================================

def _init_state():
    """Initialize session state for auto-contribution tab."""
    defaults = {
        "autocontrib_step": 1,
        "autocontrib_source_type": "audierne_docs",
        "autocontrib_source_content": "",
        "autocontrib_source_title": "",
        "autocontrib_category": CATEGORIES[0],
        "autocontrib_draft_constat": "",
        "autocontrib_draft_idees": "",
        "autocontrib_saved_id": None,
        "autocontrib_validation_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_state():
    """Reset all state for new contribution."""
    st.session_state.autocontrib_step = 1
    st.session_state.autocontrib_source_type = "audierne_docs"
    st.session_state.autocontrib_source_content = ""
    st.session_state.autocontrib_source_title = ""
    st.session_state.autocontrib_category = CATEGORIES[0]
    st.session_state.autocontrib_draft_constat = ""
    st.session_state.autocontrib_draft_idees = ""
    st.session_state.autocontrib_saved_id = None
    st.session_state.autocontrib_validation_result = None


def _get_language() -> str:
    """Get current language code."""
    lang = get_language()
    return "en" if lang == "en" else "fr"


# =============================================================================
# MAIN VIEW
# =============================================================================

def autocontribution_view(user_id: str):
    """Main Auto-Contribution tab view - 5-step workflow."""
    _init_state()

    st.subheader(f"✨ {_('autocontrib_title')}")
    st.markdown(_("autocontrib_subtitle"))

    # Progress indicator
    step = st.session_state.autocontrib_step
    steps = [
        _("autocontrib_step1_short"),
        _("autocontrib_step2_short"),
        _("autocontrib_step3_short"),
        _("autocontrib_step4_short"),
        _("autocontrib_step5_short"),
    ]

    # Visual step indicator
    cols = st.columns(5)
    for i, (col, step_name) in enumerate(zip(cols, steps), 1):
        with col:
            if i < step:
                st.markdown(f"✅ **{step_name}**")
            elif i == step:
                st.markdown(f"🔵 **{step_name}**")
            else:
                st.markdown(f"⚪ {step_name}")

    st.markdown("---")

    # Render current step
    if step == 1:
        _render_step_1_source()
    elif step == 2:
        _render_step_2_category()
    elif step == 3:
        _render_step_3_inspiration()
    elif step == 4:
        _render_step_4_edit()
    elif step == 5:
        _render_step_5_confirmation()


# =============================================================================
# STEP RENDERERS
# =============================================================================

def _render_step_1_source():
    """Step 1: Select inspiration source."""
    st.markdown(f"### {_('autocontrib_step1_title')}")

    source_type = st.radio(
        _("autocontrib_source_type"),
        options=["audierne_docs", "paste_text"],
        format_func=lambda x: {
            "audierne_docs": f"📚 {_('autocontrib_source_audierne')}",
            "paste_text": f"📝 {_('autocontrib_source_paste')}",
        }[x],
        horizontal=True,
        key="autocontrib_source_type_radio",
    )

    st.session_state.autocontrib_source_type = source_type

    if source_type == "audierne_docs":
        # Use workflow function to load sources
        docs = step_1_load_sources()
        if docs:
            doc_options = {d["path"]: f"{d['title']} ({d['filename']})" for d in docs}
            selected_doc = st.selectbox(
                _("autocontrib_select_doc"),
                options=list(doc_options.keys()),
                format_func=lambda x: doc_options[x],
                key="autocontrib_selected_doc",
            )

            if selected_doc:
                content = load_source_content(selected_doc)
                st.session_state.autocontrib_source_content = content
                st.session_state.autocontrib_source_title = doc_options[selected_doc]

                # Preview
                with st.expander(_("autocontrib_source_preview"), expanded=False):
                    st.markdown(content[:2000] + ("..." if len(content) > 2000 else ""))
        else:
            st.warning(_("autocontrib_no_docs"))

    else:  # paste_text
        source_title = st.text_input(
            _("autocontrib_source_title_label"),
            value=st.session_state.autocontrib_source_title,
            key="autocontrib_paste_title",
        )
        st.session_state.autocontrib_source_title = source_title

        content = st.text_area(
            _("autocontrib_source_paste"),
            value=st.session_state.autocontrib_source_content,
            height=250,
            key="autocontrib_paste_content",
            placeholder=_("autocontrib_source_paste_placeholder"),
        )
        st.session_state.autocontrib_source_content = content

    # Navigation
    st.markdown("---")
    col1, col2 = st.columns([3, 1])

    with col2:
        can_proceed = bool(st.session_state.autocontrib_source_content.strip())
        if st.button(
            f"{_('autocontrib_next')} →",
            type="primary",
            disabled=not can_proceed,
            use_container_width=True,
        ):
            st.session_state.autocontrib_step = 2
            st.rerun()

    if not can_proceed:
        st.caption(_("autocontrib_validation_empty_source"))


def _render_step_2_category():
    """Step 2: Choose category."""
    st.markdown(f"### {_('autocontrib_step2_title')}")

    lang = _get_language()

    # Category selector with descriptions
    category = st.selectbox(
        _("autocontrib_select_category"),
        options=CATEGORIES,
        format_func=lambda x: f"{x.capitalize()} - {CATEGORY_DESCRIPTIONS.get(x, {}).get(lang, '')}",
        index=CATEGORIES.index(st.session_state.autocontrib_category),
        key="autocontrib_category_select",
    )
    st.session_state.autocontrib_category = category

    st.caption(_("autocontrib_category_help"))

    # Show source preview
    with st.expander(_("autocontrib_source_preview"), expanded=False):
        st.markdown(f"**{st.session_state.autocontrib_source_title}**")
        st.markdown(
            st.session_state.autocontrib_source_content[:1000]
            + ("..." if len(st.session_state.autocontrib_source_content) > 1000 else "")
        )

    # Navigation
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button(f"← {_('autocontrib_back')}", use_container_width=True):
            st.session_state.autocontrib_step = 1
            st.rerun()

    with col2:
        if st.button(
            f"{_('autocontrib_next')} →", type="primary", use_container_width=True
        ):
            st.session_state.autocontrib_step = 3
            st.rerun()


def _render_step_3_inspiration():
    """Step 3: Get AI-generated inspiration/draft."""
    st.markdown(f"### {_('autocontrib_step3_title')}")

    lang = _get_language()
    category = st.session_state.autocontrib_category
    category_desc = CATEGORY_DESCRIPTIONS.get(category, {}).get(lang, category)

    st.markdown(f"**{_('autocontrib_category')}:** {category.capitalize()} - {category_desc}")

    # Show source preview
    with st.expander(_("autocontrib_source_preview"), expanded=False):
        st.markdown(f"**{st.session_state.autocontrib_source_title}**")
        st.markdown(
            st.session_state.autocontrib_source_content[:1000]
            + ("..." if len(st.session_state.autocontrib_source_content) > 1000 else "")
        )

    # Generate button
    col1, col2 = st.columns([2, 1])
    with col1:
        generate_clicked = st.button(
            f"✨ {_('autocontrib_generate_draft')}",
            type="primary",
            use_container_width=True,
        )

    with col2:
        if st.session_state.autocontrib_draft_constat:
            regenerate_clicked = st.button(
                f"🔄 {_('autocontrib_regenerate')}",
                use_container_width=True,
            )
        else:
            regenerate_clicked = False

    if generate_clicked or regenerate_clicked:
        with st.spinner(_("autocontrib_generating")):
            provider = get_selected_provider()
            model = get_model_id()

            # Use workflow function
            draft = step_3_generate_draft(
                source_text=st.session_state.autocontrib_source_content,
                category=st.session_state.autocontrib_category,
                source_title=st.session_state.autocontrib_source_title,
                language=lang,
                provider_name=provider,
                model=model,
            )

            st.session_state.autocontrib_draft_constat = draft.constat_factuel
            st.session_state.autocontrib_draft_idees = draft.idees_ameliorations
            st.rerun()

    # Display draft if generated
    if st.session_state.autocontrib_draft_constat or st.session_state.autocontrib_draft_idees:
        st.markdown(f"#### {_('autocontrib_draft_preview')}")

        st.markdown(f"**{_('autocontrib_constat_factuel')}:**")
        st.info(st.session_state.autocontrib_draft_constat or _("autocontrib_empty_field"))

        st.markdown(f"**{_('autocontrib_idees_ameliorations')}:**")
        st.info(st.session_state.autocontrib_draft_idees or _("autocontrib_empty_field"))

    # Navigation
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button(f"← {_('autocontrib_back')}", use_container_width=True):
            st.session_state.autocontrib_step = 2
            st.rerun()

    with col2:
        can_proceed = bool(
            st.session_state.autocontrib_draft_constat
            or st.session_state.autocontrib_draft_idees
        )
        if st.button(
            f"{_('autocontrib_edit_draft')} →",
            type="primary",
            disabled=not can_proceed,
            use_container_width=True,
        ):
            st.session_state.autocontrib_step = 4
            st.rerun()


def _render_step_4_edit():
    """Step 4: Edit the contribution."""
    st.markdown(f"### {_('autocontrib_step4_title')}")

    lang = _get_language()
    category = st.session_state.autocontrib_category
    category_desc = CATEGORY_DESCRIPTIONS.get(category, {}).get(lang, category)

    st.markdown(f"**{_('autocontrib_category')}:** {category.capitalize()} - {category_desc}")

    # Editable text areas
    constat = st.text_area(
        _("autocontrib_constat_factuel"),
        value=st.session_state.autocontrib_draft_constat,
        height=150,
        help=_("autocontrib_constat_help"),
        key="autocontrib_edit_constat",
    )

    idees = st.text_area(
        _("autocontrib_idees_ameliorations"),
        value=st.session_state.autocontrib_draft_idees,
        height=150,
        help=_("autocontrib_idees_help"),
        key="autocontrib_edit_idees",
    )

    # Update session state
    st.session_state.autocontrib_draft_constat = constat
    st.session_state.autocontrib_draft_idees = idees

    # Validation
    is_valid = bool(constat.strip() and idees.strip())
    if not is_valid:
        st.warning(_("autocontrib_validation_empty"))

    # Navigation
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button(f"← {_('autocontrib_back')}", use_container_width=True):
            st.session_state.autocontrib_step = 3
            st.rerun()

    with col2:
        if st.button(
            f"🔍 {_('autocontrib_validate_save')}",
            type="primary",
            disabled=not is_valid,
            use_container_width=True,
        ):
            with st.spinner(_("autocontrib_validating")):
                provider = get_selected_provider()
                model = get_model_id()

                # Use workflow function
                result = step_5_validate_and_save(
                    constat_factuel=st.session_state.autocontrib_draft_constat,
                    idees_ameliorations=st.session_state.autocontrib_draft_idees,
                    category=st.session_state.autocontrib_category,
                    source_title=st.session_state.autocontrib_source_title,
                    provider_name=provider,
                    model=model,
                )

                st.session_state.autocontrib_saved_id = result.contribution_id
                st.session_state.autocontrib_validation_result = {
                    "is_valid": result.is_valid,
                    "violations": result.violations,
                    "encouraged_aspects": result.encouraged_aspects,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                }
                st.session_state.autocontrib_step = 5
                st.rerun()


def _render_step_5_confirmation():
    """Step 5: Confirmation after save."""
    st.markdown(f"### {_('autocontrib_step5_title')}")

    st.success(_("autocontrib_saved_success"))

    if st.session_state.autocontrib_saved_id:
        st.caption(f"ID: `{st.session_state.autocontrib_saved_id}`")

    # Display Forseti 461 validation results
    validation = st.session_state.get("autocontrib_validation_result")
    if validation:
        st.markdown(f"### 🔍 {_('forseti_title')}")

        if validation.get("is_valid"):
            st.success(f"✅ {_('forseti_compliant')}")
        else:
            st.warning(f"⚠️ {_('forseti_non_compliant')}")

        # Violations
        violations = validation.get("violations", [])
        if violations:
            st.markdown(f"**{_('forseti_violations')}**")
            for v in violations:
                st.markdown(f"- ❌ {v}")

        # Encouraged aspects
        encouraged = validation.get("encouraged_aspects", [])
        if encouraged:
            st.markdown(f"**{_('forseti_positive_points')}**")
            for e in encouraged:
                st.markdown(f"- ✨ {e}")

        # Confidence
        confidence = validation.get("confidence", 0)
        st.progress(confidence, text=f"{_('forseti_confidence')}: {confidence:.0%}")

        # Reasoning (collapsed)
        with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
            st.markdown(validation.get("reasoning", ""))

    st.markdown("---")

    # Show what was saved
    lang = _get_language()
    category = st.session_state.autocontrib_category
    category_desc = CATEGORY_DESCRIPTIONS.get(category, {}).get(lang, category)

    st.markdown(f"**{_('autocontrib_category')}:** {category.capitalize()} - {category_desc}")

    st.markdown(f"**{_('autocontrib_constat_factuel')}:**")
    st.markdown(f"> {st.session_state.autocontrib_draft_constat}")

    st.markdown(f"**{_('autocontrib_idees_ameliorations')}:**")
    st.markdown(f"> {st.session_state.autocontrib_draft_idees}")

    # Actions
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            f"➕ {_('autocontrib_new_contribution')}",
            type="primary",
            use_container_width=True,
        ):
            _reset_state()
            st.rerun()

    with col2:
        st.markdown(
            f"[📋 {_('tab_contributions')}](?tab=contributions)",
            help=_("autocontrib_view_contributions_help"),
        )
