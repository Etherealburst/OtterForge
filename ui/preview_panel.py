"""
ui/preview_panel.py
-------------------
Panneau d'aperçu de la première feuille d'impression générée.
"""

import customtkinter as ctk
from PIL import Image


class PreviewPanel(ctk.CTkFrame):
    """Affiche un aperçu réduit de la première feuille générée."""

    PREVIEW_SIZE = (400, 550)

    def __init__(self, master):
        super().__init__(master)
        self.master = master

        self.title_label = ctk.CTkLabel(self, text="Sheet Preview", font=ctk.CTkFont(size=13))
        self.title_label.pack(pady=(8, 4))

        self.image_label = ctk.CTkLabel(self, text="No preview yet")
        self.image_label.pack(expand=True)

    def update(self, sheets: list[str]) -> None:
        """Affiche un aperçu de la première feuille de la liste."""
        if not sheets:
            return

        img = Image.open(sheets[0])
        img = img.resize(self.PREVIEW_SIZE, Image.LANCZOS)

        # On garde une référence pour éviter le garbage collector
        self._ctk_img = ctk.CTkImage(light_image=img, size=self.PREVIEW_SIZE)
        self.image_label.configure(image=self._ctk_img, text="")
