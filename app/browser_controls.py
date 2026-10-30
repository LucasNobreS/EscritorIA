"""Fixed DOM observations and bounded public-navigation actions; no model-supplied code."""

import re
import unicodedata
from urllib.parse import urlsplit, parse_qs

SNAPSHOT = r"""() => {
 document.querySelectorAll('[data-atelie-control]').forEach(e=>e.removeAttribute('data-atelie-control'));
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
 const controls=[];
 for(const e of document.querySelectorAll('input,textarea,select,button,[role=button],[role=searchbox],[contenteditable=true]')){
  if(controls.length>=80)break;if(!visible(e)||e.disabled||e.getAttribute('aria-disabled')==='true')continue;
  const type=(e.type||'').toLowerCase();if(['hidden','password','file','email','tel','checkbox','radio'].includes(type))continue;
  const r=e.getBoundingClientRect(),id=String(controls.length);e.setAttribute('data-atelie-control',id);
  const label=(e.getAttribute('aria-label')||e.labels?.[0]?.innerText||e.labels?.[0]?.textContent||e.getAttribute('title')||e.innerText||e.textContent||e.placeholder||e.name||'').trim().slice(0,160);
  controls.push({id,tag:e.tagName.toLowerCase(),type,role:e.getAttribute('role')||'',label,placeholder:e.placeholder||'',value:(e.value||'').slice(0,200),on_screen:r.top<innerHeight&&r.bottom>0,bounds:{x:r.x,y:r.y,w:r.width,h:r.height},form_method:e.form?.method||'',options:e.tagName==='SELECT'?Array.from(e.options).slice(0,30).map(o=>({value:o.value,text:o.text})):undefined});
 }
 const main=document.querySelector('main')||document.querySelector('article')||document.body,text=main?.innerText||main?.textContent||'';
 const headings=Array.from(document.querySelectorAll('h1,h2,[role=heading]')).filter(visible).slice(0,30).map(e=>(e.innerText||e.textContent||'').trim().slice(0,180));
 const links=Array.from(document.querySelectorAll('a[href]')).filter(visible).slice(0,500).map(e=>({text:(e.innerText||e.textContent||e.getAttribute('aria-label')||e.title||'').trim().slice(0,200),url:e.href})).filter(l=>l.text);
 const interface_text=Array.from(document.querySelectorAll('header,nav,[role=dialog],[role=menu],[role=listbox]')).filter(visible).map(e=>e.innerText||e.textContent||'').join('\n').slice(0,3500);
 return {interface_text,text:text.slice(0,18000),truncated:text.length>18000,controls,headings,links,scroll_y:scrollY,body_signature:(document.body.innerText||document.body.textContent||'').slice(0,4000)};
}"""
UNSAFE = re.compile(
    r"\b(login|log in|sign in|sign out|logout|subscribe|unsubscribe|publish|post comment|comment|delete|remove|buy|checkout|purchase|pay|upload|download|entrar|sair|inscrever|publicar|comentar|excluir|comprar|pagar|enviar|baixar)\b",
    re.I,
)
SEARCH = re.compile(r"search|pesquis|buscar|busca|query|searchbox", re.I)


def field_is_search(c):
    return (
        c.get("type") == "search"
        or c.get("role") == "searchbox"
        or bool(
            SEARCH.search(
                " ".join(str(c.get(k, "")) for k in ("label", "placeholder", "name"))
            )
        )
    )


def control_for(decision, controls):
    ident = decision.get("id")
    if isinstance(ident, int):
        ident = str(ident)
    return next((c for c in controls if c["id"] == ident), None)


def validate_control(action, c, value=""):
    if not c:
        raise ValueError("O elemento não está na observação atual. Observe novamente.")
    if UNSAFE.search(c.get("label", "")):
        raise ValueError("Ação externa ou autenticação não autorizada nesta pesquisa.")
    if action in ("fill", "press") and not field_is_search(c):
        raise ValueError(
            "Nesta versão, digitação e Enter são permitidos apenas em campos de pesquisa identificados."
        )
    if action == "fill" and (not isinstance(value, str) or not 1 <= len(value) <= 500):
        raise ValueError("Consulta de pesquisa inválida.")
    if action == "select" and (
        c.get("tag") != "select"
        or value not in [o["value"] for o in c.get("options", [])]
    ):
        raise ValueError("Seleção inválida.")


