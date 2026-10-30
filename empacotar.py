"""Create a clean source release, preserving the organized project layout."""

from pathlib import Path
import hashlib
import re
import zipfile

ROOT = Path(__file__).resolve().parent
SKIP = {
    "dados",
    "__pycache__",
    ".git",
    ".ruff_cache",
    ".build-env",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "release",
}
EXT = {
    ".py",
    ".js",
    ".cjs",
    ".css",
    ".html",
    ".md",
    ".txt",
    ".bat",
    ".ps1",
    ".vbs",
    ".png",
    ".gif",
    ".toml",
    ".ico",
    ".mp4",
    ".iss",
}


def build(destination):
    version = re.search(
        r"VERSION\s*=\s*[\"']([^\"']+)[\"']", (ROOT / "app/server.py").read_text()
    ).group(1)
    assert "h.version!=='" + version + "'" in (ROOT / "app/web/boot.js").read_text(), (
        "Versões inconsistentes"
    )
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if not p.is_file() or p.is_symlink() or any(x in SKIP for x in rel.parts):
                continue
            if rel.as_posix() in (
                ".github/workflows/windows-release.yml",
                ".github/workflows/tests.yml",
                ".gitignore",
            ):
                z.write(p, Path("EscritorIA") / rel)
                continue
            if any(x.startswith(".") for x in rel.parts):
                continue
            if p.name in ("config.json", "credenciais.json", "release-config.json"):
                continue
            if p.suffix.lower() not in EXT and rel.as_posix() not in (
                "app/config.example.json",
                "examples/motion-saas.json",
            ):
                continue
            if p.suffix.lower() in (".png", ".gif", ".mp4") and not (
                rel.as_posix().startswith("docs/media/")
                or rel.as_posix().startswith("app/web/brand/")
                or rel.as_posix() == "app/web/tutorial-freellm.mp4"
            ):
                continue
            z.write(p, Path("EscritorIA") / rel)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(build(args.destination))
