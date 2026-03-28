import unittest
import sqlite3
import os
from datetime import datetime
from unittest.mock import MagicMock

# Import the bot module
# Note: Since the bot script is not a package, we might need some trickery
# but we'll try direct import first.
import bookclub_bot as bot

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Use an in-memory database for testing
        # We need a shared in-memory database if we close and open connections
        # but the current code opens new connections every time.
        # SQLite in-memory ":memory:" is unique to the connection.
        # Using a temporary file instead.
        self.db_file = "test_bookclub.db"
        bot.DB_PATH = self.db_file
        bot.init_db()

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_init_db(self):
        # Verify tables are created
        with sqlite3.connect(bot.DB_PATH) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            self.assertIn("books", tables)
            self.assertIn("votes", tables)

    def test_db_add_get_book(self):
        book_id = bot.db_add_book(
            title="Test Book",
            author="Test Author",
            pages=100,
            fiction=True,
            review_link="http://example.com",
            description="Test Description",
            user_id=123,
            user_name="tester",
            username="testuser"
        )
        self.assertIsNotNone(book_id)
        
        book = bot.db_get_book(book_id)
        self.assertEqual(book["title"], "Test Book")
        self.assertEqual(book["author"], "Test Author")
        self.assertEqual(book["pages"], 100)
        self.assertEqual(book["fiction"], 1)
        self.assertEqual(book["added_by"], 123)

    def test_db_get_books_undiscussed(self):
        bot.db_add_book("Book 1", "Author 1", 100, True, "", "", 1, "u1")
        bot.db_add_book("Book 2", "Author 2", 200, False, "", "", 2, "u2")
        
        books = bot.db_get_books(discussed=False)
        self.assertEqual(len(books), 2)

    def test_db_get_books_unvoted(self):
        book1_id = bot.db_add_book("Book 1", "Author 1", 100, True, "", "", 1, "u1")
        book2_id = bot.db_add_book("Book 2", "Author 2", 200, False, "", "", 2, "u2")
        
        # User 10 votes for Book 1
        bot.db_cast_vote(10, book1_id, 1)
        
        # All undiscussed
        all_books = bot.db_get_books(discussed=False)
        self.assertEqual(len(all_books), 2)
        
        # Unvoted for user 10
        unvoted = bot.db_get_books(discussed=False, user_id_unvoted=10)
        self.assertEqual(len(unvoted), 1)
        self.assertEqual(unvoted[0]["id"], book2_id)

    def test_db_mark_discussed(self):
        book_id = bot.db_add_book("Book", "Author", 100, True, "", "", 1, "u1")
        bot.db_mark_discussed(book_id, "2023-01-01")
        
        book = bot.db_get_book(book_id)
        self.assertEqual(book["discussed"], 1)
        self.assertEqual(book["discussed_at"], "2023-01-01")
        
        undiscussed = bot.db_get_books(discussed=False)
        self.assertEqual(len(undiscussed), 0)
        
        discussed = bot.db_get_books(discussed=True)
        self.assertEqual(len(discussed), 1)

    def test_db_cast_vote(self):
        book_id = bot.db_add_book("Book", "Author", 100, True, "", "", 1, "u1")
        bot.db_cast_vote(user_id=10, book_id=book_id, score=1)
        
        vote = bot.db_get_user_vote(10, book_id)
        self.assertEqual(vote, 1)
        
        book = bot.db_get_book(book_id)
        self.assertEqual(book["vote_count"], 1)
        self.assertEqual(book["avg_score"], 1.0)

    def test_db_update_book_field(self):
        book_id = bot.db_add_book("Old Title", "Author", 100, True, "", "", 1, "u1")
        bot.db_update_book_field(book_id, "title", "New Title")
        
        book = bot.db_get_book(book_id)
        self.assertEqual(book["title"], "New Title")

    def test_db_delete_book(self):
        book_id = bot.db_add_book("Book", "Author", 100, True, "", "", 1, "u1")
        bot.db_delete_book(book_id)
        
        book = bot.db_get_book(book_id)
        self.assertIsNone(book)

class TestUtils(unittest.TestCase):
    def test_is_valid_url(self):
        self.assertTrue(bot.is_valid_url("http://google.com"))
        self.assertTrue(bot.is_valid_url("https://test.me/path?q=1"))
        self.assertFalse(bot.is_valid_url("google.com"))
        self.assertFalse(bot.is_valid_url("just text"))

    def test_parse_date(self):
        self.assertEqual(bot.parse_date("2023-10-25"), "2023-10-25")
        self.assertEqual(bot.parse_date("25.10.2023"), "2023-10-25")
        self.assertEqual(bot.parse_date("25/10/2023"), "2023-10-25")
        self.assertIsNone(bot.parse_date("invalid date"))

    def test_tr(self):
        # Mock context with user_data for language
        ctx = MagicMock()
        ctx.user_data = {"lang": "en"}
        self.assertEqual(bot.tr(ctx, "cancel_btn"), "❌ Cancel")
        
        ctx.user_data["lang"] = "ru"
        self.assertEqual(bot.tr(ctx, "cancel_btn"), "❌ Отмена")

    def test_score_display(self):
        book = {
            "votes_yes": 3,
            "votes_meh": 1,
            "votes_no": 0,
            "vote_count": 4,
            "avg_score": 0.5
        }
        display_en = bot.score_display(book, "en")
        self.assertIn("✅ 3", display_en)
        self.assertIn("😐 1", display_en)
        self.assertIn("❌ 0", display_en)

if __name__ == "__main__":
    unittest.main()
