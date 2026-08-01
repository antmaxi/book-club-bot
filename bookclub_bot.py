#!/usr/bin/env python3
"""
Book Club Telegram Bot — EN/RU bilingual
=========================================
Fields per book:
  - title, author, pages, fiction, review_link, description
  - added_at, added_by
  - discussed (flag, admin-only), discussed_at (date)

Features:
  - Bilingual support (English and Russian).
  - Add and manage books for the club.
  - Vote on books: "Want", "Don't care", "Don't want".
  - Ranking system (Top books) based on average score and vote count.
  - New book notifications: receive a voting card for new books after 10 minutes.
  - User settings to opt-in or out of notifications.

Commands:
  /start / /help   - Welcome message and command overview
  /add             - Add a new book (with 10-minute delayed notification to others)
  /list            - List all undiscussed books (all or only unvoted)
  /top             - View top-rated undiscussed books
  /settings        - Manage notification and language preferences
  /info            - Information about the bot and source code
  /edit            - Edit a book's details (owner/admin only)
  /delete          - Delete a book (owner/admin only)
  /discussed       - View the archive of discussed books
  /adminconsole    - Admin console: mark discussed or hide
  /cancel          - Cancel the current operation
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import sqlite3
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, cast

from telegram import (
    Bot,
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import NetworkError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    TypeHandler,
    filters,
)

Lang = Literal["en", "ru"]
TranslationValue = str | Callable[..., str]
BookLike = sqlite3.Row | Mapping[str, Any]

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
_ENTITY_DEFAULT_CHAT_NAMES = {"book": "Книжный клуб", "film": "Киноклуб"}
ALLOWED_CHAT_NAME = (
    os.environ.get("ALLOWED_CHAT_NAME") or _ENTITY_DEFAULT_CHAT_NAMES[CLUB_ENTITY]
)

# Language for messages the bot posts into the group chat. Group messages are
# shared, so they can't follow any single user's language preference.
CHAT_LANG = os.environ.get("CHAT_LANG", "ru")

# Conversation states
(
    ADDING_TITLE,
    ADDING_AUTHOR,
    ADDING_PAGES,
    ADDING_FICTION,
    ADDING_REVIEW,
    ADDING_DESCRIPTION,
) = range(6)
EDITING_CHOOSE = 6
EDITING_FIELD = 7  # waiting for new value of current field
DELETING_CHOOSE = 8
ADMIN_MENU, ADMIN_MARK_CHOOSE, ADMIN_MARK_DATE, ADMIN_HIDE_CHOOSE, ADMIN_NOTIFY_PICK, ADMIN_NOTIFY_CHAT_PICK = (
    range(9, 15)
)

LOG_FILE = os.environ.get("LOG_FILE", "logs/bookclub_bot.log")

_log_fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

_handlers: list[logging.Handler] = [_console_handler]

# The log directory is not in git (see .gitignore), so on a fresh clone it does
# not exist yet and RotatingFileHandler would raise at import time — taking the
# whole module, and the test suite, down with it.
_log_dir = os.path.dirname(LOG_FILE)
try:
    if _log_dir:
        os.makedirs(_log_dir, exist_ok=True)
    _file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _file_handler.setFormatter(_log_fmt)
    _handlers.append(_file_handler)
except OSError as e:
    # Read-only filesystem, bad LOG_FILE path, … — console logging still works.
    print(f"Warning: file logging disabled ({LOG_FILE}): {e}")

logging.basicConfig(level=logging.INFO, handlers=_handlers)
logger = logging.getLogger(__name__)

# ── Error alerting to Telegram ───────────────────────────────────────────────────
# Anything logged at ERROR or above is forwarded to the main admin's Telegram
# chat, so failures surface immediately instead of sitting unread in the log
# file. The logging handler runs synchronously (and may fire before the event
# loop even exists, e.g. during import), so it only *buffers* records; a
# background task started at startup drains the buffer and does the sending.
ERROR_ALERTS = os.environ.get("ERROR_ALERTS", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
# Optional label so a shared admin can tell which bot an alert came from.
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "")

# Bounded so a burst of errors — or a wedged loop that never drains this —
# can't grow memory without limit; oldest alerts are dropped first.
_ALERT_BUFFER_MAX = 200
_alert_buffer: deque[str] = deque(maxlen=_ALERT_BUFFER_MAX)
_alert_dropped = 0  # records discarded because the buffer was full

_ALERT_FLUSH_INTERVAL = 3.0  # seconds between sends — a basic rate limit
_ALERT_MAX_PER_FLUSH = 5  # records coalesced into one message per flush

# Loggers whose failures we must NOT alert on, or we risk a feedback loop:
# sending an alert can itself fail deep inside httpx/telegram and log an error,
# which would enqueue another alert, which fails again, forever.
_ALERT_SKIP_PREFIXES = ("httpx", "httpcore", "telegram", "apscheduler")


class _TelegramAlertHandler(logging.Handler):
    """Buffer ERROR+ log records for later delivery to the admin via Telegram."""

    def emit(self, record: logging.LogRecord) -> None:
        global _alert_dropped
        name = record.name or ""
        # ".alert" is our own delivery-failure logger (see _alert_logger); the
        # prefixes are the networking stack that a failing send screams from.
        if name.endswith(".alert") or name.startswith(_ALERT_SKIP_PREFIXES):
            return
        try:
            msg = self.format(record)
        except Exception:
            return
        if len(_alert_buffer) == _alert_buffer.maxlen:
            _alert_dropped += 1
        _alert_buffer.append(msg)


# Child logger for reporting alert-delivery failures. Its name ends in
# ".alert" so _TelegramAlertHandler.emit() skips it — otherwise a failed send
# would try to alert about itself and never stop.
_alert_logger = logger.getChild("alert")

if ERROR_ALERTS:
    _alert_handler = _TelegramAlertHandler(level=logging.ERROR)
    _alert_handler.setFormatter(_log_fmt)
    logging.getLogger().addHandler(_alert_handler)


async def _drain_alert_queue(app: Application) -> None:
    """Forward buffered ERROR logs to the main admin.

    Runs for the lifetime of the bot. Coalesces up to _ALERT_MAX_PER_FLUSH
    records into a single message every _ALERT_FLUSH_INTERVAL seconds, so a
    storm of errors can't turn into a storm of notifications.
    """
    global _alert_dropped
    admin_id = ADMIN_IDS[0]
    prefix = f"[{INSTANCE_NAME}] " if INSTANCE_NAME else ""
    while True:
        await asyncio.sleep(_ALERT_FLUSH_INTERVAL)
        if not _alert_buffer:
            continue

        batch: list[str] = []
        while _alert_buffer and len(batch) < _ALERT_MAX_PER_FLUSH:
            batch.append(_alert_buffer.popleft())
        dropped, _alert_dropped = _alert_dropped, 0

        header = f"{prefix}⚠️ {len(batch)} error(s) logged"
        if dropped:
            header += f" (+{dropped} dropped)"
        if _alert_buffer:
            header += f" (+{len(_alert_buffer)} still queued)"
        text = f"{header}:\n\n" + "\n\n".join(batch)
        if len(text) > 3900:  # Telegram caps messages at 4096; leave headroom
            text = text[:3900] + "\n… (truncated)"

        try:
            # Plain text on purpose: tracebacks are full of Markdown-special
            # characters that would break parse_mode rendering (or get dropped).
            await app.bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            # Reported via the ".alert" child so this failure is not itself
            # turned into an alert (which could not be delivered either).
            _alert_logger.warning(f"Could not deliver error alert: {e}")


# ── Translations ───────────────────────────────────────────────────────────────
T: dict[str, dict[str, TranslationValue]] = {
    "en": {
        "welcome": (
            "📚 <b>Welcome to the Book Club Bot!</b>\n\n"
            "➕ /add — Add a book\n"
            "📋 /list — See all books\n"
            "🏆 /top — Top rated books\n"
            "⚙️ /settings — Settings\n"
            "ℹ️ /info — About the bot\n"
            "✏️ /edit — Edit a book entry\n"
            "🗑 /delete — Delete a book\n"
            "✅ /discussed — Books already discussed\n"
            "🛠 /adminconsole — Admin console\n"
            "❓ /help — Show this message"
        ),
        "lang_set": "🇬🇧 Language set to English.",
        "ask_title": "📖 What is the <b>title</b> of the book?",
        "ask_author": "✍️ Who is the <b>author</b>?",
        "ask_pages": "📄 How many <b>pages</b> does it have? (enter a number)",
        "invalid_pages": "⚠️ Please enter a valid number of pages (e.g. 320):",
        "ask_fiction": "📂 Is it <b>Fiction</b> or <b>Non-fiction</b>?",
        "fiction_btn": "📖 Fiction",
        "nonfiction_btn": "📰 Non-fiction",
        "ask_review": "🔗 Paste the <b>link to a review</b> (must start with http:// or https://):",
        "invalid_review": "⚠️ That doesn't look like a valid URL. Please paste a link starting with http:// or https://:",
        "ask_desc": "📝 Add a <b>description</b> (or /skip to leave empty):",
        "book_added": "✅ Book added!",
        "no_books": "📭 No books yet. Use /add to add one!",
        "no_undiscussed": "📭 No undiscussed books — use /discussed to see past reads.",
        "no_votes": "No votes yet. Use /list to see books and vote inline!",
        "no_books_edit": "📭 No books to edit yet.",
        "no_books_delete": "📭 No books to delete yet.",
        "cancelled": "❌ Cancelled.",
        "unexpected_error": "⚠️ Something went wrong on my side. Please try again — use /cancel first if you were in the middle of something.",
        "choose_vote": "📊 Choose a book to vote on:",
        "choose_edit": "✏️ Choose a book to edit:",
        "choose_delete": "🗑 Choose a book to delete:",
        "your_vote": "Your current vote",
        "none_vote": "—",
        "rate_book": "📊 Vote on <b>{title}</b>",
        "desc_updated": "✅ Description updated!",
        "top_title": "🏆 <b>Top Books</b>\nSorted by total score.\n\n",
        "added_by": "Added by",
        "added_on": "Added on",
        "pages_label": "Pages",
        "review_label": "Review",
        "cancel_btn": "❌ Cancel",
        "edit_field_prompt": "✏️ <b>{field}</b>\nCurrent value: <i>{value}</i>\n\nModify this field?",
        "edit_yes_btn": "✏️ Yes, change it",
        "edit_no_btn": "⏭ Skip",
        "edit_ask_new": "Send the new value for <b>{field}</b>:",
        "edit_done": "✅ Book updated!",
        "edit_invalid_pages": "⚠️ Must be a positive number. Send again:",
        "edit_invalid_url": "⚠️ Must start with http:// or https://. Send again:",
        "field_title": "Title",
        "field_author": "Author",
        "field_pages": "Pages",
        "field_fiction": "Fiction / Non-fiction",
        "field_review": "Review link",
        "field_description": "Description",
        "deleted": "🗑 <b>{title}</b> has been deleted.",
        "fiction_label": "Fiction",
        "nonfiction_label": "Non-fiction",
        "votes_label": lambda n: f"({n} vote{'s' if n != 1 else ''})",
        "want_label": "✅ want to read",
        "meh_label": "😐 don't care",
        "no_label": "❌ don't want to read",
        "vote_registered": "Your vote: {label}",
        "want_btn": "✅ Want",
        "meh_btn": "😐 Don't care",
        "no_btn": "❌ Don't want",
        "voted_msg": "✅ Vote saved for <b>{title}</b>",
        "score_label": "Score",
        "no_permission": "⛔ You can only edit or delete books you added.",
        "no_own_books": "📭 You have no books to edit or delete.",
        "admin_only": "⛔ This command is for admins only.",
        "admin_console_title": "🛠 <b>Admin Console</b>",
        "admin_mark_btn": "📌 Mark discussed",
        "admin_hide_btn": "👻 Hide book",
        "admin_notify_btn": "🔔 Send voting reminder (top)",
        "admin_notify_one_btn": "🔔 Send reminder for a specific book",
        "admin_notify_chat_btn": "💬 Post voting reminder to chat (top)",
        "admin_notify_chat_one_btn": "💬 Post reminder to chat (pick book)",
        "choose_notify_chat": "💬 Choose a book to post a voting reminder in the group chat:",
        "vote_reminder_chat": "🔔 <b>Voting reminder!</b>\n\n",
        "admin_notify_chat_confirm": "💬 Voting reminder posted to the group chat ({count} book(s)).",
        "admin_notify_chat_no_chat": "ℹ️ Group chat is not configured (ALLOWED_CHAT_ID).",
        "admin_notify_chat_failed": "⚠️ Failed to post to the group chat.",
        "admin_toggle_chat_btn": "💬 Post to chat: {state}",
        "admin_unhide_btn": "👁 Show book",
        "choose_hide": "👻 Choose a book to hide from the list:",
        "choose_notify": "🔔 Choose a book to send a reminder for:",
        "book_hidden": "✅ <b>{title}</b> is now hidden.",
        "book_unhidden": "✅ <b>{title}</b> is now visible.",
        "choose_mark": "📌 Choose a book to mark as discussed:",
        "no_unmark": "📭 No undiscussed books to mark.",
        "ask_discuss_date": "📅 Enter the <b>discussion date</b> (YYYY-MM-DD), or /today to use today:",
        "invalid_date": "⚠️ Invalid date. Use YYYY-MM-DD format (e.g. 2026-03-17):",
        "marked_discussed": "✅ <b>{title}</b> marked as discussed on {date}.",
        "discussed_title": "✅ <b>Discussed Books</b>\n\n",
        "no_discussed": "📭 No books have been discussed yet.",
        "discussed_on": "Discussed on",
        "list_prompt": "📋 <b>List of Books</b>\nShow all books or only those you haven't voted for yet?",
        "list_all_btn": "📚 All books",
        "list_unvoted_btn": "🗳 Unvoted only",
        "score_calc_btn": "📊 How a score is calculated",
        "score_calc_info": "✅ Want: +1 point\n😐 Don't care: +0.5 points\n❌ Don't want: -1 point\nTotal score = sum of all votes (not average).Sorted by this score, then by date added.",
        "settings_title": "⚙️ <b>Settings</b>",
        "settings_notify_label": "Notifications for new books:",
        "settings_notify_on": "🔔 Enabled (10 min delay)",
        "settings_notify_off": "🔕 Disabled",
        "settings_notify_btn": "Toggle Notifications",
        "settings_lang_btn": "🌐 Switch to Russian",
        "notify_optin_prompt": "Would you like to receive notifications (with a 10-minute delay) when others add new books?",
        "notify_optin_yes": "🔔 Yes, notify me",
        "notify_optin_no": "🔕 No, thanks",
        "notify_optin_success": "✅ Settings saved!",
        "new_book_notification": "🆕 <b>New book added!</b>\n(Note: you receive this 10 minutes after it was added)\n\n",
        "new_book_delay_note": "\n\n<i>(Notifications for this book will be sent to others in 10 minutes)</i>",
        "not_member": "⛔ This bot is only for members of the <b>{chat}</b> chat. Please join first.",
        "bot_started": "🚀 <b>Bot is up!</b>",
        "bot_stopped": "🛑 <b>Bot is down.</b>",
        "admin_notify_confirm": "🔔 Voting reminder sent to {count} users.",
        "admin_notify_no_users": "ℹ️ No users to notify (everyone has voted or notifications disabled).",
        "vote_reminder_msg": "👋 <b>Friendly reminder!</b>\nYou haven't voted for some of our top books yet. Take a look and cast your vote:\n\n",
        "last_activity_label": "Last non-admin activity",
        "never": "never",
        "bot_name": "Book Club Bot",
        "card_icon": "📖",
        "subtitle_icon": "✍️",
        "all_voted": "You've voted on all books!",
        "info_msg": (
            "🤖 <b>{bot_name}</b>\n\n"
            "📅 <b>Last update:</b> {last_commit}\n"
            "🔗 <b>Source code:</b> {github_repo}"
        ),
    },
    "ru": {
        "welcome": (
            "📚 <b>Добро пожаловать в Книжный клуб!</b>\n\n"
            "➕ /add — Добавить книгу\n"
            "📋 /list — Список книг\n"
            "🏆 /top — Топ книг\n"
            "⚙️ /settings — Настройки\n"
            "ℹ️ /info — О боте\n"
            "✏️ /edit — Редактировать запись\n"
            "🗑 /delete — Удалить книгу\n"
            "✅ /discussed — Обсуждённые книги\n"
            "🛠 /adminconsole — Админ-панель\n"
            "❓ /help — Показать это сообщение"
        ),
        "lang_set": "🇷🇺 Язык установлен: Русский.",
        "ask_title": "📖 Как называется книга (<b>название</b>)?",
        "ask_author": "✍️ Кто <b>автор</b>?",
        "ask_pages": "📄 Сколько <b>страниц</b> в книге? (введите число)",
        "invalid_pages": "⚠️ Введите корректное число страниц (например, 320):",
        "ask_fiction": "📂 Это <b>художественная</b> или <b>нехудожественная</b> литература?",
        "fiction_btn": "📖 Худ. литература",
        "nonfiction_btn": "📰 Нехуд. литература",
        "ask_review": "🔗 Вставьте <b>ссылку на рецензию</b> (должна начинаться с http:// или https://):",
        "invalid_review": "⚠️ Это не похоже на корректный URL. Вставьте ссылку, начинающуюся с http:// или https://:",
        "ask_desc": "📝 Добавьте <b>описание</b> (или /skip, чтобы пропустить):",
        "book_added": "✅ Книга добавлена!",
        "no_books": "📭 Книг пока нет. Используйте /add, чтобы добавить!",
        "no_undiscussed": "📭 Необсуждённых книг нет — используйте /discussed для просмотра прочитанных.",
        "no_votes": "Голосов пока нет. Используйте /list для голосования!",
        "no_books_edit": "📭 Нет книг для редактирования.",
        "no_books_delete": "📭 Нет книг для удаления.",
        "cancelled": "❌ Отменено.",
        "unexpected_error": "⚠️ Что-то пошло не так с моей стороны. Попробуйте ещё раз — если вы были в середине команды, сначала используйте /cancel.",
        "choose_vote": "📊 Выберите книгу для голосования:",
        "choose_edit": "✏️ Выберите книгу для редактирования:",
        "choose_delete": "🗑 Выберите книгу для удаления:",
        "your_vote": "Ваш текущий голос",
        "none_vote": "—",
        "rate_book": "📊 Голосование: <b>{title}</b>",
        "desc_updated": "✅ Описание обновлено!",
        "top_title": "🏆 <b>Топ книг</b>\nСортировка по общему баллу.\n\n",
        "added_by": "Добавил",
        "added_on": "Добавлено",
        "pages_label": "Страниц",
        "review_label": "Рецензия",
        "cancel_btn": "❌ Отмена",
        "edit_field_prompt": "✏️ <b>{field}</b>\nТекущее значение: <i>{value}</i>\n\nИзменить это поле?",
        "edit_yes_btn": "✏️ Да, изменить",
        "edit_no_btn": "⏭ Пропустить",
        "edit_ask_new": "Отправьте новое значение для <b>{field}</b>:",
        "edit_done": "✅ Книга обновлена!",
        "edit_invalid_pages": "⚠️ Должно быть положительным числом. Отправьте снова:",
        "edit_invalid_url": "⚠️ Должна начинаться с http:// или https://. Отправьте снова:",
        "field_title": "Название",
        "field_author": "Автор",
        "field_pages": "Страниц",
        "field_fiction": "Fiction / Non-fiction",
        "field_review": "Ссылка на рецензию",
        "field_description": "Описание",
        "deleted": "🗑 <b>{title}</b> удалена.",
        "fiction_label": "Fiction",
        "nonfiction_label": "Non-fiction",
        "votes_label": lambda n: (
            f"({n} оценка)"
            if n == 1
            else f"({n} оценки)" if 2 <= n <= 4 else f"({n} оценок)"
        ),
        "want_label": "✅ хочу читать",
        "meh_label": "😐 всё равно",
        "no_label": "❌ не хочу читать",
        "vote_registered": "Ваш голос: {label}",
        "want_btn": "✅ Хочу",
        "meh_btn": "😐 Всё равно",
        "no_btn": "❌ Не хочу",
        "voted_msg": "✅ Голос сохранён для <b>{title}</b>",
        "score_label": "Балл",
        "no_permission": "⛔ Вы можете редактировать или удалять только добавленные вами книги.",
        "no_own_books": "📭 У вас нет книг для редактирования или удаления.",
        "admin_only": "⛔ Эта команда доступна только администраторам.",
        "admin_console_title": "🛠 <b>Админ-панель</b>",
        "admin_mark_btn": "📌 Отметить обсуждённой",
        "admin_hide_btn": "👻 Скрыть книгу",
        "admin_notify_btn": "🔔 Напомнить о голосовании (топ)",
        "admin_notify_one_btn": "🔔 Напомнить об одной книге",
        "admin_notify_chat_btn": "💬 Напомнить в чате (топ)",
        "admin_notify_chat_one_btn": "💬 Напомнить в чате (выбрать книгу)",
        "choose_notify_chat": "💬 Выберите книгу для напоминания о голосовании в общем чате:",
        "vote_reminder_chat": "🔔 <b>Напоминание о голосовании!</b>\n\n",
        "admin_notify_chat_confirm": "💬 Напоминание о голосовании отправлено в общий чат ({count} книг(и)).",
        "admin_notify_chat_no_chat": "ℹ️ Общий чат не настроен (ALLOWED_CHAT_ID).",
        "admin_notify_chat_failed": "⚠️ Не удалось отправить сообщение в общий чат.",
        "admin_toggle_chat_btn": "💬 Писать в чат: {state}",
        "admin_unhide_btn": "👁 Показать книгу",
        "choose_hide": "👻 Выберите книгу, чтобы скрыть её из списка:",
        "choose_notify": "🔔 Выберите книгу для напоминания:",
        "book_hidden": "✅ Книга <b>{title}</b> скрыта.",
        "book_unhidden": "✅ Книга <b>{title}</b> снова видна.",
        "choose_mark": "📌 Выберите книгу для отметки как обсуждённой:",
        "no_unmark": "📭 Нет необсуждённых книг для отметки.",
        "ask_discuss_date": "📅 Введите <b>дату обсуждения</b> (ГГГГ-ММ-ДД) или /today для сегодняшней даты:",
        "invalid_date": "⚠️ Неверный формат даты. Используйте ГГГГ-ММ-ДД (например, 2026-03-17):",
        "marked_discussed": "✅ <b>{title}</b> отмечена как обсуждённая {date}.",
        "discussed_title": "✅ <b>Обсуждённые книги</b>\n\n",
        "no_discussed": "📭 Пока ни одна книга не была обсуждена.",
        "discussed_on": "Обсуждено",
        "list_prompt": "📋 <b>Список книг</b>\nПоказать все книги или только те, за которые вы ещё не голосовали?",
        "list_all_btn": "📚 Все книги",
        "list_unvoted_btn": "🗳 Только без моего голоса",
        "score_calc_btn": "📊 Как рассчитывается балл",
        "score_calc_info": "✅ Хочу: +1 балл\n😐 Всё равно: +0.5 баллов\n❌ Не хочу: -1 балл\n\nСортировка по суммарному баллу, затем по дате добавления.",
        "settings_title": "⚙️ <b>Настройки</b>",
        "settings_notify_label": "Уведомления о новых книгах:",
        "settings_notify_on": "🔔 Включены (задержка 10 мин)",
        "settings_notify_off": "🔕 Выключены",
        "settings_notify_btn": "Переключить уведомления",
        "settings_lang_btn": "🌐 Switch to English",
        "notify_optin_prompt": "Хотите получать уведомления (с задержкой 10 минут), когда другие добавляют новые книги?",
        "notify_optin_yes": "🔔 Да, уведомлять",
        "notify_optin_no": "🔕 Нет, спасибо",
        "notify_optin_success": "✅ Настройки сохранены!",
        "new_book_notification": "🆕 <b>Добавлена новая книга!</b>\n(Примечание: вы получили это через 10 минут после добавления)\n\n",
        "new_book_delay_note": "\n\n<i>(Уведомления об этой книге будут разосланы остальным через 10 минут)</i>",
        "not_member": "⛔ Этот бот только для участников чата <b>{chat}</b>. Пожалуйста, сначала вступите в него.",
        "bot_started": "🚀 <b>Бот запущен!</b>",
        "bot_stopped": "🛑 <b>Бот остановлен.</b>",
        "admin_notify_confirm": "🔔 Напоминание о голосовании отправлено {count} пользователям.",
        "admin_notify_no_users": "ℹ️ Нет пользователей для уведомления (все проголосовали или уведомления отключены).",
        "vote_reminder_msg": "👋 <b>Напоминание!</b>\nВы еще не проголосовали за некоторые популярные книги. Посмотрите и оставьте свой голос:\n\n",
        "last_activity_label": "Последняя активность (не админ)",
        "never": "никогда",
        "bot_name": "Книжный клуб-бот",
        "card_icon": "📖",
        "subtitle_icon": "✍️",
        "all_voted": "Вы проголосовали за все книги!",
        "info_msg": (
            "🤖 <b>{bot_name}</b>\n\n"
            "📅 <b>Последнее обновление:</b> {last_commit}\n"
            "🔗 <b>Исходный код:</b> {github_repo}"
        ),
    },
}

# Per-entity copy overrides (DB columns stay: author, pages, fiction).
ENTITY_STRING_OVERLAYS: dict[str, dict[str, dict[str, TranslationValue]]] = {
    "film": {
        "en": {
            "welcome": (
                "🎬 <b>Welcome to the Film Club Bot!</b>\n\n"
                "➕ /add — Add a film\n"
                "📋 /list — See all films\n"
                "🏆 /top — Top rated films\n"
                "⚙️ /settings — Settings\n"
                "ℹ️ /info — About the bot\n"
                "✏️ /edit — Edit a film entry\n"
                "🗑 /delete — Delete a film\n"
                "✅ /discussed — Films already discussed\n"
                "🛠 /adminconsole — Admin console\n"
                "❓ /help — Show this message"
            ),
            "bot_name": "Film Club Bot",
            "card_icon": "🎬",
            "subtitle_icon": "🎬",
            "ask_title": "🎬 What is the <b>title</b> of the film?",
            "ask_author": "🎬 Who is the <b>director</b>?",
            "ask_pages": "⏱ How long is it (<b>runtime in minutes</b>)? (enter a number)",
            "invalid_pages": "⚠️ Please enter a valid runtime in minutes (e.g. 120):",
            "ask_fiction": "📂 Is it a <b>feature film</b> or a <b>documentary</b>?",
            "fiction_btn": "🎬 Feature",
            "nonfiction_btn": "📽 Documentary",
            "book_added": "✅ Film added!",
            "no_books": "📭 No films yet. Use /add to add one!",
            "no_undiscussed": "📭 No undiscussed films — use /discussed to see past picks.",
            "no_votes": "No votes yet. Use /list to see films and vote inline!",
            "no_books_edit": "📭 No films to edit yet.",
            "no_books_delete": "📭 No films to delete yet.",
            "choose_vote": "📊 Choose a film to vote on:",
            "choose_edit": "✏️ Choose a film to edit:",
            "choose_delete": "🗑 Choose a film to delete:",
            "rate_book": "📊 Vote on <b>{title}</b>",
            "top_title": "🏆 <b>Top Films</b>\nSorted by total score.\n\n",
            "pages_label": "min",
            "edit_done": "✅ Film updated!",
            "edit_invalid_pages": "⚠️ Must be a positive number of minutes. Send again:",
            "field_author": "Director",
            "field_pages": "Runtime (min)",
            "field_fiction": "Feature / Documentary",
            "fiction_label": "Feature",
            "nonfiction_label": "Documentary",
            "want_label": "✅ want to watch",
            "no_label": "❌ don't want to watch",
            "no_permission": "⛔ You can only edit or delete films you added.",
            "no_own_books": "📭 You have no films to edit or delete.",
            "admin_hide_btn": "👻 Hide film",
            "admin_notify_one_btn": "🔔 Send reminder for a specific film",
            "admin_notify_chat_one_btn": "💬 Post reminder to chat (pick film)",
            "choose_notify_chat": "💬 Choose a film to post a voting reminder in the group chat:",
            "admin_unhide_btn": "👁 Show film",
            "choose_hide": "👻 Choose a film to hide from the list:",
            "choose_notify": "🔔 Choose a film to send a reminder for:",
            "choose_mark": "📌 Choose a film to mark as discussed:",
            "no_unmark": "📭 No undiscussed films to mark.",
            "marked_discussed": "✅ <b>{title}</b> marked as discussed on {date}.",
            "discussed_title": "✅ <b>Discussed Films</b>\n\n",
            "no_discussed": "📭 No films have been discussed yet.",
            "list_prompt": "📋 <b>List of Films</b>\nShow all films or only those you haven't voted for yet?",
            "list_all_btn": "🎬 All films",
            "all_voted": "You've voted on all films!",
            "settings_notify_label": "Notifications for new films:",
            "notify_optin_prompt": "Would you like to receive notifications (with a 10-minute delay) when others add new films?",
            "new_book_notification": "🆕 <b>New film added!</b>\n(Note: you receive this 10 minutes after it was added)\n\n",
            "new_book_delay_note": "\n\n<i>(Notifications for this film will be sent to others in 10 minutes)</i>",
            "vote_reminder_msg": "👋 <b>Friendly reminder!</b>\nYou haven't voted for some of our top films yet. Take a look and cast your vote:\n\n",
            "admin_notify_chat_confirm": "💬 Voting reminder posted to the group chat ({count} film(s)).",
        },
        "ru": {
            "welcome": (
                "🎬 <b>Добро пожаловать в Киноклуб!</b>\n\n"
                "➕ /add — Добавить фильм\n"
                "📋 /list — Список фильмов\n"
                "🏆 /top — Топ фильмов\n"
                "⚙️ /settings — Настройки\n"
                "ℹ️ /info — О боте\n"
                "✏️ /edit — Редактировать запись\n"
                "🗑 /delete — Удалить фильм\n"
                "✅ /discussed — Обсуждённые фильмы\n"
                "🛠 /adminconsole — Админ-панель\n"
                "❓ /help — Показать это сообщение"
            ),
            "bot_name": "Киноклуб-бот",
            "card_icon": "🎬",
            "subtitle_icon": "🎬",
            "ask_title": "🎬 Как называется <b>фильм</b> (название)?",
            "ask_author": "🎬 Кто <b>режиссёр</b>?",
            "ask_pages": "⏱ Сколько <b>минут</b> длится фильм? (введите число)",
            "invalid_pages": "⚠️ Введите корректную длительность в минутах (например, 120):",
            "ask_fiction": "📂 Это <b>художественный фильм</b> или <b>документальный</b>?",
            "fiction_btn": "🎬 Худ. фильм",
            "nonfiction_btn": "📽 Документальный",
            "book_added": "✅ Фильм добавлен!",
            "no_books": "📭 Фильмов пока нет. Используйте /add, чтобы добавить!",
            "no_undiscussed": "📭 Необсуждённых фильмов нет — используйте /discussed для архива.",
            "no_votes": "Голосов пока нет. Используйте /list для голосования!",
            "no_books_edit": "📭 Нет фильмов для редактирования.",
            "no_books_delete": "📭 Нет фильмов для удаления.",
            "choose_vote": "📊 Выберите фильм для голосования:",
            "choose_edit": "✏️ Выберите фильм для редактирования:",
            "choose_delete": "🗑 Выберите фильм для удаления:",
            "rate_book": "📊 Голосование: <b>{title}</b>",
            "top_title": "🏆 <b>Топ фильмов</b>\nСортировка по общему баллу.\n\n",
            "pages_label": "мин",
            "edit_done": "✅ Фильм обновлён!",
            "edit_invalid_pages": "⚠️ Должно быть положительное число минут. Отправьте снова:",
            "field_author": "Режиссёр",
            "field_pages": "Длительность (мин)",
            "field_fiction": "Худ. / документальный",
            "fiction_label": "Худ. фильм",
            "nonfiction_label": "Документальный",
            "want_label": "✅ хочу смотреть",
            "no_label": "❌ не хочу смотреть",
            "no_permission": "⛔ Вы можете редактировать или удалять только добавленные вами фильмы.",
            "no_own_books": "📭 У вас нет фильмов для редактирования или удаления.",
            "admin_hide_btn": "👻 Скрыть фильм",
            "admin_notify_one_btn": "🔔 Напомнить об одном фильме",
            "admin_notify_chat_one_btn": "💬 Напомнить в чате (выбрать фильм)",
            "choose_notify_chat": "💬 Выберите фильм для напоминания о голосовании в общем чате:",
            "admin_unhide_btn": "👁 Показать фильм",
            "choose_hide": "👻 Выберите фильм, чтобы скрыть его из списка:",
            "choose_notify": "🔔 Выберите фильм для напоминания:",
            "choose_mark": "📌 Выберите фильм для отметки как обсуждённого:",
            "no_unmark": "📭 Нет необсуждённых фильмов для отметки.",
            "marked_discussed": "✅ <b>{title}</b> отмечен как обсуждённый {date}.",
            "discussed_title": "✅ <b>Обсуждённые фильмы</b>\n\n",
            "no_discussed": "📭 Пока ни один фильм не был обсуждён.",
            "list_prompt": "📋 <b>Список фильмов</b>\nПоказать все фильмы или только те, за которые вы ещё не голосовали?",
            "list_all_btn": "🎬 Все фильмы",
            "all_voted": "Вы проголосовали за все фильмы!",
            "settings_notify_label": "Уведомления о новых фильмах:",
            "notify_optin_prompt": "Хотите получать уведомления (с задержкой 10 минут), когда другие добавляют новые фильмы?",
            "new_book_notification": "🆕 <b>Добавлен новый фильм!</b>\n(Примечание: вы получили это через 10 минут после добавления)\n\n",
            "new_book_delay_note": "\n\n<i>(Уведомления об этом фильме будут разосланы остальным через 10 минут)</i>",
            "vote_reminder_msg": "👋 <b>Напоминание!</b>\nВы ещё не проголосовали за некоторые популярные фильмы. Посмотрите и оставьте свой голос:\n\n",
            "admin_notify_chat_confirm": "💬 Напоминание о голосовании отправлено в общий чат ({count} фильм(ов)).",
        },
    },
}

_COMMAND_DESC_OVERLAYS: dict[str, dict[str, dict[str, str]]] = {
    "film": {
        "en": {
            "add": "➕ Add a film",
            "list": "📋 List films & vote inline",
            "top": "🏆 Top rated films",
            "discussed": "✅ Films already discussed",
            "edit": "✏️ Edit a film entry",
            "delete": "🗑 Delete a film",
        },
        "ru": {
            "add": "➕ Добавить фильм",
            "list": "📋 Список фильмов и голосование",
            "top": "🏆 Топ фильмов",
            "discussed": "✅ Обсуждённые фильмы",
            "edit": "✏️ Редактировать фильм",
            "delete": "🗑 Удалить фильм",
        },
    },
}


def _apply_entity_string_overlays(entity: str) -> None:
    for lang, keys in ENTITY_STRING_OVERLAYS.get(entity, {}).items():
        T[lang].update(keys)


_apply_entity_string_overlays(CLUB_ENTITY)

PM = "HTML"


IMPORTED_USER_ID = 0  # sentinel for books imported without a real user_id


def can_modify(user_id: int, book: BookLike, username: str | None = None) -> bool:
    """Admin always wins. For imported books (added_by=0), match by @username."""
    if user_id in ADMIN_IDS:
        return True
    if book["added_by"] == IMPORTED_USER_ID:
        # Imported book — allow if the caller's @username matches
        stored = book["added_by_username"]
        clean = (username or "").lstrip("@")
        return bool(clean and stored and clean.lower() == stored.lower())
    return bool(user_id == book["added_by"])


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_lang(ctx: ContextTypes.DEFAULT_TYPE) -> str:
    return str(ctx.user_data.get("lang", "ru"))


def tr(ctx_or_lang: ContextTypes.DEFAULT_TYPE | str, key: str, **kwargs: Any) -> str:
    lang = ctx_or_lang if isinstance(ctx_or_lang, str) else get_lang(ctx_or_lang)
    val = T[lang][key]
    if callable(val):
        result = val(**kwargs)
        return str(result)
    return val.format(**kwargs) if kwargs else str(val)


def s(lang: str, key: str) -> str:
    """Plain-string translation (not callable)."""
    val = T[lang][key]
    if not isinstance(val, str):
        raise TypeError(f"translation {key!r} is not a plain string")
    return val


_VOTE_LABEL_KEYS = {1: "want_label", 0: "meh_label", -1: "no_label"}


def vote_label_text(lang: str, score: int | None) -> str:
    if score not in _VOTE_LABEL_KEYS:
        raise ValueError(f"invalid vote score: {score!r}")
    return s(lang, _VOTE_LABEL_KEYS[score])


def require_book(book_id: int) -> sqlite3.Row:
    book = db_get_book(book_id)
    if book is None:
        raise RuntimeError(f"book {book_id} not found")
    return book


# ── Database ───────────────────────────────────────────────────────────────────
def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL,
                author        TEXT NOT NULL,
                pages         INTEGER NOT NULL DEFAULT 0,
                fiction       INTEGER NOT NULL DEFAULT 1,
                review_link   TEXT NOT NULL DEFAULT '',
                description   TEXT DEFAULT '',
                hidden        INTEGER NOT NULL DEFAULT 0,
                discussed     INTEGER NOT NULL DEFAULT 0,
                discussed_at  TEXT DEFAULT NULL,
                added_by      INTEGER NOT NULL,
                added_by_name     TEXT NOT NULL,
                added_by_username TEXT DEFAULT NULL,
                added_at          TEXT NOT NULL
            )
        """)
        # Migrate existing DB: add book columns if missing
        for col, definition in [
            ("pages", "INTEGER NOT NULL DEFAULT 0"),
            ("fiction", "INTEGER NOT NULL DEFAULT 1"),
            ("review_link", "TEXT NOT NULL DEFAULT ''"),
            ("hidden", "INTEGER NOT NULL DEFAULT 0"),
            ("discussed", "INTEGER NOT NULL DEFAULT 0"),
            ("discussed_at", "TEXT DEFAULT NULL"),
            ("added_by_username", "TEXT DEFAULT NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE books ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass

        # Migrate votes table: rename stars→score, clear old 1-5 data
        try:
            conn.execute("ALTER TABLE votes RENAME COLUMN stars TO score")
            conn.execute("DELETE FROM votes WHERE score NOT IN (-1, 0, 1)")
        except sqlite3.OperationalError:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                score   INTEGER NOT NULL,
                PRIMARY KEY (user_id, book_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id      INTEGER NOT NULL,
                setting_key  TEXT NOT NULL,
                setting_val  INTEGER NOT NULL,
                PRIMARY KEY (user_id, setting_key)
            )
        """)
        conn.commit()


def db_add_book(
    title: str,
    author: str,
    pages: int,
    fiction: bool,
    review_link: str,
    description: str,
    user_id: int,
    user_name: str,
    username: str | None = None,
) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(
            """INSERT INTO books
               (title, author, pages, fiction, review_link, description,
                added_by, added_by_name, added_by_username, added_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                title,
                author,
                pages,
                int(fiction),
                review_link,
                description,
                user_id,
                user_name,
                username,
                datetime.now().strftime("%Y-%m-%d"),
            ),
        )
        return cur.lastrowid


def _books_query(
    extra_where: str = "",
    order: str = "avg_score DESC, vote_count DESC, b.added_at DESC",
) -> str:
    # Note: avg_score is actually the SUM of weighted scores:
    # 1.0 for 'want', 0.5 for 'don''t care', -1.0 for 'don''t want'
    return f"""
        SELECT b.*,
               COALESCE(
                    SUM(
                        CASE    
                            WHEN v.score = 1  THEN 1
                            WHEN v.score = 0  THEN 0.5
                            WHEN v.score = -1 THEN -1
                        END
                    ), 
                0) AS avg_score,
               COUNT(v.user_id)                                    AS vote_count,
               COALESCE(SUM(CASE WHEN v.score=1  THEN 1 ELSE 0 END),0) AS votes_yes,
               COALESCE(SUM(CASE WHEN v.score=0  THEN 1 ELSE 0 END),0) AS votes_meh,
               COALESCE(SUM(CASE WHEN v.score=-1 THEN 1 ELSE 0 END),0) AS votes_no
        FROM books b
        LEFT JOIN votes v ON b.id = v.book_id
        {extra_where}
        GROUP BY b.id
        ORDER BY {order}
    """


def db_get_books(
    discussed: bool = False,
    user_id_unvoted: int | None = None,
    include_hidden: bool = False,
) -> list[sqlite3.Row]:
    """Return books. discussed=False → undiscussed, discussed=True → discussed.
    If user_id_unvoted is provided, only return books that this user has NOT voted for yet.
    """
    flag = 1 if discussed else 0
    where = "WHERE b.discussed = ?"
    params = [flag]
    if not include_hidden:
        where += " AND b.hidden = 0"
    if user_id_unvoted:
        where += " AND b.id NOT IN (SELECT book_id FROM votes WHERE user_id = ?)"
        params.append(user_id_unvoted)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn.execute(
            _books_query(
                where,
                (
                    "b.discussed_at DESC"
                    if discussed
                    else "avg_score DESC, vote_count DESC, b.added_at DESC"
                ),
            ),
            tuple(params),
        ).fetchall()


def db_get_book(book_id: int) -> sqlite3.Row | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return cast(
            sqlite3.Row | None,
            conn.execute(_books_query("WHERE b.id = ?"), (book_id,)).fetchone(),
        )


def db_update_book_field(book_id: int, field: str, value: Any) -> None:
    """Update a single whitelisted field."""
    allowed = {"title", "author", "pages", "fiction", "review_link", "description"}
    if field not in allowed:
        raise ValueError(f"Field {field!r} not editable")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Field name is whitelisted above, so this is safe from injection.
        conn.execute(f"UPDATE books SET {field}=? WHERE id=?", (value, book_id))
        conn.commit()


def db_mark_discussed(book_id: int, date_str: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "UPDATE books SET discussed=1, discussed_at=? WHERE id=?",
            (date_str, book_id),
        )


def db_toggle_hidden(book_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "UPDATE books SET hidden = 1 - hidden WHERE id = ?",
            (book_id,),
        )
        conn.commit()


def db_delete_book(book_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        conn.commit()


def db_cast_vote(user_id: int, book_id: int, score: int) -> None:
    """score: -1 = don't want, 0 = don't care, 1 = want to read"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO votes (user_id,book_id,score) VALUES (?,?,?) "
            "ON CONFLICT(user_id,book_id) DO UPDATE SET score=excluded.score",
            (user_id, book_id, score),
        )
        conn.commit()


def db_get_user_vote(user_id: int, book_id: int) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT score FROM votes WHERE user_id=? AND book_id=?", (user_id, book_id)
        ).fetchone()
        return row[0] if row else None


def db_get_user_setting(user_id: int, key: str, default: int = -1) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT setting_val FROM user_settings WHERE user_id=? AND setting_key=?",
            (user_id, key),
        ).fetchone()
        return row[0] if row is not None else default


def db_set_user_setting(user_id: int, key: str, value: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, setting_key, setting_val) VALUES (?,?,?) "
            "ON CONFLICT(user_id, setting_key) DO UPDATE SET setting_val=excluded.setting_val",
            (user_id, key, value),
        )
        conn.commit()


def db_get_users_with_setting(key: str, value: int) -> list[int]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id FROM user_settings WHERE setting_key=? AND setting_val=?",
            (key, value),
        ).fetchall()
        return [r[0] for r in rows]


ADMIN_USER_ID = 0


def db_get_admin_setting(key: str, default: int = 0) -> int:
    return db_get_user_setting(ADMIN_USER_ID, key, default)


def db_set_admin_setting(key: str, value: int) -> None:
    db_set_user_setting(ADMIN_USER_ID, key, value)


# ── Formatting ─────────────────────────────────────────────────────────────────
def format_user(book: BookLike) -> str:
    """Return @username if available, otherwise fall back to display name."""
    username = book["added_by_username"]
    if username:
        return f"@{h(username)}"
    return h(book["added_by_name"] or "unknown")


def h(text: str) -> str:
    # `"` must be escaped too: h() is used inside href="..." attributes, where a
    # raw quote breaks out of the attribute and makes Telegram reject the whole
    # message — which would take down /list for everyone, not just the author.
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt_dt_utc(dt: datetime) -> str:
    """Format a datetime as 'YYYY-MM-DD HH:MM:SS UTC±HH:MM'.

    Naive datetimes are assumed to be in the server's local timezone. The
    explicit UTC offset lets admins reading this from any timezone interpret
    the value without having to know where the server is.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attach the server's local tz
    off = dt.strftime("%z")  # +0200 / -0500 / +0000
    return dt.strftime("%Y-%m-%d %H:%M:%S") + f" UTC{off[:3]}:{off[3:5]}"


SCORE_EMOJI = {1: "✅", 0: "😐", -1: "❌", None: "—"}


def score_display(book: BookLike, lang: str = "en") -> str:
    """Show vote tally: ✅12  😐3  ❌2  (N votes)"""
    yes = book["votes_yes"]
    meh = book["votes_meh"]
    no = book["votes_no"]
    total = book["vote_count"]
    if total == 0:
        votes_label = T[lang]["votes_label"]
        if not callable(votes_label):
            raise TypeError("votes_label must be callable")
        return str(votes_label(0))
    votes_label = T[lang]["votes_label"]
    if not callable(votes_label):
        raise TypeError("votes_label must be callable")
    return f"✅ {yes}  😐 {meh}  ❌ {no}  {votes_label(total)}"


def book_card(book: BookLike, lang: str = "en", user_vote: int | None = None) -> str:
    fiction_label = (
        s(lang, "fiction_label") if book["fiction"] else s(lang, "nonfiction_label")
    )
    lines = [
        f"{s(lang, 'card_icon')} <b>{h(book['title'])}</b>",
        f"{s(lang, 'subtitle_icon')} {h(book['author'])}",
        f"📂 {h(fiction_label)}  •  📄 {h(str(book['pages']))} {h(s(lang, 'pages_label'))}",
        score_display(book, lang),
    ]
    if user_vote is not None:
        vote_label = vote_label_text(lang, user_vote)
        lines[-1] += f"  <i>({h(s(lang, 'your_vote'))}: {h(vote_label)})</i>"
    if book["review_link"]:
        lines.append(
            f'🔗 <a href="{h(book["review_link"])}">{h(s(lang, "review_label"))}</a>'
        )
    if book["description"]:
        lines += ["", f"<i>{h(book['description'])}</i>"]
    meta = (
        f"<i>{h(s(lang, 'added_by'))}: {h(format_user(book))}"
        f"  •  {h(s(lang, 'added_on'))}: {h(book['added_at'])}"
    )
    if book["discussed"] and book["discussed_at"]:
        meta += f"  •  ✅ {h(s(lang, 'discussed_on'))}: {h(book['discussed_at'])}"
    meta += "</i>"
    lines += ["", meta]
    return "\n".join(lines)


def books_keyboard(
    books: Sequence[BookLike], prefix: str, cancel_label: str
) -> InlineKeyboardMarkup:
    buttons = []
    for b in books:
        label = f"{b['title']} — {b['author']}"
        if len(label) > 48:
            label = label[:45] + "…"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"{prefix}:{b['id']}")]
        )
    buttons.append(
        [InlineKeyboardButton(cancel_label, callback_data=f"{prefix}:cancel")]
    )
    return InlineKeyboardMarkup(buttons)


