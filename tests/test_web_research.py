import unittest
import json
import time
from unittest.mock import patch
import test_integrations
from web_research import Research, ResearchError

s = test_integrations.s
RSS = b"""<rss version="2.0"><channel><item><title>Marketing atual</title><link>https://example.com/news</link><description>&lt;b&gt;Texto&lt;/b&gt; resumido</description><pubDate>Fri, 23 Oct 2026 10:00:00 +0000</pubDate><source>Veiculo</source></item><item><title>Data desconhecida</title><link>https://example.com/other</link><description>Resumo</description></item></channel></rss>"""


class ResearchTests(unittest.TestCase):
    def test_public_sources_dates_and_ttl_cache(self):
        r = Research()
        with patch.object(r, "fetch", return_value=RSS) as fetch:
            a = r.search({"query": "marketing", "mode": "news"})
            b = r.search({"query": "marketing", "mode": "news"})
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(a["items"]), 2)
        self.assertIn("2026-10-23", a["items"][0]["published"])
        self.assertIsNone(a["items"][1]["published"])
        self.assertTrue(b["cached"])
        self.assertEqual(a["retrieved_at"], b["retrieved_at"])
        self.assertNotIn("<b>", a["items"][0]["snippet"])
        self.assertIn("news.google.com", fetch.call_args.args[0])
        self.assertIn("when%3A7d", fetch.call_args.args[0])

    def test_social_only_queries_indexed_pages_and_unknown_date_is_explicit(self):
        r = Research()
        with patch.object(r, "fetch", return_value=RSS) as fetch:
            result = r.search({"mode": "social", "query": "tendencias"})
        self.assertIn("site%3Ainstagram.com", fetch.call_args.args[0])
        self.assertIn("não houve leitura integral", result["scope"])

    def test_bad_xml_untrusted_entities_and_queries_are_rejected(self):
        for raw in (b"<html>Blocked</html>", b"broken", b"<!DOCTYPE rss><rss/>"):
            r = Research()
            with patch.object(r, "fetch", return_value=raw):
                with self.assertRaises(ResearchError):
                    r.search({"query": "teste"})
        for params in (
            {"query": ""},
            {"query": "x" * 241},
            {"query": "x", "mode": "paid"},
            {"query": "x", "days": "abc"},
        ):
            with self.assertRaises(ResearchError):
                Research().search(params)

    def test_empty_results_and_trends_filter_never_invent_evidence(self):
        r = Research()
        with patch.object(r, "fetch", return_value=RSS):
            a = r.search({"mode": "trends", "query": "inexistente"})
        self.assertEqual(a["items"], [])
        self.assertIn("não prova", a["note"])


class ResearchIntegration(unittest.TestCase):
    setUp = test_integrations.Integrations.setUp
    tearDown = test_integrations.Integrations.tearDown
    task = test_integrations.Integrations.task

    def test_marketing_research_is_free_permissioned_and_in_model_context(self):
        t = self.task(3)
        with s.db() as c:
            self.assertIn("research", self.r.profile(c, 3)["tools"])
            jid = self.r.enqueue(
                c, 3, t, "research", {"query": "marketing", "mode": "news"}
            )
        with (
            patch.object(self.r.research, "fetch", return_value=RSS),
            patch.object(
                self.r,
                "require_key",
                side_effect=AssertionError("Research must not require a key"),
            ),
        ):
            self.r.tick()
        with s.db() as c:
            job = c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            self.assertEqual(job["status"], "succeeded")
            self.assertIn("https://example.com/news", job["result"])
            context = self.r.context(c, 3, t)
            self.assertIn("https://example.com/news", context["results"][0]["result"])
            self.r.save_profile(c, {"employee": 3, "inherit": True, "tools": ["board"]})
            with self.assertRaises(ValueError):
                self.r.enqueue(c, 3, t, "research", {"query": "negado"})
