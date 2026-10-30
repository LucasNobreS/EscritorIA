import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_server
import freellm_gateway
import chat_models

s = test_server.s


class OutputRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()
        self.cfg = {
            "mode": "api",
            "base_url": freellm_gateway.BASE,
            "model": "auto",
            "max_tokens": 0,
        }
        self.messages = [{"role": "user", "content": "Crie um arquivo completo"}]

    def tearDown(self):
        s.DATA = self.old
        self.temp.cleanup()

    def answer(self, reason="stop", content="completo"):
        return {"choices": [{"finish_reason": reason, "message": {"content": content}}]}

    def test_provider_managed_payload_and_large_recovery_caps(self):
        self.assertNotIn(
            "max_tokens", freellm_gateway.payload(self.messages, "auto", 0)
        )
        for size in (500, 2400, 32768, 65536):
            self.assertEqual(
                freellm_gateway.payload(self.messages, "auto", size)["max_tokens"], size
            )

    def test_full_regeneration_discards_partial_and_counts_calls(self):
        with patch.object(
            s.runtime,
            "_text_request",
            side_effect=[self.answer("length", "arquivo cortado"), self.answer()],
        ) as request:
            result = s.runtime.text_request(self.cfg, "test", self.messages)
        self.assertEqual(chat_models.final_text(result), "completo")
        self.assertEqual(request.call_count, 2)
        self.assertEqual([c.args[3] for c in request.call_args_list], [0, 32768])
        self.assertNotIn("arquivo cortado", str(request.call_args_list[1].args[2]))
        self.assertEqual(s.runtime.text_budget.status()["requests"], 2)

    def test_three_attempts_then_reject_incomplete_output(self):
        with patch.object(
            s.runtime,
            "_text_request",
            side_effect=[self.answer("length") for _ in range(3)],
        ) as request:
            result = s.runtime.text_request(self.cfg, "test", self.messages)
        self.assertEqual([c.args[3] for c in request.call_args_list], [0, 32768, 65536])
        with self.assertRaises(ValueError):
            chat_models.final_text(result)

    def test_third_attempt_can_complete(self):
        with patch.object(
            s.runtime,
            "_text_request",
            side_effect=[self.answer("length"), self.answer("length"), self.answer()],
        ):
            result = s.runtime.text_request(self.cfg, "test", self.messages)
        self.assertEqual(chat_models.final_text(result), "completo")

    def test_explicit_browser_limit_does_not_expand(self):
        with patch.object(
            s.runtime, "_text_request", return_value=self.answer("length")
        ) as request:
            s.runtime.text_request(self.cfg, "test", self.messages, limit=2400)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[3], 2400)

    def test_non_gateway_keeps_existing_limit(self):
        cfg = {
            "mode": "api",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "openai/gpt-oss-20b",
            "max_tokens": 2600,
        }
        with patch.object(
            s.runtime, "_text_request", return_value=self.answer("length")
        ) as request:
            s.runtime.text_request(cfg, "test", self.messages)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[3], 2600)

    def test_legacy_gateway_default_no_longer_imposes_2600(self):
        with patch.object(
            s.runtime, "_text_request", return_value=self.answer()
        ) as request:
            s.runtime.text_request(
                dict(self.cfg, max_tokens=2600), "test", self.messages
            )
        self.assertEqual(request.call_args.args[3], 0)

    def test_hard_provider_error_is_not_retried(self):
        with patch.object(
            s.runtime,
            "_text_request",
            side_effect=ValueError("HTTP 401 chave inválida"),
        ) as request:
            with self.assertRaises(ValueError):
                s.runtime.text_request(self.cfg, "test", self.messages)
        self.assertEqual(request.call_count, 1)

    def test_restart_migrates_old_default_without_removing_key(self):
        s.runtime.store_key(freellm_gateway.KEY, "test-preserved-key")
        with s.db() as c:
            s.runtime.save_settings(
                c,
                {
                    "text_mode": "api",
                    "text_base_url": freellm_gateway.BASE,
                    "text_model": "auto",
                    "text_key": freellm_gateway.KEY,
                    "text_max_tokens": "2600",
                },
            )
        s.runtime.recover()
        self.assertEqual(s.runtime.settings()["text_max_tokens"], "0")
        self.assertEqual(s.runtime.key(freellm_gateway.KEY), "test-preserved-key")

    def test_all_truncated_task_never_creates_archive_or_applies_actions(self):
        with s.db() as c:
            tid = s.create_task(c, 1, "Criar página completa")
            x, y = s.station_position(s.world_state(c)["layout"], 1)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=1", (x, y))
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
        partial = self.answer(
            "length",
            '{"reply":"incompleto","files":[{"filename":"index.html","content":"<html>',
        )
        with (
            patch.object(s.runtime, "effective_text", return_value=(self.cfg, "test")),
            patch.object(
                s.runtime, "_text_request", side_effect=[partial, partial, partial]
            ),
            patch.object(s, "apply_actions") as actions,
        ):
            s.process_task(task)
        actions.assert_not_called()
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0],
                "pausada",
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM archives").fetchone()[0], 0
            )
