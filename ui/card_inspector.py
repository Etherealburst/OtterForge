"""
ui/card_inspector.py
--------------------
Panneau latéral droit — dual-mode :
  CARD : aperçu de la carte sélectionnée (image + infos)
  STATS : composition du deck actif
"""

import os
import json
import threading
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from config import CACHE_DIR


# ── Cache helpers (used by inspector buttons) ─────────────────────────────────

def _cache_stem(image_path: str) -> str:
    """Return the root stem (no suffix, no face tag) for a cache image path."""
    base = image_path
    for suf in ("_1200dpi.png", "_mpc300.png"):
        if base.endswith(suf):
            base = base[: -len(suf)] + ".png"
            break
    # Strip .png
    stem = base[:-4] if base.endswith(".png") else base
    # Strip _face0 / _face1
    for face in ("_face0", "_face1"):
        if stem.endswith(face):
            stem = stem[: -len(face)]
            break
    return stem


def _delete_card_cache_files(image_path: str) -> int:
    """Delete all cache variants for a card. Returns count of deleted files."""
    stem = _cache_stem(image_path)
    variants = [
        f"{stem}.png",
        f"{stem}_1200dpi.png",
        f"{stem}_mpc300.png",
        f"{stem}_orig.png",
        f"{stem}_face0.png",
        f"{stem}_face0_1200dpi.png",
        f"{stem}_face0_mpc300.png",
        f"{stem}_face0_orig.png",
        f"{stem}_face1.png",
        f"{stem}_face1_1200dpi.png",
        f"{stem}_face1_mpc300.png",
        f"{stem}_face1_orig.png",
    ]
    deleted = 0
    for p in variants:
        if os.path.exists(p):
            try:
                os.remove(p)
                deleted += 1
            except OSError:
                pass
    return deleted


