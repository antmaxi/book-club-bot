"""Tests for LLM-backed admin add-book suggestions."""

from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import bookclub.config as cfg
import bookclub.logging_setup as log_setup
from bookclub import llm


class TestExtractJson(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(llm.extract_json_object('{"author": "A"}'), {"author": "A"})

    def test_fenced_block(self):
        text = 'Sure.\n```json\n{"pages": 100}\n```\n'
        self.assertEqual(llm.extract_json_object(text), {"pages": 100})

    def test_embedded_object(self):
        text = 'Here you go: {"fiction": true} thanks'
        self.assertEqual(llm.extract_json_object(text), {"fiction": True})

    def test_rejects_non_object(self):
        with self.assertRaises(ValueError):
            llm.extract_json_object("[1, 2]")


class TestNormalizeSuggestions(unittest.TestCase):
    def test_keeps_enabled_fields_and_coerces_types(self):
        raw = {
            "author": "  Leo Tolstoy ",
            "pages": "1,225",
            "fiction": "fiction",
            "review_link": "https://en.wikipedia.org/wiki/War_and_Peace",
            "original_language": "русский",
            "creation_year": 1869,
            "language_levels": ["b2", "C1", "nope"],
            "description": " An epic. ",
        }
        enabled = frozenset(cfg.OPTIONAL_ENTRY_FIELDS)
        got = llm.normalize_suggestions(raw, enabled=enabled)
        self.assertEqual(got["author"], "Leo Tolstoy")
        self.assertEqual(got["pages"], 1225)
        self.assertTrue(got["fiction"])
        self.assertEqual(
            got["review_link"], "https://en.wikipedia.org/wiki/War_and_Peace"
        )
        self.assertEqual(got["original_language"], "Russian")
        self.assertEqual(got["creation_year"], 1869)
        self.assertEqual(got["language_levels"], {"B2", "C1"})
        self.assertEqual(got["description"], "An epic.")

    def test_drops_disabled_and_invalid_values(self):
        raw = {
            "author": "A",
            "pages": 0,
            "review_link": "not-a-url",
            "creation_year": 99,
            "fiction": "maybe",
        }
        got = llm.normalize_suggestions(raw, enabled=frozenset({"author"}))
        self.assertEqual(got, {"author": "A"})

    def test_film_aliases(self):
        raw = {"director": "Nolan", "runtime_minutes": 148, "is_feature_film": True}
        got = llm.normalize_suggestions(
            raw, enabled=frozenset({"author", "pages", "fiction"})
        )
        self.assertEqual(got["author"], "Nolan")
        self.assertEqual(got["pages"], 148)
        self.assertTrue(got["fiction"])

    def test_original_language_from_ui_label(self):
        self.assertEqual(llm.normalize_original_language("🇩🇪 Deutsch"), "German")
        self.assertEqual(llm.normalize_original_language("de"), "German")
        self.assertEqual(llm.normalize_original_language("Klingon"), "Klingon")


class TestSuggestBookFields(unittest.TestCase):
    def test_not_configured(self):
        with patch.object(cfg, "LLM_API_KEY", ""):
            fields, error = llm.suggest_book_fields("Title", lang="en")
        self.assertEqual(fields, {})
        self.assertEqual(error, "not_configured")

    def test_no_optional_fields(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(llm, "chat_completion") as mocked,
        ):
            fields, error = llm.suggest_book_fields(
                "Title", lang="en", enabled_fields=frozenset()
            )
        self.assertEqual(fields, {})
        self.assertIsNone(error)
        mocked.assert_not_called()

    def test_request_failed(self):
        # Do not wrap with assertLogs: that disables propagate, so the root
        # ERROR-alert handler would not see the record.
        log_setup._alert_buffer.clear()
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(cfg, "LLM_MODEL", "test-model"),
            patch.object(cfg, "LLM_API_BASE", "https://example.test/v1"),
            patch.object(
                llm, "chat_completion", side_effect=llm.LlmRequestError("boom")
            ),
        ):
            fields, error = llm.suggest_book_fields("War and Peace", lang="en")
        self.assertEqual(fields, {})
        self.assertIsNotNone(error)
        self.assertIn("boom", error or "")
        self.assertTrue(error and error.startswith("request:"))
        self.assertTrue(log_setup.ERROR_ALERTS)
        joined = "\n".join(log_setup._alert_buffer)
        self.assertIn("LLM book suggestions failed [request]", joined)
        self.assertIn("boom", joined)
        self.assertIn("War and Peace", joined)
        self.assertIn("test-model", joined)

    def test_unusable_json_logs_error(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(llm, "chat_completion", return_value="not json at all"),
            self.assertLogs("bookclub.logging_setup", level="ERROR") as captured,
        ):
            fields, error = llm.suggest_book_fields("Title", lang="en")
        self.assertEqual(fields, {})
        self.assertIsNotNone(error)
        self.assertTrue(any("unusable_json" in line for line in captured.output))
        self.assertTrue(error and error.startswith("unusable_json:"))

    def test_not_configured_does_not_log_error(self):
        with (
            patch.object(cfg, "LLM_API_KEY", ""),
            patch.object(llm.logger, "error") as mock_error,
        ):
            fields, error = llm.suggest_book_fields("Title", lang="en")
        self.assertEqual(error, "not_configured")
        mock_error.assert_not_called()

    def test_parses_completion(self):
        payload = json.dumps({"author": "A", "pages": 10, "fiction": True})
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(llm, "chat_completion", return_value=payload),
            patch.object(
                cfg, "ENTRY_FIELDS", frozenset({"author", "pages", "fiction"})
            ),
        ):
            fields, error = llm.suggest_book_fields("Title", lang="en")
        self.assertIsNone(error)
        self.assertEqual(fields["author"], "A")
        self.assertEqual(fields["pages"], 10)
        self.assertTrue(fields["fiction"])

    def test_film_prompt_mentions_director(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(llm, "chat_completion", return_value="{}") as mocked,
        ):
            llm.suggest_book_fields(
                "Inception",
                lang="en",
                entity="film",
                enabled_fields=frozenset({"author", "pages"}),
            )
        messages = mocked.call_args[0][0]
        user = messages[1]["content"]
        self.assertIn("director", user)
        self.assertIn("runtime", user)

    def test_book_prompt_review_mentions_goodreads_or_litres(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(llm, "chat_completion", return_value="{}") as mocked,
        ):
            llm.suggest_book_fields(
                "War and Peace",
                lang="en",
                entity="book",
                enabled_fields=frozenset({"review"}),
            )
        user = mocked.call_args[0][0][1]["content"]
        self.assertIn("Goodreads", user)
        self.assertIn("LitRes", user)
        self.assertNotIn("IMDb", user)

    def test_film_prompt_review_mentions_catalog_sites(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(llm, "chat_completion", return_value="{}") as mocked,
        ):
            llm.suggest_book_fields(
                "Inception",
                lang="en",
                entity="film",
                enabled_fields=frozenset({"review"}),
            )
        user = mocked.call_args[0][0][1]["content"]
        self.assertIn("IMDb", user)
        self.assertIn("Kinopoisk", user)


