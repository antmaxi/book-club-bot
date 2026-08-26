"""Club Voting Bot — package root (re-exported by bookclub_bot)."""

# This module intentionally defines the compatibility facade through imports.
# ruff: noqa: F401

from bookclub.config import *  # noqa: F403
from bookclub.db import *  # noqa: F403
from bookclub.domain import *  # noqa: F403

# Handlers (tests and patches import these from bookclub_bot)
from bookclub.handlers.add import *  # noqa: F403
from bookclub.handlers.add_flow import add_go_back, add_previous_state  # noqa: F403
from bookclub.handlers.admin import *  # noqa: F403
from bookclub.handlers.commands import *  # noqa: F403
from bookclub.handlers.edit_delete import *  # noqa: F403
from bookclub.handlers.misc import *  # noqa: F403
from bookclub.i18n import *  # noqa: F403
from bookclub.lifecycle import bot_notify_shutdown, bot_notify_startup
from bookclub.logging_setup import logger, logging
from bookclub.main import main, register_handlers
from bookclub.membership import _membership_cache, error_handler, membership_gate
from bookclub.notifications import (
    enqueue_new_book_notify_job,
    notify_new_book_job,
    recover_pending_new_book_notifications,
    schedule_new_book_notifications,
)
from bookclub.types import *  # noqa: F403
from bookclub.ui import *  # noqa: F403
