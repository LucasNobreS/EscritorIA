import base64
import json
import tempfile
import time
import unittest
import os
from pathlib import Path
from unittest.mock import patch
import test_server
from integrations import ConfigurationError, UncertainError

s = test_server.s
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1sAAAAASUVORK5CYII="
)


class Integrations(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = s.DATA
        s.DATA = Path(self.temp.name)
        s.init_db()
        self.r = s.runtime

    def tearDown(self):
        s.DATA = self.old
        self.temp.cleanup()

    def task(self, emp=2):
        with s.db() as c:
            tid = s.create_task(c, emp, "Teste de integração")
            return dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def job(self, kind="image", emp=2):
        t = self.task(emp)
        with s.db() as c:
            with (
                patch.object(self.r, "free_media_guard", return_value=None),
                patch.object(self.r, "require_key", return_value="test-unified-key"),
            ):
                jid = self.r.enqueue(c, emp, t, kind, {"prompt": "Teste"})
            return dict(
                c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            )

    def test_secret_write_only_and_model_routing(self):
        self.r.store_key("CODER_API_KEY", "segredo-teste")
        with s.db() as c:
            self.r.save_profile(
                c,
                {
                    "employee": 1,
                    "inherit": False,
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "code-model",
                    "key_name": "CODER_API_KEY",
                    "tools": ["code"],
                },
            )
        cfg, key = self.r.effective_text(1, {})
        self.assertEqual(key, "segredo-teste")
        self.assertEqual(cfg["model"], "code-model")
        self.assertNotIn("segredo-teste", json.dumps(self.r.public_state()))
        with s.db() as c:
            self.assertNotIn("segredo-teste", json.dumps(self.r.context(c, 1, None)))
        # Windows uses ACLs rather than POSIX permission bits.
        if os.name != "nt":
            self.assertEqual(
                (s.DATA / "credenciais.json").stat().st_mode & 0o777, 0o600
            )

    def test_permission_and_daily_cap(self):
        t = self.task(0)
        with s.db() as c:
            with self.assertRaises(ConfigurationError):
                self.r.enqueue(c, 0, t, "image", {"prompt": "x"})
            self.r.save_settings(c, {"limits": {"image": 1}})
        self.job()
        with self.assertRaises(ConfigurationError):
            self.job()

    def test_video_uses_unified_gateway_and_never_fal_queue(self):
        with s.db() as c:
            self.r.save_profile(c, dict(self.r.profile(c, 2), tools=["video"]))
            self.r.save_settings(c, {"video_gateway_enabled": "yes"})
        self.r.store_key("FREELLM_API_KEY", "unified-test")
        task = self.task(2)
        with s.db() as c:
            jid = self.r.enqueue(
                c, 2, task, "video", {"prompt": "Uma cena de escritório"}
            )
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            )
        import gateway_video

        with (
            patch.object(
                gateway_video,
                "generate",
                return_value=(b"\x00\x00\x00\x18ftypmp42", {"provider": "FreeLLMAPI"}),
            ) as call,
            patch.object(self.r, "request") as legacy,
            patch(
                "local_video.probe",
                return_value={
                    "duration": 6,
                    "width": 1280,
                    "height": 720,
                    "audio": False,
                },
            ),
        ):
            result = self.r.video(job, {"prompt": "Uma cena de escritório"})
        self.assertEqual(result["mime"], "video/mp4")
        self.assertEqual(call.call_args.args[0], "unified-test")
        legacy.assert_not_called()

    def test_social_review_and_publish_once(self):
        j = self.job()
        asset = self.r.save_asset(j, PNG, "image/png")
        with s.db() as c:
            self.r.save_settings(c, {"instagram_user_id": "123"})
            t = dict(
                c.execute("SELECT * FROM tasks WHERE id=?", (j["task"],)).fetchone()
            )
            pid = self.r.create_post(
                c, 2, t, {"asset_ids": [asset["asset_id"]], "caption": "Olá"}
            )
            self.assertEqual(
                c.execute("SELECT status FROM social_posts").fetchone()[0], "draft"
            )
            self.r.approve_post(c, pid)
            with self.assertRaises(ConfigurationError):
                self.r.approve_post(c, pid)
        with s.db() as c:
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE kind='instagram'").fetchone()
            )
        with (
            patch.object(
                self.r, "ensure_public", return_value="https://example.com/image.jpg"
            ),
            patch.object(self.r, "graph", return_value={"id": "container"}),
        ):
            self.assertIsNone(self.r.publish(job, {"post_id": pid}))
        with patch.object(
            self.r,
            "graph",
            side_effect=[{"status_code": "FINISHED"}, {"id": "published-1"}],
        ):
            result = self.r.publish(job, {"post_id": pid})
        self.assertTrue(result["published"])
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT status FROM social_posts").fetchone()[0], "published"
            )

    def test_ambiguous_publication_never_auto_restarts(self):
        j = self.job()
        a = self.r.save_asset(j, PNG, "image/png")
        with s.db() as c:
            self.r.save_settings(c, {"instagram_user_id": "123"})
            t = dict(
                c.execute("SELECT * FROM tasks WHERE id=?", (j["task"],)).fetchone()
            )
            pid = self.r.create_post(c, 2, t, {"asset_ids": [a["asset_id"]]})
            self.r.approve_post(c, pid)
            c.execute(
                "UPDATE social_posts SET container_id='container' WHERE id=?", (pid,)
            )
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE kind='instagram'").fetchone()
            )
        with patch.object(
            self.r, "graph", side_effect=[{"status_code": "FINISHED"}, TimeoutError()]
        ):
            with self.assertRaises(UncertainError):
                self.r.publish(job, {"post_id": pid})
        self.r.recover()
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT status FROM social_posts").fetchone()[0], "uncertain"
            )

    def test_recovery_restores_media_and_marks_running_uncertain(self):
        j = self.job()
        a = self.r.save_asset(j, PNG, "image/png")
        p = s.DATA / "midia" / f"tarefa-{j['task']}" / a["filename"]
        p.unlink()
        with s.db() as c:
            c.execute("UPDATE tool_jobs SET status='running'")
        self.r.recover()
        self.assertEqual(p.read_bytes(), PNG)
        with s.db() as c:
            self.assertEqual(
                c.execute("SELECT status FROM tool_jobs").fetchone()[0], "uncertain"
            )

    def test_server_room_reachable_and_panel_required(self):
        layout = s.default_layout()
        panel = next(o for o in layout if o["kind"] == "server_panel")
        self.assertTrue(s.route(690, 730, *s.local_point(panel, 75, 80), layout))
        with self.assertRaises(ValueError):
            s.validate_layout([o for o in layout if o["kind"] != "server_panel"])

    def test_invalid_endpoints_rejected(self):
        with s.db() as c:
            with self.assertRaises(ConfigurationError):
                self.r.save_profile(
                    c,
                    {
                        "employee": 1,
                        "inherit": False,
                        "base_url": "http://example.com",
                        "model": "x",
                    },
                )
        with self.assertRaises(ConfigurationError):
            self.r.fal_url("https://evil.example/queue")

    def test_code_container_has_no_network_or_credentials_and_caps_output(self):
        import io
        from unittest.mock import MagicMock

        j = self.job("code", 1)
        with s.db() as c:
            t = dict(
                c.execute("SELECT * FROM tasks WHERE id=?", (j["task"],)).fetchone()
            )
            s.save_task_files(
                c, t, [{"filename": "test.py", "content": "print(123)"}], "Código"
            )
        process = MagicMock()
        process.stdout = io.BytesIO(b"x" * 15000)
        process.returncode = 1
        with (
            patch("integrations.shutil.which", return_value="/usr/bin/docker"),
            patch("integrations.subprocess.run", return_value=MagicMock(returncode=0)),
            patch("integrations.subprocess.Popen", return_value=process) as popen,
        ):
            result = self.r.run_code(j, {"filename": "test.py"})
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("--read-only", command)
        self.assertIn("readonly", command[command.index("--mount") + 1])
        self.assertNotIn("--env", command)
        self.assertEqual(len(result["output"]), 12000)
        self.assertEqual(result["exit_code"], 1)

    def test_board_action_persists_and_tool_report_written(self):
        j = self.job("board", 0)
        result = self.r.office(
            j, {"operation": "write", "title": "Objetivo", "content": "Entregar amanhã"}
        )
        self.assertEqual(result["notes"][0]["title"], "Objetivo")
        self.r.finish_job(j, result)
        self.assertTrue(
            (
                s.DATA
                / "arquivos"
                / f"tarefa-{j['task']}"
                / f"ferramenta-{j['id']}.json"
            ).exists()
        )
