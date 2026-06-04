"""
engine/symbol_cache.py
-----------------------
Downloads official MTG mana symbol PNGs from Scryfall and caches them locally.
Falls back to PIL-drawn symbols if cairosvg is not installed.

Install cairosvg for best quality: pip install cairosvg
"""

import os
import io
import math

from PIL import Image, ImageDraw

# ── Cache dir — uses config.CACHE_DIR (PyInstaller-aware, next to the EXE) ───

def _cache_dir() -> str:
    try:
        from config import CACHE_DIR
        d = os.path.join(CACHE_DIR, "symbols")
    except Exception:
        d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "symbols")
    os.makedirs(d, exist_ok=True)
    return d


# ── In-memory image cache ─────────────────────────────────────────────────────

_MEM: dict = {}   # (upper_symbol, diam) → PIL RGBA Image


# ── Symbol shape colors (official Scryfall palette) ──────────────────────────

_BG = {
    'W': (249, 250, 244),   # near-white
    'U': (14,  104, 171),   # blue
    'B': (21,  11,   0),    # black
    'R': (211, 73,  16),    # red
    'G': (0,   115, 62),    # green
    'C': (202, 194, 190),   # colorless crystal (gray)
    'X': (149, 149, 149),   # gray
    'T': (206, 110, 34),    # orange (tap)
    'Q': (206, 110, 34),    # orange (untap)
    'S': (168, 210, 248),   # snow (light blue)
    'P': (167, 30,  42),    # phyrexian (dark red)
    'E': (180, 120, 60),    # energy (amber)
}

_FG = {
    'W': (40,  30,   5),
    'U': (255, 255, 255),
    'B': (220, 210, 190),
    'R': (255, 255, 255),
    'G': (255, 255, 255),
    'C': (40,  40,  40),
    'X': (255, 255, 255),
    'T': (255, 255, 255),
    'Q': (255, 255, 255),
    'S': (20,  20,  20),
    'P': (255, 255, 255),
    'E': (255, 255, 255),
}

# Generic mana (numbers): medium-gray circle, very dark text — matches real MTG pips
_NUM_BG = (165, 162, 160)   # MTG generic mana gray
_NUM_FG = (22,  18,  14)    # near-black, same as card text


def _sym_colors(symbol: str) -> tuple[tuple, tuple]:
    import re as _re
    k = symbol.upper()
    if _re.fullmatch(r'\d+', k):
        return _NUM_BG, _NUM_FG
    return _BG.get(k, (149, 149, 149)), _FG.get(k, (255, 255, 255))


# ── Scryfall SVG download + cairosvg conversion ───────────────────────────────

_SCRYFALL_SVG = "https://svgs.scryfall.io/card-symbols/{}.svg"


