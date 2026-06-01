"""
ui/card_back_picker.py
----------------------
Dialog pour choisir l'image d'endos des cartes.

Trois sources :
  - "From a file"     : sélectionne un fichier image depuis l'ordinateur
  - "MPCFill Presets" : carte dos MTG standard (téléchargeable) + images card_backs/
"""

import io
import os
import queue
import threading
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk

from config import CACHE_DIR, CARD_BACKS_DIR

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
THUMB_W, THUMB_H = 120, 168

# Standard MTG card back — downloaded from Scryfall CDN on first use
_MPCFILL_MPC300  = os.path.join(CACHE_DIR, "scryfall", "_mpcfill_cardback_mpc300.png")
_MPCFILL_RAW     = os.path.join(CACHE_DIR, "scryfall", "_mpcfill_cardback.png")
_MPCFILL_SOURCES = [
    "https://c2.scryfall.com/file/scryfall-card-backs/large/0a/0aeebaf5-8c7d-4636-9e82-8c27447861f7.jpg",
    "https://upload.wikimedia.org/wikipedia/en/a/aa/Magic_the_gathering-card_back.jpg",
]


def _mpcfill_path() -> str | None:
    """Return local path of the standard MTG card back, or None if not yet downloaded."""
    if os.path.exists(_MPCFILL_MPC300):
        return _MPCFILL_MPC300
    if os.path.exists(_MPCFILL_RAW):
        return _MPCFILL_RAW
    return None


def _download_mpcfill() -> str | None:
    """Download the standard MTG card back to cache.  Returns path on success."""
    try:
        import requests as _req
    except ImportError:
        return None

    os.makedirs(os.path.dirname(_MPCFILL_RAW), exist_ok=True)
    for url in _MPCFILL_SOURCES:
        try:
            r = _req.get(url, timeout=20, headers={"User-Agent": "OtterForge/2.0"})
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            img.save(_MPCFILL_RAW, "PNG")
            return _MPCFILL_RAW
        except Exception:
            continue
    return None


