#!/usr/bin/env python3
"""
Book Club Telegram Bot — EN/RU bilingual
=========================================
Fields per book:
  - title, author, pages, fiction, review_link, description
  - added_at, added_by
  - discussed (flag, admin-only), discussed_at (date)

Commands:
  /start / /help   - Welcome + command list
  /language        - Switch language (EN <-> RU)
  /add             - Add a new book
  /list            - List all undiscussed books
  /edit            - Edit a book's description (owner/admin only)
  /delete          - Delete a book (owner/admin only)
  /top             - Top rated undiscussed books
  /discussed       - List books already discussed (admin-only to mark)
  /markdiscussed   - Admin: mark a book as discussed (with date)
  /cancel          - Cancel current action
"""

import logging
import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat, BotCommandScopeChatMember
from telegram.ext import (
    Application,
    PicklePersistence,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS  = set(
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
)
DB_PATH = "bookclub.db"

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Translations ───────────────────────────────────────────────────────────────
T = {
    "en": {
        "welcome": (
            "📚 <b>Welcome to the Book Club Bot!</b>\n\n"
            "➕ /add — Add a book\n"
            "📋 /list — See all books\n"
            "✏️ /edit — Edit a description\n"
            "🗑 /delete — Delete a book\n"
            "🏆 /top — Top rated books\n"
            "✅ /discussed — Books already discussed\n"
            "📌 /markdiscussed — Mark a book as discussed (admin)\n"
            "🌐 /language — Switch to Russian\n"
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
        "top_title":           "🏆 <b>Top Books</b>\n\n",
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
    },
    "ru": {
        "welcome": (
            "📚 <b>Добро пожаловать в Книжный клуб!</b>\n\n"
            "➕ /add — Добавить книгу\n"
            "📋 /list — Список книг\n"
            "✏️ /edit — Редактировать описание\n"
            "🗑 /delete — Удалить книгу\n"
            "🏆 /top — Топ книг\n"
            "✅ /discussed — Обсуждённые книги\n"
            "📌 /markdiscussed — Отметить книгу как обсуждённую (админ)\n"
            "🌐 /language — Switch to English\n"
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
        "top_title":           "🏆 <b>Топ книг</b>\n\n",
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


def db_get_books(discussed=False):
    """Return books. discussed=False → undiscussed, discussed=True → discussed."""
    flag = 1 if discussed else 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            _books_query("WHERE b.discussed = ?",
                         "b.discussed_at DESC" if discussed else "avg_score DESC, vote_count DESC, b.added_at DESC"),
            (flag,)
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
        BotCommand("discussed",     "✅ Books already discussed"),
        BotCommand("edit",          "✏️ Edit a book description"),
        BotCommand("delete",        "🗑 Delete a book"),
        BotCommand("markdiscussed", "📌 Mark as discussed (admin)"),
        BotCommand("language",      "🌐 Switch to Russian"),
        BotCommand("help",          "❓ Show help"),
        BotCommand("cancel",        "❌ Cancel current action"),
    ],
    "ru": [
        BotCommand("add",           "➕ Добавить книгу"),
        BotCommand("list",          "📋 Список книг и голосование"),
        BotCommand("top",           "🏆 Топ книг"),
        BotCommand("discussed",     "✅ Обсуждённые книги"),
        BotCommand("edit",          "✏️ Редактировать описание"),
        BotCommand("delete",        "🗑 Удалить книгу"),
        BotCommand("markdiscussed", "📌 Отметить как обсуждённую (админ)"),
        BotCommand("language",      "🌐 Switch to English"),
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
            await bot.set_my_commands(
                COMMANDS[lang],
                scope=BotCommandScopeChat(chat_id=chat_id),
            )
        else:
            await bot.set_my_commands(
                COMMANDS[lang],
                scope=BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id),
            )
    except Exception as e:
        logger.warning(f"Could not set commands for user {user_id}: {e}")


async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    new_lang = "ru" if get_lang(ctx) == "en" else "en"
    ctx.user_data["lang"] = new_lang
    await set_user_commands(ctx.bot, update, new_lang)
    await update.message.reply_text(tr(ctx, "lang_set"), parse_mode=PM)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await set_user_commands(ctx.bot, update, get_lang(ctx))
    await update.message.reply_text(tr(ctx, "welcome"), parse_mode=PM)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    user_id = update.effective_user.id
    books = db_get_books(discussed=False)
    if not books:
        await update.message.reply_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
        return
    for book in books:
        uv = db_get_user_vote(user_id, book["id"])
        await update.message.reply_text(
            book_card(book, lang, user_vote=uv),
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
    books = db_get_books(discussed=False)[:5]
    if not books:
        await update.message.reply_text(tr(ctx, "no_undiscussed"), parse_mode=PM)
        return

    lines = [tr(ctx, "top_title")]
    for i, book in enumerate(books, 1):
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
    text = update.message.text.strip()
    desc = "" if text == "/skip" else text
    nb = ctx.user_data["new_book"]
    user = update.effective_user
    book_id = db_add_book(
        nb["title"], nb["author"], nb["pages"], nb["fiction"],
        nb["review_link"], desc, user.id, user.full_name, user.username,
    )
    book = db_get_book(book_id)
    await update.message.reply_text(
        f"{tr(ctx, 'book_added')}\n\n{book_card(book, lang)}", parse_mode=PM
    )
    ctx.user_data.pop("new_book", None)
    return ConversationHandler.END


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


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    init_db()
    persistence = PicklePersistence(filepath="bot_persistence")
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

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
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("markdiscussed", cmd_markdiscussed)],
        states={
            MARKING_CHOOSE: [CallbackQueryHandler(mark_pick_cb, pattern=r"^mark_pick:")],
            MARKING_DATE:   [MessageHandler(filters.TEXT, mark_date_handler)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
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
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete", cmd_delete)],
        states={
            DELETING_CHOOSE: [CallbackQueryHandler(delete_pick_cb, pattern=r"^del_pick:")],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    ))

    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("help",           cmd_help))
    app.add_handler(CommandHandler("list",           cmd_list))
    app.add_handler(CommandHandler("top",            cmd_top))
    app.add_handler(CommandHandler("discussed",      cmd_discussed))
    app.add_handler(CommandHandler("language",       cmd_language))

    app.add_handler(CallbackQueryHandler(vote_cast_cb, pattern=r"^vote_cast:"))

    # ── Register default command menu in Russian (fallback for all users) ───────
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        app.bot.set_my_commands(COMMANDS["ru"], scope=BotCommandScopeDefault())
    )

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
