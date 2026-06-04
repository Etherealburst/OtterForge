# OtterForge — Plan d'action : Système de création de cartes MTG custom

> **Projet**: Module `card_creator` dans OtterForge  
> **Objectif**: Créer des cartes MTG personnalisées visuellement fidèles, exportables en PNG haute résolution pour impression proxy maison  
> **Usage**: Personnel, proxies maison seulement (non commercial)  
> **Auteur du plan**: Claude (pour Claude Code)

---

## CHEMINS RÉELS DU PROJET (Windows)

```
Racine du projet:
C:\Users\Samuel\Documents\Projets Claude AI\OtterForge\

Assets disponibles:
C:\Users\Samuel\Documents\Projets Claude AI\OtterForge\assets\fonts\
  └── Contenu du repo mtg-font (Mplantin.ttf, Beleren.ttf, Matrix-Bold.ttf, etc.)

C:\Users\Samuel\Documents\Projets Claude AI\OtterForge\assets\frames\
  └── Contenu du repo cardconjurer → les frames PNG sont dans img\frames\
      Exemple: assets\frames\img\frames\normal\w.png

C:\Users\Samuel\Documents\Projets Claude AI\OtterForge\assets\mana_symbols\
  └── Contenu du repo mana → les SVG sont dans svg\
      Exemple: assets\mana_symbols\svg\w.svg
              assets\mana_symbols\svg\u.svg
              assets\mana_symbols\svg\tap.svg

C:\Users\Samuel\Documents\Projets Claude AI\OtterForge\assets\set_symbols\
  └── Contenu du repo keyrune → fonts dans fonts\, SVG dans svg\
```

### Chemins à utiliser dans le code Python

```python
import os

# Racine assets — chemin relatif depuis main.py (recommandé)
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

FONTS_DIR         = os.path.join(ASSETS_DIR, "fonts")
FRAMES_DIR        = os.path.join(ASSETS_DIR, "frames", "img", "frames")
MANA_SYMBOLS_DIR  = os.path.join(ASSETS_DIR, "mana_symbols", "svg")
SET_SYMBOLS_DIR   = os.path.join(ASSETS_DIR, "set_symbols", "svg")

# Fonts spécifiques
FONT_MPLANTIN         = os.path.join(FONTS_DIR, "Mplantin.ttf")
FONT_MPLANTIN_ITALIC  = os.path.join(FONTS_DIR, "Mplantin-Italic.ttf")
FONT_BELEREN          = os.path.join(FONTS_DIR, "Beleren.ttf")
FONT_BELEREN_BOLD     = os.path.join(FONTS_DIR, "Beleren-Bold.ttf")
# Note: vérifier les noms exacts des fichiers .ttf présents dans assets/fonts/
# avec os.listdir(FONTS_DIR) si nécessaire
```

> ⚠️ **Note pour Claude Code**: Utiliser des chemins relatifs (`os.path.dirname(__file__)`) plutôt que des chemins absolus. Ça rend le projet portable si le dossier est déplacé.

---

## CONTEXTE TECHNIQUE

- Application desktop Python avec CustomTkinter
- Architecture stricte : `UI` / `App Controller` / `Engine`
- Existant dans MTG Print Factory : `engine/print_engine.py`, `ui/`, `cards/`, `output/`
- Ce module est **nouveau** : `engine/card_creator_engine.py` + `ui/card_creator_panel.py`
- Le rendu de carte se fait avec **Pillow (PIL)** — déjà présent dans l'environnement
- Les symboles mana dans `assets/mana_symbols/svg/` sont des **SVG** — les convertir en PNG avec `cairosvg` ou les rasteriser avec Pillow + `cairosvg`. Alternative: utiliser la **Mana font TTF** (`assets/fonts/`) directement comme glyphes texte.

---

## APPROCHE GÉNÉRALE

On utilise **Pillow + assets communautaires libres** pour reconstruire les cartes layer par layer (comme Photoshop, mais en Python).

