"""Persistent office-wide failures and bounded retries of read-only operations."""

import json
import re
import time
import urllib.error

DELAYS = (15, 45)
ACTIVE = ("open", "retry_wait", "retrying")


def schema(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS alert_settings(id INTEGER PRIMARY KEY CHECK(id=1),auto_retry INTEGER DEFAULT 1);
INSERT OR IGNORE INTO alert_settings(id,auto_retry) VALUES(1,1);
CREATE TABLE IF NOT EXISTS failure_alerts(id INTEGER PRIMARY KEY,target_type TEXT,target_id INTEGER,employee INTEGER,root INTEGER,title TEXT,message TEXT,status TEXT DEFAULT 'open',attempts INTEGER DEFAULT 0,next_retry REAL DEFAULT 0,auto_safe INTEGER DEFAULT 0,created REAL,updated REAL,UNIQUE(target_type,target_id));
CREATE INDEX IF NOT EXISTS alerts_status_retry ON failure_alerts(status,next_retry);""")


def enabled(c):
    return bool(
        c.execute("SELECT auto_retry FROM alert_settings WHERE id=1").fetchone()[0]
    )


def transient(error):
    message = str(error).casefold()
    # Unknown quotas and permanent configuration errors must not consume repeated requests.
    if re.search(
        r"\b(?:400|401|402|403|404|422|429)\b|cota|saldo|faturamento|credencial|chave inv|sem acesso|permiss|configur|cancelad|interrompid|limite|formato|modelo não encontrado",
        message,
    ):
        return False
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (408, 500, 502, 503, 504)
    if isinstance(error, (TimeoutError, ConnectionError, urllib.error.URLError)):
        return True
    return bool(
        re.search(
            r"\b(?:408|500|502|503|504)\b|timeout|timed out|não foi possível conectar|nao foi possivel conectar|conexão (?:recusada|temporariamente|interrompida)|temporariamente indisponível",
            message,
        )
    )


def target(c, typ, ident):
    if typ == "task":
        row = c.execute(
            "SELECT id,employee,root,title,status,error FROM tasks WHERE id=?", (ident,)
        ).fetchone()
        return dict(row) if row else None
    if typ == "tool":
        row = c.execute(
            "SELECT j.id,j.employee,j.root,j.status,j.error,j.kind,j.params,t.title FROM tool_jobs j LEFT JOIN tasks t ON t.id=j.task WHERE j.id=?",
            (ident,),
        ).fetchone()
        return dict(row) if row else None
    return None


def record(c, typ, ident, error, allow_auto=False, now=None):
    now = time.time() if now is None else now
    item = target(c, typ, ident)
    if not item:
        return
    old = c.execute(
        "SELECT attempts FROM failure_alerts WHERE target_type=? AND target_id=?",
        (typ, ident),
    ).fetchone()
    attempts = old[0] if old else 0
    safe = (
        allow_auto
        and (typ == "task" or item.get("kind") in ("research", "browser"))
        and item["status"] != "uncertain"
    )
    scheduled = safe and enabled(c) and transient(error) and attempts < len(DELAYS)
    status = "retry_wait" if scheduled else "open"
    when = now + DELAYS[attempts] if scheduled else 0
    title = str(item.get("title") or "Atividade do escritório")[:240]
    if typ == "tool":
        title = item["kind"] + " · " + title
    message = str(error).strip()[:600] or (
        "Tempo de resposta excedido."
        if isinstance(error, TimeoutError)
        else "A atividade não foi concluída. Confira a configuração e tente novamente."
    )
    c.execute(
        """INSERT INTO failure_alerts(target_type,target_id,employee,root,title,message,status,attempts,next_retry,auto_safe,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(target_type,target_id) DO UPDATE SET employee=excluded.employee,root=excluded.root,title=excluded.title,message=excluded.message,status=excluded.status,next_retry=excluded.next_retry,auto_safe=excluded.auto_safe,updated=excluded.updated""",
        (
            typ,
            ident,
            item["employee"],
            item["root"],
            title,
            message,
            status,
            attempts,
            when,
            int(safe),
            now,
            now,
        ),
    )
    return c.execute(
        "SELECT id FROM failure_alerts WHERE target_type=? AND target_id=?",
        (typ, ident),
    ).fetchone()[0]


def sync(c):
    # Also pick up older failures and failures originating outside the main worker.
    for typ, query in (
        (
            "task",
            "SELECT t.id,t.error FROM tasks t LEFT JOIN failure_alerts a ON a.target_type='task' AND a.target_id=t.id WHERE t.status='pausada' AND t.error!='' AND a.id IS NULL",
        ),
        (
            "tool",
            "SELECT j.id,j.error FROM tool_jobs j LEFT JOIN failure_alerts a ON a.target_type='tool' AND a.target_id=j.id WHERE j.status IN ('failed','uncertain') AND a.id IS NULL",
        ),
    ):
        for row in c.execute(query).fetchall():
            record(c, typ, row["id"], row["error"], allow_auto=False)
    now = time.time()
    c.execute(
        "UPDATE failure_alerts SET status='open',next_retry=0,updated=? WHERE status='retrying' AND ((target_type='task' AND target_id IN (SELECT id FROM tasks WHERE status='pausada')) OR (target_type='tool' AND target_id IN (SELECT id FROM tool_jobs WHERE status IN ('failed','uncertain'))))",
        (now,),
    )
    c.execute(
        "UPDATE failure_alerts SET status='resolved',next_retry=0,updated=? WHERE status IN ('open','retry_wait','retrying') AND ((target_type='task' AND target_id IN (SELECT id FROM tasks WHERE status='concluida')) OR (target_type='tool' AND target_id IN (SELECT id FROM tool_jobs WHERE status IN ('succeeded','cancelled'))))",
        (now,),
    )


def resolve(c, typ, ident):
    c.execute(
        "UPDATE failure_alerts SET status='resolved',next_retry=0,updated=? WHERE target_type=? AND target_id=?",
        (time.time(), typ, ident),
    )


def mark_retry(c, typ, ident, manual=True):
    c.execute(
        "UPDATE failure_alerts SET status='retrying',next_retry=0,attempts=CASE WHEN ? THEN 0 ELSE attempts END,updated=? WHERE target_type=? AND target_id=?",
        (int(manual), time.time(), typ, ident),
    )


def configure(c, value):
    if type(value) is not bool:
        raise ValueError("Escolha ativar ou desativar a repetição automática.")
    c.execute("UPDATE alert_settings SET auto_retry=? WHERE id=1", (int(value),))
    if not value:
        c.execute(
            "UPDATE failure_alerts SET status='open',next_retry=0,updated=? WHERE status='retry_wait'",
            (time.time(),),
        )


def dismiss(c, ident):
    if not c.execute(
        "UPDATE failure_alerts SET status='dismissed',next_retry=0,updated=? WHERE id=?",
        (time.time(), ident),
    ).rowcount:
        raise ValueError("Alerta não encontrado.")


def release_due(c, reserve, now=None):
    now = time.time() if now is None else now
    if not enabled(c):
        return 0
    changed = 0
    rows = c.execute(
        "SELECT * FROM failure_alerts WHERE status='retry_wait' AND next_retry<=? ORDER BY next_retry,id",
        (now,),
    ).fetchall()
    for row in rows:
        alert = dict(row)
        item = target(c, alert["target_type"], alert["target_id"])
        if not item:
            resolve(c, alert["target_type"], alert["target_id"])
            continue
        expected = "pausada" if alert["target_type"] == "task" else "failed"
        if item["status"] != expected:
            if item["status"] in ("concluida", "succeeded", "cancelled"):
                resolve(c, alert["target_type"], alert["target_id"])
            else:
                mark_retry(c, alert["target_type"], alert["target_id"], manual=False)
            continue
        active = c.execute(
            "SELECT active FROM employees WHERE id=?", (item["employee"],)
        ).fetchone()
        if not active or not active[0]:
            c.execute(
                "UPDATE failure_alerts SET status='open',next_retry=0,message=message||' Funcionário inativo; repetição suspensa.',updated=? WHERE id=?",
                (now, alert["id"]),
            )
            continue
        if alert["attempts"] >= len(DELAYS) or not alert["auto_safe"]:
            continue
        if alert["target_type"] == "tool":
            if item.get("kind") not in ("research", "browser"):
                continue
            try:
                reserve(c, item["kind"])
            except ValueError:
                c.execute(
                    "UPDATE failure_alerts SET status='open',next_retry=0,message=message||' Limite da ferramenta impede a repetição automática.',updated=? WHERE id=?",
                    (now, alert["id"]),
                )
                continue
            c.execute(
                "UPDATE tool_jobs SET status='queued',error='',next_poll=0,updated=? WHERE id=? AND status='failed'",
                (now, item["id"]),
            )
        else:
            c.execute(
                "UPDATE tasks SET status='fila',error='' WHERE id=? AND status='pausada'",
                (item["id"],),
            )
        c.execute(
            "UPDATE failure_alerts SET status='retrying',attempts=attempts+1,next_retry=0,updated=? WHERE id=? AND status='retry_wait'",
            (now, alert["id"]),
        )
        changed += 1
    return changed


def public(c, history=False, offset=0, limit=40):
    sync(c)
    where = "" if history else " WHERE a.status IN ('open','retry_wait','retrying')"
    total = c.execute("SELECT COUNT(*) FROM failure_alerts a" + where).fetchone()[0]
    rows = c.execute(
        "SELECT a.*,e.name AS employee_name,e.active AS employee_active FROM failure_alerts a LEFT JOIN employees e ON e.id=a.employee"
        + where
        + " ORDER BY a.updated DESC,a.id DESC LIMIT ? OFFSET ?",
        (limit, max(0, offset)),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        current = target(c, item["target_type"], item["target_id"])
        status = current["status"] if current else ""
        item["target_status"] = status
        item["tool"] = current.get("kind", "") if current else ""
        item["can_retry"] = bool(
            item["employee_active"]
            and (
                (item["target_type"] == "task" and status == "pausada")
                or (
                    item["target_type"] == "tool"
                    and status == "failed"
                    and item["tool"] != "instagram"
                )
            )
        )
        item["requires_review"] = status == "uncertain" or item["tool"] == "instagram"
        items.append(item)
    counts = {
        row[0]: row[1]
        for row in c.execute(
            "SELECT status,COUNT(*) FROM failure_alerts GROUP BY status"
        )
    }
    return {
        "revision": c.execute(
            "SELECT COALESCE(MAX(updated),0) FROM failure_alerts"
        ).fetchone()[0],
        "items": items,
        "total": total,
        "open_count": sum(counts.get(k, 0) for k in ACTIVE),
        "waiting_count": counts.get("retry_wait", 0),
        "auto_retry": enabled(c),
        "max_retries": len(DELAYS),
        "delays": list(DELAYS),
    }
