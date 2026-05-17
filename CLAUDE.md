# CLAUDE.md — MTG Print Factory (OtterForge V2.0)

## Vue d'ensemble

Application desktop Python permettant de créer des decks proxy MTG et de les uploader automatiquement sur **MakePlayingCards.com (MPC)** pour impression.

**Lancer l'application :** `python main.py`

---

## Stack technique

| Composant | Détail |
|-----------|--------|
| GUI | `customtkinter` (dark mode, thème CTk) |
| Images | `Pillow` (PIL) |
| HTTP / Scryfall API | `requests` |
| Automation navigateur | `playwright` (installé séparément via `pip install playwright && playwright install chromium`) |
| Upscaling IA | Real-ESRGAN `realesrgan-ncnn-vulkan.exe` à `C:\Users\Samuel\Documents\MTG\Real-ESGRAN\` (optionnel) |

---

## Architecture des fichiers

```
OtterForge - V2.0/
├── main.py                        # Point d'entrée — crée les dossiers, lance l'app
├── config.py                      # Constantes globales (dimensions, DPI, dossiers)
├── requirements.txt
│
├── engine/                        # Logique métier (aucun import UI)
│   ├── models.py                  # Card (dataclass: name, image_path, count, back_image_path)
│   ├── deck_manager.py            # DeckManager + Deck — CRUD, save/load JSON
│   ├── scryfall_downloader.py     # API Scryfall (fuzzy name, set+CN exact, download images)
│   ├── batch_importer.py          # Import TXT/Moxfield — parse + download + upscale batch
│   ├── upscaler.py                # ImageUpscaler — Real-ESRGAN ×4 → 1200 DPI (3288×4488 px)
│   ├── mpc_print_engine.py        # Génération feuilles d'impression 3×3 à 300 DPI (format MPC)
│   └── mpc_uploader.py            # MPCUploader — automation Playwright pour upload sur MPC
│
├── ui/                            # Composants UI (tous via customtkinter)
│   ├── app.py                     # MTGPrintFactoryApp — fenêtre principale, controller
│   ├── toolbar.py                 # Toolbar — boutons actions principales
│   ├── deck_tabs.py               # DeckTabs — onglets entre decks (+ / renommer / supprimer)
│   ├── card_search.py             # CardSearch — barre de recherche Scryfall (en haut)
│   ├── workspace.py               # Workspace — canvas cartes (zoom, drag, preview, find)
│   ├── deck_sidebar.py            # DeckSidebar — liste cartes avec compteurs (à gauche)
│   ├── preview_panel.py           # PreviewPanel — aperçu feuilles d'impression (à droite)
│   ├── statusbar.py               # StatusBar — barre de statut + progress bar
│   └── card_back_picker.py        # CardBackPickerDialog — sélecteur d'image d'endos
│
├── cache/scryfall/                # Images PNG téléchargées depuis Scryfall (cachées)
│   └── *_1200dpi.png              # Versions upscalées (Real-ESRGAN ×4)
├── decks/                         # Decks auto-sauvegardés en JSON
├── card_backs/                    # Images d'endos fournies par l'utilisateur
├── output/sheets/                 # Feuilles d'impression générées
├── output/exports/                # Archives ZIP pour MPC
└── debug_mpc/                     # Screenshots + dumps DOM du flux MPC (debug)
```

---

## Modèle de données

### `Card` (engine/models.py)
```python
card.name            # str — nom face recto (pour DFC : "Delver of Secrets", pas "Delver // Insectile")
card.image_path      # str — chemin local face recto (préféré : _1200dpi.png si disponible)
card.count           # int — nombre de copies dans le deck
card.back_image_path # str | None — chemin face verso (DFC face1) ou None
```

`to_dict()` omet `back_image_path` s'il est None (compact JSON).

### `Deck` (engine/deck_manager.py)
```python
deck.name       # str
deck.cards      # list[Card]
deck.back_image # str | None — endos global du deck (overridé par card.back_image_path pour DFC)
```

### `DeckManager`
- `active_deck()` — deck actif (index)
- `add_card(card)` — fusionne par nom normalisé DFC (voir ci-dessous)
- `add_cards_bulk(list[dict])` — import batch, pas de dédup
- `save_deck_at(deck, path)` / `load_deck(path)` — JSON

---

## Threading

**Règle absolue : les widgets Tkinter ne sont jamais touchés depuis un thread secondaire.**  
Toujours passer par `self.after(0, callback, args...)` depuis les threads.

| Opération | Thread |
|-----------|--------|
| Recherche Scryfall + upscaling (CardSearch) | `threading.Thread` daemon → résultats via `self.after()` |
| Import TXT batch | `threading.Thread` daemon → progress via `self.after()` |
| Chargement images workspace | `threading.Thread` daemon + `queue.Queue` polling à 40ms |
| Automation MPC | `threading.Thread` daemon |

---

## Flux principaux

### 1. Ajout d'une carte (CardSearch)

```
CardSearch._on_add(name)
  → app.search_and_add_card(query)
    → batch_importer.parse_line(query)          # parse format (voir ci-dessous)
    → _search_worker(parsed) [thread]
        → scryfall.get_card_by_set() ou get_card()
        → scryfall.download_all_face_images()    # face0.png + face1.png pour DFC
        → upscaler.upscale_to_1200dpi() par face
        → Card(faces[0].name, face0_path, back=face1_path)
        → self.after(0, _on_search_success, [card])
  → deck_manager.add_card(card)                 # merge par nom normalisé DFC
  → workspace.load_cards(deck.cards, scroll_to_bottom=True)
