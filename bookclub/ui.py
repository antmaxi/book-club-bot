from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import bookclub.config as config
from bookclub.db import (
    db_meeting_user_suggestions,
    db_upsert_club_user,
    format_club_user_display,
)
from bookclub.i18n import PM, T, get_lang, s, tr, vote_label_text
from bookclub.logging_setup import logger
from bookclub.types import BookLike

from bookclub.config import (
    ADMIN_MEETING_ATTENDEES,
    ADMIN_NOTIFY_CHAT_PICK,
    ADMIN_NOTIFY_PICK,
    MEETING_ATTENDEES_PAGE_SIZE,
    NOTIFY_BOOKS_PAGE_SIZE,
)

def format_user(book: BookLike) -> str:
    """Return @username if available, otherwise fall back to display name."""
    username = book["added_by_username"]
    if username:
        return f"@{h(username)}"
    return h(book["added_by_name"] or "unknown")


def h(text: str) -> str:
    # `"` must be escaped too: h() is used inside href="..." attributes, where a
    # raw quote breaks out of the attribute and makes Telegram reject the whole
    # message — which would take down /list for everyone, not just the author.
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def similar_title_warning_matches_text(
    matches: Sequence[tuple[int, str, float]], *, limit: int = 5
) -> str:
    lines: list[str] = []
    for _book_id, title, ratio in matches[:limit]:
        pct = int(round(ratio * 100))
        lines.append(f"• {h(title)} ({pct}%)")
    return "\n".join(lines)


def similar_title_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    s(lang, "similar_title_confirm_btn"),
                    callback_data="title_sim:yes",
                ),
                InlineKeyboardButton(
                    s(lang, "similar_title_cancel_btn"),
                    callback_data="title_sim:no",
                ),
            ]
        ]
    )


