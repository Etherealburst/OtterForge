#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/download_card_backs.py
-------------------------------
Télécharge les images d'endos depuis l'API mpcfill.com
et les enregistre dans le dossier card_backs/ du projet.

Usage :  python scripts/download_card_backs.py
"""

import os
import re
import sys
import time
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from config import CARD_BACKS_DIR
    DEST = Path(CARD_BACKS_DIR)
except ImportError:
    DEST = ROOT / "card_backs"

API_BASE = "https://mpcfill.com"
GDRIVE_DL = "https://drive.google.com/uc?export=download&id={id}"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": API_BASE,
    "Referer": API_BASE + "/",
}


# ── Session + CSRF ────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_BROWSER_HEADERS)
    return s


def _get_csrf(session: requests.Session) -> str:
    try:
        session.get(API_BASE + "/", timeout=15)
        return session.cookies.get("csrftoken", "")
    except Exception as e:
        print(f"  Avertissement : impossible d'obtenir le jeton CSRF ({e})")
        return ""


# ── API mpcfill ───────────────────────────────────────────────────────────────

def _fetch_card_backs(session: requests.Session, csrf: str) -> list[dict]:
    url = API_BASE + "/2/cardbacks/"
    hdrs = {"Content-Type": "application/json"}
    if csrf:
        hdrs["X-CSRFToken"] = csrf

    body = {
        "searchSettings": {
            "sources": {},
            "sourceSettings": {"sources": []},
            "filterCardLanguages": [],
            "filterEnabled": False,
            "searchTypeSettings": {
                "filterCardbacks": False,
                "filterCards": False,
                "filterTokens": False,
                "fuzzySearch": False,
            },
            "filterSettings": {
                "excludesTags": [],
                "includesTags": [],
                "languages": [],
                "maximumDPI": 2400,
                "minimumDPI": 0,
                "maximumSize": 0,
                "minimumSize": 0,
            },
        }
    }

    try:
        resp = session.post(url, json=body, headers=hdrs, timeout=30)
    except Exception as e:
        print(f"  Requête échouée : {e}")
        return []

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code} — {resp.text[:200]}")
        return []

    try:
        data = resp.json()
    except Exception:
        print("  Réponse non-JSON.")
        return []

    # Response may be a list of identifier strings OR a list of dicts
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("cardbacks", "results", "cards", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]

    print(f"  Structure inattendue : {str(data)[:200]}")
    return []


def _gdrive_filename(file_id: str) -> str:
    """Get the original filename from a Google Drive file ID via a clean HEAD request."""
    try:
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        s = requests.Session()
        s.headers["User-Agent"] = _BROWSER_HEADERS["User-Agent"]
        resp = s.get(url, stream=True, timeout=12, allow_redirects=True)
        resp.close()
        cd = resp.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd)
        if m:
            return m.group(1).strip().strip('"\'')
    except Exception:
        pass
    return ""


# ── Téléchargement image ──────────────────────────────────────────────────────

def _dl_gdrive(file_id: str, dest: Path, session: requests.Session) -> Path | None:
    """Download from Google Drive. Returns actual dest path (ext may change), or None on failure."""
    # Use a clean session without mpcfill.com Origin/Referer — Drive returns 403 otherwise
    dl_session = requests.Session()
    dl_session.headers["User-Agent"] = _BROWSER_HEADERS["User-Agent"]

    url = GDRIVE_DL.format(id=file_id)
    try:
        resp = dl_session.get(url, stream=True, timeout=40, allow_redirects=True)

        # Confirmation pour les gros fichiers (page HTML avec token)
        ct = resp.headers.get("Content-Type", "")
        if "html" in ct:
            m = re.search(r'confirm=([A-Za-z0-9_-]+)', resp.text)
            if not m:
                return None
            resp = dl_session.get(
                url + f"&confirm={m.group(1)}",
                stream=True, timeout=60,
            )
            ct = resp.headers.get("Content-Type", "")

        if resp.status_code != 200:
            return None

        # Detect real extension from Content-Type
        ct_ext = {"image/png": ".png", "image/jpeg": ".jpg",
                  "image/webp": ".webp", "image/gif": ".gif"}.get(ct.split(";")[0].strip())
        if ct_ext and dest.suffix != ct_ext:
            dest = dest.with_suffix(ct_ext)

        if dest.exists():
            return dest  # already there with correct ext

        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(65536):
                fh.write(chunk)

        if dest.stat().st_size < 8_000:
            dest.unlink()
            return None
        return dest

    except Exception as e:
        print(f" ({e})", end="")
        if dest.exists():
            dest.unlink()
        return None


def _dl_url(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        resp = session.get(url, stream=True, timeout=30)
        if resp.status_code != 200:
            return False
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(65536):
                fh.write(chunk)
        if dest.stat().st_size < 8_000:
            dest.unlink()
            return False
        return True
    except Exception as e:
        if dest.exists():
            dest.unlink()
        return False


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "card_back"


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dest_dir: Path | None = None, limit: int = 0) -> tuple[int, int, int]:
    """
    Télécharge les endos depuis mpcfill.com.
    limit=0 → tous ; limit=N → les N premiers.
    Retourne (ok, skipped, failed).
    """
    out = dest_dir or DEST
    out.mkdir(parents=True, exist_ok=True)
    print(f"Dossier cible : {out.resolve()}")

    session = _make_session()

    print("Connexion à mpcfill.com…")
    csrf = _get_csrf(session)

    print("Récupération de la liste des endos…")
    backs = _fetch_card_backs(session, csrf)

    if not backs:
        print(
            "\nImpossible de récupérer la liste depuis mpcfill.com.\n"
            "Ajoutez manuellement des images dans :\n"
            f"  {out.resolve()}"
        )
        return 0, 0, 0

    if limit:
        backs = backs[:limit]
    print(f"  {len(backs)} endos à télécharger.\n")

    ok = failed = skipped = 0

    for idx, back in enumerate(backs):
        # API returns either a plain identifier string or a dict
        if isinstance(back, str):
            identifier = back
            # Get real filename from Google Drive Content-Disposition
            real_name = _gdrive_filename(identifier)
            if real_name:
                stem = os.path.splitext(real_name)[0]
                ext  = os.path.splitext(real_name)[1] or ".jpg"
                name = stem
            else:
                name = f"back_{idx+1:03d}"
                ext  = ".jpg"
            thumb_url = ""
        else:
            name       = back.get("name") or back.get("cardName") or f"back_{idx+1:03d}"
            identifier = back.get("identifier") or back.get("id") or back.get("drive_id") or ""
            ext        = "." + (back.get("extension") or "jpg").lstrip(".")
            thumb_url  = back.get("mediumThumbnailUrl") or back.get("smallThumbnailUrl") or ""

        safe_name = _safe(name)
        dest = out / f"{safe_name}{ext}"

        # Skip if any extension variant already present
        existing = next(out.glob(f"{safe_name}.*"), None)
        if existing:
            print(f"  ok {existing.name}  (deja present)")
            skipped += 1
            continue

        print(f"  [{idx+1}/{len(backs)}] {dest.name}…", end=" ", flush=True)
        actual: Path | None = None

        if identifier:
            actual = _dl_gdrive(identifier, dest, session)
        if actual is None and thumb_url:
            if _dl_url(thumb_url, dest, session):
                actual = dest

        if actual is not None:
            kb = actual.stat().st_size // 1024
            print(f"OK ({kb} Ko)")
            ok += 1
        else:
            print("ÉCHEC")
            failed += 1

        time.sleep(0.2)

    print(f"\nTerminé : {ok} téléchargés · {skipped} ignorés · {failed} échecs")
    return ok, skipped, failed


if __name__ == "__main__":
    run()
