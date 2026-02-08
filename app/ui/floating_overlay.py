# app/ui/floating_overlay.py
"""
Floating Overlay Component for Streamlit

Provides a floating result panel that displays action results
(validation, classification, anonymization) without closing
the parent component (contribution card, issue, etc.).

Usage:
    from app.ui.floating_overlay import init_floating_overlay, render_floating_overlay, add_to_overlay

    # In your view function:
    init_floating_overlay()

    # When an action completes:
    add_to_overlay("item_id", "validation", result_dict)

    # At the end of your view function:
    render_floating_overlay()
"""

import streamlit as st
from streamlit_float import float_init, float_css_helper
from typing import Dict, Any, Optional

from app.services.translations import _


def init_floating_overlay() -> None:
    """
    Initialize the floating result overlay for action feedback.

    Call this at the start of your view function, before any buttons.
    """
    float_init()

    if "overlay_results" not in st.session_state:
        st.session_state["overlay_results"] = {}
    if "overlay_visible" not in st.session_state:
        st.session_state["overlay_visible"] = False


def add_to_overlay(item_id: str, result_type: str, result: Dict[str, Any]) -> None:
    """
    Add a result to the floating overlay.

    Args:
        item_id: Unique identifier for the item (contribution ID, issue ID, etc.)
        result_type: Type of result ("validation", "classification", "anonymization")
        result: Result dictionary with at minimum {"success": bool} and type-specific fields
    """
    if "overlay_results" not in st.session_state:
        st.session_state["overlay_results"] = {}

    if item_id not in st.session_state["overlay_results"]:
        st.session_state["overlay_results"][item_id] = {}

    st.session_state["overlay_results"][item_id][result_type] = result
    st.session_state["overlay_visible"] = True


def clear_overlay(item_id: Optional[str] = None) -> None:
    """
    Clear results from the overlay.

    Args:
        item_id: If provided, clear only that item's results. Otherwise clear all.
    """
    if item_id:
        if "overlay_results" in st.session_state and item_id in st.session_state["overlay_results"]:
            del st.session_state["overlay_results"][item_id]
            if not st.session_state["overlay_results"]:
                st.session_state["overlay_visible"] = False
    else:
        st.session_state["overlay_results"] = {}
        st.session_state["overlay_visible"] = False


def render_floating_overlay() -> None:
    """
    Render the floating result overlay if there are results to display.

    Call this at the end of your view function, after all other components.
    The overlay appears on the right side of the screen.
    """
    if not st.session_state.get("overlay_visible"):
        return

    overlay_results = st.session_state.get("overlay_results", {})
    if not overlay_results:
        return

    # Create floating container
    overlay_container = st.container()

    # Light theme styling - responsive width
    css_overlay = float_css_helper(
        bottom="20px",
        right="10px",
        width="min(380px, calc(100vw - 40px))",  # Responsive: max 380px or viewport - 40px
        max_height="70vh",
        background="#ffffff",  # Light background
        border_radius="10px",
        custom=(
            "overflow-y: auto; padding: 12px; "
            "box-shadow: 0 4px 16px rgba(0,0,0,0.12); z-index: 9999; "
            "border: 1px solid #e0e0e0; "
            "color: #1a1a1a; font-size: 0.9em;"
        ),
    )

    with overlay_container:
        # Compact header with close button
        col_title, col_close = st.columns([5, 1])
        with col_title:
            st.markdown("**📊 Forseti Results**")
        with col_close:
            if st.button("✕", key="overlay_close_btn", help=_("close")):
                clear_overlay()
                return

        # Display results by item ID
        for item_id, results in list(overlay_results.items()):
            # Smart ID display based on format
            if item_id.startswith("issue_"):
                display_id = item_id.replace("issue_", "#")
            elif item_id.startswith("field_"):
                # field_logement_abc123 → logement_abc123
                display_id = item_id[6:]
            else:
                display_id = item_id[:8]

            st.markdown(f"---\n**{display_id}**")

            # Validation result
            if "validation" in results:
                _render_validation_result(results["validation"])

            # Classification result
            if "classification" in results:
                _render_classification_result(results["classification"])

            # Anonymization result
            if "anonymization" in results:
                _render_anonymization_result(results["anonymization"])

            # Clear button for this item
            if st.button("🗑️", key=f"overlay_clear_{item_id}", help=_("clear")):
                clear_overlay(item_id)

    overlay_container.float(css_overlay)


