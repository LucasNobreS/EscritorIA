import json
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import test_server
import failure_center as f

s = test_server.s


class FailureCenter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()
        s.paused = False

    def tearDown(self):
        s.DATA = self.previous
        self.temp.cleanup()

    def task(self, emp=0):
        with s.db() as c:
            tid = s.create_task(c, emp, "Projeto de teste")
            x, y = s.station_position(s.world_state(c)["layout"], emp)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=?", (x, y, emp))
            return dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def snapshot(self):
        with s.db() as c:
            return f.public(c)

    def test_transient_text_failure_is_visible_globally_and_scheduled_without_extra_model_call(
        self,
    ):
        task = self.task(1)
        with patch.object(
            s,
            "generate",
            side_effect=TimeoutError("Conexão temporariamente indisponível"),
        ) as generate:
            s.process_task(task)
        self.assertEqual(generate.call_count, 1)
        data = self.snapshot()
        self.assertEqual(data["open_count"], 1)
        item = data["items"][0]
        self.assertEqual(item["employee_name"], "Theo")
        self.assertEqual(item["status"], "retry_wait")
        self.assertEqual(item["target_id"], task["id"])
        self.assertEqual(item["attempts"], 0)
        self.assertTrue(item["can_retry"])
        self.assertGreater(item["next_retry"], time.time())

    def test_two_retries_use_backoff_then_require_attention_and_survive_restart(self):
        task = self.task()
        clock = 1000
        with s.db() as c:
            c.execute(
                "UPDATE tasks SET status='pausada',error='HTTP 503 temporário' WHERE id=?",
                (task["id"],),
            )
            f.record(
                c,
                "task",
                task["id"],
                ValueError("HTTP 503 temporário"),
                allow_auto=True,
                now=clock,
            )
            self.assertEqual(f.release_due(c, s.runtime.reserve, now=1014), 0)
            self.assertEqual(f.release_due(c, s.runtime.reserve, now=1015), 1)
            c.execute(
                "UPDATE tasks SET status='pausada',error='HTTP 503 temporário' WHERE id=?",
                (task["id"],),
            )
            f.record(
                c,
                "task",
                task["id"],
                ValueError("HTTP 503 temporário"),
                allow_auto=True,
                now=1016,
            )
            row = c.execute("SELECT * FROM failure_alerts").fetchone()
            self.assertEqual(row["attempts"], 1)
            self.assertEqual(row["next_retry"], 1061)
        s.init_db()
        with s.db() as c:
            self.assertEqual(f.release_due(c, s.runtime.reserve, now=1061), 1)
            c.execute("UPDATE tasks SET status='pausada' WHERE id=?", (task["id"],))
            f.record(
                c,
                "task",
                task["id"],
                ValueError("HTTP 503 temporário"),
                allow_auto=True,
                now=1062,
            )
            row = c.execute("SELECT * FROM failure_alerts").fetchone()
            self.assertEqual(row["attempts"], 2)
            self.assertEqual(row["status"], "open")
            self.assertEqual(row["next_retry"], 0)
            self.assertEqual(f.release_due(c, s.runtime.reserve, now=2000), 0)

    def test_success_resolves_alert_without_losing_failure_history(self):
        task = self.task(1)
        with patch.object(s, "generate", side_effect=TimeoutError("HTTP 503")):
            s.process_task(task)
        with s.db() as c:
            f.release_due(c, s.runtime.reserve, now=time.time() + 20)
            task = dict(
                c.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
            )
        with patch.object(
            s,
            "generate",
            return_value={"reply": "Concluído após a retomada", "actions": []},
        ):
            s.process_task(task)
        self.assertEqual(self.snapshot()["open_count"], 0)
        with s.db() as c:
            history = f.public(c, history=True)
            self.assertEqual(history["items"][0]["status"], "resolved")
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM archives").fetchone()[0], 1
            )

    def test_invalid_key_quota_and_permission_errors_are_never_automatic(self):
        for error in (
            "FreeLLMAPI HTTP 401: chave inválida",
            "HTTP 429 cota atingida",
            "HTTP 503: cota esgotada",
            "Funcionário sem acesso à ferramenta",
            "Modelo não encontrado HTTP 404",
            "Limite diário compartilhado atingido",
        ):
            task = self.task()
            with patch.object(s, "generate", side_effect=ValueError(error)):
                s.process_task(task)
        with s.db() as c:
            self.assertEqual(
                c.execute(
                    "SELECT COUNT(*) FROM failure_alerts WHERE status='retry_wait'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM failure_alerts").fetchone()[0], 6
            )

    def test_action_failure_is_not_replayed_even_if_error_mentions_http_503(self):
        task = self.task()
        with (
            patch.object(
                s, "generate", return_value={"reply": "Resposta", "actions": []}
            ),
            patch.object(
                s,
                "apply_actions",
                side_effect=ValueError("HTTP 503 durante aplicação da ação"),
            ),
        ):
            s.process_task(task)
        self.assertEqual(self.snapshot()["items"][0]["status"], "open")

    def test_disabling_automatic_retry_cancels_pending_schedule_and_keeps_the_alert(
        self,
    ):
        task = self.task()
        with patch.object(s, "generate", side_effect=TimeoutError("HTTP 503")):
            s.process_task(task)
        with s.db() as c:
            f.configure(c, False)
            self.assertEqual(
                f.release_due(c, s.runtime.reserve, now=time.time() + 100), 0
            )
        item = self.snapshot()["items"][0]
        self.assertEqual(item["status"], "open")
        self.assertEqual(item["next_retry"], 0)

    def test_dismissal_cancels_only_the_pending_retry_and_does_not_delete_the_task(
        self,
    ):
        task = self.task()
        with patch.object(s, "generate", side_effect=TimeoutError("HTTP 503")):
            s.process_task(task)
        with s.db() as c:
            f.dismiss(c, self.snapshot()["items"][0]["id"])
            self.assertEqual(
                f.release_due(c, s.runtime.reserve, now=time.time() + 100), 0
            )
            self.assertEqual(
                c.execute(
                    "SELECT status FROM tasks WHERE id=?", (task["id"],)
                ).fetchone()[0],
                "pausada",
            )
        self.assertEqual(self.snapshot()["open_count"], 0)

    def test_old_errors_are_imported_without_replaying_historical_work(self):
        task = self.task()
        with s.db() as c:
            c.execute(
                "UPDATE tasks SET status='pausada',error='HTTP 503 antigo' WHERE id=?",
                (task["id"],),
            )
        s.init_db()
        item = self.snapshot()["items"][0]
        self.assertEqual(item["status"], "open")
        self.assertEqual(item["next_retry"], 0)

    def test_tools_with_side_effects_or_uncertain_results_are_not_automatically_repeated(
        self,
    ):
        task = self.task()
        with s.db() as c:
            for kind, status in [
                ("image", "failed"),
                ("video", "uncertain"),
                ("instagram", "failed"),
                ("code", "failed"),
            ]:
                jid = c.execute(
                    "INSERT INTO tool_jobs(task,root,employee,kind,params,status,error,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        task["id"],
                        task["root"],
                        task["employee"],
                        kind,
                        "{}",
                        status,
                        "HTTP 503 temporário",
                        1000,
                        1000,
                    ),
                ).lastrowid
                f.record(
                    c, "tool", jid, TimeoutError("HTTP 503"), allow_auto=True, now=1000
                )
            self.assertEqual(f.release_due(c, s.runtime.reserve, now=2000), 0)
        data = self.snapshot()
        self.assertEqual(len(data["items"]), 4)
        self.assertTrue(all(item["status"] == "open" for item in data["items"]))
        self.assertFalse(
            next(item for item in data["items"] if item["tool"] == "video")["can_retry"]
        )

    def test_read_only_research_retry_respects_daily_tool_budget(self):
        task = self.task()
        with s.db() as c:
            jid = c.execute(
                "INSERT INTO tool_jobs(task,root,employee,kind,params,status,error,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    task["id"],
                    task["root"],
                    0,
                    "research",
                    "{}",
                    "failed",
                    "HTTP 503",
                    1000,
                    1000,
                ),
            ).lastrowid
            f.record(
                c, "tool", jid, TimeoutError("HTTP 503"), allow_auto=True, now=1000
            )
            s.runtime.save_settings(c, {"limits": {"research": 0}})
            self.assertEqual(f.release_due(c, s.runtime.reserve, now=1015), 0)
            row = c.execute("SELECT * FROM failure_alerts").fetchone()
            self.assertEqual(row["status"], "open")
            self.assertIn("Limite", row["message"])

    def test_nonzero_code_exit_is_visible_in_center_and_result_log_is_preserved(self):
        task = self.task(1)
        with s.db() as c:
            jid = s.runtime.enqueue(c, 1, task, "code", {"filename": "test.py"})
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            )
        s.runtime.finish_job(
            job, {"exit_code": 1, "output": "AssertionError: cálculo incorreto"}
        )
        item = self.snapshot()["items"][0]
        self.assertEqual(item["tool"], "code")
        self.assertEqual(item["status"], "open")
        self.assertEqual(item["target_status"], "failed")
        with s.db() as c:
            self.assertIn(
                "AssertionError",
                c.execute("SELECT result FROM tool_jobs WHERE id=?", (jid,)).fetchone()[
                    0
                ],
            )

    def test_remote_generation_interrupted_by_shutdown_is_uncertain(self):
        task = self.task()
        with s.db() as c:
            c.execute(
                "INSERT INTO tool_jobs(task,root,employee,kind,params,status,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                (task["id"], task["root"], 0, "video", "{}", "running", 1000, 1000),
            )
        s.runtime.recover()
        item = self.snapshot()["items"][0]
        self.assertEqual(item["target_status"], "uncertain")
        self.assertTrue(item["requires_review"])
        self.assertFalse(item["can_retry"])

    def test_real_worker_retries_a_temporary_model_failure_then_resolves_the_alert(
        self,
    ):
        task = self.task(1)
        with (
            patch.object(s.time, "sleep", side_effect=[None, None, StopIteration]),
            patch.object(f, "DELAYS", (0, 0)),
            patch.object(
                s,
                "generate",
                side_effect=[
                    TimeoutError("HTTP 503 temporário"),
                    {"reply": "Resposta recuperada", "actions": []},
                ],
            ) as generate,
        ):
            with self.assertRaises(StopIteration):
                s.worker()
        self.assertEqual(generate.call_count, 2)
        with s.db() as c:
            self.assertEqual(
                c.execute(
                    "SELECT status FROM tasks WHERE id=?", (task["id"],)
                ).fetchone()[0],
                "concluida",
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM archives").fetchone()[0], 1
            )
            self.assertEqual(
                c.execute("SELECT attempts FROM failure_alerts").fetchone()[0], 1
            )
        self.assertEqual(self.snapshot()["open_count"], 0)

    def test_automatic_retries_wait_while_team_is_paused_or_off_duty(self):
        self.task()
        for paused, resting in ((True, False), (False, True)):
            s.paused = paused
            with (
                patch.object(s.time, "sleep", side_effect=[None, StopIteration]),
                patch.object(s.town, "resting", return_value=resting),
                patch.object(f, "release_due") as release,
                patch.object(s, "generate") as generate,
            ):
                with self.assertRaises(StopIteration):
                    s.worker()
                release.assert_not_called()
                generate.assert_not_called()
        s.paused = False


