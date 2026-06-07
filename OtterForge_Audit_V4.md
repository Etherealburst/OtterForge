# OtterForge V2.0 — Audit Externe (V4)
*Fichier de revue à soumettre à Claude AI / ChatGPT — Session 2026-06-06*

---

## 0. Contexte & consignes de lecture

OtterForge est une application desktop Windows (Python + customtkinter) pour créer des proxies MTG imprimables. Ce fichier documente l'état **actuel** du code après deux sessions de fixes et d'ajouts de fonctionnalités. Les fixes précédents (V3) ont été appliqués localement mais **pas encore pushés vers GitHub** — le code sur la branche `feature/card-creator` représente l'état pré-fixes.

Merci de noter que toutes les corrections listées ci-dessous ont été **appliquées au code local** et sont effectives.

---

## 1. Corrections appliquées depuis V3

### 1.1 Tableau de statut

| # | ID | Description | Statut |
|---|-----|-------------|--------|
| 1 | B13 | `_load_saved_decks` : warning statusbar pour deck corrompu | ✅ Appliqué |
| 2 | M2 | Écriture atomique PNG via `safe_save_png` + `file_utils.py` | ✅ Appliqué |
| 3 | B8 | `_META_CACHE_FOLDER` → chemin absolu via `CACHE_DIR` | ✅ Appliqué |
| 4 | A1 | `is_custom: bool` sur `Card` remplace détection chemin fragile | ✅ Appliqué |
| 5 | N1 | `_MEM_LOCK` double-check dans `symbol_cache.py` | ✅ Appliqué |
| 6 | M1 | `_get_with_retry()` pour téléchargements images Scryfall | ✅ Appliqué |
| 7 | N2 | `_upload_in_progress = False` double-reset supprimé | ✅ Appliqué |
| 8 | A2 | `schema_version: 2` + migration v1→v2 dans `deck_manager` | ✅ Appliqué |
| 9 | **NEW** | `User-Agent: OtterForge/2.0` sur toutes les requêtes Scryfall | ✅ Appliqué |
| 10 | **NEW** | Batch upscaling ESRGAN (modèle chargé une seule fois) | ✅ Appliqué |

### 1.2 Fix 9 — User-Agent (critique, régressif)

