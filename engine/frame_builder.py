"""
engine/frame_builder.py
-----------------------
Builds complete MTG-style proxy card images from scratch.
No Scryfall template required — frame, art, text and mana symbols
are all rendered programmatically in the M15 style.

Card dimensions: 745×1040 px  (Scryfall "normal" format)
"""

import os
import re
from PIL import Image, ImageDraw, ImageFont

CARD_W, CARD_H = 745, 1040

# ── Layout — absolute pixel coordinates ──────────────────────────────────────

BORDER   = 30   # outer black border (both axes)
CORNER_R = 18   # outer rounded corner radius

# Name bar
NB_Y0, NB_Y1 = 30, 78

# Art box  (between name bar and type bar, matches Scryfall proportions)
AB_PAD   = 4    # inner art-box padding from card edge
AB_Y0    = 85
AB_Y1    = 540

# Type bar
TB_Y0, TB_Y1 = 549, 592

# Rules text box
RB_PAD   = 4
RB_Y0    = 598
RB_Y1    = 882

# P/T oval (creature only)
PT_CX, PT_CY = 656, 916
PT_RX,  PT_RY = 52, 27    # half-axes of the oval

# Artist / collector strip (cosmetic only)
COLL_Y = 940


# ── Mana symbol colors ────────────────────────────────────────────────────────

_MANA = {
    'W': ((252, 244, 200), (40, 30, 5)),
    'U': ((14,  104, 170), (255, 255, 255)),
    'B': ((21,   11,   0), (222, 212, 192)),
    'R': ((211,  72,  15), (255, 255, 255)),
    'G': ((0,   115,  62), (255, 255, 255)),
    'C': ((196, 192, 192), (40,  40,  40)),
    'X': ((140, 140, 140), (255, 255, 255)),
    'T': ((200, 110,  30), (255, 255, 255)),
    'Q': ((200, 110,  30), (255, 255, 255)),   # untap
    'S': ((168, 210, 248), (20,  20,  20)),
    'P': ((170,  30,  30), (255, 255, 255)),
    'E': ((180, 120,  60), (255, 255, 255)),
}

def _mana_col(symbol: str) -> tuple:
    k = symbol.upper()
    if re.fullmatch(r'\d+', k):
        return (196, 192, 192), (40, 40, 40)
    return _MANA.get(k, ((160, 160, 160), (255, 255, 255)))


# ── Frame color palettes (M15-inspired) ───────────────────────────────────────

FRAME_COLORS = {
    'W': dict(bar_top=(208, 194, 140), bar_bot=(254, 248, 218),
              art_edge=(220, 208, 158), rules_bg=(246, 240, 212),
              rules_border=(210, 198, 150), border=(222, 210, 164),
              text=(28, 18, 4)),
    'U': dict(bar_top=(8,   64, 128), bar_bot=(64,  144, 208),
              art_edge=(12,  84, 162), rules_bg=(192, 216, 240),
              rules_border=(10,  78, 150), border=(10,  80, 152),
              text=(6,  28, 58)),
    'B': dict(bar_top=(8,    4,   0), bar_bot=(86,  62,  30),
              art_edge=(20,  12,   4), rules_bg=(154, 138, 108),
              rules_border=(14,   8,   0), border=(14,   8,   0),
              text=(14,  8,  0)),
    'R': dict(bar_top=(160,  38,   4), bar_bot=(244, 128,  52),
              art_edge=(190,  64,  12), rules_bg=(240, 196, 156),
              rules_border=(180,  52,   8), border=(182,  54,   8),
              text=(50, 10,  0)),
    'G': dict(bar_top=(0,   76,  34), bar_bot=(62,  152,  88),
              art_edge=(4,  100,  48), rules_bg=(180, 220, 178),
              rules_border=(0,   92,  42), border=(0,   94,  44),
              text=(0,  28, 10)),
    'M': dict(bar_top=(126,  96,   8), bar_bot=(240, 202,  88),
              art_edge=(160, 128,  18), rules_bg=(244, 226, 162),
              rules_border=(150, 116,  12), border=(152, 118,  12),
              text=(28, 18,  0)),
    'C': dict(bar_top=(108, 108, 116), bar_bot=(206, 206, 212),
              art_edge=(134, 134, 140), rules_bg=(218, 218, 222),
              rules_border=(126, 126, 132), border=(126, 126, 132),
              text=(20, 20, 20)),
    'A': dict(bar_top=(80,   98, 120), bar_bot=(192, 206, 226),
              art_edge=(104, 122, 144), rules_bg=(208, 218, 230),
              rules_border=(96,  114, 134), border=(96,  114, 134),
              text=(20, 20, 20)),
}

