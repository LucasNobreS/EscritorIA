import task_engine
from http_api import make_handler
from runtime_context import RuntimeContext
import work_policy
import delegation
import staff_service
import floorplan
import failure_center
import access_matrix
import town as town_module
import social_radar
import attachments
import json
import os
import sqlite3
import threading
import time
import secrets
import urllib.request
import urllib.error
import webbrowser
import re
import math
import unicodedata
import tempfile
import io
import zipfile
from urllib.parse import urlsplit, parse_qs, quote
from integrations import IntegrationRuntime, ConfigurationError
import customization
import chat_models
import freellm_gateway
import runtime_health
import office_backup
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = Path(__file__).parent.resolve()
STATE_ROOT = Path(
    os.environ.get(
        "ATELIE_STATE_ROOT",
        str(ROOT.parent if (ROOT.parent / "Iniciar.bat").exists() else ROOT),
    )
).resolve()
DATA = STATE_ROOT / "dados"
DATA.mkdir(parents=True, exist_ok=True)
VERSION = "0.45.0"
TOKEN = secrets.token_urlsafe(32)
paused = False
health = runtime_health.Health(DATA)
ROLES = [
    (
        "Helena",
        "Gerente",
        "#c5a1ff",
        "Organize demandas, conheça as especialidades da equipe, delegue com briefing e acompanhe as entregas.",
    ),
    (
        "Theo",
        "Desenvolvedor",
        "#73c5ff",
        "Produza código e explique sua utilização. Não afirme ter executado código ou ferramentas.",
    ),
    (
        "Lia",
        "Designer",
        "#ffaecc",
        "Defina interfaces, identidade visual e especificações utilizáveis.",
    ),
    (
        "Caio",
        "Marketing",
        "#ffc77b",
        "Crie textos e campanhas com objetivos concretos, sem inventar resultados.",
    ),
    (
        "Nina",
        "QA",
        "#7fe0c0",
        "Revise entregas e proponha testes. Não invente testes executados.",
    ),
]
DESKS = [(x + 78, y + 100) for y in (235, 470) for x in (210, 385, 560, 735)]
DESTINATIONS = {
    "copa": (1190, 665),
    "reuniao": (1190, 390),
    "recepcao": (570, 740),
    "biblioteca": (175, 650),
}


def db():
    c = sqlite3.connect(DATA / "escritorio.db", timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    return c


def init_db():
    with db() as c:
        schema_version = c.execute("PRAGMA user_version").fetchone()[0]
        if schema_version > 1:
            raise RuntimeError(
                "Este banco pertence a uma versão mais recente. Abra o aplicativo atualizado para preservar os dados."
            )
        if (
            schema_version < 1
            and c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='employees'"
            ).fetchone()
        ):
            if c.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError(
                    "Banco com erro de integridade. Restaure um backup antes de continuar."
                )
            target = DATA / "antes-schema-1.db"
            if not target.exists():
                with sqlite3.connect(target) as snapshot:
                    c.backup(snapshot)
        c.execute("PRAGMA journal_mode=WAL")
        IntegrationRuntime.schema(c)
        customization.schema(c)
        c.executescript("""CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, employee INTEGER, role TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, employee INTEGER, title TEXT, status TEXT DEFAULT 'fila', result TEXT DEFAULT '', error TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY,name TEXT,role TEXT,color TEXT,context TEXT,background TEXT DEFAULT '',skills TEXT DEFAULT '',expectations TEXT DEFAULT '',manager INTEGER DEFAULT 0,slot INTEGER UNIQUE,x REAL,y REAL,destination TEXT DEFAULT 'mesa',active INTEGER DEFAULT 1,revision INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,title TEXT,content TEXT,updated REAL);
CREATE TABLE IF NOT EXISTS staff_messages(id INTEGER PRIMARY KEY,sender INTEGER,recipient INTEGER,content TEXT,root INTEGER,created REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,employee INTEGER,content TEXT,created REAL);
CREATE TABLE IF NOT EXISTS office_outline(id INTEGER PRIMARY KEY CHECK(id=1),outline TEXT);
CREATE TABLE IF NOT EXISTS office_plan(id INTEGER PRIMARY KEY CHECK(id=1),rooms TEXT);
CREATE TABLE IF NOT EXISTS game_world(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER DEFAULT 1,layout TEXT,player TEXT);
CREATE TABLE IF NOT EXISTS task_files(id INTEGER PRIMARY KEY,task INTEGER,employee INTEGER,filename TEXT,content TEXT,created REAL,UNIQUE(task,filename));
CREATE TABLE IF NOT EXISTS source_attachments(id INTEGER PRIMARY KEY,task INTEGER,filename TEXT,content TEXT,data BLOB,created REAL);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY,root INTEGER UNIQUE,manager INTEGER,title TEXT,summary TEXT,status TEXT,created REAL,received REAL,unread INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS delivery_files(delivery INTEGER,file INTEGER,PRIMARY KEY(delivery,file));
CREATE TABLE IF NOT EXISTS usage_day(day TEXT PRIMARY KEY,idle_calls INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS knowledge_meta(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER DEFAULT 0);
INSERT OR IGNORE INTO knowledge_meta(id,revision) VALUES(1,0);
CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY,employee INTEGER,scope TEXT,kind TEXT,title TEXT,content TEXT,search_text TEXT,source TEXT,source_task INTEGER,status TEXT,revision INTEGER DEFAULT 1,created REAL,updated REAL);
CREATE TABLE IF NOT EXISTS memory_versions(id INTEGER PRIMARY KEY,memory INTEGER,snapshot TEXT,created REAL);
CREATE TABLE IF NOT EXISTS archives(id INTEGER PRIMARY KEY,task INTEGER UNIQUE,employee INTEGER,title TEXT,content TEXT,search_text TEXT,demo INTEGER,created REAL);
CREATE INDEX IF NOT EXISTS memory_owner ON memories(employee,scope,status);
CREATE INDEX IF NOT EXISTS archive_owner ON archives(employee,task);

""")
        if "purpose" not in {
            r["name"] for r in c.execute("PRAGMA table_info(task_files)")
        }:
            c.execute("ALTER TABLE task_files ADD COLUMN purpose TEXT DEFAULT 'legacy'")
        source_columns = {
            r["name"] for r in c.execute("PRAGMA table_info(source_attachments)")
        }
        for name, definition in [
            ("mime", "TEXT DEFAULT 'text/plain'"),
            ("analysis_status", "TEXT DEFAULT 'text'"),
        ]:
            if name not in source_columns:
                c.execute(
                    "ALTER TABLE source_attachments ADD COLUMN "
                    + name
                    + " "
                    + definition
                )
        columns = {r["name"] for r in c.execute("PRAGMA table_info(tasks)")}
        for name, definition in [
            ("intent", "TEXT DEFAULT 'legacy'"),
            ("parent", "INTEGER"),
            ("root", "INTEGER"),
            ("depth", "INTEGER DEFAULT 0"),
            ("kind", "TEXT DEFAULT 'task'"),
            ("board_seen", "TEXT DEFAULT ''"),
            ("revision_used", "INTEGER"),
        ]:
            if name not in columns:
                c.execute("ALTER TABLE tasks ADD COLUMN " + name + " " + definition)
        if c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            for i, (name, role, color, context) in enumerate(ROLES):
                x, y = DESKS[i]
                c.execute(
                    "INSERT INTO employees(id,name,role,color,context,manager,slot,x,y) VALUES(?,?,?,?,?,?,?,?,?)",
                    (i, name, role, color, context, int(i == 0), i, x, y),
                )
        c.execute(
            "CREATE INDEX IF NOT EXISTS messages_employee_id ON messages(employee,id)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS tasks_status_id ON tasks(status,id)")
        c.execute(
            "CREATE INDEX IF NOT EXISTS tool_jobs_status_poll ON tool_jobs(status,next_poll,id)"
        )
        if "skin" not in {r["name"] for r in c.execute("PRAGMA table_info(employees)")}:
            c.execute("ALTER TABLE employees ADD COLUMN skin TEXT DEFAULT '{}'")
        if not c.execute("SELECT id FROM game_world WHERE id=1").fetchone():
            c.execute(
                "INSERT INTO game_world(id,layout,player) VALUES(1,?,?)",
                (
                    json.dumps(default_layout()),
                    json.dumps({"name": "Lucas", "skin": DEFAULT_SKIN}),
                ),
            )
        row = c.execute("SELECT layout FROM game_world WHERE id=1").fetchone()
        layout = json.loads(row["layout"])
        if not any(i["kind"] == "server_panel" for i in layout):
            layout += [
                i for i in default_layout() if i["kind"] in ("server", "server_panel")
            ]
            c.execute(
                "UPDATE game_world SET layout=?,revision=revision+1 WHERE id=1",
                (json.dumps(layout),),
            )

        c.execute("UPDATE tasks SET root=id WHERE root IS NULL")
        town_module.Town.schema(c)
        failure_center.schema(c)
        failure_center.sync(c)
        c.execute("PRAGMA user_version=1")


