"""Local public-web research, two isolated contexts on one dedicated asyncio loop."""

import browser_controls
import base64
import atexit
import asyncio
import concurrent.futures
import importlib.util
import ipaddress
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class BrowserError(ValueError):
    pass


class BrowserStopped(BrowserError):
    pass


def public_url(value, hosts=None):
    if not isinstance(value, str) or len(value) > 2048:
        raise BrowserError("Endereço inválido.")
    p = urlsplit(value)
    if (
        p.scheme not in ("https", "http")
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 80, 443)
    ):
        raise BrowserError(
            "Use um endereço HTTP/HTTPS público, sem credenciais e sem porta especial."
        )
    host = p.hostname.encode("idna").decode().lower()
    if hosts is not None and host not in hosts:
        raise BrowserError("Link fora dos domínios autorizados para esta pesquisa.")
    try:
        addresses = socket.getaddrinfo(
            host,
            p.port or (443 if p.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        if not addresses or any(
            not ipaddress.ip_address(a[4][0].split("%")[0]).is_global for a in addresses
        ):
            raise BrowserError("Acesso a rede local ou endereço reservado bloqueado.")
    except OSError:
        raise BrowserError("Não foi possível resolver o domínio.") from None
    return urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))


def validate(params):
    urls = params.get("urls")
    if not isinstance(urls, list) or not 1 <= len(urls) <= 4:
        raise BrowserError("Informe de 1 a 4 URLs iniciais públicas.")
    goal = str(params.get("goal", "")).strip()
    if not 5 <= len(goal) <= 2000:
        raise BrowserError("Descreva o objetivo da pesquisa (5 a 2000 caracteres).")
    # DNS is checked during execution, outside database transactions.
    for url in urls:
        p = urlsplit(str(url))
        if (
            p.scheme not in ("http", "https")
            or not p.hostname
            or p.username
            or p.password
        ):
            raise BrowserError("URLs iniciais inválidas.")
    return {
        "goal": goal,
        "urls": list(dict.fromkeys(urls)),
        "steps": max(1, min(int(params.get("steps", 16)), 24)),
        "vision": params.get("vision", "auto")
        if params.get("vision", "auto") in ("auto", "always", "off")
        else "auto",
    }


def installed():
    if not importlib.util.find_spec("playwright"):
        return False
    try:
        import playwright
        import sys

        package = Path(playwright.__file__).parent / "driver" / "package"
        registry = json.loads((package / "browsers.json").read_text())
        entry = next(
            item for item in registry["browsers"] if item["name"] == "chromium"
        )
        revisions = {str(entry["revision"])}
        # Registry overrides are OS-specific; a matching executable is still required.
        revisions.update(
            str(value) for value in entry.get("revisionOverrides", {}).values()
        )
        roots = [package / ".local-browsers"]
        custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        if custom and custom != "0":
            roots.insert(0, Path(custom))
        elif custom != "0":
            roots.append(
                Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")))
                / "ms-playwright"
            )
        patterns = (
            ("chrome-win/chrome.exe", "chrome-win64/chrome.exe")
            if sys.platform == "win32"
            else ("chrome-mac*/**/Google Chrome for Testing", "chrome-mac*/**/Chromium")
            if sys.platform == "darwin"
            else ("chrome-linux/chrome", "chrome-linux64/chrome")
        )
        return any(
            file.is_file() and (sys.platform == "win32" or os.access(file, os.X_OK))
            for root in roots
            for revision in revisions
            for pattern in patterns
            for file in (root / ("chromium-" + revision)).glob(pattern)
        )
    except (OSError, ValueError, StopIteration, KeyError, TypeError):
        return False


