#!/usr/bin/env python3
"""Split bookclub_bot.py into the bookclub/ package (run from repo root)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_LINES = (ROOT / "bookclub_bot.py").read_text(encoding="utf-8").splitlines()


def extract(start: int, end: int) -> str:
    return "\n".join(SRC_LINES[start - 1 : end]) + "\n"


PKG = ROOT / "bookclub"
HANDLERS = PKG / "handlers"
PKG.mkdir(exist_ok=True)
HANDLERS.mkdir(exist_ok=True)

(PKG / "types.py").write_text(
    """from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, Literal

Lang = Literal["en", "ru"]
TranslationValue = str | Callable[..., str]
BookLike = sqlite3.Row | Mapping[str, Any]
""",
    encoding="utf-8",
)

(PKG / "config.py").write_text(
    """from __future__ import annotations

import os

"""
    + extract(74, 136),
    encoding="utf-8",
)

(PKG / "logging_setup.py").write_text(
    """from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
from collections import deque

from telegram.ext import Application

from bookclub.config import ADMIN_IDS, ERROR_ALERTS, INSTANCE_NAME, LOG_FILE

"""
    + extract(140, 263),
    encoding="utf-8",
)

(PKG / "i18n.py").write_text(
    """from __future__ import annotations

from typing import Any

from telegram.ext import ContextTypes

from bookclub.config import CLUB_ENTITY
from bookclub.types import TranslationValue

"""
    + extract(266, 844)
    + extract(866, 894),
    encoding="utf-8",
)

(PKG / "domain.py").write_text(
    """from __future__ import annotations

import sqlite3

from bookclub.config import ADMIN_IDS
from bookclub.db import db_get_book
from bookclub.types import BookLike

"""
    + extract(847, 863)
    + extract(896, 900),
    encoding="utf-8",
)

(PKG / "db.py").write_text(
    """from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from bookclub.config import DB_PATH
from bookclub.types import BookLike

"""
    + extract(904, 1654),
    encoding="utf-8",
)

(PKG / "ui.py").write_text(
    """from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.config import (
    ALLOWED_CHAT_ID,
    CHAT_LANG,
    MEETING_ATTENDEES_PAGE_SIZE,
)
from bookclub.db import db_meeting_user_suggestions, db_upsert_club_user
from bookclub.i18n import PM, T, get_lang, h, s, tr, vote_label_text
from bookclub.logging_setup import logger
from bookclub.types import BookLike

"""
    + extract(1657, 2116),
    encoding="utf-8",
)

(PKG / "notifications.py").write_text(
    """from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from telegram.ext import ContextTypes

from bookclub.config import (
    ALLOWED_CHAT_ID,
    CHAT_LANG,
    NEW_BOOK_NOTIFY_DELAY_SECONDS,
)
from bookclub.db import (
    db_begin_new_book_notify,
    db_get_books_pending_notify,
    db_get_user_setting,
    db_get_users_with_setting,
    db_get_admin_setting,
)
from bookclub.domain import require_book
from bookclub.i18n import PM, get_lang, tr
from bookclub.logging_setup import logger
from bookclub.ui import book_card, post_book_voting_to_group_chat, score_keyboard

"""
    + extract(2683, 2808),
    encoding="utf-8",
)

(HANDLERS / "commands.py").write_text(
    """from __future__ import annotations

import os
import subprocess
from datetime import datetime

