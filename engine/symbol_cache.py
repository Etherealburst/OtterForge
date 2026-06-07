"""
engine/symbol_cache.py
-----------------------
Renders MTG mana symbol PNGs using the local mana-font TTF (assets/mana_symbols/fonts/mana.ttf).
Falls back to Scryfall download, then crude PIL shapes, if the font is unavailable.
"""

import os
import io
import math
import re as _re_mod
import threading

from PIL import Image, ImageDraw


# ── Cache dir ─────────────────────────────────────────────────────────────────

def _cache_dir() -> str:
    try:
        from config import CACHE_DIR
        d = os.path.join(CACHE_DIR, "symbols")
    except Exception:
        d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "symbols")
    os.makedirs(d, exist_ok=True)
    return d


# ── In-memory image cache ─────────────────────────────────────────────────────

_MEM: dict = {}         # (upper_symbol, diam) → PIL RGBA Image
_MEM_LOCK = threading.Lock()


# ── Mana font (mana-font TTF by Andrew Gioia) ─────────────────────────────────

# Unicode Private-Use Area codepoints (from mana-font CSS)
_MANA_CP: dict[str, int] = {
    'W':  0xe600, 'U':  0xe601, 'B':  0xe602, 'R':  0xe603, 'G':  0xe604,
    '0':  0xe605, '1':  0xe606, '2':  0xe607, '3':  0xe608, '4':  0xe609,
    '5':  0xe60a, '6':  0xe60b, '7':  0xe60c, '8':  0xe60d, '9':  0xe60e,
    '10': 0xe60f, '11': 0xe610, '12': 0xe611, '13': 0xe612, '14': 0xe613,
    '15': 0xe614, '16': 0xe62a, '17': 0xe62b, '18': 0xe62c, '19': 0xe62d,
    '20': 0xe62e,
    'X':  0xe615, 'Y':  0xe616, 'Z':  0xe617,
    'P':  0xe618,   # Phyrexian
    'S':  0xe619,   # Snow
    'T':  0xe61a,   # Tap
    'Q':  0xe61b,   # Untap
    'C':  0xe904,   # Colorless
    'E':  0xe907,   # Energy
}

# Official Scryfall palette: (background, foreground)
_BG = {
    'W': (249, 250, 244),   'U': (14,  104, 171),   'B': (21,  11,   0),
    'R': (211,  73,  16),   'G': (0,   115,  62),   'C': (202, 194, 190),
    'X': (149, 149, 149),   'T': (206, 110,  34),   'Q': (206, 110,  34),
    'S': (168, 210, 248),   'P': (167,  30,  42),   'E': (180, 120,  60),
}
_FG = {
    'W': (40,  30,   5),    'U': (255, 255, 255),   'B': (220, 210, 190),
    'R': (255, 255, 255),   'G': (255, 255, 255),   'C': (40,  40,  40),
    'X': (255, 255, 255),   'T': (255, 255, 255),   'Q': (255, 255, 255),
    'S': (20,  20,  20),    'P': (255, 255, 255),   'E': (255, 255, 255),
}
_NUM_BG = (165, 162, 160)
_NUM_FG = (22,  18,  14)


def _sym_colors(symbol: str) -> tuple[tuple, tuple]:
    k = symbol.upper()
    if _re_mod.fullmatch(r'\d+', k):
        return _NUM_BG, _NUM_FG
    return _BG.get(k, (149, 149, 149)), _FG.get(k, (255, 255, 255))


def _mana_font_path() -> "str | None":
    """Return local mana.ttf path if available."""
    try:
        from config import BASE_DIR as _BD
        base = _BD
    except Exception:
        base = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__file__))))
    p = os.path.join(base, "assets", "mana_symbols", "fonts", "mana.ttf")
    return p if os.path.isfile(p) else None


