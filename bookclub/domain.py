from __future__ import annotations

import sqlite3

import bookclub.config as config
from bookclub.db import db_get_book
from bookclub.types import BookLike

IMPORTED_USER_ID = config.IMPORTED_USER_ID


def can_modify(user_id: int, book: BookLike, username: str | None = None) -> bool:
    """Admin always wins. For imported books (added_by=0), match by @username."""
    if user_id in config.ADMIN_IDS:
        return True
    if book["added_by"] == IMPORTED_USER_ID:
        stored = book["added_by_username"]
        clean = (username or "").lstrip("@")
        return bool(clean and stored and clean.lower() == stored.lower())
    return bool(user_id == book["added_by"])


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def require_book(book_id: int) -> sqlite3.Row:
    book = db_get_book(book_id)
    if book is None:
        raise RuntimeError(f"book {book_id} not found")
    return book