class CardBackPickerDialog(ctk.CTkToplevel):
    """
    Fenêtre modale de sélection d'endos.
    Résultat dans self.result (str path ou None si annulé).
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("Choose Card Back")
        self.geometry("760x560")
        self.minsize(620, 480)
        self.resizable(True, True)
        self.grab_set()
        self.focus_set()

        self.result: str | None = None
        self._thumb_refs: list = []
        self._thumb_queue: queue.Queue = queue.Queue()
        self._thumb_labels: dict = {}
        self._placeholder_ref = None

        os.makedirs(CARD_BACKS_DIR, exist_ok=True)
        self._build()

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------

    def _build(self):
        # Main area: tabview + footer
        tabview = ctk.CTkTabview(self)
        tabview.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        tab_upload  = tabview.add("From a file")
        tab_gallery = tabview.add("MPCFill Presets")

        self._build_upload_tab(tab_upload)
        self._build_gallery_tab(tab_gallery)

        # Footer — always visible at the bottom
        footer = ctk.CTkFrame(self, fg_color="transparent", height=44)
        footer.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer, text="Cancel",
            fg_color="#581e10", hover_color="#3a1a10",
            command=self.destroy,
        ).pack(side="right", padx=4)

    # ------ UPLOAD TAB ------

    def _build_upload_tab(self, parent):
        ctk.CTkLabel(
            parent,
            text="Choose any image from your computer to use as card back.",
            font=ctk.CTkFont(size=12),
            text_color="#a09aaa",
        ).pack(pady=(20, 12))

        self._upload_preview_label = ctk.CTkLabel(parent, text="")
        self._upload_preview_label.pack(pady=(0, 10))

        self._upload_path_var = tk.StringVar(value="No file selected")
        ctk.CTkLabel(parent, textvariable=self._upload_path_var,
                     text_color="#a09aaa", font=ctk.CTkFont(size=11)).pack()

        ctk.CTkButton(parent, text="Browse…", command=self._browse_file).pack(pady=10)

        ctk.CTkButton(
            parent, text="Use this image",
            fg_color="#c04828", hover_color="#a83820", text_color="#f0ece4",
            command=self._confirm_upload,
        ).pack(pady=(0, 8))

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select card back image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._upload_path_var.set(os.path.basename(path))
        self._selected_upload_path = path
        self._show_upload_preview(path)

    def _show_upload_preview(self, path: str):
        try:
            img = Image.open(path).resize((THUMB_W, THUMB_H), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._upload_thumb_ref = tk_img
            self._upload_preview_label.configure(image=tk_img, text="")
        except Exception:
            self._upload_preview_label.configure(text="Preview unavailable", image="")

    def _confirm_upload(self):
        path = getattr(self, "_selected_upload_path", None)
        if not path or not os.path.isfile(path):
            return
        self.result = path
        self.destroy()

    # ------ GALLERY TAB ------

    def _build_gallery_tab(self, parent):
        # Header row with folder button and refresh
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(
            header,
            text=f"Card backs folder: {CARD_BACKS_DIR}",
            font=ctk.CTkFont(size=11),
            text_color="#a09aaa",
        ).pack(side="left")

        ctk.CTkButton(
            header, text="Open folder", width=100, height=26,
            font=ctk.CTkFont(size=11),
            command=self._open_card_backs_folder,
        ).pack(side="right")

        ctk.CTkButton(
            header, text="Refresh", width=70, height=26,
            font=ctk.CTkFont(size=11),
            command=self._refresh_gallery,
        ).pack(side="right", padx=(0, 6))

        self._gallery_frame = ctk.CTkScrollableFrame(parent)
        self._gallery_frame.pack(fill="both", expand=True, padx=8, pady=4)

        # Shared grey placeholder
        ph = Image.new("RGB", (THUMB_W, THUMB_H), (43, 43, 43))
        self._placeholder_ref = ImageTk.PhotoImage(ph)

        self._refresh_gallery()

    def _refresh_gallery(self):
        for widget in self._gallery_frame.winfo_children():
            widget.destroy()
        self._thumb_refs.clear()
        self._thumb_labels.clear()

        # ── Built-in: standard MTG card back ─────────────────────────────────
        mpcfill = _mpcfill_path()
        builtin_frame = ctk.CTkFrame(self._gallery_frame, fg_color="#1a1724")
        builtin_frame.pack(fill="x", pady=(0, 8), padx=2)

        ctk.CTkLabel(
            builtin_frame,
            text="Standard MTG Card Back",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#c04828",
        ).pack(anchor="w", padx=10, pady=(8, 4))

        if mpcfill:
            self._add_builtin_card(builtin_frame, mpcfill, "Standard MTG")
        else:
            self._add_download_button(builtin_frame)

        # ── Separator ────────────────────────────────────────────────────────
        ctk.CTkFrame(self._gallery_frame, height=1, fg_color="#34303e").pack(
            fill="x", padx=4, pady=(0, 6))

        # ── User card backs from card_backs/ ──────────────────────────────────
        images = sorted([
            os.path.join(CARD_BACKS_DIR, f)
            for f in os.listdir(CARD_BACKS_DIR)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        ])

        if not images:
            ctk.CTkLabel(
                self._gallery_frame,
                text="No custom card backs found.\nAdd images to the card_backs/ folder and click Refresh.",
                text_color="#a09aaa",
                font=ctk.CTkFont(size=12),
            ).pack(pady=20)
        else:
            cols = 4
            row_frame = None
            for idx, path in enumerate(images):
                if idx % cols == 0:
                    row_frame = ctk.CTkFrame(self._gallery_frame, fg_color="transparent")
                    row_frame.pack(fill="x", pady=4)
                lbl = self._add_gallery_placeholder(row_frame, path)
                self._thumb_labels[path] = lbl

            # Load thumbnails in background
            self._thumb_queue = queue.Queue()
            threading.Thread(
                target=self._load_thumbs_bg,
                args=(list(images),),
                daemon=True,
            ).start()
            self.after(30, self._poll_thumb_queue)

    def _add_builtin_card(self, parent, path: str, label: str) -> None:
        card = ctk.CTkFrame(parent, fg_color="#221f28", corner_radius=6)
        card.pack(side="left", padx=10, pady=(0, 10))

        try:
            img = Image.open(path).resize((THUMB_W, THUMB_H), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._thumb_refs.append(tk_img)
            lbl = tk.Label(card, image=tk_img, bg="#221f28", cursor="hand2")
        except Exception:
            lbl = tk.Label(card, text="?", bg="#221f28", width=THUMB_W, height=THUMB_H,
                           fg="#a09aaa", cursor="hand2")

        lbl.pack(padx=4, pady=(6, 2))
        lbl.bind("<Button-1>", lambda e, p=path: self._select_gallery_back(p))

        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                     text_color="#a09aaa").pack(padx=4, pady=(0, 6))

    def _add_download_button(self, parent) -> None:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(padx=10, pady=(0, 12), anchor="w")

        self._dl_status = ctk.CTkLabel(
            inner, text="Not yet downloaded.",
            font=ctk.CTkFont(size=11), text_color="#a09aaa",
        )
        self._dl_status.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            inner, text="Download", width=110, height=28,
            fg_color="#c04828", hover_color="#a83820",
            command=self._download_mpcfill_bg,
        ).pack(side="left")

    def _download_mpcfill_bg(self) -> None:
        self._dl_status.configure(text="Downloading…")
        threading.Thread(target=self._do_download, daemon=True).start()

    def _do_download(self) -> None:
        path = _download_mpcfill()
        if path:
            self.after(0, self._refresh_gallery)
        else:
            self.after(0, lambda: self._dl_status.configure(
                text="Download failed — check your internet connection."))

    # ── Gallery placeholders + thumbnail loader ───────────────────────────────

    def _add_gallery_placeholder(self, parent, path: str) -> tk.Label:
        card = ctk.CTkFrame(parent, fg_color="#221f28", corner_radius=6)
        card.pack(side="left", padx=6)

        lbl = tk.Label(card, image=self._placeholder_ref, bg="#221f28", cursor="hand2")
        lbl.pack(padx=4, pady=(6, 2))
        lbl.bind("<Button-1>", lambda e, p=path: self._select_gallery_back(p))

        name = os.path.splitext(os.path.basename(path))[0][:18]
        ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=10),
                     text_color="#a09aaa").pack(padx=4, pady=(0, 6))
        return lbl

    def _load_thumbs_bg(self, images: list) -> None:
        for path in images:
            try:
                img = Image.open(path)
                img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                self._thumb_queue.put(("ok", path, img))
            except Exception:
                self._thumb_queue.put(("err", path, None))
        self._thumb_queue.put(("done", None, None))

    def _poll_thumb_queue(self) -> None:
        try:
            for _ in range(8):
                tag, path, img = self._thumb_queue.get_nowait()
                if tag == "done":
                    return
                if tag == "ok" and path in self._thumb_labels:
                    tk_img = ImageTk.PhotoImage(img)
                    self._thumb_refs.append(tk_img)
                    self._thumb_labels[path].configure(image=tk_img)
        except queue.Empty:
            pass
        try:
            self.after(30, self._poll_thumb_queue)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────

    def _select_gallery_back(self, path: str):
        self.result = path
        self.destroy()

    def _open_card_backs_folder(self):
        import subprocess
        abs_path = os.path.abspath(CARD_BACKS_DIR)
        os.makedirs(abs_path, exist_ok=True)
        subprocess.Popen(f'explorer "{abs_path}"')
