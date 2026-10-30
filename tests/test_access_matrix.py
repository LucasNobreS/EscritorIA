import copy
import json
import unittest
from unittest.mock import patch
import test_game
import access_matrix
from integrations import ConfigurationError

s = test_game.s


class AccessMatrix(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def rows(self):
        data = json.loads(self.raw("integrations"))
        return [
            {
                "employee": p["employee"],
                "expected": p["access_version"],
                "provider": "keep",
                "tools": p["tools"],
                "youtube": p["youtube_allowed"],
            }
            for p in data["profiles"]
        ]

    def test_batch_changes_providers_and_permissions_with_one_request(self):
        rows = self.rows()
        rows[0].update(provider="groq", tools=["board", "research"], youtube=False)
        rows[2].update(provider="general", tools=["board", "image"], youtube=False)
        self.post("integrations/access", {"rows": rows})
        s.init_db()
        with s.db() as c:
            manager = s.runtime.profile(c, 0)
            designer = s.runtime.profile(c, 2)
            self.assertEqual(manager["key_name"], "GROQ_API_KEY")
            self.assertFalse(manager["inherit"])
            self.assertFalse(manager["youtube_allowed"])
            self.assertTrue(designer["inherit"])
            self.assertIn("image", designer["tools"])

    def test_keep_preserves_custom_model_and_key(self):
        with s.db() as c:
            s.runtime.save_profile(
                c,
                {
                    "employee": 1,
                    "inherit": False,
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "custom-code-model",
                    "key_name": "CODER_API_KEY",
                    "tools": ["code"],
                    "max_tokens": 4000,
                },
            )
        rows = self.rows()
        row = next(r for r in rows if r["employee"] == 1)
        row["tools"].append("image")
        self.post("integrations/access", {"rows": rows})
        with s.db() as c:
            p = s.runtime.profile(c, 1)
            self.assertEqual(p["model"], "custom-code-model")
            self.assertEqual(p["key_name"], "CODER_API_KEY")
            self.assertEqual(p["max_tokens"], 4000)

    def test_invalid_or_stale_row_rolls_back_everyone(self):
        import urllib.error

        rows = self.rows()
        original = copy.deepcopy(rows)
        rows[0]["provider"] = "groq"
        rows[1]["expected"] = "stale"
        with self.assertRaises(urllib.error.HTTPError):
            self.post("integrations/access", {"rows": rows})
        self.assertEqual(self.rows(), original)
        rows = self.rows()
        rows[0]["youtube"] = True
        rows[0]["tools"] = []
        with self.assertRaises(urllib.error.HTTPError):
            self.post("integrations/access", {"rows": rows})
        rows = self.rows()
        rows.append(rows[0])
        with self.assertRaises(urllib.error.HTTPError):
            self.post("integrations/access", {"rows": rows})

    def test_youtube_revocation_prevents_api_call_but_radar_keeps_other_sources(self):
        rows = self.rows()
        row = next(r for r in rows if r["employee"] == 3)
        row["youtube"] = False
        self.post("integrations/access", {"rows": rows})
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "tools/job",
                {"employee": 3, "kind": "research", "params": {"mode": "youtube"}},
            )
        self.post(
            "tools/job",
            {"employee": 3, "kind": "research", "params": {"mode": "radar"}},
        )
        with (
            patch.object(
                s.runtime.radar, "youtube", side_effect=AssertionError("Not authorized")
            ),
            patch.object(s.runtime.research, "search", return_value={"items": []}),
        ):
            s.runtime.tick()
        jobs = json.loads(self.raw("integrations"))["jobs"]
        result = json.loads(jobs[0]["result"])
        self.assertEqual(jobs[0]["status"], "succeeded")
        self.assertEqual(result["sections"][1]["status"], "unavailable")
        self.assertIn("não tem acesso", result["sections"][1]["message"])

    def test_revoked_flux_permission_stops_previously_queued_generation(self):
        self.post(
            "integrations/settings", {"credentials": {"FREELLM_API_KEY": "test-token"}}
        )
        self.post(
            "tools/job",
            {"employee": 2, "kind": "image", "params": {"prompt": "Garden"}},
        )
        rows = self.rows()
        row = next(r for r in rows if r["employee"] == 2)
        row["tools"].remove("image")
        self.post("integrations/access", {"rows": rows})
        with patch("freellm_gateway.request", side_effect=AssertionError("Revoked")):
            s.runtime.tick()
        job = json.loads(self.raw("integrations"))["jobs"][0]
        self.assertEqual(job["status"], "failed")
        self.assertIn("revogada", job["error"])
