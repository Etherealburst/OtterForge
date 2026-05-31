"""
ui/dialogs/import_source_dialog.py
------------------------------------
Dialog asking whether to import a TXT deck file or a folder of images.
"""

import customtkinter as ctk


class ImportSourceDialog(ctk.CTkToplevel):
    """Result: 'txt' | 'folder' | None (cancelled)."""

    def __init__(self, master):
        super().__init__(master)
        self.result: str | None = None

        self.title("Import")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()
        self.transient(master)

        master.update_idletasks()
        dw, dh = 380, 210
        if master.winfo_viewable():
            px = master.winfo_x()
            py = master.winfo_y()
            pw = master.winfo_width()
            ph = master.winfo_height()
            self.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
        else:
            self.geometry(f"{dw}x{dh}")

        ctk.CTkLabel(
            self, text="What would you like to import?",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(26, 8))

        ctk.CTkLabel(
            self, text="TXT / Moxfield file  or  folder with card images",
            font=ctk.CTkFont(size=11), text_color="#a09aaa",
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 12))

        ctk.CTkButton(
            btn_frame, text="TXT File", width=140, height=40,
            font=ctk.CTkFont(size=12),
            command=self._pick_txt,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="Image Folder", width=140, height=40,
            font=ctk.CTkFont(size=12),
            fg_color="#1a3a4a", hover_color="#1e4a5e",
            command=self._pick_folder,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            self, text="Cancel", width=80, height=28,
            fg_color="#2a2733", hover_color="#3a3548",
            font=ctk.CTkFont(size=11),
            command=self.destroy,
        ).pack(pady=(0, 16))

        self.bind("<Escape>", lambda e: self.destroy())

    def _pick_txt(self):
        self.result = "txt"
        self.destroy()

    def _pick_folder(self):
        self.result = "folder"
        self.destroy()