def fiction_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(s(lang, "fiction_btn"), callback_data="fiction:1"),
                InlineKeyboardButton(
                    s(lang, "nonfiction_btn"), callback_data="fiction:0"
                ),
            ]
        ]
    )


def books_top_n(books: Sequence[BookLike], n: int = 5) -> list[BookLike]:
    """First n books by rank, including all ties at the nth position."""
    top: list[BookLike] = []
    for i, book in enumerate(books):
        if i < n:
            top.append(book)
        elif n > 0:
            nth = books[n - 1]
            if (
                book["avg_score"] == nth["avg_score"]
                and book["vote_count"] == nth["vote_count"]
            ):
                top.append(book)
            else:
                break
        else:
            break
    return top


async def post_book_voting_to_group_chat(
    bot: Bot, book: BookLike, *, intro_key: str
) -> bool:
    """Post a book card with inline vote buttons to the configured group chat."""
    if not ALLOWED_CHAT_ID:
        return False
    try:
        chat_lang = CHAT_LANG
        text = tr(chat_lang, intro_key) + book_card(book, chat_lang)
        await bot.send_message(
            chat_id=ALLOWED_CHAT_ID,
            text=text,
            parse_mode=PM,
            reply_markup=score_keyboard(book["id"], chat_lang),
        )
        return True
    except Exception as e:
        logger.warning(
            "post_book_voting_to_group_chat: failed to post book %s to chat %s: %s",
            book["id"],
            ALLOWED_CHAT_ID,
            e,
        )
        return False


