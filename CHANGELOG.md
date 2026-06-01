# Changelog — OtterForge

All notable changes to OtterForge are documented here.

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
