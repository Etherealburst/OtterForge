"""
ui/toolbar.py
-------------
Barre d'outils principale — compacte avec logo, groupes d'actions et tooltips.
"""

import os
import sys
import tkinter as tk
import customtkinter as ctk
from PIL import Image


def _asset_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    return os.path.join(base, name)


class Toolbar(ctk.CTkFrame):

    HEIGHT = 64

    def __init__(self, master):
        super().__init__(master, height=self.HEIGHT, corner_radius=0, fg_color="#1c1a20")
        self.master = master
        self.pack_propagate(False)
        self._build()

    def _build(self):
        # ── Branding ──────────────────────────────────────────────────────
        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(side="left", fill="y", padx=(12, 4))

        logo_path = _asset_path("assets/OtterForge_Image.jpg")
        try:
            raw = Image.open(logo_path)
            w, h = raw.size
            m = int(min(w, h) * 0.03)
            pil_img = raw.crop((m, m, w - m, h - m)).resize((56, 56), Image.LANCZOS)
            ctk_logo = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(56, 56))
            ctk.CTkLabel(brand, image=ctk_logo, text="").pack(side="left", padx=(0, 10), pady=4)
        except Exception:
            pass

        name_frame = ctk.CTkFrame(brand, fg_color="transparent")
        name_frame.pack(side="left")
        ctk.CTkLabel(
            name_frame, text="OTTER",
            font=ctk.CTkFont(family="Georgia", size=15, weight="bold"),
            text_color="#f0ece4",
        ).pack(side="left")
        ctk.CTkLabel(
            name_frame, text="FORGE",
            font=ctk.CTkFont(family="Georgia", size=15, weight="bold"),
            text_color="#c04828",
        ).pack(side="left")

        # ── Séparateur ────────────────────────────────────────────────────
        _vsep(self)

        # ── Groupe DECK ───────────────────────────────────────────────────
        deck_grp = ctk.CTkFrame(self, fg_color="transparent")
        deck_grp.pack(side="left", fill="y", padx=4)

        _micro_label(deck_grp, "DECK")

        row = ctk.CTkFrame(deck_grp, fg_color="transparent")
        row.pack(pady=(0, 6))

        _tool_btn(row, "Load",      self.master.load_deck_file,          "Load a deck JSON file")
        _tool_btn(row, "Save",      self.master.save_deck,               "Save the active deck")
        _tool_btn(row, "Import",    self.master.import_txt_deck,         "Import a TXT / Moxfield file")
        _tool_btn(row, "TXT",       self.master.export_txt_deck,         "Export deck as text file")
        _tool_btn(row, "+ Custom",  self.master.add_custom_image_dialog, "Add a local PNG image as a custom card")

        # ── Séparateur ────────────────────────────────────────────────────
        _vsep(self)

        # ── Groupe OUTPUT ─────────────────────────────────────────────────
        out_grp = ctk.CTkFrame(self, fg_color="transparent")
        out_grp.pack(side="left", fill="y", padx=4)

        _micro_label(out_grp, "OUTPUT")

        row2 = ctk.CTkFrame(out_grp, fg_color="transparent")
        row2.pack(pady=(0, 6))

        _tool_btn(row2, "Export",      self.master.export_print_sheets,    "Generate MPC print sheets (3×3 grid)")
        _tool_btn(row2, "Print",       self.master.open_home_print_dialog, "Print at home (PDF/PNG)")
        _tool_btn(row2, "Card Back",   self.master.choose_card_back,       "Choose deck card back image")
        _tool_btn(row2, "MPC",         self.master.upload_to_mpc,          "Upload to MakePlayingCards.com")
        _tool_btn(row2, "Upscale",     self.master.upscale_cache_batch,    "Upscale cache with Real-ESRGAN (×4)")
        _tool_btn(row2, "Clear Cache", self.master.purge_cache,            "Clear Scryfall image cache")

        # ── Séparateur ────────────────────────────────────────────
        _vsep(self)

        # ── Groupe CONFIG ─────────────────────────────────────────
        cfg_grp = ctk.CTkFrame(self, fg_color="transparent")
        cfg_grp.pack(side="left", fill="y", padx=(4, 8))

        _micro_label(cfg_grp, "CONFIG")

        row3 = ctk.CTkFrame(cfg_grp, fg_color="transparent")
        row3.pack(pady=(0, 6))

        _tool_btn(row3, "Settings", self.master.open_settings,  "Open settings")
        _tool_btn(row3, "Sidebar",  self.master.toggle_sidebar, "Toggle sidebar (normal / compact / hidden)")
        _tool_btn(row3, "?",        _open_user_guide,           "User guide")


