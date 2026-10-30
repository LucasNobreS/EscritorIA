import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_server
import chat_models

s = test_server.s


class ChatModels(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()

    def tearDown(self):
        s.DATA = self.old
        self.temp.cleanup()

    def test_general_gemini_inheritance_and_specialist_key_are_independent(self):
        s.runtime.store_key("GEMINI_API_KEY", "gemini-test")
        s.runtime.store_key("GROQ_API_KEY", "groq-test")
        with s.db() as c:
            s.runtime.save_settings(
                c,
                {
                    "text_mode": "api",
                    "text_base_url": chat_models.GEMINI_BASE,
                    "text_model": chat_models.GEMINI_DEFAULT,
                    "text_key": "GEMINI_API_KEY",
                },
            )
            s.runtime.save_profile(
                c,
                {
                    "employee": 1,
                    "inherit": False,
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "openai/gpt-oss-20b",
                    "key_name": "GROQ_API_KEY",
                    "tools": ["code"],
                },
            )
        cfg, key = s.runtime.effective_text(0, {"mode": "demo"})
        self.assertEqual(key, "gemini-test")
        self.assertEqual(cfg["model"], chat_models.GEMINI_DEFAULT)
        cfg, key = s.runtime.effective_text(1, {"mode": "demo"})
        self.assertEqual(key, "groq-test")
        self.assertEqual(cfg["model"], "openai/gpt-oss-20b")
        s.runtime.free_text_guard(
            {"base_url": chat_models.GEMINI_BASE, "model": chat_models.GEMINI_DEFAULT}
        )
        s.init_db()
        self.assertEqual(
            s.runtime.effective_text(0, {"mode": "demo"})[1], "gemini-test"
        )

    def test_empty_reasoning_only_and_truncated_outputs_are_errors(self):
        for message in (
            {"content": None, "reasoning": "internal"},
            {"content": ""},
            {"content": "   "},
        ):
            with self.assertRaises(ValueError):
                chat_models.final_text({"choices": [{"message": message}]})
        with self.assertRaises(ValueError):
            chat_models.final_text(
                {
                    "choices": [
                        {"message": {"content": "partial"}, "finish_reason": "length"}
                    ]
                }
            )
        self.assertEqual(
            chat_models.final_text(
                {
                    "choices": [
                        {"message": {"content": [{"type": "text", "text": "Olá"}]}}
                    ]
                }
            ),
            "Olá",
        )

    def test_provider_payload_uses_groq_reasoning_parameters_only_for_supported_models(
        self,
    ):
        body = chat_models.payload(
            {
                "base_url": "https://api.groq.com/openai/v1",
                "model": "openai/gpt-oss-20b",
            },
            [],
        )
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["reasoning_format"], "hidden")
        self.assertIn("max_completion_tokens", body)
        body = chat_models.payload(
            {"base_url": chat_models.GEMINI_BASE, "model": chat_models.GEMINI_DEFAULT},
            [],
        )
        self.assertNotIn("reasoning_effort", body)
        self.assertIn("max_tokens", body)

    def test_empty_json_does_not_mark_task_as_delivered(self):
        with s.db() as c:
            tid = s.create_task(c, 0, "Olá")
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
            x, y = s.station_position(s.world_state(c)["layout"], 0)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=0", (x, y))

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "{}"}}]}
                ).encode()

        cfg = {
            "mode": "api",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "openai/gpt-oss-20b",
        }
        with (
            patch.object(s.runtime, "effective_text", return_value=(cfg, "test")),
            patch.object(s.urllib.request, "urlopen", return_value=Response()),
        ):
            s.process_task(task)
        with s.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
            self.assertEqual(task["status"], "pausada")
            self.assertIn("sem resposta", task["error"])
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM archives").fetchone()[0], 0
            )

    def test_config_status_does_not_expose_api_keys(self):
        s.runtime.store_key("GEMINI_API_KEY", "private-test")
        with s.db() as c:
            s.runtime.save_settings(c, {"text_mode": "api"})
        status = s.runtime.text_status(0, {"mode": "demo"})
        self.assertEqual(status["status"], "configured")
        self.assertNotIn("private-test", json.dumps(status))
