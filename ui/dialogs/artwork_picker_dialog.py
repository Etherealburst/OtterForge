"""
ui/dialogs/artwork_picker_dialog.py
-------------------------------------
Dialog shown during folder import when multiple artwork files share the
same normalized card name. Displays thumbnails with checkboxes so the
user can choose which artworks to include.
"""

import os
import tkinter as tk
import customtkinter as ctk
from PIL import Image


THUMB_W, THUMB_H = 80, 112
MAX_PER_ROW = 4


def _load_thumb(path: str) -> ctk.CTkImage | None:
    try:
        img = Image.open(path).convert("RGB")
        img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(THUMB_W, THUMB_H))
    except Exception:
        return None


class ArtworkPickerDialog(ctk.CTkToplevel):
    """
    Shows conflict groups where multiple files share the same normalized card name.
    For each group, thumbnails are displayed with checkboxes (all checked by default).

    Attributes after the window closes:
      .cancelled  — True if the user dismissed without confirming
      .selections — {normalized_name: [selected_path, ...]}
    """

    def __init__(self, master, conflict_groups: dict[str, list[str]]):
        """
        conflict_groups: {normalized_card_name: [path1, path2, ...]}
        """
        super().__init__(master)
        self._conflict_groups = conflict_groups
        self.cancelled = True
        self.selections: dict[str, list[str]] = {}
        self._vars: dict[str, list[tk.BooleanVar]] = {}

        self.title("Multiple Artworks Found")
        self.resizable(False, True)
        self.grab_set()
        self.focus_set()
        self.transient(master)

        master.update_idletasks()
        dw, dh = 530, 600
        if master.winfo_viewable():
            px = master.winfo_x()
            py = master.winfo_y()
            pw = master.winfo_width()
            ph = master.winfo_height()
            self.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
        else:
            self.geometry(f"{dw}x{dh}")

        ctk.CTkLabel(
            self, text="Multiple Artworks Found",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="Several files share the same card name.\n"
                 "Check the artworks you want to include (all selected by default).",
            font=ctk.CTkFont(size=11), text_color="#a09aaa", justify="center",
        ).pack(pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(self, fg_color="#0d0a14")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for card_name, paths in conflict_groups.items():
            self._build_group(scroll, card_name, paths)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(4, 16))

        ctk.CTkButton(
            btn_frame, text="Import Selected",
            width=150, height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#8a6a1a", hover_color="#b08820",
            command=self._confirm,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="Cancel",
            width=90, height=36,
            fg_color="#2a2733", hover_color="#3a3548",
            font=ctk.CTkFont(size=12),
            command=self.destroy,
        ).pack(side="left", padx=8)

        self.bind("<Escape>", lambda e: self.destroy())

    def _build_group(self, parent: ctk.CTkScrollableFrame, card_name: str, paths: list[str]) -> None:
        group_frame = ctk.CTkFrame(parent, fg_color="#15121e", corner_radius=8)
        group_frame.pack(fill="x", padx=4, pady=(0, 10))

        n = len(paths)
        ctk.CTkLabel(
            group_frame,
            text=f"{card_name}  —  {n} artworks found",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#d4a843",
        ).pack(anchor="w", padx=12, pady=(10, 8))

        vars_for_group: list[tk.BooleanVar] = []

        for row_start in range(0, len(paths), MAX_PER_ROW):
            row_paths = paths[row_start:row_start + MAX_PER_ROW]
            row = ctk.CTkFrame(group_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=(0, 6))

            for path in row_paths:
                cell = ctk.CTkFrame(row, fg_color="transparent")
                cell.pack(side="left", padx=8)

                thumb = _load_thumb(path)
                if thumb:
                    lbl = ctk.CTkLabel(cell, image=thumb, text="")
                    lbl.image = thumb
                    lbl.pack()
                else:
                    ctk.CTkLabel(
                        cell, text="[No preview]",
                        width=THUMB_W, height=THUMB_H,
                        fg_color="#252228", corner_radius=4,
                        font=ctk.CTkFont(size=9), text_color="#6a6478",
                    ).pack()

                fname = os.path.splitext(os.path.basename(path))[0]
                display = fname if len(fname) <= 13 else fname[:11] + "…"
                ctk.CTkLabel(
                    cell, text=display,
                    font=ctk.CTkFont(size=9), text_color="#8a8498",
                    wraplength=THUMB_W,
                ).pack(pady=(2, 4))

                var = tk.BooleanVar(value=True)
                vars_for_group.append(var)
                ctk.CTkCheckBox(
                    cell, text="Include",
                    variable=var,
                    font=ctk.CTkFont(size=10),
                    checkbox_width=14, checkbox_height=14,
                    corner_radius=3,
                ).pack()

        ctk.CTkFrame(group_frame, fg_color="transparent", height=4).pack()
        self._vars[card_name] = vars_for_group

    def _confirm(self) -> None:
        for card_name, paths in self._conflict_groups.items():
            selected = [p for p, var in zip(paths, self._vars[card_name]) if var.get()]
            self.selections[card_name] = selected
        self.cancelled = False
        self.destroy()
