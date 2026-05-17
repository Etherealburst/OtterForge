"""
ui/toolbar.py
-------------
Barre d'outils principale — compacte avec logo, groupes d'actions et tooltips.
"""

import os
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw


class Toolbar(ctk.CTkFrame):

    HEIGHT = 52

    def __init__(self, master):
        super().__init__(master, height=self.HEIGHT, corner_radius=0, fg_color="#0d0c0e")
        self.master = master
        self.pack_propagate(False)
        self._build()

    def _build(self):
        # ── Branding ──────────────────────────────────────────────────────
        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(side="left", fill="y", padx=(12, 4))

        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "OtterForge_Image.jpg"
        )
        try:
            pil_img = Image.open(logo_path).resize((38, 38), Image.LANCZOS).convert("RGBA")
            mask = Image.new("L", (38, 38), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 38, 38), fill=255)
            pil_img.putalpha(mask)
            ctk_logo = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(38, 38))
            ctk.CTkLabel(brand, image=ctk_logo, text="").pack(side="left", padx=(0, 10))
        except Exception:
            pass

        ctk.CTkLabel(
            brand, text="OTTERFORGE",
            font=ctk.CTkFont(family="Georgia", size=15, weight="bold"),
            text_color="#f0ece4",
        ).pack(side="left")

        # ── Séparateur ────────────────────────────────────────────────────
        _vsep(self)

        # ── Groupe DECK ───────────────────────────────────────────────────
        deck_grp = ctk.CTkFrame(self, fg_color="transparent")
        deck_grp.pack(side="left", fill="y", padx=4)

        _micro_label(deck_grp, "DECK")

        row = ctk.CTkFrame(deck_grp, fg_color="transparent")
        row.pack(pady=(0, 6))

        _tool_btn(row, "↑ Open",   self.master.load_deck_file,   "Charger un deck JSON")
        _tool_btn(row, "↓ Save",   self.master.save_deck,        "Sauvegarder le deck actif")
        _tool_btn(row, "⬇ Import", self.master.import_txt_deck,  "Importer un fichier TXT / Moxfield")

        # ── Séparateur ────────────────────────────────────────────────────
        _vsep(self)

        # ── Groupe OUTPUT ─────────────────────────────────────────────────
        out_grp = ctk.CTkFrame(self, fg_color="transparent")
        out_grp.pack(side="left", fill="y", padx=4)

        _micro_label(out_grp, "OUTPUT")

        row2 = ctk.CTkFrame(out_grp, fg_color="transparent")
        row2.pack(pady=(0, 6))

        _tool_btn(row2, "⊞ Export",   self.master.export_print_sheets, "Générer les feuilles d'impression")
        _tool_btn(row2, "◧ Card Back", self.master.choose_card_back,   "Choisir l'image d'endos du deck")
        _tool_btn(row2, "⬆ MPC",       self.master.upload_to_mpc,      "Uploader sur MakePlayingCards.com")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _vsep(parent) -> None:
    ctk.CTkFrame(parent, width=1, fg_color="#252030").pack(
        side="left", fill="y", padx=10, pady=10
    )


def _micro_label(parent, text: str) -> None:
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=9),
        text_color="#5a5060",
        anchor="w",
    ).pack(anchor="w", padx=4, pady=(4, 2))


def _tool_btn(parent, text: str, command, tooltip: str = "") -> ctk.CTkButton:
    btn = ctk.CTkButton(
        parent, text=text, width=90, height=26,
        font=ctk.CTkFont(size=11),
        command=command,
    )
    btn.pack(side="left", padx=2)
    if tooltip:
        _Tooltip(btn, tooltip)
    return btn


class _Tooltip:
    """Tooltip léger qui apparaît sous le widget au survol."""

    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip:
            return
        w = self._widget
        x = w.winfo_rootx()
        y = w.winfo_rooty() + w.winfo_height() + 4
        self._tip = tk.Toplevel(w)
        self._tip.wm_overrideredirect(True)
        self._tip.geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self._tip, text=self._text,
            bg="#1a1820", fg="#c4bfb8",
            font=("Arial", 10),
            padx=10, pady=5,
            relief="flat",
        )
        lbl.pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
