import base64
import concurrent.futures
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, Mock
import test_server
import freellm_gateway as gateway
import browser_controls
import office_backup
import runtime_health
import credential_store

s = test_server.s


class Gateway(unittest.TestCase):
    def test_only_exact_loopback_endpoint_accepts_the_unified_key(self):
        for url in (gateway.BASE, "http://localhost:3001/v1", "http://[::1]:3001/v1/"):
            self.assertTrue(gateway.is_local(url), url)
        for url in (
            "https://evil.test/v1",
            "http://127.0.0.1:3001.evil.test/v1",
            "http://127.0.0.1:8765/v1",
            "http://user:key@localhost:3001/v1",
            "http://localhost:3001/v1?key=secret",
            "http://localhost:3001/v1#x",
        ):
            self.assertFalse(gateway.is_local(url), url)

    def test_image_bytes_become_openai_vision_content(self):
        body = gateway.payload(
            [
                {
                    "role": "user",
                    "content": "Leia",
                    "inline_files": [{"mime": "image/jpeg", "data": "aW1hZ2U="}],
                }
            ],
            "auto",
            512,
        )
        self.assertEqual(
            body["messages"][0]["content"][1]["image_url"]["url"],
            "data:image/jpeg;base64,aW1hZ2U=",
        )
        self.assertNotIn("inline_files", json.dumps(body))
        with self.assertRaises(ValueError):
            gateway.payload(
                [
                    {
                        "role": "user",
                        "content": "PDF",
                        "inline_files": [{"mime": "application/pdf", "data": "cGRm"}],
                    }
                ],
                "auto",
                512,
            )

    def test_redirects_do_not_forward_credentials(self):
        self.assertIsNone(
            gateway.NoRedirect().redirect_request(None, None, 302, "", "", gateway.BASE)
        )

    def test_local_transport_ignores_system_proxy_and_sanitizes_errors(self):
        import urllib.error

        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            gateway.BASE, 401, "secret-provider-body", {}, None
        )
        with patch.object(gateway.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(
                ValueError, "chave unificada inválida"
            ) as failure:
                gateway.request(gateway.BASE, "private-key", "/chat/completions", {})
        self.assertNotIn("private-key", str(failure.exception))
        self.assertNotIn("secret-provider-body", str(failure.exception))


class Reliability(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = s.DATA
        s.DATA = Path(self.temp.name) / "dados"
        s.DATA.mkdir()
        s.init_db()

    def tearDown(self):
        s.DATA = self.previous
        self.temp.cleanup()

    def task(self, emp=0):
        with s.db() as c:
            tid = s.create_task(c, emp, "Projeto de teste")
            x, y = s.station_position(s.world_state(c)["layout"], emp)
            c.execute("UPDATE employees SET x=?,y=? WHERE id=?", (x, y, emp))
            return dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def test_denied_action_rolls_back_files_memories_and_false_completion(self):
        task = self.task(1)
        answer = {
            "reply": "Pesquisando",
            "actions": [
                {
                    "type": "tool",
                    "tool": "browser",
                    "params": {
                        "goal": "Consultar fontes",
                        "urls": ["https://example.com"],
                    },
                }
            ],
            "files": [{"filename": "falso.txt", "content": "Não entregar"}],
        }
        with patch.object(s, "generate", return_value=answer):
            s.process_task(task)
        with s.db() as c:
            row = c.execute(
                "SELECT status,error FROM tasks WHERE id=?", (task["id"],)
            ).fetchone()
            self.assertEqual(row["status"], "pausada")
            self.assertIn("sem acesso", row["error"])
            for table in ("task_files", "archives", "deliveries", "tool_jobs"):
                self.assertEqual(
                    c.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0, table
                )

    def test_mixed_actions_are_atomic_and_retry_cannot_duplicate_the_first(self):
        task = self.task()
        answer = {
            "reply": "Ações",
            "actions": [
                {"type": "tool", "tool": "board", "params": {"operation": "read"}},
                {
                    "type": "tool",
                    "tool": "browser",
                    "params": {
                        "goal": "Consultar fontes",
                        "urls": ["https://example.com"],
                    },
                },
            ],
        }
        for _ in range(2):
            with patch.object(s, "generate", return_value=answer):
                s.process_task(task)
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM tool_jobs").fetchone()[0], 0
            )

    def test_gateway_connect_tests_before_saving_and_can_apply_to_the_whole_team(self):
        with s.db() as c:
            s.runtime.save_profile(
                c,
                {
                    "employee": 1,
                    "inherit": False,
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "openai/gpt-oss-20b",
                    "key_name": "GROQ_API_KEY",
                    "tools": ["code"],
                },
            )
        result = {"model": "served-model", "choices": [{"message": {"content": "OK"}}]}
        with patch.object(gateway, "request", return_value=result):
            s.runtime.connect_freellm("unified-test", True)
        self.assertEqual(
            s.runtime.effective_text(1, {"mode": "demo"})[1], "unified-test"
        )
        with patch.object(
            gateway, "request", side_effect=ValueError("Roteador indisponível")
        ):
            with self.assertRaises(ValueError):
                s.runtime.connect_freellm("bad-key")
        self.assertEqual(s.runtime.key(gateway.KEY), "unified-test")

    def test_daily_shared_budget_is_persistent_and_counts_failures(self):
        with s.db() as c:
            s.runtime.save_settings(c, {"text_daily_limit": "1"})
        cfg = {"base_url": gateway.BASE, "model": "auto"}
        with patch.object(
            gateway, "request", side_effect=ValueError("offline")
        ) as transport:
            with self.assertRaises(ValueError):
                s.runtime.text_request(
                    cfg, "key", [{"role": "user", "content": "Teste"}], 512
                )
            with self.assertRaisesRegex(ValueError, "Limite diário"):
                s.runtime.text_request(cfg, "key", [], 512)
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(s.runtime.text_budget.status()["requests"], 1)

    def test_background_chatter_does_not_wait_in_front_of_work(self):
        with s.runtime.text_budget.lock:
            with self.assertRaisesRegex(ValueError, "ocupada"):
                s.runtime.text_request(
                    {"base_url": gateway.BASE, "model": "auto"},
                    "key",
                    [],
                    512,
                    priority="background",
                )

    def test_queue_does_not_stop_at_an_employee_still_walking(self):
        first = self.task(0)
        second = self.task(1)
        with s.db() as c:
            s.runtime.enqueue(c, 0, first, "board", {"operation": "read"})
            s.runtime.enqueue(c, 1, second, "board", {"operation": "read"})
            c.execute("UPDATE employees SET x=690,y=730 WHERE id=0")
        with (
            patch.object(s.runtime, "office", return_value={"notes": []}),
            patch.object(s.runtime, "finish_job") as finish,
        ):
            s.runtime.tick()
        self.assertEqual(finish.call_args.args[0]["employee"], 1)

    def test_backup_restore_preserves_original_and_excludes_keys(self):
        task = self.task()
        home = Path(self.temp.name)
        (home / "config.json").write_text(
            json.dumps({"mode": "api", "model": "auto", "api_key": "MUST-NOT-EXPORT"})
        )
        s.runtime.store_key(gateway.KEY, "MUST-NOT-EXPORT")
        raw = office_backup.create(s.DATA, home, s.VERSION)
        backup = home / "backup.zip"
        backup.write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"manifest.json", "config.json", "escritorio.db"},
            )
            self.assertNotIn("MUST-NOT-EXPORT", archive.read("config.json").decode())
        with s.db() as c:
            c.execute("UPDATE tasks SET title='Modificado'")
        safety = office_backup.restore(backup, s.DATA, home, s.VERSION)
        with s.db() as c:
            self.assertEqual(
                c.execute(
                    "SELECT title FROM tasks WHERE id=?", (task["id"],)
                ).fetchone()[0],
                "Projeto de teste",
            )
        with sqlite3.connect(safety / "escritorio.db") as old:
            self.assertEqual(
                old.execute("SELECT title FROM tasks").fetchone()[0], "Modificado"
            )
        self.assertEqual(s.runtime.key(gateway.KEY), "MUST-NOT-EXPORT")

    def test_restore_rejects_path_traversal_without_touching_the_database(self):
        path = Path(self.temp.name) / "evil.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../escape.txt", "bad")
        with self.assertRaises(ValueError):
            office_backup.restore(path, s.DATA, Path(self.temp.name), s.VERSION)
        self.assertFalse((Path(self.temp.name) / "escape.txt").exists())

    def test_instance_lock_prevents_two_process_lifetimes_for_the_same_data(self):
        first = runtime_health.Health(s.DATA)
        second = runtime_health.Health(s.DATA)
        first.acquire()
        try:
            with self.assertRaises(RuntimeError):
                second.acquire()
        finally:
            first.instance.close()

    def test_spelled_out_ranking_count_cannot_pass_with_two_items(self):
        links = [
            {"url": f"https://www.youtube.com/watch?v=v{n}", "text": f"Vídeo {n}"}
            for n in range(2)
        ]
        page = {
            "url": "https://www.youtube.com/trending",
            "text": "Em alta Brasil",
            "headings": ["Em alta Brasil"],
            "links": links,
        }
        decision = {
            "outcome": "success",
            "report": "Resultado",
            "ranking_label": "Em alta Brasil",
            "items": links,
            "evidence": [{"url": page["url"], "quote": page["text"]}],
        }
        result = browser_controls.final_result(
            "Os dez primeiros vídeos em alta YouTube Brasil", decision, [page]
        )
        self.assertEqual(result["requested_count"], 10)
        self.assertFalse(result["complete"])

    def test_cofre_legacy_migration_preserves_every_credential(self):
        path = s.DATA / "credenciais.json"
        path.write_text(
            json.dumps({"GEMINI_API_KEY": "legacy", "FREELLM_API_KEY": "unified"})
        )
        self.assertEqual(credential_store.load(path)["GEMINI_API_KEY"], "legacy")
        credential_store.save(
            path, {"GEMINI_API_KEY": "legacy", "FREELLM_API_KEY": "unified"}
        )
        self.assertEqual(credential_store.load(path)["FREELLM_API_KEY"], "unified")