async def interact(page, decision, controls):
    action = decision.get("action")
    if action == "scroll":
        amount = decision.get("amount", 650)
        if type(amount) not in (int, float):
            raise ValueError("Rolagem inválida.")
        await page.mouse.wheel(0, max(-900, min(900, amount)))
        return
    if action == "wait":
        try:
            await page.wait_for_function(
                'previous => (document.body.innerText||"").slice(0,4000) !== previous',
                arg=decision.get("_previous_text", ""),
                timeout=2500,
            )
        except Exception:
            pass
        return
    if action not in ("fill", "press", "click", "select"):
        raise ValueError("Ação não suportada.")
    c = control_for(decision, controls)
    validate_control(
        action,
        c,
        decision.get("text") if action == "fill" else decision.get("value", ""),
    )
    target = page.locator('[data-atelie-control="' + c["id"] + '"]')
    if action == "fill":
        await target.fill(decision["text"], timeout=7000)
    elif action == "press":
        key = decision.get("key", "Enter")
        if key not in ("Enter", "Tab", "Escape", "ArrowDown", "ArrowUp"):
            raise ValueError("Tecla não permitida.")
        await target.press(key, timeout=7000)
    elif action == "click":
        await target.click(timeout=7000)
    else:
        await target.select_option(decision["value"], timeout=7000)


def request_allowed(method, url, resource_type, hosts):
    if method == "GET":
        return True
    p = urlsplit(url)
    # Only the public web app's known read endpoints; no direct private API client or login.
    return (
        method == "POST"
        and p.hostname in hosts
        and p.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com")
        and resource_type in ("fetch", "xhr")
        and bool(
            re.fullmatch(
                r"/youtubei/v1/(search|browse|next|player|navigation/resolve_url)",
                p.path,
            )
        )
    )


