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
  /edit            - Edit a book's details (owner/admin only)
  /delete          - Delete a book (owner/admin only)
  /discussed       - View the archive of discussed books
  /markdiscussed   - Admin: mark a book as discussed (with date)
  /cancel          - Cancel the current operation
"""

import logging
import logging.handlers
import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat, BotCommandScopeChatMember
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    PicklePersistence,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    TypeHandler,
    filters,
)

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
]
DB_PATH = "bookclub.db"

# Members of this chat are allowed to use the bot.
# Set via environment variable: export ALLOWED_CHAT_ID="-1001234567890"
# Leave empty to allow everyone (useful during initial setup).
ALLOWED_CHAT_ID   = int(os.environ.get("ALLOWED_CHAT_ID", "0")) or None
ALLOWED_CHAT_NAME = os.environ.get("ALLOWED_CHAT_NAME", "Книжный клуб")

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
EDITING_FIELD  = 7   # waiting for new value of current field
DELETING_CHOOSE = 8
MARKING_CHOOSE, MARKING_DATE = range(9, 11)

LOG_FILE = os.environ.get("LOG_FILE", "bookclub_bot.log")

_log_fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

_file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])
logger = logging.getLogger(__name__)

# ── Translations ───────────────────────────────────────────────────────────────
T = {
    "en": {
        "welcome": (
            "📚 <b>Welcome to the Book Club Bot!</b>\n\n"
            "➕ /add — Add a book\n"
            "📋 /list — See all books\n"
            "🏆 /top — Top rated books\n"
            "⚙️ /settings — Settings\n"
            "✏️ /edit — Edit a book entry\n"
            "🗑 /delete — Delete a book\n"
            "🏆 /top — Top rated books\n"
            "✅ /discussed — Books already discussed\n"
            "📌 /markdiscussed — Mark a book as discussed (admin)\n"
            "❓ /help — Show this message"
        ),
        "lang_set":            "🇬🇧 Language set to English.",
        "ask_title":           "📖 What is the <b>title</b> of the book?",
        "ask_author":          "✍️ Who is the <b>author</b>?",
        "ask_pages":           "📄 How many <b>pages</b> does it have? (enter a number)",
        "invalid_pages":       "⚠️ Please enter a valid number of pages (e.g. 320):",
        "ask_fiction":         "📂 Is it <b>Fiction</b> or <b>Non-fiction</b>?",
        "fiction_btn":         "📖 Fiction",
        "nonfiction_btn":      "📰 Non-fiction",
        "ask_review":          "🔗 Paste the <b>link to a review</b> (must start with http:// or https://):",
        "invalid_review":      "⚠️ That doesn't look like a valid URL. Please paste a link starting with http:// or https://:",
        "ask_desc":            "📝 Add a <b>description</b> (or /skip to leave empty):",
        "book_added":          "✅ Book added!",
        "no_books":            "📭 No books yet. Use /add to add one!",
        "no_undiscussed":      "📭 No undiscussed books — use /discussed to see past reads.",
        "no_votes":            "No votes yet. Use /list to see books and vote inline!",
        "no_books_edit":       "📭 No books to edit yet.",
        "no_books_delete":     "📭 No books to delete yet.",
        "cancelled":           "❌ Cancelled.",
        "choose_vote":         "📊 Choose a book to vote on:",
        "choose_edit":         "✏️ Choose a book to edit:",
        "choose_delete":       "🗑 Choose a book to delete:",
        "your_vote":           "Your current vote",
        "none_vote":           "—",
        "rate_book":           "📊 Vote on <b>{title}</b>",
        "desc_updated":        "✅ Description updated!",
        "top_title":           "🏆 <b>Top Books</b>\nSorted by average score and then by vote count.\n\n",
        "added_by":            "Added by",
        "added_on":            "Added on",
        "pages_label":         "Pages",
        "review_label":        "Review",
        "cancel_btn":          "❌ Cancel",
        "edit_field_prompt":   "✏️ <b>{field}</b>\nCurrent value: <i>{value}</i>\n\nModify this field?",
        "edit_yes_btn":        "✏️ Yes, change it",
        "edit_no_btn":         "⏭ Skip",
        "edit_ask_new":        "Send the new value for <b>{field}</b>:",
        "edit_done":           "✅ Book updated!",
        "edit_invalid_pages":  "⚠️ Must be a positive number. Send again:",
        "edit_invalid_url":    "⚠️ Must start with http:// or https://. Send again:",
        "field_title":         "Title",
        "field_author":        "Author",
        "field_pages":         "Pages",
        "field_fiction":       "Fiction / Non-fiction",
        "field_review":        "Review link",
        "field_description":   "Description",
        "deleted":             "🗑 <b>{title}</b> has been deleted.",
        "fiction_label":       "Fiction",
        "nonfiction_label":    "Non-fiction",
        "votes_label":         lambda n: f"({n} vote{'s' if n != 1 else ''})",
        "want_label":          "✅ want to read",
        "meh_label":           "😐 don't care",
        "no_label":            "❌ don't want to read",
        "want_btn":            "✅ Want",
        "meh_btn":             "😐 Don't care",
        "no_btn":              "❌ Don't want",
        "voted_msg":           "✅ Vote saved for <b>{title}</b>",
        "no_permission":       "⛔ You can only edit or delete books you added.",
        "no_own_books":        "📭 You have no books to edit or delete.",
        "admin_only":          "⛔ This command is for admins only.",
        "choose_mark":         "📌 Choose a book to mark as discussed:",
        "no_unmark":           "📭 No undiscussed books to mark.",
        "ask_discuss_date":    "📅 Enter the <b>discussion date</b> (YYYY-MM-DD), or /today to use today:",
        "invalid_date":        "⚠️ Invalid date. Use YYYY-MM-DD format (e.g. 2026-03-17):",
        "marked_discussed":    "✅ <b>{title}</b> marked as discussed on {date}.",
        "discussed_title":     "✅ <b>Discussed Books</b>\n\n",
        "no_discussed":        "📭 No books have been discussed yet.",
        "discussed_on":        "Discussed on",
        "list_prompt":         "📋 <b>List of Books</b>\nShow all books or only those you haven't voted for yet?",
        "list_all_btn":        "📚 All books",
        "list_unvoted_btn":    "🗳 Unvoted only",
        "score_calc_btn":      "📊 How a score is calculated",
        "score_calc_info":     "✅ Want: +1 point\n😐 Don't care: 0 points\n❌ Don't want: -1 point\n\nSorted by average score, then by the total number of votes, and then by the date added.",
        "settings_title":      "⚙️ <b>Settings</b>",
        "settings_notify_label": "Notifications for new books:",
        "settings_notify_on":   "🔔 Enabled (10 min delay)",
        "settings_notify_off":  "🔕 Disabled",
        "settings_notify_btn":  "Toggle Notifications",
        "settings_lang_btn":    "🌐 Switch to Russian",
        "notify_optin_prompt": "Would you like to receive notifications (with a 10-minute delay) when others add new books?",
        "notify_optin_yes":    "🔔 Yes, notify me",
        "notify_optin_no":     "🔕 No, thanks",
        "notify_optin_success": "✅ Settings saved!",
        "new_book_notification": "🆕 <b>New book added!</b>\n(Note: you receive this 10 minutes after it was added)\n\n",
        "new_book_delay_note": "\n\n<i>(Notifications for this book will be sent to others in 10 minutes)</i>",
        "not_member":  "⛔ This bot is only for members of the <b>{chat}</b> chat. Please join first.",
        "bot_started": "🚀 <b>Bot is up!</b>",
        "bot_stopped": "🛑 <b>Bot is down.</b>",
    },
    "ru": {
        "welcome": (
            "📚 <b>Добро пожаловать в Книжный клуб!</b>\n\n"
            "➕ /add — Добавить книгу\n"
            "📋 /list — Список книг\n"
            "🏆 /top — Топ книг\n"
            "⚙️ /settings — Настройки\n"
            "✏️ /edit — Редактировать запись\n"
            "🗑 /delete — Удалить книгу\n"
            "🏆 /top — Топ книг\n"
            "✅ /discussed — Обсуждённые книги\n"
            "📌 /markdiscussed — Отметить книгу как обсуждённую (админ)\n"
            "❓ /help — Показать это сообщение"
        ),
        "lang_set":            "🇷🇺 Язык установлен: Русский.",
        "ask_title":           "📖 Как называется книга (<b>название</b>)?",
        "ask_author":          "✍️ Кто <b>автор</b>?",
        "ask_pages":           "📄 Сколько <b>страниц</b> в книге? (введите число)",
        "invalid_pages":       "⚠️ Введите корректное число страниц (например, 320):",
        "ask_fiction":         "📂 Это <b>художественная</b> или <b>нехудожественная</b> литература?",
        "fiction_btn":         "📖 Худ. литература",
        "nonfiction_btn":      "📰 Нехуд. литература",
        "ask_review":          "🔗 Вставьте <b>ссылку на рецензию</b> (должна начинаться с http:// или https://):",
        "invalid_review":      "⚠️ Это не похоже на корректный URL. Вставьте ссылку, начинающуюся с http:// или https://:",
        "ask_desc":            "📝 Добавьте <b>описание</b> (или /skip, чтобы пропустить):",
        "book_added":          "✅ Книга добавлена!",
        "no_books":            "📭 Книг пока нет. Используйте /add, чтобы добавить!",
        "no_undiscussed":      "📭 Необсуждённых книг нет — используйте /discussed для просмотра прочитанных.",
        "no_votes":            "Голосов пока нет. Используйте /list для голосования!",
        "no_books_edit":       "📭 Нет книг для редактирования.",
        "no_books_delete":     "📭 Нет книг для удаления.",
        "cancelled":           "❌ Отменено.",
        "choose_vote":         "📊 Выберите книгу для голосования:",
        "choose_edit":         "✏️ Выберите книгу для редактирования:",
        "choose_delete":       "🗑 Выберите книгу для удаления:",
        "your_vote":           "Ваш текущий голос",
        "none_vote":           "—",
        "rate_book":           "📊 Голосование: <b>{title}</b>",
        "desc_updated":        "✅ Описание обновлено!",
        "top_title":           "🏆 <b>Топ книг</b>\nСортировка по среднему баллу и по количеству голосов.\n\n",
        "added_by":            "Добавил",
        "added_on":            "Добавлено",
        "pages_label":         "Страниц",
        "review_label":        "Рецензия",
        "cancel_btn":          "❌ Отмена",
        "edit_field_prompt":   "✏️ <b>{field}</b>\nТекущее значение: <i>{value}</i>\n\nИзменить это поле?",
        "edit_yes_btn":        "✏️ Да, изменить",
        "edit_no_btn":         "⏭ Пропустить",
        "edit_ask_new":        "Отправьте новое значение для <b>{field}</b>:",
        "edit_done":           "✅ Книга обновлена!",
        "edit_invalid_pages":  "⚠️ Должно быть положительным числом. Отправьте снова:",
        "edit_invalid_url":    "⚠️ Должна начинаться с http:// или https://. Отправьте снова:",
        "field_title":         "Название",
        "field_author":        "Автор",
        "field_pages":         "Страниц",
        "field_fiction":       "Fiction / Non-fiction",
        "field_review":        "Ссылка на рецензию",
        "field_description":   "Описание",
        "deleted":             "🗑 <b>{title}</b> удалена.",
        "fiction_label":       "Fiction",
        "nonfiction_label":    "Non-fiction",
        "votes_label":         lambda n: (
            f"({n} оценка)" if n == 1 else
            f"({n} оценки)" if 2 <= n <= 4 else
            f"({n} оценок)"
        ),
        "want_label":          "✅ хочу читать",
        "meh_label":           "😐 всё равно",
        "no_label":            "❌ не хочу читать",
        "want_btn":            "✅ Хочу",
        "meh_btn":             "😐 Всё равно",
        "no_btn":              "❌ Не хочу",
        "voted_msg":           "✅ Голос сохранён для <b>{title}</b>",
        "no_permission":       "⛔ Вы можете редактировать или удалять только добавленные вами книги.",
        "no_own_books":        "📭 У вас нет книг для редактирования или удаления.",
        "admin_only":          "⛔ Эта команда доступна только администраторам.",
        "choose_mark":         "📌 Выберите книгу для отметки как обсуждённой:",
        "no_unmark":           "📭 Нет необсуждённых книг для отметки.",
        "ask_discuss_date":    "📅 Введите <b>дату обсуждения</b> (ГГГГ-ММ-ДД) или /today для сегодняшней даты:",
        "invalid_date":        "⚠️ Неверный формат даты. Используйте ГГГГ-ММ-ДД (например, 2026-03-17):",
        "marked_discussed":    "✅ <b>{title}</b> отмечена как обсуждённая {date}.",
        "discussed_title":     "✅ <b>Обсуждённые книги</b>\n\n",
        "no_discussed":        "📭 Пока ни одна книга не была обсуждена.",
        "discussed_on":        "Обсуждено",
        "list_prompt":         "📋 <b>Список книг</b>\nПоказать все книги или только те, за которые вы ещё не голосовали?",
        "list_all_btn":        "📚 Все книги",
        "list_unvoted_btn":    "🗳 Только без моего голоса",
        "score_calc_btn":      "📊 Как рассчитывается балл",
        "score_calc_info":     "✅ Хочу: +1 балл\n😐 Всё равно: 0 баллов\n❌ Не хочу: -1 балл\n\nСортировка по среднему баллу, затем по количеству голосов и затем по дате добавления.",
        "settings_title":      "⚙️ <b>Настройки</b>",
        "settings_notify_label": "Уведомления о новых книгах:",
        "settings_notify_on":   "🔔 Включены (задержка 10 мин)",
        "settings_notify_off":  "🔕 Выключены",
        "settings_notify_btn":  "Переключить уведомления",
        "settings_lang_btn":    "🌐 Switch to English",
        "notify_optin_prompt": "Хотите получать уведомления (с задержкой 10 минут), когда другие добавляют новые книги?",
        "notify_optin_yes":    "🔔 Да, уведомлять",
        "notify_optin_no":     "🔕 Нет, спасибо",
        "notify_optin_success": "✅ Настройки сохранены!",
        "new_book_notification": "🆕 <b>Добавлена новая книга!</b>\n(Примечание: вы получили это через 10 минут после добавления)\n\n",
        "new_book_delay_note": "\n\n<i>(Уведомления об этой книге будут разосланы остальным через 10 минут)</i>",
        "not_member":  "⛔ Этот бот только для участников чата <b>{chat}</b>. Пожалуйста, сначала вступите в него.",
        "bot_started": "🚀 <b>Бот запущен!</b>",
        "bot_stopped": "🛑 <b>Бот остановлен.</b>",
    },
}

PM = "HTML"


IMPORTED_USER_ID = 0  # sentinel for books imported without a real user_id


def can_modify(user_id: int, book, username: str = None) -> bool:
    """Admin always wins. For imported books (added_by=0), match by @username."""
    if user_id in ADMIN_IDS:
        return True
    if book["added_by"] == IMPORTED_USER_ID:
        # Imported book — allow if the caller's @username matches
        stored = book["added_by_username"]
        clean  = (username or "").lstrip("@")
        return bool(clean and stored and clean.lower() == stored.lower())
    return user_id == book["added_by"]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_lang(ctx):
    return ctx.user_data.get("lang", "ru")


def tr(ctx_or_lang, key, **kwargs):
    lang = ctx_or_lang if isinstance(ctx_or_lang, str) else get_lang(ctx_or_lang)
    val = T[lang][key]
    if callable(val):
        return val(**kwargs)
    return val.format(**kwargs) if kwargs else val


# ── Database ───────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL,
                author        TEXT NOT NULL,
                pages         INTEGER NOT NULL DEFAULT 0,
                fiction       INTEGER NOT NULL DEFAULT 1,
                review_link   TEXT NOT NULL DEFAULT '',
                description   TEXT DEFAULT '',
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
            ("pages",             "INTEGER NOT NULL DEFAULT 0"),
            ("fiction",           "INTEGER NOT NULL DEFAULT 1"),
            ("review_link",       "TEXT NOT NULL DEFAULT ''"),
            ("discussed",         "INTEGER NOT NULL DEFAULT 0"),
            ("discussed_at",      "TEXT DEFAULT NULL"),
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
                book_id INTEGER NOT NULL,
                score   INTEGER NOT NULL,
                PRIMARY KEY (user_id, book_id),
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
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


def db_add_book(title, author, pages, fiction, review_link, description, user_id, user_name, username=None):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """INSERT INTO books
               (title, author, pages, fiction, review_link, description,
                added_by, added_by_name, added_by_username, added_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (title, author, pages, int(fiction), review_link, description,
             user_id, user_name, username, datetime.now().strftime("%Y-%m-%d")),
        )
        return cur.lastrowid


