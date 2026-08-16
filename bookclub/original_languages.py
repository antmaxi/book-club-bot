from __future__ import annotations

from typing import Final

from bookclub.i18n import s

# Callback codes → value stored in DB (English names for consistency).
ORIGINAL_LANGUAGE_CODES: Final = ("ru", "de", "en", "it", "fr", "es", "zh", "ja")

STORED_ORIGINAL_LANGUAGE: dict[str, str] = {
    "ru": "Russian",
    "de": "German",
    "en": "English",
    "it": "Italian",
    "fr": "French",
    "es": "Spanish",
    "zh": "Chinese",
    "ja": "Japanese",
}

_CODE_BY_STORED: dict[str, str] = {
    name: code for code, name in STORED_ORIGINAL_LANGUAGE.items()
}


def stored_original_language(code: str) -> str | None:
    return STORED_ORIGINAL_LANGUAGE.get(code)


def original_language_code_for_stored(stored: str) -> str | None:
    return _CODE_BY_STORED.get(stored)


def display_original_language(stored: str, lang: str) -> str:
    """UI label for a DB-stored original-language name, in the user's language."""
    code = original_language_code_for_stored(stored)
    if code is None:
        return stored
    return s(lang, f"orig_lang_{code}")