from telegram import (
    Bot,
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeChatMember,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bookclub.config import CLUB_ENTITY, GITHUB_REPO
from bookclub.db import (
    db_cast_vote,
    db_get_books,
    db_get_user_setting,
    db_get_user_vote,
    db_set_user_setting,
)
from bookclub.i18n import PM, T, get_lang, s, tr
from bookclub.logging_setup import logger
from bookclub.ui import (
    _parse_list_callback,
    _show_list_format_prompt,
    book_card,
    book_compact_line,
    books_keyboard,
    books_top_n,
    fmt_dt_utc,
    h,
    score_keyboard,
    send_chunked_html_messages,
)

"""
    + extract(2121, 2537),
    encoding="utf-8",
)

(HANDLERS / "add.py").write_text(
    """from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.config import (
    ADDING_AUTHOR,
    ADDING_CREATION_YEAR,
    ADDING_DESCRIPTION,
    ADDING_FICTION,
    ADDING_ORIGINAL_LANGUAGE,
    ADDING_PAGES,
    ADDING_REVIEW,
    ADDING_TITLE,
    ADDING_TITLE_CONFIRM,
)
from bookclub.db import db_add_book, find_similar_book_titles
from bookclub.i18n import PM, get_lang, s, tr
from bookclub.notifications import schedule_new_book_notifications
from bookclub.ui import (
    fiction_keyboard,
    is_valid_url,
    parse_optional_creation_year,
    similar_title_confirm_keyboard,
    similar_title_warning_matches_text,
)

"""
    + extract(2539, 2681),
    encoding="utf-8",
)

(HANDLERS / "misc.py").write_text(
    """from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.config import CHAT_LANG
from bookclub.db import db_cast_vote, db_get_user_vote, db_upsert_club_user
from bookclub.domain import require_book
from bookclub.i18n import PM, get_lang, tr, vote_label_text
from bookclub.logging_setup import logger
from bookclub.ui import book_card, score_keyboard

"""
    + extract(2810, 2938),
    encoding="utf-8",
)

(HANDLERS / "admin.py").write_text(
    """from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.config import (
    ADMIN_EXPORT_CHOOSE,
    ADMIN_HIDE_CHOOSE,
    ADMIN_IMPORT_CONFIRM,
    ADMIN_IMPORT_WAIT,
    ADMIN_MARK_CHOOSE,
    ADMIN_MARK_DATE,
    ADMIN_MEETING_ADD_ID,
    ADMIN_MEETING_ATTENDEES,
    ADMIN_MEETING_BOOK,
    ADMIN_MEETING_DATE,
    ADMIN_MEETINGS_VIEW,
    ADMIN_MENU,
    ADMIN_NOTIFY_CHAT_PICK,
    ADMIN_NOTIFY_PICK,
    ADMIN_UNHIDE_CHOOSE,
    ALLOWED_CHAT_ID,
    CHAT_LANG,
)
from bookclub.db import (
    book_to_export_payload,
    db_create_meeting,
    db_get_admin_setting,
    db_get_book,
    db_get_books,
    db_get_meeting,
    db_get_meeting_attendee_rows,
    db_get_user_setting,
    db_get_user_vote,
    db_get_users_with_setting,
    db_import_book,
    db_list_meetings,
    db_mark_discussed,
    db_set_admin_setting,
    db_set_hidden,
    db_upsert_club_user,
    format_club_user_display,
    parse_book_import,
)
from bookclub.domain import is_admin, require_book
from bookclub.i18n import PM, T, get_lang, h, s, tr
from bookclub.logging_setup import logger
from bookclub.notifications import schedule_new_book_notifications
from bookclub.ui import (
    _show_meeting_attendee_picker,
    book_card,
    books_keyboard,
    books_top_n,
    meetings_keyboard,
    parse_date,
    post_book_voting_to_group_chat,
    score_keyboard,
)

"""
    + extract(2941, 3760),
    encoding="utf-8",
)

(HANDLERS / "edit_delete.py").write_text(
    """from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.config import DELETING_CHOOSE, EDITING_CHOOSE, EDITING_FIELD
from bookclub.db import db_delete_book, db_get_book, db_get_books, db_update_book_field
from bookclub.domain import can_modify, require_book
from bookclub.i18n import PM, T, get_lang, h, s, tr
from bookclub.ui import books_keyboard

"""
    + extract(3761, 4020),
    encoding="utf-8",
)

(PKG / "lifecycle.py").write_text(
    """from __future__ import annotations

from telegram import BotCommandScopeDefault
from telegram.ext import Application

from bookclub.config import ADMIN_IDS, ERROR_ALERTS
from bookclub.handlers.commands import COMMANDS
from bookclub.i18n import PM, T
from bookclub.logging_setup import _drain_alert_queue, logger
from bookclub.notifications import recover_pending_new_book_notifications

"""
    + extract(4021, 4057),
    encoding="utf-8",
)

(PKG / "membership.py").write_text(
    """from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bookclub.config import ADMIN_IDS, ALLOWED_CHAT_ID, ALLOWED_CHAT_NAME
from bookclub.db import db_upsert_club_user
from bookclub.i18n import PM, get_lang, h, s
from bookclub.logging_setup import logger

"""
    + extract(4064, 4194),
    encoding="utf-8",
)

(PKG / "main.py").write_text(
    """from __future__ import annotations

import os

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    TypeHandler,
    filters,
)

