import unittest
from unittest.mock import patch
import test_server
import delegation

s = test_server.s


class ManagerDelegation(unittest.TestCase):
    setUp = test_server.Integration.setUp
    tearDown = test_server.Integration.tearDown
    post = test_server.Integration.post
    state = test_server.Integration.state

    def task(self):
        with s.db() as c:
            tid = s.create_task(c, 0, "Planeje uma aula de história")
            x, y = s.station_position(s.world_state(c)["layout"], 0)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=0", (x, y))
            c.execute(
                "UPDATE employees SET role='Professor de história',context='Preparar aulas para adultos' WHERE id=1"
            )
            return dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def test_manager_corrects_self_execution_before_commit(self):
        task = self.task()
        wrong = {
            "reply": "Fiz tudo",
            "files": [{"filename": "aula.md", "content": "Prematuro"}],
            "actions": [],
        }
        plan = {
            "reply": "Distribuí o planejamento ao professor",
            "files": [],
            "actions": [
                {
                    "type": "delegate",
                    "employee_id": 1,
                    "task": "Prepare uma aula de história para adultos com fontes e exercícios.",
                }
            ],
        }
        with patch.object(s, "generate", side_effect=[wrong, plan]) as model:
            s.process_task(task)
        self.assertEqual(model.call_count, 2)
        with s.db() as c:
            child = c.execute(
                "SELECT * FROM tasks WHERE parent=? AND kind='delegated'", (task["id"],)
            ).fetchone()
            self.assertEqual(child["employee"], 1)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM task_files").fetchone()[0], 0
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0
            )
        # A real child result creates exactly one manager review.
        with s.db() as c:
            x, y = s.station_position(s.world_state(c)["layout"], 1)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=1", (x, y))
        with patch.object(
            s,
            "generate",
            return_value={
                "reply": "Plano preparado",
                "actions": [],
                "files": [{"filename": "aula.md", "content": "Plano de aula"}],
            },
        ):
            s.process_task(dict(child))
        with s.db() as c:
            self.assertEqual(
                c.execute(
                    "SELECT COUNT(*) FROM tasks WHERE kind='review' AND employee=0"
                ).fetchone()[0],
                1,
            )

    def test_persistent_refusal_does_not_deliver_or_run_tools(self):
        task = self.task()
        with patch.object(
            s,
            "generate",
            return_value={"reply": "Fiz tudo", "actions": [], "files": []},
        ):
            s.process_task(task)
        with s.db() as c:
            self.assertEqual(
                c.execute(
                    "SELECT status FROM tasks WHERE id=?", (task["id"],)
                ).fetchone()[0],
                "pausada",
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0
            )

    def test_arbitrary_profession_and_last_manager_protection(self):
        body = dict(self.state()["employees"][1])
        body.update(
            role="Curador de museu",
            context="Catalogar acervos e elaborar exposições",
            manager=False,
        )
        self.post("employee", body)
        self.assertEqual(self.state()["employees"][1]["role"], "Curador de museu")
        manager = dict(self.state()["employees"][0])
        manager["manager"] = False
        with self.assertRaises(Exception):
            self.post("employee", manager)
        with self.assertRaises(Exception):
            self.post("employee/archive", {"id": 0})
        self.post("employee/archive", {"id": 1})
        self.assertEqual(len(self.state()["employees"]), 4)
        body.pop("id")
        body["name"] = "Novo curador"
        self.post("employee", body)
        self.assertEqual(len(self.state()["employees"]), 5)

    def test_coordinator_authority_is_not_derived_from_title(self):
        self.assertTrue(
            delegation.is_planning(
                {"manager": 1}, {"intent": "project", "kind": "task", "parent": None}
            )
        )
        self.assertFalse(
            delegation.is_planning({"manager": 1}, {"intent": "chat", "kind": "task"})
        )
        self.assertFalse(
            delegation.is_planning(
                {"manager": 1}, {"intent": "project", "kind": "review", "parent": 1}
            )
        )
        self.assertIsNotNone(
            delegation.validate_plan(
                {
                    "actions": [
                        {"type": "delegate", "employee_id": 0, "task": "eu faço"}
                    ]
                },
                [{"id": 1}],
            )
        )
