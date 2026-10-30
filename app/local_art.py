"""Local social cards: text and geometric artwork, no remote image service."""

import io
import re
import os
from pathlib import Path


def render(params):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ValueError(
            "Para gerar artes, execute Instalar-imagens.bat e reinicie o escritório."
        ) from None

    def color(key, default):
        value = str(params.get(key, default))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Use cores no formato #112233.")
        return value

    def text(key, limit):
        value = str(params.get(key, "")).strip()
        if len(value) > limit:
            raise ValueError(f"{key}: limite de {limit} caracteres.")
        return value

    title = text("title", 100)
    subtitle = text("subtitle", 260)
    brand = text("brand", 50)
    cta = text("cta", 50)
    if not title:
        raise ValueError("Informe um título para a arte.")
    size = (1080, 1080) if params.get("format") == "square" else (1080, 1350)
    bg = color("background", "#101d32")
    fg = color("foreground", "#ffffff")
    accent = color("accent", "#70e2bf")
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    w, h = size

    def font(size, bold=False):
        names = [
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            str(
                Path(os.environ.get("WINDIR", "C:/Windows"))
                / "Fonts"
                / ("arialbd.ttf" if bold else "arial.ttf")
            ),
        ]
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default(size=size)

    def lines(value, f, width):
        out = []
        for para in value.splitlines():
            line = ""
            for word in para.split():
                if d.textlength(word, font=f) > width:
                    raise ValueError(
                        "Palavra longa demais para a arte; divida o texto."
                    )
                trial = (line + " " + word).strip()
                if line and d.textlength(trial, font=f) > width:
                    out.append(line)
                    line = word
                else:
                    line = trial
            out.append(line)
        return out

    # Decorative geometry, deliberately no external URLs, scripts or file access.
    d.ellipse((w - 370, -170, w + 200, 400), fill=accent)
    d.rounded_rectangle((72, 82, 148, 94), radius=6, fill=accent)
    bf = font(26, True)
    for index, line in enumerate(lines(brand, bf, 560)):
        d.text((72, 116 + index * 36), line, font=bf, fill=fg)
    ts = 86
    while ts >= 42:
        tf = font(ts, True)
        tl = lines(title, tf, w - 144)
        if len(tl) * (ts + 14) <= h * 0.34:
            break
        ts -= 4
    else:
        raise ValueError("Título muito extenso; reduza o texto.")
    y = int(h * 0.30)
    for line in tl:
        d.text((72, y), line, font=tf, fill=fg)
        y += ts + 14
    y += 35
    sf = font(32)
    sl = lines(subtitle, sf, w - 144)
    if y + len(sl) * 46 > h - 230:
        raise ValueError("Texto não cabe na arte; reduza título ou descrição.")
    for line in sl:
        d.text((72, y), line, font=sf, fill=fg)
        y += 46
    if cta:
        cf = font(29, True)
        cw = d.textlength(cta, font=cf)
        if cw > w - 192:
            raise ValueError("Chamada final longa demais; reduza o texto.")
        d.rounded_rectangle((72, h - 172, 120 + cw, h - 94), radius=18, fill=accent)
        d.text((96, h - 154), cta, font=cf, fill=bg)
    output = io.BytesIO()
    im.save(output, format="JPEG", quality=95, optimize=True)
    return output.getvalue()
