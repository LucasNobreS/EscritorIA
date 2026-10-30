"""Check public releases; never install or execute a downloaded file silently."""

import json
from pathlib import Path
import re
import urllib.request
import webbrowser


def repository(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", value
    ):
        raise ValueError(
            "Configure o repositorio publico de atualizacoes antes de distribuir."
        )
    return value


def version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError("Versao de release invalida. Use v0.24.1, por exemplo.")
    return tuple(map(int, match.groups()))


def check(current, root=None):
    root = Path(root or Path(__file__).parent)
    path = root / "release-config.json"
    if not path.is_file():
        return {
            "configured": False,
            "message": "O canal de atualizacoes ainda nao foi publicado pelo desenvolvedor.",
        }
    repo = repository(json.loads(path.read_text(encoding="utf-8")).get("repository"))
    req = urllib.request.Request(
        "https://api.github.com/repos/" + repo + "/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "EscritorIA"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Resposta de atualizacao muito grande.")
    release = json.loads(raw)
    tag = release.get("tag_name", "")
    latest = version(tag)
    newer = latest > version(current)
    asset = next(
        (
            item
            for item in release.get("assets", [])
            if item.get("name") == "EscritorIA-Setup.exe"
        ),
        None,
    )
    if newer and (release.get("draft") or release.get("prerelease") or not asset):
        raise ValueError(
            "A release mais recente ainda nao possui um instalador estavel."
        )
    # Construct the official download URL rather than trusting remote URLs.
    return {
        "configured": True,
        "available": newer,
        "version": tag,
        "url": "https://github.com/"
        + repo
        + "/releases/download/"
        + tag
        + "/EscritorIA-Setup.exe",
    }


def show_updates(current):
    import ctypes

    message = ctypes.windll.user32.MessageBoxW
    try:
        result = check(current)
        if not result["configured"]:
            message(None, result["message"], "Atualizacoes do EscritorIA", 64)
        elif not result["available"]:
            message(
                None,
                "Voce esta usando a versao mais recente publicada.",
                "Atualizacoes do EscritorIA",
                64,
            )
        elif (
            message(
                None,
                "Versao "
                + result["version"]
                + " disponivel. Baixar o instalador? Depois de baixar, feche o EscritorIA e abra o instalador. Seus dados ficam preservados.",
                "Atualizacoes do EscritorIA",
                4,
            )
            == 6
        ):
            webbrowser.open(result["url"])
    except Exception as error:
        message(
            None,
            "Nao foi possivel verificar atualizacoes. Confira sua conexao.\n"
            + str(error),
            "Atualizacoes do EscritorIA",
            48,
        )
