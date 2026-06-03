"""
config.py
---------
Constantes globales de OtterForge.
Importez ce fichier dans n'importe quel module pour accéder aux paramètres.

Les valeurs DOSSIERS et REALESRGAN_DIR peuvent être surchargées via
config_user.json (clé "settings") — les modifications s'appliquent au redémarrage.
"""

import json
import os
import sys

# Base directory for all runtime data (cache, decks, output).
# When running as a PyInstaller exe, anchor to the exe's folder so
# data files always end up next to the exe regardless of CWD.
BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)


def _read_user_settings() -> dict:
    try:
        with open(os.path.join(BASE_DIR, "config_user.json"), "r", encoding="utf-8") as f:
            return json.load(f).get("settings", {})
    except Exception:
        return {}


_s = _read_user_settings()


# ------------------------------------------------------------------
# DIMENSIONS DES CARTES (affichage workspace)
# ------------------------------------------------------------------
CARD_WIDTH = 300
CARD_HEIGHT = 420

# ------------------------------------------------------------------
# DIMENSIONS DES THUMBNAILS (sidebar)
# ------------------------------------------------------------------
THUMB_WIDTH = 120
THUMB_HEIGHT = 168

# ------------------------------------------------------------------
# PARAMÈTRES D'IMPRESSION MPC
# ------------------------------------------------------------------
MPC_DPI = 300           # DPI de sortie pour les feuilles d'impression

SHEET_COLS = 3
SHEET_ROWS = 3

# Dimensions d'une carte sur la feuille (pixels à MPC_DPI)
MPC_CARD_W = 745
MPC_CARD_H = 1040

# Marges et espacement entre les cartes (pixels)
MPC_MARGIN = 80
MPC_GAP = 30

# ------------------------------------------------------------------
# DOSSIERS (surchargeables via config_user.json > settings)
# ------------------------------------------------------------------
CACHE_DIR      = _s.get("cache_dir",  os.path.join(BASE_DIR, "cache"))
OUTPUT_DIR     = _s.get("output_dir", os.path.join(BASE_DIR, "output"))
DECKS_DIR      = _s.get("decks_dir",  os.path.join(BASE_DIR, "decks"))
CARD_BACKS_DIR         = os.path.join(BASE_DIR, "card_backs")
OTTERFORGE_DEFAULT_BACK = os.path.join(CARD_BACKS_DIR, "OtterForge_CardBack_1200dpi.png")

# ------------------------------------------------------------------
# UPSCALING (Real-ESRGAN) — surchargeable via config_user.json
# ------------------------------------------------------------------
REALESRGAN_DIR = _s.get(
    "realesrgan_dir",
    r"C:\Users\Samuel\Documents\MTG\Real-ESGRAN",
)
