# i18n.py
"""
OCapistaine - Internationalization Module

Simple JSON-based translation system for Streamlit.
Supports French and English with easy extensibility.
"""

import json
from pathlib import Path
from typing import Dict

import streamlit as st

# Translation files directory
TRANSLATIONS_DIR = Path(__file__).parent / "translations"

# Supported languages
LANGUAGES = {
    "fr": "Français",
    "en": "English",
}

DEFAULT_LANGUAGE = "fr"


@st.cache_data
def load_translations() -> Dict[str, Dict[str, str]]:
    """
    Load all translation files.

    Returns:
        Dict mapping language codes to translation dictionaries.
    """
    translations = {}

    for lang_code in LANGUAGES.keys():
        file_path = TRANSLATIONS_DIR / f"{lang_code}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                translations[lang_code] = json.load(f)
        else:
            translations[lang_code] = {}

    return translations


def get_language() -> str:
    """Get the current language from session state."""
    if "lang" not in st.session_state:
        st.session_state.lang = DEFAULT_LANGUAGE
    return st.session_state.lang


def set_language(lang_code: str) -> None:
    """Set the current language in session state."""
    if lang_code in LANGUAGES:
        st.session_state.lang = lang_code


def _(key: str, **kwargs) -> str:
    """
    Translate a key to the current language.

    Args:
        key: Translation key to look up.
        **kwargs: Format arguments for string interpolation.

    Returns:
        Translated string, or the key itself if not found.

    Example:
        _("sidebar_session_id", user_id="abc123")
        # Returns "ID: `abc123...`" in current language
    """
    translations = load_translations()
    lang = get_language()

    # Get translation, fallback to key if not found
    text = translations.get(lang, {}).get(key, key)

    # Apply format arguments if provided
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass  # If format fails, return unformatted text

    return text


def language_selector() -> None:
    """
    Display a language selector widget.

    Typically placed in the sidebar. Updates session state on change.
    """
    current_lang = get_language()

    # Get language names in their native form
    lang_codes = list(LANGUAGES.keys())
    lang_names = list(LANGUAGES.values())

    current_index = lang_codes.index(current_lang) if current_lang in lang_codes else 0

    selected_name = st.selectbox(
        _("language_selector"),
        options=lang_names,
        index=current_index,
        key="language_select",
    )

    # Find the code for the selected language name
    selected_code = lang_codes[lang_names.index(selected_name)]

    if selected_code != current_lang:
        set_language(selected_code)
        st.rerun()
