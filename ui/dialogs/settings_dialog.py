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
        self.geometry("520x560")
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

        self._watermark_var = ctk.BooleanVar(
            value=bool(current_settings.get("proxy_watermark", True))
        )

        _mode_labels = {
            "name_only":       "Name only",
            "fetch_metadata":  "Fetch metadata",
            "frame_overlay":   "Frame overlay",
        }
        saved_mode = current_settings.get("custom_artwork_mode", "name_only")
        self._artwork_mode_var = ctk.StringVar(
            value=_mode_labels.get(saved_mode, "Name only")
        )

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

        # ── PROXY WATERMARK ───────────────────────────────────────────────────
        _section(scroll, "PROXY WATERMARK")

        wm_row = ctk.CTkFrame(scroll, fg_color="transparent")
        wm_row.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkSwitch(
            wm_row,
            text='Add "OtterForge Proxy - Not for sale" stamp to all card images',
            variable=self._watermark_var,
            font=ctk.CTkFont(size=11),
            onvalue=True, offvalue=False,
        ).pack(side="left", fill="x")

        ctk.CTkLabel(
            scroll,
            text="Applied after download/upscaling. Replaces the original MTG copyright line.",
            font=ctk.CTkFont(size=10), text_color="#a09aaa", anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 10))

        # ── CUSTOM ARTWORK ────────────────────────────────────────────────────
        _section(scroll, "CUSTOM ARTWORK (+ Custom button)")

        ctk.CTkLabel(
            scroll, text="When associating a custom image with a real card name:",
            font=ctk.CTkFont(size=11), anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkSegmentedButton(
            scroll,
            values=["Name only", "Fetch metadata", "Frame overlay"],
            variable=self._artwork_mode_var,
            font=ctk.CTkFont(size=11),
            height=32,
        ).pack(fill="x", padx=20, pady=(0, 4))

        mode_hints = {
            "Name only":      "Image used as-is. Card name used for deck list only.",
            "Fetch metadata": "Fetches year/set/artist from Scryfall and applies the proxy stamp.",
            "Frame overlay":  "Downloads the card frame from Scryfall and pastes your artwork into the art box.",
        }
        self._mode_hint_label = ctk.CTkLabel(
            scroll, text=mode_hints.get(self._artwork_mode_var.get(), ""),
            font=ctk.CTkFont(size=10), text_color="#a09aaa", anchor="w",
            wraplength=460,
        )
        self._mode_hint_label.pack(fill="x", padx=20, pady=(0, 10))
        self._artwork_mode_var.trace_add("write", self._update_mode_hint)

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

    def _update_mode_hint(self, *_):
        hints = {
            "Name only":      "Image used as-is. Card name used for deck list only.",
            "Fetch metadata": "Fetches year/set/artist from Scryfall and applies the proxy stamp.",
            "Frame overlay":  "Downloads the card frame from Scryfall and pastes your artwork into the art box.",
        }
        self._mode_hint_label.configure(text=hints.get(self._artwork_mode_var.get(), ""))

    def _save(self):
        result = {k: v.get() for k, v in self._vars.items()}
        result["proxy_watermark"] = bool(self._watermark_var.get())
        mode_map = {
            "Name only":      "name_only",
            "Fetch metadata": "fetch_metadata",
            "Frame overlay":  "frame_overlay",
        }
        result["custom_artwork_mode"] = mode_map.get(self._artwork_mode_var.get(), "name_only")
        self.result = result
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
