"""
ui/deck_sidebar.py
------------------
Panneau latéral gauche affichant la liste des cartes du deck actif.
Comprend un filtre rapide par nom et trois états : normal / compact / hidden.
"""

import os
import threading
import tkinter as tk
import customtkinter as ctk
from collections import Counter
from PIL import Image


class _Tooltip:
    """Petit popup qui affiche le texte complet au survol d'un widget."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, event: tk.Event) -> None:
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 10
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            tw, text=self._text,
            background="#3a3548", foreground="#f0ece4",
            relief="solid", borderwidth=1,
            highlightbackground="#c04828", highlightthickness=1,
            font=("Segoe UI", 20),
            padx=16, pady=10,
        )
        lbl.pack()

    def _hide(self, event: tk.Event) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


class DeckSidebar(ctk.CTkFrame):

    WIDTH = 280
    COMPACT_WIDTH = 72

    def __init__(self, master, app):
        super().__init__(master, width=self.WIDTH, corner_radius=0, fg_color="#1c1a20")
        self.app = app
        self.pack_propagate(False)
        self._state = 'normal'
        self._current_w = self.WIDTH   # logical px — source of truth for drag handle
        self._thumb_generation = 0  # incremented each refresh to cancel stale callbacks
        self._list_gen = 0          # incremented each rebuild to cancel stale batch
        self._resize_after_id = None
        self._rebuild_after_id = None
        self.bind("<Configure>", self._on_sidebar_configure)

        # ── Header compact ───────────────────────────────────────────────────
        header = ctk.CTkFrame(self, height=22, fg_color="transparent")
        header.pack(fill="x", padx=0, pady=(1, 0))
        header.pack_propagate(False)

        ctk.CTkFrame(header, width=3, fg_color="#c04828",
                     corner_radius=2).pack(side="left", fill="y", padx=(8, 6))

        ctk.CTkLabel(
            header, text="DECK",
            font=ctk.CTkFont(size=10),
            text_color="#a09aaa",
            anchor="w",
        ).pack(side="left")

        self.total_label = ctk.CTkLabel(
            header, text="",
            text_color="#c4bfb8",
            font=ctk.CTkFont(size=10),
        )
        self.total_label.pack(side="right", padx=8)

        # Clickable toggle icon — always visible in normal/compact states
        _toggle_lbl = ctk.CTkLabel(
            header, text="◧",
            font=ctk.CTkFont(size=11),
            text_color="#c04828",
            cursor="hand2",
            width=18,
        )
        _toggle_lbl.pack(side="right", padx=(0, 4))
        _toggle_lbl.bind("<Button-1>", lambda e: self.app.toggle_sidebar())
        _Tooltip(_toggle_lbl, "Toggle sidebar  (Ctrl+B)")

        ctk.CTkFrame(self, height=1, fg_color="#28252e",
                     corner_radius=0).pack(fill="x", padx=8, pady=(1, 1))

        # ── Barre de filtre ─────────────────────────────────────────────────
        self._filter_frame = ctk.CTkFrame(self, fg_color="#221f28", corner_radius=4)
        self._filter_frame.pack(fill="x", padx=8, pady=(0, 4))

        self._filter_var = ctk.StringVar()

        self._filter_clear_btn = ctk.CTkButton(
            self._filter_frame, text="×", width=22, height=22,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#922b21",
            text_color="#34303e",
            command=lambda: self._filter_var.set(""),
        )
        self._filter_clear_btn.pack(side="right", padx=(0, 4), pady=3)

        self._filter_entry = ctk.CTkEntry(
            self._filter_frame,
            textvariable=self._filter_var,
            placeholder_text="Filter cards…",
            height=32,
            font=ctk.CTkFont(size=11),
            border_width=0,
            fg_color="#221f28",
            text_color="#f0ece4",
            placeholder_text_color="#a09aaa",
        )
        self._filter_entry.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=3)
        self._filter_var.trace_add("write", self._on_filter_change)

        # ── Liste des cartes ─────────────────────────────────────────────────
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # ── Thumbnails (mode compact uniquement) ─────────────────────────────
        self._thumb_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        # Not packed initially — shown only in compact state

    def _on_sidebar_configure(self, event) -> None:
        """Rebuilds the card list when the sidebar is resized (sash drag)."""
        if self._state != 'normal':
            return
        new_w = self.winfo_width()
        if new_w < 80 or abs(new_w - self._current_w) < 15:
            return
        self._current_w = new_w
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(200, self._rebuild_list)

    # ══════════════════════════════════════════════════════════════════════════
    # STATE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def set_state(self, state: str, width: int | None = None) -> None:
        """Switch between 'normal', 'compact', and 'hidden'. width overrides normal width."""
        self._state = state
        if state == 'normal':
            w = width if width is not None else self.WIDTH
            self._current_w = w
            self.configure(width=w)
            self._filter_frame.pack(fill="x", padx=8, pady=(0, 4))
            self.list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self._thumb_frame.pack_forget()
        elif state == 'compact':
            self._current_w = self.COMPACT_WIDTH
            self.configure(width=self.COMPACT_WIDTH)
            self._filter_frame.pack_forget()
            self.list_frame.pack_forget()
            self._thumb_frame.pack(fill="both", expand=True, padx=2, pady=(0, 4))
            self._refresh_thumbnails()
        elif state == 'hidden':
            self._current_w = 1
            self.configure(width=1)
            self._filter_frame.pack_forget()
            self.list_frame.pack_forget()
            self._thumb_frame.pack_forget()

    # ══════════════════════════════════════════════════════════════════════════
    # THUMBNAIL VIEW (compact state)
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_thumbnails(self) -> None:
        """Rebuild thumbnail grid progressively in a background thread."""
        self._thumb_generation += 1
        gen = self._thumb_generation

        for w in self._thumb_frame.winfo_children():
            w.destroy()

        deck = self.app.deck_manager.active_deck()
        if not deck:
            return

        cards = list(deck.cards)

        def _load() -> None:
            for card in cards:
                img_path = card.image_path
                if not img_path:
                    self.after(0, self._add_thumb_placeholder, gen, card)
                    continue
                # Prefer the smaller Scryfall PNG over the heavy 1200dpi version
                if '_1200dpi.png' in img_path:
                    alt = img_path.replace('_1200dpi.png', '.png')
                    if os.path.exists(alt):
                        img_path = alt
                if not os.path.exists(img_path):
                    self.after(0, self._add_thumb_placeholder, gen, card)
                    continue
                try:
                    # PIL work in thread; CTkImage created on main thread via after()
                    pil = Image.open(img_path).resize((64, 90), Image.LANCZOS)
                    self.after(0, self._add_thumb_item, gen, card, pil)
                except Exception:
                    self.after(0, self._add_thumb_placeholder, gen, card)

        threading.Thread(target=_load, daemon=True).start()

    def _add_thumb_item(self, gen: int, card, pil_img: Image.Image) -> None:
        if self._state != 'compact' or gen != self._thumb_generation:
            return
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(64, 90))
        item = ctk.CTkFrame(self._thumb_frame, fg_color="#221f28", corner_radius=3)
        item.pack(fill="x", pady=1, padx=2)
        item.bind("<Button-1>", lambda e, c=card: self._inspect(c))
        img_lbl = ctk.CTkLabel(item, image=ctk_img, text="")
        img_lbl.pack(pady=(2, 0))
        img_lbl.bind("<Button-1>", lambda e, c=card: self._inspect(c))
        count_lbl = ctk.CTkLabel(
            item, text=f"×{card.count}",
            font=ctk.CTkFont(size=9),
            text_color="#c04828",
        )
        count_lbl.pack(pady=(0, 2))
        count_lbl.bind("<Button-1>", lambda e, c=card: self._inspect(c))
        _Tooltip(item, card.name)

    def _add_thumb_placeholder(self, gen: int, card) -> None:
        if self._state != 'compact' or gen != self._thumb_generation:
            return
        item = ctk.CTkFrame(self._thumb_frame, fg_color="#221f28", corner_radius=3)
        item.pack(fill="x", pady=1, padx=2)
        item.bind("<Button-1>", lambda e, c=card: self._inspect(c))
        name = card.name[:7] + "…" if len(card.name) > 7 else card.name
        ctk.CTkLabel(
            item, text=name,
            font=ctk.CTkFont(size=8),
            text_color="#a09aaa",
        ).pack(pady=(6, 0))
        ctk.CTkLabel(
            item, text=f"×{card.count}",
            font=ctk.CTkFont(size=9),
            text_color="#c04828",
        ).pack(pady=(0, 6))
        _Tooltip(item, card.name)

    # ══════════════════════════════════════════════════════════════════════════
    # FILTER + REFRESH
    # ══════════════════════════════════════════════════════════════════════════

    def _on_filter_change(self, *_) -> None:
        has_text = bool(self._filter_var.get())
        self._filter_clear_btn.configure(
            text_color="#c4bfb8" if has_text else "#34303e",
            hover_color="#922b21" if has_text else "#28252e",
        )
        self.refresh()

    def refresh(self) -> None:
        deck = self.app.deck_manager.active_deck()

        if deck:
            total = sum(c.count for c in deck.cards)
            self.total_label.configure(text=f"{total} card{'s' if total != 1 else ''}")
        else:
            self.total_label.configure(text="")

        if hasattr(self.app, "inspector"):
            self.app.inspector.refresh_stats()

        # Debounce : annule un rebuild en attente et en planifie un nouveau
        if hasattr(self, '_rebuild_after_id') and self._rebuild_after_id:
            self.after_cancel(self._rebuild_after_id)
        self._rebuild_after_id = self.after(150, self._rebuild_list)

    def _rebuild_list(self) -> None:
        deck = self.app.deck_manager.active_deck()

        if self._state == 'compact':
            self._refresh_thumbnails()
            return

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not deck:
            return

        query = self._filter_var.get().strip().lower()
        cards = deck.cards
        if query:
            cards = [c for c in cards if query in c.name.lower()]

        if not cards:
            msg = (f'No card "{query}"' if query
                   else "No cards in this deck.\nUse the search bar\nto add some.")
            ctk.CTkLabel(
                self.list_frame, text=msg,
                text_color="#a09aaa",
                font=ctk.CTkFont(size=10),
                justify="center",
            ).pack(pady=20)
            return

        # Show artwork filename as subtitle when multiple entries share the same card name.
        name_counts = Counter(c.name for c in cards)
        name_seen: dict[str, int] = {}

        for card in cards:
            subtitle = None
            if name_counts[card.name] > 1:
                occ = name_seen.get(card.name, 0) + 1
                name_seen[card.name] = occ
                fname = os.path.splitext(os.path.basename(card.image_path))[0]
                if len(fname) > 22:
                    fname = fname[:20] + "…"
                subtitle = fname
            self._build_row(card, subtitle=subtitle)

    def _build_row(self, card, subtitle: str | None = None) -> None:
        RB = "#221f28"
        CTRL_W = 152

        row = tk.Frame(self.list_frame, bg=RB)
        row.pack(fill="x", pady=1, padx=2)

        # Name (and optional per-artwork filename when multiple artworks share the same name)
        max_chars = max(6, (self._current_w - CTRL_W - 20) // 11)
        truncated = len(card.name) > max_chars
        name_text = card.name[:max_chars - 1] + "…" if truncated else card.name

        pad_y = (10, 8) if subtitle else (14, 14)
        name_container = tk.Frame(row, bg=RB)
        name_container.pack(side="left", padx=(8, 4), pady=pad_y, expand=True, fill="x")

        name_lbl = tk.Label(name_container, text=name_text, anchor="w", bg=RB, fg="#e8e4f0",
                            font=("Segoe UI", 11), cursor="hand2")
        name_lbl.pack(side="top", anchor="w")
        name_lbl.bind("<Button-1>", lambda e, c=card: self._inspect(c))
        if truncated:
            _Tooltip(name_lbl, card.name)

        if subtitle:
            sub_lbl = tk.Label(name_container, text=subtitle, anchor="w", bg=RB, fg="#6a6478",
                               font=("Segoe UI", 9), cursor="hand2")
            sub_lbl.pack(side="top", anchor="w")
            sub_lbl.bind("<Button-1>", lambda e, c=card: self._inspect(c))

        # Boutons — Canvas 2× plus grands (40×44px par bouton, police 24pt)
        c = tk.Canvas(row, bg=RB, width=CTRL_W, height=44,
                      highlightthickness=0, cursor="hand2")
        c.pack(side="right", padx=(0, 6))

        CY = 22
        DEL_X = CTRL_W - 14
        PLS_X = DEL_X - 36
        CNT_X = PLS_X - 36
        MIN_X = CNT_X - 36

        for bx in (MIN_X, PLS_X, DEL_X):
            c.create_rectangle(bx - 14, CY - 11, bx + 14, CY + 11,
                               fill="#28252e", outline="")

        c.create_text(MIN_X, CY, text="−", anchor="center",
                      fill="#c4bfb8", font=("Segoe UI", 13))
        c.create_text(CNT_X, CY, text=f"×{card.count}", anchor="center",
                      fill="#c04828", font=("Segoe UI", 12, "bold"))
        c.create_text(PLS_X, CY, text="+", anchor="center",
                      fill="#c4bfb8", font=("Segoe UI", 13))
        c.create_text(DEL_X, CY, text="×", anchor="center",
                      fill="#a06070", font=("Segoe UI", 12))

        def _click(event, card=card, min_x=MIN_X, plus_x=PLS_X, del_x=DEL_X):
            x = event.x
            if x >= del_x - 14:
                self._remove_card(card)
            elif x >= plus_x - 14:
                self._change_count(card, 1)
            elif x >= min_x - 14:
                self._change_count(card, -1)
            else:
                self._inspect(card)

        c.bind("<Button-1>", _click)

        tk.Frame(self.list_frame, bg="#2a2630", height=1).pack(fill="x", padx=4)

    def _move_card(self, card, direction: int) -> None:
        """direction: -1 = vers le haut, +1 = vers le bas"""
        deck = self.app.deck_manager.active_deck()
        if not deck:
            return
        idx = next((i for i, c in enumerate(deck.cards) if c is card), None)
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(deck.cards):
            return
        deck.cards[idx], deck.cards[new_idx] = deck.cards[new_idx], deck.cards[idx]
        self._sync()

    def _inspect(self, card) -> None:
        if hasattr(self.app, "inspector"):
            self.app.inspector.show_card(card)
        if hasattr(self.app, "workspace"):
            self.app.workspace.scroll_to_card(card)

    def _change_count(self, card, delta: int) -> None:
        new_count = card.count + delta
        if new_count <= 0:
            self._remove_card(card)
            return
        self.app._push_undo_snapshot()  # snapshot avant la mutation
        card.count = new_count
        self._sync()

    def _remove_card(self, card) -> None:
        self.app._push_undo_snapshot()  # snapshot avant la mutation
        deck = self.app.deck_manager.active_deck()
        if deck:
            deck.cards = [c for c in deck.cards if c is not card]
        self._sync()

    def _sync(self) -> None:
        deck = self.app.deck_manager.active_deck()
        if deck:
            self.app.workspace.load_cards(deck.cards)
        # _on_filter_change met à jour l'état du bouton × ET appelle refresh()
        self._on_filter_change()
        self.app._auto_save()
