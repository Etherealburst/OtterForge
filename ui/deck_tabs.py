"""
ui/deck_tabs.py
---------------
Onglets de navigation entre les decks ouverts.
Affiche au maximum MAX_VISIBLE onglets avec flèches gauche/droite pour défiler.

Each arrow/tab button lives inside a fixed-size CTkFrame wrapper.
The wrapper's pack slot never changes size, so clicking arrows never
shifts positions — even though CTkButton ignores explicit width in configure().
"""

import copy
import tkinter as tk
import customtkinter as ctk

_BG = "#1c1a20"


class DeckTabs(ctk.CTkFrame):

    N_MAX = 16   # max slots ever created

    def __init__(self, master):
        super().__init__(master, height=36, corner_radius=0, fg_color=_BG)
        self.master = master
        self.pack_propagate(False)
        self.buttons: list[ctk.CTkButton] = []
        self._tab_wrappers: list[ctk.CTkFrame] = []
        self._context_popup = None
        self._tab_offset = 0
        self._visible_count = 4   # updated dynamically in _on_configure
        self._tab_btn_width = 110  # updated dynamically in _on_configure
        self._build_layout()
        self.render()

    # ── Build static layout (called once) ────────────────────────────────────

    def _build_layout(self) -> None:
        # Left-anchored fixed elements
        ctk.CTkFrame(self, width=3, fg_color="#34303e",
                     corner_radius=0).pack(side="left", fill="y")
        ctk.CTkLabel(
            self, text="DECKS",
            font=ctk.CTkFont(size=9),
            text_color="#a09aaa",
        ).pack(side="left", padx=(8, 4))
        ctk.CTkButton(
            self, text="−", width=26, height=24,
            fg_color="#28252e", hover_color="#922b21",
            text_color="#c4bfb8", font=ctk.CTkFont(size=15),
            command=self._delete_active_deck,
        ).pack(side="left", padx=(2, 4))

        lf = ctk.CTkFrame(self, fg_color=_BG, width=24, height=24, corner_radius=0)
        lf.pack(side="left", padx=(0, 2), pady=6)
        lf.pack_propagate(False)
        self._btn_left = ctk.CTkButton(
            lf, text="◀",
            fg_color=_BG, hover_color=_BG, text_color=_BG,
            font=ctk.CTkFont(size=11), state="disabled",
            command=self._scroll_left,
        )
        self._btn_left.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)

        # Tab slots — created but NOT packed yet; _update_visible_tabs handles packing
        self.buttons = []
        self._tab_wrappers = []
        for _ in range(self.N_MAX):
            tf = ctk.CTkFrame(self, fg_color=_BG, width=110, height=24, corner_radius=0)
            tf.pack_propagate(False)
            btn = ctk.CTkButton(
                tf, text="",
                fg_color=_BG, hover_color=_BG,
                text_color="#f0ece4",
                border_width=1, border_color=_BG,
                font=ctk.CTkFont(size=11),
                state="disabled",
            )
            btn.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
            self.buttons.append(btn)
            self._tab_wrappers.append(tf)

        # ▶ and + packed RIGHT immediately — always visible regardless of tab count
        self._btn_add = ctk.CTkButton(
            self, text="+", width=26, height=24,
            fg_color="#28252e", hover_color="#302c3a",
            text_color="#a09aaa", font=ctk.CTkFont(size=15),
            command=self._create_deck_dialog,
        )
        self._btn_add.pack(side="right", padx=(4, 8))

        self._rf_right = ctk.CTkFrame(self, fg_color=_BG, width=24, height=24, corner_radius=0)
        self._rf_right.pack_propagate(False)
        self._rf_right.pack(side="right", padx=(0, 2), pady=6)
        self._btn_right = ctk.CTkButton(
            self._rf_right, text="▶",
            fg_color=_BG, hover_color=_BG, text_color=_BG,
            font=ctk.CTkFont(size=11), state="disabled",
            command=self._scroll_right,
        )
        self._btn_right.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)

        self.bind("<Configure>", self._on_configure)

    # ── Slot visibility ───────────────────────────────────────────────────────

    def _update_visible_tabs(self) -> None:
        """Pack visible tab wrappers with dynamic width. ▶ and + are always anchored right."""
        n_decks = max(1, len(self.master.deck_manager.decks))
        effective_count = min(self._visible_count, n_decks)

        tab_w = self._tab_btn_width
        for i, (tf, btn) in enumerate(zip(self._tab_wrappers, self.buttons)):
            if i < effective_count:
                tf.configure(width=tab_w)
                btn.configure(width=tab_w)
                if not tf.winfo_ismapped():
                    tf.pack(side="left", padx=2, pady=6)
            else:
                tf.pack_forget()

    def _on_configure(self, event) -> None:
        if event.width < 100:
            return
        FIXED_W = 210   # separator + DECKS + − + ◀ + ▶ + + buttons + padding
        available_w = max(0, event.width - FIXED_W)
        n_decks = max(1, len(self.master.deck_manager.decks))
        new_count = max(1, min(self.N_MAX, available_w // 80))
        new_tab_w = max(80, min(200, available_w // new_count))
        if new_count == self._visible_count and new_tab_w == self._tab_btn_width:
            return
        self._visible_count = new_count
        self._tab_btn_width = new_tab_w
        self._update_visible_tabs()
        self.render()

    # ── Render (configure only — wrapper sizes are immutable) ─────────────────

    def render(self) -> None:
        decks = self.master.deck_manager.decks
        total = len(decks)
        active_idx = self.master.deck_manager.active_index
        MAX_TAB_CHARS = max(8, self._tab_btn_width // 9)

        self._update_visible_tabs()
        self._tab_offset = max(0, min(self._tab_offset, max(0, total - self._visible_count)))
        visible_end = min(self._tab_offset + self._visible_count, total)

        can_left = self._tab_offset > 0
        self._btn_left.configure(
            fg_color="#28252e" if can_left else _BG,
            hover_color="#302c3a" if can_left else _BG,
            text_color="#a09aaa" if can_left else _BG,
            state="normal" if can_left else "disabled",
        )

        for slot, btn in enumerate(self.buttons[:self._visible_count]):
            deck_idx = self._tab_offset + slot
            if deck_idx < total:
                deck = decks[deck_idx]
                is_active = (deck_idx == active_idx)
                label = (deck.name[:MAX_TAB_CHARS - 1] + "…"
                         if len(deck.name) > MAX_TAB_CHARS else deck.name)
                btn.configure(
                    text=label,
                    fg_color="#c04828" if is_active else "#28252e",
                    hover_color="#a83820" if is_active else "#302c3a",
                    border_color="#c04828" if is_active else "#34303e",
                    state="normal",
                    command=lambda idx=deck_idx: self._select(idx),
                )
                btn.bind("<Button-3>", lambda e, idx=deck_idx: self._show_context_menu(e, idx))
            else:
                btn.configure(
                    text="", fg_color=_BG, hover_color=_BG,
                    border_color=_BG, state="disabled",
                    command=lambda: None,
                )
                btn.bind("<Button-3>", lambda e: None)

        can_right = visible_end < total
        self._btn_right.configure(
            fg_color="#28252e" if can_right else _BG,
            hover_color="#302c3a" if can_right else _BG,
            text_color="#a09aaa" if can_right else _BG,
            state="normal" if can_right else "disabled",
        )

    # ── Pagination ───────────────────────────────────────────────────────────

    def _scroll_left(self) -> None:
        self._tab_offset = max(0, self._tab_offset - 1)
        self.render()

    def _scroll_right(self) -> None:
        total = len(self.master.deck_manager.decks)
        self._tab_offset = min(max(0, total - self._visible_count), self._tab_offset + 1)
        self.render()

    def _ensure_tab_visible(self, index: int) -> None:
        if index < self._tab_offset:
            self._tab_offset = index
        elif index >= self._tab_offset + self._visible_count:
            self._tab_offset = index - self._visible_count + 1

    # ── Sélection ────────────────────────────────────────────────────────────

    def _select(self, index: int) -> None:
        if index == self.master.deck_manager.active_index:
            return
        self.master.deck_manager.set_active(index)
        deck = self.master.deck_manager.active_deck()
        self.master._sync_back_from_active_deck()
        self.master.workspace.load_cards(deck.cards)
        self.master.statusbar.set_status(f"Active deck: {deck.name}")
        self._ensure_tab_visible(index)
        self.render()
        # Defer sidebar rebuild so the workspace canvas appears first
        self.after(150, self.master.sidebar.refresh)

    # ── Menu contextuel ───────────────────────────────────────────────────────

    def _show_context_menu(self, event: tk.Event, index: int) -> None:
        self._close_context_popup()
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"+{event.x_root}+{event.y_root}")
        self._context_popup = popup

        frame = ctk.CTkFrame(popup, fg_color="#28252e", corner_radius=8)
        frame.pack(padx=2, pady=2)

        font = ctk.CTkFont(size=13)
        kw = dict(font=font, width=160, height=36, anchor="w")

        def _cmd(fn):
            def _():
                self._close_context_popup()
                fn()
            return _

        ctk.CTkButton(frame, text="  Rename",
                      command=_cmd(lambda: self._rename_deck_dialog(index)), **kw,
                      ).pack(padx=6, pady=(6, 2))
        ctk.CTkButton(frame, text="  Duplicate",
                      command=_cmd(lambda: self._duplicate_deck(index)), **kw,
                      ).pack(padx=6, pady=(2, 2))
        ctk.CTkButton(frame, text="  Delete", fg_color="#581e10", hover_color="#922b21",
                      command=_cmd(lambda: self._delete_deck(index)), **kw,
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
        dialog.title("Rename deck")
        dialog.geometry("300x130")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(dialog, text="New name:").pack(pady=(16, 4))
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
            self._ensure_tab_visible(index)
            self.render()
            self.master.statusbar.set_status(f"Deck renamed: {name}")
            dialog.destroy()

        entry.bind("<Return>", lambda e: confirm())
        ctk.CTkButton(dialog, text="Rename", command=confirm).pack(pady=8)

    def _delete_active_deck(self) -> None:
        self._delete_deck(self.master.deck_manager.active_index)

    def _delete_deck(self, index: int) -> None:
        decks = self.master.deck_manager.decks
        if len(decks) <= 1:
            self.master.statusbar.set_status("Cannot delete the only deck.")
            return
        deck_name = decks[index].name
        dialog = ctk.CTkToplevel(self)
        dialog.title("Delete deck")
        dialog.geometry("320x140")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(dialog, text=f'Delete "{deck_name}"?',
                     font=ctk.CTkFont(size=14)).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="This action is irreversible.",
                     text_color="#c4bfb8").pack(pady=(0, 12))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()

        def confirm():
            self.master._delete_deck_file(deck_name)
            self.master.deck_manager.delete_deck(index)
            new_active = self.master.deck_manager.active_index
            self._ensure_tab_visible(new_active)
            self.render()
            active = self.master.deck_manager.active_deck()
            if active:
                self.master._sync_back_from_active_deck()
                self.master.workspace.load_cards(active.cards)
                self.master.sidebar.refresh()
                self.master.statusbar.set_status(f"Deck deleted. Active deck: {active.name}")
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Delete", fg_color="#c0392b", hover_color="#922b21",
                      command=confirm).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#581e10", hover_color="#3a1a10",
                      command=dialog.destroy).pack(side="left", padx=8)

    # ── Créer / dupliquer ─────────────────────────────────────────────────────

    def _duplicate_deck(self, index: int) -> None:
        from engine.deck_manager import Deck
        source = self.master.deck_manager.decks[index]
        new_deck = Deck(f"{source.name} (copy)")
        new_deck.cards = copy.deepcopy(source.cards)
        new_deck.back_image = source.back_image
        self.master.deck_manager.decks.append(new_deck)
        new_index = len(self.master.deck_manager.decks) - 1
        self.master.deck_manager.set_active(new_index)
        self.master.deck_manager.save_deck_at(new_deck, self.master._deck_path(new_deck.name))
        self._ensure_tab_visible(new_index)
        self.render()
        self.master.workspace.load_cards(new_deck.cards)
        self.master.sidebar.refresh()
        self.master.statusbar.set_status(f"Deck duplicated: {new_deck.name}")

    def _create_deck_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("New deck")
        dialog.geometry("300x130")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(dialog, text="Deck name:").pack(pady=(16, 4))
        entry = ctk.CTkEntry(dialog, width=220, placeholder_text="My deck...")
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
            self._ensure_tab_visible(new_index)
            self.render()
            deck = self.master.deck_manager.active_deck()
            self.master.workspace.load_cards(deck.cards)
            self.master.sidebar.refresh()
            self.master.statusbar.set_status(f"New deck created: {name}")
            dialog.destroy()

        entry.bind("<Return>", lambda e: confirm())
        ctk.CTkButton(dialog, text="Create", command=confirm).pack(pady=8)
