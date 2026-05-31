"""
main.py
-------
Point d'entrée d'OtterForge.
Crée les dossiers requis, applique le thème, puis lance l'application.
"""

import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr:
    sys.stderr.reconfigure(encoding="utf-8")


# ------------------------------------------------------------------
# PLAYWRIGHT BROWSERS — bundle detection
# Must happen before any playwright import (triggered by ui.app).
# ------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _bundle_dir = os.path.dirname(sys.executable)
    _browsers_dir = os.path.join(_bundle_dir, "playwright_browsers")
    if os.path.isdir(_browsers_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers_dir


# ------------------------------------------------------------------
# IMPORTS (after env setup)
# ------------------------------------------------------------------
import customtkinter as ctk
from ui.app import OtterForgeApp
from config import CACHE_DIR, OUTPUT_DIR, DECKS_DIR, CARD_BACKS_DIR


def _resource_path(relative: str) -> str:
    """Resolve a bundled asset path — uses sys._MEIPASS in exe, __file__ in dev."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


# ------------------------------------------------------------------
# CRÉATION DES DOSSIERS REQUIS (avant le démarrage de l'app)
# ------------------------------------------------------------------

REQUIRED_FOLDERS = [
    CACHE_DIR,
    os.path.join(CACHE_DIR, "thumbs"),
    os.path.join(CACHE_DIR, "scryfall"),
    os.path.join(CACHE_DIR, "rendered"),
    os.path.join(CACHE_DIR, "temp"),
    OUTPUT_DIR,
    os.path.join(OUTPUT_DIR, "sheets"),
    os.path.join(OUTPUT_DIR, "previews"),
    os.path.join(OUTPUT_DIR, "exports"),
    os.path.join(OUTPUT_DIR, "logs"),
    DECKS_DIR,
    CARD_BACKS_DIR,
]

for folder in REQUIRED_FOLDERS:
    os.makedirs(folder, exist_ok=True)


# ------------------------------------------------------------------
# THÈME OTTERFORGE
# ------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme(_resource_path("assets/otterforge_theme.json"))


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