class AlertHTTP(unittest.TestCase):
    setUp = test_server.Integration.setUp
    tearDown = test_server.Integration.tearDown
    post = test_server.Integration.post
    state = test_server.Integration.state

    def get(self, path):
        request = urllib.request.Request(
            self.url + "/api/" + path, headers={"X-Office-Token": s.TOKEN}
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def test_center_lists_all_staff_errors_and_direct_retry_does_not_duplicate_tasks(
        self,
    ):
        with s.db() as c:
            first = s.create_task(c, 1, "Erro do desenvolvedor")
            second = s.create_task(c, 2, "Erro do designer")
            c.execute(
                "UPDATE tasks SET status='pausada',error='Chave inválida' WHERE id IN (?,?)",
                (first, second),
            )
        data = self.get("alerts")
        self.assertEqual(data["open_count"], 2)
        self.assertEqual(
            {item["employee_name"] for item in data["items"]}, {"Theo", "Lia"}
        )
        self.post("retry", {"id": first})
        state = self.state()
        self.assertEqual(
            next(t for t in state["tasks"] if t["id"] == first)["status"], "fila"
        )
        self.assertEqual(len(state["tasks"]), 2)
        self.assertEqual(
            next(a for a in self.get("alerts")["items"] if a["target_id"] == first)[
                "status"
            ],
            "retrying",
        )

    def test_settings_and_dismissal_are_authenticated_and_persisted(self):
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.url + "/api/alerts")
        self.post("alerts/settings", {"auto_retry": False})
        self.assertFalse(self.get("alerts")["auto_retry"])
        self.assertFalse(self.state()["alerts"]["auto_retry"])
        with s.db() as c:
            tid = s.create_task(c, 3, "Erro no marketing")
            c.execute(
                "UPDATE tasks SET status='pausada',error='Permissão ausente' WHERE id=?",
                (tid,),
            )
        ident = self.get("alerts")["items"][0]["id"]
        self.post("alerts/dismiss", {"id": ident})
        self.assertEqual(self.get("alerts")["open_count"], 0)
        self.assertEqual(
            self.get("alerts?history=1")["items"][0]["status"], "dismissed"
        )
