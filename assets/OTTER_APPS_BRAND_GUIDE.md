# Otter Apps — Brand Guide & Contexte de Développement
*Document de référence pour Claude Code — Samuel 2026*

---

## 🦦 Vue d'ensemble

**Otter Apps** est une famille de 4 applications personnelles développées par Samuel.
Chaque app partage une identité visuelle cohérente basée sur des **illustrations de loutres aquarelle/gravure**, des **fonds sombres**, et des **palettes de couleurs distinctes par app**.

Le style général est : **artisanal · professionnel · sombre · organique**

---

## 📱 Les applications

### 1. 🎵 OtterFlow
- **Fonction** : Lecteur/streamer de musique (Spotify-like, basé sur Navidrome + yt-dlp)
- **Tagline** : *"Your music, flowing freely."*
- **Badge** : `Musique · Stream`

### 2. 🃏 OtterForge
- **Fonction** : Convertisseur d'images Magic: The Gathering en proxies imprimables
- **Tagline** : *"Craft every card, your way."*
- **Badge** : `MTG · Proxy Forge`

### 3. 📚 OtterLore
- **Fonction** : Bibliothèque personnelle — listes de livres, notes, notations
- **Tagline** : *"Every story worth keeping."*
- **Badge** : `Livres · Bibliothèque`

### 4. 🏠 OtterHolt
- **Fonction** : Gestionnaire de tâches ménagères
- **Tagline** : *"A tidy holt, a happy otter."*
- **Badge** : `Maison · Tâches`

### 5. 📦 OtterStash
- **Fonction** : Stockage et gestion de collection personnelle
- **Tagline** : *"Keep what matters, find it always."*
- **Badge** : `Stockage · Collection`

### 6. 🪶 OtterQuill
- **Fonction** : Prise de notes rapide et ordonnée — texte, listes, tags, et notes vocales avec transcription automatique
- **Tagline** : *"Your thoughts, inked and ordered."*
- **Badge** : `Notes · Journal`

---

## 🎨 Palettes de couleurs

### OtterFlow — Teal / Océan
```
Primaire      : #2d7d7a
Accent        : #4ab5b0
Clair         : #d0f0ee
Fond carte    : #0a1f1e
Bordure       : rgba(45, 125, 122, 0.22)
Glow          : rgba(45, 125, 122, 0.16)
Texte nom     : #c8f0ec
Texte tagline : rgba(200, 240, 236, 0.38)
Badge bg      : rgba(45, 125, 122, 0.20)
Badge texte   : #7ececa
Badge bordure : rgba(45, 125, 122, 0.32)
```

### OtterForge — Or / Charbon
```
Primaire      : #d4a843
Accent        : #c8902a
Clair         : #f0e0a0
Fond carte    : #0f0b05
Bordure       : rgba(212, 168, 67, 0.18)
Glow          : rgba(212, 168, 67, 0.13)
Texte nom     : #f0dfa0
Texte tagline : rgba(240, 223, 160, 0.36)
Badge bg      : rgba(212, 168, 67, 0.13)
Badge texte   : #d4a843
Badge bordure : rgba(212, 168, 67, 0.28)
```

### OtterLore — Mauve / Bordeaux
```
Primaire      : #8c50b4
Accent        : #b070d8
Clair         : #e8d0f8
Fond carte    : #0d0818
Bordure       : rgba(140, 80, 180, 0.20)
Glow          : rgba(120, 60, 180, 0.18)
Texte nom     : #d8b8f8
Texte tagline : rgba(200, 160, 240, 0.38)
Badge bg      : rgba(140, 80, 180, 0.15)
Badge texte   : #c090e8
Badge bordure : rgba(140, 80, 180, 0.28)
```

### OtterHolt — Vert-jaune mousse
```
Primaire      : #7a8c18
Accent        : #a0b830
Clair         : #d0e060
Fond carte    : #0e1402
Bordure       : rgba(120, 140, 30, 0.22)
Glow          : rgba(120, 140, 30, 0.16)
Texte nom     : #b8d890
Texte tagline : rgba(200, 200, 120, 0.38)
Badge bg      : rgba(90, 120, 50, 0.15)
Badge texte   : #a0c870
Badge bordure : rgba(90, 120, 50, 0.28)
```

### Fond global (toutes apps)
```
Background body : #080e10
Fond sombre     : #0d0a14
```

---

## 🔤 Typographies

| App | Police | Style | Taille recommandée |
|-----|--------|-------|-------------------|
| OtterFlow | Josefin Sans | Light (300), uppercase, letter-spacing: 0.3em | 2.2rem |
| OtterForge | Cinzel | Semibold (600), letter-spacing: 0.1em | 2.2rem |
| OtterLore | Cormorant Garamond | Semibold Italic (600), letter-spacing: 0.04em | 2.3rem |
| OtterHolt | Lora | Semibold (600), letter-spacing: 0.02em | 2.2rem |
| OtterStash | Playfair Display | Semibold (600), letter-spacing: 0.06em | 2.2rem |
| OtterQuill | IM Fell English | Regular Italic, letter-spacing: 0.04em | 2.4rem |

