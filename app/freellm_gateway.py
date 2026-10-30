"""Local FreeLLMAPI transport. Never follow redirects carrying the unified key."""

import json
import re
import os
import urllib.request
import urllib.error
from urllib.parse import urlsplit

BASE = "http://127.0.0.1:3001/v1"
KEY = "FREELLM_API_KEY"
MODELS = ("auto", "auto:fast", "auto:smart", "auto:reliable")
OUTPUT_RECOVERY_LIMITS = (32768, 65536)


def text_timeout():
    try:
        value = int(os.environ.get("ATELIE_TEXT_TIMEOUT_SECONDS", "1800"))
    except ValueError:
        value = 1800
    return max(120, min(value, 7200))


def is_local(base):
    try:
        p = urlsplit(base)
        return (
            p.scheme == "http"
            and p.hostname in ("localhost", "127.0.0.1", "::1")
            and p.port == 3001
            and p.path.rstrip("/") == "/v1"
            and not (p.username or p.password or p.query or p.fragment)
        )
    except (ValueError, TypeError):
        return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_failure(error):
    """Classify a bounded error body without exposing prompts, keys or upstream text."""
    detail = {
        401: "chave unificada inválida",
        403: "acesso não autorizado",
        404: "modelo ou endpoint não encontrado",
        422: "nenhum modelo compatível com este pedido; confira os recursos exigidos no painel",
        429: "cota ou limite temporário atingido",
        502: "o roteador recebeu uma falha ao consultar os provedores; a causa não foi confirmada",
        503: "o roteador informou indisponibilidade temporária",
    }.get(error.code, "pedido recusado pelo roteador")
    code = ""
    message = ""
    try:
        raw = error.read(16385)
        if len(raw) <= 16384:
            body = json.loads(raw)
            entry = body.get("error", {}) if isinstance(body, dict) else {}
            if isinstance(entry, dict):
                code = str(entry.get("code") or entry.get("type") or "")
                message = str(entry.get("message") or "")
    except (OSError, ValueError, TypeError):
        pass
    # Only predefined summaries leave this function. Never echo a provider error body.
    signal = (code + " " + message).casefold()
    if error.code in (502, 503):
        if re.search(
            r"quota_exceeded|insufficient_quota|quota exhausted|quota exceeded|billing|insufficient balance|credit.*exhaust",
            signal,
        ):
            detail = "cota ou saldo de provedor indisponível; confira as cotas e as chaves no painel da FreeLLMAPI"
        elif re.search(
            r"invalid_api_key|authentication_error|invalid api key|incorrect api key|unauthorized",
            signal,
        ):
            detail = "credencial de um provedor recusada; confira a chave desse provedor no painel da FreeLLMAPI"
        elif re.search(
            r"no[_ ](?:available[_ ])?providers|no eligible|no.*enabled key|no.*enabled provider|all providers.*(?:failed|unavailable)",
            signal,
        ):
            detail = "o roteador não encontrou um provedor elegível ou esgotou as alternativas; confira provedores ativos, chaves, modelos, capacidade disponível e o registro desta requisição no painel"
        elif re.search(r"timeout|timed out|deadline", signal):
            detail = "um provedor demorou demais para responder; confira o registro da requisição no painel"
    return ValueError(
        f"FreeLLMAPI HTTP {error.code}: {detail}. O serviço local respondeu; isso não significa que o EscritorIA esteja desconectado."
    )


def request(base, key, path, body=None, timeout=120):
    if not is_local(base):
        raise ValueError(
            "FreeLLMAPI deve usar http://127.0.0.1:3001/v1 neste computador."
        )
    if path not in ("/models", "/chat/completions", "/images/generations"):
        raise ValueError("Operação FreeLLMAPI inválida.")
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    # Ignore system HTTP proxies for loopback; prevent redirects to another server.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            max_response = (
                24 * 1024 * 1024 if path == "/images/generations" else 8 * 1024 * 1024
            )
            raw = response.read(max_response + 1)
            if len(raw) > max_response:
                raise ValueError("Resposta FreeLLMAPI muito grande.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Resposta FreeLLMAPI inválida.")
            return result
    except urllib.error.HTTPError as ex:
        try:
            failure = http_failure(ex)
        finally:
            ex.close()
        raise failure from None
    except TimeoutError:
        raise ValueError(
            "FreeLLMAPI timeout: a resposta demorou além do prazo. Confira o registro da requisição no painel antes de tentar novamente."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError(
            "Abra o aplicativo FreeLLMAPI e confirme que ele está atendendo na porta 3001."
        ) from None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError(
            "O serviço na porta 3001 não retornou JSON válido da FreeLLMAPI."
        ) from None


def payload(messages, model, limit):
    prepared = []
    for message in messages:
        entry = {k: v for k, v in message.items() if k != "inline_files"}
        media = message.get("inline_files", [])
        if media:
            parts = [{"type": "text", "text": str(message.get("content", ""))}]
            for item in media:
                if item.get("mime") not in (
                    "image/png",
                    "image/jpeg",
                    "image/webp",
                    "image/gif",
                ):
                    raise ValueError(
                        "Este anexo exige um leitor multimodal específico. Pela FreeLLMAPI, use texto extraído ou imagens PNG/JPEG/WebP/GIF; PDF/áudio/vídeo não são enviados como se fossem compreendidos."
                    )
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:" + item["mime"] + ";base64," + item["data"]
                        },
                    }
                )
            entry["content"] = parts
        prepared.append(entry)
    body = {"model": model, "messages": prepared, "stream": False}
    if limit is not None and int(limit) > 0:
        body["max_tokens"] = max(128, min(int(limit), 65536))
    return body


def image_params(params):
    prompt = params.get("prompt", "")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2048:
        raise ValueError("Descreva a imagem em até 2048 caracteres.")
    if params.get("reference_asset"):
        raise ValueError(
            "A geração pela FreeLLMAPI não edita imagens de referência nesta versão."
        )
    if params.get("aspect_ratio") not in (None, "", "1:1"):
        raise ValueError("Use proporção 1:1 nesta integração de imagens.")
    return {
        "model": "auto",
        "prompt": prompt.strip(),
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }


def image_result(result):
    import base64

    rows = result.get("data")
    if (
        not isinstance(rows, list)
        or not rows
        or not isinstance(rows[0], dict)
        or not isinstance(rows[0].get("b64_json"), str)
    ):
        raise ValueError(
            "FreeLLMAPI não retornou imagem em base64. Habilite um modelo de imagens gratuito no painel; URLs externas não são baixadas automaticamente."
        )
    try:
        raw = base64.b64decode(rows[0]["b64_json"], validate=True)
    except (ValueError, TypeError):
        raise ValueError("Imagem FreeLLMAPI em formato inválido.") from None
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
    else:
        raise ValueError("A FreeLLMAPI deve retornar PNG ou JPEG.")
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Imagem maior que 16 MB.")
    return raw, mime
