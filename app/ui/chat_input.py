# app/ui/chat_input.py
"""
Chat Scroll & Input Utilities

Provides scroll-to-bottom helper for Grok/ChatGPT-like auto-follow behavior.
Uses native st.chat_input() (pinned at viewport bottom by Streamlit).

streamlit-float is still initialized here for floating_overlay.py (Forseti results).

Usage:
    from app.ui.chat_input import init_chat_float, scroll_to_bottom

    # At the top of your page:
    init_chat_float()

    # After adding new content (user message, assistant reply):
    scroll_to_bottom()
"""

import streamlit as st
from streamlit_float import float_init


def init_chat_float() -> None:
    """
    Initialize streamlit-float (for floating overlay) and base chat CSS.

    Call once at the top of your page.
    """
    float_init()

    st.markdown(
        """
    <style>
    /* Ensure smooth scrolling on the main container */
    [data-testid="stAppViewContainer"],
    section.main {
        scroll-behavior: smooth;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def scroll_to_bottom(smooth: bool = True) -> None:
    """
    Force-scroll the viewport to the bottom of the page.

    Grok/ChatGPT-like behavior: after a new message is added or during
    streaming, the view follows the latest content.

    Uses multiple selectors for Streamlit version compatibility.
    A small setTimeout ensures the DOM has updated before scrolling.

    Args:
        smooth: If True, smooth scroll animation. If False, instant jump.
    """
    behavior = "smooth" if smooth else "auto"
    st.markdown(
        f"""
        <script>
        setTimeout(function() {{
            // Primary: scroll the window itself
            window.parent.scrollTo({{ top: window.parent.document.body.scrollHeight, behavior: '{behavior}' }});

            // Fallback: scroll known Streamlit containers
            var selectors = [
                '[data-testid="stAppViewContainer"]',
                'section.main',
                '.main'
            ];
            for (var i = 0; i < selectors.length; i++) {{
                var el = window.parent.document.querySelector(selectors[i]);
                if (el && el.scrollHeight > el.clientHeight) {{
                    el.scrollTo({{ top: el.scrollHeight, behavior: '{behavior}' }});
                }}
            }}
        }}, 80);
        </script>
        """,
        unsafe_allow_html=True,
    )


def scroll_to_bottom_streaming() -> None:
    """
    Install a MutationObserver for continuous auto-scroll during streaming.

    Call this once before st.write_stream() begins. The observer will:
    - Throttle scrolls to max 10/sec (avoid layout thrashing)
    - Auto-disconnect 3s after the last DOM mutation (streaming done)
    - Hard-disconnect after 90s (safety net)
    """
    st.markdown(
        """
    <script>
    (function() {
        var doc = window.parent.document;
        var main = doc.querySelector('[data-testid="stAppViewContainer"]')
                || doc.querySelector('section.main')
                || doc.querySelector('.main');
        if (!main) return;

        // Immediate snap
        main.scrollTo({ top: main.scrollHeight, behavior: 'instant' });

        // Clean up previous observer
        if (window._ocapAutoScroll) { window._ocapAutoScroll.disconnect(); }

        var lastScroll = 0;
        var silenceTimer = null;

        function scrollDown() {
            var now = Date.now();
            if (now - lastScroll < 100) return;
            lastScroll = now;
            main.scrollTo({ top: main.scrollHeight, behavior: 'smooth' });

            // Disconnect after 3s of silence (streaming done)
            if (silenceTimer) clearTimeout(silenceTimer);
            silenceTimer = setTimeout(function() {
                if (window._ocapAutoScroll) {
                    window._ocapAutoScroll.disconnect();
                    window._ocapAutoScroll = null;
                }
            }, 3000);
        }

        window._ocapAutoScroll = new MutationObserver(scrollDown);
        window._ocapAutoScroll.observe(main, {
            childList: true,
            subtree: true,
            characterData: true
        });

        // Hard timeout: 90s
        setTimeout(function() {
            if (window._ocapAutoScroll) {
                window._ocapAutoScroll.disconnect();
                window._ocapAutoScroll = null;
            }
        }, 90000);
    })();
    </script>
    """,
        unsafe_allow_html=True,
    )
