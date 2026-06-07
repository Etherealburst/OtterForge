"""
engine/file_utils.py
--------------------
Utilitaires d'I/O partagés par les modules engine.
"""

import os
import tempfile

from PIL import Image


def safe_save_png(img: Image.Image, final_path: str, **save_kwargs) -> None:
    """Écriture atomique d'un PNG via fichier temporaire.

    Évite les PNG partiels dans le cache si Python crashe ou l'app est fermée
    pendant l'écriture. os.replace() est atomique sur Windows et Linux.
    """
    dir_ = os.path.dirname(final_path) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        os.close(fd)
        img.save(tmp, "PNG", **save_kwargs)
        os.replace(tmp, final_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def safe_write_bytes(data: bytes, final_path: str) -> None:
    """Écriture atomique de données brutes via fichier temporaire."""
    dir_ = os.path.dirname(final_path) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        os.close(fd)
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, final_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
