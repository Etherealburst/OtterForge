# Changelog — OtterForge

All notable changes to OtterForge are documented here.

---

## [v1.5.2] — 2026-06-03

### Fixed
- **Zoom popup double-ouverture** — `grab_release()` appelé sur l'ancien popup avant sa destruction, évite le "vol de grab" non documenté sur Windows
- **`_refresh_canvas` après fermeture** — guard `popup.winfo_exists()` empêche une `TclError` silencieuse si le popup est fermé avant que le thread image ait terminé
- **Stats de deck jamais persistées hors exe dir** — `os.makedirs("cache")` (CWD relatif) remplacé par `os.makedirs(os.path.dirname(_METADATA_CACHE_PATH))` (chemin absolu) ; la courbe de mana et les types de cartes sont maintenant correctement sauvegardés entre sessions même si l'exe est lancé via raccourci Windows
- **`_on_popup_press` borne exclusive** — `<= cv_w` → `< cv_w` : le pixel à exactement `x == cv_w` est maintenant correctement traité comme clic extérieur

### Improved
- **`_InspectorTooltip`** — police ramenée à 9pt (proportionnée à 100% DPI Windows)

---

## [v1.5.1] — 2026-06-03

### Fixed
- **Outside-click detection in zoom popup** — replaced unreliable `bind_all` approach (broken on Windows when widgets interrupt the event chain) with `popup.grab_set()` + coordinate check; outside clicks now reliably show the Save/Back dialog after dragging
- **Stats panel race condition** — `_fetch_metadata` no longer writes directly to `_metadata_cache` from a background thread; data is accumulated locally then merged on the main thread via `_merge_metadata`, preventing `RuntimeError: dictionary changed size during iteration`
- **Search dropdown idempotence** — `_bind_global_click` guard prevents double-registration if widget is recreated

### Improved
- **`_orig.png` compression** — Scryfall fallback image now saved at `compress_level=6` (consistent with `proxy_watermark.py`)
- **Code cleanup** — removed dead `card_json` parameter from `ProxyWatermark._stamp()`

---

## [v1.5.0] — 2026-06-03

### Added
- **Watermark zoom popup** — click the card image in the inspector to open a full-resolution zoom where you can drag-and-drop the "OtterForge Proxy" and "Not for sale" stamps to any position; changes are saved per-card and reapplied on the disk image
- **Save / Back dialog** — after dragging a stamp, clicking anywhere outside the zoom shows a centred overlay asking to Save (writes offset to card + re-downloads + re-stamps) or Back (reverts position, stays in zoom)
- **Artist name preserved** — removed the left collector-bar fill zone; artist name is now visible on the final printed card; "OtterForge Proxy" text is still clearly legible via white + black outline on any background

### Fixed
- **Workspace hover glow** — the orange highlight rectangle now only appears when the mouse is actually over a card; previously `find_closest` would illuminate a card even when the cursor was in empty canvas space
- **Search dropdown closes on outside click** — clicking anywhere outside the search entry or history list now hides the dropdown (previously stayed open until an item was selected)
- **Search dropdown opens on re-click** — clicking the entry again when it already has focus now re-opens the dropdown (`<Button-1>` binding added alongside `<FocusIn>`)
- **"Not for sale" position in zoom** — NFS text position in the zoom popup now matches the actual card position (uses the apply_fill formula from card metadata — borderless / showcase / full-art cards use a different offset)
- **Zoom popup size** — popup now fills the available workspace area (up to 500 px wide) instead of a fixed 380 px

### Improved
- **Unified tooltip style** — all tooltips (sidebar, inspector, workspace, search dropdown) now use Segoe UI 20 pt, background `#3a3548`, border `#c04828`

---

## [v1.4.1] — 2026-06-01

### Fixed
- **MPCFill card backs missing on first launch** — the `card_backs/` folder (including `MPCFILL.png` and `MPCFILL PG.png`) was not bundled in the distributed zip, causing the Card Back Picker's MPCFill tab to appear empty on a fresh install; it is now always included in the build

---

## [v1.3.0] — 2026-05-31

### Added
- **README screenshots** — three app screenshots added to the repository main page

### Fixed
- **Card back picker — button cropped** — dialog resized to 760×560 with a fixed-height footer; the "Use this image" and Cancel buttons are always fully visible regardless of DPI scaling
- **Card back picker — MPCFill presets missing** — the standard MTG card back is now shown directly in the MPCFill tab if already downloaded (from a previous MPC upload), or can be fetched with a single "Download" button; download runs in a background thread and refreshes the gallery automatically

---

## [v1.2.0] — 2026-05-31

### Fixed
- **Workspace duplication / art swap** — cards no longer flicker or show wrong art when adding a card or toggling Faces Only ↔ Faces+Backs; the canvas now renders all cards atomically (batch) instead of progressively one by one
- **Double watermark stamp** — removed the redundant in-memory `apply_to_image()` pass in the workspace worker; `apply()` on disk is always called before `load_cards()` so a single clean stamp is applied
- **Watermark "22026" artefact** — background rectangle now always extends from `erase_x` to the right edge, fully erasing any previously-written stamp before drawing the new one
- **Wizards copyright still visible** — tight `getbbox` box was insufficient for cards with slightly varying copyright y-positions; restored full-height strip `[erase_x, y_top, w, h]` as the only reliable approach

### Improved
- **Proxy watermark strip** — strip height reduced by 7 px (`strip_h - 7`) and text baseline lowered 1 px, less intrusive on card art
- **Folder import — artwork conflict picker** — when multiple images share the same normalised card name, a new `ArtworkPickerDialog` lets you choose which artwork to keep per card
- **Deck sidebar — artwork subtitle** — rows with duplicate card names now show the source filename as a small subtitle so you can distinguish multiple artworks for the same card
- **TXT batch import — watermark progress** — a dedicated `watermark_callback` parameter now reports stamping progress in the status bar during large imports
- **Folder import — consistent watermark display** — when upscaling, the source (native) image is also stamped so the workspace always shows the watermark regardless of which resolution is loaded

---

## [v1.1.0] — 2026-05-31

### Added
- **Folder import** — import card images directly from a local folder instead of downloading from Scryfall (Custom Artwork mode)
- **Proxy watermark** — automatically stamps a branded OtterForge strip at the bottom of each card (`YEAR OtterForge Proxy • Not for sale` + set/CN/artist metadata)
- **Custom artwork modes** — choose between Scryfall artwork, local folder artwork, or a mix per card

### Fixed
- Watermark engine: PNG images with an alpha channel (custom artwork) are now composited correctly onto the dark background before RGB conversion — transparent areas no longer go black
- Watermark `print()` calls now use ASCII-safe paths to avoid encoding errors on Windows cp1252 consoles
- Filename sanitization for cards with special characters in their name

---

## [v1.0.0] — 2026-05-14

Initial public release.

- Card search via Scryfall API (fuzzy name, set + CN, Moxfield/Arena format)
- Bulk TXT import with skip report
- Double-faced card (DFC) support — both faces downloaded and stored automatically
- AI upscaling via Real-ESRGAN ×4 to 1200 DPI (optional, external binary)
- Multiple decks with tabbed navigation
- Global and per-card back image management
- MPC automation via Playwright (card fronts + backs, global or DFC-per-slot)
- 3×3 print sheet export at 300 DPI (PNG + ZIP)
- Undo / Redo (Ctrl+Z / Ctrl+Y)
- Card inspector panel — zoom popup + mana curve / type breakdown stats
- Auto-save after every deck change
