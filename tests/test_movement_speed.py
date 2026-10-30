import math
import unittest
import urllib.error
from unittest.mock import patch
import test_game

s = test_game.s


class MovementSpeed(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def test_shared_speed_persists_and_rejects_invalid_values(self):
        self.assertEqual(self.state()["world"]["preferences"]["movementSpeed"], 1)
        self.post("world/preferences", {"movementSpeed": 1.5})
        s.init_db()
        self.assertEqual(self.state()["world"]["preferences"]["movementSpeed"], 1.5)
        for value in (0, 3, -1, True, "2", None):
            with self.assertRaises(urllib.error.HTTPError):
                self.post("world/preferences", {"movementSpeed": value})
        self.assertEqual(self.state()["world"]["preferences"]["movementSpeed"], 1.5)

    def test_staff_speed_uses_budget_across_waypoints_without_overshoot(self):
        for mult, expected in [(1, 9), (1.5, 13.5), (2, 18)]:
            self.post("world/preferences", {"movementSpeed": mult})
            with s.db() as c:
                c.execute("UPDATE employees SET active=0 WHERE id<>0")
                c.execute(
                    "UPDATE employees SET x=690,y=730,destination='ponto:750:730' WHERE id=0"
                )
            with patch.object(
                s, "route", return_value=[(695, 730), (700, 730), (750, 730)]
            ):
                s.navigation_tick({}, {})
            with s.db() as c:
                row = c.execute("SELECT x,y FROM employees WHERE id=0").fetchone()
                self.assertAlmostEqual(row["x"] - 690, expected)
                self.assertEqual(row["y"], 730)
        with s.db() as c:
            c.execute(
                "UPDATE employees SET x=748,y=730,destination='ponto:750:730' WHERE id=0"
            )
        with patch.object(s, "route", return_value=[(750, 730)]):
            s.navigation_tick({}, {})
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT x FROM employees WHERE id=0").fetchone()[0], 750
            )
