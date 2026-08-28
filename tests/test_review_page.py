"""Tests for catalog lookup and review-page fetch/verify."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from bookclub import review_page


class TestTitleMatch(unittest.TestCase):
    def test_substring_and_tokens(self):
        self.assertTrue(
            review_page.page_mentions_title(
                "War and Peace is a novel by Leo Tolstoy.", "War and Peace"
            )
        )
        self.assertFalse(
            review_page.page_mentions_title(
                "Anna Karenina is a novel by Leo Tolstoy.", "War and Peace"
            )
        )

    def test_html_to_text_strips_tags(self):
        text = review_page.html_to_text(
            "<html><script>ignore</script><p>War and Peace</p><br>1225 pages</html>"
        )
        self.assertIn("War and Peace", text)
        self.assertIn("1225 pages", text)
        self.assertNotIn("ignore", text)
        self.assertNotIn("<p>", text)


class TestHostAllowlist(unittest.TestCase):
    def test_allows_wikipedia_and_rejects_localhost(self):
        self.assertTrue(
            review_page.host_allowed("https://en.wikipedia.org/wiki/War_and_Peace")
        )
        self.assertFalse(review_page.host_allowed("https://127.0.0.1/secret"))
        self.assertFalse(review_page.host_allowed("http://localhost/wiki"))
        self.assertFalse(
            review_page.host_allowed("https://en.wikipedia.org.evil.example/wiki")
        )


class TestCatalogLookup(unittest.TestCase):
    def test_wikipedia_opensearch_match(self):
        payload = json.dumps(
            [
                "War and Peace",
                ["War and Peace"],
                ["novel by Leo Tolstoy"],
                ["https://en.wikipedia.org/wiki/War_and_Peace"],
            ]
        )

        def fake_get(url: str, **_kwargs: object) -> tuple[str, str] | None:
            if "wikipedia.org" in url:
                return url, payload
            return None

        with patch.object(review_page, "http_get", side_effect=fake_get):
            url = review_page.pick_catalog_review_url(
                "War and Peace", lang="en", entity="book"
            )
        self.assertEqual(url, "https://en.wikipedia.org/wiki/War_and_Peace")

    def test_skips_disambiguation(self):
        payload = json.dumps(
            [
                "Dune",
                ["Dune (disambiguation)"],
                ["Dune may refer to"],
                ["https://en.wikipedia.org/wiki/Dune_(disambiguation)"],
            ]
        )
        with patch.object(review_page, "http_get", return_value=("https://x", payload)):
            url = review_page.pick_catalog_review_url("Dune", lang="en", entity="film")
        self.assertIsNone(url)

    def test_verified_url_requires_title_on_page(self):
        def fake_fetch(url: str) -> tuple[str, str] | None:
            if "wrong-id" in url:
                return url, "Some other book entirely. 12 pages."
            return url, "War and Peace is a novel. 1225 pages."

        with patch.object(review_page, "fetch_review_text", side_effect=fake_fetch):
            chosen = review_page.first_verified_review_url(
                [
                    "https://www.goodreads.com/book/show/1.wrong-id",
                    "https://en.wikipedia.org/wiki/War_and_Peace",
                ],
                "War and Peace",
            )
        self.assertEqual(chosen, "https://en.wikipedia.org/wiki/War_and_Peace")