class LocalHTTP(test_server.Integration):
    def test_cross_site_or_rebound_host_cannot_bootstrap_the_token(self):
        import urllib.request
        import urllib.error

        for headers in (
            {"Host": "attacker.example"},
            {"Origin": "https://attacker.example"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            request = urllib.request.Request(self.url + "/api/state", headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)

    def test_history_is_authenticated_and_pages_by_employee_without_duplicates(self):
        with s.db() as c:
            c.executemany(
                "INSERT INTO messages(employee,role,content) VALUES(0,'user',?)",
                [(str(i),) for i in range(105)],
            )
            c.execute(
                "INSERT INTO messages(employee,role,content) VALUES(1,'user','other')"
            )
        request = __import__("urllib.request", fromlist=["Request"]).Request(
            self.url + "/api/history?employee=0", headers={"X-Office-Token": s.TOKEN}
        )
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(
            request
        ) as response:
            page = json.load(response)
        self.assertEqual(len(page["items"]), 100)
        self.assertTrue(page["has_more"])
        self.assertTrue(all(r["employee"] == 0 for r in page["items"]))
        self.assertEqual(
            len([m for m in self.state()["messages"] if m["employee"] == 0]), 100
        )


class UnifiedImages(unittest.TestCase):
    setUp = Reliability.setUp
    tearDown = Reliability.tearDown
    task = Reliability.task

    def test_image_generation_reuses_unified_key_without_cloudflare_credentials(self):
        task = self.task(2)
        s.runtime.store_key(gateway.KEY, "one-key")
        with s.db() as c:
            s.runtime.save_settings(c, {"image_provider": "freellm"})
            jid = s.runtime.enqueue(
                c, 2, task, "image", {"prompt": "Uma cidade isométrica"}
            )
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            )
        raw = b"\x89PNG\r\n\x1a\nEXAMPLE"
        with patch.object(
            gateway,
            "request",
            return_value={"data": [{"b64_json": base64.b64encode(raw).decode()}]},
        ) as transport:
            result = s.runtime.image(job, {"prompt": "Uma cidade isométrica"})
        self.assertEqual(
            transport.call_args.args[:3],
            (gateway.BASE, "one-key", "/images/generations"),
        )
        self.assertEqual(result["provider"], "FreeLLMAPI")
        self.assertEqual(s.runtime.key("CLOUDFLARE_API_TOKEN"), "")

    def test_remote_image_url_is_not_fetched_as_a_substitute(self):
        with self.assertRaisesRegex(ValueError, "URLs externas"):
            gateway.image_result({"data": [{"url": "http://127.0.0.1/private"}]})

    def test_future_schema_is_refused_before_mutation(self):
        with s.db() as c:
            c.execute("PRAGMA user_version=999")
        with self.assertRaisesRegex(RuntimeError, "mais recente"):
            s.init_db()
        with s.db() as c:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 999)
