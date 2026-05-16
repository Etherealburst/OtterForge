"""
ui/toolbar.py
-------------
Barre d'outils principale affichée en haut de la fenêtre.
Tous les boutons délèguent leurs actions à l'app (MTGPrintFactoryApp).
"""

import customtkinter as ctk


class Toolbar(ctk.CTkFrame):
    """Barre d'outils avec boutons de gestion de deck et d'export."""

    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self._build()

    def _build(self):
        buttons = [
            ("Import Deck",        self.master.load_deck_file),
            ("Save Deck",          self.master.save_deck),
            ("Import Deck (TXT / Moxfield)", self.master.import_txt_deck),
            ("Export Print Sheets",self.master.export_print_sheets),
            ("Choose Card Back",   self.master.choose_card_back),
            ("Upload to MPC",      self.master.upload_to_mpc),
        ]

        for label, command in buttons:
            btn = ctk.CTkButton(self, text=label, command=command)
            btn.pack(side="left", padx=5, pady=5)