def _render_validation_result(result: Dict[str, Any]) -> None:
    """Display compact validation result in overlay."""
    st.markdown("**🔍 Validation**")

    if not result.get("success"):
        st.error(f"❌ {result.get('error', _('forseti_unknown_error'))}")
        return

    # Status and confidence inline
    confidence = result.get("confidence", 0)
    if result.get("is_valid"):
        st.success(f"✅ Valid ({confidence:.0%})")
    else:
        st.warning(f"⚠️ Invalid ({confidence:.0%})")

    # Violations (compact)
    violations = result.get("violations", [])
    if violations:
        st.markdown(f"**{_('forseti_violations')}:** {len(violations)}")
        for v in violations:
            st.caption(f"• {v}")

    # Positive aspects (compact)
    encouraged = result.get("encouraged_aspects", [])
    if encouraged:
        st.markdown(f"**{_('forseti_positive_points')}** {len(encouraged)}")
        for e in encouraged:
            st.caption(f"• {e}")

    # Suggested category only if classification was actually performed (confidence > 0)
    suggested_category = result.get("category") or result.get("suggested_category")
    cat_confidence = result.get("category_confidence", 0)
    if suggested_category and cat_confidence > 0:
        st.caption(f"📁 {suggested_category.capitalize()} ({cat_confidence:.0%})")

    # Reasoning hidden by default
    reasoning = result.get("reasoning", "")
    if reasoning:
        with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
            st.caption(reasoning)

    # Category reasoning if different
    cat_reasoning = result.get("category_reasoning", "")
    if cat_reasoning and cat_reasoning != reasoning:
        with st.expander("📁 Category reasoning", expanded=False):
            st.caption(cat_reasoning)


def _render_classification_result(result: Dict[str, Any]) -> None:
    """Display compact classification result in overlay."""
    st.markdown("**📂 Classification**")

    if not result.get("success"):
        st.error(f"❌ {result.get('error', _('forseti_unknown_error'))}")
        return

    # Category and confidence inline
    category = result.get("category")
    confidence = result.get("confidence", 0)
    if category:
        st.success(f"📁 {category.capitalize()} ({confidence:.0%})")
    else:
        st.info("No category")

    # Alternative categories (compact)
    alternatives = result.get("alternative_categories", [])
    if alternatives:
        alt_text = ", ".join(
            f"{a.get('category', a) if isinstance(a, dict) else a}"
            for a in alternatives[:2]
        )
        st.caption(f"Alternatives: {alt_text}")

    # Reasoning hidden by default
    reasoning = result.get("reasoning", "")
    if reasoning:
        with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
            st.caption(reasoning)


def _render_anonymization_result(result: Dict[str, Any]) -> None:
    """Display compact anonymization result in overlay."""
    st.markdown("**🔒 Anonymization**")

    if not result.get("success"):
        st.error(f"❌ {result.get('error', _('forseti_unknown_error'))}")
        return

    # Entity summary inline
    entities = result.get("entities", [])
    entity_mapping = result.get("entity_mapping", {})
    keywords = result.get("keywords_extracted", [])

    entity_count = len(entities) or len(entity_mapping)
    st.caption(f"🔐 {entity_count} entities | 🏷️ {len(keywords)} keywords")

    # Entity details in expander
    if entities or entity_mapping:
        with st.expander("Entity mapping", expanded=False):
            if entities:
                for e in entities:
                    if isinstance(e, dict):
                        original = e.get("original", "")
                        anonymized = e.get("anonymized", "***")
                        entity_type = e.get("type", e.get("entity_type", ""))
                        st.caption(f"`{original}` → `{anonymized}` _{entity_type}_")
                    else:
                        st.caption(f"• {e}")
            elif entity_mapping:
                for original, anonymized in entity_mapping.items():
                    st.caption(f"`{original}` → `{anonymized}`")

    # Keywords in expander
    if keywords:
        with st.expander(f"{_('forseti_keywords_extracted')}", expanded=False):
            st.caption(", ".join(f"`{k}`" for k in keywords))

    # Reasoning hidden by default
    reasoning = result.get("reasoning", "")
    if reasoning:
        with st.expander(f"💭 {_('forseti_reasoning')}", expanded=False):
            st.caption(reasoning)

    # Anonymized text preview
    anonymized_text = result.get("anonymized_text", "")
    if anonymized_text:
        with st.expander(f"📄 {_('forseti_anonymized_preview')}", expanded=False):
            preview_length = min(500, len(anonymized_text))
            preview = anonymized_text[:preview_length]
            if len(anonymized_text) > preview_length:
                preview += f"... (+{len(anonymized_text) - preview_length})"
            st.caption(preview)