class BrowserService:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.active = {}
        self.loop = None
        self.thread = None
        self.browser = None
        self.driver = None
        atexit.register(self.close)

    def status(self):
        with self.lock:
            return {
                "installed": installed(),
                "capacity": 2,
                "active": [dict(v["status"]) for v in self.active.values()],
            }

    def stop(self, jid):
        with self.lock:
            if jid in self.active:
                self.active[jid]["stop"].set()
                ctx = self.active[jid].get("context")
                if ctx and self.loop:
                    asyncio.run_coroutine_threadsafe(ctx.close(), self.loop)
                return True
        return False

    def submit(self, job, params, decide, allowed):
        with self.lock:
            if len(self.active) >= 2 or any(
                v["status"]["employee"] == job["employee"] for v in self.active.values()
            ):
                return None
            if not self.thread:
                self.loop = asyncio.new_event_loop()
                self.thread = threading.Thread(
                    target=self.loop.run_forever, name="EscritorIA-browser", daemon=True
                )
                self.thread.start()
            flag = threading.Event()
            self.active[job["id"]] = {
                "stop": flag,
                "status": {
                    "id": job["id"],
                    "employee": job["employee"],
                    "step": 0,
                    "url": "",
                    "title": "Iniciando…",
                },
            }
            return asyncio.run_coroutine_threadsafe(
                self._run(job, params, decide, allowed, flag), self.loop
            )

    async def _engine(self):
        if self.browser and self.browser.is_connected():
            return self.browser
        import playwright

        if (
            Path(playwright.__file__).parent / "driver" / "package" / ".local-browsers"
        ).is_dir():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
        from playwright.async_api import async_playwright

        # Engine initialization happens once, even when two jobs start together.
        if not hasattr(self, "engine_lock"):
            self.engine_lock = asyncio.Lock()
        async with self.engine_lock:
            if not self.driver:
                self.driver = await async_playwright().start()
            if not self.browser or not self.browser.is_connected():
                self.browser = await self.driver.chromium.launch(
                    headless=True, channel="chromium"
                )
        return self.browser

    async def _run(self, job, raw, decide, allowed, stop):
        context = None
        deadline = time.monotonic() + 360
        seen = set()
        sources = []
        records = []
        pages = []
        verdict = {
            "report": "Limite de etapas ou tempo atingido.",
            "complete": False,
            "outcome": "partial",
            "items": [],
            "evidence": [],
        }
        last_error = ""
        repeats = {}
        need_image = False
        try:
            params = validate(raw)
            if not installed():
                raise BrowserError(
                    "Navegador indisponível. Gere o app com Chromium incluído ou execute Instalar-navegador.bat no código-fonte."
                )
            urls = [await asyncio.to_thread(public_url, u) for u in params["urls"]]
            hosts = {urlsplit(u).hostname.encode("idna").decode().lower() for u in urls}
            hosts |= {
                h[4:] if h.startswith("www.") else "www." + h for h in list(hosts)
            }
            if any(h == "youtube.com" or h.endswith(".youtube.com") for h in hosts):
                hosts |= {"charts.youtube.com", "m.youtube.com"}
            browser = await self._engine()
            context = await browser.new_context(
                accept_downloads=False,
                service_workers="block",
                viewport={"width": 1280, "height": 800},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            with self.lock:
                self.active[job["id"]]["context"] = context
            context.set_default_timeout(12000)

            async def guard(route):
                req = route.request
                try:
                    if not browser_controls.request_allowed(
                        req.method, req.url, req.resource_type, hosts
                    ):
                        return await route.abort()
                    # Documents stay within explicit research domains; public static resources may use CDNs.
                    await asyncio.to_thread(
                        public_url,
                        req.url,
                        hosts if req.is_navigation_request() else None,
                    )
                    await route.continue_()
                except Exception:
                    await route.abort()

            await context.route("**/*", guard)

            # WebSockets are unnecessary for this public-reading adapter.
            async def close_socket(ws):
                await ws.close()

            if hasattr(context, "route_web_socket"):
                await context.route_web_socket("**/*", close_socket)
            context.on(
                "page",
                lambda page: (
                    asyncio.create_task(page.close())
                    if len(context.pages) > 1
                    else None
                ),
            )
            page = await context.new_page()
            next_url = urls[0]
            for step in range(1, params["steps"] + 1):
                if time.monotonic() >= deadline:
                    break
                if stop.is_set():
                    raise BrowserStopped("Pesquisa interrompida pelo usuário.")
                if not await asyncio.to_thread(allowed):
                    raise BrowserStopped(
                        "Pesquisa pausada, expediente encerrado ou permissão revogada."
                    )
                if next_url:
                    next_url = await asyncio.to_thread(public_url, next_url, hosts)
                    try:
                        await page.goto(
                            next_url, wait_until="domcontentloaded", timeout=25000
                        )
                    except Exception:
                        raise BrowserError(
                            "A página não carregou ou bloqueou a navegação. Tente outra fonte."
                        ) from None
                    seen.add(next_url)
                    next_url = None
                await page.locator("body").wait_for(state="attached", timeout=8000)
                # Let hydration expose controls without a fixed sleep or waiting for every image/ad.
                try:
                    await page.wait_for_function(
                        'document.body && (document.body.innerText.trim().length>150 || document.querySelector("input[type=search],input[name=search_query]"))',
                        timeout=3500,
                    )
                except Exception:
                    pass
                final = await asyncio.to_thread(public_url, page.url, hosts)
                title = (await page.title())[:180]
                snapshot = await page.evaluate(browser_controls.SNAPSHOT)
                text = snapshot["text"]
                usable = []
                for link in snapshot["links"]:
                    u = urlsplit(link["url"])
                    link["url"] = urlunsplit((u.scheme, u.netloc, u.path, u.query, ""))
                    host = (u.hostname or "").lower()
                    if (
                        host in hosts
                        and u.scheme in ("http", "https")
                        and link["text"]
                        and not browser_controls.UNSAFE.search(link["text"])
                    ):
                        usable.append(link)
                    if len(usable) >= 120:
                        break
                source = {"url": final, "title": title, "consulted_at": time.time()}
                if not sources or sources[-1]["url"] != final:
                    sources.append(source)
                pages.append(
                    {
                        "url": final,
                        "step": step,
                        "vision_used": False,
                        "text": text + "\n" + snapshot.get("interface_text", ""),
                        "links": usable,
                        "headings": snapshot.get("headings", []),
                    }
                )
                with self.lock:
                    self.active[job["id"]]["status"].update(
                        step=step, url=final, title=title
                    )
                folder = self.root / "navegador" / str(job["id"])
                folder.mkdir(parents=True, exist_ok=True)
                image = None
                try:
                    shot = await page.screenshot(type="png", timeout=5000)
                    (folder / "previa.tmp").write_bytes(shot)
                    (folder / "previa.tmp").replace(folder / "previa.png")
                    if params["vision"] != "off" and (
                        params["vision"] == "always"
                        or step == 1
                        or last_error
                        or len(snapshot["controls"]) < 3
                        or need_image
                    ):
                        jpeg = await page.screenshot(
                            type="jpeg", quality=55, timeout=5000
                        )
                        (folder / f"visao-etapa-{step}.jpg").write_bytes(jpeg)
                        image = base64.b64encode(jpeg).decode()
                except Exception:
                    pass
                need_image = False
                observation = {
                    "goal": params["goal"],
                    "page": source,
                    "text": text,
                    "text_truncated": snapshot["truncated"],
                    "interface_text": snapshot.get("interface_text", ""),
                    "headings": snapshot.get("headings", []),
                    "controls": snapshot["controls"],
                    "links": [dict(id=i, **l) for i, l in enumerate(usable)],
                    "other_start_urls": [u for u in urls if u not in seen],
                    "step": step,
                    "max_steps": params["steps"],
                    "previous_observations": records,
                    "sources": sources,
                    "last_action_error": last_error,
                    "allowed_domains": sorted(hosts),
                    "scroll_y": snapshot.get("scroll_y", 0),
                }
                if image:
                    observation["_image_b64"] = image
                decision = await asyncio.wait_for(
                    asyncio.to_thread(decide, observation),
                    timeout=max(1, min(100, deadline - time.monotonic())),
                )
                if stop.is_set():
                    raise BrowserStopped("Pesquisa interrompida pelo usuário.")
                pages[-1]["vision_used"] = bool(decision.get("_vision_used"))
                record = {
                    "step": step,
                    "url": final,
                    "title": title,
                    "action": decision.get("action"),
                    "notes": str(decision.get("notes", ""))[:2000],
                    "vision_used": bool(decision.get("_vision_used")),
                }
                records.append(record)
                action = decision.get("action")
                last_error = ""
                if action == "finish":
                    verdict = browser_controls.final_result(
                        params["goal"], decision, pages
                    )
                    break
                fingerprint = json.dumps(
                    [
                        final,
                        text[:1000],
                        snapshot.get("scroll_y", 0),
                        [(c["id"], c.get("value", "")) for c in snapshot["controls"]],
                        {
                            k: v
                            for k, v in decision.items()
                            if k not in ("notes", "_vision_used")
                        },
                    ],
                    sort_keys=True,
                )
                repeats[fingerprint] = repeats.get(fingerprint, 0) + 1
                if repeats[fingerprint] >= 3:
                    verdict["report"] = (
                        "A navegação repetiu a mesma ação sem progresso. Resultado parcial."
                    )
                    break
                try:
                    if action == "observe":
                        need_image = bool(decision.get("vision", True))
                    elif action == "link":
                        idx = decision.get("id")
                        if type(idx) is not int or not 0 <= idx < len(usable):
                            raise ValueError("A IA escolheu um link inválido.")
                        next_url = usable[idx]["url"]
                    elif action in ("start", "navigate"):
                        candidate = decision.get("url")
                        if action == "start" and candidate not in urls:
                            raise ValueError("URL inicial inválida.")
                        next_url = await asyncio.to_thread(public_url, candidate, hosts)
                    else:
                        if not await asyncio.to_thread(allowed):
                            raise BrowserStopped("Pesquisa pausada ou acesso revogado.")
                        await browser_controls.interact(
                            page,
                            {
                                **decision,
                                "_previous_text": snapshot.get("body_signature", text),
                            },
                            snapshot["controls"],
                        )
                        if action not in ("fill", "wait"):
                            try:
                                await page.wait_for_function(
                                    'old => location.href!==old.url || (document.body.innerText||"").slice(0,4000)!==old.text || scrollY!==old.scroll',
                                    arg={
                                        "url": final,
                                        "text": snapshot.get("body_signature", ""),
                                        "scroll": snapshot.get("scroll_y", 0),
                                    },
                                    timeout=3500,
                                )
                            except Exception:
                                pass
                            try:
                                await page.wait_for_function(
                                    '() => {const s=(document.body.innerText||"").slice(0,12000),n=Date.now(),p=window.__atelieStable;if(!p||p.s!==s){window.__atelieStable={s,t:n};return false}return n-p.t>350}',
                                    timeout=3500,
                                )
                            except Exception:
                                pass
                except BrowserStopped:
                    raise
                except Exception as ex:
                    last_error = str(ex)[:300]
                    record["error"] = last_error
            if not await asyncio.to_thread(allowed):
                raise BrowserStopped("Pesquisa pausada ou permissão revogada.")
            return {
                **verdict,
                "notice": "Navegação real em páginas públicas. "
                + (
                    "Objetivo declarado cumprido com evidências verificadas; confira o escopo das fontes."
                    if verdict["complete"]
                    else "Objetivo não confirmado como cumprido. Não confunda resultados de busca com ranking nacional."
                ),
                "sources": sources,
                "observations": records,
                "steps": len(records),
            }

        except ImportError:
            raise BrowserError(
                "Instale o componente de navegação antes de pesquisar."
            ) from None
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            with self.lock:
                self.active.pop(job["id"], None)

    def close(self):
        with self.lock:
            for entry in self.active.values():
                entry["stop"].set()
        if not self.loop or not self.loop.is_running():
            return

        async def cleanup():
            if self.browser:
                await self.browser.close()
            if self.driver:
                await self.driver.stop()

        try:
            asyncio.run_coroutine_threadsafe(cleanup(), self.loop).result(timeout=5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
