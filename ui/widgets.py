"""
ui/widgets.py
-------------
Widgets utilitaires partagés entre les composants UI d'OtterForge.
"""

import tkinter as tk


class Tooltip:
    """Popup léger qui affiche un texte au survol d'un widget."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, event: tk.Event | None = None) -> None:
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 10
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self._text,
            background="#3a3548", foreground="#f0ece4",
            relief="solid", borderwidth=1,
            highlightbackground="#c04828", highlightthickness=1,
            font=("Segoe UI", 20),
            padx=16, pady=10,
        ).pack()

    def _hide(self, event: tk.Event | None = None) -> None:
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
