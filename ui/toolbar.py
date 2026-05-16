"""
ui/toolbar.py
-------------
Barre d'outils principale avec logo, branding et groupes d'actions.
"""

import os
import customtkinter as ctk
from PIL import Image, ImageDraw


class Toolbar(ctk.CTkFrame):

    HEIGHT = 70

    def __init__(self, master):
        super().__init__(master, height=self.HEIGHT, corner_radius=0, fg_color="#0d0c0e")
        self.master = master
        self.pack_propagate(False)
        self._build()

    def _build(self):
        # ── Branding ──────────────────────────────────────────────────────
        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(side="left", fill="y", padx=(14, 0))

        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "OtterForge_Image.jpg"
        )
        try:
            pil_img = Image.open(logo_path).resize((50, 50), Image.LANCZOS).convert("RGBA")
            mask = Image.new("L", (50, 50), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 50, 50), fill=255)
            pil_img.putalpha(mask)
            ctk_logo = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(50, 50))
            ctk.CTkLabel(brand, image=ctk_logo, text="").pack(side="left", padx=(0, 11))
        except Exception:
            pass

        name_col = ctk.CTkFrame(brand, fg_color="transparent")
        name_col.pack(side="left", fill="y", pady=12)

        ctk.CTkLabel(
            name_col, text="OTTERFORGE",
            font=ctk.CTkFont(family="Georgia", size=18, weight="bold"),
            text_color="#f0ece4",
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            name_col, text="Craft every card, your way.",
            font=ctk.CTkFont(size=10),
            text_color="#5a5060",
            anchor="w",
        ).pack(anchor="w")

        # ── Séparateur ────────────────────────────────────────────────────
        _vsep(self)

        # ── Groupe DECK ───────────────────────────────────────────────────
        deck_grp = ctk.CTkFrame(self, fg_color="transparent")
        deck_grp.pack(side="left", fill="y", padx=6)

        _micro_label(deck_grp, "DECK")

        row = ctk.CTkFrame(deck_grp, fg_color="transparent")
        row.pack(pady=(0, 8))

        for text, cmd in [
            ("Open",       self.master.load_deck_file),
            ("Save",       self.master.save_deck),
            ("Import TXT", self.master.import_txt_deck),
        ]:
            ctk.CTkButton(
                row, text=text, width=88, height=30,
                font=ctk.CTkFont(size=12),
                command=cmd,
            ).pack(side="left", padx=3)

        # ── Séparateur ────────────────────────────────────────────────────
        _vsep(self)

        # ── Groupe OUTPUT ─────────────────────────────────────────────────
        out_grp = ctk.CTkFrame(self, fg_color="transparent")
        out_grp.pack(side="left", fill="y", padx=6)

        _micro_label(out_grp, "OUTPUT")

        row2 = ctk.CTkFrame(out_grp, fg_color="transparent")
        row2.pack(pady=(0, 8))

        for text, cmd in [
            ("Export Sheets", self.master.export_print_sheets),
            ("Card Back",     self.master.choose_card_back),
            ("Upload to MPC", self.master.upload_to_mpc),
        ]:
            ctk.CTkButton(
                row2, text=text, width=110, height=30,
                font=ctk.CTkFont(size=12),
                command=cmd,
            ).pack(side="left", padx=3)


def _vsep(parent):
    ctk.CTkFrame(parent, width=1, fg_color="#252030").pack(
        side="left", fill="y", padx=8, pady=12
    )


def _micro_label(parent, text: str):
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=9),
        text_color="#5a5060",
        anchor="w",
    ).pack(anchor="w", padx=4, pady=(6, 2))