def _books_query(extra_where="", order="avg_score DESC, vote_count DESC, b.added_at DESC"):
    return f"""
        SELECT b.*,
               COALESCE(AVG(v.score), 0)                          AS avg_score,
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


def db_get_books(discussed=False, user_id_unvoted=None):
    """Return books. discussed=False → undiscussed, discussed=True → discussed.
    If user_id_unvoted is provided, only return books that this user has NOT voted for yet.
    """
    flag = 1 if discussed else 0
    where = "WHERE b.discussed = ?"
    params = [flag]
    if user_id_unvoted:
        where += " AND b.id NOT IN (SELECT book_id FROM votes WHERE user_id = ?)"
        params.append(user_id_unvoted)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            _books_query(where,
                         "b.discussed_at DESC" if discussed else "avg_score DESC, vote_count DESC, b.added_at DESC"),
            tuple(params)
        ).fetchall()


def db_get_book(book_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            _books_query("WHERE b.id = ?"), (book_id,)
        ).fetchone()


def db_update_book_field(book_id, field, value):
    """Update a single whitelisted field."""
    allowed = {"title", "author", "pages", "fiction", "review_link", "description"}
    if field not in allowed:
        raise ValueError(f"Field {field!r} not editable")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE books SET {field}=? WHERE id=?", (value, book_id))
        conn.commit()


def db_mark_discussed(book_id, date_str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE books SET discussed=1, discussed_at=? WHERE id=?",
            (date_str, book_id)
        )
        conn.commit()


def db_delete_book(book_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        conn.commit()


def db_cast_vote(user_id, book_id, score):
    """score: -1 = don't want, 0 = don't care, 1 = want to read"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO votes (user_id,book_id,score) VALUES (?,?,?) "
            "ON CONFLICT(user_id,book_id) DO UPDATE SET score=excluded.score",
            (user_id, book_id, score),
        )
        conn.commit()


