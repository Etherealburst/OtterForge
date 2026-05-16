"""
ui/deck_sidebar.py
------------------
Panneau latéral gauche affichant la liste des cartes du deck actif.
Chaque ligne expose des boutons -/+ et × pour modifier le deck directement.
"""

import customtkinter as ctk


class DeckSidebar(ctk.CTkFrame):
    """Liste les cartes du deck actif avec contrôles de quantité et suppression."""

    WIDTH = 240

    def __init__(self, master, app):
        super().__init__(master, width=self.WIDTH)
        self.app = app
        self.pack_propagate(False)

        # ------------------------------------------------------------------
        # HEADER
        # ------------------------------------------------------------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 2))

        ctk.CTkLabel(
            header,
            text="Deck",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(side="left")

        self.total_label = ctk.CTkLabel(
            header,
            text="",
            text_color="#8a7040",
            font=ctk.CTkFont(size=11),
        )
        self.total_label.pack(side="right")

        # ------------------------------------------------------------------
        # LISTE SCROLLABLE
        # ------------------------------------------------------------------
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # REFRESH
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recharge l'affichage à partir du deck actif."""
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        deck = self.app.deck_manager.active_deck()
        if not deck:
            self.total_label.configure(text="")
            return

        total = sum(c.count for c in deck.cards)
        self.total_label.configure(text=f"{total} card{'s' if total != 1 else ''}")

        for card in deck.cards:
            self._build_row(card)

    def _build_row(self, card) -> None:
        """Construit une ligne pour une carte avec ses contrôles."""
        row = ctk.CTkFrame(self.list_frame, fg_color="#1a1408")
        row.pack(fill="x", pady=2, padx=2)

        # Nom tronqué
        name = card.name if len(card.name) <= 16 else card.name[:15] + "…"
        ctk.CTkLabel(
            row,
            text=name,
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(6, 2), pady=4, expand=True, fill="x")

        # Contrôles : [-] [count] [+] [×]
        ctrl = ctk.CTkFrame(row, fg_color="transparent")
        ctrl.pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            ctrl, text="-", width=22, height=22,
            font=ctk.CTkFont(size=12),
            command=lambda c=card: self._change_count(c, -1),
        ).pack(side="left", padx=1)

        ctk.CTkLabel(
            ctrl,
            text=str(card.count),
            width=24,
            font=ctk.CTkFont(size=11),
        ).pack(side="left")

        ctk.CTkButton(
            ctrl, text="+", width=22, height=22,
            font=ctk.CTkFont(size=12),
            command=lambda c=card: self._change_count(c, 1),
        ).pack(side="left", padx=1)

        ctk.CTkButton(
            ctrl, text="×", width=22, height=22,
            font=ctk.CTkFont(size=12),
            fg_color="#2a2010", hover_color="#922b21",
            command=lambda c=card: self._remove_card(c),
        ).pack(side="left", padx=(4, 0))

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------

    def _change_count(self, card, delta: int) -> None:
        """Incrémente ou décrémente le count d'une carte."""
        new_count = card.count + delta
        if new_count <= 0:
            self._remove_card(card)
            return
        card.count = new_count
        self._sync()

    def _remove_card(self, card) -> None:
        """Supprime une carte du deck."""
        deck = self.app.deck_manager.active_deck()
        if deck:
            deck.cards = [c for c in deck.cards if c is not card]
        self._sync()

    def _sync(self) -> None:
        """Rafraîchit sidebar + workspace + auto-save."""
        deck = self.app.deck_manager.active_deck()
        if deck:
            self.app.workspace.load_cards(deck.cards)
        self.refresh()
        self.app._auto_save()
