"""
ui/dialogs/settings_dialog.py
-------------------------------
Dialog Paramètres OtterForge.
Permet de configurer le chemin Real-ESRGAN et les dossiers de données.
"""

import os
import customtkinter as ctk
from tkinter import filedialog

import config


class SettingsDialog(ctk.CTkToplevel):
    """Dialog de paramètres.

    Args:
        master: fenêtre parente.
        current_settings: dict issu de user_config["settings"].
        upscaler: instance ImageUpscaler pour afficher le statut en direct.

    Après `master.wait_window(dialog)`, lire `dialog.result` (dict ou None si annulé).
    """

    def __init__(self, master, current_settings: dict, upscaler):
        super().__init__(master)
        self.result: dict | None = None
        self._upscaler = upscaler

        self.title("Settings")
        self.geometry("520x420")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self._vars = {
            "realesrgan_dir": ctk.StringVar(value=current_settings.get(
                "realesrgan_dir", config.REALESRGAN_DIR
            )),
            "cache_dir": ctk.StringVar(value=current_settings.get(
                "cache_dir", config.CACHE_DIR
            )),
            "output_dir": ctk.StringVar(value=current_settings.get(
                "output_dir", config.OUTPUT_DIR
            )),
            "decks_dir": ctk.StringVar(value=current_settings.get(
                "decks_dir", config.DECKS_DIR
            )),
        }

        self._build()

    def _build(self):
        # ── BOUTONS — packés EN PREMIER pour réserver leur espace en bas ──────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=12)

        ctk.CTkButton(btn_frame, text="Cancel", width=110, fg_color="#2a2733",
                      hover_color="#3a3548",
                      command=self.destroy).pack(side="right", padx=(6, 0))
        ctk.CTkButton(btn_frame, text="Save", width=130,
                      command=self._save).pack(side="right")

        # ── CONTENU — remplit l'espace restant ────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # ── UPSCALING ─────────────────────────────────────────────────────────
        _section(scroll, "UPSCALING (Real-ESRGAN)")

        ctk.CTkLabel(scroll, text="Real-ESRGAN Folder", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(fill="x", padx=20, pady=(4, 2))

        esrgan_row = ctk.CTkFrame(scroll, fg_color="transparent")
        esrgan_row.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkEntry(esrgan_row, textvariable=self._vars["realesrgan_dir"],
                     height=30, font=ctk.CTkFont(size=11)
                     ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(esrgan_row, text="Browse", width=90, height=30,
                      command=lambda: self._browse_dir(self._vars["realesrgan_dir"])
                      ).pack(side="left")

        self._status_label = ctk.CTkLabel(scroll, text="", anchor="w",
                                          font=ctk.CTkFont(size=11))
        self._status_label.pack(fill="x", padx=20, pady=(0, 8))
        self._vars["realesrgan_dir"].trace_add("write", lambda *_: self._refresh_esrgan_status())
        self._refresh_esrgan_status()

        # ── DOSSIERS ──────────────────────────────────────────────────────────
        _section(scroll, "FOLDERS")

        ctk.CTkLabel(scroll,
                     text="↺  Changes take effect on next startup.",
                     text_color="#a09aaa", font=ctk.CTkFont(size=10),
                     anchor="w").pack(fill="x", padx=20, pady=(0, 8))

        for label, key in [("Cache", "cache_dir"), ("Output", "output_dir"), ("Decks", "decks_dir")]:
            _folder_row(scroll, label, self._vars[key], self._browse_dir)

    def _refresh_esrgan_status(self):
        exe = os.path.join(self._vars["realesrgan_dir"].get(),
                           "realesrgan-ncnn-vulkan.exe")
        if os.path.isfile(exe):
            self._status_label.configure(text="✓  Available", text_color="#5cb85c")
        else:
            self._status_label.configure(text="✗  Not found", text_color="#c04828")

    def _browse_dir(self, var: ctk.StringVar):
        initial = var.get() if os.path.isdir(var.get()) else os.path.expanduser("~")
        path = filedialog.askdirectory(initialdir=initial)
        if path:
            var.set(os.path.normpath(path))

    def _save(self):
        self.result = {k: v.get() for k, v in self._vars.items()}
        self.destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section(parent, title: str):
    ctk.CTkLabel(
        parent, text=title,
        font=ctk.CTkFont(size=10),
        text_color="#a09aaa",
        anchor="w",
    ).pack(fill="x", padx=20, pady=(14, 4))
    ctk.CTkFrame(parent, height=1, fg_color="#34303e").pack(fill="x", padx=20, pady=(0, 8))


def _folder_row(parent, label: str, var: ctk.StringVar, browse_fn):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(0, 6))

    ctk.CTkLabel(row, text=label, width=56, anchor="w",
                 font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
    ctk.CTkEntry(row, textvariable=var, height=30,
                 font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True, padx=(0, 6))
    ctk.CTkButton(row, text="...", width=36, height=30,
                  command=lambda v=var: browse_fn(v)).pack(side="left")
