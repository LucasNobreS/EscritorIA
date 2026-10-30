import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import test_server

s = test_server.s


class PersistentMemory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()
        self.server = s.ThreadingHTTPServer(("127.0.0.1", 0), s.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        s.DATA = self.original
        self.temp.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(
            self.url + "/api/" + path,
            data=json.dumps(body).encode(),
            headers={"X-Office-Token": s.TOKEN},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def get(self, path):
        req = urllib.request.Request(
            self.url + "/api/" + path, headers={"X-Office-Token": s.TOKEN}
        )
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def test_delivery_and_learning_survive_restart_and_old_context(self):
        self.post("task", {"employee": 1, "title": "Portal Aurora"})
        with s.db() as c:
            t = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        answer = {
            "reply": "Entregamos a especificação do Portal Aurora. Usar navegação lateral.",
            "actions": [],
            "learnings": [
                {
                    "title": "Portal Aurora: navegação",
                    "content": "O briefing do Portal Aurora pede navegação lateral.",
                    "kind": "decisao",
                    "scope": "individual",
                }
            ],
        }
        with patch.object(s, "generate", return_value=answer):
            s.process_task(t)
        self.assertIn("Portal Aurora", (s.DATA / "entregas/tarefa-1.txt").read_text())
        with s.db() as c:
            for i in range(50):
                s.create_task(c, 2, f"Outra demanda {i}")
            for i in range(20):
                c.execute(
                    'INSERT INTO messages(employee,role,content) VALUES(1,"user",?)',
                    (f"Outra conversa {i}",),
                )
        s.init_db()
        s.recover_deliveries()
        messages, _, _ = s.build_context(1, "Retome o Portal Aurora")
        dossier = json.loads(messages[0]["content"].split("CONTEXTO ATUAL:\n")[1])
        records = dossier["memoria_persistente"]
        self.assertTrue(any(r["type"] == "archive" and r["task"] == 1 for r in records))
        m = next(r for r in records if r["type"] == "memory")
        self.assertEqual(m["source_task"], 1)
        self.assertEqual(m["status"], "suggested")

    def test_private_shared_and_manager_recall(self):
        with s.db() as c:
            s.save_memory(
                c, 1, "Projeto Oceano", "Implementar catálogo Oceano", "procedimento"
            )
            s.save_memory(
                c,
                1,
                "Estilo Oceano",
                "Usar português claro no Oceano",
                "preferencia",
                "compartilhada",
            )
        with s.db() as c:
            individual = s.retrieve_knowledge(c, 1, "Oceano")
            other = s.retrieve_knowledge(c, 2, "Oceano")
            manager = s.retrieve_knowledge(c, 0, "Oceano")
        self.assertEqual(len(individual), 2)
        self.assertEqual(len(other), 1)
        self.assertEqual(other[0]["scope"], "compartilhada")
        self.assertEqual(len(manager), 2)

    def test_human_corrections_revision_and_invalidation(self):
        with s.db() as c:
            mid = s.save_memory(
                c,
                1,
                "Cor da marca",
                "A confirmar",
                "preferencia",
                source="model",
                source_task=7,
                status="suggested",
            )
        self.post(
            "memory",
            {
                "id": mid,
                "employee": 1,
                "title": "Cor da marca",
                "content": "A cor aprovada é verde",
                "kind": "preferencia",
                "scope": "individual",
                "status": "confirmed",
            },
        )
        history = self.get(f"memory/history?id={mid}")["versions"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["revision"], 2)
        self.assertEqual(history[0]["source"], "model")
        self.assertEqual(history[0]["source_task"], 7)
        self.post("memory/status", {"id": mid, "status": "inactive"})
        self.assertEqual(self.get("knowledge?employee=1&section=memories")["total"], 0)
        self.assertEqual(
            self.get("knowledge?employee=1&section=memories&inactive=1")["total"], 1
        )
        with s.db() as c:
            self.assertEqual(s.retrieve_knowledge(c, 1, "Cor da marca"), [])
        self.assertEqual(len(self.get(f"memory/history?id={mid}")["versions"]), 3)

    def test_model_cannot_resurrect_invalidated_memory_or_overwrite_correction(self):
        with s.db() as c:
            mid = s.save_memory(
                c,
                1,
                "Procedimento",
                "Texto anterior",
                source="model",
                status="suggested",
            )
            s.save_memory(
                c, 1, "Procedimento", "Texto anterior", status="inactive", memory_id=mid
            )
            duplicate = s.save_memory(
                c,
                1,
                "Procedimento",
                "Texto anterior",
                source="model",
                status="suggested",
            )
            self.assertEqual(duplicate, mid)
            self.assertEqual(
                c.execute("SELECT status FROM memories WHERE id=?", (mid,)).fetchone()[
                    0
                ],
                "inactive",
            )
            s.save_memory(
                c,
                1,
                "Procedimento",
                "Texto corrigido",
                status="confirmed",
                memory_id=mid,
            )
            same = s.save_memory(
                c,
                1,
                "Procedimento",
                "Texto corrigido",
                source="model",
                status="suggested",
            )
            self.assertEqual(same, mid)
            self.assertEqual(
                c.execute("SELECT status FROM memories WHERE id=?", (mid,)).fetchone()[
                    0
                ],
                "confirmed",
            )

    def test_migration_backfills_legacy_completed_deliveries_idempotently(self):
        old = s.DATA / "legacy"
        old.mkdir()
        s.DATA = old
        with s.db() as c:
            c.executescript(
                'CREATE TABLE tasks(id INTEGER PRIMARY KEY,employee INTEGER,title TEXT,status TEXT,result TEXT,error TEXT);INSERT INTO tasks VALUES(12,1,"Entrega anterior","concluida","Conteúdo preservado","");'
            )
        s.init_db()
        s.recover_deliveries()
        s.init_db()
        s.recover_deliveries()
        records = self.get("knowledge?section=archives")
        self.assertEqual(records["total"], 1)
        a = self.get("archive?id=1")
        self.assertEqual(a["task"], 12)
        self.assertEqual(a["content"], "Conteúdo preservado")
        self.assertTrue((old / "entregas/tarefa-12.txt").exists())

    def test_full_archive_search_finds_text_after_preview_and_bounds_prompt(self):
        with s.db() as c:
            tid = s.create_task(c, 1, "Pesquisa antiga")
            t = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
            s.record_delivery(
                c, t, "Começo. " * 1000 + "METEORITO é a palavra-chave do projeto."
            )
        result = self.get("knowledge?employee=1&q=meteorito&section=archives")
        self.assertEqual(result["total"], 1)
        self.assertIn("METEORITO", result["items"][0]["content"])
        self.assertLess(len(result["items"][0]["content"]), 1900)
        with s.db() as c:
            for i in range(30):
                s.save_memory(
                    c, 1, f"Meteorito {i}", "meteorito " + str(i) + " " + ("x" * 2400)
                )
            records = s.retrieve_knowledge(c, 1, "meteorito")
        self.assertLessEqual(len(records), 12)
        self.assertLessEqual(
            sum(len(json.dumps(r, ensure_ascii=False)) for r in records), 14000
        )

    def test_export_and_consistent_backup_include_memory_and_archive(self):
        self.post(
            "memory",
            {"employee": 0, "title": "Regra", "content": "Entregar com clareza"},
        )
        with s.db() as c:
            tid = s.create_task(c, 1, "Código")
            t = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
            s.record_delivery(c, t, 'print("olá")')
        export = self.get("knowledge/export")
        self.assertEqual(export["format"], "atelie-knowledge-v1")
        self.assertEqual(len(export["memories"]), 1)
        self.assertEqual(len(export["archives"]), 1)
        req = urllib.request.Request(
            self.url + "/api/backup", headers={"X-Office-Token": s.TOKEN}
        )
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            self.assertIn("attachment", r.headers["Content-Disposition"])
        file = s.DATA / "restored.db"
        file.write_bytes(raw)
        with sqlite3.connect(file) as c:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1
            )

    def test_validation_duplicate_and_demo_rules(self):
        with s.db() as c:
            first = s.save_memory(c, 1, "Regra", "Uma só vez")
            second = s.save_memory(c, 1, "Regra", "Uma só vez")
            self.assertEqual(first, second)
        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "memory",
                {
                    "employee": 1,
                    "title": "Ruim",
                    "content": "Inválida",
                    "kind": "arbitraria",
                },
            )
        self.post("task", {"employee": 1, "title": "Demo"})
        with s.db() as c:
            t = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        with patch.object(s, "config", return_value={"mode": "demo"}):
            s.process_task(t)
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM archives").fetchone()[0], 1
            )
            self.assertFalse(
                any(r["type"] == "archive" for r in s.retrieve_knowledge(c, 1, "Demo"))
            )
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.url + "/api/knowledge")
        self.assertEqual(e.exception.code, 403)
