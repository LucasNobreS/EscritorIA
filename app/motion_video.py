"""Deterministic SaaS motion graphics. Data-only scenes; no HTML or generated code."""

import io
import math
import os
from pathlib import Path
from functools import lru_cache

TEMPLATES = ("title", "dashboard", "features", "cta")


def pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

        return Image, ImageDraw, ImageFont, ImageOps, ImageFilter
    except ImportError:
        raise ValueError(
            "Instale Pillow com Instalar-imagens.bat para títulos e motion SaaS."
        ) from None


@lru_cache(maxsize=96)
def font(size, bold=False):
    _, _, ImageFont, _, _ = pillow()
    windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = [
        windows / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu")
        / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), max(10, int(size)))
    return ImageFont.load_default(size=max(10, int(size)))


def image(data):
    Image, _, _, _, _ = pillow()
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > 20000000:
            raise ValueError("Imagem de motion acima de 20 megapixels.")
        source.load()
        return source.convert("RGBA")


def ease(value):
    return 1 - (1 - max(0, min(1, value))) ** 3


def text_block(draw, text, xy, width, size, color, max_lines=3, bold=False):
    text = " ".join(str(text).split())
    size = int(size)

    def wrap(f):
        lines = []
        line = ""
        for word in text.split():
            if draw.textlength(word, font=f) > width:
                chunks = []
                chunk = ""
                for char in word:
                    if chunk and draw.textlength(chunk + char, font=f) > width:
                        chunks.append(chunk)
                        chunk = ""
                    chunk += char
                chunks.append(chunk)
            else:
                chunks = [word]
            for chunk in chunks:
                trial = (line + " " + chunk).strip()
                if line and draw.textlength(trial, font=f) > width:
                    lines.append(line)
                    line = chunk
                else:
                    line = trial
        if line:
            lines.append(line)
        return lines

    while True:
        f = font(size, bold)
        lines = wrap(f)
        if len(lines) <= max_lines or size <= 12:
            break
        size = max(12, size - 2)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=f) > width:
            last = last[:-1]
        lines[-1] = last + "…"
    x, y = xy
    for line in lines:
        draw.text((int(x), int(y)), line, font=f, fill=color)
        y += size * 1.32
    return y