def fmt_dt_utc(dt: datetime) -> str:
    """Format a datetime as 'YYYY-MM-DD HH:MM:SS UTC±HH:MM'.

    Naive datetimes are assumed to be in the server's local timezone. The
    explicit UTC offset lets admins reading this from any timezone interpret
    the value without having to know where the server is.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attach the server's local tz
    off = dt.strftime("%z")  # +0200 / -0500 / +0000
    return dt.strftime("%Y-%m-%d %H:%M:%S") + f" UTC{off[:3]}:{off[3:5]}"


SCORE_EMOJI = {1: "✅", 0: "😐", -1: "❌", None: "—"}


def score_display(book: BookLike, lang: str = "en") -> str:
    """Show vote tally: ✅12  😐3  ❌2  (N votes)"""
    yes = book["votes_yes"]
    meh = book["votes_meh"]
    no = book["votes_no"]
    total = book["vote_count"]
    if total == 0:
        votes_label = T[lang]["votes_label"]
        if not callable(votes_label):
            raise TypeError("votes_label must be callable")
        return str(votes_label(0))
    votes_label = T[lang]["votes_label"]
    if not callable(votes_label):
        raise TypeError("votes_label must be callable")
    return f"✅ {yes}  😐 {meh}  ❌ {no}  {votes_label(total)}"


def book_card(book: BookLike, lang: str = "en", user_vote: int | None = None) -> str:
    fiction_label = (
        s(lang, "fiction_label") if book["fiction"] else s(lang, "nonfiction_label")
    )
    lines = [
        f"{s(lang, 'card_icon')} <b>{h(book['title'])}</b>",
        f"{s(lang, 'subtitle_icon')} {h(book['author'])}",
        f"📂 {h(fiction_label)}  •  📄 {h(str(book['pages']))} {h(s(lang, 'pages_label'))}",
        score_display(book, lang),
    ]
    orig_lang = book["original_language"] if book["original_language"] else None
    if orig_lang:
        lines.insert(
            3,
            f"🌐 {h(s(lang, 'original_language_label'))}: {h(str(orig_lang))}",
        )
    creation_year = book["creation_year"]
    if creation_year is not None:
        lines.insert(
            3,
            f"📅 {h(s(lang, 'creation_year_label'))}: {h(str(creation_year))}",
        )
    if user_vote is not None:
        vote_label = vote_label_text(lang, user_vote)
        lines[-1] += f"  <i>({h(s(lang, 'your_vote'))}: {h(vote_label)})</i>"
    if book["review_link"]:
        lines.append(
            f'🔗 <a href="{h(book["review_link"])}">{h(s(lang, "review_label"))}</a>'
        )
    if book["description"]:
        lines += ["", f"<i>{h(book['description'])}</i>"]
    meta = (
        f"<i>{h(s(lang, 'added_by'))}: {h(format_user(book))}"
        f"  •  {h(s(lang, 'added_on'))}: {h(book['added_at'])}"
    )
    if book["discussed"] and book["discussed_at"]:
        meta += f"  •  ✅ {h(s(lang, 'discussed_on'))}: {h(book['discussed_at'])}"
    meta += "</i>"
    lines += ["", meta]
    return "\n".join(lines)


def book_compact_line(index: int, book: BookLike) -> str:
    year = book["creation_year"]
    year_suffix = f" ({year})" if year is not None else ""
    return f"{index}. <b>{h(book['title'])}</b> — {h(book['author'])}{year_suffix}"


TELEGRAM_MESSAGE_MAX = 4000


async def send_chunked_html_messages(
    bot,
    chat_id: int,
    lines: Sequence[str],
    *,
    joiner: str = "\n",
) -> None:
    """Send lines in as few Telegram messages as possible (HTML parse mode)."""
    if not lines:
        return
    chunk = ""
    for line in lines:
        candidate = joiner.join(filter(None, [chunk, line])) if chunk else line
        if len(candidate) > TELEGRAM_MESSAGE_MAX:
            if chunk:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=PM)
            chunk = line
            if len(chunk) > TELEGRAM_MESSAGE_MAX:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=PM)
                chunk = ""
        else:
            chunk = candidate
    if chunk:
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=PM)


def _parse_list_callback(data: str) -> tuple[str, str | None]:
    """Return (filter: all|unvoted, format: compact|full|None)."""
    parts = data.split(":")
    if parts[0] != "list" or len(parts) not in (2, 3):
        raise ValueError(f"unexpected list callback: {data!r}")
    filter_choice = parts[1]
    format_choice = parts[2] if len(parts) == 3 else None
    if filter_choice not in ("all", "unvoted"):
        raise ValueError(f"unexpected list filter: {filter_choice!r}")
    if format_choice is not None and format_choice not in ("compact", "full"):
        raise ValueError(f"unexpected list format: {format_choice!r}")
    return filter_choice, format_choice


async def _show_list_format_prompt(
    query, ctx: ContextTypes.DEFAULT_TYPE, filter_choice: str
) -> None:
    ctx.user_data["pending_list_choice"] = filter_choice
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(ctx, "list_compact_btn"),
                    callback_data=f"list:{filter_choice}:compact",
                ),
                InlineKeyboardButton(
                    tr(ctx, "list_full_btn"),
                    callback_data=f"list:{filter_choice}:full",
                ),
            ]
        ]
    )
    await query.edit_message_text(
        tr(ctx, "list_format_prompt"), reply_markup=keyboard, parse_mode=PM
    )


def books_keyboard(
    books: Sequence[BookLike], prefix: str, cancel_label: str
) -> InlineKeyboardMarkup:
    buttons = []
    for b in books:
        label = f"{b['title']} — {b['author']}"
        if len(label) > 48:
            label = label[:45] + "…"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"{prefix}:{b['id']}")]
        )
    buttons.append(
        [InlineKeyboardButton(cancel_label, callback_data=f"{prefix}:cancel")]
    )
    return InlineKeyboardMarkup(buttons)


def _notify_book_ids(ctx: ContextTypes.DEFAULT_TYPE) -> set[int]:
    raw = ctx.user_data.get("notify_book_ids")
    if raw is None:
        raw = set()
        ctx.user_data["notify_book_ids"] = raw
    return raw


def notify_books_keyboard(
    lang: str,
    books: Sequence[BookLike],
    selected: set[int],
    page: int,
    prefix: str,
    *,
    done_label_key: str,
) -> InlineKeyboardMarkup:
    total = len(books)
    page_size = NOTIFY_BOOKS_PAGE_SIZE
    start = page * page_size
    chunk = books[start : start + page_size]
    buttons: list[list[InlineKeyboardButton]] = []
    for b in chunk:
        bid = int(b["id"])
        mark = "✅" if bid in selected else "⬜"
        label = f"{b['title']} — {b['author']}"
        if b["discussed"]:
            label = f"📌 {label}"
        if len(label) > 42:
            label = label[:39] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{mark} {label}",
                    callback_data=f"{prefix}:toggle:{bid}:{page}",
                )
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if start > 0:
        nav.append(
            InlineKeyboardButton("◀️", callback_data=f"{prefix}:page:{page - 1}")
        )
    if start + page_size < total:
        nav.append(
            InlineKeyboardButton("▶️", callback_data=f"{prefix}:page:{page + 1}")
        )
    if nav:
        buttons.append(nav)
    buttons.append(
        [
            InlineKeyboardButton(
                s(lang, done_label_key),
                callback_data=f"{prefix}:done",
            )
        ]
    )
    buttons.append(
        [InlineKeyboardButton(s(lang, "cancel_btn"), callback_data=f"{prefix}:cancel")]
    )
    return InlineKeyboardMarkup(buttons)


async def show_notify_books_picker(
    update_or_query: Any,
    ctx: ContextTypes.DEFAULT_TYPE,
    books: Sequence[BookLike],
    *,
    page: int = 0,
    is_callback: bool = False,
    prefix: str,
    prompt_key: str,
    done_label_key: str,
) -> int:
    lang = get_lang(ctx)
    selected = _notify_book_ids(ctx)
    text = tr(ctx, prompt_key, count=len(selected))
    markup = notify_books_keyboard(
        lang, books, selected, page, prefix, done_label_key=done_label_key
    )
    if is_callback:
        await update_or_query.edit_message_text(text, reply_markup=markup, parse_mode=PM)
    else:
        await update_or_query.message.reply_text(text, reply_markup=markup, parse_mode=PM)
    ctx.user_data["notify_books_page"] = page
    if prefix == "admin_notify_chat_pick":
        return ADMIN_NOTIFY_CHAT_PICK
    return ADMIN_NOTIFY_PICK


def meetings_keyboard(
    meetings: Sequence[sqlite3.Row], prefix: str, cancel_label: str
) -> InlineKeyboardMarkup:
    buttons = []
    for m in meetings:
        label = f"{m['meeting_date']} — {m['title']}"
        if m["attendee_count"]:
            label += f" ({m['attendee_count']})"
        if len(label) > 48:
            label = label[:45] + "…"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"{prefix}:{m['id']}")]
        )
    buttons.append(
        [InlineKeyboardButton(cancel_label, callback_data=f"{prefix}:cancel")]
    )
    return InlineKeyboardMarkup(buttons)


def _meeting_attendee_ids(ctx: ContextTypes.DEFAULT_TYPE) -> set[int]:
    raw = ctx.user_data.get("meeting_attendee_ids")
    if raw is None:
        raw = set()
        ctx.user_data["meeting_attendee_ids"] = raw
    return raw


async def _refresh_chat_admin_suggestions(bot: Bot) -> None:
    """Best-effort: record chat admins as known users for attendee suggestions."""
    if not config.ALLOWED_CHAT_ID:
        return
    try:
        admins = await bot.get_chat_administrators(config.ALLOWED_CHAT_ID)
    except Exception as e:
        logger.warning("Could not fetch chat administrators for meeting suggestions: %s", e)
        return
    for member in admins:
        user = member.user
        if user.is_bot:
            continue
        db_upsert_club_user(user.id, user.full_name or "", user.username)


def meeting_attendees_keyboard(
    lang: str,
    suggestions: Sequence[sqlite3.Row],
    selected: set[int],
    page: int,
) -> InlineKeyboardMarkup:
    total = len(suggestions)
    page_size = MEETING_ATTENDEES_PAGE_SIZE
    start = page * page_size
    chunk = suggestions[start : start + page_size]
    buttons: list[list[InlineKeyboardButton]] = []
    for row in chunk:
        uid = int(row["user_id"])
        mark = "✅" if uid in selected else "⬜"
        label = format_club_user_display(uid, row["full_name"], row["username"])
        if row["voted"]:
            label = f"🗳 {label}"
        if len(label) > 42:
            label = label[:39] + "…"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{mark} {label}",
                    callback_data=f"admin_meeting_att:toggle:{uid}:{page}",
                )
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if start > 0:
        nav.append(
            InlineKeyboardButton("◀️", callback_data=f"admin_meeting_att:page:{page - 1}")
        )
    if start + page_size < total:
        nav.append(
            InlineKeyboardButton("▶️", callback_data=f"admin_meeting_att:page:{page + 1}")
        )
    if nav:
        buttons.append(nav)
    buttons.append(
        [
            InlineKeyboardButton(
                s(lang, "meeting_attendee_add_id_btn"),
                callback_data="admin_meeting_att:addid",
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                s(lang, "meeting_attendee_done_btn"),
                callback_data="admin_meeting_att:done",
            )
        ]
    )
    buttons.append(
        [InlineKeyboardButton(s(lang, "cancel_btn"), callback_data="admin_meeting_att:cancel")]
    )
    return InlineKeyboardMarkup(buttons)


async def _show_meeting_attendee_picker(
    update_or_query: Any,
    ctx: ContextTypes.DEFAULT_TYPE,
    *,
    page: int = 0,
    is_callback: bool = False,
) -> int:
    lang = get_lang(ctx)
    book_id = ctx.user_data.get("meeting_book_id")
    if book_id is None:
        text = s(lang, "cancelled")
        if is_callback:
            await update_or_query.edit_message_text(text, parse_mode=PM)
        else:
            await update_or_query.message.reply_text(text, parse_mode=PM)
        return ConversationHandler.END
    await _refresh_chat_admin_suggestions(ctx.bot)
    suggestions = db_meeting_user_suggestions(book_id)
    selected = _meeting_attendee_ids(ctx)
    meeting_date = ctx.user_data.get("meeting_date", "")
    text = tr(
        ctx,
        "meeting_attendees_prompt",
        count=len(selected),
        date=h(str(meeting_date)),
    )
    markup = meeting_attendees_keyboard(lang, suggestions, selected, page)
    if is_callback:
        await update_or_query.edit_message_text(text, reply_markup=markup, parse_mode=PM)
    else:
        await update_or_query.message.reply_text(text, reply_markup=markup, parse_mode=PM)
    ctx.user_data["meeting_attendee_page"] = page
    return ADMIN_MEETING_ATTENDEES


def fiction_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(s(lang, "fiction_btn"), callback_data="fiction:1"),
                InlineKeyboardButton(
                    s(lang, "nonfiction_btn"), callback_data="fiction:0"
                ),
            ]
        ]
    )


def books_top_n(books: Sequence[BookLike], n: int = 5) -> list[BookLike]:
    """First n books by rank, including all ties at the nth position."""
    top: list[BookLike] = []
    for i, book in enumerate(books):
        if i < n:
            top.append(book)
        elif n > 0:
            nth = books[n - 1]
            if (
                book["avg_score"] == nth["avg_score"]
                and book["vote_count"] == nth["vote_count"]
            ):
                top.append(book)
            else:
                break
        else:
            break
    return top


async def post_book_voting_to_group_chat(
    bot: Bot, book: BookLike, *, intro_key: str
) -> bool:
    """Post a book card with inline vote buttons to the configured group chat."""
    if not config.ALLOWED_CHAT_ID:
        return False
    try:
        chat_lang = config.CHAT_LANG
        text = tr(chat_lang, intro_key) + book_card(book, chat_lang)
        await bot.send_message(
            chat_id=config.ALLOWED_CHAT_ID,
            text=text,
            parse_mode=PM,
            reply_markup=score_keyboard(book["id"], chat_lang),
        )
        return True
    except Exception as e:
        logger.warning(
            "post_book_voting_to_group_chat: failed to post book %s to chat %s: %s",
            book["id"],
            config.ALLOWED_CHAT_ID,
            e,
        )
        return False


def score_keyboard(
    book_id: int, lang: str, current: int | None = None
) -> InlineKeyboardMarkup:
    """Compact 3-button vote row to attach directly to book cards."""
    options = [
        (1, s(lang, "want_btn")),
        (0, s(lang, "meh_btn")),
        (-1, s(lang, "no_btn")),
    ]
    row = [
        InlineKeyboardButton(
            label + (" ✓" if current == score else ""),
            callback_data=f"vote_cast:{book_id}:{score}",
        )
        for score, label in options
    ]
    return InlineKeyboardMarkup([row])


def is_valid_url(text: str) -> bool:
    if not (text.startswith("http://") or text.startswith("https://")):
        return False
    # Reject characters that cannot legally appear unencoded in a URL. They are
    # the ones that would otherwise corrupt the surrounding HTML anchor.
    if any(c in text for c in '"<>') or any(c.isspace() for c in text):
        return False
    # Require something after the scheme.
    return bool(text.split("://", 1)[1])


_CREATION_YEAR_MIN = 1000
_CREATION_YEAR_MAX = 2100


def parse_optional_creation_year(text: str) -> int | None:
    """Return year, or None for /skip. Raises ValueError if invalid."""
    stripped = text.strip()
    if stripped == "/skip":
        return None
    if len(stripped) != 4 or not stripped.isdigit():
        raise ValueError("invalid year")
    year = int(stripped)
    if year < _CREATION_YEAR_MIN or year > _CREATION_YEAR_MAX:
        raise ValueError("year out of range")
    return year


def parse_date(text: str) -> str | None:
    """Return date string if valid YYYY-MM-DD, DD.MM.YYYY, or DD/MM/YYYY, else None."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
