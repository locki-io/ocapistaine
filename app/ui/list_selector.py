# app/ui/list_selector.py
"""
List Selector — Tête de Liste Avatar Chips (Floating)

Compact avatar strip that floats just above st.chat_input().
Citizens tap a portrait to filter by list — visual, intuitive, no dropdown.

Click = select filter (blue ring). Click again = deselect.
Does NOT auto-fire a query — the citizen types their question with the filter active.

Photos live in app/ui/assets/tete_{list_key}.png
Falls back to initials when image is missing.

Usage:
    from app.ui.list_selector import render_list_selector

    # Renders floating avatars, returns selected list key (or "")
    filter_list = render_list_selector(LISTS, include_all=True)
"""

import base64
from pathlib import Path
from functools import lru_cache

import streamlit as st
from streamlit_float import float_css_helper

# Resolve assets directory once
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# Tête de liste metadata: key -> (name, short_label, list_name)
TETE_DE_LISTE = {
    "audierne2026": ("Programme co-construit", "Tous", "Programme co-construit"),
    "ca": ("Florent Lardic", "CA", "Construire l'Avenir"),
    "paa": ("Didier Guillon", "PAA", "Passons à l'Action !"),
    "spae": ("Michel van Praët", "SPAE", "S'unir pour Audierne-Esquibien"),
    "csnf": ("Eric Bosser", "CSNF", "Cap sur Notre Futur"),
}


@lru_cache(maxsize=10)
def _load_image_b64(list_key: str) -> str | None:
    """Load tête de liste image as base64, cached across reruns."""
    img_path = _ASSETS_DIR / f"tete_{list_key}.png"
    if img_path.exists():
        return base64.b64encode(img_path.read_bytes()).decode()
    if list_key == "audierne2026":
        all_path = _ASSETS_DIR / "tete_all.png"
        if all_path.exists():
            return base64.b64encode(all_path.read_bytes()).decode()
    return None


def _initials(name: str) -> str:
    """Get initials from a name for fallback display."""
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper()


def _inject_float_css() -> None:
    """Inject CSS for the floating avatar strip above st.chat_input()."""
    st.markdown(
        """
    <style>
    /* Strip padding from the floating avatar panel */
    div[style*="position: fixed"][style*="z-index: 9980"],
    div[style*="position: fixed"][style*="z-index: 9980"] > div,
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stVerticalBlock"],
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stColumn"] {
        padding: 0 !important;
        margin: 0 !important;
        gap: 0 !important;
    }
    /* Each column is a positioning context for the absolute button */
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stColumn"] {
        position: relative !important;
        min-height: 56px !important;
        max-height: 56px !important;
        width: 56px !important;
        overflow: visible !important;
    }
    /* Button: covers the entire avatar area for easy clicking */
    div[style*="position: fixed"][style*="z-index: 9980"] .stButton {
        padding: 0 !important;
        margin: 0 !important;
        height: 0 !important;
        overflow: visible !important;
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
    }
    div[style*="position: fixed"][style*="z-index: 9980"] .stButton > button {
        min-height: 56px !important;
        height: 56px !important;
        width: 56px !important;
        min-width: 56px !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 50% !important;
        cursor: pointer !important;
    }
    /* Stack vertically with spacing */
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 10px !important;
        align-items: center !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    /* Kill markdown wrapper padding */
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stMarkdown"] {
        padding: 0 !important;
        margin: 0 !important;
    }
    /* Kill all inner container margins/padding */
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stElementContainer"],
    div[style*="position: fixed"][style*="z-index: 9980"] [data-testid="stVerticalBlockBorderWrapper"],
    div[style*="position: fixed"][style*="z-index: 9980"] .block-container,
    div[style*="position: fixed"][style*="z-index: 9980"] div {
        padding-left: 0 !important;
        margin-left: 0 !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_list_selector(
    lists: dict[str, str],
    include_all: bool = True,
) -> str:
    """
    Render floating tête de liste avatar chips above st.chat_input().

    Click = select (blue ring + name label). Click again = deselect.
    Does NOT fire a query — just sets the filter for the next question.

    Args:
        lists: Dict of {list_key: list_display_name}
        include_all: Include "Toutes les sources" option

    Returns:
        Selected list key (str), or "" if none selected.
    """
    _inject_float_css()

    # Initialize selection state
    if "_selected_list" not in st.session_state:
        st.session_state._selected_list = ""

    current_selection = st.session_state._selected_list

    # Build the list of chips to display
    chip_keys = []
    if include_all:
        chip_keys.append("")  # "all" option
    chip_keys.extend(lists.keys())

    # Floating container — sits above st.chat_input()
    strip = st.container()

    with strip:
        cols = st.columns(len(chip_keys), gap="small")

        for col, key in zip(cols, chip_keys):
            with col:
                # Get metadata
                if key == "":
                    tete_name = "Toutes les sources"
                    lookup_key = "audierne2026"
                else:
                    meta = TETE_DE_LISTE.get(key)
                    if meta:
                        tete_name, _, _ = meta
                    else:
                        tete_name = lists.get(key, key)
                    lookup_key = key

                # Load image
                img_b64 = _load_image_b64(lookup_key)

                # Visual state: selected = thick blue ring, unselected = thin grey
                is_selected = current_selection == key
                size = 52
                if is_selected:
                    border_color = "#0092ca"
                    border_width = "3px"
                    opacity = "1"
                    shadow = "0 0 0 3px rgba(0,146,202,0.3)"
                else:
                    border_color = "#cecfd1"
                    border_width = "2px"
                    opacity = "0.7"
                    shadow = "none"

                if img_b64:
                    avatar_html = (
                        f'<img src="data:image/png;base64,{img_b64}" '
                        f'style="width:{size}px;min-width:{size}px;height:{size}px;'
                        f"border-radius:50%;aspect-ratio:1;"
                        f"object-fit:cover;border:{border_width} solid {border_color};"
                        f"opacity:{opacity};display:block;margin:0 auto;"
                        f'box-shadow:{shadow};">'
                    )
                else:
                    bg = "#0092ca" if is_selected else "#cecfd1"
                    fg = "#fff"
                    ini = _initials(tete_name)
                    avatar_html = (
                        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
                        f"background:{bg};color:{fg};display:flex;align-items:center;"
                        f"justify-content:center;font-weight:bold;font-size:13px;"
                        f"font-family:Inter,sans-serif;border:{border_width} solid {border_color};"
                        f"opacity:{opacity};margin:0 auto;"
                        f'box-shadow:{shadow};">{ini}</div>'
                    )

                st.markdown(
                    f'<div style="text-align:center;">{avatar_html}</div>',
                    unsafe_allow_html=True,
                )

                # Invisible button covering the avatar — toggle on click
                if st.button(
                    "\u200b",
                    key=f"list_chip_{key or 'all'}",
                    use_container_width=True,
                ):
                    if is_selected:
                        # Deselect: click again to clear
                        st.session_state._selected_list = ""
                    else:
                        # Select this list
                        st.session_state._selected_list = key
                    st.rerun()

    # Float the strip just above st.chat_input (~56px from bottom)
    strip.float(
        float_css_helper(
            bottom="100px",
            left="24px",
            width="auto",
            background="rgba(255,255,255,0.92)",
            border="1px solid #cecfd1",
            z_index="9980",
            css=(
                "padding: 8px; margin: 0; "
                "border-radius: 28px; "
                "backdrop-filter: blur(8px); "
                "box-shadow: 0 2px 12px rgba(0,0,0,0.08); "
                "right: auto;"
            ),
        )
    )

    return current_selection
