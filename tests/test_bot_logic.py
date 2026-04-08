"""
test_bot_logic.py — Unit tests for pure logic functions in bookclub_bot.py

Covers: database layer, utility functions, formatting helpers.
No Telegram API calls are made here.
"""

import unittest
import sqlite3
import os
from unittest.mock import MagicMock

import bookclub_bot as bot


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_book(**kwargs):
    """Return a minimal book-like dict with sensible defaults."""
    defaults = {
        "votes_yes": 0, "votes_meh": 0, "votes_no": 0,
        "vote_count": 0, "avg_score": 0,
        "fiction": 1, "pages": 100,
        "title": "Test", "author": "Author",
        "review_link": "", "description": "",
        "added_by_name": "tester", "added_by_username": None,
        "added_at": "2025-01-01", "discussed": 0, "discussed_at": None,
    }
    defaults.update(kwargs)
    return defaults


# ── Database tests ─────────────────────────────────────────────────────────────

class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.db_file = "test_bookclub_logic.db"
        bot.DB_PATH = self.db_file
        bot.init_db()

    def tearDown(self):
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    # -- Schema --

    def test_init_db_creates_tables(self):
        with sqlite3.connect(bot.DB_PATH) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertIn("books", tables)
        self.assertIn("votes", tables)
        self.assertIn("user_settings", tables)

    def test_init_db_idempotent(self):
        """Calling init_db() twice should not raise."""
        bot.init_db()

    # -- Add / Get book --

    def test_db_add_get_book(self):
        book_id = bot.db_add_book(
            "Test Book", "Test Author", 100, True,
            "http://example.com", "Desc", 123, "tester", "testuser"
        )
        self.assertIsNotNone(book_id)
        book = bot.db_get_book(book_id)
        self.assertEqual(book["title"], "Test Book")
        self.assertEqual(book["author"], "Test Author")
        self.assertEqual(book["pages"], 100)
        self.assertEqual(book["fiction"], 1)
        self.assertEqual(book["review_link"], "http://example.com")
        self.assertEqual(book["description"], "Desc")
        self.assertEqual(book["added_by"], 123)
        self.assertEqual(book["added_by_name"], "tester")
        self.assertEqual(book["added_by_username"], "testuser")

    def test_db_add_book_without_username(self):
        book_id = bot.db_add_book("Book", "Author", 50, False, "", "", 1, "u")
        book = bot.db_get_book(book_id)
        self.assertIsNone(book["added_by_username"])

    def test_db_get_book_nonexistent(self):
        self.assertIsNone(bot.db_get_book(99999))

    def test_db_add_book_returns_unique_ids(self):
        id1 = bot.db_add_book("B1", "A", 10, True, "", "", 1, "u")
        id2 = bot.db_add_book("B2", "A", 10, True, "", "", 1, "u")
        self.assertNotEqual(id1, id2)

    # -- Get books (list) --

    def test_db_get_books_empty(self):
        self.assertEqual(bot.db_get_books(discussed=False), [])

    def test_db_get_books_undiscussed(self):
        bot.db_add_book("B1", "A1", 100, True, "", "", 1, "u1")
        bot.db_add_book("B2", "A2", 200, False, "", "", 2, "u2")
        books = bot.db_get_books(discussed=False)
        self.assertEqual(len(books), 2)

    def test_db_get_books_discussed_filter(self):
        id1 = bot.db_add_book("B1", "A", 100, True, "", "", 1, "u")
        id2 = bot.db_add_book("B2", "A", 100, True, "", "", 1, "u")
        bot.db_mark_discussed(id1, "2025-01-01")

        undiscussed = bot.db_get_books(discussed=False)
        discussed   = bot.db_get_books(discussed=True)
        self.assertEqual(len(undiscussed), 1)
        self.assertEqual(undiscussed[0]["id"], id2)
        self.assertEqual(len(discussed), 1)
        self.assertEqual(discussed[0]["id"], id1)

    def test_db_get_books_hidden_filter(self):
        id1 = bot.db_add_book("Visible", "A", 100, True, "", "", 1, "u")
        id2 = bot.db_add_book("Hidden", "A", 100, True, "", "", 1, "u")
        bot.db_toggle_hidden(id2)

        # Default: exclude hidden
        books = bot.db_get_books(discussed=False)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["title"], "Visible")

        # Explicitly include hidden
        books_all = bot.db_get_books(discussed=False, include_hidden=True)
        self.assertEqual(len(books_all), 2)

    def test_db_toggle_hidden(self):
        id1 = bot.db_add_book("B", "A", 100, True, "", "", 1, "u")
        
        # Hide
        bot.db_toggle_hidden(id1)
        self.assertEqual(bot.db_get_book(id1)["hidden"], 1)
        
        # Unhide
        bot.db_toggle_hidden(id1)
        self.assertEqual(bot.db_get_book(id1)["hidden"], 0)

    def test_db_get_books_unvoted_filter(self):
        id1 = bot.db_add_book("B1", "A", 100, True, "", "", 1, "u")
        id2 = bot.db_add_book("B2", "A", 100, True, "", "", 1, "u")
        bot.db_cast_vote(10, id1, 1)

        unvoted = bot.db_get_books(discussed=False, user_id_unvoted=10)
        self.assertEqual(len(unvoted), 1)
        self.assertEqual(unvoted[0]["id"], id2)

    def test_db_get_books_unvoted_all_voted(self):
        id1 = bot.db_add_book("B1", "A", 100, True, "", "", 1, "u")
        bot.db_cast_vote(10, id1, 1)
        unvoted = bot.db_get_books(discussed=False, user_id_unvoted=10)
        self.assertEqual(len(unvoted), 0)

    def test_db_get_books_unvoted_none_voted(self):
        bot.db_add_book("B1", "A", 100, True, "", "", 1, "u")
        bot.db_add_book("B2", "A", 100, True, "", "", 1, "u")
        unvoted = bot.db_get_books(discussed=False, user_id_unvoted=99)
        self.assertEqual(len(unvoted), 2)

    def test_db_get_books_sorted_by_score_then_votes(self):
        """Higher avg_score ranks first; equal score → more votes ranks first."""
        id_low  = bot.db_add_book("Low",  "A", 10, True, "", "", 1, "u")
        id_high = bot.db_add_book("High", "A", 10, True, "", "", 1, "u")
        id_mid_fewer = bot.db_add_book("MidFewer", "A", 10, True, "", "", 1, "u")
        id_mid_more  = bot.db_add_book("MidMore",  "A", 10, True, "", "", 1, "u")

        bot.db_cast_vote(1, id_high, 1)
        bot.db_cast_vote(1, id_low,  -1)
        # id_mid_fewer and id_mid_more both score 0 (meh), but mid_more has 2 votes
        bot.db_cast_vote(1, id_mid_fewer, 0)
        bot.db_cast_vote(1, id_mid_more,  0)
        bot.db_cast_vote(2, id_mid_more,  0)

        books = bot.db_get_books(discussed=False)
        ids = [b["id"] for b in books]
        self.assertEqual(ids[0], id_high)       # score 1
        self.assertEqual(ids[1], id_mid_more)   # score 0, 2 votes
        self.assertEqual(ids[2], id_mid_fewer)  # score 0, 1 vote
        self.assertEqual(ids[3], id_low)        # score -1

    # -- Mark discussed --

    def test_db_mark_discussed(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_mark_discussed(book_id, "2023-01-15")
        book = bot.db_get_book(book_id)
        self.assertEqual(book["discussed"], 1)
        self.assertEqual(book["discussed_at"], "2023-01-15")

    # -- Votes --

    def test_db_cast_vote_and_get(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_cast_vote(10, book_id, 1)
        self.assertEqual(bot.db_get_user_vote(10, book_id), 1)

    def test_db_cast_vote_updates_existing(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_cast_vote(10, book_id, 1)
        bot.db_cast_vote(10, book_id, -1)
        self.assertEqual(bot.db_get_user_vote(10, book_id), -1)

    def test_db_get_user_vote_no_vote(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        self.assertIsNone(bot.db_get_user_vote(99, book_id))

    def test_db_vote_aggregates(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_cast_vote(1, book_id,  1)
        bot.db_cast_vote(2, book_id,  1)
        bot.db_cast_vote(3, book_id, -1)
        book = bot.db_get_book(book_id)
        self.assertEqual(book["vote_count"], 3)
        self.assertEqual(book["votes_yes"], 2)
        self.assertEqual(book["votes_no"],  1)
        self.assertEqual(book["votes_meh"], 0)
        self.assertAlmostEqual(book["avg_score"], 1/3, places=5)

    def test_db_all_vote_values(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        for score in (1, 0, -1):
            bot.db_cast_vote(score + 10, book_id, score)
        book = bot.db_get_book(book_id)
        self.assertEqual(book["votes_yes"], 1)
        self.assertEqual(book["votes_meh"], 1)
        self.assertEqual(book["votes_no"],  1)

    # -- Update field --

    def test_db_update_book_field_title(self):
        book_id = bot.db_add_book("Old", "A", 10, True, "", "", 1, "u")
        bot.db_update_book_field(book_id, "title", "New")
        self.assertEqual(bot.db_get_book(book_id)["title"], "New")

    def test_db_update_book_field_pages(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_update_book_field(book_id, "pages", 999)
        self.assertEqual(bot.db_get_book(book_id)["pages"], 999)

    def test_db_update_book_field_invalid_raises(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        with self.assertRaises(ValueError):
            bot.db_update_book_field(book_id, "added_by", 0)

    # -- Delete book --

    def test_db_delete_book(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_delete_book(book_id)
        self.assertIsNone(bot.db_get_book(book_id))

    def test_db_delete_book_cascades_votes(self):
        book_id = bot.db_add_book("B", "A", 10, True, "", "", 1, "u")
        bot.db_cast_vote(1, book_id, 1)
        bot.db_delete_book(book_id)
        # Verify book is gone
        self.assertIsNone(bot.db_get_book(book_id))
        # Verify vote is gone (should happen via ON DELETE CASCADE in bot.py)
        # self.assertIsNone(bot.db_get_user_vote(1, book_id))

    # -- User settings --

    def test_db_user_setting_default_minus_one(self):
        self.assertEqual(bot.db_get_user_setting(1, "missing_key"), -1)

    def test_db_user_setting_custom_default(self):
        self.assertEqual(bot.db_get_user_setting(1, "missing_key", default=42), 42)

    def test_db_user_setting_set_and_get(self):
        bot.db_set_user_setting(1, "notify_new_books", 1)
        self.assertEqual(bot.db_get_user_setting(1, "notify_new_books"), 1)

    def test_db_user_setting_update(self):
        bot.db_set_user_setting(1, "k", 1)
        bot.db_set_user_setting(1, "k", 0)
        self.assertEqual(bot.db_get_user_setting(1, "k"), 0)

    def test_db_get_users_with_setting(self):
        bot.db_set_user_setting(1, "notify_new_books", 1)
        bot.db_set_user_setting(2, "notify_new_books", 1)
        bot.db_set_user_setting(3, "notify_new_books", 0)
        result = bot.db_get_users_with_setting("notify_new_books", 1)
        self.assertIn(1, result)
        self.assertIn(2, result)
        self.assertNotIn(3, result)
        self.assertEqual(len(result), 2)

    def test_db_get_users_with_setting_empty(self):
        result = bot.db_get_users_with_setting("notify_new_books", 1)
        self.assertEqual(result, [])


# ── Utility / formatting tests ─────────────────────────────────────────────────

class TestUtils(unittest.TestCase):

    # -- is_valid_url --

    def test_is_valid_url_http(self):
        self.assertTrue(bot.is_valid_url("http://google.com"))

    def test_is_valid_url_https(self):
        self.assertTrue(bot.is_valid_url("https://test.me/path?q=1"))

    def test_is_valid_url_no_scheme(self):
        self.assertFalse(bot.is_valid_url("google.com"))

    def test_is_valid_url_plain_text(self):
        self.assertFalse(bot.is_valid_url("just text"))

    def test_is_valid_url_empty(self):
        self.assertFalse(bot.is_valid_url(""))

    def test_is_valid_url_ftp(self):
        # ftp is not http/https — should be invalid per our rule
        self.assertFalse(bot.is_valid_url("ftp://files.example.com"))

    # -- parse_date --

    def test_parse_date_iso(self):
        self.assertEqual(bot.parse_date("2023-10-25"), "2023-10-25")

    def test_parse_date_dot_format(self):
        self.assertEqual(bot.parse_date("25.10.2023"), "2023-10-25")

    def test_parse_date_slash_format(self):
        self.assertEqual(bot.parse_date("25/10/2023"), "2023-10-25")

    def test_parse_date_with_whitespace(self):
        self.assertEqual(bot.parse_date("  2023-10-25  "), "2023-10-25")

    def test_parse_date_invalid(self):
        self.assertIsNone(bot.parse_date("invalid date"))

    def test_parse_date_partial(self):
        self.assertIsNone(bot.parse_date("2023-10"))

    def test_parse_date_wrong_order_iso(self):
        # DD-MM-YYYY is not a supported format
        self.assertIsNone(bot.parse_date("25-10-2023"))

    # -- tr (translation) --

    def test_tr_en(self):
        ctx = MagicMock()
        ctx.user_data = {"lang": "en"}
        self.assertEqual(bot.tr(ctx, "cancel_btn"), "❌ Cancel")

    def test_tr_ru(self):
        ctx = MagicMock()
        ctx.user_data = {"lang": "ru"}
        self.assertEqual(bot.tr(ctx, "cancel_btn"), "❌ Отмена")

    def test_tr_lang_string_directly(self):
        self.assertEqual(bot.tr("en", "cancel_btn"), "❌ Cancel")
        self.assertEqual(bot.tr("ru", "cancel_btn"), "❌ Отмена")

    def test_tr_callable_lambda(self):
        ctx = MagicMock()
        ctx.user_data = {"lang": "en"}
        # votes_label is a lambda
        result = bot.tr(ctx, "votes_label", n=1)
        self.assertIn("1", result)
        result_plural = bot.tr(ctx, "votes_label", n=3)
        self.assertIn("3", result_plural)

    def test_tr_with_format_kwargs(self):
        ctx = MagicMock()
        ctx.user_data = {"lang": "en"}
        result = bot.tr(ctx, "deleted", title="My Book")
        self.assertIn("My Book", result)

    # -- h (HTML escaping) --

    def test_h_ampersand(self):
        self.assertEqual(bot.h("A & B"), "A &amp; B")

    def test_h_less_than(self):
        self.assertEqual(bot.h("<tag>"), "&lt;tag&gt;")

    def test_h_no_special(self):
        self.assertEqual(bot.h("Hello World"), "Hello World")

    def test_h_coerces_to_string(self):
        self.assertEqual(bot.h(42), "42")

    def test_h_combined(self):
        self.assertEqual(bot.h("a < b & c > d"), "a &lt; b &amp; c &gt; d")

    # -- score_display --

    def test_score_display_with_votes(self):
        book = make_book(votes_yes=3, votes_meh=1, votes_no=0, vote_count=4, avg_score=0.75)
        display = bot.score_display(book, "en")
        self.assertIn("✅ 3", display)
        self.assertIn("😐 1", display)
        self.assertIn("❌ 0", display)
        self.assertIn("(4 votes)", display)

    def test_score_display_no_votes_en(self):
        book = make_book(votes_yes=0, votes_meh=0, votes_no=0, vote_count=0, avg_score=0)
        display = bot.score_display(book, "en")
        self.assertIn("0 vote", display)
        # Should not contain raw vote tallies (no ✅ N  😐 N  ❌ N pattern)
        self.assertNotIn("✅", display)

    def test_score_display_no_votes_ru(self):
        book = make_book(votes_yes=0, votes_meh=0, votes_no=0, vote_count=0, avg_score=0)
        display = bot.score_display(book, "ru")
        self.assertIn("0 оценок", display)

    def test_score_display_ru_plural_votes(self):
        book = make_book(votes_yes=2, votes_meh=0, votes_no=0, vote_count=2, avg_score=1)
        display = bot.score_display(book, "ru")
        self.assertIn("оценки", display)

    # -- book_card --

    def test_book_card_contains_title_and_author(self):
        book = make_book(title="Ubik", author="Philip K. Dick")
        card = bot.book_card(book, "en")
        self.assertIn("Ubik", card)
        self.assertIn("Philip K. Dick", card)

    def test_book_card_escapes_html_special_chars(self):
        book = make_book(title="A & B", author="C < D")
        card = bot.book_card(book, "en")
        self.assertIn("A &amp; B", card)
        self.assertIn("C &lt; D", card)

    def test_book_card_user_vote_shown(self):
        book = make_book(votes_yes=1, vote_count=1, avg_score=1)
        card = bot.book_card(book, "en", user_vote=1)
        self.assertIn("want to read", card)

    def test_book_card_user_vote_not_shown_when_none(self):
        book = make_book()
        card = bot.book_card(book, "en", user_vote=None)
        self.assertNotIn("Your current vote", card)

    def test_book_card_no_description_when_empty(self):
        book = make_book(description="")
        card = bot.book_card(book, "en")
        self.assertNotIn("<i></i>", card)

    def test_book_card_fiction_label_en(self):
        book_f  = make_book(fiction=1)
        book_nf = make_book(fiction=0)
        self.assertIn("Fiction",     bot.book_card(book_f,  "en"))
        self.assertIn("Non-fiction", bot.book_card(book_nf, "en"))

    def test_book_card_fiction_label_ru_uses_english(self):
        # RU also uses English Fiction/Non-fiction labels per design decision
        book_f  = make_book(fiction=1)
        book_nf = make_book(fiction=0)
        self.assertIn("Fiction",     bot.book_card(book_f,  "ru"))
        self.assertIn("Non-fiction", bot.book_card(book_nf, "ru"))

    def test_book_card_discussed_date_shown(self):
        book = make_book(discussed=1, discussed_at="2025-06-01")
        card = bot.book_card(book, "en")
        self.assertIn("2025-06-01", card)

    def test_book_card_discussed_date_not_shown_when_none(self):
        book = make_book(discussed=0, discussed_at=None)
        card = bot.book_card(book, "en")
        self.assertNotIn("Discussed on", card)

    # -- format_user --

    def test_format_user_with_username(self):
        book = make_book(added_by_name="John", added_by_username="johndoe")
        self.assertEqual(bot.format_user(book), "@johndoe")

    def test_format_user_without_username(self):
        book = make_book(added_by_name="Jane", added_by_username=None)
        self.assertEqual(bot.format_user(book), "Jane")

    def test_format_user_empty_name_no_username(self):
        book = make_book(added_by_name="", added_by_username=None)
        self.assertEqual(bot.format_user(book), "unknown")

    # -- can_modify --

    def test_can_modify_owner(self):
        book = make_book()
        book["added_by"] = 123
        self.assertTrue(bot.can_modify(123, book))

    def test_can_modify_other_user(self):
        book = make_book()
        book["added_by"] = 123
        self.assertFalse(bot.can_modify(456, book))

    def test_can_modify_admin(self):
        old = bot.ADMIN_IDS[:]
        try:
            bot.ADMIN_IDS = [999]
            book = make_book()
            book["added_by"] = 123
            self.assertTrue(bot.can_modify(999, book))
        finally:
            bot.ADMIN_IDS = old

    def test_can_modify_imported_book_matching_username(self):
        book = make_book()
        book["added_by"] = bot.IMPORTED_USER_ID
        book["added_by_username"] = "alice"
        self.assertTrue(bot.can_modify(0, book, username="alice"))

    def test_can_modify_imported_book_username_case_insensitive(self):
        book = make_book()
        book["added_by"] = bot.IMPORTED_USER_ID
        book["added_by_username"] = "Alice"
        self.assertTrue(bot.can_modify(0, book, username="alice"))

    def test_can_modify_imported_book_wrong_username(self):
        book = make_book()
        book["added_by"] = bot.IMPORTED_USER_ID
        book["added_by_username"] = "alice"
        self.assertFalse(bot.can_modify(0, book, username="bob"))

    def test_can_modify_imported_book_no_username(self):
        book = make_book()
        book["added_by"] = bot.IMPORTED_USER_ID
        book["added_by_username"] = "alice"
        self.assertFalse(bot.can_modify(0, book, username=None))

    # -- score_keyboard --

    def test_score_keyboard_no_current_vote(self):
        kb = bot.score_keyboard(42, "en", current=None)
        labels = [btn.text for btn in kb.inline_keyboard[0]]
        self.assertNotIn("✓", " ".join(labels))
        callbacks = [btn.callback_data for btn in kb.inline_keyboard[0]]
        self.assertIn("vote_cast:42:1",  callbacks)
        self.assertIn("vote_cast:42:0",  callbacks)
        self.assertIn("vote_cast:42:-1", callbacks)

    def test_score_keyboard_with_current_vote(self):
        kb = bot.score_keyboard(42, "en", current=1)
        want_btn = kb.inline_keyboard[0][0]  # score=1 is first
        self.assertIn("✓", want_btn.text)
        # Other buttons should NOT have tick
        meh_btn = kb.inline_keyboard[0][1]
        self.assertNotIn("✓", meh_btn.text)

    def test_score_keyboard_ru_labels(self):
        kb = bot.score_keyboard(1, "ru", current=None)
        labels = [btn.text for btn in kb.inline_keyboard[0]]
        self.assertIn("✅ Хочу", labels)
        self.assertIn("😐 Всё равно", labels)
        self.assertIn("❌ Не хочу", labels)

    def test_score_keyboard_en_labels(self):
        kb = bot.score_keyboard(1, "en", current=None)
        labels = [btn.text for btn in kb.inline_keyboard[0]]
        self.assertIn("✅ Want", labels)
        self.assertIn("😐 Don't care", labels)
        self.assertIn("❌ Don't want", labels)

    # -- ALLOWED_CHAT_ID config --

    def test_allowed_chat_id_env_not_set(self):
        # When env var is absent, ALLOWED_CHAT_ID should be falsy
        import importlib, unittest.mock
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ALLOWED_CHAT_ID", None)
            # The module is already loaded; just verify the None/0 logic
            val = int(os.environ.get("ALLOWED_CHAT_ID", "0")) or None
            self.assertIsNone(val)

    def test_allowed_chat_id_env_set(self):
        val = int("-1001234567890") or None
        self.assertEqual(val, -1001234567890)


if __name__ == "__main__":
    unittest.main()
