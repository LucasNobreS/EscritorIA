"""Portable SQLite snapshot plus configuration; credentials are deliberately excluded."""

import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

FORMAT = "atelie-office-backup-v1"
MAX_SIZE = 512 * 1024 * 1024


def create(data, state_root, version):
    output = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="atelie-backup-") as temp:
        snapshot = Path(temp) / "escritorio.db"
        with (
            sqlite3.connect(Path(data) / "escritorio.db") as source,
            sqlite3.connect(snapshot) as target,
        ):
            source.backup(target)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "escritorio.db")
            config = Path(state_root) / "config.json"
            if config.is_file():
                settings = json.loads(config.read_text("utf-8"))
                # The legacy config must never carry literal API credentials into the backup.
                allowed = {
                    k: settings[k]
                    for k in ("mode", "base_url", "model", "max_tokens")
                    if k in settings
                }
                archive.writestr("config.json", json.dumps(allowed))
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": FORMAT,
                        "version": version,
                        "created": time.time(),
                        "credentials": False,
                        "contents": "SQLite: equipe, conversas, memórias, planta, cidade, anexos e mídias; configuração básica.",
                    }
                ),
            )
    return output.getvalue()


def restore(path, data, state_root, current_version):
    """Caller must own the data-directory lock and have no open database connections."""
    data = Path(data)
    state_root = Path(state_root)
    with tempfile.TemporaryDirectory(prefix="atelie-restore-") as temp:
        temp = Path(temp)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if (
                len(set(names)) != len(names)
                or set(names) - {"manifest.json", "escritorio.db", "config.json"}
                or not {"manifest.json", "escritorio.db"} <= set(names)
            ):
                raise ValueError("Pacote de backup inválido.")
            if sum(i.file_size for i in archive.infolist()) > MAX_SIZE:
                raise ValueError("Backup descompactado acima de 512 MB.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != FORMAT:
                raise ValueError("Formato de backup não reconhecido.")
            version = lambda value: tuple(int(n) for n in str(value).split("."))
            if version(manifest.get("version", "999")) > version(current_version):
                raise ValueError(
                    "Atualize o EscritorIA antes de restaurar um backup de uma versão mais recente."
                )
            snapshot = temp / "escritorio.db"
            snapshot.write_bytes(archive.read("escritorio.db"))
            with sqlite3.connect(snapshot) as check:
                if check.execute("PRAGMA user_version").fetchone()[0] > 1:
                    raise ValueError(
                        "O banco usa um esquema mais recente. Atualize o EscritorIA antes de restaurar."
                    )
                if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError(
                        "Banco do backup não passou na verificação de integridade."
                    )
                tables = {
                    r[0]
                    for r in check.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if (
                    not {
                        "employees",
                        "tasks",
                        "messages",
                        "game_world",
                        "assets",
                        "source_attachments",
                    }
                    <= tables
                ):
                    raise ValueError("O backup não contém um escritório completo.")
            config = archive.read("config.json") if "config.json" in names else None
            if config is not None:
                cfg = json.loads(config)
                if not isinstance(cfg, dict) or set(cfg) - {
                    "mode",
                    "base_url",
                    "model",
                    "max_tokens",
                }:
                    raise ValueError("Configuração inválida no backup.")
        data.mkdir(parents=True, exist_ok=True)
        original = data / "escritorio.db"
        # Consolidate an existing WAL before retaining the rollback copy.
        if original.exists():
            with sqlite3.connect(original) as old:
                old.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        safety = data / ("antes-restauracao-" + str(time.time_ns()))
        safety.mkdir()
        for name in ("escritorio.db", "escritorio.db-wal", "escritorio.db-shm"):
            source = data / name
            if source.exists():
                shutil.copy2(source, safety / name)
        if (state_root / "config.json").exists():
            shutil.copy2(state_root / "config.json", safety / "config.json")
        staged = data / ".restauracao.db"
        shutil.copy2(snapshot, staged)
        for name in ("escritorio.db-wal", "escritorio.db-shm"):
            (data / name).unlink(missing_ok=True)
        os.replace(staged, original)
        try:
            if config is not None:
                cfg_tmp = state_root / ".config-restauracao.json"
                cfg_tmp.write_bytes(config)
                os.replace(cfg_tmp, state_root / "config.json")
        except OSError:
            if (safety / "escritorio.db").exists():
                shutil.copy2(safety / "escritorio.db", original)
            raise
    return safety


def restore_dialog(state_root, version):
    from tkinter import Tk, filedialog, messagebox
    import runtime_health

    root = Tk()
    root.withdraw()
    state_root = Path(state_root)
    data = state_root / "dados"
    data.mkdir(parents=True, exist_ok=True)
    lock = runtime_health.Health(data)
    try:
        lock.acquire()
        path = filedialog.askopenfilename(
            title="Restaurar escritório — escolha o backup ZIP",
            filetypes=[("Backup do EscritorIA", "*.zip")],
        )
        if not path:
            return 0
        if not messagebox.askyesno(
            "Restaurar escritório",
            "Substituir o escritório atual pelo backup? Uma cópia de segurança será guardada. As chaves locais serão preservadas; talvez seja necessário reconectar os serviços.",
        ):
            return 0
        safety = restore(path, data, state_root, version)
        messagebox.showinfo(
            "Escritório restaurado",
            "Restauração concluída. Abra o EscritorIA normalmente.\nCópia anterior: "
            + str(safety),
        )
        return 0
    except Exception as error:
        messagebox.showerror("Não foi possível restaurar", str(error))
        return 1
    finally:
        if lock.instance:
            lock.instance.close()
        root.destroy()


if __name__ == "__main__":
    import re

    home = Path(__file__).parent
    version = re.search(
        r"VERSION\s*=\s*[\"']([^\"']+)[\"']", (home / "server.py").read_text()
    ).group(1)
    raise SystemExit(
        restore_dialog(Path(os.environ.get("ATELIE_STATE_ROOT", str(home))), version)
    )
