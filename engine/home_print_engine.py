"""
engine/home_print_engine.py
---------------------------
Génère des feuilles d'impression pour impression à domicile.
Supporte Letter/A4, marges configurables, crop marks, et mode recto-verso (deux passes).
"""

import os
from PIL import Image, ImageDraw
from engine.models import Card

PAPER_SIZES_IN = {
    "Letter": (8.5, 11.0),
    "A4":     (8.27, 11.69),
}


class HomePrintEngine:
    """
    Génère des feuilles d'impression optimisées pour imprimante à domicile.

    Args:
        paper:      "Letter" ou "A4"
        dpi:        résolution de sortie (défaut 300)
        card_w_mm:  largeur d'une carte en mm (défaut 63.5 = poker standard)
        card_h_mm:  hauteur d'une carte en mm (défaut 88.9 = poker standard)
        margin_mm:  marge extérieure en mm (défaut 5)
        crop_marks: dessiner des traits de coupe aux coins (défaut False)
        duplex:     ajouter feuilles verso miroir pour impression deux passes (défaut False)
    """

    def __init__(
        self,
        paper: str = "Letter",
        dpi: int = 300,
        card_w_mm: float = 63.5,
        card_h_mm: float = 88.9,
        margin_mm: float = 5.0,
        crop_marks: bool = False,
        duplex: bool = False,
    ):
        self.paper = paper
        self.dpi = dpi
        self.crop_marks = crop_marks
        self.duplex = duplex

        def mm_to_px(mm: float) -> int:
            return round(mm / 25.4 * dpi)

        self.card_w = mm_to_px(card_w_mm)
        self.card_h = mm_to_px(card_h_mm)
        self.margin = mm_to_px(margin_mm)

        pw_in, ph_in = PAPER_SIZES_IN.get(paper, PAPER_SIZES_IN["Letter"])
        self.sheet_w = round(pw_in * dpi)
        self.sheet_h = round(ph_in * dpi)

        usable_w = self.sheet_w - 2 * self.margin
        usable_h = self.sheet_h - 2 * self.margin
        self.cols = max(1, usable_w // self.card_w)
        self.rows = max(1, usable_h // self.card_h)
        self.cards_per_sheet = self.cols * self.rows

        # Centre la grille sur la feuille
        grid_w = self.cols * self.card_w
        grid_h = self.rows * self.card_h
        self.offset_x = (self.sheet_w - grid_w) // 2
        self.offset_y = (self.sheet_h - grid_h) // 2

    # ------------------------------------------------------------------

    def sheet_count(self, cards: list) -> int:
        """Nombre de feuilles recto (sans compter les versos duplex)."""
        total = sum(getattr(c, "count", 1) for c in cards)
        if total == 0:
            return 0
        return -(-total // self.cards_per_sheet)  # ceil division

    def generate(self, cards: list) -> list[Image.Image]:
        """
        Génère toutes les feuilles PIL.
        Si duplex=True, chaque feuille recto est suivie de son miroir verso.
        """
        expanded = []
        for card in cards:
            expanded.extend([card] * getattr(card, "count", 1))

        sheets: list[Image.Image] = []
        for i in range(0, max(len(expanded), 1), self.cards_per_sheet):
            batch = expanded[i:i + self.cards_per_sheet]
            front = self._render_sheet(batch)
            sheets.append(front)
            if self.duplex:
                sheets.append(self._mirror_sheet(front))

        return sheets

    def export_png(self, cards: list, output_dir: str) -> list[str]:
        """Exporte une PNG par feuille dans output_dir. Retourne les chemins."""
        os.makedirs(output_dir, exist_ok=True)
        paths = []
        for i, sheet in enumerate(self.generate(cards)):
            path = os.path.join(output_dir, f"home_sheet_{i + 1:03}.png")
            sheet.save(path, "PNG", dpi=(self.dpi, self.dpi))
            paths.append(path)
        return paths

    def export_pdf(self, cards: list, output_path: str) -> str:
        """Exporte un PDF multi-pages. Retourne le chemin."""
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        sheets = [s.convert("RGB") for s in self.generate(cards)]
        if not sheets:
            return output_path
        sheets[0].save(
            output_path, "PDF",
            save_all=True,
            append_images=sheets[1:],
            resolution=self.dpi,
        )
        return output_path

    # ------------------------------------------------------------------

    def _render_sheet(self, cards: list) -> Image.Image:
        sheet = Image.new("RGB", (self.sheet_w, self.sheet_h), "white")
        draw = ImageDraw.Draw(sheet) if self.crop_marks else None

        for i, card in enumerate(cards):
            col = i % self.cols
            row = i // self.cols
            x = self.offset_x + col * self.card_w
            y = self.offset_y + row * self.card_h

            path = card.image_path if hasattr(card, "image_path") else card
            try:
                img = Image.open(path).convert("RGB")
                img = img.resize((self.card_w, self.card_h), Image.LANCZOS)
                sheet.paste(img, (x, y))
            except Exception as e:
                print(f"[HomePrintEngine] Erreur image : {e}")

            if draw:
                self._draw_crop_marks(draw, x, y, self.card_w, self.card_h)

        return sheet

    def _draw_crop_marks(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int
    ) -> None:
        """Traits de coupe aux 4 coins, 5 mm de long avec 1 mm de marge."""
        def mm(v):
            return round(v / 25.4 * self.dpi)

        mark = mm(5)
        gap  = mm(1)
        lw   = max(1, mm(0.25))
        color = "#aaaaaa"

        for cx, cy, dx, dy in [
            (x,     y,     -1, -1),
            (x + w, y,     +1, -1),
            (x,     y + h, -1, +1),
            (x + w, y + h, +1, +1),
        ]:
            draw.line([(cx + dx * gap, cy), (cx + dx * (gap + mark), cy)], fill=color, width=lw)
            draw.line([(cx, cy + dy * gap), (cx, cy + dy * (gap + mark))], fill=color, width=lw)

    def _mirror_sheet(self, sheet: Image.Image) -> Image.Image:
        """Miroir horizontal pour impression recto-verso manuelle."""
        return sheet.transpose(Image.FLIP_LEFT_RIGHT)