def score_keyboard(
    book_id: int, lang: str, current: int | None = None
) -> InlineKeyboardMarkup:
    """Compact 3-button vote row to attach directly to book cards."""
    options = [
        (1, s(lang, "want_btn")),
        (0, s(lang, "meh_btn")),
        (-1, s(lang, "no_btn")),
    ]
    row = [
        InlineKeyboardButton(
            label + (" ✓" if current == score else ""),
            callback_data=f"vote_cast:{book_id}:{score}",
        )
        for score, label in options
    ]
    return InlineKeyboardMarkup([row])


def is_valid_url(text: str) -> bool:
    if not (text.startswith("http://") or text.startswith("https://")):
        return False
    # Reject characters that cannot legally appear unencoded in a URL. They are
    # the ones that would otherwise corrupt the surrounding HTML anchor.
    if any(c in text for c in '"<>') or any(c.isspace() for c in text):
        return False
    # Require something after the scheme.
    return bool(text.split("://", 1)[1])


def parse_date(text: str) -> str | None:
    """Return date string if valid YYYY-MM-DD, DD.MM.YYYY, or DD/MM/YYYY, else None."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ── Handlers ───────────────────────────────────────────────────────────────────
# ── Per-language command menus ─────────────────────────────────────────────────
COMMANDS = {
    "en": [
        BotCommand("add", "➕ Add a book"),
        BotCommand("list", "📋 List books & vote inline"),
        BotCommand("top", "🏆 Top rated books"),
        BotCommand("settings", "⚙️ Settings"),
        BotCommand("discussed", "✅ Books already discussed"),
        BotCommand("edit", "✏️ Edit a book entry"),
        BotCommand("delete", "🗑 Delete a book"),
        BotCommand("adminconsole", "🛠 Admin console"),
        BotCommand("info", "ℹ️ About the bot"),
        BotCommand("help", "❓ Show help"),
        BotCommand("cancel", "❌ Cancel current action"),
    ],
    "ru": [
        BotCommand("add", "➕ Добавить книгу"),
        BotCommand("list", "📋 Список книг и голосование"),
        BotCommand("top", "🏆 Топ книг"),
        BotCommand("settings", "⚙️ Настройки"),
        BotCommand("discussed", "✅ Обсуждённые книги"),
        BotCommand("edit", "✏️ Редактировать запись"),
        BotCommand("delete", "🗑 Удалить книгу"),
        BotCommand("adminconsole", "🛠 Админ-панель"),
        BotCommand("info", "ℹ️ О боте"),
        BotCommand("help", "❓ Показать помощь"),
        BotCommand("cancel", "❌ Отменить действие"),
    ],
}


def _apply_entity_command_overlays(entity: str) -> None:
    cmd_overlay = _COMMAND_DESC_OVERLAYS.get(entity, {})
    for lang, by_name in cmd_overlay.items():
        COMMANDS[lang] = [
            BotCommand(c.command, by_name.get(c.command, c.description))
            for c in COMMANDS[lang]
        ]


_apply_entity_command_overlays(CLUB_ENTITY)


async def set_user_commands(bot: Bot, update: Update, lang: str) -> None:
    """Set the command menu for a specific user in their chosen language.
    Uses BotCommandScopeChatMember for groups, BotCommandScopeChat for private."""
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    chat_id = chat.id
    user_id = user.id
    try:
        if chat.type == "private":
            scope: BotCommandScopeChat | BotCommandScopeChatMember = (
                BotCommandScopeChat(chat_id=chat_id)
            )
            await bot.delete_my_commands(scope=scope)
            await bot.set_my_commands(COMMANDS[lang], scope=scope)
        else:
            scope = BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
            await bot.delete_my_commands(scope=scope)
            await bot.set_my_commands(COMMANDS[lang], scope=scope)
    except Exception as e:
        logger.warning(f"Could not set commands for user {user_id}: {e}")


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    notify = db_get_user_setting(user_id, "notify_new_books")

    # -1 means not set, we'll treat it as Off (0) for the UI if they just run /settings
    # but the logic for /list will still trigger the opt-in if it's -1.
    val_str = tr(ctx, "settings_notify_on" if notify == 1 else "settings_notify_off")

    text = (
        f"{tr(ctx, 'settings_title')}\n\n{tr(ctx, 'settings_notify_label')} {val_str}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(ctx, "settings_notify_btn"),
                    callback_data="settings:toggle_notify",
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "settings_lang_btn"), callback_data="settings:toggle_lang"
                )
            ],
        ]
    )
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=PM)


async def settings_choice_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split(":")

    if data[1] == "toggle_notify":
        await query.answer()
        current = db_get_user_setting(user_id, "notify_new_books")
        new_val = 1 if current <= 0 else 0
        db_set_user_setting(user_id, "notify_new_books", new_val)

        val_str = tr(
            ctx, "settings_notify_on" if new_val == 1 else "settings_notify_off"
        )
        text = f"{tr(ctx, 'settings_title')}\n\n{tr(ctx, 'settings_notify_label')} {val_str}"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr(ctx, "settings_notify_btn"),
                        callback_data="settings:toggle_notify",
                    )
                ],
                [
                    InlineKeyboardButton(
                        tr(ctx, "settings_lang_btn"),
                        callback_data="settings:toggle_lang",
                    )
                ],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=PM)
    elif data[1] == "toggle_lang":
        new_lang = "ru" if get_lang(ctx) == "en" else "en"
        ctx.user_data["lang"] = new_lang
        await set_user_commands(ctx.bot, update, new_lang)
        await query.answer(tr(ctx, "lang_set"))

        notify = db_get_user_setting(user_id, "notify_new_books")
        val_str = tr(
            ctx, "settings_notify_on" if notify == 1 else "settings_notify_off"
        )
        text = f"{tr(ctx, 'settings_title')}\n\n{tr(ctx, 'settings_notify_label')} {val_str}"
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr(ctx, "settings_notify_btn"),
                        callback_data="settings:toggle_notify",
                    )
                ],
                [
                    InlineKeyboardButton(
                        tr(ctx, "settings_lang_btn"),
                        callback_data="settings:toggle_lang",
                    )
                ],
            ]
        )
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=PM)
    elif data[1] == "optin":
        val = int(data[2])
        db_set_user_setting(user_id, "notify_new_books", val)
        await query.answer(tr(ctx, "notify_optin_success"))
        # After choosing, we continue with the list if possible?
        # Actually, the opt-in was triggered by /list.
        # Let's just say "Settings saved" and let them run /list again or just finish.
        # But the prompt said "ask... first time one runs list command".
        # Better to show the list after they choose.
        await list_choice_cb(update, ctx)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await set_user_commands(ctx.bot, update, get_lang(ctx))
    await update.message.reply_text(tr(ctx, "welcome"), parse_mode=PM)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    import os
    import subprocess

    last_commit = None
    # 1. Try git log — commit time as a Unix timestamp, so it goes through the
    #    same formatter as everything else (server-local time + UTC offset)
    #    instead of git's own zone-dependent rendering.
    try:
        if os.path.exists(".git"):
            ct = (
                subprocess.check_output(
                    ["git", "log", "-1", "--format=%ct"], stderr=subprocess.DEVNULL
                )
                .decode("utf-8")
                .strip()
            )
            last_commit = fmt_dt_utc(datetime.fromtimestamp(int(ct)))
    except Exception as e:
        logger.warning(f"Could not get last commit via git: {e}")

    # 2. Fallback to file mtime
    if not last_commit:
        try:
            mtime = os.path.getmtime(__file__)
            last_commit = fmt_dt_utc(datetime.fromtimestamp(mtime))
        except Exception as e:
            logger.warning(f"Could not get file mtime: {e}")
            last_commit = "unknown"

    text = tr(
        ctx,
        "info_msg",
        bot_name=s(get_lang(ctx), "bot_name"),
        last_commit=last_commit,
        github_repo=GITHUB_REPO,
    )
    await update.message.reply_text(text, parse_mode=PM, disable_web_page_preview=True)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(tr(ctx, "list_all_btn"), callback_data="list:all"),
                InlineKeyboardButton(
                    tr(ctx, "list_unvoted_btn"), callback_data="list:unvoted"
                ),
            ]
        ]
    )
    await update.message.reply_text(
        tr(ctx, "list_prompt"), reply_markup=keyboard, parse_mode=PM
    )


async def list_choice_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    # We might be called from settings_choice_cb, so query might be None-ish or already answered
    if query.data.startswith("settings:optin:"):
        # We need to recover the original list choice if we want to be seamless.
        # But for simplicity, let's just show 'all' if they just opted in,
        # or we could have stored it in user_data.
        choice = ctx.user_data.get("pending_list_choice", "all")
        user_id = query.from_user.id
        # We don't call query.answer() here because it was already answered in settings_choice_cb
    else:
        await query.answer()
        user_id = query.from_user.id
        _, choice = query.data.split(":")

    # Check for notification opt-in
    if db_get_user_setting(user_id, "notify_new_books") == -1:
        ctx.user_data["pending_list_choice"] = choice
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr(ctx, "notify_optin_yes"), callback_data="settings:optin:1"
                    )
                ],
                [
                    InlineKeyboardButton(
                        tr(ctx, "notify_optin_no"), callback_data="settings:optin:0"
                    )
                ],
            ]
        )
        await query.edit_message_text(
            tr(ctx, "notify_optin_prompt"), reply_markup=keyboard, parse_mode=PM
        )
        return

    lang = get_lang(ctx)

    user_id_unvoted = user_id if choice == "unvoted" else None
    books = db_get_books(discussed=False, user_id_unvoted=user_id_unvoted)

    if not books:
        if choice == "unvoted":
            # Check if there are ANY books at all
            all_undiscussed = db_get_books(discussed=False)
            if not all_undiscussed:
                text = tr(ctx, "no_undiscussed")
            else:
                text = "✅ " + tr(ctx, "all_voted")
        else:
            text = tr(ctx, "no_undiscussed")

        try:
            await query.edit_message_text(text, parse_mode=PM)
        except Exception as e:
            if "Message to edit not found" in str(e):
                await ctx.bot.send_message(
                    chat_id=update.effective_chat.id, text=text, parse_mode=PM
                )
            else:
                raise
        return

    # Delete the prompt message
    try:
        await query.delete_message()
    except Exception as e:
        if "Message to delete not found" in str(e):
            pass
        else:
            raise

    for book in books:
        uv = db_get_user_vote(user_id, book["id"])
        try:
            await ctx.bot.send_message(
                chat_id=update.effective_chat.id,
                text=book_card(book, lang, user_vote=uv),
                parse_mode=PM,
                reply_markup=score_keyboard(book["id"], lang, uv),
            )
        except Exception as e:
            # Never let one malformed book (e.g. a bad review link) abort the
            # whole list for the user.
            logger.warning(f"list_choice_cb: failed to send book {book['id']}: {e}")


async def cmd_discussed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(ctx)
    books = db_get_books(discussed=True)
    if not books:
        await update.message.reply_text(tr(ctx, "no_discussed"), parse_mode=PM)
        return
    text = tr(ctx, "discussed_title")
    user_id = update.effective_user.id
    await update.message.reply_text(text, parse_mode=PM)
    for book in books:
        uv = db_get_user_vote(user_id, book["id"])
        await update.message.reply_text(
            book_card(book, lang, user_vote=uv), parse_mode=PM
        )


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(ctx)
    books = db_get_books(discussed=False)
    if not books:
        await update.message.reply_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
        return

    # Show top 5, but if there's a tie for the 5th place, show all tied books.
    # Sorting is already done in db_get_books by (avg_score DESC, vote_count DESC, added_at DESC)
    top_books = books_top_n(books)

    lines = [tr(ctx, "top_title")]
    for i, book in enumerate(top_books, 1):
        fiction_label = (
            s(lang, "fiction_label") if book["fiction"] else s(lang, "nonfiction_label")
        )
        score_val = book["avg_score"]
        score_fmt = f"{score_val:g}"
        lines.append(
            f"{i}. <b>{h(book['title'])}</b> — {h(book['author'])}\n"
            f"   {h(fiction_label)}  •  {h(str(book['pages']))} {h(s(lang, 'pages_label'))}  •  <b>{h(s(lang, 'score_label'))}: {score_fmt}</b>\n"
            f"   {score_display(book, lang)}"
        )

    # Send as one message; if it exceeds Telegram's limit split into chunks
    MAX = 4000
    message = "\n\n".join(lines)
    if len(message) <= MAX:
        await update.message.reply_text(message, parse_mode=PM)
    else:
        chunk = ""
        for line in lines:
            candidate = (chunk + "\n\n" + line).lstrip("\n")
            if len(candidate) > MAX:
                await update.message.reply_text(chunk, parse_mode=PM)
                chunk = line
            else:
                chunk = candidate
        if chunk:
            await update.message.reply_text(chunk, parse_mode=PM)

    # Add "How a score is calculated" button
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(ctx, "score_calc_btn"), callback_data="score_calc_info"
                )
            ]
        ]
    )
    await update.message.reply_text(
        "---",  # Visual separator or just a small text
        reply_markup=reply_markup,
        parse_mode=PM,
    )


async def score_calc_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer(text=tr(ctx, "score_calc_info"), show_alert=True)


# ── /add conversation ──────────────────────────────────────────────────────────
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"] = {}
    await update.message.reply_text(tr(ctx, "ask_title"), parse_mode=PM)
    return ADDING_TITLE


async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"]["title"] = update.message.text.strip()
    await update.message.reply_text(tr(ctx, "ask_author"), parse_mode=PM)
    return ADDING_AUTHOR


async def add_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"]["author"] = update.message.text.strip()
    await update.message.reply_text(tr(ctx, "ask_pages"), parse_mode=PM)
    return ADDING_PAGES


async def add_pages(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text(tr(ctx, "invalid_pages"), parse_mode=PM)
        return ADDING_PAGES
    ctx.user_data["new_book"]["pages"] = int(text)
    await update.message.reply_text(
        tr(ctx, "ask_fiction"),
        reply_markup=fiction_keyboard(get_lang(ctx)),
        parse_mode=PM,
    )
    return ADDING_FICTION


async def add_fiction_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, value = query.data.split(":")
    ctx.user_data["new_book"]["fiction"] = value == "1"
    await query.edit_message_text(tr(ctx, "ask_review"), parse_mode=PM)
    return ADDING_REVIEW


async def add_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not is_valid_url(text):
        await update.message.reply_text(tr(ctx, "invalid_review"), parse_mode=PM)
        return ADDING_REVIEW
    ctx.user_data["new_book"]["review_link"] = text
    await update.message.reply_text(tr(ctx, "ask_desc"), parse_mode=PM)
    return ADDING_DESCRIPTION


async def add_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_lang(ctx)
    text = update.message.text.strip() if update.message and update.message.text else ""
    desc = "" if text == "/skip" else text

    if ctx.user_data is None or "new_book" not in ctx.user_data:
        # Should not happen in normal conversation, but could if user sends message after timeout
        logger.warning(
            f"User {update.effective_user.id} tried to add description but 'new_book' is missing."
        )
        await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END

    nb = ctx.user_data["new_book"]
    user = update.effective_user
    book_id = db_add_book(
        nb["title"],
        nb["author"],
        nb["pages"],
        nb["fiction"],
        nb["review_link"],
        desc,
        user.id,
        user.full_name,
        user.username,
    )
    if book_id is None:
        raise RuntimeError("db_add_book did not return a book id")
    book = db_get_book(book_id)
    if book is None:
        raise RuntimeError(f"book {book_id} missing immediately after insert")

    # Mention the 10-minute delay in the confirmation message
    confirm_text = f"{tr(ctx, 'book_added')}\n\n{book_card(book, lang)}{tr(ctx, 'new_book_delay_note')}"

    await update.message.reply_text(confirm_text, parse_mode=PM)
    ctx.user_data.pop("new_book", None)

    # Schedule notifications for others
    if ctx.job_queue:
        ctx.job_queue.run_once(
            notify_new_book_job,
            when=600,  # 10 minutes
            data={"book_id": book_id, "adder_id": user.id},
            name=f"notify_book_{book_id}",
        )
    else:
        logger.error(
            "JobQueue is None — notifications will not be sent.\n"
            'Fix: pip install "python-telegram-bot[job-queue]"\n'
            "Then restart the bot."
        )

    return ConversationHandler.END


async def notify_new_book_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Fired 10 minutes after a book is added. Sends a card to all opted-in users."""
    book_id = ctx.job.data["book_id"]
    adder_id = ctx.job.data["adder_id"]

    book = db_get_book(book_id)
    if not book:
        logger.info(f"notify_new_book_job: book {book_id} no longer exists, skipping.")
        return
    if book["discussed"]:
        logger.info(f"notify_new_book_job: book {book_id} already discussed, skipping.")
        return
    if book["hidden"]:
        logger.info(f"notify_new_book_job: book {book_id} was hidden, skipping.")
        return

    user_ids = db_get_users_with_setting("notify_new_books", 1)
    logger.info(
        f"notify_new_book_job: notifying {len(user_ids)} user(s) about book {book_id}."
    )

    sent = 0
    for user_id in user_ids:
        if user_id == adder_id:
            continue
        # Resolve language from persistence; fall back to Russian
        user_data = ctx.application.user_data.get(user_id, {})
        lang = user_data.get("lang", "ru")
        try:
            uv = db_get_user_vote(user_id, book_id)
            text = tr(lang, "new_book_notification") + book_card(
                book, lang, user_vote=uv
            )
            await ctx.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=PM,
                reply_markup=score_keyboard(book_id, lang, uv),
            )
            sent += 1
        except Exception as e:
            logger.warning(f"notify_new_book_job: failed to notify user {user_id}: {e}")

    if ALLOWED_CHAT_ID and db_get_admin_setting("post_new_books_to_chat", 0):
        if await post_book_voting_to_group_chat(
            ctx.bot, book, intro_key="new_book_notification"
        ):
            logger.info(
                f"notify_new_book_job: posted book {book_id} to chat {ALLOWED_CHAT_ID}."
            )

    logger.info(f"notify_new_book_job: done — sent to {sent} user(s).")


