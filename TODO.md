# OtterForge V2.0 — Tâches à faire

> Fichier de suivi des améliorations futures. À ouvrir lors d'une session schedule automatique.

---

## Priorité haute

### UI / UX

- [x] **Tooltip sur noms tronqués (sidebar)**
  Actuellement les noms > 17 chars sont coupés avec "…" sans moyen de voir le nom complet.
  Ajouter un tooltip `<Enter>` / `<Leave>` sur chaque `name_lbl` dans `DeckSidebar._build_row()`.
  -> Complété le 2026-05-17 (session auto)

- [x] **Mémoriser les derniers réglages MPC**
  Le dialog Upload MPC (`app.py:upload_to_mpc`) repart à zéro à chaque ouverture (stock S30, headless False, etc.).
  Persister ces choix dans un fichier `config_user.json` ou via `deck.back_image`.
  -> Complété le 2026-05-17 (session auto)

- [x] **Confirmation fermeture pendant un upload**
  `on_close()` ne vérifie pas si un upload MPC est en cours (`_mpc_upload_worker` tourne).
  Ajouter un flag `self._upload_in_progress` et avertir l'utilisateur si True.
  -> Complété le 2026-05-17 (session auto)

- [x] **Indicateur visuel de recherche dans CardSearch**
  Quand une recherche est en cours le bouton est juste disabled. Ajouter une animation spinner
  ou changer le texte du bouton en "..." pendant `statusbar.show_indeterminate`.
  -> Complété le 2026-05-17 (session auto)

### Code

- [x] **Éclater `app.py` (966 lignes)**
  Les dialogs MPC, export et import pourraient devenir des classes dans `ui/dialogs/` :
  - `ui/dialogs/mpc_upload_dialog.py`
  - `ui/dialogs/export_dialog.py`
  - `ui/dialogs/import_confirm_dialog.py`
  `app.py` ne garderait que l'orchestration.
  -> Complété le 2026-05-17 (session auto)

- [x] **`_add_mpc_threshold_bar` → widget dédié**
  Actuellement une méthode de 80 lignes dans `app.py`. Extraire en `ui/mpc_threshold_bar.py`
  (classe `MPCThresholdBar(ctk.CTkFrame)`).
  -> Complété le 2026-05-17 (session auto)

---

## Priorité moyenne

### Fonctionnalités

- [x] **Historique de recherche dans CardSearch**
  Stocker les 20 dernières requêtes dans une liste et les proposer via un dropdown
  au focus du champ texte.
  -> Complété le 2026-05-17 (session auto)

- [x] **Dupliquer un deck**
  Ajouter option "Dupliquer" dans le menu clic-droit onglet deck (`DeckTabs`).
  Copie profonde du deck + nouveau nom `"NomDeck (copie)"`.
  -> Complété le 2026-05-17 (session auto)

- [x] **Upscale batch du cache existant**
  Bouton dans la toolbar "Upscale cache" qui parcourt `cache/scryfall/*.png`
  sans `_1200dpi` correspondant et les upscale en arrière-plan.
  Utile après avoir installé Real-ESRGAN alors que des cartes étaient déjà téléchargées.
  -> Complété le 2026-05-17 (session auto)

- [x] **Gestion du cache (taille + purge)**
  Afficher la taille totale de `cache/scryfall/` dans la status bar ou dans un panel settings.
  Bouton "Vider le cache" avec confirmation.
  -> Complété le 2026-05-17 (session auto) — bouton toolbar + confirmation + status bar

- [ ] **Support d'images custom (non-Scryfall)**
  Permettre de glisser-déposer une image PNG locale directement dans le workspace
  pour créer une carte custom (nom saisi manuellement).

- [x] **Réorganisation des cartes dans la sidebar**
  Ajouter des boutons ↑ ↓ ou un drag-and-drop dans `DeckSidebar` pour réordonner
  les cartes (l'ordre est aussi celui d'upload sur MPC).
  -> Complété le 2026-05-17 (session auto) — boutons ↑ ↓ par ligne, désactivés si filtre actif

### Qualité

