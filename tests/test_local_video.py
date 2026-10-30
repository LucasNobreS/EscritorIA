import base64
import io
import json
import math
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_game
import local_video

s = test_game.s
from PIL import Image


def picture(color):
    out = io.BytesIO()
    Image.new("RGB", (320, 240), color).save(out, format="PNG")
    return out.getvalue()


class VideoValidation(unittest.TestCase):
    def test_untrusted_plans_and_resource_limits(self):
        good = {"scenes": [{"asset_id": 1, "duration": 2}]}
        self.assertEqual(local_video.validate(good)["format"], "portrait")
        for bad in (
            {"scenes": []},
            {"scenes": [{"asset_id": True}]},
            {"scenes": [{"asset_id": 1, "duration": float("nan")}]},
            {"scenes": [{"asset_id": 1, "duration": True}]},
            {"scenes": [{"asset_id": 1, "path": "/tmp/file"}]},
            {"scenes": [{"asset_id": 1, "attachment_id": 2}]},
            {
                "scenes": [
                    {"asset_id": 1, "duration": 30},
                    {"asset_id": 1, "duration": 30},
                    {"asset_id": 1, "duration": 1},
                ]
            },
            {"scenes": [{"asset_id": 1}] * 13},
            {"scenes": [{"asset_id": 1}], "command": "rm"},
            {"scenes": [{"asset_id": 1}], "format": "4k"},
        ):
            with self.assertRaises(local_video.VideoError):
                local_video.validate(bad)

    def test_missing_dependency_and_unsupported_import(self):
        with patch("local_video.binaries", return_value=(None, None)):
            with self.assertRaises(local_video.VideoError):
                local_video.require()
        for data, name in ((b"<!doctype html>", "x.html"), (b"not a png", "x.png")):
            with self.assertRaises(local_video.VideoError):
                local_video.inspect(data, name)

    def test_cancellation_terminates_a_running_process(self):
        original = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            children.append(process)
            return process

        def cancel(value):
            raise local_video.VideoCancelled("cancel")

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("local_video.subprocess.Popen", side_effect=spawn),
        ):
            with self.assertRaises(local_video.VideoCancelled):
                local_video.run(
                    [sys.executable, "-c", "import time;time.sleep(30)"],
                    tmp,
                    1,
                    time.monotonic() + 5,
                    cancel,
                )
        self.assertIsNotNone(children[0].poll())