# Human-readable labels for the UI dropdown
COLOR_LABELS = {
    'W': 'W — Blanc',
    'U': 'U — Bleu',
    'B': 'B — Noir',
    'R': 'R — Rouge',
    'G': 'G — Vert',
    'M': 'M — Multicolore',
    'C': 'C — Incolore',
    'A': 'A — Artefact',
}

def label_to_code(label: str) -> str:
    for code, lbl in COLOR_LABELS.items():
        if lbl == label or code == label:
            return code
    return label[0].upper() if label else 'C'


# ── Card layout variants ──────────────────────────────────────────────────────

LAYOUT_LABELS = {
    'standard':          'Standard',
    'borderless':        'Borderless (full art)',
    'extended':          'Art étendu',
    'transparent_rules': 'Règles transparentes',
}

def layout_label_to_key(label: str) -> str:
    for key, lbl in LAYOUT_LABELS.items():
        if lbl == label or key == label:
            return key
    return 'standard'


# ── Font helpers ──────────────────────────────────────────────────────────────
#
# MTG font hierarchy (most → least accurate):
#   Card name / type : Beleren Bold  → palatin.ttf (Palatino Linotype) → Georgia → fallback
#   Rules text       : MPlantin      → palati.ttf  (Palatino Linotype) → Georgia → fallback
#   Italic rules     : MPlantin Ital → palatii.ttf → Georgia Italic    → fallback
#
# Palatino Linotype is bundled with Windows and is stylistically close to the
# MTG official fonts (serif, classical). Much better than Arial for proxy cards.

_FONT_CACHE: dict = {}

