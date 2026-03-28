import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sqlite3
import bookclub_bot as bot
from telegram import Update, Message, User, Chat

class TestHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_file = "test_handlers.db"
        bot.DB_PATH = self.db_file
        bot.init_db()
        
        # Mocking update and context
        self.update = MagicMock(spec=Update)
        self.context = MagicMock()
        self.context.user_data = {"lang": "en"}
        self.context.bot = AsyncMock()
        
        # Mock message
        self.message = AsyncMock(spec=Message)
        self.update.message = self.message
        self.update.effective_chat = MagicMock(spec=Chat)
        self.update.effective_chat.id = 12345
        self.update.effective_chat.type = "private"
        self.update.effective_user = MagicMock(spec=User)
        self.update.effective_user.id = 67890
        self.update.effective_user.first_name = "Test User"
        self.update.effective_user.username = "testuser"

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_start(self, mock_set_commands):
        await bot.cmd_start(self.update, self.context)
        self.message.reply_text.assert_called_once()
        args, kwargs = self.message.reply_text.call_args
        self.assertIn("Welcome", args[0])
        mock_set_commands.assert_called_once()

    @patch("bookclub_bot.set_user_commands", new_callable=AsyncMock)
    async def test_cmd_language(self, mock_set_commands):
        self.context.user_data["lang"] = "en"
        await bot.cmd_language(self.update, self.context)
        self.assertEqual(self.context.user_data["lang"], "ru")
        self.message.reply_text.assert_called_once()
        mock_set_commands.assert_called_once_with(self.context.bot, self.update, "ru")

    async def test_cmd_list_empty(self):
        await bot.cmd_list(self.update, self.context)
        self.message.reply_text.assert_called_once()
        args, kwargs = self.message.reply_text.call_args
        # Should show 'no undiscussed books'
        self.assertIn("No undiscussed books", args[0])

    async def test_cmd_list_with_books(self):
        bot.db_add_book("Book 1", "Author 1", 100, True, "", "", 1, "u1")
        await bot.cmd_list(self.update, self.context)
        # Should be called once for each book + possibly header (but cmd_list calls once per book)
        # Actually cmd_list calls once per book and no header if undiscussed
        self.assertEqual(self.message.reply_text.call_count, 1)
        args, kwargs = self.message.reply_text.call_args
        self.assertIn("Book 1", args[0])

    async def test_cmd_add(self):
        state = await bot.cmd_add(self.update, self.context)
        self.assertEqual(state, bot.ADDING_TITLE)
        self.message.reply_text.assert_called_once()
        self.assertIn("title", self.message.reply_text.call_args[0][0])

    async def test_add_title(self):
        self.context.user_data["new_book"] = {}
        self.message.text = "My Great Book"
        state = await bot.add_title(self.update, self.context)
        self.assertEqual(self.context.user_data["new_book"]["title"], "My Great Book")
        self.assertEqual(state, bot.ADDING_AUTHOR)
        self.message.reply_text.assert_called_once()

    async def test_add_pages_invalid(self):
        self.message.text = "not a number"
        state = await bot.add_pages(self.update, self.context)
        self.assertEqual(state, bot.ADDING_PAGES)
        self.message.reply_text.assert_called_once()
        self.assertIn("valid number", self.message.reply_text.call_args[0][0])

if __name__ == "__main__":
    unittest.main()