def config():
    p = STATE_ROOT / "config.json"
    return (
        json.loads(p.read_text("utf-8"))
        if p.exists()
        else {"mode": "demo", "base_url": "", "model": ""}
    )


def event(c, emp, content):
    c.execute(
        "INSERT INTO events(employee,content,created) VALUES(?,?,?)",
        (emp, content, time.time()),
    )


def employee(c, emp):
    e = c.execute("SELECT * FROM employees WHERE id=? AND active=1", (emp,)).fetchone()
    if not e:
        raise ValueError("Funcionário não encontrado.")
    return dict(e)


def create_task(c, emp, title, parent=None, kind="task", intent="project"):
    employee(c, emp)
    root = None
    depth = 0
    if parent:
        p = c.execute("SELECT * FROM tasks WHERE id=?", (parent,)).fetchone()
        if not p:
            raise ValueError("Tarefa de origem não encontrada.")
        root = p["root"] or p["id"]
        depth = p["depth"] + 1
        intent = p["intent"]
        if (
            depth > 3
            or c.execute("SELECT COUNT(*) FROM tasks WHERE root=?", (root,)).fetchone()[
                0
            ]
            >= 12
        ):
            raise ValueError(
                "Limite de colaboração atingido para esta demanda (12 etapas, profundidade 3)."
            )
    cur = c.execute(
        "INSERT INTO tasks(employee,title,parent,root,depth,kind,intent) VALUES(?,?,?,?,?,?,?)",
        (emp, title, parent, root, depth, kind, intent),
    )
    tid = cur.lastrowid
    if not root:
        c.execute("UPDATE tasks SET root=? WHERE id=?", (tid, tid))
    return tid


def normalize(text):
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", str(text).lower())
        if not unicodedata.combining(ch)
    )


def knowledge_changed(c):
    c.execute("UPDATE knowledge_meta SET revision=revision+1 WHERE id=1")