class Scene:
    def __init__(self, scene, w, h, brand=None, screen=None, logo=None):
        Image, ImageDraw, _, ImageOps, ImageFilter = pillow()
        self.scene = scene
        self.w = w
        self.h = h
        self.unit = min(w, h) / 720
        self.brand = brand or {}
        self.logo = logo
        self.screen = screen
        self.accent = scene.get("accent", self.brand.get("accent", "#70e2bf"))
        self.foreground = scene.get(
            "foreground", self.brand.get("foreground", "#f5f7fc")
        )
        self.background = scene.get(
            "background", self.brand.get("background", "#101b31")
        )
        self.base = Image.new("RGB", (w, h), self.background)
        draw = ImageDraw.Draw(self.base)
        color = tuple(int(self.background[n : n + 2], 16) for n in (1, 3, 5))
        for y in range(h):
            factor = y / max(1, h - 1)
            draw.line(
                (0, y, w, y), fill=tuple(min(255, int(c + factor * 12)) for c in color)
            )
        glow = Image.new("RGBA", (w, h))
        g = ImageDraw.Draw(glow)
        rgb = tuple(int(self.accent[n : n + 2], 16) for n in (1, 3, 5))
        g.ellipse((w * 0.55, -h * 0.3, w * 1.3, h * 0.5), fill=rgb + (28,))
        glow = glow.filter(ImageFilter.GaussianBlur(max(8, int(50 * self.unit))))
        self.base.paste(glow, (0, 0), glow)
        for x in range(20, w, max(24, int(48 * self.unit))):
            for y in range(20, h, max(24, int(48 * self.unit))):
                draw.ellipse((x, y, x + 1, y + 1), fill="#34405a")
        self.brand_name = scene.get("brand", self.brand.get("name", ""))
        if screen:
            box = (int(w * 0.78), int(h * 0.28))
            self.screen = ImageOps.contain(screen, box, Image.Resampling.LANCZOS)
        if logo:
            self.logo = ImageOps.contain(
                logo, (int(w * 0.18), int(h * 0.08)), Image.Resampling.LANCZOS
            )

    def frame(self, t):
        Image, ImageDraw, _, _, _ = pillow()
        w, h, u = self.w, self.h, self.unit
        s = self.scene
        frame = self.base.copy()
        draw = ImageDraw.Draw(frame)
        margin = w * 0.08
        content = w * 0.84
        template = s.get("template", "title")
        duration = s["duration"]
        enter = ease(t / 0.7)
        dy = (1 - enter) * 42 * u
        if self.brand_name:
            text_block(
                draw,
                self.brand_name,
                (margin, h * 0.055),
                w * 0.62,
                19 * u,
                self.accent,
                1,
                True,
            )
        if self.logo:
            frame.paste(
                self.logo, (int(w * 0.92 - self.logo.width), int(h * 0.045)), self.logo
            )
        title_y = h * (0.24 if template in ("title", "cta") else 0.13) + dy
        title_size = (
            min(w * 0.078, h * 0.10)
            if template in ("title", "cta")
            else min(w * 0.065, h * 0.065)
        )
        end = text_block(
            draw,
            s.get("title", ""),
            (margin, title_y),
            content,
            title_size,
            self.foreground,
            3 if template in ("title", "cta") else 2,
            True,
        )
        if s.get("subtitle"):
            text_block(
                draw,
                s["subtitle"],
                (margin, end + 18 * u),
                content,
                min(26 * u, w * 0.036),
                "#b5bfd2",
                3 if template in ("title", "cta") else 2,
            )
        if template == "dashboard":
            self.dashboard(frame, draw, t, enter)
        elif template == "features":
            items = s.get("items") or [
                "Organize sua rotina",
                "Acompanhe seus resultados",
                "Simplifique sua operação",
            ]
            columns = 2 if w > h else 1
            gap = 16 * u
            card_w = (content - gap * (columns - 1)) / columns
            rows = math.ceil(len(items) / columns)
            start = h * 0.45
            card_h = min(130 * u, h * 0.39 / rows - 12 * u)
            for i, label in enumerate(items):
                appear = ease((t - 0.2 - i * 0.13) / 0.65)
                x = margin + (i % columns) * (card_w + gap) + (1 - appear) * 32 * u
                y = start + (i // columns) * (card_h + gap)
                draw.rounded_rectangle(
                    (x, y, x + card_w, y + card_h),
                    radius=int(16 * u),
                    fill="#1c2b45",
                    outline="#354866",
                    width=max(1, int(u)),
                )
                draw.ellipse(
                    (x + 18 * u, y + 20 * u, x + 26 * u, y + 28 * u), fill=self.accent
                )
                text_block(
                    draw,
                    label,
                    (x + 42 * u, y + 14 * u),
                    card_w - 60 * u,
                    22 * u,
                    self.foreground,
                    2,
                    True,
                )
        else:
            y = h * 0.64 + (1 - enter) * 30 * u
            bar_w = content * ease((t - 0.2) / 1.2)
            draw.rounded_rectangle(
                (margin, y, margin + content, y + 5 * u),
                radius=max(1, int(2 * u)),
                fill="#2a3c59",
            )
            if bar_w > 2:
                draw.rounded_rectangle(
                    (margin, y, margin + bar_w, y + 5 * u),
                    radius=max(1, int(2 * u)),
                    fill=self.accent,
                )
            if template == "title":
                for i, label in enumerate(s.get("items", [])[:3]):
                    text_block(
                        draw,
                        "• " + label,
                        (margin, y + 30 * u + i * 38 * u),
                        content,
                        21 * u,
                        "#b5bfd2",
                        1,
                    )
        if template == "cta" or s.get("cta"):
            label = s.get("cta") or "Conheça a solução"
            f = font(23 * u, True)
            button_w = min(content, draw.textlength(label, font=f) + 58 * u)
            x = margin
            y = h * 0.82 + (1 - ease((t - 0.35) / 0.7)) * 20 * u
            draw.rounded_rectangle(
                (x, y, x + button_w, y + 60 * u), radius=int(15 * u), fill=self.accent
            )
            text_block(
                draw,
                label,
                (x + 25 * u, y + 14 * u),
                button_w - 45 * u,
                23 * u,
                "#101b31",
                1,
                True,
            )
        return frame

    def dashboard(self, frame, draw, t, enter):
        w, h, u = self.w, self.h, self.unit
        x = w * 0.08
        y = h * 0.43 + (1 - enter) * 35 * u
        cw = w * 0.84
        ch = h * 0.42
        draw.rounded_rectangle(
            (x + 6 * u, y + 12 * u, x + cw + 6 * u, y + ch + 12 * u),
            radius=int(20 * u),
            fill="#0b1427",
        )
        draw.rounded_rectangle(
            (x, y, x + cw, y + ch), radius=int(20 * u), fill="#f4f6fb"
        )
        draw.rounded_rectangle(
            (x, y, x + cw, y + 34 * u), radius=int(17 * u), fill="#dce3ef"
        )
        for i, color in enumerate(("#f58783", "#e9c675", "#77c9ab")):
            draw.ellipse(
                (
                    x + 18 * u + i * 17 * u,
                    y + 12 * u,
                    x + 26 * u + i * 17 * u,
                    y + 20 * u,
                ),
                fill=color,
            )
        draw.text(
            (x + 80 * u, y + 8 * u),
            "Prévia do produto" if self.screen else "Demonstração ilustrativa",
            font=font(12 * u),
            fill="#4c5e7b",
        )
        if self.screen:
            frame.paste(
                self.screen,
                (int(x + (cw - self.screen.width) / 2), int(y + 44 * u)),
                self.screen,
            )
        else:
            ix = x + 22 * u
            iy = y + 52 * u
            iw = cw - 44 * u
            ih = ch - 80 * u
            labels = self.scene.get("items") or [
                "Organização",
                "Produtividade",
                "Visão geral",
            ]
            for i in range(3):
                bx = ix + i * (iw / 3)
                bw = iw / 3 - 8 * u
                draw.rounded_rectangle(
                    (bx, iy, bx + bw, iy + ih * 0.3), radius=int(8 * u), fill="#e7ecf6"
                )
                text_block(
                    draw,
                    labels[i % len(labels)],
                    (bx + 9 * u, iy + 7 * u),
                    bw - 18 * u,
                    13 * u,
                    "#566986",
                    1,
                )
                number = int((24 + i * 37) * ease((t - 0.2 - i * 0.15) / 1.8))
                draw.text(
                    (bx + 9 * u, iy + 24 * u),
                    str(number),
                    font=font(24 * u, True),
                    fill="#253d60",
                )
            chart_y = iy + ih * 0.45
            chart_h = ih * 0.48
            for i, ratio in enumerate((0.32, 0.46, 0.39, 0.62, 0.54, 0.78, 0.9)):
                bx = ix + i * (iw / 7) + 7 * u
                by = chart_y + chart_h * (1 - ratio * ease((t - 0.25 - i * 0.08) / 1.2))
                draw.rounded_rectangle(
                    (bx, by, bx + iw / 7 - 16 * u, chart_y + chart_h),
                    radius=max(1, int(4 * u)),
                    fill=self.accent,
                )
        p = ease((t - 0.5) / 2)
        cx = x + cw * (0.28 + 0.48 * p)
        cy = y + ch * (0.78 - 0.2 * p)
        draw.polygon(
            [
                (cx, cy),
                (cx + 20 * u, cy + 29 * u),
                (cx + 9 * u, cy + 27 * u),
                (cx + 5 * u, cy + 39 * u),
            ],
            fill="#1b2c47",
            outline="#ffffff",
        )
        if 1.8 < t < 2.5:
            radius = (t - 1.8) * 32 * u
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                outline=self.accent,
                width=max(1, int(2 * u)),
            )


