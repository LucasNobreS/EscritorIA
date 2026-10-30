import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str((Path(__file__).parents[1] / "app")))
import work_policy
import freellm_gateway
import text_budget


class WorkPolicy(unittest.TestCase):
    def test_activity_routing_preserves_explicit_choices(self):
        cfg = {"base_url": freellm_gateway.BASE, "model": "auto"}
        for kind, model in [
            ("chat", "auto:reliable"),
            ("project", "auto:smart"),
            ("browser", "auto:fast"),
        ]:
            self.assertEqual(work_policy.route(cfg, kind)["model"], model)
        self.assertEqual(
            work_policy.route(cfg, "project", True)["model"], "auto:reliable"
        )
        self.assertEqual(cfg["model"], "auto")
        explicit = dict(cfg, model="auto:fast")
        self.assertEqual(work_policy.route(explicit, "project"), explicit)
        remote = {"base_url": "https://example.com/v1", "model": "auto"}
        self.assertEqual(work_policy.route(remote, "project"), remote)

    def test_fifo_and_background_admission(self):
        q = text_budget.RequestQueue()
        order = []
        q.acquire()
        threads = []

        def run(i):
            with q:
                order.append(i)

        for i in range(5):
            thread = threading.Thread(target=run, args=(i,))
            thread.start()
            threads.append(thread)
            deadline = time.monotonic() + 2
            while True:
                with q.condition:
                    count = len(q.waiting)
                if count == i + 1:
                    break
                if time.monotonic() > deadline:
                    self.fail("Thread não entrou na fila")
                time.sleep(0.001)
        self.assertFalse(q.acquire(False))
        q.release()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(order, list(range(5)))
        self.assertTrue(q.acquire(False))
        q.release()

    def test_exceptions_release_slot(self):
        q = text_budget.RequestQueue()
        with self.assertRaises(ValueError):
            with q:
                raise ValueError("teste")
        self.assertTrue(q.acquire(False))
        q.release()