def save_memory(
    c,
    emp,
    title,
    content,
    kind="aprendizado",
    scope="individual",
    source="manual",
    source_task=None,
    status="confirmed",
    memory_id=None,
):
    employee(c, emp)
    title = str(title).strip()
    content = str(content).strip()
    if not title or not content or len(title) > 120 or len(content) > 3000:
        raise ValueError(
            "Memória precisa de título (até 120) e conteúdo (até 3000 caracteres)."
        )
    if kind not in ("aprendizado", "decisao", "preferencia", "procedimento"):
        raise ValueError("Categoria de memória inválida.")
    if scope not in ("individual", "compartilhada"):
        raise ValueError("Escopo inválido.")
    if status not in ("suggested", "confirmed", "inactive"):
        raise ValueError("Estado de memória inválido.")
    now = time.time()
    search = normalize(title + " " + content)
    old = None
    if memory_id is not None:
        old = c.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        if not old:
            raise ValueError("Memória não encontrada.")
        # Human corrections keep original provenance and task reference.
        source = old["source"]
        source_task = old["source_task"]
        c.execute(
            "UPDATE memories SET employee=?,scope=?,kind=?,title=?,content=?,search_text=?,status=?,revision=revision+1,updated=? WHERE id=?",
            (emp, scope, kind, title, content, search, status, now, memory_id),
        )
    else:
        old = c.execute(
            "SELECT id FROM memories WHERE employee=? AND scope=? AND title=? AND content=?",
            (emp, scope, title, content),
        ).fetchone()
        if old:
            if source == "manual":
                return save_memory(
                    c,
                    emp,
                    title,
                    content,
                    kind,
                    scope,
                    status=status,
                    memory_id=old["id"],
                )
            return old["id"]
        memory_id = c.execute(
            "INSERT INTO memories(employee,scope,kind,title,content,search_text,source,source_task,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                emp,
                scope,
                kind,
                title,
                content,
                search,
                source,
                source_task,
                status,
                now,
                now,
            ),
        ).lastrowid
    snapshot = dict(
        c.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    )
    c.execute(
        "INSERT INTO memory_versions(memory,snapshot,created) VALUES(?,?,?)",
        (memory_id, json.dumps(snapshot, ensure_ascii=False), now),
    )
    knowledge_changed(c)
    return memory_id


def record_delivery(c, t, content):
    if not content.strip():
        return None
    old = c.execute("SELECT id FROM archives WHERE task=?", (t["id"],)).fetchone()
    if old:
        return old["id"]
    aid = c.execute(
        "INSERT INTO archives(task,employee,title,content,search_text,demo,created) VALUES(?,?,?,?,?,?,?)",
        (
            t["id"],
            t["employee"],
            t["title"],
            content,
            normalize(t["title"] + " " + content),
            int(content.startswith("[DEMONSTRAÇÃO")),
            time.time(),
        ),
    ).lastrowid
    knowledge_changed(c)
    return aid


def write_delivery(aid):
    with db() as c:
        a = c.execute("SELECT * FROM archives WHERE id=?", (aid,)).fetchone()
    if not a:
        return
    folder = DATA / "entregas"
    folder.mkdir(exist_ok=True)
    path = folder / f"tarefa-{a['task']}.txt"
    temp = folder / f".tarefa-{a['task']}.tmp"
    temp.write_text(
        f"Tarefa #{a['task']} — {a['title']}\nFuncionário #{a['employee']}\n\n{a['content']}",
        encoding="utf-8",
    )
    temp.replace(path)


def recover_deliveries():
    with db() as c:
        for t in c.execute(
            "SELECT * FROM tasks WHERE status='concluida' AND result!='' AND id NOT IN (SELECT task FROM archives)"
        ).fetchall():
            record_delivery(c, dict(t), t["result"])
        ids = [(r["id"], r["task"]) for r in c.execute("SELECT id,task FROM archives")]
    for aid, tid in ids:
        if not (DATA / "entregas" / f"tarefa-{tid}.txt").exists():
            try:
                write_delivery(aid)
            except OSError:
                pass  # SQLite remains the authoritative copy if the folder is read-only.


STOPWORDS = set(
    "a o as os de da do das dos e em para por com um uma uns umas que qual quais como meu minha seus suas seu sua voce eu nos isso isto esse essa aquele aquela tarefa trabalho favor sobre quero fazer feito ja foi sao ser ter tem nao sim este esta todos todas agora preciso".split()
)


def search_terms(text):
    return list(
        dict.fromkeys(
            w
            for w in re.findall(r"[a-z0-9]+", normalize(text))
            if len(w) > 1 and w not in STOPWORDS
        )
    )[:24]


def knowledge_records(
    c, emp=None, query="", section="all", include_inactive=False, manager=False
):
    if section not in ("all", "memories", "archives"):
        raise ValueError("Tipo de consulta inválido.")
    terms = search_terms(query)
    items = []
    for table, typ in [("memories", "memory"), ("archives", "archive")]:
        if section != "all" and section != table:
            continue
        where = []
        args = []
        if emp is not None and not manager:
            where.append(
                '(employee=? OR scope="compartilhada")'
                if typ == "memory"
                else "employee=?"
            )
            args.append(emp)
        if typ == "memory" and not include_inactive:
            where.append("status!='inactive'")
        if terms:
            where.append("(" + " OR ".join("search_text LIKE ?" for _ in terms) + ")")
            args.extend("%" + t + "%" for t in terms)
        fields = (
            "id,employee,scope,kind,title,content,source,source_task,status,revision,created,updated"
            if typ == "memory"
            else "id,employee,task,title,content,demo,created"
        )
        # Search runs in SQLite over the full text; previews stay bounded.
        rows = c.execute(
            "SELECT "
            + fields
            + " FROM "
            + table
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY id DESC",
            args,
        )
        for row in rows:
            item = dict(row)
            item["type"] = typ
            title = normalize(item["title"])
            body = normalize(item["content"])
            item["_score"] = sum(6 * title.count(t) + body.count(t) for t in terms) + (
                2 if item.get("status") == "confirmed" else 0
            )
            if typ == "archive":
                hit = min((body.find(t) for t in terms if t in body), default=0)
                start = max(0, hit - 240) if terms else 0
                original = item["content"]
                item["content"] = (
                    ("…" if start else "")
                    + original[start : start + 1800]
                    + ("…" if start + 1800 < len(original) else "")
                )
            items.append(item)
    items.sort(
        key=lambda x: (
            x["_score"] if terms else 0,
            x.get("updated", x["created"]),
            x["id"],
        ),
        reverse=True,
    )
    for item in items:
        item.pop("_score", None)
    return items


