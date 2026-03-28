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

    async def test_cmd_list(self):
        # Now cmd_list only shows a prompt
        await bot.cmd_list(self.update, self.context)
        self.message.reply_text.assert_called_once()
        args, kwargs = self.message.reply_text.call_args
        self.assertIn("Show all books", args[0])
        self.assertIn("reply_markup", kwargs)

    async def test_list_choice_all(self):
        bot.db_add_book("Book 1", "Author 1", 100, True, "", "", 1, "u1")
        # Mock callback query
        query = AsyncMock()
        query.data = "list:all"
        query.from_user.id = self.update.effective_user.id
        self.update.callback_query = query
        
        await bot.list_choice_cb(self.update, self.context)
        
        query.answer.assert_called_once()
        query.delete_message.assert_called_once()
        # Should send message for the book
        self.context.bot.send_message.assert_called_once()
        args, kwargs = self.context.bot.send_message.call_args
        self.assertIn("Book 1", kwargs["text"])

    async def test_list_choice_unvoted(self):
        book_id = bot.db_add_book("Book 1", "Author 1", 100, True, "", "", 1, "u1")
        # Vote on it
        bot.db_cast_vote(self.update.effective_user.id, book_id, 1)
        
        # Mock callback query
        query = AsyncMock()
        query.data = "list:unvoted"
        query.from_user.id = self.update.effective_user.id
        self.update.callback_query = query
        
        await bot.list_choice_cb(self.update, self.context)
        
        # Should NOT send message for the book (already voted)
        # Instead should show "You've voted on all books!"
        self.context.bot.send_message.assert_not_called()
        query.edit_message_text.assert_called_once()
        self.assertIn("voted on all", query.edit_message_text.call_args[0][0])

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

    async def test_cmd_top(self):
        # Create 6 books, with 5th and 6th having the same score/votes
        for i in range(1, 7):
            book_id = bot.db_add_book(f"Book {i}", f"Author {i}", 100, True, "", "", i, f"u{i}")
            # Give same score to all
            bot.db_cast_vote(1001, book_id, 1) # All have 1 vote with score 1
        
        await bot.cmd_top(self.update, self.context)
        
        # Should have called reply_text twice: once for the list, once for the button
        self.assertEqual(self.message.reply_text.call_count, 2)
        text = self.message.reply_text.call_args_list[0][0][0]
        self.assertIn("Top Books", text)
        self.assertIn("Sorted by average score", text)
        # Should show all 6 books because they all have the same score
        for i in range(1, 7):
            self.assertIn(f"Book {i}", text)

    async def test_cmd_top_score_calc_btn(self):
        bot.db_add_book("Book 1", "Author 1", 100, True, "", "", 1, "u1")
        await bot.cmd_top(self.update, self.context)
        
        # Should have called reply_text twice: once for the list, once for the button
        self.assertEqual(self.message.reply_text.call_count, 2)
        
        # Second call should have the button
        args, kwargs = self.message.reply_text.call_args_list[1]
        self.assertEqual(args[0], "---")
        self.assertIn("reply_markup", kwargs)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].callback_data, "score_calc_info")
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].text, "📊 How a score is calculated")

    async def test_score_calc_cb(self):
        query = AsyncMock()
        query.data = "score_calc_info"
        self.update.callback_query = query
        
        await bot.score_calc_cb(self.update, self.context)
        
        query.answer.assert_called_once()
        kwargs = query.answer.call_args[1]
        self.assertTrue(kwargs["show_alert"])
        self.assertIn("score is calculated as follows", kwargs["text"])

    async def test_cmd_top_cut_off(self):
        # Create 7 books, 1-5 have score 1, 6-7 have score 0.5
        for i in range(1, 6):
            book_id = bot.db_add_book(f"Book {i}", f"Author {i}", 100, True, "", "", i, f"u{i}")
            bot.db_cast_vote(1001, book_id, 1)
        
        for i in range(6, 8):
            book_id = bot.db_add_book(f"Book {i}", f"Author {i}", 100, True, "", "", i, f"u{i}")
            bot.db_cast_vote(1001, book_id, 0)
            
        await bot.cmd_top(self.update, self.context)
        
        self.assertEqual(self.message.reply_text.call_count, 2)
        text = self.message.reply_text.call_args_list[0][0][0]
        # Should show only first 5
        for i in range(1, 6):
            self.assertIn(f"Book {i}", text)
        self.assertNotIn("Book 6", text)
        self.assertNotIn("Book 7", text)

    async def test_cmd_top_ru(self):
        self.context.user_data["lang"] = "ru"
        bot.db_add_book("Книга 1", "Автор 1", 100, True, "", "", 1, "u1")
        await bot.cmd_top(self.update, self.context)
        self.assertEqual(self.message.reply_text.call_count, 2)
        text = self.message.reply_text.call_args_list[0][0][0]
        self.assertIn("Топ книг", text)
        self.assertIn("Сортировка по среднему баллу", text)

if __name__ == "__main__":
    unittest.main()