def _get_font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold, italic)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    if bold and italic:
        cands = [
            r"C:\Windows\Fonts\palatbi.ttf",    # Palatino Linotype Bold Italic
            r"C:\Windows\Fonts\georgiabi.ttf",
            r"C:\Windows\Fonts\arialbi.ttf",
        ]
    elif italic:
        cands = [
            r"C:\Windows\Fonts\palatii.ttf",    # Palatino Linotype Italic
            r"C:\Windows\Fonts\georgiai.ttf",
            r"C:\Windows\Fonts\timesi.ttf",
            r"C:\Windows\Fonts\ariali.ttf",
        ]
    elif bold:
        cands = [
            r"C:\Windows\Fonts\palatinb.ttf",   # Palatino Linotype Bold
            r"C:\Windows\Fonts\georgiab.ttf",
            r"C:\Windows\Fonts\garabd.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
        ]
    else:
        cands = [
            r"C:\Windows\Fonts\palatin.ttf",    # Palatino Linotype (closest to MTG rules text)
            r"C:\Windows\Fonts\georgia.ttf",
            r"C:\Windows\Fonts\gara.ttf",       # Garamond
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
        ]
    cands += [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\tahoma.ttf"]
    for p in cands:
        try:
            f = ImageFont.truetype(p, size)
            _FONT_CACHE[key] = f
            return f
        except Exception:
            continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _get_mtg_font(role: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Return the best available MTG font for the given role.
    Tries Beleren/MPlantin (downloaded), then Palatino/Georgia fallbacks.
    role: 'name' | 'type' | 'rules' | 'italic'
    """
    try:
        from engine.font_manager import get_font_path
        path = get_font_path(role)
        if path:
            key = (path, size)
            if key not in _FONT_CACHE:
                _FONT_CACHE[key] = ImageFont.truetype(path, size)
            return _FONT_CACHE[key]
    except Exception:
        pass
    # Fallback by role
    if role == 'name':
        return _get_font(size, bold=True)
    if role == 'type':
        return _get_font(size, bold=True)
    if role == 'italic':
        return _get_font(size, italic=True)
    return _get_font(size)


def _measure(font, text: str) -> tuple[int, int]:
    try:
        bb = font.getbbox(text)
        return bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        return len(text) * 7, 12


def _line_height(font) -> int:
    try:
        bb = font.getbbox("Ag")
        return bb[3] - bb[1]
    except Exception:
        return 12


def _text_y_centered(font, y_top: int, bar_h: int) -> int:
    """Return the y coordinate that visually centers text in a bar."""
    try:
        bb = font.getbbox("Ag")
        return y_top + (bar_h - (bb[3] - bb[1])) // 2 - bb[1]
    except Exception:
        return y_top + bar_h // 4


def _outlined(draw, pos, text, font, fill=(255, 255, 255),
              outline=(0, 0, 0), ep=1):
    x, y = pos
    for dx in range(-ep, ep + 1):
        for dy in range(-ep, ep + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text(pos, text, fill=fill, font=font)


def _bar_text_colors(pal: dict) -> tuple:
    """Return (fill, outline) for text on the gradient bars."""
    mid = tuple((a + b) // 2 for a, b in zip(pal['bar_top'], pal['bar_bot']))
    bright = sum(mid) // 3
    if bright < 140:
        return (255, 250, 210), (0, 0, 0)
    return (24, 14, 2), (255, 240, 180)


# ── Gradient helpers ──────────────────────────────────────────────────────────

def _grad_v(draw, x0, y0, x1, y1, c_top, c_bot):
    steps = y1 - y0
    if steps <= 0:
        return
    for y in range(y0, y1):
        t = (y - y0) / steps
        r = int(c_top[0] + (c_bot[0] - c_top[0]) * t)
        g = int(c_top[1] + (c_bot[1] - c_top[1]) * t)
        b = int(c_top[2] + (c_bot[2] - c_top[2]) * t)
        draw.line([(x0, y), (x1 - 1, y)], fill=(r, g, b))


# ── Mana symbol — uses symbol_cache for official Scryfall symbols ─────────────

def _paste_mana_sym(img: Image.Image, cx: int, cy: int,
                    symbol: str, radius: int) -> None:
    """Paste an official mana symbol image centered at (cx, cy)."""
    try:
        from engine.symbol_cache import get_symbol
        diam = radius * 2
        sym_img = get_symbol(symbol, diam)
        x = cx - radius
        y = cy - radius
        if sym_img.mode == 'RGBA':
            img.paste(sym_img, (x, y), mask=sym_img)
        else:
            img.paste(sym_img.convert('RGBA'), (x, y))
    except Exception as e:
        print(f"[FrameBuilder] Symbol fallback for {symbol!r}: {e}")
        # Inline fallback: simple colored circle
        draw = ImageDraw.Draw(img)
        bg, fg = _mana_col(symbol)
        r = radius
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=bg, outline=(0, 0, 0), width=max(1, r // 7))
        f = _get_font(max(7, int(r * 1.0)), bold=True)
        sym = symbol.upper()
        sw, sh = _measure(f, sym)
        draw.text((cx - sw // 2, cy - sh // 2), sym, fill=fg, font=f)


def parse_mana_cost(mana_str: str) -> list[str]:
    """Parse '{2}{W}{W}' or '2WW' → ['2', 'W', 'W']."""
    if not mana_str:
        return []
    s = mana_str.strip()
    if '{' in s:
        return re.findall(r'\{([^}]+)\}', s)
    tokens, i = [], 0
    while i < len(s):
        if s[i].isdigit():
            j = i + 1
            while j < len(s) and s[j].isdigit():
                j += 1
            tokens.append(s[i:j])
            i = j
        elif s[i].upper() in 'WUBRGCXTSPQE':
            tokens.append(s[i].upper())
            i += 1
        else:
            i += 1
    return tokens


# ── Rules text parser + renderer ──────────────────────────────────────────────

_SYM_RE = re.compile(r'\{([^}]+)\}')

def _tokenize(text: str) -> list[tuple[str, str]]:
    """Split rules text into ('text'|'symbol', value) tokens."""
    out, last = [], 0
    for m in _SYM_RE.finditer(text):
        if m.start() > last:
            out.append(('text', text[last:m.start()]))
        out.append(('symbol', m.group(1)))
        last = m.end()
    if last < len(text):
        out.append(('text', text[last:]))
    return out


def _word_tokens(tokens: list[tuple]) -> list[tuple[str, str]]:
    """Expand 'text' tokens into individual words + spaces for wrapping."""
    out = []
    for kind, val in tokens:
        if kind == 'symbol':
            out.append(('symbol', val))
        else:
            parts = val.split(' ')
            for i, p in enumerate(parts):
                if p:
                    out.append(('text', p))
                if i < len(parts) - 1:
                    out.append(('space', ' '))
    return out


def _token_width(tok: tuple, font, sym_r: int) -> int:
    kind, val = tok
    if kind == 'symbol':
        return sym_r * 2 + 5
    if kind == 'space':
        return _measure(font, ' ')[0]
    return _measure(font, val)[0]


def _wrap_rules(text: str, font, max_w: int, sym_r: int) -> list[list[tuple]]:
    """Wrap rules text into lines of (kind, value) tuples, respecting max_w."""
    lines = []
    for para in text.split('\n'):
        if not para.strip():
            lines.append([])
            continue
        words = _word_tokens(_tokenize(para))
        cur_line: list[tuple] = []
        cur_w = 0
        for tok in words:
            tw = _token_width(tok, font, sym_r)
            if tok[0] == 'space':
                if cur_line:
                    cur_line.append(tok)
                    cur_w += tw
                continue
            if cur_w + tw > max_w and cur_line:
                while cur_line and cur_line[-1][0] == 'space':
                    cur_line.pop()
                lines.append(cur_line)
                cur_line = [tok]
                cur_w = tw
            else:
                cur_line.append(tok)
                cur_w += tw
        while cur_line and cur_line[-1][0] == 'space':
            cur_line.pop()
        if cur_line:
            lines.append(cur_line)
    return lines


def _render_rules_line_outlined(draw, img: Image.Image, line: list[tuple],
                                 x: int, y: int, font, color: tuple, sym_r: int) -> None:
    """Same as _render_rules_line but with a black outline around text tokens."""
    cx = x
    th = _line_height(font)
    sym_cy = y + th // 2
    for kind, val in line:
        if kind == 'space':
            cx += _measure(font, val)[0]
        elif kind == 'symbol':
            _paste_mana_sym(img, cx + sym_r, sym_cy, val, sym_r)
            cx += sym_r * 2 + 5
        else:
            _outlined(draw, (cx, y), val, font, fill=color, outline=(0, 0, 0), ep=1)
            cx += _measure(font, val)[0]


def _render_rules_line(draw, img: Image.Image, line: list[tuple],
                        x: int, y: int, font, color: tuple, sym_r: int) -> None:
    cx = x
    th = _line_height(font)
    sym_cy = y + th // 2
    for kind, val in line:
        if kind == 'space':
            cx += _measure(font, val)[0]
        elif kind == 'symbol':
            _paste_mana_sym(img, cx + sym_r, sym_cy, val, sym_r)
            cx += sym_r * 2 + 5
        else:
            draw.text((cx, y), val, fill=color, font=font)
            cx += _measure(font, val)[0]


# ── Blank frame construction ──────────────────────────────────────────────────

def _build_frame(color: str, is_creature: bool, layout: str = 'standard') -> Image.Image:
    """
    Draw the blank card frame.
    layout: 'standard' | 'borderless' | 'extended' | 'transparent_rules'
    """
    pal = FRAME_COLORS.get(color.upper(), FRAME_COLORS['C'])

    img = Image.new('RGB', (CARD_W, CARD_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Outer border — BLACK for borderless, frame color otherwise ────────────
    border_fill = (0, 0, 0) if layout == 'borderless' else pal['border']
    draw.rounded_rectangle(
        [0, 0, CARD_W - 1, CARD_H - 1],
        radius=CORNER_R, fill=border_fill
    )
    draw.rounded_rectangle(
        [2, 2, CARD_W - 3, CARD_H - 3],
        radius=CORNER_R - 2, fill=None, outline=(0, 0, 0), width=2
    )
    INN = BORDER - 4

    if layout == 'borderless':
        # Interior: solid black — artwork will cover it entirely
        draw.rounded_rectangle(
            [INN, INN, CARD_W - INN - 1, CARD_H - INN - 1],
            radius=6, fill=(8, 6, 4)
        )
        # Thin bottom strip for collector text readability
        draw.line([(BORDER, COLL_Y - 4), (CARD_W - BORDER, COLL_Y - 4)],
                  fill=(80, 60, 40), width=1)

    elif layout == 'extended':
        # Background — art will replace the entire top half
        draw.rounded_rectangle(
            [INN, INN, CARD_W - INN - 1, CARD_H - INN - 1],
            radius=6, fill=pal['rules_bg']
        )
        # Art area placeholder (art will be pasted from BORDER to TB_Y0)
        draw.rectangle([BORDER, BORDER, CARD_W - BORDER, TB_Y0],
                       fill=(200, 190, 170))
        # Type bar
        _grad_v(draw, BORDER, TB_Y0, CARD_W - BORDER, TB_Y1,
                pal['bar_top'], pal['bar_bot'])
        draw.line([(BORDER, TB_Y0), (CARD_W - BORDER, TB_Y0)],
                  fill=pal['art_edge'], width=2)
        draw.line([(BORDER, TB_Y1), (CARD_W - BORDER, TB_Y1)],
                  fill=pal['art_edge'], width=2)
        # Rules box
        rb_x0, rb_x1 = BORDER + RB_PAD, CARD_W - BORDER - RB_PAD
        draw.rectangle([rb_x0, RB_Y0, rb_x1, RB_Y1],
                       fill=pal['rules_bg'], outline=pal['rules_border'], width=2)

    else:
        # standard or transparent_rules — full traditional frame
        draw.rounded_rectangle(
            [INN, INN, CARD_W - INN - 1, CARD_H - INN - 1],
            radius=6, fill=pal['rules_bg']
        )
        # Name bar
        _grad_v(draw, BORDER, NB_Y0, CARD_W - BORDER, NB_Y1,
                pal['bar_top'], pal['bar_bot'])
        draw.line([(BORDER, NB_Y1), (CARD_W - BORDER, NB_Y1)],
                  fill=pal['art_edge'], width=2)
        # Art box
        art_x0 = BORDER + AB_PAD
        art_x1 = CARD_W - BORDER - AB_PAD
        draw.rectangle([art_x0, AB_Y0, art_x1, AB_Y1], fill=(240, 234, 218))
        draw.rectangle([art_x0, AB_Y0, art_x1, AB_Y1],
                       fill=None, outline=pal['art_edge'], width=2)
        # Type bar
        _grad_v(draw, BORDER, TB_Y0, CARD_W - BORDER, TB_Y1,
                pal['bar_top'], pal['bar_bot'])
        draw.line([(BORDER, TB_Y0), (CARD_W - BORDER, TB_Y0)],
                  fill=pal['art_edge'], width=2)
        draw.line([(BORDER, TB_Y1), (CARD_W - BORDER, TB_Y1)],
                  fill=pal['art_edge'], width=2)
        # Rules box
        rb_x0, rb_x1 = BORDER + RB_PAD, CARD_W - BORDER - RB_PAD
        if layout == 'transparent_rules':
            draw.rectangle([rb_x0, RB_Y0, rb_x1, RB_Y1],
                           fill=None, outline=pal['rules_border'], width=1)
        else:
            draw.rectangle([rb_x0, RB_Y0, rb_x1, RB_Y1],
                           fill=pal['rules_bg'], outline=pal['rules_border'], width=2)

    # ── OtterForge mark — collector strip (all layouts) ───────────────────────
    coll_f = _get_font(10)
    coll_txt = "OtterForge Proxy — Not for sale"
    cw, _ = _measure(coll_f, coll_txt)
    draw.text(((CARD_W - cw) // 2, COLL_Y),
              coll_txt, fill=pal['art_edge'], font=coll_f)

    # OF mark in type bar (only layouts that have a type bar)
    if layout in ('standard', 'transparent_rules', 'extended'):
        mark_f = _get_font(11, bold=True)
        mark = "OF"
        mw, _ = _measure(mark_f, mark)
        fill, _ = _bar_text_colors(pal)
        draw.text((CARD_W - BORDER - mw - 6,
                   TB_Y0 + (TB_Y1 - TB_Y0 - _line_height(mark_f)) // 2),
                  mark, fill=fill, font=mark_f)

    return img


# ── Element renderers ─────────────────────────────────────────────────────────

def _paste_artwork(img: Image.Image, art_path: str, layout: str = 'standard') -> None:
    if not art_path or not os.path.isfile(art_path):
        return
    try:
        art = Image.open(art_path).convert('RGB')

        if layout == 'borderless':
            # Art fills the entire interior — edge to edge inside border
            INN = BORDER - 3
            bx0, by0 = INN, INN
            bx1, by1 = CARD_W - INN, CARD_H - INN
        elif layout == 'extended':
            # Art covers the entire top half of the card (inner border → type bar)
            # Name bar is overlaid on top of the art after pasting
            bx0 = BORDER
            bx1 = CARD_W - BORDER
            by0 = BORDER        # starts right at the inner top edge
            by1 = TB_Y0         # ends at type bar top
        else:
            # standard or transparent_rules — normal art box
            bx0 = BORDER + AB_PAD + 2
            bx1 = CARD_W - BORDER - AB_PAD - 2
            by0 = AB_Y0 + 2
            by1 = AB_Y1 - 2

        bw, bh = bx1 - bx0, by1 - by0
        if bw <= 0 or bh <= 0:
            return
        scale = max(bw / art.width, bh / art.height)
        nw = max(1, round(art.width * scale))
        nh = max(1, round(art.height * scale))
        art = art.resize((nw, nh), Image.LANCZOS)
        cx = (nw - bw) // 2
        cy = (nh - bh) // 2
        art = art.crop((cx, cy, cx + bw, cy + bh))
        img.paste(art, (bx0, by0))

        # Borderless: darken name+type bar areas so text stays readable over art
        if layout == 'borderless':
            _darken_text_bars(img)

    except Exception as e:
        print(f"[FrameBuilder] Artwork error: {e}")


def _darken_text_bars(img: Image.Image) -> None:
    """Darken the name-bar and type-bar strips for borderless layout readability."""
    # Build a semi-transparent dark overlay using numpy if available, else row-by-row
    try:
        import numpy as np
        arr = np.array(img, dtype=np.float32)
        # Name bar: gradient darken 75%→45% (top→bottom)
        for y in range(NB_Y0, NB_Y1):
            t = (y - NB_Y0) / max(1, NB_Y1 - NB_Y0 - 1)
            factor = 0.25 + 0.30 * t   # keep 25%→55% of original brightness
            arr[y, BORDER:CARD_W - BORDER] *= factor
        # Type bar: darken to ~30%
        arr[TB_Y0:TB_Y1, BORDER:CARD_W - BORDER] *= 0.28
        img.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    except ImportError:
        # Numpy not available: use Pillow ImageEnhance approach per strip
        from PIL import ImageEnhance
        def _darken_strip(y0, y1, factor):
            strip = img.crop((BORDER, y0, CARD_W - BORDER, y1))
            strip = ImageEnhance.Brightness(strip).enhance(factor)
            img.paste(strip, (BORDER, y0))
        _darken_strip(NB_Y0, NB_Y1, 0.35)
        _darken_strip(TB_Y0, TB_Y1, 0.28)


def _render_name(draw: ImageDraw.ImageDraw, name: str, pal: dict) -> None:
    if not name:
        return
    bar_h = NB_Y1 - NB_Y0
    mana_reserve = 140      # pixels reserved on the right for mana cost
    avail_w = CARD_W - BORDER * 2 - mana_reserve - 8
    font_sz = max(14, int(bar_h * 0.62))
    font = _get_mtg_font('name', font_sz)
    # Shrink to fit
    while font_sz > 10 and _measure(font, name)[0] > avail_w:
        font_sz -= 1
        font = _get_mtg_font('name', font_sz)
    fill, outline = _bar_text_colors(pal)
    ty = _text_y_centered(font, NB_Y0, bar_h)
    _outlined(draw, (BORDER + 6, ty), name, font, fill=fill, outline=outline, ep=1)


def _render_mana_cost(img: Image.Image, mana_cost: str) -> None:
    tokens = parse_mana_cost(mana_cost)
    if not tokens:
        return
    bar_h = NB_Y1 - NB_Y0
    R   = max(10, int(bar_h * 0.38))
    GAP = 3
    total_w = len(tokens) * (R * 2 + GAP) - GAP
    x = CARD_W - BORDER - 6 - total_w
    cy = NB_Y0 + bar_h // 2
    for sym in tokens:
        _paste_mana_sym(img, x + R, cy, sym, R)
        x += R * 2 + GAP


def _render_type_line(draw: ImageDraw.ImageDraw, type_line: str, pal: dict) -> None:
    if not type_line:
        return
    bar_h = TB_Y1 - TB_Y0
    of_reserve = 30    # space for the OF mark
    avail_w = CARD_W - BORDER * 2 - of_reserve - 8
    font_sz = max(11, int(bar_h * 0.52))
    font = _get_mtg_font('type', font_sz)
    while font_sz > 9 and _measure(font, type_line)[0] > avail_w:
        font_sz -= 1
        font = _get_mtg_font('type', font_sz)
    fill, outline = _bar_text_colors(pal)
    ty = _text_y_centered(font, TB_Y0, bar_h)
    _outlined(draw, (BORDER + 6, ty), type_line, font, fill=fill, outline=outline, ep=1)


def _render_rules_text(draw: ImageDraw.ImageDraw, img: Image.Image,
                        rules_text: str, pal: dict,
                        strong_outline: bool = False) -> None:
    if not rules_text or not rules_text.strip():
        return
    PADDING = 12
    x0 = BORDER + RB_PAD + PADDING
    x1 = CARD_W - BORDER - RB_PAD - PADDING
    y0 = RB_Y0 + PADDING
    y1 = RB_Y1 - PADDING
    max_w = x1 - x0
    max_h = y1 - y0
    color = pal['text']

    # Auto-fit font size using MTG rules text font (MPlantin)
    font_sz = 19
    sym_r   = 8
    lines   = []
    while font_sz >= 9:
        font  = _get_mtg_font('rules', font_sz)
        sym_r = max(6, int(font_sz * 0.52))
        lines = _wrap_rules(rules_text, font, max_w, sym_r)
        lh    = _line_height(font) + 5
        if len(lines) * lh <= max_h:
            break
        font_sz -= 1

    # On non-standard layouts the rules box may have no background — use white outline
    color = (255, 255, 255) if strong_outline else pal['text']

    lh = _line_height(font) + 5
    y  = y0
    for line in lines:
        if y + lh > y1:
            break
        if line:
            if strong_outline:
                # Draw outline manually for each text token before rendering symbols
                _render_rules_line_outlined(draw, img, line, x0, y, font, color, sym_r)
            else:
                _render_rules_line(draw, img, line, x0, y, font, color, sym_r)
        y += lh


def _render_pt(draw: ImageDraw.ImageDraw, img: Image.Image,
               pt: str, pal: dict) -> None:
    """Draw the P/T oval (background + text) — called for ALL layouts."""
    if not pt:
        return

    # ── Oval background (MTG style: gradient fill + thick border) ────────────
    # Slightly larger and lower than before to match real MTG position
    CX, CY = PT_CX, PT_CY + 6    # nudge down to overlap collector strip edge
    RX, RY = PT_RX + 4, PT_RY + 4

    # Multi-layer oval for depth effect
    # 1. Shadow (1px shifted, dark)
    draw.ellipse([CX - RX + 2, CY - RY + 3, CX + RX + 2, CY + RY + 3],
                 fill=(0, 0, 0))
    # 2. Outer border ring (frame color, 3px thick)
    draw.ellipse([CX - RX, CY - RY, CX + RX, CY + RY],
                 fill=pal['art_edge'], outline=(0, 0, 0), width=1)
    # 3. Inner fill (gradient via two ellipses — lighter at top)
    draw.ellipse([CX - RX + 3, CY - RY + 3, CX + RX - 3, CY + RY - 3],
                 fill=pal['bar_bot'])
    # 4. Highlight — subtle lighter top-half tint
    hi = tuple(min(255, c + 40) for c in pal['bar_bot'])
    draw.ellipse([CX - RX + 5, CY - RY + 5, CX + RX - 5, CY - 2],
                 fill=hi)

    # ── P/T text ──────────────────────────────────────────────────────────────
    font_sz = 26
    font = _get_font(font_sz, bold=True)
    while font_sz > 13 and _measure(font, pt)[0] > RX * 1.55:
        font_sz -= 1
        font = _get_font(font_sz, bold=True)
    fill, _ = _bar_text_colors(pal)
    try:
        bb = font.getbbox(pt)
        tx = CX - (bb[2] - bb[0]) // 2 - bb[0]
        ty = CY - (bb[3] - bb[1]) // 2 - bb[1]
    except Exception:
        w, h = _measure(font, pt)
        tx, ty = CX - w // 2, CY - h // 2
    _outlined(draw, (tx, ty), pt, font, fill=fill, outline=(0, 0, 0), ep=2)


# ── Public API ────────────────────────────────────────────────────────────────

def render_card(
    art_path: str,
    name: str,
    mana_cost: str,
    type_line: str,
    rules_text: str,
    pt: str,
    color: str,
    output_path: str,
    layout: str = 'standard',
) -> str:
    """
    Compose a full custom MTG-style proxy card and save it to output_path.

    color:  one of 'W', 'U', 'B', 'R', 'G', 'M', 'C', 'A'
            (or a COLOR_LABELS string like 'W — Blanc')
    layout: 'standard' | 'borderless' | 'extended' | 'transparent_rules'
            (or a LAYOUT_LABELS string like 'Borderless (full art)')
    Returns output_path on success.
    """
    color  = label_to_code(color)
    layout = layout_label_to_key(layout)
    is_creature = bool(pt and pt.strip())
    pal = FRAME_COLORS.get(color, FRAME_COLORS['C'])

    img = _build_frame(color, is_creature, layout)
    draw = ImageDraw.Draw(img)

    # Artwork first (borderless needs re-draw of bars after paste)
    _paste_artwork(img, art_path, layout)

    # Re-create draw after artwork paste (artwork modifies the pixel buffer)
    draw = ImageDraw.Draw(img)

    if layout == 'borderless':
        # Re-draw name bar + type bar as dark overlay on art
        _grad_v(draw, BORDER, NB_Y0, CARD_W - BORDER, NB_Y1,
                (0, 0, 0), (24, 16, 8))
        _grad_v(draw, BORDER, TB_Y0, CARD_W - BORDER, TB_Y1,
                (0, 0, 0), (24, 16, 8))
        draw.line([(BORDER, NB_Y1), (CARD_W - BORDER, NB_Y1)],
                  fill=pal['art_edge'], width=1)

    elif layout == 'extended':
        # Art now covers BORDER→TB_Y0 — redraw name bar gradient on top of the art
        _grad_v(draw, BORDER, NB_Y0, CARD_W - BORDER, NB_Y1,
                pal['bar_top'], pal['bar_bot'])
        draw.line([(BORDER, NB_Y1), (CARD_W - BORDER, NB_Y1)],
                  fill=pal['art_edge'], width=2)

    _render_name(draw, name, pal)
    _render_mana_cost(img, mana_cost)
    _render_type_line(draw, type_line, pal)

    # For borderless/extended/transparent_rules: text uses strong outline (no bg)
    _render_rules_text(draw, img, rules_text, pal, strong_outline=(layout != 'standard'))

    if is_creature:
        _render_pt(draw, img, pt, pal)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, 'PNG', compress_level=6)
    print(f"[FrameBuilder] Rendered: {os.path.basename(output_path)}")
    return output_path