def retrieve_knowledge(c, emp, text):
    e = employee(c, emp)
    can_manage = bool(e["manager"])
    result = []
    seen = set()
    budget = 14000
    # Relevant records plus a few recent records retain continuity without sending the entire archive.
    ranked = (
        knowledge_records(c, emp, text, manager=can_manage)
        + knowledge_records(c, emp, manager=can_manage)[:4]
    )
    for item in ranked:
        key = (item["type"], item["id"])
        if key in seen or item.get("demo"):
            continue
        seen.add(key)
        item = dict(item)
        item["content"] = item["content"][: 1800 if item["type"] == "archive" else 2500]
        cost = len(json.dumps(item, ensure_ascii=False))
        if cost > budget:
            continue
        budget -= cost
        result.append(item)
        if len(result) >= 12:
            break
    return result


# Shared world data drives both the editor and server-side navigation.
WORLD_WALLS = [
    (35, 35, 1370, 18),
    (35, 947, 545, 18),
    (720, 947, 1150, 18),
    (35, 35, 18, 930),
    (1387, 35, 18, 165),
    (1387, 310, 18, 415),
    (1387, 835, 18, 130),
    (960, 45, 16, 145),
    (960, 270, 16, 410),
    (960, 770, 16, 180),
    (970, 470, 420, 16),
    (1405, 470, 465, 18),
    (1852, 470, 18, 495),
    (1405, 35, 465, 18),
    (1852, 35, 18, 423),
    (1405, 440, 465, 18),
]
WORLD_ZONES = [
    (53, 53, 1334, 894),
    (1387, 725, 40, 110),
    (1405, 488, 447, 459),
    (1387, 200, 40, 110),
    (1405, 53, 447, 387),
]
CATALOG = {
    **{
        k: {"name": name, "w": w, "d": d, "solid": solid, "color": color}
        for k, name, w, d, solid, color in [
            ("lamp", "Luminária", 32, 32, True, "#e2c47e"),
            ("screen", "Painel digital", 150, 40, False, "#4c7881"),
            ("aquarium", "Aquário", 100, 48, True, "#6baab0"),
            ("clock", "Relógio", 45, 28, False, "#b2bda3"),
            ("printer", "Impressora", 65, 48, True, "#d2d6cd"),
            ("beanbag", "Pufe", 65, 55, True, "#bc93af"),
            ("speaker", "Caixa de ambiente", 35, 35, True, "#526f7b"),
        ]
    },
    "server": {
        "name": "Rack de servidores",
        "w": 80,
        "d": 65,
        "solid": True,
        "color": "#344d5d",
    },
    "server_panel": {
        "name": "Painel de integrações",
        "w": 150,
        "d": 45,
        "solid": False,
        "color": "#4e8075",
    },
    "workdesk": {
        "name": "Estação de trabalho",
        "w": 155,
        "d": 68,
        "solid": True,
        "color": "#dfc4a1",
    },
    "executive": {
        "name": "Mesa da diretoria",
        "w": 180,
        "d": 80,
        "solid": True,
        "color": "#a58766",
    },
    "inbox": {
        "name": "Arquivo de entregas",
        "w": 80,
        "d": 55,
        "solid": True,
        "color": "#6c9184",
    },
    "board": {
        "name": "Quadro da equipe",
        "w": 180,
        "d": 62,
        "solid": False,
        "color": "#e7dcc0",
    },
    "table": {
        "name": "Mesa de reunião",
        "w": 210,
        "d": 130,
        "solid": True,
        "color": "#d8bd96",
    },
    "coffee": {
        "name": "Mesa de centro",
        "w": 110,
        "d": 55,
        "solid": True,
        "color": "#c4a17c",
    },
    "sofa": {"name": "Sofá", "w": 230, "d": 65, "solid": True, "color": "#90a496"},
    "chair": {"name": "Cadeira", "w": 42, "d": 38, "solid": False, "color": "#6b8b81"},
    "shelf": {"name": "Estante", "w": 50, "d": 200, "solid": True, "color": "#c3a784"},
    "cabinet": {
        "name": "Armário baixo",
        "w": 130,
        "d": 39,
        "solid": True,
        "color": "#b99b74",
    },
    "kitchen": {
        "name": "Bancada da copa",
        "w": 320,
        "d": 56,
        "solid": True,
        "color": "#91a18f",
    },
    "plant": {"name": "Planta", "w": 30, "d": 30, "solid": True, "color": "#69976e"},
    "rug": {"name": "Tapete", "w": 230, "d": 150, "solid": False, "color": "#92a391"},
    "partition": {
        "name": "Divisória modular",
        "w": 120,
        "d": 16,
        "solid": True,
        "color": "#b8baa9",
    },
    "planter": {
        "name": "Jardineira longa",
        "w": 110,
        "d": 35,
        "solid": True,
        "color": "#8dac86",
    },
    "bookcase": {
        "name": "Estante baixa",
        "w": 120,
        "d": 35,
        "solid": True,
        "color": "#bb9c78",
    },
    "ottoman": {
        "name": "Pufe retangular",
        "w": 60,
        "d": 45,
        "solid": False,
        "color": "#b99aad",
    },
    "art": {
        "name": "Quadro decorativo",
        "w": 125,
        "d": 36,
        "solid": False,
        "color": "#526f66",
    },
}
DEFAULT_SKIN = {
    "skin": "#e7b68f",
    "hair": "#3a3836",
    "hairStyle": "short",
    "shirt": "#c5dfa1",
    "pants": "#344957",
    "shoes": "#243039",
    "accessory": "none",
    "outfit": "casual",
    "gender": "unspecified",
    "body": "regular",
    "beard": "none",
    "bottom": "pants",
    "pattern": "plain",
    "accent": "#e6c58a",
    "bodyType": "auto",
}


