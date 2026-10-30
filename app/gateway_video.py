"""Optional FreeLLMAPI text-to-video transport. Bounded binary result, no paid fallback."""

import http.client
import json
import time
import urllib.request
import urllib.error
import freellm_gateway


class VideoError(ValueError):
    pass


class VideoUncertain(VideoError):
    pass


MAX_VIDEO = 64 * 1024 * 1024


def validate(params):
    if not isinstance(params, dict) or set(params) - {
        "prompt",
        "duration",
        "aspect_ratio",
    }:
        raise VideoError(
            "Use descrição, duração e proporção; não envie URLs, caminhos ou comandos."
        )
    prompt = params.get("prompt", "")
    duration = params.get("duration", 6)
    aspect = params.get("aspect_ratio", "16:9")
    if not isinstance(prompt, str) or not 5 <= len(prompt.strip()) <= 2000:
        raise VideoError("Descreva a cena em 5 a 2000 caracteres.")
    if type(duration) is not int or not 4 <= duration <= 10:
        raise VideoError(
            "Escolha duração de 4 a 10 segundos, conforme suporte do provedor."
        )
    if aspect not in ("9:16", "16:9", "1:1"):
        raise VideoError("Proporção de vídeo inválida.")
    return {
        "model": "auto",
        "prompt": prompt.strip(),
        "duration": duration,
        "aspect_ratio": aspect,
    }


def generate(key, params, progress=lambda value: None):
    body = validate(params)
    progress(0)
    request = urllib.request.Request(
        freellm_gateway.BASE + "/videos/generations",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "video/mp4",
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), freellm_gateway.NoRedirect()
    )
    deadline = time.monotonic() + 330
    try:
        with opener.open(request, timeout=330) as response:
            length = int(response.headers.get("Content-Length", "0"))
            if length > MAX_VIDEO:
                raise VideoError("Vídeo gerado acima de 64 MB.")
            chunks = []
            size = 0
            while True:
                if time.monotonic() > deadline:
                    raise VideoUncertain(
                        "Tempo de geração esgotado. Confira o roteador antes de pedir novamente."
                    )
                progress(size / length * 0.95 if length > 0 else None)
                chunk = response.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_VIDEO:
                    raise VideoError("Vídeo gerado acima de 64 MB.")
                chunks.append(chunk)
            data = b"".join(chunks)
            if b"ftyp" not in data[:32]:
                raise VideoError(
                    "O roteador não retornou MP4. Confira se há um modelo de vídeo disponível e saldo/cota no provedor."
                )
            return data, {
                "provider": "FreeLLMAPI",
                "model": str(response.headers.get("X-Model", "auto"))[:150],
                "requested_duration": body["duration"],
                "aspect_ratio": body["aspect_ratio"],
            }
    except urllib.error.HTTPError as error:
        reason = {
            401: "chave unificada inválida",
            402: "saldo insuficiente ou modelo exige pagamento",
            403: "acesso negado",
            404: "endpoint ou modelo de vídeo indisponível",
            422: "nenhum modelo de vídeo compatível habilitado",
            429: "cota ou limite temporário atingido",
        }.get(error.code, "falha do roteador/provedor")
        if error.code >= 500:
            raise VideoUncertain(
                f"Vídeo HTTP {error.code}: {reason}. Confira o histórico do roteador antes de repetir."
            ) from None
        raise VideoError(
            f"Vídeo HTTP {error.code}: {reason}. Nenhuma compra ou recarga automática foi feita."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise VideoUncertain(
            "A conexão terminou sem confirmar o vídeo. Confira o histórico do roteador antes de reenviar; não houve repetição automática."
        ) from None
