"""Local office customization and object actions; no network calls."""

import json
import re
import time

PREFERENCES = {
    "name": "EscritorIA",
    "floor": "#d8cbb4",
    "wall": "#eeeee3",
    "accent": "#739b8e",
    "lighting": "day",
    "floorPattern": "wood",
    "movementSpeed": 1,
    "graphicsMode": "smooth",
    "sound": False,
    "welcomeSeen": False,
}
ACTIONS = {
    "workdesk": [("computer", "Abrir computador")],
    "executive": [("tasks", "Gerenciar tarefas")],
    "inbox": [("deliveries", "Abrir entregas")],
    "board": [("board", "Abrir quadro")],
    "server": [("connections", "Ver integrações")],
    "server_panel": [("connections", "Configurar integrações")],
    "table": [("meeting", "Planejar reunião")],
    "coffee": [("coffee", "Pegar um café")],
    "kitchen": [("coffee", "Preparar café")],
    "sofa": [("sit", "Sentar e descansar")],
    "chair": [("sit", "Sentar")],
    "beanbag": [("sit", "Relaxar")],
    "shelf": [("memory", "Consultar biblioteca")],
    "cabinet": [("files", "Consultar arquivos")],
    "plant": [("water", "Regar planta")],
    "rug": [("style", "Personalizar ambiente")],
    "art": [("message", "Trocar frase")],
    "lamp": [("toggle", "Ligar / desligar")],
    "screen": [
        ("tv", "Consultar séries — TVmaze"),
        ("board", "Ver quadro"),
        ("toggle", "Ligar / desligar"),
    ],
    "aquarium": [("feed", "Alimentar peixes")],
    "clock": [("time", "Consultar horário local")],
    "printer": [("files", "Abrir documentos"), ("print", "Registrar impressão")],
    "partition": [("style", "Personalizar ambiente")],
    "planter": [("water", "Regar planta")],
    "bookcase": [("memory", "Consultar biblioteca")],
    "ottoman": [("sit", "Sentar")],
    "speaker": [("toggle", "Ativar / desativar ambiente visual")],
}


