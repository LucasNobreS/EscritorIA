"""Install the complete frozen application and create native Windows shortcuts."""

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


def copy_application(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not (source / "EscritorIA.exe").is_file() or not (source / "_internal").is_dir():
        raise RuntimeError(
            "Pacote incompleto. Extraia a pasta compilada inteira, incluindo _internal."
        )
    if source != destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination / "EscritorIA.exe"


def create_shortcuts(executable):
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    for location in ("Desktop", "Programs"):
        shortcut = shell.CreateShortcut(
            str(Path(shell.SpecialFolders(location)) / "EscritorIA.lnk")
        )
        shortcut.TargetPath = str(executable)
        shortcut.WorkingDirectory = str(executable.parent)
        shortcut.IconLocation = str(executable) + ",0"
        shortcut.Save()

    restore = shell.CreateShortcut(
        str(Path(shell.SpecialFolders("Programs")) / "Restaurar EscritorIA.lnk")
    )
    restore.TargetPath = str(executable)
    restore.Arguments = "--restore"
    restore.WorkingDirectory = str(executable.parent)
    restore.IconLocation = str(executable) + ",0"
    restore.Save()


def install_main():
    import ctypes

    message = ctypes.windll.user32.MessageBoxW
    if not getattr(sys, "frozen", False):
        message(
            None, "Gere o EXE primeiro com Gerar-app-Windows.bat.", "EscritorIA", 16
        )
        return 1
    if (
        message(
            None,
            "Instalar ou atualizar o EscritorIA e criar atalhos? Feche outras janelas do EscritorIA antes de continuar. Seus dados ficam preservados.",
            "EscritorIA",
            1,
        )
        != 1
    ):
        return 0
    try:
        # Install beside older builds: an open EXE or a read-only resource from
        # a previous build must never be overwritten. User data lives elsewhere.
        target = (
            Path(os.environ["LOCALAPPDATA"])
            / "Programs"
            / "AtelieIA"
            / "versions"
            / uuid.uuid4().hex
        )
        executable = copy_application(Path(sys.executable).parent, target)
        create_shortcuts(executable)
        subprocess.Popen([str(executable)], cwd=str(target))
        return 0
    except Exception as error:
        message(
            None,
            "Falha na instalacao: "
            + str(error)
            + "\nFeche o EscritorIA e tente novamente. O aplicativo tambem pode ser aberto diretamente na pasta compilada.",
            "EscritorIA",
            16,
        )
        return 1
