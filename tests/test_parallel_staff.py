import threading
import unittest
from unittest.mock import patch
import test_server
import text_budget

s = test_server.s


class ParallelStaff(unittest.TestCase):
    setUp = test_server.Integration.setUp
    tearDown = test_server.Integration.tearDown

    def task(self, employee):
        with s.db() as c:
            tid = s.create_task(c, employee, "Trabalho")
            x, y = s.station_position(s.world_state(c)["layout"], employee)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=?", (x, y, employee))
            return dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def test_two_staff_generate_concurrently(self):
        tasks = [self.task(1), self.task(2)]
        barrier = threading.Barrier(2)

        def generate(*args):
            barrier.wait(3)
            return {"reply": "Feito", "actions": []}

        with patch.object(s, "generate", side_effect=generate):
            threads = [
                threading.Thread(target=s.process_task, args=(t,)) for t in tasks
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)
                self.assertFalse(t.is_alive())
        with s.db() as c:
            self.assertEqual(
                c.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status='concluida'"
                ).fetchone()[0],
                2,
            )

    def test_same_task_is_claimed_only_once(self):
        task = self.task(1)
        entered = threading.Event()
        release = threading.Event()

        def generate(*args):
            entered.set()
            release.wait(3)
            return {"reply": "Feito", "actions": []}

        with patch.object(s, "generate", side_effect=generate) as call:
            worker = threading.Thread(target=s.process_task, args=(task,))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertFalse(s.process_task(task))
            finally:
                release.set()
                worker.join(4)
            self.assertEqual(call.call_count, 1)

    def test_queue_allows_two_and_holds_third(self):
        q = text_budget.RequestQueue(2)
        q.acquire()
        q.acquire()
        entered = threading.Event()

        def third():
            with q:
                entered.set()

        thread = threading.Thread(target=third)
        thread.start()
        self.assertFalse(entered.wait(0.05))
        q.release()
        self.assertTrue(entered.wait(2))
        thread.join(2)
        q.release()
