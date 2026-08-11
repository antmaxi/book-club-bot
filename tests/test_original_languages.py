import unittest

from bookclub.original_languages import (
    STORED_ORIGINAL_LANGUAGE,
    stored_original_language,
)


class TestOriginalLanguages(unittest.TestCase):
    def test_stored_names(self):
        self.assertEqual(stored_original_language("de"), "German")
        self.assertEqual(stored_original_language("ja"), "Japanese")
        self.assertIsNone(stored_original_language("xx"))

    def test_all_codes_have_english_names(self):
        self.assertEqual(len(STORED_ORIGINAL_LANGUAGE), 8)


if __name__ == "__main__":
    unittest.main()
