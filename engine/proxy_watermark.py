"""
engine/proxy_watermark.py
--------------------------
Applies an OtterForge proxy watermark to the bottom strip of a card image.
Overwrites the existing MTG copyright/legal text with:
  Line 1 : "[YEAR] OtterForge Proxy • Not for sale"
  Line 2 : "[SET] • [CN]  [LANG]  ✶ [ARTIST]"  (when Scryfall metadata provided)
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

_STRIP_RATIO = 0.034   # fraction of image height replaced by the watermark strip


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _WINDOWS_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


class ProxyWatermark:
    """Replaces the bottom strip of a card image with an OtterForge proxy stamp."""

    def apply(self, image_path: str, card_json: dict | None = None) -> None:
        """Modify the image at image_path in-place."""
        try:
            raw = Image.open(image_path)
            if raw.mode in ("RGBA", "LA", "PA"):
                # Composite onto the watermark background colour so transparency
                # doesn't go black when we later drop to RGB.
                bg = Image.new("RGBA", raw.size, (14, 11, 19, 255))
                bg.paste(raw, mask=raw.split()[-1])
                img = bg.convert("RGB")
            else:
                img = raw.convert("RGB")
        except Exception as e:
            print(f"[ProxyWatermark] Cannot open {image_path!r}: {e}")
            return

        w, h = img.size
        strip_h = max(28, int(h * _STRIP_RATIO))
        y_top = h - strip_h

        draw = ImageDraw.Draw(img)
        draw.rectangle([0, y_top, w, h], fill=(14, 11, 19))

        line1 = self._line1(card_json)
        line2 = self._line2(card_json)

        sz1 = max(9,  strip_h // 3)
        sz2 = max(7,  strip_h // 4)
        font1 = _load_font(sz1)
        font2 = _load_font(sz2)

        pad_x = max(6, w // 80)
        used_h = sz1 + (sz2 + 2 if line2 else 0)
        margin_top = max(3, (strip_h - used_h) // 3)
        y1 = y_top + margin_top
        y2 = y1 + sz1 + 2

        draw.text((pad_x, y1), line1, fill=(212, 207, 200), font=font1)
        if line2:
            draw.text((pad_x, y2), line2, fill=(150, 144, 140), font=font2)

        img.save(image_path, "PNG", compress_level=9, optimize=True)
        print(f"[ProxyWatermark] Applied: {os.path.basename(image_path)}")

    # ── text builders ─────────────────────────────────────────────────────────

    def _line1(self, card_json: dict | None) -> str:
        if card_json:
            year = (card_json.get("released_at") or "")[:4]
            if year:
                return f"{year} OtterForge Proxy • Not for sale"
        return "OtterForge Proxy • Not for sale"

    def _line2(self, card_json: dict | None) -> str:
        if not card_json:
            return ""
        set_code = (card_json.get("set") or "").upper()
        cn       = card_json.get("collector_number") or ""
        lang     = (card_json.get("lang") or "EN").upper()
        artist   = self._artist(card_json)

        parts: list[str] = []
        if set_code and cn:
            parts.append(f"{set_code} • {cn}")
        if lang:
            parts.append(lang)
        if artist:
            parts.append(f"✶ {artist.upper()}")
        return "  ".join(parts)

    def _artist(self, card_json: dict) -> str:
        faces = card_json.get("card_faces", [])
        if faces:
            return faces[0].get("artist") or card_json.get("artist") or ""
        return card_json.get("artist") or ""
