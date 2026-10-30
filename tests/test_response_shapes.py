import unittest
import test_server
import chat_models
from unittest.mock import patch

s = test_server.s


class ResponseShapes(unittest.TestCase):
    def test_malformed_provider_choices_have_clear_errors(self):
        for result in [
            {"choices": [None]},
            {"choices": ["bad"]},
            {"choices": [{"message": "bad"}]},
        ]:
            with self.assertRaises(ValueError):
                chat_models.final_text(result)

    def test_project_array_is_not_treated_as_completed(self):
        cfg = {
            "mode": "api",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "test",
        }
        with (
            patch.object(s.runtime, "effective_text", return_value=(cfg, "test")),
            patch.object(
                s,
                "build_context",
                return_value=(
                    [],
                    {
                        "name": "Theo",
                        "role": "Desenvolvedor",
                        "revision": 1,
                        "manager": 0,
                    },
                    [],
                ),
            ),
            patch.object(
                s.runtime,
                "text_request",
                return_value={"choices": [{"message": {"content": "[]"}}]},
            ),
            patch.object(s.runtime, "record_text_check"),
        ):
            with self.assertRaisesRegex(ValueError, "objeto JSON"):
                s.generate(1, "Projeto", {"id": -1, "root": -1, "intent": "project"})
