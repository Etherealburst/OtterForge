"""
engine/card_creator_engine.py — CardCreator: rendu de cartes MTG custom
Utilise les assets communautaires libres: cardconjurer (frames), mana SVGs, polices MTG.

Phase 1: frame + artwork + nom
Phase 2: type line, oracle text (inline mana), flavor, P/T, mana cost, collector strip
"""

import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from engine.file_utils import safe_save_png


# ── Asset paths ───────────────────────────────────────────────────────────────

def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

def _assets_dir() -> str:
    return os.path.join(_base_dir(), "assets")

def _fonts_dir() -> str:
    return os.path.join(_assets_dir(), "fonts")

def _frames_dir() -> str:
    return os.path.join(_assets_dir(), "frames", "img", "frames")


# ── Canvas dimensions (300 DPI, 63×88 mm poker card) ─────────────────────────

CARD_W = 744
CARD_H = 1040

# Art window: transparent region in the frame PNG (confirmed by pixel analysis)
ART_BOX = (57, 118, 687, 577)

# Text zones: (x0, y0, x1, y1)
NAME_BOX   = (64,  52, 435, 104)   # card name text (measured from frame PNG)
MANA_X1    = 686                    # right edge for right-aligned mana cost
MANA_Y_CTR = 79                     # vertical center of name bar (measured: interior y=51..107)
TYPE_BOX   = (62, 584, 645, 634)   # type line
TEXT_BOX   = (68, 660, 676, 892)   # oracle + flavor text
COLL_Y     = 958                    # collector strip baseline
ARTIST_X   = 62
SET_X1     = 684


# ── Enums ─────────────────────────────────────────────────────────────────────

class CardColor(Enum):
    WHITE      = "W"
    BLUE       = "U"
    BLACK      = "B"
    RED        = "R"
    GREEN      = "G"
    MULTICOLOR = "M"
    COLORLESS  = "C"
    ARTIFACT   = "A"
    LAND       = "L"


class CardType(Enum):
    CREATURE     = "Creature"
    INSTANT      = "Instant"
    SORCERY      = "Sorcery"
    ENCHANTMENT  = "Enchantment"
    ARTIFACT     = "Artifact"
    PLANESWALKER = "Planeswalker"
    LAND         = "Land"
    TOKEN        = "Token"
    SAGA         = "Saga"


class FrameStyle(Enum):
    M15        = "m15"        # Modern (2015+)    — m15/regular/m15Frame{X}.png
    EXTENDED   = "extended"   # Extended Art M15  — m15/new/extended/{x}.png
    BORDERLESS = "borderless" # Borderless M15    — m15/borderless/m15GenericShowcaseFrame{X}.png
    FULLART    = "fullart"    # Full Art M15      — m15/new/fullart/{x}.png
    EIGHTH     = "8th"        # 8th Edition       — 8th/{x}.png
    OLD        = "old"        # Pre-2003          — old/floating/{x}.png
    TOKEN      = "token"      # Token             — token/m15/regular/{x}.png


class Rarity(Enum):
    COMMON   = "C"
    UNCOMMON = "U"
    RARE     = "R"
    MYTHIC   = "M"


