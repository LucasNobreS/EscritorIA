import base64
import json
import unittest
from unittest.mock import patch
import test_integrations
import test_game
from integrations import ConfigurationError

s = test_integrations.s


class UnifiedImages(unittest.TestCase):
    setUp = test_integrations.Integrations.setUp
    tearDown = test_integrations.Integrations.tearDown
    task = test_integrations.Integrations.task

    def test_legacy_provider_migrates_and_preserves_credentials(self):
        self.r.store_key("CLOUDFLARE_API_TOKEN", "legacy-private")
        self.r.store_key("FREELLM_API_KEY", "unified-private")
        t = self.task(2)
        with s.db() as c:
            c.execute(
                "UPDATE integration_settings SET data=?",
                (json.dumps({"image_provider": "cloudflare"}),),
            )
            self.assertEqual(self.r.settings(c)["image_provider"], "freellm")
            jid = self.r.enqueue(c, 2, t, "image", {"prompt": "A garden"})
        response = {
            "data": [{"b64_json": base64.b64encode(test_integrations.PNG).decode()}],
            "model": "cloudflare-image",
        }
        with patch("freellm_gateway.request", return_value=response) as request:
            self.r.tick()
        self.assertEqual(request.call_args.args[1], "unified-private")
        self.assertEqual(request.call_args.args[2], "/images/generations")
        with s.db() as c:
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            )
            self.assertEqual(job["status"], "succeeded")
            with patch(
                "freellm_gateway.request", side_effect=AssertionError("Duplicate")
            ):
                self.r.image(job, {"prompt": "A garden"})
        self.assertEqual(self.r.key("CLOUDFLARE_API_TOKEN"), "legacy-private")
        self.assertNotIn("legacy-private", json.dumps(self.r.public_state()))

    def test_requires_unified_key(self):
        t = self.task(2)
        with s.db() as c:
            with self.assertRaises(ConfigurationError):
                self.r.enqueue(c, 2, t, "image", {"prompt": "A garden"})


class FirstAccess(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def test_flag_survives_database_reinitialization(self):
        with s.db() as c:
            self.assertFalse(s.world_state(c)["preferences"]["welcomeSeen"])
        self.post("world/preferences", {"welcomeSeen": True})
        s.init_db()
        with s.db() as c:
            self.assertTrue(s.world_state(c)["preferences"]["welcomeSeen"])

    def test_existing_installation_skips_welcome_and_keeps_preferences(self):
        with s.db() as c:
            c.execute(
                "UPDATE office_preferences SET data=?",
                (json.dumps({"name": "Meu escritório", "movementSpeed": 2}),),
            )
        s.init_db()
        with s.db() as c:
            prefs = s.world_state(c)["preferences"]
            self.assertTrue(prefs["welcomeSeen"])
            self.assertEqual(prefs["name"], "Meu escritório")
            self.assertEqual(prefs["movementSpeed"], 2)
