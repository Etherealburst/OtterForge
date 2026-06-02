"""
engine/proxy_watermark.py
--------------------------
Two-zone proxy watermark for MTG cards.

Collector bar layout (left → right):
  [CN number]  [set symbol ~center]  [™ & © Wizards of the Coast]

Drawing order (all card types):
  1. Copyright fill (57 %→right edge) — per-column median, hides WotC text.
  2. "OtterForge Proxy" — outlined text at _STAMP_X, no opaque box.
  3. "Not for sale"     — outlined text, right-aligned, on the artist/set row.
"""

import os
from PIL import Image, ImageDraw, ImageFont


_WINDOWS_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\verdana.ttf",
]

_STRIP_RATIO       = 0.08   # strip height as fraction of card height
_STAMP_X           = 0.193  # "OtterForge Proxy" x-start (left zone, after CN number)
_COPYRIGHT_X       = 0.57   # copyright fill start (right zone, clears set symbol)
_COPYRIGHT_Y       = 0.065  # text baseline from bottom
_DARK_BG_THRESHOLD = 40     # border brightness below this → dark card → apply fill


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _WINDOWS_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _sample_bg(img: Image.Image, x0: int, y0: int, x1: int, y1: int) -> tuple:
    """Return the background colour (darkest 50 % of sampled pixels)."""
    iw, ih = img.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(iw, x1), min(ih, y1)
    pixels = []
    sx = max(1, (x1 - x0) // 16)
    sy = max(1, (y1 - y0) // 5)
    for y in range(y0, y1, sy):
        for x in range(x0, x1, sx):
            pixels.append(img.getpixel((x, y)))
    if not pixels:
        return (14, 11, 19)
    pixels.sort(key=lambda p: p[0] + p[1] + p[2])
    dark = pixels[: max(1, len(pixels) // 2)]
    r = sum(p[0] for p in dark) // len(dark)
    g = sum(p[1] for p in dark) // len(dark)
    b = sum(p[2] for p in dark) // len(dark)
    return (r, g, b)


def _outlined_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple,
    text: str,
    font,
    fill: tuple = (220, 216, 208),
    outline: tuple = (0, 0, 0),
    epaisseur: int = 2,
) -> None:
    """Draw text with a stroke outline — readable on any background colour."""
    x, y = pos
    for dx in range(-epaisseur, epaisseur + 1):
        for dy in range(-epaisseur, epaisseur + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text(pos, text, fill=fill, font=font)


class ProxyWatermark:

    def apply(self, image_path: str, card_json: dict | None = None) -> None:
        """Modify the image at image_path in-place (disk write)."""
        try:
            raw = Image.open(image_path)
            if raw.mode in ("RGBA", "LA", "PA"):
                bg = Image.new("RGBA", raw.size, (14, 11, 19, 255))
                bg.paste(raw, mask=raw.split()[-1])
                img = bg.convert("RGB")
            else:
                img = raw.convert("RGB")
        except Exception as e:
            print(f"[ProxyWatermark] Cannot open {image_path!r}: {e}")
            return

        self._draw(img, card_json)
        img.save(image_path, "PNG", compress_level=6)
        print(f"[ProxyWatermark] Applied: {os.path.basename(image_path)}")

    def apply_to_image(self, img: Image.Image, card_json: dict | None = None) -> None:
        self._draw(img, card_json)

    def _draw(self, img: Image.Image, card_json: dict | None) -> None:
        w, h = img.size

        strip_h = max(14, int(h * _STRIP_RATIO)) - 9
        y_top   = h - strip_h

        stamp = self._stamp(card_json)
        if not stamp:
            return

        sz   = max(10, int(h * 0.020))
        font = _load_font(sz)

        copyright_y = h - max(sz + 2, int(h * _COPYRIGHT_Y))
        text_y = max(y_top + 1, copyright_y) - 5

        nfs = "Not for sale"
        try:
            nfs_w = font.getbbox(nfs)[2] - font.getbbox(nfs)[0]
        except Exception:
            nfs_w = len(nfs) * max(4, sz * 6 // 10)

        stamp_x = int(w * _STAMP_X)
        cx      = int(w * _COPYRIGHT_X)
        nfs_x   = w - max(4, w // 60) - nfs_w - 40
        nfs_y   = text_y + sz + 2   # second collector row — set code + artist line

        draw = ImageDraw.Draw(img)

        # Prefer Scryfall's border_color field; fall back to pixel sampling.
        # "black" / "gold" → dark frame → apply copyright fill.
        # "white" / "borderless" / "silver" → light/no frame → skip fill.
        border_color_field = (card_json or {}).get("border_color", "")
        if border_color_field in ("black", "gold"):
            dark_card = True
        elif border_color_field in ("white", "borderless", "silver"):
            dark_card = False
        else:
            border_sample = _sample_bg(img, 0, int(h * 0.93), int(w * 0.04), h)
            dark_card = (border_sample[0] + border_sample[1] + border_sample[2]) // 3 < _DARK_BG_THRESHOLD

        # ── 1. Copyright fill (dark cards only) ───────────────────────────────
        if dark_card:
            for x in range(cx, w):
                col = [img.getpixel((x, y)) for y in range(y_top, h)]
                col.sort(key=lambda p: p[0] + p[1] + p[2])
                bg_col = col[len(col) // 2]
                draw.line([(x, y_top), (x, h - 1)], fill=bg_col)

        # ── 2. "OtterForge Proxy" — outlined text, no background box ─────────
        _outlined_text(draw, (stamp_x, text_y), stamp, font, epaisseur=2)

        # ── 3. "Not for sale" — outlined text on the artist/set row ──────────
        _outlined_text(draw, (nfs_x, nfs_y), nfs, font, epaisseur=1)

    def _stamp(self, card_json: dict | None) -> str:
        return "OtterForge Proxy"
