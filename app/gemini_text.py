"""Native Gemini text adapter with model discovery and bounded 404 recovery."""

import hashlib
import time

NATIVE_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Known text families with a documented free tier. Listing alone does not prove a free quota.
FREE_TEXT_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)
AUTO_MODEL = "auto-gemini-free"


class GeminiHTTPError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def discover(request, key):
    models = {}
    token = ""
    for _ in range(10):
        url = (
            NATIVE_BASE
            + "/models?pageSize=100"
            + (
                "&pageToken="
                + __import__("urllib.parse", fromlist=["quote"]).quote(token, safe="")
                if token
                else ""
            )
        )
        result = request(url, headers={"x-goog-api-key": key})
        for model in result.get("models", []):
            name = model.get("name", "").removeprefix("models/")
            if name in FREE_TEXT_MODELS and "generateContent" in model.get(
                "supportedGenerationMethods", []
            ):
                models[name] = model
        token = result.get("nextPageToken", "")
        if not token:
            break
    return [name for name in FREE_TEXT_MODELS if name in models]


def native_payload(messages, max_tokens):
    system = []
    contents = []
    for message in messages:
        text = message.get("content", "")
        if not isinstance(text, str) or not text:
            continue
        if message["role"] == "system":
            system.append(text)
            continue
        role = "model" if message["role"] == "assistant" else "user"
        parts = [{"text": text}]
        for file in message.get("inline_files", []):
            parts.extend(
                [
                    {"text": "Arquivo: " + file["filename"]},
                    {"inlineData": {"mimeType": file["mime"], "data": file["data"]}},
                ]
            )
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    body = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max(128, min(int(max_tokens), 8000))},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
    return body


def normalize(result, model):
    candidates = result.get("candidates", [])
    if not candidates:
        raise ValueError(
            "Gemini não retornou texto. Confira permissões, cota e restrições do projeto Google."
        )
    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "\n".join(
        p["text"]
        for p in parts
        if isinstance(p.get("text"), str) and not p.get("thought")
    )
    reason = "length" if candidate.get("finishReason") == "MAX_TOKENS" else "stop"
    return {
        "model": model,
        "choices": [{"message": {"content": text}, "finish_reason": reason}],
    }


def call(request, key, messages, max_tokens, preferred=AUTO_MODEL, cache=None):
    if not key:
        raise ValueError("Cole sua chave Google no botão Conectar Gemini e testar.")
    cache = cache if cache is not None else {}
    cache_key = hashlib.sha256(key.encode()).hexdigest()
    entry = cache.get(cache_key)
    available = (
        entry[1] if entry and time.time() - entry[0] < 600 else discover(request, key)
    )
    cache[cache_key] = (time.time(), available)
    if not available:
        raise ValueError(
            "Gemini não disponibilizou nenhum modelo de texto da lista gratuita verificada para esta chave. Confira o projeto e sua cota no Google AI Studio. Nenhum modelo pago foi selecionado."
        )
    ordered = ([preferred] if preferred in available else []) + [
        m for m in available if m != preferred
    ]
    refreshed = False
    for model in ordered:
        try:
            result = request(
                NATIVE_BASE + "/models/" + model + ":generateContent",
                native_payload(messages, max_tokens),
                {"x-goog-api-key": key},
                timeout=120,
            )
            return normalize(result, model)
        except GeminiHTTPError as ex:
            if ex.status != 404:
                raise
            cache.pop(cache_key, None)
            if not refreshed:
                refreshed = True
                fresh = discover(request, key)
                cache[cache_key] = (time.time(), fresh)
                ordered.extend(m for m in fresh if m not in ordered)
    raise ValueError(
        "Gemini retornou 404 nos modelos listados para sua chave. O modelo não está acessível ao projeto. Verifique o Google AI Studio; não houve troca para serviço pago."
    )
