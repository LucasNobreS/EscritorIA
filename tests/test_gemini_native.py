import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_server
import gemini_text

s = test_server.s
KEY = "test-google-key"


def listing(*names):
    return {
        "models": [
            {"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]}
            for n in names
        ]
    }


def answer(text="OK"):
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]
    }


class GeminiNative(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()
        s.runtime.gemini_cache.clear()

    def tearDown(self):
        s.DATA = self.old
        s.runtime.gemini_cache.clear()
        self.temp.cleanup()

    def test_discovers_supported_free_text_model_and_uses_native_endpoint(self):
        calls = []

        def request(url, payload=None, headers=None, timeout=60):
            calls.append((url, payload, headers))
            if ":generateContent" not in url:
                return listing("gemini-3.1-flash-lite", "gemini-3-pro-image-preview")
            return answer("Olá")

        result = gemini_text.call(
            request,
            KEY,
            [
                {"role": "system", "content": "Seu perfil"},
                {"role": "user", "content": "Olá"},
            ],
            2600,
        )
        self.assertEqual(result["choices"][0]["message"]["content"], "Olá")
        self.assertEqual(result["model"], "gemini-3.1-flash-lite")
        self.assertIn(
            "/v1beta/models/gemini-3.1-flash-lite:generateContent", calls[1][0]
        )
        self.assertNotIn("/openai/", calls[1][0])
        self.assertEqual(calls[1][2]["x-goog-api-key"], KEY)
        self.assertEqual(
            calls[1][1]["systemInstruction"]["parts"][0]["text"], "Seu perfil"
        )

    def test_404_refreshes_catalog_once_and_tries_only_verified_text_families(self):
        cache = {}
        calls = []
        lists = 0

        def request(url, payload=None, headers=None, timeout=60):
            nonlocal lists
            calls.append(url)
            if ":generateContent" not in url:
                lists += 1
                return (
                    listing("gemini-2.5-flash-lite")
                    if lists == 1
                    else listing("gemini-3.1-flash-lite", "paid-pro-model")
                )
            if "gemini-2.5" in url:
                raise gemini_text.GeminiHTTPError(404, "modelo não encontrado")
            return answer()

        result = gemini_text.call(
            request, KEY, [{"role": "user", "content": "Oi"}], 512, cache=cache
        )
        self.assertEqual(result["model"], "gemini-3.1-flash-lite")
        self.assertEqual(lists, 2)
        self.assertFalse(any("paid-pro-model:" in url for url in calls))

    def test_quota_or_auth_failure_does_not_switch_models(self):
        for status in (403, 429):
            calls = []

            def request(url, payload=None, headers=None, timeout=60):
                calls.append(url)
                if ":generateContent" not in url:
                    return listing("gemini-3.1-flash-lite", "gemini-2.5-flash-lite")
                raise gemini_text.GeminiHTTPError(status, "quota ou permissão")

            with self.assertRaises(gemini_text.GeminiHTTPError):
                gemini_text.call(request, KEY, [{"role": "user", "content": "Oi"}], 512)
            self.assertEqual(len(calls), 2)

    def test_no_verified_model_rejects_paid_and_image_models_without_generating(self):
        with patch("gemini_text.discover", return_value=[]) as discover:
            with self.assertRaises(ValueError):
                gemini_text.call(
                    lambda *a, **k: self.fail("Não deve gerar"), KEY, [], 512
                )
            discover.assert_called_once()

    def test_quick_connection_saves_only_after_real_text_response(self):
        with patch.object(
            s.runtime,
            "gemini_request",
            side_effect=[listing("gemini-3.1-flash-lite"), answer()],
        ):
            result = s.runtime.connect_gemini(KEY, 0)
        self.assertEqual(result["model"], "gemini-3.1-flash-lite")
        self.assertEqual(s.runtime.key("GEMINI_API_KEY"), KEY)
        cfg, key = s.runtime.effective_text(0, {"mode": "demo"})
        self.assertEqual(cfg["model"], "auto-gemini-free")
        self.assertEqual(key, KEY)

    def test_failed_quick_connection_does_not_replace_saved_settings_or_key(self):
        s.runtime.store_key("GEMINI_API_KEY", "previous")
        with patch.object(
            s.runtime,
            "gemini_request",
            side_effect=[listing("gemini-3.1-flash-lite"), answer("")],
        ):
            with self.assertRaises(ValueError):
                s.runtime.connect_gemini("new-key", 0)
        self.assertEqual(s.runtime.key("GEMINI_API_KEY"), "previous")
        with s.db() as c:
            self.assertEqual(s.runtime.settings(c)["text_mode"], "legacy")

    def test_actual_generate_uses_discovered_native_model_and_returns_reply(self):
        cfg = {
            "mode": "api",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "auto-gemini-free",
            "max_tokens": 2600,
        }
        with (
            patch.object(s.runtime, "effective_text", return_value=(cfg, KEY)),
            patch.object(
                s.runtime,
                "gemini_request",
                side_effect=[
                    listing("gemini-3.1-flash-lite"),
                    answer(json.dumps({"reply": "Olá Lucas", "actions": []})),
                ],
            ),
        ):
            result = s.generate(0, "Olá")
        self.assertEqual(result["reply"], "Olá Lucas")

    def test_connection_proof_is_persistent_and_invalidated_when_key_changes(self):
        with patch.object(
            s.runtime,
            "gemini_request",
            side_effect=[listing("gemini-3.1-flash-lite"), answer()],
        ):
            s.runtime.connect_gemini(KEY, 0)
        self.assertTrue(s.runtime.text_status(0, {"mode": "demo"})["verified"])
        s.init_db()
        self.assertTrue(s.runtime.public_state()["general_connection"]["verified"])
        s.runtime.store_key("GEMINI_API_KEY", "replacement")
        self.assertFalse(s.runtime.text_status(0, {"mode": "demo"})["verified"])

    def test_team_connection_does_not_replace_specialist_or_mislabel_its_test(self):
        with s.db() as c:
            s.runtime.save_profile(
                c,
                {
                    "employee": 0,
                    "inherit": False,
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "openai/gpt-oss-20b",
                    "key_name": "GROQ_API_KEY",
                    "tools": [],
                },
            )
        s.runtime.store_key("GROQ_API_KEY", "specialist-test")
        with patch.object(
            s.runtime,
            "gemini_request",
            side_effect=[listing("gemini-3.1-flash-lite"), answer()],
        ):
            s.runtime.connect_gemini(KEY, None)
        self.assertEqual(
            s.runtime.effective_text(0, {"mode": "demo"})[1], "specialist-test"
        )
        self.assertFalse(s.runtime.text_status(0, {"mode": "demo"})["verified"])
        self.assertTrue(s.runtime.public_state()["general_connection"]["verified"])
        self.assertTrue(s.runtime.text_status(1, {"mode": "demo"})["verified"])
