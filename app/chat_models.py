"""Provider-specific chat payloads and validated final answers (no reasoning output)."""

import re

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_DEFAULT = "auto-gemini-free"


def payload(cfg, messages, limit=None):
    count = max(
        128, min(int(limit if limit is not None else cfg.get("max_tokens", 2600)), 8000)
    )
    body = {"model": cfg["model"], "messages": messages}
    if cfg.get("base_url", "").rstrip("/") == "https://api.groq.com/openai/v1":
        body["max_completion_tokens"] = count
        if cfg["model"] in ("openai/gpt-oss-20b", "openai/gpt-oss-120b"):
            body.update(reasoning_effort="low", reasoning_format="hidden")
    else:
        body["max_tokens"] = count
    return body


def final_text(result):
    choices = result.get("choices") if isinstance(result, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError(
            "O provedor não retornou uma resposta de chat. Confira o modelo e o endereço."
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("O provedor retornou uma opção de resposta inválida.")
    if choice.get("finish_reason") == "length":
        raise ValueError(
            "O provedor encerrou a resposta antes de completá-la. Nenhum trecho cortado foi entregue como arquivo final. Se isso persistir após a recuperação automática, peça uma etapa menor ou escolha no roteador um modelo com saída maior."
        )
    message = choice.get("message") or {}
    if not isinstance(message, dict):
        raise ValueError("O provedor retornou uma mensagem em formato inválido.")
    content = message.get("content")
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    if not isinstance(content, str):
        content = ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    if not content:
        raise ValueError(
            "O modelo não retornou resposta final. Confira o modelo, o limite de saída e a cota na sala de servidores; depois clique em Tentar novamente."
        )
    return content
