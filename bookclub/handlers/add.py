from __future__ import annotations

import asyncio

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from bookclub.cefr import format_language_levels
from bookclub.config import (
    ADDING_AI_CHOOSE,
    ADDING_AUTHOR,
    ADDING_CREATION_YEAR,
    ADDING_FICTION,
    ADDING_LANGUAGE_LEVEL,
    ADDING_ORIGINAL_LANGUAGE,
    ADDING_ORIGINAL_LANGUAGE_OTHER,
    ADDING_PAGES,
    ADDING_REVIEW,
    ADDING_TITLE,
    ADDING_TITLE_CONFIRM,
    llm_configured,
)
from bookclub.db import db_add_book, db_get_book, find_similar_book_titles
from bookclub.handlers.add_flow import (
    add_next_state,
    add_prompt_markup,
    build_add_prompt_text,
    continue_add,
    send_add_prompt,
)
from bookclub.i18n import PM, get_lang, tr
from bookclub.llm import (
    apply_suggestions_to_book,
    llm_error_kind_i18n_key,
    split_llm_error,
    suggest_book_fields,
    ui_llm_error,
)
from bookclub.logging_setup import logger
from bookclub.notifications import schedule_new_book_notifications
from bookclub.original_languages import stored_original_language
from bookclub.ui import (
    add_ai_choice_keyboard,
    book_card,
    h,
    is_valid_url,
    parse_optional_creation_year,
    similar_title_confirm_keyboard,
    similar_title_warning_matches_text,
)


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_add_state(ctx)
    ctx.user_data["new_book"] = {}
    return await send_add_prompt(update, ctx, ADDING_TITLE)


def _clear_add_state(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("new_book", None)
    ctx.user_data.pop("add_state", None)
    ctx.user_data.pop("llm_add", None)
    ctx.user_data.pop("admin_add", None)
    ctx.user_data.pop("llm_suggestions_applied", None)
    ctx.user_data.pop("llm_filled_keys", None)


async def add_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    ctx.user_data.setdefault("new_book", {})["title"] = title
    ctx.user_data.pop("llm_suggestions_applied", None)
    ctx.user_data.pop("llm_filled_keys", None)
    ctx.user_data.pop("llm_add", None)
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
    return await advance_after_title(update, ctx, ADDING_TITLE)


async def add_title_similar_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, action = query.data.split(":", 1)
    if action == "no":
        _clear_add_state(ctx)
        await query.edit_message_text(tr(ctx, "cancelled"), parse_mode=PM)
        return ConversationHandler.END
    return await advance_after_title(update, ctx, ADDING_TITLE_CONFIRM, edit=True)


async def _send_add_status(
    update: Update, text: str, *, edit: bool = False, parse_mode: str | None = PM
) -> None:
    query = update.callback_query
    try:
        if edit and query:
            await query.edit_message_text(text, parse_mode=parse_mode)
            return
        if update.message:
            await update.message.reply_text(text, parse_mode=parse_mode)
            return
        if query and query.message:
            await query.message.reply_text(text, parse_mode=parse_mode)  # type: ignore[attr-defined]
    except BadRequest:
        logger.warning(
            "add status send failed with parse_mode=%s; retrying plain", parse_mode
        )
        if edit and query:
            await query.edit_message_text(text)
            return
        if update.message:
            await update.message.reply_text(text)
            return
        if query and query.message:
            await query.message.reply_text(text)  # type: ignore[attr-defined]


async def apply_llm_suggestions(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.user_data.get("llm_add"):
        return
    if ctx.user_data.get("llm_suggestions_applied"):
        return
    if add_next_state(ADDING_TITLE) is None:
        ctx.user_data["llm_suggestions_applied"] = True
        return
    title = str(ctx.user_data.get("new_book", {}).get("title") or "")
    await _send_add_status(
        update,
        tr(ctx, "add_ai_suggesting", title=h(title)),
        edit=bool(update.callback_query),
    )
    lang = get_lang(ctx)
    suggestions, error = await asyncio.to_thread(suggest_book_fields, title, lang=lang)
    ctx.user_data["llm_suggestions_applied"] = True
    if error == "not_configured":
        await _send_add_status(update, tr(ctx, "add_ai_no_llm"))
        return
    if error:
        kind, detail = split_llm_error(error)
        kind_label = tr(ctx, llm_error_kind_i18n_key(kind))
        detail_text = ui_llm_error(detail) or error
        # Plain text: provider errors often contain <>&{} that break Telegram HTML
        # and would drop this message, leaving only the generic warning.
        await _send_add_status(
            update,
            tr(ctx, "add_ai_suggest_failed", kind=kind_label, error=detail_text),
            parse_mode=None,
        )
        return
    nb = ctx.user_data.setdefault("new_book", {})
    ctx.user_data["llm_filled_keys"] = apply_suggestions_to_book(nb, suggestions)
    if ctx.user_data["llm_filled_keys"]:
        await _send_add_status(update, tr(ctx, "add_ai_suggested"))


async def ask_add_ai(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, *, edit: bool = False
) -> int:
    ctx.user_data["add_state"] = ADDING_AI_CHOOSE
    lang = get_lang(ctx)
    text = tr(ctx, "add_ai_ask")
    markup = add_ai_choice_keyboard(lang)
    query = update.callback_query
    if edit and query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=PM)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=PM)
    elif query and query.message:
        await query.message.reply_text(  # type: ignore[attr-defined]
            text, reply_markup=markup, parse_mode=PM
        )
    return ADDING_AI_CHOOSE


