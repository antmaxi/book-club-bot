from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from telegram.ext import ContextTypes

import bookclub.config as config
from bookclub.db import (
    db_begin_new_book_notify,
    db_get_book,
    db_get_books_pending_notify,
    db_get_user_setting,
    db_get_user_vote,
    db_get_users_with_setting,
    db_get_admin_setting,
    db_mark_new_book_notify_done,
    db_set_new_book_notify_pending,
)
from bookclub.domain import require_book
from bookclub.i18n import PM, get_lang, tr
from bookclub.logging_setup import logger
from bookclub.ui import book_card, post_book_voting_to_group_chat, score_keyboard

def enqueue_new_book_notify_job(
    job_queue: Any, book_id: int, delay_seconds: float
) -> None:
    job_queue.run_once(
        notify_new_book_job,
        when=delay_seconds,
        data={"book_id": book_id},
        name=f"notify_book_{book_id}",
    )


def schedule_new_book_notifications(
    job_queue: Any,
    book_id: int,
    adder_id: int,
    delay_seconds: float | None = None,
) -> None:
    """Schedule delayed new-book notifications (survives restart via DB + recovery)."""
    delay = (
        float(config.NEW_BOOK_NOTIFY_DELAY_SECONDS)
        if delay_seconds is None
        else delay_seconds
    )
    notify_after = datetime.now() + timedelta(seconds=delay)
    db_set_new_book_notify_pending(book_id, adder_id, notify_after)
    if job_queue:
        enqueue_new_book_notify_job(job_queue, book_id, delay)
    else:
        logger.error(
            "JobQueue is None — in-memory job not scheduled; "
            "notify will run after restart if notify_after is still in the DB.\n"
            'Fix: pip install "python-telegram-bot[job-queue]"\n'
            "Then restart the bot."
        )


def recover_pending_new_book_notifications(job_queue: Any) -> None:
    """Re-queue new-book notify jobs lost when the process restarted."""
    if not job_queue:
        logger.warning(
            "recover_pending_new_book_notifications: no JobQueue, skipping recovery"
        )
        return
    now = datetime.now()
    for book in db_get_books_pending_notify():
        raw = book["notify_after"]
        if not raw:
            continue
        try:
            notify_after = datetime.fromisoformat(str(raw))
        except ValueError:
            logger.warning(
                "recover_pending_new_book_notifications: bad notify_after "
                f"for book {book['id']}: {raw!r}"
            )
            continue
        delay = max(0.0, (notify_after - now).total_seconds())
        enqueue_new_book_notify_job(job_queue, int(book["id"]), delay)
        logger.info(
            "Recovered new-book notify job for book %s (fires in %.0fs)",
            book["id"],
            delay,
        )


async def notify_new_book_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Fired after the new-book delay. Sends a card to all opted-in users."""
    book_id = int(ctx.job.data["book_id"])

    book = db_get_book(book_id)
    if not book:
        logger.info(f"notify_new_book_job: book {book_id} no longer exists, skipping.")
        return
    if book["discussed"]:
        logger.info(f"notify_new_book_job: book {book_id} already discussed, skipping.")
        db_mark_new_book_notify_done(book_id)
        return
    if book["hidden"]:
        logger.info(f"notify_new_book_job: book {book_id} was hidden, skipping.")
        db_mark_new_book_notify_done(book_id)
        return

    adder_id = db_begin_new_book_notify(book_id)
    if adder_id is None:
        logger.info(
            f"notify_new_book_job: book {book_id} already notified, skipping."
        )
        return

    user_ids = db_get_users_with_setting("notify_new_books", 1)
    logger.info(
        f"notify_new_book_job: notifying {len(user_ids)} user(s) about book {book_id}."
    )

    sent = 0
    for user_id in user_ids:
        if user_id == adder_id:
            continue
        # Resolve language from persistence; fall back to Russian
        user_data = ctx.application.user_data.get(user_id, {})
        lang = user_data.get("lang", "ru")
        try:
            uv = db_get_user_vote(user_id, book_id)
            text = tr(lang, "new_book_notification") + book_card(
                book, lang, user_vote=uv
            )
            await ctx.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=PM,
                reply_markup=score_keyboard(book_id, lang, uv),
            )
            sent += 1
        except Exception as e:
            logger.warning(f"notify_new_book_job: failed to notify user {user_id}: {e}")

    if config.ALLOWED_CHAT_ID and db_get_admin_setting("post_new_books_to_chat", 0):
        if await post_book_voting_to_group_chat(
            ctx.bot, book, intro_key="new_book_notification"
        ):
            logger.info(
                f"notify_new_book_job: posted book {book_id} to chat {config.ALLOWED_CHAT_ID}."
            )

    logger.info(f"notify_new_book_job: done — sent to {sent} user(s).")

