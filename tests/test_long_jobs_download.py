import io
import os
import urllib.request
import zipfile
import unittest
from unittest.mock import patch
import test_server
import freellm_gateway

s = test_server.s


class LongJobsDownload(unittest.TestCase):
    setUp = test_server.Integration.setUp
    tearDown = test_server.Integration.tearDown

    def test_long_text_timeout_is_used_by_transport(self):
        cfg = {"base_url": freellm_gateway.BASE, "model": "auto", "max_tokens": 0}
        with (
            patch.dict(os.environ, {"ATELIE_TEXT_TIMEOUT_SECONDS": "1800"}),
            patch.object(freellm_gateway, "request", return_value={}) as call,
        ):
            s.runtime._text_request(cfg, "test", [], 0)
        self.assertEqual(call.call_args.kwargs["timeout"], 1800)

    def test_timeout_is_configurable_and_invalid_values_are_bounded(self):
        for value, expected in [
            ("3600", 3600),
            ("invalid", 1800),
            ("0", 120),
            ("99999", 7200),
        ]:
            with patch.dict(os.environ, {"ATELIE_TEXT_TIMEOUT_SECONDS": value}):
                self.assertEqual(freellm_gateway.text_timeout(), expected)

    def test_single_file_download_keeps_employee_filename_and_content(self):
        with s.db() as c:
            tid = s.create_task(c, 1, "Página")
            c.execute(
                "INSERT INTO task_files(task,employee,filename,content,created) VALUES(?,?,?,?,0)",
                (tid, 1, "pagina-cliente.html", "<h1>Olá</h1>"),
            )
        req = urllib.request.Request(
            self.url + "/api/task-download?id=" + str(tid),
            headers={"X-Office-Token": s.TOKEN},
        )
        with urllib.request.urlopen(req) as response:
            self.assertIn(
                "pagina-cliente.html", response.headers["Content-Disposition"]
            )
            self.assertEqual(response.read().decode(), "<h1>Olá</h1>")

    def test_multiple_files_preserve_names_inside_zip(self):
        with s.db() as c:
            tid = s.create_task(c, 1, "Página")
            for name in ["index.html", "estilo.css"]:
                c.execute(
                    "INSERT INTO task_files(task,employee,filename,content,created) VALUES(?,?,?,?,0)",
                    (tid, 1, name, "conteúdo"),
                )
        req = urllib.request.Request(
            self.url + "/api/task-download?id=" + str(tid),
            headers={"X-Office-Token": s.TOKEN},
        )
        with urllib.request.urlopen(req) as response:
            self.assertIn("index.zip", response.headers["Content-Disposition"])
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                self.assertEqual(z.namelist(), ["index.html", "estilo.css"])
