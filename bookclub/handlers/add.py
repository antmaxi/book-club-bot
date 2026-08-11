from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.config import (
    ADDING_AUTHOR,
    ADDING_CREATION_YEAR,
    ADDING_DESCRIPTION,
    ADDING_FICTION,
    ADDING_LANGUAGE_LEVEL,
    ADDING_ORIGINAL_LANGUAGE,
    ADDING_ORIGINAL_LANGUAGE_OTHER,
    ADDING_PAGES,
    ADDING_REVIEW,
    ADDING_TITLE,
    ADDING_TITLE_CONFIRM,
    language_level_prompt_enabled,
)
from bookclub.cefr import format_language_levels
from bookclub.original_languages import stored_original_language
from bookclub.db import db_add_book, db_get_book, find_similar_book_titles
from bookclub.handlers.add_flow import (
    build_add_prompt_text,
    send_add_prompt,
)
from bookclub.i18n import PM, get_lang, tr
from bookclub.logging_setup import logger
from bookclub.notifications import schedule_new_book_notifications
from bookclub.ui import (
    add_back_keyboard,
    book_card,
    cefr_levels_keyboard,
    h,
    is_valid_url,
    original_language_keyboard,
    parse_optional_creation_year,
    similar_title_confirm_keyboard,
    similar_title_warning_matches_text,
)

async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"] = {}
    return await send_add_prompt(update, ctx, ADDING_TITLE)


async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    ctx.user_data["new_book"]["title"] = title
    lang = get_lang(ctx)
    similar = find_similar_book_titles(title)
    if similar:
        ctx.user_data["add_state"] = ADDING_TITLE_CONFIRM
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
    return await send_add_prompt(update, ctx, ADDING_AUTHOR)


async def add_title_similar_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, action = query.data.split(":", 1)
    if action == "no":
        ctx.user_data.pop("new_book", None)
        ctx.user_data.pop("add_state", None)
        await query.edit_message_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END
    return await send_add_prompt(update, ctx, ADDING_AUTHOR, edit=True)


async def add_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"]["author"] = update.message.text.strip()
    return await send_add_prompt(update, ctx, ADDING_PAGES)


