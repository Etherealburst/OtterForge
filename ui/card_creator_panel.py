"""
ui/card_creator_panel.py — CardCreatorPanel
Dialog two-column: scrollable form (left) + live preview + export (right).
Opened from toolbar "+Forge" or app.open_card_creator().
"""

import os
import threading
import datetime
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

from engine.card_creator_engine import (
    CardCreatorEngine, CardData,
    CardColor, CardType, FrameStyle, Rarity,
)

# ── Labels for UI display ─────────────────────────────────────────────────────

_COLOR_LABELS = {
    "W": "W — Blanc",
    "U": "U — Bleu",
    "B": "B — Noir",
    "R": "R — Rouge",
    "G": "G — Vert",
    "M": "M — Multicolore",
    "C": "C — Incolore",
    "A": "A — Artefact",
    "L": "L — Terrain",
}
_COLOR_CODES   = {v: k for k, v in _COLOR_LABELS.items()}

_TYPE_LABELS   = [ct.value for ct in CardType]

_FRAME_LABELS  = {
    FrameStyle.M15:    "M15 (Modern 2015+)",
    FrameStyle.EIGHTH: "8th Edition (Classic)",
    FrameStyle.OLD:    "Old Border (pre-2003)",
    FrameStyle.TOKEN:  "Token",
}
_FRAME_BY_LABEL = {v: k for k, v in _FRAME_LABELS.items()}

_RARITY_LABELS = {
    Rarity.COMMON:   "Commune",
    Rarity.UNCOMMON: "Inhabituelle",
    Rarity.RARE:     "Rare",
    Rarity.MYTHIC:   "Mythique",
}
_RARITY_BY_LABEL = {v: k for k, v in _RARITY_LABELS.items()}

# Physical preview dimensions (pixels on screen)
_PREVIEW_W_PX = 190
_PREVIEW_H_PX = 265


# ── Panel ─────────────────────────────────────────────────────────────────────

