"""Local HTTP endpoints. Business services are supplied by the application."""

import staff_service
import floorplan
import failure_center
import access_matrix
import town as town_module
import social_radar
import attachments
import json
import sqlite3
import time
import re
import tempfile
import io
import zipfile
from urllib.parse import urlsplit, parse_qs, quote
import customization
import chat_models
import office_backup
from pathlib import Path
from http.server import SimpleHTTPRequestHandler


def make_handler(app):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(app.ROOT / "web"), **kw)

        def guess_type(self, path):
            extension = Path(path).suffix.lower()
            return {
                ".ico": "image/x-icon",
                ".png": "image/png",
                ".mp4": "video/mp4",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".html": "text/html; charset=utf-8",
            }.get(extension) or super().guess_type(path)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def log_message(self, *a):
            pass

        def send_json(self, obj, status=200):
            raw = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def send_file(self, raw, name, mime):
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header(
                "Content-Disposition",
                'attachment; filename="'
                + re.sub("[^a-zA-Z0-9_.-]", "_", name)
                + "\"; filename*=UTF-8''"
                + quote(name, safe=""),
            )
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def valid_local_request(self):
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host", "").lower() not in allowed:
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in allowed}:
                return False
            return self.headers.get("Sec-Fetch-Site", "") != "cross-site"

        def do_GET(self):
            if not self.valid_local_request():
                return self.send_json({"error": "Origem local inválida"}, 403)
            url = urlsplit(self.path)
            params = parse_qs(url.query)
            if url.path == "/api/alerts":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                try:
                    with app.db() as c:
                        return self.send_json(
                            failure_center.public(
                                c,
                                history=params.get("history", ["0"])[0] == "1",
                                offset=max(0, int(params.get("offset", ["0"])[0])),
                            )
                        )
                except (ValueError, TypeError):
                    return self.send_json({"error": "Página de alertas inválida"}, 400)
            if url.path == "/api/health":
                return self.send_json({"ok": True, "version": app.VERSION})
            if url.path == "/api/backup/full":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                return self.send_file(
                    office_backup.create(app.DATA, app.STATE_ROOT, app.VERSION),
                    "atelie-backup.zip",
                    "application/zip",
                )
            if url.path == "/api/history":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                try:
                    emp = int(params.get("employee", ["0"])[0])
                    before = int(params.get("before", ["9223372036854775807"])[0])
                    with app.db() as c:
                        app.employee(c, emp)
                        rows = [
                            dict(r)
                            for r in c.execute(
                                "SELECT * FROM messages WHERE employee=? AND id<? ORDER BY id DESC LIMIT 101",
                                (emp, before),
                            )
                        ]
                    return self.send_json(
                        {
                            "items": list(reversed(rows[:100])),
                            "has_more": len(rows) > 100,
                        }
                    )
                except ValueError as ex:
                    return self.send_json({"error": str(ex)}, 400)
            if url.path == "/api/diagnostics":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                return self.send_json(
                    {
                        "workers": app.health.state(),
                        "text_budget": app.runtime.text_budget.status(),
                        "browser": __import__("browser_agent").installed(),
                        "version": app.VERSION,
                    }
                )
            if url.path == "/oauth/instagram/callback":
                try:
                    account = app.runtime.oauth_callback(params)
                    return self.send_json(
                        {
                            "ok": True,
                            "message": "Instagram conectado. Volte ao escritório e abra a sala de servidores.",
                            "account": account,
                        }
                    )
                except (ValueError, KeyError) as ex:
                    return self.send_json(
                        {
                            "error": str(ex)
                            if isinstance(ex, ValueError)
                            else "Falha ao concluir autorização."
                        },
                        400,
                    )
            if url.path == "/api/integrations":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                return self.send_json(app.runtime.public_state())
            if url.path == "/api/asset":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                try:
                    with app.db() as c:
                        a = c.execute(
                            "SELECT * FROM assets WHERE id=?", (int(params["id"][0]),)
                        ).fetchone()
                    if not a:
                        return self.send_json({"error": "Mídia não encontrada"}, 404)
                    return self.send_file(a["data"], a["filename"], a["mime"])
                except (KeyError, ValueError):
                    return self.send_json({"error": "ID de mídia inválido"}, 400)
            if url.path == "/api/browser/preview":
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                try:
                    jid = int(params["id"][0])
                    with app.db() as c:
                        job = c.execute(
                            "SELECT id FROM tool_jobs WHERE id=? AND kind='browser'",
                            (jid,),
                        ).fetchone()
                    path = app.DATA / "navegador" / str(jid) / "previa.png"
                    if not job or not path.is_file():
                        return self.send_json(
                            {"error": "Prévia ainda indisponível."}, 404
                        )
                    return self.send_file(
                        path.read_bytes(), "navegacao.png", "image/png"
                    )
                except (ValueError, KeyError):
                    return self.send_json({"error": "ID inválido"}, 400)
            if url.path in (
                "/api/knowledge",
                "/api/archive",
                "/api/memory/history",
                "/api/knowledge/export",
                "/api/backup",
                "/api/delivery",
                "/api/task-file",
                "/api/attachment",
                "/api/delivery/zip",
                "/api/task-download",
            ):
                if self.headers.get("X-Office-Token") != app.TOKEN:
                    return self.send_json({"error": "Acesso recusado"}, 403)
                try:
                    with app.db() as c:
                        if url.path == "/api/task-download":
                            task_id = int(params["id"][0])
                            t = c.execute(
                                "SELECT * FROM tasks WHERE id=?", (task_id,)
                            ).fetchone()
                            if not t:
                                raise ValueError("Tarefa não encontrada.")
                            files = c.execute(
                                "SELECT * FROM task_files WHERE task=? ORDER BY id",
                                (task_id,),
                            ).fetchall()
                            if len(files) == 1:
                                return self.send_file(
                                    files[0]["content"].encode("utf-8"),
                                    files[0]["filename"],
                                    "application/octet-stream",
                                )
                            if files:
                                buf = io.BytesIO()
                                with zipfile.ZipFile(
                                    buf, "w", zipfile.ZIP_DEFLATED
                                ) as z:
                                    for f in files:
                                        z.writestr(f["filename"], f["content"])
                                return self.send_file(
                                    buf.getvalue(),
                                    Path(files[0]["filename"]).stem + ".zip",
                                    "application/zip",
                                )
                            return self.send_file(
                                t["result"].encode("utf-8"),
                                "resumo-tarefa-" + str(task_id) + ".txt",
                                "text/plain;charset=utf-8",
                            )
                        if url.path in ("/api/delivery", "/api/delivery/zip"):
                            d = c.execute(
                                "SELECT * FROM deliveries WHERE id=?",
                                (int(params["id"][0]),),
                            ).fetchone()
                            if not d or d["status"] != "delivered":
                                raise ValueError(
                                    "O gerente ainda não entregou este pacote na sua sala."
                                )
                            files = [
                                dict(r)
                                for r in c.execute(
                                    "SELECT f.* FROM task_files f JOIN delivery_files df ON df.file=f.id WHERE df.delivery=? ORDER BY f.task,f.filename",
                                    (d["id"],),
                                )
                            ]
                            if url.path == "/api/delivery/zip":
                                buf = io.BytesIO()
                                with zipfile.ZipFile(
                                    buf, "w", zipfile.ZIP_DEFLATED
                                ) as z:
                                    z.writestr("resumo.txt", d["summary"])
                                    for f in files:
                                        z.writestr(
                                            f"tarefa-{f['task']}/{f['filename']}",
                                            f["content"],
                                        )
                                    for a in c.execute(
                                        "SELECT a.* FROM assets a JOIN delivery_assets da ON da.asset=a.id WHERE da.delivery=?",
                                        (d["id"],),
                                    ):
                                        z.writestr(
                                            f"midia/{a['id']}-{a['filename']}",
                                            a["data"],
                                        )
                                return self.send_file(
                                    buf.getvalue(),
                                    Path(files[0]["filename"]).stem + ".zip"
                                    if files
                                    else re.sub("[^\\w .-]", "_", d["title"])[:100]
                                    + ".zip",
                                    "application/zip",
                                )
                            metadata = [
                                {k: v for k, v in f.items() if k != "content"}
                                | {"size": len(f["content"].encode("utf-8"))}
                                for f in files
                            ]
                            metadata += [
                                dict(r) | {"kind": "asset"}
                                for r in c.execute(
                                    "SELECT a.id,a.task,a.filename,a.mime,length(a.data) AS size FROM assets a JOIN delivery_assets da ON da.asset=a.id WHERE da.delivery=?",
                                    (d["id"],),
                                )
                            ]
                            return self.send_json(dict(d, files=metadata))
                        if url.path == "/api/attachment":
                            f = c.execute(
                                "SELECT * FROM source_attachments WHERE id=?",
                                (int(params["id"][0]),),
                            ).fetchone()
                            if not f:
                                raise ValueError("Anexo não encontrado.")
                            return self.send_file(
                                f["data"], f["filename"], "application/octet-stream"
                            )
                        if url.path == "/api/task-file":
                            f = c.execute(
                                "SELECT * FROM task_files WHERE id=?",
                                (int(params["id"][0]),),
                            ).fetchone()
                            if not f:
                                raise ValueError("Arquivo não encontrado.")
                            return self.send_file(
                                f["content"].encode("utf-8"),
                                f["filename"],
                                "application/octet-stream",
                            )
                        if url.path == "/api/knowledge":
                            raw_emp = params.get("employee", [""])[0]
                            emp = int(raw_emp) if raw_emp != "" else None
                            if emp is not None:
                                app.employee(c, emp)
                            items = app.knowledge_records(
                                c,
                                emp,
                                params.get("q", [""])[0][:300],
                                params.get("section", ["all"])[0],
                                params.get("inactive", ["0"])[0] == "1",
                            )
                            offset = max(0, int(params.get("offset", ["0"])[0]))
                            return self.send_json(
                                {
                                    "items": items[offset : offset + 30],
                                    "total": len(items),
                                }
                            )
                        if url.path == "/api/archive":
                            a = c.execute(
                                "SELECT * FROM archives WHERE id=?",
                                (int(params["id"][0]),),
                            ).fetchone()
                            if not a:
                                raise ValueError("Entrega não encontrada.")
                            return self.send_json(dict(a))
                        if url.path == "/api/memory/history":
                            rows = c.execute(
                                "SELECT snapshot,created FROM memory_versions WHERE memory=? ORDER BY id DESC",
                                (int(params["id"][0]),),
                            ).fetchall()
                            return self.send_json(
                                {"versions": [json.loads(r["snapshot"]) for r in rows]}
                            )
                        if url.path == "/api/knowledge/export":
                            data = {
                                "format": "atelie-knowledge-v1",
                                "exported": time.time(),
                                "employees": [
                                    dict(r)
                                    for r in c.execute("SELECT * FROM employees")
                                ],
                                "memories": [
                                    dict(r) for r in c.execute("SELECT * FROM memories")
                                ],
                                "versions": [
                                    dict(r)
                                    for r in c.execute("SELECT * FROM memory_versions")
                                ],
                                "archives": [
                                    dict(r) for r in c.execute("SELECT * FROM archives")
                                ],
                                "files": [
                                    dict(r)
                                    for r in c.execute("SELECT * FROM task_files")
                                ],
                            }
                            return self.send_file(
                                json.dumps(data, ensure_ascii=False, indent=2).encode(),
                                "conhecimento-atelie.json",
                                "application/json; charset=utf-8",
                            )
                    if url.path == "/api/backup":
                        with tempfile.TemporaryDirectory() as folder:
                            file = Path(folder) / "backup.db"
                            with app.db() as source, sqlite3.connect(file) as dest:
                                source.backup(dest)
                            return self.send_file(
                                file.read_bytes(),
                                "escritorio-backup.db",
                                "application/vnd.sqlite3",
                            )
                except (ValueError, KeyError, TypeError) as ex:
                    return self.send_json({"error": str(ex)}, 400)
            if url.path == "/api/state":
                with app.db() as c:
                    result = {
                        k: [dict(r) for r in c.execute(sql)]
                        for k, sql in {
                            "attachments": "SELECT a.id,a.task,a.filename,a.analysis_status,a.mime,length(a.data) AS size,t.employee FROM source_attachments a JOIN tasks t ON t.id=a.task ORDER BY a.id DESC LIMIT 120",
                            "employees": "SELECT * FROM employees WHERE active=1 ORDER BY slot",
                            "tasks": "SELECT * FROM tasks WHERE status!='concluida' OR id IN (SELECT id FROM tasks ORDER BY id DESC LIMIT 200) ORDER BY id DESC",
                            "messages": "SELECT * FROM messages WHERE 0",
                            "notes": "SELECT * FROM notes ORDER BY id",
                            "staff_messages": "SELECT * FROM staff_messages ORDER BY id DESC LIMIT 80",
                            "events": "SELECT * FROM events ORDER BY id DESC LIMIT 40",
                            "deliveries": "SELECT d.*, (SELECT COUNT(*) FROM delivery_files df WHERE df.delivery=d.id) AS file_count FROM deliveries d WHERE status!='delivered' OR id IN (SELECT id FROM deliveries ORDER BY id DESC LIMIT 100) ORDER BY id DESC",
                        }.items()
                    }
                    try:
                        after = max(0, int(params.get("messages_after", ["0"])[0]))
                    except (TypeError, ValueError):
                        after = 0
                    if after:
                        result["messages"] = [
                            dict(r)
                            for r in c.execute(
                                "SELECT * FROM messages WHERE id>? ORDER BY id LIMIT 800",
                                (after,),
                            )
                        ]
                    else:
                        result["messages"] = sorted(
                            [
                                dict(r)
                                for e in result["employees"]
                                for r in c.execute(
                                    "SELECT * FROM messages WHERE employee=? ORDER BY id DESC LIMIT 100",
                                    (e["id"],),
                                )
                            ],
                            key=lambda r: r["id"],
                        )
                    result["messages_delta"] = bool(after)
                try:
                    mode = app.config().get("mode", "demo")
                except Exception:
                    mode = "configuração inválida"
                with app.db() as c:
                    revision = c.execute(
                        "SELECT revision FROM knowledge_meta WHERE id=1"
                    ).fetchone()[0]
                    world = app.world_state(c)
                for e in result["employees"]:
                    e["skin"] = app.clean_skin(
                        json.loads(e.get("skin") or "{}")
                        | {
                            "shirt": json.loads(e.get("skin") or "{}").get(
                                "shirt", e["color"]
                            )
                        }
                    )
                try:
                    base = app.config()
                except Exception:
                    base = {"mode": "demo"}
                connection_status = [
                    app.runtime.text_status(e["id"], base) for e in result["employees"]
                ]
                mode = (
                    "api"
                    if any(
                        (info["status"] == "configured" for info in connection_status)
                    )
                    else mode
                )
                with app.db() as c:
                    town_state = app.town.state(c)
                with app.db() as c:
                    alerts = failure_center.public(c, limit=24)
                return self.send_json(
                    dict(
                        result,
                        alerts=alerts,
                        connection_status=connection_status,
                        paused=app.paused,
                        mode=mode,
                        token=app.TOKEN,
                        knowledge_revision=revision,
                        world=world,
                        town=town_state,
                        integration_activity=[dict(r) for r in app._integration_jobs()],
                        asset_count=app._asset_count(),
                    )
                )
            if self.path.startswith("/api/"):
                return self.send_json({"error": "Não encontrado"}, 404)
            return super().do_GET()

        def do_POST(self):
            if not self.valid_local_request():
                return self.send_json({"error": "Origem local inválida"}, 403)
            if self.headers.get("X-Office-Token") != app.TOKEN:
                return self.send_json({"error": "Acesso recusado"}, 403)
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size < 0 or size > (
                    30000000
                    if self.path == "/api/media/import"
                    else 15000000
                    if self.path == "/api/task"
                    else 64000
                ):
                    raise ValueError("Conteúdo muito grande.")
                body = json.loads(self.rfile.read(size))
                if self.path == "/api/town/map":
                    with app.db() as c:
                        return self.send_json(app.town.map_state(c))
                if self.path == "/api/culture/search":
                    return self.send_json(app.runtime.culture.run(body))
                if self.path == "/api/integrations/freellm/connect":
                    return self.send_json(
                        app.runtime.connect_freellm(
                            body.get("key", ""),
                            body.get("all_staff", True) is True,
                            body.get("images", False) is True,
                        )
                    )
                if self.path == "/api/integrations/gemini/connect":
                    return self.send_json(
                        app.runtime.connect_gemini(
                            body.get("key", ""), body.get("employee")
                        )
                    )
                if self.path == "/api/video/preview":
                    return self.send_json(app.runtime.video_preview(body))
                if self.path == "/api/media/import":
                    return self.send_json(app.runtime.import_media(body))
                with app.db() as c:
                    if self.path == "/api/alerts/settings":
                        failure_center.configure(c, body.get("auto_retry"))
                    elif self.path == "/api/alerts/dismiss":
                        failure_center.dismiss(c, int(body["id"]))
                    elif self.path == "/api/town/command":
                        command = body.get("command", "")
                        if town_module.night_greeting(command):
                            app.town.set_rest(c, True)
                        elif command in ("retomar", "bom dia", "voltar ao trabalho"):
                            app.town.set_rest(c, False)
                        else:
                            raise ValueError("Use Boa noite ou Retomar.")
                    elif self.path == "/api/town/chat":
                        return self.send_json(
                            {
                                "ok": True,
                                "id": app.town.chat(
                                    c, body.get("npc"), body.get("message")
                                ),
                            }
                        )
                    elif self.path == "/api/town/interact":
                        return self.send_json(
                            app.town.interact(
                                c,
                                body.get("scene"),
                                body.get("id"),
                                body.get("action", "inspect"),
                            )
                        )
                    elif self.path == "/api/town/decorate":
                        return self.send_json(app.town.decorate(c, body))
                    elif self.path == "/api/town/settings":
                        if not isinstance(body.get("npc_social"), bool):
                            raise ValueError(
                                "Escolha ativar ou desativar as conversas."
                            )
                        c.execute(
                            "UPDATE town_state SET npc_social=? WHERE id=1",
                            (int(body["npc_social"]),),
                        )
                    elif self.path == "/api/world/preferences":
                        customization.save_preferences(c, body)
                    elif self.path == "/api/world/interact":
                        return self.send_json(
                            customization.interact(
                                c,
                                app.world_state(c)["layout"],
                                str(body.get("id", "")),
                                str(body.get("action", "inspect")),
                                body.get("text", ""),
                            )
                        )
                    elif self.path == "/api/integrations/settings":
                        app.runtime.save_settings(c, body.get("settings", {}))
                        credentials = body.get("credentials", {})
                        if not isinstance(credentials, dict):
                            raise ValueError("Credenciais inválidas.")
                        for name, value in credentials.items():
                            if value:
                                app.runtime.store_key(name, value)
                    elif self.path == "/api/integrations/access":
                        access_matrix.save(
                            app.runtime,
                            c,
                            body.get("rows"),
                            __import__("integrations").TOOLS,
                        )
                    elif self.path == "/api/integrations/profile":
                        app.runtime.save_profile(c, body)
                    elif self.path == "/api/integrations/test":
                        kind = body.get("kind")
                        if kind == "instagram":
                            result = app.runtime.check_instagram()
                            return self.send_json(result)
                        if kind == "text":
                            emp = int(body["employee"])
                            cfg, key = app.runtime.effective_text(emp, app.config())
                            if cfg.get("mode") == "demo":
                                return self.send_json(
                                    {
                                        "ok": False,
                                        "message": "Modelo geral ainda está em demonstração. Configure config.json ou um modelo próprio.",
                                    }
                                )
                            app.runtime.free_text_guard(cfg)
                            if not key:
                                raise ValueError("Credencial de texto não configurada.")
                            result = app.runtime.text_request(
                                cfg,
                                key,
                                [
                                    {
                                        "role": "user",
                                        "content": "Responda apenas OK, sem explicações.",
                                    }
                                ],
                                1024,
                            )
                            chat_models.final_text(result)
                            app.runtime.record_text_check(
                                emp, result.get("model", cfg["model"])
                            )
                            return self.send_json(
                                {
                                    "ok": True,
                                    "message": "Conexão confirmada com resposta de texto. Modelo: "
                                    + str(result.get("model", cfg["model"])),
                                }
                            )
                        if kind == "video":
                            app.runtime.free_media_guard()
                        if kind == "image":
                            app.runtime.require_key("FREELLM_API_KEY")
                            return self.send_json(
                                {
                                    "ok": True,
                                    "verified": False,
                                    "message": "Chave unificada cadastrada. Gere uma imagem para testar o modelo de imagens no painel FreeLLMAPI.",
                                }
                            )
                        raise ValueError("Tipo de teste inválido.")
                    elif self.path == "/api/integrations/oauth":
                        return self.send_json({"url": app.runtime.oauth_start()})
                    elif self.path == "/api/radar/tiktok":
                        social_radar.save_tiktok(
                            c, body.get("text", ""), body.get("observed", "")
                        )
                    elif self.path == "/api/tools/job":
                        if app.town.resting(c):
                            app.town.set_rest(c, False)
                        emp = int(body["employee"])
                        app.employee(c, emp)
                        tid = app.create_task(
                            c,
                            emp,
                            "Solicitação de ferramenta: " + str(body.get("kind", "")),
                        )
                        task = dict(
                            c.execute(
                                "SELECT * FROM tasks WHERE id=?", (tid,)
                            ).fetchone()
                        )
                        c.execute(
                            "UPDATE tasks SET status='concluida',result='Ferramenta solicitada pelo usuário.' WHERE id=?",
                            (tid,),
                        )
                        params = body.get("params", {})
                        if body.get("kind") in ("code", "files") and params.get(
                            "file_id"
                        ):
                            source = c.execute(
                                "SELECT * FROM task_files WHERE id=?",
                                (int(params["file_id"]),),
                            ).fetchone()
                            if not source:
                                raise ValueError("Arquivo não encontrado.")
                            clone = c.execute(
                                "INSERT INTO task_files(task,employee,filename,content,created) VALUES(?,?,?,?,?)",
                                (
                                    tid,
                                    emp,
                                    source["filename"],
                                    source["content"],
                                    time.time(),
                                ),
                            ).lastrowid
                            params = dict(params, file_id=clone)
                        app.runtime.enqueue(
                            c, emp, task, str(body.get("kind", "")), params
                        )
                    elif self.path == "/api/tools/retry":
                        if app.town.resting(c):
                            app.town.set_rest(c, False)
                        job = c.execute(
                            "SELECT * FROM tool_jobs WHERE id=?", (int(body["id"]),)
                        ).fetchone()
                        if (
                            not job
                            or job["status"] != "failed"
                            or job["kind"] == "instagram"
                        ):
                            raise ValueError(
                                "Apenas falhas confirmadas de ferramentas não sociais podem ser retomadas. Estados incertos precisam ser conferidos no provedor."
                            )
                        app.runtime.reserve(c, job["kind"])
                        c.execute(
                            "UPDATE tool_jobs SET status=?,error='',next_poll=0,updated=? WHERE id=?",
                            (
                                "waiting" if json.loads(job["remote"]) else "queued",
                                time.time(),
                                job["id"],
                            ),
                        )
                        failure_center.mark_retry(c, "tool", job["id"])
                    elif self.path == "/api/tools/cancel":
                        job = c.execute(
                            "SELECT * FROM tool_jobs WHERE id=?", (int(body["id"]),)
                        ).fetchone()
                        if (
                            job
                            and job["kind"] == "browser"
                            and (job["status"] in ("queued", "running"))
                        ):
                            if app.runtime.browser:
                                app.runtime.browser.stop(job["id"])
                            c.execute(
                                "UPDATE tool_jobs SET status='cancelled',error='Interrompido pelo usuário.',updated=? WHERE id=?",
                                (time.time(), job["id"]),
                            )
                            return self.send_json({"ok": True})
                        if (
                            job
                            and job["kind"] in ("video_local", "video")
                            and (job["status"] in ("queued", "running"))
                        ):
                            app.runtime.cancel_video(c, dict(job))
                            return self.send_json({"ok": True})
                        if not job or job["status"] not in ("failed", "uncertain"):
                            raise ValueError(
                                "Apenas falhas ou estados incertos podem ser encerrados localmente."
                            )
                        c.execute(
                            "UPDATE tool_jobs SET status='cancelled',updated=? WHERE id=?",
                            (time.time(), job["id"]),
                        )
                        task = dict(
                            c.execute(
                                "SELECT * FROM tasks WHERE id=?", (job["task"],)
                            ).fetchone()
                        )
                        app.save_task_files(
                            c,
                            task,
                            [
                                {
                                    "filename": f"ferramenta-{job['id']}-encerrada.txt",
                                    "content": "Ferramenta encerrada localmente pelo usuário. "
                                    + str(job["error"]),
                                }
                            ],
                            "Ferramenta encerrada",
                            internal=True,
                        )
                        app.queue_delivery(c, job["root"])
                    elif self.path == "/api/assets/url":
                        value = str(body["url"]).strip()
                        p = urlsplit(value)
                        if (
                            p.scheme != "https"
                            or not p.hostname
                            or p.username
                            or p.password
                        ):
                            raise ValueError(
                                "Informe uma URL HTTPS pública sem credenciais."
                            )
                        c.execute(
                            "UPDATE assets SET public_url=? WHERE id=?",
                            (value, int(body["id"])),
                        )
                    elif self.path == "/api/social/create":
                        aid = int(body["asset_id"])
                        asset = c.execute(
                            "SELECT * FROM assets WHERE id=?", (aid,)
                        ).fetchone()
                        if not asset:
                            raise ValueError("Mídia não encontrada.")
                        task = dict(
                            c.execute(
                                "SELECT * FROM tasks WHERE id=?", (asset["task"],)
                            ).fetchone()
                        )
                        mode = app.runtime.settings(c)["publish_mode"]
                        settings = app.runtime.settings(c)
                        settings["publish_mode"] = "review"
                        c.execute(
                            "UPDATE integration_settings SET data=? WHERE id=1",
                            (json.dumps(settings),),
                        )
                        app.runtime.create_post(
                            c,
                            asset["employee"],
                            task,
                            {
                                "asset_ids": body.get("asset_ids", [aid]),
                                "caption": body.get("caption", ""),
                            },
                            owner=True,
                        )
                        settings["publish_mode"] = mode
                        c.execute(
                            "UPDATE integration_settings SET data=? WHERE id=1",
                            (json.dumps(settings),),
                        )
                    elif self.path == "/api/social/update":
                        caption = str(body.get("caption", "")).strip()
                        if len(caption) > 2200:
                            raise ValueError("Legenda deve ter até 2200 caracteres.")
                        if not c.execute(
                            "UPDATE social_posts SET caption=?,updated=? WHERE id=? AND status='draft'",
                            (caption, time.time(), int(body["id"])),
                        ).rowcount:
                            raise ValueError(
                                "Só é possível editar rascunhos ainda não autorizados."
                            )
                    elif self.path == "/api/social/approve":
                        app.runtime.approve_post(
                            c, int(body["id"]), float(body.get("scheduled", 0))
                        )
                    elif self.path == "/api/task":
                        emp = int(body["employee"])
                        title = str(body["title"]).strip()
                        if not title or len(title) > 12000:
                            raise ValueError("Tarefa inválida.")
                        if town_module.night_greeting(title):
                            app.employee(c, emp)
                            app.town.set_rest(c, True)
                            c.execute(
                                'INSERT INTO messages(employee,role,content) VALUES(?,"user",?)',
                                (emp, title),
                            )
                            c.execute(
                                'INSERT INTO messages(employee,role,content) VALUES(?,"assistant",?)',
                                (
                                    emp,
                                    "Boa noite! A equipe vai para casa. O trabalho na fila fica salvo até sua próxima instrução.",
                                ),
                            )
                            return self.send_json({"ok": True, "resting": True})
                        intent = body.get("intent", "chat")
                        if intent not in ("chat", "project"):
                            raise ValueError("Escolha Conversar ou Novo projeto.")
                        sources = attachments.decode(body.get("attachments", []))
                        refs = body.get("reference_ids", [])
                        if not isinstance(refs, list) or len(refs) > 6:
                            raise ValueError("Referências inválidas.")
                        for ref in refs:
                            original = c.execute(
                                "SELECT * FROM source_attachments WHERE id=?",
                                (int(ref),),
                            ).fetchone()
                            if not original:
                                raise ValueError("Anexo original não encontrado.")
                            sources.append(dict(original))
                        attachments.validate(sources)
                        app.town.set_rest(c, False) if app.town.resting(c) else None
                        tid = app.create_task(c, emp, title, intent=intent)
                        for source in sources:
                            c.execute(
                                "INSERT INTO source_attachments(task,filename,content,data,created,mime,analysis_status) VALUES(?,?,?,?,?,?,?)",
                                (
                                    tid,
                                    source["filename"],
                                    source["content"],
                                    source["data"],
                                    time.time(),
                                    source.get("mime", "text/plain"),
                                    source.get("analysis_status", "text"),
                                ),
                            )
                        c.execute(
                            'INSERT INTO messages(employee,role,content) VALUES(?,"user",?)',
                            (emp, title),
                        )
                    elif self.path == "/api/employee/archive":
                        staff_service.archive(c, int(body["id"]))
                    elif self.path == "/api/employee":
                        name = str(body.get("name", "")).strip()[:80]
                        role = str(body.get("role", "")).strip()[:100]
                        context = str(body.get("context", "")).strip()[:6000]
                        color = body.get("color", "#7fe0c0")
                        if not name or not role or (not context):
                            raise ValueError("Preencha nome, função e contexto.")
                        if not re.fullmatch("#[0-9a-fA-F]{6}", color):
                            raise ValueError("Cor inválida.")
                        manager = int(body.get("manager") is True)
                        staff_service.validate_manager(c, body.get("id"), manager)
                        bg = str(body.get("background", ""))[:4000]
                        skills = str(body.get("skills", ""))[:4000]
                        expectations = str(body.get("expectations", ""))[:4000]
                        if body.get("id") is not None:
                            emp = int(body["id"])
                            app.employee(c, emp)
                            c.execute(
                                "UPDATE employees SET name=?,role=?,color=?,context=?,background=?,skills=?,expectations=?,manager=?,revision=revision+1 WHERE id=?",
                                (
                                    name,
                                    role,
                                    color,
                                    context,
                                    bg,
                                    skills,
                                    expectations,
                                    manager,
                                    emp,
                                ),
                            )
                        else:
                            used = {
                                r[0]
                                for r in c.execute(
                                    "SELECT slot FROM employees WHERE active=1"
                                )
                            }
                            slot = next((i for i in range(8) if i not in used), None)
                            if slot is None:
                                raise ValueError(
                                    "Este escritório tem 8 estações. Edite um funcionário existente."
                                )
                            x, y = app.station_position(
                                app.world_state(c)["layout"], slot
                            )
                            emp = c.execute(
                                "INSERT INTO employees(name,role,color,context,background,skills,expectations,manager,slot,x,y) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                (
                                    name,
                                    role,
                                    color,
                                    context,
                                    bg,
                                    skills,
                                    expectations,
                                    manager,
                                    slot,
                                    x,
                                    y,
                                ),
                            ).lastrowid
                        app.event(
                            c,
                            emp,
                            "Perfil profissional atualizado. O novo contexto será enviado na próxima solicitação à IA.",
                        )
                    elif self.path == "/api/note":
                        title = str(body.get("title", "")).strip()[:120]
                        content = str(body.get("content", "")).strip()[:6000]
                        if not title or not content:
                            raise ValueError("Preencha título e anotação.")
                        if body.get("id") is not None:
                            c.execute(
                                "UPDATE notes SET title=?,content=?,updated=? WHERE id=?",
                                (title, content, time.time(), int(body["id"])),
                            )
                        else:
                            if (
                                c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
                                >= 20
                            ):
                                raise ValueError(
                                    "Limite de 20 anotações. Edite uma existente."
                                )
                            c.execute(
                                "INSERT INTO notes(title,content,updated) VALUES(?,?,?)",
                                (title, content, time.time()),
                            )
                    elif self.path == "/api/note/delete":
                        c.execute("DELETE FROM notes WHERE id=?", (int(body["id"]),))
                    elif self.path == "/api/board/review":
                        if app.town.resting(c):
                            app.town.set_rest(c, False)
                        manager = c.execute(
                            "SELECT id FROM employees WHERE active=1 AND manager=1 ORDER BY slot LIMIT 1"
                        ).fetchone()
                        if not manager:
                            raise ValueError("Defina um gerente na equipe.")
                        app.create_task(
                            c,
                            manager["id"],
                            "Leia as anotações atuais do quadro compartilhado, revise as tarefas e organize o trabalho necessário. Delegue somente o que ainda não está em andamento.",
                        )
                    elif self.path == "/api/memory":
                        mid = app.save_memory(
                            c,
                            int(body["employee"]),
                            body.get("title", ""),
                            body.get("content", ""),
                            body.get("kind", "aprendizado"),
                            body.get("scope", "individual"),
                            "manual",
                            None,
                            body.get("status", "confirmed"),
                            int(body["id"]) if body.get("id") is not None else None,
                        )
                        app.event(
                            c,
                            int(body["employee"]),
                            f"Memória #{mid} salva pelo usuário.",
                        )
                    elif self.path == "/api/memory/status":
                        m = c.execute(
                            "SELECT * FROM memories WHERE id=?", (int(body["id"]),)
                        ).fetchone()
                        if not m:
                            raise ValueError("Memória não encontrada.")
                        app.save_memory(
                            c,
                            m["employee"],
                            m["title"],
                            m["content"],
                            m["kind"],
                            m["scope"],
                            status=body["status"],
                            memory_id=m["id"],
                        )
                    elif self.path == "/api/skin":
                        skin = app.clean_skin(body.get("skin", {}))
                        if body.get("employee") is None:
                            world = app.world_state(c)
                            name = str(
                                body.get("name", world["player"]["name"])
                            ).strip()[:60]
                            if not name:
                                raise ValueError("Informe o nome do seu personagem.")
                            c.execute(
                                "UPDATE game_world SET player=? WHERE id=1",
                                (json.dumps({"name": name, "skin": skin}),),
                            )
                        else:
                            emp = int(body["employee"])
                            app.employee(c, emp)
                            c.execute(
                                "UPDATE employees SET skin=? WHERE id=?",
                                (json.dumps(skin), emp),
                            )
                    elif self.path in ("/api/layout", "/api/layout/validate"):
                        if not app.paused:
                            raise ValueError("Pause a equipe antes de decorar.")
                        if c.execute(
                            "SELECT id FROM tasks WHERE status='executando'"
                        ).fetchone():
                            raise ValueError(
                                "Aguarde a tarefa em andamento terminar antes de mudar os móveis."
                            )
                        world = app.world_state(c)
                        if int(body.get("revision", 0)) != world["revision"]:
                            raise ValueError(
                                "O escritório mudou em outra janela. Reabra o modo decorar."
                            )
                        outline = floorplan.validate_outline(
                            body.get("outline", world["outline"])
                        )
                        rooms = floorplan.validate(
                            body.get("rooms", world["rooms"]), outline
                        )
                        walls, zones = floorplan.geometry(
                            rooms, app.WORLD_WALLS, app.WORLD_ZONES, outline
                        )
                        layout = app.validate_layout(
                            body.get("layout"), walls, zones, rooms, outline
                        )
                        if self.path.endswith("/validate"):
                            return self.send_json({"ok": True})
                        c.execute(
                            "INSERT OR REPLACE INTO office_outline(id,outline) VALUES(1,?)",
                            (json.dumps(outline),),
                        )
                        c.execute(
                            "INSERT OR REPLACE INTO office_plan(id,rooms) VALUES(1,?)",
                            (json.dumps(rooms),),
                        )
                        c.execute(
                            "UPDATE game_world SET layout=?,revision=revision+1 WHERE id=1",
                            (json.dumps(layout),),
                        )
                        for e in c.execute(
                            "SELECT id,slot,x,y FROM employees"
                        ).fetchall():
                            if app.blocked(e["x"], e["y"], layout) or not app.route(
                                e["x"],
                                e["y"],
                                *app.station_position(layout, e["slot"]),
                                layout,
                            ):
                                x, y = app.station_position(layout, e["slot"])
                                c.execute(
                                    "UPDATE employees SET x=?,y=? WHERE id=?",
                                    (x, y, e["id"]),
                                )
                    elif self.path == "/api/delivery/read":
                        c.execute(
                            "UPDATE deliveries SET unread=0 WHERE id=? AND status='delivered'",
                            (int(body["id"]),),
                        )
                    elif self.path == "/api/pause":
                        app.paused = not app.paused
                    elif self.path == "/api/retry":
                        if app.town.resting(c):
                            app.town.set_rest(c, False)
                        if not c.execute(
                            "UPDATE tasks SET status='fila',error='' WHERE id=? AND status='pausada'",
                            (int(body["id"]),),
                        ).rowcount:
                            raise ValueError(
                                "A tarefa já foi retomada ou não está pausada. Atualize a central."
                            )
                        failure_center.mark_retry(c, "task", int(body["id"]))
                    else:
                        return self.send_json({"error": "Não encontrado"}, 404)
                self.send_json({"ok": True})
            except Exception as ex:
                self.send_json({"error": str(ex)}, 400)

    return Handler
