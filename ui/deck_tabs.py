"""
ui/deck_tabs.py
---------------
Onglets de navigation entre les decks ouverts.
"""

import tkinter as tk
import customtkinter as ctk


class DeckTabs(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, height=40, corner_radius=0, fg_color="#0d0c0e")
        self.master = master
        self.pack_propagate(False)
        self.buttons: list[ctk.CTkButton] = []
        self._context_popup = None
        self.render()

    def render(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self.buttons.clear()

        active_idx = self.master.deck_manager.active_index

        ctk.CTkFrame(self, width=3, fg_color="#252030",
                     corner_radius=0).pack(side="left", fill="y")

        ctk.CTkLabel(
            self, text="DECKS",
            font=ctk.CTkFont(size=9),
            text_color="#5a5060",
        ).pack(side="left", padx=(8, 4))

        ctk.CTkButton(
            self, text="−", width=28, height=26,
            fg_color="#1a1820", hover_color="#922b21",
            text_color="#c4bfb8",
            font=ctk.CTkFont(size=16),
            command=self._delete_active_deck,
        ).pack(side="left", padx=(2, 4))

        for i, deck in enumerate(self.master.deck_manager.decks):
            is_active = (i == active_idx)
            btn = ctk.CTkButton(
                self,
                text=deck.name,
                width=max(80, len(deck.name) * 8 + 20),
                height=26,
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                fg_color="#c04828" if is_active else "#1a1820",
                hover_color="#a83820" if is_active else "#221e2c",
                text_color="#f0ece4",
                border_width=1 if not is_active else 0,
                border_color="#252030",
                command=lambda idx=i: self._select(idx),
            )
            btn.pack(side="left", padx=3, pady=7)
            btn.bind("<Button-3>", lambda e, idx=i: self._show_context_menu(e, idx))
            self.buttons.append(btn)

        ctk.CTkButton(
            self, text="+", width=28, height=26,
            fg_color="#1a1820", hover_color="#221e2c",
            text_color="#5a5060",
            font=ctk.CTkFont(size=16),
            command=self._create_deck_dialog,
        ).pack(side="left", padx=(2, 8))

    def _select(self, index: int) -> None:
        self.master.deck_manager.set_active(index)
        deck = self.master.deck_manager.active_deck()
        self.master._sync_back_from_active_deck()
        self.master.workspace.load_cards(deck.cards)
        self.master.sidebar.refresh()
        self.master.statusbar.set_status(f"Deck actif : {deck.name}")
        self.render()

    # ------------------------------------------------------------------
    # MENU CONTEXTUEL
    # ------------------------------------------------------------------

    def _show_context_menu(self, event: tk.Event, index: int) -> None:
        self._close_context_popup()

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"+{event.x_root}+{event.y_root}")
        self._context_popup = popup

        frame = ctk.CTkFrame(popup, fg_color="#1a1820", corner_radius=8)
        frame.pack(padx=2, pady=2)

        font = ctk.CTkFont(size=13)
        kw = dict(font=font, width=160, height=36, anchor="w")

        def _cmd(fn):
            def _():
                self._close_context_popup()
                fn()
            return _

        ctk.CTkButton(
            frame, text="  Renommer",
            command=_cmd(lambda: self._rename_deck_dialog(index)),
            **kw,
        ).pack(padx=6, pady=(6, 2))

        ctk.CTkButton(
            frame, text="  Supprimer",
            fg_color="#581e10", hover_color="#922b21",
            command=_cmd(lambda: self._delete_deck(index)),
            **kw,
        ).pack(padx=6, pady=(2, 6))

        def _on_focus_out(e):
            focused = str(popup.focus_get() or "")
            if not focused.startswith(str(popup)):
                self._close_context_popup()

        popup.bind("<FocusOut>", _on_focus_out)
        popup.bind("<Escape>", lambda e: self._close_context_popup())
        popup.focus_force()

    def _close_context_popup(self) -> None:
        if self._context_popup:
            try:
                self._context_popup.destroy()
            except Exception:
                pass
            self._context_popup = None

    def _rename_deck_dialog(self, index: int) -> None:
        current_name = self.master.deck_manager.decks[index].name

        dialog = ctk.CTkToplevel(self)
        dialog.title("Renommer le deck")
        dialog.geometry("300x130")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(dialog, text="Nouveau nom :").pack(pady=(16, 4))

        entry = ctk.CTkEntry(dialog, width=220)
        entry.insert(0, current_name)
        entry.select_range(0, "end")
        entry.pack(pady=4)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if not name:
                return
            old_name = self.master.deck_manager.decks[index].name
            self.master._delete_deck_file(old_name)
            self.master.deck_manager.rename_deck(index, name)
            deck = self.master.deck_manager.decks[index]
            self.master.deck_manager.save_deck_at(deck, self.master._deck_path(name))
            self.render()
            self.master.statusbar.set_status(f"Deck renommé : {name}")
            dialog.destroy()

        entry.bind("<Return>", lambda e: confirm())
        ctk.CTkButton(dialog, text="Renommer", command=confirm).pack(pady=8)

    def _delete_active_deck(self) -> None:
        self._delete_deck(self.master.deck_manager.active_index)

    def _delete_deck(self, index: int) -> None:
        decks = self.master.deck_manager.decks
        if len(decks) <= 1:
            self.master.statusbar.set_status("Impossible de supprimer le seul deck.")
            return

        deck_name = decks[index].name

        dialog = ctk.CTkToplevel(self)
        dialog.title("Supprimer le deck")
        dialog.geometry("320x140")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(
            dialog, text=f'Supprimer "{deck_name}" ?',
            font=ctk.CTkFont(size=14),
        ).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="Cette action est irréversible.",
                     text_color="#c4bfb8").pack(pady=(0, 12))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()

        def confirm():
            self.master._delete_deck_file(deck_name)
            self.master.deck_manager.delete_deck(index)
            self.render()
            active = self.master.deck_manager.active_deck()
            if active:
                self.master._sync_back_from_active_deck()
                self.master.workspace.load_cards(active.cards)
                self.master.sidebar.refresh()
                self.master.statusbar.set_status(f"Deck supprimé. Deck actif : {active.name}")
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Supprimer", fg_color="#c0392b", hover_color="#922b21",
                      command=confirm).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Annuler", fg_color="#581e10", hover_color="#3a1a10",
                      command=dialog.destroy).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # CRÉER UN NOUVEAU DECK
    # ------------------------------------------------------------------

    def _create_deck_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Nouveau deck")
        dialog.geometry("300x130")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(dialog, text="Nom du deck :").pack(pady=(16, 4))

        entry = ctk.CTkEntry(dialog, width=220, placeholder_text="Mon deck...")
        entry.pack(pady=4)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if not name:
                return
            self.master.deck_manager.create_deck(name)
            self.master._auto_save()
            new_index = len(self.master.deck_manager.decks) - 1
            self.master.deck_manager.set_active(new_index)
            self.render()
            deck = self.master.deck_manager.active_deck()
            self.master.workspace.load_cards(deck.cards)
            self.master.sidebar.refresh()
            self.master.statusbar.set_status(f"Nouveau deck créé : {name}")
            dialog.destroy()

        entry.bind("<Return>", lambda e: confirm())
        ctk.CTkButton(dialog, text="Créer", command=confirm).pack(pady=8)