def _draw_mana_font_symbol(symbol: str, diam: int) -> "Image.Image | None":
    """
    Render a mana symbol using mana-font TTF.
    The font glyph encodes the inner symbol shape; we provide the circle background.
    """
    sym_up = symbol.upper()
    cp = _MANA_CP.get(sym_up)
    if cp is None:
        return None

    font_path = _mana_font_path()
    if not font_path:
        return None

    try:
        from PIL import ImageFont
        fnt = ImageFont.truetype(font_path, diam)
        ch = chr(cp)
        bg, fg = _sym_colors(sym_up)

        # Render at 2× for smooth edges, then downscale
        big = diam * 2
        fnt_big = ImageFont.truetype(font_path, big)

        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Outer circle (background pip color)
        bw = max(2, big // 18)
        draw.ellipse([0, 0, big - 1, big - 1],
                     fill=bg + (255,), outline=(0, 0, 0, 200), width=bw)

        # 2. Inner symbol glyph centered — numbers at 62% (tight pip), colors at 86%
        is_num = bool(_re_mod.fullmatch(r'\d+', sym_up))
        g = round(big * (0.62 if is_num else 0.86))
        off = (big - g) // 2
        fnt_g = ImageFont.truetype(font_path, g)
        draw.text((off, off), ch, font=fnt_g, fill=fg + (255,))

        # 3. Circular alpha mask (crop corners cleanly)
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).ellipse([bw, bw, big - bw - 1, big - bw - 1], fill=255)
        img.putalpha(mask)

        return img.resize((diam, diam), Image.LANCZOS)

    except Exception:
        return None


# ── Scryfall SVG download + cairosvg conversion ───────────────────────────────

_SCRYFALL_SVG = "https://svgs.scryfall.io/card-symbols/{}.svg"


def _svg_to_pil(svg_bytes: bytes, diam: int) -> "Image.Image | None":
    """Convert SVG bytes → RGBA PIL Image via cairosvg or svglib."""
    try:
        import cairosvg
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes,
                                     output_width=diam, output_height=diam)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception:
        pass
    try:
        import tempfile, os as _os
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            f.write(svg_bytes); tmp = f.name
        try:
            drawing = svg2rlg(tmp)
            if drawing:
                sx = diam / drawing.width  if drawing.width  else 1
                sy = diam / drawing.height if drawing.height else 1
                drawing.width = diam; drawing.height = diam
                drawing.transform = (sx, 0, 0, sy, 0, 0)
                png_bytes = renderPM.drawToString(drawing, fmt="PNG",
                                                  dpi=72, bg=0xFFFFFF00)
                return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        finally:
            try: _os.unlink(tmp)
            except Exception: pass
    except Exception:
        pass
    return None


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (128, 128, 128)


def _extract_svg_colors(svg_bytes: bytes) -> "tuple[tuple, tuple] | None":
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(svg_bytes.decode('utf-8', errors='replace'))
        def _strip_ns(tag): return tag.split('}')[-1] if '}' in tag else tag
        bg = fg = None
        for el in root.iter():
            tag = _strip_ns(el.tag)
            fill = el.get('fill', '')
            if not fill or fill in ('none', 'transparent', ''):
                continue
            if tag == 'circle' and bg is None:
                bg = _hex_to_rgb(fill)
            elif tag in ('path', 'polygon', 'rect') and fg is None and fill != '#000000':
                fg = _hex_to_rgb(fill)
            elif tag in ('path', 'polygon') and fg is None:
                fg = _hex_to_rgb(fill)
        if bg is None:
            return None
        if fg is None:
            bright = sum(bg) // 3
            fg = (20, 15, 5) if bright > 150 else (245, 240, 220)
        return bg, fg
    except Exception:
        return None


def _download_symbol(symbol: str, diam: int) -> "Image.Image | None":
    """Download from Scryfall: try full SVG render, else color-accurate PIL."""
    try:
        import requests as _req
        url = _SCRYFALL_SVG.format(symbol.upper())
        r = _req.get(url, timeout=10, headers={"User-Agent": "OtterForge/1.0"})
        if not r.ok:
            return None
        svg_bytes = r.content
        img = _svg_to_pil(svg_bytes, diam)
        if img:
            return img
        colors = _extract_svg_colors(svg_bytes)
        if colors:
            bg, fg = colors
            k = symbol.upper()
            _BG[k] = bg
            _FG[k] = fg
    except Exception:
        pass
    return None