# Rarity indicator colors (for the set symbol dot / badge)
_RARITY_COLOR = {
    Rarity.COMMON:   (0,   0,   0),
    Rarity.UNCOMMON: (140, 150, 160),
    Rarity.RARE:     (200, 165,  30),
    Rarity.MYTHIC:   (210,  80,  30),
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class CardData:
    # Identity
    name: str = "Card Name"
    mana_cost: str = ""                # ex: "{2}{W}{U}"

    # Type
    card_type: CardType = CardType.CREATURE
    supertype: str = ""                # "Legendary", "Basic", "Snow"
    subtype: str = ""                  # "Human Warrior", "Forest"

    # Color
    color: CardColor = CardColor.WHITE

    # Frame
    frame_style: FrameStyle = FrameStyle.M15

    # Rarity
    rarity: Rarity = Rarity.COMMON

    # Text
    oracle_text: str = ""
    flavor_text: str = ""

    # Creature stats (empty = non-creature)
    power: str = ""
    toughness: str = ""

    # Planeswalker loyalty (empty = non-planeswalker)
    loyalty: str = ""

    # Artwork
    art_path: Optional[str] = None     # Absolute path to artwork image file

    # Collector metadata
    artist: str = "Unknown Artist"
    set_code: str = "OTF"
    collector_number: str = "001"
    show_number: bool = False       # render number at bottom-left below OtterForge Proxy

    # Typography — text colors
    name_color: tuple = (0, 0, 0)       # RGB — name text
    type_color: tuple = (0, 0, 0)       # RGB — type line text
    text_color: tuple = (0, 0, 0)       # RGB — oracle / flavor text
    pt_color:   tuple = (0, 0, 0)       # RGB — P/T text

    # Typography — font sizes
    name_size:       int = 28           # name bar font size
    type_size:       int = 22           # type line font size
    min_oracle_size: int = 9            # oracle starting size (auto-shrinks to 6 if overflow)
    pt_size:         int = 26           # P/T font size

    # Oracle text formatting
    oracle_bold:      bool = False      # faux bold via stroke
    oracle_italic:    bool = False      # use italic font variant
    oracle_underline: bool = False      # underline each text line
    oracle_highlight: bool = False      # semi-transparent yellow highlight

    # Name bar formatting
    name_bold:        bool = False
    name_italic:      bool = False
    name_underline:   bool = False
    name_highlight:   bool = False

    # Type line formatting
    type_bold:        bool = False
    type_italic:      bool = False
    type_underline:   bool = False
    type_highlight:   bool = False

    # P/T box formatting
    pt_bold:          bool = False
    pt_italic:        bool = False
    pt_underline:     bool = False
    pt_highlight:     bool = False


# ── Mana token parser ─────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r'\{([^}]+)\}|([^{]+)')

def _parse_tokens(text: str) -> list[tuple[str, str]]:
    """Split text into ('sym', 'W') and ('txt', 'some text') tokens."""
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) is not None:
            tokens.append(("sym", m.group(1).upper()))
        else:
            tokens.append(("txt", m.group(2)))
    return tokens


def _normalize_mana_sym(sym: str) -> str:
    """Map a mana symbol code to the key used by symbol_cache.get_symbol()."""
    return sym.upper()


_BARE_MANA_RE = re.compile(r'(\d+|[WUBRGCXTSQP])', re.IGNORECASE)

def _normalize_mana_cost(mana: str) -> str:
    """
    Normalize mana cost to {}-brace format.
    Handles both '{2}{W}{U}' (already correct) and bare '2WU'.
    """
    mana = mana.strip()
    if not mana:
        return mana
    if '{' in mana:
        return mana
    # Bare notation: split digits and letters into individual tokens
    tokens = []
    buf = ""
    for ch in mana:
        if ch.isdigit():
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            if ch.upper() in "WUBRGCXTSQP/":
                tokens.append(ch.upper())
    if buf:
        tokens.append(buf)
    return "".join(f"{{{t}}}" for t in tokens)


# ── Engine ────────────────────────────────────────────────────────────────────

