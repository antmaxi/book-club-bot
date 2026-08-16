import unittest

from bookclub.original_languages import (
    STORED_ORIGINAL_LANGUAGE,
    display_original_language,
    original_language_code_for_stored,
    stored_original_language,
)


class TestOriginalLanguages(unittest.TestCase):
    def test_stored_names(self):
        self.assertEqual(stored_original_language("de"), "German")
        self.assertEqual(stored_original_language("ja"), "Japanese")
        self.assertIsNone(stored_original_language("xx"))

    def test_all_codes_have_english_names(self):
        self.assertEqual(len(STORED_ORIGINAL_LANGUAGE), 8)

    def test_display_follows_ui_language(self):
        self.assertIn("German", display_original_language("German", "en"))
        self.assertIn("Немецкий", display_original_language("German", "ru"))
        self.assertNotIn("German", display_original_language("German", "ru"))
        self.assertEqual(display_original_language("Ukrainian", "ru"), "Ukrainian")

    def test_code_for_stored(self):
        self.assertEqual(original_language_code_for_stored("German"), "de")
        self.assertIsNone(original_language_code_for_stored("Ukrainian"))


if __name__ == "__main__":
    unittest.main()
