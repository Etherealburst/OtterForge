"""
engine/proxy_watermark.py
--------------------------
Two-zone proxy watermark for MTG cards.

Collector bar layout (left → right):
  [CN number]  [set symbol ~center]  [™ & © Wizards of the Coast]

Drawing order:
  1. Pre-clear old stamp zone (26%→53%) — erases any previously applied stamp.
  2. Copyright fill (53%→right edge) — hides Wizards text.
  3. "OtterForge Proxy" tight box at fixed position (~43 % of width).
  4. "Not for sale" small text, right-aligned in the copyright fill zone.
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


def _text_color(bg: tuple) -> tuple:
    if (bg[0] + bg[1] + bg[2]) // 3 > 100:
        return (25, 20, 30)
    return (210, 206, 198)


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
        text_y = max(y_top + 1, copyright_y) - 5   # 1px higher than before

        # Measure stamp text dimensions before pre-clear so we can limit its height
        try:
            bb = font.getbbox(stamp)
            text_w    = bb[2] - bb[0]
            text_h_px = bb[3] - bb[1]
        except Exception:
            text_w    = len(stamp) * max(4, sz * 6 // 10)
            text_h_px = sz

        draw = ImageDraw.Draw(img)

        stamp_x = int(w * _STAMP_X)
        cx      = int(w * _COPYRIGHT_X)

        # Sample bg_right before fill for "Not for sale" text colour reference
        bg_right = _sample_bg(img, int(w * 0.70), y_top, int(w * 0.90), h)

        # ── 1. Copyright fill — per-column median, no hard edge / no overflow ─
        # For each column, take the median brightness pixel in the strip as the
        # background colour.  Text pixels (minority, high contrast) fall outside
        # the median and get overwritten; the rest of the strip looks unchanged.
        for x in range(cx, w):
            col = [img.getpixel((x, y)) for y in range(y_top, h)]
            col.sort(key=lambda p: p[0] + p[1] + p[2])
            bg_col = col[len(col) // 2]
            draw.line([(x, y_top), (x, h - 1)], fill=bg_col)

        # ── 2. "OtterForge Proxy" — tight bg box, colour from left footer edge ─
        # Sample from the far-left CN zone (0–12 %) which is untouched and holds
        # the true card-frame colour.
        text_x   = stamp_x
        bg_stamp = _sample_bg(img, 0, y_top, int(w * 0.12), h)
        draw.rectangle(
            [text_x,              text_y - 1,
             text_x + text_w + 1, text_y + text_h_px + 1],
            fill=bg_stamp,
        )
        draw.text((text_x, text_y), stamp, fill=_text_color(bg_stamp), font=font)

        # ── 4. "Not for sale" — same y-line, right-aligned in copyright zone ─
        nfs = "Not for sale"
        try:
            nfs_w = font.getbbox(nfs)[2] - font.getbbox(nfs)[0]
        except Exception:
            nfs_w = len(nfs) * max(4, sz * 6 // 10)
        nfs_x = w - max(4, w // 60) - nfs_w - 32
        draw.text((nfs_x, text_y), nfs, fill=_text_color(bg_right), font=font)

    def _stamp(self, card_json: dict | None) -> str:
        return "OtterForge Proxy"