class CardCreatorEngine:
    """
    Renders a CardData into a PIL Image using cardconjurer frame assets.
    Layer order: frame → artwork → name+mana → type line → oracle → flavor → P/T → collector.
    """

    # M15 uses uppercase suffix: m15FrameW.png, m15FrameU.png, etc.
    _M15_COLOR = {
        "W": "W", "U": "U", "B": "B", "R": "R", "G": "G",
        "M": "M", "A": "A", "L": "L", "C": "A",
    }
    _SIMPLE_COLOR = {
        "W": "w", "U": "u", "B": "b", "R": "r", "G": "g",
        "M": "m", "A": "a", "L": "l", "C": "c",
    }
    _FALLBACK_RGB = {
        "W": (248, 241, 216), "U": (14, 100, 174),  "B": (21,  11,   0),
        "R": (211,  32,  42), "G": (  0, 115,  62),  "M": (202, 151,  28),
        "A": (155, 160, 165), "L": ( 82, 107,  62),  "C": (155, 160, 165),
    }

    def __init__(self):
        self._sym_cache: dict = {}   # (sym_key, size) → PIL RGBA image

    # ── Frame ─────────────────────────────────────────────────────────────────

    def _get_frame_path(self, card: CardData) -> Optional[str]:
        base = _frames_dir()
        code = card.color.value
        if card.frame_style == FrameStyle.M15:
            suffix = self._M15_COLOR.get(code, "W")
            path   = os.path.join(base, "m15", "regular", f"m15Frame{suffix}.png")
        elif card.frame_style == FrameStyle.EXTENDED:
            c    = self._SIMPLE_COLOR.get(code, "w")
            path = os.path.join(base, "m15", "new", "extended", f"{c}.png")
        elif card.frame_style == FrameStyle.BORDERLESS:
            suffix = self._M15_COLOR.get(code, "W")
            path   = os.path.join(base, "m15", "borderless", f"m15GenericShowcaseFrame{suffix}.png")
        elif card.frame_style == FrameStyle.FULLART:
            c = self._SIMPLE_COLOR.get(code, "w")
            if c == "c":      # no colorless fullart — use artifact
                c = "a"
            path = os.path.join(base, "m15", "new", "fullart", f"{c}.png")
        elif card.frame_style == FrameStyle.EIGHTH:
            path = os.path.join(base, "8th", f"{self._SIMPLE_COLOR.get(code,'w')}.png")
        elif card.frame_style == FrameStyle.OLD:
            path = os.path.join(base, "old", "floating", f"{self._SIMPLE_COLOR.get(code,'w')}.png")
        elif card.frame_style == FrameStyle.TOKEN:
            path = os.path.join(base, "token", "m15", "regular", f"{self._SIMPLE_COLOR.get(code,'w')}.png")
        else:
            return None
        return path if os.path.isfile(path) else None

    def _load_frame(self, card: CardData) -> Image.Image:
        canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 255))
        path   = self._get_frame_path(card)
        if path:
            try:
                frame = Image.open(path).convert("RGBA")
                frame = frame.resize((CARD_W, CARD_H), Image.LANCZOS)
                canvas.paste(frame, (0, 0), frame)
                return canvas
            except Exception as e:
                print(f"[CardCreator] Frame load failed: {e}")
        fill = self._FALLBACK_RGB.get(card.color.value, (100, 100, 100))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, CARD_W-1, CARD_H-1], fill=fill+(255,))
        draw.rectangle([0, 0, CARD_W-1, CARD_H-1], outline=(0,0,0), width=8)
        return canvas

    # ── Fonts ─────────────────────────────────────────────────────────────────

    def _load_font(self, size: int, role: str = "rules") -> ImageFont.FreeTypeFont:
        fdir = _fonts_dir()
        _frames_fonts = os.path.join(_assets_dir(), "frames", "fonts")
        candidates = {
            "name":   ["Beleren-Bold.ttf",       os.path.join("fonts", "Mplantin.ttf")],
            "type":   ["Beleren-SmallCaps.ttf",   os.path.join("fonts", "Mplantin.ttf")],
            "rules":  [os.path.join("fonts", "Mplantin.ttf")],
            "flavor": [os.path.join("fonts", "Mplantin.ttf")],
            "italic": [os.path.join("fonts", "Mplantin-Italic.ttf"),
                       os.path.join("fonts", "MPlantinItalic.ttf"),
                       os.path.join("fonts", "Mplantin.ttf")],
            "pt":     [os.path.join(_frames_fonts, "matrix-b.ttf"),
                       os.path.join("fonts", "Matrix-Bold.ttf"),
                       "Beleren-Bold.ttf",
                       os.path.join("fonts", "Mplantin.ttf")],
            "small":  [os.path.join("fonts", "Mplantin.ttf")],
        }
        for fname in candidates.get(role, [os.path.join("fonts", "Mplantin.ttf")]):
            fpath = fname if os.path.isabs(fname) else os.path.join(fdir, fname)
            if os.path.isfile(fpath):
                try:
                    return ImageFont.truetype(fpath, size)
                except Exception:
                    continue
        for sys_name in ("Palatino Linotype", "Georgia", "Arial"):
            try:
                return ImageFont.truetype(sys_name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # ── Mana symbols ──────────────────────────────────────────────────────────

    def _get_symbol(self, sym: str, size: int) -> Optional[Image.Image]:
        """Return a PIL RGBA image of the mana symbol, using symbol_cache."""
        key = (sym, size)
        if key in self._sym_cache:
            return self._sym_cache[key]
        try:
            from engine.symbol_cache import get_symbol
            img = get_symbol(_normalize_mana_sym(sym), size)
            self._sym_cache[key] = img
            return img
        except Exception as e:
            print(f"[CardCreator] Symbol {sym!r} failed: {e}")
            return None

    # ── Artwork ───────────────────────────────────────────────────────────────

    def _paste_artwork(self, canvas: Image.Image, art_path: Optional[str]) -> None:
        x0, y0, x1, y1 = ART_BOX
        box_w, box_h    = x1 - x0, y1 - y0
        if art_path and os.path.isfile(art_path):
            try:
                art   = Image.open(art_path).convert("RGBA")
                scale = max(box_w / art.width, box_h / art.height)
                nw    = round(art.width  * scale)
                nh    = round(art.height * scale)
                art   = art.resize((nw, nh), Image.LANCZOS)
                cx    = (nw - box_w) // 2
                cy    = (nh - box_h) // 2
                art   = art.crop((cx, cy, cx + box_w, cy + box_h))
                canvas.paste(art, (x0, y0), art)
                return
            except Exception as e:
                print(f"[CardCreator] Art load failed: {e}")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([x0, y0, x1-1, y1-1], fill=(80, 80, 80, 220))
        try:
            f = self._load_font(28, "rules")
            draw.text((x0 + box_w//2 - 22, y0 + box_h//2 - 16), "ART",
                      fill=(180, 180, 180), font=f)
        except Exception:
            pass

    # ── Name bar ──────────────────────────────────────────────────────────────

    def _render_name(self, canvas: Image.Image, card: CardData) -> None:
        draw = ImageDraw.Draw(canvas)
        font = self._load_font(card.name_size, "italic" if card.name_italic else "name")
        x0, y0, x1, y1 = NAME_BOX
        try:
            bb = font.getbbox(card.name)
            ty = y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]
            tw = bb[2] - bb[0]
        except Exception:
            ty = y0 + 4
            tw = round(font.getlength(card.name))
            bb = (0, 0, tw, card.name_size)

        if card.name_highlight:
            hl = Image.new("RGBA", (max(1, tw + 4), max(1, y1 - y0)), (255, 210, 0, 90))
            canvas.alpha_composite(hl, dest=(max(0, x0 - 2), max(0, y0)))

        kw = {"fill": card.name_color + (255,), "font": font}
        if card.name_bold:
            kw["stroke_width"] = 1
            kw["stroke_fill"]  = card.name_color + (255,)
        draw.text((x0, ty), card.name, **kw)

        if card.name_underline:
            uy = ty + (bb[3] - bb[1]) + 1
            draw.line([(x0, uy), (min(x0 + tw, x1), uy)],
                       fill=card.name_color + (200,), width=1)

    def _render_mana_cost(self, canvas: Image.Image, mana_str: str) -> None:
        """Render mana cost symbols right-aligned in the name bar."""
        if not mana_str:
            return
        mana_str   = _normalize_mana_cost(mana_str)
        tokens     = _parse_tokens(mana_str)
        sym_tokens = [t[1] for t in tokens if t[0] == "sym"]
        if not sym_tokens:
            return

        sym_size = 34           # slightly larger for visibility
        gap      = 2
        total_w  = len(sym_tokens) * (sym_size + gap) - gap
        x        = MANA_X1 - total_w - 4   # 4 px right margin
        y        = MANA_Y_CTR - sym_size // 2

        for sym in sym_tokens:
            img = self._get_symbol(sym, sym_size)
            if img:
                canvas.paste(img, (x, y), img)
            x += sym_size + gap

    # ── Type line ─────────────────────────────────────────────────────────────

    def _type_line_str(self, card: CardData) -> str:
        parts = []
        if card.supertype:
            parts.append(card.supertype)
        parts.append(card.card_type.value)
        if card.subtype:
            parts.append(f"— {card.subtype}")   # em dash
        return " ".join(parts)

    def _render_type_line(self, canvas: Image.Image, card: CardData) -> None:
        draw = ImageDraw.Draw(canvas)
        font = self._load_font(card.type_size, "italic" if card.type_italic else "type")
        x0, y0, x1, y1 = TYPE_BOX
        text = self._type_line_str(card)
        while font.getlength(text) > (x1 - x0) and len(text) > 3:
            text = text[:-4] + "..."
        try:
            bb = font.getbbox(text)
            ty = y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]
            tw = bb[2] - bb[0]
        except Exception:
            ty = y0 + 2
            tw = round(font.getlength(text))
            bb = (0, 0, tw, card.type_size)

        if card.type_highlight:
            hl = Image.new("RGBA", (max(1, tw + 4), max(1, y1 - y0)), (255, 210, 0, 90))
            canvas.alpha_composite(hl, dest=(max(0, x0 - 2), max(0, y0)))

        kw = {"fill": card.type_color + (255,), "font": font}
        if card.type_bold:
            kw["stroke_width"] = 1
            kw["stroke_fill"]  = card.type_color + (255,)
        draw.text((x0, ty), text, **kw)

        if card.type_underline:
            uy = ty + (bb[3] - bb[1]) + 1
            draw.line([(x0, uy), (min(x0 + tw, x1), uy)],
                       fill=card.type_color + (200,), width=1)

    def _render_rarity_dot(self, canvas: Image.Image, card: CardData) -> None:
        """Draw a small rarity-colored circle next to the type bar right edge."""
        r    = 10
        cx   = SET_X1 - 12
        cy   = (TYPE_BOX[1] + TYPE_BOX[3]) // 2
        rgb  = _RARITY_COLOR.get(card.rarity, (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=rgb+(255,), outline=(0,0,0,200), width=2)

    # ── Oracle + flavor text ───────────────────────────────────────────────────

    def _measure_token(self, tok_type: str, tok_val: str,
                       font: ImageFont.FreeTypeFont, sym_size: int) -> int:
        if tok_type == "sym":
            return sym_size
        try:
            return round(font.getlength(tok_val))
        except Exception:
            return len(tok_val) * (font.size * 6 // 10)

    def _token_height(self, font: ImageFont.FreeTypeFont, sym_size: int) -> int:
        try:
            bb = font.getbbox("Ag")
            return max(bb[3] - bb[1], sym_size)
        except Exception:
            return max(font.size, sym_size)

    def _render_oracle(self, canvas: Image.Image, card: CardData) -> None:
        """
        Render oracle text with inline mana symbols + optional flavor text.
        Auto-shrinks font size if text overflows the text box.
        """
        x0, y0, x1, y1 = TEXT_BOX
        box_w = x1 - x0
        box_h = y1 - y0

        oracle  = card.oracle_text or ""
        flavor  = card.flavor_text or ""
        has_both = bool(oracle and flavor)

        # Start from the user's chosen size; auto-shrink by 1pt steps down to 6
        start_sz = max(6, card.min_oracle_size)
        for font_size in range(start_sz, 5, -1):
            sym_size  = font_size
            line_gap  = max(3, font_size // 5)
            font_body = self._load_font(font_size, "rules")
            font_flav = self._load_font(font_size, "flavor")

            lines, total_h = self._layout_oracle(
                oracle, flavor, has_both,
                font_body, font_flav, sym_size, line_gap, box_w
            )
            if total_h <= box_h:
                break
        else:
            font_size  = 6
            sym_size   = 6
            line_gap   = 2
            font_body  = self._load_font(6, "rules")
            font_flav  = self._load_font(6, "flavor")
            lines, _   = self._layout_oracle(
                oracle, flavor, has_both,
                font_body, font_flav, sym_size, line_gap, box_w
            )

        # Pre-load italic variant once (avoids per-token file opens)
        font_italic = self._load_font(font_size, "italic") if card.oracle_italic else font_body

        # Draw the lines
        draw = ImageDraw.Draw(canvas)
        lh   = self._token_height(font_body, sym_size)
        cur_y = y0
        for line in lines:
            if line is None:
                # Separator line between oracle and flavor
                draw.line([(x0 + box_w//4, cur_y + line_gap//2),
                           (x1 - box_w//4, cur_y + line_gap//2)],
                          fill=(0, 0, 0, 140), width=1)
                cur_y += line_gap + 2
                continue

            # Semi-transparent highlight rect drawn before text
            if card.oracle_highlight:
                lw = sum(
                    sym_size if tt == "sym" else round(tf.getlength(tv))
                    for tt, tv, tf, _ in line
                )
                hl = Image.new("RGBA", (max(1, lw + 4), max(1, lh + 2)), (255, 210, 0, 90))
                canvas.alpha_composite(hl, dest=(max(0, x0 - 2), max(0, cur_y)))

            cur_x = x0
            for tok_type, tok_val, tok_font, tok_sym in line:
                if tok_type == "sym":
                    img = self._get_symbol(tok_val, sym_size)
                    if img:
                        ty = cur_y + (lh - sym_size) // 2
                        canvas.paste(img, (cur_x, ty), img)
                    cur_x += sym_size
                else:
                    render_font = font_italic if card.oracle_italic else tok_font
                    try:
                        asc = render_font.getbbox("Ag")[1]
                        ty = cur_y - asc
                    except Exception:
                        ty = cur_y
                    text_kw = {"fill": card.text_color + (255,), "font": render_font}
                    if card.oracle_bold:
                        text_kw["stroke_width"] = 1
                        text_kw["stroke_fill"]  = card.text_color + (255,)
                    draw.text((cur_x, ty), tok_val, **text_kw)
                    cur_x += round(render_font.getlength(tok_val))

            # Underline drawn after all tokens of this line
            if card.oracle_underline and cur_x > x0:
                uy = cur_y + lh + 1
                draw.line([(x0, uy), (cur_x, uy)],
                           fill=card.text_color + (200,), width=1)

            cur_y += lh + line_gap

    def _layout_oracle(self, oracle: str, flavor: str, has_both: bool,
                       font_body, font_flav, sym_size: int, line_gap: int,
                       box_w: int) -> tuple[list, int]:
        """
        Lay out all oracle and flavor tokens into wrapped lines.
        Returns (lines, total_height).
        Each line is a list of (tok_type, tok_val, font, sym_size) tuples.
        None in lines = separator.
        """
        lh    = self._token_height(font_body, sym_size)
        lines = []
        total = 0

        def _add_para(text: str, font: ImageFont.FreeTypeFont) -> None:
            nonlocal total
            if not text.strip():
                lines.append([])
                total += lh + line_gap
                return
            toks  = _parse_tokens(text)
            words = self._split_to_words(toks, font)
            line  = []
            cur_w = 0
            for word_toks in words:
                word_w = sum(self._measure_token(t, v, font, sym_size)
                             for t, v in word_toks)
                if cur_w + word_w > box_w and line:
                    lines.append([(t, v, font, sym_size) for t, v in line])
                    total += lh + line_gap
                    line   = list(word_toks)
                    cur_w  = word_w
                else:
                    line.extend(word_toks)
                    cur_w += word_w
            if line:
                lines.append([(t, v, font, sym_size) for t, v in line])
                total += lh + line_gap

        if oracle:
            for para in oracle.split("\n"):
                _add_para(para, font_body)

        if has_both:
            lines.append(None)          # separator
            total += line_gap + 2

        if flavor:
            for para in flavor.split("\n"):
                _add_para(para, font_flav)

        return lines, total

    def _split_to_words(self, tokens: list[tuple[str, str]],
                        font: ImageFont.FreeTypeFont) -> list[list[tuple[str, str]]]:
        """
        Break a token list into word groups (each group = a unit that won't be split).
        Symbols are always their own word. Text is split on spaces.
        """
        words = []
        buf   = []
        for tok_type, tok_val in tokens:
            if tok_type == "sym":
                if buf:
                    words.append(buf)
                    buf = []
                words.append([("sym", tok_val)])
            else:
                # Split on spaces, keeping spaces attached to the preceding word
                parts = tok_val.split(" ")
                for i, part in enumerate(parts):
                    if i > 0:
                        # flush buf as a word
                        if buf:
                            words.append(buf)
                            buf = []
                    if part:
                        buf.append(("txt", part + (" " if i < len(parts)-1 else "")))
                if parts and not parts[-1]:
                    # trailing space
                    if buf:
                        words.append(buf)
                        buf = []
        if buf:
            words.append(buf)
        return words

    # ── P/T box (rounded rectangle, 3-layer — matches M15 style) ─────────────

    @staticmethod
    def _rrect(draw: ImageDraw.ImageDraw, xy, radius: int,
               fill=None, outline=None) -> None:
        """Draw a rounded rectangle; falls back to regular rect on old Pillow."""
        try:
            draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline)
        except AttributeError:
            draw.rectangle(xy, fill=fill, outline=outline)

    def _render_pt(self, canvas: Image.Image, card: CardData) -> None:
        if card.power and card.toughness:
            pt_text = f"{card.power}  /  {card.toughness}"
        elif card.loyalty:
            pt_text = card.loyalty
        else:
            return

        draw      = ImageDraw.Draw(canvas)
        font      = self._load_font(card.pt_size, "italic" if card.pt_italic else "pt")
        text_fill = card.pt_color + (255,)

        try:
            bb = font.getbbox(pt_text)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            tw, th = max(len(pt_text) * 14, 60), card.pt_size
            bb = (0, 0, tw, th)

        pad_x = 16
        bw    = max(120, tw + pad_x * 2)
        bh    = max(44, th + 16)
        r     = 8

        cx, cy = 651, 941
        x0, y0 = cx - bw // 2, cy - bh // 2
        x1, y1 = cx + bw // 2, cy + bh // 2

        frame_rgb = self._FALLBACK_RGB.get(card.color.value, (100, 100, 100))

        self._rrect(draw, [x0 - 4, y0 - 4, x1 + 4, y1 + 4],
                    radius=r + 3, fill=(0, 0, 0, 220))
        self._rrect(draw, [x0 - 2, y0 - 2, x1 + 2, y1 + 2],
                    radius=r + 1, fill=frame_rgb + (255,))
        self._rrect(draw, [x0, y0, x1, y1],
                    radius=r, fill=(248, 245, 228, 255))

        if card.pt_highlight:
            hl = Image.new("RGBA", (max(1, bw - 4), max(1, bh - 4)), (255, 210, 0, 90))
            canvas.alpha_composite(hl, dest=(max(0, x0 + 2), max(0, y0 + 2)))

        tx = cx - (tw // 2) - bb[0]
        ty = cy - (th // 2) - bb[1]
        kw = {"fill": text_fill, "font": font}
        if card.pt_bold:
            kw["stroke_width"] = 1
            kw["stroke_fill"]  = text_fill
        draw.text((tx, ty), pt_text, **kw)

        if card.pt_underline:
            uy = ty + th + 2
            draw.line([(tx, uy), (tx + tw, uy)], fill=card.pt_color + (200,), width=1)

    # ── Card number (bottom-left, below OtterForge Proxy stamp) ─────────────

    def _render_card_number(self, canvas: Image.Image, card: CardData) -> None:
        """Draw collector_number at bottom-left, below where OtterForge Proxy watermark appears."""
        if not card.show_number or not card.collector_number:
            return
        w, h   = canvas.size
        # x-fraction 0.193 aligns with _STAMP_X in proxy_watermark.py
        # y-fraction 0.958 places text below OtterForge Proxy (~0.933 for 1040px)
        x      = round(w * 0.193)
        y      = round(h * 0.958)
        font   = self._load_font(13, "small")
        text   = card.collector_number
        draw   = ImageDraw.Draw(canvas)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0, 180), font=font)
        draw.text((x, y), text, fill=(255, 255, 255, 200), font=font)

    # ── Collector strip (kept for reference) ──────────────────────────────────

    def _render_collector(self, canvas: Image.Image, card: CardData) -> None:
        draw = ImageDraw.Draw(canvas)
        font = self._load_font(14, "small")
        # Artist left, set/number right
        artist_str = card.artist
        set_str    = f"{card.set_code.upper()} {card.collector_number}/{card.collector_number}"
        draw.text((ARTIST_X, COLL_Y), artist_str, fill=(0, 0, 0, 180), font=font)
        try:
            sw = round(font.getlength(set_str))
        except Exception:
            sw = len(set_str) * 8
        draw.text((SET_X1 - sw, COLL_Y), set_str, fill=(0, 0, 0, 180), font=font)

    # ── Full-bleed render (Extended / Borderless / Full Art) ─────────────────

    _FULL_BLEED_STYLES = {FrameStyle.EXTENDED, FrameStyle.BORDERLESS, FrameStyle.FULLART}

    def _render_full_bleed(self, card: CardData) -> Image.Image:
        """Artwork fills the entire canvas first, then frame composited on top."""
        canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 255))
        # Artwork: scale-to-cover the full card
        if card.art_path and os.path.isfile(card.art_path):
            try:
                art   = Image.open(card.art_path).convert("RGBA")
                scale = max(CARD_W / art.width, CARD_H / art.height)
                nw    = round(art.width  * scale)
                nh    = round(art.height * scale)
                art   = art.resize((nw, nh), Image.LANCZOS)
                cx    = (nw - CARD_W) // 2
                cy    = (nh - CARD_H) // 2
                art   = art.crop((cx, cy, cx + CARD_W, cy + CARD_H))
                canvas.paste(art, (0, 0), art)
            except Exception as e:
                print(f"[CardCreator] Art load failed: {e}")
        else:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([0, 0, CARD_W-1, CARD_H-1], fill=(80, 80, 80, 220))
        # Frame composited on top (opaque areas cover art, transparent areas reveal it)
        path = self._get_frame_path(card)
        if path:
            try:
                frame = Image.open(path).convert("RGBA")
                frame = frame.resize((CARD_W, CARD_H), Image.LANCZOS)
                canvas.paste(frame, (0, 0), frame)
            except Exception as e:
                print(f"[CardCreator] Frame load failed: {e}")
        self._render_name(canvas, card)
        self._render_mana_cost(canvas, card.mana_cost)
        self._render_type_line(canvas, card)
        self._render_rarity_dot(canvas, card)
        self._render_oracle(canvas, card)
        self._render_pt(canvas, card)
        self._render_card_number(canvas, card)
        return canvas

    # ── Public API ────────────────────────────────────────────────────────────

    def render_card(self, card: CardData) -> Image.Image:
        """
        Full render: frame + artwork + all text layers.
        Returns a PIL RGBA Image (CARD_W x CARD_H).
        """
        if card.frame_style in self._FULL_BLEED_STYLES:
            return self._render_full_bleed(card)
        canvas = self._load_frame(card)
        self._paste_artwork(canvas, card.art_path)
        self._render_name(canvas, card)
        self._render_mana_cost(canvas, card.mana_cost)
        self._render_type_line(canvas, card)
        self._render_rarity_dot(canvas, card)
        self._render_oracle(canvas, card)
        self._render_pt(canvas, card)
        self._render_card_number(canvas, card)
        return canvas

    def export_card(self, card: CardData, output_path: str, dpi: int = 300) -> str:
        """Render and save as PNG. Returns the saved path."""
        img    = self.render_card(card).convert("RGB")
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        safe_save_png(img, output_path, dpi=(dpi, dpi))
        print(f"[CardCreator] Exported {dpi} DPI: {os.path.basename(output_path)}")
        return output_path
