"""
ui/card_search.py
-----------------
Barre de recherche de cartes Magic.
"""

import customtkinter as ctk


class CardSearch(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, height=46, corner_radius=0, fg_color="#1c1a20")
        self.master = master
        self.pack_propagate(False)
        self._build()

    def _build(self):
        ctk.CTkFrame(self, width=3, height=26, fg_color="#c04828",
                     corner_radius=2).pack(side="left", padx=(10, 8))

        ctk.CTkLabel(
            self, text="SEARCH",
            font=ctk.CTkFont(size=9),
            text_color="#5a5060",
        ).pack(side="left", padx=(0, 8))

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Card name  ·  s:SET cn:NUM  ·  1 Name (SET) #",
            width=460, height=30,
            font=ctk.CTkFont(size=12),
        )
        self.entry.pack(side="left", padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._on_add())

        self.add_btn = ctk.CTkButton(
            self, text="Add to Deck", width=110, height=30,
            font=ctk.CTkFont(size=12),
            command=self._on_add,
        )
        self.add_btn.pack(side="left")

    def _on_add(self):
        name = self.entry.get().strip()
        if not name:
            return
        self.master.search_and_add_card(name)
        self.entry.delete(0, "end")
