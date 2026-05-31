# HANDOFF — OtterForge V2.0

**Dernière mise à jour :** 2026-05-23 (session 4)
**GitHub :** https://github.com/Etherealburst/OtterForge-V2 (privé, branche `master`)
**Dernier commit :** `1f02ba6`
**Pour démarrer :** `python main.py` depuis `C:\Users\Samuel\Documents\MTG\OtterForge - V2.0\`
**Référence architecture :** `CLAUDE.md` (lire en entier avant de toucher quoi que ce soit)

---

## Contexte du projet (ultra-court)

Application desktop Python qui :
1. Permet de construire des decks proxy MTG (recherche Scryfall, import TXT/Moxfield)
2. Génère des feuilles d'impression 3×3 au format MPC (300 DPI)
3. Uploade automatiquement sur MakePlayingCards.com via Playwright (Chromium)

Stack : `customtkinter` (GUI), `Pillow` (images), `requests` (Scryfall API), `playwright` (automation navigateur), Real-ESRGAN optionnel (upscaling ×4 → 1200 DPI).

---

## État au 2026-05-23 — Fonctionnel avec 1 bug à corriger ⚠️

**Fonctionnel :** Import Scryfall, workspace, sidebar (optimisée tk natif), deck switching, fermeture instantanée, inspector stats+tooltips, upload MPC, zoom card popup.

**Bug actif :** Popup zoom mana curve (onglet STATS) — la fenêtre popup n'est pas centrée. Voir PRIORITÉ 0 dans "Ce qui reste à faire".

**Changements session 2026-05-23 :**
- `deck_sidebar._build_row()` : tous les widgets remplacés par tk natifs (×10-20 plus rapide)
- `deck_sidebar._rebuild_list()` : batch system avec `_list_gen` counter
- `deck_tabs._select()` : `sidebar.refresh()` différé de 30ms
- `app.on_close()` : `os._exit(0)` pour fermeture instantanée
- `card_inspector._InspectorTooltip` : police 20, style uniforme
- `card_inspector._build_type_dist` : tooltip simplifié (count+%, sans noms de cartes)

**État antérieur 2026-05-16 :**
L'upload complet (fronts → backs → page de révision) est stable.
L'UI a été entièrement redesignée avec la palette v2 "métal froid + braise".
Les fonctionnalités principales (import, search, workspace, sidebar, inspector) sont opérationnelles.

---

## Palette UI v2 — "Métal froid + Braise"

Toutes les couleurs hardcodées dans les fichiers UI suivent cette palette. **Ne jamais utiliser les anciennes couleurs or/charbon (#d4a843, #0f0b05, #2a2010, #1a1408).**

| Rôle | Hex |
|------|-----|
| Accent principal | `#c04828` (braise) |
| Accent hover | `#a83820` |
| Fond principal (fenêtre) | `#0d0c0e` (quasi-noir bleu-nuit froid) |
| Fond frame | `#1a1820` (bleu-nuit sombre) |
| Surface (rows, cards) | `#131118` |
| Bouton secondaire | `#581e10` |
| Bouton secondaire hover | `#3a1a10` |
| Bouton danger | `#922b21` |
| Texte principal | `#f0ece4` |
| Texte secondaire | `#c4bfb8` |
| Texte muet / labels | `#5a5060` |
| Bordures / séparateurs | `#252030` |

---

## Architecture UI — État actuel

```
Toolbar (64px)
  └─ Logo rond 38px + "OTTERFORGE" Georgia 15pt
  └─ Groupe DECK : [↑ Open] [↓ Save] [⬇ Import]   (boutons 104px)
  └─ Groupe OUTPUT : [⊞ Export] [◧ Card Back] [⬆ MPC]
  └─ Tooltips au survol (_Tooltip via tk.Toplevel)

DeckTabs (36px)
  └─ MAX_VISIBLE = 4 onglets, flèches ◀▶ pour défiler
  └─ _tab_offset : premier onglet visible
  └─ _ensure_tab_visible(index) : appelé après select/create/delete

CardSearch (46px)
  └─ Accent bar #c04828 + label "SEARCH" + entry + bouton "Add to Deck"

── main_frame ──────────────────────────────────────────────────────────
│                                                                       │
│  DeckSidebar (248px)    Workspace (expand)    CardInspectorPanel (270px) │
│                                                                       │
────────────────────────────────────────────────────────────────────────

StatusBar (30px)
```

