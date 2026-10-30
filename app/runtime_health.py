"""Worker supervision and a process-lifetime lock for one local data directory."""

import atexit
import logging
import logging.handlers
import os
import threading
import time


class Health:
    def __init__(self, data):
        self.data = data
        self.lock = threading.Lock()
        self.states = {}
        self.threads = {}
        self.instance = None
        self.log = logging.getLogger("atelie.workers." + str(data))
        self.log.setLevel(logging.ERROR)
        handler = logging.handlers.RotatingFileHandler(
            data / "runtime.log", maxBytes=512000, backupCount=2, encoding="utf-8"
        )
        self.log.addHandler(handler)

    def acquire(self):
        file = (self.data / "instance.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                file.seek(0)
                file.write(b"0")
                file.flush()
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise RuntimeError(
                "Este escritório já está aberto. Use a janela existente; não abra duas instâncias sobre os mesmos dados."
            ) from None
        self.instance = file
        atexit.register(file.close)

    def start(self, name, target):
        with self.lock:
            if name in self.threads and self.threads[name].is_alive():
                return

            def supervise():
                while True:
                    with self.lock:
                        self.states[name] = {
                            "status": "running",
                            "started": time.time(),
                        }
                    try:
                        target()
                        raise RuntimeError("O serviço encerrou antes do esperado.")
                    except Exception:
                        self.log.exception("Serviço %s interrompido; reiniciando", name)
                        with self.lock:
                            self.states[name] = {
                                "status": "restarting",
                                "failed_at": time.time(),
                            }
                        time.sleep(2)

            thread = threading.Thread(
                target=supervise, name="EscritorIA-" + name, daemon=True
            )
            self.threads[name] = thread
            thread.start()

    def state(self):
        with self.lock:
            return {
                k: dict(v, alive=self.threads[k].is_alive())
                for k, v in self.states.items()
            }
