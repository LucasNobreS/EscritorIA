import base64
import json
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch
import test_game
import attachments

s = test_game.s


class Attachments(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def upload(self, name, content):
        return {
            "filename": name,
            "data": base64.b64encode(content.encode("utf-8")).decode(),
        }

    def test_edit_preserves_original_and_sends_full_source_to_colleagues(self):
        original = "<html>" + (" " * 3500) + "<button>Original</button></html>"
        self.post(
            "task",
            {
                "employee": 0,
                "title": "Mude o botão para Enviar",
                "intent": "project",
                "attachments": [
                    self.upload("index.html", original),
                    self.upload("style.css", "button {color:blue}"),
                ],
            },
        )
        with s.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
            child = s.create_task(c, 1, "Editar o HTML", parent=1)
            delegated = dict(
                c.execute("SELECT * FROM tasks WHERE id=?", (child,)).fetchone()
            )
        for t in (task, delegated):
            context = s.build_context(t["employee"], t["title"], t)[0][0]["content"]
            self.assertIn("<button>Original</button>", context)
            self.assertIn("button {color:blue}", context)
        edited = original.replace("Original", "Enviar")
        with patch.object(
            s,
            "generate",
            return_value={
                "reply": "Arquivo alterado",
                "files": [{"filename": "index.html", "content": edited}],
                "actions": [],
            },
        ):
            s.process_task(delegated)
        with s.db() as c:
            source = c.execute(
                "SELECT * FROM source_attachments WHERE filename='index.html'"
            ).fetchone()
            self.assertEqual(source["content"], original)
            self.assertEqual(
                c.execute(
                    "SELECT content FROM task_files WHERE task=?", (child,)
                ).fetchone()[0],
                edited,
            )
            aid = source["id"]
        self.assertEqual(self.raw("attachment?id=" + str(aid)).decode(), original)
        s.init_db()
        self.assertEqual(len(self.state()["attachments"]), 2)
        self.post(
            "task",
            {"employee": 1, "title": "Analise o mesmo arquivo", "reference_ids": [aid]},
        )
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM source_attachments").fetchone()[0], 3
            )

    def test_chat_attachments_do_not_become_project_deliveries(self):
        self.post(
            "task",
            {
                "employee": 1,
                "title": "Explique",
                "attachments": [self.upload("app.js", "const x=1;")],
            },
        )
        with s.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        with patch.object(
            s,
            "generate",
            return_value={"reply": "Uma constante", "files": [], "actions": []},
        ):
            s.process_task(task)
        s.recover_packages()
        self.assertEqual(self.state()["deliveries"], [])

    def test_invalid_attachments_are_rejected_atomically(self):
        bad = [
            self.upload("../index.html", "X"),
            {"filename": "x.txt", "data": "@@@"},
            self.upload("x.txt", "a" * 60001),
        ]
        for item in bad:
            with self.assertRaises(urllib.error.HTTPError):
                self.post(
                    "task", {"employee": 1, "title": "Editar", "attachments": [item]}
                )
        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "task",
                {
                    "employee": 1,
                    "title": "Editar",
                    "attachments": [
                        self.upload("a.txt", "X"),
                        self.upload("a.txt", "Y"),
                    ],
                },
            )
        self.assertEqual(self.state()["tasks"], [])

    def test_any_extension_is_preserved_and_unreadable_binary_is_labeled(self):
        self.post(
            "task",
            {
                "employee": 1,
                "title": "Analise",
                "attachments": [
                    {
                        "filename": "desenho.psd",
                        "data": base64.b64encode(b"8BPS\0\1").decode(),
                    }
                ],
            },
        )
        item = self.state()["attachments"][0]
        self.assertEqual(item["analysis_status"], "unavailable")
        self.assertEqual(self.raw("attachment?id=" + str(item["id"])), b"8BPS\0\1")

    def test_gemini_receives_uploaded_pdf_bytes_during_generation(self):
        raw = b"%PDF-1.7 test"
        self.post(
            "task",
            {
                "employee": 1,
                "title": "Analise o PDF",
                "attachments": [
                    {
                        "filename": "relatorio.pdf",
                        "data": base64.b64encode(raw).decode(),
                    }
                ],
            },
        )
        with s.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=1").fetchone())
        with (
            patch.object(
                s.runtime,
                "effective_text",
                return_value=(
                    {
                        "mode": "api",
                        "base_url": s.chat_models.GEMINI_BASE,
                        "model": "auto-gemini-free",
                    },
                    "test-key",
                ),
            ),
            patch.object(
                s.runtime,
                "text_request",
                return_value={
                    "choices": [
                        {
                            "message": {
                                "content": '{"reply":"Análise simulada","actions":[]}'
                            }
                        }
                    ]
                },
            ) as request,
        ):
            s.generate(1, task["title"], task)
        messages = request.call_args.args[2]
        inline = messages[-1]["inline_files"][0]
        self.assertEqual(inline["mime"], "application/pdf")
        self.assertEqual(base64.b64decode(inline["data"]), raw)

    def test_original_download_requires_auth_and_handles_unicode_filename(self):
        self.post(
            "task",
            {
                "employee": 1,
                "title": "Leia",
                "attachments": [self.upload("página-测试.html", "<p>Olá</p>")],
            },
        )
        aid = self.state()["attachments"][0]["id"]
        self.assertIn("Olá", self.raw("attachment?id=" + str(aid)).decode())
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.url + "/api/attachment?id=" + str(aid))
