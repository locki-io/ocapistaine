# app/ui/chat_input.py
"""
Floating Chat Input Component

Keeps the prompt input always visible at the bottom of the viewport,
even when the user scrolls through long conversation history.
Uses streamlit-float for CSS positioning.

Note: st.chat_input() has special Streamlit rendering that conflicts
with float containers. We use st.text_area + button inside a floated
container instead, styled to match the chat aesthetic.

Usage:
    from app.ui.chat_input import init_chat_float, render_floating_input

    # At the top of your page:
    init_chat_float()

    # Where you want the input (typically at the end):
    prompt = render_floating_input(placeholder="Votre question...")
"""

import streamlit as st
from streamlit_float import float_init, float_css_helper


def init_chat_float() -> None:
    """
    Initialize streamlit-float for the chat interface.

    Call once at the top of your page, before any floating components.
    """
    float_init()

    # Responsive styles — desktop: centered 40% width; mobile: full width
    # Target the float container via its inline style (position:fixed + bottom:0)
    st.markdown(
        """
    <style>
    /* Bottom padding so content doesn't hide behind the float */
    section.main > div.block-container {
        padding-bottom: 7rem !important;
    }

    /* Desktop: centered bar, 40% width, rounded top corners, subtle shadow */
    @media (min-width: 768px) {
        div[style*="position: fixed"][style*="bottom: 0px"][style*="z-index: 9990"] {
            width: 40% !important;
            left: 30% !important;
            border-radius: 1rem 1rem 0 0 !important;
            box-shadow: 0 -4px 16px rgba(0,0,0,0.08) !important;
            border: 1px solid #cecfd1 !important;
            border-bottom: none !important;
        }
    }

    /* Mobile: full width, flush to edges */
    @media (max-width: 767px) {
        div[style*="position: fixed"][style*="bottom: 0px"][style*="z-index: 9990"] {
            width: 100% !important;
            left: 0 !important;
            border-radius: 0 !important;
        }
    }

    /* Override Streamlit's default red submit button → light blue */
    div[style*="position: fixed"][style*="z-index: 9990"] button[kind="secondaryFormSubmit"],
    div[style*="position: fixed"][style*="z-index: 9990"] button[type="submit"] {
        background-color: rgba(0, 146, 202, 0.1) !important;
        border-color: #0092ca !important;
        color: #0092ca !important;
    }
    div[style*="position: fixed"][style*="z-index: 9990"] button[kind="secondaryFormSubmit"]:hover,
    div[style*="position: fixed"][style*="z-index: 9990"] button[type="submit"]:hover {
        background-color: rgba(0, 146, 202, 0.2) !important;
        border-color: #007aab !important;
        color: #007aab !important;
    }

    /* Also override the text_area focus ring to light blue */
    div[style*="position: fixed"][style*="z-index: 9990"] textarea:focus {
        border-color: #0092ca !important;
        box-shadow: 0 0 0 1px #0092ca !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_floating_input(
    placeholder: str = "Votre question...",
) -> str | None:
    """
    Render a text area inside a floating container pinned to the viewport bottom.

    Desktop: centered, 40% width, 3-4 lines tall.
    Mobile: full width, compact.

    Args:
        placeholder: Input placeholder text.

    Returns:
        The user's input string, or None if nothing submitted.
    """
    input_container = st.container()

    prompt = None

    with input_container:
        with st.form("chat_form", clear_on_submit=True, border=False):
            col_input, col_send = st.columns([10, 1], gap="small")
            with col_input:
                user_text = st.text_area(
                    "question",
                    placeholder=placeholder,
                    label_visibility="collapsed",
                    key="floating_chat_text",
                    height=80,
                )
            with col_send:
                submitted = st.form_submit_button(
                    "➤",
                    use_container_width=True,
                )

            if submitted and user_text and user_text.strip():
                prompt = user_text.strip()

    # Float to viewport bottom — full width as base, CSS media queries override for desktop
    input_container.float(
        float_css_helper(
            bottom="0px",
            left="0px",
            width="100%",
            background="#ffffff",
            border_radius="0px",
            custom=(
                "padding: 0.5rem 1rem 0.75rem; "
                "z-index: 9990; "
                "border-top: 1px solid #cecfd1;"
            ),
        )
    )

    return prompt