def default_layout():
    items = []

    def add(id, kind, x, y, **kw):
        items.append(
            dict(
                id=id,
                kind=kind,
                x=x,
                y=y,
                rotation=0,
                color=CATALOG[kind]["color"],
                **kw,
            )
        )

    for i, (x, y) in enumerate(
        [(x, y) for y in (235, 470) for x in (210, 385, 560, 735)]
    ):
        add("desk-" + str(i), "workdesk", x, y, slot=i)
    for id, kind, x, y in [
        ("board", "board", 530, 96),
        ("meeting", "table", 1070, 165),
        ("kitchen", "kitchen", 1040, 520),
        ("reception-sofa", "sofa", 110, 805),
        ("lounge-sofa", "sofa", 1040, 830),
        ("books", "shelf", 80, 365),
        ("cabinet", "cabinet", 745, 660),
        ("coffee", "coffee", 760, 785),
        ("lounge-table", "coffee", 1155, 735),
        ("owner-desk", "executive", 1510, 650),
        ("owner-inbox", "inbox", 1740, 580),
        ("owner-sofa", "sofa", 1460, 850),
        ("owner-rug", "rug", 1480, 730),
        ("art", "art", 760, 99),
    ]:
        add(id, kind, x, y)
    for i, (x, y) in enumerate(
        [
            (100, 150),
            (900, 100),
            (900, 670),
            (1300, 105),
            (1000, 895),
            (95, 690),
            (1800, 875),
            (1460, 525),
        ]
    ):
        add("plant-" + str(i), "plant", x, y)
    for i, (x, y) in enumerate(
        [(1080, 110), (1180, 110), (1080, 325), (1180, 325), (1010, 210), (1300, 210)]
    ):
        add("chair-" + str(i), "chair", x, y)
    for i, x in enumerate((1470, 1600, 1730)):
        add("server-" + str(i), "server", x, 120)
    add("server-panel", "server_panel", 1480, 335)
    return items


def clean_skin(value):
    if not isinstance(value, dict):
        raise ValueError("Aparência inválida.")
    skin = dict(DEFAULT_SKIN)
    for key in ("skin", "hair", "shirt", "pants", "shoes", "accent"):
        if key in value:
            if not isinstance(value[key], str) or not re.fullmatch(
                r"#[0-9a-fA-F]{6}", value[key]
            ):
                raise ValueError("Cor inválida em " + key)
            skin[key] = value[key]
    for key, allowed in [
        (
            "hairStyle",
            (
                "short",
                "long",
                "curly",
                "bald",
                "bob",
                "ponytail",
                "afro",
                "braids",
                "mohawk",
                "bun",
                "pixie",
                "twintails",
                "sidecut",
            ),
        ),
        (
            "accessory",
            (
                "none",
                "glasses",
                "tie",
                "headphones",
                "cap",
                "hat",
                "earrings",
                "scarf",
                "backpack",
                "watch",
                "bow",
            ),
        ),
        (
            "outfit",
            (
                "casual",
                "shirt",
                "suit",
                "hoodie",
                "dress",
                "blazer",
                "vest",
                "coat",
                "polo",
                "overalls",
                "cardigan",
                "sport",
                "labcoat",
            ),
        ),
        ("gender", ("unspecified", "woman", "man", "nonbinary")),
        ("body", ("slim", "regular", "broad")),
        ("bodyType", ("auto", "feminine", "masculine", "neutral")),
        ("beard", ("none", "stubble", "full", "moustache")),
        ("bottom", ("pants", "shorts", "skirt")),
        ("pattern", ("plain", "stripes", "dots", "checks")),
    ]:
        if key in value:
            if value[key] not in allowed:
                raise ValueError("Opção de aparência inválida.")
            skin[key] = value[key]
    return skin


def world_state(c):
    row = c.execute("SELECT * FROM game_world WHERE id=1").fetchone()
    plan = c.execute("SELECT rooms FROM office_plan WHERE id=1").fetchone()
    rooms = json.loads(plan["rooms"]) if plan else None
    outline_row = c.execute("SELECT outline FROM office_outline WHERE id=1").fetchone()
    outline = json.loads(outline_row["outline"]) if outline_row else None
    walls, zones = floorplan.geometry(rooms, WORLD_WALLS, WORLD_ZONES, outline)
    return {
        "revision": row["revision"],
        "layout": floorplan.Layout(
            json.loads(row["layout"]), walls, zones, floorplan.exit_point(outline)
        ),
        "rooms": rooms,
        "outline": outline,
        "exit": floorplan.exit_point(outline),
        "originalGeometry": {"walls": WORLD_WALLS, "zones": WORLD_ZONES},
        "player": json.loads(row["player"]),
        "catalog": CATALOG,
        "walls": walls,
        "zones": zones,
        "width": outline["width"] + 70 if outline else 1900,
        "height": outline["height"] + 70 if outline else 1000,
        "preferences": customization.preferences(c),
        "objectStates": customization.states(c),
        "objectActions": customization.ACTIONS,
    }


def item_bounds(item):
    info = CATALOG[item["kind"]]
    w, d = info["w"], info["d"]
    return (
        (item["x"], item["y"], d, w)
        if item["rotation"] in (90, 270)
        else (item["x"], item["y"], w, d)
    )


def local_point(item, lx, ly):
    w, d = CATALOG[item["kind"]]["w"], CATALOG[item["kind"]]["d"]
    x, y = item["x"], item["y"]
    rot = item["rotation"]
    return (
        (x + lx, y + ly)
        if rot == 0
        else (x + d - ly, y + lx)
        if rot == 90
        else (x + w - lx, y + d - ly)
        if rot == 180
        else (x + ly, y + w - lx)
    )


def station_position(layout, slot):
    item = next(i for i in layout if i["kind"] == "workdesk" and i["slot"] == slot)
    return local_point(item, 78, 100)


def inbox_position(layout):
    item = next(i for i in layout if i["kind"] == "inbox")
    return local_point(item, 40, 90)


def point_in_world(x, y, zones=None):
    return any(
        a <= x <= a + w and b <= y <= b + h
        for a, b, w, h in (WORLD_ZONES if zones is None else zones)
    )