async def add_ai_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, action = query.data.split(":", 1)
    ctx.user_data["llm_add"] = action == "yes"
    if ctx.user_data["llm_add"]:
        await apply_llm_suggestions(update, ctx)
        return await continue_add(update, ctx, ADDING_TITLE, edit=False)
    return await continue_add(update, ctx, ADDING_TITLE, edit=True)


async def advance_after_title(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    current: int,
    *,
    edit: bool = False,
) -> int:
    if add_next_state(ADDING_TITLE) is not None and llm_configured():
        return await ask_add_ai(update, ctx, edit=edit)
    return await continue_add(update, ctx, current, edit=edit)


async def add_author(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["new_book"]["author"] = update.message.text.strip()
    return await continue_add(update, ctx, ADDING_AUTHOR)


async def add_pages(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    lang = get_lang(ctx)
    nb = ctx.user_data["new_book"]
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text(
            f"{tr(ctx, 'invalid_pages')}\n\n{build_add_prompt_text(ctx, ADDING_PAGES, nb)}",
            reply_markup=add_prompt_markup(lang, ADDING_PAGES, nb),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_PAGES
        return ADDING_PAGES
    ctx.user_data["new_book"]["pages"] = int(text)
    return await continue_add(update, ctx, ADDING_PAGES)


async def add_fiction_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, value = query.data.split(":")
    ctx.user_data["new_book"]["fiction"] = value == "1"
    return await continue_add(update, ctx, ADDING_FICTION, edit=True)


async def add_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    lang = get_lang(ctx)
    nb = ctx.user_data["new_book"]
    if not is_valid_url(text):
        await update.message.reply_text(
            f"{tr(ctx, 'invalid_review')}\n\n{build_add_prompt_text(ctx, ADDING_REVIEW, nb)}",
            reply_markup=add_prompt_markup(lang, ADDING_REVIEW, nb),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_REVIEW
        return ADDING_REVIEW
    ctx.user_data["new_book"]["review_link"] = text
    return await continue_add(update, ctx, ADDING_REVIEW)


async def add_original_language_skip(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    ctx.user_data["new_book"]["original_language"] = ""
    return await continue_add(update, ctx, ADDING_ORIGINAL_LANGUAGE)


async def add_original_language_cb(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    _, action = query.data.split(":", 1)
    if action == "skip":
        ctx.user_data["new_book"]["original_language"] = ""
        return await continue_add(update, ctx, ADDING_ORIGINAL_LANGUAGE, edit=True)
    if action == "other":
        ctx.user_data["add_state"] = ADDING_ORIGINAL_LANGUAGE_OTHER
        await query.edit_message_text(
            build_add_prompt_text(
                ctx, ADDING_ORIGINAL_LANGUAGE_OTHER, ctx.user_data["new_book"]
            ),
            reply_markup=add_prompt_markup(
                get_lang(ctx),
                ADDING_ORIGINAL_LANGUAGE_OTHER,
                ctx.user_data["new_book"],
            ),
            parse_mode=PM,
        )
        return ADDING_ORIGINAL_LANGUAGE_OTHER
    stored = stored_original_language(action)
    if stored is None:
        return ADDING_ORIGINAL_LANGUAGE
    ctx.user_data["new_book"]["original_language"] = stored
    return await continue_add(update, ctx, ADDING_ORIGINAL_LANGUAGE, edit=True)


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
            reply_markup=add_prompt_markup(
                lang, ADDING_ORIGINAL_LANGUAGE_OTHER, ctx.user_data["new_book"]
            ),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_ORIGINAL_LANGUAGE_OTHER
        return ADDING_ORIGINAL_LANGUAGE_OTHER
    ctx.user_data["new_book"]["original_language"] = text
    return await continue_add(update, ctx, ADDING_ORIGINAL_LANGUAGE_OTHER)


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
            reply_markup=add_prompt_markup(lang, ADDING_CREATION_YEAR, nb),
            parse_mode=PM,
        )
        ctx.user_data["add_state"] = ADDING_CREATION_YEAR
        return ADDING_CREATION_YEAR
    ctx.user_data["new_book"]["creation_year"] = year
    return await continue_add(update, ctx, ADDING_CREATION_YEAR)


async def add_language_level_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
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
            build_add_prompt_text(
                ctx, ADDING_LANGUAGE_LEVEL, ctx.user_data["new_book"]
            ),
            reply_markup=add_prompt_markup(
                lang, ADDING_LANGUAGE_LEVEL, ctx.user_data["new_book"]
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
        return await continue_add(update, ctx, ADDING_LANGUAGE_LEVEL, edit=True)
    await query.answer()
    return ADDING_LANGUAGE_LEVEL


async def complete_new_book(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    *,
    description: str | None = None,
) -> int:
    lang = get_lang(ctx)
    if ctx.user_data is None or "new_book" not in ctx.user_data:
        logger.warning(
            f"User {update.effective_user.id} tried to add an entry but 'new_book' is missing."
        )
        if update.message:
            await update.message.reply_text(tr(ctx, "cancelled"), parse_mode=PM)
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                tr(ctx, "cancelled"), parse_mode=PM
            )
        return ConversationHandler.END

    nb = ctx.user_data["new_book"]
    desc = description if description is not None else (nb.get("description") or "")
    user = update.effective_user
    levels_set = nb.get("language_levels")
    language_levels = (
        format_language_levels(levels_set) if isinstance(levels_set, set) else None
    )
    book_id = db_add_book(
        nb["title"],
        nb.get("author") or "",
        nb.get("pages") or 0,
        nb.get("fiction", True),
        nb.get("review_link") or "",
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

    query = update.callback_query
    if update.message:
        await update.message.reply_text(confirm_text, parse_mode=PM)
    elif query and query.message:
        await query.edit_message_text(confirm_text, parse_mode=PM)

    _clear_add_state(ctx)

    schedule_new_book_notifications(ctx.job_queue, book_id, user.id)

    return ConversationHandler.END


async def add_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip() if update.message and update.message.text else ""
    desc = "" if text == "/skip" else text
    return await complete_new_book(update, ctx, description=desc)