def overlay(scene, w, h, brand=None, logo=None):
    Image, ImageDraw, _, ImageOps, _ = pillow()
    brand = brand or {}
    canvas = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(canvas)
    u = min(w, h) / 720
    if scene.get("title") or scene.get("subtitle"):
        x = w * 0.05
        y = h * 0.73
        draw.rounded_rectangle(
            (x, y, w * 0.95, h * 0.95), radius=int(18 * u), fill=(12, 23, 42, 225)
        )
        end = text_block(
            draw,
            scene.get("title", ""),
            (x + 22 * u, y + 14 * u),
            w * 0.85,
            32 * u,
            brand.get("foreground", "#f5f7fc"),
            2,
            True,
        )
        text_block(
            draw,
            scene.get("subtitle", ""),
            (x + 22 * u, end + 5 * u),
            w * 0.85,
            20 * u,
            "#c0c9d9",
            2,
        )
    if brand.get("name"):
        text_block(
            draw,
            brand["name"],
            (w * 0.05, h * 0.045),
            w * 0.65,
            20 * u,
            brand.get("accent", "#70e2bf"),
            1,
            True,
        )
    if logo:
        small = ImageOps.contain(
            logo, (int(w * 0.18), int(h * 0.09)), Image.Resampling.LANCZOS
        )
        canvas.paste(small, (int(w * 0.95 - small.width), int(h * 0.04)), small)
    return canvas
