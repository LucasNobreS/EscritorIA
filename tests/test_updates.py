import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app_updates


class Updates(unittest.TestCase):
    def test_unconfigured_channel_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(app_updates.check("0.24.1", directory)["configured"])

    def test_published_installer_and_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "release-config.json").write_text(
                json.dumps({"repository": "example/atelie"})
            )
            payload = {
                "tag_name": "v0.25.0",
                "assets": [
                    {
                        "name": "EscritorIA-Setup.exe",
                        "browser_download_url": "https://untrusted.invalid/file",
                    }
                ],
            }
            with patch(
                "app_updates.urllib.request.urlopen",
                return_value=io.BytesIO(json.dumps(payload).encode()),
            ):
                result = app_updates.check("0.24.1", directory)
            self.assertTrue(result["available"])
            self.assertEqual(
                result["url"],
                "https://github.com/example/atelie/releases/download/v0.25.0/EscritorIA-Setup.exe",
            )
            with patch(
                "app_updates.urllib.request.urlopen",
                return_value=io.BytesIO(json.dumps(payload).encode()),
            ):
                self.assertFalse(app_updates.check("0.25.0", directory)["available"])

    def test_missing_installer_cannot_be_offered(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "release-config.json").write_text(
                json.dumps({"repository": "example/atelie"})
            )
            with patch(
                "app_updates.urllib.request.urlopen",
                return_value=io.BytesIO(b'{"tag_name":"v0.25.0","assets":[]}'),
            ):
                with self.assertRaisesRegex(ValueError, "instalador"):
                    app_updates.check("0.24.1", directory)

    def test_only_public_github_repository_and_simple_versions(self):
        for value in ("https://example.com/a/b", "a/b/c", "a/b?token=x", "../x", ""):
            with self.assertRaises(ValueError):
                app_updates.repository(value)
        for value in ("v1.2.3/other", "v1.0.0-beta", "https://example.com"):
            with self.assertRaises(ValueError):
                app_updates.version(value)
        self.assertGreater(
            app_updates.version("v0.10.0"), app_updates.version("v0.9.9")
        )
