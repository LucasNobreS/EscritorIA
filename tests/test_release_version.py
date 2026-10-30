import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"


class ReleaseVersion(unittest.TestCase):
    def test_interface_and_server_expect_same_version(self):
        version = re.search(
            r"VERSION\s*=\s*[\"']([^\"']+)[\"']",
            (ROOT / "server.py").read_text(encoding="utf-8"),
        ).group(1)
        boot = (ROOT / "web" / "boot.js").read_text(encoding="utf-8")
        expected = re.search(r"h.version!=='([^']+)'", boot).group(1)
        self.assertEqual(expected, version)
        self.assertIn(
            "v" + version, (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        )

    def test_restore_entrypoint_matches_release_version(self):
        version = re.search(
            r"VERSION\s*=\s*[\"']([^\"']+)[\"']", (ROOT / "server.py").read_text()
        ).group(1)
        self.assertIn(version, (ROOT / "desktop.py").read_text())
