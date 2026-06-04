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
NAME_BOX   = (62,  44, 435,  88)   # card name text
MANA_X1    = 686                    # right edge for right-aligned mana cost
MANA_Y_CTR = 64                     # vertical center for mana symbols
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
    M15    = "m15"     # Modern (2015+) — m15/regular/m15Frame{X}.png
    EIGHTH = "8th"     # 8th edition classic (2003) — 8th/{x}.png
    OLD    = "old"     # Pre-2003 (Alpha/Beta) — old/floating/{x}.png
    TOKEN  = "token"   # Token — token/m15/regular/{x}.png


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
    # {T} tap, {Q} untap — symbol_cache uses 'T' and 'Q'
    return sym.upper()


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
        candidates = {
            "name":   ["Beleren-Bold.ttf",       os.path.join("fonts", "Mplantin.ttf")],
            "type":   ["Beleren-SmallCaps.ttf",   os.path.join("fonts", "Mplantin.ttf")],
            "rules":  [os.path.join("fonts", "Mplantin.ttf")],
            "flavor": [os.path.join("fonts", "Mplantin.ttf")],
            "pt":     ["Beleren-Bold.ttf", os.path.join("fonts", "Matrix-Bold.ttf"),
                       os.path.join("fonts", "Mplantin.ttf")],
            "small":  [os.path.join("fonts", "Mplantin.ttf")],
        }
        for fname in candidates.get(role, [os.path.join("fonts", "Mplantin.ttf")]):
            fpath = os.path.join(fdir, fname)
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
        font = self._load_font(28, "name")
        x0, y0, x1, y1 = NAME_BOX
        # Vertical center in the name box
        try:
            bb = font.getbbox(card.name)
            ty = y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]
        except Exception:
            ty = y0 + 4
        draw.text((x0, ty), card.name, fill=(0, 0, 0, 255), font=font)

    def _render_mana_cost(self, canvas: Image.Image, mana_str: str) -> None:
        """Render mana cost symbols right-aligned in the name bar."""
        if not mana_str:
            return
        tokens = _parse_tokens(mana_str)
        sym_tokens = [t[1] for t in tokens if t[0] == "sym"]
        if not sym_tokens:
            return

        sym_size = 30
        gap      = 3
        total_w  = len(sym_tokens) * (sym_size + gap) - gap
        x        = MANA_X1 - total_w
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
        font = self._load_font(22, "type")
        x0, y0, x1, y1 = TYPE_BOX
        text = self._type_line_str(card)
        # Truncate if too wide
        while font.getlength(text) > (x1 - x0) and len(text) > 3:
            text = text[:-4] + "..."
        try:
            bb = font.getbbox(text)
            ty = y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]
        except Exception:
            ty = y0 + 2
        draw.text((x0, ty), text, fill=(0, 0, 0, 255), font=font)

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

        for font_size in range(20, 8, -2):
            sym_size  = max(14, font_size)
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
            font_size  = 9
            sym_size   = 9
            line_gap   = 2
            font_body  = self._load_font(9, "rules")
            font_flav  = self._load_font(9, "flavor")
            lines, _   = self._layout_oracle(
                oracle, flavor, has_both,
                font_body, font_flav, sym_size, line_gap, box_w
            )

        # Draw the lines
        draw  = ImageDraw.Draw(canvas)
        cur_y = y0
        for line in lines:
            if line is None:
                # Separator line between oracle and flavor
                draw.line([(x0 + box_w//4, cur_y + line_gap//2),
                           (x1 - box_w//4, cur_y + line_gap//2)],
                          fill=(0, 0, 0, 140), width=1)
                cur_y += line_gap + 2
                continue
            cur_x = x0
            for tok_type, tok_val, tok_font, tok_sym in line:
                if tok_type == "sym":
                    img = self._get_symbol(tok_val, sym_size)
                    if img:
                        ty = cur_y + (self._token_height(tok_font, sym_size) - sym_size) // 2
                        canvas.paste(img, (cur_x, ty), img)
                    cur_x += sym_size
                else:
                    try:
                        bb = tok_font.getbbox(tok_val)
                        ty = cur_y - bb[1]
                    except Exception:
                        ty = cur_y
                    draw.text((cur_x, ty), tok_val, fill=(0, 0, 0, 255), font=tok_font)
                    cur_x += round(tok_font.getlength(tok_val))
            cur_y += self._token_height(font_body, sym_size) + line_gap

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

    # ── P/T box ───────────────────────────────────────────────────────────────

    def _render_pt(self, canvas: Image.Image, card: CardData) -> None:
        pt_text = ""
        if card.power and card.toughness:
            pt_text = f"{card.power}/{card.toughness}"
        elif card.loyalty:
            pt_text = card.loyalty
        if not pt_text:
            return

        draw = ImageDraw.Draw(canvas)
        font = self._load_font(24, "pt")

        # PT oval / badge center (bottom-right of card)
        cx, cy = 651, 936
        rw, rh = 58, 22

        # Oval background
        draw.ellipse([cx-rw, cy-rh, cx+rw, cy+rh],
                     fill=(248, 245, 230, 255), outline=(0, 0, 0, 255), width=2)
        # Text centered
        try:
            bb = font.getbbox(pt_text)
            tx = cx - (bb[2] - bb[0]) // 2 - bb[0]
            ty = cy - (bb[3] - bb[1]) // 2 - bb[1]
        except Exception:
            tx, ty = cx - len(pt_text)*8, cy - 12
        draw.text((tx, ty), pt_text, fill=(0, 0, 0, 255), font=font)

    # ── Collector strip ───────────────────────────────────────────────────────

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

    # ── Public API ────────────────────────────────────────────────────────────

    def render_card(self, card: CardData) -> Image.Image:
        """
        Full render: frame + artwork + all text layers.
        Returns a PIL RGBA Image (CARD_W x CARD_H).
        """
        canvas = self._load_frame(card)
        self._paste_artwork(canvas, card.art_path)
        self._render_name(canvas, card)
        self._render_mana_cost(canvas, card.mana_cost)
        self._render_type_line(canvas, card)
        self._render_rarity_dot(canvas, card)
        self._render_oracle(canvas, card)
        self._render_pt(canvas, card)
        self._render_collector(canvas, card)
        return canvas

    def export_card(self, card: CardData, output_path: str, dpi: int = 300) -> str:
        """Render and save as PNG. Returns the saved path."""
        img    = self.render_card(card).convert("RGB")
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        img.save(output_path, "PNG", dpi=(dpi, dpi))
        print(f"[CardCreator] Exported {dpi} DPI: {os.path.basename(output_path)}")
        return output_path
