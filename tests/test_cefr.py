import unittest

from bookclub.cefr import format_language_levels, parse_language_levels


class TestCefrLevels(unittest.TestCase):
    def test_format_orders_levels(self):
        self.assertEqual(format_language_levels({"B2", "A1", "B1"}), "A1,B1,B2")

    def test_parse_roundtrip(self):
        stored = "C1,C2"
        self.assertEqual(format_language_levels(parse_language_levels(stored)), stored)

    def test_invalid_levels_ignored(self):
        self.assertEqual(format_language_levels({"XX", "A1"}), "A1")


if __name__ == "__main__":
    unittest.main()