@unittest.skipUnless(all(local_video.binaries()), "FFmpeg/FFprobe não instalados")
class VideoRender(unittest.TestCase):
    def test_real_images_zoom_concat_mp4_and_dimensions(self):
        images = {1: picture("#345a89"), 2: picture("#bb9955")}
        progress = []
        data, meta = local_video.render(
            {
                "format": "landscape",
                "transition": "fade",
                "scenes": [
                    {"asset_id": 1, "duration": 0.5, "motion": "zoom"},
                    {"asset_id": 2, "duration": 0.5},
                ],
            },
            lambda scene: (images[scene["asset_id"]], "image/png", "image.png"),
            progress.append,
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.mp4"
            out.write_bytes(data)
            info = local_video.probe(out)
        self.assertEqual((info["width"], info["height"]), (1280, 720))
        self.assertAlmostEqual(info["duration"], 1, delta=0.15)
        self.assertEqual(meta["scenes"], 2)
        self.assertIn(b"ftyp", data[:32])
        self.assertTrue(any(p and p > 0.8 for p in progress))

    def test_cut_preserves_or_mutes_audio_and_checks_source_range(self):
        ffmpeg, _ = local_video.require()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=160x120:r=24",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000",
                    "-t",
                    "1.5",
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
            original = source.read_bytes()
            amplitudes = []
            for mute in (False, True):
                data, meta = local_video.render(
                    {
                        "format": "square",
                        "scenes": [
                            {
                                "asset_id": 1,
                                "start": 0.25,
                                "duration": 0.5,
                                "mute": mute,
                            }
                        ],
                    },
                    lambda scene: (original, "video/mp4", "source.mp4"),
                )
                output = Path(tmp) / ("muted.mp4" if mute else "cut.mp4")
                output.write_bytes(data)
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

                values = array.array("h")
                values.frombytes(samples)
                amplitudes.append(max(map(abs, values)))
            self.assertGreater(amplitudes[0], 500)
            self.assertLess(amplitudes[1], 10)
            self.assertEqual(source.read_bytes(), original)
            with self.assertRaises(local_video.VideoError):
                local_video.render(
                    {"scenes": [{"asset_id": 1, "start": 1, "duration": 1}]},
                    lambda scene: (original, "video/mp4", "source.mp4"),
                )


@unittest.skipUnless(all(local_video.binaries()), "FFmpeg/FFprobe não instalados")
class VideoHTTP(unittest.TestCase):
    setUp = test_game.OfficeGame.setUp
    tearDown = test_game.OfficeGame.tearDown
    post = test_game.OfficeGame.post
    raw = test_game.OfficeGame.raw
    state = test_game.OfficeGame.state

    def test_import_queue_real_worker_gallery_and_download(self):
        original = picture("#567887")
        asset = self.post(
            "media/import",
            {
                "employee": 2,
                "filename": "original.png",
                "data": base64.b64encode(original).decode(),
            },
        )
        self.post(
            "tools/job",
            {
                "employee": 2,
                "kind": "video_local",
                "params": {
                    "format": "square",
                    "scenes": [{"asset_id": asset["asset_id"], "duration": 0.5}],
                },
            },
        )
        s.runtime.tick()
        d = json.loads(self.raw("integrations"))
        job = next(j for j in d["jobs"] if j["kind"] == "video_local")
        self.assertEqual(job["status"], "succeeded", job["error"])
        self.assertEqual(job["progress"], 100)
        result = json.loads(job["result"])
        self.assertEqual(result["mime"], "video/mp4")
        self.assertIn(b"ftyp", self.raw("asset?id=" + str(result["asset_id"]))[:32])
        self.assertEqual(self.raw("asset?id=" + str(asset["asset_id"])), original)

    def test_cancel_queued_video_without_rendering(self):
        asset = self.post(
            "media/import",
            {
                "employee": 2,
                "filename": "image.png",
                "data": base64.b64encode(picture("red")).decode(),
            },
        )
        self.post(
            "tools/job",
            {
                "employee": 2,
                "kind": "video_local",
                "params": {"scenes": [{"asset_id": asset["asset_id"], "duration": 1}]},
            },
        )
        job = json.loads(self.raw("integrations"))["jobs"][0]
        self.post("tools/cancel", {"id": job["id"]})
        with patch("local_video.render", side_effect=AssertionError("Cancelled")):
            s.runtime.tick()
        d = json.loads(self.raw("integrations"))
        self.assertEqual(
            next(j for j in d["jobs"] if j["id"] == job["id"])["status"], "cancelled"
        )

    def test_interrupted_local_job_can_be_manually_retried(self):
        asset = self.post(
            "media/import",
            {
                "employee": 2,
                "filename": "image.png",
                "data": base64.b64encode(picture("blue")).decode(),
            },
        )
        self.post(
            "tools/job",
            {
                "employee": 2,
                "kind": "video_local",
                "params": {"scenes": [{"asset_id": asset["asset_id"], "duration": 1}]},
            },
        )
        job = json.loads(self.raw("integrations"))["jobs"][0]
        with s.db() as c:
            c.execute("UPDATE tool_jobs SET status='running' WHERE id=?", (job["id"],))
        s.runtime.recover()
        d = json.loads(self.raw("integrations"))
        self.assertEqual(
            next(j for j in d["jobs"] if j["id"] == job["id"])["status"], "failed"
        )
        self.post("tools/retry", {"id": job["id"]})
        d = json.loads(self.raw("integrations"))
        self.assertEqual(
            next(j for j in d["jobs"] if j["id"] == job["id"])["status"], "queued"
        )
