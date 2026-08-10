from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bookclub.cefr import format_language_levels, language_levels_display
from bookclub.config import (
    ADDING_AUTHOR,
    ADDING_CREATION_YEAR,
    ADDING_DESCRIPTION,
    ADDING_FICTION,
    ADDING_LANGUAGE_LEVEL,
    ADDING_ORIGINAL_LANGUAGE,
    ADDING_PAGES,
    ADDING_REVIEW,
    ADDING_TITLE,
    ADDING_TITLE_CONFIRM,
    language_level_prompt_enabled,
)
from bookclub.i18n import PM, get_lang, s, tr
from bookclub.ui import (
    add_back_keyboard,
    cefr_levels_keyboard,
    fiction_keyboard,
    h,
    similar_title_confirm_keyboard,
)


def add_previous_state(current: int) -> int | None:
    if current == ADDING_TITLE_CONFIRM:
        return ADDING_TITLE
    if current == ADDING_DESCRIPTION:
        if language_level_prompt_enabled():
            return ADDING_LANGUAGE_LEVEL
        return ADDING_CREATION_YEAR
    return {
        ADDING_AUTHOR: ADDING_TITLE,
        ADDING_PAGES: ADDING_AUTHOR,
        ADDING_FICTION: ADDING_PAGES,
        ADDING_REVIEW: ADDING_FICTION,
        ADDING_ORIGINAL_LANGUAGE: ADDING_REVIEW,
        ADDING_CREATION_YEAR: ADDING_ORIGINAL_LANGUAGE,
        ADDING_LANGUAGE_LEVEL: ADDING_CREATION_YEAR,
    }.get(current)


def _prompt_key_for_state(state: int) -> str | None:
    return {
        ADDING_TITLE: "ask_title",
        ADDING_AUTHOR: "ask_author",
        ADDING_PAGES: "ask_pages",
        ADDING_FICTION: "ask_fiction",
        ADDING_REVIEW: "ask_review",
        ADDING_ORIGINAL_LANGUAGE: "ask_original_language",
        ADDING_CREATION_YEAR: "ask_creation_year",
        ADDING_LANGUAGE_LEVEL: "ask_language_level",
        ADDING_DESCRIPTION: "ask_desc",
    }.get(state)


def _current_value_display(nb: dict, state: int, lang: str) -> str | None:
    dash = "—"
    if state == ADDING_TITLE:
        v = nb.get("title")
        return str(v) if v else None
    if state == ADDING_AUTHOR:
        v = nb.get("author")
        return str(v) if v else None
    if state == ADDING_PAGES:
        v = nb.get("pages")
        return str(v) if v is not None else None
    if state == ADDING_FICTION:
        if "fiction" not in nb:
            return None
        return (
            s(lang, "fiction_label") if nb["fiction"] else s(lang, "nonfiction_label")
        )
    if state == ADDING_REVIEW:
        v = nb.get("review_link")
        return str(v) if v else None
    if state == ADDING_ORIGINAL_LANGUAGE:
        v = nb.get("original_language")
        if v is None:
            return None
        return str(v) if v else dash
    if state == ADDING_CREATION_YEAR:
        v = nb.get("creation_year")
        return str(v) if v is not None else None
    if state == ADDING_LANGUAGE_LEVEL:
        levels = nb.get("language_levels")
        if isinstance(levels, set):
            text = language_levels_display(format_language_levels(levels))
            return text if text else None
        if isinstance(levels, str):
            return language_levels_display(levels)
        return None
    return None


def build_add_prompt_text(
    ctx: ContextTypes.DEFAULT_TYPE, state: int, nb: dict
) -> str:
    key = _prompt_key_for_state(state)
    if key is None:
        return ""
    lang = get_lang(ctx)
    if state == ADDING_LANGUAGE_LEVEL:
        levels = nb.get("language_levels")
        count = len(levels) if isinstance(levels, set) else 0
        body = tr(ctx, key, count=count)
    else:
        body = tr(ctx, key)
    current = _current_value_display(nb, state, lang)
    parts = [body]
    if current is not None:
        parts.append(tr(ctx, "add_current_value", value=h(current)))
    if state != ADDING_TITLE:
        parts.append(tr(ctx, "add_back_hint"))
    return "\n".join(parts)


def add_prompt_markup(
    lang: str, state: int, nb: dict
) -> object | None:
    if state == ADDING_TITLE:
        return None
    if state == ADDING_FICTION:
        return fiction_keyboard(lang, show_add_back=True)
    if state == ADDING_LANGUAGE_LEVEL:
        levels = nb.get("language_levels")
        selected = levels if isinstance(levels, set) else set()
        return cefr_levels_keyboard(
            lang, selected, prefix="add_cefr", show_add_back=True
        )
    if state in (
        ADDING_AUTHOR,
        ADDING_PAGES,
        ADDING_REVIEW,
        ADDING_ORIGINAL_LANGUAGE,
        ADDING_CREATION_YEAR,
        ADDING_DESCRIPTION,
    ):
        return add_back_keyboard(lang)
    return None


async def send_add_prompt(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    state: int,
    *,
    edit: bool = False,
) -> int:
    nb = ctx.user_data.setdefault("new_book", {})
    text = build_add_prompt_text(ctx, state, nb)
    lang = get_lang(ctx)
    markup = add_prompt_markup(lang, state, nb)
    ctx.user_data["add_state"] = state

    query = update.callback_query
    if edit and query:
        await query.edit_message_text(text, parse_mode=PM, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, parse_mode=PM, reply_markup=markup)
    elif query and query.message:
        await query.message.reply_text(text, parse_mode=PM, reply_markup=markup)
    return state


async def add_go_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    current = ctx.user_data.get("add_state")
    if current is None:
        return ADDING_TITLE
    prev = add_previous_state(current)
    query = update.callback_query
    if prev is None:
        msg = tr(ctx, "add_back_at_start")
        if query:
            await query.answer(msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(msg, parse_mode=PM)
        return current
    if query:
        await query.answer()
    return await send_add_prompt(update, ctx, prev, edit=bool(query))