def _svg_to_pil(svg_bytes: bytes, diam: int) -> "Image.Image | None":
    """Convert SVG bytes → RGBA PIL Image.
    Tries cairosvg first, then svglib+reportlab, returns None if both unavailable.
    """
    # ── cairosvg ──────────────────────────────────────────────────────────────
    try:
        import cairosvg
        png_bytes = cairosvg.svg2png(
            bytestring=svg_bytes, output_width=diam, output_height=diam
        )
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except ImportError:
        pass
    except Exception:
        pass

    # ── svglib + reportlab ────────────────────────────────────────────────────
    try:
        import tempfile, os as _os
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            f.write(svg_bytes)
            tmp = f.name
        try:
            drawing = svg2rlg(tmp)
            if drawing:
                # Scale to diam×diam
                sx = diam / drawing.width  if drawing.width  else 1
                sy = diam / drawing.height if drawing.height else 1
                drawing.width  = diam
                drawing.height = diam
                drawing.transform = (sx, 0, 0, sy, 0, 0)
                png_bytes = renderPM.drawToString(drawing, fmt="PNG",
                                                  dpi=72, bg=0xFFFFFF00)
                return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        finally:
            try:
                _os.unlink(tmp)
            except Exception:
                pass
    except ImportError:
        pass
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
    """Extract (bg_color, fg_color) from a Scryfall mana symbol SVG using stdlib XML."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(svg_bytes.decode('utf-8', errors='replace'))
        # Strip namespace for easier search
        def _strip_ns(tag):
            return tag.split('}')[-1] if '}' in tag else tag

        bg, fg = None, None
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
            # Determine text color based on bg brightness
            bright = sum(bg) // 3
            fg = (20, 15, 5) if bright > 150 else (245, 240, 220)
        return bg, fg
    except Exception:
        return None


def _download_symbol(symbol: str, diam: int) -> "Image.Image | None":
    """Download SVG from Scryfall, try full render first, then color-accurate PIL fallback."""
    try:
        import requests as _req
        url = _SCRYFALL_SVG.format(symbol.upper())
        r = _req.get(url, timeout=10, headers={"User-Agent": "OtterForge/1.0"})
        if not r.ok:
            return None
        svg_bytes = r.content

        # 1. Try full SVG → PNG render (cairosvg / svglib)
        img = _svg_to_pil(svg_bytes, diam)
        if img:
            return img

        # 2. Color-accurate PIL fallback: extract exact Scryfall colors from SVG XML
        colors = _extract_svg_colors(svg_bytes)
        if colors:
            bg, fg = colors
            # Temporarily override the symbol's palette entry so _draw_pil_symbol
            # uses the EXACT official Scryfall colors
            k = symbol.upper()
            _BG[k] = bg
            _FG[k] = fg
            result = _draw_pil_symbol(k, diam)
            return result

    except Exception:
        pass
    return None


# ── PIL fallback drawing (supersampled for smooth circles) ───────────────────

def _draw_pil_symbol(symbol: str, diam: int) -> "Image.Image":
    """Draw a mana symbol entirely in PIL (supersampled 4×, then downscaled)."""
    import re
    OS = 4          # oversample factor
    big = diam * OS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx = cy = big // 2
    r = big // 2 - OS   # leave 1px logical margin

    sym = symbol.upper()
    bg, fg = _sym_colors(sym)

    # ── Background circle ─────────────────────────────────────────────────────
    bw = max(2, big // 18)   # border width
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=bg, outline=(0, 0, 0, 255), width=bw)

    # ── Inner shape ───────────────────────────────────────────────────────────
    if sym == 'W':
        _sun(draw, cx, cy, int(r * 0.52), fg)
    elif sym == 'U':
        _teardrop(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'B':
        _skull(draw, cx, cy, int(r * 0.48), fg)
    elif sym == 'R':
        _flame(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'G':
        _leaf(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'T':
        _tap_arrow(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'S':
        _snowflake(draw, cx, cy, int(r * 0.50), fg)
    elif sym == 'C':
        _diamond(draw, cx, cy, int(r * 0.48), fg)
    elif sym == 'P':
        _phi(draw, cx, cy, int(r * 0.50), fg, big)
    else:
        # Number or X — draw text
        _center_text(draw, cx, cy, sym, int(r * 0.88), fg, big)

    return img.resize((diam, diam), Image.LANCZOS)


# ── Shape primitives ──────────────────────────────────────────────────────────

def _sun(draw, cx, cy, r, color):
    """5-pointed star (white mana sun)."""
    pts = []
    for i in range(10):
        ang = math.pi * i / 5 - math.pi / 2
        rad = r if i % 2 == 0 else int(r * 0.42)
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def _teardrop(draw, cx, cy, r, color):
    """Teardrop (blue mana water)."""
    n = 24
    pts = [(cx + r * math.sin(math.pi * i / (n - 1)) * 0.85,
            cy - r * 0.65 + r * 0.65 * (1 - math.cos(math.pi * i / (n - 1))))
           for i in range(n)]
    pts.append((cx, cy + r))
    draw.polygon(pts, fill=color)


def _skull(draw, cx, cy, r, color):
    """Skull-inspired shape (black mana — diamond/death mark)."""
    # Use a downward-pointing diamond (death mark approximation)
    pts = [(cx,        cy - r),
           (cx + r,    cy),
           (cx,        cy + int(r * 0.55)),
           (cx - r,    cy)]
    draw.polygon(pts, fill=color)
    # Small notch at bottom to hint jaw
    draw.rectangle([cx - int(r * 0.35), cy + int(r * 0.40),
                    cx + int(r * 0.35), cy + int(r * 0.58)],
                   fill=color)


def _flame(draw, cx, cy, r, color):
    """Flame (red mana)."""
    pts = [
        (cx,            cy - r),
        (cx + int(r * 0.55), cy - int(r * 0.20)),
        (cx + int(r * 0.35), cy + int(r * 0.10)),
        (cx + int(r * 0.70), cy + int(r * 0.55)),
        (cx,            cy + r),
        (cx - int(r * 0.70), cy + int(r * 0.55)),
        (cx - int(r * 0.35), cy + int(r * 0.10)),
        (cx - int(r * 0.55), cy - int(r * 0.20)),
    ]
    draw.polygon(pts, fill=color)


def _leaf(draw, cx, cy, r, color):
    """Simple leaf (green mana)."""
    # Pointed oval rotated ~15°
    draw.ellipse([cx - int(r * 0.38), cy - r, cx + int(r * 0.38), cy + r], fill=color)
    # Tip accent
    draw.polygon([(cx, cy - r), (cx + int(r * 0.18), cy - int(r * 0.55)),
                  (cx - int(r * 0.18), cy - int(r * 0.55))], fill=color)


def _tap_arrow(draw, cx, cy, r, color):
    """Curved tap arrow (simplified as a rotated chevron)."""
    # Draw a clockwise arrow: thick arc not easily done in PIL,
    # so draw a bent-polygon arrow
    hw = max(1, int(r * 0.28))
    pts = [
        (cx + int(r * 0.10), cy - r),
        (cx + r,             cy + int(r * 0.10)),
        (cx + int(r * 0.55), cy + int(r * 0.55)),
        (cx + int(r * 0.30), cy + int(r * 0.25)),
        (cx + int(r * 0.30), cy + r),
        (cx - int(r * 0.30), cy + r),
        (cx - int(r * 0.30), cy + int(r * 0.25)),
        (cx - int(r * 0.55), cy + int(r * 0.55)),
        (cx - r,             cy + int(r * 0.10)),
        (cx - int(r * 0.10), cy - r),
    ]
    draw.polygon(pts, fill=color)


def _snowflake(draw, cx, cy, r, color):
    """6-spoke snowflake (snow mana)."""
    for i in range(6):
        ang = math.pi * i / 3
        x1, y1 = cx + int(r * math.cos(ang)), cy + int(r * math.sin(ang))
        lw = max(1, r // 4)
        draw.line([(cx, cy), (x1, y1)], fill=color, width=lw)


def _diamond(draw, cx, cy, r, color):
    """Diamond (colorless crystal mana)."""
    draw.polygon([(cx, cy - r), (cx + int(r * 0.72), cy),
                  (cx, cy + r), (cx - int(r * 0.72), cy)], fill=color)


def _phi(draw, cx, cy, r, color):
    """Phi-like mark (Phyrexian mana)."""
    # Circle with vertical bar
    lw = max(1, r // 3)
    draw.ellipse([cx - int(r * 0.7), cy - int(r * 0.7),
                  cx + int(r * 0.7), cy + int(r * 0.7)],
                 fill=None, outline=color, width=lw)
    draw.line([(cx, cy - r), (cx, cy + r)], fill=color, width=lw)


def _center_text(draw, cx, cy, text: str, r: int, color: tuple, big: int) -> None:
    """Draw centered text in the symbol circle — sized to fit within the pip."""
    from PIL import ImageFont
    # Shrink font until the text fits inside r*1.5 width
    font_sz = max(8, int(r * 1.10))   # larger initial size — auto-shrinks if needed
    cands = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
             r"C:\Windows\Fonts\segoeui.ttf"]
    font = ImageFont.load_default()
    for p in cands:
        try:
            font = ImageFont.truetype(p, font_sz)
            break
        except Exception:
            continue
    # Auto-shrink for multi-character strings (10, 11, 12…)
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
                font = ImageFont.truetype(p, font_sz)
                break
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

import re as _re_mod


def get_symbol(symbol: str, diam: int = 36) -> "Image.Image":
    """
    Return a PIL RGBA image of the given mana symbol at diam×diam pixels.
    Downloads from Scryfall (requires cairosvg) or falls back to PIL drawing.
    Results are cached in memory and on disk.

    symbol: 'W', 'U', 'B', 'R', 'G', 'C', 'X', 'T', '2', '10', etc.
    """
    sym_up = symbol.upper()
    key = (sym_up, diam)
    if key in _MEM:
        return _MEM[key]

    cd = _cache_dir()
    safe = sym_up.replace('/', '_')
    png_path = os.path.join(cd, f"{safe}.png")

    # 1. Try disk cache (at 64px master, then resize)
    master_path = os.path.join(cd, f"{safe}_64.png")
    if os.path.isfile(master_path):
        try:
            img = Image.open(master_path).convert("RGBA")
            img = img.resize((diam, diam), Image.LANCZOS)
            _MEM[key] = img
            return img
        except Exception:
            pass

    # 2. Try Scryfall download → cairosvg
    img = _download_symbol(sym_up, 64)
    if img:
        try:
            img.save(master_path)
        except Exception:
            pass
        out = img.resize((diam, diam), Image.LANCZOS)
        _MEM[key] = out
        return out

    # 3. PIL fallback
    img = _draw_pil_symbol(sym_up, 64)
    try:
        img.save(master_path)
    except Exception:
        pass
    out = img.resize((diam, diam), Image.LANCZOS)
    _MEM[key] = out
    return out
