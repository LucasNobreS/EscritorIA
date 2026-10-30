import base64
import io
import json
import subprocess
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image, ImageChops
import test_game
import local_video
import motion_video
import gateway_video

s = test_game.s


def picture(color="navy"):
    out = io.BytesIO()
    Image.new("RGB", (320, 180), color).save(out, format="PNG")
    return out.getvalue()


class MotionValidation(unittest.TestCase):
    def test_procedural_scene_requires_no_invented_media_id(self):
        plan = local_video.validate(
            {
                "scenes": [
                    {
                        "kind": "motion",
                        "template": "dashboard",
                        "title": "Gestão em ação",
                        "duration": 4,
                    }
                ]
            }
        )
        self.assertNotIn("asset_id", plan["scenes"][0])
        self.assertEqual(plan["scenes"][0]["kind"], "motion")

    def test_limits_and_filter_injection_are_rejected(self):
        good = {"kind": "motion", "template": "title", "duration": 5}
        self.assertEqual(
            len(local_video.validate({"scenes": [good] * 12})["scenes"]), 12
        )
        for body in (
            {"scenes": [good] * 13},
            {"scenes": [{**good, "duration": 6}] * 12},
            {"scenes": [{**good, "template": "<script>"}]},
            {"scenes": [{**good, "items": ["x"] * 5}]},
            {"scenes": [{"asset_id": 1, "background": "black;movie=/private"}]},
            {"scenes": [{**good, "speed": 2}]},
            {"scenes": [{**good, "title": "x" * 101}]},
            {"scenes": [good], "brand": {"accent": "red"}},
            {"scenes": [good], "soundtrack": {"asset_id": 1, "path": "/private"}},
            {"scenes": [good], "quality": "4k"},
        ):
            with self.assertRaises(local_video.VideoError, msg=str(body)):
                local_video.validate(body)

    def test_templates_animate_in_all_aspect_ratios_and_keep_frame_bounds(self):
        for fmt, (w, h) in {
            "landscape": (854, 480),
            "portrait": (480, 854),
            "square": (480, 480),
        }.items():
            for template in motion_video.TEMPLATES:
                scene = {
                    "kind": "motion",
                    "template": template,
                    "duration": 4,
                    "title": "Gestão simples e próxima",
                    "subtitle": "Dados claros para organizar a rotina.",
                    "items": ["Planeje", "Acompanhe", "Conclua"],
                    "cta": "Conheça agora",
                }
                painter = motion_video.Scene(
                    scene,
                    w,
                    h,
                    {"name": "Marca • ação"},
                    screen=motion_video.image(picture())
                    if template == "dashboard"
                    else None,
                )
                first = painter.frame(0)
                later = painter.frame(1.5)
                self.assertEqual(later.size, (w, h))
                self.assertIsNotNone(
                    ImageChops.difference(first, later).getbbox(), (fmt, template)
                )

    def test_remote_plan_is_bounded_and_never_accepts_urls_or_model_code(self):
        self.assertEqual(
            gateway_video.validate({"prompt": "Uma cena de cidade"})["model"], "auto"
        )
        for body in (
            {"prompt": "x"},
            {"prompt": "Uma cidade", "duration": True},
            {"prompt": "Uma cidade", "duration": 60},
            {"prompt": "Uma cidade", "url": "http://127.0.0.1"},
            {"prompt": "Uma cidade", "aspect_ratio": "4k"},
        ):
            with self.assertRaises(gateway_video.VideoError):
                gateway_video.validate(body)

    def test_remote_insufficient_balance_does_not_retry_or_buy_anything(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            "http://127.0.0.1:3001", 402, "private upstream error", {}, None
        )
        with patch.object(
            gateway_video.urllib.request, "build_opener", return_value=opener
        ):
            with self.assertRaisesRegex(gateway_video.VideoError, "Nenhuma compra"):
                gateway_video.generate("private-key", {"prompt": "Uma cidade"})
        self.assertEqual(opener.open.call_count, 1)
        request = opener.open.call_args.args[0]
        self.assertEqual(
            request.full_url, "http://127.0.0.1:3001/v1/videos/generations"
        )
        self.assertEqual(json.loads(request.data)["model"], "auto")

    def test_remote_timeout_has_uncertain_state_and_no_automatic_second_call(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError()
        with patch.object(
            gateway_video.urllib.request, "build_opener", return_value=opener
        ):
            with self.assertRaises(gateway_video.VideoUncertain):
                gateway_video.generate("key", {"prompt": "Uma cidade"})
        self.assertEqual(opener.open.call_count, 1)


@unittest.skipUnless(all(local_video.binaries()), "FFmpeg/FFprobe não instalados")
class MotionRender(unittest.TestCase):
    def test_real_motion_mp4_has_animated_frames_and_editable_plan(self):
        body = {
            "format": "landscape",
            "quality": "480p",
            "brand": {"name": "Minha marca"},
            "scenes": [
                {
                    "kind": "motion",
                    "template": "dashboard",
                    "title": "Seu negócio em movimento",
                    "duration": 1.2,
                }
            ],
        }
        raw, meta = local_video.render(
            body,
            lambda _: self.fail("Motion sem captura não pode buscar mídia inventada"),
        )
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "motion.mp4"
            output.write_bytes(raw)
            info = local_video.probe(output)
            frames = []
            for timestamp in (0, 0.8):
                png = subprocess.check_output(
                    [
                        local_video.require()[0],
                        "-v",
                        "error",
                        "-ss",
                        str(timestamp),
                        "-i",
                        str(output),
                        "-frames:v",
                        "1",
                        "-f",
                        "image2pipe",
                        "-c:v",
                        "png",
                        "-",
                    ],
                    timeout=20,
                )
                frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
        self.assertIsNotNone(ImageChops.difference(*frames).getbbox())
        self.assertEqual((info["width"], info["height"]), (854, 480))
        self.assertAlmostEqual(info["duration"], 1.2, delta=0.15)
        self.assertEqual(meta["motion_scenes"], 1)
        self.assertEqual(
            meta["edit_plan"]["scenes"][0]["title"], body["scenes"][0]["title"]
        )

    def test_mixed_video_speed_captions_logo_and_audio_track_render_without_changing_originals(
        self,
    ):
        ffmpeg, _ = local_video.require()
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "source.mp4"
            audio = temp / "voice.wav"
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=blue:s=320x180:r=24",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000",
                    "-t",
                    "2",
                    "-c:v",
                    "libx264",
                    "-threads",
                    "2",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(source),
                ],
                check=True,
                timeout=20,
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:sample_rate=48000",
                    "-t",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(audio),
                ],
                check=True,
                timeout=20,
            )
            original = source.read_bytes()
            voice = audio.read_bytes()
            media = {
                1: (original, "video/mp4", "source.mp4"),
                2: (picture("gold"), "image/png", "logo.png"),
                3: (voice, "audio/wav", "voice.wav"),
            }
            plan = {
                "format": "square",
                "quality": "480p",
                "brand": {"name": "Teste"},
                "logo_asset_id": 2,
                "soundtrack": {"asset_id": 3, "volume": 0.5, "loop": True},
                "scenes": [
                    {
                        "kind": "motion",
                        "template": "cta",
                        "title": "Vamos começar",
                        "duration": 0.5,
                    },
                    {
                        "asset_id": 1,
                        "start": 0.2,
                        "duration": 0.5,
                        "speed": 2,
                        "title": "Título sobre o vídeo",
                        "subtitle": "Legenda manual",
                        "mute": True,
                        "fit": "cover",
                    },
                ],
            }
            raw, meta = local_video.render(plan, lambda row: media[row["asset_id"]])
            output = temp / "edited.mp4"
            output.write_bytes(raw)
            info = local_video.probe(output)
            samples = subprocess.check_output(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-i",
                    str(output),
                    "-f",
                    "s16le",
                    "-ac",
                    "1",
                    "-ar",
                    "8000",
                    "-",
                ],
                timeout=20,
            )
            import array

            levels = array.array("h")
            levels.frombytes(samples)
            self.assertGreater(max(map(abs, levels)), 100)
            self.assertEqual((info["width"], info["height"]), (480, 480))
            self.assertAlmostEqual(info["duration"], 1, delta=0.15)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(audio.read_bytes(), voice)
            self.assertEqual(meta["edit_plan"]["scenes"][1]["speed"], 2)

    def test_audio_import_is_decoded_and_bad_audio_is_rejected(self):
        ffmpeg, _ = local_video.require()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "voice.wav"
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:sample_rate=48000",
                    "-t",
                    "0.5",
                    str(path),
                ],
                check=True,
                timeout=20,
            )
            mime, info = local_video.inspect(path.read_bytes(), "voice.wav")
            self.assertEqual(mime, "audio/wav")
            self.assertTrue(info["audio"])
        with self.assertRaises(local_video.VideoError):
            local_video.inspect(b"not audio", "bad.mp3")


