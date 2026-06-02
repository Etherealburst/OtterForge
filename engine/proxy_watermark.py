"""
engine/proxy_watermark.py
--------------------------
Two-zone proxy watermark for MTG cards.

Collector bar layout (left → right):
  [CN number]  [set symbol ~center]  [artist]  [™ & © Wizards of the Coast]

Drawing order:
  For standard dark-bordered cards:
    1. Targeted fill (text-height only) on stamp zone + copyright zone
       → hides artist name and WotC text with minimal visual footprint.
  For all card types:
    2. "OtterForge Proxy" — white outlined text at _STAMP_X.
    3. "Not for sale"     — white outlined text, right-aligned, same row.
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
_STAMP_X      = 0.193   # "OtterForge Proxy" x-start (after CN number)
_COPYRIGHT_X  = 0.60    # right fill zone start (clears WotC copyright)
_COPYRIGHT_Y  = 0.065   # text baseline from bottom


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
    fill: tuple = (255, 255, 255),
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


def _should_apply_fill(card_json: dict | None, img: Image.Image) -> bool:
    """Return True for standard dark-bordered cards where a fill can safely
    hide the original collector-bar text without creating visible artifacts.

    Skips fill for: borderless, white-bordered, full-art, extended-art,
    showcase, and any other non-standard frame treatment.
    """
    if card_json:
        bc = card_json.get("border_color", "")
        if bc in ("white", "borderless", "silver"):
            return False
        fe = card_json.get("frame_effects") or []
        if any(e in fe for e in ("extendedart", "showcase", "inverted", "fullart")):
            return False
        if card_json.get("full_art", False):
            return False
        return bc in ("black", "gold")
    # Fallback: pixel-sample bottom-left corner (card border zone)
    w, h = img.size
    sample = _sample_bg(img, 0, int(h * 0.93), int(w * 0.04), h)
    return (sample[0] + sample[1] + sample[2]) // 3 < 40


def _fill_zone(draw: ImageDraw.ImageDraw, img: Image.Image,
               x0: int, x1: int, y0: int, y1: int, y_sample_top: int) -> None:
    """Fill columns x0..x1 between y0..y1 with per-column median brightness.

    Samples from y_sample_top to card bottom so that majority background
    pixels dominate the median and high-contrast text pixels are erased.
    """
    h = img.size[1]
    for x in range(x0, x1):
        col = [img.getpixel((x, y)) for y in range(y_sample_top, h)]
        col.sort(key=lambda p: p[0] + p[1] + p[2])
        draw.line([(x, y0), (x, y1)], fill=col[len(col) // 2])


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

        sz   = max(9, int(h * 0.020) - 1)    # font size -1
        font = _load_font(sz)

        copyright_y = h - max(sz + 2, int(h * _COPYRIGHT_Y))
        text_y = max(y_top + 1, copyright_y) - 3   # moved up vs previous +2

        # Measure text height for the targeted fill
        try:
            bb = font.getbbox(stamp)
            text_h_px = bb[3] - bb[1]
        except Exception:
            text_h_px = sz

        nfs = "Not for sale"
        try:
            nfs_w = font.getbbox(nfs)[2] - font.getbbox(nfs)[0]
        except Exception:
            nfs_w = len(nfs) * max(4, sz * 6 // 10)

        stamp_x   = int(w * _STAMP_X)
        cx        = int(w * _COPYRIGHT_X)
        apply_fill = _should_apply_fill(card_json, img)

        # NFS x: standard dark cards keep right-aligned position;
        # extended/borderless shift 3× further left (floor at card centre).
        if apply_fill:
            nfs_x = w - max(4, w // 60) - nfs_w - 40
        else:
            nfs_x = max(w // 2, w - max(4, w // 60) - nfs_w - 190)
        nfs_y = text_y

        # Fill band: text height + 2px padding, stays within the strip
        fill_y0 = max(y_top, text_y - 2)
        fill_y1 = min(h - 1, text_y + text_h_px + 2)

        draw = ImageDraw.Draw(img)

        if apply_fill:
            # Left zone: covers OtterForge Proxy text + stale artifacts.
            # Ends at ~45% (text can extend to ~45%, set symbol starts at ~62%).
            # Starts at y_top to catch artifacts at any vertical offset.
            _fill_zone(draw, img, stamp_x, int(w * 0.45), y_top, fill_y1, y_top)
            # Right zone: WotC copyright (70% to edge), text height only.
            _fill_zone(draw, img, cx, w, fill_y0, fill_y1, y_top)

        # ── "OtterForge Proxy" — white outlined text (epaisseur 1) ───────────
        _outlined_text(draw, (stamp_x, text_y), stamp, font, epaisseur=1)

        # ── "Not for sale" — white outlined text (epaisseur 1) ───────────────
        _outlined_text(draw, (nfs_x, nfs_y), nfs, font, epaisseur=1)

    def _stamp(self, card_json: dict | None) -> str:
        return "OtterForge Proxy"
