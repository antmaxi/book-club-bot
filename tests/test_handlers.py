"""
test_handlers.py — Async handler tests for bookclub_bot.py

Tests Telegram command/callback handlers using mocked Update + Context.
No real Telegram API calls are made.
"""

import unittest
import sqlite3
import os
from unittest.mock import AsyncMock, MagicMock, patch

import bookclub_bot as bot
from telegram import Update, Message, User, Chat
from telegram.ext import ConversationHandler


# ── Base test class with shared setUp ─────────────────────────────────────────

class BotHandlerTestCase(unittest.IsolatedAsyncioTestCase):
    """Base class: creates a fresh temp DB and standard mock update/ctx."""

    DB_FILE = "test_handlers.db"

    def setUp(self):
        bot.DB_PATH = self.DB_FILE
        bot.init_db()

        # Disable ALLOWED_CHAT_ID so membership gate never blocks during tests
        self._orig_chat_id = bot.ALLOWED_CHAT_ID
        bot.ALLOWED_CHAT_ID = None

        self.update = MagicMock(spec=Update)
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

    def _add_book(self, title="Book", author="Author", pages=100,
                  fiction=True, review="", desc="", user_id=1, username="u"):
        return bot.db_add_book(title, author, pages, fiction, review, desc, user_id, username)


# ── /start and /help ───────────────────────────────────────────────────────────

