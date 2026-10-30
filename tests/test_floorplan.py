import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
import test_server
import test_game
import floorplan

s = test_server.s


class FloorplanValidation(unittest.TestCase):
    def test_invalid_dimensions_and_overlap(self):
        r = dict(id="a", name="Reuniões", x=980, y=70, w=380, h=370, door="south")
        for change in [
            dict(w=100),
            dict(x=float("nan")),
            dict(x=1800),
            dict(door="bad"),
        ]:
            with self.assertRaises(ValueError):
                floorplan.validate([{**r, **change}])
        with self.assertRaises(ValueError):
            floorplan.validate([r, {**r, "id": "b"}])

    def test_moving_resizing_geometry_is_isolated(self):
        r = dict(id="a", name="Reuniões", x=980, y=70, w=380, h=370, door="south")
        walls, zones = floorplan.geometry([r], [], [])
        layout = s.validate_layout(s.default_layout(), walls, zones, [r])
        self.assertTrue(s.blocked(980, 100, layout))
        self.assertFalse(s.blocked(1170, 432, layout))
        for e in range(8):
            self.assertTrue(s.route(690, 730, *s.station_position(layout, e), layout))
        # Expanding the meeting room remains valid; the original wall list is unchanged.
        changed = {**r, "h": 400}
        w2, z2 = floorplan.geometry([changed], [], [])
        s.validate_layout(s.default_layout(), w2, z2, [changed])
        self.assertNotEqual(walls, w2)
        self.assertTrue(s.blocked(960, 100, s.default_layout()))


class FloorplanPersistence(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state


def save_restart(self):
    world = self.state()["world"]
    self.post("pause", {})
    r = dict(id="meeting", name="Reuniões", x=980, y=70, w=380, h=370, door="south")
    self.post(
        "layout", dict(revision=world["revision"], layout=world["layout"], rooms=[r])
    )
    s.init_db()
    world = self.state()["world"]
    self.assertEqual(world["rooms"], [r])
    with s.db() as c:
        layout = s.world_state(c)["layout"]
        self.assertTrue(s.blocked(980, 100, layout))
    with self.assertRaises(urllib.error.HTTPError):
        self.post(
            "layout",
            dict(revision=world["revision"] - 1, layout=world["layout"], rooms=[]),
        )
    with self.assertRaises(urllib.error.HTTPError):
        self.post(
            "layout",
            dict(
                revision=world["revision"],
                layout=world["layout"],
                rooms=[{**r, "x": 200}],
            ),
        )
    self.assertEqual(self.state()["world"]["rooms"], [r])
    self.post(
        "layout", dict(revision=world["revision"], layout=world["layout"], rooms=None)
    )
    self.assertIsNone(self.state()["world"]["rooms"])


FloorplanPersistence.test_save_restart_reject_and_restore = save_restart


class OutlineTests(unittest.TestCase):
    def test_presets_have_reachable_exit_and_leave_cutouts_unwalkable(self):
        for shape, w, h in [
            ("rectangle", 2000, 1100),
            ("l", 3000, 1600),
            ("t", 3000, 1600),
        ]:
            o = floorplan.validate_outline(dict(shape=shape, width=w, height=h))
            walls, zones = floorplan.geometry([], [], [], o)
            layout = s.validate_layout(s.default_layout(), walls, zones, [], o)
            self.assertEqual(layout.exit, (650, h - 12))
            self.assertTrue(s.route(690, 730, *layout.exit, layout))
            if shape == "l":
                self.assertTrue(s.blocked(2500, 100, layout))
            if shape == "t":
                self.assertTrue(s.blocked(2500, 1400, layout))

    def test_shrink_does_not_silently_drop_furniture(self):
        o = floorplan.validate_outline(dict(shape="rectangle", width=1000, height=850))
        walls, zones = floorplan.geometry([], [], [], o)
        with self.assertRaises(ValueError):
            s.validate_layout(s.default_layout(), walls, zones, [], o)

    def test_invalid_outlines_and_room_in_cutout(self):
        for value in [
            dict(width=999),
            dict(height=1801),
            dict(width=float("inf")),
            dict(shape="unknown"),
        ]:
            with self.assertRaises(ValueError):
                floorplan.validate_outline(value)
        with self.assertRaises(ValueError):
            floorplan.validate(
                [dict(id="r", name="Sala", x=2300, y=70, w=300, h=300, door="south")],
                dict(shape="l", width=3000, height=1600),
            )


def outline_roundtrip(self):
    self.post("pause", {})
    world = self.state()["world"]
    body = dict(
        revision=world["revision"],
        rooms=[],
        layout=world["layout"],
        outline=dict(shape="l", width=3000, height=1600),
    )
    self.post("layout/validate", body)
    self.assertEqual(self.state()["world"]["revision"], world["revision"])
    self.assertIsNone(self.state()["world"]["outline"])
    self.post("layout", body)
    s.init_db()
    world = self.state()["world"]
    self.assertEqual(world["outline"], body["outline"])
    self.assertEqual(world["exit"], [650, 1588])
    self.assertEqual(world["width"], 3070)
    with s.db() as c:
        layout = s.world_state(c)["layout"]
        self.assertTrue(s.route(690, 730, *layout.exit, layout))


FloorplanPersistence.test_outline_validation_is_readonly_and_saved_shape_survives_restart = outline_roundtrip
