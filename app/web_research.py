"""Public RSS discovery without keys, paid endpoints, page scraping or login."""

import re
import time
import html
import urllib.request
import urllib.error
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree as ET
from html.parser import HTMLParser


class ResearchError(ValueError):
    pass


class Plain(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)


def clean(value, limit=300):
    p = Plain()
    p.feed(str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(" ".join(p.parts))).strip()[:limit]


def public_link(value):
    p = urlsplit(str(value or ""))
    return (
        str(value)[:1200]
        if p.scheme in ("http", "https")
        and p.hostname
        and not p.username
        and not p.password
        and p.hostname not in ("localhost", "127.0.0.1", "::1")
        else ""
    )


def normal(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )


class Research:
    def __init__(self):
        self.cache = {}

    def fetch(self, url):
        class FixedHost(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                if (
                    urlsplit(newurl).scheme != "https"
                    or urlsplit(newurl).hostname != urlsplit(req.full_url).hostname
                ):
                    raise ResearchError(
                        "O feed redirecionou para fora do serviço esperado."
                    )
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "EscritorIAOffice/0.16 (RSS reader)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
        )
        try:
            with urllib.request.build_opener(FixedHost()).open(req, timeout=18) as r:
                if int(r.headers.get("Content-Length", 0)) > 700000:
                    raise ResearchError("Feed maior que o limite de leitura.")
                raw = r.read(700001)
        except urllib.error.HTTPError as ex:
            raise ResearchError(
                "Pesquisa gratuita indisponível (HTTP "
                + str(ex.code)
                + "). Aguarde e tente novamente; nenhum serviço pago foi acionado."
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ResearchError(
                "Não foi possível acessar o feed público. Confira a internet e tente novamente."
            ) from None
        if len(raw) > 700000:
            raise ResearchError("Feed maior que o limite de leitura.")
        return raw

    def search(self, params):
        query = str(params.get("query", "")).strip()
        mode = params.get("mode", "news")
        try:
            days = int(params.get("days", 7))
        except (ValueError, TypeError):
            raise ResearchError("Período de pesquisa inválido.") from None
        if mode not in ("news", "web", "social", "trends"):
            raise ResearchError("Escolha notícias, web, redes indexadas ou tendências.")
        if len(query) > 240 or (not query and mode != "trends"):
            raise ResearchError("Escreva uma busca de até 240 caracteres.")
        days = max(1, min(days, 30))
        key = (query, mode, days)
        now = time.time()
        if key in self.cache and now - self.cache[key][0] < 600:
            return dict(self.cache[key][1], cached=True)
        if mode == "trends":
            provider = "Google Trends RSS"
            url = "https://trends.google.com/trending/rss?geo=BR"
        elif mode == "news":
            provider = "Google Notícias RSS"
            url = "https://news.google.com/rss/search?" + urlencode(
                {
                    "q": query + f" when:{days}d",
                    "hl": "pt-BR",
                    "gl": "BR",
                    "ceid": "BR:pt-419",
                }
            )
        else:
            provider = "Bing RSS"
            term = query + (
                " (site:instagram.com OR site:tiktok.com OR site:youtube.com)"
                if mode == "social"
                else ""
            )
            url = "https://www.bing.com/search?" + urlencode(
                {"q": term, "format": "rss", "setlang": "pt-BR"}
            )
        raw = self.fetch(url)
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ResearchError("O serviço retornou um XML não permitido.")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            raise ResearchError(
                "O serviço não retornou RSS válido; ele pode estar temporariamente indisponível."
            ) from None
        if root.tag.rsplit("}", 1)[-1] != "rss":
            raise ResearchError(
                "O retorno não é um feed RSS. Não foi possível pesquisar."
            )
        items = []
        seen = set()
        for item in root.findall("./channel/item"):
            title = clean(item.findtext("title"), 180)
            link = public_link(item.findtext("link"))
            snippet = clean(item.findtext("description"), 300)
            if (
                mode == "trends"
                and query
                and normal(query) not in normal(title + " " + snippet)
            ):
                continue
            if not title or not link or link in seen:
                continue
            seen.add(link)
            published = None
            raw_date = item.findtext("pubDate") or ""
            try:
                published = (
                    parsedate_to_datetime(raw_date).astimezone(timezone.utc).isoformat()
                )
            except (ValueError, TypeError, AttributeError, OverflowError):
                pass
            source = item.find("source")
            entry = {
                "title": title,
                "url": link,
                "snippet": snippet,
                "publisher": clean(source.text, 100)
                if source is not None
                else urlsplit(link).hostname,
                "published": published,
            }
            if mode == "trends":
                traffic = next(
                    (
                        clean(e.text, 60)
                        for e in item
                        if e.tag.rsplit("}", 1)[-1] == "approx_traffic"
                    ),
                    "",
                )
                if traffic:
                    entry["reported_search_bucket"] = traffic
            items.append(entry)
            if len(items) >= 6:
                break
        result = {
            "query": query,
            "mode": mode,
            "provider": provider,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "requested_days": days if mode == "news" else None,
            "items": items,
            "cached": False,
            "scope": "Descoberta pública por títulos e resumos RSS; não houve leitura integral de artigos nem acesso direto às contas sociais. Não prova engajamento nem garante tendência no seu nicho. Datas ausentes são desconhecidas.",
            "note": "Nenhum resultado encontrado. Isso não prova ausência de interesse."
            if not items
            else "Compare fontes e datas antes de propor uma campanha.",
        }
        self.cache[key] = (now, result)
        if len(self.cache) > 80:
            self.cache.pop(next(iter(self.cache)))
        return result