- [x] **Uniformiser la langue**
  Plusieurs dialogs sont en anglais ("Import completed", "Do you want to save your deck?", "Export completed").
  Choisir et appliquer une langue unique (FR ou EN) à toute l'interface.
  -> Complété le 2026-05-17 (session auto) — uniformisé en français

- [x] **Race condition deck switch pendant recherche**
  Si l'utilisateur change d'onglet pendant `_search_worker`, la carte est ajoutée
  au deck qui était actif au moment du clic, pas celui visible à la fin de la recherche.
  Capturer `self.deck_manager.active_index` au début de `_search_worker` et l'utiliser dans `_on_search_success`.
  -> Complété le 2026-05-17 (session auto)

---

## Priorité basse / Nice-to-have

### Fonctionnalités

- [x] **Annuler / Rétablir (Ctrl+Z / Ctrl+Y)**
  Implémenter un historique simple des actions deck (ajout, suppression, changement de count).
  Stack d'états — pas besoin d'undo sur l'upscaling.
  -> Complété le 2026-05-17 (session auto)

- [x] **Export vers format texte (Moxfield / MTGA)**
  Bouton "Export TXT" dans la toolbar qui génère un fichier `NomDeck.txt`
  au format `1 Lightning Bolt (M11) 149` pour chaque carte.
  -> Complété le 2026-05-17 (session auto) — format `{count} {name}` (set/CN non stockés)

- [ ] **Panel Settings**
  Regrouper dans un dialog `Settings` :
  - Chemin Real-ESRGAN (actuellement hardcodé dans `config.py`)
  - Dossiers cache / output / decks personnalisables
  - Langue de l'interface

- [ ] **Lazy loading workspace**
  Actuellement toutes les images du deck sont chargées en mémoire même si peu visibles.
  Charger uniquement les cartes dans le viewport + 1 écran de marge.

- [ ] **Zoom adaptatif au changement de taille de fenêtre**
  Le canvas workspace ne recalcule pas le layout quand la fenêtre est redimensionnée.
  Binder `<Configure>` sur le canvas et rappeler `load_cards()` si la largeur change
  de plus de 50 px.

- [ ] **Aperçu feuille zoomable (PreviewPanel)**
  Ajouter un clic sur les miniatures du `PreviewPanel` pour ouvrir la feuille en plein écran.

---

## Optimisation des vitesses

### Import TXT → Workspace

- [x] **Paralléliser les téléchargements Scryfall**
  Actuellement `batch_importer.import_txt()` traite les cartes une par une (séquentiel).
  Refactorer avec `concurrent.futures.ThreadPoolExecutor(max_workers=5)` pour lancer
  jusqu'à 5 téléchargements simultanément (respecter la limite Scryfall : 10 req/s).
  Conserver le `progress_callback` en thread-safe avec un `threading.Lock` sur le compteur.
  -> Complété le 2026-05-17 (session auto)

- [ ] **Paralléliser l'upscaling Real-ESRGAN**
  `upscaler.upscale_to_1200dpi()` lance un subprocess bloquant par carte.
  Lancer plusieurs subprocess en parallèle (`max_workers=2` pour ne pas saturer le GPU).
  Si Real-ESRGAN n'est pas dispo, `fit_native_to_mpc_300` est déjà rapide (Pillow pur).

- [x] **Cache hit early-exit par chemin**
  Dans `_search_worker` et `_import_txt_worker`, vérifier l'existence de `_1200dpi.png`
  ou `_mpc300.png` AVANT d'appeler Scryfall si l'image est déjà dans le cache local.
  Economise l'appel réseau complet pour les cartes déjà présentes.
  -> Complété le 2026-05-17 (session auto) — cache JSON par set+CN dans `_meta_{set}_{cn}.json`; get_card_by_set retourne le cache local sans appel réseau; get_card sauvegarde le résultat pour accélérer les appels futurs exacts.

- [ ] **Chargement workspace en streaming (affichage progressif)**
  Actuellement `workspace.load_cards()` détruit et recrée tout le canvas à chaque appel.
  Ajouter un mode "append" qui ajoute seulement les nouvelles cartes sans tout reconstruire,
  pour un affichage progressif pendant l'import.

