"""Shared request admission for employees, browser agents and background NPCs."""

import threading
import time
from collections import deque
from datetime import datetime, timezone, timedelta


class RequestQueue:
    """FIFO admission; background work never overtakes a waiting foreground call."""

    def __init__(self, capacity=1):
        self.condition = threading.Condition()
        self.waiting = deque()
        self.capacity = capacity
        self.active = 0

    def acquire(self, blocking=True):
        with self.condition:
            if not blocking and (self.active or self.waiting):
                return False
            ticket = object()
            self.waiting.append(ticket)
            try:
                while self.active >= self.capacity or self.waiting[0] is not ticket:
                    self.condition.wait()
                self.waiting.popleft()
                self.active += 1
                self.condition.notify_all()
                return True
            except BaseException:
                self.waiting.remove(ticket)
                self.condition.notify_all()
                raise

    def release(self):
        with self.condition:
            if not self.active:
                raise RuntimeError("Fila liberada sem chamada ativa")
            self.active -= 1
            self.condition.notify_all()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class Budget:
    def __init__(self, db):
        self.db = db
        self.lock = RequestQueue(2)

    @staticmethod
    def schema(c):
        c.execute(
            "CREATE TABLE IF NOT EXISTS text_budget(day TEXT PRIMARY KEY,requests INTEGER DEFAULT 0,input_estimate INTEGER DEFAULT 0,output_reserved INTEGER DEFAULT 0)"
        )

    @staticmethod
    def day():
        return datetime.now(timezone(timedelta(hours=-3))).date().isoformat()

    def reserve(self, messages, output, limit):
        # Conservative planning estimate, not provider billing or tokenizer measurement.
        size = sum(len(str(m.get("content", ""))) for m in messages)
        if size > 160000:
            raise ValueError(
                "Contexto maior que 160 mil caracteres. Divida a demanda ou reduza os anexos."
            )
        with self.db() as c:
            c.execute("INSERT OR IGNORE INTO text_budget(day) VALUES(?)", (self.day(),))
            if not c.execute(
                "UPDATE text_budget SET requests=requests+1,input_estimate=input_estimate+?,output_reserved=output_reserved+? WHERE day=? AND requests<?",
                ((size + 2) // 3, int(output), self.day(), int(limit)),
            ).rowcount:
                raise ValueError(
                    "Limite diário compartilhado de chamadas de IA atingido. Ajuste o limite em Configurar IA ou aguarde o próximo dia em Brasília."
                )

    def status(self):
        with self.db() as c:
            row = c.execute(
                "SELECT * FROM text_budget WHERE day=?", (self.day(),)
            ).fetchone()
            return (
                dict(row)
                if row
                else {
                    "day": self.day(),
                    "requests": 0,
                    "input_estimate": 0,
                    "output_reserved": 0,
                }
            )
