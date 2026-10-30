import asyncio
import concurrent.futures
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
import test_server
import browser_agent as b


class FakePage:
    def __init__(self):
        self.url = ""

    async def goto(self, url, **kw):
        self.url = url

    async def evaluate(self, *a):
        return {
            "text": "Conteúdo principal da fonte",
            "truncated": False,
            "controls": [],
            "links": [{"text": "Referência", "url": self.url + "outra"}],
            "headings": [],
            "scroll_y": 0,
        }

    def locator(self, q):
        return self

    async def wait_for(self, **kw):
        pass

    async def title(self):
        return "Fonte pública"

    async def inner_text(self, **kw):
        return "Informações verificáveis desta fonte."

    async def evaluate_all(self, *a):
        return [{"text": "Referência", "url": self.url + "outra"}]

    async def screenshot(self, **kw):
        return b"PNG"


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    def set_default_timeout(self, *a):
        pass

    async def route(self, *a):
        self.guard = a[1]

    async def route_web_socket(self, *a):
        pass

    def on(self, *a):
        pass

    async def new_page(self):
        p = FakePage()
        self.pages.append(p)
        return p

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.contexts = []

    async def new_context(self, **kw):
        c = FakeContext()
        self.contexts.append(c)
        return c

    async def close(self):
        pass


class BrowserValidation(unittest.TestCase):
    def test_public_urls_reject_private_network_credentials_and_domains(self):
        for ip in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.2"]:
            with patch.object(
                b.socket, "getaddrinfo", return_value=[(0, 0, 0, "", (ip, 443))]
            ):
                with self.assertRaises(b.BrowserError):
                    b.public_url("https://example.com")
        for url in [
            "file:///etc/passwd",
            "https://u:p@example.com",
            "http://example.com:8765",
            "javascript:alert(1)",
        ]:
            with self.assertRaises(b.BrowserError):
                b.public_url(url)
        with self.assertRaises(b.BrowserError):
            b.public_url("https://other.com", {"example.com"})

    def test_budget_and_parameters(self):
        self.assertEqual(
            b.validate(
                {
                    "urls": ["https://example.com"],
                    "goal": "Consultar fonte",
                    "steps": 999,
                }
            )["steps"],
            24,
        )
        with self.assertRaises(b.BrowserError):
            b.validate({"urls": [], "goal": "abc"})

    def test_two_sessions_isolated_third_waits_and_close_cleans_up(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(b, "installed", return_value=True),
            patch.object(b, "public_url", side_effect=lambda u, hosts=None: u),
        ):
            service = b.BrowserService(folder)
            engine = FakeBrowser()
            service._engine = AsyncMock(return_value=engine)
            release = threading.Event()
            both = threading.Event()
            lock = threading.Lock()
            count = [0]

            def decide(obs):
                with lock:
                    count[0] += 1
                    if count[0] == 2:
                        both.set()
                release.wait(3)
                return {
                    "action": "finish",
                    "outcome": "success",
                    "report": "Relatório com fontes.",
                    "evidence": [
                        {
                            "url": obs["page"]["url"],
                            "quote": "Conteúdo principal da fonte",
                        }
                    ],
                }

            params = {
                "urls": ["https://example.com"],
                "goal": "Consultar fonte",
                "steps": 2,
            }
            try:
                first = service.submit(
                    {"id": 1, "employee": 0}, params, decide, lambda: True
                )
                second = service.submit(
                    {"id": 2, "employee": 1}, params, decide, lambda: True
                )
                self.assertTrue(both.wait(3))
                self.assertEqual(len(service.status()["active"]), 2)
                self.assertIsNone(
                    service.submit(
                        {"id": 3, "employee": 2}, params, decide, lambda: True
                    )
                )
                release.set()
                self.assertTrue(first.result(5)["complete"])
                self.assertTrue(second.result(5)["complete"])
                self.assertEqual(len(engine.contexts), 2)
                self.assertIsNot(engine.contexts[0], engine.contexts[1])
                self.assertTrue(all(c.closed for c in engine.contexts))
                self.assertEqual(service.status()["active"], [])
            finally:
                release.set()
                service.close()

    def test_permission_revocation_and_stop_prevent_next_page(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(b, "installed", return_value=True),
            patch.object(b, "public_url", side_effect=lambda u, hosts=None: u),
        ):
            service = b.BrowserService(folder)
            engine = FakeBrowser()
            service._engine = AsyncMock(return_value=engine)
            try:
                future = service.submit(
                    {"id": 1, "employee": 0},
                    {"urls": ["https://example.com"], "goal": "Consultar fonte"},
                    lambda o: {"action": "finish", "report": "Não deveria executar"},
                    lambda: False,
                )
                with self.assertRaises(b.BrowserStopped):
                    future.result(5)
                self.assertTrue(all(c.closed for c in engine.contexts))
            finally:
                service.close()