@unittest.skipUnless(all(local_video.binaries()), "FFmpeg/FFprobe não instalados")
class MotionHTTP(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def test_motion_preview_and_render_run_through_real_permission_queue_gallery_and_project(
        self,
    ):
        body = {
            "employee": 2,
            "plan": {
                "format": "landscape",
                "scenes": [
                    {
                        "kind": "motion",
                        "template": "features",
                        "title": "Meu produto",
                        "items": ["Agenda", "Relatórios"],
                        "duration": 0.5,
                    }
                ],
            },
        }
        preview = self.post("video/preview", body)
        image = Image.open(io.BytesIO(base64.b64decode(preview["data"])))
        self.assertEqual(image.size, (854, 480))
        self.post(
            "tools/job", {"employee": 2, "kind": "video_local", "params": body["plan"]}
        )
        s.runtime.tick()
        data = json.loads(self.raw("integrations"))
        job = next(j for j in data["jobs"] if j["kind"] == "video_local")
        self.assertEqual(job["status"], "succeeded", job["error"])
        result = json.loads(job["result"])
        self.assertEqual(result["motion_scenes"], 1)
        self.assertIn(b"ftyp", self.raw("asset?id=" + str(result["asset_id"]))[:32])
        with s.db() as c:
            self.assertIsNotNone(
                c.execute(
                    "SELECT id FROM task_files WHERE filename=?",
                    (f"video-projeto-{job['id']}.json",),
                ).fetchone()
            )

    def test_motion_preview_needs_permission_and_remote_video_needs_separate_optin(
        self,
    ):
        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "video/preview",
                {
                    "employee": 1,
                    "plan": {"scenes": [{"kind": "motion", "title": "Teste"}]},
                },
            )
        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "tools/job",
                {
                    "employee": 2,
                    "kind": "video",
                    "params": {"prompt": "Uma cena de produto"},
                },
            )

    def test_ia_context_describes_motion_and_does_not_expose_remote_video_when_disabled(
        self,
    ):
        messages, _, _ = s.build_context(2, "Crie um motion SaaS")
        self.assertIn("template", messages[0]["content"])
        self.assertIn("soundtrack", messages[0]["content"])
        with s.db() as c:
            self.assertNotIn("video", s.runtime.context(c, 2, None)["tools"])


