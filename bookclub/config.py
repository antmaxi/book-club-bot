from __future__ import annotations

import os
from datetime import timedelta, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]
GITHUB_REPO = os.environ.get("GITHUB_REPO", "https://github.com/antmaxi/book-club-bot")
DB_PATH = os.environ.get("DB_PATH", "bookclub.db")

# Members of this chat are allowed to use the bot.
# Set via environment variable: export ALLOWED_CHAT_ID="-1001234567890"
# Leave empty to allow everyone (useful during initial setup).
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", "0")) or None

# What members vote on: books (default) or films. Same DB schema; labels and prompts
# differ. More kinds (podcast, TV series, …) can be added via ENTITY_STRING_OVERLAYS.
_VALID_CLUB_ENTITIES = frozenset({"book", "film"})


def _club_entity_from_env() -> str:
    raw = os.environ.get("CLUB_ENTITY", "book").strip().lower()
    if raw not in _VALID_CLUB_ENTITIES:
        print(
            f"Warning: unknown CLUB_ENTITY={raw!r}, using 'book'. "
            f"Valid values: {', '.join(sorted(_VALID_CLUB_ENTITIES))}"
        )
        return "book"
    return raw


CLUB_ENTITY = _club_entity_from_env()


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


# When enabled, /add and /edit ask for estimated CEFR level(s) (A1–C2).
ASK_LANGUAGE_LEVEL = _env_truthy("ASK_LANGUAGE_LEVEL")


def language_level_prompt_enabled() -> bool:
    return ASK_LANGUAGE_LEVEL


def _display_utc_offset_hours_from_env() -> int:
    raw = os.environ.get("DISPLAY_UTC_OFFSET_HOURS", "2").strip()
    try:
        hours = int(raw)
    except ValueError:
        print(f"Warning: invalid DISPLAY_UTC_OFFSET_HOURS={raw!r}, using 2 (UTC+2).")
        return 2
    if hours < -12 or hours > 14:
        print(
            f"Warning: DISPLAY_UTC_OFFSET_HOURS={hours} out of range, using 2 (UTC+2)."
        )
        return 2
    return hours


# Wall-clock times in bot messages (e.g. /info, admin console) use this UTC offset.
DISPLAY_UTC_OFFSET_HOURS = _display_utc_offset_hours_from_env()


def display_timezone() -> timezone:
    return timezone(timedelta(hours=DISPLAY_UTC_OFFSET_HOURS))


_ENTITY_DEFAULT_CHAT_NAMES = {"book": "Книжный клуб", "film": "Киноклуб"}
ALLOWED_CHAT_NAME = (
    os.environ.get("ALLOWED_CHAT_NAME") or _ENTITY_DEFAULT_CHAT_NAMES[CLUB_ENTITY]
)

# Language for messages the bot posts into the group chat (en, ru, or de).
# Group messages are shared, so they can't follow any single user's language.
CHAT_LANG = os.environ.get("CHAT_LANG", "ru")

# Delay before broadcasting a new-book card to opted-in users (and optional group chat).
NEW_BOOK_NOTIFY_DELAY_SECONDS = int(
    os.environ.get("NEW_BOOK_NOTIFY_DELAY_SECONDS", "300")
)


def notify_delay_minutes() -> int:
    """Whole minutes for UI copy, derived from NEW_BOOK_NOTIFY_DELAY_SECONDS."""
    secs = NEW_BOOK_NOTIFY_DELAY_SECONDS
    if secs <= 0:
        return 0
    return max(1, secs // 60)


# Conversation states
(
    ADDING_TITLE,
    ADDING_AUTHOR,
    ADDING_PAGES,
    ADDING_FICTION,
    ADDING_REVIEW,
    ADDING_ORIGINAL_LANGUAGE,
    ADDING_CREATION_YEAR,
    ADDING_DESCRIPTION,
) = range(8)
ADDING_TITLE_CONFIRM = 25
ADMIN_IMPORT_CONFIRM = 26
ADDING_LANGUAGE_LEVEL = 27
ADDING_ORIGINAL_LANGUAGE_OTHER = 28
EDITING_CHOOSE = 8
EDITING_FIELD = 9  # waiting for new value of current field
DELETING_CHOOSE = 10
(
    ADMIN_MENU,
    ADMIN_MARK_CHOOSE,
    ADMIN_MARK_DATE,
    ADMIN_HIDE_CHOOSE,
    ADMIN_UNHIDE_CHOOSE,
    ADMIN_NOTIFY_PICK,
    ADMIN_NOTIFY_CHAT_PICK,
    ADMIN_EXPORT_CHOOSE,
    ADMIN_IMPORT_WAIT,
    ADMIN_MEETING_BOOK,
    ADMIN_MEETING_DATE,
    ADMIN_MEETING_ATTENDEES,
    ADMIN_MEETING_ADD_ID,
    ADMIN_MEETINGS_VIEW,
) = range(11, 25)

MEETING_ATTENDEES_PAGE_SIZE = 7
NOTIFY_BOOKS_PAGE_SIZE = 8

LOG_FILE = os.environ.get("LOG_FILE", "logs/bookclub_bot.log")

ERROR_ALERTS = os.environ.get("ERROR_ALERTS", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "")

IMPORTED_USER_ID = 0  # books imported without a real Telegram user
