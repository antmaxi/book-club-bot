from __future__ import annotations

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bookclub.cefr import format_language_levels, language_levels_display
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
from bookclub.i18n import PM, get_lang, s, tr
from bookclub.original_languages import display_original_language
from bookclub.ui import (
    add_nav_keyboard,
    cefr_levels_keyboard,
    fiction_keyboard,
    h,
    original_language_keyboard,
)


def add_previous_state(current: int) -> int | None:
    if current == ADDING_TITLE_CONFIRM:
        return ADDING_TITLE
    if current == ADDING_ORIGINAL_LANGUAGE_OTHER:
        return ADDING_ORIGINAL_LANGUAGE
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


def add_next_state(current: int) -> int | None:
    if current in (ADDING_TITLE, ADDING_TITLE_CONFIRM):
        return ADDING_AUTHOR
    if current == ADDING_ORIGINAL_LANGUAGE_OTHER:
        return ADDING_CREATION_YEAR
    if current == ADDING_CREATION_YEAR:
        if language_level_prompt_enabled():
            return ADDING_LANGUAGE_LEVEL
        return ADDING_DESCRIPTION
    return {
        ADDING_AUTHOR: ADDING_PAGES,
        ADDING_PAGES: ADDING_FICTION,
        ADDING_FICTION: ADDING_REVIEW,
        ADDING_REVIEW: ADDING_ORIGINAL_LANGUAGE,
        ADDING_ORIGINAL_LANGUAGE: ADDING_CREATION_YEAR,
        ADDING_LANGUAGE_LEVEL: ADDING_DESCRIPTION,
    }.get(current)


def _prompt_key_for_state(state: int) -> str | None:
    return {
        ADDING_TITLE: "ask_title",
        ADDING_AUTHOR: "ask_author",
        ADDING_PAGES: "ask_pages",
        ADDING_FICTION: "ask_fiction",
        ADDING_REVIEW: "ask_review",
        ADDING_ORIGINAL_LANGUAGE: "ask_original_language",
        ADDING_ORIGINAL_LANGUAGE_OTHER: "ask_original_language_other",
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
    if state in (ADDING_ORIGINAL_LANGUAGE, ADDING_ORIGINAL_LANGUAGE_OTHER):
        if "original_language" not in nb:
            return None
        v = nb.get("original_language")
        if not v:
            return dash
        return display_original_language(str(v), lang)
    if state == ADDING_CREATION_YEAR:
        if "creation_year" not in nb:
            return None
        v = nb.get("creation_year")
        return str(v) if v is not None else dash
    if state == ADDING_LANGUAGE_LEVEL:
        levels = nb.get("language_levels")
        if isinstance(levels, set):
            text = language_levels_display(format_language_levels(levels))
            return text if text else None
        if isinstance(levels, str):
            return language_levels_display(levels)
        return None
    return None


def add_field_is_set(nb: dict, state: int) -> bool:
    return _current_value_display(nb, state, "en") is not None


def build_add_prompt_text(ctx: ContextTypes.DEFAULT_TYPE, state: int, nb: dict) -> str:
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
    if current is not None and state == ADDING_TITLE:
        parts.append(tr(ctx, "add_forward_hint"))
    elif current is not None:
        parts.append(tr(ctx, "add_nav_hint"))
    elif state != ADDING_TITLE:
        parts.append(tr(ctx, "add_back_hint"))
    return "\n".join(parts)


def add_prompt_markup(lang: str, state: int, nb: dict) -> InlineKeyboardMarkup | None:
    can_forward = add_field_is_set(nb, state)
    show_back = state != ADDING_TITLE
    if state == ADDING_TITLE:
        return add_nav_keyboard(lang, show_back=False, show_forward=can_forward)
    if state == ADDING_FICTION:
        return fiction_keyboard(lang, show_add_back=True, show_add_forward=can_forward)
    if state == ADDING_ORIGINAL_LANGUAGE:
        return original_language_keyboard(
            lang,
            prefix="add_orig_lang",
            show_add_back=True,
            show_add_forward=can_forward,
        )
    if state == ADDING_LANGUAGE_LEVEL:
        levels = nb.get("language_levels")
        selected = levels if isinstance(levels, set) else set()
        return cefr_levels_keyboard(
            lang,
            selected,
            prefix="add_cefr",
            show_add_back=True,
            show_add_forward=can_forward,
        )
    if state in (
        ADDING_AUTHOR,
        ADDING_PAGES,
        ADDING_REVIEW,
        ADDING_ORIGINAL_LANGUAGE_OTHER,
        ADDING_CREATION_YEAR,
        ADDING_DESCRIPTION,
    ):
        return add_nav_keyboard(lang, show_back=show_back, show_forward=can_forward)
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


async def _nav_alert(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, key: str, current: int
) -> int:
    query = update.callback_query
    msg = tr(ctx, key)
    if query:
        await query.answer(msg, show_alert=True)
    elif update.message:
        await update.message.reply_text(msg, parse_mode=PM)
    return current


async def add_go_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    current = ctx.user_data.get("add_state")
    if current is None:
        return ADDING_TITLE
    prev = add_previous_state(current)
    query = update.callback_query
    if prev is None:
        return await _nav_alert(update, ctx, "add_back_at_start", current)
    if query:
        await query.answer()
    return await send_add_prompt(update, ctx, prev, edit=bool(query))


async def add_go_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    current = ctx.user_data.get("add_state")
    if current is None:
        return ADDING_TITLE
    nb = ctx.user_data.setdefault("new_book", {})
    query = update.callback_query
    if not add_field_is_set(nb, current):
        return await _nav_alert(update, ctx, "add_forward_need_value", current)
    nxt = add_next_state(current)
    if nxt is None:
        return await _nav_alert(update, ctx, "add_forward_at_end", current)
    if query:
        await query.answer()
    return await send_add_prompt(update, ctx, nxt, edit=bool(query))
