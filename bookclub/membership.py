from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.error import BadRequest, Forbidden, NetworkError
from telegram.ext import ApplicationHandlerStop, ContextTypes

import bookclub.config as config
from bookclub.db import db_upsert_club_user
from bookclub.i18n import PM, get_lang, s, tr
from bookclub.ui import h
from bookclub.logging_setup import logger

MEMBERSHIP_CACHE_TTL = 300  # seconds
_membership_cache: dict[int, tuple[bool, datetime]] = {}


def _membership_cache_evict(user_id: int) -> None:
    _membership_cache.pop(user_id, None)


def _membership_fail_open_on_api_error(exc: BaseException) -> bool:
    """True when the bot cannot verify membership due to chat/bot config, not the user."""
    msg = str(exc).lower()
    if isinstance(exc, NetworkError):
        return True
    if isinstance(exc, Forbidden):
        # Bot removed from the allowed group — same class of misconfiguration.
        return any(
            needle in msg
            for needle in ("kicked", "not a member", "chat not found", "forbidden")
        )
    if isinstance(exc, BadRequest):
        return any(
            needle in msg
            for needle in (
                "chat not found",
                "chat_id_invalid",
                "peer_id_invalid",
                "group chat was deactivated",
                "supergroup chat was deactivated",
            )
        )
    return any(
        needle in msg
        for needle in (
            "chat not found",
            "chat_id_invalid",
            "peer_id_invalid",
        )
    )


async def _check_membership(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the user is a member of ALLOWED_CHAT_ID (or no restriction set)."""
    if not config.ALLOWED_CHAT_ID:
        return True
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return False
    # Admins always pass
    if user_id in config.ADMIN_IDS:
        return True

    cached = _membership_cache.get(user_id)
    if cached is not None:
        allowed, checked_at = cached
        if (datetime.now() - checked_at).total_seconds() < MEMBERSHIP_CACHE_TTL:
            return allowed
        _membership_cache_evict(user_id)

    try:
        member = await ctx.bot.get_chat_member(config.ALLOWED_CHAT_ID, user_id)
        allowed = member.status in ("member", "administrator", "creator", "restricted")
        _membership_cache[user_id] = (allowed, datetime.now())
        return allowed
    except Exception as e:
        # Don't cache failures — a transient API error shouldn't lock a real
        # member out for the whole TTL.
        logger.warning(f"Membership check failed for user {user_id}: {e}")
        if _membership_fail_open_on_api_error(e):
            logger.error(
                "Membership gate bypassed for user %s: bot cannot access "
                "ALLOWED_CHAT_ID=%s (%s). Re-add the bot to that chat or fix "
                "ALLOWED_CHAT_ID in .env.",
                user_id,
                config.ALLOWED_CHAT_ID,
                e,
            )
            return True
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
    if user_id and user_id not in config.ADMIN_IDS:
        ctx.bot_data["last_non_admin_activity"] = datetime.now()

    if user_id and update.effective_user:
        db_upsert_club_user(
            user_id,
            update.effective_user.full_name or "",
            update.effective_user.username,
        )

    if await _check_membership(update, ctx):
        return
    blocked_uid = update.effective_user.id if update.effective_user else None
    logger.info(
        f"Blocked user {blocked_uid or '?'} — not a member of chat {config.ALLOWED_CHAT_ID}"
    )
    lang = get_lang(ctx) if ctx.user_data else "ru"
    text = s(lang, "not_member").format(chat=h(config.ALLOWED_CHAT_NAME))
    try:
        if update.callback_query:
            await update.callback_query.answer(
                config.ALLOWED_CHAT_NAME + " — members only", show_alert=True
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

