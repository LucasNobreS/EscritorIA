"""Bounded CPU-only MP4 editing. Inputs and filters are selected by the program."""

import json
import math
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import motion_video
import re

FORMATS = {"portrait": (720, 1280), "landscape": (1280, 720), "square": (720, 720)}
EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
}
AUDIO_EXTENSIONS = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
MAX_IMPORT = 20 * 1024 * 1024
MAX_SCENES = 12
MAX_DURATION = 60


class VideoError(ValueError):
    pass


class VideoCancelled(VideoError):
    pass


def binaries():
    root = Path(__file__).parent / "tools" / "ffmpeg" / "bin"

    def find(name, env):
        value = os.environ.get(env)
        if value and Path(value).is_file():
            return str(Path(value).resolve())
        for suffix in (".exe", ""):
            if (root / (name + suffix)).is_file():
                return str((root / (name + suffix)).resolve())
        return shutil.which(name)

    return find("ffmpeg", "FFMPEG_PATH"), find("ffprobe", "FFPROBE_PATH")


def require():
    ffmpeg, ffprobe = binaries()
    if not ffmpeg or not ffprobe:
        raise VideoError(
            "Instale FFmpeg e FFprobe com Instalar-video.bat e reinicie o escritório. Não precisa de chave de vídeo."
        )
    return ffmpeg, ffprobe


def number(value, label, minimum, maximum):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise VideoError(label + " inválido.")
    return float(value)


def reference(value, required=True):
    ids = [key for key in ("asset_id", "attachment_id") if key in value]
    if (
        len(ids) > 1
        or (required and len(ids) != 1)
        or any(type(value[key]) is not int or value[key] <= 0 for key in ids)
    ):
        raise VideoError("Use um ID real de mídia ou anexo.")
    return {key: value[key] for key in ids}


