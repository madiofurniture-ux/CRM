"""Product mockups for architects' renders and project presentations.

- cut-out: the product on a transparent background (PNG), to drop into a
  render or mood board. The plain, light backdrop most catalogue shots use
  is removed: near-white pixels connected to the picture's edge become
  transparent (the product's own whites, inside it, stay). A busy backdrop
  can't be removed this way; the picture is then kept as it is and says so.
- room: the cut-out standing on the floor of a neutral room, with a soft
  shadow (furniture).
- wall: the picture tiled across a wall above a skirting (MAP finishes and
  textures).
- framed: the picture hung on the wall (doors, windows and other pictures).
- render kit: a ZIP of every product's cut-out and mockup, with a CSV of
  codes, names and sizes, for an architect to use in their renders.

Pure Pillow + numpy; MADIO's name and the product code go on every mockup.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
WALL, FLOOR, SKIRTING = (237, 232, 226), (205, 191, 174), (222, 214, 204)
KINDS = ("cutout", "room", "wall", "framed")
DEFAULT_KIND = {"Furniture": "room", "MAP": "wall", "D&W": "framed"}
MAX_KIT_ITEMS = 60


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)
    except Exception:
        return ImageFont.load_default()


def load(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def _grow(seed: np.ndarray, allowed: np.ndarray, limit: int = 600) -> np.ndarray:
    """The part of `allowed` connected to `seed` (4-neighbour flood fill)."""
    region = seed & allowed
    for _ in range(limit):
        grown = region.copy()
        grown[1:, :] |= region[:-1, :]
        grown[:-1, :] |= region[1:, :]
        grown[:, 1:] |= region[:, :-1]
        grown[:, :-1] |= region[:, 1:]
        grown &= allowed
        if (grown == region).all():
            break
        region = grown
    return region


def cutout(data: bytes, tolerance: int = 26) -> tuple[Image.Image, bool]:
    """(RGBA cut-out, whether the backdrop was removed)."""
    img = load(data)
    img.thumbnail((1400, 1400))
    arr = np.asarray(img).astype(np.int16)
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    light = (border.min(axis=1) >= 255 - 3 * tolerance)
    if light.mean() < 0.7:                       # not a plain light backdrop
        rgba = img.convert("RGBA")
        return rgba, False
    near_white = arr.min(axis=2) >= 255 - tolerance
    # Flood from the edges on a reduced copy (fast), then refine at full size.
    step = max(1, max(img.size) // 350)
    small = near_white[::step, ::step]
    seed = np.zeros_like(small)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    region = _grow(seed, small)
    full = np.repeat(np.repeat(region, step, axis=0), step, axis=1)[:near_white.shape[0], :near_white.shape[1]]
    background = full & near_white
    if background.mean() < 0.05:                 # nothing to remove: the product fills the picture
        return img.convert("RGBA"), False
    alpha = Image.fromarray(np.where(background, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.8))
    rgba = img.convert("RGBA")
    rgba.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        pad = int(0.03 * max(rgba.size))
        rgba = rgba.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                          min(rgba.width, box[2] + pad), min(rgba.height, box[3] + pad)))
    return rgba, True


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def jpeg_bytes(img: Image.Image, quality: int = 88) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _room(size=(1600, 1000), floor_at: int = 720) -> Image.Image:
    w, h = size
    room = Image.new("RGB", size, WALL)
    d = ImageDraw.Draw(room)
    for y in range(floor_at, h):                  # floor, a touch darker towards the front
        t = (y - floor_at) / max(h - floor_at, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(c * (1 - 0.12 * t)) for c in FLOOR))
    d.rectangle([0, floor_at - 14, w, floor_at], fill=SKIRTING)
    return room


def _label(img: Image.Image, company: str, code: str, name: str, size_text: str = "") -> None:
    d = ImageDraw.Draw(img)
    w, h = img.size
    lines = [(f"{company}".upper(), _font(22, True)), (" · ".join(x for x in (code, name) if x), _font(20))]
    if size_text:
        lines.append((size_text, _font(17)))
    y = h - 30 - sum(f.size + 8 for _, f in lines)
    pad_w = max(d.textlength(t, font=f) for t, f in lines) + 36
    panel = Image.new("RGBA", (int(pad_w), h - y - 12), (255, 255, 255, 205))
    img.paste(panel, (24, y - 10), panel)
    for text, f in lines:
        d.text((42, y), text, font=f, fill=(32, 33, 61))
        y += f.size + 8


def room(data: bytes, *, company: str = "MADIO", code: str = "", name: str = "", size_text: str = "",
         cut: tuple | None = None) -> Image.Image:
    """The product standing on the floor of a neutral room. A picture whose
    backdrop can't be removed (a room shot) is hung on the wall instead.
    `cut` is the picture's cutout() when the caller already has it."""
    piece, ok = cut or cutout(data)
    piece = piece.copy()
    if not ok:
        return framed(data, company=company, code=code, name=name, size_text=size_text)
    scene = _room()
    W, H = scene.size
    piece.thumbnail((int(W * 0.6), int(H * 0.55)))
    pw, ph = piece.size
    x, base = (W - pw) // 2, 790
    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([x + pw * 0.06, base - 22, x + pw * 0.94, base + 18], fill=(40, 30, 20, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    scene.paste(shadow, (0, 0), shadow)
    scene.paste(piece, (x, base - ph), piece)
    _label(scene, company, code, name, size_text)
    return scene


def wall(data: bytes, *, company: str = "MADIO", code: str = "", name: str = "", size_text: str = "") -> Image.Image:
    """The finish across a wall: the picture tiled above the skirting."""
    texture = load(data)
    texture.thumbnail((520, 520))
    scene = _room()
    W, H = scene.size
    wall_h = 706
    tiled = Image.new("RGB", (W, wall_h))
    for ty in range(0, wall_h, texture.height):
        for tx in range(0, W, texture.width):
            tiled.paste(texture, (tx, ty))
    # Light from the top left, so the wall reads as a surface, not a photo.
    shade = Image.linear_gradient("L").resize((W, wall_h)).point(lambda v: int(v * 0.35))
    tiled = Image.composite(Image.new("RGB", tiled.size, (20, 20, 20)), tiled, shade)
    scene.paste(tiled, (0, 0))
    _label(scene, company, code, name, size_text)
    return scene


def framed(data: bytes, *, company: str = "MADIO", code: str = "", name: str = "", size_text: str = "") -> Image.Image:
    """The picture hung on the wall with a frame and shadow."""
    pic = load(data)
    scene = _room()
    W, H = scene.size
    pic.thumbnail((int(W * 0.46), int(H * 0.5)))
    pw, ph = pic.size
    x, y = (W - pw) // 2, 120
    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([x + 10, y + 16, x + pw + 26, y + ph + 30], fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    scene.paste(shadow, (0, 0), shadow)
    ImageDraw.Draw(scene).rectangle([x - 14, y - 14, x + pw + 14, y + ph + 14], fill=(60, 58, 56))
    scene.paste(pic, (x, y))
    _label(scene, company, code, name, size_text)
    return scene


def make(kind: str, data: bytes, **label) -> tuple[bytes, str, bool]:
    """(image bytes, media type, backdrop removed?) for one mockup kind."""
    if kind == "cutout":
        img, ok = cutout(data)
        return png_bytes(img), "image/png", ok
    fn = {"room": room, "wall": wall, "framed": framed}.get(kind)
    if not fn:
        raise ValueError(f"Mockup kind must be one of {', '.join(KINDS)}")
    return jpeg_bytes(fn(data, **label)), "image/jpeg", True


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-")[:40] or "item"


def render_kit(items: list[dict], *, company: str = "MADIO", division_kind: dict | None = None) -> bytes:
    """ZIP for architects: each product's cut-out (PNG) and mockup (JPG), a
    CSV of codes, names and sizes, and a short read-me."""
    buf = io.BytesIO()
    rows = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for it in items[:MAX_KIT_ITEMS]:
            data = it.get("image_bytes") or b""
            if not data:
                continue
            base = f"{slug(it.get('code'))}_{slug(it.get('name'))}"
            label = {"company": company, "code": it.get("code", ""), "name": it.get("name", ""),
                     "size_text": it.get("size_text", "")}
            try:
                cut, ok = cutout(data)
            except Exception:
                continue                                   # not a readable picture
            z.writestr(f"cutouts/{base}.png", png_bytes(cut))
            kind = (division_kind or DEFAULT_KIND).get(it.get("division") or "", "room")
            scene = room(data, cut=(cut, ok), **label) if kind == "room" else \
                {"wall": wall, "framed": framed}[kind](data, **label)
            z.writestr(f"mockups/{base}_{kind}.jpg", jpeg_bytes(scene))
            rows.append({"code": it.get("code", ""), "name": it.get("name", ""), "category": it.get("category", ""),
                         "size": it.get("size_text", ""), "features": " | ".join(it.get("features") or []),
                         "cutout": f"cutouts/{base}.png", "background_removed": "yes" if ok else "no"})
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["code", "name", "category", "size", "features", "cutout",
                                                 "background_removed"])
        writer.writeheader()
        writer.writerows(rows)
        z.writestr("products.csv", out.getvalue())
        z.writestr("README.txt", (
            f"{company} render kit\n\n"
            "cutouts/  - each product on a transparent background (PNG) for your renders and mood boards.\n"
            "mockups/  - each product in a neutral room or on a wall, for presentations.\n"
            "products.csv - codes, names and sizes; scale the cut-outs to the sizes listed.\n\n"
            "Where background_removed is 'no', the original picture had a busy backdrop and is included as is.\n"
            f"Please quote the {company} code when you specify a product.\n"))
    return buf.getvalue()