async def conv_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
    ctx.user_data.clear()
    return ConversationHandler.END


# ── /vote removed — voting now done inline in /list ──────────────────────────


async def vote_cast_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline voting callbacks — works for both private and group chats.

    Vote statistics are recalculated after each vote and the message is updated
    for all viewers in the group chat."""
    from telegram.error import BadRequest

    query = update.callback_query
    lang = get_lang(ctx)
    _, book_id, score = query.data.split(":")
    if book_id == "cancel":
        await query.answer()
        await query.edit_message_text(s(lang, "cancelled"))
        return
    book_id, score = int(book_id), int(score)
    if score not in (-1, 0, 1):
        logger.warning(f"vote_cast_cb: ignoring out-of-range score {score}")
        await query.answer()
        return

    user_id = query.from_user.id

    # Get the user's CURRENT vote BEFORE saving the new one
    old_vote = db_get_user_vote(user_id, book_id)

    # Save vote to database (will INSERT or UPDATE — commits immediately)
    db_cast_vote(user_id, book_id, score)

    book = require_book(book_id)
    uv = db_get_user_vote(user_id, book_id)

    chat = update.effective_chat

    # === SAME-VOTE RE-VOTE: nothing actually changed in statistics ===
    if old_vote is not None and old_vote == score:
        if chat is not None and chat.type != "private":
            # Group chat: acknowledge voter, skip edit entirely
            # (statistics would be identical anyway)
            vote_label = vote_label_text(CHAT_LANG, uv)
            await query.answer(tr(CHAT_LANG, "vote_registered", label=vote_label))
            logger.info(
                f"[RE-VOTE] User {user_id} re-voted '{vote_label}' on book {book_id} "
                f"('{book['title']}') in group chat — no edit performed"
            )
            return
        else:
            # Private chat: same vote, message would be identical — skip edit
            vote_label = vote_label_text(lang, uv)
            await query.answer(tr(lang, "vote_registered", label=vote_label))
            logger.info(
                f"[RE-VOTE] User {user_id} re-voted '{vote_label}' on book {book_id} "
                f"('{book['title']}') in private chat — no edit performed"
            )
            return

    # === NORMAL VOTE PROCESSING (first vote or changed vote) ===
    if chat is not None and chat.type != "private":
        # Shared message: visible to whole club, show AGGREGATED statistics only
        vote_label = vote_label_text(CHAT_LANG, uv)
        await query.answer(tr(CHAT_LANG, "vote_registered", label=vote_label))

        # Build the message content with fresh statistics
        new_text = book_card(book, CHAT_LANG)
        new_markup = score_keyboard(book_id, CHAT_LANG)

        # Attempt to update — on race condition, fetch fresh data and retry once
        max_retries = 2
        for attempt in range(max_retries):
            try:
                await query.edit_message_text(
                    new_text,
                    parse_mode=PM,
                    reply_markup=new_markup,
                )
                break  # Success — exit retry loop
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    if attempt < max_retries - 1:
                        # Another edit completed first — refetch fresh data and retry
                        logger.debug(
                            f"vote_cast_cb: race condition detected (attempt {attempt+1}/{max_retries}), "
                            f"refetching book {book_id}..."
                        )
                        book = require_book(book_id)  # Fresh aggregates
                        new_text = book_card(book, CHAT_LANG)
                        new_markup = score_keyboard(book_id, CHAT_LANG)
                    else:
                        # Final attempt failed — log but don't propagate error
                        logger.info(
                            f"vote_cast_cb: message update skipped for book {book_id}, "
                            f"user {user_id} (concurrent edit with same final state)"
                        )
                else:
                    # Different error — propagate
                    raise
        return

    await query.answer()
    # Private chat: show individual vote inline (always unique per user)
    try:
        await query.edit_message_text(
            book_card(book, lang, user_vote=uv),
            parse_mode=PM,
            reply_markup=score_keyboard(book_id, lang, uv),
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.info(
                f"vote_cast_cb: no-op edit for book {book_id}, user {user_id} "
                f"in private chat (likely concurrent edit)"
            )
        else:
            raise


# ── /adminconsole conversation (admin only) ───────────────────────────────────
async def _deny_non_admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Answer and reject a callback from a non-admin. Returns True if denied.

    Conversation state already keeps non-admins out, but these buttons are
    visible to everyone when /adminconsole is run in a group, so the handlers
    verify the caller themselves rather than relying on routing alone.
    """
    if is_admin(update.effective_user.id):
        return False
    await update.callback_query.answer(tr(ctx, "admin_only"), show_alert=True)
    return True


