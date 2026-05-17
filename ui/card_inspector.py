"""
ui/card_inspector.py
--------------------
Panneau latéral droit — dual-mode :
  CARD : aperçu de la carte sélectionnée (image + infos)
  STATS : composition du deck actif
"""

import os
import threading
import customtkinter as ctk
from PIL import Image

_CARD_RATIO = 420 / 300   # hauteur / largeur MTG standard


class CardInspectorPanel(ctk.CTkFrame):

    WIDTH = 270

    def __init__(self, master, app):
        super().__init__(master, width=self.WIDTH, corner_radius=0, fg_color="#1c1a20")
        self.app = app
        self.pack_propagate(False)

        self._current_card = None
        self._img_ref = None
        self._tab = "card"
        self._show_back = False

        img_w = self.WIDTH - 24
        img_h = int(img_w * _CARD_RATIO)
        self._img_size = (img_w, img_h)

        self._build_header()
        ctk.CTkFrame(self, height=1, fg_color="#28252e",
                     corner_radius=0).pack(fill="x", padx=8, pady=(0, 4))
        self._build_card_pane()
        self._build_stats_pane()

        # Afficher le pane CARD par défaut
        self._stats_pane.pack_forget()
        self._card_pane.pack(fill="both", expand=True)

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=0, pady=(10, 4))

        ctk.CTkFrame(header, width=3, fg_color="#c04828",
                     corner_radius=2).pack(side="left", fill="y", padx=(8, 6))
        ctk.CTkLabel(
            header, text="INSPECTOR",
            font=ctk.CTkFont(size=9), text_color="#5a5060", anchor="w",
        ).pack(side="left")

        tab_frame = ctk.CTkFrame(header, fg_color="transparent")
        tab_frame.pack(side="right", padx=8)

        self._btn_card = ctk.CTkButton(
            tab_frame, text="CARD", width=52, height=22,
            font=ctk.CTkFont(size=9),
            fg_color="#c04828", hover_color="#a83820",
            command=lambda: self._switch_tab("card"),
        )
        self._btn_card.pack(side="left", padx=(0, 2))

        self._btn_stats = ctk.CTkButton(
            tab_frame, text="STATS", width=52, height=22,
            font=ctk.CTkFont(size=9),
            fg_color="#28252e", hover_color="#34303e",
            command=lambda: self._switch_tab("stats"),
        )
        self._btn_stats.pack(side="left")

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self, tab: str) -> None:
        self._tab = tab
        if tab == "card":
            self._stats_pane.pack_forget()
            self._card_pane.pack(fill="both", expand=True)
            self._btn_card.configure(fg_color="#c04828", hover_color="#a83820")
            self._btn_stats.configure(fg_color="#28252e", hover_color="#34303e")
        else:
            self._card_pane.pack_forget()
            self._stats_pane.pack(fill="both", expand=True)
            self._btn_stats.configure(fg_color="#c04828", hover_color="#a83820")
            self._btn_card.configure(fg_color="#28252e", hover_color="#34303e")
            self._build_stats()

    # ── Card pane ─────────────────────────────────────────────────────────────

    def _build_card_pane(self) -> None:
        self._card_pane = ctk.CTkFrame(self, fg_color="transparent")

        # Image — placeholder initial (cliquable pour zoom)
        self._img_label = ctk.CTkLabel(
            self._card_pane, text="",
            fg_color="#221f28", corner_radius=6,
            width=self._img_size[0], height=self._img_size[1],
            cursor="hand2",
        )
        self._img_label.pack(padx=12, pady=(4, 8))
        self._img_label.bind("<Button-1>", lambda e: self._open_zoom_popup())

        self._placeholder_text = ctk.CTkLabel(
            self._card_pane,
            text="Clique sur une carte\npour l'inspecter",
            font=ctk.CTkFont(size=11), text_color="#5a5060",
            justify="center",
        )
        self._placeholder_text.place(
            in_=self._img_label,
            relx=0.5, rely=0.5, anchor="center",
        )

        # Nom de la carte
        self._name_label = ctk.CTkLabel(
            self._card_pane, text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f0ece4",
            wraplength=self.WIDTH - 28, anchor="w",
        )
        self._name_label.pack(padx=14, anchor="w")

        # Set / meta
        self._meta_label = ctk.CTkLabel(
            self._card_pane, text="",
            font=ctk.CTkFont(size=10), text_color="#5a5060", anchor="w",
        )
        self._meta_label.pack(padx=14, anchor="w", pady=(2, 0))

        # Nombre de copies
        self._count_label = ctk.CTkLabel(
            self._card_pane, text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#c04828", anchor="w",
        )
        self._count_label.pack(padx=14, anchor="w", pady=(4, 0))

        # Indicateur DFC
        self._dfc_label = ctk.CTkLabel(
            self._card_pane, text="",
            font=ctk.CTkFont(size=9), text_color="#5a5060", anchor="w",
        )
        self._dfc_label.pack(padx=14, anchor="w", pady=(2, 0))

    # ── Stats pane ────────────────────────────────────────────────────────────

    def _build_stats_pane(self) -> None:
        self._stats_pane = ctk.CTkScrollableFrame(self, fg_color="transparent")

    def _build_stats(self) -> None:
        for w in self._stats_pane.winfo_children():
            w.destroy()

        deck = self.app.deck_manager.active_deck()
        if not deck or not deck.cards:
            ctk.CTkLabel(
                self._stats_pane, text="Deck vide",
                text_color="#5a5060", font=ctk.CTkFont(size=11),
            ).pack(pady=24)
            return

        total = sum(c.count for c in deck.cards)
        unique = len(deck.cards)
        dfc = sum(1 for c in deck.cards if getattr(c, "back_image_path", None))

        dist: dict[int, int] = {}
        for c in deck.cards:
            key = min(c.count, 4)
            dist[key] = dist.get(key, 0) + 1

        # Totaux
        self._stat_section("TOTAL")
        self._stat_row("Total cards", total, accent=True)
        self._stat_row("Unique cards", unique)
        if dfc:
            self._stat_row("Double-faced", dfc)

        # Distribution par copies
        self._stat_section("COPIES")
        labels = {4: "4× playset", 3: "3×", 2: "2×", 1: "1× singleton"}
        for n in (4, 3, 2, 1):
            cnt = dist.get(n, 0)
            if cnt:
                self._stat_row(labels[n], f"{cnt} card{'s' if cnt > 1 else ''}")

        # Backs
        if deck.back_image or dfc:
            self._stat_section("BACKS")
            if deck.back_image:
                name = os.path.splitext(os.path.basename(deck.back_image))[0]
                self._stat_row("Global back", name[:18] + ("…" if len(name) > 18 else ""))
            if dfc:
                self._stat_row("Individual backs", dfc)

        # Top cartes (par copies)
        top = sorted(deck.cards, key=lambda c: c.count, reverse=True)
        if top and top[0].count > 1:
            self._stat_section("TOP CARDS")
            for c in top[:6]:
                if c.count < 2:
                    break
                short = c.name[:20] + ("…" if len(c.name) > 20 else "")
                self._stat_row(short, f"×{c.count}")

    def _stat_section(self, text: str) -> None:
        f = ctk.CTkFrame(self._stats_pane, fg_color="transparent")
        f.pack(fill="x", padx=4, pady=(10, 2))
        ctk.CTkFrame(f, width=3, fg_color="#c04828", corner_radius=0).pack(
            side="left", fill="y", padx=(0, 6))
        ctk.CTkLabel(
            f, text=text, font=ctk.CTkFont(size=9),
            text_color="#5a5060", anchor="w",
        ).pack(side="left")

    def _stat_row(self, label: str, value, accent: bool = False) -> None:
        row = ctk.CTkFrame(self._stats_pane, fg_color="#221f28", corner_radius=4)
        row.pack(fill="x", pady=2, padx=4)
        ctk.CTkLabel(
            row, text=label, font=ctk.CTkFont(size=11),
            text_color="#c4bfb8", anchor="w",
        ).pack(side="left", padx=(8, 4), pady=6, fill="x", expand=True)
        ctk.CTkLabel(
            row, text=str(value),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#c04828" if accent else "#f0ece4",
        ).pack(side="right", padx=8)

    # ── API publique ──────────────────────────────────────────────────────────

    def show_card(self, card, show_back: bool = False) -> None:
        """Appelé depuis workspace ou sidebar quand une carte est sélectionnée."""
        self._current_card = card
        self._show_back = show_back
        if self._tab != "card":
            self._switch_tab("card")

        # Labels instantanés
        self._name_label.configure(text=card.name)
        count = card.count
        self._count_label.configure(text=f"×{count}  dans le deck")
        self._placeholder_text.place_forget()

        has_back = bool(getattr(card, "back_image_path", None))
        if show_back and has_back:
            self._dfc_label.configure(text="← face verso", text_color="#c04828")
        elif has_back:
            self._dfc_label.configure(text="Double-faced card  ·  DFC", text_color="#5a5060")
        else:
            self._dfc_label.configure(text="", text_color="#5a5060")

        # Set code via le nom du fichier (best-effort)
        path = card.image_path or ""
        basename = os.path.splitext(os.path.basename(path))[0]
        parts = [p for p in basename.split("_") if p]
        set_hint = ""
        for p in reversed(parts):
            if 2 <= len(p) <= 5 and p.isalpha() and not p.startswith("face"):
                set_hint = p.upper()
                break
        self._meta_label.configure(text=set_hint)

        # Image en thread
        threading.Thread(
            target=self._load_image_bg,
            args=(card, show_back),
            daemon=True,
        ).start()

    def _load_image_bg(self, card, show_back: bool = False) -> None:
        try:
            path = card.image_path
            if show_back:
                back_path = getattr(card, "back_image_path", None)
                if back_path and os.path.isfile(back_path):
                    path = back_path
            if path.endswith("_1200dpi.png"):
                native = path.replace("_1200dpi.png", ".png")
                if os.path.exists(native):
                    path = native
            img = Image.open(path).resize(self._img_size, Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, size=self._img_size)
            self.after(0, self._apply_image, ctk_img, card)
        except Exception:
            self.after(0, self._img_label.configure, {"image": "", "text": "⚠"})

    def _apply_image(self, ctk_img, card) -> None:
        if card is not self._current_card:
            return
        self._img_ref = ctk_img
        self._img_label.configure(image=ctk_img, text="", fg_color="transparent")

    def _open_zoom_popup(self) -> None:
        """Ouvre un popup centré avec la carte agrandie. Clic ou Échap pour fermer."""
        card = self._current_card
        if card is None:
            return

        # Ferme un éventuel popup déjà ouvert
        if getattr(self, '_zoom_popup', None) is not None:
            try:
                self._zoom_popup.destroy()
            except Exception:
                pass
            self._zoom_popup = None

        self.app.update_idletasks()
        ws = self.app.workspace
        ws.update_idletasks()

        # CTkToplevel._apply_geometry_scaling scale la TAILLE (logique→physique)
        # mais laisse la position +X+Y inchangée → passer des pixels physiques.
        try:
            from customtkinter import ScalingTracker
            _s = ScalingTracker.get_window_scaling(self.app)
        except Exception:
            _s = 1.0

        # Centre du workspace en pixels physiques
        cx = ws.winfo_rootx() + ws.winfo_width()  // 2
        cy = ws.winfo_rooty() + ws.winfo_height() // 2

        # Taille en pixels logiques (CTkToplevel applique _s automatiquement)
        img_w = 380
        img_h = int(img_w * _CARD_RATIO)

        # Offset centrage en pixels physiques (taille physique = logique * _s)
        px = cx - round(img_w * _s) // 2
        py = cy - round(img_h * _s) // 2

        popup = ctk.CTkToplevel(self.app)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.geometry(f"{img_w}x{img_h}+{px}+{py}")
        popup.lift()
        self._zoom_popup = popup

        def _conditional_close(p):
            if getattr(self, '_zoom_popup', None) is not p:
                return
            try:
                if p.winfo_exists():
                    p.destroy()
            except Exception:
                pass
            self._zoom_popup = None

        lbl = ctk.CTkLabel(popup, text="", fg_color="#1c1a20",
                           width=img_w, height=img_h, corner_radius=8)
        lbl.pack(fill="both", expand=True)

        close = lambda e=None: _conditional_close(popup)
        popup.bind("<Button-1>", close)
        popup.bind("<Escape>", close)
        lbl.bind("<Button-1>", close)

        # Clic en dehors du popup → fermer. bind_all capte tous les clics de l'app.
        # _active démarre à False pour ignorer le clic d'ouverture lui-même.
        _active = [False]

        def _activate():
            if popup.winfo_exists():
                _active[0] = True

        def _on_any_click(event):
            if not _active[0]:
                return
            if not popup.winfo_exists():
                _active[0] = False
                return
            if getattr(self, '_zoom_popup', None) is not popup:
                _active[0] = False
                return
            try:
                x1 = popup.winfo_rootx()
                y1 = popup.winfo_rooty()
                x2 = x1 + popup.winfo_width()
                y2 = y1 + popup.winfo_height()
                if not (x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2):
                    _active[0] = False
                    _conditional_close(popup)
            except Exception:
                _active[0] = False
                _conditional_close(popup)

        self.app.bind_all("<ButtonPress-1>", _on_any_click, add="+")
        self.after(200, _activate)

        self._zoom_img_ref = None

        def _load():
            try:
                path = card.image_path
                if self._show_back:
                    back = getattr(card, "back_image_path", None)
                    if back and os.path.isfile(back):
                        path = back
                if path.endswith("_1200dpi.png"):
                    native = path.replace("_1200dpi.png", ".png")
                    if os.path.exists(native):
                        path = native
                img = Image.open(path).resize((img_w, img_h), Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, size=(img_w, img_h))
                self._zoom_img_ref = ctk_img

                def _apply():
                    if popup.winfo_exists():
                        lbl.configure(image=ctk_img, fg_color="transparent")
                self.after(0, _apply)
            except Exception:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def refresh_stats(self) -> None:
        """À appeler après chaque modification du deck."""
        if self._tab == "stats":
            self._build_stats()