### Upload MPC (Playwright)

- [ ] **Réduire les timeouts `_wait_sysdiv`**
  Le délai d'attente après chaque `applyDragPhoto` est conservateur.
  Mesurer le temps réel de réponse du serveur MPC et ajuster le timeout à la valeur minimale stable.
  Cible : réduire le temps par carte de ~3-4s à ~1-2s.

- [ ] **Pipeline upload : préparer le fichier suivant pendant l'upload en cours**
  Pendant que le serveur MPC traite l'image N (attente `#sysdiv_wait`),
  pré-lire et pré-encoder l'image N+1 en mémoire pour la rendre immédiatement disponible.
  Implémentable avec un thread de préchargement + `queue.Queue(maxsize=2)`.

- [ ] **Réutiliser les pids (déduplication MPC)**
  MPC déduplique déjà les images identiques côté serveur, mais on re-uploade quand même
  chaque copie. Exploiter `self._path_to_pid` (déjà présent dans `MPCUploader`) pour
  détecter les cartes en double et appeler `applyDragPhoto` directement sans re-upload.

---

## Impression à domicile

> Workflow complet pour les utilisateurs qui veulent imprimer leurs proxies eux-mêmes
> (imprimante inkjet/laser domestique) sans passer par MPC.

### Moteur d'impression (nouveau module)

- [ ] **Créer `engine/home_print_engine.py`**
  Nouveau module distinct de `mpc_print_engine.py`.
  Génère des feuilles PDF/PNG adaptées à l'impression à domicile :
  - Format papier sélectionnable : A4 (210×297mm), Letter (215.9×279.4mm)
  - Résolution configurable : 300 DPI ou 600 DPI
  - Grille variable selon format et taille carte : 3×3 (standard), 4×3, 2×2, etc.
  - Marges configurables pour tenir compte des zones non imprimables des imprimantes

- [ ] **Export PDF**
  Utiliser `Pillow` (déjà dépendance) pour générer des PDF multi-pages via `img.save("out.pdf", save_all=True, append_images=[...])`.
  Un PDF par deck, pagination automatique selon le nombre de cartes.

