"""
test_handlers.py — Async handler tests for bookclub_bot.py

Tests Telegram command/callback handlers using mocked Update + Context.
No real Telegram API calls are made.
"""

import os
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Bot, Chat, Message, MessageEntity, Update, User
from telegram.error import BadRequest, NetworkError
from telegram.ext import ConversationHandler

import bookclub_bot as bot
import bookclub.config as cfg

# ── Base test class with shared setUp ─────────────────────────────────────────


class BotHandlerTestCase(unittest.IsolatedAsyncioTestCase):
    """Base class: creates a fresh temp DB and standard mock update/ctx."""

    DB_FILE = "test_handlers.db"

    def setUp(self):
        cfg.DB_PATH = self.DB_FILE
        bot.DB_PATH = self.DB_FILE
        bot.init_db()

        # Disable ALLOWED_CHAT_ID so membership gate never blocks during tests
        self._orig_chat_id = cfg.ALLOWED_CHAT_ID
        cfg.ALLOWED_CHAT_ID = None
        bot.ALLOWED_CHAT_ID = None

        # The membership cache is module-global; a verdict cached by one test
        # would otherwise leak into the next.
        bot._membership_cache.clear()

        self.update = MagicMock(spec=Update)
        self.update.callback_query = None  # Explicitly set to None by default
        self.ctx = MagicMock()
        self.ctx.user_data = {"lang": "en"}
        self.ctx.bot = AsyncMock()

        self.message = AsyncMock(spec=Message)
        self.update.message = self.message
        self.update.effective_chat = MagicMock(spec=Chat)
        self.update.effective_chat.id = 12345
        self.update.effective_chat.type = "private"
        self.update.effective_user = MagicMock(spec=User)
        self.update.effective_user.id = 67890
        self.update.effective_user.full_name = "Test User"
        self.update.effective_user.username = "testuser"

        # Default: notifications off so /list doesn't show opt-in prompt
        bot.db_set_user_setting(67890, "notify_new_books", 0)

    def tearDown(self):
        cfg.ALLOWED_CHAT_ID = self._orig_chat_id
        bot.ALLOWED_CHAT_ID = self._orig_chat_id
        if os.path.exists(self.DB_FILE):
            os.remove(self.DB_FILE)

    def _callback_query(self, data, user_id=None):
        """Return a mock callback query with the given data."""
        q = AsyncMock()
        q.data = data
        q.from_user = MagicMock()
        q.from_user.id = user_id or self.update.effective_user.id
        q.from_user.username = "testuser"
        self.update.callback_query = q
        return q

    def _add_book(
        self,
        title="Book",
        author="Author",
        pages=100,
        fiction=True,
        review="",
        desc="",
        user_id=1,
        username="u",
    ):
        return bot.db_add_book(
            title, author, pages, fiction, review, desc, user_id, username
        )


# ── /start and /help ───────────────────────────────────────────────────────────


