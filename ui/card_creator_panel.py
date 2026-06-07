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

from config import CACHE_DIR

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
    FrameStyle.M15:        "M15 (Modern 2015+)",
    FrameStyle.EXTENDED:   "Extended Art",
    FrameStyle.BORDERLESS: "Borderless",
    FrameStyle.FULLART:    "Full Art",
    FrameStyle.EIGHTH:     "8th Edition (Classic)",
    FrameStyle.OLD:        "Old Border (pre-2003)",
    FrameStyle.TOKEN:      "Token",
}
_FRAME_BY_LABEL = {v: k for k, v in _FRAME_LABELS.items()}

_RARITY_LABELS = {
    Rarity.COMMON:   "Commune",
    Rarity.UNCOMMON: "Inhabituelle",
    Rarity.RARE:     "Rare",
    Rarity.MYTHIC:   "Mythique",
}
_RARITY_BY_LABEL = {v: k for k, v in _RARITY_LABELS.items()}

# Text color presets for typography controls
_TEXT_COLORS = {
    "Noir":  (0, 0, 0),
    "Blanc": (255, 255, 255),
    "Or":    (210, 170, 45),
    "Gris":  (140, 140, 140),
}

# Physical preview dimensions (pixels on screen)
_PREVIEW_W_PX = 190
_PREVIEW_H_PX = 265


# ── Zoom preview popup ────────────────────────────────────────────────────────

