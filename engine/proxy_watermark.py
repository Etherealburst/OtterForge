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
from engine.file_utils import safe_save_png


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
_FILL_X       = 0.57    # fill zone start (covers stamps + WotC copyright, skips set symbol)
_COPYRIGHT_X  = 0.59    # sample zone for dark-bar detection
_COPYRIGHT_Y  = 0.065   # text baseline from bottom
_CARD_W_REF   = 672.0   # Scryfall native PNG width (reference for offset scaling)
_CARD_H_REF   = 936.0   # Scryfall native PNG height (reference for offset scaling)

# MPC bleed image sizes → (x_bleed, y_bleed) in pixels.
# _fit_to_mpc() and fit_native_to_mpc_300() centre the card content in a larger canvas
# with a black bleed border.  All position fractions must be applied to the card-content
# area, not the full canvas, otherwise the watermark drifts toward the top-left.
# x_bleed is always exactly MPC_BLEED_PX (the card hits the trim width precisely).
# y_bleed is approximated as the same value; the actual value is within ~15 px of this.
_MPC_BLEED_SIZES: dict[tuple[int, int], tuple[int, int]] = {
    (3288, 4488): (144, 144),   # 1200 DPI with bleed
    (822,  1122): (36,  36),    # 300 DPI with bleed
}


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


