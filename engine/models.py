"""
engine/models.py
----------------
Modèles de données de base pour MTG Print Factory.
"""


class Card:
    """Représente une carte Magic dans un deck."""

    def __init__(self, name: str, image_path: str):
        self.name = name
        self.image_path = image_path
        self.count = 1
        self.back_image_path: str | None = None  # override endos pour cette carte

    def to_dict(self) -> dict:
        """Sérialise la carte en dictionnaire (pour sauvegarde JSON)."""
        d = {
            "name": self.name,
            "image_path": self.image_path,
            "count": self.count,
        }
        if self.back_image_path:
            d["back_image_path"] = self.back_image_path
        return d

    def __repr__(self):
        return f"Card(name={self.name!r}, count={self.count})"
