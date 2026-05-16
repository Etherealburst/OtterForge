"""
engine/mpc_print_engine.py
--------------------------
MPC Print Engine v2 — génération de feuilles d'impression proxy.
Remplace print_engine.py et sheet_builder.py.

Dimensions MPC standard :
  - Carte : 745 × 1040 px (à 300 DPI = 2.48" × 3.46")
  - Feuille : grille 3×3 avec marges et espacement
  - Export : PNG 300 DPI, prêt pour upload MPC
"""

import os
from PIL import Image
from engine.models import Card
from config import (
    SHEET_COLS, SHEET_ROWS,
    MPC_CARD_W, MPC_CARD_H,
    MPC_MARGIN, MPC_GAP,
    MPC_DPI,
    OUTPUT_DIR,
)


class MPCPrintEngine:
    """
    Génère des feuilles d'impression MPC au format 3×3.

    Paramètres configurables à l'instanciation :
        cols, rows      : disposition de la grille (défaut depuis config.py)
        card_w, card_h  : dimensions d'une carte en pixels (défaut depuis config.py)
        margin          : marge extérieure de la feuille en pixels
        gap             : espacement entre les cartes en pixels
    """

    def __init__(
        self,
        cols: int = SHEET_COLS,
        rows: int = SHEET_ROWS,
        card_w: int = MPC_CARD_W,
        card_h: int = MPC_CARD_H,
        margin: int = MPC_MARGIN,
        gap: int = MPC_GAP,
    ):
        self.cols = cols
        self.rows = rows
        self.card_w = card_w
        self.card_h = card_h
        self.margin = margin
        self.gap = gap
        self.cards_per_sheet = cols * rows

    # ------------------------------------------------------------------
    # DIMENSIONS DE LA FEUILLE
    # ------------------------------------------------------------------

    @property
    def sheet_width(self) -> int:
        return self.margin * 2 + self.cols * self.card_w + (self.cols - 1) * self.gap

    @property
    def sheet_height(self) -> int:
        return self.margin * 2 + self.rows * self.card_h + (self.rows - 1) * self.gap

    # ------------------------------------------------------------------
    # GÉNÉRATION DES FEUILLES (depuis objets Card)
    # ------------------------------------------------------------------

    def generate_sheets(self, cards: list[Card], output_dir: str = f"{OUTPUT_DIR}/sheets") -> list[str]:
        """
        Génère les feuilles d'impression à partir d'une liste de cartes.
        Tient compte du count de chaque carte (une carte x3 apparaît 3 fois).
        Retourne la liste des chemins de feuilles générées.
        """
        os.makedirs(output_dir, exist_ok=True)

        # Expansion : on répète chaque carte selon son count
        expanded = []
        for card in cards:
            expanded.extend([card] * card.count)

        sheets = []

        for i in range(0, len(expanded), self.cards_per_sheet):
            batch = expanded[i:i + self.cards_per_sheet]
            sheet_index = i // self.cards_per_sheet + 1
            path = os.path.join(output_dir, f"sheet_{sheet_index:03}.png")
            self._render_sheet(batch, path)
            sheets.append(path)
            print(f"[MPCPrintEngine] Feuille générée : {path}")

        return sheets

    # ------------------------------------------------------------------
    # GÉNÉRATION DES FEUILLES (depuis chemins d'images bruts)
    # ------------------------------------------------------------------

    def generate_sheets_from_paths(self, image_paths: list[str], output_dir: str = "output/sheets") -> list[str]:
        """
        Génère les feuilles depuis une liste de chemins d'images.
        Utile pour export direct sans objets Card.
        """
        os.makedirs(output_dir, exist_ok=True)
        sheets = []

        for i in range(0, len(image_paths), self.cards_per_sheet):
            batch = image_paths[i:i + self.cards_per_sheet]
            sheet_index = i // self.cards_per_sheet + 1
            path = os.path.join(output_dir, f"sheet_{sheet_index:03}.png")
            self._render_sheet_from_paths(batch, path)
            sheets.append(path)
            print(f"[MPCPrintEngine] Feuille générée : {path}")

        return sheets

    # ------------------------------------------------------------------
    # RENDU D'UNE FEUILLE (depuis Card)
    # ------------------------------------------------------------------

    def _render_sheet(self, cards: list[Card], output_path: str) -> None:
        """Compose et sauvegarde une feuille à partir d'objets Card."""
        sheet = Image.new("RGB", (self.sheet_width, self.sheet_height), "white")

        for i, card in enumerate(cards):
            try:
                img = Image.open(card.image_path).convert("RGB")
                img = img.resize((self.card_w, self.card_h), Image.LANCZOS)
                x, y = self._card_position(i)
                sheet.paste(img, (x, y))
            except Exception as e:
                print(f"[MPCPrintEngine] Erreur carte {card.name!r} : {e}")

        sheet.save(output_path, "PNG", dpi=(MPC_DPI, MPC_DPI))

    # ------------------------------------------------------------------
    # RENDU D'UNE FEUILLE (depuis chemins)
    # ------------------------------------------------------------------

    def _render_sheet_from_paths(self, paths: list[str], output_path: str) -> None:
        """Compose et sauvegarde une feuille à partir de chemins d'images."""
        sheet = Image.new("RGB", (self.sheet_width, self.sheet_height), "white")

        for i, path in enumerate(paths):
            try:
                img = Image.open(path).convert("RGB")
                img = img.resize((self.card_w, self.card_h), Image.LANCZOS)
                x, y = self._card_position(i)
                sheet.paste(img, (x, y))
            except Exception as e:
                print(f"[MPCPrintEngine] Erreur image {path!r} : {e}")

        sheet.save(output_path, "PNG", dpi=(MPC_DPI, MPC_DPI))

    # ------------------------------------------------------------------
    # CALCUL DE POSITION
    # ------------------------------------------------------------------

    def _card_position(self, index: int) -> tuple[int, int]:
        """Calcule la position (x, y) d'une carte dans la grille."""
        col = index % self.cols
        row = index // self.cols
        x = self.margin + col * (self.card_w + self.gap)
        y = self.margin + row * (self.card_h + self.gap)
        return x, y
