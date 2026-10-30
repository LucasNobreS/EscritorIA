"""Native desktop entry point; packaged resources are separate from user data."""

import os
import sys
import threading
import traceback
from pathlib import Path


def state_root():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AtelieIA"


def main():
    data = state_root()
    data.mkdir(parents=True, exist_ok=True)
    os.environ["ATELIE_STATE_ROOT"] = str(data)
    os.environ["OFFICE_NO_BROWSER"] = "1"
    # The windowed executable has no console. Keep diagnostics outside resources.
    log = (data / "desktop.log").open("a", encoding="utf-8", buffering=1)
    previous_stdout, previous_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = log
    http = None
    serving = None
    try:
        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["ALLOW_FILE_URLS"] = False
        import server
        from webview.menu import Menu, MenuAction
        from app_updates import show_updates

        def check_updates():
            threading.Thread(
                target=show_updates, args=(server.VERSION,), daemon=True
            ).start()

        menu = [
            Menu("EscritorIA", [MenuAction("Verificar atualizacoes", check_updates)])
        ]
        server.health.acquire()
        server.validate_web_files()
        http = server.create_local_server()
        server.start_workers()
        serving = threading.Thread(target=http.serve_forever, daemon=True)
        serving.start()
        webview.create_window(
            "EscritorIA",
            f"http://127.0.0.1:{http.server_port}/",
            width=1280,
            height=800,
            min_size=(960, 600),
        )
        webview.start(
            gui="edgechromium" if sys.platform == "win32" else None,
            private_mode=False,
            storage_path=str(data / "webview"),
            menu=menu,
        )
    except Exception as error:
        traceback.print_exc()
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "Nao foi possivel abrir o EscritorIA: "
                + str(error)
                + "\nConfira desktop.log em "
                + str(data)
                + "\nVerifique se Microsoft Edge WebView2 Runtime esta instalado.",
                "EscritorIA",
                16,
            )
        return 1
    finally:
        if http is not None:
            # Stop accepting work and let video cancellation callbacks kill FFmpeg.
            server.paused = True
            try:
                with server.db() as c:
                    for row in c.execute(
                        "SELECT id FROM tool_jobs WHERE kind IN ('video_local','video') AND status IN ('queued','running')"
                    ).fetchall():
                        server.runtime.cancel_video(
                            c, row["id"], "Aplicativo encerrado pelo usuario."
                        )
            except Exception:
                traceback.print_exc()
            if serving is not None:
                http.shutdown()
                serving.join(timeout=3)
            http.server_close()
        log.flush()
        sys.stdout, sys.stderr = previous_stdout, previous_stderr
        log.close()
    return 0


if __name__ == "__main__":
    if "--restore" in sys.argv:
        import office_backup

        os.environ["ATELIE_STATE_ROOT"] = str(state_root())
        raise SystemExit(office_backup.restore_dialog(state_root(), "0.45.0"))
    if "--install" in sys.argv:
        from windows_install import install_main

        raise SystemExit(install_main())
    raise SystemExit(main())
