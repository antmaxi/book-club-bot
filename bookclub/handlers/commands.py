from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

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

import bookclub.config as config
from bookclub.db import (
    db_cast_vote,
    db_get_books,
    db_get_user_setting,
    db_get_user_vote,
    db_set_user_setting,
    db_votes_use_attendance,
)
from bookclub.domain import is_admin
from bookclub.i18n import PM, T, _COMMAND_DESC_OVERLAYS, get_lang, s, tr
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
    score_display,
    score_keyboard,
    send_chunked_html_messages,
)

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
        BotCommand("cancel", "❌ Cancel current action"),
        BotCommand("help", "❓ Show help"),
        BotCommand("info", "ℹ️ About the bot"),
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
        BotCommand("cancel", "❌ Отменить действие"),
        BotCommand("help", "❓ Показать помощь"),
        BotCommand("info", "ℹ️ О боте"),
    ],
}


def _apply_entity_command_overlays(entity: str) -> None:
    cmd_overlay = _COMMAND_DESC_OVERLAYS.get(entity, {})
    for lang, by_name in cmd_overlay.items():
        COMMANDS[lang] = [
            BotCommand(c.command, by_name.get(c.command, c.description))
            for c in COMMANDS[lang]
        ]


_apply_entity_command_overlays(config.CLUB_ENTITY)

_ADMIN_MENU_COMMAND = "adminconsole"


def commands_for_user(lang: str, user_id: int) -> list[BotCommand]:
    """Telegram command menu for a user; admins see /adminconsole, others do not."""
    cmds = COMMANDS[lang]
    if user_id in config.ADMIN_IDS:
        return cmds
    return [c for c in cmds if c.command != _ADMIN_MENU_COMMAND]


async def refresh_admin_command_menus(bot: Bot) -> None:
    """Push admin command menus to each admin's private chat (if the bot can)."""
    from telegram import BotCommandScopeChat

    for admin_id in config.ADMIN_IDS:
        for lang in ("en", "ru"):
            scope = BotCommandScopeChat(chat_id=admin_id)
            try:
                await bot.delete_my_commands(scope=scope)
                await bot.set_my_commands(
                    commands_for_user(lang, admin_id), scope=scope
                )
            except Exception as e:
                logger.warning(
                    "Could not set admin commands for user %s (%s): %s",
                    admin_id,
                    lang,
                    e,
                )


async def set_user_commands(bot: Bot, update: Update, lang: str) -> None:
    """Set the command menu for a specific user in their chosen language.
    Uses BotCommandScopeChatMember for groups, BotCommandScopeChat for private."""
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    chat_id = chat.id
    user_id = user.id
    menu = commands_for_user(lang, user_id)
    try:
        if chat.type == "private":
            scope: BotCommandScopeChat | BotCommandScopeChatMember = (
                BotCommandScopeChat(chat_id=chat_id)
            )
            await bot.delete_my_commands(scope=scope)
            await bot.set_my_commands(menu, scope=scope)
        else:
            scope = BotCommandScopeChatMember(chat_id=chat_id, user_id=user_id)
            await bot.delete_my_commands(scope=scope)
            await bot.set_my_commands(menu, scope=scope)
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
    text = tr(ctx, "welcome")
    if is_admin(update.effective_user.id):
        text += tr(ctx, "welcome_admin_suffix")
    await update.message.reply_text(text, parse_mode=PM)


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
            last_commit = fmt_dt_utc(
                datetime.fromtimestamp(int(ct), tz=timezone.utc)
            )
    except Exception as e:
        logger.warning(f"Could not get last commit via git: {e}")

    # 2. Fallback to file mtime
    if not last_commit:
        try:
            mtime = os.path.getmtime(__file__)
            last_commit = fmt_dt_utc(
                datetime.fromtimestamp(mtime, tz=timezone.utc)
            )
        except Exception as e:
            logger.warning(f"Could not get file mtime: {e}")
            last_commit = "unknown"

    text = tr(
        ctx,
        "info_msg",
        bot_name=s(get_lang(ctx), "bot_name"),
        last_commit=last_commit,
        github_repo=config.GITHUB_REPO,
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
        filter_choice = ctx.user_data.get("pending_list_choice", "all")
        format_choice = None
        user_id = query.from_user.id
        # We don't call query.answer() here because it was already answered in settings_choice_cb
    else:
        await query.answer()
        user_id = query.from_user.id
        filter_choice, format_choice = _parse_list_callback(query.data)

    # Check for notification opt-in
    if db_get_user_setting(user_id, "notify_new_books") == -1:
        ctx.user_data["pending_list_choice"] = filter_choice
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

    if format_choice is None:
        await _show_list_format_prompt(query, ctx, filter_choice)
        return

    lang = get_lang(ctx)
    choice = filter_choice

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

    chat_id = update.effective_chat.id

    if format_choice == "compact":
        header = tr(ctx, "list_compact_title", count=len(books))
        lines = [header] + [
            book_compact_line(i, book) for i, book in enumerate(books, 1)
        ]
        await send_chunked_html_messages(
            ctx.bot, chat_id, lines, joiner="\n"
        )
        return

    for book in books:
        uv = db_get_user_vote(user_id, book["id"])
        try:
            await ctx.bot.send_message(
                chat_id=chat_id,
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
    key = (
        "score_calc_info_attendance"
        if db_votes_use_attendance()
        else "score_calc_info"
    )
    await query.answer(text=tr(ctx, key), show_alert=True)