---

## DeckSidebar (`ui/deck_sidebar.py`)

- Header compact (pady=3) : "DECK" label (9pt, muted) + total count (droite)
- Séparateur mince 1px
- Filtre temps réel avec bouton × (s'illumine quand filtre non vide)
- Liste scrollable : CTkScrollableFrame avec rows (−/count/+/×)
- Clic sur carte → `self.app.inspector.show_card(card)`

**TÂCHE PENDING — header height** : L'utilisateur veut que le strip "DECK + 101 cards" soit plus compact (il a demandé 1/3 de la hauteur actuelle). Une tentative a été faite en réduisant `pady=(10,4)→(3,0)` sur le header frame mais le changement visuel était imperceptible — CTk impose une hauteur minimale via le `fill="y"` de l'accent bar de 3px.

**Fix à essayer** : au lieu de modifier le padding, remplacer l'accent bar verticale par une barre horizontale (changer `side="left", fill="y"` en `side="top", fill="x"` avec height=2), ou supprimer complètement l'accent bar dans le header et mettre le label "DECK" inline avec la count en une seule ligne, taille de font réduite à 8-9pt. L'objectif est un header d'environ 18-22px de haut au lieu des ~34px actuels.

---

## Workspace (`ui/workspace.py`)

- **Auto-layout** : `cards_per_row = max(1, canvas_w // spacing_x)` — adaptatif
- **Centrage** : `start_x = max(20, (canvas_w - row_content_w) // 2)`
  - En mode Faces+Backs : `row_content_w = (n-1)*spacing_x + card_w*2 + back_gap` (IMPORTANT : inclure le verso de la dernière paire sinon débordement droite)
- **BACKS_SCALE = 0.88** : les cartes en mode Faces+Backs sont à 88% de la taille normale → ~4 paires par rangée sur l'écran de l'utilisateur
- **Resize** : binding `<Configure>` + debounce 400ms
- Clic sur carte (ou verso) → `inspector.show_card(card, show_back=self._last_clicked_back)`
- Clic droit : Remove / +1 / -1 / Open file / Change image / Set Card Back / Export image

---

## CardInspectorPanel (`ui/card_inspector.py`)

Dual-mode :

**Onglet CARD** :
- `show_card(card, show_back=False)` — si `show_back=True` et que la carte a `back_image_path`, charge le verso. Label `← face verso` en braise affiché.
- Image chargée en thread (non-bloquant), guard stale `if card is not self._current_card`

**Onglet STATS** :
- Total / unique / DFC count
- Distribution copies / backs / top 6 cartes
- `refresh_stats()` appelé depuis `app._on_search_success()` et `app._on_import_complete()`

---

## Toolbar (`ui/toolbar.py`)

- HEIGHT = 64px, boutons 104×28px, font 11pt
- `_Tooltip` : tk.Toplevel borderless
- Logo : PIL Image circulaire 38px, `ctk.CTkImage`

---

## Règles critiques à ne jamais briser

### Upload MPC (`engine/mpc_uploader.py`)
Ordre obligatoire dans `_advance_to_back()` :
1. Attendre `sysdiv_wait` caché
2. `_post_complete_sources()` ← PREMIER, toujours
3. wait 3 secondes
4. `oDesign.setNextStep()` ← confirm() dialog géré par `page.on("dialog", accept)`

### Thème CTk (`assets/otterforge_theme.json`)
Doit contenir **toutes** les clés structurelles (corner_radius, border_width, button_length…). Si une clé manque → `KeyError` au démarrage.

---

## Bugs corrigés dans cette session (2026-05-16 session 2)

| # | Bug | Fix |
|---|-----|-----|
| 1 | Faces+Backs : trop de colonnes + débordement droite | `BACKS_SCALE` 0.75→0.88, correction formule centrage `row_content_w` |
| 2 | Inspector ne montrait pas le verso en cliquant sur le back | `show_card(show_back=True)` + `_load_image_bg` lit `back_image_path` |
| 3 | Sidebar sans bouton clear filtre | Ajout bouton × (dim quand vide, illuminé quand filtre actif) |
| 4 | Sidebar HEIGHT trop grande (tentative ratée) | Rétablie en `fill="y"` — voir section DeckSidebar pour le fix pending |

---

## Ce qui reste à faire (2026-05-23)

### PRIORITÉ 0 — BUG : Centrage popup zoom mana curve (régressé cette session)

**Fichier :** `ui/card_inspector.py`, méthode `_open_mana_curve_zoom()` (~ligne 388)

**Problème :** La formule de centrage a été changée (`round(winfo_width() * _s)`) ce qui a cassé le centrage. Le popup n'est plus centré sur la fenêtre.

**Fix exact — utiliser la formule VALIDÉE (identique à `_open_zoom_popup` qui fonctionne) :**
```python
# Remplacer le bloc actuel qui contient app_phys_w, app_phys_h PAR :
self.app.update_idletasks()
try:
    from customtkinter import ScalingTracker
    _s = ScalingTracker.get_window_scaling(self.app)
except Exception:
    _s = 1.0

cx = self.app.winfo_rootx() + self.app.winfo_width() // 2
cy = self.app.winfo_rooty() + self.app.winfo_height() // 2
px = cx - round(POP_W * _s) // 2
py = cy - round(POP_H * _s) // 2
```
Garder `POP_W = 1100`, `POP_H = 700`. Ne RIEN changer d'autre dans la méthode.

**Règle : ne jamais toucher `_open_zoom_popup()` (card zoom) — il fonctionne.**

---

### PRIORITÉ 1 — Sidebar switching : couper en 2 si possible (être honnête)

**État actuel :** tk widgets natifs (~1ms/widget × 10/row × 60 rows = ~600ms), batches de 20 avec `after(0)` = 3 batches de ~200ms chacun.

**Option A (honnête, ~50% gain) — Virtual scrolling :**
Créer seulement les rows visibles dans la hauteur du `list_frame`. Hauteur visible ÷ row height (≈44px) = ~8-12 rows max. Recréer sur scroll event. Restructuration modérée de `_rebuild_list`.

**Option B (quick win, perçu plus rapide) — 1 seul batch :**
Changer `BATCH = 20` → `BATCH = 9999` dans `_build_rows_batch`. Cela crée tout en une passe (~600ms de freeze unique) mais l'utilisateur ne voit pas les rows apparaître un par un. Psychologiquement plus rapide même si temps total identique.

---

### PRIORITÉ 2 — DeckSidebar header trop grand (demande ancienne non résolue)
Voir section DeckSidebar ci-dessus. Le strip "DECK + 101 cards" en haut de la sidebar fait ~34px. L'utilisateur veut ~12-18px. La réduction de padding ne suffit pas car CTk force une hauteur min.

**Approche recommandée** :
```python
# Remplacer le header actuel par une ligne inline ultra-compacte :
header = ctk.CTkFrame(self, fg_color="#131118", height=22, corner_radius=0)
header.pack(fill="x", padx=0, pady=0)
header.pack_propagate(False)

ctk.CTkLabel(header, text="DECK", font=ctk.CTkFont(size=8), text_color="#5a5060").pack(side="left", padx=(8,4))
self.total_label = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=9), text_color="#c4bfb8")
self.total_label.pack(side="right", padx=6)
# Accent bar : ligne horizontale de 2px EN BAS du header (pas à gauche)
ctk.CTkFrame(self, height=2, fg_color="#c04828", corner_radius=0).pack(fill="x")
```
Cela force le header à exactement 22px de haut avec `pack_propagate(False)`.

### PRIORITÉ 3 — Améliorations non critiques
- Workspace resize : légère disparition des cartes pendant ~400ms (debounce)
- Inspector : afficher back image quand `_last_clicked_back` depuis la sidebar (pas encore de concept "back" dans sidebar)
- MPC : retry automatique sur erreur réseau
- Real-ESRGAN : chemin configurable via UI Préférences

---

## Commandes utiles

```powershell
# Lancer l'app
python main.py

# Pull les derniers commits
git pull

# Supprimer le cache scryfall pour forcer re-upscale
Remove-Item "cache\scryfall\*_1200dpi.png"

# Vérifier que le thème charge sans erreur
python -c "import customtkinter as ctk; ctk.set_default_color_theme('assets/otterforge_theme.json'); print('OK')"
```