Chaque carte = empilement d'images PNG :
1. Frame de fond (selon type/couleur) — depuis `assets/frames/img/frames/`
2. Zone art (image importée par l'utilisateur)
3. Texte (nom, type, oracle, flavor) — fonts depuis `assets/fonts/`
4. Symboles mana inline — depuis `assets/mana_symbols/svg/` (convertis en PNG)
5. Stats (P/T, loyauté)

### Symboles mana — stratégie recommandée

Les fichiers dans `assets/mana_symbols/svg/` sont des SVG. Deux options:

**Option A (recommandée)** — Convertir les SVG en PNG au premier lancement et les mettre en cache:
```python
# pip install cairosvg
import cairosvg
cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=30, output_height=30)
```

**Option B** — Utiliser la Mana font TTF comme police de caractères (les glyphes sont les symboles):
```python
# La Mana font encode les symboles comme caractères Unicode spéciaux
# Consulter assets/mana_symbols/css/ ou fonts/ pour le mapping caractère → symbole
```

---

## ÉTAPES D'IMPLÉMENTATION

### ÉTAPE 0 — Assets ✅ DÉJÀ FAIT

Structure en place:
```
assets/
├── fonts/           ← repo mtg-font (Mplantin.ttf, Beleren.ttf, etc.)
├── frames/          ← repo cardconjurer (frames dans img/frames/)
├── mana_symbols/    ← repo mana (SVG dans svg/)
└── set_symbols/     ← repo keyrune (fonts + SVG)
```

**Première tâche de Claude Code**: Lister les fichiers présents avec `os.listdir()` pour confirmer les noms exacts avant de coder les chemins.

---

### ÉTAPE 1 — Modèle de données de la carte

**Fichier à créer**: `engine/card_creator_engine.py`

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class CardColor(Enum):
    WHITE      = "W"
    BLUE       = "U"
    BLACK      = "B"
    RED        = "R"
    GREEN      = "G"
    MULTICOLOR = "MULTI"
    COLORLESS  = "C"
    ARTIFACT   = "A"

class CardType(Enum):
    CREATURE     = "Creature"
    INSTANT      = "Instant"
    SORCERY      = "Sorcery"
    ENCHANTMENT  = "Enchantment"
    ARTIFACT     = "Artifact"
    PLANESWALKER = "Planeswalker"
    LAND         = "Land"
    TOKEN        = "Token"
    SAGA         = "Saga"

class FrameStyle(Enum):
    MODERN     = "normal"      # Frame standard actuelle (2003+) — nom du dossier dans cardconjurer
    EXTENDED   = "extended"    # Extended art
    FULLART    = "fullart"     # Full art (lands Zendikar style)
    BORDERLESS = "borderless"  # Borderless/showcase
    OLD        = "old"         # Frame classique (pre-2003)
    TOKEN      = "token"       # Frame token

class Rarity(Enum):
    COMMON   = "C"
    UNCOMMON = "U"
    RARE     = "R"
    MYTHIC   = "M"

@dataclass
class CardData:
    # Identité
    name: str = "Card Name"
    mana_cost: str = ""              # Ex: "{2}{W}{U}"

    # Type
    card_type: CardType = CardType.CREATURE
    supertype: str = ""              # "Legendary", "Basic", "Snow"
    subtype: str = ""                # "Human Warrior", "Forest"

    # Couleur
    color: CardColor = CardColor.WHITE
    color_indicator: bool = False    # Pour cartes double-face

    # Frame
    frame_style: FrameStyle = FrameStyle.MODERN

    # Rareté
    rarity: Rarity = Rarity.COMMON

    # Texte
    oracle_text: str = ""
    flavor_text: str = ""

    # Stats créature
    power: str = ""
    toughness: str = ""

    # Planeswalker
    loyalty: str = ""

    # Art
    art_path: Optional[str] = None   # Chemin absolu vers l'image de l'artwork

    # Métadonnées
    artist: str = "Unknown Artist"
    set_code: str = "OTF"
    collector_number: str = "001"

    # Options visuelles
    extended_art: bool = False
    full_art: bool = False
    borderless: bool = False
```

---

### ÉTAPE 2 — Moteur de rendu de carte

**Fichier**: `engine/card_creator_engine.py` (suite)

#### 2.1 Constantes de mise en page

```python
# Dimensions carte standard à 300 DPI (63 × 88 mm)
CARD_WIDTH  = 744
CARD_HEIGHT = 1040

# Zones (x, y, largeur, hauteur) en pixels
ZONES = {
    "name":       (55,  50,  500, 45),
    "mana_cost":  (560, 40,  170, 55),
    "art":        (55,  110, 634, 460),
    "type_line":  (55,  580, 600, 40),
    "set_symbol": (620, 580, 60,  40),
    "text_box":   (55,  630, 634, 280),
    "pt_box":     (575, 930, 115, 55),
    "artist":     (65,  950, 300, 30),
    "collector":  (380, 950, 300, 30),
}
```

#### 2.2 Logique de sélection de frame

```python
def _get_frame_path(self, card: CardData) -> str:
    """
    Cherche la frame PNG dans assets/frames/img/frames/
    
    Structure observée dans cardconjurer:
    img/frames/
      ├── normal/      → w.png, u.png, b.png, r.png, g.png, m.png (multicolor), c.png, a.png (artifact)
      ├── extended/    → mêmes variantes
      ├── fullart/     → mêmes variantes
      ├── token/       → variantes token
      └── ... autres dossiers

    Logique de sélection:
    1. Choisir le sous-dossier selon frame_style.value
    2. Choisir le fichier selon color.value (en minuscule)
       - CardType.ARTIFACT → "a.png"
       - CardType.LAND     → chercher dans land/ ou utiliser couleur
       - CardColor.MULTI   → "m.png"
       - Sinon             → "{color.value.lower()}.png"
    3. Si le fichier n'existe pas → fallback sur rectangle coloré uni
    """
```

#### 2.3 Méthode principale de rendu

```python
def render_card(self, card: CardData) -> Image.Image:
    """
    Génère une image PIL complète de la carte.
    
    Ordre des layers:
    1. Canvas blanc CARD_WIDTH × CARD_HEIGHT (RGBA)
    2. Frame PNG (resize to card dimensions, paste with alpha)
    3. Artwork (crop/resize dans ZONES["art"])
    4. Nom de carte — font Beleren Bold, ZONES["name"]
    5. Coût en mana — symboles SVG→PNG inline, ZONES["mana_cost"]
    6. Ligne de type — font Beleren, ZONES["type_line"]
    7. Symbole de set + couleur de rareté, ZONES["set_symbol"]
    8. Texte oracle — font MPlantin avec parsing {symboles}, ZONES["text_box"]
    9. Texte flavor — font MPlantin Italic, séparé par ligne décorative
    10. P/T (si créature) ou Loyauté (si planeswalker), ZONES["pt_box"]
    11. Artist + collector info — font MPlantin petite taille
    
    Retourne: PIL.Image en mode RGBA
    """
```

#### 2.4 Parsing du texte oracle avec symboles mana

```python
def _render_oracle_text(self, image: Image.Image, text: str, zone: tuple, font):
    """
    Parse {W}, {U}, {T}, {2}, etc. et les remplace par des images inline.
    
    Algorithme:
    1. Regex split sur \{([^}]+)\} pour isoler tokens texte et tokens symbole
    2. Pour chaque token:
       - Texte normal → ImageDraw.text() à la position courante
       - Symbole {X}  → charger assets/mana_symbols/svg/x.svg,
                        convertir en PNG 20×20px,
                        Image.paste() à la position courante
    3. Gérer les retours à la ligne automatiquement (word wrap)
    4. Réduire la taille de police si le texte dépasse la zone
    """
```

#### 2.5 Export

```python
def export_card(self, card: CardData, output_path: str, dpi: int = 300):
    """
    Rend et sauvegarde la carte en PNG.
    output_path: chemin complet incluant nom de fichier
    dpi: 300 standard, 900 haute qualité impression
    """
    img = self.render_card(card)
    img = img.convert("RGB")  # PNG sans transparence pour impression
    img.save(output_path, "PNG", dpi=(dpi, dpi))
```

---

### ÉTAPE 3 — Interface utilisateur

**Fichier à créer**: `ui/card_creator_panel.py`

Layout: deux colonnes dans un CTkFrame
- **Colonne gauche** (scrollable): formulaire complet
- **Colonne droite** (fixe): prévisualisation carte + boutons export

#### 3.1 Sections du formulaire

**Section 1 — Identité**
- CTkEntry: Nom de la carte
- CTkEntry: Coût en mana — avec label d'aide: `syntaxe: {W} {U} {2} {T}`

**Section 2 — Type de carte**
- CTkOptionMenu: Créature / Éphémère / Rituel / Enchantement / Artefact / Planeswalker / Terrain / Token / Saga
- CTkEntry: Supertype (Legendary, Basic, Snow...)
- CTkEntry: Sous-type (Human Warrior, Island...)

**Section 3 — Couleur**
- CTkSegmentedButton ou 8 CTkCheckBox: W / U / B / R / G / Multicolore / Incolore / Artefact
- Si 2+ couleurs cochées → forcer Multicolore automatiquement

**Section 4 — Frame**
- CTkOptionMenu: Modern / Old Border / Extended Art / Full Art / Borderless / Token
- CTkSwitch: Extended Art
- CTkSwitch: Full Art
- CTkSwitch: Borderless

**Section 5 — Rareté**
- CTkOptionMenu: Commune / Inhabituelle / Rare / Mythique Rare

**Section 6 — Texte**
- CTkTextbox: Texte oracle (règles)
- CTkTextbox: Texte flavor

**Section 7 — Stats** (visibilité conditionnelle)
- CTkEntry × 2: Force / Endurance (visible si Créature)
- CTkEntry: Loyauté initiale (visible si Planeswalker)

**Section 8 — Art**
- CTkButton: "Importer une image..." → filedialog.askopenfilename()
- CTkLabel: miniature de l'art sélectionné (100×70px)

**Section 9 — Métadonnées**
- CTkEntry: Nom de l'artiste
- CTkEntry: Code de set (3 lettres, ex: OTF)
- CTkEntry: Numéro de collectionneur

#### 3.2 Prévisualisation et export

```python
# Debounce: déclencher preview 500ms après la dernière modification
def _schedule_preview(self):
    if self._preview_job:
        self.after_cancel(self._preview_job)
    self._preview_job = self.after(500, self._update_preview)

def _update_preview(self):
    card = self._build_card_data()
    img = self.engine.render_card(card)
    # Redimensionner à ~300px de haut pour l'affichage
    preview_img = img.resize((215, 300), Image.LANCZOS)
    # Afficher dans CTkLabel
    self._preview_photo = ImageTk.PhotoImage(preview_img)
    self._preview_label.configure(image=self._preview_photo)
```

#### 3.3 Boutons d'action

```python
# Sous la prévisualisation, colonne droite:
CTkButton("Prévisualiser",        command=self._update_preview)
CTkButton("Exporter PNG 300 DPI", command=lambda: self._export(300))
CTkButton("Exporter PNG 900 DPI", command=lambda: self._export(900))

def _export(self, dpi: int):
    card = self._build_card_data()
    filename = f"{card.name.replace(' ', '_')}_{dpi}dpi.png"
    output_path = os.path.join("output", "custom_cards", filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    self.engine.export_card(card, output_path, dpi)
    # Afficher confirmation dans statusbar
```

---

### ÉTAPE 4 — Intégration dans l'app principale

**Fichier à modifier**: `ui/toolbar.py` ou `ui/app.py`

- Ajouter bouton ou onglet "🃏 Créer une carte"
- Ouvrir `CardCreatorPanel` dans un CTkToplevel ou CTkTabview selon l'architecture existante
- Passer référence AppController pour accès aux chemins output

---

## ORDRE D'IMPLÉMENTATION RECOMMANDÉ

```
Phase 1 — Fondations
├── [x] Assets en place (FAIT)
├── [ ] Lister les fichiers réels dans assets/ avec os.listdir() pour confirmer les noms
├── [ ] Créer CardData dataclass
├── [ ] Créer CardCreatorEngine._get_frame_path() avec fallback
└── [ ] Créer render_card() minimal: frame + rectangle art placeholder + nom

Phase 2 — Rendu complet
├── [ ] Intégrer artwork réel dans la zone art
├── [ ] Implémenter _render_oracle_text() avec symboles mana
├── [ ] Ajouter type line, flavor text, P/T, loyauté
└── [ ] Tester export PNG 300 DPI

Phase 3 — UI
├── [ ] Créer CardCreatorPanel avec formulaire complet
├── [ ] Connecter à engine (preview debounced)
└── [ ] Boutons export fonctionnels

Phase 4 — Intégration
├── [ ] Intégrer dans app principale
├── [ ] Tester tous les types de cartes
└── [ ] Polish et gestion d'erreurs
```

---

## DÉPENDANCES PYTHON À INSTALLER

```bash
pip install pillow          # déjà présent
pip install cairosvg        # pour convertir SVG mana → PNG
```

> Si `cairosvg` pose problème sur Windows, alternative: `pip install svglib reportlab`

---

## NOTES CRITIQUES POUR CLAUDE CODE

1. **Lister les assets en premier**: Avant de coder les chemins, faire `os.listdir(FONTS_DIR)` et `os.listdir(FRAMES_DIR)` pour voir les noms de fichiers exacts. Ne pas assumer les noms.

2. **Fallback obligatoire**: Si un fichier de frame est introuvable → dessiner un rectangle de la couleur correspondante. Ne jamais laisser crasher sur un asset manquant.

3. **SVG → PNG pour mana symbols**: Les fichiers dans `assets/mana_symbols/svg/` sont des SVG. Les convertir en PNG 20×20px avec cairosvg au premier lancement, mettre en cache dans `assets/mana_symbols/cache/`.

4. **Taille de police adaptative**: Si le texte oracle dépasse la zone → réduire la taille jusqu'à ce que ça rentre. Taille min = 9pt.

5. **Debounce preview**: Utiliser `self.after(500, callback)` dans Tkinter. Ne jamais appeler `render_card()` à chaque keystroke.

6. **Chemin de sortie**: `output/custom_cards/{nom_carte}_{dpi}dpi_{timestamp}.png`

7. **Chemins relatifs**: Toujours construire les chemins avec `os.path.join(os.path.dirname(__file__), ...)` pour portabilité.

8. **Frames dans cardconjurer**: Les frames sont dans `assets/frames/img/frames/`. Explorer ce dossier pour voir les sous-dossiers disponibles (normal, extended, etc.) avant de coder la logique de sélection.

---

## RÉSULTAT ATTENDU

Une carte MTG custom générée par ce système doit avoir:
- ✅ Frame correcte par couleur/type (depuis cardconjurer assets)
- ✅ Art centré et redimensionné dans la zone artwork
- ✅ Nom en font Beleren Bold
- ✅ Coût en mana avec symboles SVG convertis inline
- ✅ Ligne de type correcte
- ✅ Texte oracle avec symboles mana inline
- ✅ Texte flavor en italique MPlantin
- ✅ P/T ou Loyauté si applicable
- ✅ Symbole de rareté coloré
- ✅ Export PNG 300 DPI (imprimable à taille réelle 63×88mm)

**Fidélité visuelle estimée**: 85-90% d'une vraie carte Magic.

---

*Plan rédigé par Claude pour être exécuté par Claude Code — OtterForge v1.x*
*Assets préparés et vérifiés — Prêt pour implémentation*
