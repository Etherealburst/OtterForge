"""
ui/deck_sidebar.py
------------------
Panneau latéral gauche affichant la liste des cartes du deck actif.
Comprend un filtre rapide par nom.
"""

import customtkinter as ctk


class DeckSidebar(ctk.CTkFrame):

    WIDTH = 248

    def __init__(self, master, app):
        super().__init__(master, width=self.WIDTH, corner_radius=0, fg_color="#0d0c0e")
        self.app = app
        self.pack_propagate(False)

        # ── Header ──────────────────────────────────────────────────────────
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

        # ── Barre de filtre ─────────────────────────────────────────────────
        filter_frame = ctk.CTkFrame(self, fg_color="#131118", corner_radius=4)
        filter_frame.pack(fill="x", padx=8, pady=(0, 4))

        self._filter_var = ctk.StringVar()

        self._filter_clear_btn = ctk.CTkButton(
            filter_frame, text="×", width=22, height=22,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#922b21",
            text_color="#252030",
            command=lambda: self._filter_var.set(""),
        )
        self._filter_clear_btn.pack(side="right", padx=(0, 4), pady=3)

        self._filter_entry = ctk.CTkEntry(
            filter_frame,
            textvariable=self._filter_var,
            placeholder_text="Filtrer les cartes…",
            height=28,
            font=ctk.CTkFont(size=11),
            border_width=0,
            fg_color="#131118",
            text_color="#f0ece4",
            placeholder_text_color="#5a5060",
        )
        self._filter_entry.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=3)
        self._filter_var.trace_add("write", self._on_filter_change)

        # ── Liste des cartes ─────────────────────────────────────────────────
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def _on_filter_change(self, *_) -> None:
        has_text = bool(self._filter_var.get())
        self._filter_clear_btn.configure(
            text_color="#c4bfb8" if has_text else "#252030",
            hover_color="#922b21" if has_text else "#1a1820",
        )
        self.refresh()

    def refresh(self) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        deck = self.app.deck_manager.active_deck()
        if not deck:
            self.total_label.configure(text="")
            return

        total = sum(c.count for c in deck.cards)
        self.total_label.configure(text=f"{total} card{'s' if total != 1 else ''}")

        query = self._filter_var.get().strip().lower()
        cards = deck.cards
        if query:
            cards = [c for c in cards if query in c.name.lower()]

        if not cards:
            msg = (f'Aucune carte "{query}"' if query
                   else "Aucune carte dans ce deck.\nUtilise la barre de recherche\npour en ajouter.")
            ctk.CTkLabel(
                self.list_frame, text=msg,
                text_color="#5a5060",
                font=ctk.CTkFont(size=10),
                justify="center",
            ).pack(pady=20)
            return

        for card in cards:
            self._build_row(card)

    def _build_row(self, card) -> None:
        row = ctk.CTkFrame(self.list_frame, fg_color="#131118", corner_radius=4)
        row.pack(fill="x", pady=2, padx=2)

        # Clic sur la ligne → envoie la carte à l'inspecteur
        row.bind("<Button-1>", lambda e, c=card: self._inspect(c))

        name = card.name if len(card.name) <= 17 else card.name[:16] + "…"
        name_lbl = ctk.CTkLabel(
            row, text=name, anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#f0ece4",
            cursor="hand2",
        )
        name_lbl.pack(side="left", padx=(8, 2), pady=5, expand=True, fill="x")
        name_lbl.bind("<Button-1>", lambda e, c=card: self._inspect(c))

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

    def _inspect(self, card) -> None:
        if hasattr(self.app, "inspector"):
            self.app.inspector.show_card(card)

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
        if hasattr(self.app, "inspector"):
            self.app.inspector.refresh_stats()
