"""
ui/card_search.py
-----------------
Barre de recherche de cartes Magic avec historique des 20 dernières requêtes.
"""

import tkinter as tk
import customtkinter as ctk

_HISTORY_MAX = 20


class CardSearch(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, height=46, corner_radius=0, fg_color="#1c1a20")
        self.master = master
        self.pack_propagate(False)
        self._history: list[str] = []
        self._dropdown: tk.Toplevel | None = None
        self._build()

    def _build(self):
        ctk.CTkFrame(self, width=3, height=26, fg_color="#c04828",
                     corner_radius=2).pack(side="left", padx=(10, 8))

        ctk.CTkLabel(
            self, text="SEARCH",
            font=ctk.CTkFont(size=9),
            text_color="#5a5060",
        ).pack(side="left", padx=(0, 8))

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Card name  ·  s:SET cn:NUM  ·  1 Name (SET) #",
            width=460, height=30,
            font=ctk.CTkFont(size=12),
        )
        self.entry.pack(side="left", padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._on_add())
        self.entry.bind("<FocusIn>", self._on_entry_focus)
        self.entry.bind("<FocusOut>", lambda e: self.after(150, self._hide_dropdown))
        self.entry.bind("<Escape>", lambda e: self._hide_dropdown())

        self.add_btn = ctk.CTkButton(
            self, text="Add to Deck", width=110, height=30,
            font=ctk.CTkFont(size=12),
            command=self._on_add,
        )
        self.add_btn.pack(side="left")

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _push_history(self, query: str) -> None:
        if query in self._history:
            self._history.remove(query)
        self._history.insert(0, query)
        if len(self._history) > _HISTORY_MAX:
            self._history = self._history[:_HISTORY_MAX]

    # ------------------------------------------------------------------
    # Dropdown
    # ------------------------------------------------------------------

    def _on_entry_focus(self, event=None) -> None:
        if self._history:
            self._show_dropdown()

    def _show_dropdown(self) -> None:
        self._hide_dropdown()
        if not self._history:
            return

        self.entry.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        w = self.entry.winfo_width()

        tw = tk.Toplevel(self.entry)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"{w}x{min(len(self._history), 8) * 26}+{x}+{y}")
        tw.configure(bg="#221f28")
        self._dropdown = tw

        lb = tk.Listbox(
            tw,
            bg="#221f28", fg="#f0ece4",
            selectbackground="#c04828", selectforeground="#ffffff",
            activestyle="none",
            relief="flat", borderwidth=0,
            font=("Segoe UI", 11),
            highlightthickness=0,
        )
        lb.pack(fill="both", expand=True)

        for item in self._history:
            lb.insert(tk.END, item)

        def on_select(event):
            if lb.curselection():
                chosen = lb.get(lb.curselection()[0])
                self.entry.delete(0, tk.END)
                self.entry.insert(0, chosen)
                self._hide_dropdown()
                self.entry.focus_set()

        lb.bind("<ButtonRelease-1>", on_select)
        lb.bind("<Return>", on_select)

    def _hide_dropdown(self) -> None:
        if self._dropdown:
            try:
                self._dropdown.destroy()
            except Exception:
                pass
            self._dropdown = None

    # ------------------------------------------------------------------
    # Add action
    # ------------------------------------------------------------------

    def _on_add(self):
        name = self.entry.get().strip()
        if not name:
            return
        self._push_history(name)
        self._hide_dropdown()
        self.master.search_and_add_card(name)
        self.entry.delete(0, "end")
