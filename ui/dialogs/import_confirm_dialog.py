"""
ui/dialogs/import_confirm_dialog.py
------------------------------------
Dialog de confirmation avant l'import d'un fichier TXT.
"""

import os
import customtkinter as ctk


class ImportConfirmDialog(ctk.CTkToplevel):
    """Affiche les infos du fichier et demande confirmation.

    Après `master.wait_window(dialog)`, lire `dialog.result` (bool).
    """

    def __init__(self, master, path: str, card_count: int, upscaler_available: bool):
        super().__init__(master)
        self.result: bool = False

        self.title("Importer un deck")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()
        self.transient(master)

        master.update_idletasks()
        dw, dh = 420, 260
        if master.winfo_viewable():
            px, py = master.winfo_x(), master.winfo_y()
            pw, ph = master.winfo_width(), master.winfo_height()
            self.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
        else:
            self.geometry(f"{dw}x{dh}")

        padx = 28

        ctk.CTkLabel(
            self, text="Importer ce deck ?",
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=360,
        ).pack(pady=(24, 16))

        fname = os.path.basename(path)
        ctk.CTkLabel(
            self, text=f"Fichier : {fname}",
            font=ctk.CTkFont(size=11), text_color="#5a5060",
        ).pack(padx=padx)

        ctk.CTkLabel(
            self, text=f"Cartes détectées : {card_count}",
            font=ctk.CTkFont(size=12),
        ).pack(padx=padx, pady=(6, 0))

        if card_count > 0:
            # Download parallelized ×5 workers (~0.4s/card wall time from Scryfall)
            # Upscaled images are cached — repeat imports take only a few seconds
            total_secs = max(5, card_count * 2 // 5)
            mins, secs = divmod(total_secs, 60)
            if mins > 0:
                time_str = f"~{mins} min {secs} s" if secs else f"~{mins} min"
            else:
                time_str = f"~{total_secs} s"
            if upscaler_available:
                quality = "images en cache → rapide ; 1ère fois avec upscaling : plus long"
            else:
                quality = "téléchargement seul, sans upscaling"
            eta_text = f"Temps estimé : {time_str}  ({quality})"
        else:
            eta_text = "Aucune carte détectée dans ce fichier."

        ctk.CTkLabel(
            self, text=eta_text,
            font=ctk.CTkFont(size=11), text_color="#5a5060",
            wraplength=360,
        ).pack(padx=padx, pady=(4, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        def on_yes():
            self.result = True
            self.destroy()

        def on_no():
            self.destroy()

        ctk.CTkButton(
            btn_frame, text="Oui", width=110, height=36,
            font=ctk.CTkFont(size=13),
            command=on_yes,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="Non", width=110, height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#581e10", hover_color="#3a1a10",
            command=on_no,
        ).pack(side="left", padx=10)

        self.bind("<Return>", lambda e: on_yes())
        self.bind("<Escape>", lambda e: on_no())
