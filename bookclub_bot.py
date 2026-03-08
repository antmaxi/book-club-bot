#!/usr/bin/env python3
"""
Book Club Telegram Bot — EN/RU bilingual
=========================================
Commands:
  /start / /help  - Welcome + command list
  /language       - Switch language (EN ↔ RU)
  /add            - Add a new book
  /list           - List all books with ratings
  /vote           - Rate a book (1–5 stars)
  /edit           - Edit any book's description
  /delete         - Delete a book
  /top            - Top rated books
  /cancel         - Cancel current action
"""

import logging
import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DB_PATH = "bookclub.db"

# Conversation states
ADDING_TITLE, ADDING_AUTHOR, ADDING_DESCRIPTION = range(3)
EDITING_CHOOSE, EDITING_DESCRIPTION = range(3, 5)
DELETING_CHOOSE = 5

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Translations ───────────────────────────────────────────────────────────────
T = {
    "en": {
        "welcome": (
            "📚 *Welcome to the Book Club Bot\\!*\n\n"
            "➕ /add — Add a book\n"
            "📋 /list — See all books\n"
            "⭐ /vote — Rate a book\n"
            "✏️ /edit — Edit a description\n"
            "🗑 /delete — Delete a book\n"
            "🏆 /top — Top rated books\n"
            "🌐 /language — Switch to Russian\n"
            "❓ /help — Show this message"
        ),
        "lang_set": "🇬🇧 Language set to English\\.",
        "ask_title": "📖 What is the *title* of the book?",
        "ask_author": "✍️ Who is the *author*?",
        "ask_desc": "📝 Add a *description* \\(or /skip to leave empty\\):",
        "book_added": "✅ Book added\\!",
        "no_books": "📭 No books yet\\. Use /add to add one\\!",
        "no_votes": "No votes yet\\. Use /vote to start rating\\!",
        "no_books_edit": "📭 No books to edit yet\\.",
        "no_books_delete": "📭 No books to delete yet\\.",
        "cancelled": "❌ Cancelled\\.",
        "choose_vote": "⭐ Choose a book to rate:",
        "choose_edit": "✏️ Choose a book to edit:",
        "choose_delete": "🗑 Choose a book to delete:",
        "your_vote": "Your current rating",
        "none_vote": "none",
        "rate_book": "⭐ Rate *{title}*",
        "desc_updated": "✅ Description updated\\!",
        "top_title": "🏆 *Top Books*\n\n",
        "added_by": "Added by",
        "cancel_btn": "❌ Cancel",
        "editing": "✏️ Editing *{title}*\n\nCurrent description:\n_{desc}_\n\nSend the new description:",
        "deleted": "🗑 *{title}* has been deleted\\.",
        "votes_label": lambda n: f"({n} vote{'s' if n != 1 else ''})",
    },
    "ru": {
        "welcome": (
            "📚 *Добро пожаловать в Книжный клуб\\!*\n\n"
            "➕ /add — Добавить книгу\n"
            "📋 /list — Список книг\n"
            "⭐ /vote — Оценить книгу\n"
            "✏️ /edit — Редактировать описание\n"
            "🗑 /delete — Удалить книгу\n"
            "🏆 /top — Топ книг\n"
            "🌐 /language — Switch to English\n"
            "❓ /help — Показать это сообщение"
        ),
        "lang_set": "🇷🇺 Язык установлен: Русский\\.",
        "ask_title": "📖 Как называется книга \\(*название*\\)?",
        "ask_author": "✍️ Кто *автор*?",
        "ask_desc": "📝 Добавьте *описание* \\(или /skip, чтобы пропустить\\):",
        "book_added": "✅ Книга добавлена\\!",
        "no_books": "📭 Книг пока нет\\. Используйте /add, чтобы добавить\\!",
        "no_votes": "Оценок пока нет\\. Используйте /vote\\!",
        "no_books_edit": "📭 Нет книг для редактирования\\.",
        "no_books_delete": "📭 Нет книг для удаления\\.",
        "cancelled": "❌ Отменено\\.",
        "choose_vote": "⭐ Выберите книгу для оценки:",
        "choose_edit": "✏️ Выберите книгу для редактирования:",
        "choose_delete": "🗑 Выберите книгу для удаления:",
        "your_vote": "Ваша текущая оценка",
        "none_vote": "нет",
        "rate_book": "⭐ Оцените *{title}*",
        "desc_updated": "✅ Описание обновлено\\!",
        "top_title": "🏆 *Топ книг*\n\n",
        "added_by": "Добавил",
        "cancel_btn": "❌ Отмена",
        "editing": "✏️ Редактирование *{title}*\n\nТекущее описание:\n_{desc}_\n\nОтправьте новое описание:",
        "deleted": "🗑 *{title}* удалена\\.",
        "votes_label": lambda n: (
            f"({n} оценка)" if n == 1 else
            f"({n} оценки)" if 2 <= n <= 4 else
            f"({n} оценок)"
        ),
    },
}