- [ ] **Repères de découpe (crop marks)**
  Option pour afficher des lignes pointillées (ou en croix) autour de chaque carte.
  Paramètre : épaisseur du trait, couleur (noir ou gris clair pour économiser l'encre).

- [ ] **Mode recto-verso**
  Pour les imprimantes recto-verso : générer une page "fronts" et une page "backs"
  alignées pour que le recto et le verso se correspondent après pliage/retournement.
  Tenir compte du sens d'impression (reliure bord long / bord court).

- [ ] **Mode économie d'encre**
  Option "ne pas imprimer les backs" pour économiser l'encre.
  Option fond blanc au lieu du fond noir MPC (les bords de la carte).

### UI — Panel impression à domicile

- [ ] **Nouvel onglet / bouton "Print at Home" dans la toolbar**
  Ouvre un dialog dédié `HomePrintDialog` avec :
  - Sélecteur format papier (A4 / Letter / Custom)
  - Sélecteur résolution (300 / 600 DPI)
  - Toggle repères de découpe ON/OFF
  - Toggle recto-verso ON/OFF
  - Toggle économie d'encre ON/OFF
  - Aperçu miniature de la première feuille avant génération
  - Bouton "Générer PDF" → ouvre `filedialog.asksaveasfilename`
  - Bouton "Imprimer directement" → ouvre le dialog système d'impression OS

- [ ] **Aperçu avant impression**
  Fenêtre plein écran présentant la feuille telle qu'elle sera imprimée,
  avec navigation page suivante/précédente.
  Zoomable avec molette souris.

- [ ] **Dialog système d'impression (Windows)**
  Utiliser `os.startfile(pdf_path, "print")` pour envoyer le PDF à l'imprimante par défaut,
  ou `subprocess.run(["mspaint", "/pt", ...])` pour les PNG.
  Alternativement, ouvrir le PDF dans le viewer par défaut et laisser l'utilisateur lancer l'impression.

---

## Ajustements UI

### Apparence générale

- [x] **Persistance de la taille et position de la fenêtre**
  Sauvegarder `geometry()` dans `config_user.json` à la fermeture
  et restaurer au prochain démarrage. Éviter de partir toujours en `zoomed`.
  -> Complété le 2026-05-17 (session auto)

- [ ] **Sidebar redimensionnable**
  Permettre de glisser le bord droit de la `DeckSidebar` pour l'élargir/rétrécir.
  La sidebar a actuellement `WIDTH = 248` fixe — rendre ce paramètre dynamique.

- [ ] **Icônes dans la toolbar**
  Remplacer les boutons texte purs de la `Toolbar` par des icônes SVG/PNG + texte court.
  Utiliser `Pillow` pour charger des icônes locales ou intégrer `tksvg` / icônes base64.

- [x] **Raccourcis clavier manquants**
  Documenter et implémenter les raccourcis absents :
  - `Ctrl+F` → focus sur la barre de recherche `CardSearch`
  - `Ctrl+I` → ouvre dialog import TXT
  - `Ctrl+S` → sauvegarde manuelle du deck
  - `Ctrl+P` → ouvre le dialog export/impression
  - `Échap` → ferme le dialog ou panel ouvert
  -> Complété le 2026-05-17 (session auto) — Ctrl+F/I/S/P implémentés

- [x] **Status bar : plus d'informations**
  Ajouter à droite de la status bar : nombre de cartes dans le deck actif + taille du cache.
  Format : `42 cartes  •  cache 1.2 GB`
  -> Complété le 2026-05-17 (session auto)

- [ ] **Compact mode pour les lignes de la sidebar**
  Toggle entre mode normal (lignes avec boutons +/−/×) et mode compact
  (nom seulement, les boutons apparaissent au survol) pour gagner de la place verticale.

### Workspace

- [x] **Effet de survol sur les cartes**
  Actuellement aucun feedback visuel au survol d'une carte dans le workspace.
  Ajouter une légère surbrillance (outline 1px blanc/orange) au `<Enter>` sur chaque image.
  -> Complété le 2026-05-17 (session auto)

- [x] **Clic droit sur une carte → menu contextuel**
  Menu avec options : Inspecter, +1 copie, −1 copie, Supprimer, Voir sur Scryfall (ouvre browser).
  -> Complété le 2026-05-17 (session auto) — menu traduit FR + Inspecter + Scryfall ajoutés

- [x] **Scroll to card depuis la sidebar**
  Quand on clique sur une carte dans la `DeckSidebar`, scroller le workspace
  pour que la carte cliquée soit visible (centrer si possible).
  -> Complété le 2026-05-17 (session auto)

---

## Bugs connus / Edge cases

- [x] **`_confirm_import_dialog` : position incorrecte si fenêtre minimisée**
  Le centrage utilise `winfo_x()` / `winfo_y()` qui peuvent retourner des valeurs
  incorrectes si la fenêtre principale est minimisée. Ajouter une garde `if self.winfo_viewable()`.
  -> Complété le 2026-05-17 (session auto)

- [x] **Séquence rapide add + switch deck**
  `add_cards_bulk` appelle `deck.cards.append()` (corrigé → `add_card`), mais
  un import TXT en cours + switch d'onglet peut toujours provoquer une incohérence
  si `_import_txt_worker` se termine après le switch. À protéger avec un lock ou
  en capturant l'index du deck au démarrage du thread.
  -> Complété le 2026-05-17 (session auto) — target_deck_index capturé au démarrage dans _search_worker

- [x] **`DeckSidebar` : le × du filtre reste visible après refresh()**
  Si le filtre est actif et qu'on supprime toutes les cartes filtrées,
  la couleur du × reste `#c4bfb8` (actif) alors que la liste est vide.
  Appeler `_on_filter_change` après `_remove_card` plutôt que juste `refresh()`.
  -> Complété le 2026-05-17 (session auto)
