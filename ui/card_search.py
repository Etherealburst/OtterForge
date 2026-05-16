"""
ui/card_search.py
-----------------
Barre de recherche de cartes Magic.
Délègue la recherche et l'ajout à MTGPrintFactoryApp.
"""

import customtkinter as ctk


class CardSearch(ctk.CTkFrame):
    """
    Barre de recherche avec champ texte et bouton Add.
    Appelle app.search_and_add_card(name) sur soumission.
    """

    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self._build()

    def _build(self):
        self.entry = ctk.CTkEntry(self, placeholder_text="Card name  or  s:SET cn:NUM", width=340)
        self.entry.pack(side="left", padx=5, pady=5)

        # Permet d'appuyer sur Entrée pour lancer la recherche
        self.entry.bind("<Return>", lambda e: self._on_add())

        self.add_btn = ctk.CTkButton(self, text="Add", command=self._on_add)
        self.add_btn.pack(side="left", padx=5)

    def _on_add(self):
        """Déclenche la recherche et l'ajout de la carte dans le deck."""
        name = self.entry.get().strip()
        if not name:
            return

        self.master.search_and_add_card(name)
        self.entry.delete(0, "end")
