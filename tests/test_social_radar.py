import json
import unittest
from unittest.mock import patch
import test_integrations
from social_radar import SocialRadar, save_tiktok
from web_research import ResearchError

s = test_integrations.s
VIDEO = {
    "id": "abcdefghijk",
    "snippet": {
        "title": "Marketing musical",
        "channelTitle": "Canal",
        "publishedAt": "2026-10-23T12:00:00Z",
        "description": "Descrição",
    },
    "statistics": {"viewCount": "123", "likeCount": "4", "commentCount": "unknown"},
}


class RadarTests(unittest.TestCase):
    setUp = test_integrations.Integrations.setUp
    tearDown = test_integrations.Integrations.tearDown
    task = test_integrations.Integrations.task

    def test_youtube_cache_metrics_and_private_key(self):
        r = SocialRadar(lambda name: "secret-key", self.r.research, s.db)
        with patch.object(r, "request", return_value={"items": [VIDEO]}) as req:
            a = r.youtube({"region": "BR", "category": "10"})
            b = r.youtube({"region": "BR", "category": "10"})
        self.assertEqual(req.call_count, 1)
        self.assertTrue(b["cached"])
        self.assertEqual(a["items"][0]["statistics"], {"views": 123, "likes": 4})
        self.assertNotIn("secret-key", json.dumps(a))
        self.assertIn("não são um ranking geral", a["scope"])
        self.assertEqual(req.call_args.args[0]["chart"], "mostPopular")

    def test_invalid_parameters_and_empty_theme_filter(self):
        r = SocialRadar(lambda name: "key", self.r.research, s.db)
        for params in (
            {"region": "evil.com"},
            {"category": "99"},
            {"query": "x" * 241},
        ):
            with self.assertRaises(ResearchError):
                r.youtube(params)
        with patch.object(
            r, "request", return_value={"items": [VIDEO, {"id": "bad-url"}]}
        ):
            self.assertEqual(r.youtube({"query": "no match"})["items"], [])

    def test_tiktok_references_persist_and_bad_set_does_not_erase(self):
        with s.db() as c:
            save_tiktok(c, "Moda | https://www.tiktok.com/tag/moda", "2026-01-01")
        for text in (
            "Título | https://tiktok.com.evil.org/x",
            "Título | https://user:pass@tiktok.com/x",
            "Sem separador",
        ):
            with s.db() as c:
                with self.assertRaises(ResearchError):
                    save_tiktok(c, text, "2026-01-01")
        result = self.r.radar.tiktok({})
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["evidence"], "owner_reference")
        self.assertIn("Não é coleta automática", result["scope"])
        with s.db() as c:
            save_tiktok(c, "", "2026-01-01")
        self.assertEqual(self.r.radar.tiktok({})["items"], [])

    def test_partial_radar_reports_missing_source_without_paid_fallback(self):
        self.r.radar.key = lambda name: None
        data = {"items": [{"title": "Buscas reais", "url": "https://example.com"}]}
        with patch.object(self.r.research, "search", return_value=data):
            result = self.r.radar.run({"mode": "radar"})
        self.assertEqual(
            [x["status"] for x in result["sections"]],
            ["available", "unavailable", "empty"],
        )
        self.assertEqual(len(result["items"]), 1)

    def test_worker_stores_radar_and_exposes_evidence_to_employee(self):
        task = self.task(3)
        with s.db() as c:
            jid = self.r.enqueue(c, 3, task, "research", {"mode": "radar"})
        with (
            patch.object(
                self.r.radar, "youtube", side_effect=ResearchError("Chave ausente")
            ),
            patch.object(self.r.research, "search", return_value={"items": []}),
        ):
            self.r.tick()
        with s.db() as c:
            job = c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            self.assertEqual(job["status"], "succeeded")
            self.assertIn("Chave ausente", job["result"])
            self.assertIn(
                "Chave ausente",
                json.dumps(self.r.context(c, 3, task), ensure_ascii=False),
            )

    def test_key_is_never_returned_in_public_configuration(self):
        self.r.store_key("YOUTUBE_API_KEY", "private-youtube-key")
        d = self.r.public_state()
        self.assertNotIn("private-youtube-key", json.dumps(d))
        self.assertTrue(
            next(x for x in d["credentials"] if x["name"] == "YOUTUBE_API_KEY")[
                "configured"
            ]
        )
