"""
OCapistaine Translation Service

Internationalization (i18n) for the application.
Supports French and English with JSON-based translation files.

Usage:
    from app.services.translations import _, get_language, language_selector

    # Translate a key
    text = _("app_title")

    # With interpolation
    text = _("sidebar_session_id", user_id="abc123")

    # Get current language
    lang = get_language()  # "fr" or "en"

    # Display language selector widget
    language_selector()
"""

from app.services.translations.i18n import (
    LANGUAGES,
    LOCALES_DIR,
    DEFAULT_LANGUAGE,
    load_translations,
    get_language,
    set_language,
    _,
    language_selector,
)

__all__ = [
    "LANGUAGES",
    "LOCALES_DIR",
    "DEFAULT_LANGUAGE",
    "load_translations",
    "get_language",
    "set_language",
    "_",
    "language_selector",
]
