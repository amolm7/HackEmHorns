"""A provider's temporary failure should not fail a hire, but a real error still must."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from backend.contracts import Error
from backend.recruiter import setup_generate
from backend.runtime import model


def http_error(code, message):
    return urllib.error.HTTPError("https://api.meta.ai", code, "x", {}, io.BytesIO(json.dumps({"error": {"message": message}}).encode()))


def good_reply():
    text = json.dumps({"name": "A", "job_description": "j", "instructions": "i", "capability_ids": [], "kind": "hire"})
    return {"role": "model", "parts": [{"text": text}]}, {}


class App:
    config = {"SETUP_TIMEOUT": 10}


class MetaNotFoundIsTemporary(unittest.TestCase):
    def meta(self, code, message):
        settings = {"MODEL_API_KEY": "k"}
        with patch.object(model.urllib.request, "urlopen", side_effect=http_error(code, message)):
            with self.assertRaises(Error) as raised:
                model.meta_generate(settings, [{"role": "user", "parts": [{"text": "hi"}]}], "s")
        return raised.exception

    def test_model_not_found_404_is_marked_retryable(self):
        self.assertTrue(self.meta(404, "The requested model was not found.").details["retryable"])

    def test_other_client_errors_are_not(self):
        self.assertFalse(self.meta(400, "Bad schema").details["retryable"])
        self.assertFalse(self.meta(401, "Invalid key").details["retryable"])
        self.assertFalse(self.meta(404, "No such endpoint").details["retryable"])


class HiringRetries(unittest.TestCase):
    def run_setup(self, side_effect):
        with patch("backend.recruiter.RETRY_PAUSES", (0, 0)), patch.object(model, "generate", side_effect=side_effect) as gen:
            try:
                return setup_generate(App, ([], "x"), "meta"), gen.call_count
            except Error as error:
                return error, gen.call_count

    def temporary(self):
        return Error("Meta Model API returned HTTP 404: The requested model was not found.", 502, "provider_error", {"retryable": True})

    def test_succeeds_after_two_temporary_failures(self):
        result, calls = self.run_setup([self.temporary(), self.temporary(), good_reply()])
        self.assertEqual(calls, 3)
        self.assertEqual(result["name"], "A")

    def test_gives_up_after_three_attempts(self):
        result, calls = self.run_setup([self.temporary()] * 5)
        self.assertEqual(calls, 3)
        self.assertIsInstance(result, Error)

    def test_a_real_error_is_not_retried(self):
        result, calls = self.run_setup([Error("Meta Model API returned HTTP 401", 502, "provider_error", {"retryable": False})])
        self.assertEqual(calls, 1)
        self.assertIsInstance(result, Error)


if __name__ == "__main__":
    unittest.main()


class GeminiFallsBack(unittest.TestCase):
    def reply(self):
        body = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        response = io.BytesIO(json.dumps(body).encode())
        response.__enter__ = lambda self=response: self
        response.__exit__ = lambda *a: False
        return response

    def call(self, effects, config=None):
        settings = {"GEMINI_API_KEY": "k", **(config or {})}
        with patch.object(model.urllib.request, "urlopen", side_effect=effects) as opened:
            try:
                model.gemini_generate(settings, [{"role": "user", "parts": [{"text": "hi"}]}], "s")
                error = None
            except Error as caught:
                error = caught
        return error, [call.args[0].full_url for call in opened.call_args_list]

    def test_overloaded_model_falls_back_to_the_next(self):
        error, urls = self.call([http_error(503, "high demand"), self.reply()])
        self.assertIsNone(error)
        self.assertIn("gemini-3.8-flash", urls[0])
        self.assertIn("gemini-3.6-flash", urls[1])

    def test_client_errors_do_not_fall_back(self):
        error, urls = self.call([http_error(400, "bad request")])
        self.assertEqual(len(urls), 1)
        self.assertFalse(error.details["retryable"])

    def test_all_models_overloaded_still_fails_retryable(self):
        error, urls = self.call([http_error(503, "busy")] * 3)
        self.assertEqual(len(urls), 3)
        self.assertTrue(error.details["retryable"])