**Import Google Fonts :**
```html
<link href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@200;300;400;600&family=Cinzel:wght@400;600;700&family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400;1,600&family=Lora:ital,wght@0,400;0,600;1,400&family=Playfair+Display:ital,wght@0,400;0,600;1,400;1,600&family=IM+Fell+English:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
```

**Police UI générale (labels, textes courants) :** `DM Sans` — poids 300/400/500

---

## 🃏 Composant Badge (commun à toutes les apps)

```css
.badge {
  font-size: 0.56rem;
  font-weight: 500;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  padding: 0.22rem 0.8rem;
  border-radius: 20px;
}
```

---

## 🖼️ Style des cartes / conteneurs

```css
.card {
  border-radius: 24px;
  overflow: hidden;
  transition: transform 0.4s cubic-bezier(.2,.8,.3,1), box-shadow 0.4s ease;
}
.card:hover {
  transform: translateY(-6px);
}
```

**Section labels (titres de section) :**
```css
.section-label {
  font-size: 0.58rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  padding-left: 0.7rem;
  border-left: 2px solid <couleur-app>;
}
.section-label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255,255,255,0.05);
}
```

---

## 📐 Espacements & Layout

```
Padding body       : 3-4rem 1.5rem
Gap entre sections : 5rem
Border-radius card : 24px
Border-radius icon : 22.5% (arrondi), 50% (cercle), 28% (squircle/iOS)
Max-width contenu  : 900px (desktop), 480px (single column)
```

---

## 🌑 Effets visuels récurrents

**Gradient de fondu image → fond de carte :**
```css
/* Exemple OtterFlow */
background: linear-gradient(
  to top,
  #0a1f1e 0%,
  rgba(10, 31, 30, 0.75) 45%,
  transparent 100%
);
height: 60%;
```

**Glow au hover :**
```css
box-shadow: 0 24px 80px rgba(0,0,0,0.5),
            0 0 100px <couleur-glow-app>;
```

**Bruit de texture (optionnel, subtil) :**
```css
opacity: 0.025;
background-image: url("data:image/svg+xml,...fractalNoise...");
```

---

## 🦦 Illustrations

Chaque app possède une illustration de loutre en style **aquarelle/gravure artisanale** :

| App | Accessoire | Style illustration |
|-----|-----------|-------------------|
| OtterFlow | Coquillage nautile teal | Linogravure, tons teal |
| OtterForge | Caillou de rivière | Gravure ancienne, tons or/sépia |
| OtterLore | Livre ancien ouvert | Aquarelle, halo mauve/bordeaux |
| OtterHolt | Balai en bois | Aquarelle, fond vert-jaune mousse |
| OtterStash | Caillou/Pierre dorée | Aquarelle sombre, fond noir organique, touches dorées |
| OtterQuill | Grande plume d'oie | Aquarelle sombre, parchemin vieilli, tons bleu nuit, halo indigo |

Les illustrations sont des fichiers JPG générés via Bing Image Creator (DALL-E 3).
Les images sont intégrées en **base64** dans les fichiers HTML pour éviter les dépendances externes.

---

## 🗂️ Fichiers de référence

- `otter-logos-final.html` — Logos finaux OtterFlow + OtterForge
- `otter-icons-final.html` — Icônes OtterFlow + OtterForge (toutes tailles + mockups)
- `otterlore-otterholt-logos.html` — Logos OtterLore + OtterHolt
- `otterlore-otterholt-icons.html` — Icônes OtterLore + OtterHolt
- `otterstash-logo.html` — Logo principal OtterStash + version horizontale
- `otterstash-icons.html` — Icônes OtterStash toutes tailles + mockups
- `otterquill-logo.html` — Logo principal OtterQuill + version horizontale
- `otterquill-icons.html` — Icônes OtterQuill toutes tailles + mockups
- `App_Musique_Youtube_A_Distance.docx` — Architecture technique OtterFlow

---

## ⚙️ Stack technique (OtterFlow — seule app avec architecture complète définie)

| Composant | Outil | Rôle |
|-----------|-------|------|
| Téléchargement audio | yt-dlp + ffmpeg | Extraire audio YouTube → MP3 |
| Automatisation | Python | Surveiller playlists, auto-télécharger |
| Serveur musique | Navidrome | Streamer via protocole Subsonic |
| Accès distant | Tailscale | VPN gratuit (≤3 appareils) |
| App mobile | DSub / Symfonium | Android, protocole Subsonic |

---

## 📝 Notes de style général

