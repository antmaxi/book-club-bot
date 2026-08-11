from __future__ import annotations

from typing import Final

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


def stored_original_language(code: str) -> str | None:
    return STORED_ORIGINAL_LANGUAGE.get(code)