def label(value, name, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise VideoError(name + " deve ter até " + str(limit) + " caracteres.")
    return value.strip()


def palette(value):
    if not isinstance(value, dict) or set(value) - {
        "name",
        "background",
        "foreground",
        "accent",
    }:
        raise VideoError("Identidade visual inválida.")
    result = {}
    for key, item in value.items():
        if key == "name":
            result[key] = label(item, "Marca", 50)
        elif not isinstance(item, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", item):
            raise VideoError("Use cores no formato #RRGGBB.")
        else:
            result[key] = item
    return result


def validate(params):
    if not isinstance(params, dict):
        raise VideoError("Plano de vídeo inválido.")
    scenes = params.get("scenes")
    fmt = params.get("format", "portrait")
    transition = params.get("transition", "cut")
    quality = params.get("quality", "720p")
    if (
        fmt not in FORMATS
        or transition not in ("cut", "fade")
        or quality not in ("480p", "720p", "1080p")
    ):
        raise VideoError("Formato, qualidade ou transição inválidos.")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise VideoError("Use de 1 a 12 cenas.")
    result = []
    for scene in scenes:
        if not isinstance(scene, dict):
            raise VideoError("Cena inválida.")
        if set(scene) - {
            "asset_id",
            "attachment_id",
            "kind",
            "template",
            "title",
            "subtitle",
            "items",
            "cta",
            "brand",
            "accent",
            "background",
            "foreground",
            "start",
            "duration",
            "motion",
            "mute",
            "speed",
            "volume",
            "fit",
        }:
            raise VideoError(
                "Campo de cena não permitido; não envie caminhos, comandos ou filtros."
            )
        kind = scene.get("kind", "media")
        if kind not in ("media", "motion"):
            raise VideoError("Tipo de cena inválido.")
        row = reference(scene, required=kind == "media")
        row.update(
            kind=kind,
            duration=number(
                scene.get("duration", 4 if kind == "motion" else 3), "Duração", 0.5, 30
            ),
            start=number(scene.get("start", 0), "Início", 0, 180),
        )
        row["motion"] = scene.get("motion", "still")
        row["mute"] = scene.get("mute", False)
        row["fit"] = scene.get("fit", "contain")
        if (
            row["motion"] not in ("still", "zoom", "pan-left", "pan-right")
            or type(row["mute"]) is not bool
            or row["fit"] not in ("contain", "cover")
        ):
            raise VideoError("Movimento, enquadramento ou áudio inválido.")
        row["speed"] = number(scene.get("speed", 1), "Velocidade", 0.5, 2)
        row["volume"] = number(scene.get("volume", 1), "Volume", 0, 2)
        for key, limit in (
            ("title", 100),
            ("subtitle", 240),
            ("cta", 60),
            ("brand", 50),
        ):
            if key in scene:
                row[key] = label(scene[key], key, limit)
        if kind == "motion":
            row["template"] = scene.get("template", "title")
            if row["template"] not in motion_video.TEMPLATES:
                raise VideoError("Template de motion inválido.")
            items = scene.get("items", [])
            if not isinstance(items, list) or len(items) > 4:
                raise VideoError("Use até quatro benefícios na cena.")
            row["items"] = [label(item, "Benefício", 70) for item in items]
            if row["start"] or row["speed"] != 1:
                raise VideoError(
                    "Cenas motion usam início zero e velocidade 1; altere a duração da cena."
                )
            for key in ("accent", "background", "foreground"):
                if key in scene:
                    row.update(palette({key: scene[key]}))
        for key in ("accent", "background", "foreground"):
            if key in scene:
                row.update(palette({key: scene[key]}))
        result.append(row)
    if sum(row["duration"] for row in result) > MAX_DURATION + 0.00001:
        raise VideoError("O vídeo pode ter até 60 segundos no total.")
    if set(params) - {
        "scenes",
        "format",
        "transition",
        "quality",
        "brand",
        "logo_asset_id",
        "soundtrack",
    }:
        raise VideoError("Parâmetro de vídeo não permitido.")
    plan = {
        "scenes": result,
        "format": fmt,
        "transition": transition,
        "quality": quality,
        "brand": palette(params.get("brand", {})),
    }
    if "logo_asset_id" in params:
        if type(params["logo_asset_id"]) is not int or params["logo_asset_id"] <= 0:
            raise VideoError("Escolha um ID real para o logo.")
        plan["logo_asset_id"] = params["logo_asset_id"]
    if params.get("soundtrack"):
        track = params["soundtrack"]
        if not isinstance(track, dict) or set(track) - {
            "asset_id",
            "attachment_id",
            "volume",
            "start",
            "loop",
        }:
            raise VideoError("Faixa de áudio inválida.")
        plan["soundtrack"] = dict(
            reference(track),
            volume=number(track.get("volume", 0.25), "Volume da faixa", 0, 1),
            start=number(track.get("start", 0), "Início do áudio", 0, 180),
            loop=track.get("loop", False),
        )
        if type(plan["soundtrack"]["loop"]) is not bool:
            raise VideoError("Repetição da faixa inválida.")
    return plan


def probe(path, allow_audio=False):
    _, ffprobe = require()
    args = [
        ffprobe,
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        "mov,png_pipe,jpeg_pipe,webp_pipe,image2,mp3,wav",
        "-show_entries",
        "stream=codec_type,width,height:format=duration,format_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=True,
        )
        info = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise VideoError(
            "Não foi possível ler esta mídia. Use JPG, PNG, WebP ou MP4 compatível com FFmpeg."
        ) from None
    stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if (
        not stream
        and not (
            allow_audio
            and any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        )
    ) or (
        stream
        and not (
            1 <= int(stream.get("width", 0)) <= 4096
            and 1 <= int(stream.get("height", 0)) <= 4096
        )
    ):
        raise VideoError(
            "Mídia sem imagem válida ou acima de 4096 pixels por dimensão."
        )
    try:
        duration = float(info.get("format", {}).get("duration", 0))
    except (ValueError, TypeError):
        raise VideoError("Duração da mídia inválida.") from None
    if not math.isfinite(duration) or duration < 0 or duration > 180:
        raise VideoError("O vídeo de origem deve ter até 180 segundos.")
    return {
        "duration": duration,
        "audio": any(s.get("codec_type") == "audio" for s in info.get("streams", [])),
        "width": stream["width"] if stream else 0,
        "height": stream["height"] if stream else 0,
    }


def inspect(data, filename):
    ext = Path(filename).suffix.lower()
    if (
        ext not in {**EXTENSIONS, **AUDIO_EXTENSIONS}
        or not data
        or len(data) > MAX_IMPORT
    ):
        raise VideoError("Importe um JPG, PNG, WebP ou MP4 de até 20 MB.")
    with tempfile.TemporaryDirectory(prefix="atelie-probe-") as folder:
        path = Path(folder) / ("source" + ext)
        path.write_bytes(data)
        info = probe(path, allow_audio=ext in AUDIO_EXTENSIONS)
    if ext in AUDIO_EXTENSIONS:
        if not info["audio"] or info["duration"] <= 0:
            raise VideoError("Áudio inválido ou sem duração.")
        return AUDIO_EXTENSIONS[ext], info
    if ext == ".mp4" and (b"ftyp" not in data[:32] or info["duration"] <= 0):
        raise VideoError("MP4 inválido ou sem duração.")
    if ext != ".mp4":
        good = (
            data.startswith(b"\x89PNG\r\n\x1a\n")
            or data.startswith(b"\xff\xd8")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        )
        if not good:
            raise VideoError("Formato de imagem não reconhecido.")
    mime = (
        "image/png"
        if data.startswith(b"\x89PNG")
        else "image/jpeg"
        if data.startswith(b"\xff\xd8")
        else "image/webp"
        if ext != ".mp4"
        else "video/mp4"
    )
    return mime, info


def run(args, cwd, duration, deadline, progress, frames=None):
    messages = queue.Queue(maxsize=8)
    process = subprocess.Popen(
        args,
        cwd=cwd,
        stdin=subprocess.PIPE if frames is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    def read():
        for raw in iter(process.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_us="):
                try:
                    messages.put_nowait(
                        min(1, max(0, int(line.split("=", 1)[1]) / 1000000 / duration))
                    )
                except (ValueError, queue.Full):
                    pass

    errors = []

    def feed():
        try:
            for frame in frames:
                process.stdin.write(frame)
        except (BrokenPipeError, OSError):
            pass
        except Exception as error:
            errors.append(error)
            process.kill()
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    writer = threading.Thread(target=feed, daemon=True) if frames is not None else None
    if writer:
        writer.start()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise VideoError(
                    "Renderização excedeu 8 minutos. Reduza cenas ou duração e tente novamente."
                )
            try:
                progress(messages.get(timeout=0.25))
            except queue.Empty:
                progress(None)
        if errors:
            raise VideoError("Falha ao desenhar a cena: " + str(errors[0])[:180])
        if process.returncode:
            raise VideoError(
                "FFmpeg não conseguiu renderizar a cena. Confira o arquivo, os codecs e o intervalo escolhido."
            )
        progress(1)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=1)
        process.stdout.close()
        if writer:
            writer.join(timeout=3)


def dimensions(plan):
    w, h = FORMATS[plan["format"]]
    ratio = {"480p": 2 / 3, "720p": 1, "1080p": 1.5}[plan["quality"]]
    return int(round(w * ratio / 2)) * 2, int(round(h * ratio / 2)) * 2


def render(params, resolve, progress=lambda value: None):
    plan = validate(params)
    ffmpeg, _ = require()
    deadline = time.monotonic() + 480
    w, h = dimensions(plan)
    total = sum(s["duration"] for s in plan["scenes"])
    elapsed = 0
    base = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-threads",
        "2",
        "-filter_threads",
        "1",
        "-filter_complex_threads",
        "1",
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    brand = plan["brand"]
    logo = None
    if plan.get("logo_asset_id"):
        data, mime, _ = resolve({"asset_id": plan["logo_asset_id"]})
        if not mime.startswith("image/"):
            raise VideoError("O logo deve ser uma imagem.")
        logo = motion_video.image(data)
    with tempfile.TemporaryDirectory(prefix="atelie-video-") as folder:
        root = Path(folder)
        parts = []
        for index, scene in enumerate(plan["scenes"]):
            progress(elapsed / total * 0.85)
            frames = None
            overlay_index = None
            if scene["kind"] == "motion":
                screenshot = None
                if "asset_id" in scene or "attachment_id" in scene:
                    data, mime, _ = resolve(scene)
                    if len(data) > MAX_IMPORT or not mime.startswith("image/"):
                        raise VideoError(
                            "A tela do motion deve ser uma imagem de até 20 MB."
                        )
                    screenshot = motion_video.image(data)
                painter = motion_video.Scene(scene, w, h, brand, screenshot, logo)
                frames = (
                    painter.frame(frame / 24).tobytes()
                    for frame in range(math.ceil(scene["duration"] * 24))
                )
                args = base + [
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    "-s",
                    f"{w}x{h}",
                    "-r",
                    "24",
                    "-i",
                    "pipe:0",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                ]
                silent = True
                filters = "setsar=1,fps=24"
            else:
                data, mime, filename = resolve(scene)
                if len(data) > MAX_IMPORT:
                    raise VideoError("Mídia de origem excede 20 MB.")
                ext = Path(filename).suffix.lower()
                if ext not in EXTENSIONS:
                    raise VideoError(
                        "Fonte não suportada. Importe imagens ou MP4 no estúdio de vídeo."
                    )
                source = root / ("source-" + str(index) + ext)
                source.write_bytes(data)
                info = probe(source)
                image = mime.startswith("image/")
                if not image and scene["motion"] != "still":
                    raise VideoError(
                        "Movimentos de câmera estão disponíveis apenas para imagens."
                    )
                if image and (scene["start"] != 0 or scene["speed"] != 1):
                    raise VideoError("Imagens usam início zero e velocidade 1.")
                if (
                    not image
                    and scene["start"] + scene["duration"] * scene["speed"]
                    > info["duration"] + 0.05
                ):
                    raise VideoError(
                        "O corte e a velocidade ultrapassam a duração da origem."
                    )
                args = base + [
                    "-protocol_whitelist",
                    "file,pipe",
                    "-format_whitelist",
                    "mov,png_pipe,jpeg_pipe,webp_pipe,image2",
                ]
                if image:
                    args += ["-loop", "1", "-framerate", "24"]
                else:
                    args += ["-ss", str(scene["start"])]
                args += ["-i", str(source)]
                silent = image or scene["mute"] or not info["audio"]
                if silent:
                    args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                fill = scene.get(
                    "background", brand.get("background", "#101b31")
                ).replace("#", "0x")
                filters = (
                    f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
                    if scene["fit"] == "cover"
                    else f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={fill}"
                ) + ",setsar=1"
                if not image:
                    filters += f",setpts=(PTS-STARTPTS)/{scene['speed']}"
                filters += ",fps=24"
                if image and scene["motion"] != "still":
                    zoom = (
                        "min(pzoom+0.0008,1.12)"
                        if scene["motion"] == "zoom"
                        else "1.12"
                    )
                    x = (
                        "iw/2-iw/zoom/2"
                        if scene["motion"] == "zoom"
                        else f"(iw-iw/zoom)*{'1-' if scene['motion'] == 'pan-left' else ''}min(on/{max(1, int(scene['duration'] * 24) - 1)},1)"
                    )
                    # Parentheses keep reverse pans bounded too.
                    if scene["motion"] == "pan-left":
                        x = f"(iw-iw/zoom)*(1-min(on/{max(1, int(scene['duration'] * 24) - 1)},1))"
                    filters += f",zoompan=z='{zoom}':x='{x}':y='ih/2-ih/zoom/2':d=1:s={w}x{h}:fps=24"
                if (
                    scene.get("title")
                    or scene.get("subtitle")
                    or brand.get("name")
                    or logo
                ):
                    overlay = root / f"overlay-{index}.png"
                    motion_video.overlay(scene, w, h, brand, logo).save(overlay)
                    overlay_index = 2 if silent else 1
                    args += ["-loop", "1", "-framerate", "24", "-i", str(overlay)]
            if plan["transition"] == "fade":
                filters += f",fade=t=in:st=0:d=0.2,fade=t=out:st={max(0, scene['duration'] - 0.2)}:d=0.2"
            out = root / f"part-{index}.mp4"
            parts.append(out.name)
            if overlay_index is not None:
                args += [
                    "-filter_complex",
                    f"[0:v]{filters}[base];[{overlay_index}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1[caption];[base][caption]overlay=0:0:shortest=1[out]",
                    "-map",
                    "[out]",
                ]
            else:
                args += ["-map", "0:v:0", "-vf", filters]
            audio = (
                "apad"
                if silent
                else f"atempo={scene['speed']},volume={scene['volume']},apad"
            )
            args += [
                "-map",
                "1:a:0" if silent else "0:a:0",
                "-t",
                str(scene["duration"]),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-maxrate",
                "6M",
                "-bufsize",
                "12M",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-af",
                audio,
                "-map_metadata",
                "-1",
                "-movflags",
                "+faststart",
                str(out),
            ]
            offset = elapsed
            run(
                args,
                root,
                scene["duration"],
                deadline,
                lambda value: progress(
                    None
                    if value is None
                    else (offset + value * scene["duration"]) / total * 0.85
                ),
                frames=frames,
            )
            elapsed += scene["duration"]
        manifest = root / "scenes.txt"
        manifest.write_text(
            "".join("file '" + name + "'\n" for name in parts), encoding="utf-8"
        )
        output = root / "result.mp4"
        args = base + [
            "-protocol_whitelist",
            "file,pipe",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(manifest),
            "-c",
            "copy",
            "-t",
            str(total),
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            str(output),
        ]
        run(
            args,
            root,
            total,
            deadline,
            lambda value: progress(None if value is None else 0.85 + value * 0.05),
        )
        if plan.get("soundtrack"):
            track = plan["soundtrack"]
            data, mime, filename = resolve(track)
            ext = Path(filename).suffix.lower()
            if len(data) > MAX_IMPORT or ext not in AUDIO_EXTENSIONS:
                raise VideoError("Use uma faixa MP3, WAV ou M4A de até 20 MB.")
            source = root / ("audio" + ext)
            source.write_bytes(data)
            info = probe(source, allow_audio=True)
            if track["start"] >= info["duration"]:
                raise VideoError("O início da faixa está além da duração do áudio.")
            mixed = root / "mixed.mp4"
            args = base + ["-i", str(output)]
            if track["loop"]:
                args += ["-stream_loop", "-1"]
            args += [
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                "mov,mp3,wav",
                "-ss",
                str(track["start"]),
                "-i",
                str(source),
                "-filter_complex",
                f"[1:a]volume={track['volume']},afade=t=in:d=0.3,afade=t=out:st={max(0, total - 0.5)}:d=0.5[track];[0:a][track]amix=inputs=2:duration=first:normalize=0[a]",
                "-map",
                "0:v:0",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-t",
                str(total),
                "-map_metadata",
                "-1",
                "-movflags",
                "+faststart",
                str(mixed),
            ]
            run(
                args,
                root,
                total,
                deadline,
                lambda value: progress(None if value is None else 0.9 + value * 0.09),
            )
            output = mixed
        if output.stat().st_size > 64 * 1024 * 1024:
            raise VideoError("O resultado excedeu 64 MB.")
        result = output.read_bytes()
        return result, {
            "format": plan["format"],
            "quality": plan["quality"],
            "width": w,
            "height": h,
            "fps": 24,
            "duration": total,
            "scenes": len(parts),
            "provider": "FFmpeg local (CPU)",
            "edit_plan": plan,
            "motion_scenes": sum(s["kind"] == "motion" for s in plan["scenes"]),
        }
