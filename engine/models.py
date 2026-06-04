"""
engine/models.py
----------------
Modèles de données de base pour OtterForge.
"""

import os


def resolve_display_path(image_path: str) -> str:
    """Retourne le chemin d'affichage optimal : préfère le .png natif au _1200dpi.png.

    Les fichiers _1200dpi.png sont très lourds (3288×4488 px). Pour l'affichage
    à l'écran, le .png Scryfall natif (672×936 px) est suffisant et charge 10× plus vite.
    """
    if image_path and image_path.endswith("_1200dpi.png"):
        native = image_path.replace("_1200dpi.png", ".png")
        if os.path.exists(native):
            return native
    return image_path


class Card:
    """Représente une carte Magic dans un deck."""

    def __init__(self, name: str, image_path: str):
        self.name = name
        self.image_path = image_path
        self.count = 1
        self.back_image_path: str | None = None  # override endos pour cette carte
        self.watermark_offset: tuple = (0, 0)      # "OtterForge Proxy" (dx, dy), ref 672×936 px
        self.watermark_nfs_offset: tuple = (0, 0)  # "Not for sale" (dx, dy), ref 672×936 px
        self.watermark_bg: str = "auto"            # "auto" | "transparent" | "black"

    def to_dict(self) -> dict:
        """Sérialise la carte en dictionnaire (pour sauvegarde JSON)."""
        d = {
            "name": self.name,
            "image_path": self.image_path,
            "count": self.count,
        }
        if self.back_image_path:
            d["back_image_path"] = self.back_image_path
        if self.watermark_offset != (0, 0):
            d["watermark_offset"] = list(self.watermark_offset)
        if self.watermark_nfs_offset != (0, 0):
            d["watermark_nfs_offset"] = list(self.watermark_nfs_offset)
        if self.watermark_bg != "auto":
            d["watermark_bg"] = self.watermark_bg
        return d

    def __repr__(self):
        return f"Card(name={self.name!r}, count={self.count})"
