from __future__ import annotations

CEFR_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
_CEFR_ORDER = {level: i for i, level in enumerate(CEFR_LEVELS)}


def parse_language_levels(stored: str | None) -> set[str]:
    if not stored:
        return set()
    parts = [p.strip().upper() for p in stored.split(",") if p.strip()]
    return {p for p in parts if p in _CEFR_ORDER}


def format_language_levels(levels: set[str] | list[str] | str | None) -> str | None:
    if levels is None:
        return None
    if isinstance(levels, str):
        parsed = parse_language_levels(levels)
        if not parsed:
            return None
        levels_set = parsed
    else:
        levels_set = {lvl.upper() for lvl in levels if lvl.upper() in _CEFR_ORDER}
    if not levels_set:
        return None
    ordered = sorted(levels_set, key=lambda x: _CEFR_ORDER[x])
    return ",".join(ordered)


def language_levels_display(stored: str | None) -> str | None:
    """Human-readable levels for cards (e.g. A2, B1)."""
    canonical = format_language_levels(stored)
    if not canonical:
        return None
    return canonical.replace(",", ", ")
