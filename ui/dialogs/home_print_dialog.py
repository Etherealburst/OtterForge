"""
ui/dialogs/home_print_dialog.py
--------------------------------
Dialog d'impression à domicile — configuration et génération des feuilles.
"""

import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

from engine.home_print_engine import HomePrintEngine, PAPER_SIZES_IN


class HomePrintDialog(ctk.CTkToplevel):
    """
    Dialog de configuration pour l'impression à domicile.

    Args:
        master:      fenêtre parente
        cards:       liste de Card à imprimer

    Après `master.wait_window(dialog)`, `dialog.result` est None si annulé.
    La génération des fichiers se fait directement dans ce dialog.
    """

    def __init__(self, master, cards: list):
        super().__init__(master)
        self.result = None
        self._cards = cards

        self.title("Home Printing")
        self.geometry("480x540")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self._paper    = ctk.StringVar(value="Letter")
        self._fmt      = ctk.StringVar(value="PDF")
        self._margin   = ctk.StringVar(value="5")
        self._card_w   = ctk.StringVar(value="63.5")
        self._card_h   = ctk.StringVar(value="88.9")
        self._crops    = ctk.BooleanVar(value=False)
        self._duplex   = ctk.BooleanVar(value=False)

        self._build()
        self._refresh_preview()

        for v in (self._paper, self._fmt, self._margin, self._card_w, self._card_h):
            v.trace_add("write", lambda *_: self._refresh_preview())
        self._crops.trace_add("write", lambda *_: self._refresh_preview())
        self._duplex.trace_add("write", lambda *_: self._refresh_preview())

    # ------------------------------------------------------------------

    def _build(self):
        # ── BOUTONS — packés EN PREMIER ───────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=12)

        ctk.CTkButton(btn_frame, text="Cancel", width=110,
                      fg_color="#2a2733", hover_color="#3a3548",
                      command=self.destroy).pack(side="right", padx=(6, 0))
        self._gen_btn = ctk.CTkButton(btn_frame, text="Generate", width=130,
                                      command=self._generate)
        self._gen_btn.pack(side="right")

        # ── STATUT en bas ─────────────────────────────────────────────
        self._status = ctk.CTkLabel(self, text="", anchor="w",
                                    font=ctk.CTkFont(size=11))
        self._status.pack(side="bottom", fill="x", padx=20, pady=(0, 2))

        # ── CONTENU scrollable ────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ── PAPIER ───────────────────────────────────────────────────
        _section(scroll, "PAPER")

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(row, text="Format", width=80, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkOptionMenu(row, variable=self._paper,
                          values=list(PAPER_SIZES_IN.keys()),
                          width=120).pack(side="left", padx=(0, 24))
        ctk.CTkLabel(row, text="Margins (mm)", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(row, textvariable=self._margin, width=60,
                     height=28, font=ctk.CTkFont(size=11)).pack(side="left", padx=(6, 0))

        # ── CARTE ────────────────────────────────────────────────────
        _section(scroll, "CARD")

        ctk.CTkLabel(scroll, text="Size in mm  (standard poker: 63.5 × 88.9)",
                     text_color="#a09aaa", font=ctk.CTkFont(size=10),
                     anchor="w").pack(fill="x", padx=20, pady=(0, 6))

        sz_row = ctk.CTkFrame(scroll, fg_color="transparent")
        sz_row.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(sz_row, text="Width", width=60, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(sz_row, textvariable=self._card_w, width=72,
                     height=28, font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 16))
        ctk.CTkLabel(sz_row, text="Height", width=60, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(sz_row, textvariable=self._card_h, width=72,
                     height=28, font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 0))

        # ── OPTIONS ──────────────────────────────────────────────────
        _section(scroll, "OPTIONS")

        fmt_row = ctk.CTkFrame(scroll, fg_color="transparent")
        fmt_row.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(fmt_row, text="Output format", width=100, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkOptionMenu(fmt_row, variable=self._fmt,
                          values=["PDF", "PNG"],
                          width=100).pack(side="left")

        ctk.CTkCheckBox(scroll, text="Crop marks",
                        variable=self._crops).pack(anchor="w", padx=20, pady=(4, 4))
        ctk.CTkCheckBox(scroll, text="Duplex — generate mirrored back sheets",
                        variable=self._duplex).pack(anchor="w", padx=20, pady=(0, 6))

        # ── APERÇU ───────────────────────────────────────────────────
        _section(scroll, "PREVIEW")

        self._preview = ctk.CTkLabel(scroll, text="", anchor="w",
                                     font=ctk.CTkFont(size=12),
                                     text_color="#f0ece4")
        self._preview.pack(fill="x", padx=20, pady=(0, 8))

    # ------------------------------------------------------------------

    def _engine(self) -> HomePrintEngine | None:
        try:
            return HomePrintEngine(
                paper=self._paper.get(),
                card_w_mm=float(self._card_w.get()),
                card_h_mm=float(self._card_h.get()),
                margin_mm=float(self._margin.get()),
                crop_marks=self._crops.get(),
                duplex=self._duplex.get(),
            )
        except (ValueError, ZeroDivisionError):
            return None

    def _refresh_preview(self) -> None:
        eng = self._engine()
        if eng is None:
            self._preview.configure(text="⚠  Invalid values", text_color="#c04828")
            self._gen_btn.configure(state="disabled")
            return

        total_cards = sum(getattr(c, "count", 1) for c in self._cards)
        n_front = eng.sheet_count(self._cards)
        n_total = n_front * (2 if self._duplex.get() else 1)

        fmt = self._fmt.get()
        duplex_note = "  (front + back)" if self._duplex.get() else ""
        self._preview.configure(
            text=(
                f"{eng.cols} col × {eng.rows} rows = {eng.cards_per_sheet} cards/sheet\n"
                f"{total_cards} cards → {n_front} front sheet(s) → {n_total} file(s){duplex_note}\n"
                f"Format: {fmt}   |   {self._paper.get()}   |   300 DPI"
            ),
            text_color="#f0ece4",
        )
        self._gen_btn.configure(state="normal")

    # ------------------------------------------------------------------

    def _generate(self) -> None:
        eng = self._engine()
        if eng is None:
            return

        fmt = self._fmt.get()
        cards = self._cards

        if fmt == "PDF":
            path = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="home_print.pdf",
            )
            if not path:
                return
        else:
            path = filedialog.askdirectory(parent=self)
            if not path:
                return

        self._gen_btn.configure(state="disabled", text="Processing…")
        self._status.configure(text="Generating…", text_color="#d4a843")

        def _worker():
            try:
                if fmt == "PDF":
                    result = eng.export_pdf(cards, path)
                    msg = f"PDF generated:\n{result}"
                else:
                    paths = eng.export_png(cards, path)
                    msg = f"{len(paths)} PNG(s) generated in:\n{path}"
                self.after(0, self._on_done, msg, None)
            except Exception as e:
                self.after(0, self._on_done, None, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_done(self, msg: str | None, err: str | None) -> None:
        self._gen_btn.configure(state="normal", text="Generate")
        if err:
            self._status.configure(text=f"Error: {err}", text_color="#c04828")
            messagebox.showerror("Error", err, parent=self)
        else:
            self._status.configure(text="Sheets generated successfully ✓", text_color="#5cb85c")
            messagebox.showinfo("Home Printing", msg, parent=self)
            self.result = True
            self.destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section(parent, title: str) -> None:
    ctk.CTkLabel(parent, text=title,
                 font=ctk.CTkFont(size=10),
                 text_color="#a09aaa",
                 anchor="w").pack(fill="x", padx=20, pady=(14, 4))
    ctk.CTkFrame(parent, height=1, fg_color="#34303e").pack(fill="x", padx=20, pady=(0, 8))