async def add_pages(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    lang = get_lang(ctx)
    nb = ctx.user_data["new_book"]
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text(
            f"{tr(ctx, 'invalid_pages')}\n\n{build_add_prompt_text(ctx, ADDING_PAGES, nb)}",
            reply_markup=add_back_keyboard(lang),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_PAGES
        return ADDING_PAGES
    ctx.user_data["new_book"]["pages"] = int(text)
    return await send_add_prompt(update, ctx, ADDING_FICTION)


async def add_fiction_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, value = query.data.split(":")
    ctx.user_data["new_book"]["fiction"] = value == "1"
    return await send_add_prompt(update, ctx, ADDING_REVIEW, edit=True)


async def add_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    lang = get_lang(ctx)
    nb = ctx.user_data["new_book"]
    if not is_valid_url(text):
        await update.message.reply_text(
            f"{tr(ctx, 'invalid_review')}\n\n{build_add_prompt_text(ctx, ADDING_REVIEW, nb)}",
            reply_markup=add_back_keyboard(lang),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_REVIEW
        return ADDING_REVIEW
    ctx.user_data["new_book"]["review_link"] = text
    return await send_add_prompt(update, ctx, ADDING_ORIGINAL_LANGUAGE)


async def add_original_language_skip(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    ctx.user_data["new_book"]["original_language"] = ""
    return await send_add_prompt(update, ctx, ADDING_CREATION_YEAR)


async def add_original_language_cb(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    _, action = query.data.split(":", 1)
    if action == "skip":
        ctx.user_data["new_book"]["original_language"] = ""
        return await send_add_prompt(update, ctx, ADDING_CREATION_YEAR, edit=True)
    if action == "other":
        ctx.user_data["add_state"] = ADDING_ORIGINAL_LANGUAGE_OTHER
        await query.edit_message_text(
            build_add_prompt_text(
                ctx, ADDING_ORIGINAL_LANGUAGE_OTHER, ctx.user_data["new_book"]
            ),
            reply_markup=add_back_keyboard(get_lang(ctx)),
            parse_mode=PM,
        )
        return ADDING_ORIGINAL_LANGUAGE_OTHER
    stored = stored_original_language(action)
    if stored is None:
        return ADDING_ORIGINAL_LANGUAGE
    ctx.user_data["new_book"]["original_language"] = stored
    return await send_add_prompt(update, ctx, ADDING_CREATION_YEAR, edit=True)


async def add_original_language_other(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip() if update.message and update.message.text else ""
    if not text:
        lang = get_lang(ctx)
        await update.message.reply_text(
            build_add_prompt_text(
                ctx, ADDING_ORIGINAL_LANGUAGE_OTHER, ctx.user_data["new_book"]
            ),
            reply_markup=add_back_keyboard(lang),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_ORIGINAL_LANGUAGE_OTHER
        return ADDING_ORIGINAL_LANGUAGE_OTHER
    ctx.user_data["new_book"]["original_language"] = text
    return await send_add_prompt(update, ctx, ADDING_CREATION_YEAR)


async def _prompt_after_creation_year(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    if language_level_prompt_enabled():
        ctx.user_data["new_book"].setdefault("language_levels", set())
        return await send_add_prompt(update, ctx, ADDING_LANGUAGE_LEVEL)
    return await send_add_prompt(update, ctx, ADDING_DESCRIPTION)


async def add_creation_year(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip() if update.message and update.message.text else ""
    lang = get_lang(ctx)
    nb = ctx.user_data["new_book"]
    try:
        year = parse_optional_creation_year(text)
    except ValueError:
        await update.message.reply_text(
            f"{tr(ctx, 'invalid_creation_year')}\n\n"
            f"{build_add_prompt_text(ctx, ADDING_CREATION_YEAR, nb)}",
            reply_markup=add_back_keyboard(lang),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_CREATION_YEAR
        return ADDING_CREATION_YEAR
    ctx.user_data["new_book"]["creation_year"] = year
    return await _prompt_after_creation_year(update, ctx)


async def add_language_level_cb(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    lang = get_lang(ctx)
    _, action, *rest = query.data.split(":")
    selected: set[str] = ctx.user_data["new_book"].setdefault("language_levels", set())
    if action == "toggle":
        level = rest[0]
        if level in selected:
            selected.discard(level)
        else:
            selected.add(level)
        await query.answer()
        await query.edit_message_text(
            build_add_prompt_text(ctx, ADDING_LANGUAGE_LEVEL, ctx.user_data["new_book"]),
            reply_markup=cefr_levels_keyboard(
                lang, selected, prefix="add_cefr", show_add_back=True
            ),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_LANGUAGE_LEVEL
        return ADDING_LANGUAGE_LEVEL
    if action == "done":
        if not selected:
            await query.answer(tr(ctx, "language_level_none_selected"), show_alert=True)
            return ADDING_LANGUAGE_LEVEL
        await query.answer()
        return await send_add_prompt(update, ctx, ADDING_DESCRIPTION, edit=True)
    await query.answer()
    return ADDING_LANGUAGE_LEVEL


async def add_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_lang(ctx)
    text = update.message.text.strip() if update.message and update.message.text else ""
    desc = "" if text == "/skip" else text

    if ctx.user_data is None or "new_book" not in ctx.user_data:
        logger.warning(
            f"User {update.effective_user.id} tried to add description but 'new_book' is missing."
        )
        await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END

    nb = ctx.user_data["new_book"]
    user = update.effective_user
    levels_set = nb.get("language_levels")
    language_levels = (
        format_language_levels(levels_set) if isinstance(levels_set, set) else None
    )
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
        language_levels=language_levels,
    )
    if book_id is None:
        raise RuntimeError("db_add_book did not return a book id")
    book = db_get_book(book_id)
    if book is None:
        raise RuntimeError(f"book {book_id} missing immediately after insert")

    confirm_text = f"{tr(ctx, 'book_added')}\n\n{book_card(book, lang)}{tr(ctx, 'new_book_delay_note')}"

    await update.message.reply_text(confirm_text, parse_mode=PM)
    ctx.user_data.pop("new_book", None)
    ctx.user_data.pop("add_state", None)

    schedule_new_book_notifications(ctx.job_queue, book_id, user.id)

    return ConversationHandler.END