# ── PIL fallback drawing (supersampled) ───────────────────────────────────────

def _draw_pil_symbol(symbol: str, diam: int) -> "Image.Image":
    """Draw a mana symbol entirely in PIL (supersampled 4×)."""
    OS = 4
    big = diam * OS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = big // 2
    r = big // 2 - OS
    sym = symbol.upper()
    bg, fg = _sym_colors(sym)
    bw = max(2, big // 18)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=bg, outline=(0, 0, 0, 255), width=bw)
    if sym == 'W':   _sun(draw, cx, cy, int(r * 0.52), fg)
    elif sym == 'U': _teardrop(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'B': _skull(draw, cx, cy, int(r * 0.48), fg)
    elif sym == 'R': _flame(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'G': _leaf(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'T': _tap_arrow(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'S': _snowflake(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'C': _diamond(draw, cx, cy, int(r * 0.48), fg)
    elif sym == 'P': _phi(draw, cx, cy, int(r * 0.50), fg, big)
    else: _center_text(draw, cx, cy, sym, int(r * 0.88), fg, big)
    return img.resize((diam, diam), Image.LANCZOS)


def _sun(draw, cx, cy, r, color):
    pts = []
    for i in range(10):
        ang = math.pi * i / 5 - math.pi / 2
        rad = r if i % 2 == 0 else int(r * 0.42)
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def _teardrop(draw, cx, cy, r, color):
    n = 24
    pts = [(cx + r * math.sin(math.pi * i / (n - 1)) * 0.85,
            cy - r * 0.65 + r * 0.65 * (1 - math.cos(math.pi * i / (n - 1))))
           for i in range(n)]
    pts.append((cx, cy + r))
    draw.polygon(pts, fill=color)


def _skull(draw, cx, cy, r, color):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + int(r * 0.55)), (cx - r, cy)]
    draw.polygon(pts, fill=color)
    draw.rectangle([cx - int(r * 0.35), cy + int(r * 0.40),
                    cx + int(r * 0.35), cy + int(r * 0.58)], fill=color)


def _flame(draw, cx, cy, r, color):
    pts = [
        (cx, cy - r), (cx + int(r * 0.55), cy - int(r * 0.20)),
        (cx + int(r * 0.35), cy + int(r * 0.10)), (cx + int(r * 0.70), cy + int(r * 0.55)),
        (cx, cy + r), (cx - int(r * 0.70), cy + int(r * 0.55)),
        (cx - int(r * 0.35), cy + int(r * 0.10)), (cx - int(r * 0.55), cy - int(r * 0.20)),
    ]
    draw.polygon(pts, fill=color)


def _leaf(draw, cx, cy, r, color):
    draw.ellipse([cx - int(r * 0.38), cy - r, cx + int(r * 0.38), cy + r], fill=color)
    draw.polygon([(cx, cy - r), (cx + int(r * 0.18), cy - int(r * 0.55)),
                  (cx - int(r * 0.18), cy - int(r * 0.55))], fill=color)


def _tap_arrow(draw, cx, cy, r, color):
    hw = max(1, int(r * 0.28))
    pts = [
        (cx + int(r * 0.10), cy - r), (cx + r, cy + int(r * 0.10)),
        (cx + int(r * 0.55), cy + int(r * 0.55)), (cx + int(r * 0.30), cy + int(r * 0.25)),
        (cx + int(r * 0.30), cy + r), (cx - int(r * 0.30), cy + r),
        (cx - int(r * 0.30), cy + int(r * 0.25)), (cx - int(r * 0.55), cy + int(r * 0.55)),
        (cx - r, cy + int(r * 0.10)), (cx - int(r * 0.10), cy - r),
    ]
    draw.polygon(pts, fill=color)


def _snowflake(draw, cx, cy, r, color):
    for i in range(6):
        ang = math.pi * i / 3
        x1, y1 = cx + int(r * math.cos(ang)), cy + int(r * math.sin(ang))
        lw = max(1, r // 4)
        draw.line([(cx, cy), (x1, y1)], fill=color, width=lw)


def _diamond(draw, cx, cy, r, color):
    draw.polygon([(cx, cy - r), (cx + int(r * 0.72), cy),
                  (cx, cy + r), (cx - int(r * 0.72), cy)], fill=color)


def _phi(draw, cx, cy, r, color):
    lw = max(1, r // 3)
    draw.ellipse([cx - int(r * 0.7), cy - int(r * 0.7),
                  cx + int(r * 0.7), cy + int(r * 0.7)],
                 fill=None, outline=color, width=lw)
    draw.line([(cx, cy - r), (cx, cy + r)], fill=color, width=lw)


def _center_text(draw, cx, cy, text: str, r: int, color: tuple, big: int) -> None:
    from PIL import ImageFont
    font_sz = max(8, int(r * 1.10))
    cands = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
             r"C:\Windows\Fonts\segoeui.ttf"]
    font = ImageFont.load_default()
    for p in cands:
        try:
            font = ImageFont.truetype(p, font_sz); break
        except Exception:
            continue
    max_text_w = int(r * 1.65)
    while font_sz > 7:
        try:
            bb = font.getbbox(text)
            if bb[2] - bb[0] <= max_text_w:
                break
        except Exception:
            break
        font_sz -= 1
        for p in cands:
            try:
                font = ImageFont.truetype(p, font_sz); break
            except Exception:
                continue
    try:
        bb = font.getbbox(text)
        tx = cx - (bb[2] - bb[0]) // 2 - bb[0]
        ty = cy - (bb[3] - bb[1]) // 2 - bb[1]
    except Exception:
        tx, ty = cx - font_sz // 3, cy - font_sz // 2
    draw.text((tx, ty), text, fill=color, font=font)


# ── Public API ────────────────────────────────────────────────────────────────

def get_symbol(symbol: str, diam: int = 36) -> "Image.Image":
    """
    Return a PIL RGBA image of the given mana symbol at diam×diam pixels.
    Priority: disk cache → mana-font TTF → Scryfall download → PIL fallback.

    symbol: 'W', 'U', 'B', 'R', 'G', 'C', 'X', 'T', '2', '10', etc.
    Thread-safe: double-check lock prevents duplicate downloads.
    """
    sym_up = symbol.upper()
    key    = (sym_up, diam)

    # Fast path — pas de verrou si déjà en mémoire
    if key in _MEM:
        return _MEM[key]

    with _MEM_LOCK:
        # Double-check : un autre thread peut avoir rempli le cache pendant l'attente
        if key in _MEM:
            return _MEM[key]

        cd          = _cache_dir()
        safe        = sym_up.replace('/', '_')
        master_path = os.path.join(cd, f"{safe}_64_v2.png")

        # 1. Disk cache (64 px master, rescaled on demand)
        if os.path.isfile(master_path):
            try:
                img = Image.open(master_path).convert("RGBA")
                out = img.resize((diam, diam), Image.LANCZOS)
                _MEM[key] = out
                return out
            except Exception:
                pass

        # 2. Mana-font TTF (local, no network, good quality)
        img = _draw_mana_font_symbol(sym_up, 64)
        if img:
            try:
                img.save(master_path)
            except Exception:
                pass
            out = img.resize((diam, diam), Image.LANCZOS)
            _MEM[key] = out
            return out

        # 3. Scryfall download (network — best quality if cairosvg available)
        img = _download_symbol(sym_up, 64)
        if img:
            try:
                img.save(master_path)
            except Exception:
                pass
            out = img.resize((diam, diam), Image.LANCZOS)
            _MEM[key] = out
            return out

        # 4. PIL fallback (always succeeds)
        img = _draw_pil_symbol(sym_up, 64)
        try:
            img.save(master_path)
        except Exception:
            pass
        out = img.resize((diam, diam), Image.LANCZOS)
        _MEM[key] = out
        return out
