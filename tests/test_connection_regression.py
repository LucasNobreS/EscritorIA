"""Real local HTTP regressions: persisted chat, gateway connect, first request and town."""

import json
import threading
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import test_server
import freellm_gateway

s = test_server.s


class ConnectionRegression(unittest.TestCase):
    setUp = test_server.Integration.setUp
    tearDown = test_server.Integration.tearDown
    post = test_server.Integration.post
    state = test_server.Integration.state

    def poll(self, after):
        with urllib.request.urlopen(
            self.url + "/api/state?messages_after=" + str(after)
        ) as response:
            return json.load(response)

    def test_incremental_poll_with_query_returns_state_and_only_new_messages(self):
        with s.db() as c:
            first = c.execute(
                "INSERT INTO messages(employee,role,content) VALUES(0,'user','Primeira')"
            ).lastrowid
            second = c.execute(
                "INSERT INTO messages(employee,role,content) VALUES(0,'assistant','Resposta')"
            ).lastrowid
        data = self.poll(first)
        self.assertTrue(data["messages_delta"])
        self.assertEqual([m["id"] for m in data["messages"]], [second])
        self.assertEqual(data["token"], s.TOKEN)
        self.assertEqual(self.poll(second)["messages"], [])

    def test_invalid_cursor_falls_back_to_bootstrap_instead_of_404(self):
        data = self.poll("invalid")
        self.assertFalse(data["messages_delta"])
        self.assertTrue(data["employees"])

    def test_key_connect_first_chat_and_city_open_survive_existing_history(self):
        with s.db() as c:
            existing = c.execute(
                "INSERT INTO messages(employee,role,content) VALUES(0,'user','Histórico já existente')"
            ).lastrowid
        calls = []
        request_started = threading.Event()
        release_response = threading.Event()

        class Gateway(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                calls.append(request)
                if request["messages"][-1].get("content") != "Responda apenas OK.":
                    request_started.set()
                    release_response.wait(5)
                text = (
                    "OK"
                    if request["messages"][-1].get("content") == "Responda apenas OK."
                    else json.dumps(
                        {
                            "reply": "Olá! Recebi sua primeira solicitação.",
                            "actions": [],
                        }
                    )
                )
                raw = json.dumps(
                    {
                        "model": "modelo-de-teste",
                        "choices": [{"message": {"content": text}}],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
        thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{gateway.server_port}/v1"
        original_guard = freellm_gateway.is_local
        try:
            with (
                patch.object(freellm_gateway, "BASE", base),
                patch.object(
                    freellm_gateway,
                    "is_local",
                    side_effect=lambda url: url == base or original_guard(url),
                ),
            ):
                result = self.post(
                    "integrations/freellm/connect",
                    {
                        "key": "chave-unificada-de-teste",
                        "all_staff": True,
                        "images": False,
                    },
                )
                self.assertTrue(result["ok"])
                self.assertTrue(self.poll(existing)["employees"])
                self.post(
                    "task",
                    {
                        "employee": 0,
                        "title": "Olá, esta é minha primeira solicitação",
                        "intent": "chat",
                    },
                )
                with s.db() as c:
                    task = dict(
                        c.execute(
                            "SELECT * FROM tasks ORDER BY id DESC LIMIT 1"
                        ).fetchone()
                    )
                    x, y = s.station_position(s.world_state(c)["layout"], 0)
                    c.execute("UPDATE employees SET x=?,y=? WHERE id=0", (x, y))
                worker = threading.Thread(
                    target=s.process_task, args=(task,), daemon=True
                )
                worker.start()
                try:
                    self.assertTrue(
                        request_started.wait(3),
                        "A primeira chamada ao roteador não foi iniciada",
                    )
                    during = self.poll(existing)
                    self.assertEqual(
                        next(t for t in during["tasks"] if t["id"] == task["id"])[
                            "status"
                        ],
                        "executando",
                    )
                finally:
                    release_response.set()
                    worker.join(timeout=5)
                self.assertFalse(
                    worker.is_alive(),
                    "O processamento não terminou após a resposta do roteador",
                )
                data = self.poll(existing)
                self.assertTrue(
                    any(
                        "Recebi sua primeira solicitação" in m["content"]
                        for m in data["messages"]
                    )
                )
                self.assertEqual(
                    next(t for t in data["tasks"] if t["id"] == task["id"])["status"],
                    "concluida",
                )
                city = self.post("town/map", {})
                self.assertTrue(city["buildings"])
                last = max(m["id"] for m in data["messages"])
                self.assertEqual(self.poll(last)["messages"], [])
                self.assertEqual(len(calls), 2)
        finally:
            release_response.set()
            gateway.shutdown()
            gateway.server_close()
            thread.join(timeout=2)