async def cmd_admin_console(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(tr(ctx, "admin_only"), parse_mode=PM)
        return ConversationHandler.END

    last_act = ctx.bot_data.get("last_non_admin_activity")
    last_act_str = fmt_dt_utc(last_act) if last_act else tr(ctx, "never")

    text = (
        tr(ctx, "admin_console_title")
        + f"\n\n{tr(ctx, 'last_activity_label')}: <code>{last_act_str}</code>"
    )

    post_chat = db_get_admin_setting("post_new_books_to_chat", 0)
    chat_state = "✅" if post_chat else "❌"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_mark_btn"), callback_data="admin:mark"
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_hide_btn"), callback_data="admin:hide"
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_notify_btn"), callback_data="admin:notify"
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_notify_one_btn"), callback_data="admin:notify_pick"
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_notify_chat_btn"), callback_data="admin:notify_chat"
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_notify_chat_one_btn"),
                    callback_data="admin:notify_chat_pick",
                )
            ],
            [
                InlineKeyboardButton(
                    tr(ctx, "admin_toggle_chat_btn", state=chat_state),
                    callback_data="admin:toggle_chat",
                )
            ],
        ]
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=keyboard, parse_mode=PM
        )
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=PM)
    return ADMIN_MENU


async def admin_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")[1]

    if data == "mark":
        books = db_get_books(discussed=False, include_hidden=True)
        if not books:
            await query.edit_message_text(tr(ctx, "no_unmark"), parse_mode=PM)
            return ConversationHandler.END
        await query.edit_message_text(
            tr(ctx, "choose_mark"),
            reply_markup=books_keyboard(
                books, "admin_mark_pick", tr(ctx, "cancel_btn")
            ),
        )
        return ADMIN_MARK_CHOOSE
    elif data == "hide":
        # Show all undiscussed books (including already hidden ones to allow unhiding)
        books = db_get_books(discussed=False, include_hidden=True)
        if not books:
            await query.edit_message_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
            return ConversationHandler.END

        # Custom keyboard to show current hidden status
        keyboard_btns = []
        for b in books:
            label = ("👁 " if b["hidden"] else "") + b["title"]
            keyboard_btns.append(
                [
                    InlineKeyboardButton(
                        label, callback_data=f"admin_hide_pick:{b['id']}"
                    )
                ]
            )
        keyboard_btns.append(
            [
                InlineKeyboardButton(
                    tr(ctx, "cancel_btn"), callback_data="admin_hide_pick:cancel"
                )
            ]
        )

        await query.edit_message_text(
            tr(ctx, "choose_hide"),
            reply_markup=InlineKeyboardMarkup(keyboard_btns),
        )
        return ADMIN_HIDE_CHOOSE
    elif data == "notify":
        return await admin_notify_top_cb(update, ctx)
    elif data == "notify_pick":
        books = db_get_books(discussed=False)
        if not books:
            await query.edit_message_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
            return ConversationHandler.END
        await query.edit_message_text(
            tr(ctx, "choose_notify"),
            reply_markup=books_keyboard(
                books, "admin_notify_pick", tr(ctx, "cancel_btn")
            ),
        )
        return ADMIN_NOTIFY_PICK
    elif data == "notify_chat":
        return await admin_notify_chat_top_cb(update, ctx)
    elif data == "notify_chat_pick":
        books = db_get_books(discussed=False)
        if not books:
            await query.edit_message_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
            return ConversationHandler.END
        await query.edit_message_text(
            tr(ctx, "choose_notify_chat"),
            reply_markup=books_keyboard(
                books, "admin_notify_chat_pick", tr(ctx, "cancel_btn")
            ),
        )
        return ADMIN_NOTIFY_CHAT_PICK
    elif data == "toggle_chat":
        current = db_get_admin_setting("post_new_books_to_chat", 0)
        db_set_admin_setting("post_new_books_to_chat", 1 - current)
        return await cmd_admin_console(update, ctx)
    return ConversationHandler.END