def blocked(x, y, layout=None):
    if layout is None:
        with db() as c:
            layout = world_state(c)["layout"]
    return (
        not point_in_world(x, y, getattr(layout, "zones", WORLD_ZONES))
        or any(
            a - 13 < x < a + w + 13 and b - 13 < y < b + h + 13
            for a, b, w, h in getattr(layout, "walls", WORLD_WALLS)
        )
        or any(
            CATALOG[i["kind"]]["solid"]
            and a - 13 < x < a + w + 13
            and b - 13 < y < b + h + 13
            for i in layout
            for a, b, w, h in [item_bounds(i)]
        )
    )


def route(x, y, tx, ty, layout=None):
    if layout is None:
        with db() as c:
            layout = world_state(c)["layout"]
    if blocked(tx, ty, layout):
        return []
    start = (round(x / 20), round(y / 20))
    end = (round(tx / 20), round(ty / 20))
    q = [start]
    prev = {start: None}
    for a, b in q:
        if (a, b) == end:
            p = []
            cur = end
            while cur is not None:
                p.append((cur[0] * 20, cur[1] * 20))
                cur = prev[cur]
            return list(reversed(p)) + [(tx, ty)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (a + dx, b + dy)
            if n not in prev and not blocked(n[0] * 20, n[1] * 20, layout):
                prev[n] = (a, b)
                q.append(n)
    return []


def validate_layout(value, walls=None, zones=None, rooms=None, outline=None):
    walls = WORLD_WALLS if walls is None else walls
    zones = WORLD_ZONES if zones is None else zones
    if not isinstance(value, list) or not 12 <= len(value) <= 80:
        raise ValueError("Use entre 12 e 80 móveis.")
    items = floorplan.Layout([], walls, zones, floorplan.exit_point(outline))
    ids = set()
    slots = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("Móvel inválido.")
        id = str(raw.get("id", ""))
        kind = raw.get("kind")
        if (
            not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", id)
            or id in ids
            or kind not in CATALOG
        ):
            raise ValueError("Identidade ou tipo de móvel inválido.")
        ids.add(id)
        x = float(raw["x"])
        y = float(raw["y"])
        rot = int(raw.get("rotation", 0))
        color = raw.get("color", CATALOG[kind]["color"])
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or rot not in (0, 90, 180, 270)
            or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
        ):
            raise ValueError("Posição, rotação ou cor inválida.")
        item = dict(id=id, kind=kind, x=x, y=y, rotation=rot, color=color)
        item["label"] = str(raw.get("label", ""))[:80]
        item["variant"] = str(raw.get("variant", "classic"))
        if item["variant"] not in ("classic", "modern", "striped"):
            raise ValueError("Acabamento inválido.")
        if kind == "workdesk":
            slot = int(raw["slot"])
            if slot not in range(8):
                raise ValueError("Estação inválida.")
            item["slot"] = slot
            slots.append(slot)
        a, b, w, d = item_bounds(item)
        if not all(
            point_in_world(px, py, zones)
            for px, py in [(a, b), (a + w, b), (a, b + d), (a + w, b + d)]
        ):
            raise ValueError("Móvel fora do escritório: " + id)
        if any(
            a < u + uw and a + w > u and b < v + vh and b + d > v
            for u, v, uw, vh in walls
        ):
            raise ValueError("Móvel sobre uma parede: " + id)
        items.append(item)
    if sorted(slots) != list(range(8)):
        raise ValueError("Mantenha as 8 estações de trabalho.")
    for kind in ("executive", "inbox", "board", "server_panel"):
        if sum(i["kind"] == kind for i in items) != 1:
            raise ValueError("Mantenha exatamente um item: " + CATALOG[kind]["name"])
    solids = [(i, item_bounds(i)) for i in items if CATALOG[i["kind"]]["solid"]]
    for n, (i, (x, y, w, d)) in enumerate(solids):
        for j, (a, b, aw, bd) in solids[n + 1 :]:
            if x < a + aw and x + w > a and y < b + bd and y + d > b:
                raise ValueError("Móveis sobrepostos: " + i["id"] + " e " + j["id"])
    # Flood the walkable grid once to protect access to all stations and the inbox.
    start = (34, 36)
    q = [start]
    visited = {start}
    if blocked(690, 730, items):
        raise ValueError("Deixe livre o ponto de entrada na recepção.")
    for a, b in q:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (a + dx, b + dy)
            if n not in visited and not blocked(n[0] * 20, n[1] * 20, items):
                visited.add(n)
                q.append(n)
    panel = next(i for i in items if i["kind"] == "server_panel")
    targets = (
        [items.exit, (items.exit[0], items.exit[1] - 15), local_point(panel, 75, 80)]
        + [station_position(items, i) for i in range(8)]
        + [inbox_position(items)]
    )
    for r in rooms or []:
        x, y, w, h = (r[k] for k in ("x", "y", "w", "h"))
        side = r["door"]
        targets.extend(
            [(x + w / 2, y + 30), (x + w / 2, y - 30)]
            if side == "north"
            else [(x + w / 2, y + h - 30), (x + w / 2, y + h + 30)]
            if side == "south"
            else [(x + 30, y + h / 2), (x - 30, y + h / 2)]
            if side == "west"
            else [(x + w - 30, y + h / 2), (x + w + 30, y + h / 2)]
        )
    executive = next(i for i in items if i["kind"] == "executive")
    targets.append(local_point(executive, 90, 115))
    for x, y in targets:
        if blocked(x, y, items) or (round(x / 20), round(y / 20)) not in visited:
            raise ValueError(
                "O layout bloqueia acesso a uma mesa ou ao arquivo. Deixe corredores mais largos."
            )
    return items


FILE_EXTENSIONS = attachments.EXTENSIONS


