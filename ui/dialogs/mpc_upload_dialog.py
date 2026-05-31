"""
ui/dialogs/mpc_upload_dialog.py
---------------------------------
Dialog de configuration de l'upload MPC.
"""

import os
import customtkinter as ctk
from tkinter import messagebox

from ui.mpc_threshold_bar import MPCThresholdBar


class MPCUploadDialog(ctk.CTkToplevel):
    """Dialog de configuration MPC.

    Args:
        master: fenêtre parente.
        deck_name: nom du deck.
        total_slots: nombre de slots occupés.
        mpc_qty: quantité MPC (multiple de 18 >= total_slots).
        has_backs: True si des endos sont détectés.
        deck_back_image: chemin de l'image d'endos globale (ou None).
        mpc_prefs: dict des préférences précédentes {'stock', 'headless', 'login', 'upload_backs'}.

    Après `master.wait_window(dialog)`, lire `dialog.result` (dict ou None si annulé).
    Le dict contient : headless, stock, login, upload_backs, confirmed=True.
    """

    def __init__(
        self,
        master,
        deck_name: str,
        total_slots: int,
        mpc_qty: int,
        has_backs: bool,
        deck_back_image: str | None,
        mpc_prefs: dict,
    ):
        super().__init__(master)
        self.result: dict | None = None

        self.title("Upload to MPC")
        self.geometry("440x600")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        empty_slots = mpc_qty - total_slots

        ctk.CTkLabel(
            self,
            text="Upload to MakePlayingCards.com",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            self,
            text=f"Deck: {deck_name}   •   {total_slots} card(s)",
            font=ctk.CTkFont(size=11),
            text_color="#a09aaa",
        ).pack(pady=(0, 6))

        MPCThresholdBar(self, total_slots, mpc_qty).pack(padx=20, fill="x", pady=(0, 8))

        _est_fronts = total_slots * 5
        _est_backs = total_slots * 3 if has_backs else 0
        _est_total_min = max(1, (_est_fronts + _est_backs + 60) // 60)
        _eta_parts = [f"fronts ~{max(1, _est_fronts // 60)} min"]
        if has_backs:
            _eta_parts.append(f"backs ~{max(1, _est_backs // 60)} min")
        ctk.CTkLabel(
            self,
            text=f"Estimated time: ~{_est_total_min} min  ({' + '.join(_eta_parts)})",
            font=ctk.CTkFont(size=10),
            text_color="gray60",
        ).pack(pady=(0, 6))

        if empty_slots > 0:
            warn_frame = ctk.CTkFrame(self, fg_color="#3d1a1a", corner_radius=6)
            warn_frame.pack(padx=20, fill="x", pady=(0, 8))
            ctk.CTkLabel(
                warn_frame,
                text=f"⚠  {empty_slots} empty slot(s) — they will appear at the end of the MPC order.",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#f5e6e6",
                wraplength=380,
                justify="left",
            ).pack(padx=12, pady=8)

        if not deck_back_image:
            noback_frame = ctk.CTkFrame(self, fg_color="#162436", corner_radius=6)
            noback_frame.pack(padx=20, fill="x", pady=(0, 8))
            ctk.CTkLabel(
                noback_frame,
                text="ℹ  No global card back set — the standard MTG card back (MPCFILL) will be automatically downloaded and used for all non-DFC cards.",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#e6f0f8",
                wraplength=380,
                justify="left",
            ).pack(padx=12, pady=8)

        # Card stock
        stock_frame = ctk.CTkFrame(self, fg_color="transparent")
        stock_frame.pack(padx=24, anchor="w", pady=(0, 6))
        ctk.CTkLabel(stock_frame, text="Card stock :", font=ctk.CTkFont(size=11)).pack(
            side="left", padx=(0, 8)
        )
        stock_var = ctk.StringVar(value=mpc_prefs.get("stock", "S30"))
        for s in ("S30", "S33"):
            ctk.CTkRadioButton(
                stock_frame, text=s, variable=stock_var, value=s,
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=6)

        # Connexion MPC
        login_var = ctk.BooleanVar(value=mpc_prefs.get("login", False))
        ctk.CTkCheckBox(
            self,
            text="Log in to MPC (2 min for login, optional)",
            variable=login_var,
            font=ctk.CTkFont(size=11),
        ).pack(padx=24, anchor="w", pady=(0, 4))

        # Mode navigateur
        headless_var = ctk.BooleanVar(value=mpc_prefs.get("headless", False))
        ctk.CTkCheckBox(
            self,
            text="Background mode (invisible browser)",
            variable=headless_var,
            font=ctk.CTkFont(size=11),
        ).pack(padx=24, anchor="w", pady=(0, 6))

        # Upload backs
        back_label = ""
        if deck_back_image:
            back_label = f" ({os.path.basename(deck_back_image)})"
        elif not has_backs:
            back_label = " (no card back detected)"
        saved_upload_backs = mpc_prefs.get("upload_backs", has_backs) if has_backs else False
        upload_backs_var = ctk.BooleanVar(value=saved_upload_backs)
        ctk.CTkCheckBox(
            self,
            text=f"Upload backs{back_label}",
            variable=upload_backs_var,
            state="normal" if has_backs else "disabled",
            font=ctk.CTkFont(size=11),
        ).pack(padx=24, anchor="w", pady=(0, 12))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack()

        def on_start():
            if not deck_back_image:
                if not messagebox.askyesno(
                    "No card back — standard fill",
                    "No global card back is set.\n\n"
                    "The standard MTG card back (MPCFILL) will be automatically downloaded "
                    "and used as the back for all non-DFC cards before uploading.\n\n"
                    "Proceed?",
                    parent=self,
                ):
                    return
            if empty_slots > 0:
                if not messagebox.askyesno(
                    "Empty slots",
                    f"Your deck has {total_slots} card(s), but MPC requires {mpc_qty} slots.\n\n"
                    f"{empty_slots} slot(s) will remain empty at the end of the order.\n\n"
                    "Continue anyway?",
                    parent=self,
                ):
                    return
            self.result = {
                "headless": headless_var.get(),
                "stock": stock_var.get(),
                "login": login_var.get(),
                "upload_backs": upload_backs_var.get(),
                "confirmed": True,
            }
            self.destroy()

        ctk.CTkButton(btn_frame, text="Start upload", width=170,
                      command=on_start).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Cancel", width=100,
                      fg_color="#581e10", hover_color="#3a1a10",
                      command=self.destroy).pack(side="left", padx=6)
