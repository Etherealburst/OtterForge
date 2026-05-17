"""
main.py
-------
Point d'entrée d'OtterForge.
Crée les dossiers requis, applique le thème, puis lance l'application.
"""

import os
import sys
import customtkinter as ctk
from ui.app import OtterForgeApp

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


# ------------------------------------------------------------------
# CRÉATION DES DOSSIERS REQUIS (avant le démarrage de l'app)
# ------------------------------------------------------------------

REQUIRED_FOLDERS = [
    "cache",
    "cache/thumbs",
    "cache/scryfall",
    "cache/rendered",
    "cache/temp",
    "output",
    "output/sheets",
    "output/previews",
    "output/exports",
    "output/logs",
    "decks",
]

for folder in REQUIRED_FOLDERS:
    os.makedirs(folder, exist_ok=True)


# ------------------------------------------------------------------
# THÈME OTTERFORGE
# ------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("assets/otterforge_theme.json")


# ------------------------------------------------------------------
# LANCEMENT
# ------------------------------------------------------------------

if __name__ == "__main__":
    # Déclare un AppUserModelID unique pour que Windows affiche l'icône
    # OtterForge dans la barre des tâches (sinon Python montre son propre icône).
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "OtterApps.OtterForge.2.0"
        )

    app = OtterForgeApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