def final_result(goal, decision, pages):
    outcome = decision.get("outcome", "partial")
    report = str(decision.get("report", "")).strip()[:18000]
    if outcome not in ("success", "partial", "blocked"):
        outcome = "partial"
    normalize = lambda text: " ".join(str(text).split()).casefold()
    evidence = []
    for item in (
        decision.get("evidence", [])[:20]
        if isinstance(decision.get("evidence", []), list)
        else []
    ):
        if not isinstance(item, dict):
            continue
        image_step = item.get("image_step")
        description = str(item.get("description", "")).strip()[:600]
        if (
            type(image_step) is int
            and len(description) >= 10
            and any(
                p["url"] == item.get("url")
                and p.get("step") == image_step
                and p.get("vision_used")
                for p in pages
            )
        ):
            evidence.append(
                {
                    "url": item["url"],
                    "image_step": image_step,
                    "description": description,
                }
            )
            continue
        quote = str(item.get("quote", "")).strip()[:600]
        if len(quote) < 5:
            continue
        if any(
            p["url"] == item.get("url") and normalize(quote) in normalize(p["text"])
            for p in pages
        ):
            evidence.append({"url": item["url"], "quote": quote})
    complete = outcome == "success" and bool(report) and bool(evidence)
    if re.search(
        r"não foi possível|não consegui|não tenho acesso|acesso bloqueado|sem dados suficientes|não foi encontrado",
        report,
        re.I,
    ):
        complete = False
    goal_numbers = (
        unicodedata.normalize("NFKD", goal).encode("ascii", "ignore").decode()
    )
    numbers = {
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
        "onze": 11,
        "doze": 12,
        "treze": 13,
        "quatorze": 14,
        "catorze": 14,
        "quinze": 15,
        "dezesseis": 16,
        "dezessete": 17,
        "dezoito": 18,
        "dezenove": 19,
        "vinte": 20,
    }
    goal_numbers = re.sub(
        r"\b(" + ("|".join(numbers)) + r")\b",
        lambda m: str(numbers[m.group().lower()]),
        goal_numbers,
        flags=re.I,
    )
    required = re.search(
        r"(?:top\s*|primeiros?\s+)(\d{1,2})|(\d{1,2})\s+primeiros?", goal_numbers, re.I
    )
    count = int(next(g for g in required.groups() if g)) if required else 0
    if not count:
        other = re.search(
            r"(\d{1,2})\s+(?:v[ií]deos|resultados|itens)", goal_numbers, re.I
        )
        count = int(other.group(1)) if other else 0
    observed = {link["url"]: link["text"] for p in pages for link in p["links"]}
    items = []
    seen = set()
    for item in (
        decision.get("items", [])[:50]
        if isinstance(decision.get("items", []), list)
        else []
    ):
        if (
            not isinstance(item, dict)
            or item.get("url") not in observed
            or item.get("url") in seen
        ):
            continue
        url = item["url"]
        key = url
        if "youtube" in goal.casefold():
            parsed = urlsplit(url)
            host = parsed.hostname or ""
            if host != "youtube.com" and not host.endswith(".youtube.com"):
                continue
            video = (
                parse_qs(parsed.query).get("v", [""])[0]
                if parsed.path == "/watch"
                else parsed.path.split("/shorts/", 1)[1]
                if parsed.path.startswith("/shorts/")
                else ""
            )
            if not video:
                continue
            key = "youtube:" + video
        if key in seen:
            continue
        seen.add(key)
        items.append({"position": len(items) + 1, "title": observed[url], "url": url})
    if count and len(items) < count:
        complete = False
    ranking = bool(re.search(r"em alta|trending|ranking", goal, re.I))
    ranklabel = str(decision.get("ranking_label", "")).strip()
    rankpages = [
        p
        for p in pages
        if ranklabel
        and normalize(ranklabel) in [normalize(h) for h in p.get("headings", [])]
        and re.search(
            r"em alta|trending|chart|ranking|mais populares|\btop\b", ranklabel, re.I
        )
    ]
    if ranking:
        if not rankpages:
            complete = False
        elif count:
            groups = {}
            group_keys = {}
            for p in rankpages:
                group = groups.setdefault(p["url"], [])
                keys = group_keys.setdefault(p["url"], set())
                for link in p["links"]:
                    candidate = link["url"]
                    key = candidate
                    if "youtube" in goal.casefold():
                        parsed = urlsplit(candidate)
                        host = parsed.hostname or ""
                        if host != "youtube.com" and not host.endswith(".youtube.com"):
                            continue
                        video = (
                            parse_qs(parsed.query).get("v", [""])[0]
                            if parsed.path == "/watch"
                            else parsed.path.split("/shorts/", 1)[1]
                            if parsed.path.startswith("/shorts/")
                            else ""
                        )
                        if not video:
                            continue
                        key = video
                    elif candidate not in [i["url"] for i in items]:
                        continue
                    if key not in keys:
                        group.append(candidate)
                        keys.add(key)
            order = max(groups.values(), key=len, default=[])
            if len(order) < count:
                complete = False
            items.sort(
                key=lambda i: order.index(i["url"]) if i["url"] in order else 9999
            )
            if [i["url"] for i in items[:count]] != order[:count]:
                complete = False
    if (
        ranking
        and re.search(r"brasil|brazil", goal, re.I)
        and not any(
            re.search(
                r"brasil|brazil|[?&](?:gl|region|country)=BR(?:&|$)|/br/",
                p["text"] + " " + p["url"],
                re.I,
            )
            for p in rankpages
        )
    ):
        complete = False
    if not complete and outcome == "success":
        outcome = "partial"
        report += "\nVerificação do aplicativo: não há evidências suficientes para confirmar o cumprimento integral do pedido."
    for index, item in enumerate(items, 1):
        item["position"] = index
    if count and items:
        report += "\n\nItens observados nas páginas consultadas:\n" + "\n".join(
            f"{i + 1}. {item['title']} — {item['url']}"
            for i, item in enumerate(items[:count])
        )
    return {
        "report": report,
        "complete": complete,
        "outcome": outcome,
        "items": items,
        "evidence": evidence,
        "ranking_label": ranklabel,
        "requested_count": count,
    }