def _should_apply_fill(card_json: dict | None, img: Image.Image,
                       x0: int = 0, y0: int = 0,
                       ew: int | None = None, eh: int | None = None) -> bool:
    """Return True when the collector bar is dark enough to need fill/black-bg.

    White/silver borders are excluded upfront (they genuinely have light bars).
    Everything else — including borderless, extended-art, full-art, inverted —
    is decided by pixel-sampling the right zone of the collector bar, because
    Scryfall's border_color describes the card frame, not the collector strip.
    Many 'borderless' cards (Secret Lair, Final Fantasy, etc.) still have a
    dark bar at the bottom that benefits from fill treatment.

    x0, y0, ew, eh define the card-content area (bleed excluded).
    """
    if card_json:
        bc = card_json.get("border_color", "")
        if bc in ("white", "silver"):
            return False
    w, h = img.size
    if ew is None:
        ew = w - 2 * x0
    if eh is None:
        eh = h - 2 * y0
    sample = _sample_bg(img,
                        x0 + int(ew * _COPYRIGHT_X),
                        y0 + int(eh * 0.92),
                        x0 + ew,
                        y0 + eh)
    return (sample[0] + sample[1] + sample[2]) // 3 < 60


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

    def apply(self, image_path: str, card_json: dict | None = None,
              offset: tuple = (0, 0), nfs_offset: tuple = (0, 0),
              bg: str = "transparent", is_custom: bool = False) -> None:
        """Modify the image at image_path in-place (disk write).
        Saves a clean _orig.png alongside on first application (for preview use).
        is_custom=True skips the collector-bar fill zone (custom cards have no MTG bar).
        """
        # Preserve the pre-watermark original for zoom-preview transparency.
        # Always draw from _orig.png when it exists so re-applying watermark
        # (e.g. after creature-offset code update) never stacks two watermarks.
        _source = image_path
        if image_path.endswith(".png"):
            _orig = image_path.replace(".png", "_orig.png")
            if os.path.exists(_orig):
                _source = _orig          # draw on clean source, overwrite image_path
            else:
                try:
                    import shutil as _sh
                    _sh.copy2(image_path, _orig)
                except Exception:
                    pass

        try:
            raw = Image.open(_source)
            if raw.mode in ("RGBA", "LA", "PA"):
                _bg_img = Image.new("RGBA", raw.size, (14, 11, 19, 255))
                _bg_img.paste(raw, mask=raw.split()[-1])
                img = _bg_img.convert("RGB")
            else:
                img = raw.convert("RGB")
        except Exception as e:
            print(f"[ProxyWatermark] Cannot open {image_path!r}: {e}")
            return

        _norm = image_path.replace("\\", "/")
        _skip_fill = is_custom or "/cache/custom/" in _norm
        self._draw(img, card_json, offset, nfs_offset, bg, skip_fill=_skip_fill)
        safe_save_png(img, image_path, compress_level=6)
        print(f"[ProxyWatermark] Applied: {os.path.basename(image_path)}")

        # Workspace and inspector fall back to the native .png for display (not _1200dpi.png).
        # For upscaled custom cards, also watermark the native .png so the UI shows the change.
        if _skip_fill and image_path.endswith("_1200dpi.png"):
            _native = image_path.replace("_1200dpi.png", ".png")
            if os.path.isfile(_native):
                self.apply(_native, card_json, offset, nfs_offset, bg)

    def apply_to_image(self, img: Image.Image, card_json: dict | None = None,
                       offset: tuple = (0, 0), nfs_offset: tuple = (0, 0),
                       bg: str = "transparent") -> None:
        self._draw(img, card_json, offset, nfs_offset, bg)

    def _draw(self, img: Image.Image, card_json: dict | None,
              offset: tuple = (0, 0), nfs_offset: tuple = (0, 0),
              bg: str = "transparent", skip_fill: bool = False) -> None:
        w, h = img.size

        # Bleed compensation: MPC output images have a black border around the card
        # content.  All fractional positions must be computed against the card-content
        # area (ew × eh), then shifted by the bleed offsets (x0, y0) to canvas coords.
        _bleed = _MPC_BLEED_SIZES.get((w, h))
        if _bleed:
            x0, y0 = _bleed
        else:
            x0, y0 = 0, 0
        ew = w - 2 * x0   # effective card-content width
        eh = h - 2 * y0   # effective card-content height

        # Scale offsets from 672×936 reference to card-content dimensions
        ox     = round(offset[0]     * ew / _CARD_W_REF)
        oy     = round(offset[1]     * eh / _CARD_H_REF)
        nfs_ox = round(nfs_offset[0] * ew / _CARD_W_REF)
        nfs_oy = round(nfs_offset[1] * eh / _CARD_H_REF)

        strip_h = max(14, int(eh * _STRIP_RATIO)) - 9
        y_top   = y0 + eh - strip_h          # canvas y of collector-bar top

        stamp = self._stamp()
        if not stamp:
            return

        sz   = max(9, int(eh * 0.020) - 1)
        font = _load_font(sz)

        copyright_y  = y0 + eh - max(sz + 2, int(eh * _COPYRIGHT_Y))  # canvas y
        base_text_y  = max(y_top + 1, copyright_y) - 3                # canvas y, before offsets

        try:
            font.getbbox(stamp)   # validate font metrics are available
        except Exception:
            pass

        nfs = "Not for sale"
        try:
            nfs_w = font.getbbox(nfs)[2] - font.getbbox(nfs)[0]
        except Exception:
            nfs_w = len(nfs) * max(4, sz * 6 // 10)

        stamp_x   = max(x0, min(x0 + ew - 1, x0 + int(ew * _STAMP_X) + ox))
        stamp_ty  = max(y0, min(y0 + eh - sz - 1, base_text_y + oy))

        cx         = x0 + int(ew * _FILL_X)
        apply_fill = not skip_fill and _should_apply_fill(card_json, img, x0, y0, ew, eh)

        is_creature = card_json and "Creature" in card_json.get("type_line", "")
        nfs_creature_dy = sz if is_creature else 0

        if apply_fill:
            nfs_x = max(x0, min(x0 + ew - 1,
                                x0 + ew - max(4, ew // 60) - nfs_w - 40 + nfs_ox))
        else:
            nfs_x = max(x0, min(x0 + ew - 1,
                                max(x0 + ew // 2,
                                    x0 + ew - max(4, ew // 60) - nfs_w - 190) + nfs_ox))
        nfs_ty = max(y0, min(y0 + eh - sz - 1, base_text_y + nfs_oy + nfs_creature_dy))

        draw = ImageDraw.Draw(img)

        if apply_fill:
            # For creature cards stop 5 px before NFS to avoid clipping the P/T box.
            fill_x1 = max(cx, nfs_x - 5) if is_creature else x0 + ew
            # Sample the left border strip (within card content area) to get the frame colour.
            _border_col = _sample_bg(img, x0, y_top, max(x0 + 1, x0 + int(ew * 0.04)), y0 + eh)
            draw.rectangle([cx, y_top, fill_x1 - 1, y0 + eh - 1], fill=_border_col)
            _text_bg_fill = _border_col
        else:
            _text_bg_fill = (0, 0, 0)

        if bg == "black" or (bg == "auto" and apply_fill):
            pad_stamp = 1
            pad_nfs   = 4
            try:
                bb_s = font.getbbox(stamp)
                draw.rectangle([
                    stamp_x + bb_s[0] - pad_stamp, stamp_ty + bb_s[1] - pad_stamp,
                    stamp_x + bb_s[2] + pad_stamp, stamp_ty + bb_s[3] + pad_stamp,
                ], fill=_text_bg_fill)
                bb_n = font.getbbox(nfs)
                draw.rectangle([
                    nfs_x + bb_n[0] - pad_nfs, nfs_ty + bb_n[1] - pad_nfs,
                    nfs_x + bb_n[2] + pad_nfs, nfs_ty + bb_n[3] + pad_nfs,
                ], fill=_text_bg_fill)
            except Exception:
                pass

        _outlined_text(draw, (stamp_x, stamp_ty), stamp, font, epaisseur=1)
        _outlined_text(draw, (nfs_x,   nfs_ty),   nfs,   font, epaisseur=1)

    def _stamp(self) -> str:
        return "OtterForge Proxy"
