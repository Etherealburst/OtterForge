"""
engine/batch_importer.py
------------------------
Import de decks depuis un fichier TXT ou export Moxfield.

Formats supportés (une carte par ligne) :
  1 Lightning Bolt (M11) 149             # Arena / Moxfield précis (set+CN exact)
  1 Lightning Bolt                       # Moxfield basique (fuzzy search)
  Lightning Bolt x4                      # TXT custom (nom + count en fin)
  Lightning Bolt s:lea x4               # TXT custom (nom + set)
  Rip Apart s:sld cn:1917 x4            # TXT custom (nom + set + CN)
  s:sld cn:1917 x4                      # TXT custom (set + CN sans nom)

Télécharge les images via Scryfall et upscale à 1200 DPI via Real-ESRGAN.
Génère un rapport des cartes ignorées en fin d'import.
"""

import os
import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from engine.scryfall_downloader import ScryfallDownloader
from engine.upscaler import ImageUpscaler


class BatchImporter:
    """
    Importe un deck complet depuis un fichier TXT ou export Moxfield.
    Détecte automatiquement le format de chaque ligne.
    """

    # Format Arena/Moxfield précis : "1 Lightning Bolt (M11) 149"
    _MOXFIELD_FULL_RE = re.compile(
        r'^(\d+)\s+(.+?)\s+\(([A-Za-z0-9]+)\)\s+(\S+)$'
    )
    # Format Moxfield basique : "1 Lightning Bolt"
    _MOXFIELD_BASIC_RE = re.compile(
        r'^(\d+)\s+(.+)$'
    )

    def __init__(self):
        self.downloader = ScryfallDownloader()
        self.upscaler = ImageUpscaler()

    def parse_line(self, line: str) -> dict | None:
        """
        Parse une ligne de deck.

        Retourne un dict :
          {
            "name": str | None,
            "set": str | None,
            "collector_number": str | None,
            "count": int,
            "raw": str,           # ligne originale pour le rapport d'erreur
          }
        Retourne None si la ligne est vide ou un commentaire.
        """
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        # Strip marqueurs spéciaux Moxfield : *F* (foil), *E* (etched), ★, etc.
        line = re.sub(r'(\s+\*\w+\*|\s+★)+$', '', line).strip()

        # --- Format Arena/Moxfield précis : "1 Lightning Bolt (M11) 149" ---
        m = self._MOXFIELD_FULL_RE.match(line)
        if m:
            # Normalise le séparateur double-face " / " → " // " pour Scryfall
            # urllib.parse.unquote : décode les noms encodés URL (ex : Continue%3F → Continue?)
            name = urllib.parse.unquote(m.group(2).strip().replace(' / ', ' // '))
            return {
                "name": name,
                "set": m.group(3).lower(),
                "collector_number": m.group(4),
                "count": int(m.group(1)),
                "raw": line,
            }

        # --- Format Moxfield basique : "1 Lightning Bolt" ---
        # Ignoré si la partie nom contient s:/cn: — le chemin TXT personnalisé gère ça mieux
        m = self._MOXFIELD_BASIC_RE.match(line)
        if m and not re.search(r'\b(s:|cn:)', m.group(2), re.IGNORECASE):
            name = urllib.parse.unquote(m.group(2).strip().replace(' / ', ' // '))
            return {
                "name": name,
                "set": None,
                "collector_number": None,
                "count": int(m.group(1)),
                "raw": line,
            }

        # --- Format TXT personnalisé ---
        result = {
            "name": None,
            "set": None,
            "collector_number": None,
            "count": 1,
            "raw": line,
        }

        # Extraction du count : "x4" en fin de ligne, OU chiffre en début ("1 Bolt s:m10 cn:149")
        count_match = re.search(r"\s+x\s*(\d+)\s*$", line, re.IGNORECASE)
        if count_match:
            result["count"] = int(count_match.group(1))
            line = line[:count_match.start()].strip()
        else:
            leading = re.match(r'^(\d+)\s+', line)
            if leading:
                result["count"] = int(leading.group(1))
                line = line[leading.end():]

        # Extraction de s:XXX
        set_match = re.search(r"\bs:(\S+)", line, re.IGNORECASE)
        if set_match:
            result["set"] = set_match.group(1).lower()
            line = line[:set_match.start()] + line[set_match.end():]

        # Extraction de cn:XXX
        cn_match = re.search(r"\bcn:(\S+)", line, re.IGNORECASE)
        if cn_match:
            result["collector_number"] = cn_match.group(1)
            line = line[:cn_match.start()] + line[cn_match.end():]

        name = urllib.parse.unquote(line.strip())
        if name:
            result["name"] = name

        if not result["name"] and not (result["set"] and result["collector_number"]):
            return None

        return result

    def import_txt(self, path: str, progress_callback=None) -> tuple[list[dict], list[dict]]:
        """
        Importe toutes les cartes depuis un fichier TXT.

        Phase 1 (parallèle, max 5 workers) : appels Scryfall + téléchargements images.
        Phase 2 (séquentielle) : upscaling Real-ESRGAN (GPU bound).

        Retourne un tuple :
          - cards   : liste de dicts {"name", "image_path", "count"} — cartes importées
          - skipped : liste de dicts {"raw", "reason"} — cartes ignorées avec raison
        """
        upscaler_available = self.upscaler.is_available()
        if not upscaler_available:
            print("[BatchImporter] Real-ESRGAN introuvable — images utilisées à 300 DPI natif Scryfall")

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        parsed_lines = [p for p in (self.parse_line(l) for l in lines) if p]
        total = len(parsed_lines)

        # ── Phase 1 : téléchargements en parallèle ────────────────────────
        _lock = threading.Lock()
        _counter = [0]
        download_results: dict = {}

        def _download_one(idx_parsed):
            idx, parsed = idx_parsed
            raw = parsed["raw"]
            card_label = parsed.get("name") or f"{parsed.get('set')} {parsed.get('collector_number')}"

            card_json = None
            if parsed["set"] and parsed["collector_number"]:
                card_json = self.downloader.get_card_by_set(parsed["set"], parsed["collector_number"])
                if not card_json and parsed["name"]:
                    card_json = self.downloader.get_card(parsed["name"])
            elif parsed["name"]:
                card_json = self.downloader.get_card(parsed["name"])

            with _lock:
                _counter[0] += 1
                if progress_callback:
                    progress_callback(_counter[0], total, card_label)

            if not card_json:
                return idx, {"skip": raw, "reason": "Carte introuvable sur Scryfall"}

            face_paths = self.downloader.download_all_face_images(card_json)
            if not face_paths:
                return idx, {"skip": raw, "reason": "Image introuvable sur Scryfall"}

            return idx, (card_json, face_paths, parsed)

        with ThreadPoolExecutor(max_workers=5) as pool:
            for idx, result in pool.map(_download_one, enumerate(parsed_lines)):
                download_results[idx] = result

        # ── Phase 2 : upscaling (parallèle max 2 workers) + construction ────
        # Collecter les tâches d'upscaling en filtrant les cache hits
        upscale_tasks = []          # [(idx, face_index, raw_path, fname)]
        final_face_paths: dict = {} # (idx, face_index) → chemin final

        for idx in range(len(parsed_lines)):
            result = download_results.get(idx)
            if result is None or (isinstance(result, dict) and "skip" in result):
                continue
            card_json, face_paths, parsed = result
            faces = card_json.get("card_faces", [])
            for face_index, raw_path in enumerate(face_paths):
                out_1200 = raw_path.replace(".png", "_1200dpi.png")
                if upscaler_available:
                    if os.path.exists(out_1200):
                        print(f"[BatchImporter] Cache hit 1200dpi : {os.path.basename(out_1200)}")
                        final_face_paths[(idx, face_index)] = out_1200
                    else:
                        fname = (faces[face_index]["name"] if faces and face_index < len(faces)
                                 else card_json["name"])
                        upscale_tasks.append((idx, face_index, raw_path, fname))
                else:
                    final_face_paths[(idx, face_index)] = self._apply_300dpi_bleed(raw_path)

        # Upscaling parallèle (max 2 pour ne pas saturer le GPU)
        def _upscale_one(task):
            idx, face_index, raw_path, fname = task
            out = raw_path.replace(".png", "_1200dpi.png")
            try:
                return idx, face_index, self.upscaler.upscale_to_1200dpi(raw_path, out)
            except Exception as e:
                print(f"[BatchImporter] Upscaling échoué pour {fname!r} : {e} — fallback 300 DPI")
                return idx, face_index, self._apply_300dpi_bleed(raw_path)

        if upscale_tasks:
            with ThreadPoolExecutor(max_workers=2) as pool:
                for idx, face_index, fp in pool.map(_upscale_one, upscale_tasks):
                    final_face_paths[(idx, face_index)] = fp

        # Construction des cartes dans l'ordre original
        cards = []
        skipped = []
        for idx in range(len(parsed_lines)):
            result = download_results.get(idx)
            if result is None:
                continue
            if isinstance(result, dict) and "skip" in result:
                print(f"[BatchImporter] Ignoré ({result['reason']}) : {result['skip']!r}")
                skipped.append({"raw": result["skip"], "reason": result["reason"]})
                continue

            card_json, face_paths, parsed = result
            faces = card_json.get("card_faces", [])
            final_paths = [final_face_paths[(idx, fi)] for fi in range(len(face_paths))
                           if (idx, fi) in final_face_paths]
            if not final_paths:
                continue

            face_name = faces[0]["name"] if faces else card_json["name"]
            card_dict = {
                "name": face_name,
                "image_path": final_paths[0],
                "count": parsed["count"],
            }
            if len(final_paths) > 1:
                card_dict["back_image_path"] = final_paths[1]
            cards.append(card_dict)
            print(f"[BatchImporter] Importé : {card_json['name']!r} x{parsed['count']} ({len(face_paths)} face(s))")

        print(f"\n[BatchImporter] ✅ {len(cards)} carte(s) importée(s)")
        if skipped:
            print(f"[BatchImporter] ⚠️  {len(skipped)} carte(s) ignorée(s) :")
            for s in skipped:
                print(f"  • {s['raw']}  →  {s['reason']}")

        return cards, skipped

    def _apply_300dpi_bleed(self, raw_path: str) -> str:
        """Adapte l'image native Scryfall au format MPC 300 DPI (822×1122) avec bleed.
        Retourne le chemin de l'image adaptée (_mpc300.png).
        """
        out_path = raw_path.replace(".png", "_mpc300.png")
        try:
            return self.upscaler.fit_native_to_mpc_300(raw_path, out_path)
        except Exception as e:
            print(f"[BatchImporter] Bleed 300 DPI échoué : {e} — image native utilisée")
            return raw_path
