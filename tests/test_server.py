import importlib.util
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
import json
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str((Path(__file__).parents[1] / "app")))
spec = importlib.util.spec_from_file_location(
    "office", (Path(__file__).parents[1] / "app") / "server.py"
)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = s.DATA
        s.DATA = Path(self.tmp.name)
        s.init_db()
        s.paused = False
        self.server = s.ThreadingHTTPServer(("127.0.0.1", 0), s.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        s.DATA = self.original
        self.tmp.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(
            self.url + "/api/" + path,
            data=json.dumps(body).encode(),
            headers={"X-Office-Token": s.TOKEN},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def state(self):
        with urllib.request.urlopen(self.url + "/api/state") as r:
            return json.load(r)

    def task(self, tid):
        with s.db() as c:
            return dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def test_auth_and_queue(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(
                urllib.request.Request(
                    self.url + "/api/task", data=b"{}", method="POST"
                )
            )
        self.assertEqual(e.exception.code, 403)
        self.post("task", {"employee": 1, "title": "Criar página"})
        data = self.state()
        self.assertEqual(data["tasks"][0]["status"], "fila")
        self.assertEqual(data["messages"][0]["employee"], 1)

    def test_profile_edits_and_board_are_in_model_context(self):
        e = self.state()["employees"][1]
        e.update(
            name="Theo Novo",
            role="Engenheiro Python",
            context="Automação para logística",
            background="Formação de personagem em ADS",
            skills="Python, SQLite",
            expectations="Entregas com testes",
            manager=False,
        )
        self.post("employee", e)
        self.post(
            "note", {"title": "Prioridade", "content": "Projetar módulo de estoque"}
        )
        messages, profile, notes = s.build_context(0, "Planeje")
        self.assertIn("Theo Novo", messages[0]["content"])
        self.assertIn("Automação para logística", messages[0]["content"])
        self.assertIn("Projetar módulo de estoque", messages[0]["content"])
        self.assertEqual(self.state()["employees"][1]["revision"], 2)
        self.post("task", {"employee": 1, "title": "Leia o quadro"})
        with patch.object(s, "config", return_value={"mode": "demo"}):
            s.process_task(self.task(1))
        t = self.task(1)
        self.assertEqual(t["revision_used"], 2)
        self.assertIn("Projetar módulo", t["board_seen"])

    def test_hire_capacity_and_profile_persistence(self):
        for i in range(3):
            self.post(
                "employee",
                {
                    "name": f"Nova {i}",
                    "role": "Analista",
                    "context": "Analisar requisitos",
                    "color": "#abcdef",
                    "manager": False,
                },
            )
        self.assertEqual(len(self.state()["employees"]), 8)
        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "employee",
                {"name": "Excesso", "role": "Analista", "context": "Contexto"},
            )
        s.init_db()
        self.assertEqual(len(self.state()["employees"]), 8)

    def test_manager_delegation_delivery_and_consolidation(self):
        self.post(
            "task", {"employee": 0, "title": "Crie uma campanha", "intent": "project"}
        )

        def fake(emp, text, task=None):
            if task["id"] == 1:
                return {
                    "reply": "Vou pedir o texto ao marketing.",
                    "actions": [
                        {
                            "type": "delegate",
                            "employee_id": 3,
                            "task": "Crie o texto da campanha",
                        }
                    ],
                }
            return {
                "reply": "Entrega consolidada"
                if task["kind"] == "review"
                else "Texto da campanha",
                "actions": [],
            }

        with patch.object(s, "generate", side_effect=fake):
            s.process_task(self.task(1))
            self.assertEqual(self.task(2)["employee"], 3)
            s.process_task(self.task(2))
            self.assertEqual(self.task(3)["kind"], "review")
            s.process_task(self.task(3))
        data = self.state()
        self.assertEqual(len(data["tasks"]), 3)
        self.assertEqual(data["tasks"][0]["status"], "concluida")
        self.assertTrue(
            any("Texto da campanha" in m["content"] for m in data["staff_messages"])
        )

    def test_nonmanager_cannot_delegate_and_work_requires_desk(self):
        self.post("task", {"employee": 1, "title": "Teste"})
        with s.db() as c:
            s.apply_actions(
                c,
                1,
                self.task(1),
                [{"type": "delegate", "employee_id": 2, "task": "Indevida"}],
            )
            c.execute("UPDATE employees SET x=1190,y=665,destination='copa' WHERE id=1")
        with patch.object(s, "generate") as gen:
            self.assertFalse(s.process_task(self.task(1)))
            gen.assert_not_called()
        self.assertEqual(self.task(1)["status"], "indo_mesa")
        self.assertEqual(len(self.state()["tasks"]), 1)

    def test_navigation_avoids_obstacles_and_ai_can_choose_floor_point(self):
        for target in s.DESKS + list(s.DESTINATIONS.values()):
            route = s.route(1190, 665, *target)
            self.assertTrue(route, target)
            for x, y in route:
                self.assertFalse(s.blocked(x, y), (x, y))
        self.post("task", {"employee": 0, "title": "Andar"})
        with s.db() as c:
            s.apply_actions(c, 0, self.task(1), [{"type": "move", "x": 900, "y": 740}])
        self.assertEqual(
            self.state()["employees"][0]["destination"], "ponto:900.0:740.0"
        )

    def test_api_adapter_sends_actual_context_and_parses_actions(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "reply": "Olá",
                                            "actions": [
                                                {"type": "move", "destination": "copa"}
                                            ],
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode()

        cfg = {
            "mode": "api",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "test",
        }
        with (
            patch.object(s, "config", return_value=cfg),
            patch.dict(s.os.environ, {"OFFICE_API_KEY": "test-key"}),
            patch.object(s.urllib.request, "urlopen", return_value=Response()) as call,
        ):
            result = s.generate(0, "Conheça a equipe")
            payload = json.loads(call.call_args.args[0].data)
        self.assertEqual(result["actions"][0]["destination"], "copa")
        self.assertIn("equipe", payload["messages"][0]["content"])
        self.assertIn("Gerente", payload["messages"][0]["content"])

    def test_collaboration_budget(self):
        with s.db() as c:
            parent = s.create_task(c, 0, "Raiz")
            for i in range(3):
                parent = s.create_task(c, 1, "Consulta", parent)
            with self.assertRaises(ValueError):
                s.create_task(c, 2, "Excesso", parent)
