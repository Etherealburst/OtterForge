"""
engine/scryfall_downloader.py
-----------------------------
Téléchargement de cartes et d'images via l'API Scryfall.

Endpoints supportés :
  - /cards/named?fuzzy=   : recherche par nom (fuzzy)
  - /cards/:set/:cn       : recherche par set + numéro de collector (exact)
"""

import os
import json
import time
import requests

from config import CACHE_DIR as _BASE_CACHE
from engine.file_utils import safe_write_bytes


SCRYFALL_API_NAMED = "https://api.scryfall.com/cards/named"
SCRYFALL_API_SET   = "https://api.scryfall.com/cards/{set_code}/{collector_number}"

_META_CACHE_FOLDER = os.path.join(_BASE_CACHE, "scryfall")

_HEADERS = {"User-Agent": "OtterForge/2.0 (personal proxy tool)"}


def _get_with_retry(url: str, max_attempts: int = 3, timeout: int = 30, **kwargs) -> requests.Response:
    """GET avec retry linéaire (1 s, 2 s, 3 s) sur erreurs réseau transitoires.

    Retry : ConnectionError, Timeout, 5xx serveur.
    Pas de retry : 4xx client (erreur attendue, ex. carte introuvable).
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(attempt + 1)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code < 500:
                raise  # 4xx = erreur client → pas de retry
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(attempt + 1)
    raise last_exc


class ScryfallDownloader:
    """
    Interface avec l'API Scryfall.
    Supporte la recherche fuzzy par nom et la recherche exacte par set/collector.
    """

    def get_card(self, name: str, set_code: str | None = None) -> dict | None:
        """
        Recherche une carte par nom (fuzzy), avec set optionnel.
        Retourne le JSON Scryfall, ou None si introuvable.
        Le résultat est mis en cache par set+CN pour accélérer les appels futurs exacts.
        """
        params: dict = {"fuzzy": name}
        if set_code:
            params["set"] = set_code.lower()
        try:
            response = requests.get(
                SCRYFALL_API_NAMED,
                params=params,
                headers=_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            card_json = response.json()
        except requests.exceptions.HTTPError as e:
            print(f"[ScryfallDownloader] Carte introuvable : {name!r} — {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[ScryfallDownloader] Erreur réseau : {e}")
            return None

        set_code = card_json.get("set", "")
        collector = card_json.get("collector_number", "")
        if set_code and collector:
            meta_path = os.path.join(
                _META_CACHE_FOLDER,
                f"_meta_{set_code.lower()}_{collector}.json",
            )
            if not os.path.exists(meta_path):
                try:
                    os.makedirs(_META_CACHE_FOLDER, exist_ok=True)
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(card_json, f, ensure_ascii=False)
                except Exception:
                    pass

        return card_json

    def get_card_by_set(self, set_code: str, collector_number: str) -> dict | None:
        """
        Recherche une carte par code de set et numéro de collector.
        Ex : get_card_by_set("sld", "1917")
        Retourne le JSON Scryfall, ou None si introuvable.
        Résultat mis en cache local (_meta_{set}_{cn}.json) pour éviter les appels réseau répétés.
        """
        meta_path = os.path.join(
            _META_CACHE_FOLDER,
            f"_meta_{set_code.lower()}_{collector_number}.json",
        )
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        url = SCRYFALL_API_SET.format(
            set_code=set_code.lower(),
            collector_number=collector_number,
        )
        try:
            response = requests.get(url, headers=_HEADERS, timeout=10)
            response.raise_for_status()
            card_json = response.json()
        except requests.exceptions.HTTPError as e:
            print(f"[ScryfallDownloader] Carte introuvable : s:{set_code} cn:{collector_number} — {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[ScryfallDownloader] Erreur réseau : {e}")
            return None

        try:
            os.makedirs(_META_CACHE_FOLDER, exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(card_json, f, ensure_ascii=False)
        except Exception:
            pass

        return card_json

    def download_image(self, card_json: dict, folder: str | None = None) -> str | None:
        """
        Télécharge l'image PNG de la face principale d'une carte.
        Retourne le chemin local, ou None en cas d'erreur.
        Utilise le cache : si le fichier existe déjà, ne re-télécharge pas.
        """
        paths = self.download_all_face_images(card_json, folder)
        return paths[0] if paths else None

    def download_all_face_images(self, card_json: dict, folder: str | None = None) -> list[str]:
        """
        Télécharge toutes les faces d'une carte.
        Retourne une liste de chemins :
          - 1 élément pour une carte simple-face
          - 2 éléments pour une carte double-face (transform, modal_dfc…)
        """
        if folder is None:
            folder = os.path.join(_BASE_CACHE, "scryfall")
        os.makedirs(folder, exist_ok=True)

        set_code  = card_json.get("set", "")
        collector = card_json.get("collector_number", "")

        def _download_face(image_url: str, face_name: str, suffix: str = "") -> str | None:
            safe_name = face_name
            for ch in r'\/:*?"<>|':
                safe_name = safe_name.replace(ch, "-")
            if set_code and collector:
                filename = f"{safe_name}_{set_code}_{collector}{suffix}.png"
            else:
                filename = f"{safe_name}{suffix}.png"
            path = os.path.join(folder, filename)
            if os.path.exists(path):
                return path
            try:
                response = _get_with_retry(image_url, timeout=30, headers={"User-Agent": "OtterForge/2.0"})
                with open(path, "wb") as fh:
                    fh.write(response.content)
                return path
            except (requests.exceptions.RequestException, OSError) as e:
                print(f"[ScryfallDownloader] Erreur téléchargement image : {e}")
                return None

        # Carte simple-face
        if "image_uris" in card_json:
            path = _download_face(
                card_json["image_uris"]["png"],
                card_json["name"],
            )
            return [path] if path else []

        # Carte double-face
        if "card_faces" in card_json:
            paths = []
            for i, face in enumerate(card_json["card_faces"]):
                if "image_uris" not in face:
                    continue
                path = _download_face(
                    face["image_uris"]["png"],
                    face["name"],
                    suffix=f"_face{i}",
                )
                if path:
                    paths.append(path)
            return paths

        print(f"[ScryfallDownloader] Pas d'image trouvée pour : {card_json.get('name')}")
        return []