class TestStartHelp(BotHandlerTestCase):

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_sends_welcome(self, mock_set):
        await bot.cmd_start(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Welcome", text)
        self.assertIn("/info", text)

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_sets_menu(self, mock_set):
        await bot.cmd_start(self.update, self.ctx)
        mock_set.assert_called_once_with(self.ctx.bot, self.update, "en")

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start_ru(self, mock_set):
        self.ctx.user_data["lang"] = "ru"
        await bot.cmd_start(self.update, self.ctx)
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Добро пожаловать", text)
        self.assertIn("/info", text)

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_help_delegates_to_start(self, mock_set):
        await bot.cmd_help(self.update, self.ctx)
        self.message.reply_text.assert_called_once()


# ── /info ─────────────────────────────────────────────────────────────────────

class TestInfo(BotHandlerTestCase):

    @patch("subprocess.check_output")
    async def test_cmd_info_en(self, mock_git):
        mock_git.return_value = b"2026-04-04 12:00:00\n"
        with patch("bookclub_bot.GITHUB_REPO", "https://test.repo"):
            await bot.cmd_info(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Book Club Bot", text)
        self.assertIn("2026-04-04 12:00:00", text)
        self.assertIn("https://test.repo", text)

    @patch("subprocess.check_output")
    async def test_cmd_info_ru(self, mock_git):
        self.ctx.user_data["lang"] = "ru"
        mock_git.return_value = b"2026-04-04 12:00:00\n"
        await bot.cmd_info(self.update, self.ctx)
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Последнее обновление", text)
        self.assertIn("2026-04-04 12:00:00", text)

    @patch("subprocess.check_output")
    async def test_cmd_info_git_error(self, mock_git):
        mock_git.side_effect = Exception("git not found")
        await bot.cmd_info(self.update, self.ctx)
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("unknown", text)


# ── set_user_commands ──────────────────────────────────────────────────────────

class TestSetUserCommands(BotHandlerTestCase):

    @patch("bookclub_bot.BotCommandScopeChat")
    async def test_private_chat_uses_chat_scope(self, mock_scope_cls):
        mock_scope = MagicMock()
        mock_scope_cls.return_value = mock_scope
        mock_bot = AsyncMock()
        self.update.effective_chat.type = "private"

        await bot.set_user_commands(mock_bot, self.update, "en")

        mock_bot.delete_my_commands.assert_called_once_with(scope=mock_scope)
        mock_bot.set_my_commands.assert_called_once_with(bot.COMMANDS["en"], scope=mock_scope)

    @patch("bookclub_bot.BotCommandScopeChatMember")
    async def test_group_chat_uses_member_scope(self, mock_scope_cls):
        mock_scope = MagicMock()
        mock_scope_cls.return_value = mock_scope
        mock_bot = AsyncMock()
        self.update.effective_chat.type = "supergroup"

        await bot.set_user_commands(mock_bot, self.update, "ru")

        mock_bot.set_my_commands.assert_called_once_with(bot.COMMANDS["ru"], scope=mock_scope)

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
            self.assertNotIn("language", cmds, f"'language' should not be in {lang} menu")

    async def test_settings_description_en(self):
        desc = next(c.description for c in bot.COMMANDS["en"] if c.command == "settings")
        self.assertEqual(desc, "⚙️ Settings")

    async def test_settings_description_ru(self):
        desc = next(c.description for c in bot.COMMANDS["ru"] if c.command == "settings")
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


# ── /list ──────────────────────────────────────────────────────────────────────

class TestList(BotHandlerTestCase):

    async def test_cmd_list_shows_prompt(self):
        await bot.cmd_list(self.update, self.ctx)
        self.message.reply_text.assert_called_once()
        text = self.message.reply_text.call_args[0][0]
        self.assertIn("Show all books", text)
        self.assertIn("reply_markup", self.message.reply_text.call_args[1])

    async def test_list_choice_all_sends_book(self):
        self._add_book("Book 1")
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        q.answer.assert_called_once()
        q.delete_message.assert_called_once()
        self.ctx.bot.send_message.assert_called_once()
        self.assertIn("Book 1", self.ctx.bot.send_message.call_args[1]["text"])

    async def test_list_choice_unvoted_excludes_voted_book(self):
        book_id = self._add_book("Book 1")
        bot.db_cast_vote(self.update.effective_user.id, book_id, 1)
        q = self._callback_query("list:unvoted")
        await bot.list_choice_cb(self.update, self.ctx)
        self.ctx.bot.send_message.assert_not_called()
        q.edit_message_text.assert_called_once()
        self.assertIn("voted on all", q.edit_message_text.call_args[0][0])

    async def test_list_choice_all_no_books(self):
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        self.ctx.bot.send_message.assert_not_called()

    async def test_list_choice_multiple_books(self):
        self._add_book("Alpha")
        self._add_book("Beta")
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        self.assertEqual(self.ctx.bot.send_message.call_count, 2)

    async def test_list_triggers_optin_when_setting_missing(self):
        """First-time users without a notify setting see the opt-in prompt."""
        with sqlite3.connect(bot.DB_PATH) as conn:
            conn.execute("DELETE FROM user_settings WHERE user_id=?",
                         (self.update.effective_user.id,))
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        q.edit_message_text.assert_called_once()
        self.assertIn("Would you like to receive notifications",
                      q.edit_message_text.call_args[0][0])
        self.assertEqual(self.ctx.user_data["pending_list_choice"], "all")

    async def test_list_no_optin_when_setting_already_set(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        self._add_book("B")
        q = self._callback_query("list:all")
        await bot.list_choice_cb(self.update, self.ctx)
        # edit_message_text should NOT be called for opt-in prompt
        q.edit_message_text.assert_not_called()
        self.ctx.bot.send_message.assert_called_once()


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

    async def test_add_review_valid(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "https://goodreads.com/book/1"
        state = await bot.add_review(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["new_book"]["review_link"],
                         "https://goodreads.com/book/1")
        self.assertEqual(state, bot.ADDING_DESCRIPTION)

    async def test_add_review_invalid_url(self):
        self.ctx.user_data["new_book"] = {}
        self.message.text = "not a url"
        state = await bot.add_review(self.update, self.ctx)
        self.assertEqual(state, bot.ADDING_REVIEW)

    async def test_add_description_completes_and_schedules_job(self):
        self.ctx.user_data["new_book"] = {
            "title": "T", "author": "A", "pages": 100,
            "fiction": True, "review_link": "http://x.com",
        }
        self.message.text = "Great book"
        self.ctx.job_queue = MagicMock()

        state = await bot.add_description(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.message.reply_text.assert_called_once()
        confirm = self.message.reply_text.call_args[0][0]
        self.assertIn("Book added", confirm)
        self.assertIn("10 minutes", confirm)
        self.ctx.job_queue.run_once.assert_called_once()
        job_kwargs = self.ctx.job_queue.run_once.call_args[1]
        self.assertEqual(job_kwargs["when"], 600)
        self.assertEqual(job_kwargs["data"]["adder_id"], self.update.effective_user.id)

    async def test_add_description_no_job_queue(self):
        self.ctx.user_data["new_book"] = {
            "title": "T", "author": "A", "pages": 100,
            "fiction": True, "review_link": "http://x.com",
        }
        self.message.text = "Desc"
        self.ctx.job_queue = None

        state = await bot.add_description(self.update, self.ctx)

        self.assertEqual(state, ConversationHandler.END)
        self.assertIn("Book added", self.message.reply_text.call_args[0][0])

    async def test_add_description_skip(self):
        self.ctx.user_data["new_book"] = {
            "title": "T", "author": "A", "pages": 100,
            "fiction": True, "review_link": "http://x.com",
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
        self.assertEqual(bot.db_get_user_setting(self.update.effective_user.id,
                                                  "notify_new_books"), 1)

    async def test_settings_toggle_notify_one_to_zero(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 1)
        q = self._callback_query("settings:toggle_notify")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_user_setting(self.update.effective_user.id,
                                                  "notify_new_books"), 0)

    async def test_settings_toggle_notify_zero_to_one(self):
        bot.db_set_user_setting(self.update.effective_user.id, "notify_new_books", 0)
        q = self._callback_query("settings:toggle_notify")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_user_setting(self.update.effective_user.id,
                                                  "notify_new_books"), 1)

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_settings_toggle_lang_en_to_ru(self, mock_set):
        self.ctx.user_data["lang"] = "en"
        q = self._callback_query("settings:toggle_lang")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["lang"], "ru")
        q.answer.assert_called_once_with("🇷🇺 Язык установлен: Русский.")
        mock_set.assert_called_once_with(self.ctx.bot, self.update, "ru")

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_settings_toggle_lang_ru_to_en(self, mock_set):
        self.ctx.user_data["lang"] = "ru"
        q = self._callback_query("settings:toggle_lang")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(self.ctx.user_data["lang"], "en")
        mock_set.assert_called_once_with(self.ctx.bot, self.update, "en")

    async def test_optin_yes_sets_notify_and_continues_list(self):
        with sqlite3.connect(bot.DB_PATH) as conn:
            conn.execute("DELETE FROM user_settings WHERE user_id=?",
                         (self.update.effective_user.id,))
        self._add_book("Book 1")
        self.ctx.user_data["pending_list_choice"] = "unvoted"
        q = self._callback_query("settings:optin:1")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_user_setting(self.update.effective_user.id,
                                                  "notify_new_books"), 1)
        q.answer.assert_called_once_with("✅ Settings saved!")
        self.ctx.bot.send_message.assert_called_once()
        self.assertIn("Book 1", self.ctx.bot.send_message.call_args[1]["text"])

    async def test_optin_no_sets_zero(self):
        with sqlite3.connect(bot.DB_PATH) as conn:
            conn.execute("DELETE FROM user_settings WHERE user_id=?",
                         (self.update.effective_user.id,))
        self.ctx.user_data["pending_list_choice"] = "all"
        q = self._callback_query("settings:optin:0")
        await bot.settings_choice_cb(self.update, self.ctx)
        self.assertEqual(bot.db_get_user_setting(self.update.effective_user.id,
                                                  "notify_new_books"), 0)


# ── Membership gate ────────────────────────────────────────────────────────────

class TestMembershipGate(BotHandlerTestCase):

    async def test_gate_allows_when_no_chat_id_set(self):
        bot.ALLOWED_CHAT_ID = None
        result = await bot._check_membership(self.update, self.ctx)
        self.assertTrue(result)

    async def test_gate_allows_admin_without_api_call(self):
        bot.ALLOWED_CHAT_ID = -1001111111111
        old = bot.ADMIN_IDS[:]
        try:
            bot.ADMIN_IDS = [self.update.effective_user.id]
            result = await bot._check_membership(self.update, self.ctx)
            self.assertTrue(result)
            # Bot API should NOT have been called for admin
            self.ctx.bot.get_chat_member.assert_not_called()
        finally:
            bot.ADMIN_IDS = old

    async def test_gate_allows_member_status(self):
        bot.ALLOWED_CHAT_ID = -1001111111111
        for status in ("member", "administrator", "creator", "restricted"):
            member = MagicMock()
            member.status = status
            self.ctx.bot.get_chat_member = AsyncMock(return_value=member)
            result = await bot._check_membership(self.update, self.ctx)
            self.assertTrue(result, f"Status '{status}' should be allowed")

    async def test_gate_blocks_non_member(self):
        bot.ALLOWED_CHAT_ID = -1001111111111
        for status in ("left", "kicked"):
            member = MagicMock()
            member.status = status
            self.ctx.bot.get_chat_member = AsyncMock(return_value=member)
            result = await bot._check_membership(self.update, self.ctx)
            self.assertFalse(result, f"Status '{status}' should be blocked")

    async def test_gate_allows_on_api_exception(self):
        """If get_chat_member fails, we fail open (allow) with a warning."""
        bot.ALLOWED_CHAT_ID = -1001111111111
        self.ctx.bot.get_chat_member = AsyncMock(side_effect=Exception("API error"))
        result = await bot._check_membership(self.update, self.ctx)
        self.assertFalse(result)


# ── Startup / shutdown notifications ──────────────────────────────────────────

class TestStartupShutdown(BotHandlerTestCase):

    async def test_bot_notify_startup_sends_to_first_admin(self):
        old = bot.ADMIN_IDS[:]
        try:
            bot.ADMIN_IDS = [111, 222]
            app = MagicMock()
            app.bot = AsyncMock()
            await bot.bot_notify_startup(app)
            app.bot.send_message.assert_called_once()
            self.assertEqual(app.bot.send_message.call_args[1]["chat_id"], 111)
            self.assertIn("Bot is up", app.bot.send_message.call_args[1]["text"])
        finally:
            bot.ADMIN_IDS = old

    async def test_bot_notify_shutdown_sends_to_first_admin(self):
        old = bot.ADMIN_IDS[:]
        try:
            bot.ADMIN_IDS = [333, 444]
            app = MagicMock()
            app.bot = AsyncMock()
            await bot.bot_notify_shutdown(app)
            app.bot.send_message.assert_called_once()
            self.assertEqual(app.bot.send_message.call_args[1]["chat_id"], 333)
            self.assertIn("Bot is down", app.bot.send_message.call_args[1]["text"])
        finally:
            bot.ADMIN_IDS = old

    async def test_bot_notify_no_admins_does_nothing(self):
        old = bot.ADMIN_IDS[:]
        try:
            bot.ADMIN_IDS = []
            app = MagicMock()
            app.bot = AsyncMock()
            await bot.bot_notify_startup(app)
            app.bot.send_message.assert_not_called()
        finally:
            bot.ADMIN_IDS = old

    async def test_bot_notify_startup_api_error_does_not_crash(self):
        old = bot.ADMIN_IDS[:]
        try:
            bot.ADMIN_IDS = [123]
            app = MagicMock()
            app.bot = AsyncMock()
            app.bot.send_message.side_effect = Exception("Network error")
            # Should not raise
            await bot.bot_notify_startup(app)
        finally:
            bot.ADMIN_IDS = old


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


if __name__ == "__main__":
    unittest.main()