def db_get_user_vote(user_id, book_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT score FROM votes WHERE user_id=? AND book_id=?", (user_id, book_id)
        ).fetchone()
        return row[0] if row else None


def db_get_user_setting(user_id, key, default=-1):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT setting_val FROM user_settings WHERE user_id=? AND setting_key=?",
            (user_id, key),
        ).fetchone()
        return row[0] if row is not None else default


def db_set_user_setting(user_id, key, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, setting_key, setting_val) VALUES (?,?,?) "
            "ON CONFLICT(user_id, setting_key) DO UPDATE SET setting_val=excluded.setting_val",
            (user_id, key, value),
        )
        conn.commit()


def db_get_users_with_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id FROM user_settings WHERE setting_key=? AND setting_val=?",
            (key, value),
        ).fetchall()
        return [r[0] for r in rows]


# ── Formatting ─────────────────────────────────────────────────────────────────
def format_user(book) -> str:
    """Return @username if available, otherwise fall back to display name."""
    username = book["added_by_username"]
    if username:
        return f"@{username}"
    return book["added_by_name"] or "unknown"

def h(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


SCORE_EMOJI = {1: "✅", 0: "😐", -1: "❌", None: "—"}


def score_display(book, lang="en"):
    """Show vote tally: ✅12  😐3  ❌2  (N votes)"""
    yes   = book["votes_yes"]
    meh   = book["votes_meh"]
    no    = book["votes_no"]
    total = book["vote_count"]
    if total == 0:
        return T[lang]['votes_label'](0)
    return f"✅ {yes}  😐 {meh}  ❌ {no}  {T[lang]['votes_label'](total)}"


def book_card(book, lang="en", user_vote=None):
    fiction_label = T[lang]["fiction_label"] if book["fiction"] else T[lang]["nonfiction_label"]
    lines = [
        f"📖 <b>{h(book['title'])}</b>",
        f"✍️ {h(book['author'])}",
        f"📂 {h(fiction_label)}  •  📄 {h(str(book['pages']))} {h(T[lang]['pages_label'])}",
        score_display(book, lang),
    ]
    if user_vote is not None:
        vote_label = T[lang][{1: "want_label", 0: "meh_label", -1: "no_label"}[user_vote]]
        lines[-1] += f"  <i>({h(T[lang]['your_vote'])}: {h(vote_label)})</i>"
    if book["review_link"]:
        lines.append(f'🔗 <a href="{h(book["review_link"])}">{h(T[lang]["review_label"])}</a>')
    if book["description"]:
        lines += ["", f"<i>{h(book['description'])}</i>"]
    meta = (
        f"<i>{h(T[lang]['added_by'])}: {h(format_user(book))}"
        f"  •  {h(T[lang]['added_on'])}: {h(book['added_at'])}"
    )
    if book["discussed"] and book["discussed_at"]:
        meta += f"  •  ✅ {h(T[lang]['discussed_on'])}: {h(book['discussed_at'])}"
    meta += "</i>"
    lines += ["", meta]
    return "\n".join(lines)

def books_keyboard(books, prefix, cancel_label):
    buttons = []
    for b in books:
        label = f"{b['title']} — {b['author']}"
        if len(label) > 48:
            label = label[:45] + "…"
        buttons.append([InlineKeyboardButton(label, callback_data=f"{prefix}:{b['id']}")])
    buttons.append([InlineKeyboardButton(cancel_label, callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(buttons)


def fiction_keyboard(lang):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(T[lang]["fiction_btn"],    callback_data="fiction:1"),
        InlineKeyboardButton(T[lang]["nonfiction_btn"], callback_data="fiction:0"),
    ]])


def score_keyboard(book_id, lang, current=None):
    """Compact 3-button vote row to attach directly to book cards."""
    options = [
        (1,  T[lang]["want_btn"]),
        (0,  T[lang]["meh_btn"]),
        (-1, T[lang]["no_btn"]),
    ]
    row = [
        InlineKeyboardButton(
            label + (" ✓" if current == score else ""),
            callback_data=f"vote_cast:{book_id}:{score}"
        )
        for score, label in options
    ]
    return InlineKeyboardMarkup([row])


def is_valid_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def parse_date(text: str):
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
        BotCommand("add",           "➕ Add a book"),
        BotCommand("list",          "📋 List books & vote inline"),
        BotCommand("top",           "🏆 Top rated books"),
        BotCommand("settings",      "⚙️ Settings"),
        BotCommand("discussed",     "✅ Books already discussed"),
        BotCommand("edit",          "✏️ Edit a book entry"),
        BotCommand("delete",        "🗑 Delete a book"),
        BotCommand("markdiscussed", "📌 Mark as discussed (admin)"),
        BotCommand("help",          "❓ Show help"),
        BotCommand("cancel",        "❌ Cancel current action"),
    ],
    "ru": [
        BotCommand("add",           "➕ Добавить книгу"),
        BotCommand("list",          "📋 Список книг и голосование"),
        BotCommand("top",           "🏆 Топ книг"),
        BotCommand("settings",      "⚙️ Настройки"),
        BotCommand("discussed",     "✅ Обсуждённые книги"),
        BotCommand("edit",          "✏️ Редактировать запись"),
        BotCommand("delete",        "🗑 Удалить книгу"),
        BotCommand("markdiscussed", "📌 Отметить как обсуждённую (админ)"),
        BotCommand("help",          "❓ Показать помощь"),
        BotCommand("cancel",        "❌ Отменить действие"),
    ],
}


