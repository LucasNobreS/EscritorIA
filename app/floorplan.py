"""Validated office partitions. Geometry travels with the layout, never global state."""

import math


class Layout(list):
    def __init__(self, items, walls, zones, exit_point=(650, 900)):
        super().__init__(items)
        self.walls = walls
        self.zones = zones
        self.exit = exit_point


def geometry(rooms, legacy_walls, legacy_zones, outline=None):
    if rooms is None and outline is None:
        return legacy_walls, legacy_zones
    walls = [
        (35, 35, 1835, 18),
        (35, 35, 18, 930),
        (1852, 35, 18, 930),
        (35, 947, 545, 18),
        (720, 947, 1150, 18),
    ]
    if outline is not None:
        walls, zones = envelope(outline)
    for r in rooms or []:
        x, y, w, h = (r[k] for k in ("x", "y", "w", "h"))
        door = r["door"]
        gap = 120
        t = 16
        for side in ("north", "south", "west", "east"):
            horizontal = side in ("north", "south")
            length = w if horizontal else h
            a = x if horizontal else (x if side == "west" else x + w - t)
            b = (y if side == "north" else y + h - t) if horizontal else y
            if side == door:
                half = (length - gap) / 2
                walls.extend(
                    [(a, b, half, t), (a + half + gap, b, half, t)]
                    if horizontal
                    else [(a, b, t, half), (a, b + half + gap, t, half)]
                )
            else:
                walls.append((a, b, w, t) if horizontal else (a, b, t, h))
    return walls, zones if outline is not None else [(53, 53, 1799, 894)]


def validate(value, outline=None):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 12:
        raise ValueError("Use no máximo 12 cômodos.")
    result = []
    ids = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("Cômodo inválido.")
        r = {k: float(raw[k]) for k in ("x", "y", "w", "h")}
        if not all(math.isfinite(v) for v in r.values()):
            raise ValueError("Medidas inválidas.")
        x, y, w, h = (r[k] for k in ("x", "y", "w", "h"))
        if (
            min(w, h) < 180
            or x < 70
            or y < 70
            or x + w > (outline["width"] + 15 if outline else 1830)
            or y + h > (outline["height"] + 15 if outline else 925)
        ):
            raise ValueError(
                "Cômodos devem ter pelo menos 180 × 180 e ficar dentro do piso."
            )
        if outline:
            _, zones = envelope(outline)
            if not all(
                any(
                    a + 20 <= px <= a + ww - 20 and b + 20 <= py <= b + hh - 20
                    for a, b, ww, hh in zones
                )
                for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))
            ):
                raise ValueError(
                    "Cômodo fora do formato escolhido. Mova ou diminua o cômodo."
                )
        for other in result:
            if (
                x < other["x"] + other["w"] + 32
                and x + w + 32 > other["x"]
                and y < other["y"] + other["h"] + 32
                and y + h + 32 > other["y"]
            ):
                raise ValueError(
                    "Separe os cômodos por pelo menos 32 unidades; não sobreponha paredes."
                )
        ident = str(raw.get("id", ""))
        if not ident or len(ident) > 50 or ident in ids:
            raise ValueError("Identificador de cômodo inválido.")
        ids.add(ident)
        r.update(
            id=ident,
            name=str(raw.get("name", "Cômodo"))[:40],
            door=raw.get("door", "south"),
        )
        if r["door"] not in ("north", "south", "west", "east"):
            raise ValueError("Porta inválida.")
        result.append(r)
    return result


def validate_outline(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Formato do escritório inválido.")
    shape = value.get("shape", "rectangle")
    width = float(value.get("width", 1835))
    height = float(value.get("height", 930))
    if shape not in ("rectangle", "l", "t") or not all(
        math.isfinite(n) for n in (width, height)
    ):
        raise ValueError("Formato ou medidas inválidas.")
    if not 1000 <= width <= 3000 or not 850 <= height <= 1800:
        raise ValueError("Largura: 1000 a 3000. Profundidade: 850 a 1800.")
    return dict(shape=shape, width=width, height=height)


def exit_point(outline):
    return (650, outline["height"] - 12) if outline else (650, 900)


def envelope(o):
    w, h = o["width"], o["height"]
    a = math.floor(w * 0.65 / 10 + 0.5) * 10
    b = math.floor(h * 0.55 / 10 + 0.5) * 10
    if o["shape"] == "l":
        vertices = [(0, 0), (a, 0), (a, b), (w, b), (w, h), (0, h)]
        zones = [(35, 35, a, h), (35 + a, 35 + b, w - a, h - b)]
    elif o["shape"] == "t":
        c = (w - a) / 2
        vertices = [
            (0, 0),
            (w, 0),
            (w, b),
            (c + a, b),
            (c + a, h),
            (c, h),
            (c, b),
            (0, b),
        ]
        zones = [(35, 35, w, b), (35 + c, 35 + b, a, h - b)]
    else:
        vertices = [(0, 0), (w, 0), (w, h), (0, h)]
        zones = [(35, 35, w, h)]
    walls = []
    for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1]):
        x, y = 35 + min(x1, x2), 35 + min(y1, y2)
        length = abs(x2 - x1) if y1 == y2 else abs(y2 - y1)
        if y1 == y2:
            if y1 == h and x <= 580 and x + length >= 720:
                walls.extend(
                    [(x, y - 9, 580 - x, 18), (720, y - 9, x + length - 720, 18)]
                )
            else:
                walls.append((x, y - 9, length, 18))
        else:
            walls.append((x - 9, y, 18, length))
    return walls, zones
