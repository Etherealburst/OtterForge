"""
engine/proxy_watermark.py
--------------------------
Two-zone proxy watermark for MTG cards.

Collector bar layout (left → right):
  [CN number]  [set symbol ~center]  [™ & © Wizards of the Coast]

Dark-bordered cards (standard behaviour):
  1. Copyright fill (57%→right edge) — hides Wizards text via per-column median.
  2. "OtterForge Proxy" tight opaque box at _STAMP_X, colour from CN zone.
  3. "Not for sale" right-aligned in copyright fill zone.

Light-bordered / extended-art cards (adaptive behaviour):
  No copyright fill. Both labels get a semi-transparent dark overlay so they
  remain readable without obscuring card art or border colour.
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

_STRIP_RATIO  = 0.08    # strip height as fraction of card height
_STAMP_X      = 0.193   # stamp start: ~4px left of previous 0.206
_COPYRIGHT_X  = 0.57    # copyright fill start (right zone)
_COPYRIGHT_Y  = 0.065   # text baseline from bottom
_PRE_CLEAR_X  = 0.17    # left boundary of pre-clear zone

# Brightness threshold (0–255) for border detection.
# Below → dark border (standard black-bordered card).
# Above → light border (white, tan, extended-art, borderless…).
_DARK_BORDER_THRESHOLD = 40


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
) -> None:
    """Draw text with a 1-pixel outline — readable on any background."""
    x, y = pos
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text(pos, text, fill=fill, font=font)


def _text_color(bg: tuple) -> tuple:
    if (bg[0] + bg[1] + bg[2]) // 3 > 100:
        return (25, 20, 30)
    return (210, 206, 198)


def _is_dark_border(img: Image.Image) -> bool:
    """Detect border type by sampling the bottom-left corner of the card.

    For standard black-bordered cards the corner is near-black.
    For white/tan/extended-art cards it is clearly brighter.
    """
    w, h = img.size
    # Sample a small strip at the very bottom-left (outside card art)
    sample = _sample_bg(img, 0, int(h * 0.93), int(w * 0.04), h)
    brightness = (sample[0] + sample[1] + sample[2]) // 3
    return brightness < _DARK_BORDER_THRESHOLD



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

        try:
            bb = font.getbbox(stamp)
            text_w    = bb[2] - bb[0]
            text_h_px = bb[3] - bb[1]
        except Exception:
            text_w    = len(stamp) * max(4, sz * 6 // 10)
            text_h_px = sz

        nfs = "Not for sale"
        try:
            nfs_w = font.getbbox(nfs)[2] - font.getbbox(nfs)[0]
        except Exception:
            nfs_w = len(nfs) * max(4, sz * 6 // 10)

        stamp_x = int(w * _STAMP_X)
        cx      = int(w * _COPYRIGHT_X)
        nfs_x   = w - max(4, w // 60) - nfs_w - 40  # shifted left
        nfs_y   = text_y + sz + 2  # second collector row — set code + artist line

        dark_border = _is_dark_border(img)

        if dark_border:
            self._draw_dark(img, w, h, y_top, stamp, nfs,
                            stamp_x, cx, nfs_x, text_y, nfs_y, text_w, text_h_px, font)
        else:
            self._draw_adaptive(img, w, h, y_top, stamp, nfs,
                                 stamp_x, nfs_x, text_y, nfs_y, text_w, text_h_px, nfs_w, font)

    def _draw_dark(self, img, w, h, y_top, stamp, nfs,
                   stamp_x, cx, nfs_x, text_y, nfs_y, text_w, text_h_px, font):
        """Standard dark-border path: copyright fill + opaque stamp box."""
        draw = ImageDraw.Draw(img)

        bg_right = _sample_bg(img, int(w * 0.70), y_top, int(w * 0.90), h)

        # ── 1. Copyright fill — per-column median ────────────────────────────
        for x in range(cx, w):
            col = [img.getpixel((x, y)) for y in range(y_top, h)]
            col.sort(key=lambda p: p[0] + p[1] + p[2])
            bg_col = col[len(col) // 2]
            draw.line([(x, y_top), (x, h - 1)], fill=bg_col)

        # ── 2. "OtterForge Proxy" — tight opaque box, colour from CN zone ────
        bg_stamp = _sample_bg(img, 0, y_top, int(w * 0.12), h)
        draw.rectangle(
            [stamp_x,              text_y - 1,
             stamp_x + text_w + 1, text_y + text_h_px + 1],
            fill=bg_stamp,
        )
        draw.text((stamp_x, text_y), stamp, fill=_text_color(bg_stamp), font=font)

        # ── 3. "Not for sale" — right-aligned, shifted down ──────────────────
        draw.text((nfs_x, nfs_y), nfs, fill=_text_color(bg_right), font=font)

    def _draw_adaptive(self, img, w, h, y_top, stamp, nfs,
                       stamp_x, nfs_x, text_y, nfs_y, text_w, text_h_px, nfs_w, font):
        """Light-border / extended-art path: outlined text, no background box."""
        draw = ImageDraw.Draw(img)
        _outlined_text(draw, (stamp_x, text_y), stamp, font)
        _outlined_text(draw, (nfs_x,   nfs_y),  nfs,   font)

    def _stamp(self, card_json: dict | None) -> str:
        return "OtterForge Proxy"
