# app/ui/footer.py
"""
Footer Component

Renders the civic footer with links to audierne2026.fr,
the Lighthouse Manifesto, and open-source attribution.

Usage:
    from app.ui.footer import render_footer
    render_footer()
"""

import streamlit as st


def render_footer(
    show_clear: bool = False,
    on_clear=None,
) -> None:
    """
    Render the civic footer with links and optional clear button.

    Args:
        show_clear: Whether to show the "Nouvelle conversation" button.
        on_clear: Callback when clear is clicked (should handle session reset + rerun).
    """
    if show_clear and on_clear:
        if st.button("🔄 Nouvelle conversation", use_container_width=False):
            on_clear()

    st.markdown(
        """
<div class="audierne-footer">
    <a href="https://audierne2026.fr" target="_blank">audierne2026.fr</a>
    &nbsp;·&nbsp;
    <a href="https://docs.locki.io/blog/the-lighthouse-manifesto" target="_blank">Le Manifeste du Phare</a>
    &nbsp;·&nbsp;
    <a href="https://github.com/locki-io/ocapistaine" target="_blank">Code source ouvert</a>
    <br>
    Ò Capistaine — IA civique transparente pour Audierne-Esquibien
</div>
""",
        unsafe_allow_html=True,
    )