**Symptôme :** Import TXT → "Aucune carte importée, carte introuvable sur Scryfall".  
**Cause :** Scryfall retourne désormais `400 Bad Request { "subcode": "generic_user_agent" }` pour tout `requests.get` sans `User-Agent` personnalisé. `get_card()` et `get_card_by_set()` utilisaient `requests.get` nu (pas d'en-tête), donc toutes les requêtes metadata échouaient → skip systématique.

**Fix appliqué dans `engine/scryfall_downloader.py` :**
```python
_HEADERS = {"User-Agent": "OtterForge/2.0 (personal proxy tool)"}

# Ajouté dans get_card() et get_card_by_set() :
response = requests.get(SCRYFALL_API_NAMED, params=params, headers=_HEADERS, timeout=10)
```

**Question pour le reviewer :** Scryfall demande aussi un email de contact dans le User-Agent pour les outils personnels (`User-Agent: MyApp/1.0 contact@example.com`). Faut-il ajouter l'email de Samuel dans le header pour être plus conforme aux guidelines Scryfall ?

### 1.3 Fix 10 — Batch upscaling

**Problème :** Real-ESRGAN était appelé **une fois par carte** (`subprocess.run` individuel). Chaque appel charge le modèle IA (~5-10s d'overhead), puis traite une image (~10-20s). Pour 10 cartes : 10 × 30s = ~5 minutes.

**Fix :** `upscaler.upscale_batch()` passe **toutes les cartes en un seul processus** ESRGAN (input folder → output folder). Le modèle se charge une fois, toutes les images sont traitées en séquence GPU. Gain estimé : 3-5× pour 5+ cartes.

**Deuxième optimisation :** `_fit_to_mpc()` utilisait `compress_level=9, optimize=True` pour sauvegarder un PNG 3288×4488. Changé à `compress_level=3` → ~5× plus rapide, taille fichier +20% acceptable pour des prints.

**Code `upscaler.py` — méthode clé :**
```python
def upscale_batch(self, tasks: list[tuple[str, str]], progress_cb=None) -> dict[str, str]:
    # Crée dossier temp, copie inputs avec noms indexés
    # Lance ESRGAN UNE FOIS sur tout le dossier
    # Déplace les outputs vers les destinations finales
    # Retourne {input_path: output_path} pour les réussites
```

**Fallback :** Si `upscale_batch()` échoue (ESRGAN retourne non-0), le code retombe sur l'ancienne méthode individuelle carte par carte.

**Question pour le reviewer :** Le `tempfile.TemporaryDirectory` dans `upscale_batch` crée des fichiers `.tmp` dans le dossier temp Windows par défaut. Sur certains systèmes, l'antivirus peut scanner ces fichiers et bloquer le déplacement (`shutil.move`). Est-ce qu'un paramètre `dir=CACHE_DIR` sur `TemporaryDirectory` serait plus sûr ?

---

## 2. Système Card Creator (fonctionnalité principale de cette session)

### 2.1 Architecture

```
ui/card_creator_panel.py      ←── Formulaire + preview temps réel
engine/card_creator_engine.py ←── Rendu PIL des cartes
assets/frames/                ←── PNGs de frames cardconjurer (non inclus dans git)
assets/fonts/                 ←── Beleren, MPlantin (téléchargés au premier lancement)
assets/mana_symbols/          ←── SVGs symboles mana Scryfall (cachés)
```

Le panel s'intègre dans `+Forge` dans la toolbar. Il génère un preview live (throttle 500ms) et permet d'ajouter la carte custom au deck actif.

### 2.2 Modèle de données — `CardData` (engine/card_creator_engine.py)

```python
@dataclass
class CardData:
    name: str = "Card Name"
    mana_cost: str = ""            # "{2}{W}{U}"
    card_type: CardType = CardType.CREATURE
    supertype: str = ""            # "Legendary", "Snow"
    subtype: str = ""              # "Human Warrior"
    color: CardColor = CardColor.WHITE
    frame_style: FrameStyle = FrameStyle.M15
    rarity: Rarity = Rarity.COMMON
    oracle_text: str = ""
    flavor_text: str = ""
    power: str = ""
    toughness: str = ""
    loyalty: str = ""
    art_path: Optional[str] = None
    artist: str = "Unknown Artist"
    set_code: str = "OTF"
    collector_number: str = "001"
    show_number: bool = False     # N° carte visible en bas à gauche (disabled par défaut)
    name_color: tuple = (0, 0, 0)
    type_color: tuple = (0, 0, 0)
    text_color: tuple = (0, 0, 0)
    pt_color:   tuple = (0, 0, 0)
    name_size:       int = 28
    type_size:       int = 22
    min_oracle_size: int = 9      # auto-shrink jusqu'à 6 si débordement
```

### 2.3 Enums

| Enum | Valeurs |
|------|---------|
| `CardColor` | W U B R G M C A L |
| `CardType` | Creature Instant Sorcery Enchantment Artifact Planeswalker Land Token Saga |
| `FrameStyle` | M15 EXTENDED BORDERLESS FULLART EIGHTH OLD TOKEN |
| `Rarity` | C U R M |

### 2.4 Layout des zones de texte

```
CARD_W = 744 px   CARD_H = 1040 px   (300 DPI, carte poker 63×88 mm)

ART_BOX  = (57,  118, 687, 577)   # fenêtre artwork (transparent dans le frame PNG)
NAME_BOX = (64,   52, 435, 104)   # barre de nom
TYPE_BOX = (62,  584, 645, 634)   # barre de type
TEXT_BOX = (68,  660, 676, 892)   # oracle + flavor
COLL_Y   = 958                    # baseline bande de collecteur
```

### 2.5 Chemin de rendu (méthode `render_card`)

```
render_card(card: CardData) -> Image
  1. _load_frame(card.frame_style, card.color)     ← PNG frame depuis assets/frames/
  2. _composite_art(canvas, card.art_path)          ← scale-to-fill dans ART_BOX
  3. _render_name(canvas, card)                     ← Beleren Bold, centré dans NAME_BOX
  4. _render_mana_cost(canvas, card)                ← symboles PNG droit-alignés
  5. _render_type_line(canvas, card)                ← Beleren, TYPE_BOX
  6. _render_oracle(canvas, card)                   ← MPlantin, auto-shrink, inline mana
  7. _render_pt(canvas, card)                       ← si creature/planeswalker
  8. _render_card_number(canvas, card)              ← si show_number=True
  export_card(card) → CACHE_DIR/custom/{safe_name}_forged.png
```

### 2.6 Auto-shrink oracle

L'oracle text tente d'abord `min_oracle_size` (défaut 9). Si le texte déborde `TEXT_BOX`, il réduit la taille par pas de 1 jusqu'à 6. Si encore overflow, il tronque avec `...`. Les symboles mana inline `{W}`, `{2}`, etc. sont rendus comme des images PIL inline dans le flow de texte.

### 2.7 N° de carte

Checkbox "N° carte :" dans le formulaire, disabled par défaut. Quand activé, dessine `collector_number` en bas à gauche (x ≈ 14% w, y ≈ 95.8% h) sous le filigrane "OtterForge Proxy".

---

## 3. Nouveaux findings (de la revue V3 par Claude AI)

### F1 — `_preview_busy` deadlock si panel détruit [MINEUR]

**Fichier :** `ui/card_creator_panel.py` — méthode `_render_worker`

`_render_worker` n'a pas de `try/finally`. Si `render_card()` lève une exception ET que le panel est détruit avant que `self.after()` s'exécute, `_preview_busy` reste `True` — le preview est bloqué pour le reste de la session.

**Fix proposé :**
```python
def _render_worker(self, card: CardData) -> None:
    try:
        img = self._engine.render_card(card)
        # ... resize ...
        self.after(0, self._set_preview, img)
    except Exception as e:
        try:
            self.after(0, self._set_preview_error, str(e))
        except Exception:
            self._preview_busy = False  # panel détruit — reset direct
```

**Décision :** À appliquer dans la prochaine session (non critique).

### F2 — Collision de noms de fichiers custom [MINEUR]

**Fichier :** `engine/card_creator_engine.py` — méthode `export_card`

Deux cartes custom avec le même nom → même chemin `cache/custom/lightning_bolt_forged.png` → la seconde écrase la première silencieusement. Pas de timestamp ni UUID dans le nom.

**Fix proposé :**
```python
import time
safe = re.sub(r'[\\/:*?"<>|]', "_", card.name.strip())[:48]
ts = int(time.time() * 1000) % 100000  # 5 chiffres
output_path = os.path.join(custom_dir, f"{safe}_{ts}_forged.png")
```

**Décision :** À appliquer dans la prochaine session.

### F3 — Noms Windows réservés non exclus [MINEUR]

**Fichier :** `engine/card_creator_engine.py` — sanitization des noms de fichiers

La sanitization retire `\/:*?"<>|` mais pas les noms réservés Windows : `CON`, `NUL`, `PRN`, `AUX`, `COM1`–`COM9`, `LPT1`–`LPT9`. Une carte nommée "CON" créerait un fichier illisible sur Windows.

**Fix proposé :**
```python
WINDOWS_RESERVED = {"CON","PRN","AUX","NUL",
                    "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
                    "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}
if safe.upper() in WINDOWS_RESERVED:
    safe = f"_{safe}"
```

**Décision :** À appliquer dans la prochaine session.

### F4 — `schema_version` sans cast `int()` [MINEUR]

**Fichier :** `engine/deck_manager.py` — migration de schéma

Si le JSON est édité manuellement avec `"schema_version": "2"` (string), `"2" < 2` lève `TypeError` au lieu de traiter correctement.

**Fix proposé :**
```python
schema_version = int(data.get("schema_version", 1))
```

**Décision :** À appliquer dans la prochaine session.

---

## 4. Profil de performance

| Opération | Avant | Après | Gain |
|-----------|-------|-------|------|
| Import TXT 10 cartes (download) | ~30s | ~30s | = (réseau) |
| Upscaling 10 cartes (ESRGAN) | ~5 min | ~1-2 min | ~3-5× |
| Save PNG 3288×4488 | ~10s | ~2s | ~5× |
| Recherche Scryfall unitaire | OK | OK (User-Agent) | fixé |

---

## 5. Architecture des fichiers (état actuel)

```
engine/
  models.py            Card(is_custom: bool)  schema_version: 2
  deck_manager.py      migration v1→v2, _load_saved_decks warning
  scryfall_downloader.py  _HEADERS, _get_with_retry, download_all_face_images absolu
  batch_importer.py    upscale_batch(), fallback individuel
  upscaler.py          upscale_batch() + compress_level=3
  file_utils.py        safe_save_png, safe_write_bytes
  symbol_cache.py      _MEM_LOCK double-check
  card_creator_engine.py  render_card(), CardData, FrameStyle, CardColor, CardType
  frame_builder.py     +Forge legacy (frame PIL custom, 8 couleurs, 4 layouts)

ui/
  app.py               _on_import_complete affiche skip report si cards=[]
  card_inspector.py    is_custom (flag) au lieu de détection chemin
  card_creator_panel.py  preview live, N° carte checkbox, _render_worker
```

---

## 6. Questions pour le reviewer

**Q1 — User-Agent Scryfall**
Les guidelines Scryfall demandent un email de contact dans le User-Agent pour éviter d'être rate-limité. Actuellement : `OtterForge/2.0 (personal proxy tool)`. Faut-il y ajouter l'email ?

**Q2 — Batch upscaling + antivirus**
`upscale_batch()` utilise `tempfile.TemporaryDirectory()` → dossier dans `%TEMP%`. Sur Windows avec Defender activé, les fichiers `.tmp` peuvent être scannés/bloqués pendant `shutil.move`. Est-ce qu'il vaut mieux créer le dossier temp dans `CACHE_DIR` à la place ?

**Q3 — `compress_level` des PNG MPC**
Changé de 9 à 3 pour la vitesse. Les fichiers MPC passent de ~4 MB à ~6 MB par carte (estimation). Est-ce un compromis acceptable pour l'upload MPC ? MPC accepte des fichiers jusqu'à 100 MB.

**Q4 — Fallback `upscale_batch`**
Si `upscale_batch()` échoue (ESRGAN retourne code d'erreur non-0), le code retombe sur les appels individuels. Mais si ESRGAN échoue en batch, il échouera probablement aussi en individuel. Est-ce qu'il vaut mieux signaler l'erreur directement et utiliser le fallback 300 DPI sans ESRGAN ?

**Q5 — `_preview_busy` dans CardCreatorPanel**
Le flag n'est pas thread-safe — il est écrit depuis le thread UI et depuis le thread de rendu (via `self.after()`). `self.after()` étant toujours exécuté dans le thread principal Tkinter, est-ce que ça reste safe même sans Lock ?

**Q6 — Frame PNG assets absents du repo**
Les frames cardconjurer sont dans `assets/frames/` (non commitées). Le panneau Card Creator montre une erreur si les frames sont absentes. Est-ce qu'il vaut mieux un message d'erreur explicite dans l'UI à l'ouverture du panel, ou un téléchargement automatique comme pour les polices ?

**Q7 — `schema_version` rétrocompatibilité**
La migration v1→v2 ajoute `is_custom: False` pour toutes les cartes existantes. Les cartes dans `cache/custom/` qui avaient un `image_path` relatif à custom seront-elles correctement détectées comme custom après la migration, ou faut-il aussi une détection chemin comme fallback de la migration ?

---

## 7. Risques non corrigés (backlog)

| Risque | Sévérité | Fichier | Description |
|--------|----------|---------|-------------|
| Collision noms custom | Mineur | card_creator_engine.py | Deux cartes "Lightning Bolt" → même fichier |
| Noms Windows réservés | Mineur | card_creator_engine.py | `CON`, `NUL`, etc. |
| `_preview_busy` deadlock | Mineur | card_creator_panel.py | Panel détruit avant callback |
| `schema_version` cast | Mineur | deck_manager.py | Édition manuelle JSON → TypeError |
| Frame assets absents | Info | card_creator_panel.py | Pas de message d'erreur explicite si assets/ vide |

---

*Samuel · OtterForge V2.0 · 2026-06-06*
