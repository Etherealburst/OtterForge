"""
ui/card_back_picker.py
----------------------
Dialog pour choisir l'image d'endos des cartes.

Deux modes :
  - "Upload" : sélectionne un fichier image depuis l'ordinateur
  - "MPCFill" : choisit parmi les images dans card_backs/
"""

import os
import queue
import threading
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk

from config import CARD_BACKS_DIR

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
THUMB_W, THUMB_H = 120, 168


class CardBackPickerDialog(ctk.CTkToplevel):
    """
    Fenêtre modale de sélection d'endos.
    Résultat dans self.result (str path ou None si annulé).
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("Choisir un endos")
        self.geometry("680x480")
        self.resizable(True, True)
        self.grab_set()
        self.focus_set()

        self.result: str | None = None
        self._thumb_refs: list = []
        self._thumb_queue: queue.Queue = queue.Queue()
        self._thumb_labels: dict = {}   # path → tk.Label
        self._placeholder_ref = None    # shared placeholder image

        os.makedirs(CARD_BACKS_DIR, exist_ok=True)
        self._build()

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------

    def _build(self):
        tabview = ctk.CTkTabview(self)
        tabview.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        tab_upload = tabview.add("Depuis un fichier")
        tab_gallery = tabview.add("Préréglages MPCFill")

        self._build_upload_tab(tab_upload)
        self._build_gallery_tab(tab_gallery)

        ctk.CTkButton(self, text="Annuler", fg_color="#581e10", hover_color="#3a1a10",
                      command=self.destroy).pack(pady=(0, 10))

    # ------ UPLOAD TAB ------

    def _build_upload_tab(self, parent):
        ctk.CTkLabel(
            parent,
            text="Choose any image from your computer to use as card back.",
            font=ctk.CTkFont(size=12),
            text_color="#5a5060",
        ).pack(pady=(24, 16))

        self._upload_preview_label = ctk.CTkLabel(parent, text="")
        self._upload_preview_label.pack(pady=(0, 12))

        self._upload_path_var = tk.StringVar(value="No file selected")
        ctk.CTkLabel(parent, textvariable=self._upload_path_var,
                     text_color="#5a5060", font=ctk.CTkFont(size=11)).pack()

        ctk.CTkButton(parent, text="Browse…", command=self._browse_file).pack(pady=12)
        ctk.CTkButton(parent, text="Use this image", fg_color="#c04828",
                      hover_color="#a83820", text_color="#f0ece4",
                      command=self._confirm_upload).pack()

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
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            header,
            text=f"Images in card_backs/ folder ({CARD_BACKS_DIR})",
            font=ctk.CTkFont(size=11),
            text_color="#5a5060",
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

        # Shared grey placeholder so all card slots appear instantly
        ph = Image.new("RGB", (THUMB_W, THUMB_H), (43, 43, 43))
        self._placeholder_ref = ImageTk.PhotoImage(ph)

        self._refresh_gallery()

    def _refresh_gallery(self):
        for widget in self._gallery_frame.winfo_children():
            widget.destroy()
        self._thumb_refs.clear()
        self._thumb_labels.clear()

        images = sorted([
            os.path.join(CARD_BACKS_DIR, f)
            for f in os.listdir(CARD_BACKS_DIR)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        ])

        if not images:
            ctk.CTkLabel(
                self._gallery_frame,
                text=(
                    "No card backs found.\n\n"
                    "Add .png / .jpg images to the card_backs/ folder,\n"
                    "then click Refresh."
                ),
                text_color="#5a5060",
                font=ctk.CTkFont(size=12),
            ).pack(pady=40)
            return

        # Build all card frames with grey placeholders — instant, no I/O
        cols = 4
        row_frame = None
        for idx, path in enumerate(images):
            if idx % cols == 0:
                row_frame = ctk.CTkFrame(self._gallery_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=4)
            lbl = self._add_gallery_placeholder(row_frame, path)
            self._thumb_labels[path] = lbl

        # Load real thumbnails in a background thread
        self._thumb_queue = queue.Queue()
        threading.Thread(
            target=self._load_thumbs_bg,
            args=(list(images),),
            daemon=True,
        ).start()
        self.after(30, self._poll_thumb_queue)

    def _add_gallery_placeholder(self, parent, path: str) -> tk.Label:
        card = ctk.CTkFrame(parent, fg_color="#221f28", corner_radius=6)
        card.pack(side="left", padx=6)

        lbl = tk.Label(card, image=self._placeholder_ref, bg="#221f28", cursor="hand2")
        lbl.pack(padx=4, pady=(6, 2))
        lbl.bind("<Button-1>", lambda e, p=path: self._select_gallery_back(p))

        name = os.path.splitext(os.path.basename(path))[0][:18]
        ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=10),
                     text_color="#5a5060").pack(padx=4, pady=(0, 6))

        return lbl

    # ── Background thumbnail loader ───────────────────────────────────────────

    def _load_thumbs_bg(self, images: list) -> None:
        """Background thread: decode + resize each image, push PIL Image to queue."""
        for path in images:
            try:
                img = Image.open(path)
                img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                self._thumb_queue.put(("ok", path, img))
            except Exception:
                self._thumb_queue.put(("err", path, None))
        self._thumb_queue.put(("done", None, None))

    def _poll_thumb_queue(self) -> None:
        """Main thread: drain queue, convert PIL Images to PhotoImages, update labels."""
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
            pass  # dialog was destroyed

    # ─────────────────────────────────────────────────────────────────────────

    def _select_gallery_back(self, path: str):
        self.result = path
        self.destroy()

    def _open_card_backs_folder(self):
        import subprocess
        abs_path = os.path.abspath(CARD_BACKS_DIR)
        os.makedirs(abs_path, exist_ok=True)
        subprocess.Popen(f'explorer "{abs_path}"')