def get_lang(ctx):
    return ctx.user_data.get("lang", "en")


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
                description   TEXT DEFAULT '',
                added_by      INTEGER NOT NULL,
                added_by_name TEXT NOT NULL,
                added_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                stars   INTEGER NOT NULL,
                PRIMARY KEY (user_id, book_id),
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def db_add_book(title, author, description, user_id, user_name):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO books (title,author,description,added_by,added_by_name,added_at) VALUES (?,?,?,?,?,?)",
            (title, author, description, user_id, user_name, datetime.now().isoformat()),
        )
        return cur.lastrowid


def db_get_books():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT b.*,
                   COALESCE(AVG(v.stars), 0) AS avg_stars,
                   COUNT(v.user_id)           AS vote_count
            FROM books b
            LEFT JOIN votes v ON b.id = v.book_id
            GROUP BY b.id
            ORDER BY avg_stars DESC, b.added_at DESC
        """).fetchall()


def db_get_book(book_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT b.*,
                   COALESCE(AVG(v.stars), 0) AS avg_stars,
                   COUNT(v.user_id)           AS vote_count
            FROM books b
            LEFT JOIN votes v ON b.id = v.book_id
            WHERE b.id = ?
            GROUP BY b.id
        """, (book_id,)).fetchone()


def db_update_description(book_id, description):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE books SET description=? WHERE id=?", (description, book_id))
        conn.commit()


def db_delete_book(book_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        conn.commit()


def db_cast_vote(user_id, book_id, stars):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO votes (user_id,book_id,stars) VALUES (?,?,?) "
            "ON CONFLICT(user_id,book_id) DO UPDATE SET stars=excluded.stars",
            (user_id, book_id, stars),
        )
        conn.commit()


def db_get_user_vote(user_id, book_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT stars FROM votes WHERE user_id=? AND book_id=?", (user_id, book_id)
        ).fetchone()
        return row[0] if row else None


# ── Formatting helpers ─────────────────────────────────────────────────────────
def escape(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def stars_display(avg, count, lang="en"):
    filled = round(avg)
    bar = "⭐" * filled + "☆" * (5 - filled)
    return f"{bar} {avg:.1f}/5 {T[lang]['votes_label'](count)}"


def book_card(book, lang="en"):
    lines = [
        f"📖 *{escape(book['title'])}*",
        f"✍️ {escape(book['author'])}",
        stars_display(book["avg_stars"], book["vote_count"], lang),
    ]
    if book["description"]:
        lines += ["", f"_{escape(book['description'])}_"]
    lines += ["", f"_{escape(T[lang]['added_by'])}: {escape(book['added_by_name'])}_"]
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


def stars_keyboard(book_id, cancel_label, current=None):
    row = [
        InlineKeyboardButton(
            "⭐" * i + (" ✓" if current == i else ""),
            callback_data=f"vote_cast:{book_id}:{i}"
        )
        for i in range(1, 6)
    ]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton(cancel_label, callback_data="vote_cast:cancel:0")]])


# ── Handlers ───────────────────────────────────────────────────────────────────
async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    new_lang = "ru" if get_lang(ctx) == "en" else "en"
    ctx.user_data["lang"] = new_lang
    await update.message.reply_text(tr(ctx, "lang_set"), parse_mode="MarkdownV2")


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tr(ctx, "welcome"), parse_mode="MarkdownV2")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    books = db_get_books()
    if not books:
        await update.message.reply_text(tr(ctx, "no_books"), parse_mode="MarkdownV2")
        return
    for book in books:
        await update.message.reply_text(book_card(book, lang), parse_mode="MarkdownV2")


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    voted = [b for b in db_get_books() if b["vote_count"] > 0]
    if not voted:
        await update.message.reply_text(tr(ctx, "no_votes"), parse_mode="MarkdownV2")
        return
    text = tr(ctx, "top_title")
    for i, book in enumerate(voted[:5], 1):
        text += f"{i}\\. *{escape(book['title'])}* — {escape(book['author'])}\n"
        text += f"   {stars_display(book['avg_stars'], book['vote_count'], lang)}\n\n"
    await update.message.reply_text(text, parse_mode="MarkdownV2")


# /add
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tr(ctx, "ask_title"), parse_mode="MarkdownV2")
    return ADDING_TITLE

async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_book"] = {"title": update.message.text.strip()}
    await update.message.reply_text(tr(ctx, "ask_author"), parse_mode="MarkdownV2")
    return ADDING_AUTHOR

async def add_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_book"]["author"] = update.message.text.strip()
    await update.message.reply_text(tr(ctx, "ask_desc"), parse_mode="MarkdownV2")
    return ADDING_DESCRIPTION

