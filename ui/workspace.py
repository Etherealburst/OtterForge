"""
ui/workspace.py
---------------
Canvas principal de l'application.
"""

import os
import queue
import tkinter as tk
import threading
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageTk


class Workspace(ctk.CTkFrame):

    BASE_CARD_W = 300
    BASE_CARD_H = 420
    BASE_SPACING_X = 360
    BASE_SPACING_Y = 490
    BACK_GAP = 8               # px entre recto et verso (avant zoom)
    BACKS_SCALE = 0.88         # échelle des cartes en mode Faces+Backs (≈4 paires/rangée)
    START_Y = 50
    SCROLL_PADDING = 40
    ZOOM_LEVELS = [1.0, 1.5, 2.0]
    SNAP_THRESHOLD = 150
    CLICK_THRESHOLD = 5

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._zoom = 1.0
        self._load_version = 0
        self._render_queue: queue.Queue = queue.Queue()
        self._show_backs = False
        self._scroll_to_bottom_on_load = False
        self._find_matches: list = []
        self._find_index: int = -1
        self._find_query: str = ""
        self._find_highlight: int | None = None
        self._all_selected: bool = False
        self._selection_rects: list = []
        self._resize_after_id = None
        self._last_canvas_w: int = 0

        # ------------------------------------------------------------------
        # BARRE DE ZOOM + CONTRÔLES
        # ------------------------------------------------------------------
        zoom_bar = ctk.CTkFrame(self, fg_color="#1c1a20", height=36, corner_radius=0)
        zoom_bar.pack(side="top", fill="x")
        zoom_bar.pack_propagate(False)

        # Accent bar + micro-label
        ctk.CTkFrame(zoom_bar, width=3, fg_color="#c04828",
                     corner_radius=0).pack(side="left", fill="y")
        ctk.CTkLabel(zoom_bar, text="ZOOM",
                     font=ctk.CTkFont(size=9), text_color="#5a5060").pack(
            side="left", padx=(8, 6)
        )

        self._zoom_buttons: dict = {}
        for factor in self.ZOOM_LEVELS:
            label = f"{int(factor)}×" if factor == int(factor) else f"{factor}×"
            btn = ctk.CTkButton(
                zoom_bar, text=label, width=44, height=26,
                font=ctk.CTkFont(size=11),
                command=lambda f=factor: self._set_zoom(f),
            )
            btn.pack(side="left", padx=2, pady=5)
            self._zoom_buttons[factor] = btn

        ctk.CTkFrame(zoom_bar, width=1, fg_color="#34303e").pack(
            side="left", fill="y", padx=8, pady=8)

        # Toggle affichage dos
        self._back_toggle_btn = ctk.CTkButton(
            zoom_bar, text="Faces Only", width=110, height=26,
            font=ctk.CTkFont(size=11),
            command=self._toggle_back_display,
        )
        self._back_toggle_btn.pack(side="left", padx=2, pady=5)

        # Aperçu de l'endos choisi
        self._back_thumb_ref = None
        self._back_thumb_label = tk.Label(zoom_bar, bg="#1c1a20", cursor="hand2")
        self._back_thumb_label.pack(side="left", padx=(8, 2), pady=3)
        self._back_name_label = ctk.CTkLabel(zoom_bar, text="", font=ctk.CTkFont(size=10),
                                              text_color="#c4bfb8")
        self._back_name_label.pack(side="left", padx=(0, 2))

        self._back_clear_btn = ctk.CTkButton(
            zoom_bar, text="×", width=22, height=22,
            font=ctk.CTkFont(size=12),
            fg_color="#581e10", hover_color="#3a1a10",
            command=self._clear_back,
        )
        self._back_clear_btn.pack(side="left")
        self._back_clear_btn.pack_forget()  # caché jusqu'à ce qu'un endos soit choisi

        # --- Barre de recherche (droite de la zoom bar) ---
        ctk.CTkFrame(zoom_bar, width=1, fg_color="#34303e").pack(
            side="right", fill="y", padx=8, pady=8)

        self._find_next_btn = ctk.CTkButton(
            zoom_bar, text=">", width=28, height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#581e10", hover_color="#3a1a10",
            command=self._find_next,
        )
        self._find_next_btn.pack(side="right", padx=(0, 4), pady=5)

        self._find_prev_btn = ctk.CTkButton(
            zoom_bar, text="<", width=28, height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#581e10", hover_color="#3a1a10",
            command=self._find_prev,
        )
        self._find_prev_btn.pack(side="right", padx=(0, 2), pady=5)

        self._find_count_label = ctk.CTkLabel(
            zoom_bar, text="", font=ctk.CTkFont(size=10), text_color="#c4bfb8", width=50,
        )
        self._find_count_label.pack(side="right", padx=(0, 2))

        self._find_entry = ctk.CTkEntry(
            zoom_bar, placeholder_text="Find in deck…", width=160, height=26,
            font=ctk.CTkFont(size=11),
        )
        self._find_entry.pack(side="right", padx=(4, 0), pady=5)
        self._find_entry.bind("<Return>", lambda e: self._find_next())
        self._find_entry.bind("<KeyRelease>", self._on_find_key_release)

        self._update_zoom_buttons()

        # ------------------------------------------------------------------
        # SCROLLBARS + CANVAS
        # ------------------------------------------------------------------
        self.scrollbar_y = ctk.CTkScrollbar(
            self, orientation="vertical",
            fg_color="#1c1a20",
            button_color="#34303e",
            button_hover_color="#5a5060",
        )
        self.scrollbar_y.pack(side="right", fill="y")

        self.scrollbar_x = ctk.CTkScrollbar(
            self, orientation="horizontal",
            fg_color="#1c1a20",
            button_color="#34303e",
            button_hover_color="#5a5060",
        )
        self.scrollbar_x.pack(side="bottom", fill="x")

        self.canvas = tk.Canvas(
            self, bg="#1c1a20",
            yscrollcommand=self.scrollbar_y.set,
            xscrollcommand=self.scrollbar_x.set,
        )
        self.canvas.pack(fill="both", expand=True)

        self.scrollbar_y.configure(command=self.canvas.yview)
        self.scrollbar_x.configure(command=self.canvas.xview)

        # ------------------------------------------------------------------
        # ÉTAT
        # ------------------------------------------------------------------
        self.cards = []
        self.canvas_items: dict = {}
        self.text_to_card_item: dict = {}   # text_item id → image_item id
        self._back_item_map: dict = {}       # back canvas id → front canvas id
        self._last_clicked_back: bool = False
        self.selected_item = None
        self._hover_rect: int | None = None
        self._hover_item: int | None = None
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._drag_origin_x = 0
        self._drag_origin_y = 0
        self._context_menu = None
        self._image_refs: list = []

        # ------------------------------------------------------------------
        # BINDINGS
        # ------------------------------------------------------------------
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Delete>", self._on_delete)
        self.canvas.bind("<Button-3>", self._show_context_menu)
        self.canvas.bind("<Escape>", self._on_escape)
        self.canvas.bind("<Control-a>", self._on_select_all)

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_mousewheel_x)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", self._on_hover_leave)

        self.canvas.focus_set()

    # ------------------------------------------------------------------
    # PROPRIÉTÉS ZOOM + LAYOUT
    # ------------------------------------------------------------------

    @property
    def _card_w(self) -> int:
        scale = self.BACKS_SCALE if self._show_backs else 1.0
        return int(self.BASE_CARD_W * self._zoom * scale)

    @property
    def _card_h(self) -> int:
        scale = self.BACKS_SCALE if self._show_backs else 1.0
        return int(self.BASE_CARD_H * self._zoom * scale)

    @property
    def _back_gap(self) -> int:
        return int(self.BACK_GAP * self._zoom)

    @property
    def _spacing_x(self) -> int:
        if self._show_backs:
            cw = int(self.BASE_CARD_W * self._zoom * self.BACKS_SCALE)
            gap = int(self.BACK_GAP * self._zoom)
            return cw * 2 + gap + int(20 * self._zoom)
        return int(self.BASE_SPACING_X * self._zoom)

    @property
    def _spacing_y(self) -> int:
        scale = self.BACKS_SCALE if self._show_backs else 1.0
        return int(self.BASE_SPACING_Y * self._zoom * scale)

    def _set_zoom(self, factor: float) -> None:
        self._zoom = factor
        self._update_zoom_buttons()
        deck = self.app.deck_manager.active_deck()
        if not deck or not deck.cards:
            return
        self._start_progressive_load(deck.cards)

    # ------------------------------------------------------------------
    # CONTRÔLES ENDOS
    # ------------------------------------------------------------------

    def _toggle_back_display(self) -> None:
        self._show_backs = not self._show_backs
        self._back_toggle_btn.configure(
            text="Faces + Backs" if self._show_backs else "Faces Only"
        )
        deck = self.app.deck_manager.active_deck()
        if deck and deck.cards:
            self._start_progressive_load(deck.cards)

    def update_back_preview(self, path: str | None) -> None:
        """Met à jour la vignette d'endos dans la zoom bar."""
        if not path:
            self._back_thumb_label.configure(image="")
            self._back_thumb_ref = None
            self._back_name_label.configure(text="")
            self._back_clear_btn.pack_forget()
            return
        try:
            h = 28
            w = int(h * self.BASE_CARD_W / self.BASE_CARD_H)
            img = Image.open(path).resize((w, h), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._back_thumb_ref = tk_img
            self._back_thumb_label.configure(image=tk_img)
            self._back_name_label.configure(text=os.path.splitext(os.path.basename(path))[0][:20])
            self._back_clear_btn.pack(side="left")
        except Exception:
            self._back_name_label.configure(text="(endos)")
            self._back_clear_btn.pack(side="left")

    def _clear_back(self) -> None:
        self.app.deck_back_image = None
        deck = self.app.deck_manager.active_deck()
        if deck:
            deck.back_image = None
            self.app._auto_save()
        self.update_back_preview(None)
        self.app.statusbar.set_status("Endos supprimé")

    def _update_zoom_buttons(self) -> None:
        for factor, btn in self._zoom_buttons.items():
            if factor == self._zoom:
                btn.configure(fg_color="#c04828")
            else:
                btn.configure(fg_color="#581e10")

    # ------------------------------------------------------------------
    # CHARGEMENT PROGRESSIF — queue.Queue pour thread safety
    # ------------------------------------------------------------------

    def load_cards(self, cards, scroll_to_bottom=False) -> None:
        self._scroll_to_bottom_on_load = scroll_to_bottom
        self._start_progressive_load(cards)

    def _start_progressive_load(self, cards) -> None:
        """Vide le canvas immédiatement, puis charge les cartes via un thread + queue."""
        self.canvas.delete("all")
        self.cards = list(cards)
        self.canvas_items.clear()
        self.text_to_card_item.clear()
        self.selected_item = None
        self._hover_rect = None
        self._hover_item = None
        self._image_refs.clear()
        # Réinitialise l'état de recherche et de sélection (les items canvas vont changer)
        self._find_matches = []
        self._find_index = -1
        self._find_highlight = None
        self._find_count_label.configure(text="")
        self._all_selected = False
        self._selection_rects.clear()  # canvas.delete("all") efface déjà les rects

        if not self.cards:
            self._update_scrollregion(50, self.START_Y)
            return

        # Nouvelle queue propre pour ce chargement (annule les items de l'ancienne)
        self._render_queue = queue.Queue()
        self._load_version += 1
        version = self._load_version
        self._back_item_map.clear()

        # Capture canvas width + spacing sur le main thread (thread-safe)
        canvas_w = max(self.canvas.winfo_width(), 500)
        spacing_x = self._spacing_x
        card_w = self._card_w

        self.app.statusbar.show_indeterminate("Chargement des cartes...")
        threading.Thread(
            target=self._card_load_worker,
            args=(list(self.cards), version, canvas_w, spacing_x, card_w),
            daemon=True,
        ).start()
        # Lance le polling sur le main thread (40 ms ≈ 25 fps)
        self.after(40, self._poll_render_queue, version)

    def _card_load_worker(self, cards, version: int,
                          canvas_w: int, spacing_x: int, card_w: int) -> None:
        """Thread : charge chaque image PIL et la dépose dans la queue."""
        show_backs = self._show_backs
        global_back = self.app.deck_back_image
        card_h = self._card_h
        spacing_y = self._spacing_y
        back_gap = self._back_gap

        # Auto-layout : nombre de colonnes selon la largeur du canvas
        cards_per_row = max(1, canvas_w // spacing_x)

        # Centrage horizontal : largeur réelle de la rangée (inclut le verso de la dernière paire)
        n_in_row = min(cards_per_row, len(cards))
        if show_backs:
            row_content_w = (n_in_row - 1) * spacing_x + card_w * 2 + back_gap
        else:
            row_content_w = (n_in_row - 1) * spacing_x + card_w
        start_x = max(20, (canvas_w - row_content_w) // 2)
        start_y = self.START_Y

        x, y = start_x, start_y
        max_x, max_y = start_x, start_y

        for i, card in enumerate(cards):
            if version != self._load_version:
                return

            cx, cy = x, y
            try:
                display_path = card.image_path
                if display_path.endswith("_1200dpi.png"):
                    original = display_path.replace("_1200dpi.png", ".png")
                    if os.path.exists(original):
                        display_path = original
                img = Image.open(display_path).resize((card_w, card_h), Image.LANCZOS)

                back_img = None
                if show_backs:
                    back_path = getattr(card, "back_image_path", None)
                    if back_path is None:
                        back_path = global_back
                    if back_path and not os.path.isfile(back_path) and back_path.endswith("_1200dpi.png"):
                        native = back_path.replace("_1200dpi.png", ".png")
                        if os.path.isfile(native):
                            back_path = native
                    if back_path and os.path.isfile(back_path):
                        try:
                            back_img = Image.open(back_path).resize((card_w, card_h), Image.LANCZOS)
                        except Exception:
                            pass
                    if back_img is None:
                        back_img = Image.new("RGB", (card_w, card_h), (35, 35, 35))

                self._render_queue.put(("card", card, img, back_img, cx, cy))
            except Exception as e:
                print(f"[Workspace] Erreur chargement {card.name!r} : {e}")

            item_w = card_w * 2 + back_gap if show_backs else card_w
            max_x = max(max_x, cx + item_w)
            max_y = max(max_y, cy + card_h)
            x += spacing_x
            if (i + 1) % cards_per_row == 0:
                x = start_x
                y += spacing_y

        self._render_queue.put(("done", max_x, max_y))

    def _poll_render_queue(self, version: int) -> None:
        """Main thread : vide la queue et met à jour le canvas."""
        if version != self._load_version:
            return

        try:
            for _ in range(10):
                item = self._render_queue.get_nowait()
                if item[0] == "done":
                    self._finalize_load(item[1], item[2], version)
                    return
                _, card, img, back_img, cx, cy = item
                self._add_card_to_canvas(card, img, back_img, cx, cy)
        except queue.Empty:
            pass

        self.after(40, self._poll_render_queue, version)

    def _add_card_to_canvas(self, card, img, back_img, x: int, y: int) -> None:
        """Main thread : crée les items canvas pour une carte (+ endos si activé)."""
        tk_img = ImageTk.PhotoImage(img)
        self._image_refs.append(tk_img)
        item = self.canvas.create_image(x, y, image=tk_img, anchor="nw")
        text_item = None
        if card.count > 1:
            text_item = self.canvas.create_text(
                x + 30, y + 30, text=f"x{card.count}",
                fill="white", font=("Arial", 18, "bold"),
            )
            self.text_to_card_item[text_item] = item

        back_item = None
        if back_img is not None:
            tk_back = ImageTk.PhotoImage(back_img)
            self._image_refs.append(tk_back)
            bx = x + self._card_w + self._back_gap
            back_item = self.canvas.create_image(bx, y, image=tk_back, anchor="nw")
            self._back_item_map[back_item] = item   # back id → front id
            self.canvas.create_text(
                bx + self._card_w // 2, y + self._card_h + 10,
                text="BACK", fill="#5a5060", font=("Arial", 9),
                tags=("back_label",),
            )

        self.canvas_items[item] = {
            "card": card, "image": tk_img, "text_item": text_item,
            "back_item": back_item,
            "x": x, "y": y,
            "slot_x": x, "slot_y": y,
        }

    # ------------------------------------------------------------------
    # RECHERCHE DANS LE WORKSPACE
    # ------------------------------------------------------------------

    def _on_find_key_release(self, event) -> None:
        """Réinitialise l'index de recherche si la query a changé."""
        q = self._find_entry.get()
        if q != self._find_query:
            self._find_query = q
            self._find_index = -1
            self._find_matches = []
            self._find_count_label.configure(text="")
            self._clear_find_highlight()
            self._find_entry.configure(text_color="#f0ece4")

    def _build_find_matches(self, query: str) -> list:
        """Retourne les canvas items dont le nom de carte contient query (insensible à la casse)."""
        q = query.strip().lower()
        if not q:
            return []
        return [
            (item_id, info)
            for item_id, info in self.canvas_items.items()
            if q in info["card"].name.lower()
        ]

    def _find_next(self) -> None:
        """Va au prochain résultat de recherche (cycle vers l'avant)."""
        self._find_step(+1)

    def _find_prev(self) -> None:
        """Va au résultat précédent (cycle vers l'arrière)."""
        self._find_step(-1)

    def _find_step(self, direction: int) -> None:
        query = self._find_entry.get()
        if not query.strip():
            return

        # Rebuild si query changée ou canvas rechargé
        if query != self._find_query or not self._find_matches:
            self._find_query = query
            self._find_matches = self._build_find_matches(query)
            self._find_index = -1

        if not self._find_matches:
            self._find_count_label.configure(text="0 / 0")
            self._find_entry.configure(text_color="#c0392b")
            return

        self._find_entry.configure(text_color=("gray10", "gray90"))
        self._find_index = (self._find_index + direction) % len(self._find_matches)
        total = len(self._find_matches)
        self._find_count_label.configure(text=f"{self._find_index + 1} / {total}")

        item_id, info = self._find_matches[self._find_index]
        self._scroll_to_canvas_pos(info["x"], info["y"])
        self._highlight_card(item_id, info)

    def _scroll_to_canvas_pos(self, cx: int, cy: int) -> None:
        """Scrolle le canvas pour centrer (cx, cy) verticalement."""
        sr = self.canvas.cget("scrollregion")
        if not sr:
            return
        parts = sr.split()
        if len(parts) < 4:
            return
        total_h = float(parts[3])
        if total_h <= 0:
            return
        canvas_h = self.canvas.winfo_height()
        target_top = cy - canvas_h // 3
        frac = max(0.0, min(1.0, target_top / total_h))
        self.canvas.yview_moveto(frac)

    def _highlight_card(self, item_id: int, info: dict) -> None:
        """Dessine un rectangle lumineux autour de la carte trouvée."""
        self._clear_find_highlight()
        x, y = info["x"], info["y"]
        pad = 6
        rect = self.canvas.create_rectangle(
            x - pad, y - pad,
            x + self._card_w + pad, y + self._card_h + pad,
            outline="#c04828", width=3, tags=("find_highlight",),
        )
        self._find_highlight = rect
        # Efface le highlight après 2 secondes
        self.after(2000, self._clear_find_highlight)

    def _clear_find_highlight(self) -> None:
        if self._find_highlight is not None:
            try:
                self.canvas.delete(self._find_highlight)
            except Exception:
                pass
            self._find_highlight = None

    def _finalize_load(self, max_x: int, max_y: int, version: int) -> None:
        if version != self._load_version:
            return
        self._update_scrollregion(max_x, max_y)
        self.app.statusbar.hide_progress()
        if self._scroll_to_bottom_on_load:
            self._scroll_to_bottom_on_load = False
            self.canvas.yview_moveto(1.0)
        else:
            self.app.statusbar.set_status("Ready")

    def _update_scrollregion(self, max_x: int, max_y: int) -> None:
        self.canvas.configure(
            scrollregion=(0, 0, max_x + self.SCROLL_PADDING, max_y + self.SCROLL_PADDING)
        )

    # ------------------------------------------------------------------
    # SURVOL — OUTLINE DE SURBRILLANCE
    # ------------------------------------------------------------------

    def _on_hover(self, event) -> None:
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        items = self.canvas.find_closest(cx, cy)
        item = items[0] if items else None
        if item in self._back_item_map:
            item = self._back_item_map[item]
        if item in self.text_to_card_item:
            item = self.text_to_card_item[item]
        if item not in self.canvas_items:
            item = None

        if item == self._hover_item:
            return
        self._hover_item = item

        if self._hover_rect is not None:
            self.canvas.delete(self._hover_rect)
            self._hover_rect = None

        if item is None:
            return

        data = self.canvas_items[item]
        x, y = data["x"], data["y"]
        cw, ch = self._card_w, self._card_h
        self._hover_rect = self.canvas.create_rectangle(
            x - 2, y - 2, x + cw + 2, y + ch + 2,
            outline="#f0a050", width=2, tags=("hover_rect",),
        )
        self.canvas.tag_lower("hover_rect")

    def _on_hover_leave(self, event) -> None:
        self._hover_item = None
        if self._hover_rect is not None:
            self.canvas.delete(self._hover_rect)
            self._hover_rect = None

    # ------------------------------------------------------------------
    # SCROLL — MOLETTE
    # ------------------------------------------------------------------

    def _on_mousewheel(self, event) -> None:
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_x(self, event) -> None:
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # DRAG & SNAP
    # ------------------------------------------------------------------

    def _resolve_item(self, event) -> int | None:
        """Retourne l'id front sous le curseur. Positionne _last_clicked_back."""
        items = self.canvas.find_closest(
            self.canvas.canvasx(event.x),
            self.canvas.canvasy(event.y),
        )
        if not items:
            self._last_clicked_back = False
            return None
        found = items[0]
        # Clic sur l'image endos → on retrouve l'item front associé
        if found in self._back_item_map:
            self._last_clicked_back = True
            return self._back_item_map[found]
        self._last_clicked_back = False
        if found in self.text_to_card_item:
            found = self.text_to_card_item[found]
        return found if found in self.canvas_items else None

    def _on_click(self, event) -> None:
        if self._all_selected:
            self._clear_selection()

        self._close_context_menu()
        self.selected_item = None

        found = self._resolve_item(event)
        if found is not None:
            self.selected_item = found
            data = self.canvas_items[found]
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            self._drag_offset_x = cx - data["x"]
            self._drag_offset_y = cy - data["y"]
            self._drag_origin_x = data["x"]
            self._drag_origin_y = data["y"]

    def _on_drag(self, event) -> None:
        if self.selected_item is None:
            return
        data = self.canvas_items.get(self.selected_item)
        if not data:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        new_x = cx - self._drag_offset_x
        new_y = cy - self._drag_offset_y
        self.canvas.coords(self.selected_item, new_x, new_y)
        if data.get("text_item"):
            self.canvas.coords(data["text_item"], new_x + 30, new_y + 30)
        if data.get("back_item"):
            self.canvas.coords(data["back_item"], new_x + self._card_w + self._back_gap, new_y)
        data["x"] = new_x
        data["y"] = new_y

    def _on_release(self, event) -> None:
        if self.selected_item is not None:
            data = self.canvas_items.get(self.selected_item)
            if data:
                sx, sy = data["slot_x"], data["slot_y"]

                # Distance au slot fixe (décide du snap)
                dx_slot = data["x"] - sx
                dy_slot = data["y"] - sy
                dist_slot = (dx_slot * dx_slot + dy_slot * dy_slot) ** 0.5

                # Distance au point de départ du drag (détecte un clic pur)
                dx_drag = data["x"] - self._drag_origin_x
                dy_drag = data["y"] - self._drag_origin_y
                moved = (dx_drag * dx_drag + dy_drag * dy_drag) ** 0.5

                if dist_slot < self.SNAP_THRESHOLD:
                    # Snap vers le slot de grille
                    self.canvas.coords(self.selected_item, sx, sy)
                    if data.get("text_item"):
                        self.canvas.coords(data["text_item"], sx + 30, sy + 30)
                    if data.get("back_item"):
                        self.canvas.coords(data["back_item"], sx + self._card_w + self._back_gap, sy)
                    data["x"] = sx
                    data["y"] = sy

                    # Clic pur → envoie la carte à l'inspecteur (panneau droit)
                    if moved < self.CLICK_THRESHOLD:
                        if hasattr(self.app, "inspector"):
                            card = self.canvas_items[self.selected_item]["card"]
                            self.app.inspector.show_card(card, show_back=self._last_clicked_back)

        self.selected_item = None

    # ------------------------------------------------------------------
    # SÉLECTION GLOBALE (Ctrl+A)
    # ------------------------------------------------------------------

    def _on_escape(self, event) -> None:
        self._clear_selection()

    def _on_select_all(self, event=None) -> None:
        """Sélectionne toutes les cartes visibles (Ctrl+A)."""
        self._clear_selection()
        if not self.canvas_items:
            return
        self._all_selected = True
        pad = 4
        for item_id, info in self.canvas_items.items():
            x, y = info["x"], info["y"]
            rect = self.canvas.create_rectangle(
                x - pad, y - pad,
                x + self._card_w + pad, y + self._card_h + pad,
                outline="#c04828", width=2, tags=("selection_rect",),
            )
            self._selection_rects.append(rect)
        total = len(self.canvas_items)
        self.app.statusbar.set_status(
            f"{total} carte(s) sélectionnée(s) — Suppr pour tout effacer · Échap pour annuler"
        )

    def _clear_selection(self) -> None:
        """Efface la sélection globale sans toucher au reste du canvas."""
        self._all_selected = False
        for r in self._selection_rects:
            try:
                self.canvas.delete(r)
            except Exception:
                pass
        self._selection_rects.clear()

    def _delete_all_cards(self) -> None:
        """Supprime toutes les cartes du deck actif après confirmation."""
        deck = self.app.deck_manager.active_deck()
        if not deck or not deck.cards:
            return
        total = sum(c.count for c in deck.cards)
        if not messagebox.askyesno(
            "Supprimer tout",
            f"Supprimer toutes les {total} carte(s) du deck ?\nCette action est irréversible.",
        ):
            self._clear_selection()
            return
        deck.cards.clear()
        self._clear_selection()
        self.load_cards([])
        self.app.sidebar.refresh()
        self.app._auto_save()
        self.app.statusbar.set_status("Deck vidé.")

    def _on_delete(self, event) -> None:
        if self._all_selected:
            self._delete_all_cards()
        else:
            self._delete_selected()

    # ------------------------------------------------------------------
    # RESIZE — auto-relayout quand le canvas change de taille
    # ------------------------------------------------------------------

    def _on_canvas_resize(self, event=None) -> None:
        new_w = event.width if event else self.canvas.winfo_width()
        if abs(self._last_canvas_w - new_w) < 30:
            return
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(400, self._on_resize_done)

    def _on_resize_done(self) -> None:
        self._resize_after_id = None
        self._last_canvas_w = self.canvas.winfo_width()
        deck = self.app.deck_manager.active_deck()
        if deck and deck.cards:
            self._start_progressive_load(deck.cards)

    # ------------------------------------------------------------------
    # MENU CONTEXTUEL
    # ------------------------------------------------------------------

    def _show_context_menu(self, event) -> None:
        self._close_context_menu()

        found = self._resolve_item(event)
        if found is None:
            return

        self.selected_item = found

        # Borderless Toplevel positioned at exact cursor coords (absolute screen)
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"+{event.x_root}+{event.y_root}")

        frame = ctk.CTkFrame(popup, fg_color="#28252e", corner_radius=8)
        frame.pack(padx=2, pady=2)

        def _cmd(fn):
            """Wrap a command so it closes the menu before executing."""
            def _():
                self._close_context_menu()
                fn()
            return _

        font = ctk.CTkFont(size=13)
        kw = dict(font=font, width=160, height=32, anchor="w")
        ctk.CTkButton(frame, text="  Remove",        command=_cmd(self._delete_selected),        **kw).pack(padx=6, pady=(6, 2))
        ctk.CTkButton(frame, text="  +1",            command=_cmd(lambda: self._modify_qty(1)),  **kw).pack(padx=6, pady=2)
        ctk.CTkButton(frame, text="  -1",            command=_cmd(lambda: self._modify_qty(-1)), **kw).pack(padx=6, pady=2)
        ctk.CTkButton(frame, text="  Open file",     command=_cmd(self._open_card_file),         **kw).pack(padx=6, pady=2)
        ctk.CTkButton(frame, text="  Change image",  command=_cmd(self._change_card_image),      **kw).pack(padx=6, pady=2)
        ctk.CTkButton(frame, text="  Set Card Back", command=_cmd(self._set_card_back),          **kw).pack(padx=6, pady=2)
        ctk.CTkButton(frame, text="  Export image",  command=_cmd(self._export_card_image),      **kw).pack(padx=6, pady=(2, 6))

        self._context_menu = popup

        # Close when focus leaves the popup (e.g. click elsewhere)
        def _on_focus_out(e):
            focused = str(self.focus_get() or "")
            if not focused.startswith(str(popup)):
                self._close_context_menu()

        popup.bind("<FocusOut>", _on_focus_out)
        popup.focus_force()

    def _close_context_menu(self) -> None:
        if self._context_menu:
            self._context_menu.destroy()
            self._context_menu = None

    def _delete_selected(self) -> None:
        if self.selected_item is None:
            return

        data = self.canvas_items.get(self.selected_item)
        if data:
            card = data["card"]
            deck = self.app.deck_manager.active_deck()
            if deck:
                deck.cards = [c for c in deck.cards if c is not card]
            # Nettoie le mapping text → card
            if data.get("text_item") and data["text_item"] in self.text_to_card_item:
                del self.text_to_card_item[data["text_item"]]
            # Nettoie le mapping back → front
            if data.get("back_item"):
                self._back_item_map.pop(data["back_item"], None)

        if data and data.get("back_item"):
            self.canvas.delete(data["back_item"])
        self.canvas.delete(self.selected_item)
        self.canvas_items.pop(self.selected_item, None)
        self.selected_item = None
        self._close_context_menu()

        self.app.sidebar.refresh()
        self.app._auto_save()

    def _modify_qty(self, delta: int) -> None:
        data = self.canvas_items.get(self.selected_item)
        if not data:
            return

        card = data["card"]
        card.count = max(1, card.count + delta)

        self.app.sidebar.refresh()
        self.app._auto_save()
        deck = self.app.deck_manager.active_deck()
        if deck:
            self.load_cards(deck.cards)

        self._close_context_menu()

    def _change_card_image(self) -> None:
        """Replace a card's front image via file picker."""
        self._close_context_menu()
        data = self.canvas_items.get(self.selected_item)
        if not data:
            return
        card = data["card"]

        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select new card image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        card.image_path = path
        self.app._auto_save()

        deck = self.app.deck_manager.active_deck()
        if deck:
            self.load_cards(deck.cards)

    def _set_card_back(self) -> None:
        """Ouvre le picker d'endos et assigne l'image choisie à la carte sélectionnée."""
        self._close_context_menu()
        data = self.canvas_items.get(self.selected_item)
        if not data:
            return
        card = data["card"]

        from ui.card_back_picker import CardBackPickerDialog
        dialog = CardBackPickerDialog(self.app)
        self.app.wait_window(dialog)
        if dialog.result is None:
            return

        card.back_image_path = dialog.result
        self.app._auto_save()

        deck = self.app.deck_manager.active_deck()
        if deck:
            self.load_cards(deck.cards)

    def _open_card_file(self) -> None:
        """Ouvre l'image de la carte sélectionnée dans la visionneuse OS."""
        data = self.canvas_items.get(self.selected_item)
        if not data:
            return
        card = data["card"]
        path = card.image_path
        if path.endswith("_1200dpi.png"):
            native = path.replace("_1200dpi.png", ".png")
            if os.path.exists(native):
                path = native
        try:
            os.startfile(path)
        except Exception as e:
            print(f"[Workspace] Impossible d'ouvrir {path!r} : {e}")

    def _export_card_image(self) -> None:
        """Exporte l'image haute résolution de la carte sélectionnée vers un fichier."""
        data = self.canvas_items.get(self.selected_item)
        if not data:
            return
        card = data["card"]

        # Préfère la version haute résolution si disponible
        src_path = card.image_path
        if src_path.endswith("_mpc300.png"):
            hires = src_path.replace("_mpc300.png", "_1200dpi.png")
            if os.path.isfile(hires):
                src_path = hires
        elif not src_path.endswith("_1200dpi.png"):
            hires = src_path.replace(".png", "_1200dpi.png")
            if os.path.isfile(hires):
                src_path = hires

        # Nom de fichier par défaut : nom de la carte (caractères invalides → tiret)
        safe = card.name
        for ch in r'\/:*?"<>|':
            safe = safe.replace(ch, "-")
        default_name = safe + ".png"

        from tkinter import filedialog
        dest = filedialog.asksaveasfilename(
            title="Exporter l'image",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not dest:
            return

        try:
            img = Image.open(src_path)
            if dest.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
            img.save(dest)
            self.app.statusbar.set_status(f"Image exportée : {os.path.basename(dest)}")
        except Exception as e:
            messagebox.showerror("Erreur export", f"Impossible d'exporter l'image :\n{e}")