async def admin_notify_top_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query

    books = db_get_books(discussed=False)
    if not books:
        await query.edit_message_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
        return ConversationHandler.END

    # Top 5 selection (same logic as /top)
    top_books = books_top_n(books)

    user_ids = db_get_users_with_setting("notify_new_books", 1)
    notified_count = 0

    for user_id in user_ids:
        # For each user, find which of the top books they HAVEN'T voted for
        unvoted_tops = []
        for b in top_books:
            if db_get_user_vote(user_id, b["id"]) is None:
                unvoted_tops.append(b)

        if not unvoted_tops:
            continue

        # Send reminder to this user
        user_data = ctx.application.user_data.get(user_id, {})
        user_lang = user_data.get("lang", "ru") if isinstance(user_data, dict) else "ru"
        text = tr(user_lang, "vote_reminder_msg")

        # We'll send the reminder text and then the book cards
        try:
            await ctx.bot.send_message(chat_id=user_id, text=text, parse_mode=PM)
            for b in unvoted_tops:
                await ctx.bot.send_message(
                    chat_id=user_id,
                    text=book_card(b, user_lang),
                    parse_mode=PM,
                    reply_markup=score_keyboard(b["id"], user_lang),
                )
            notified_count += 1
        except Exception as e:
            logger.warning(f"admin_notify_top_cb: failed to notify user {user_id}: {e}")

    if notified_count > 0:
        await query.edit_message_text(
            tr(ctx, "admin_notify_confirm", count=notified_count), parse_mode=PM
        )
    else:
        await query.edit_message_text(tr(ctx, "admin_notify_no_users"), parse_mode=PM)

    return ConversationHandler.END