# ── User Guide ───────────────────────────────────────────────────────────────

_GUIDE_TEXT = """\
OTTERFORGE — USER GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LAYOUT
  • Search bar (top)    — find and add cards
  • Workspace (center)  — visual card grid
  • Sidebar (left)      — deck list with counts
  • Inspector (right)   — card preview & deck stats

─────────────────────────────────────────────────
ADDING CARDS
  • By name        "Lightning Bolt"
  • By set + #     "s:m11 cn:149"
  • Moxfield fmt   "1 Lightning Bolt (M11) 149"
  • DFC            "Delver of Secrets // Insectile Aberration"
  • Custom image   drag & drop PNG/JPG onto workspace
                   or toolbar → + Custom

─────────────────────────────────────────────────
MANAGING DECKS
  • +  (deck bar)       create a new deck
  • Right-click a tab   rename / duplicate / delete
  • Ctrl+A → Delete     select all cards, then delete
  • Clear Deck button   delete all cards at once

─────────────────────────────────────────────────
IMPORTING / EXPORTING
  • Import   load a .txt file (Moxfield/Arena format)
  • TXT      export deck list as text
  • Export   generate 3×3 print sheets (PNG + ZIP)
  • Print    generate a home-print PDF

─────────────────────────────────────────────────
UPLOADING TO MPC (makeplayingcards.com)
  1. Optional: choose a card back — "Card Back" button
  2. Click  MPC  button in the toolbar
  3. Configure: quantity, stock type, login option
  4. The browser opens automatically — review & order

  Note: first run requires Playwright (see README).

─────────────────────────────────────────────────
KEYBOARD SHORTCUTS
  Ctrl+A        select all cards in workspace
  Delete        delete selected / all if Ctrl+A used
  Ctrl+Z        undo last action
  Ctrl+Y        redo
  Ctrl+B        toggle sidebar
  Escape        cancel selection

─────────────────────────────────────────────────
TIPS
  • Images are cached in cache/scryfall/ — no re-download
  • Upscaling (Real-ESRGAN) is optional; 300 DPI works fine
  • Decks auto-save to decks/ on every change
  • Run  compress_cache.py  to shrink cache by ~30–50%
  • STATS tab (inspector) shows mana curve & type breakdown
"""


def _open_user_guide() -> None:
    popup = ctk.CTkToplevel()
    popup.title("OtterForge — User Guide")
    popup.geometry("620x680")
    popup.resizable(False, False)
    popup.attributes("-topmost", True)
    popup.grab_set()

    frame = ctk.CTkFrame(popup, fg_color="#1c1a20")
    frame.pack(fill="both", expand=True, padx=0, pady=0)

    txt = ctk.CTkTextbox(
        frame, fg_color="#1c1a20", text_color="#c4bfb8",
        font=ctk.CTkFont(family="Consolas", size=12),
        wrap="none", activate_scrollbars=True,
    )
    txt.pack(fill="both", expand=True, padx=12, pady=(12, 4))
    txt.insert("0.0", _GUIDE_TEXT)
    txt.configure(state="disabled")

    ctk.CTkButton(frame, text="Close", width=80, height=28,
                  command=popup.destroy).pack(pady=(4, 10))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _vsep(parent) -> None:
    ctk.CTkFrame(parent, width=1, fg_color="#34303e").pack(
        side="left", fill="y", padx=10, pady=10
    )


def _micro_label(parent, text: str) -> None:
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=9),
        text_color="#a09aaa",
        anchor="w",
    ).pack(anchor="w", padx=4, pady=(4, 2))


def _tool_btn(parent, text: str, command, tooltip: str = "") -> ctk.CTkButton:
    btn = ctk.CTkButton(
        parent, text=text, width=104, height=28,
        font=ctk.CTkFont(size=11),
        command=command,
    )
    btn.pack(side="left", padx=2)
    if tooltip:
        _Tooltip(btn, tooltip)
    return btn


class _Tooltip:
    """Tooltip léger qui apparaît sous le widget au survol."""

    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip:
            return
        w = self._widget
        x = w.winfo_rootx() + 10
        y = w.winfo_rooty() + w.winfo_height() + 4
        self._tip = tk.Toplevel(w)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self._tip, text=self._text,
            background="#3a3548", foreground="#f0ece4",
            relief="solid", borderwidth=1,
            highlightbackground="#c04828", highlightthickness=1,
            font=("Segoe UI", 20),
            padx=16, pady=10,
        )
        lbl.pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
