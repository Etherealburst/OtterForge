# HANDOFF — OtterForge V2.0

**Date :** 2026-05-14  
**Fichier à lire en premier :** `engine/mpc_uploader.py`  
**Référence :** `CLAUDE.md` (architecture complète du projet)

---

## Contexte du projet (ultra-court)

Application Python (customtkinter) qui upload des decks proxy MTG sur MakePlayingCards.com via Playwright (Chromium headless/visible). Le flux upload est dans `engine/mpc_uploader.py`, classe `MPCUploader`.

---

## État actuel : TOUT FONCTIONNE ✅

L'upload complet (fronts → backs → page de révision) est opérationnel depuis le 2026-05-14.

---

## Ce qui a été corrigé dans cette session

### 1. Bleed / pointillé rouge MPC (`engine/upscaler.py`) ✅

**Problème :** Les cartes "dépassaient le pointillé rouge" dans l'éditeur MPC. La fonction `_fit_to_mpc` utilisait **scale-to-cover + crop**, ce qui étirait la carte pour remplir toute la zone de fond perdu — le contenu de la carte (bordure noire incluse) dépassait la ligne de coupe (trim line = pointillé rouge).

**Correction appliquée :**  
`_fit_to_mpc` utilise maintenant **scale-to-fit dans la zone de coupe + canvas noir** (fond perdu = noir uni, ce qui correspond aux bordures Magic).

- 1200 DPI (images upscalées) : carte ~3000×4188 centrée dans un canvas 3288×4488, entourée de 144 px de noir.
- 300 DPI (images natives Scryfall) : nouvelle méthode `fit_native_to_mpc_300()` → carte ~750×1047 dans 822×1122.

**Fichiers modifiés :**  
- `engine/upscaler.py` — `_fit_to_mpc()` réécrit, `fit_native_to_mpc_300()` ajouté  
- `engine/batch_importer.py` — appelle `fit_native_to_mpc_300()` quand upscaler absent  
- `ui/app.py` — même logique dans `_search_worker` pour les cartes ajoutées unitairement

**⚠ Important :** Les `_1200dpi.png` déjà en cache ont l'ANCIEN format (scale-to-cover). Il faut les supprimer dans `cache/scryfall/` pour forcer le re-upscale. Les imports TXT batch re-upscalent toujours → auto-corrigés. Les cartes ajoutées via la barre de recherche ne re-upscalent que si `_1200dpi.png` est absent.

---

### 2. Viewport navigateur (`engine/mpc_uploader.py`) ✅

**Problème :** La fenêtre MPC s'ouvrait décalée à droite / ne prenait pas tout l'écran. Playwright ignorait `--start-maximized` parce que `viewport` était forcé à `{"width": 1920, "height": 1080}`.

**Correction :** `page = browser.new_page(viewport=None)` — le navigateur utilise maintenant la vraie taille maximisée.

---

### 3. ETA dans le dialog "Upload to MPC" (`ui/app.py`) ✅

Ajout d'une ligne de temps estimé sous la barre de seuils MPC :  
`~{N} min  (fronts ~X min + backs ~Y min)`  
Formule : ~35s/slot fronts + ~20s/slot backs + 3 min overhead.

---

### 4. Upload bloqué au step 1 (Customize Front → Customize Back) ✅ RÉSOLU

#### Symptôme
Après l'upload de toutes les cartes recto (~129 cartes), le flux MPC restait bloqué à la page "Customize Front" et ne passait jamais à "Customize Back". Les logs montraient :

```
[MPC] MPC idle — sysdiv_wait caché
[MPC] oDesign.setNextStep() — attente navigation (max 10 min)…
[MPC] ⚠ setNextStep (page): Timeout 600000ms exceeded.
```

#### Historique des tentatives (ce qui n'a PAS marché)

**Tentative 1 — Augmenter le timeout + wait_for_url**  
Augmenter le timeout à 600s et remplacer `expect_navigation` par `wait_for_url`. L'URL ne changeait jamais. `wait_for_url` rate les navigations déclenchées pendant l'évaluation JS. Revenu à `expect_navigation`.

**Tentative 2 — `_post_complete_sources` avant setNextStep (partiellement)**  
Hypothèse : MPC ne connaissait que le dernier slot. On a forcé un POST manuel à `dn_update_transition_data.aspx` avec tous les slots capturés, puis forcé `btn_next_step` visible via CSS. Le bouton était bien forcé visible, `setNextStep()` était appelé, mais **aucune navigation ne se produisait**. Timeout 10 min. → Cause identifiée : le `confirm()` dialog.

**Tentative 3 — Restructurer `_advance_to_back` (dans le mauvais ordre)**  
On a déplacé `_post_complete_sources` en **dernier recours** (étape 4) pour "éviter les conflits AJAX". C'était l'erreur : sans `_post_complete_sources` en étape 2, `btn_next_step` reste désactivé côté serveur → `setNextStep()` ne fait rien → timeout.

#### Cause réelle (deux problèmes combinés)