def save_task_files(c, t, files, reply, internal=False):
    if not internal and t.get("intent", "project") != "project":
        return
    if not isinstance(files, list):
        files = []
    for file in files[:6]:
        try:
            name = str(file["filename"]).strip()
            content = file["content"]
            if (
                not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", name)
                or ".." in name
                or name.rsplit(".", 1)[-1].lower() not in FILE_EXTENSIONS
            ):
                raise ValueError("Nome de arquivo não permitido.")
            if not isinstance(content, str) or len(content) > 150000:
                raise ValueError("Conteúdo de arquivo inválido ou muito grande.")
            c.execute(
                "INSERT OR IGNORE INTO task_files(task,employee,filename,content,created,purpose) VALUES(?,?,?,?,?,?)",
                (
                    t["id"],
                    t["employee"],
                    name,
                    content,
                    time.time(),
                    "internal" if internal else "artifact",
                ),
            )
        except (KeyError, TypeError, ValueError) as ex:
            event(c, t["employee"], "Arquivo não salvo: " + str(ex))


def write_task_files(tid):
    with db() as c:
        files = c.execute(
            "SELECT filename,content FROM task_files WHERE task=?", (tid,)
        ).fetchall()
    folder = DATA / "arquivos" / f"tarefa-{tid}"
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = f["filename"]
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", name) or ".." in name:
            continue
        temp = folder / ("." + name + ".tmp")
        temp.write_text(f["content"], encoding="utf-8")
        temp.replace(folder / name)


def queue_delivery(c, root):
    origin = c.execute("SELECT intent FROM tasks WHERE id=?", (root,)).fetchone()
    if not origin or origin["intent"] != "project":
        return
    if c.execute("SELECT id FROM deliveries WHERE root=?", (root,)).fetchone():
        return
    if c.execute(
        "SELECT id FROM tool_jobs WHERE root=? AND status NOT IN ('succeeded','cancelled')",
        (root,),
    ).fetchone():
        return
    if c.execute(
        "SELECT COUNT(*) FROM tasks WHERE root=? AND status!='concluida'", (root,)
    ).fetchone()[0]:
        return
    manager = c.execute(
        "SELECT id FROM employees WHERE active=1 AND manager=1 ORDER BY slot LIMIT 1"
    ).fetchone()
    if not manager:
        return
    tasks = c.execute(
        "SELECT * FROM tasks WHERE root=? ORDER BY id", (root,)
    ).fetchall()
    if not tasks:
        return
    files = c.execute(
        "SELECT f.id FROM task_files f JOIN tasks t ON t.id=f.task WHERE t.root=? AND f.purpose='artifact' AND t.kind NOT IN ('consult','consultation')",
        (root,),
    ).fetchall()
    assets = c.execute(
        "SELECT id FROM assets WHERE task IN (SELECT id FROM tasks WHERE root=?)",
        (root,),
    ).fetchall()
    if not files and not assets:
        return
    summary = next(
        (t["result"] for t in reversed(tasks) if t["employee"] == manager["id"]),
        tasks[-1]["result"],
    )
    did = c.execute(
        "INSERT INTO deliveries(root,manager,title,summary,status,created) VALUES(?,?,?,?,'pending',?)",
        (root, manager["id"], tasks[0]["title"], summary, time.time()),
    ).lastrowid
    for f in files:
        c.execute(
            "INSERT INTO delivery_files(delivery,file) VALUES(?,?)", (did, f["id"])
        )
    for a in assets:
        c.execute(
            "INSERT INTO delivery_assets(delivery,asset) VALUES(?,?)", (did, a["id"])
        )
    event(c, manager["id"], f"Preparou a entrega #{did} para sua sala.")


def recover_packages():
    with db() as c:
        # Preserve historical files, but never transport old conversations after upgrade.
        c.execute(
            "UPDATE deliveries SET status='cancelled' WHERE status IN ('pending','in_transit') AND root IN (SELECT id FROM tasks WHERE intent='legacy')"
        )
        for r in c.execute(
            "SELECT DISTINCT root FROM tasks WHERE status='concluida'"
        ).fetchall():
            queue_delivery(c, r["root"])
        tids = [r[0] for r in c.execute("SELECT DISTINCT task FROM task_files")]
    for tid in tids:
        try:
            write_task_files(tid)
        except OSError:
            pass


def destination_position(layout, destination, slot=0):
    kinds = {
        "copa": ("coffee", "sofa"),
        "reuniao": ("table",),
        "biblioteca": ("shelf",),
        "recepcao": ("reception", "sofa"),
    }
    for kind in kinds.get(destination, ()):
        for item in layout:
            if item["kind"] != kind:
                continue
            x, y, w, d = item_bounds(item)
            for px, py in (
                (x + w / 2, y + d + 35),
                (x + w + 35, y + d / 2),
                (x - 35, y + d / 2),
                (x + w / 2, y - 35),
            ):
                if not blocked(px, py, layout):
                    return (px, py)
    fallback = DESTINATIONS.get(destination)
    return (
        fallback
        if fallback and not blocked(*fallback, layout)
        else station_position(layout, slot)
    )


