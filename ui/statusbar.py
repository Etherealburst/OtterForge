"""
ui/statusbar.py
---------------
Barre de statut affichée en bas de la fenêtre principale.
Inclut une barre de progression affichée uniquement pendant les imports.
"""

import customtkinter as ctk


class StatusBar(ctk.CTkFrame):
    """Barre de statut fixe en bas de la fenêtre."""

    def __init__(self, master):
        super().__init__(master, height=28, corner_radius=0)
        self.pack_propagate(False)
        self.configure(fg_color="#2b2b2b")

        self.label = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.label.pack(side="left", padx=10)

        # ------------------------------------------------------------------
        # BARRE DE PROGRESSION (cachée par défaut)
        # ------------------------------------------------------------------
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")

        self._progress_count = ctk.CTkLabel(
            self._progress_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        )
        self._progress_count.pack(side="right", padx=(4, 10))

        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, width=180, height=10)
        self._progress_bar.set(0)
        self._progress_bar.pack(side="right", padx=4)

    def set_status(self, text: str) -> None:
        """Met à jour le texte de la barre de statut."""
        self.label.configure(text=text)

    def show_progress(self) -> None:
        """Affiche la barre en mode déterminé (import avec total connu)."""
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        self._progress_bar.set(0)
        self._progress_count.configure(text="")
        self._progress_frame.pack(side="right", padx=4)

    def show_indeterminate(self, label: str = "") -> None:
        """Affiche la barre en mode indéterminé (pulsation) pour les opérations sans total connu."""
        if label:
            self.label.configure(text=label)
        self._progress_bar.configure(mode="indeterminate")
        self._progress_bar.start()
        self._progress_count.configure(text="")
        self._progress_frame.pack(side="right", padx=4)

    def update_progress(self, current: int, total: int) -> None:
        """Met à jour la valeur de la barre de progression."""
        self._progress_bar.set(current / total if total else 0)
        self._progress_count.configure(text=f"{current} / {total}")

    def hide_progress(self) -> None:
        """Cache la barre et arrête toute animation."""
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        self._progress_frame.pack_forget()
