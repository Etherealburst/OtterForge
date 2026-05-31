# Changelog — OtterForge

All notable changes to OtterForge are documented here.

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
