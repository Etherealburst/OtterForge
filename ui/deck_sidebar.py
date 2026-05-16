"""
ui/deck_sidebar.py
------------------
Panneau latéral gauche affichant la liste des cartes du deck actif.
"""

import customtkinter as ctk


class DeckSidebar(ctk.CTkFrame):

    WIDTH = 248

    def __init__(self, master, app):
        super().__init__(master, width=self.WIDTH, corner_radius=0, fg_color="#0d0c0e")
        self.app = app
        self.pack_propagate(False)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=0, pady=(10, 4))

        ctk.CTkFrame(header, width=3, fg_color="#c04828",
                     corner_radius=2).pack(side="left", fill="y", padx=(8, 6))

        ctk.CTkLabel(
            header, text="DECK",
            font=ctk.CTkFont(size=9),
            text_color="#5a5060",
            anchor="w",
        ).pack(side="left")

        self.total_label = ctk.CTkLabel(
            header, text="",
            text_color="#c4bfb8",
            font=ctk.CTkFont(size=11),
        )
        self.total_label.pack(side="right", padx=8)

        ctk.CTkFrame(self, height=1, fg_color="#1a1820",
                     corner_radius=0).pack(fill="x", padx=8, pady=(0, 4))

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def refresh(self) -> None:
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
        row = ctk.CTkFrame(self.list_frame, fg_color="#131118", corner_radius=4)
        row.pack(fill="x", pady=2, padx=2)

        name = card.name if len(card.name) <= 17 else card.name[:16] + "…"
        ctk.CTkLabel(
            row, text=name, anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#f0ece4",
        ).pack(side="left", padx=(8, 2), pady=5, expand=True, fill="x")

        ctrl = ctk.CTkFrame(row, fg_color="transparent")
        ctrl.pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            ctrl, text="−", width=22, height=22,
            font=ctk.CTkFont(size=13),
            fg_color="#1a1820", hover_color="#221e2c",
            text_color="#c4bfb8",
            command=lambda c=card: self._change_count(c, -1),
        ).pack(side="left", padx=1)

        ctk.CTkLabel(
            ctrl, text=str(card.count), width=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#c04828",
        ).pack(side="left")

        ctk.CTkButton(
            ctrl, text="+", width=22, height=22,
            font=ctk.CTkFont(size=13),
            fg_color="#1a1820", hover_color="#221e2c",
            text_color="#c4bfb8",
            command=lambda c=card: self._change_count(c, 1),
        ).pack(side="left", padx=1)

        ctk.CTkButton(
            ctrl, text="×", width=22, height=22,
            font=ctk.CTkFont(size=13),
            fg_color="#1a1820", hover_color="#922b21",
            text_color="#5a5060",
            command=lambda c=card: self._remove_card(c),
        ).pack(side="left", padx=(4, 0))

    def _change_count(self, card, delta: int) -> None:
        new_count = card.count + delta
        if new_count <= 0:
            self._remove_card(card)
            return
        card.count = new_count
        self._sync()

    def _remove_card(self, card) -> None:
        deck = self.app.deck_manager.active_deck()
        if deck:
            deck.cards = [c for c in deck.cards if c is not card]
        self._sync()

    def _sync(self) -> None:
        deck = self.app.deck_manager.active_deck()
        if deck:
            self.app.workspace.load_cards(deck.cards)
        self.refresh()
        self.app._auto_save()