def schema(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS office_preferences(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT);
 CREATE TABLE IF NOT EXISTS object_states(object_id TEXT PRIMARY KEY,data TEXT);
 CREATE TABLE IF NOT EXISTS object_history(id INTEGER PRIMARY KEY,object_id TEXT,actor TEXT,action TEXT,created REAL);""")
    c.execute("CREATE TABLE IF NOT EXISTS visual_migrations(version TEXT PRIMARY KEY)")
    if not c.execute("SELECT 1 FROM visual_migrations WHERE version='0.30'").fetchone():
        row = c.execute("SELECT data FROM office_preferences WHERE id=1").fetchone()
        if row:
            data = json.loads(row[0])
            data["graphicsMode"] = "smooth"
            c.execute(
                "UPDATE office_preferences SET data=? WHERE id=1", (json.dumps(data),)
            )
        c.execute("INSERT INTO visual_migrations(version) VALUES('0.30')")
    row = c.execute("SELECT data FROM office_preferences WHERE id=1").fetchone()
    if row:
        data = json.loads(row[0])
        if "welcomeSeen" not in data:
            data["welcomeSeen"] = True
            c.execute(
                "UPDATE office_preferences SET data=? WHERE id=1", (json.dumps(data),)
            )
    c.execute(
        "INSERT OR IGNORE INTO office_preferences(id,data) VALUES(1,?)",
        (json.dumps(PREFERENCES),),
    )


def preferences(c):
    return dict(
        PREFERENCES,
        **json.loads(
            c.execute("SELECT data FROM office_preferences WHERE id=1").fetchone()[0]
        ),
    )


def save_preferences(c, body):
    data = preferences(c)
    if "movementSpeed" in body:
        value = body["movementSpeed"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value not in (1, 1.5, 2)
        ):
            raise ValueError("Use velocidade 1, 1,5 ou 2.")
        data["movementSpeed"] = value
    for key in ("floor", "wall", "accent"):
        if key in body:
            if not isinstance(body[key], str) or not re.fullmatch(
                r"#[0-9a-fA-F]{6}", body[key]
            ):
                raise ValueError("Cor inválida: " + key)
            data[key] = body[key]
    for key, allowed in [
        ("lighting", ("day", "warm", "night")),
        ("floorPattern", ("wood", "tiles", "plain", "checker")),
        ("graphicsMode", ("pixel", "smooth")),
    ]:
        if key in body:
            if body[key] not in allowed:
                raise ValueError("Estilo de ambiente inválido.")
            data[key] = body[key]
    if "welcomeSeen" in body:
        if body["welcomeSeen"] is not True:
            raise ValueError("Primeiro acesso só pode ser concluído.")
        data["welcomeSeen"] = True
    if "sound" in body:
        if not isinstance(body["sound"], bool):
            raise ValueError("Som inválido.")
        data["sound"] = body["sound"]
    if "name" in body:
        data["name"] = str(body["name"]).strip()[:40]
        if not data["name"]:
            raise ValueError("Informe o nome do escritório.")
    c.execute("UPDATE office_preferences SET data=? WHERE id=1", (json.dumps(data),))
    return data


def states(c):
    return {
        r["object_id"]: json.loads(r["data"])
        for r in c.execute("SELECT * FROM object_states")
    }


def interact(c, layout, object_id, action="inspect", text="", actor="player"):
    item = next((o for o in layout if o["id"] == object_id), None)
    if not item:
        raise ValueError("Objeto não encontrado. Reabra o painel.")
    actions = ACTIONS[item["kind"]]
    if action != "inspect" and action not in [a for a, label in actions]:
        raise ValueError("Ação não disponível para este móvel.")
    row = c.execute(
        "SELECT data FROM object_states WHERE object_id=?", (object_id,)
    ).fetchone()
    data = json.loads(row["data"]) if row else {}
    message = "Escolha uma ação para interagir."
    pane = None
    if action in ("toggle", "water", "feed", "coffee", "print", "message"):
        if action == "toggle":
            data["on"] = not data.get("on", True)
            message = "Ligado." if data["on"] else "Desligado."
        elif action == "message":
            message = str(text).strip()[:80]
            if not message:
                raise ValueError("Escreva uma frase.")
            data["message"] = message
        else:
            data[action + "Count"] = int(data.get(action + "Count", 0)) + 1
            data["lastAction"] = action
            data["lastAt"] = time.time()
            message = {
                "water": "Planta regada.",
                "feed": "Peixes alimentados.",
                "coffee": "Café preparado.",
                "print": "Impressão registrada no escritório; nenhum documento enviado a uma impressora física.",
            }[action]
        c.execute(
            "INSERT INTO object_states(object_id,data) VALUES(?,?) ON CONFLICT(object_id) DO UPDATE SET data=excluded.data",
            (object_id, json.dumps(data)),
        )
    elif action == "sit":
        message = "Você se sentou. Use WASD, setas ou clique no piso para levantar."
    elif action == "time":
        message = "Horário: consulte o relógio local exibido neste painel."
    elif action != "inspect":
        pane = {
            "tv": "culture",
            "computer": "chat",
            "tasks": "tasks",
            "deliveries": "inbox",
            "board": "notes",
            "connections": "connections",
            "meeting": "tasks",
            "memory": "knowledge",
            "files": "knowledge",
            "style": "decorate",
        }[action]
    if action != "inspect":
        c.execute(
            "INSERT INTO object_history(object_id,actor,action,created) VALUES(?,?,?,?)",
            (object_id, str(actor), action, time.time()),
        )
        c.execute(
            "DELETE FROM object_history WHERE id NOT IN (SELECT id FROM object_history ORDER BY id DESC LIMIT 300)"
        )
    return {
        "object": item,
        "state": data,
        "actions": [{"id": a, "label": b} for a, b in actions],
        "message": message,
        "pane": pane,
        "pose": "sitting" if action == "sit" else None,
        "history": [
            dict(r)
            for r in c.execute(
                "SELECT actor,action,created FROM object_history WHERE object_id=? ORDER BY id DESC LIMIT 8",
                (object_id,),
            )
        ],
    }
