# app/ui/header.py
"""
Branded Header Component

Renders the Ò Capistaine header banner with the Audierne blason,
matching the audierne2026.fr visual identity.

Usage:
    from app.ui.header import render_header
    render_header()
"""

import base64
from pathlib import Path

import streamlit as st

# Resolve blason path once at module level
_BLASON_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "ext_data"
    / "audierne2026"
    / "assets"
    / "images"
    / "Blason_fr_Audierne.svg.png"
)


def render_header(
    title: str = "Ò Capistaine — Audierne",
    subtitle: str = "Ensemble, écoutons et co-construisons",
    tagline: str = "Ici l'IA n'est pas une boite noire, c'est notre phare vers les municipales",
) -> None:
    """
    Render the branded header with Audierne blason and tagline.

    Falls back to a plain st.title() if the blason image is missing.

    Args:
        title: Main title text.
        subtitle: Subtitle text below the title.
        tagline: Lighthouse tagline shown below the banner.
    """
    if _BLASON_PATH.exists():
        blason_b64 = base64.b64encode(_BLASON_PATH.read_bytes()).decode()
        st.markdown(
            f"""
        <div class="audierne-header">
            <div class="audierne-header-top">
                <img src="data:image/png;base64,{blason_b64}" alt="Audierne">
                <div>
                    <div class="title">{title}</div>
                    <div class="subtitle">{subtitle}</div>
                </div>
            </div>
            <div class="audierne-header-divider"></div>
            <div class="tagline">{tagline}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    else:
        st.title(title)