import test_game


class BrowserHTTP(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def grant(self, emp=0):
        with test_server.s.db() as c:
            r = test_server.s.runtime
            p = r.profile(c, emp)
            p["tools"].append("browser")
            r.save_profile(c, p)

    def test_optin_queue_cancel_and_preview_auth(self):
        import urllib.error
        import urllib.request

        body = {
            "employee": 0,
            "kind": "browser",
            "params": {
                "goal": "Comparar fontes públicas",
                "urls": ["https://example.com"],
            },
        }
        with self.assertRaises(urllib.error.HTTPError):
            self.post("tools/job", body)
        self.grant()
        self.post("tools/job", body)
        jobs = json.loads(self.raw("integrations"))["jobs"]
        job = next(j for j in jobs if j["kind"] == "browser")
        self.assertEqual(job["status"], "queued")
        self.post("tools/cancel", {"id": job["id"]})
        self.assertEqual(
            next(
                j
                for j in json.loads(self.raw("integrations"))["jobs"]
                if j["id"] == job["id"]
            )["status"],
            "cancelled",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(
                self.url + "/api/browser/preview?id=" + str(job["id"])
            )
        self.assertEqual(error.exception.code, 403)

    def test_dispatch_claims_job_and_callback_finishes_real_task_pipeline(self):
        s = test_server.s
        self.grant()
        self.post(
            "tools/job",
            {
                "employee": 0,
                "kind": "browser",
                "params": {
                    "goal": "Consultar fontes públicas",
                    "urls": ["https://example.com"],
                },
            },
        )

        class Service:
            def status(self):
                return {"active": [], "capacity": 2, "installed": True}

            def submit(self, job, params, decide, allowed):
                self.job = job
                self.future = concurrent.futures.Future()
                return self.future

        service = Service()
        old = s.runtime.browser
        s.runtime.browser = service
        try:
            s.runtime.browser_tick()
            jid = service.job["id"]
            self.assertTrue(s.runtime.browser_allowed(service.job))
            service.future.set_result(
                {
                    "complete": True,
                    "report": "Resultado real",
                    "sources": [{"url": "https://example.com"}],
                }
            )
            with s.db() as c:
                row = c.execute(
                    "SELECT status,result FROM tool_jobs WHERE id=?", (jid,)
                ).fetchone()
                self.assertEqual(row["status"], "succeeded")
                self.assertIn("Resultado real", row["result"])
                self.assertTrue(
                    c.execute(
                        "SELECT id FROM tasks WHERE kind='tool_result'"
                    ).fetchone()
                )
        finally:
            s.runtime.browser = old

    def test_failure_is_reported_in_employee_chat(self):
        s = test_server.s
        self.grant()
        self.post(
            "tools/job",
            {
                "employee": 0,
                "kind": "browser",
                "params": {
                    "goal": "Consultar fontes públicas",
                    "urls": ["https://example.com"],
                },
            },
        )
        with s.db() as c:
            job = dict(
                c.execute(
                    "SELECT * FROM tool_jobs WHERE kind='browser' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            )
            c.execute("UPDATE tool_jobs SET status='running' WHERE id=?", (job["id"],))
        future = concurrent.futures.Future()
        future.set_exception(b.BrowserError("Navegador indisponível."))
        s.runtime.browser_finished(job, future)
        with s.db() as c:
            msg = c.execute(
                "SELECT content FROM messages WHERE employee=0 ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            self.assertIn("Navegador indisponível", msg)
            self.assertIn("não foi concluída", msg)

    def test_common_chat_can_enqueue_browser_without_player_tool_form(self):
        s = test_server.s
        self.grant()
        self.post(
            "task",
            {
                "employee": 0,
                "intent": "chat",
                "title": "Pesquise nesta página https://example.com",
            },
        )
        with s.db() as c:
            task = dict(
                c.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 1").fetchone()
            )
        action = {
            "type": "tool",
            "tool": "browser",
            "params": {
                "goal": "Consultar a página solicitada",
                "urls": ["https://example.com"],
            },
        }
        with patch.object(
            s,
            "generate",
            return_value={"reply": "Vou consultar a página.", "actions": [action]},
        ):
            self.assertTrue(s.process_task(task))
        with s.db() as c:
            job = c.execute(
                "SELECT * FROM tool_jobs WHERE task=? AND kind='browser'", (task["id"],)
            ).fetchone()
            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "queued")

    def test_fake_wait_is_repaired_into_actual_browser_action(self):
        s = test_server.s
        self.grant()
        self.post(
            "task",
            {
                "employee": 0,
                "intent": "chat",
                "title": "Abra https://example.com e consulte o conteúdo",
            },
        )
        with s.db() as c:
            task = dict(
                c.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 1").fetchone()
            )
        action = {
            "type": "tool",
            "tool": "browser",
            "params": {
                "goal": "Consultar conteúdo solicitado",
                "urls": ["https://example.com"],
            },
        }
        with patch.object(
            s,
            "generate",
            side_effect=[
                {"reply": "Continuo aguardando o navegador assíncrono.", "actions": []},
                {"reply": "Pesquisa solicitada.", "actions": [action]},
            ],
        ) as model:
            s.process_task(task)
            self.assertEqual(model.call_count, 2)
        with s.db() as c:
            self.assertTrue(
                c.execute(
                    "SELECT id FROM tool_jobs WHERE task=? AND kind='browser'",
                    (task["id"],),
                ).fetchone()
            )


class InteractiveWorkflow(unittest.TestCase):
    def test_search_enter_click_and_ten_videos_without_reload(self):
        class Target:
            def __init__(self, p):
                self.p = p

            async def wait_for(self, **kw):
                pass

            async def fill(self, value, **kw):
                self.p.query = value

            async def press(self, key, **kw):
                self.p.stage = 1

            async def click(self, **kw):
                self.p.stage = 2

        class Page(FakePage):
            def __init__(self):
                super().__init__()
                self.stage = 0
                self.query = ""
                self.loads = 0

            async def goto(self, url, **kw):
                self.url = url
                self.loads += 1

            def locator(self, q):
                return Target(self)

            async def wait_for_function(self, *a, **kw):
                pass

            async def evaluate(self, *a):
                links = (
                    [
                        {
                            "text": f"Vídeo {i}",
                            "url": f"https://www.youtube.com/watch?v=video{i}",
                        }
                        for i in range(10)
                    ]
                    if self.stage == 2
                    else []
                )
                controls = [
                    {
                        "id": "0",
                        "type": "search",
                        "tag": "input",
                        "label": "Pesquisar",
                        "value": self.query,
                    }
                ]
                if self.stage == 1:
                    controls.append({"id": "1", "tag": "button", "label": "Em alta"})
                heading = (
                    "Em alta Brasil"
                    if self.stage == 2
                    else "Resultados"
                    if self.stage
                    else "Pesquisar no YouTube"
                )
                return {
                    "text": heading + " Conteúdo real observado",
                    "truncated": False,
                    "controls": controls,
                    "links": links,
                    "headings": [heading],
                    "scroll_y": 0,
                }

        class Context(FakeContext):
            async def new_page(self):
                p = Page()
                self.pages.append(p)
                return p

        class Engine(FakeBrowser):
            async def new_context(self, **kw):
                ctx = Context()
                self.contexts.append(ctx)
                return ctx

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(b, "installed", return_value=True),
            patch.object(b, "public_url", side_effect=lambda u, hosts=None: u),
        ):
            service = b.BrowserService(folder)
            engine = Engine()
            service._engine = AsyncMock(return_value=engine)
            observed = []

            def decide(obs):
                observed.append(obs)
                controls = obs["controls"]
                if "Em alta Brasil" in obs["headings"]:
                    return {
                        "action": "finish",
                        "outcome": "success",
                        "report": "Lista consultada",
                        "evidence": [
                            {"url": obs["page"]["url"], "quote": "Em alta Brasil"}
                        ],
                        "items": obs["links"],
                        "ranking_label": "Em alta Brasil",
                    }
                if any(c["label"] == "Em alta" for c in controls):
                    return {"action": "click", "id": "1"}
                if controls[0]["value"]:
                    return {"action": "press", "id": "0", "key": "Enter"}
                return {"action": "fill", "id": "0", "text": "programação"}

            try:
                result = service.submit(
                    {"id": 11, "employee": 0},
                    {
                        "goal": "Top 10 em alta YouTube Brasil",
                        "urls": ["https://www.youtube.com"],
                        "steps": 8,
                    },
                    decide,
                    lambda: True,
                ).result(6)
                self.assertTrue(result["complete"])
                self.assertEqual(len(result["items"]), 10)
                self.assertEqual(engine.contexts[0].pages[0].loads, 1)
                self.assertIn("_image_b64", observed[0])
                self.assertEqual(
                    [r["action"] for r in result["observations"]],
                    ["fill", "press", "click", "finish"],
                )
            finally:
                service.close()


class BrowserVision(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown

    def test_gemini_receives_actual_image_part_not_base64_in_text(self):
        s = test_server.s
        cfg = {
            "mode": "api",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "auto-gemini-free",
        }
        # Use the adapter's canonical base rather than relying on endpoint spelling.
        cfg["base_url"] = s.chat_models.GEMINI_BASE
        result = {
            "choices": [
                {
                    "message": {
                        "content": '{"action":"finish","outcome":"blocked","report":"Dados indisponíveis"}'
                    }
                }
            ]
        }
        with (
            patch.object(s.runtime, "browser_allowed", return_value=True),
            patch.object(s.runtime, "effective_text", return_value=(cfg, "test-key")),
            patch.object(s.runtime, "text_request", return_value=result) as request,
            patch("integrations.time.sleep"),
        ):
            decision = s.runtime.browser_decide(
                {"id": 55, "employee": 0},
                {"goal": "Consultar página", "_image_b64": "ZmFrZQ=="},
            )
        messages = request.call_args.args[2]
        self.assertTrue(decision["_vision_used"])
        self.assertEqual(messages[1]["inline_files"][0]["data"], "ZmFrZQ==")
        self.assertNotIn("ZmFrZQ==", messages[1]["content"])
        import gemini_text

        payload = gemini_text.native_payload(messages, 2400)
        self.assertEqual(
            payload["contents"][0]["parts"][-1]["inlineData"]["mimeType"], "image/jpeg"
        )

    def test_other_providers_do_not_receive_unsupported_image(self):
        s = test_server.s
        cfg = {
            "mode": "api",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "test",
        }
        result = {"choices": [{"message": {"content": '{"action":"wait"}'}}]}
        with (
            patch.object(s.runtime, "browser_allowed", return_value=True),
            patch.object(s.runtime, "effective_text", return_value=(cfg, "test-key")),
            patch.object(s.runtime, "text_request", return_value=result) as request,
            patch("integrations.time.sleep"),
        ):
            decision = s.runtime.browser_decide(
                {"id": 56, "employee": 0},
                {"goal": "Consultar página", "_image_b64": "ZmFrZQ=="},
            )
        self.assertFalse(decision["_vision_used"])
        self.assertNotIn("inline_files", request.call_args.args[2][1])
        self.assertNotIn("ZmFrZQ==", request.call_args.args[2][1]["content"])

    def test_tool_context_preserves_failure_flag_even_for_long_reports(self):
        s = test_server.s
        with s.db() as db:
            tid = s.create_task(db, 0, "Pesquisar fonte")
            task = dict(db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
            data = {
                "report": "Relatório longo " * 2000,
                "complete": False,
                "outcome": "blocked",
                "items": [],
                "sources": [],
                "evidence": [],
                "notice": "Dados indisponíveis",
            }
            db.execute(
                "INSERT INTO tool_jobs(task,root,employee,kind,params,status,result,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    tid,
                    task["root"],
                    0,
                    "browser",
                    "{}",
                    "succeeded",
                    json.dumps(data),
                    0,
                    0,
                ),
            )
            context = s.runtime.context(db, 0, task)
        result = json.loads(context["results"][0]["result"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(len(result["report"]), 6000)
