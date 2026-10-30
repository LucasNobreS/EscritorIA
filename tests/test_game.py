import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch
import test_server

s = test_server.s


class OfficeGame(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()
        s.paused = False
        self.server = s.ThreadingHTTPServer(("127.0.0.1", 0), s.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        s.DATA = self.original
        s.paused = False
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

    def raw(self, path):
        req = urllib.request.Request(
            self.url + "/api/" + path, headers={"X-Office-Token": s.TOKEN}
        )
        with urllib.request.urlopen(req) as r:
            return r.read()

    def state(self):
        return json.loads(self.raw("state"))

    def test_owner_room_is_reachable_and_skins_survive_restart(self):
        state = self.state()
        layout = state["world"]["layout"]
        self.assertTrue(s.route(690, 730, *s.inbox_position(layout), layout))
        skin = dict(
            s.DEFAULT_SKIN,
            hairStyle="curly",
            shirt="#aabbcc",
            skin="#804f37",
            accessory="glasses",
            outfit="suit",
        )
        self.post("skin", {"name": "Lucas", "skin": skin})
        self.post("skin", {"employee": 0, "skin": dict(skin, hairStyle="long")})
        s.init_db()
        state = self.state()
        self.assertEqual(state["world"]["player"]["skin"]["hairStyle"], "curly")
        self.assertEqual(state["world"]["player"]["skin"]["outfit"], "suit")
        self.assertEqual(state["employees"][0]["skin"]["shirt"], "#aabbcc")
        self.assertEqual(state["employees"][0]["skin"]["hairStyle"], "long")
        with self.assertRaises(urllib.error.HTTPError):
            self.post("skin", {"skin": {"hairStyle": "invalid"}})

    def test_furniture_edit_rotates_station_and_updates_navigation(self):
        world = self.state()["world"]
        layout = world["layout"]
        layout[0]["rotation"] = 90
        layout[0]["color"] = "#bbaa88"
        with self.assertRaises(urllib.error.HTTPError):
            self.post("layout", {"revision": world["revision"], "layout": layout})
        self.post("pause", {})
        self.post("layout", {"revision": world["revision"], "layout": layout})
        current = self.state()
        self.assertEqual(current["world"]["revision"], world["revision"] + 1)
        target = s.station_position(current["world"]["layout"], 0)
        self.assertEqual(target, (178.0, 313.0))
        self.assertTrue(s.route(690, 730, *target, current["world"]["layout"]))
        self.assertEqual(
            (current["employees"][0]["x"], current["employees"][0]["y"]), target
        )
        s.init_db()
        self.assertEqual(self.state()["world"]["layout"][0]["rotation"], 90)
        with self.assertRaises(urllib.error.HTTPError):
            self.post("layout", {"revision": world["revision"], "layout": layout})

    def test_overlap_and_blocked_door_are_rejected_without_changing_layout(self):
        world = self.state()["world"]
        layout = world["layout"]
        self.post("pause", {})
        plant = next(i for i in layout if i["kind"] == "plant")
        plant["x"] = 210
        plant["y"] = 235
        with self.assertRaises(urllib.error.HTTPError):
            self.post("layout", {"revision": world["revision"], "layout": layout})
        self.assertEqual(self.state()["world"]["revision"], world["revision"])
        layout = s.default_layout()
        layout.extend(
            [
                {
                    "id": "block-a",
                    "kind": "plant",
                    "x": 1360,
                    "y": 730,
                    "rotation": 0,
                    "color": "#445566",
                },
                {
                    "id": "block-b",
                    "kind": "plant",
                    "x": 1360,
                    "y": 790,
                    "rotation": 0,
                    "color": "#445566",
                },
            ]
        )
        with self.assertRaises(ValueError):
            s.validate_layout(layout)

    def test_generated_files_are_persisted_and_manager_delivers_downloadable_zip(self):
        self.post(
            "task",
            {"intent": "project", "employee": 1, "title": "Criar página inicial"},
        )
        with s.db() as c:
            t = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        answer = {
            "reply": "Página e estilos preparados.",
            "actions": [],
            "files": [
                {"filename": "index.html", "content": "<h1>Olá</h1>"},
                {"filename": "style.css", "content": "h1 { color: green; }"},
            ],
        }
        with patch.object(s, "generate", return_value=answer):
            s.process_task(t)
        self.assertEqual(
            (s.DATA / "arquivos/tarefa-1/index.html").read_text(), "<h1>Olá</h1>"
        )
        delivery = self.state()["deliveries"][0]
        self.assertEqual(delivery["status"], "pending")
        self.assertEqual(delivery["file_count"], 2)
        with self.assertRaises(urllib.error.HTTPError):
            self.raw("delivery?id=" + str(delivery["id"]))
        paths = {}
        idle = {}
        for _ in range(500):
            s.navigation_tick(paths, idle)
            with s.db() as c:
                status = c.execute(
                    "SELECT status FROM deliveries WHERE id=?", (delivery["id"],)
                ).fetchone()[0]
            if status == "delivered":
                break
        self.assertEqual(status, "delivered")
        package = json.loads(self.raw("delivery?id=" + str(delivery["id"])))
        self.assertEqual(len(package["files"]), 2)
        downloaded = self.raw("task-file?id=" + str(package["files"][0]["id"]))
        self.assertIn(downloaded, (b"<h1>Ol\xc3\xa1</h1>", b"h1 { color: green; }"))
        with zipfile.ZipFile(
            io.BytesIO(self.raw("delivery/zip?id=" + str(delivery["id"])))
        ) as z:
            self.assertEqual(z.read("tarefa-1/index.html").decode(), "<h1>Olá</h1>")
            self.assertIn("resumo.txt", z.namelist())
        self.post("delivery/read", {"id": delivery["id"]})
        self.assertEqual(self.state()["deliveries"][0]["unread"], 0)

    def test_delegated_work_waits_for_all_steps_before_packaging(self):
        self.post("task", {"intent": "project", "employee": 0, "title": "Campanha"})
        with s.db() as c:
            t = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        with patch.object(
            s,
            "generate",
            return_value={
                "reply": "Vou delegar.",
                "actions": [
                    {"type": "delegate", "employee_id": 3, "task": "Escrever copy"}
                ],
            },
        ):
            s.process_task(t)
        self.assertEqual(self.state()["deliveries"], [])

    def test_invalid_filenames_and_plain_reply_never_fabricate_deliverables(self):
        self.post("task", {"intent": "project", "employee": 1, "title": "Teste"})
        with s.db() as c:
            t = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
            s.save_task_files(
                c,
                t,
                [
                    {"filename": "../escape.py", "content": "x"},
                    {"filename": "bad.exe", "content": "x"},
                ],
                "Resposta preservada",
            )
        s.write_task_files(1)
        with s.db() as c:
            files = c.execute("SELECT filename FROM task_files").fetchall()
        self.assertEqual(files, [])
        self.assertFalse((s.DATA / "arquivos/tarefa-1/entrega.txt").exists())

    def test_chat_never_creates_delivery_even_if_model_returns_files(self):
        self.post("task", {"employee": 0, "title": "Bom dia"})
        with s.db() as c:
            t = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        with patch.object(
            s,
            "generate",
            return_value={
                "reply": "Bom dia!",
                "files": [{"filename": "oi.txt", "content": "Bom dia"}],
                "actions": [
                    {
                        "type": "delegate",
                        "employee_id": 1,
                        "task": "Criar projeto indevido",
                    }
                ],
            },
        ):
            s.process_task(t)
        s.recover_packages()
        s.init_db()
        s.recover_packages()
        with s.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM task_files").fetchone()[0], 0
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM archives").fetchone()[0], 0
            )
            self.assertEqual(
                c.execute("SELECT status FROM tasks WHERE id=1").fetchone()[0],
                "pausada",
            )

    def test_project_waits_for_real_files_and_internal_reports_are_excluded(self):
        with s.db() as c:
            tid = s.create_task(c, 0, "Projeto")
            t = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
            c.execute("UPDATE tasks SET status='concluida' WHERE id=?", (tid,))
            s.save_task_files(c, t, [], "Explicação")
            s.queue_delivery(c, tid)
            s.save_task_files(
                c,
                t,
                [{"filename": "relatorio.json", "content": "{}"}],
                "Tool",
                internal=True,
            )
            s.queue_delivery(c, tid)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0
            )
            child = s.create_task(c, 1, "Implementar", parent=tid)
            self.assertEqual(
                c.execute("SELECT intent FROM tasks WHERE id=?", (child,)).fetchone()[
                    0
                ],
                "project",
            )
            c.execute("UPDATE tasks SET status='concluida' WHERE id=?", (child,))
            s.save_task_files(
                c,
                t,
                [{"filename": "projeto.html", "content": "<h1>Projeto</h1>"}],
                "Pronto",
            )
            s.queue_delivery(c, tid)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM delivery_files").fetchone()[0], 1
            )

    def test_upgrade_preserves_history_but_stops_legacy_pending_packages(self):
        with s.db() as c:
            tid = s.create_task(c, 0, "Olá antigo", intent="legacy")
            c.execute(
                "UPDATE tasks SET status='concluida',result='Olá' WHERE id=?", (tid,)
            )
            c.execute(
                "INSERT INTO deliveries(root,manager,title,summary,status,created) VALUES(?,0,'Olá','Olá','pending',0)",
                (tid,),
            )
            c.execute(
                "INSERT INTO task_files(task,employee,filename,content,created) VALUES(?,0,'entrega.txt','Olá',0)",
                (tid,),
            )
        s.recover_packages()
        s.recover_packages()
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT status FROM deliveries").fetchone()[0], "cancelled"
            )
            self.assertEqual(
                c.execute("SELECT content FROM task_files").fetchone()[0], "Olá"
            )

    def test_local_art_http_pipeline_and_draft_caption_edit(self):
        self.post(
            "tools/job",
            {
                "employee": 2,
                "kind": "art",
                "params": {"title": "Minha arte", "format": "square"},
            },
        )
        with patch.object(
            s.runtime, "request", side_effect=AssertionError("No network for local art")
        ):
            s.runtime.tick()
        with s.db() as c:
            asset = dict(c.execute("SELECT * FROM assets").fetchone())
            self.assertEqual(asset["mime"], "image/jpeg")
        self.post("social/create", {"asset_id": asset["id"], "caption": "Original"})
        with s.db() as c:
            pid = c.execute("SELECT id FROM social_posts").fetchone()[0]
        self.post("social/update", {"id": pid, "caption": "Legenda revisada"})
        with s.db() as c:
            post = c.execute("SELECT * FROM social_posts WHERE id=?", (pid,)).fetchone()
            self.assertEqual(post["caption"], "Legenda revisada")
            self.assertEqual(post["status"], "draft")
            c.execute("UPDATE social_posts SET status='queued' WHERE id=?", (pid,))
        with self.assertRaises(urllib.error.HTTPError):
            self.post("social/update", {"id": pid, "caption": "Alteração tardia"})

    def test_api_response_includes_file_payload(self):
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
                                            "reply": "Pronto",
                                            "files": [
                                                {
                                                    "filename": "app.js",
                                                    "content": "console.log(1)",
                                                }
                                            ],
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode()

        with (
            patch.object(
                s,
                "config",
                return_value={
                    "mode": "api",
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "test",
                },
            ),
            patch.dict(s.os.environ, {"OFFICE_API_KEY": "test"}),
            patch.object(s.urllib.request, "urlopen", return_value=Response()),
        ):
            result = s.generate(1, "Crie um script")
        self.assertEqual(result["files"][0]["filename"], "app.js")

    def test_static_assets_ignore_windows_mime_registry_and_disable_cache(self):
        with patch("mimetypes.guess_type", return_value=("text/plain", None)):
            for name, mime in [
                ("style.css", "text/css"),
                ("app.js", "text/javascript"),
                ("connections.js", "text/javascript"),
                ("world.js", "text/javascript"),
            ]:
                with urllib.request.urlopen(
                    self.url + "/" + name + "?v=0.8.1"
                ) as response:
                    self.assertTrue(response.headers["Content-Type"].startswith(mime))
                    self.assertIn("no-store", response.headers.get_all("Cache-Control"))
                    self.assertGreater(len(response.read()), 100)

    def test_all_html_assets_load_with_absolute_paths_and_correct_content(self):
        import re

        html = urllib.request.urlopen(self.url + "/").read().decode()
        assets = [
            a
            for a in re.findall(r'(?:src|href)="([^"]+)"', html)
            if a.startswith("/") and a.endswith((".js", ".css"))
        ]
        self.assertEqual(len(assets), 12)
        self.assertIn("/alerts.js", assets)
        self.assertIn("/catalogs.js", assets)
        self.assertIn("/town.js", assets)
        self.assertIn("/town-art.js", assets)
        self.assertIn("/town.css", assets)
        for asset in assets:
            self.assertTrue(asset.startswith("/"))
            self.assertNotIn("?", asset)
            with urllib.request.urlopen(self.url + asset) as response:
                content = response.read().decode()
                self.assertGreater(len(content), 100)
                self.assertNotIn("<!doctype", content.lower())
                self.assertTrue(
                    response.headers["Content-Type"].startswith(
                        "text/css" if asset.endswith(".css") else "text/javascript"
                    )
                )
        for path, mime in [
            ("/tutorial-freellm.html", "text/html"),
            ("/tutorial-freellm.mp4", "video/mp4"),
        ]:
            with urllib.request.urlopen(self.url + path) as response:
                self.assertTrue(response.headers["Content-Type"].startswith(mime))
                self.assertGreater(len(response.read()), 100)
        self.assertEqual(json.loads(self.raw("health"))["version"], s.VERSION)

    def test_startup_skips_port_occupied_by_old_server(self):
        old = s.ThreadingHTTPServer(("127.0.0.1", 0), s.Handler)
        try:
            with patch.object(
                s,
                "ThreadingHTTPServer",
                side_effect=[OSError(98, "address in use"), old],
            ) as constructor:
                self.assertIs(s.create_local_server(), old)
                self.assertEqual(constructor.call_args.args[0], ("127.0.0.1", 8766))
        finally:
            old.server_close()
        s.validate_web_files()

    def test_customization_endpoints_save_skin_preferences_and_object_actions(self):
        self.post(
            "skin",
            {
                "employee": 0,
                "skin": {
                    "gender": "woman",
                    "outfit": "blazer",
                    "hairStyle": "bun",
                    "pattern": "dots",
                    "accessory": "earrings",
                    "body": "slim",
                    "bottom": "skirt",
                    "accent": "#ccaa88",
                },
            },
        )
        self.post(
            "world/preferences",
            {
                "name": "Lucas Studio",
                "floor": "#ccddee",
                "wall": "#aabbcc",
                "accent": "#112233",
                "lighting": "warm",
                "floorPattern": "plain",
            },
        )
        result = self.post("world/interact", {"id": "plant-0", "action": "water"})
        self.assertEqual(result["state"]["waterCount"], 1)
        self.assertEqual(result["message"], "Planta regada.")
        state = self.state()
        self.assertEqual(state["world"]["preferences"]["name"], "Lucas Studio")
        self.assertEqual(state["employees"][0]["skin"]["gender"], "woman")
        self.assertEqual(state["world"]["objectStates"]["plant-0"]["waterCount"], 1)

    def test_quick_gemini_connection_endpoint_detects_model_and_activates_selected_employee(
        self,
    ):
        from unittest.mock import patch

        replies = [
            {
                "models": [
                    {
                        "name": "models/gemini-3.1-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
            {
                "candidates": [
                    {"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}
                ]
            },
        ]
        with patch.object(s.runtime, "gemini_request", side_effect=replies):
            result = self.post(
                "integrations/gemini/connect",
                {"key": "google-test-only", "employee": 0},
            )
        self.assertEqual(result["model"], "gemini-3.1-flash-lite")
        self.assertEqual(
            s.runtime.effective_text(0, {"mode": "demo"})[0]["model"],
            "auto-gemini-free",
        )
        self.assertEqual(self.state()["connection_status"][0]["status"], "configured")
