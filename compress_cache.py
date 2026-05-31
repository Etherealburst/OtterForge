"""
compress_cache.py — Re-compresse les _1200dpi.png existants au niveau PNG max.
Aucune perte de qualité. Gain typique : 30 à 50%.
Usage : python compress_cache.py [--dry-run] [--backup]
"""
import os, sys, argparse, io
from PIL import Image
from config import CACHE_DIR as _BASE_CACHE

CACHE_DIR = os.path.join(_BASE_CACHE, "scryfall")

def format_mb(n): return f"{n/1_048_576:.1f} MB"

def compress_cache(dry_run=False, backup=False):
    if not os.path.isdir(CACHE_DIR):
        print(f"Dossier introuvable : {CACHE_DIR!r}"); sys.exit(1)
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith("_1200dpi.png")]
    if not files:
        print("Aucun fichier _1200dpi.png trouvé."); return
    print(f"{len(files)} fichier(s) trouvé(s)\n")
    total_before = total_after = skipped = 0
    for i, fname in enumerate(sorted(files), 1):
        path = os.path.join(CACHE_DIR, fname)
        sb = os.path.getsize(path); total_before += sb
        try:
            img = Image.open(path)
            buf = io.BytesIO()
            img.save(buf, format="PNG", compress_level=9, optimize=True)
            sa = buf.tell(); total_after += sa
            gain = sb - sa; pct = gain/sb*100 if sb else 0
            print(f"[{i:>3}/{len(files)}] {fname}")
            print(f"         {format_mb(sb)} → {format_mb(sa)}  (gain {pct:.0f}%)")
            if gain <= 0:
                print("         → Déjà optimisé, ignoré."); skipped += 1; continue
            if not dry_run:
                if backup: os.rename(path, path+".bak")
                with open(path, "wb") as f: f.write(buf.getvalue())
                print("         → Mis à jour.")
        except Exception as e:
            print(f"         ⚠ Erreur : {e}"); skipped += 1
    tg = total_before - total_after
    print(f"\n{'='*50}")
    print(f"  Avant  : {format_mb(total_before)}")
    print(f"  Après  : {format_mb(total_after)}")
    if total_before:
        print(f"  Gain   : {format_mb(tg)}  ({tg/total_before*100:.0f}%)")
    if skipped: print(f"  Ignorés : {skipped}")
    if dry_run: print("\n  DRY-RUN — aucun fichier modifié.")
    print('='*50)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--backup", action="store_true")
    a = p.parse_args()
    compress_cache(a.dry_run, a.backup)