class _ZoomPreviewDialog(ctk.CTkToplevel):
    """Read-only zoomed card preview, centered on screen."""

    # Logical display size (CTk units). On high-DPI: PIL renders at _ws× physical pixels.
    _ZOOM_W = 465
    _ZOOM_H = 651

    def __init__(self, parent, img: Image.Image) -> None:
        super().__init__(parent)
        self.title("Apercu carte")
        self.resizable(False, False)
        self._parent_ref = parent

        try:
            from customtkinter import ScalingTracker as _ST
            _ws = _ST.get_widget_scaling(parent)
        except Exception:
            _ws = 1.0

        pad_x, pad_y = 16, 52
        W = self._ZOOM_W + pad_x          # logical window width
        H = self._ZOOM_H + pad_y          # logical window height

        # Set size; positioning is done after idle to use consistent winfo coords
        self.geometry(f"{W}x{H}")

        # PIL at physical pixels → CTkImage at logical units (exact pixel match)
        phys_w = max(1, round(self._ZOOM_W * _ws))
        phys_h = max(1, round(self._ZOOM_H * _ws))
        zoom = img.convert("RGB").resize((phys_w, phys_h), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=zoom, dark_image=zoom,
                               size=(self._ZOOM_W, self._ZOOM_H))
        self._img_ref = ctk_img

        ctk.CTkLabel(self, image=ctk_img, text="",
                     fg_color="#0d0a14").pack(padx=8, pady=(8, 4))
        ctk.CTkButton(self, text="Fermer", width=120, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color="#28252e", hover_color="#3a3548",
                      command=self.destroy).pack(pady=(0, 8))

        self.lift()
        self.grab_set()
        self.bind("<Escape>", lambda _: self.destroy())
        # Center on parent after window is mapped (avoids physical/logical px mismatch)
        self.after(10, self._center_on_parent)

    def _center_on_parent(self) -> None:
        parent = self._parent_ref
        self.update_idletasks()
        dw = self.winfo_width()
        dh = self.winfo_height()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx() + (pw - dw) // 2
        py = parent.winfo_rooty() + (ph - dh) // 2
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = max(0, min(px, sw - dw))
        py = max(0, min(py, sh - dh))
        self.geometry(f"+{px}+{py}")


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
        self._v_upscale    = ctk.BooleanVar(value=False)
        # Typography — colors
        self._v_name_color  = ctk.StringVar(value="Noir")
        self._v_type_color  = ctk.StringVar(value="Noir")
        self._v_text_color  = ctk.StringVar(value="Noir")
        self._v_pt_color    = ctk.StringVar(value="Noir")
        # Typography — sizes
        self._v_name_size   = ctk.StringVar(value="28")
        self._v_type_size   = ctk.StringVar(value="22")
        self._v_oracle_min  = ctk.StringVar(value="9")
        self._v_pt_size     = ctk.StringVar(value="26")
        # Per-section formatting toggles (bold / italic / underline / highlight)
        self._v_name_bold        = ctk.BooleanVar(value=False)
        self._v_name_italic      = ctk.BooleanVar(value=False)
        self._v_name_underline   = ctk.BooleanVar(value=False)
        self._v_name_highlight   = ctk.BooleanVar(value=False)
        self._v_type_bold        = ctk.BooleanVar(value=False)
        self._v_type_italic      = ctk.BooleanVar(value=False)
        self._v_type_underline   = ctk.BooleanVar(value=False)
        self._v_type_highlight   = ctk.BooleanVar(value=False)
        self._v_oracle_bold      = ctk.BooleanVar(value=False)
        self._v_oracle_italic    = ctk.BooleanVar(value=False)
        self._v_oracle_underline = ctk.BooleanVar(value=False)
        self._v_oracle_highlight = ctk.BooleanVar(value=False)
        self._v_pt_bold          = ctk.BooleanVar(value=False)
        self._v_pt_italic        = ctk.BooleanVar(value=False)
        self._v_pt_underline     = ctk.BooleanVar(value=False)
        self._v_pt_highlight     = ctk.BooleanVar(value=False)

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

        W, H = 920, 700
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
        """Top bar: preview image (left) + status + action buttons (right)."""
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
                     wraplength=260, anchor="w").pack(fill="x", pady=(2, 6))

        btn_w = 220

        # Primary action: Add to deck
        deck_row = ctk.CTkFrame(rhs, fg_color="transparent")
        deck_row.pack(anchor="w", pady=(0, 4))
        ctk.CTkButton(deck_row, text="Ajouter au deck", width=btn_w, height=34,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color="#c04828", hover_color="#a83820",
                      command=self._add_to_deck).pack(side="left")
        upscale_available = getattr(self._app, "upscaler", None) and self._app.upscaler.is_available()
        ctk.CTkCheckBox(deck_row, text="Upscale", variable=self._v_upscale,
                        state="normal" if upscale_available else "disabled",
                        width=80, font=ctk.CTkFont(size=10),
                        text_color="#a09aaa" if not upscale_available else "#f0ece4",
                        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(rhs, text="Zoom apercu", width=btn_w, height=30,
                      font=ctk.CTkFont(size=11),
                      fg_color="#28252e", hover_color="#3a3548",
                      command=self._show_zoom_preview).pack(anchor="w", pady=(0, 4))
        ctk.CTkButton(rhs, text="Exporter PNG 300 DPI", width=btn_w, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color="#28252e", hover_color="#3a3548",
                      command=lambda: self._export(300)).pack(anchor="w", pady=(0, 4))
        ctk.CTkButton(rhs, text="Exporter PNG 900 DPI", width=btn_w, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color="#28252e", hover_color="#3a3548",
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

        # ── 9. Typography ─────────────────────────────────────────────────────
        _sep()
        _lbl("Typographie", size=11, color="#f0ece4")

        color_values = list(_TEXT_COLORS.keys())
        typo_grid = ctk.CTkFrame(f, fg_color="transparent")
        typo_grid.pack(fill="x", padx=12)
        # cols: label | color menu | size label | size entry | unit label
        typo_grid.grid_columnconfigure(1, weight=1)

        _FMT_OPTS = [("Gras", 0), ("Ital.", 1), ("Souligne", 2), ("Surligné", 3)]

        def _row(parent, row_i, lbl_txt, v_color, v_size,
                 size_hint="pt", sep_before=False, fmt_vars=None):
            if sep_before:
                ctk.CTkFrame(parent, height=1, fg_color="#2a2535").grid(
                    row=row_i, column=0, columnspan=5, sticky="ew",
                    padx=0, pady=(6, 4))
                row_i += 1

            ctk.CTkLabel(parent, text=lbl_txt, anchor="w",
                         font=ctk.CTkFont(size=10), text_color="#a09aaa",
                         width=80).grid(row=row_i, column=0, sticky="w", pady=(2, 0))
            ctk.CTkOptionMenu(parent, variable=v_color, values=color_values,
                               font=ctk.CTkFont(size=10), height=26, width=96,
                               fg_color="#28252e", button_color="#3a3548",
                               ).grid(row=row_i, column=1, sticky="w",
                                      padx=(4, 8), pady=(2, 0))
            v_color.trace_add("write", self._on_form_change)

            ctk.CTkLabel(parent, text="Taille:", anchor="e",
                         font=ctk.CTkFont(size=10), text_color="#a09aaa",
                         width=44).grid(row=row_i, column=2, sticky="e", pady=(2, 0))
            ctk.CTkEntry(parent, textvariable=v_size,
                         width=46, font=ctk.CTkFont(size=11),
                         ).grid(row=row_i, column=3, sticky="w",
                                padx=(4, 2), pady=(2, 0))
            ctk.CTkLabel(parent, text=size_hint, anchor="w",
                         font=ctk.CTkFont(size=9), text_color="#6a6478",
                         width=24).grid(row=row_i, column=4, sticky="w", pady=(2, 0))
            v_size.trace_add("write", self._on_form_change)
            row_i += 1

            if fmt_vars:
                _fmt = ctk.CTkFrame(parent, fg_color="transparent")
                _fmt.grid(row=row_i, column=1, columnspan=4, sticky="w", pady=(0, 4))
                for _fl, _fv in zip([l for l, _ in _FMT_OPTS], fmt_vars):
                    ctk.CTkCheckBox(_fmt, text=_fl, variable=_fv,
                                     font=ctk.CTkFont(size=10),
                                     checkbox_width=14, checkbox_height=14, width=70,
                                     ).pack(side="left", padx=(0, 2))
                    _fv.trace_add("write", self._on_form_change)
                row_i += 1

            return row_i

        _nf = [self._v_name_bold,   self._v_name_italic,
               self._v_name_underline, self._v_name_highlight]
        _tf = [self._v_type_bold,   self._v_type_italic,
               self._v_type_underline, self._v_type_highlight]
        _of = [self._v_oracle_bold, self._v_oracle_italic,
               self._v_oracle_underline, self._v_oracle_highlight]
        _pf = [self._v_pt_bold,     self._v_pt_italic,
               self._v_pt_underline, self._v_pt_highlight]

        r = 0
        r = _row(typo_grid, r, "Nom:",         self._v_name_color,  self._v_name_size, fmt_vars=_nf)
        r = _row(typo_grid, r, "Type:",        self._v_type_color,  self._v_type_size, fmt_vars=_tf)
        r = _row(typo_grid, r, "Texte oracle:", self._v_text_color, self._v_oracle_min, fmt_vars=_of)
        r = _row(typo_grid, r, "Force/End:",   self._v_pt_color,    self._v_pt_size,
                 sep_before=True, fmt_vars=_pf)

        # ── 10. Numéro de carte ────────────────────────────────────────────────
        _sep()
        num_row = ctk.CTkFrame(f, fg_color="transparent")
        num_row.pack(fill="x", padx=12, pady=(0, 4))

        self._v_show_number = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            num_row, text="N° carte :", variable=self._v_show_number,
            font=ctk.CTkFont(size=11), text_color="#a09aaa",
            command=self._on_show_number_toggle,
            checkbox_width=16, checkbox_height=16,
        ).pack(side="left")

        self._v_number = ctk.StringVar(value="001")
        self._e_number = ctk.CTkEntry(
            num_row, textvariable=self._v_number, width=60,
            font=ctk.CTkFont(size=11), state="disabled",
        )
        self._e_number.pack(side="left", padx=(8, 0))
        self._v_number.trace_add("write", self._on_form_change)

        # Bottom padding
        ctk.CTkFrame(f, height=16, fg_color="transparent").pack()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_form_change(self, *_) -> None:
        self._schedule_preview()

    def _on_show_number_toggle(self) -> None:
        state = "normal" if self._v_show_number.get() else "disabled"
        self._e_number.configure(state=state)
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

    # ── Preview (thumbnail) ───────────────────────────────────────────────────

    def _schedule_preview(self, *_) -> None:
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(500, self._update_preview)

    def _update_preview(self) -> None:
        self._preview_job = None
        if self._preview_busy:
            return
        self._preview_busy = True
        try:
            card = self._build_card_data()
        except Exception as e:
            self._preview_busy = False
            self._status_var.set(f"Erreur params: {str(e)[:60]}")
            return
        threading.Thread(target=self._render_worker, args=(card, False), daemon=True).start()

    def _render_worker(self, card: CardData, for_zoom: bool) -> None:
        try:
            img = self._engine.render_card(card)
            if for_zoom:
                self.after(0, self._open_zoom_preview, img)
            else:
                thumb = img.convert("RGB").resize((_PREVIEW_W_PX, _PREVIEW_H_PX), Image.LANCZOS)
                self.after(0, self._set_preview, thumb)
        except Exception as e:
            self.after(0, self._set_preview_error, str(e))

    def _set_preview(self, img: Image.Image) -> None:
        self._preview_busy = False
        try:
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                   size=(self._pw, self._ph))
            self._preview_tk = ctk_img
            self._preview_label.configure(image=ctk_img, text="")
            self._status_var.set("")
        except Exception as e:
            self._status_var.set(f"Erreur affichage: {e}")

    def _set_preview_error(self, msg: str) -> None:
        self._preview_busy = False
        self._preview_label.configure(image=None, text="Erreur rendu")
        self._status_var.set(msg[:80])

    # ── Zoom preview popup ────────────────────────────────────────────────────

    def _show_zoom_preview(self) -> None:
        if self._preview_busy:
            return
        self._preview_busy = True
        self._status_var.set("Rendu zoom...")
        try:
            card = self._build_card_data()
        except Exception as e:
            self._preview_busy = False
            self._status_var.set(f"Erreur params: {str(e)[:60]}")
            return
        threading.Thread(target=self._render_worker, args=(card, True), daemon=True).start()

    def _open_zoom_preview(self, img: Image.Image) -> None:
        self._preview_busy = False
        self._status_var.set("")
        _ZoomPreviewDialog(self, img)

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

        # Typography — colors
        name_color = _TEXT_COLORS.get(self._v_name_color.get(), (0, 0, 0))
        type_color = _TEXT_COLORS.get(self._v_type_color.get(), (0, 0, 0))
        text_color = _TEXT_COLORS.get(self._v_text_color.get(), (0, 0, 0))
        pt_color   = _TEXT_COLORS.get(self._v_pt_color.get(),   (0, 0, 0))

        def _sz(var, default, lo=6, hi=60):
            try:
                return max(lo, min(hi, int(var.get())))
            except ValueError:
                return default

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
            collector_number = self._v_number.get().strip() or "001",
            show_number      = self._v_show_number.get(),
            name_color       = name_color,
            type_color       = type_color,
            text_color       = text_color,
            pt_color         = pt_color,
            name_size        = _sz(self._v_name_size,   28, lo=8, hi=48),
            type_size        = _sz(self._v_type_size,   22, lo=8, hi=40),
            min_oracle_size  = _sz(self._v_oracle_min,   9, lo=6, hi=32),
            pt_size          = _sz(self._v_pt_size,     26, lo=8, hi=48),
            oracle_bold      = self._v_oracle_bold.get(),
            oracle_italic    = self._v_oracle_italic.get(),
            oracle_underline = self._v_oracle_underline.get(),
            oracle_highlight = self._v_oracle_highlight.get(),
            name_bold        = self._v_name_bold.get(),
            name_italic      = self._v_name_italic.get(),
            name_underline   = self._v_name_underline.get(),
            name_highlight   = self._v_name_highlight.get(),
            type_bold        = self._v_type_bold.get(),
            type_italic      = self._v_type_italic.get(),
            type_underline   = self._v_type_underline.get(),
            type_highlight   = self._v_type_highlight.get(),
            pt_bold          = self._v_pt_bold.get(),
            pt_italic        = self._v_pt_italic.get(),
            pt_underline     = self._v_pt_underline.get(),
            pt_highlight     = self._v_pt_highlight.get(),
        )

    # ── Add to deck ───────────────────────────────────────────────────────────

    def _add_to_deck(self) -> None:
        card   = self._build_card_data()
        upscale = self._v_upscale.get() and getattr(self._app, "upscaler", None) and self._app.upscaler.is_available()
        self._status_var.set("Ajout au deck en cours...")
        threading.Thread(
            target=self._add_to_deck_worker, args=(card, bool(upscale)), daemon=True
        ).start()

    def _add_to_deck_worker(self, card: CardData, upscale: bool) -> None:
        try:
            custom_cache = os.path.join(CACHE_DIR, "custom")
            os.makedirs(custom_cache, exist_ok=True)

            safe = card.name
            for ch in r'\/:*?"<>|':
                safe = safe.replace(ch, "-")
            safe = safe.strip().replace(" ", "_")[:40]
            path = os.path.join(custom_cache, f"{safe}_creator.png")

            self._engine.export_card(card, path, dpi=300)

            if upscale:
                upscaled = os.path.join(custom_cache, f"{safe}_creator_1200dpi.png")
                try:
                    path = self._app.upscaler.upscale_to_1200dpi(path, upscaled)
                except Exception as e:
                    print(f"[CardCreator] Upscale failed: {e}")

            if self._app._watermark_enabled:
                self._app._watermark.apply(path)

            final = os.path.normpath(path)
            name  = card.name
            self._app.after(0, self._app._add_custom_card, name, final)
            self.after(0, self._status_var.set, f"Ajoute au deck : {name}")
        except Exception as e:
            self.after(0, self._status_var.set, f"Erreur: {e}")

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