class CardCreatorPanel(ctk.CTkToplevel):
    """Full-featured card creator: form on the left, live preview on the right."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._app          = app
        self._engine       = CardCreatorEngine()
        self._preview_job  = None
        self._preview_busy = False
        self._preview_tk   = None
        self._art_path     = ""

        # Compute CTk-unit sizes from physical target (accounts for widget_scaling)
        try:
            from customtkinter import ScalingTracker as _ST2
            _ws = _ST2.get_widget_scaling(app)
        except Exception:
            _ws = 1.0
        self._pw = max(1, round(_PREVIEW_W_PX / _ws))   # CTk units for preview width
        self._ph = max(1, round(_PREVIEW_H_PX / _ws))   # CTk units for preview height

        self.title("Card Creator — OtterForge")
        self.resizable(True, True)
        self.grab_set()
        self.lift()

        W, H = 920, 900
        self.update_idletasks()
        try:
            from customtkinter import ScalingTracker as _ST
            _sc = _ST.get_window_scaling(app)
        except Exception:
            _sc = 1.0
        px = app.winfo_rootx() + (app.winfo_width()  - round(W * _sc)) // 2
        py = app.winfo_rooty() + (app.winfo_height() - round(H * _sc)) // 2
        self.geometry(f"{W}x{H}+{px}+{py}")

        self._build_ui()
        self._schedule_preview()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Top bar: preview + export buttons (fixed, no scroll) ─────────────
        self._top = ctk.CTkFrame(self, fg_color="#16131d", corner_radius=0)
        self._top.pack(side="top", fill="x", padx=0, pady=0)
        self._build_top_bar()

        # ── Scrollable form below ─────────────────────────────────────────────
        self._form_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._form_frame.pack(side="top", fill="both", expand=True, padx=8, pady=(4, 8))

        # Fix scroll wheel on Windows
        def _focus_scroll(e=None):
            for attr in ("_parent_canvas", "_canvas"):
                w = getattr(self._form_frame, attr, None)
                if w:
                    w.focus_set()
                    break
        self._form_frame.bind("<Enter>", _focus_scroll, add="+")

        self._build_form()

    def _build_top_bar(self) -> None:
        """Top bar: preview image (left) + status + export buttons (right)."""
        PAD = 10
        # Preview image
        self._preview_label = ctk.CTkLabel(
            self._top, text="Rendu...",
            width=self._pw, height=self._ph,
            fg_color="#0d0a14", corner_radius=4,
            font=ctk.CTkFont(size=10), text_color="#6a6478",
        )
        self._preview_label.pack(side="left", padx=(PAD, 4), pady=PAD)

        # Right side: label + status + buttons
        rhs = ctk.CTkFrame(self._top, fg_color="transparent")
        rhs.pack(side="left", fill="both", expand=True, padx=(4, PAD), pady=PAD)

        ctk.CTkLabel(rhs, text="Apercu carte", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#f0ece4", anchor="w").pack(fill="x")

        self._status_var = ctk.StringVar(value="")
        ctk.CTkLabel(rhs, textvariable=self._status_var,
                     font=ctk.CTkFont(size=9), text_color="#a09aaa",
                     wraplength=260, anchor="w").pack(fill="x", pady=(2, 8))

        btn_w = 220
        ctk.CTkButton(rhs, text="Previsualiser", width=btn_w, height=30,
                      font=ctk.CTkFont(size=11),
                      fg_color="#28252e", hover_color="#3a3548",
                      command=self._update_preview).pack(anchor="w", pady=(0, 4))
        ctk.CTkButton(rhs, text="Exporter PNG 300 DPI", width=btn_w, height=30,
                      font=ctk.CTkFont(size=11),
                      fg_color="#c04828", hover_color="#a83820",
                      command=lambda: self._export(300)).pack(anchor="w", pady=(0, 4))
        ctk.CTkButton(rhs, text="Exporter PNG 900 DPI", width=btn_w, height=30,
                      font=ctk.CTkFont(size=11),
                      fg_color="#8a3018", hover_color="#7a2810",
                      command=lambda: self._export(900)).pack(anchor="w")

    # ── Form ──────────────────────────────────────────────────────────────────

    def _build_form(self) -> None:
        f   = self._form_frame
        PAD = (12, 4)

        def _sep():
            ctk.CTkFrame(f, height=1, fg_color="#2a2535").pack(
                fill="x", padx=12, pady=(10, 6)
            )

        def _lbl(text, size=10, color="#a09aaa"):
            ctk.CTkLabel(
                f, text=text, font=ctk.CTkFont(size=size),
                text_color=color, anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 2))

        def _entry(var: ctk.StringVar, placeholder="", width=None):
            e = ctk.CTkEntry(
                f, textvariable=var, placeholder_text=placeholder,
                font=ctk.CTkFont(size=11),
                **({"width": width} if width else {}),
            )
            e.pack(fill="x" if not width else None,
                   padx=12, anchor="w")
            var.trace_add("write", self._on_form_change)
            return e

        def _optmenu(var: ctk.StringVar, values: list, width=None):
            m = ctk.CTkOptionMenu(
                f, variable=var, values=values,
                font=ctk.CTkFont(size=11), height=30,
                fg_color="#28252e", button_color="#3a3548",
                **({"width": width} if width else {}),
            )
            m.pack(fill="x" if not width else None,
                   padx=12, anchor="w")
            var.trace_add("write", self._on_form_change)
            return m

        # ── 1. Identity ───────────────────────────────────────────────────────
        _lbl("Nom de la carte *", size=11, color="#f0ece4")
        self._v_name = ctk.StringVar(value="Card Name")
        _entry(self._v_name)

        _lbl("Cout en mana  (ex: {2}{W}{U})")
        self._v_mana = ctk.StringVar()
        _entry(self._v_mana, placeholder="{2}{W}{W}")

        # ── 2. Type ───────────────────────────────────────────────────────────
        _sep()
        _lbl("Type de carte", size=11, color="#f0ece4")

        row_type = ctk.CTkFrame(f, fg_color="transparent")
        row_type.pack(fill="x", padx=12, pady=(0, 0))

        self._v_type = ctk.StringVar(value=CardType.CREATURE.value)
        ctk.CTkOptionMenu(
            row_type, variable=self._v_type, values=_TYPE_LABELS,
            font=ctk.CTkFont(size=11), height=30, width=170,
            fg_color="#28252e", button_color="#3a3548",
        ).pack(side="left", padx=(0, 6))
        self._v_type.trace_add("write", self._on_type_change)

        ctk.CTkLabel(row_type, text="Supertype:",
                     font=ctk.CTkFont(size=10), text_color="#a09aaa",
                     width=70, anchor="e").pack(side="left")
        self._v_supertype = ctk.StringVar()
        e_super = ctk.CTkEntry(row_type, textvariable=self._v_supertype,
                               placeholder_text="Legendary",
                               font=ctk.CTkFont(size=11), width=140)
        e_super.pack(side="left")
        self._v_supertype.trace_add("write", self._on_form_change)

        _lbl("Sous-type")
        self._v_subtype = ctk.StringVar()
        _entry(self._v_subtype, placeholder="Human Wizard")

        # ── 3. Color ──────────────────────────────────────────────────────────
        _sep()
        _lbl("Couleur du frame", size=11, color="#f0ece4")
        self._v_color = ctk.StringVar(value=_COLOR_LABELS["W"])
        ctk.CTkOptionMenu(
            f, variable=self._v_color,
            values=list(_COLOR_LABELS.values()),
            font=ctk.CTkFont(size=11), height=30,
            fg_color="#28252e", button_color="#3a3548",
        ).pack(fill="x", padx=12)
        self._v_color.trace_add("write", self._on_form_change)

        # ── 4. Frame style ────────────────────────────────────────────────────
        _lbl("Style de frame")
        self._v_frame = ctk.StringVar(value=_FRAME_LABELS[FrameStyle.M15])
        ctk.CTkOptionMenu(
            f, variable=self._v_frame,
            values=list(_FRAME_LABELS.values()),
            font=ctk.CTkFont(size=11), height=30,
            fg_color="#28252e", button_color="#3a3548",
        ).pack(fill="x", padx=12)
        self._v_frame.trace_add("write", self._on_form_change)

        # ── 5. Rarity ─────────────────────────────────────────────────────────
        _lbl("Rarete")
        self._v_rarity = ctk.StringVar(value=_RARITY_LABELS[Rarity.COMMON])
        ctk.CTkOptionMenu(
            f, variable=self._v_rarity,
            values=list(_RARITY_LABELS.values()),
            font=ctk.CTkFont(size=11), height=30,
            fg_color="#28252e", button_color="#3a3548",
        ).pack(fill="x", padx=12)
        self._v_rarity.trace_add("write", self._on_form_change)

        # ── 6. Oracle + Flavor ────────────────────────────────────────────────
        _sep()
        _lbl("Texte oracle", size=11, color="#f0ece4")
        self._oracle_box = ctk.CTkTextbox(
            f, height=100, font=ctk.CTkFont(size=11),
            fg_color="#1c1a20", border_color="#34303e", border_width=1,
        )
        self._oracle_box.pack(fill="x", padx=12, pady=(0, 0))
        self._oracle_box.bind("<KeyRelease>", self._on_form_change)

        _lbl("Texte flavor")
        self._flavor_box = ctk.CTkTextbox(
            f, height=70, font=ctk.CTkFont(size=11),
            fg_color="#1c1a20", border_color="#34303e", border_width=1,
        )
        self._flavor_box.pack(fill="x", padx=12)
        self._flavor_box.bind("<KeyRelease>", self._on_form_change)

        # ── 7. Stats (creature / planeswalker) ────────────────────────────────
        _sep()
        self._stats_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._stats_frame.pack(fill="x", padx=12)

        # Creature row
        self._creature_row = ctk.CTkFrame(self._stats_frame, fg_color="transparent")
        self._creature_row.pack(fill="x")
        ctk.CTkLabel(self._creature_row, text="Force / Endurance:",
                     font=ctk.CTkFont(size=10), text_color="#a09aaa",
                     width=140, anchor="w").pack(side="left")
        self._v_power = ctk.StringVar()
        ctk.CTkEntry(self._creature_row, textvariable=self._v_power,
                     placeholder_text="4", width=60,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(self._creature_row, text="/",
                     font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 4))
        self._v_toughness = ctk.StringVar()
        ctk.CTkEntry(self._creature_row, textvariable=self._v_toughness,
                     placeholder_text="4", width=60,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._v_power.trace_add("write", self._on_form_change)
        self._v_toughness.trace_add("write", self._on_form_change)

        # Planeswalker row
        self._pw_row = ctk.CTkFrame(self._stats_frame, fg_color="transparent")
        ctk.CTkLabel(self._pw_row, text="Loyaute initiale:",
                     font=ctk.CTkFont(size=10), text_color="#a09aaa",
                     width=140, anchor="w").pack(side="left")
        self._v_loyalty = ctk.StringVar()
        ctk.CTkEntry(self._pw_row, textvariable=self._v_loyalty,
                     placeholder_text="4", width=80,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._v_loyalty.trace_add("write", self._on_form_change)

        self._refresh_stats_visibility()

        # ── 8. Artwork ────────────────────────────────────────────────────────
        _sep()
        _lbl("Artwork", size=11, color="#f0ece4")
        art_row = ctk.CTkFrame(f, fg_color="transparent")
        art_row.pack(fill="x", padx=12)
        self._art_var = ctk.StringVar(value="Aucune image selectionnee")
        ctk.CTkEntry(art_row, textvariable=self._art_var,
                     state="disabled", width=300,
                     font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkButton(art_row, text="Browse...", width=88, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color="#28252e", hover_color="#3a3548",
                      command=self._browse_art).pack(side="left", padx=(6, 0))

        # ── 9. Metadata ───────────────────────────────────────────────────────
        _sep()
        _lbl("Metadonnees", size=11, color="#f0ece4")

        meta_grid = ctk.CTkFrame(f, fg_color="transparent")
        meta_grid.pack(fill="x", padx=12)
        meta_grid.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(meta_grid, text="Artiste:", anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#a09aaa",
                     width=50).grid(row=0, column=0, sticky="w")
        self._v_artist = ctk.StringVar(value="Unknown Artist")
        ctk.CTkEntry(meta_grid, textvariable=self._v_artist,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="ew", padx=(4, 12))
        self._v_artist.trace_add("write", self._on_form_change)

        ctk.CTkLabel(meta_grid, text="Set:", anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#a09aaa",
                     width=30).grid(row=0, column=2, sticky="w")
        self._v_set = ctk.StringVar(value="OTF")
        ctk.CTkEntry(meta_grid, textvariable=self._v_set, width=60,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=3, sticky="w")
        self._v_set.trace_add("write", self._on_form_change)

        ctk.CTkLabel(meta_grid, text="No:", anchor="w",
                     font=ctk.CTkFont(size=10), text_color="#a09aaa",
                     width=30).grid(row=1, column=2, sticky="w", pady=(4, 0))
        self._v_number = ctk.StringVar(value="001")
        ctk.CTkEntry(meta_grid, textvariable=self._v_number, width=60,
                     font=ctk.CTkFont(size=11)).grid(row=1, column=3, sticky="w", pady=(4, 0))
        self._v_number.trace_add("write", self._on_form_change)

        # Bottom padding
        ctk.CTkFrame(f, height=16, fg_color="transparent").pack()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_form_change(self, *_) -> None:
        self._schedule_preview()

    def _on_type_change(self, *_) -> None:
        self._refresh_stats_visibility()
        self._schedule_preview()

    def _refresh_stats_visibility(self) -> None:
        typ = self._v_type.get()
        if typ == CardType.CREATURE.value:
            self._creature_row.pack(fill="x")
            self._pw_row.pack_forget()
        elif typ == CardType.PLANESWALKER.value:
            self._creature_row.pack_forget()
            self._pw_row.pack(fill="x")
        else:
            self._creature_row.pack_forget()
            self._pw_row.pack_forget()

    def _browse_art(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choisir un artwork",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("Tous", "*.*")],
        )
        if path:
            self._art_path = path
            fname = os.path.basename(path)
            self._art_var.set(fname if len(fname) <= 42 else "..." + fname[-40:])
            self._schedule_preview()

    # ── Preview ───────────────────────────────────────────────────────────────

    def _schedule_preview(self, *_) -> None:
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(500, self._update_preview)

    def _update_preview(self) -> None:
        self._preview_job = None
        if self._preview_busy:
            return
        self._preview_busy = True
        self._status_var.set("Rendu en cours...")
        card = self._build_card_data()
        threading.Thread(target=self._render_worker, args=(card,), daemon=True).start()

    def _render_worker(self, card: CardData) -> None:
        try:
            img = self._engine.render_card(card)
            img = img.convert("RGB").resize((_PREVIEW_W_PX, _PREVIEW_H_PX), Image.LANCZOS)
            self.after(0, self._set_preview, img)
        except Exception as e:
            self.after(0, self._set_preview_error, str(e))

    def _set_preview(self, img: Image.Image) -> None:
        self._preview_busy = False
        try:
            # CTkImage size in CTk units (self._pw/ph) → renders at physical _PX dimensions
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                   size=(self._pw, self._ph))
            self._preview_tk = ctk_img          # prevent GC
            self._preview_label.configure(image=ctk_img, text="")
            self._status_var.set("")
        except Exception as e:
            self._status_var.set(f"Erreur affichage: {e}")

    def _set_preview_error(self, msg: str) -> None:
        self._preview_busy = False
        self._preview_label.configure(image=None, text="Erreur rendu")
        self._status_var.set(msg[:80])

    # ── Card data builder ─────────────────────────────────────────────────────

    def _build_card_data(self) -> CardData:
        typ_str = self._v_type.get()
        try:
            card_type = CardType(typ_str)
        except ValueError:
            card_type = CardType.CREATURE

        color_label = self._v_color.get()
        color_code  = _COLOR_CODES.get(color_label, "W")
        try:
            color = CardColor(color_code)
        except ValueError:
            color = CardColor.WHITE

        frame_label = self._v_frame.get()
        frame       = _FRAME_BY_LABEL.get(frame_label, FrameStyle.M15)

        rarity_label = self._v_rarity.get()
        rarity       = _RARITY_BY_LABEL.get(rarity_label, Rarity.COMMON)

        oracle = self._oracle_box.get("1.0", "end").strip()
        flavor = self._flavor_box.get("1.0", "end").strip()

        power     = self._v_power.get().strip()     if card_type == CardType.CREATURE     else ""
        toughness = self._v_toughness.get().strip() if card_type == CardType.CREATURE     else ""
        loyalty   = self._v_loyalty.get().strip()   if card_type == CardType.PLANESWALKER else ""

        return CardData(
            name             = self._v_name.get().strip() or "Card Name",
            mana_cost        = self._v_mana.get().strip(),
            card_type        = card_type,
            supertype        = self._v_supertype.get().strip(),
            subtype          = self._v_subtype.get().strip(),
            color            = color,
            frame_style      = frame,
            rarity           = rarity,
            oracle_text      = oracle,
            flavor_text      = flavor,
            power            = power,
            toughness        = toughness,
            loyalty          = loyalty,
            art_path         = self._art_path or None,
            artist           = self._v_artist.get().strip() or "Unknown Artist",
            set_code         = self._v_set.get().strip().upper() or "OTF",
            collector_number = self._v_number.get().strip() or "001",
        )

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self, dpi: int) -> None:
        card    = self._build_card_data()
        safe    = card.name.replace(" ", "_")
        for ch in r'\/:*?"<>|':
            safe = safe.replace(ch, "-")
        safe    = safe[:40]
        ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default = f"{safe}_{dpi}dpi_{ts}.png"

        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "output", "custom_cards",
        )
        os.makedirs(out_dir, exist_ok=True)

        path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Exporter PNG {dpi} DPI",
            initialdir=out_dir,
            initialfile=default,
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
        )
        if not path:
            return

        self._status_var.set(f"Export {dpi} DPI en cours...")
        threading.Thread(
            target=self._export_worker, args=(card, path, dpi), daemon=True
        ).start()

    def _export_worker(self, card: CardData, path: str, dpi: int) -> None:
        try:
            self._engine.export_card(card, path, dpi)
            self.after(0, self._status_var.set,
                       f"Exporte : {os.path.basename(path)}")
        except Exception as e:
            self.after(0, self._status_var.set, f"Erreur export: {e}")
