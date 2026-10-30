"""On-demand Open Library and TVmaze lookups; bounded cache and no credentials."""

import copy
import html
import json
import re
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode, urlsplit


class CatalogError(ValueError):
    pass


def plain(value, limit=1800):
    if isinstance(value, dict):
        value = value.get("value", "")
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or "")))[:limit]


def trusted(value, hosts):
    try:
        p = urlsplit(str(value))
        return (
            "https://" + p.netloc + p.path + ("?" + p.query if p.query else "")
            if p.hostname in hosts
            and p.scheme in ("https", "http")
            and not p.username
            and not p.port
            else ""
        )
    except ValueError:
        return ""


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted(newurl, ("openlibrary.org", "api.tvmaze.com")):
            raise CatalogError("Redirecionamento inesperado da fonte.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Catalog:
    MODES = ("books", "book", "book_reader", "tvmaze")

    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()
        self.last = 0

    @staticmethod
    def schema(c):
        c.execute(
            "CREATE TABLE IF NOT EXISTS culture_cache(url TEXT PRIMARY KEY,data TEXT,created REAL)"
        )

    def fetch(self, url):
        with self.lock:
            with self.db() as c:
                row = c.execute(
                    "SELECT data,created FROM culture_cache WHERE url=?", (url,)
                ).fetchone()
            if row and time.time() - row["created"] < 86400:
                return json.loads(row["data"]), row["created"], True
            wait = 1.1 - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            try:
                self.last = time.monotonic()
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "EscritorIA/0.30 (local book discovery)",
                        "Accept": "application/json",
                    },
                )
                with urllib.request.build_opener(SafeRedirect()).open(
                    req, timeout=18
                ) as response:
                    raw = response.read(1500001)
                if len(raw) > 1500000:
                    raise CatalogError("A fonte retornou dados demais. Refine a busca.")
                data = json.loads(raw)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    raise CatalogError(
                        "A fonte pediu uma pausa. Aguarde um minuto antes de tentar novamente."
                    ) from e
                if e.code == 404:
                    raise CatalogError("A fonte não encontrou esse registro.") from e
                raise CatalogError(
                    "A fonte está indisponível (HTTP " + str(e.code) + ")."
                ) from e
            except (OSError, ValueError) as e:
                if isinstance(e, CatalogError):
                    raise
                raise CatalogError(
                    "Não foi possível consultar a fonte. Verifique a internet e tente novamente."
                ) from e
            stamp = time.time()
            with self.db() as c:
                c.execute(
                    "INSERT OR REPLACE INTO culture_cache(url,data,created) VALUES(?,?,?)",
                    (url, json.dumps(data), stamp),
                )
                c.execute(
                    "DELETE FROM culture_cache WHERE url NOT IN (SELECT url FROM culture_cache ORDER BY created DESC LIMIT 120)"
                )
            return data, stamp, False

    def run(self, params):
        mode = params.get("mode")
        query = params.get("query", "")
        if mode not in self.MODES:
            raise CatalogError("Escolha livros ou séries.")
        if mode in ("books", "tvmaze"):
            if not isinstance(query, str) or not 2 <= len(query.strip()) <= 160:
                raise CatalogError("Digite de 2 a 160 caracteres para buscar.")
            query = query.strip()
        if mode == "books":
            fields = "key,title,author_name,first_publish_year,edition_key,cover_i,ebook_access,language"
            url = "https://openlibrary.org/search.json?" + urlencode(
                {"q": query, "fields": fields, "limit": 8, "lang": "pt"}
            )
            raw, stamp, cached = self.fetch(url)
            items = []
            for d in raw.get("docs", [])[:8]:
                key = str(d.get("key", "")).split("/")[-1]
                if not re.fullmatch(r"OL[0-9]+W", key):
                    continue
                editions = [
                    e
                    for e in d.get("edition_key", [])
                    if isinstance(e, str) and re.fullmatch(r"OL[0-9]+M", e)
                ]
                cover = d.get("cover_i")
                items.append(
                    dict(
                        id=key,
                        title=plain(d.get("title"), 240),
                        authors=[plain(a, 100) for a in d.get("author_name", [])[:4]],
                        year=d.get("first_publish_year"),
                        edition=editions[0] if editions else None,
                        url="https://openlibrary.org/works/" + key,
                        cover="https://covers.openlibrary.org/b/id/"
                        + str(cover)
                        + "-M.jpg"
                        if isinstance(cover, int) and cover > 0
                        else "",
                        availability=plain(d.get("ebook_access", "unknown"), 30),
                        evidence="bibliographic_metadata",
                    )
                )
            return dict(
                source="Open Library",
                source_url="https://openlibrary.org",
                query=query,
                items=items,
                consulted_at=stamp,
                cached=cached,
                notice="Busca bibliográfica. Encontrar um título não significa ler seu conteúdo; a disponibilidade de leitura precisa ser consultada.",
            )
        if mode == "book":
            id = params.get("id", "")
            if not isinstance(id, str) or not re.fullmatch(r"OL[0-9]+W", id):
                raise CatalogError("Identificador de obra inválido.")
            url = "https://openlibrary.org/works/" + id
            raw, stamp, cached = self.fetch(url + ".json")
            excerpts = [
                dict(
                    text=plain(e.get("excerpt"), 800),
                    comment=plain(e.get("comment"), 300),
                )
                for e in raw.get("excerpts", [])[:2]
                if isinstance(e, dict)
            ]
            return dict(
                source="Open Library",
                id=id,
                title=plain(raw.get("title"), 240),
                url=url,
                description=plain(raw.get("description"), 3000),
                excerpts=excerpts,
                subjects=[plain(v, 80) for v in raw.get("subjects", [])[:12]],
                evidence="catalog_description_and_available_excerpts",
                full_text_read=False,
                consulted_at=stamp,
                cached=cached,
                notice="Descrição de catálogo e trechos disponibilizados pela fonte. Não é leitura integral do livro. Cite somente o material efetivamente retornado.",
            )
        if mode == "book_reader":
            id = params.get("id", "")
            if not isinstance(id, str) or not re.fullmatch(r"OL[0-9]+M", id):
                raise CatalogError("Identificador de edição inválido.")
            raw, stamp, cached = self.fetch(
                "https://openlibrary.org/api/volumes/brief/olid/" + id + ".json"
            )
            links = []
            for item in raw.get("items", [])[:8]:
                url = trusted(
                    item.get("itemURL"),
                    ("archive.org", "www.archive.org", "openlibrary.org"),
                )
                if not url:
                    continue
                match = re.match(
                    r"^/(?:stream|details)/([a-zA-Z0-9_.-]+)(?:/|$)", urlsplit(url).path
                )
                embed = (
                    "https://archive.org/embed/" + match.group(1)
                    if item.get("status") == "full access"
                    and match
                    and urlsplit(url).hostname in ("archive.org", "www.archive.org")
                    else ""
                )
                links.append(
                    dict(
                        url=url,
                        status=plain(item.get("status"), 40),
                        match=plain(item.get("match"), 20),
                        embed=embed,
                    )
                )
            return dict(
                source="Open Library / Internet Archive",
                id=id,
                items=links,
                url="https://openlibrary.org/books/" + id,
                consulted_at=stamp,
                cached=cached,
                notice="Leitura depende da edição. Empréstimos ou itens restritos são abertos no provedor; o aplicativo não contorna acesso nem pede sua senha.",
            )
        raw, stamp, cached = self.fetch(
            "https://api.tvmaze.com/search/shows?" + urlencode({"q": query})
        )
        items = []
        for item in raw[:8] if isinstance(raw, list) else []:
            d = item.get("show") or {}
            id = d.get("id")
            if not isinstance(id, int):
                continue
            items.append(
                dict(
                    id=id,
                    title=plain(d.get("name"), 240),
                    url=trusted(d.get("url"), ("www.tvmaze.com", "tvmaze.com"))
                    or "https://www.tvmaze.com/shows/" + str(id),
                    description=plain(d.get("summary")),
                    genres=[plain(v, 80) for v in d.get("genres", [])[:8]],
                    premiered=d.get("premiered"),
                    status=plain(d.get("status"), 60),
                    cover=trusted(
                        (d.get("image") or {}).get("medium"), ("static.tvmaze.com",)
                    ),
                    evidence="tv_metadata",
                )
            )
        return dict(
            source="TVmaze",
            source_url="https://www.tvmaze.com",
            license="CC BY-SA",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            query=query,
            items=items,
            consulted_at=stamp,
            cached=cached,
            notice="Catálogo de séries e programas de TV. Não fornece filmes, episódios em vídeo, streaming nem rankings de tendências.",
        )