class AudioAndRemoteHTTP(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    @unittest.skipUnless(all(local_video.binaries()), "FFmpeg/FFprobe não instalados")
    def test_audio_import_uses_gallery_mime_and_rejects_it_as_an_instagram_post(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "voice.wav"
            subprocess.run(
                [
                    local_video.require()[0],
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000",
                    "-t",
                    "0.5",
                    str(path),
                ],
                check=True,
                timeout=20,
            )
            result = self.post(
                "media/import",
                {
                    "employee": 2,
                    "filename": "voz.wav",
                    "data": base64.b64encode(path.read_bytes()).decode(),
                },
            )
        self.assertEqual(result["mime"], "audio/wav")
        self.assertEqual(self.raw("asset?id=" + str(result["asset_id"]))[:4], b"RIFF")
        with self.assertRaises(urllib.error.HTTPError):
            self.post(
                "social/draft",
                {
                    "asset_ids": [result["asset_id"]],
                    "caption": "Não publicar áudio sozinho",
                },
            )

    def test_cancelled_remote_result_is_never_saved_or_delivered(self):
        import gateway_video

        s.runtime.store_key("FREELLM_API_KEY", "unified-test")
        with s.db() as c:
            s.runtime.save_settings(c, {"video_gateway_enabled": "yes"})
            p = s.runtime.profile(c, 2)
            s.runtime.save_profile(c, dict(p, tools=[*p["tools"], "video"]))
        self.post(
            "tools/job",
            {
                "employee": 2,
                "kind": "video",
                "params": {"prompt": "Uma cena do escritório"},
            },
        )
        data = json.loads(self.raw("integrations"))
        job = next(j for j in data["jobs"] if j["kind"] == "video")

        def interrupted(key, params, progress):
            self.post("tools/cancel", {"id": job["id"]})
            progress(None)
            self.fail("Cancellation callback must interrupt the generation result")

        with patch.object(gateway_video, "generate", side_effect=interrupted):
            s.runtime.tick()
        data = json.loads(self.raw("integrations"))
        self.assertEqual(
            next(j for j in data["jobs"] if j["id"] == job["id"])["status"], "cancelled"
        )
        self.assertFalse(any(a.get("job") == job["id"] for a in data["assets"]))


class EditingAttachmentContext(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown

    def test_freellm_can_plan_edits_for_attached_video_without_claiming_to_see_its_content(
        self,
    ):
        with s.db() as c:
            tid = s.create_task(c, 2, "Corte os primeiros dois segundos do meu vídeo")
            aid = c.execute(
                "INSERT INTO source_attachments(task,filename,content,data,created,mime,analysis_status) VALUES(?,?,?,?,?,?,?)",
                (
                    tid,
                    "meu-video.mp4",
                    "Arquivo multimodal armazenado",
                    b"not-sent-as-model-input",
                    time.time(),
                    "video/mp4",
                    "gemini",
                ),
            ).lastrowid
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
        import freellm_gateway

        cfg = {
            "mode": "api",
            "base_url": freellm_gateway.BASE,
            "model": "auto",
            "max_tokens": 2600,
        }
        result = {
            "model": "test-model",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "reply": "Vou solicitar o corte conforme sua instrução.",
                                "actions": [
                                    {
                                        "type": "tool",
                                        "tool": "video_local",
                                        "params": {
                                            "scenes": [
                                                {
                                                    "attachment_id": aid,
                                                    "start": 0,
                                                    "duration": 2,
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        )
                    }
                }
            ],
        }
        with (
            patch.object(s.runtime, "effective_text", return_value=(cfg, "test-key")),
            patch.object(s.runtime, "text_request", return_value=result) as call,
        ):
            answer = s.generate(2, task["title"], task)
        messages = call.call_args.args[2]
        self.assertTrue(
            any("SEM análise multimodal" in m.get("content", "") for m in messages)
        )
        self.assertFalse(any(m.get("inline_files") for m in messages))
        self.assertEqual(
            answer["actions"][0]["params"]["scenes"][0]["attachment_id"], aid
        )