- **Pas de fond blanc** — tout est sur fond sombre
- **Pas de couleurs vives saturées** — palettes désaturées, organiques
- **Animations subtiles** — transitions lentes (0.4s), pas d'effets agressifs
- **Typographie sobre** — peu de niveaux hiérarchiques, espacement généreux
- **Cohérence famille** — même structure de composants pour toutes les apps, seules les couleurs et polices changent par app

---

*Samuel · Otter Apps · 2026 🦦*

---

## 📦 OtterStash *(ajout)*

- **Fonction** : Stockage et gestion de collection personnelle
- **Tagline** : *"Keep what matters, find it always."*
- **Badge** : `Stockage · Collection`

### Palette — Cuivré / Brun sombre
```
Primaire      : #b56a3a
Accent        : #d4884a
Clair         : #f0d0a0
Fond carte    : #140a04
Fond body     : #050a0c
Bordure       : rgba(181, 106, 58, 0.22)
Glow          : rgba(181, 106, 58, 0.16)
Texte nom     : #f0d0a0  (Otter) + #d4884a (Stash)
Texte tagline : rgba(240, 208, 160, 0.38)
Badge bg      : rgba(181, 106, 58, 0.13)
Badge texte   : #d4884a
Badge bordure : rgba(181, 106, 58, 0.28)
Section label : #7a6040
```

### Typographie
| Élément | Police | Style |
|---------|--------|-------|
| Nom app | Playfair Display | Semibold (600), letter-spacing: 0.06em |
| Nom bicolore | *Otter* → `#f0d0a0` / *Stash* → `#d4884a` | — |
| Tagline | Playfair Display | Italic, font-size: 13px |
| UI générale | DM Sans | 300/400/500 |

### Illustration
| Accessoire | Style |
|-----------|-------|
| Caillou/Pierre dorée | Aquarelle sombre, fond noir organique, touches dorées |

### Fichiers de référence
- `otterstash-logo.html` — Logo principal + version horizontale
- `otterstash-icons.html` — Icônes toutes tailles + mockups

---

## 🪶 OtterQuill *(ajout)*

- **Fonction** : Prise de notes rapide et ordonnée — texte, listes, tags, et notes vocales avec transcription automatique
- **Tagline** : *"Your thoughts, inked and ordered."*
- **Badge** : `Notes · Journal`

### Palette — Encre / Ardoise
```
Primaire      : #2a4d8a
Accent        : #5a8fd4
Clair         : #c8dcf4
Fond carte    : #050c18
Fond body     : #020810
Bordure       : rgba(42, 77, 138, 0.25)
Glow          : rgba(42, 77, 138, 0.18)
Texte nom     : #c8dcf4  (Otter) + #5a8fd4 (Quill)
Texte tagline : rgba(180, 210, 250, 0.42)
Badge bg      : rgba(42, 77, 138, 0.18)
Badge texte   : #7aaad8
Badge bordure : rgba(42, 77, 138, 0.35)
Section label : #3a5a8c
```

### Typographie
| Élément | Police | Style |
|---------|--------|-------|
| Nom app | IM Fell English | Regular Italic, letter-spacing: 0.04em |
| Nom bicolore | *Otter* → `#c8dcf4` / *Quill* → `#5a8fd4` | — |
| Tagline | IM Fell English | Italic, font-size: 13px |
| UI générale | DM Sans | 300/400/500 |

### Fonctionnalités principales
- **Notes texte rapides** — capture on-the-go, Windows & mobile
- **Listes & checklists** — todo lists, listes imbriquées, état de complétion
- **Tags & catégories** — classification manuelle + classification automatique par IA
- **Notes vocales** — enregistrement → transcription (Whisper) → classement automatique (Claude API)

### Illustration
| Accessoire | Style |
|-----------|-------|
| Grande plume d'oie / calligraphie | Aquarelle sombre mêlant parchemin vieilli et tableau de liège. Tons bleu nuit, encre bleue, touches de cire à cacheter. Halo bleu indigo. Style gravure ancienne avec lavis aquarelle. |

### Stack technique envisagé
| Composant | Outil | Rôle |
|-----------|-------|------|
| Backend | Python / FastAPI | API, stockage et sync des notes |
| Transcription vocale | Whisper (OpenAI, local) | Audio → texte |
| Classification auto | Claude API | Catégorisation intelligente des notes |
| Stockage | SQLite | Base locale légère |
| Interface | PWA ou React Native | Windows + mobile (cross-platform) |
| Accès distant | Tailscale | Sync PC ↔ mobile (comme OtterFlow) |

### Fichiers de référence
- `otterquill-logo.html` — Logo principal + version horizontale
- `otterquill-icons.html` — Icônes toutes tailles + mockups

---

*Mis à jour — Samuel · Otter Apps · 2026 🦦*
