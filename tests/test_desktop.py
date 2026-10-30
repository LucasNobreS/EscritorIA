import os
import sys
import tempfile
import types
import sqlite3
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import desktop
import windows_install


class Desktop(unittest.TestCase):
    def test_lifecycle_uses_user_data_and_stops_http(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(":memory:")
            connection.row_factory = sqlite3.Row
            connection.execute(
                "CREATE TABLE tool_jobs(id INTEGER, kind TEXT, status TEXT)"
            )
            connection.execute(
                "INSERT INTO tool_jobs VALUES(7,'video_local','running')"
            )
            http = Mock(server_port=8766)
            backend = types.SimpleNamespace(
                validate_web_files=Mock(),
                create_local_server=Mock(return_value=http),
                health=Mock(),
                start_workers=Mock(),
                navigation=Mock(),
                worker=Mock(),
                runtime=Mock(),
                town=Mock(),
                db=Mock(return_value=connection),
                paused=False,
            )
            view = Mock(settings={})
            old_stdout = sys.stdout
            fake_menu = types.SimpleNamespace(Menu=Mock(), MenuAction=Mock())
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": directory}),
                patch.dict(
                    sys.modules,
                    {"server": backend, "webview": view, "webview.menu": fake_menu},
                ),
            ):
                self.assertEqual(desktop.main(), 0)
                self.assertEqual(
                    os.environ["ATELIE_STATE_ROOT"], str(desktop.state_root())
                )
            view.create_window.assert_called_once()
            self.assertEqual(
                view.create_window.call_args.args[1], "http://127.0.0.1:8766/"
            )
            http.shutdown.assert_called_once()
            http.server_close.assert_called_once()
            self.assertTrue(backend.paused)
            backend.runtime.cancel_video.assert_called_once_with(
                connection, 7, "Aplicativo encerrado pelo usuario."
            )
            self.assertIs(sys.stdout, old_stdout)
            connection.close()

    def test_complete_application_copy_preserves_separate_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "EscritorIA.exe").write_bytes(b"exe")
            (source / "_internal").mkdir()
            (source / "_internal" / "resource").write_text("resource")
            data = root / "AtelieIA" / "dados"
            data.mkdir(parents=True)
            (data / "memory").write_text("keep")
            target = root / "Programs" / "AtelieIA"
            result = windows_install.copy_application(source, target)
            self.assertTrue(result.is_file())
            self.assertEqual(
                (target / "_internal" / "resource").read_text(), "resource"
            )
            self.assertEqual((data / "memory").read_text(), "keep")
            self.assertEqual(windows_install.copy_application(target, target), result)

    def test_incomplete_package_rejected_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "Pacote incompleto"):
                windows_install.copy_application(root, root / "target")
            self.assertFalse((root / "target").exists())

    def test_installer_uses_new_version_folder(self):
        message = Mock(return_value=1)
        fake_ctypes = types.SimpleNamespace(
            windll=types.SimpleNamespace(
                user32=types.SimpleNamespace(MessageBoxW=message)
            )
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"LOCALAPPDATA": directory}),
            patch.dict(sys.modules, {"ctypes": fake_ctypes}),
            patch.object(sys, "frozen", True, create=True),
            patch.object(
                windows_install,
                "copy_application",
                return_value=Path(directory) / "app.exe",
            ) as copy,
            patch.object(windows_install, "create_shortcuts"),
            patch.object(windows_install.subprocess, "Popen"),
        ):
            self.assertEqual(windows_install.install_main(), 0)
            target = copy.call_args.args[1]
            self.assertEqual(
                target.parent, Path(directory) / "Programs" / "AtelieIA" / "versions"
            )
            self.assertEqual(windows_install.install_main(), 0)
            self.assertNotEqual(target, copy.call_args.args[1])

    def test_start_failure_restores_logging(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"LOCALAPPDATA": directory}),
            patch.dict(sys.modules, {"webview": None}),
            patch.object(sys, "platform", "linux"),
        ):
            old_stdout = sys.stdout
            self.assertEqual(desktop.main(), 1)
            self.assertIs(sys.stdout, old_stdout)
