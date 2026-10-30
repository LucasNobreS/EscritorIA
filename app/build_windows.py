"""Build on Windows with a persistent diagnostic log and checked output."""

import os
from pathlib import Path
import subprocess
import sys
import json
import re
import shutil
import hashlib

ROOT = Path(__file__).resolve().parent


def build(installer=False, headless=False):
    if sys.platform != "win32":
        raise RuntimeError("O aplicativo Windows precisa ser gerado no Windows.")
    if sys.version_info < (3, 10):
        raise RuntimeError("Instale Python 3.10 ou superior.")
    log_path = ROOT / "gerar-app.log"
    with log_path.open("w", encoding="utf-8") as log:

        def run(args):
            print("Executando:", " ".join(map(str, args)), flush=True)
            log.write("Executando: " + " ".join(map(str, args)) + "\n")
            log.flush()
            result = subprocess.run(
                list(map(str, args)), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
            )
            if result.returncode:
                raise RuntimeError(
                    "Etapa falhou. Envie o arquivo gerar-app.log para diagnostico."
                )

        print(
            "Gerando aplicativo. Pode levar varios minutos; acompanhe gerar-app.log.",
            flush=True,
        )
        run([sys.executable, "-m", "venv", ROOT / ".build-env"])
        python = ROOT / ".build-env" / "Scripts" / "python.exe"
        run([python, "-m", "pip", "install", "--upgrade", "pip"])
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "pywebview",
                "pyinstaller",
                "Pillow",
                "pywin32",
                "playwright==1.64.1",
            ]
        )
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
        run([python, "-m", "playwright", "install", "chromium", "--no-shell"])
        version = re.search(
            r"VERSION\s*=\s*[\"']([^\"']+)[\"']",
            (ROOT / "server.py").read_text(encoding="utf-8"),
        ).group(1)
        expected = re.search(
            r"h.version!=='([^']+)'",
            (ROOT / "web" / "boot.js").read_text(encoding="utf-8"),
        ).group(1)
        if version != expected:
            raise RuntimeError("Versoes diferentes entre interface e servidor.")
        extra = []
        repo = os.environ.get("ATELIE_RELEASE_REPO", "").strip()
        if repo:
            from app_updates import repository

            config = ROOT / ".build-env" / "release-config.json"
            config.write_text(
                json.dumps({"repository": repository(repo)}), encoding="utf-8"
            )
            extra = ["--add-data", str(config) + ";."]
        run(
            [
                python,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onedir",
                "--windowed",
                "--name",
                "EscritorIA",
                "--icon",
                str(ROOT / "web" / "brand" / "escritoria.ico"),
                "--add-data",
                "web;web",
                "--collect-all",
                "webview",
                "--collect-all",
                "playwright",
                "--hidden-import",
                "PIL.Image",
                "--hidden-import",
                "PIL.ImageDraw",
                "--hidden-import",
                "PIL.ImageFont",
                "--hidden-import",
                "win32com.client",
                *extra,
                "desktop.py",
            ]
        )
        output = ROOT / "dist" / "EscritorIA"
        if (
            not (output / "EscritorIA.exe").is_file()
            or not (output / "_internal" / "web" / "index.html").is_file()
        ):
            raise RuntimeError(
                "Compilacao incompleta: faltam o EXE ou os recursos web."
            )
        if not any(
            (
                output
                / "_internal"
                / "playwright"
                / "driver"
                / "package"
                / ".local-browsers"
            ).glob("chromium-*/**/chrome.exe")
        ):
            raise RuntimeError(
                "Compilacao incompleta: Chromium nao foi incluido. Confira gerar-app.log."
            )
        shutil.copy2(
            output / "EscritorIA.exe", output / "AtelieIA.exe"
        )  # Compatibility with existing shortcuts.
        (output / "Instalar.bat").write_bytes(
            b'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0EscritorIA.exe" --install\r\n'
        )
        print("Aplicativo gerado em:", output, flush=True)
        print("Abra Instalar.bat nessa pasta para criar os atalhos.", flush=True)
        if installer:
            compiler = shutil.which("ISCC.exe")
            if not compiler:
                compiler = str(
                    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
                    / "Inno Setup 6"
                    / "ISCC.exe"
                )
            if not Path(compiler).is_file():
                raise RuntimeError(
                    "Instale Inno Setup 6 no computador de compilacao: https://jrsoftware.org/isdl.php"
                )
            run([compiler, "/DAppVersion=" + version, ROOT / "installer.iss"])
            setup = ROOT / "release" / "EscritorIA-Setup.exe"
            if not setup.is_file():
                raise RuntimeError("O compilador nao gerou o instalador.")
            shutil.copy2(
                setup, setup.parent / "AtelieIA-Setup.exe"
            )  # Update bridge for older installed clients.
            (setup.parent / "SHA256SUMS.txt").write_text(
                "".join(
                    hashlib.sha256(setup.read_bytes()).hexdigest() + "  " + name + "\n"
                    for name in (setup.name, "AtelieIA-Setup.exe")
                ),
                encoding="utf-8",
            )
            output = setup.parent
            print("Instalador pronto:", setup, flush=True)
        if not headless:
            os.startfile(str(output))


if __name__ == "__main__":
    try:
        build(installer="--installer" in sys.argv, headless="--headless" in sys.argv)
    except Exception as error:
        print("ERRO:", error, flush=True)
        raise SystemExit(1)
