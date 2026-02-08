# app/ui/__init__.py
"""
UI Components for OCapistaine Streamlit Application.

Components:
- floating_overlay: Floating result panel for action feedback
"""

from app.ui.floating_overlay import (
    init_floating_overlay,
    render_floating_overlay,
    add_to_overlay,
    clear_overlay,
)

__all__ = [
    "init_floating_overlay",
    "render_floating_overlay",
    "add_to_overlay",
    "clear_overlay",
]
