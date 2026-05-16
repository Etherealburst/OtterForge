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

import re
import urllib.parse
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

        Retourne un tuple :
          - cards   : liste de dicts {"name", "image_path", "count"} — cartes importées
          - skipped : liste de dicts {"raw", "reason"} — cartes ignorées avec raison

        progress_callback(msg) : appelé à chaque carte pour mettre à jour l'UI.
        Si Real-ESRGAN est disponible, upscale chaque image à 1200 DPI.
        Sinon, utilise l'image Scryfall PNG native (300 DPI).
        """
        cards = []
        skipped = []
        upscaler_available = self.upscaler.is_available()

        if not upscaler_available:
            print("[BatchImporter] Real-ESRGAN introuvable — images utilisées à 300 DPI natif Scryfall")

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        parsed_lines = [p for p in (self.parse_line(l) for l in lines) if p]
        total = len(parsed_lines)

        for i, parsed in enumerate(parsed_lines, start=1):
            raw = parsed["raw"]
            card_label = parsed.get("name") or f"{parsed.get('set')} {parsed.get('collector_number')}"
            if progress_callback:
                progress_callback(i, total, card_label)

            # --- Recherche Scryfall ---
            card_json = None

            # Priorité : set + collector number (recherche exacte)
            if parsed["set"] and parsed["collector_number"]:
                card_json = self.downloader.get_card_by_set(
                    parsed["set"], parsed["collector_number"]
                )
                if not card_json and parsed["name"]:
                    # Fallback : essai par nom si set/cn échoue
                    print(f"[BatchImporter] set/cn introuvable, essai par nom : {parsed['name']!r}")
                    card_json = self.downloader.get_card(parsed["name"])

            # Recherche par nom seul
            elif parsed["name"]:
                card_json = self.downloader.get_card(parsed["name"])

            if not card_json:
                reason = "Carte introuvable sur Scryfall"
                print(f"[BatchImporter] Ignoré ({reason}) : {raw!r}")
                skipped.append({"raw": raw, "reason": reason})
                continue

            # --- Téléchargement toutes les faces ---
            face_paths = self.downloader.download_all_face_images(card_json)
            if not face_paths:
                reason = "Image introuvable sur Scryfall"
                print(f"[BatchImporter] Ignoré ({reason}) : {raw!r}")
                skipped.append({"raw": raw, "reason": reason})
                continue

            faces = card_json.get("card_faces", [])

            # --- Upscaling de toutes les faces ---
            final_paths = []
            for face_index, raw_path in enumerate(face_paths):
                fname = (faces[face_index]["name"] if faces and face_index < len(faces) else card_json["name"])
                if upscaler_available:
                    try:
                        fp = self.upscaler.upscale_to_1200dpi(
                            raw_path,
                            raw_path.replace(".png", "_1200dpi.png"),
                        )
                    except Exception as e:
                        print(f"[BatchImporter] Upscaling échoué pour {fname!r} : {e} — fallback 300 DPI")
                        fp = self._apply_300dpi_bleed(raw_path)
                else:
                    fp = self._apply_300dpi_bleed(raw_path)
                final_paths.append(fp)

            # --- Ajout au deck (face0 seulement ; face1 = back_image_path pour les DFC) ---
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

        # --- Rapport final ---
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
