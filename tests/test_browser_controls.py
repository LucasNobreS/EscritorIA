import unittest
from unittest.mock import AsyncMock
import test_server
import browser_controls as c


class Controls(unittest.IsolatedAsyncioTestCase):
    async def test_search_fill_then_enter_without_changing_field(self):
        target = AsyncMock()
        page = type("Page", (), {"locator": lambda self, s: target})()
        controls = [{"id": "0", "type": "search", "label": "Pesquisar", "tag": "input"}]
        await c.interact(
            page, {"action": "fill", "id": "0", "text": "programação"}, controls
        )
        await c.interact(page, {"action": "press", "id": "0", "key": "Enter"}, controls)
        target.fill.assert_awaited_once_with("programação", timeout=7000)
        target.press.assert_awaited_once_with("Enter", timeout=7000)

    async def test_nonsearch_password_and_destructive_buttons_are_blocked(self):
        for control, action in [
            ({"id": "1", "type": "password", "label": "Senha"}, "fill"),
            ({"id": "1", "label": "Comprar agora"}, "click"),
            ({"id": "1", "label": "Publicar"}, "click"),
        ]:
            with self.assertRaises(ValueError):
                await c.interact(
                    None, {"action": action, "id": "1", "text": "segredo"}, [control]
                )
        with self.assertRaises(ValueError):
            await c.interact(None, {"action": "evaluate", "code": "evil()"}, [])

    async def test_scroll_is_bounded(self):
        page = type("Page", (), {"mouse": AsyncMock()})()
        await c.interact(page, {"action": "scroll", "amount": 99999}, [])
        page.mouse.wheel.assert_awaited_once_with(0, 900)

    def test_youtube_read_requests_allowed_but_writes_blocked(self):
        hosts = {"www.youtube.com"}
        self.assertTrue(
            c.request_allowed(
                "POST",
                "https://www.youtube.com/youtubei/v1/search?key=web",
                "xhr",
                hosts,
            )
        )
        for path in [
            "comment/create_comment",
            "subscription/subscribe",
            "like/like",
            "account/accounts_list",
        ]:
            self.assertFalse(
                c.request_allowed(
                    "POST", "https://www.youtube.com/youtubei/v1/" + path, "xhr", hosts
                )
            )
        self.assertFalse(
            c.request_allowed(
                "POST", "https://other.com/youtubei/v1/search", "xhr", hosts
            )
        )

    def test_finish_with_only_failure_report_is_not_success(self):
        result = c.final_result(
            "Pesquise conteúdo",
            {"action": "finish", "report": "Não foi possível pesquisar."},
            [],
        )
        self.assertFalse(result["complete"])
        self.assertEqual(result["outcome"], "partial")

    def test_top_ten_requires_ten_observed_items_and_ranking(self):
        links = [
            {"text": f"Vídeo {n}", "url": f"https://www.youtube.com/watch?v=video{n}"}
            for n in range(10)
        ]
        pages = [
            {
                "url": "https://www.youtube.com/trending",
                "text": "Ranking em alta Brasil: dez vídeos",
                "headings": ["Em alta Brasil"],
                "links": links,
            }
        ]
        decision = {
            "outcome": "success",
            "report": "Dez vídeos consultados",
            "evidence": [{"url": pages[0]["url"], "quote": "Ranking em alta Brasil"}],
            "items": links,
            "ranking_label": "Em alta Brasil",
        }
        result = c.final_result("Top 10 em alta YouTube Brasil", decision, pages)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["items"]), 10)
        reversed_result = c.final_result(
            "Top 10 em alta YouTube Brasil",
            {**decision, "items": list(reversed(links))},
            pages,
        )
        self.assertEqual(reversed_result["items"][0]["url"], links[0]["url"])
        extra = [
            {
                "text": f"Vídeo extra {n}",
                "url": f"https://www.youtube.com/watch?v=extra{n}",
            }
            for n in range(10)
        ]
        self.assertFalse(
            c.final_result(
                "Top 10 em alta YouTube Brasil",
                {**decision, "items": extra},
                [{**pages[0], "links": links + extra}],
            )["complete"]
        )
        self.assertFalse(
            c.final_result(
                "Top 10 em alta YouTube Brasil", {**decision, "items": links[:2]}, pages
            )["complete"]
        )
        self.assertFalse(
            c.final_result(
                "Top 10 em alta YouTube Brasil",
                {**decision, "ranking_label": "Resultados da pesquisa"},
                pages,
            )["complete"]
        )
        self.assertFalse(
            c.final_result(
                "Top 10 em alta YouTube Brasil",
                {**decision, "items": [links[0]] * 10},
                pages,
            )["complete"]
        )

    def test_invented_evidence_is_rejected(self):
        result = c.final_result(
            "Consultar informações",
            {
                "outcome": "success",
                "report": "Resposta",
                "evidence": [{"url": "https://example.com", "quote": "inventado"}],
            },
            [{"url": "https://example.com", "text": "Outro texto real", "links": []}],
        )
        self.assertFalse(result["complete"])

    def test_visual_evidence_requires_image_actually_sent_to_model(self):
        page = {
            "url": "https://example.com",
            "text": "",
            "links": [],
            "step": 2,
            "vision_used": True,
        }
        decision = {
            "outcome": "success",
            "report": "O gráfico visível é azul.",
            "evidence": [
                {
                    "url": page["url"],
                    "image_step": 2,
                    "description": "A captura recebida mostra um gráfico azul.",
                }
            ],
        }
        self.assertTrue(
            c.final_result("Descreva o gráfico visível", decision, [page])["complete"]
        )
        self.assertFalse(
            c.final_result(
                "Descreva o gráfico visível", decision, [{**page, "vision_used": False}]
            )["complete"]
        )