async def admin_notify_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)

    if book_id == "cancel":
        await query.edit_message_text(s(lang, "cancelled"))
        return ConversationHandler.END

    book_id = int(book_id)
    book = db_get_book(book_id)
    if not book:
        await query.edit_message_text("Error: book not found.")
        return ConversationHandler.END

    user_ids = db_get_users_with_setting("notify_new_books", 1)
    notified_count = 0

    for user_id in user_ids:
        # Check if user has NOT voted for this book
        if db_get_user_vote(user_id, book_id) is not None:
            continue

        user_data = ctx.application.user_data.get(user_id, {})
        user_lang = user_data.get("lang", "ru") if isinstance(user_data, dict) else "ru"

        try:
            # Send reminder to this user
            text = tr(user_lang, "vote_reminder_msg")
            await ctx.bot.send_message(chat_id=user_id, text=text, parse_mode=PM)
            await ctx.bot.send_message(
                chat_id=user_id,
                text=book_card(book, user_lang),
                parse_mode=PM,
                reply_markup=score_keyboard(book_id, user_lang),
            )
            notified_count += 1
        except Exception as e:
            logger.warning(
                f"admin_notify_pick_cb: failed to notify user {user_id}: {e}"
            )

    if notified_count > 0:
        await query.edit_message_text(
            tr(ctx, "admin_notify_confirm", count=notified_count), parse_mode=PM
        )
    else:
        await query.edit_message_text(tr(ctx, "admin_notify_no_users"), parse_mode=PM)

    return ConversationHandler.END


async def admin_notify_chat_top_cb(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query

    if not ALLOWED_CHAT_ID:
        await query.edit_message_text(tr(ctx, "admin_notify_chat_no_chat"), parse_mode=PM)
        return ConversationHandler.END

    books = db_get_books(discussed=False)
    if not books:
        await query.edit_message_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
        return ConversationHandler.END

    top_books = books_top_n(books)
    posted = 0
    for b in top_books:
        if await post_book_voting_to_group_chat(
            ctx.bot, b, intro_key="vote_reminder_chat"
        ):
            posted += 1

    if posted > 0:
        await query.edit_message_text(
            tr(ctx, "admin_notify_chat_confirm", count=posted), parse_mode=PM
        )
    else:
        await query.edit_message_text(tr(ctx, "admin_notify_chat_failed"), parse_mode=PM)

    return ConversationHandler.END


async def admin_notify_chat_pick_cb(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)

    if book_id == "cancel":
        await query.edit_message_text(s(lang, "cancelled"))
        return ConversationHandler.END

    if not ALLOWED_CHAT_ID:
        await query.edit_message_text(tr(ctx, "admin_notify_chat_no_chat"), parse_mode=PM)
        return ConversationHandler.END

    book_id = int(book_id)
    book = db_get_book(book_id)
    if not book:
        await query.edit_message_text("Error: book not found.")
        return ConversationHandler.END

    if await post_book_voting_to_group_chat(
        ctx.bot, book, intro_key="vote_reminder_chat"
    ):
        await query.edit_message_text(
            tr(ctx, "admin_notify_chat_confirm", count=1), parse_mode=PM
        )
    else:
        await query.edit_message_text(tr(ctx, "admin_notify_chat_failed"), parse_mode=PM)

    return ConversationHandler.END


async def admin_mark_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(s(lang, "cancelled"))
        return ConversationHandler.END
    ctx.user_data["mark_book_id"] = int(book_id)
    await query.edit_message_text(tr(ctx, "ask_discuss_date"), parse_mode=PM)
    return ADMIN_MARK_DATE


async def admin_mark_date_handler(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(tr(ctx, "admin_only"), parse_mode=PM)
        return ConversationHandler.END
    lang = get_lang(ctx)
    text = update.message.text.strip()
    if text == "/today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    else:
        parsed = parse_date(text)
        if parsed is None:
            await update.message.reply_text(tr(ctx, "invalid_date"), parse_mode=PM)
            return ADMIN_MARK_DATE
        date_str = parsed
    book_id = ctx.user_data.pop("mark_book_id", None)
    if book_id is None:
        # State was lost (e.g. bot restarted mid-conversation).
        await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END
    db_mark_discussed(book_id, date_str)
    book = require_book(book_id)
    await update.message.reply_text(
        T[lang]["marked_discussed"].format(title=h(book["title"]), date=h(date_str)),
        parse_mode=PM,
    )
    return ConversationHandler.END


async def admin_hide_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_non_admin_cb(update, ctx):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(s(lang, "cancelled"))
        return ConversationHandler.END

    book_id = int(book_id)
    db_toggle_hidden(book_id)
    book = db_get_book(book_id)

    msg_key = "book_hidden" if book["hidden"] else "book_unhidden"
    await query.edit_message_text(
        tr(ctx, msg_key, title=h(book["title"])),
        parse_mode=PM,
    )
    return ConversationHandler.END


# ── /edit — sequential field-by-field editor ──────────────────────────────────
# Fields edited in order: title, author, pages, fiction, review_link, description
EDIT_FIELDS = ["title", "author", "pages", "fiction", "review_link", "description"]


def edit_field_key(field: str) -> str:
    return f"field_{field.replace('_link', '').replace('review', 'review')}"


def edit_current_value(book: BookLike, field: str, lang: str) -> str:
    """Return human-readable current value for a field."""
    if field == "fiction":
        return (
            s(lang, "fiction_label") if book["fiction"] else s(lang, "nonfiction_label")
        )
    if field == "review_link":
        return book["review_link"] or ("—" if lang == "en" else "—")
    if field == "description":
        return book["description"] or ("—" if lang == "en" else "—")
    return str(book[field])


def edit_yn_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    s(lang, "edit_yes_btn"), callback_data="edit_yn:yes"
                ),
                InlineKeyboardButton(
                    s(lang, "edit_no_btn"), callback_data="edit_yn:no"
                ),
            ]
        ]
    )


def edit_fiction_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    s(lang, "fiction_btn"), callback_data="edit_fiction:1"
                ),
                InlineKeyboardButton(
                    s(lang, "nonfiction_btn"), callback_data="edit_fiction:0"
                ),
            ]
        ]
    )


async def _ask_edit_field(
    update_or_query: Any,
    ctx: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False,
) -> int:
    """Ask user about the next field to edit. Returns next state or END."""
    lang = get_lang(ctx)
    fields = ctx.user_data.get("edit_fields", [])
    if not fields:
        # All fields done — save and show result
        book_id = ctx.user_data.pop("edit_book_id")
        changes = ctx.user_data.pop("edit_changes", {})
        for field, value in changes.items():
            db_update_book_field(book_id, field, value)
        book = require_book(book_id)
        text = f"{s(lang, 'edit_done')}\n\n{book_card(book, lang)}"
        if is_callback:
            await update_or_query.edit_message_text(text, parse_mode=PM)
        else:
            await update_or_query.message.reply_text(text, parse_mode=PM)
        ctx.user_data.pop("edit_fields", None)
        return ConversationHandler.END

    field = fields[0]
    book = require_book(ctx.user_data["edit_book_id"])
    field_key = f"field_{field}" if field != "review_link" else "field_review"
    field_name = s(lang, field_key)
    current = edit_current_value(book, field, lang)
    text = T[lang]["edit_field_prompt"].format(field=field_name, value=h(current))

    if is_callback:
        await update_or_query.edit_message_text(
            text, parse_mode=PM, reply_markup=edit_yn_keyboard(lang)
        )
    else:
        await update_or_query.message.reply_text(
            text, parse_mode=PM, reply_markup=edit_yn_keyboard(lang)
        )
    return EDITING_FIELD


async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    uname = update.effective_user.username
    all_books = db_get_books(discussed=False) + list(db_get_books(discussed=True))
    books = [b for b in all_books if can_modify(user_id, b, uname)]
    if not books:
        await update.message.reply_text(tr(ctx, "no_own_books"), parse_mode=PM)
        return ConversationHandler.END
    await update.message.reply_text(
        tr(ctx, "choose_edit"),
        reply_markup=books_keyboard(books, "edit_pick", tr(ctx, "cancel_btn")),
    )
    return EDITING_CHOOSE


async def edit_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(s(lang, "cancelled"))
        return ConversationHandler.END
    book_id = int(book_id)
    book = db_get_book(book_id)
    if book is None or not can_modify(
        query.from_user.id, book, query.from_user.username
    ):
        await query.edit_message_text(s(lang, "no_permission"), parse_mode=PM)
        return ConversationHandler.END
    ctx.user_data["edit_book_id"] = book_id
    ctx.user_data["edit_fields"] = list(EDIT_FIELDS)
    ctx.user_data["edit_changes"] = {}
    return await _ask_edit_field(query, ctx, is_callback=True)


async def edit_yn_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """User clicked Yes or No on whether to edit the current field."""
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, ans = query.data.split(":")
    field = ctx.user_data["edit_fields"][0]

    if ans == "no":
        ctx.user_data["edit_fields"].pop(0)
        return await _ask_edit_field(query, ctx, is_callback=True)

    # ans == "yes" — ask for new value
    if field == "fiction":
        await query.edit_message_text(
            T[lang]["edit_ask_new"].format(field=T[lang]["field_fiction"]),
            parse_mode=PM,
            reply_markup=edit_fiction_keyboard(lang),
        )
        return EDITING_FIELD  # handled by edit_fiction_cb

    field_name = T[lang][f"field_{field}" if field != "review_link" else "field_review"]
    await query.edit_message_text(
        T[lang]["edit_ask_new"].format(field=field_name),
        parse_mode=PM,
    )
    return EDITING_FIELD


async def edit_fiction_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked Fiction/Non-fiction via inline button."""
    query = update.callback_query
    await query.answer()
    _, value = query.data.split(":")
    ctx.user_data["edit_changes"]["fiction"] = int(value)
    ctx.user_data["edit_fields"].pop(0)
    return await _ask_edit_field(query, ctx, is_callback=True)


async def edit_value_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed a new value for the current field."""
    text = update.message.text.strip()
    field = ctx.user_data["edit_fields"][0]

    # Validate
    value: int | str
    if field == "pages":
        if not text.isdigit() or int(text) <= 0:
            await update.message.reply_text(
                tr(ctx, "edit_invalid_pages"), parse_mode=PM
            )
            return EDITING_FIELD
        value = int(text)
    elif field == "review_link":
        if not is_valid_url(text):
            await update.message.reply_text(tr(ctx, "edit_invalid_url"), parse_mode=PM)
            return EDITING_FIELD
        value = text
    else:
        value = text

    ctx.user_data["edit_changes"][field] = value
    ctx.user_data["edit_fields"].pop(0)
    return await _ask_edit_field(update, ctx, is_callback=False)