class TestChatCompletion(unittest.TestCase):
    def _response(self, payload: dict) -> MagicMock:
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    def test_reads_message_content(self):
        payload = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(cfg, "LLM_API_BASE", "https://example.test/v1"),
            patch.object(cfg, "LLM_MODEL", "test-model"),
            patch(
                "urllib.request.urlopen", return_value=self._response(payload)
            ) as mocked,
        ):
            content = llm.chat_completion([{"role": "user", "content": "hi"}])
        self.assertEqual(content, '{"ok": true}')
        req = mocked.call_args[0][0]
        self.assertEqual(req.full_url, "https://example.test/v1/chat/completions")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-model")
        self.assertIn("Bearer sk-test", req.get_header("Authorization") or "")
        self.assertEqual(body["temperature"], 0.2)
        self.assertNotIn("reasoning_effort", body)

    def test_grok_omits_temperature_and_uses_low_effort(self):
        payload = {"choices": [{"message": {"content": "{}"}}]}
        with (
            patch.object(cfg, "LLM_API_KEY", "xai-test"),
            patch.object(cfg, "LLM_API_BASE", "https://api.x.ai/v1"),
            patch.object(cfg, "LLM_MODEL", "grok-4.6"),
            patch.object(cfg, "LLM_REASONING_EFFORT", ""),
            patch(
                "urllib.request.urlopen", return_value=self._response(payload)
            ) as mocked,
        ):
            llm.chat_completion([{"role": "user", "content": "hi"}])
        body = json.loads(mocked.call_args[0][0].data.decode("utf-8"))
        self.assertNotIn("temperature", body)
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(
            mocked.call_args[0][0].full_url, "https://api.x.ai/v1/chat/completions"
        )

    def test_reads_json_from_reasoning_content(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning_content": 'thinking...\n{"author": "A"}\n',
                    }
                }
            ]
        }
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(cfg, "LLM_API_BASE", "https://example.test/v1"),
            patch.object(cfg, "LLM_MODEL", "test-model"),
            patch("urllib.request.urlopen", return_value=self._response(payload)),
        ):
            content = llm.chat_completion([{"role": "user", "content": "hi"}])
        self.assertIn('"author": "A"', content)

    def test_http_error(self):
        err = HTTPError(
            "https://example.test/v1/chat/completions",
            401,
            "Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error":"nope"}'),
        )
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch("urllib.request.urlopen", side_effect=err),
            self.assertRaises(llm.LlmRequestError) as caught,
        ):
            llm.chat_completion([{"role": "user", "content": "hi"}])
        self.assertEqual(str(caught.exception), "auth: HTTP 401: nope")
        self.assertEqual(caught.exception.kind, "auth")

    def test_urlerror_timeout(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch(
                "urllib.request.urlopen",
                side_effect=URLError(TimeoutError("timed out")),
            ),
            self.assertRaises(llm.LlmRequestError) as caught,
        ):
            llm.chat_completion([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "timeout")
        self.assertIn("timed out after", str(caught.exception))

    def test_network_error(self):
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch("urllib.request.urlopen", side_effect=URLError("down")),
            self.assertRaises(llm.LlmRequestError) as caught,
        ):
            llm.chat_completion([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "network")
        self.assertIn("down", str(caught.exception))


class TestApplySuggestions(unittest.TestCase):
    def test_copies_keys(self):
        nb = {"title": "T"}
        filled = llm.apply_suggestions_to_book(nb, {"author": "A", "pages": 3})
        self.assertEqual(nb["author"], "A")
        self.assertEqual(nb["title"], "T")
        self.assertEqual(filled, {"author", "pages"})


class TestResolveLlmSettings(unittest.TestCase):
    def test_xai_key_infers_base_and_model(self):
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "xai-secret",
                "XAI_API_KEY": "",
                "LLM_API_BASE": "",
                "LLM_MODEL": "",
            },
            clear=False,
        ):
            key = cfg.resolve_llm_api_key()
            base = cfg.resolve_llm_api_base(key)
            model = cfg.resolve_llm_model(base, key)
        self.assertEqual(key, "xai-secret")
        self.assertEqual(base, "https://api.x.ai/v1")
        self.assertEqual(model, "grok-4.6")

    def test_xai_api_key_alias(self):
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "",
                "OPENAI_API_KEY": "",
                "CURSOR_API_KEY": "",
                "XAI_API_KEY": "xai-from-alias",
                "LLM_API_BASE": "",
                "LLM_MODEL": "",
            },
            clear=False,
        ):
            key = cfg.resolve_llm_api_key()
            self.assertEqual(key, "xai-from-alias")
            self.assertEqual(cfg.resolve_llm_api_base(key), "https://api.x.ai/v1")

    def test_xai_key_overrides_leftover_openai_defaults(self):
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "xai-secret",
                "XAI_API_KEY": "",
                "LLM_API_BASE": "https://api.openai.com/v1",
                "LLM_MODEL": "gpt-4o-mini",
                "LLM_TIMEOUT_SECONDS": "",
            },
            clear=False,
        ):
            key = cfg.resolve_llm_api_key()
            base = cfg.resolve_llm_api_base(key)
            model = cfg.resolve_llm_model(base, key)
            timeout = cfg.resolve_llm_timeout_seconds(model)
        self.assertEqual(base, "https://api.x.ai/v1")
        self.assertEqual(model, "grok-4.6")
        self.assertEqual(timeout, 120.0)

    def test_ui_llm_error_redacts_keys(self):
        text = llm.ui_llm_error(
            'HTTP 401: Incorrect API key provided: xai-abc123SECRET {"error":"nope"}'
        )
        self.assertIn("401", text)
        self.assertNotIn("abc123SECRET", text)
        self.assertIn("xai-…", text)