class TestStartHelp(BotHandlerTestCase):

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_sends_welcome(self, mock_set):
        await bot.cmd_start(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Welcome", text)
        self.assertIn("/info", text)
        self.assertNotIn("/adminconsole", text)

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_admin_includes_adminconsole_in_help(self, mock_set):
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = [self.update.effective_user.id]
            await bot.cmd_start(self.update, self.ctx)
            text = self.message.reply_text.call_args[0][0]
            self.assertIn("/adminconsole", text)
        finally:
            cfg.ADMIN_IDS = old

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_sets_menu(self, mock_set):
        await bot.cmd_start(self.update, self.ctx)
        mock_set.assert_called_once_with(self.ctx.bot, self.update, "en")

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_ru(self, mock_set):
        self.ctx.user_data["lang"] = "ru"
        await bot.cmd_start(self.update, self.ctx)
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Добро пожаловать", text)
        self.assertIn("/info", text)

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_help_delegates_to_start(self, mock_set):
        await bot.cmd_help(self.update, self.ctx)
        self.message.reply_text.assert_called_once()


# ── /info ─────────────────────────────────────────────────────────────────────


class TestInfo(BotHandlerTestCase):

    # Git reports the commit time as a Unix timestamp (--format=%ct), which the
    # handler renders via fmt_dt_utc into server-local time with a UTC offset.
    GIT_COMMIT_EPOCH = 1775649600  # 2026-04-04 12:00:00 UTC

    @patch("os.path.exists")
    @patch("subprocess.check_output")
    async def test_cmd_info_en(self, mock_git, mock_exists):
        mock_exists.return_value = True
        mock_git.return_value = f"{self.GIT_COMMIT_EPOCH}\n".encode()
        with patch.object(cfg, "GITHUB_REPO", "https://test.repo"):
            await bot.cmd_info(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Book Club Bot", text)
        import datetime

        expected = bot.fmt_dt_utc(
            datetime.datetime.fromtimestamp(
                self.GIT_COMMIT_EPOCH, tz=datetime.timezone.utc
            )
        )
        self.assertIn(expected, text)
        self.assertRegex(text, r"UTC[+-]\d{2}:\d{2}")
        self.assertIn("https://test.repo", text)
        self.assertIn("@antmaxi", text)

    @patch("os.path.exists")
    @patch("subprocess.check_output")
    async def test_cmd_info_ru(self, mock_git, mock_exists):
        mock_exists.return_value = True
        self.ctx.user_data["lang"] = "ru"
        mock_git.return_value = f"{self.GIT_COMMIT_EPOCH}\n".encode()
        await bot.cmd_info(self.update, self.ctx)
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Последнее обновление", text)
        import datetime

        expected = bot.fmt_dt_utc(
            datetime.datetime.fromtimestamp(
                self.GIT_COMMIT_EPOCH, tz=datetime.timezone.utc
            )
        )
        self.assertIn(expected, text)
        self.assertRegex(text, r"UTC[+-]\d{2}:\d{2}")
        self.assertIn("@antmaxi", text)

    @patch("os.path.exists")
    @patch("os.path.getmtime")
    @patch("subprocess.check_output")
    async def test_cmd_info_git_fallback_to_mtime(
        self, mock_git, mock_mtime, mock_exists
    ):
        # Git exists but fails
        mock_exists.return_value = True
        mock_git.side_effect = Exception("git error")
        mock_mtime.return_value = 1775728800

        await bot.cmd_info(self.update, self.ctx)

        text = self.message.reply_text.call_args[0][0]
        self.assertNotEqual(text, "unknown")
        # The exact string depends on local timezone, so build the expectation
        # the same way the handler does.
        import datetime

        expected_date = bot.fmt_dt_utc(
            datetime.datetime.fromtimestamp(1775728800, tz=datetime.timezone.utc)
        )
        self.assertIn(expected_date, text)
        self.assertRegex(text, r"UTC[+-]\d{2}:\d{2}")

    @patch("os.path.exists")
    @patch("subprocess.check_output")
    async def test_cmd_info_no_git_dir_fallback(self, mock_git, mock_exists):
        # No .git directory
        mock_exists.return_value = False

        await bot.cmd_info(self.update, self.ctx)

        # Should not even call git
        mock_git.assert_not_called()

        text = self.message.reply_text.call_args[0][0]
        self.assertIn("20", text)  # Should have a date starting with 20...


# ── set_user_commands ──────────────────────────────────────────────────────────


class TestSetUserCommands(BotHandlerTestCase):

    @patch("bookclub.handlers.commands.BotCommandScopeChat")
    async def test_private_chat_uses_chat_scope(self, mock_scope_cls):
        mock_scope = MagicMock()
        mock_scope_cls.return_value = mock_scope
        mock_bot = AsyncMock()
        self.update.effective_chat.type = "private"

        await bot.set_user_commands(mock_bot, self.update, "en")

        mock_bot.delete_my_commands.assert_called_once_with(scope=mock_scope)
        mock_bot.set_my_commands.assert_called_once_with(
            bot.commands_for_user("en", self.update.effective_user.id),
            scope=mock_scope,
        )

    @patch("bookclub.handlers.commands.BotCommandScopeChatMember")
    async def test_group_chat_uses_member_scope(self, mock_scope_cls):
        mock_scope = MagicMock()
        mock_scope_cls.return_value = mock_scope
        mock_bot = AsyncMock()
        self.update.effective_chat.type = "supergroup"

        await bot.set_user_commands(mock_bot, self.update, "ru")

        mock_bot.set_my_commands.assert_called_once_with(
            bot.commands_for_user("ru", self.update.effective_user.id),
            scope=mock_scope,
        )

    async def test_commands_for_user_hides_adminconsole_for_members(self):
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = [999999]
            member = bot.commands_for_user("en", 12345)
            self.assertNotIn("adminconsole", [c.command for c in member])
            admin = bot.commands_for_user("en", 999999)
            self.assertIn("adminconsole", [c.command for c in admin])
        finally:
            cfg.ADMIN_IDS = old

    async def test_set_user_commands_exception_does_not_propagate(self):
        mock_bot = AsyncMock()
        mock_bot.set_my_commands.side_effect = Exception("Network error")
        # Should not raise
        await bot.set_user_commands(mock_bot, self.update, "en")


# ── COMMANDS menu structure ────────────────────────────────────────────────────


class TestCommandsMenu(BotHandlerTestCase):

    async def test_settings_in_both_menus(self):
        for lang in ("en", "ru"):
            cmds = [c.command for c in bot.COMMANDS[lang]]
            self.assertIn("settings", cmds, f"'settings' missing from {lang} menu")

    async def test_language_not_in_menus(self):
        for lang in ("en", "ru"):
            cmds = [c.command for c in bot.COMMANDS[lang]]
            self.assertNotIn(
                "language", cmds, f"'language' should not be in {lang} menu"
            )

    async def test_settings_description_en(self):
        desc = next(
            c.description for c in bot.COMMANDS["en"] if c.command == "settings"
        )
        self.assertEqual(desc, "⚙️ Settings")

    async def test_settings_description_ru(self):
        desc = next(
            c.description for c in bot.COMMANDS["ru"] if c.command == "settings"
        )
        self.assertEqual(desc, "⚙️ Настройки")

    async def test_info_in_both_menus(self):
        for lang in ("en", "ru"):
            cmds = [c.command for c in bot.COMMANDS[lang]]
            self.assertIn("info", cmds, f"'info' missing from {lang} menu")

    async def test_info_description_en(self):
        desc = next(c.description for c in bot.COMMANDS["en"] if c.command == "info")
        self.assertEqual(desc, "ℹ️ About the bot")

    async def test_info_description_ru(self):
        desc = next(c.description for c in bot.COMMANDS["ru"] if c.command == "info")
        self.assertEqual(desc, "ℹ️ О боте")

    async def test_info_after_help_in_menu(self):
        for lang in ("en", "ru"):
            cmds = [c.command for c in bot.COMMANDS[lang]]
            self.assertEqual(cmds[-2:], ["help", "info"])


# ── /list ──────────────────────────────────────────────────────────────────────


class TestList(BotHandlerTestCase):

    async def test_cmd_list_shows_prompt(self):
        await bot.cmd_list(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Show all books", text)
        self.assertIn("reply_markup", self.message.reply_text.call_args[1])

    async def test_list_choice_all_shows_format_prompt(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        q.edit_message_text.assert_called_once()
        self.assertIn("How would you like", q.edit_message_text.call_args[0][0])
        q.delete_message.assert_not_called()

    async def test_list_choice_all_sends_book(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        self._add_book("Book 1")
        q = self._callback_query("list:all:full")
        await bot.list_choice_cb(self.update, self.ctx)
        q.answer.assert_called_once()
        q.delete_message.assert_called_once()
        self.ctx.bot.send_message.assert_called_once()
        self.assertIn("Book 1", self.ctx.bot.send_message.call_args[1]["text"])

    async def test_list_choice_unvoted_excludes_voted_book(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        book_id = self._add_book("Book 1")
        bot.db_cast_vote(self.update.effective_user.id, book_id, 1)
        q = self._callback_query("list:unvoted:full")
        await bot.list_choice_cb(self.update, self.ctx)
        self.ctx.bot.send_message.assert_not_called()
        q.edit_message_text.assert_called_once()
        self.assertIn("voted on all", q.edit_message_text.call_args[0][0])

    async def test_list_choice_all_no_books(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        q = self._callback_query("list:all:compact")
        await bot.list_choice_cb(self.update, self.ctx)
        self.ctx.bot.send_message.assert_not_called()

    async def test_list_choice_multiple_books(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        self._add_book("Alpha")
        self._add_book("Beta")
        q = self._callback_query("list:all:full")
        await bot.list_choice_cb(self.update, self.ctx)
        self.assertEqual(self.ctx.bot.send_message.call_count, 2)

    async def test_list_choice_compact_single_message(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        bot.db_add_book(
            "Alpha", "Author A", 100, True, "", "", 1, "u", creation_year=2001
        )
        bot.db_add_book("Beta", "Author B", 100, True, "", "", 1, "u")
        q = self._callback_query("list:all:compact")
        await bot.list_choice_cb(self.update, self.ctx)
        self.ctx.bot.send_message.assert_called_once()
        text = self.ctx.bot.send_message.call_args[1]["text"]
        self.assertIn("Alpha", text)
        self.assertIn("Author A", text)
        self.assertIn("(2001)", text)
        self.assertIn("Beta", text)
        self.assertIn("Author B", text)

    async def test_list_triggers_optin_when_setting_missing(self):
        """First-time users without a notify setting see the opt-in prompt."""
        with sqlite3.connect(bot.DB_PATH) as conn:
            conn.execute(
                "DELETE FROM user_settings WHERE user_id=?",
                (self.update.effective_user.id,),
            )
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        q.edit_message_text.assert_called_once()
        self.assertIn(
            "Would you like to receive notifications",
            q.edit_message_text.call_args[0][0],
        )
        self.assertEqual(self.ctx.user_data["pending_list_choice"], "all")

    async def test_list_no_optin_when_setting_already_set(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        self._add_book("B")
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        q.edit_message_text.assert_called_once()
        self.assertIn("How would you like", q.edit_message_text.call_args[0][0])
        self.ctx.bot.send_message.assert_not_called()


# ── /top ──────────────────────────────────────────────────────────────────────


class TestTop(BotHandlerTestCase):

    async def test_cmd_top_no_books(self):
        await bot.cmd_top(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        self.assertIn("No undiscussed", self.message.reply_text.call_args[0][0])

    async def test_cmd_top_shows_top_5(self):
        """With 7 books of different scores, only top 5 appear."""
        for i in range(1, 6):
            bid = self._add_book(f"Book {i}", user_id=i)
            bot.db_cast_vote(1001, bid, 1)
        for i in range(6, 8):
            bid = self._add_book(f"Book {i}", user_id=i)
            bot.db_cast_vote(1001, bid, -1)

        await bot.cmd_top(self.update, self.ctx)

        # First reply_text call is the top list
        text = self.message.reply_text.call_args_list[0][0][0]
        for i in range(1, 6):
            self.assertIn(f"Book {i}", text)
        self.assertNotIn("Book 6", text)
        self.assertNotIn("Book 7", text)

    async def test_cmd_top_tie_at_5th_includes_tied_books(self):
        """If books 5 and 6 have identical score+votes, both are shown."""
        for i in range(1, 6):
            bid = self._add_book(f"Book {i}", user_id=i)
            bot.db_cast_vote(1001, bid, 1)
        # Books 6 & 7 also score 1 with 1 vote each — tied with Book 5
        for i in range(6, 8):
            bid = self._add_book(f"Book {i}", user_id=i)
            bot.db_cast_vote(1001, bid, 1)

        await bot.cmd_top(self.update, self.ctx)

        text = self.message.reply_text.call_args_list[0][0][0]
        for i in range(1, 8):
            self.assertIn(f"Book {i}", text)

    async def test_cmd_top_score_calc_button_sent(self):
        self._add_book("B")
        await bot.cmd_top(self.update, self.ctx)
        # Last call should have the score calc button
        last_call = self.message.reply_text.call_args_list[-1]
        kwargs = last_call[1]
        self.assertIn("reply_markup", kwargs)
        btn = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(btn.callback_data, "score_calc_info")

    async def test_cmd_top_score_calc_button_text_en(self):
        self._add_book("B")
        await bot.cmd_top(self.update, self.ctx)
        last_call = self.message.reply_text.call_args_list[-1]
        btn = last_call[1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(btn.text, "📊 How a score is calculated")

    async def test_cmd_top_ru(self):
        self.ctx.user_data["lang"] = "ru"
        self._add_book("Книга 1")
        await bot.cmd_top(self.update, self.ctx)
        text = self.message.reply_text.call_args_list[0][0][0]
        self.assertIn("Топ книг", text)

    async def test_cmd_top_includes_unvoted_books(self):
        """Books with no votes should still appear in /top."""
        self._add_book("Unvoted")
        await bot.cmd_top(self.update, self.ctx)
        text = self.message.reply_text.call_args_list[0][0][0]
        self.assertIn("Unvoted", text)


# ── score_calc_cb ──────────────────────────────────────────────────────────────


class TestScoreCalc(BotHandlerTestCase):

    async def test_score_calc_cb_shows_alert(self):
        q = self._callback_query("score_calc_info")
        await bot.score_calc_cb(self.update, self.ctx)
        q.answer.assert_called_once()
        kwargs = q.answer.call_args[1]
        self.assertTrue(kwargs["show_alert"])
        self.assertIn("Want: +1 point", kwargs["text"])

    async def test_score_calc_cb_ru(self):
        self.ctx.user_data["lang"] = "ru"
        q = self._callback_query("score_calc_info")
        await bot.score_calc_cb(self.update, self.ctx)
        kwargs = q.answer.call_args[1]
        self.assertIn("Хочу: +1 балл", kwargs["text"])


# ── /add conversation ──────────────────────────────────────────────────────────


class TestAddConversation(BotHandlerTestCase):

    async def test_cmd_add_returns_adding_title(self):
        state = await bot.cmd_add(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_TITLE)
        self.message.reply_text.assert_called_once()

    async def test_add_title_stores_and_advances(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "My Book"
        state = await bot.add_title(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["new_book"]["title"], "My Book")
        self.assertEqual(state, bot.ADDING_AUTHOR)

    async def test_add_title_similar_warns_before_author(self):
        self._add_book("War and Peace")
        self.ctx.user_data["new_book"] = {}
        self.message.text = "War and Peace Extended"
        state = await bot.add_title(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_TITLE_CONFIRM)
        warning = self.message.reply_text.call_args[0][0]
        self.assertIn("War and Peace", warning)

    async def test_add_title_similar_confirm_advances(self):
        self._add_book("War and Peace")
        self.ctx.user_data["new_book"] = {"title": "War and Peace Extended"}
        q = self._callback_query("title_sim:yes")
        state = await bot.add_title_similar_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_AUTHOR)
        q.edit_message_text.assert_called_once()

    async def test_add_author_stores_and_advances(self):
        self.ctx.user_data["new_book"] = {"title": "T"}
        self.message.text = "Jane Austen"
        state = await bot.add_author(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["new_book"]["author"], "Jane Austen")
        self.assertEqual(state, bot.ADDING_PAGES)

    async def test_add_pages_valid(self):
        self.ctx.user_data["new_book"] = {"title": "T", "author": "A"}
        self.message.text = "320"
        state = await bot.add_pages(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["new_book"]["pages"], 320)
        self.assertEqual(state, bot.ADDING_FICTION)

    async def test_add_pages_invalid_text(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "not a number"
        state = await bot.add_pages(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_PAGES)
        self.assertIn("valid number", self.message.reply_text.call_args[0][0])

    async def test_add_pages_zero_invalid(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "0"
        state = await bot.add_pages(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_PAGES)

    async def test_add_back_from_pages_returns_author(self):
        self.ctx.user_data["new_book"] = {
            "title": "T",
            "author": "Author Name",
            "pages": 100,
        }
        self.ctx.user_data["add_state"] = bot.ADDING_PAGES
        self.message.text = "/back"
        state = await bot.add_go_back(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_AUTHOR)
        self.assertEqual(self.ctx.user_data["add_state"], bot.ADDING_AUTHOR)
        reply = self.message.reply_text.call_args[0][0]
        self.assertIn("Author Name", reply)

    async def test_add_back_callback_from_fiction_returns_pages(self):
        self.ctx.user_data["new_book"] = {
            "title": "T",
            "author": "A",
            "pages": 200,
            "fiction": True,
        }
        self.ctx.user_data["add_state"] = bot.ADDING_FICTION
        q = self._callback_query("add_back")
        state = await bot.add_go_back(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_PAGES)
        q.edit_message_text.assert_called_once()
        text = q.edit_message_text.call_args[0][0]
        self.assertIn("200", text)

    async def test_add_review_valid(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "https://goodreads.com/book/1"
        state = await bot.add_review(self.update, self.ctx)
        self.assertEqual(
            self.ctx.user_data["new_book"]["review_link"],
            "https://goodreads.com/book/1",
        )
        self.assertEqual(state, bot.ADDING_ORIGINAL_LANGUAGE)

    async def test_add_original_language_skip(self):
        self.ctx.user_data["new_book"] = {"review_link": "http://x.com"}
        self.message.text = "/skip"
        state = await bot.add_original_language(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["new_book"]["original_language"], "")
        self.assertEqual(state, bot.ADDING_CREATION_YEAR)

    async def test_add_creation_year_valid(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "1984"
        state = await bot.add_creation_year(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["new_book"]["creation_year"], 1984)
        self.assertEqual(state, bot.ADDING_DESCRIPTION)

    async def test_add_creation_year_skip(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "/skip"
        state = await bot.add_creation_year(self.update, self.ctx)
        self.assertIsNone(self.ctx.user_data["new_book"]["creation_year"])
        self.assertEqual(state, bot.ADDING_DESCRIPTION)

    async def test_add_creation_year_invalid(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "84"
        state = await bot.add_creation_year(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_CREATION_YEAR)

    async def test_add_review_invalid_url(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "not a url"
        state = await bot.add_review(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_REVIEW)

    async def test_add_description_completes_and_schedules_job(self):
        self.ctx.user_data["new_book"] = {
            "title": "T",
            "author": "A",
            "pages": 100,
            "fiction": True,
            "review_link": "http://x.com",
            "original_language": "German",
        }
        self.message.text = "Great book"
        self.ctx.job_queue = MagicMock()

        state = await bot.add_description(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.message.reply_text.assert_called_once()
        confirm = self.message.reply_text.call_args[0][0]
        self.assertIn("Book added", confirm)
        self.assertIn("5 minutes", confirm)
        self.ctx.job_queue.run_once.assert_called_once()
        job_kwargs = self.ctx.job_queue.run_once.call_args[1]
        self.assertEqual(job_kwargs["when"], bot.NEW_BOOK_NOTIFY_DELAY_SECONDS)
        book_id = job_kwargs["data"]["book_id"]
        book = bot.db_get_book(book_id)
        self.assertEqual(book["notify_adder_id"], self.update.effective_user.id)
        self.assertEqual(book["notify_sent"], 0)

    async def test_add_description_no_job_queue(self):
        self.ctx.user_data["new_book"] = {
            "title": "T",
            "author": "A",
            "pages": 100,
            "fiction": True,
            "review_link": "http://x.com",
        }
        self.message.text = "Desc"
        self.ctx.job_queue = None

        state = await bot.add_description(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.assertIn("Book added", self.message.reply_text.call_args[0][0])

    async def test_add_description_skip(self):
        self.ctx.user_data["new_book"] = {
            "title": "T",
            "author": "A",
            "pages": 100,
            "fiction": True,
            "review_link": "http://x.com",
        }
        self.message.text = "/skip"
        self.ctx.job_queue = None

        await bot.add_description(self.update, self.ctx)

        # Book should be saved with empty description
        books = bot.db_get_books(discussed=False)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["description"], "")

    async def test_add_description_missing_new_book_returns_cancelled(self):
        self.ctx.user_data = {"lang": "en"}
        self.message.text = "some text"
        self.ctx.job_queue = MagicMock()

        state = await bot.add_description(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.assertIn("Cancelled", self.message.reply_text.call_args[0][0])
        self.ctx.job_queue.run_once.assert_not_called()


# ── /settings ─────────────────────────────────────────────────────────────────


class TestSettings(BotHandlerTestCase):

    async def test_cmd_settings_shows_panel(self):
        await bot.cmd_settings(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Settings", text)
        self.assertIn("Notifications", text)

    async def test_settings_toggle_notify_minus_one_to_one(self):
        # Default is -1; first toggle → 1
        q = self._callback_query("settings:toggle_notify")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(
            bot.db_get_user_setting(self.update.effective_user.id, "notify_new_books"),
            1,
        )

    async def test_settings_toggle_notify_one_to_zero(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 1)
        q = self._callback_query("settings:toggle_notify")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(
            bot.db_get_user_setting(self.update.effective_user.id, "notify_new_books"),
            0,
        )

    async def test_settings_toggle_notify_zero_to_one(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        q = self._callback_query("settings:toggle_notify")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(
            bot.db_get_user_setting(self.update.effective_user.id, "notify_new_books"),
            1,
        )

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_settings_toggle_lang_en_to_ru(self, mock_set):
        self.ctx.user_data["lang"] = "en"
        q = self._callback_query("settings:toggle_lang")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["lang"], "ru")
        q.answer.assert_called_once_with("🇷🇺 Язык установлен: Русский.")
        mock_set.assert_called_once_with(self.ctx.bot, self.update, "ru")

    @patch("bookclub.handlers.commands.set_user_commands", new_callable=AsyncMock)
    async def test_settings_toggle_lang_ru_to_en(self, mock_set):
        self.ctx.user_data["lang"] = "ru"
        q = self._callback_query("settings:toggle_lang")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["lang"], "en")
        mock_set.assert_called_once_with(self.ctx.bot, self.update, "en")

    async def test_optin_yes_sets_notify_and_continues_list(self):
        with sqlite3.connect(bot.DB_PATH) as conn:
            conn.execute(
                "DELETE FROM user_settings WHERE user_id=?",
                (self.update.effective_user.id,),
            )
        self._add_book("Book 1")
        self.ctx.user_data["pending_list_choice"] = "unvoted"
        q = self._callback_query("settings:optin:1")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(
            bot.db_get_user_setting(self.update.effective_user.id, "notify_new_books"),
            1,
        )
        q.answer.assert_called_once_with("✅ Settings saved!")
        q.edit_message_text.assert_called_once()
        self.assertIn("How would you like", q.edit_message_text.call_args[0][0])
        self.ctx.bot.send_message.assert_not_called()

    async def test_optin_no_sets_zero(self):
        with sqlite3.connect(bot.DB_PATH) as conn:
            conn.execute(
                "DELETE FROM user_settings WHERE user_id=?",
                (self.update.effective_user.id,),
            )
        self.ctx.user_data["pending_list_choice"] = "all"
        q = self._callback_query("settings:optin:0")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(
            bot.db_get_user_setting(self.update.effective_user.id, "notify_new_books"),
            0,
        )


# ── Membership gate ────────────────────────────────────────────────────────────


class TestMembershipGate(BotHandlerTestCase):

    async def test_gate_allows_when_no_chat_id_set(self):
        cfg.ALLOWED_CHAT_ID = None
        result = await bot._check_membership(self.update, self.ctx)
        self.assertTrue(result)

    async def test_gate_allows_admin_without_api_call(self):
        cfg.ALLOWED_CHAT_ID = -1001111111111
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = [self.update.effective_user.id]
            result = await bot._check_membership(self.update, self.ctx)
            self.assertTrue(result)
            # Bot API should NOT have been called for admin
            self.ctx.bot.get_chat_member.assert_not_called()
        finally:
            cfg.ADMIN_IDS = old

    async def test_gate_allows_member_status(self):
        cfg.ALLOWED_CHAT_ID = -1001111111111
        for status in ("member", "administrator", "creator", "restricted"):
            bot._membership_cache.clear()  # else only the first status is tested
            member = MagicMock()
            member.status = status
            self.ctx.bot.get_chat_member = AsyncMock(return_value=member)
            result = await bot._check_membership(self.update, self.ctx)
            self.assertTrue(result, f"Status '{status}' should be allowed")

    async def test_gate_blocks_non_member(self):
        cfg.ALLOWED_CHAT_ID = -1001111111111
        for status in ("left", "kicked"):
            bot._membership_cache.clear()  # else only the first status is tested
            member = MagicMock()
            member.status = status
            self.ctx.bot.get_chat_member = AsyncMock(return_value=member)
            result = await bot._check_membership(self.update, self.ctx)
            self.assertFalse(result, f"Status '{status}' should be blocked")

    async def test_gate_allows_on_chat_not_found(self):
        """If the bot cannot access ALLOWED_CHAT_ID, do not lock out real members."""
        cfg.ALLOWED_CHAT_ID = -1001111111111
        self.ctx.bot.get_chat_member = AsyncMock(
            side_effect=BadRequest("Chat not found")
        )
        result = await bot._check_membership(self.update, self.ctx)
        self.assertTrue(result)

    async def test_gate_blocks_on_unknown_api_exception(self):
        cfg.ALLOWED_CHAT_ID = -1001111111111
        self.ctx.bot.get_chat_member = AsyncMock(side_effect=Exception("API error"))
        result = await bot._check_membership(self.update, self.ctx)
        self.assertFalse(result)

    async def test_gate_caches_result_to_avoid_api_call_per_update(self):
        """The gate runs on every update; it must not hit the API each time."""
        cfg.ALLOWED_CHAT_ID = -1001111111111
        member = MagicMock()
        member.status = "member"
        self.ctx.bot.get_chat_member = AsyncMock(return_value=member)
        for _ in range(5):
            self.assertTrue(await bot._check_membership(self.update, self.ctx))
        self.ctx.bot.get_chat_member.assert_awaited_once()

    async def test_gate_does_not_cache_api_failures(self):
        """A transient error must not lock a real member out for the whole TTL."""
        cfg.ALLOWED_CHAT_ID = -1001111111111
        self.ctx.bot.get_chat_member = AsyncMock(side_effect=Exception("boom"))
        self.assertFalse(await bot._check_membership(self.update, self.ctx))

        member = MagicMock()
        member.status = "member"
        self.ctx.bot.get_chat_member = AsyncMock(return_value=member)
        self.assertTrue(await bot._check_membership(self.update, self.ctx))

    async def test_leaving_evicts_user_from_membership_cache(self):
        cfg.ALLOWED_CHAT_ID = -1001111111111
        uid = self.update.effective_user.id
        bot._membership_cache[uid] = (True, datetime.now())
        self.update.message.left_chat_member = MagicMock(spec=User)
        self.update.message.left_chat_member.id = uid
        await bot.membership_gate(self.update, self.ctx)
        self.assertNotIn(uid, bot._membership_cache)

    async def test_gate_ignores_new_chat_members_service_message(self):
        cfg.ALLOWED_CHAT_ID = -1001111111111
        joiner = MagicMock(spec=User)
        joiner.id = 55555
        bot._membership_cache[55555] = (False, datetime.now())
        self.update.message.left_chat_member = None
        self.update.message.new_chat_members = [joiner]
        await bot.membership_gate(self.update, self.ctx)
        self.assertNotIn(55555, bot._membership_cache)
        self.message.reply_text.assert_not_called()

    async def test_gate_ignores_left_chat_member_service_message(self):
        """A 'user left the chat' service message must not trigger a reply in the group."""
        cfg.ALLOWED_CHAT_ID = -1001111111111
        self.update.message.left_chat_member = MagicMock(spec=User)
        await bot.membership_gate(self.update, self.ctx)
        self.ctx.bot.get_chat_member.assert_not_called()
        self.message.reply_text.assert_not_called()


# ── Startup / shutdown notifications ──────────────────────────────────────────


class TestStartupShutdown(BotHandlerTestCase):

    async def test_bot_notify_startup_sends_to_first_admin(self):
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = [111, 222]
            app = MagicMock()
            app.bot = AsyncMock()
            # bot_notify_startup schedules the error-alert drain via
            # app.create_task; close the coroutine so it isn't left un-awaited.
            app.create_task.side_effect = lambda coro: coro.close()
            await bot.bot_notify_startup(app)
            app.bot.send_message.assert_called_once()
            self.assertEqual(app.bot.send_message.call_args[1]["chat_id"], 111)
            self.assertIn("Bot is up", app.bot.send_message.call_args[1]["text"])
        finally:
            cfg.ADMIN_IDS = old

    async def test_bot_notify_shutdown_sends_to_first_admin(self):
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = [333, 444]
            app = MagicMock()
            app.bot = AsyncMock()
            await bot.bot_notify_shutdown(app)
            app.bot.send_message.assert_called_once()
            self.assertEqual(app.bot.send_message.call_args[1]["chat_id"], 333)
            self.assertIn("Bot is down", app.bot.send_message.call_args[1]["text"])
        finally:
            cfg.ADMIN_IDS = old

    async def test_bot_notify_no_admins_does_nothing(self):
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = []
            app = MagicMock()
            app.bot = AsyncMock()
            await bot.bot_notify_startup(app)
            app.bot.send_message.assert_not_called()
        finally:
            cfg.ADMIN_IDS = old

    async def test_bot_notify_startup_api_error_does_not_crash(self):
        old = cfg.ADMIN_IDS[:]
        try:
            cfg.ADMIN_IDS = [123]
            app = MagicMock()
            app.bot = AsyncMock()
            app.create_task.side_effect = lambda coro: coro.close()
            app.bot.send_message.side_effect = Exception("Network error")
            # Should not raise
            await bot.bot_notify_startup(app)
        finally:
            cfg.ADMIN_IDS = old


# ── /edit ─────────────────────────────────────────────────────────────────────


class TestEdit(BotHandlerTestCase):

    async def test_edit_skip_all_fields_shows_book_card(self):
        """Regression: finishing /edit must render book_card (import from bookclub.ui)."""
        bid = self._add_book(
            "Card Title",
            author="A. Writer",
            pages=200,
            user_id=self.update.effective_user.id,
            username="testuser",
        )
        q = self._callback_query(f"edit_pick:{bid}")
        state = await bot.edit_pick_cb(self.update, self.ctx)
        self.assertEqual(state, bot.EDITING_FIELD)

        for _ in bot.EDIT_FIELDS:
            q = self._callback_query("edit_yn:no")
            state = await bot.edit_yn_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        q.edit_message_text.assert_called()
        body = q.edit_message_text.call_args[0][0]
        self.assertIn("Book updated", body)
        self.assertIn("Card Title", body)
        self.assertIn("A. Writer", body)


# ── /cancel ────────────────────────────────────────────────────────────────────


class TestCancel(BotHandlerTestCase):

    async def test_conv_cancel_clears_user_data(self):
        self.ctx.user_data["new_book"] = {"title": "T"}
        self.ctx.user_data["edit_book_id"] = 5
        state = await bot.conv_cancel(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(self.ctx.user_data, {})

    async def test_conv_cancel_sends_message(self):
        state = await bot.conv_cancel(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        self.assertIn("Cancelled", self.message.reply_text.call_args[0][0])


# ── /adminconsole ─────────────────────────────────────────────────────────────


class TestAdminConsole(BotHandlerTestCase):

    def setUp(self):
        super().setUp()
        self.old_admins = cfg.ADMIN_IDS[:]
        cfg.ADMIN_IDS = [self.update.effective_user.id]

    def tearDown(self):
        cfg.ADMIN_IDS = self.old_admins
        super().tearDown()

    async def test_cmd_admin_console_as_non_admin_fails(self):
        cfg.ADMIN_IDS = [999]
        state = await bot.cmd_admin_console(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        self.message.reply_text.assert_called_once()
        self.assertIn("admins only", self.message.reply_text.call_args[0][0])

    async def test_cmd_admin_console_shows_menu(self):
        state = await bot.cmd_admin_console(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MENU)
        self.message.reply_text.assert_called_once()
        self.assertIn("Admin Console", self.message.reply_text.call_args[0][0])

    async def test_admin_menu_cb_mark_shows_submenu(self):
        q = self._callback_query("admin:mark")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MENU)
        q.edit_message_text.assert_called_once()
        self.assertIn("Mark as discussed", q.edit_message_text.call_args[0][0])

    async def test_admin_menu_cb_mark_new_shows_books(self):
        self._add_book("Mark Me")
        q = self._callback_query("admin:mark_new")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MARK_CHOOSE)
        q.edit_message_text.assert_called_once()
        self.assertIn("Choose a book", q.edit_message_text.call_args[0][0])

    async def test_admin_menu_cb_hide_shows_books(self):
        self._add_book("Hide Me")
        q = self._callback_query("admin:hide")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_HIDE_CHOOSE)
        q.edit_message_text.assert_called_once()
        self.assertIn("Choose a book to hide", q.edit_message_text.call_args[0][0])

    async def test_admin_hide_pick_hides_book(self):
        bid = self._add_book("Ghost")
        q = self._callback_query(f"admin_hide_pick:{bid}")
        state = await bot.admin_hide_pick_cb(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(bot.db_get_book(bid)["hidden"], 1)
        q.edit_message_text.assert_called_once()
        self.assertIn("is now hidden", q.edit_message_text.call_args[0][0])

    async def test_admin_menu_cb_unhide_shows_hidden_books(self):
        bid = self._add_book("Hidden One")
        bot.db_set_hidden(bid, True)
        q = self._callback_query("admin:unhide")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_UNHIDE_CHOOSE)
        q.edit_message_text.assert_called_once()
        self.assertIn("hidden", q.edit_message_text.call_args[0][0].lower())

    async def test_admin_unhide_pick_shows_book(self):
        bid = self._add_book("Ghost")
        bot.db_set_hidden(bid, True)
        q = self._callback_query(f"admin_unhide_pick:{bid}")
        state = await bot.admin_unhide_pick_cb(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(bot.db_get_book(bid)["hidden"], 0)
        self.assertIn("visible", q.edit_message_text.call_args[0][0].lower())

    async def test_admin_mark_pick_advances_to_date(self):
        bid = self._add_book("Discuss Me")
        q = self._callback_query(f"admin_mark_pick:{bid}")
        state = await bot.admin_mark_pick_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MARK_DATE)
        self.assertEqual(self.ctx.user_data["mark_book_id"], bid)

    async def test_admin_mark_date_handler_completes(self):
        bid = self._add_book("Dated")
        self.ctx.user_data["mark_book_id"] = bid
        self.message.text = "2026-03-17"
        state = await bot.admin_mark_date_handler(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        book = bot.db_get_book(bid)
        self.assertEqual(book["discussed"], 1)
        self.assertEqual(book["discussed_at"], "2026-03-17")
        self.message.reply_text.assert_called_once()
        self.assertIn("marked as discussed", self.message.reply_text.call_args[0][0])

    async def test_admin_mark_edit_date_updates_discussed_at(self):
        bid = self._add_book("Already Discussed")
        bot.db_mark_discussed(bid, "2026-01-01")
        q = self._callback_query(f"admin_mark_edit_pick:{bid}")
        state = await bot.admin_mark_edit_pick_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MARK_DATE)
        self.assertTrue(self.ctx.user_data.get("mark_edit_date"))
        self.message.text = "2026-06-15"
        state = await bot.admin_mark_date_handler(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        book = bot.db_get_book(bid)
        self.assertEqual(book["discussed"], 1)
        self.assertEqual(book["discussed_at"], "2026-06-15")
        self.assertIn("updated to", self.message.reply_text.call_args[0][0])

    async def test_admin_notify_top_sends_reminders(self):
        # 1. Setup books
        bid1 = self._add_book("Top Book 1")
        bid2 = self._add_book("Top Book 2")

        # 2. Setup user with notifications ON
        user_id = 12345
        bot.db_set_user_setting(user_id, "notify_new_books", 1)
        # Ensure user has NOT voted for bid1 and bid2

        # 3. Trigger notify
        q = self._callback_query("admin:notify")
        state = await bot.admin_notify_top_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        # Check if bot.send_message was called for the user
        # 1 message for reminder text + 2 messages for books = 3 messages
        # Our mock bot is self.ctx.bot
        self.assertGreaterEqual(self.ctx.bot.send_message.call_count, 1)

        # Verify confirm message to admin
        q.edit_message_text.assert_called_once()
        self.assertIn("reminder sent", q.edit_message_text.call_args[0][0])

    async def test_admin_notify_top_no_unvoted_books(self):
        # 1. Setup book
        bid = self._add_book("Voted Book")

        # 2. Setup user who already voted
        user_id = 12345
        bot.db_set_user_setting(user_id, "notify_new_books", 1)
        bot.db_cast_vote(user_id, bid, 1)

        # 3. Trigger notify
        q = self._callback_query("admin:notify")
        state = await bot.admin_notify_top_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        # No messages should be sent to user
        self.ctx.bot.send_message.assert_not_called()

        # Verify info message to admin
        q.edit_message_text.assert_called_once()
        self.assertIn("No users to notify", q.edit_message_text.call_args[0][0])

    async def test_admin_notify_pick_sends_reminders(self):
        bid = self._add_book("Target Book")
        user_id = 12345
        bot.db_set_user_setting(user_id, "notify_new_books", 1)

        self.ctx.user_data["notify_book_ids"] = {bid}
        q = self._callback_query("admin_notify_pick:done")
        state = await bot.admin_notify_pick_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.assertGreaterEqual(self.ctx.bot.send_message.call_count, 1)
        q.edit_message_text.assert_called_once()
        self.assertIn("reminder sent", q.edit_message_text.call_args[0][0])

    async def test_admin_notify_pick_toggle_updates_selection(self):
        bid = self._add_book("Toggle Book")
        q = self._callback_query(f"admin_notify_pick:toggle:{bid}:0")
        state = await bot.admin_notify_pick_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_NOTIFY_PICK)
        self.assertEqual(self.ctx.user_data["notify_book_ids"], {bid})
        q.edit_message_text.assert_called_once()
        self.assertIn("Selected", q.edit_message_text.call_args[0][0])

    async def test_admin_notify_chat_top_posts_to_group(self):
        bid1 = self._add_book("Chat Top 1")
        bid2 = self._add_book("Chat Top 2")
        cfg.ALLOWED_CHAT_ID = -100123

        q = self._callback_query("admin:notify_chat")
        with patch.object(cfg, "CHAT_LANG", "en"):
            state = await bot.admin_notify_chat_top_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(self.ctx.bot.send_message.call_count, 2)
        for call in self.ctx.bot.send_message.call_args_list:
            self.assertEqual(call.kwargs["chat_id"], -100123)
            self.assertIn("Voting reminder", call.kwargs["text"])
            self.assertIsNotNone(call.kwargs.get("reply_markup"))

        q.edit_message_text.assert_called_once()
        self.assertIn("group chat", q.edit_message_text.call_args[0][0])

    async def test_admin_notify_chat_pick_posts_to_group(self):
        bid = self._add_book("Chat Pick Book")
        cfg.ALLOWED_CHAT_ID = -100123
        self.ctx.user_data["notify_book_ids"] = {bid}

        q = self._callback_query("admin_notify_chat_pick:done")
        with patch.object(cfg, "CHAT_LANG", "en"):
            state = await bot.admin_notify_chat_pick_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.ctx.bot.send_message.assert_called_once()
        kwargs = self.ctx.bot.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], -100123)
        self.assertIn("Voting reminder", kwargs["text"])
        self.assertIsNotNone(kwargs.get("reply_markup"))

    async def test_admin_notify_chat_no_allowed_chat_id(self):
        cfg.ALLOWED_CHAT_ID = None
        self._add_book("Orphan Book")

        q = self._callback_query("admin:notify_chat")
        state = await bot.admin_notify_chat_top_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.ctx.bot.send_message.assert_not_called()
        self.assertIn("ALLOWED_CHAT_ID", q.edit_message_text.call_args[0][0])

    async def test_admin_menu_cb_export_shows_books(self):
        self._add_book("Export Me")
        q = self._callback_query("admin:export")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_EXPORT_CHOOSE)
        q.edit_message_text.assert_called_once()
        self.assertIn("export", q.edit_message_text.call_args[0][0].lower())

    async def test_admin_export_pick_sends_json(self):
        bid = self._add_book("Export Me", author="Auth")
        q = self._callback_query(f"admin_export_pick:{bid}")
        state = await bot.admin_export_pick_cb(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        q.edit_message_text.assert_called_once()
        body = q.edit_message_text.call_args[0][0]
        self.assertIn("Export Me", body)
        self.assertIn("bookclub-bot-book", body)

    async def test_admin_menu_cb_import_prompts(self):
        q = self._callback_query("admin:import")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_IMPORT_WAIT)
        q.edit_message_text.assert_called_once()
        self.assertIn("JSON", q.edit_message_text.call_args[0][0])

    async def test_admin_import_handler_inserts_book(self):
        payload = bot.book_to_export_payload(
            bot.db_get_book(self._add_book("Imported", author="Writer"))
        )
        self.update.message.text = payload
        state = await bot.admin_import_handler(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_IMPORT_CONFIRM)
        q = self._callback_query("title_sim:yes")
        state = await bot.admin_import_similar_cb(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        books = bot.db_get_books(discussed=False, include_hidden=True)
        titles = [b["title"] for b in books]
        self.assertEqual(titles.count("Imported"), 2)

    async def test_admin_import_handler_schedules_notification_job(self):
        source = bot.db_get_book(self._add_book("Notify Me", author="Writer"))
        payload = bot.book_to_export_payload(source)
        self.update.message.text = payload
        self.ctx.job_queue = MagicMock()

        state = await bot.admin_import_handler(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_IMPORT_CONFIRM)
        q = self._callback_query("title_sim:yes")
        state = await bot.admin_import_similar_cb(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.ctx.job_queue.run_once.assert_called_once()
        job_kwargs = self.ctx.job_queue.run_once.call_args[1]
        self.assertEqual(job_kwargs["when"], bot.NEW_BOOK_NOTIFY_DELAY_SECONDS)
        imported_id = job_kwargs["data"]["book_id"]
        self.assertNotEqual(imported_id, source["id"])
        imported = bot.db_get_book(imported_id)
        self.assertEqual(
            imported["notify_adder_id"], self.update.effective_user.id
        )

    async def test_admin_toggle_chat_works(self):
        # Default should be 0
        self.assertEqual(bot.db_get_admin_setting("post_new_books_to_chat"), 0)

        # Toggle ON
        q = self._callback_query("admin:toggle_chat")
        await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_admin_setting("post_new_books_to_chat"), 1)

        # Toggle OFF
        q = self._callback_query("admin:toggle_chat")
        await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_admin_setting("post_new_books_to_chat"), 0)

    async def test_notify_new_book_job_posts_to_chat_when_enabled(self):
        bid = self._add_book("Chatty Book")
        cfg.ALLOWED_CHAT_ID = -100123
        bot.db_set_admin_setting("post_new_books_to_chat", 1)
        bot.db_set_new_book_notify_pending(
            bid, 999, datetime.now() + timedelta(minutes=5)
        )

        # Setup job mock. The adder's language is deliberately English to show
        # the shared group post does NOT follow it — group messages use CHAT_LANG.
        self.ctx.job = MagicMock()
        self.ctx.job.data = {"book_id": bid}
        self.ctx.application.user_data = {999: {"lang": "en"}}

        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.notify_new_book_job(self.ctx)

        # Should be called once for ALLOWED_CHAT_ID (and 0 users opted in by default in this test)
        self.ctx.bot.send_message.assert_called()
        args, kwargs = self.ctx.bot.send_message.call_args
        self.assertEqual(kwargs["chat_id"], -100123)
        self.assertIn("New book added", kwargs["text"])

    async def test_chat_post_uses_chat_lang_not_adder_lang(self):
        """A shared group post must not follow the adder's personal language."""
        bid = self._add_book("Shared Book")
        cfg.ALLOWED_CHAT_ID = -100123
        bot.db_set_admin_setting("post_new_books_to_chat", 1)

        self.ctx.job = MagicMock()
        self.ctx.job.data = {"book_id": bid}
        self.ctx.application.user_data = {999: {"lang": "en"}}  # adder prefers English

        bot.db_set_new_book_notify_pending(
            bid, 999, datetime.now() + timedelta(minutes=5)
        )

        with patch.object(cfg, "CHAT_LANG", "ru"):
            await bot.notify_new_book_job(self.ctx)

        kwargs = self.ctx.bot.send_message.call_args[1]
        self.assertIn("Добавлена новая книга", kwargs["text"])
        self.assertNotIn("New book added", kwargs["text"])

    async def test_notify_new_book_job_skips_hidden_book(self):
        bid = self._add_book("Hidden Book")
        cfg.ALLOWED_CHAT_ID = -100123
        bot.db_set_admin_setting("post_new_books_to_chat", 1)
        bot.db_toggle_hidden(bid)  # admin hid it inside the notify delay window
        bot.db_set_new_book_notify_pending(
            bid, 999, datetime.now() + timedelta(minutes=5)
        )

        self.ctx.job = MagicMock()
        self.ctx.job.data = {"book_id": bid}
        self.ctx.application.user_data = {}

        await bot.notify_new_book_job(self.ctx)

        self.ctx.bot.send_message.assert_not_called()

    async def test_notify_new_book_job_does_not_post_to_chat_when_disabled(self):
        bid = self._add_book("Quiet Book")
        cfg.ALLOWED_CHAT_ID = -100123
        bot.db_set_admin_setting("post_new_books_to_chat", 0)
        bot.db_set_new_book_notify_pending(
            bid, 999, datetime.now() + timedelta(minutes=5)
        )

        self.ctx.job = MagicMock()
        self.ctx.job.data = {"book_id": bid}
        self.ctx.application.user_data = {}

        await bot.notify_new_book_job(self.ctx)

        # Should NOT be called for ALLOWED_CHAT_ID
        # (It might be called if there were opted-in users, but there are none)
        self.ctx.bot.send_message.assert_not_called()

    async def test_admin_meeting_create_flow(self):
        bid = self._add_book("Discussed Book")
        bot.db_mark_discussed(bid, "2026-03-01")
        voter_id = 4242
        bot.db_upsert_club_user(voter_id, "Voter One", "voter1")
        bot.db_cast_vote(voter_id, bid, 1)

        q = self._callback_query("admin:meeting_create")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MEETING_BOOK)

        q = self._callback_query(f"admin_meeting_book:{bid}")
        state = await bot.admin_meeting_book_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MEETING_ATTENDEES)

        q = self._callback_query(f"admin_meeting_att:toggle:{voter_id}:0")
        state = await bot.admin_meeting_att_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MEETING_ATTENDEES)
        self.assertIn(voter_id, self.ctx.user_data["meeting_attendee_ids"])

        q = self._callback_query("admin_meeting_att:done")
        state = await bot.admin_meeting_att_cb(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        meetings = bot.db_list_meetings()
        self.assertEqual(len(meetings), 1)
        self.assertEqual(meetings[0]["book_id"], bid)
        attendees = bot.db_get_meeting_attendee_rows(meetings[0]["id"])
        self.assertEqual([int(r["user_id"]) for r in attendees], [voter_id])

    async def test_admin_meetings_view_lists_attendees(self):
        bid = self._add_book("Past Read")
        bot.db_mark_discussed(bid, "2026-02-01")
        uid = 7777
        bot.db_upsert_club_user(uid, "Alice", "alice")
        mid = bot.db_create_meeting(bid, "2026-02-15", self.update.effective_user.id, [uid])

        q = self._callback_query("admin:meetings_view")
        state = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(state, bot.ADMIN_MEETINGS_VIEW)

        q = self._callback_query(f"admin_meeting_view:{mid}")
        state = await bot.admin_meeting_view_cb(self.update, self.ctx)
        self.assertEqual(state, ConversationHandler.END)
        body = q.edit_message_text.call_args[0][0]
        self.assertIn("Past Read", body)
        self.assertIn("Alice", body)


# ── Voting in a shared group message ──────────────────────────────────────────


class TestGroupVoteCard(BotHandlerTestCase):
    """A card posted to the club chat is shared, so it must stay impersonal."""

    def _vote_in(self, chat_type, book_id, score=1):
        self.update.effective_chat.type = chat_type
        q = self._callback_query(f"vote_cast:{book_id}:{score}")
        return q

    def _add_book(self, title="Group Book"):
        return bot.db_add_book(title, "Author", 100, 1, "", "", 999, "u", "u")

    async def test_group_card_omits_personal_vote(self):
        bid = self._add_book()
        q = self._vote_in("supergroup", bid)
        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.vote_cast_cb(self.update, self.ctx)
        text = q.edit_message_text.call_args[0][0]
        self.assertNotIn(
            "Your current vote",
            text,
            "shared group card must not show one member's vote",
        )

    async def test_group_card_updates_statistics_after_vote(self):
        """Group chat message must show updated aggregate stats after voting."""
        bid = self._add_book()

        # First vote: +1
        q = self._vote_in("supergroup", bid, score=1)
        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.vote_cast_cb(self.update, self.ctx)

        text = q.edit_message_text.call_args[0][0]
        self.assertIn("✅ 1", text, "Should show 1 'want' vote")

        # Second user votes: +1 more (simulate by changing mock user ID)
        self.update.effective_user.id = 99999
        q2 = self._callback_query(f"vote_cast:{bid}:1")
        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.vote_cast_cb(self.update, self.ctx)

        text2 = q2.edit_message_text.call_args[0][0]
        self.assertIn("✅ 2", text2, "Should show 2 'want' votes after second vote")
        self.assertNotIn("✅ 1", text2, "Old count must be replaced")

    async def test_group_card_reflects_changed_votes(self):
        """If a user changes their vote, statistics update accordingly."""
        bid = self._add_book()

        # User votes +1
        q = self._vote_in("supergroup", bid, score=1)
        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.vote_cast_cb(self.update, self.ctx)
        text = q.edit_message_text.call_args[0][0]
        self.assertIn("✅ 1", text)
        self.assertIn("❌ 0", text)

        # Same user changes to -1 (don't want)
        q2 = self._callback_query(f"vote_cast:{bid}:-1")
        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.vote_cast_cb(self.update, self.ctx)

        text2 = q2.edit_message_text.call_args[0][0]
        self.assertIn("✅ 0", text2, "'want' count should drop to 0")
        self.assertIn("❌ 1", text2, "'don't want' count should be 1")

    async def test_group_card_acknowledges_voter_via_toast(self):
        bid = self._add_book()
        q = self._vote_in("supergroup", bid)
        with patch.object(cfg, "CHAT_LANG", "en"):
            await bot.vote_cast_cb(self.update, self.ctx)
        q.answer.assert_called_once()
        self.assertIn("Your vote", q.answer.call_args[0][0])

    async def test_group_card_ignores_clicker_language(self):
        bid = self._add_book()
        self.ctx.user_data["lang"] = "en"  # clicker prefers English
        q = self._vote_in("supergroup", bid)
        with patch.object(cfg, "CHAT_LANG", "ru"):
            await bot.vote_cast_cb(self.update, self.ctx)
        text = q.edit_message_text.call_args[0][0]
        # Rendered in CHAT_LANG, not the clicker's "en".
        self.assertIn("Добавлено", text)
        self.assertNotIn("Added on", text)

    async def test_private_card_still_shows_personal_vote(self):
        bid = self._add_book()
        q = self._vote_in("private", bid)
        await bot.vote_cast_cb(self.update, self.ctx)
        text = q.edit_message_text.call_args[0][0]
        self.assertIn("Your current vote", text)

    async def test_out_of_range_score_is_ignored(self):
        """Crafted callback data must not raise a KeyError inside the handler."""
        bid = self._add_book()
        self._vote_in("supergroup", bid, score=7)
        await bot.vote_cast_cb(self.update, self.ctx)
        self.assertIsNone(bot.db_get_user_vote(self.update.effective_user.id, bid))

    async def test_vote_is_recorded_in_both_chat_types(self):
        for chat_type in ("private", "supergroup"):
            bid = self._add_book(f"B-{chat_type}")
            self._vote_in(chat_type, bid)
            with patch.object(cfg, "CHAT_LANG", "en"):
                await bot.vote_cast_cb(self.update, self.ctx)
            self.assertEqual(
                bot.db_get_user_vote(self.update.effective_user.id, bid), 1
            )


# ── Admin authorization on callbacks ──────────────────────────────────────────


class TestAdminCallbackGuards(BotHandlerTestCase):

    def setUp(self):
        super().setUp()
        self._orig_admins = cfg.ADMIN_IDS[:]
        cfg.ADMIN_IDS = [11111]  # caller (67890) is NOT admin

    def tearDown(self):
        cfg.ADMIN_IDS = self._orig_admins
        super().tearDown()

    async def test_admin_menu_cb_rejects_non_admin(self):
        q = self._callback_query("admin:toggle_chat")
        before = bot.db_get_admin_setting("post_new_books_to_chat", 0)
        result = await bot.admin_menu_cb(self.update, self.ctx)
        self.assertEqual(result, ConversationHandler.END)
        q.answer.assert_called_once()
        self.assertIn("admins only", q.answer.call_args[0][0])
        self.assertEqual(
            bot.db_get_admin_setting("post_new_books_to_chat", 0),
            before,
            "non-admin must not flip the chat-posting setting",
        )

    async def test_admin_notify_pick_cb_rejects_non_admin(self):
        self._callback_query("admin_notify_pick:cancel")
        result = await bot.admin_notify_pick_cb(self.update, self.ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.ctx.bot.send_message.assert_not_called()

    async def test_admin_hide_pick_cb_rejects_non_admin(self):
        bid = bot.db_add_book("H", "A", 1, 1, "", "", 999, "u", "u")
        self._callback_query(f"admin_hide_pick:{bid}")
        await bot.admin_hide_pick_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_book(bid)["hidden"], 0)

    async def test_admin_mark_date_handler_rejects_non_admin(self):
        bid = bot.db_add_book("M", "A", 1, 1, "", "", 999, "u", "u")
        self.ctx.user_data["mark_book_id"] = bid
        self.message.text = "/today"
        await bot.admin_mark_date_handler(self.update, self.ctx)
        self.assertEqual(bot.db_get_book(bid)["discussed"], 0)


# ── Stale conversation state ──────────────────────────────────────────────────


class TestStaleState(BotHandlerTestCase):

    async def test_mark_date_without_book_id_ends_gracefully(self):
        """State can be lost if the bot restarts mid-conversation."""
        cfg.ADMIN_IDS = [self.update.effective_user.id]
        try:
            self.ctx.user_data.pop("mark_book_id", None)
            self.message.text = "/today"
            result = await bot.admin_mark_date_handler(self.update, self.ctx)
            self.assertEqual(result, ConversationHandler.END)
            self.message.reply_text.assert_called_once()
        finally:
            cfg.ADMIN_IDS = []


# ── Conversation wiring ───────────────────────────────────────────────────────


class TestConversationWiring(unittest.TestCase):
    """Guards the state/fallback ordering in register_handlers().

    ConversationHandler matches state handlers BEFORE fallbacks, so a bare
    filters.TEXT in a state silently swallows /cancel. These tests assert the
    states that accept free text still let commands through to the fallback.
    """

    def _states(self, entry_command):
        app = MagicMock()
        added = []
        app.add_handler = lambda h, *a, **kw: added.append(h)
        bot.register_handlers(app)
        for h in added:
            if not isinstance(h, ConversationHandler):
                continue
            names = {
                getattr(e, "commands", None) and tuple(e.commands)
                for e in h.entry_points
            }
            if (entry_command,) in names:
                return h
        self.fail(f"No ConversationHandler with entry /{entry_command}")

    def _matches(self, handlers, text, is_command):
        """True if any handler in the state would consume this message."""
        update = MagicMock(spec=Update)
        update.callback_query = None
        msg = MagicMock(spec=Message)
        msg.text = text
        update.message = msg
        update.effective_message = msg
        update.channel_post = None
        update.edited_message = None
        # Both filters.COMMAND and CommandHandler key off the leading entity;
        # CommandHandler slices text[1:length] to read the command name.
        msg.entities = (
            [MagicMock(type="bot_command", offset=0, length=len(text))]
            if is_command
            else []
        )
        return any(h.check_update(update) for h in handlers)

    def test_description_state_lets_cancel_reach_fallback(self):
        conv = self._states("add")
        handlers = conv.states[bot.ADDING_DESCRIPTION]
        self.assertFalse(
            self._matches(handlers, "/cancel", is_command=True),
            "/cancel must not be consumed as the book description",
        )

    def test_description_state_still_accepts_skip_and_plain_text(self):
        conv = self._states("add")
        handlers = conv.states[bot.ADDING_DESCRIPTION]
        self.assertTrue(
            self._matches(handlers, "/skip", is_command=True),
            "/skip must still be handled",
        )
        self.assertTrue(self._matches(handlers, "a description", is_command=False))

    def test_mark_date_state_lets_cancel_reach_fallback(self):
        conv = self._states("adminconsole")
        handlers = conv.states[bot.ADMIN_MARK_DATE]
        self.assertFalse(
            self._matches(handlers, "/cancel", is_command=True),
            "/cancel must not be parsed as a discussion date",
        )

    def test_mark_date_state_still_accepts_today_and_plain_date(self):
        conv = self._states("adminconsole")
        handlers = conv.states[bot.ADMIN_MARK_DATE]
        self.assertTrue(self._matches(handlers, "/today", is_command=True))
        self.assertTrue(self._matches(handlers, "2026-01-01", is_command=False))


class TestConversationReentry(unittest.TestCase):
    """Re-sending an entry command must always work.

    ConversationHandler only consults entry_points when no conversation is
    active (unless allow_reentry). Without it, a user who opened /adminconsole
    and walked away could re-send /adminconsole forever and match nothing —
    the update fell through every handler and the bot replied with silence.

    Uses real Telegram objects rather than mocks: a MagicMock bot makes
    CommandHandler's username comparison behave differently from production.
    """

    @classmethod
    def setUpClass(cls):
        cls.bot_obj = Bot("123456:AAHkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk")
        cls.bot_obj._bot_user = User(
            id=1, first_name="B", is_bot=True, username="testbot"
        )

    def _conversations(self):
        added = []
        app = MagicMock()
        app.add_handler = lambda h, *a, **kw: added.append(h)
        bot.register_handlers(app)
        return [h for h in added if isinstance(h, ConversationHandler)]

    def _conv(self, command):
        for conv in self._conversations():
            for entry in conv.entry_points:
                if getattr(entry, "commands", None) == {command}:
                    return conv
        self.fail(f"No ConversationHandler with entry /{command}")

    def _command_update(self, text):
        chat = Chat(id=-100123, type="supergroup")
        user = User(id=99, first_name="Admin", is_bot=False)
        msg = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text=text,
            entities=[MessageEntity(type="bot_command", offset=0, length=len(text))],
        )
        msg.set_bot(self.bot_obj)
        upd = Update(update_id=1, message=msg)
        upd.set_bot(self.bot_obj)
        return upd

    def _handled(self, conv, update, state):
        key = conv._get_key(update)
        conv._conversations[key] = state
        try:
            return conv.check_update(update) is not None
        finally:
            conv._conversations.pop(key, None)

    def test_adminconsole_recovers_from_every_open_state(self):
        conv = self._conv("adminconsole")
        upd = self._command_update("/adminconsole")
        for state in (
            bot.ADMIN_MENU,
            bot.ADMIN_MARK_CHOOSE,
            bot.ADMIN_MARK_DATE,
            bot.ADMIN_HIDE_CHOOSE,
            bot.ADMIN_NOTIFY_PICK,
            bot.ADMIN_NOTIFY_CHAT_PICK,
        ):
            self.assertTrue(
                self._handled(conv, upd, state),
                f"/adminconsole did nothing while stuck in state {state}",
            )

    def test_add_edit_delete_recover_from_open_state(self):
        for command, state in (
            ("add", bot.ADDING_TITLE),
            ("add", bot.ADDING_DESCRIPTION),
            ("edit", bot.EDITING_CHOOSE),
            ("edit", bot.EDITING_FIELD),
            ("delete", bot.DELETING_CHOOSE),
        ):
            conv = self._conv(command)
            upd = self._command_update(f"/{command}")
            self.assertTrue(
                self._handled(conv, upd, state),
                f"/{command} did nothing while stuck in state {state}",
            )

    def test_entry_command_still_works_with_no_conversation(self):
        conv = self._conv("adminconsole")
        upd = self._command_update("/adminconsole")
        self.assertIsNotNone(conv.check_update(upd))

    def test_all_conversations_allow_reentry(self):
        for conv in self._conversations():
            self.assertTrue(
                conv.allow_reentry, "every conversation must be re-enterable"
            )


# ── Global error handler ──────────────────────────────────────────────────────

# ── Global error handler ──────────────────────────────────────────────────────


class TestErrorHandler(BotHandlerTestCase):
    """Without an error handler the bot replies with silence when a handler
    raises, which looks identical to the bot being down.

    The updated error_handler suppresses error notifications in group chats
    (errors are still logged and sent to the admin via _TelegramAlertHandler).
    Tests that check user-facing replies must therefore run in a private-chat
    context."""

    def setUp(self):
        super().setUp()
        # The updated error_handler checks effective_message.chat.type and
        # returns early for non-private chats. Default to private so existing
        # tests exercise the reply path.
        self.update.effective_message.chat.type = "private"

    async def test_error_handler_replies_to_message(self):
        self.ctx.error = RuntimeError("boom")
        await bot.error_handler(self.update, self.ctx)
        self.update.effective_message.reply_text.assert_called_once()
        text = self.update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Something went wrong", text)

    async def test_error_handler_replies_in_russian(self):
        self.ctx.user_data["lang"] = "ru"
        self.ctx.error = RuntimeError("boom")
        await bot.error_handler(self.update, self.ctx)
        text = self.update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Что-то пошло не так", text)

    async def test_error_handler_answers_callback_query(self):
        q = self._callback_query("vote_cast:1:1")
        # effective_message is already set to private by setUp; the handler
        # will reach the callback_query branch and clear the spinner.
        self.ctx.error = RuntimeError("boom")
        await bot.error_handler(self.update, self.ctx)
        # Spinner must be cleared, otherwise the button spins forever.
        q.answer.assert_awaited_once()
        q.message.reply_text.assert_called_once()

    async def test_error_handler_ignores_non_update(self):
        """Job errors carry no update — must not raise trying to reply."""
        self.ctx.error = RuntimeError("boom")
        await bot.error_handler("not-an-update", self.ctx)
        self.message.reply_text.assert_not_called()

    async def test_error_handler_network_error_logs_warning_only(self):
        """Transient API failures must not alert the admin or message the user."""
        self.ctx.error = NetworkError("Bad Gateway")
        with (
            patch.object(bot.logger, "warning") as mock_warn,
            patch.object(bot.logger, "error") as mock_err,
        ):
            await bot.error_handler(self.update, self.ctx)
            mock_warn.assert_called_once()
            mock_err.assert_not_called()
        self.update.effective_message.reply_text.assert_not_called()

    async def test_error_handler_survives_failed_delivery(self):
        """If replying also fails, the original error must not be masked."""
        self.ctx.error = RuntimeError("boom")
        self.update.effective_message.reply_text.side_effect = Exception("network")
        await bot.error_handler(self.update, self.ctx)  # must not raise

    async def test_error_handler_suppressed_in_group_chat(self):
        """Errors in group chats must not spam members with error messages."""
        self.update.effective_message.chat.type = "supergroup"
        self.ctx.error = RuntimeError("boom")
        await bot.error_handler(self.update, self.ctx)
        self.update.effective_message.reply_text.assert_not_called()

    async def test_error_handler_suppresses_callback_query_in_group(self):
        """A callback-query error in a group must not post a reply there."""
        self._callback_query("vote_cast:1:1")
        self.update.effective_message.chat.type = "supergroup"
        self.ctx.error = RuntimeError("boom")
        await bot.error_handler(self.update, self.ctx)
        # No reply should be sent into the group chat
        self.update.effective_message.reply_text.assert_not_called()
        # The callback query answer should also not fire a visible alert
        self.update.callback_query.answer.assert_not_awaited()

    async def test_error_handler_logs_error_in_group_chat(self):
        """Even when suppressed in groups, the error must still be logged."""
        self.update.effective_message.chat.type = "supergroup"
        self.ctx.error = RuntimeError("boom")
        with patch.object(bot.logger, "error") as mock_err:
            await bot.error_handler(self.update, self.ctx)
            mock_err.assert_called_once()

    def test_error_handler_is_registered(self):
        app = MagicMock()
        registered = []
        app.add_error_handler = lambda h: registered.append(h)
        bot.register_handlers(app)
        self.assertIn(bot.error_handler, registered)


if __name__ == "__main__":
    unittest.main()