```

### 2. Import TXT / Moxfield

```
app.import_txt_deck()
  → _import_txt_worker(path) [thread]
      → batch_importer.import_txt(path, progress_callback)
          pour chaque ligne : parse_line → Scryfall → download → upscale
          retourne (cards: list[dict], skipped: list[dict])
      → self.after(0, _on_import_complete, cards, skipped)
  → deck_manager.add_cards_bulk(cards)          # append direct, pas de dédup
  → workspace.load_cards()
```

### 3. Upload MPC (Playwright)

```
app.upload_to_mpc()
  → dialog config (stock, login, headless, upload_backs)
  → _mpc_upload_worker(cards, ...) [thread]
      → MPCUploader.upload(cards, back_image_path, ...)
          1. product page → doPersonalize() → éditeur iframe
          2. setMode('ImageText', 0) → éditeur slots
          3. Pour chaque front : #uploadId → pid → applyDragPhoto(slot, pid)
          4. oDesign.setNextStep() → page backs
          5. Pour backs globaux : mode 1 (same image) → upload once → applyDragPhoto slot 0
             Pour backs DFC : mode 0 → upload par slot
          6. setNextStep() → page révision → scroll lazy-load
          7. Laisse le navigateur ouvert (3600s timeout)
```

---

## Formats supportés par `batch_importer.parse_line()`

| Format | Exemple |
|--------|---------|
| Arena / Moxfield précis | `1 Lightning Bolt (M11) 149` |
| Moxfield basique | `1 Lightning Bolt` |
| Nom seul | `Lightning Bolt` |
| Nom + count | `Lightning Bolt x4` |
| Set + CN | `s:sld cn:1917` |
| Nom + Set + CN | `Rip Apart s:sld cn:1917 x2` |
| Noms DFC | `Delver of Secrets // Insectile Aberration` |

Commentaires (`#`) et marqueurs Moxfield (`*F*`, `*E*`, `★`) ignorés.

---

## Cartes double-face (DFC)

### Stockage
- Face recto : `*_face0.png` → `card.image_path`
- Face verso : `*_face1.png` → `card.back_image_path`
- `load_deck` ignore les entrées JSON dont `image_path` contient `_face1`

### Résolution des chemins (load_deck + workspace)
Si `_1200dpi.png` absent → fallback vers `.png` natif pour `image_path` ET `back_image_path`.  
`back_image_path` mis à `None` si aucune version n'existe.

### Déduplication (add_card)
`_card_name_key(name)` : `name.split(" // ")[0].strip().lower()`  
→ "Delver of Secrets" == "Delver of Secrets // Insectile Aberration" lors du merge.

### Affichage workspace
- Mode **Faces Only** (défaut) : seul le recto affiché.
- Mode **Faces + Backs** (bouton toggle) : recto + verso côte à côte.
- Ordre de résolution du verso : `card.back_image_path` → `app.deck_back_image` (global).

---

## Upscaling (Real-ESRGAN)

- Exécutable : `C:\Users\Samuel\Documents\MTG\Real-ESGRAN\realesrgan-ncnn-vulkan.exe`
- Facteur : ×4, modèle `realesrgan-x4plus`
- Cible : 3288×4488 px (1200 DPI, format MPC avec bleed)
- `is_available()` : vérifie l'existence de l'exe → toute l'app est opérationnelle sans lui (300 DPI)
- Chemin upscalé : `original.replace(".png", "_1200dpi.png")`

---

## MPC Uploader — notes techniques

### Iframe éditeur
L'éditeur MPC vit dans un iframe `sysifm_loginFrame` (URL `dn_playingcards_mode_nf` / `_nb`).  
`_find_editor_frame()` détecte le frame par présence de `#uploadId` / `fmItem0` / `bnbox0`.

### Flux de configuration
1. Sélectionne la quantité via `dro_total_count` (arrondi au multiple de 18 ≥ nb cartes)
2. Tape la quantité dans `txt_card_number` → déclenche `renderPacking()` (onkeyup)
3. Appelle `setMode('ImageText', 0)` → navigue vers l'éditeur de slots

### Upload et placement
- Upload via `frame.locator("#uploadId").set_input_files(image_path)`
- Récupère le `pid` via `oDesignImage.dn_getImageList()`
- Place via `PageLayout.prototype.applyDragPhoto(el, 0, pid)`
- Attend `#sysdiv_wait` caché après chaque placement (`_wait_sysdiv`)

