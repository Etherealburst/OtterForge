"""
ui/dialogs/export_dialog.py
----------------------------
Dialog de choix du mode d'export des feuilles d'impression.
"""

import customtkinter as ctk


class ExportModeDialog(ctk.CTkToplevel):
    """Demande le mode d'export : 'sheets', 'zip', 'both', ou None si annulé.

    Après `master.wait_window(dialog)`, lire `dialog.result`.
    """

    def __init__(self, master):
        super().__init__(master)
        self.result: str | None = None

        self.title("Exporter les feuilles")
        self.geometry("300x200")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        ctk.CTkLabel(
            self,
            text="Que souhaitez-vous exporter ?",
            font=ctk.CTkFont(size=13),
        ).pack(pady=(20, 16))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=4)

        def choose(mode: str):
            self.result = mode
            self.destroy()

        ctk.CTkButton(btn_frame, text="Feuilles seules", width=200,
                      command=lambda: choose("sheets")).pack(pady=4)
        ctk.CTkButton(btn_frame, text="ZIP seulement", width=200,
                      command=lambda: choose("zip")).pack(pady=4)
        ctk.CTkButton(btn_frame, text="Les deux", width=200,
                      command=lambda: choose("both")).pack(pady=4)

        ctk.CTkButton(self, text="Annuler", fg_color="#581e10", hover_color="#3a1a10",
                      command=self.destroy).pack(pady=(8, 0))