def navigation_tick(paths, idle_at):
    with db() as c:
        town.ensure(c)
        world = world_state(c)
        layout = world["layout"]
        movement_speed = world["preferences"]["movementSpeed"]
        for r in c.execute("SELECT * FROM employees WHERE active=1").fetchall():
            if town.staff_tick(c, dict(r), layout, paths, movement_speed):
                continue
            e = dict(r)
            emp = e["id"]
            working = c.execute(
                "SELECT status FROM tasks WHERE employee=? AND status IN ('fila','indo_mesa','executando') ORDER BY id LIMIT 1",
                (emp,),
            ).fetchone()
            delivery = c.execute(
                "SELECT * FROM deliveries WHERE manager=? AND status IN ('pending','in_transit') ORDER BY id LIMIT 1",
                (emp,),
            ).fetchone()
            tool_work = c.execute(
                "SELECT id FROM tool_jobs WHERE employee=? AND status IN ('queued','running','waiting')",
                (emp,),
            ).fetchone()
            moving_delivery = (
                delivery
                and not tool_work
                and not (working and working["status"] == "executando")
            )
            dest = (
                "diretoria"
                if moving_delivery
                else "mesa"
                if working or tool_work
                else e["destination"]
            )
            target = (
                inbox_position(layout)
                if moving_delivery
                else station_position(layout, e["slot"])
                if dest == "mesa"
                else tuple(map(float, dest.split(":")[1:]))
                if dest.startswith("ponto:")
                else destination_position(layout, dest, e["slot"])
            )
            if moving_delivery:
                c.execute(
                    "UPDATE deliveries SET status='in_transit' WHERE id=?",
                    (delivery["id"],),
                )
            if dest in DESTINATIONS and not moving_delivery:
                tx, ty = target
                offset = (tx + (e["slot"] % 3 - 1) * 25, ty + (e["slot"] // 3) * 24)
                if not blocked(*offset, layout):
                    target = offset
            key = (world["revision"], dest, target)
            if emp not in paths or paths[emp][0] != key:
                paths[emp] = (key, route(e["x"], e["y"], *target, layout))
            p = paths[emp][1]
            # Spend the movement budget across waypoints, preserving the original route.
            remaining = 9 * movement_speed
            while p and remaining > 0:
                tx, ty = p[0]
                dx, dy = tx - e["x"], ty - e["y"]
                distance = math.hypot(dx, dy)
                if distance < 0.000001:
                    p.pop(0)
                    continue
                step = min(remaining, distance)
                e["x"] += dx / distance * step
                e["y"] += dy / distance * step
                remaining -= step
                if step >= distance:
                    p.pop(0)
            if abs(e["x"] - r["x"]) + abs(e["y"] - r["y"]) > 0.0001:
                c.execute(
                    "UPDATE employees SET x=?,y=? WHERE id=?", (e["x"], e["y"], emp)
                )
            if (
                moving_delivery
                and math.hypot(e["x"] - target[0], e["y"] - target[1]) < 5
            ):
                c.execute(
                    "UPDATE deliveries SET status='delivered',received=? WHERE id=?",
                    (time.time(), delivery["id"]),
                )
                event(
                    c,
                    emp,
                    f"Entregou o pacote #{delivery['id']} no arquivo da sua sala.",
                )
            if not working and not tool_work and not delivery and not p:
                idle_at.setdefault(emp, time.time())
                if time.time() - idle_at[emp] > 30 + emp % 5 * 7:
                    options = ["mesa", "copa", "reuniao", "recepcao", "biblioteca"]
                    new = options[(int(time.time() / 40) + emp) % len(options)]
                    c.execute(
                        "UPDATE employees SET destination=? WHERE id=?", (new, emp)
                    )
                    idle_at[emp] = time.time()
            else:
                idle_at[emp] = time.time()


def navigation():
    paths = {}
    idle_at = {}
    while True:
        time.sleep(0.1)
        if not paused or town.resting():
            navigation_tick(paths, idle_at)
        town.tick()


services = RuntimeContext(globals())
runtime = IntegrationRuntime(globals())
town = town_module.Town(globals())
init_db()


def build_context(emp, text, task=None):
    return task_engine.build_context(services, emp, text, task)


def generate(emp, text, task=None):
    return task_engine.generate(services, emp, text, task)


def apply_actions(c, emp, task, actions, strict=False):
    return task_engine.apply_actions(services, c, emp, task, actions, strict)


def unsupported_browser_wait(answer, task):
    return task_engine.unsupported_browser_wait(services, answer, task)


def process_task(t):
    return task_engine.process_task(services, t)


def worker():
    return task_engine.worker(
        services,
    )


def _integration_jobs():
    with db() as c:
        return c.execute(
            "SELECT id,employee,kind,status,progress FROM tool_jobs WHERE status IN ('queued','running','waiting')"
        ).fetchall()


def _asset_count():
    with db() as c:
        return c.execute("SELECT COUNT(*) FROM assets").fetchone()[0]


Handler = make_handler(services)


def create_local_server():
    for port in range(8765, 8796):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as ex:
            if (
                ex.errno not in (98, 48, 10048)
                and getattr(ex, "winerror", None) != 10048
            ):
                raise
    raise RuntimeError("Nenhuma porta local livre entre 8765 e 8795.")


def validate_web_files():
    for name in (
        "index.html",
        "style.css",
        "app.js",
        "alerts.js",
        "game-ui.js",
        "connections.js",
        "world.js",
        "town.js",
        "town-art.js",
        "town.css",
        "boot.js",
        "personalization.js",
        "catalogs.js",
    ):
        if not (ROOT / "web" / name).is_file():
            raise RuntimeError(
                "Arquivo ausente: web/" + name + ". Extraia o ZIP inteiro."
            )
    css = (ROOT / "web/style.css").read_text(encoding="utf-8")
    if not css.startswith("*{box-sizing:border-box}") or "let state" in css:
        raise RuntimeError(
            "style.css inválido. Extraia novamente a pasta web completa."
        )


def start_workers():
    runtime.recover()
    recover_deliveries()
    recover_packages()
    with db() as c:
        c.execute(
            "UPDATE tasks SET status='pausada',error='Aplicativo interrompido durante a etapa. Confira os resultados antes de tentar novamente.' WHERE status='executando'"
        )
    for name, fn in (
        ("navigation", navigation),
        ("tasks", worker),
        ("tasks-secondary", worker),
        ("tools", runtime.worker),
        ("town", town.worker),
    ):
        health.start(name, fn)


if __name__ == "__main__":
    health.acquire()
    validate_web_files()
    server = create_local_server()
    start_workers()
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"EscritorIA v{VERSION}: {url} — Ctrl+C para encerrar", flush=True)
    print(f"Pasta em uso: {ROOT}", flush=True)
    if server.server_port != 8765:
        print(
            "Outra instância ocupa a porta 8765. Use a NOVA aba desta instalação.",
            flush=True,
        )
    if not os.environ.get("OFFICE_NO_BROWSER"):
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