class TestLlmErrorKinds(unittest.TestCase):
    def test_classifies_http_kinds(self):
        cases = [
            (401, "HTTP 401: nope", "auth"),
            (400, "HTTP 400: Incorrect API key provided", "auth"),
            (429, "HTTP 429: Too Many Requests", "rate_limit"),
            (404, "HTTP 404: The model `gpt-4o-mini` does not exist", "bad_model"),
            (404, "HTTP 404: no such endpoint", "not_found"),
            (400, "HTTP 400: Invalid argument", "bad_request"),
            (503, "HTTP 503: unavailable", "server"),
        ]
        for code, detail, kind in cases:
            with self.subTest(detail=detail):
                self.assertEqual(llm._http_error_kind(code, detail), kind)

    def test_split_llm_error(self):
        self.assertEqual(
            llm.split_llm_error("auth: HTTP 401: Incorrect API key"),
            ("auth", "HTTP 401: Incorrect API key"),
        )
        self.assertEqual(
            llm.split_llm_error("HTTP 401: leftover"),
            ("request", "HTTP 401: leftover"),
        )

    def test_empty_reply_kind(self):
        payload = {"choices": [{"message": {"content": ""}}]}
        with (
            patch.object(cfg, "LLM_API_KEY", "sk-test"),
            patch.object(cfg, "LLM_API_BASE", "https://example.test/v1"),
            patch.object(cfg, "LLM_MODEL", "test-model"),
            patch(
                "urllib.request.urlopen",
                return_value=TestChatCompletion()._response(payload),
            ),
            self.assertRaises(llm.LlmRequestError) as caught,
        ):
            llm.chat_completion([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.kind, "empty_reply")
