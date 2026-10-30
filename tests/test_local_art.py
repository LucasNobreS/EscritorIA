import io
import json
import unittest
from unittest.mock import patch
import test_integrations
from PIL import Image
import local_art

s = test_integrations.s


class LocalArt(unittest.TestCase):
    setUp = test_integrations.Integrations.setUp
    tearDown = test_integrations.Integrations.tearDown
    task = test_integrations.Integrations.task

    def test_card_formats_and_text_validation(self):
        for fmt, size in [("portrait", (1080, 1350)), ("square", (1080, 1080))]:
            data = local_art.render(
                {
                    "title": "Gestão sem complicação",
                    "subtitle": "Projetos e resultados em um só lugar.",
                    "brand": "OrganizeJust",
                    "cta": "Conheça",
                    "format": fmt,
                }
            )
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size, size)
                self.assertEqual(image.format, "JPEG")
        for params in (
            {"title": ""},
            {"title": "X", "background": "red"},
            {"title": "a" * 101},
            {"title": "ok", "subtitle": "a" * 260},
        ):
            with self.assertRaises(ValueError):
                local_art.render(params)

    def test_art_to_draft_to_mocked_instagram_preserves_actual_jpeg(self):
        t = self.task(2)
        with s.db() as c:
            jid = self.r.enqueue(
                c, 2, t, "art", {"title": "Minha publicação", "brand": "Lucas"}
            )
            job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE id=?", (jid,)).fetchone()
            )
        with patch.object(
            self.r,
            "request",
            side_effect=AssertionError("Art cannot use external services"),
        ):
            result = self.r.art(job, {"title": "Minha publicação", "brand": "Lucas"})
        with s.db() as c:
            asset = c.execute(
                "SELECT * FROM assets WHERE id=?", (result["asset_id"],)
            ).fetchone()
            self.assertEqual(asset["mime"], "image/jpeg")
            self.assertTrue(asset["data"].startswith(b"\xff\xd8"))
            c.execute("UPDATE tool_jobs SET status='succeeded' WHERE id=?", (jid,))
            c.execute("UPDATE tasks SET status='concluida' WHERE id=?", (t["id"],))
            s.queue_delivery(c, t["root"])
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM delivery_assets").fetchone()[0], 1
            )
            pid = self.r.create_post(
                c,
                2,
                t,
                {"asset_ids": [result["asset_id"]], "caption": "Minha legenda"},
                owner=True,
            )
            self.assertEqual(
                c.execute(
                    "SELECT status FROM social_posts WHERE id=?", (pid,)
                ).fetchone()[0],
                "draft",
            )
            self.r.save_settings(c, {"instagram_user_id": "123"})
            self.r.approve_post(c, pid)
            publish_job = dict(
                c.execute("SELECT * FROM tool_jobs WHERE kind='instagram'").fetchone()
            )
        with (
            patch.object(
                self.r, "ensure_public", return_value="https://example.com/art.jpg"
            ),
            patch.object(self.r, "graph", return_value={"id": "container"}) as graph,
        ):
            self.r.publish(publish_job, {"post_id": pid})
            self.assertEqual(
                graph.call_args.args[1]["image_url"], "https://example.com/art.jpg"
            )
        with patch.object(
            self.r, "graph", side_effect=[{"status_code": "FINISHED"}, {"id": "post"}]
        ):
            self.assertTrue(self.r.publish(publish_job, {"post_id": pid})["published"])