### Navigation entre étapes — CRITIQUE
Chaque `applyDragPhoto` ne POST qu'un seul slot à `dn_update_transition_data.aspx`.
Après N uploads, le serveur ne connaît que le dernier slot → `btn_next_step` reste désactivé.

Ordre obligatoire dans `_advance_to_back` / `_click_next_step` :
1. **`_post_complete_sources()`** — POST tous les slots capturés → serveur active `btn_next_step`
2. **`oDesign.setNextStep()`** — MPC affiche un `confirm()` dialog → accepté par `page.on("dialog", accept)` enregistré au démarrage
3. Fallback : forcer `#btn_next_step` visible + clic
4. Dernier recours : `__doPostBack('btn_next_step','')`

### `_post_complete_sources`
POST vers `dn_update_transition_data.aspx` avec `hidd_image_list` complet.  
Construit la liste depuis les sources capturées via intercepts `dn_product_analysis_photo`.  
**Doit être appelé AVANT `setNextStep()`** — pas en dernier recours.

### Endos global vs DFC
- Endos global : `setMode('ImageText', 1)` → upload une seule image → `applyDragPhoto` slot 0 → MPC réplique
- DFC (backs individuels) : `setMode('ImageText', 0)` → upload + place chaque slot

---

## Dossiers et persistence

| Dossier | Contenu |
|---------|---------|
| `cache/scryfall/` | Images PNG (cachées, jamais re-téléchargées si présentes) |
| `decks/` | JSON auto-sauvegardés à chaque modification |
| `card_backs/` | Images d'endos fournies par l'utilisateur |
| `output/sheets/` | Feuilles 3×3 PNG générées |
| `output/exports/` | ZIP prêts pour MPC |
| `debug_mpc/` | Screenshots Playwright + dumps JSON DOM (debugging) |

Auto-save : déclenché par `_auto_save()` après chaque ajout, suppression ou modification de count.  
Chargement au démarrage : `_load_saved_decks()` charge tous les JSON de `decks/` triés par nom.

---

## État du projet (2026-05-16)

### Fonctionnel
- Import Scryfall (nom fuzzy + set/CN exact + formats Moxfield/Arena)
- Import batch TXT avec rapport des cartes ignorées
- Upscaling Real-ESRGAN (optionnel)
- Workspace : zoom 3 niveaux, drag & drop, find-in-deck, mode Faces+Backs (BACKS_SCALE=0.88 → ~4 paires/rangée)
- Sidebar : compteurs +/-/×, filtre temps réel avec bouton × clear
- Multiple decks avec onglets paginés MAX_VISIBLE=4 (créer, renommer, supprimer, switcher)
- Endos global du deck + endos par carte (DFC et override manuel)
- Export feuilles d'impression + ZIP
- Upload MPC automatisé (Playwright) avec progress bar
- DFC : téléchargement des deux faces, stockage `back_image_path`, affichage et upload corrects
- CardInspectorPanel dual-mode (CARD tab + STATS tab) — affiche le verso si clic sur back en workspace

### Points d'attention
- **Upload MPC** : le flux fonctionne mais dépend de la structure HTML de MPC. Voir HANDOFF.md section "Règles critiques".
- **Real-ESRGAN** : chemin hardcodé dans `config.py` (`REALESRGAN_DIR`). Si absent → 300 DPI.
- **Playwright** : installer séparément (`pip install playwright && playwright install chromium`).
- **`add_cards_bulk`** (import TXT) : pas de dédup voulu — append direct.
- **DeckSidebar header** : tentative de réduction padding (session 2) inefficace — voir HANDOFF.md section PRIORITÉ 1 pour le fix avec `pack_propagate(False)` + height=22.

### Bugs corrigés (sessions 1 + 2, 2026-05-14 → 2026-05-16)
1. **Upload bloqué front→back** : `_post_complete_sources` AVANT `setNextStep()` + dialog handler.
2. **Bleed / pointillé rouge MPC** : `_fit_to_mpc` scale-to-fit + canvas noir.
3. **KeyError 'corner_radius'** : `otterforge_theme.json` doit contenir toutes les clés CTk structurelles.
4. **CardSearch ignorait s:/cn:** : guard ajouté dans `_MOXFIELD_BASIC_RE` branch.
5. **Dédup par nom fusionnait éditions différentes** : dédup par `image_path` à la place.
6. **Toolbar boutons coupés** : HEIGHT 52→64px.
7. **DeckTabs débordement** : MAX_VISIBLE=4 + flèches ◀▶ + `_ensure_tab_visible`.
8. **Workspace cartes à gauche** : auto-layout `canvas_w // spacing_x` + centrage.
9. **Scrollbars système incohérentes** : remplacées par `ctk.CTkScrollbar`.
10. **Faces+Backs : trop de colonnes + débordement** : BACKS_SCALE=0.88, formule centrage corrigée (inclure `card_w*2 + back_gap` pour la dernière paire).
