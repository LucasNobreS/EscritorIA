"""Free-quota YouTube charts plus explicitly owner-supplied TikTok references."""

import json
import time
import re
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from web_research import ResearchError, clean


class SocialRadar:
    def __init__(self, key, research, db):
        self.key = key
        self.research = research
        self.db = db
        self.cache = {}

    def request(self, params, key):
        url = "https://www.googleapis.com/youtube/v3/videos?" + urlencode(
            dict(params, key=key)
        )
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"Accept": "application/json"}),
                timeout=18,
            ) as r:
                raw = r.read(1000001)
        except urllib.error.HTTPError as ex:
            raise ResearchError(
                "YouTube HTTP "
                + str(ex.code)
                + ": confira a chave, ativação da YouTube Data API v3, restrições e cota gratuita. Nenhuma alternativa paga foi acionada."
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ResearchError(
                "Não foi possível consultar o YouTube. Confira a conexão."
            ) from None
        if len(raw) > 1000000:
            raise ResearchError("Resposta do YouTube maior que o limite.")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise ResearchError("O YouTube retornou uma resposta inválida.") from None

    def youtube(self, params):
        key = self.key("YOUTUBE_API_KEY")
        if not key:
            raise ResearchError(
                "Cadastre a chave YouTube — vídeos populares em Configurações avançadas. Use um projeto com YouTube Data API v3 e cota gratuita."
            )
        region = str(params.get("region", "BR")).upper()
        category = str(params.get("category", "0"))
        query = str(params.get("query", "")).strip()
        if (
            not re.fullmatch("[A-Z]{2}", region)
            or category not in ("0", "1", "10", "20")
            or len(query) > 240
        ):
            raise ResearchError("País, categoria ou tema do radar inválido.")
        ck = (hashlib.sha256(key.encode()).hexdigest(), region, category, query)
        if ck in self.cache and time.time() - self.cache[ck][0] < 600:
            return dict(self.cache[ck][1], cached=True)
        payload = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": 10,
        }
        if category != "0":
            payload["videoCategoryId"] = category
        response = self.request(payload, key)
        items = []
        for item in response.get("items", []):
            vid = str(item.get("id", ""))
            sn = item.get("snippet", {})
            st = item.get("statistics", {})
            title = clean(sn.get("title", ""), 180)
            description = clean(sn.get("description", ""), 280)
            if not re.fullmatch(r"[\w-]{11}", vid):
                continue
            if query and query.casefold() not in (title + " " + description).casefold():
                continue
            stats = {}
            for field, label in [
                ("viewCount", "views"),
                ("likeCount", "likes"),
                ("commentCount", "comments"),
            ]:
                value = str(st.get(field, ""))
                if value.isdigit():
                    stats[label] = int(value)
            items.append(
                {
                    "title": title,
                    "url": "https://www.youtube.com/watch?v=" + vid,
                    "publisher": clean(sn.get("channelTitle", ""), 100),
                    "published": sn.get("publishedAt") or None,
                    "snippet": description,
                    "platform": "YouTube",
                    "statistics": stats,
                    "evidence": "official_chart",
                }
            )
        result = {
            "query": query,
            "mode": "youtube",
            "provider": "YouTube Data API v3 / mostPopular",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "region": region,
            "category": category,
            "items": items,
            "cached": False,
            "scope": "Charts oficiais disponíveis de música, filmes e jogos; não são um ranking geral de toda a rede. Contadores são acumulados e não medem crescimento recente. Tema filtra o lote retornado, não busca toda a plataforma.",
            "note": "Compare o contexto com seu nicho. Sem resultados não significa ausência de interesse.",
        }
        self.cache[ck] = (time.time(), result)
        if len(self.cache) > 40:
            self.cache.pop(next(iter(self.cache)))
        return result

    def tiktok(self, params):
        query = str(params.get("query", "")).casefold().strip()
        with self.db() as c:
            rows = [
                dict(r)
                for r in c.execute(
                    "SELECT title,url,observed_at,saved_at FROM radar_tiktok ORDER BY id"
                )
            ]
        items = [
            dict(
                r,
                platform="TikTok",
                publisher="Referência informada pelo usuário",
                published=None,
                snippet="Observada em "
                + r["observed_at"]
                + "; conteúdo não coletado automaticamente.",
                evidence="owner_reference",
            )
            for r in rows
            if not query or query in r["title"].casefold()
        ]
        return {
            "query": query,
            "mode": "tiktok",
            "provider": "TikTok Creative Center / referências manuais",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "cached": False,
            "scope": "Referências fornecidas pelo usuário. Não é coleta automática, ranking completo ou verificação de métricas do TikTok. Confira a data observada.",
            "note": "Abra o Creative Center e salve referências no painel para incluir no radar.",
        }

    def run(self, params, allow_youtube=True):
        mode = params.get("mode", "radar")

        def youtube():
            if not allow_youtube:
                raise ResearchError(
                    "Este funcionário não tem acesso à API do YouTube. Habilite na matriz Minha equipe."
                )
            return self.youtube(params)

        if mode == "youtube":
            return youtube()
        if mode == "tiktok":
            return self.tiktok(params)
        if mode != "radar":
            return self.research.search(params)
        sections = []
        items = []
        for name, fn in [
            (
                "Google Trends",
                lambda: self.research.search(dict(params, mode="trends", query="")),
            ),
            ("YouTube", youtube),
            ("TikTok", lambda: self.tiktok(params)),
        ]:
            try:
                data = fn()
                items.extend(data["items"])
                sections.append(
                    {
                        "platform": name,
                        "status": "available" if data["items"] else "empty",
                        "result": data,
                    }
                )
            except ResearchError as ex:
                sections.append(
                    {"platform": name, "status": "unavailable", "message": str(ex)}
                )
        return {
            "query": str(params.get("query", "")),
            "mode": "radar",
            "provider": "Radar de sinais por plataforma",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "sections": sections,
            "cached": False,
            "scope": "Fontes têm coberturas diferentes: buscas Google, charts oficiais do YouTube e referências TikTok informadas pelo usuário. Não há pontuação global nem medição de engajamento entre redes.",
            "note": "O radar preserva os resultados disponíveis e identifica fontes ausentes; nunca usa serviço pago como fallback.",
        }


def save_tiktok(c, text, observed):
    text = str(text)
    observed = str(observed)
    if len(text) > 6000:
        raise ResearchError("Use até 10 referências curtas, uma por linha.")
    try:
        day = datetime.strptime(observed, "%Y-%m-%d").date()
    except ValueError:
        raise ResearchError(
            "Informe a data em que você observou as referências."
        ) from None
    if day > datetime.now(timezone.utc).date():
        raise ResearchError("A data observada não pode estar no futuro.")
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            raise ResearchError("Cada linha deve ser: assunto | link TikTok HTTPS")
        title = clean(parts[0], 180)
        url = parts[1].strip()
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        if (
            not title
            or len(url) > 1200
            or p.scheme != "https"
            or p.username
            or p.password
            or not (host == "tiktok.com" or host.endswith(".tiktok.com"))
        ):
            raise ResearchError(
                "Informe título e link oficial HTTPS do TikTok, sem credenciais."
            )
        rows.append((title, url, observed, time.time()))
    if len(rows) > 10:
        raise ResearchError("Limite de 10 referências por conjunto.")
    c.execute("DELETE FROM radar_tiktok")
    c.executemany(
        "INSERT INTO radar_tiktok(title,url,observed_at,saved_at) VALUES(?,?,?,?)", rows
    )
