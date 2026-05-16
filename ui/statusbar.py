"""
ui/statusbar.py
---------------
Barre de statut fixe en bas de la fenêtre principale.
"""

import customtkinter as ctk


class StatusBar(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, height=30, corner_radius=0, fg_color="#0d0c0e")
        self.pack_propagate(False)

        ctk.CTkFrame(self, height=1, fg_color="#1a1820",
                     corner_radius=0).pack(side="top", fill="x")

        self.label = ctk.CTkLabel(
            self, text="Ready", anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#c4bfb8",
        )
        self.label.pack(side="left", padx=12)

        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")

        self._progress_count = ctk.CTkLabel(
            self._progress_frame, text="",
            font=ctk.CTkFont(size=11),
            text_color="#c4bfb8",
        )
        self._progress_count.pack(side="right", padx=(4, 12))

        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, width=180, height=8)
        self._progress_bar.set(0)
        self._progress_bar.pack(side="right", padx=4)

    def set_status(self, text: str) -> None:
        self.label.configure(text=text)

    def show_progress(self) -> None:
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        self._progress_bar.set(0)
        self._progress_count.configure(text="")
        self._progress_frame.pack(side="right", padx=4)

    def show_indeterminate(self, label: str = "") -> None:
        if label:
            self.label.configure(text=label)
        self._progress_bar.configure(mode="indeterminate")
        self._progress_bar.start()
        self._progress_count.configure(text="")
        self._progress_frame.pack(side="right", padx=4)

    def update_progress(self, current: int, total: int) -> None:
        self._progress_bar.set(current / total if total else 0)
        self._progress_count.configure(text=f"{current} / {total}")

    def hide_progress(self) -> None:
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        self._progress_frame.pack_forget()