async def add_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    text = update.message.text.strip()
    desc = "" if text == "/skip" else text
    nb = ctx.user_data["new_book"]
    user = update.effective_user
    book_id = db_add_book(nb["title"], nb["author"], desc, user.id, user.full_name)
    book = db_get_book(book_id)
    await update.message.reply_text(
        f"{tr(ctx, 'book_added')}\n\n{book_card(book, lang)}", parse_mode="MarkdownV2"
    )
    ctx.user_data.pop("new_book", None)
    return ConversationHandler.END

async def conv_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tr(ctx, "cancelled"), parse_mode="MarkdownV2")
    ctx.user_data.clear()
    return ConversationHandler.END


# /vote
async def cmd_vote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    books = db_get_books()
    if not books:
        await update.message.reply_text(tr(ctx, "no_books"), parse_mode="MarkdownV2")
        return
    await update.message.reply_text(
        tr(ctx, "choose_vote"),
        reply_markup=books_keyboard(books, "vote_pick", tr(ctx, "cancel_btn")),
    )

async def vote_pick_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id = query.data.split(":", 1)
    if book_id == "cancel":
        await query.edit_message_text(T[lang]["cancelled"].replace("\\", ""))
        return
    book_id = int(book_id)
    book = db_get_book(book_id)
    current = db_get_user_vote(query.from_user.id, book_id)
    current_str = ("⭐" * current) if current else T[lang]["none_vote"]
    await query.edit_message_text(
        f"{T[lang]['rate_book'].format(title=escape(book['title']))}\n"
        f"{escape(T[lang]['your_vote'])}: {escape(current_str)}",
        reply_markup=stars_keyboard(book_id, T[lang]["cancel_btn"], current),
        parse_mode="MarkdownV2",
    )

async def vote_cast_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(ctx)
    _, book_id, stars = query.data.split(":")
    if book_id == "cancel":
        await query.edit_message_text(T[lang]["cancelled"].replace("\\", ""))
        return
    book_id, stars = int(book_id), int(stars)
    db_cast_vote(query.from_user.id, book_id, stars)
    book = db_get_book(book_id)
    await query.edit_message_text(
        f"✅ {'⭐' * stars} *{escape(book['title'])}*\\!\n\n"
        f"{stars_display(book['avg_stars'], book['vote_count'], lang)}",
        parse_mode="MarkdownV2",
    )


# /edit
async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    books = db_get_books()
    if not books:
        await update.message.reply_text(tr(ctx, "no_books_edit"), parse_mode="MarkdownV2")
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
        await query.edit_message_text(T[lang]["cancelled"].replace("\\", ""))
        return ConversationHandler.END
    book_id = int(book_id)
    ctx.user_data["edit_book_id"] = book_id
    book = db_get_book(book_id)
    no_desc = "none" if lang == "en" else "нет"
    await query.edit_message_text(
        T[lang]["editing"].format(
            title=escape(book["title"]),
            desc=escape(book["description"] or no_desc),
        ),
        parse_mode="MarkdownV2",
    )
    return EDITING_DESCRIPTION

async def edit_description_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(ctx)
    book_id = ctx.user_data.get("edit_book_id")
    db_update_description(book_id, update.message.text.strip())
    book = db_get_book(book_id)
    await update.message.reply_text(
        f"{tr(ctx, 'desc_updated')}\n\n{book_card(book, lang)}", parse_mode="MarkdownV2"
    )
    ctx.user_data.pop("edit_book_id", None)
    return ConversationHandler.END


# /delete
async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    books = db_get_books()
    if not books:
        await update.message.reply_text(tr(ctx, "no_books_delete"), parse_mode="MarkdownV2")
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
        await query.edit_message_text(T[lang]["cancelled"].replace("\\", ""))
        return ConversationHandler.END
    book_id = int(book_id)
    book = db_get_book(book_id)
    title = book["title"]
    db_delete_book(book_id)
    await query.edit_message_text(
        T[lang]["deleted"].format(title=escape(title)), parse_mode="MarkdownV2"
    )
    return ConversationHandler.END


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add)],
        states={
            ADDING_TITLE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            ADDING_AUTHOR:      [MessageHandler(filters.TEXT & ~filters.COMMAND, add_author)],
            ADDING_DESCRIPTION: [MessageHandler(filters.TEXT, add_description)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("edit", cmd_edit)],
        states={
            EDITING_CHOOSE:      [CallbackQueryHandler(edit_pick_cb, pattern=r"^edit_pick:")],
            EDITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_description_handler)],
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

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("list",     cmd_list))
    app.add_handler(CommandHandler("top",      cmd_top))
    app.add_handler(CommandHandler("vote",     cmd_vote))
    app.add_handler(CommandHandler("language", cmd_language))

    app.add_handler(CallbackQueryHandler(vote_pick_cb, pattern=r"^vote_pick:"))
    app.add_handler(CallbackQueryHandler(vote_cast_cb, pattern=r"^vote_cast:"))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
