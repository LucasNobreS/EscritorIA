import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_server
import customization
from integrations import ConfigurationError

s = test_server.s


class Customization(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()

    def tearDown(self):
        s.DATA = self.old
        self.temp.cleanup()

    def test_every_catalog_object_has_real_supported_actions(self):
        self.assertEqual(set(s.CATALOG), set(customization.ACTIONS))
        with s.db() as c:
            layout = s.default_layout()
            for kind in s.CATALOG:
                item = {
                    "id": "test-" + kind,
                    "kind": kind,
                    "x": 100,
                    "y": 100,
                    "rotation": 0,
                    "color": "#aabbcc",
                }
                result = customization.interact(c, layout + [item], item["id"])
                self.assertTrue(result["actions"])
                for action in result["actions"]:
                    out = customization.interact(
                        c, layout + [item], item["id"], action["id"], "Nossa equipe"
                    )
                    self.assertIn("message", out)
            self.assertLessEqual(
                c.execute("SELECT COUNT(*) FROM object_history").fetchone()[0], 300
            )

    def test_preferences_and_object_actions_survive_restart(self):
        with s.db() as c:
            customization.save_preferences(
                c,
                {
                    "name": "Lucas Studio",
                    "floor": "#112233",
                    "wall": "#aabbcc",
                    "accent": "#334455",
                    "lighting": "night",
                    "floorPattern": "tiles",
                },
            )
            layout = s.world_state(c)["layout"]
            plant = next(i for i in layout if i["kind"] == "plant")
            customization.interact(c, layout, plant["id"], "water")
        s.init_db()
        with s.db() as c:
            world = s.world_state(c)
            self.assertEqual(world["preferences"]["name"], "Lucas Studio")
            self.assertEqual(world["objectStates"][plant["id"]]["waterCount"], 1)

    def test_skin_combinations_are_available_for_every_gender(self):
        for gender in ("woman", "man", "nonbinary", "unspecified"):
            for outfit in (
                "hoodie",
                "dress",
                "blazer",
                "vest",
                "coat",
                "polo",
                "overalls",
            ):
                out = s.clean_skin(
                    {
                        "gender": gender,
                        "outfit": outfit,
                        "body": "broad",
                        "hairStyle": "braids",
                        "beard": "moustache",
                        "accessory": "headphones",
                        "bottom": "skirt",
                        "pattern": "dots",
                        "accent": "#11aa22",
                    }
                )
                self.assertEqual(out["gender"], gender)
                self.assertEqual(out["outfit"], outfit)
        self.assertEqual(s.clean_skin({"outfit": "suit"})["gender"], "unspecified")

    def test_invalid_preferences_and_object_actions_are_rejected(self):
        with s.db() as c:
            for params in ({"floor": "red"}, {"lighting": "laser"}, {"name": ""}):
                with self.assertRaises(ValueError):
                    customization.save_preferences(c, params)
            with self.assertRaises(ValueError):
                customization.interact(c, s.default_layout(), "plant-0", "publish")
        with self.assertRaises(ValueError):
            s.clean_skin({"body": "invalid"})

    def test_furniture_labels_and_finishes_persist_in_layout(self):
        layout = s.default_layout()
        layout[0].update(label="Mesa da Helena", variant="striped")
        new = s.validate_layout(layout)
        self.assertEqual(new[0]["label"], "Mesa da Helena")
        self.assertEqual(new[0]["variant"], "striped")
        layout[0]["variant"] = "unknown"
        with self.assertRaises(ValueError):
            s.validate_layout(layout)

    def test_free_text_gate_and_paid_media_never_make_requests(self):
        runtime = s.runtime
        for cfg in [
            {
                "base_url": "https://api.groq.com/openai/v1",
                "model": "openai/gpt-oss-20b",
            },
            {"base_url": "https://openrouter.ai/api/v1", "model": "openrouter/free"},
            {"base_url": "https://openrouter.ai/api/v1", "model": "any/model:free"},
        ]:
            runtime.free_text_guard(cfg)
        for cfg in [
            {"base_url": "https://openrouter.ai/api/v1", "model": "openrouter/auto"},
            {"base_url": "http://other-host:3001/v1", "model": "auto"},
            {"base_url": "https://paid.example/v1", "model": "free"},
        ]:
            with self.assertRaises(ConfigurationError):
                runtime.free_text_guard(cfg)
        with patch.object(runtime, "request") as request:
            with self.assertRaises(ConfigurationError):
                runtime.image({"id": -1}, {})
            with self.assertRaises(ConfigurationError):
                runtime.video({}, {})
            request.assert_not_called()

    def test_employee_object_tool_updates_persistent_state(self):
        with s.db() as c:
            tid = s.create_task(c, 0, "Regar planta")
            t = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
        result = s.runtime.office(
            {"kind": "objects", "employee": 0, "task": tid, "root": t["root"]},
            {"object_id": "plant-0", "operation": "water"},
        )
        self.assertEqual(result["state"]["waterCount"], 1)
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT actor FROM object_history").fetchone()[0], "0"
            )

    def test_visual_mode_changes_only_render_preferences(self):
        with s.db() as c:
            before = s.world_state(c)
            customization.save_preferences(c, {"graphicsMode": "smooth", "sound": True})
            after = s.world_state(c)
            for key in ("layout", "player", "walls", "zones"):
                self.assertEqual(before[key], after[key])
            self.assertEqual(after["preferences"]["graphicsMode"], "smooth")
            with self.assertRaises(ValueError):
                customization.save_preferences(c, {"graphicsMode": "3d"})
        s.init_db()
        with s.db() as c:
            self.assertEqual(s.world_state(c)["preferences"]["graphicsMode"], "smooth")

    def test_new_body_and_clothes_persist_for_employee_and_player(self):
        for body in ("feminine", "masculine", "neutral", "auto"):
            skin = s.clean_skin(
                {
                    "bodyType": body,
                    "gender": "woman",
                    "hairStyle": "twintails",
                    "outfit": "cardigan",
                    "accessory": "backpack",
                    "pattern": "checks",
                }
            )
            self.assertEqual(skin["bodyType"], body)
