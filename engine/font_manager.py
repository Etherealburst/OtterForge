"""
engine/font_manager.py
-----------------------
Downloads and manages MTG-accurate fonts for +Forge proxy cards.

Font hierarchy:
  Card name / type line : Beleren Bold   (official WotC font for card names)
  Rules text body       : MPlantin       (official WotC font for oracle text)
  Flavor text           : MPlantin Italic

These fonts are freely distributed by the MTG proxy community for personal,
non-commercial use. They are downloaded once and cached in assets/fonts/.
"""

import os
import sys

# ── Font directory ────────────────────────────────────────────────────────────

def _fonts_dir() -> str:
    base = (os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    d = os.path.join(base, "assets", "fonts")
    os.makedirs(d, exist_ok=True)
    return d


# ── Known font sources (proxy-community distributions) ───────────────────────
# These URLs serve the fonts as direct file downloads. The fonts are considered
# freeware for MTG fan/proxy use. Multiple mirrors listed for reliability.

_FONT_SOURCES = {
    # Beleren Bold — WotC-commissioned, freely distributed for fan projects
    "Beleren-Bold.ttf": [
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/main/src/fonts/Beleren%20Bold.ttf",
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/refs/heads/main/src/fonts/Beleren%20Bold.ttf",
        "https://raw.githubusercontent.com/MrTeferi/MTG-Proxyshop/main/src/fonts/Beleren%20Bold.ttf",
    ],
    # Beleren Small Caps — for type line
    "Beleren-SmallCaps.ttf": [
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/main/src/fonts/Beleren%20Smallcaps%20Bold.ttf",
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/refs/heads/main/src/fonts/Beleren%20Smallcaps%20Bold.ttf",
    ],
    # MPlantin — rules text body
    "MPlantin.ttf": [
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/main/src/fonts/MPlantin.ttf",
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/refs/heads/main/src/fonts/MPlantin.ttf",
        "https://raw.githubusercontent.com/MrTeferi/MTG-Proxyshop/main/src/fonts/MPlantin.ttf",
    ],
    # MPlantin Italic — flavor text
    "MPlantin-Italic.ttf": [
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/main/src/fonts/MPlantin-Italic.ttf",
        "https://github.com/MrTeferi/MTG-Proxyshop/raw/refs/heads/main/src/fonts/MPlantin-Italic.ttf",
        "https://raw.githubusercontent.com/MrTeferi/MTG-Proxyshop/main/src/fonts/MPlantin-Italic.ttf",
    ],
}

# ── In-memory cache ───────────────────────────────────────────────────────────

_PATHS: dict[str, str | None] = {}   # font key → absolute path (or None = unavailable)


def _download_font(filename: str) -> str | None:
    """Try each mirror URL; return local path on success, None on failure."""
    import requests
    fonts_dir = _fonts_dir()
    dest = os.path.join(fonts_dir, filename)
    if os.path.isfile(dest):
        return dest

    urls = _FONT_SOURCES.get(filename, [])
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "OtterForge/1.0"})
            if r.ok and len(r.content) > 5000:   # sanity: real font > 5 KB
                with open(dest, "wb") as f:
                    f.write(r.content)
                print(f"[FontManager] Downloaded: {filename}")
                return dest
        except Exception as e:
            print(f"[FontManager] Failed {url}: {e}")
    print(f"[FontManager] All mirrors failed for {filename} — using system font fallback")
    return None


def get_font_path(role: str) -> str | None:
    """
    Return the path to the best available font for the given role.

    Roles:
      'name'   — card name (Beleren Bold)
      'type'   — type line (Beleren Small Caps)
      'rules'  — oracle text body (MPlantin)
      'italic' — flavor text (MPlantin Italic)
    """
    mapping = {
        'name':   "Beleren-Bold.ttf",
        'type':   "Beleren-SmallCaps.ttf",
        'rules':  "MPlantin.ttf",
        'italic': "MPlantin-Italic.ttf",
    }
    filename = mapping.get(role)
    if not filename:
        return None

    if filename not in _PATHS:
        _PATHS[filename] = _download_font(filename)
    return _PATHS[filename]


def prefetch_all(callback=None) -> dict[str, bool]:
    """
    Download all MTG fonts in the background. Returns {filename: success} dict.
    Optional callback(filename, success) called after each font.
    """
    results = {}
    for filename in _FONT_SOURCES:
        path = _download_font(filename)
        ok = path is not None
        results[filename] = ok
        if callback:
            try:
                callback(filename, ok)
            except Exception:
                pass
    return results


def is_available(role: str = 'name') -> bool:
    """Return True if the MTG font for this role has been downloaded."""
    return get_font_path(role) is not None