# ── /delete ────────────────────────────────────────────────────────────────────
async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    all_books = db_get_books(discussed=False) + list(db_get_books(discussed=True))
    books = [b for b in all_books if can_modify(user_id, b)]
    if not books:
        await update.message.reply_text(tr(ctx, "no_own_books"), parse_mode=PM)
        return ConversationHandler.END
    await update.message.reply_text(
        tr(ctx, "choose_delete"),
        reply_markup=books_keyboard(books, "del_pick", tr(ctx, "cancel_btn")),
    )
    return DELETING_CHOOSE


async def delete_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(s(lang, "cancelled"))
        return ConversationHandler.END
    book_id = int(book_id)
    book = db_get_book(book_id)
    if book is None or not can_modify(
        query.from_user.id, book, query.from_user.username
    ):
        await query.edit_message_text(s(lang, "no_permission"), parse_mode=PM)
        return ConversationHandler.END
    title = book["title"]
    db_delete_book(book_id)
    await query.edit_message_text(
        T[lang]["deleted"].format(title=h(title)), parse_mode=PM
    )
    return ConversationHandler.END


async def bot_notify_startup(app: Application) -> None:
    """Notify first admin that bot has started, and set default command menu."""
    # Register the default (Russian) command menu for users who haven't set a language yet
    try:
        await app.bot.delete_my_commands(scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(COMMANDS["ru"], scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning(f"Could not set default commands: {e}")
    if not ADMIN_IDS:
        return
    # Start forwarding ERROR-level logs to the admin now that a running event
    # loop and a live bot exist. Any errors buffered during import/startup are
    # flushed on the first tick.
    if ERROR_ALERTS:
        app.create_task(_drain_alert_queue(app))
    admin_id = ADMIN_IDS[0]
    try:
        # We don't have user_data here, default to English for system notifications.
        await app.bot.send_message(
            chat_id=admin_id, text=T["en"]["bot_started"], parse_mode=PM
        )
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")


async def bot_notify_shutdown(app: Application) -> None:
    """Notify first admin that bot is shutting down."""
    if not ADMIN_IDS:
        return
    admin_id = ADMIN_IDS[0]
    try:
        await app.bot.send_message(
            chat_id=admin_id, text=T["en"]["bot_stopped"], parse_mode=PM
        )
    except Exception as e:
        logger.error(f"Failed to send shutdown notification: {e}")


# ── Chat membership gate ───────────────────────────────────────────────────────
# The gate runs on every single update, so results are cached briefly to avoid a
# get_chat_member API round-trip per message. Join/leave service messages evict
# the affected user, so the common cases stay correct immediately.
MEMBERSHIP_CACHE_TTL = 300  # seconds
_membership_cache: dict[int, tuple[bool, datetime]] = {}


def _membership_cache_evict(user_id: int) -> None:
    _membership_cache.pop(user_id, None)


async def _check_membership(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the user is a member of ALLOWED_CHAT_ID (or no restriction set)."""
    if not ALLOWED_CHAT_ID:
        return True
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return False
    # Admins always pass
    if user_id in ADMIN_IDS:
        return True

    cached = _membership_cache.get(user_id)
    if cached is not None:
        allowed, checked_at = cached
        if (datetime.now() - checked_at).total_seconds() < MEMBERSHIP_CACHE_TTL:
            return allowed
        _membership_cache_evict(user_id)

    try:
        member = await ctx.bot.get_chat_member(ALLOWED_CHAT_ID, user_id)
        allowed = member.status in ("member", "administrator", "creator", "restricted")
        _membership_cache[user_id] = (allowed, datetime.now())
        return allowed
    except Exception as e:
        # Don't cache failures — a transient API error shouldn't lock a real
        # member out for the whole TTL.
        logger.warning(f"Membership check failed for user {user_id}: {e}")
        return False


async def membership_gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Block users not in the allowed chat and tell them why."""
    if update.message and update.message.left_chat_member:
        # Service message for a user leaving the chat — their membership status
        # is now "left", which would otherwise look like a blocked non-member.
        # Nothing to gate here, and we must not reply into the group over this.
        _membership_cache_evict(update.message.left_chat_member.id)
        return

    if update.message and update.message.new_chat_members:
        # Someone just joined — drop any stale "not a member" verdict for them.
        for m in update.message.new_chat_members:
            _membership_cache_evict(m.id)
        return

    user_id = update.effective_user.id if update.effective_user else None
    if user_id and user_id not in ADMIN_IDS:
        ctx.bot_data["last_non_admin_activity"] = datetime.now()

    if await _check_membership(update, ctx):
        return
    blocked_uid = update.effective_user.id if update.effective_user else None
    logger.info(
        f"Blocked user {blocked_uid or '?'} — not a member of chat {ALLOWED_CHAT_ID}"
    )
    lang = get_lang(ctx) if ctx.user_data else "ru"
    text = s(lang, "not_member").format(chat=h(ALLOWED_CHAT_NAME))
    try:
        if update.callback_query:
            await update.callback_query.answer(
                ALLOWED_CHAT_NAME + " — members only", show_alert=True
            )
        elif update.message:
            await update.message.reply_text(text, parse_mode=PM)
    except Exception as e:
        logger.warning(f"Could not send not-member message to {blocked_uid}: {e}")
    raise ApplicationHandlerStop


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Log any unhandled handler exception and tell the user something broke.

    Without this, python-telegram-bot swallows the traceback into the log and
    the user gets no reply at all — the bot just goes silent mid-command, which
    is indistinguishable from it being down.

    Note: Error messages are suppressed in group chats to avoid spamming
    members with technical notifications that belong in logs only.

    Transient Telegram API failures (e.g. 502 during long polling) are logged
    at WARNING only — they are retried by the library and should not page the admin.
    """
    if isinstance(ctx.error, NetworkError):
        logger.warning(
            "Telegram network error while processing update:", exc_info=ctx.error
        )
        return

    logger.error("Unhandled exception while processing update:", exc_info=ctx.error)

    if not isinstance(update, Update):
        return  # e.g. a job error — nobody to reply to

    # Suppress error notifications in group chats — they should only go to logs
    # or to the admin via the dedicated alert mechanism (_TelegramAlertHandler).
    if update.effective_message and update.effective_message.chat.type != "private":
        logger.info(
            f"Suppressed error notification in group chat {update.effective_message.chat.id}"
        )
        return

    lang = get_lang(ctx) if ctx.user_data is not None else "ru"
    text = tr(lang, "unexpected_error")

    try:
        if update.callback_query:
            # answer() clears the button's loading spinner; a plain message
            # would leave it spinning even though we did reply.
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text, parse_mode=PM)
        elif update.effective_message:
            await update.effective_message.reply_text(text, parse_mode=PM)
    except Exception as e:
        # Never let the error handler itself raise — that loses the original error.
        logger.warning(f"Could not deliver error notice to user: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────
def register_handlers(app: Application) -> None:
    """Attach every handler to the application.

    Split out of main() so tests can inspect the wiring — the state/fallback
    ordering here is subtle enough to be worth asserting on.
    """
    # Gate: silently block users not in the allowed chat (runs before all handlers)
    app.add_handler(TypeHandler(Update, membership_gate), group=-1)

    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("add", cmd_add)],
            states={
                ADDING_TITLE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)
                ],
                ADDING_AUTHOR: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_author)
                ],
                ADDING_PAGES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_pages)
                ],
                ADDING_FICTION: [
                    CallbackQueryHandler(add_fiction_cb, pattern=r"^fiction:")
                ],
                ADDING_REVIEW: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_review)
                ],
                # /skip needs its own handler: a bare filters.TEXT here would also
                # swallow /cancel (state handlers are matched before fallbacks).
                ADDING_DESCRIPTION: [
                    CommandHandler("skip", add_description),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, add_description),
                ],
            },
            fallbacks=[CommandHandler("cancel", conv_cancel)],
            per_message=False,
            # Without this, re-sending the entry command while the conversation is
            # still open matches nothing at all and the bot answers with silence —
            # an abandoned /adminconsole would stay stuck until the bot restarted.
            allow_reentry=True,
        )
    )

    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("adminconsole", cmd_admin_console)],
            states={
                ADMIN_MENU: [CallbackQueryHandler(admin_menu_cb, pattern=r"^admin:")],
                ADMIN_MARK_CHOOSE: [
                    CallbackQueryHandler(
                        admin_mark_pick_cb, pattern=r"^admin_mark_pick:"
                    )
                ],
                # /today needs its own handler — see the ADDING_DESCRIPTION note above.
                ADMIN_MARK_DATE: [
                    CommandHandler("today", admin_mark_date_handler),
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, admin_mark_date_handler
                    ),
                ],
                ADMIN_HIDE_CHOOSE: [
                    CallbackQueryHandler(
                        admin_hide_pick_cb, pattern=r"^admin_hide_pick:"
                    )
                ],
                ADMIN_NOTIFY_PICK: [
                    CallbackQueryHandler(
                        admin_notify_pick_cb, pattern=r"^admin_notify_pick:"
                    )
                ],
                ADMIN_NOTIFY_CHAT_PICK: [
                    CallbackQueryHandler(
                        admin_notify_chat_pick_cb, pattern=r"^admin_notify_chat_pick:"
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", conv_cancel)],
            per_message=False,
            # Without this, re-sending the entry command while the conversation is
            # still open matches nothing at all and the bot answers with silence —
            # an abandoned /adminconsole would stay stuck until the bot restarted.
            allow_reentry=True,
        )
    )

    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("edit", cmd_edit)],
            states={
                EDITING_CHOOSE: [
                    CallbackQueryHandler(edit_pick_cb, pattern=r"^edit_pick:")
                ],
                EDITING_FIELD: [
                    CallbackQueryHandler(edit_yn_cb, pattern=r"^edit_yn:"),
                    CallbackQueryHandler(edit_fiction_cb, pattern=r"^edit_fiction:"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_handler),
                ],
            },
            fallbacks=[CommandHandler("cancel", conv_cancel)],
            per_message=False,
            # Without this, re-sending the entry command while the conversation is
            # still open matches nothing at all and the bot answers with silence —
            # an abandoned /adminconsole would stay stuck until the bot restarted.
            allow_reentry=True,
        )
    )

    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("delete", cmd_delete)],
            states={
                DELETING_CHOOSE: [
                    CallbackQueryHandler(delete_pick_cb, pattern=r"^del_pick:")
                ],
            },
            fallbacks=[CommandHandler("cancel", conv_cancel)],
            per_message=False,
            # Without this, re-sending the entry command while the conversation is
            # still open matches nothing at all and the bot answers with silence —
            # an abandoned /adminconsole would stay stuck until the bot restarted.
            allow_reentry=True,
        )
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("discussed", cmd_discussed))

    app.add_handler(CallbackQueryHandler(list_choice_cb, pattern=r"^list:"))
    app.add_handler(CallbackQueryHandler(settings_choice_cb, pattern=r"^settings:"))
    app.add_handler(CallbackQueryHandler(vote_cast_cb, pattern=r"^vote_cast:"))
    app.add_handler(CallbackQueryHandler(score_calc_cb, pattern=r"^score_calc_info$"))

    # Catches anything the handlers above let escape, so a crash produces a
    # visible reply instead of silence.
    app.add_error_handler(error_handler)


def main() -> None:
    # Fail loudly here rather than letting Telegram reject the placeholder with
    # an opaque 401 several seconds into startup.
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit(
            "BOT_TOKEN is not set. Put it in your .env file (see README) "
            "or export it before starting the bot."
        )

    init_db()

    persistence_path = os.environ.get("PERSISTENCE_PATH", "bot_persistence")
    # Ensure persistence_path is a file, not a directory
    if os.path.isdir(persistence_path):
        logger.warning(
            f"Persistence path '{persistence_path}' is a directory. Removing it to allow file creation."
        )
        try:
            os.rmdir(persistence_path)
        except OSError:
            logger.error(
                f"Could not remove directory '{persistence_path}'. Please remove it manually."
            )

    persistence = PicklePersistence(filepath=persistence_path)
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .post_init(bot_notify_startup)
        .post_stop(bot_notify_shutdown)
        .build()
    )
    # Verify JobQueue is available (requires: pip install "python-telegram-bot[job-queue]")
    if app.job_queue is None:
        logger.error(
            "JobQueue is not available! New book notifications will not work.\n"
            'Fix: pip install "python-telegram-bot[job-queue]"'
        )

    register_handlers(app)

    logger.info("Club entity: %s", CLUB_ENTITY)
    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
