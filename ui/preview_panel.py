"""
ui/preview_panel.py
-------------------
Panneau d'aperçu de la première feuille d'impression générée.
"""

import customtkinter as ctk
from PIL import Image


class PreviewPanel(ctk.CTkFrame):

    PREVIEW_SIZE = (370, 515)

    def __init__(self, master):
        super().__init__(master, corner_radius=0, fg_color="#1c1a20")
        self.master = master

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=0, pady=(10, 4))

        ctk.CTkFrame(header, width=3, fg_color="#c04828",
                     corner_radius=2).pack(side="left", fill="y", padx=(8, 6))

        ctk.CTkLabel(
            header, text="SHEET PREVIEW",
            font=ctk.CTkFont(size=9),
            text_color="#5a5060",
            anchor="w",
        ).pack(side="left")

        ctk.CTkFrame(self, height=1, fg_color="#28252e",
                     corner_radius=0).pack(fill="x", padx=8, pady=(0, 6))

        self.image_label = ctk.CTkLabel(
            self, text="No sheets generated yet.",
            text_color="#5a5060",
            font=ctk.CTkFont(size=11),
        )
        self.image_label.pack(expand=True)

    def update(self, sheets: list[str]) -> None:
        if not sheets:
            return
        img = Image.open(sheets[0]).resize(self.PREVIEW_SIZE, Image.LANCZOS)
        self._ctk_img = ctk.CTkImage(light_image=img, size=self.PREVIEW_SIZE)
        self.image_label.configure(image=self._ctk_img, text="")