from bookclub.config import (
    ADDING_AUTHOR,
    ADDING_CREATION_YEAR,
    ADDING_DESCRIPTION,
    ADDING_FICTION,
    ADDING_ORIGINAL_LANGUAGE,
    ADDING_PAGES,
    ADDING_REVIEW,
    ADDING_TITLE,
    ADDING_TITLE_CONFIRM,
    ADMIN_EXPORT_CHOOSE,
    ADMIN_HIDE_CHOOSE,
    ADMIN_IMPORT_CONFIRM,
    ADMIN_IMPORT_WAIT,
    ADMIN_MARK_CHOOSE,
    ADMIN_MARK_DATE,
    ADMIN_MEETING_ADD_ID,
    ADMIN_MEETING_ATTENDEES,
    ADMIN_MEETING_BOOK,
    ADMIN_MEETING_DATE,
    ADMIN_MEETINGS_VIEW,
    ADMIN_MENU,
    ADMIN_NOTIFY_CHAT_PICK,
    ADMIN_NOTIFY_PICK,
    ADMIN_UNHIDE_CHOOSE,
    BOT_TOKEN,
    CLUB_ENTITY,
    DELETING_CHOOSE,
    EDITING_CHOOSE,
    EDITING_FIELD,
)
from bookclub.db import init_db
from bookclub.handlers.add import (
    add_author,
    add_creation_year,
    add_description,
    add_fiction_cb,
    add_original_language,
    add_pages,
    add_review,
    add_title,
    add_title_similar_cb,
    cmd_add,
)
from bookclub.handlers.admin import (
    admin_export_pick_cb,
    admin_hide_pick_cb,
    admin_import_handler,
    admin_import_similar_cb,
    admin_mark_date_handler,
    admin_mark_pick_cb,
    admin_meeting_add_id_handler,
    admin_meeting_att_cb,
    admin_meeting_book_cb,
    admin_meeting_date_handler,
    admin_meeting_view_cb,
    admin_menu_cb,
    admin_notify_chat_pick_cb,
    admin_notify_chat_top_cb,
    admin_notify_pick_cb,
    admin_notify_top_cb,
    admin_unhide_pick_cb,
    cmd_admin_console,
)
from bookclub.handlers.commands import (
    cmd_discussed,
    cmd_help,
    cmd_info,
    cmd_list,
    cmd_settings,
    cmd_start,
    cmd_top,
    list_choice_cb,
    score_calc_cb,
    settings_choice_cb,
)
from bookclub.handlers.edit_delete import (
    cmd_delete,
    cmd_edit,
    delete_pick_cb,
    edit_fiction_cb,
    edit_pick_cb,
    edit_value_handler,
    edit_yn_cb,
)
from bookclub.handlers.misc import conv_cancel, vote_cast_cb
from bookclub.lifecycle import bot_notify_shutdown, bot_notify_startup
from bookclub.logging_setup import _drain_alert_queue, logger
from bookclub.membership import error_handler, membership_gate
from bookclub.notifications import recover_pending_new_book_notifications

"""
    + extract(4197, 4445),
    encoding="utf-8",
)

(HANDLERS / "__init__.py").write_text("", encoding="utf-8")
(PKG / "__init__.py").write_text(
    '''"""Book club Telegram bot — package root (re-exported by bookclub_bot)."""
from bookclub.config import *  # noqa: F403
from bookclub.db import *  # noqa: F403
from bookclub.domain import *  # noqa: F403
from bookclub.i18n import *  # noqa: F403
from bookclub.lifecycle import bot_notify_shutdown, bot_notify_startup
from bookclub.logging_setup import logger, logging
from bookclub.main import main, register_handlers
from bookclub.membership import _membership_cache, error_handler, membership_gate
from bookclub.notifications import (
    enqueue_new_book_notify_job,
    notify_new_book_job,
    recover_pending_new_book_notifications,
    schedule_new_book_notifications,
)
from bookclub.types import *  # noqa: F403
from bookclub.ui import *  # noqa: F403

# Handlers (tests and patches import these from bookclub_bot)
from bookclub.handlers.add import *  # noqa: F403
from bookclub.handlers.admin import *  # noqa: F403
from bookclub.handlers.commands import *  # noqa: F403
from bookclub.handlers.edit_delete import *  # noqa: F403
from bookclub.handlers.misc import *  # noqa: F403
''',
    encoding="utf-8",
)

print("bookclub/ package written")
