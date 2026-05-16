"""
main.py
-------
Point d'entrée de MTG Print Factory.
Crée les dossiers requis, puis lance l'application.
"""

import os
import sys
from ui.app import MTGPrintFactoryApp

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
# LANCEMENT
# ------------------------------------------------------------------

if __name__ == "__main__":
    app = MTGPrintFactoryApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