**Problème A — Accumulation des slots côté serveur (principal)**  
Chaque `applyDragPhoto` fait un POST à `dn_update_transition_data.aspx` avec un `hidd_image_list` d'un seul élément. Après 129 uploads, le serveur ne connaît que le **dernier slot**. `btn_next_step` reste désactivé jusqu'à ce que tous les slots soient déclarés.

Vérifié dans les logs réseau :
```
[hidd_image_list] = [{"ID":"50BFDFDE..."}]  ← seulement slot 17
[hidd_image_list] = [{"ID":"FC43CC7F..."}]  ← seulement slot 18
```

**Problème B — Dialog `confirm()` JS (secondaire)**  
MPC affiche un `confirm()` JS lors du passage d'étape. mpc-autofill (Selenium) fait `alert.accept()`. Playwright **auto-dismiss** les `confirm()` (retourne `false`) sans handler → navigation jamais déclenchée.

Référence mpc-autofill :
```python
driver.execute_script("javascript:oDesign.setNextStep();")
try:
    alert = driver.switch_to.alert
    alert.accept()
except NoAlertPresentException:
    pass
```

#### Correction finale appliquée

Deux changements dans `engine/mpc_uploader.py` :

**1. Handler dialog (au démarrage, ligne ~78 dans `upload()`) :**
```python
page.on("dialog", lambda dialog: dialog.accept())
```

**2. Ordre dans `_advance_to_back` :**
```
1. Attendre sysdiv_wait caché (fin AJAX)
2. _post_complete_sources() ← OBLIGATOIRE EN PREMIER (sauvegarde tous les slots)
3. page.wait_for_timeout(3_000)
4. oDesign.setNextStep() avec expect_navigation ← confirm() géré par handler
5. Fallback : forcer btn_next_step visible + clic
6. Dernier recours : __doPostBack
```

**Règle à ne jamais casser :** `_post_complete_sources` DOIT précéder `setNextStep()`. Si quelqu'un déplace `_post_complete_sources` en fallback ou last-resort, le bug revient.

---

### 5. Ralentissement de l'upload fronts (`engine/mpc_uploader.py`) ✅

**Problème :** Le nouveau `_wait_sysdiv` attendait jusqu'à 1000ms que le spinner apparaisse avant de continuer. Si l'AJAX était très rapide (~100ms), ce timeout expirait à chaque slot → ~2 minutes perdues sur 129 cartes.

**Correction :** Timeout réduit de 1000ms à 300ms (équivalent à l'ancienne attente fixe).

```python
page.wait_for_selector("#sysdiv_wait", state="visible", timeout=300)
```

---

## Architecture rapide — fichiers clés

```
engine/mpc_uploader.py   ← Tout le flux Playwright. Classe MPCUploader.
  upload()               ← Point d'entrée. Dialog handler ICI (ligne ~78).
  _advance_to_back()     ← Transition step 1→2. _post_complete_sources() EN PREMIER.
  _click_next_step()     ← Transition step 2→3 (révision).
  _upload_and_place()    ← Upload image + applyDragPhoto pour un slot.
  _apply_drag_photo()    ← Appelle PageLayout.prototype.applyDragPhoto.
  _wait_sysdiv()         ← Attend fin du spinner MPC (visible→hidden, 300ms timeout).
  _post_complete_sources() ← POST complet à dn_update_transition_data.aspx.

engine/upscaler.py       ← Real-ESRGAN ×4 + _fit_to_mpc (bleed corrigé).
engine/batch_importer.py ← Import TXT/Moxfield. Appelle upscaler.
ui/app.py                ← UI principale. _search_worker, upload_to_mpc dialog.
```

---

## Comportement attendu du flux MPC (succès confirmé)

```
[MPC] Ouverture de MPC…
[MPC] Lancement du design…
[MPC] Préparation éditeur : 126 cartes, stock S30…
[MPC] Upload UI prêt → https://…/dn_playingcards_mode_nf…
[MPC] Front 1/126 — Lightning Bolt
...
[MPC] Front 126/126 — Island
[MPC] MPC idle — sysdiv_wait caché
[MPC] Sauvegarde front (126 slots) → serveur MPC…
[MPC] ✓ front sauvegardé → 200 OK
[MPC] oDesign.setNextStep() — attente navigation (max 10 min)…
[MPC] (setNextStep) → https://…/dn_playingcards_mode_nb…   ← NAVIGATION RÉUSSIE
[MPC] Basculement verso…
[MPC] setMode ImageText same (1) → éditeur back
[MPC] Endos global pid=abc123… → slot 0 (mode same image, MPC réplique)
[MPC] Avancement vers la page de révision…
[MPC] Page de révision : https://…/dn_playingcards_preview…
[MPC] Upload terminé — finalisez la commande dans le navigateur
```

---

## Il ne reste rien à faire

Le projet est fonctionnel bout en bout. Les prochains travaux éventuels seraient :
- Tests de robustesse sur des decks avec DFC (double-face) en upload complet
- Gestion des erreurs réseau MPC (retry automatique)
- Paramétrer le chemin Real-ESRGAN via l'UI au lieu d'un hardcode dans `upscaler.py`
