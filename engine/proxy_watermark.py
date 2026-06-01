"""
engine/proxy_watermark.py
--------------------------
Replaces the copyright line of an MTG card image with an OtterForge proxy stamp.

The copyright text ("™ & © Wizards of the Coast") lives at the right end of the
collector bar, roughly 5 % from the bottom of the image.  We:
  1. Sample the LOCAL background colour at that position (darkest pixels = bg).
  2. Fill the copyright zone with that colour so the card border looks unchanged.
  3. Draw small stamp text in an auto-adjusted colour (dark on light bg, light on dark).
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

# The copyright zone spans from this fraction of the card height FROM THE BOTTOM
# up to the card edge.  8 % gives room for the text to sit above the very bottom.
_STRIP_RATIO = 0.08

# The stamp starts at this fraction of card width.
# Copyright text begins at ~52-55 % of width; stamp overlaps it from there.
_STAMP_X = 0.533

# Fraction from the bottom where the copyright TEXT BASELINE sits.
# 0.065 = ~5px higher than 0.053 on a 420px display card.
_COPYRIGHT_Y = 0.065


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _WINDOWS_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _sample_bg(img: Image.Image, x0: int, y0: int, x1: int, y1: int) -> tuple:
    """Return the background colour of the region.

    Samples on a grid, sorts by brightness and returns the median-dark 40 %
    — those are the background pixels, not the bright text glyphs.
    """
    w, h = img.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    pixels = []
    sx = max(1, (x1 - x0) // 16)
    sy = max(1, (y1 - y0) // 5)
    for y in range(y0, y1, sy):
        for x in range(x0, x1, sx):
            pixels.append(img.getpixel((x, y)))
    if not pixels:
        return (14, 11, 19)
    pixels.sort(key=lambda p: p[0] + p[1] + p[2])
    # Take the darker half — that's the background, not the text
    dark = pixels[: max(1, len(pixels) // 2)]
    r = sum(p[0] for p in dark) // len(dark)
    g = sum(p[1] for p in dark) // len(dark)
    b = sum(p[2] for p in dark) // len(dark)
    return (r, g, b)


def _text_color(bg: tuple) -> tuple:
    """Dark text on light backgrounds, light text on dark backgrounds."""
    brightness = (bg[0] + bg[1] + bg[2]) // 3
    if brightness > 100:
        return (25, 20, 30)     # dark on light (e.g. Sol Ring silver)
    return (210, 206, 198)      # light on dark (e.g. Lightning Bolt)


class ProxyWatermark:
    """Replaces the MTG copyright text with an OtterForge proxy stamp."""

    # ── public API ────────────────────────────────────────────────────────────

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
        """Apply watermark in-place to an already-open PIL Image (no disk write)."""
        self._draw(img, card_json)

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw(self, img: Image.Image, card_json: dict | None) -> None:
        w, h = img.size

        strip_h = max(14, int(h * _STRIP_RATIO)) - 7
        y_top   = h - strip_h
        erase_x = int(w * _STAMP_X)

        stamp = self._stamp(card_json)
        if not stamp:
            return

        # Font: ~1.6 % of card height — clearly readable, close to copyright size
        sz = max(8, int(h * 0.016))
        font = _load_font(sz)

        # Horizontal: a small margin right of the erase boundary
        text_x = erase_x + max(2, w // 180)

        # Vertical: align with the copyright baseline, lowered 1px
        copyright_y = h - max(sz + 2, int(h * _COPYRIGHT_Y))
        text_y = max(y_top + 1, copyright_y) + 1

        # Sample background at the collector bar area for the fill colour
        bg = _sample_bg(img, max(0, erase_x - 60), y_top, erase_x, h)

        draw = ImageDraw.Draw(img)
        # Full strip from y_top to bottom — covers Wizards copyright regardless of card variant
        draw.rectangle([erase_x, y_top, w, h], fill=bg)
        draw.text((text_x, text_y), stamp, fill=_text_color(bg), font=font)

    # ── text builder ──────────────────────────────────────────────────────────

    def _stamp(self, card_json: dict | None) -> str:
        if card_json:
            year = (card_json.get("released_at") or "")[:4]
            if year:
                return f"{year} OtterForge Proxy • Not for sale"
        return "OtterForge Proxy • Not for sale"