def _load_card_meta(image_path: str) -> dict | None:
    """Load Scryfall card_json from the meta cache, inferring set+CN from the filename."""
    stem = _cache_stem(image_path)
    parts = os.path.basename(stem).split("_")
    if len(parts) >= 2:
        collector = parts[-1]
        set_code = parts[-2]
        meta_path = os.path.join(os.path.dirname(stem), f"_meta_{set_code}_{collector}.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None

_CARD_RATIO = 420 / 300   # hauteur / largeur MTG standard
_METADATA_CACHE_PATH = os.path.join(CACHE_DIR, "card_metadata.json")
_TYPE_ORDER = ["Creature", "Land", "Instant", "Sorcery",
               "Enchantment", "Artifact", "Planeswalker", "Battle"]


class _InspectorTooltip:
    """Tooltip léger pour les lignes de stats de l'inspecteur."""

    def __init__(self, widget: tk.Widget, text_fn) -> None:
        self._widget = widget
        self._text_fn = text_fn   # callable → str (évalué au moment du survol)
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip:
            return
        text = self._text_fn()
        if not text:
            return
        w = self._widget
        x = w.winfo_rootx() + 4
        y = w.winfo_rooty() + w.winfo_height() + 4
        self._tip = tw = tk.Toplevel(w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=text,
            background="#3a3548", foreground="#f0ece4",
            relief="solid", borderwidth=1,
            highlightbackground="#c04828", highlightthickness=1,
            font=("Segoe UI", 20),
            padx=16, pady=10, justify="left",
        ).pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def _parse_types(type_line: str) -> list:
    found = [t for t in _TYPE_ORDER if t in type_line]
    return found if found else ["Other"]


def _card_key(name: str) -> str:
    return name.lower().split(" // ")[0].strip()


class CardInspectorPanel(ctk.CTkFrame):

    WIDTH = 270

    def __init__(self, master, app):
        super().__init__(master, width=self.WIDTH, corner_radius=0, fg_color="#1c1a20")
        self.app = app
        self.pack_propagate(False)

        self._current_card = None
        self._img_ref = None
        self._img_load_gen = 0
        self._tab = "card"
        self._show_back = False
        self._metadata_cache: dict = self._load_metadata_cache()
        self._metadata_pending: bool = False
        self._metadata_failed: bool = False

        img_w = self.WIDTH - 24
        img_h = int(img_w * _CARD_RATIO)
        self._img_size = (img_w, img_h)

        self._build_header()
        self._build_card_pane()
        self._build_stats_pane()

        # Afficher le pane CARD par défaut
        self._stats_pane.pack_forget()
        self._card_pane.pack(fill="both", expand=True)

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="#1c1a20", height=34)
        header.pack(fill="x", padx=8, pady=(6, 4))
        header.pack_propagate(False)

        self._btn_card = ctk.CTkButton(
            header, text="CARD", width=68, height=28,
            font=ctk.CTkFont(size=10),
            fg_color="#c04828", hover_color="#a83820",
            command=lambda: self._switch_tab("card"),
        )
        self._btn_card.pack(side="left", padx=(0, 2))

        self._btn_stats = ctk.CTkButton(
            header, text="STATS", width=68, height=28,
            font=ctk.CTkFont(size=10),
            fg_color="#28252e", hover_color="#34303e",
            command=lambda: self._switch_tab("stats"),
        )
        self._btn_stats.pack(side="left")

        ctk.CTkFrame(self, height=1, fg_color="#28252e").pack(fill="x", padx=0, pady=(0, 4))

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
            text="Click on a card\nto inspect it",
            font=ctk.CTkFont(size=11), text_color="#a09aaa",
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
            font=ctk.CTkFont(size=10), text_color="#a09aaa", anchor="w",
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
            font=ctk.CTkFont(size=9), text_color="#a09aaa", anchor="w",
        )
        self._dfc_label.pack(padx=14, anchor="w", pady=(2, 0))

        # Action buttons
        btn_row = ctk.CTkFrame(self._card_pane, fg_color="transparent")
        btn_row.pack(padx=12, pady=(10, 4), fill="x")

        self._btn_clear_cache = ctk.CTkButton(
            btn_row, text="Clear Cache", width=112, height=26,
            font=ctk.CTkFont(size=10),
            fg_color="#28252e", hover_color="#3a3548",
            state="disabled",
            command=self._on_clear_cache,
        )
        self._btn_clear_cache.pack(side="left", padx=(0, 4))

        self._btn_move_wm = ctk.CTkButton(
            btn_row, text="Move WM", width=112, height=26,
            font=ctk.CTkFont(size=10),
            fg_color="#28252e", hover_color="#3a3548",
            state="disabled",
            command=self._on_move_watermark,
        )
        self._btn_move_wm.pack(side="left")

    # ── Stats pane ────────────────────────────────────────────────────────────

    def _build_stats_pane(self) -> None:
        self._stats_pane = ctk.CTkScrollableFrame(self, fg_color="transparent")
        # Sur Windows, la molette va au widget focusé — donner le focus au canvas
        # interne au survol pour que le scroll fonctionne sans cliquer d'abord.
        def _focus_inner(e=None):
            for attr in ("_parent_canvas", "_canvas"):
                w = getattr(self._stats_pane, attr, None)
                if w:
                    w.focus_set()
                    break
        self._stats_pane.bind("<Enter>", _focus_inner, add="+")

    def _build_stats(self) -> None:
        for w in self._stats_pane.winfo_children():
            w.destroy()

        deck = self.app.deck_manager.active_deck()
        if not deck or not deck.cards:
            ctk.CTkLabel(
                self._stats_pane, text="Empty deck",
                text_color="#a09aaa", font=ctk.CTkFont(size=11),
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

        # Mana curve + type distribution (require Scryfall metadata)
        missing = [c.name for c in deck.cards
                   if _card_key(c.name) not in self._metadata_cache]
        if missing and not self._metadata_pending and not self._metadata_failed:
            self._metadata_pending = True
            threading.Thread(
                target=self._fetch_metadata, args=(missing,), daemon=True,
            ).start()

        if not missing:
            self._build_mana_curve(deck)
            self._build_type_dist(deck)
        elif self._metadata_pending:
            ctk.CTkLabel(
                self._stats_pane, text="Fetching card data…",
                text_color="#a09aaa", font=ctk.CTkFont(size=10),
            ).pack(pady=8)

    # ── Metadata cache (Scryfall CMC + types) ────────────────────────────────

    def _load_metadata_cache(self) -> dict:
        try:
            with open(_METADATA_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _merge_metadata(self, new_data: dict) -> None:
        """Main-thread merge — safe from race conditions with _build_stats iterators."""
        self._metadata_cache.update(new_data)
        self._save_metadata_cache()
        self.refresh_stats()

    def _save_metadata_cache(self) -> None:
        os.makedirs("cache", exist_ok=True)
        try:
            with open(_METADATA_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._metadata_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _fetch_metadata(self, names: list) -> None:
        """Background thread: fetch CMC + types for missing cards via Scryfall."""
        import requests
        identifiers = [{"name": n} for n in names[:75]]
        try:
            resp = requests.post(
                "https://api.scryfall.com/cards/collection",
                json={"identifiers": identifiers},
                headers={"User-Agent": "OtterForge/1.0"},
                timeout=15,
            )
            if resp.ok:
                new_data = {}
                for card in resp.json().get("data", []):
                    key = _card_key(card["name"])
                    type_line = card.get("type_line", "")
                    if "card_faces" in card:
                        type_line = card["card_faces"][0].get("type_line", type_line)
                    new_data[key] = {
                        "cmc": int(card.get("cmc") or 0),
                        "types": _parse_types(type_line),
                    }
                self.after(0, self._merge_metadata, new_data)
            else:
                self._metadata_failed = True
        except Exception as e:
            print(f"[Inspector] Metadata fetch: {e}")
            self._metadata_failed = True
        finally:
            self._metadata_pending = False

    # ── Mana curve chart ──────────────────────────────────────────────────────

    def _build_mana_curve(self, deck) -> None:
        buckets = [0] * 7  # index 0–6, where 6 = "6+"
        for c in deck.cards:
            meta = self._metadata_cache.get(_card_key(c.name), {})
            if "Land" in meta.get("types", []):
                continue  # exclude lands from mana curve
            cmc = min(int(meta.get("cmc", 0)), 6)
            buckets[cmc] += c.count

        if not any(buckets):
            return

        self._last_mana_buckets = list(buckets)
        self._stat_section("MANA CURVE")

        ctk.CTkLabel(
            self._stats_pane,
            text="(lands excluded)",
            font=ctk.CTkFont(size=8),
            text_color="#a09aaa",
            anchor="w",
        ).pack(padx=8, anchor="w", pady=(0, 2))

        max_count = max(buckets) or 1
        labels = ["0", "1", "2", "3", "4", "5", "6+"]
        PADDING_TOP = 16
        BAR_AREA_H = 150
        GAP = 4
        SIDE_PAD = 10  # padding visible de chaque côté des barres
        # WIDTH=270, scrollbar CTkScrollableFrame ~18px → contenu utile ≈252px
        # CANVAS_W=240 + padx=4*2=8 → 248px, tient dans les 252px disponibles
        CANVAS_W = self.WIDTH - 30
        USABLE_W = CANVAS_W - 2 * SIDE_PAD
        BAR_W = max(8, (USABLE_W - (len(labels) - 1) * GAP) // len(labels))
        CANVAS_H = PADDING_TOP + BAR_AREA_H + 32
        total_bars_w = len(labels) * BAR_W + (len(labels) - 1) * GAP
        bar_start_x = SIDE_PAD + max(0, (USABLE_W - total_bars_w) // 2)

        canvas = tk.Canvas(
            self._stats_pane, bg="#221f28",
            width=CANVAS_W, height=CANVAS_H,
            highlightthickness=0,
            cursor="hand2",
        )
        canvas.pack(pady=(2, 6), padx=4, anchor="center")
        canvas.bind("<Button-1>", lambda e: self._open_mana_curve_zoom())

        COLORS = ["#7ac878", "#78b4d8", "#a078d8", "#c89630", "#d07820", "#c05020", "#c04828"]
        for i, (lbl, cnt) in enumerate(zip(labels, buckets)):
            x = bar_start_x + i * (BAR_W + GAP)
            bar_h = int((cnt / max_count) * BAR_AREA_H) if cnt > 0 else 0
            if bar_h > 0:
                y1 = PADDING_TOP + BAR_AREA_H - bar_h
                canvas.create_rectangle(x, y1, x + BAR_W, PADDING_TOP + BAR_AREA_H,
                                        fill=COLORS[i], outline="")
            if cnt > 0:
                canvas.create_text(x + BAR_W // 2, PADDING_TOP + BAR_AREA_H - bar_h - 4,
                                   text=str(cnt), fill="#f0ece4",
                                   font=("Segoe UI", 10, "bold"), anchor="s")
            canvas.create_text(x + BAR_W // 2, PADDING_TOP + BAR_AREA_H + 14,
                               text=lbl, fill="#a09aaa",
                               font=("Segoe UI", 10))

        canvas.create_text(CANVAS_W - 4, CANVAS_H - 4,
                           text="🔍 zoom", fill="#a09aaa",
                           font=("Segoe UI", 8), anchor="se")

    # ── Mana curve zoom popup ─────────────────────────────────────────────────

    def _open_mana_curve_zoom(self) -> None:
        """Ouvre un popup agrandi de la courbe de mana. Échap ou Close pour fermer."""
        buckets = getattr(self, "_last_mana_buckets", None)
        if not buckets or not any(buckets):
            return

        if getattr(self, "_curve_popup", None) is not None:
            try:
                self._curve_popup.destroy()
            except Exception:
                pass
            self._curve_popup = None

        self.app.update_idletasks()
        ws = self.app.workspace
        ws.update_idletasks()

        # DPI scale : CTkToplevel.geometry() applique _scale à la taille (WxH)
        # mais PAS à la position (+x+y). +x+y doit être en pixels physiques écran.
        try:
            from customtkinter import ScalingTracker
            _scale = ScalingTracker.get_window_scaling(self.app)
        except Exception:
            _scale = max(1.0, self.app.winfo_fpixels('1i') / 96.0)

        # Workspace en pixels physiques
        ws_rx = ws.winfo_rootx()
        ws_ry = ws.winfo_rooty()
        ws_pw = ws.winfo_width()
        ws_ph = ws.winfo_height()

        # Popup en pixels logiques (CTk scale automatiquement la taille)
        POP_W = max(360, min(int((ws_pw - 40) / _scale), 820))
        POP_H = max(280, min(int((ws_ph - 40) / _scale), 540))

        # Taille physique réelle du popup pour calculer le centrage
        phys_w = round(POP_W * _scale)
        phys_h = round(POP_H * _scale)
        px = ws_rx + (ws_pw - phys_w) // 2
        py = ws_ry + (ws_ph - phys_h) // 2

        popup = ctk.CTkToplevel(self.app)
        popup.title("Mana Curve")
        popup.resizable(True, True)
        popup.geometry(f"{POP_W}x{POP_H}+{px}+{py}")
        popup.grab_set()
        popup.lift()
        self._curve_popup = popup

        def _close(e=None):
            if popup.winfo_exists():
                popup.destroy()
            self._curve_popup = None

        popup.protocol("WM_DELETE_WINDOW", _close)
        popup.bind("<Escape>", _close)

        bg = ctk.CTkFrame(popup, fg_color="#1c1a20", corner_radius=10,
                          border_width=1, border_color="#34303e")
        bg.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(bg, text="MANA CURVE",
                     font=ctk.CTkFont(size=9), text_color="#a09aaa").pack(pady=(10, 0))

        canvas = tk.Canvas(bg, bg="#1c1a20", highlightthickness=0, cursor="hand2")
        canvas.pack(fill="both", expand=True, padx=16, pady=(4, 4))

        ctk.CTkButton(bg, text="Close", width=80, height=28, command=_close).pack(pady=(0, 8))

        labels = ["0", "1", "2", "3", "4", "5", "6+"]
        COLORS = ["#7ac878", "#78b4d8", "#a078d8", "#c89630", "#d07820", "#c05020", "#c04828"]
        _drawn = [False]

        def _draw_bars(event=None):
            if _drawn[0]:
                return
            CW = canvas.winfo_width()
            CH = canvas.winfo_height()
            if CW < 10 or CH < 10:
                return
            _drawn[0] = True
            canvas.delete("all")
            PADDING_TOP = 22
            LABEL_AREA = 44
            GAP = max(4, CW // 70)
            SIDE_PAD = max(16, CW // 20)
            USABLE_W = CW - 2 * SIDE_PAD
            BAR_W = max(8, (USABLE_W - (len(labels) - 1) * GAP) // len(labels))
            BAR_AREA_H = CH - PADDING_TOP - LABEL_AREA
            total_bars_w = len(labels) * BAR_W + (len(labels) - 1) * GAP
            start_x = SIDE_PAD + max(0, (USABLE_W - total_bars_w) // 2)
            max_count = max(buckets) or 1
            font_sz = max(11, min(22, BAR_W // 4))
            # Reserve headroom above tallest bar so count numbers never clip at the top.
            NUMBER_CLEARANCE = font_sz + 10
            BAR_H_MAX = max(4, BAR_AREA_H - NUMBER_CLEARANCE)

            for i, (lbl, cnt) in enumerate(zip(labels, buckets)):
                x = start_x + i * (BAR_W + GAP)
                bar_h = int((cnt / max_count) * BAR_H_MAX) if cnt > 0 else 0
                if bar_h > 0:
                    y1 = PADDING_TOP + BAR_AREA_H - bar_h
                    canvas.create_rectangle(x, y1, x + BAR_W, PADDING_TOP + BAR_AREA_H,
                                            fill=COLORS[i], outline="")
                if cnt > 0:
                    canvas.create_text(x + BAR_W // 2, PADDING_TOP + BAR_AREA_H - bar_h - 5,
                                       text=str(cnt), fill="#f0ece4",
                                       font=("Segoe UI", font_sz, "bold"), anchor="s")
                canvas.create_text(x + BAR_W // 2, PADDING_TOP + BAR_AREA_H + LABEL_AREA // 2,
                                   text=lbl, fill="#a09aaa",
                                   font=("Segoe UI", font_sz))

        canvas.bind("<Configure>", _draw_bars)

    # ── Type distribution chart ───────────────────────────────────────────────

    def _build_type_dist(self, deck) -> None:
        type_counts: dict[str, int] = {}
        type_cards: dict[str, list[str]] = {}   # type → noms uniques de cartes
        for c in deck.cards:
            meta = self._metadata_cache.get(_card_key(c.name), {})
            for t in meta.get("types", ["Other"]):
                type_counts[t] = type_counts.get(t, 0) + c.count
                type_cards.setdefault(t, []).append(c.name)

        if not type_counts:
            return

        self._stat_section("TYPES")

        total = sum(type_counts.values())
        max_cnt = max(type_counts.values()) or 1
        ordered = [t for t in _TYPE_ORDER + ["Other"] if t in type_counts]

        for type_name in ordered:
            cnt = type_counts[type_name]
            ratio = cnt / max_cnt
            names = type_cards.get(type_name, [])

            row = ctk.CTkFrame(self._stats_pane, fg_color="#221f28", corner_radius=4, height=22)
            row.pack(fill="x", pady=1, padx=4)
            row.pack_propagate(False)

            ctk.CTkLabel(
                row, text=type_name, width=74,
                font=ctk.CTkFont(size=10), text_color="#c4bfb8", anchor="w",
            ).pack(side="left", padx=(6, 4))

            bar_outer = ctk.CTkFrame(row, fg_color="#2a2630", corner_radius=2, height=6)
            bar_outer.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=5)
            bar_outer.pack_propagate(False)
            ctk.CTkFrame(bar_outer, fg_color="#c04828", corner_radius=2).place(
                relx=0, rely=0, relwidth=ratio, relheight=1.0)

            pct = int(cnt / total * 100) if total else 0
            ctk.CTkLabel(
                row, text=f"{cnt} ({pct}%)", width=48,
                font=ctk.CTkFont(size=10), text_color="#f0ece4",
            ).pack(side="right", padx=(0, 5))

            # Tooltip : count only, no card names
            def _make_tip(cnt=cnt, pct=pct, t=type_name):
                return f"{t}: {cnt} card{'s' if cnt != 1 else ''}  ({pct}% of deck)"

            _InspectorTooltip(row, _make_tip)

    def _stat_section(self, text: str) -> None:
        f = ctk.CTkFrame(self._stats_pane, fg_color="transparent", height=16)
        f.pack(fill="x", padx=4, pady=(6, 1))
        f.pack_propagate(False)
        ctk.CTkFrame(f, width=2, fg_color="#c04828", corner_radius=0).pack(
            side="left", fill="y", padx=(0, 4))
        ctk.CTkLabel(
            f, text=text, font=ctk.CTkFont(size=8),
            text_color="#a09aaa", anchor="w",
        ).pack(side="left")

    def _stat_row(self, label: str, value, accent: bool = False) -> None:
        row = ctk.CTkFrame(self._stats_pane, fg_color="#221f28", corner_radius=4, height=22)
        row.pack(fill="x", pady=1, padx=4)
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=label, font=ctk.CTkFont(size=10),
            text_color="#c4bfb8", anchor="w",
        ).pack(side="left", padx=(4, 2), pady=1, fill="x", expand=True)
        ctk.CTkLabel(
            row, text=str(value),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#c04828" if accent else "#f0ece4",
        ).pack(side="right", padx=6)

    # ── API publique ──────────────────────────────────────────────────────────

    def show_card(self, card, show_back: bool = False) -> None:
        """Appelé depuis workspace ou sidebar quand une carte est sélectionnée."""
        self._current_card = card
        self._show_back = show_back
        self._img_load_gen += 1
        gen = self._img_load_gen
        if self._tab != "card":
            self._switch_tab("card")

        # Labels instantanés
        self._name_label.configure(text=card.name)
        count = card.count
        self._count_label.configure(text=f"×{count}  in deck")
        self._placeholder_text.place_forget()

        has_back = bool(getattr(card, "back_image_path", None))
        if show_back and has_back:
            self._dfc_label.configure(text="← back face", text_color="#c04828")
        elif has_back:
            self._dfc_label.configure(text="Double-faced card  ·  DFC", text_color="#a09aaa")
        else:
            self._dfc_label.configure(text="", text_color="#a09aaa")

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

        # Enable action buttons
        self._btn_clear_cache.configure(state="normal")
        self._btn_move_wm.configure(state="normal")

        # Image en thread
        threading.Thread(
            target=self._load_image_bg,
            args=(card, show_back, gen),
            daemon=True,
        ).start()

    def _load_image_bg(self, card, show_back: bool = False, gen: int = 0) -> None:
        if gen != self._img_load_gen:
            return
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
        """Zoom popup — deux blocs watermark draggables.

        Charge l'image originale (_orig.png) si disponible : artiste visible,
        pas de doublon, fond transparent car le texte est cuisiné dans le PIL.
        Clic hors popup → dialog enfant tk.Toplevel (popup reste visible).
        """
        card = self._current_card
        if card is None:
            return

        if getattr(self, '_zoom_popup', None) is not None:
            try:
                self._zoom_popup.destroy()
            except Exception:
                pass
            self._zoom_popup = None

        self.app.update_idletasks()
        ws = self.app.workspace
        ws.update_idletasks()

        try:
            from customtkinter import ScalingTracker
            _scale = ScalingTracker.get_window_scaling(self.app)
        except Exception:
            _scale = max(1.0, self.app.winfo_fpixels('1i') / 96.0)

        from PIL import ImageTk as _ImageTk

        # Cap to workspace with margin, keep card ratio
        max_phys_w = max(300, ws.winfo_width()  - 40)
        max_phys_h = max(420, ws.winfo_height() - 40)
        img_w_log = min(500, int(max_phys_w / _scale))
        img_h_log = int(img_w_log * _CARD_RATIO)
        if img_h_log > int(max_phys_h / _scale):
            img_h_log = int(max_phys_h / _scale)
            img_w_log = int(img_h_log / _CARD_RATIO)
        cv_w = round(img_w_log * _scale)
        cv_h = round(img_h_log * _scale)

        ws_rx = ws.winfo_rootx()
        ws_ry = ws.winfo_rooty()
        ws_pw = ws.winfo_width()
        ws_ph = ws.winfo_height()
        px = max(0, ws_rx + (ws_pw - cv_w) // 2)
        py = max(0, ws_ry + (ws_ph - cv_h) // 2)

        popup = tk.Toplevel(self.app)
        popup.overrideredirect(True)
        popup.geometry(f"{cv_w}x{cv_h}+{px}+{py}")
        popup.lift()
        self._zoom_popup = popup

        def _conditional_close(p):
            if getattr(self, '_zoom_popup', None) is not p:
                return
            try:
                p.grab_release()
            except Exception:
                pass
            try:
                if p.winfo_exists():
                    p.destroy()
            except Exception:
                pass
            self._zoom_popup = None
            _base_img[0] = None  # libère l'image PIL de la closure

        canvas = tk.Canvas(popup, width=cv_w, height=cv_h,
                           bg="#1c1a20", highlightthickness=0, cursor="fleur")
        canvas.pack()

        # ── Watermark geometry ────────────────────────────────────────────────
        cur_ox,     cur_oy     = getattr(card, "watermark_offset",     (0, 0))
        cur_nfs_ox, cur_nfs_oy = getattr(card, "watermark_nfs_offset", (0, 0))

        strip_h = max(14, int(cv_h * 0.08)) - 9
        y_top   = cv_h - strip_h
        sz      = max(9, int(cv_h * 0.020) - 1)
        copy_y  = cv_h - max(sz + 2, int(cv_h * 0.065))
        base_ty = max(y_top + 1, copy_y) - 3
        base_sx = int(cv_w * 0.193)

        # ── PIL font ──────────────────────────────────────────────────────────
        _font_cands = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
                       r"C:\Windows\Fonts\segoeui.ttf"]
        pil_font = None
        for _fp in _font_cands:
            try:
                pil_font = ImageFont.truetype(_fp, sz)
                break
            except Exception:
                pass
        if pil_font is None:
            pil_font = ImageFont.load_default()

        _m = Image.new("RGB", (1, 1))
        _md = ImageDraw.Draw(_m)
        try:
            stamp_w = _md.textbbox((0, 0), "OtterForge Proxy", font=pil_font)[2]
            nfs_tw  = _md.textbbox((0, 0), "Not for sale",     font=pil_font)[2]
        except AttributeError:
            stamp_w = len("OtterForge Proxy") * max(4, sz * 6 // 10)
            nfs_tw  = len("Not for sale")     * max(4, sz * 6 // 10)

        # Determine apply_fill from card metadata so NFS position matches actual watermark
        _cj = _load_card_meta(card.image_path)
        _apply_fill = True
        if _cj:
            _bc = _cj.get("border_color", "")
            _fe = _cj.get("frame_effects") or []
            if (_bc in ("white", "borderless", "silver")
                    or any(e in _fe for e in ("extendedart", "showcase", "inverted", "fullart"))
                    or _cj.get("full_art", False)):
                _apply_fill = False
            elif _bc not in ("black", "gold"):
                _apply_fill = False

        if _apply_fill:
            base_nfs_x = cv_w - max(4, cv_w // 60) - nfs_tw - 40
        else:
            base_nfs_x = max(cv_w // 2, cv_w - max(4, cv_w // 60) - nfs_tw - 190)

        init_sx    = base_sx    + round(cur_ox     * cv_w / 672)
        init_ty    = base_ty    + round(cur_oy     * cv_h / 936)
        init_nfs_x = base_nfs_x + round(cur_nfs_ox * cv_w / 672)
        init_nfs_y = base_ty    + round(cur_nfs_oy * cv_h / 936)

        # ── PIL image state ───────────────────────────────────────────────────
        _base_img   = [None]
        _canvas_img = [None]
        _canvas_tk  = [None]

        # ── State variables ────────────────────────────────────────────────────
        _drag_origin = [0, 0]
        _act_group   = [None]
        _dt_stamp    = [0, 0]
        _dt_nfs      = [0, 0]
        _dragged     = [False]
        _asking      = [False]

        def _refresh_canvas():
            if _base_img[0] is None:
                return
            img  = _base_img[0].copy()
            draw = ImageDraw.Draw(img)
            sx = init_sx    + _dt_stamp[0]
            sy = init_ty    + _dt_stamp[1]
            nx = init_nfs_x + _dt_nfs[0]
            ny = init_nfs_y + _dt_nfs[1]
            for ddx, ddy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((sx+ddx, sy+ddy), "OtterForge Proxy", fill=(0,0,0), font=pil_font)
                draw.text((nx+ddx, ny+ddy), "Not for sale",     fill=(0,0,0), font=pil_font)
            draw.text((sx, sy), "OtterForge Proxy", fill=(255,255,255), font=pil_font)
            draw.text((nx, ny), "Not for sale",     fill=(255,255,255), font=pil_font)
            new_tk = _ImageTk.PhotoImage(img)
            if _canvas_img[0] is None:
                _canvas_img[0] = canvas.create_image(0, 0, image=new_tk, anchor="nw")
            else:
                canvas.itemconfig(_canvas_img[0], image=new_tk)
            _canvas_tk[0] = new_tk
            self._zoom_img_ref = new_tk

        # ── Save dialog — overlay frame inside popup (popup reste visible) ──────
        def _show_save_dialog():
            if _asking[0]:
                return
            _asking[0] = True
            ov_w = min(cv_w - 20, 600)
            ov_h = 300
            ov_x = (cv_w - ov_w) // 2
            ov_y = (cv_h - ov_h) // 2
            overlay = tk.Frame(
                popup, bg="#1c1a20",
                highlightbackground="#c04828", highlightthickness=2,
            )
            overlay.place(x=ov_x, y=ov_y, width=ov_w, height=ov_h)
            overlay.lift()

            tk.Label(overlay, text="Save changes?", bg="#1c1a20", fg="#f0ece4",
                     font=("Segoe UI", 22, "bold")).pack(pady=(44, 22))
            btn_row = tk.Frame(overlay, bg="#1c1a20")
            btn_row.pack()

            def _save():
                overlay.destroy()
                _asking[0] = False
                # Scale drag delta (cv_w/cv_h space) back to 672×936 reference space.
                # cv_w is always >= 300 (enforced above), so minimum resolution is ~2px.
                card.watermark_offset = (
                    cur_ox + round(_dt_stamp[0] * 672 / cv_w),
                    cur_oy + round(_dt_stamp[1] * 936 / cv_h),
                )
                card.watermark_nfs_offset = (
                    cur_nfs_ox + round(_dt_nfs[0] * 672 / cv_w),
                    cur_nfs_oy + round(_dt_nfs[1] * 936 / cv_h),
                )
                if hasattr(self.app, "_auto_save"):
                    self.app._auto_save()
                _conditional_close(popup)
                self._reapply_watermark(card)

            def _back():
                # Close overlay only — popup (zoom) stays open
                overlay.destroy()
                _asking[0] = False
                _dt_stamp[0] = _dt_stamp[1] = 0
                _dt_nfs[0]   = _dt_nfs[1]   = 0
                _dragged[0]  = False
                _refresh_canvas()

            tk.Button(btn_row, text="Save", bg="#c04828", fg="#f0ece4",
                      font=("Segoe UI", 16, "bold"), relief="flat", padx=28, pady=12,
                      command=_save).pack(side="left", padx=18)
            tk.Button(btn_row, text="Back", bg="#28252e", fg="#a09aaa",
                      font=("Segoe UI", 16), relief="flat", padx=28, pady=12,
                      command=_back).pack(side="left", padx=18)

        def _try_close():
            if _asking[0]:
                return
            if _dragged[0]:
                _show_save_dialog()
            else:
                _conditional_close(popup)

        # ── Drag handlers ─────────────────────────────────────────────────────
        def _on_press(e):
            if _asking[0]:
                return
            M  = max(12, sz + 4)
            sx = init_sx    + _dt_stamp[0]
            sy = init_ty    + _dt_stamp[1]
            nx = init_nfs_x + _dt_nfs[0]
            ny = init_nfs_y + _dt_nfs[1]
            if sx - M <= e.x <= sx + stamp_w + M and sy - M <= e.y <= sy + sz + M:
                _act_group[0] = "stamp"
            elif nx - M <= e.x <= nx + nfs_tw + M and ny - M <= e.y <= ny + sz + M:
                _act_group[0] = "nfs"
            else:
                _act_group[0] = None
                _try_close()
            _drag_origin[0] = e.x
            _drag_origin[1] = e.y

        def _on_motion(e):
            g = _act_group[0]
            if g is None:
                return
            ddx = e.x - _drag_origin[0]
            ddy = e.y - _drag_origin[1]
            if g == "stamp":
                if ddx != _dt_stamp[0] or ddy != _dt_stamp[1]:
                    _dt_stamp[0] = ddx
                    _dt_stamp[1] = ddy
                    _dragged[0] = True
                    _refresh_canvas()
            else:
                if ddx != _dt_nfs[0] or ddy != _dt_nfs[1]:
                    _dt_nfs[0] = ddx
                    _dt_nfs[1] = ddy
                    _dragged[0] = True
                    _refresh_canvas()

        def _on_release(e):
            was_group = _act_group[0]
            _act_group[0] = None
            if was_group is not None:
                # Distinguish click (≤4px) from drag (>4px) for THIS gesture only
                dx = abs(e.x - _drag_origin[0])
                dy = abs(e.y - _drag_origin[1])
                if dx <= 4 and dy <= 4:
                    _try_close()

        canvas.bind("<ButtonPress-1>",   _on_press)
        canvas.bind("<B1-Motion>",       _on_motion)
        canvas.bind("<ButtonRelease-1>", _on_release)
        popup.bind("<Escape>", lambda e: _try_close())

        # ── Outside-click via grab_set ────────────────────────────────────────
        # grab_set() redirects ALL pointer events to this popup.
        # Clicks outside the popup bounds have negative or out-of-range coords.
        def _on_popup_press(event):
            if _asking[0]:
                return
            outside = not (0 <= event.x <= cv_w and 0 <= event.y <= cv_h)
            if outside:
                _try_close()

        popup.grab_set()
        popup.bind("<ButtonPress-1>", _on_popup_press, add="+")

        # ── Load image — prefer _orig.png (pre-watermark) for clean preview ───
        self._zoom_img_ref = None

        def _load():
            try:
                path = card.image_path
                if self._show_back:
                    back = getattr(card, "back_image_path", None)
                    if back and os.path.isfile(back):
                        path = back
                # Prefer native .png over _1200dpi for speed
                if path.endswith("_1200dpi.png"):
                    native = path.replace("_1200dpi.png", ".png")
                    if os.path.exists(native):
                        path = native
                # Prefer _orig.png (pre-watermark) so artist name is visible
                orig = path.replace(".png", "_orig.png")
                if os.path.exists(orig):
                    path = orig
                else:
                    # _orig.png absent — try to fetch clean image from Scryfall in-memory
                    card_json = _load_card_meta(card.image_path)
                    if card_json:
                        try:
                            import requests, io as _io
                            faces = card_json.get("card_faces") or []
                            if faces and self._show_back and len(faces) > 1:
                                uris = faces[1].get("image_uris", {})
                            elif faces:
                                uris = faces[0].get("image_uris", {})
                            else:
                                uris = card_json.get("image_uris", {})
                            url = uris.get("normal") or uris.get("large")
                            if url:
                                resp = requests.get(url, timeout=15,
                                                    headers={"User-Agent": "OtterForge/1.0"})
                                if resp.ok:
                                    img = Image.open(_io.BytesIO(resp.content)).convert("RGB")
                                    img = img.resize((cv_w, cv_h), Image.LANCZOS)
                                    # Also save as _orig.png for next time
                                    try:
                                        save_path = path.replace(".png", "_orig.png")
                                        img.save(save_path, "PNG", compress_level=6)
                                    except Exception:
                                        pass
                                    _base_img[0] = img
                                    self.after(0, _refresh_canvas)
                                    return
                        except Exception:
                            pass  # fall through to watermarked image
                img = Image.open(path).convert("RGB").resize((cv_w, cv_h), Image.LANCZOS)
                _base_img[0] = img
                self.after(0, _refresh_canvas)
            except Exception as exc:
                print(f"[zoom popup] load: {exc}")

        threading.Thread(target=_load, daemon=True).start()

    # ── Inspector action buttons ──────────────────────────────────────────────

    def _on_clear_cache(self) -> None:
        card = self._current_card
        if card is None:
            return
        deleted = _delete_card_cache_files(card.image_path)
        if hasattr(self.app, "workspace"):
            self.app.workspace._pil_cache.clear()
        # Reset inspector to placeholder
        self._img_ref = None
        self._img_label.configure(image="", fg_color="#221f28")
        self._placeholder_text.place(in_=self._img_label, relx=0.5, rely=0.5, anchor="center")
        if hasattr(self.app, "statusbar"):
            self.app.statusbar.set_status(
                f"Cache cleared ({deleted} file(s)). Re-search to reapply."
            )

    def _on_move_watermark(self) -> None:
        card = self._current_card
        if card is None:
            return
        _WatermarkOffsetDialog(self, card, self.app)

    def _reapply_watermark(self, card) -> None:
        """Delete cache, re-download from Scryfall, reapply watermark with card.watermark_offset."""
        if not hasattr(self.app, "scryfall"):
            return
        if hasattr(self.app, "statusbar"):
            self.app.statusbar.set_status("Re-fetching card for watermark reapply…")

        def _worker():
            try:
                image_path = card.image_path
                # Load card_json BEFORE deleting anything
                card_json = _load_card_meta(image_path)
                if not card_json:
                    card_json = self.app.scryfall.get_card(card.name)
                if not card_json:
                    self.after(0, self.app.statusbar.set_status,
                               "Re-fetch failed — check internet connection.")
                    return

                # Delete all cache variants
                _delete_card_cache_files(image_path)

                # Re-download native PNG(s)
                paths = self.app.scryfall.download_all_face_images(card_json)
                if not paths:
                    self.after(0, self.app.statusbar.set_status, "Re-download failed.")
                    return

                # Apply watermark with stored offsets (stamp + NFS independent)
                offset     = getattr(card, "watermark_offset",     (0, 0))
                nfs_offset = getattr(card, "watermark_nfs_offset", (0, 0))
                wm_enabled = getattr(self.app, "_watermark_enabled", False)
                if wm_enabled and hasattr(self.app, "_watermark"):
                    for p in paths:
                        if os.path.exists(p):
                            self.app._watermark.apply(p, card_json,
                                                      offset=offset,
                                                      nfs_offset=nfs_offset)

                # Update card paths to freshly downloaded files
                card.image_path = paths[0]
                if len(paths) > 1:
                    card.back_image_path = paths[1]

                self.after(0, self._on_reapply_done, card)

            except Exception as e:
                print(f"[Inspector] reapply_watermark error: {e}")
                self.after(0, self.app.statusbar.set_status, f"Reapply error: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_reapply_done(self, card) -> None:
        if hasattr(self.app, "workspace"):
            self.app.workspace._pil_cache.clear()
        if hasattr(self.app, "statusbar"):
            self.app.statusbar.set_status("Watermark reapplied.")
        # Reload inspector image
        self.show_card(card, show_back=self._show_back)
        # Reload workspace thumbnails
        deck = self.app.deck_manager.active_deck()
        if deck:
            self.app.workspace.load_cards(deck.cards)

    def refresh_stats(self) -> None:
        """À appeler après chaque modification du deck."""
        self._metadata_failed = False  # permet un nouvel essai au changement de deck
        if self._tab == "stats":
            self._build_stats()


# ── Watermark offset dialog ───────────────────────────────────────────────────

class _WatermarkOffsetDialog(ctk.CTkToplevel):
    """Small dialog to adjust the per-card watermark offset (dx, dy in native pixels)."""

    def __init__(self, inspector: "CardInspectorPanel", card, app) -> None:
        super().__init__(app)
        self._inspector = inspector
        self._card = card
        self._app = app

        self.title("Move Watermark")
        self.resizable(False, False)
        self.grab_set()
        self.lift()

        # Position near the inspector panel
        self.update_idletasks()
        px = inspector.winfo_rootx() - 20
        py = inspector.winfo_rooty() + 60
        self.geometry(f"260x230+{px}+{py}")

        ox, oy = getattr(card, "watermark_offset", (0, 0))

        ctk.CTkLabel(
            self, text=f'"{card.name}"',
            font=ctk.CTkFont(size=10), text_color="#a09aaa",
            wraplength=240, justify="left",
        ).pack(padx=16, pady=(14, 6), anchor="w")

        # dx row
        dx_row = ctk.CTkFrame(self, fg_color="transparent")
        dx_row.pack(padx=16, pady=(4, 0), fill="x")
        ctk.CTkLabel(dx_row, text="Horizontal (px):", width=120,
                     font=ctk.CTkFont(size=11), anchor="w").pack(side="left")
        self._dx_var = tk.StringVar(value=str(ox))
        ctk.CTkEntry(dx_row, textvariable=self._dx_var, width=72,
                     font=ctk.CTkFont(size=11)).pack(side="left")

        # dy row
        dy_row = ctk.CTkFrame(self, fg_color="transparent")
        dy_row.pack(padx=16, pady=(8, 0), fill="x")
        ctk.CTkLabel(dy_row, text="Vertical (px):", width=120,
                     font=ctk.CTkFont(size=11), anchor="w").pack(side="left")
        self._dy_var = tk.StringVar(value=str(oy))
        ctk.CTkEntry(dy_row, textvariable=self._dy_var, width=72,
                     font=ctk.CTkFont(size=11)).pack(side="left")

        ctk.CTkLabel(
            self, text="Negative = up/left  ·  Reference: 672px native",
            font=ctk.CTkFont(size=9), text_color="#6a6478",
        ).pack(padx=16, pady=(6, 0), anchor="w")

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=16, pady=(14, 0), fill="x")
        ctk.CTkButton(btn_row, text="Cancel", width=88, height=28,
                      fg_color="#28252e", hover_color="#34303e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Apply", width=88, height=28,
                      fg_color="#c04828", hover_color="#a83820",
                      command=self._apply).pack(side="right", padx=(0, 8))

    def _apply(self) -> None:
        try:
            dx = int(self._dx_var.get())
            dy = int(self._dy_var.get())
        except ValueError:
            return
        self._card.watermark_offset = (dx, dy)
        if hasattr(self._app, "_auto_save"):
            self._app._auto_save()
        self.destroy()
        self._inspector._reapply_watermark(self._card)
