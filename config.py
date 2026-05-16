"""
config.py
---------
Constantes globales de OtterForge.
Importez ce fichier dans n'importe quel module pour accéder aux paramètres.
"""

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
# DOSSIERS
# ------------------------------------------------------------------
CACHE_DIR = "cache"
OUTPUT_DIR = "output"
DECKS_DIR = "decks"
CARD_BACKS_DIR = "card_backs"

# ------------------------------------------------------------------
# UPSCALING (Real-ESRGAN)
# ------------------------------------------------------------------
REALESRGAN_DIR = r"C:\Users\Samuel\Documents\MTG\Real-ESGRAN"
