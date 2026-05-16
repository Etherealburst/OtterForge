"""
ui/deck_tabs.py
---------------
Onglets de navigation entre les decks ouverts.
  - Bouton "−" à gauche : supprime le deck actif (avec confirmation)
  - Bouton "+" à droite : crée un nouveau deck
  - Clic droit sur un onglet : menu CTk stylé (Renommer / Supprimer)
"""

import tkinter as tk
import customtkinter as ctk


class DeckTabs(ctk.CTkFrame):
    """Affiche un bouton par deck ouvert et permet de switcher entre eux."""

    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.buttons: list[ctk.CTkButton] = []
        self._context_popup = None
        self.render()

    def render(self) -> None:
        """Recrée tous les widgets d'onglets depuis la liste des decks."""
        # Détruire TOUS les enfants (onglets + boutons ± des rendus précédents)
        for widget in self.winfo_children():
            widget.destroy()
        self.buttons.clear()

        # Bouton "−" : supprime le deck actif
        ctk.CTkButton(
            self,
            text="−",
            width=32,
            fg_color="gray30",
            hover_color="#922b21",
            font=ctk.CTkFont(size=16),
            command=self._delete_active_deck,
        ).pack(side="left", padx=(5, 2), pady=5)

        for i, deck in enumerate(self.master.deck_manager.decks):
            btn = ctk.CTkButton(
                self,
                text=deck.name,
                command=lambda idx=i: self._select(idx),
            )
            btn.pack(side="left", padx=5, pady=5)
            btn.bind("<Button-3>", lambda e, idx=i: self._show_context_menu(e, idx))
            self.buttons.append(btn)

        # Bouton "+" : crée un nouveau deck
        ctk.CTkButton(
            self,
            text="+",
            width=32,
            command=self._create_deck_dialog,
        ).pack(side="left", padx=(0, 5), pady=5)

    def _select(self, index: int) -> None:
        """Switche vers le deck sélectionné et met à jour l'UI."""
        self.master.deck_manager.set_active(index)
        deck = self.master.deck_manager.active_deck()

        self.master._sync_back_from_active_deck()
        self.master.workspace.load_cards(deck.cards)
        self.master.sidebar.refresh()
        self.master.statusbar.set_status(f"Deck actif : {deck.name}")

    # ------------------------------------------------------------------
    # MENU CONTEXTUEL (clic droit) — popup CTk lisible
    # ------------------------------------------------------------------

    def _show_context_menu(self, event: tk.Event, index: int) -> None:
        """Affiche un menu contextuel CTk bien dimensionné."""
        self._close_context_popup()

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"+{event.x_root}+{event.y_root}")
        self._context_popup = popup

        frame = ctk.CTkFrame(popup, fg_color="gray25", corner_radius=8)
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
            fg_color="gray35", hover_color="#922b21",
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
        """Ouvre une fenêtre de dialogue pour renommer le deck."""
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
        """Supprime le deck actuellement actif."""
        self._delete_deck(self.master.deck_manager.active_index)

    def _delete_deck(self, index: int) -> None:
        """Demande confirmation puis supprime le deck."""
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
            dialog,
            text=f'Supprimer "{deck_name}" ?',
            font=ctk.CTkFont(size=14),
        ).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="Cette action est irréversible.").pack(pady=(0, 12))

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
        ctk.CTkButton(btn_frame, text="Annuler", command=dialog.destroy).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # CRÉER UN NOUVEAU DECK
    # ------------------------------------------------------------------

    def _create_deck_dialog(self) -> None:
        """Ouvre une fenêtre de dialogue pour saisir le nom du nouveau deck."""
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
            self.render()
            new_index = len(self.master.deck_manager.decks) - 1
            self._select(new_index)
            self.master.statusbar.set_status(f"Nouveau deck créé : {name}")
            dialog.destroy()

        entry.bind("<Return>", lambda e: confirm())
        ctk.CTkButton(dialog, text="Créer", command=confirm).pack(pady=8)
