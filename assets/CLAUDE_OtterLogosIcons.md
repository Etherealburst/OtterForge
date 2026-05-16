# CLAUDE_OtterLogosIcons.md
*Fichier de contexte — otter-logos-icons.html*
*Samuel · Otter Apps · 2026 🦦*

---

## Fichier de référence

**`otter-logos-icons.html`** — Fichier HTML statique unique, autonome (images en base64, polices via Google Fonts).

---

## Contenu par app

Pour chacune des 6 apps, le fichier contient **3 sections** :

### 1. Logos
- **Version verticale** : marque ronde (120×120px, border-radius 27%) + bloc texte (nom bicolore, tagline, badge)
- **Version horizontale** : marque petite (52×52px, border-radius 24%) + nom inline

### 2. Icônes
Toutes les tailles : **16 · 32 · 64 · 128 · 256 · 512 px**
- Border-radius proportionnel : `max(4, size * 0.22)`
- Fond = `card_bg` de l'app, bordure = `border` de l'app

### 3. Mockups
4 formes côte à côte (100px chacune sauf mention) :
- **iOS** — border-radius 28% (100px)
- **macOS** — border-radius 22% (80px)
- **Cercle** — border-radius 50% (80px)
- **Squircle** — border-radius 24px (72px)

---

## Fix appliqué

`img { transform: scale(1.04); }` — recadre légèrement toutes les images pour masquer les artefacts de bordures blanches des JPG source. OtterStash n'en avait pas besoin (fond noir natif) mais le scale est neutre pour elle.

---

## Structure HTML

```
body #080e10
└── .container (max-width 920px)
    ├── .hub-header — titre + sous-titre
    ├── .app-nav — 6 pills de navigation ancre
    └── × 6 .app-section#[app-name]
        ├── .section-header — dot coloré + nom app
        ├── .subsection "Logos"
        │   └── .logos-grid — logo vertical + logo horizontal
        ├── .subsection "Icônes"
        │   └── .icons-row — 6 .icon-item (taille + label)
        └── .subsection "Mockup iOS/macOS"
            └── .mockup-row — 4 formes
```

---

## CSS Variables par app (inline sur `.app-section`)

Chaque section reçoit ses couleurs en inline style, issues directement de `OTTER_APPS_BRAND_GUIDE.md` :

| Variable | Usage |
|----------|-------|
| `card_bg` | Fond des conteneurs logos/icônes |
| `border` | Bordure des conteneurs |
| `glow` | `box-shadow` au hover |
| `name_color` | Couleur de "Otter" dans le nom |
| `accent2` | Couleur du mot-clé (ex. "Flow", "Forge"…) |
| `badge_bg/t/b` | Badge catégorie |
| `primary` | Dot de section, border-left du label |

---

## Images sources

| App | Fichier projet | Style |
|-----|---------------|-------|
| OtterFlow | `OtterFlow_Image.jpg` | Linogravure, fond teal, loutre + casque + coquillage |
| OtterForge | `OtterForge_Image.jpg` | Gravure sépia, loutre + marteau + enclume |
| OtterLore | `OtterLore_Image.jpg` | Aquarelle mauve, loutre + livre ancien |
| OtterHolt | `OtterHolt_Image.jpg` | Aquarelle mousse, loutre + balais |
| OtterStash | `OtterStash_Image.jpg` | Aquarelle sombre, loutre + pierre dorée |
| OtterQuill | `OtterQuill_Image.jpg` | Aquarelle bleu nuit, loutre + plume + parchemin |

Images intégrées en **base64** dans le HTML — aucune dépendance fichier externe.

---

## Typographies utilisées

| App | Police | Style appliqué |
|-----|--------|---------------|
| OtterFlow | Josefin Sans | weight 300, uppercase, letter-spacing 0.3em |
| OtterForge | Cinzel | weight 600, letter-spacing 0.1em |
| OtterLore | Cormorant Garamond | weight 600, italic, letter-spacing 0.04em |
| OtterHolt | Lora | weight 600, letter-spacing 0.02em |
| OtterStash | Playfair Display | weight 600, letter-spacing 0.06em |
| OtterQuill | IM Fell English | italic, letter-spacing 0.04em |

UI générale : **DM Sans** 300/400/500

---

## Pour régénérer le fichier

Le fichier est généré par le script Python `/tmp/gen_html.py` (non persisté).
Pour le recréer : fournir les 6 JPG sources + ce fichier de contexte à Claude, qui recodera le script.

---

*Samuel · Otter Apps · 2026 🦦*
