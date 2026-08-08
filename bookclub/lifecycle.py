from __future__ import annotations

from telegram import BotCommandScopeDefault
from telegram.ext import Application

import bookclub.config as config
from bookclub.handlers.commands import COMMANDS
from bookclub.i18n import PM, T
from bookclub.logging_setup import _drain_alert_queue, logger
from bookclub.notifications import recover_pending_new_book_notifications


async def bot_notify_startup(app: Application) -> None:
    """Notify first admin that bot has started, and set default command menu."""
    try:
        await app.bot.delete_my_commands(scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(COMMANDS["ru"], scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning(f"Could not set default commands: {e}")
    if not config.ADMIN_IDS:
        return
    if config.ERROR_ALERTS:
        app.create_task(_drain_alert_queue(app))
    recover_pending_new_book_notifications(app.job_queue)
    admin_id = config.ADMIN_IDS[0]
    try:
        await app.bot.send_message(
            chat_id=admin_id, text=T["en"]["bot_started"], parse_mode=PM
        )
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")


async def bot_notify_shutdown(app: Application) -> None:
    """Notify first admin that bot is shutting down."""
    if not config.ADMIN_IDS:
        return
    admin_id = config.ADMIN_IDS[0]
    try:
        await app.bot.send_message(
            chat_id=admin_id, text=T["en"]["bot_stopped"], parse_mode=PM
        )
    except Exception as e:
        logger.error(f"Failed to send shutdown notification: {e}")
