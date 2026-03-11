# app/ui/theme.py
"""
Audierne2026 Theme — CSS styles for Ò Capistaine Streamlit interfaces.

Centralizes the visual identity so all pages share the same look.
Colors from the "air" skin of audierne2026.fr:
    Primary: #0092ca  |  Text: #222831  |  Links: #393e46  |  BG: #eeeeee

Usage:
    from app.ui.theme import apply_theme
    apply_theme()                      # default: sidebar visible
    apply_theme(hide_sidebar=True)     # for chat page
"""

import streamlit as st

# ── Color tokens ──────────────────────────────────────────
PRIMARY = "#0092ca"
PRIMARY_DARK = "#007aab"
TEXT = "#222831"
LINK = "#393e46"
BORDER = "#cecfd1"
BG_LIGHT = "#eeeeee"
MUTED = "#9b9b9d"


def apply_theme(hide_sidebar: bool = False) -> None:
    """
    Inject the audierne2026.fr CSS theme.

    Args:
        hide_sidebar: If True, hides the Streamlit sidebar and its toggle.
    """
    sidebar_css = ""
    if hide_sidebar:
        sidebar_css = """
/* ── Hide sidebar ──────────────────────────────── */
section[data-testid="stSidebar"] {
    display: none;
}
[data-testid="stSidebarCollapsedControl"] {
    display: none;
}
"""

    st.markdown(
        f"""
<style>
/* ── Global ─────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

/* Reduce Streamlit's excessive top padding */
section.main > div.block-container {{
    padding-top: 1.5rem !important;
}}

/* ── Header banner ──────────────────────────────── */
.audierne-header {{
    padding: 0.75rem 1rem;
    background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    color: white;
}}
.audierne-header-top {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
}}
.audierne-header img {{
    height: 2.5rem;
    border-radius: 4px;
    background: white;
    padding: 2px;
}}
.audierne-header .title {{
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.01em;
}}
.audierne-header .subtitle {{
    font-size: 0.8rem;
    opacity: 0.85;
}}
.audierne-header-divider {{
    height: 1px;
    background: rgba(255, 255, 255, 0.3);
    margin: 0.6rem 0;
}}
.audierne-header .tagline {{
    font-size: 0.8rem;
    opacity: 0.85;
    font-style: italic;
    text-align: center;
}}

/* ── Primary button: selected state = white on blue ── */
.stButton > button[kind="primary"] {{
    background-color: {PRIMARY} !important;
    border-color: {PRIMARY} !important;
    color: #ffffff !important;
}}
.stButton > button[kind="primary"]:hover {{
    background-color: {PRIMARY_DARK} !important;
    border-color: {PRIMARY_DARK} !important;
    color: #ffffff !important;
}}

/* ── Secondary button: unselected state ────────── */
.stButton > button[kind="secondary"] {{
    border-color: {BORDER};
    color: {TEXT};
    background-color: #ffffff;
}}
.stButton > button[kind="secondary"]:hover {{
    border-color: {PRIMARY};
    color: {PRIMARY};
    background-color: rgba(0, 146, 202, 0.08);
}}

/* Chat input ring */
.stChatInput > div {{
    border-color: {BORDER} !important;
}}
.stChatInput > div:focus-within {{
    border-color: {PRIMARY} !important;
    box-shadow: 0 0 0 1px {PRIMARY};
}}

/* ── Chat messages ──────────────────────────────── */
[data-testid="stChatMessage"] {{
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
}}

/* ── Links ──────────────────────────────────────── */
a {{
    color: {LINK};
}}
a:hover {{
    color: {PRIMARY};
}}

/* ── Source expander ────────────────────────────── */
.streamlit-expanderHeader {{
    font-size: 0.85rem;
    color: {LINK};
}}

/* ── Info banner ────────────────────────────────── */
.stAlert > div[data-baseweb="notification"] {{
    background-color: rgba(0, 146, 202, 0.08);
    border-left-color: {PRIMARY};
}}

/* ── Metrics ────────────────────────────────────── */
[data-testid="stMetricValue"] {{
    color: {PRIMARY};
}}

/* ── Selectbox focus ────────────────────────────── */
div[data-baseweb="select"] > div:focus-within {{
    border-color: {PRIMARY} !important;
}}

/* ── Divider ────────────────────────────────────── */
hr {{
    border-color: {BORDER};
}}

/* ── Footer ─────────────────────────────────────── */
.audierne-footer {{
    text-align: center;
    padding: 1rem 0 0.5rem;
    font-size: 0.75rem;
    color: {MUTED};
    border-top: 1px solid {BORDER};
    margin-top: 2rem;
}}
.audierne-footer a {{
    color: {PRIMARY};
    text-decoration: none;
}}

{sidebar_css}
</style>
""",
        unsafe_allow_html=True,
    )
