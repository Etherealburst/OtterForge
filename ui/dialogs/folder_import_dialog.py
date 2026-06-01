"""
ui/dialogs/folder_import_dialog.py
------------------------------------
Dialog for importing card images from a local folder.
Asks whether to upload images as-is or upscale with Real-ESRGAN.
"""

import os
import re
import customtkinter as ctk


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def find_images_in_folder(folder: str) -> list[str]:
    """Return sorted list of image file paths found in folder (non-recursive)."""
    result = []
    try:
        for name in sorted(os.listdir(folder)):
            if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS:
                result.append(os.path.join(folder, name))
    except Exception:
        pass
    return result


def normalize_card_name(stem: str) -> str:
    """Extract base card name from a filename stem by stripping common version suffixes.

    Examples:
      "Lightning Bolt (2)"  → "Lightning Bolt"
      "Snapcaster Mage_v2"  → "Snapcaster Mage"
      "Force of Will_alt"   → "Force of Will"
      "Bolt_2"              → "Bolt"
    """
    name = stem
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)           # " (2)"
    name = re.sub(r'[\s_]v\d+\s*$', '', name, flags=re.IGNORECASE)   # "_v2", " v2"
    name = re.sub(r'[\s_]alt\d*\s*$', '', name, flags=re.IGNORECASE) # "_alt", "_alt2"
    name = re.sub(r'[\s_]art\d*\s*$', '', name, flags=re.IGNORECASE) # "_art", "_art2"
    name = re.sub(r'_\d+\s*$', '', name)                 # "_2", "_10"
    return name.strip()


def group_images_by_card_name(image_paths: list[str]) -> dict[str, list[str]]:
    """Group image paths by normalized card name, preserving insertion order.

    Returns {normalized_name: [path, ...]}. Groups with >1 path are conflicts.
    """
    groups: dict[str, list[str]] = {}
    for path in image_paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        key = normalize_card_name(stem)
        groups.setdefault(key, []).append(path)
    return groups


class FolderImportDialog(ctk.CTkToplevel):
    """Result: 'upload' | 'upscale' | None (cancelled)."""

    def __init__(self, master, folder: str, image_count: int, upscaler_available: bool):
        super().__init__(master)
        self.result: str | None = None

        self.title("Import Image Folder")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()
        self.transient(master)

        master.update_idletasks()
        dw, dh = 420, 300
        if master.winfo_viewable():
            px = master.winfo_x()
            py = master.winfo_y()
            pw = master.winfo_width()
            ph = master.winfo_height()
            self.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
        else:
            self.geometry(f"{dw}x{dh}")

        ctk.CTkLabel(
            self, text="Import images from folder",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(24, 6))

        fname = os.path.basename(folder) or folder
        ctk.CTkLabel(
            self, text=f"Folder: {fname}",
            font=ctk.CTkFont(size=11), text_color="#a09aaa",
        ).pack()

        ctk.CTkLabel(
            self, text=f"{image_count} image(s) found",
            font=ctk.CTkFont(size=12),
        ).pack(pady=(6, 16))

        ctk.CTkLabel(
            self, text="How would you like to process them?",
            font=ctk.CTkFont(size=11), text_color="#c4bfb8",
        ).pack(pady=(0, 12))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Upload as-is", width=145, height=40,
            font=ctk.CTkFont(size=12),
            command=self._do_upload,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="Upscale (ESRGAN)",
            width=145, height=40,
            font=ctk.CTkFont(size=12),
            state="normal" if upscaler_available else "disabled",
            fg_color="#1e4a1a" if upscaler_available else "#252228",
            hover_color="#2a6a22" if upscaler_available else "#252228",
            text_color="#d0f0d0" if upscaler_available else "#5a5568",
            command=self._do_upscale,
        ).pack(side="left", padx=8)

        if not upscaler_available:
            ctk.CTkLabel(
                self, text="Real-ESRGAN not available — configure path in Settings",
                font=ctk.CTkFont(size=10), text_color="#a06050",
            ).pack(pady=(0, 4))
        else:
            ctk.CTkLabel(
                self, text="Upscale will run Real-ESRGAN ×4 on each image (slow, best quality)",
                font=ctk.CTkFont(size=10), text_color="#a09aaa",
            ).pack(pady=(0, 4))

        ctk.CTkButton(
            self, text="Cancel", width=80, height=28,
            fg_color="#2a2733", hover_color="#3a3548",
            font=ctk.CTkFont(size=11),
            command=self.destroy,
        ).pack(pady=(4, 16))

        self.bind("<Escape>", lambda e: self.destroy())

    def _do_upload(self):
        self.result = "upload"
        self.destroy()

    def _do_upscale(self):
        self.result = "upscale"
        self.destroy()
