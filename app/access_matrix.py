"""Batch staff access edits with optimistic checks; credentials are never copied."""

import hashlib
import json
from chat_models import GEMINI_BASE
import gemini_text
import freellm_gateway

PRESETS = {
    "freellm": (freellm_gateway.BASE, "auto", freellm_gateway.KEY),
    "gemini": (GEMINI_BASE, gemini_text.AUTO_MODEL, "GEMINI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "GROQ_API_KEY"),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "openrouter/free",
        "OPENROUTER_API_KEY",
    ),
}


def fingerprint(profile):
    keys = (
        "employee",
        "inherit",
        "base_url",
        "model",
        "key_name",
        "max_tokens",
        "tools",
        "youtube_allowed",
    )
    return hashlib.sha256(
        json.dumps({k: profile.get(k) for k in keys}, sort_keys=True).encode()
    ).hexdigest()


def save(runtime, c, rows, tools_allowed):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
        raise ValueError("Envie de 1 a 8 funcionários para atualizar.")
    prepared = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("employee")) is not int:
            raise ValueError("Funcionário inválido na matriz.")
        emp = row["employee"]
        if emp in seen:
            raise ValueError("Funcionário repetido na matriz.")
        seen.add(emp)
        current = runtime.profile(c, emp)
        if row.get("expected") != fingerprint(current):
            raise ValueError(
                "A configuração de um funcionário mudou em outra tela. Descarte e recarregue a matriz antes de salvar."
            )
        tools = row.get("tools")
        provider = row.get("provider", "keep")
        youtube = row.get("youtube")
        if not isinstance(tools, list) or any(t not in tools_allowed for t in tools):
            raise ValueError("Recurso inválido na matriz.")
        if type(youtube) is not bool or (youtube and "research" not in tools):
            raise ValueError("YouTube exige a permissão de pesquisa.")
        if provider not in ("keep", "general", *PRESETS):
            raise ValueError("Provedor inválido na matriz.")
        updated = dict(current, tools=list(dict.fromkeys(tools)))
        if provider == "general":
            updated["inherit"] = True
        elif provider in PRESETS:
            updated.update(zip(("base_url", "model", "key_name"), PRESETS[provider]))
            updated["inherit"] = False
        prepared.append((updated, youtube))
    # Caller owns the transaction: failure in any row rolls back the whole batch.
    for profile, youtube in prepared:
        runtime.save_profile(c, profile)
        c.execute(
            "INSERT INTO agent_service_access(employee,youtube) VALUES(?,?) ON CONFLICT(employee) DO UPDATE SET youtube=excluded.youtube",
            (profile["employee"], int(youtube)),
        )
    return len(prepared)