async def set_user_commands(bot, update: "Update", lang: str) -> None:
    """Set the command menu for a specific user in their chosen language.
    Uses BotCommandScopeChatMember for groups, BotCommandScopeChat for private."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        if update.effective_chat.type == "private":
            scope = BotCommandScopeChat(chat_id=chat_id)
            await bot.delete_my_commands(scope=scope)
            await bot.set_my_commands(COMMANDS[lang], scope=scope)
        else:
            scope = BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
            await bot.delete_my_commands(scope=scope)
            await bot.set_my_commands(COMMANDS[lang], scope=scope)
    except Exception as e:
        logger.warning(f"Could not set commands for user {user_id}: {e}")


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    notify = db_get_user_setting(user_id, "notify_new_books")
    
    # -1 means not set, we'll treat it as Off (0) for the UI if they just run /settings
    # but the logic for /list will still trigger the opt-in if it's -1.
    val_str = tr(ctx, "settings_notify_on" if notify == 1 else "settings_notify_off")
    
    text = f"{tr(ctx, 'settings_title')}\n\n{tr(ctx, 'settings_notify_label')} {val_str}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(ctx, "settings_notify_btn"), callback_data="settings:toggle_notify")],
        [InlineKeyboardButton(tr(ctx, "settings_lang_btn"), callback_data="settings:toggle_lang")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=PM)


async def settings_choice_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split(":")
    
    if data[1] == "toggle_notify":
        await query.answer()
        current = db_get_user_setting(user_id, "notify_new_books")
        new_val = 1 if current <= 0 else 0
        db_set_user_setting(user_id, "notify_new_books", new_val)
        
        val_str = tr(ctx, "settings_notify_on" if new_val == 1 else "settings_notify_off")
        text = f"{tr(ctx, 'settings_title')}\n\n{tr(ctx, 'settings_notify_label')} {val_str}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(tr(ctx, "settings_notify_btn"), callback_data="settings:toggle_notify")],
            [InlineKeyboardButton(tr(ctx, "settings_lang_btn"), callback_data="settings:toggle_lang")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=PM)
    elif data[1] == "toggle_lang":
        new_lang = "ru" if get_lang(ctx) == "en" else "en"
        ctx.user_data["lang"] = new_lang
        await set_user_commands(ctx.bot, update, new_lang)
        await query.answer(tr(ctx, "lang_set"))
        
        notify = db_get_user_setting(user_id, "notify_new_books")
        val_str = tr(ctx, "settings_notify_on" if notify == 1 else "settings_notify_off")
        text = f"{tr(ctx, 'settings_title')}\n\n{tr(ctx, 'settings_notify_label')} {val_str}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(tr(ctx, "settings_notify_btn"), callback_data="settings:toggle_notify")],
            [InlineKeyboardButton(tr(ctx, "settings_lang_btn"), callback_data="settings:toggle_lang")]
        ])
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


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await set_user_commands(ctx.bot, update, get_lang(ctx))
    await update.message.reply_text(tr(ctx, "welcome"), parse_mode=PM)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr(ctx, "list_all_btn"), callback_data="list:all"),
            InlineKeyboardButton(tr(ctx, "list_unvoted_btn"), callback_data="list:unvoted"),
        ]
    ])
    await update.message.reply_text(
        tr(ctx, "list_prompt"),
        reply_markup=keyboard,
        parse_mode=PM
    )


async def list_choice_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(tr(ctx, "notify_optin_yes"), callback_data="settings:optin:1")],
            [InlineKeyboardButton(tr(ctx, "notify_optin_no"), callback_data="settings:optin:0")]
        ])
        await query.edit_message_text(tr(ctx, "notify_optin_prompt"), reply_markup=keyboard, parse_mode=PM)
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
                # User has voted on everything
                text = "✅ " + ("You've voted on all books!" if lang == "en" else "Вы проголосовали за все книги!")
        else:
            text = tr(ctx, "no_undiscussed")
        
        try:
            await query.edit_message_text(text, parse_mode=PM)
        except Exception as e:
            if "Message to edit not found" in str(e):
                await ctx.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode=PM)
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
        await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=book_card(book, lang, user_vote=uv),
            parse_mode=PM,
            reply_markup=score_keyboard(book["id"], lang, uv),
        )


async def cmd_discussed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(book_card(book, lang, user_vote=uv), parse_mode=PM)


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    books = db_get_books(discussed=False)
    if not books:
        await update.message.reply_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
        return

    # Show top 5, but if there's a tie for the 5th place, show all tied books.
    # Sorting is already done in db_get_books by (avg_score DESC, vote_count DESC, added_at DESC)
    top_books = []
    for i, book in enumerate(books):
        if i < 5:
            top_books.append(book)
        else:
            # Check if this book has the same score and vote count as the 5th one (index 4)
            fifth = books[4]
            if book["avg_score"] == fifth["avg_score"] and book["vote_count"] == fifth["vote_count"]:
                top_books.append(book)
            else:
                break

    lines = [tr(ctx, "top_title")]
    for i, book in enumerate(top_books, 1):
        fiction_label = T[lang]["fiction_label"] if book["fiction"] else T[lang]["nonfiction_label"]
        lines.append(
            f"{i}. <b>{h(book['title'])}</b> — {h(book['author'])}\n"
            f"   {h(fiction_label)}  •  {h(str(book['pages']))} {h(T[lang]['pages_label'])}\n"
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
    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(ctx, "score_calc_btn"), callback_data="score_calc_info")
    ]])
    await update.message.reply_text(
        "---", # Visual separator or just a small text
        reply_markup=reply_markup,
        parse_mode=PM
    )


async def score_calc_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer(
        text=tr(ctx, "score_calc_info"),
        show_alert=True
    )


# ── /add conversation ──────────────────────────────────────────────────────────
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_book"] = {}
    await update.message.reply_text(tr(ctx, "ask_title"), parse_mode=PM)
    return ADDING_TITLE


async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_book"]["title"] = update.message.text.strip()
    await update.message.reply_text(tr(ctx, "ask_author"), parse_mode=PM)
    return ADDING_AUTHOR


async def add_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_book"]["author"] = update.message.text.strip()
    await update.message.reply_text(tr(ctx, "ask_pages"), parse_mode=PM)
    return ADDING_PAGES


async def add_pages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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


async def add_fiction_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, value = query.data.split(":")
    ctx.user_data["new_book"]["fiction"] = value == "1"
    await query.edit_message_text(tr(ctx, "ask_review"), parse_mode=PM)
    return ADDING_REVIEW


async def add_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not is_valid_url(text):
        await update.message.reply_text(tr(ctx, "invalid_review"), parse_mode=PM)
        return ADDING_REVIEW
    ctx.user_data["new_book"]["review_link"] = text
    await update.message.reply_text(tr(ctx, "ask_desc"), parse_mode=PM)
    return ADDING_DESCRIPTION


async def add_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    text = update.message.text.strip() if update.message and update.message.text else ""
    desc = "" if text == "/skip" else text
    
    if "new_book" not in ctx.user_data:
        # Should not happen in normal conversation, but could if user sends message after timeout
        logger.warning(f"User {update.effective_user.id} tried to add description but 'new_book' is missing.")
        await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END

    nb = ctx.user_data["new_book"]
    user = update.effective_user
    book_id = db_add_book(
        nb["title"], nb["author"], nb["pages"], nb["fiction"],
        nb["review_link"], desc, user.id, user.full_name, user.username,
    )
    book = db_get_book(book_id)
    
    # Mention the 10-minute delay in the confirmation message
    confirm_text = f"{tr(ctx, 'book_added')}\n\n{book_card(book, lang)}{tr(ctx, 'new_book_delay_note')}"
    
    await update.message.reply_text(confirm_text, parse_mode=PM)
    ctx.user_data.pop("new_book", None)
    
    # Schedule notifications for others
    if ctx.job_queue:
        ctx.job_queue.run_once(
            notify_new_book_job,
            when=600, # 10 minutes
            data={"book_id": book_id, "adder_id": user.id},
            name=f"notify_book_{book_id}"
        )
    else:
        logger.error(
            "JobQueue is None — notifications will not be sent.\n"
            "Fix: pip install \"python-telegram-bot[job-queue]\"\n"
            "Then restart the bot."
        )
    
    return ConversationHandler.END


async def notify_new_book_job(ctx: ContextTypes.DEFAULT_TYPE):
    """Fired 10 minutes after a book is added. Sends a card to all opted-in users."""
    book_id  = ctx.job.data["book_id"]
    adder_id = ctx.job.data["adder_id"]

    book = db_get_book(book_id)
    if not book:
        logger.info(f"notify_new_book_job: book {book_id} no longer exists, skipping.")
        return
    if book["discussed"]:
        logger.info(f"notify_new_book_job: book {book_id} already discussed, skipping.")
        return

    user_ids = db_get_users_with_setting("notify_new_books", 1)
    logger.info(f"notify_new_book_job: notifying {len(user_ids)} user(s) about book {book_id}.")

    sent = 0
    for user_id in user_ids:
        if user_id == adder_id:
            continue
        # Resolve language from persistence; fall back to Russian
        user_data = ctx.application.user_data.get(user_id, {})
        lang = user_data.get("lang", "ru")
        try:
            uv   = db_get_user_vote(user_id, book_id)
            text = tr(lang, "new_book_notification") + book_card(book, lang, user_vote=uv)
            await ctx.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=PM,
                reply_markup=score_keyboard(book_id, lang, uv),
            )
            sent += 1
        except Exception as e:
            logger.warning(f"notify_new_book_job: failed to notify user {user_id}: {e}")

    logger.info(f"notify_new_book_job: done — sent to {sent} user(s).")


async def conv_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
    ctx.user_data.clear()
    return ConversationHandler.END


# ── /vote removed — voting now done inline in /list ──────────────────────────


async def vote_cast_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id, score = query.data.split(":")
    if book_id == "cancel":
        await query.edit_message_text(T[lang]["cancelled"])
        return
    book_id, score = int(book_id), int(score)
    db_cast_vote(query.from_user.id, book_id, score)
    book = db_get_book(book_id)
    user_id = query.from_user.id
    uv = db_get_user_vote(user_id, book_id)
    # Update the book card in-place with refreshed tally and user's vote marked
    await query.edit_message_text(
        book_card(book, lang, user_vote=uv),
        parse_mode=PM,
        reply_markup=score_keyboard(book_id, lang, uv),
    )


# ── /markdiscussed conversation (admin only) ───────────────────────────────────
async def cmd_markdiscussed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(tr(ctx, "admin_only"), parse_mode=PM)
        return ConversationHandler.END
    books = db_get_books(discussed=False)
    if not books:
        await update.message.reply_text(tr(ctx, "no_unmark"), parse_mode=PM)
        return ConversationHandler.END
    await update.message.reply_text(
        tr(ctx, "choose_mark"),
        reply_markup=books_keyboard(books, "mark_pick", tr(ctx, "cancel_btn")),
    )
    return MARKING_CHOOSE


async def mark_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(T[lang]["cancelled"])
        return ConversationHandler.END
    ctx.user_data["mark_book_id"] = int(book_id)
    await query.edit_message_text(tr(ctx, "ask_discuss_date"), parse_mode=PM)
    return MARKING_DATE


async def mark_date_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    text = update.message.text.strip()
    if text == "/today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    else:
        date_str = parse_date(text)
        if not date_str:
            await update.message.reply_text(tr(ctx, "invalid_date"), parse_mode=PM)
            return MARKING_DATE
    book_id = ctx.user_data.pop("mark_book_id")
    db_mark_discussed(book_id, date_str)
    book = db_get_book(book_id)
    await update.message.reply_text(
        T[lang]["marked_discussed"].format(title=h(book["title"]), date=h(date_str)),
        parse_mode=PM,
    )
    return ConversationHandler.END


# ── /edit — sequential field-by-field editor ──────────────────────────────────
# Fields edited in order: title, author, pages, fiction, review_link, description
EDIT_FIELDS = ["title", "author", "pages", "fiction", "review_link", "description"]


def edit_field_key(field):
    return f"field_{field.replace('_link', '').replace('review', 'review')}"


def edit_current_value(book, field, lang):
    """Return human-readable current value for a field."""
    if field == "fiction":
        return T[lang]["fiction_label"] if book["fiction"] else T[lang]["nonfiction_label"]
    if field == "review_link":
        return book["review_link"] or ("—" if lang == "en" else "—")
    if field == "description":
        return book["description"] or ("—" if lang == "en" else "—")
    return str(book[field])


def edit_yn_keyboard(lang):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(T[lang]["edit_yes_btn"], callback_data="edit_yn:yes"),
        InlineKeyboardButton(T[lang]["edit_no_btn"],  callback_data="edit_yn:no"),
    ]])


def edit_fiction_keyboard(lang):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(T[lang]["fiction_btn"],    callback_data="edit_fiction:1"),
        InlineKeyboardButton(T[lang]["nonfiction_btn"], callback_data="edit_fiction:0"),
    ]])


async def _ask_edit_field(update_or_query, ctx, is_callback=False):
    """Ask user about the next field to edit. Returns next state or END."""
    lang = get_lang(ctx)
    fields = ctx.user_data.get("edit_fields", [])
    if not fields:
        # All fields done — save and show result
        book_id = ctx.user_data.pop("edit_book_id")
        changes = ctx.user_data.pop("edit_changes", {})
        for field, value in changes.items():
            db_update_book_field(book_id, field, value)
        book = db_get_book(book_id)
        text = f"{T[lang]['edit_done']}\n\n{book_card(book, lang)}"
        if is_callback:
            await update_or_query.edit_message_text(text, parse_mode=PM)
        else:
            await update_or_query.message.reply_text(text, parse_mode=PM)
        ctx.user_data.pop("edit_fields", None)
        return ConversationHandler.END

    field = fields[0]
    book = db_get_book(ctx.user_data["edit_book_id"])
    field_name = T[lang][f"field_{field}" if field != "review_link" else "field_review"]
    current    = edit_current_value(book, field, lang)
    text       = T[lang]["edit_field_prompt"].format(field=field_name, value=h(current))

    if is_callback:
        await update_or_query.edit_message_text(
            text, parse_mode=PM, reply_markup=edit_yn_keyboard(lang)
        )
    else:
        await update_or_query.message.reply_text(
            text, parse_mode=PM, reply_markup=edit_yn_keyboard(lang)
        )
    return EDITING_FIELD


async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    uname   = update.effective_user.username
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


async def edit_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(T[lang]["cancelled"])
        return ConversationHandler.END
    book_id = int(book_id)
    book    = db_get_book(book_id)
    if not can_modify(query.from_user.id, book, query.from_user.username):
        await query.edit_message_text(T[lang]["no_permission"], parse_mode=PM)
        return ConversationHandler.END
    ctx.user_data["edit_book_id"] = book_id
    ctx.user_data["edit_fields"]  = list(EDIT_FIELDS)
    ctx.user_data["edit_changes"] = {}
    return await _ask_edit_field(query, ctx, is_callback=True)


async def edit_yn_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """User clicked Yes or No on whether to edit the current field."""
    query = update.callback_query
    await query.answer()
    lang    = get_lang(ctx)
    _, ans  = query.data.split(":")
    field   = ctx.user_data["edit_fields"][0]

    if ans == "no":
        ctx.user_data["edit_fields"].pop(0)
        return await _ask_edit_field(query, ctx, is_callback=True)

    # ans == "yes" — ask for new value
    if field == "fiction":
        await query.edit_message_text(
            T[lang]["edit_ask_new"].format(
                field=T[lang]["field_fiction"]
            ),
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


async def edit_fiction_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """User picked Fiction/Non-fiction via inline button."""
    query = update.callback_query
    await query.answer()
    _, value = query.data.split(":")
    ctx.user_data["edit_changes"]["fiction"] = int(value)
    ctx.user_data["edit_fields"].pop(0)
    return await _ask_edit_field(query, ctx, is_callback=True)


async def edit_value_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """User typed a new value for the current field."""
    lang  = get_lang(ctx)
    text  = update.message.text.strip()
    field = ctx.user_data["edit_fields"][0]

    # Validate
    if field == "pages":
        if not text.isdigit() or int(text) <= 0:
            await update.message.reply_text(tr(ctx, "edit_invalid_pages"), parse_mode=PM)
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
async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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


async def delete_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(T[lang]["cancelled"])
        return ConversationHandler.END
    book_id = int(book_id)
    book = db_get_book(book_id)
    if not can_modify(query.from_user.id, book, query.from_user.username):
        await query.edit_message_text(T[lang]["no_permission"], parse_mode=PM)
        return ConversationHandler.END
    title = book["title"]
    db_delete_book(book_id)
    await query.edit_message_text(
        T[lang]["deleted"].format(title=h(title)), parse_mode=PM
    )
    return ConversationHandler.END


async def bot_notify_startup(app: Application):
    """Notify first admin that bot has started, and set default command menu."""
    # Register the default (Russian) command menu for users who haven't set a language yet
    try:
        await app.bot.delete_my_commands(scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(COMMANDS["ru"], scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning(f"Could not set default commands: {e}")
    if not ADMIN_IDS:
        return
    admin_id = ADMIN_IDS[0]
    try:
        # We don't have user_data here, default to English for system notifications.
        await app.bot.send_message(
            chat_id=admin_id,
            text=T["en"]["bot_started"],
            parse_mode=PM
        )
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")


async def bot_notify_shutdown(app: Application):
    """Notify first admin that bot is shutting down."""
    if not ADMIN_IDS:
        return
    admin_id = ADMIN_IDS[0]
    try:
        await app.bot.send_message(
            chat_id=admin_id,
            text=T["en"]["bot_stopped"],
            parse_mode=PM
        )
    except Exception as e:
        logger.error(f"Failed to send shutdown notification: {e}")



# ── Chat membership gate ───────────────────────────────────────────────────────
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
    try:
        member = await ctx.bot.get_chat_member(ALLOWED_CHAT_ID, user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except Exception as e:
        logger.warning(f"Membership check failed for user {user_id}: {e}")
        return False


async def membership_gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Block users not in the allowed chat and tell them why."""
    if await _check_membership(update, ctx):
        return
    user_id = update.effective_user.id if update.effective_user else "?"
    logger.info(f"Blocked user {user_id} — not a member of chat {ALLOWED_CHAT_ID}")
    lang = get_lang(ctx) if ctx.user_data else "ru"
    text = T[lang]["not_member"].format(chat=h(ALLOWED_CHAT_NAME))
    try:
        if update.callback_query:
            await update.callback_query.answer(
                ALLOWED_CHAT_NAME + " — members only", show_alert=True
            )
        elif update.message:
            await update.message.reply_text(text, parse_mode=PM)
    except Exception as e:
        logger.warning(f"Could not send not-member message to {user_id}: {e}")
    raise ApplicationHandlerStop


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    init_db()
    persistence = PicklePersistence(file_path="bot_persistence")
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
            "Fix: pip install \"python-telegram-bot[job-queue]\""
        )

    # Gate: silently block users not in the allowed chat (runs before all handlers)
    app.add_handler(TypeHandler(Update, membership_gate), group=-1)

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add)],
        states={
            ADDING_TITLE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            ADDING_AUTHOR:      [MessageHandler(filters.TEXT & ~filters.COMMAND, add_author)],
            ADDING_PAGES:       [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pages)],
            ADDING_FICTION:     [CallbackQueryHandler(add_fiction_cb, pattern=r"^fiction:")],
            ADDING_REVIEW:      [MessageHandler(filters.TEXT & ~filters.COMMAND, add_review)],
            ADDING_DESCRIPTION: [MessageHandler(filters.TEXT, add_description)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        per_message=False,
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("markdiscussed", cmd_markdiscussed)],
        states={
            MARKING_CHOOSE: [CallbackQueryHandler(mark_pick_cb, pattern=r"^mark_pick:")],
            MARKING_DATE:   [MessageHandler(filters.TEXT, mark_date_handler)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        per_message=False,
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("edit", cmd_edit)],
        states={
            EDITING_CHOOSE: [CallbackQueryHandler(edit_pick_cb, pattern=r"^edit_pick:")],
            EDITING_FIELD:  [
                CallbackQueryHandler(edit_yn_cb,      pattern=r"^edit_yn:"),
                CallbackQueryHandler(edit_fiction_cb, pattern=r"^edit_fiction:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        per_message=False,
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete", cmd_delete)],
        states={
            DELETING_CHOOSE: [CallbackQueryHandler(delete_pick_cb, pattern=r"^del_pick:")],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        per_message=False,
    ))

    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("help",           cmd_help))
    app.add_handler(CommandHandler("list",           cmd_list))
    app.add_handler(CommandHandler("settings",       cmd_settings))
    app.add_handler(CommandHandler("top",            cmd_top))
    app.add_handler(CommandHandler("discussed",      cmd_discussed))

    app.add_handler(CallbackQueryHandler(list_choice_cb, pattern=r"^list:"))
    app.add_handler(CallbackQueryHandler(settings_choice_cb, pattern=r"^settings:"))
    app.add_handler(CallbackQueryHandler(vote_cast_cb, pattern=r"^vote_cast:"))
    app.add_handler(CallbackQueryHandler(score_calc_cb, pattern=r"^score_calc_info$"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
