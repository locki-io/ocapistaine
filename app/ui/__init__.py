# app/ui/__init__.py
"""
UI Components for OCapistaine Streamlit Application.

Niove's domain — the tide that guides users naturally.

Components:
- theme: Audierne2026 CSS theme (colors, typography, layout)
- header: Branded header banner with Audierne blason
- footer: Civic footer with manifesto + source links
- chat_input: Floating chat input pinned to viewport bottom
- floating_overlay: Floating result panel for Forseti action feedback
"""

from app.ui.theme import apply_theme
from app.ui.header import render_header
from app.ui.footer import render_footer
from app.ui.chat_input import init_chat_float, scroll_to_bottom, scroll_to_bottom_streaming
from app.ui.floating_overlay import (
    init_floating_overlay,
    render_floating_overlay,
    add_to_overlay,
    clear_overlay,
)

__all__ = [
    # Theme
    "apply_theme",
    # Header
    "render_header",
    # Footer
    "render_footer",
    # Chat scroll & input
    "init_chat_float",
    "scroll_to_bottom",
    "scroll_to_bottom_streaming",
    # Floating overlay (Forseti results)
    "init_floating_overlay",
    "render_floating_overlay",
    "add_to_overlay",
    "clear_overlay",
]
