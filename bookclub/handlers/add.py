from __future__ import annotations

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
from bookclub.db import db_add_book, db_get_book, find_similar_book_titles
from bookclub.i18n import PM, get_lang, s, tr
from bookclub.logging_setup import logger
from bookclub.notifications import schedule_new_book_notifications
from bookclub.ui import (
    book_card,
    fiction_keyboard,
    h,
    is_valid_url,
    parse_optional_creation_year,
    similar_title_confirm_keyboard,
    similar_title_warning_matches_text,
)

async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"] = {}
    await update.message.reply_text(tr(ctx, "ask_title"), parse_mode=PM)
    return ADDING_TITLE


async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    ctx.user_data["new_book"]["title"] = title
    lang = get_lang(ctx)
    similar = find_similar_book_titles(title)
    if similar:
        await update.message.reply_text(
            tr(
                ctx,
                "similar_title_warning",
                title=h(title),
                matches=similar_title_warning_matches_text(similar),
            ),
            reply_markup=similar_title_confirm_keyboard(lang),
            parse_mode=PM,
        )
        return ADDING_TITLE_CONFIRM
    await update.message.reply_text(tr(ctx, "ask_author"), parse_mode=PM)
    return ADDING_AUTHOR


async def add_title_similar_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, action = query.data.split(":", 1)
    if action == "no":
        ctx.user_data.pop("new_book", None)
        await query.edit_message_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END
    await query.edit_message_text(tr(ctx, "ask_author"), parse_mode=PM)
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
    await update.message.reply_text(tr(ctx, "ask_original_language"), parse_mode=PM)
    return ADDING_ORIGINAL_LANGUAGE


async def add_original_language(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip() if update.message and update.message.text else ""
    ctx.user_data["new_book"]["original_language"] = "" if text == "/skip" else text
    await update.message.reply_text(tr(ctx, "ask_creation_year"), parse_mode=PM)
    return ADDING_CREATION_YEAR


async def add_creation_year(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip() if update.message and update.message.text else ""
    try:
        year = parse_optional_creation_year(text)
    except ValueError:
        await update.message.reply_text(tr(ctx, "invalid_creation_year"), parse_mode=PM)
        return ADDING_CREATION_YEAR
    ctx.user_data["new_book"]["creation_year"] = year
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
        original_language=nb.get("original_language") or None,
        creation_year=nb.get("creation_year"),
    )
    if book_id is None:
        raise RuntimeError("db_add_book did not return a book id")
    book = db_get_book(book_id)
    if book is None:
        raise RuntimeError(f"book {book_id} missing immediately after insert")

    # Mention the delay in the confirmation message
    confirm_text = f"{tr(ctx, 'book_added')}\n\n{book_card(book, lang)}{tr(ctx, 'new_book_delay_note')}"

    await update.message.reply_text(confirm_text, parse_mode=PM)
    ctx.user_data.pop("new_book", None)

    schedule_new_book_notifications(ctx.job_queue, book_id, user.id)

    return ConversationHandler.END

