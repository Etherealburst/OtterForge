"""
engine/mpc_uploader.py
----------------------
Automatise l'upload d'un deck sur makeplayingcards.com via Playwright.

Flux :
  1. Navigue vers la page produit MPC
  2. doPersonalize() → dn_playingcards_front_dynamic.aspx (step 1: Customize Front)
  3. Le vrai éditeur est dans l'iframe sysifm_loginFrame
  4. Uploade chaque image via #uploadId ; récupère le pid via oDesignImage.dn_getImageList()
  5. Assigne chaque pid à son slot via PageLayout.prototype.applyDragPhoto (approche mpc-autofill)
  6. Avance vers le back et répète pour les backs DFC / endos global
  7. Laisse le navigateur ouvert pour finaliser la commande
"""

import json as _json
import os
import math
import urllib.parse as _urlparse

MPC_PRODUCT_URL = (
    "https://www.makeplayingcards.com/design/custom-blank-card-traditional-size.html"
)
MPC_PROCESS_URL = (
    "https://www.makeplayingcards.com/products/pro_item_process_flow.aspx"
)
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_mpc")


class MPCUploader:

    def __init__(self, headless: bool = False, stock: str = "S30"):
        self.headless = headless
        self.stock = stock
        self._oc_initial = None      # hidd_original_count du produit (e.g. '55')
        self._pieces_initial = None  # Pieces dans hpci du step1 initial (e.g. 55)
        self._path_to_pid: dict = {}  # image_path -> pid (survives MPC deduplication)

    # ------------------------------------------------------------------
    # POINT D'ENTRÉE
    # ------------------------------------------------------------------

    def upload(self, cards: list, progress_callback=None, login: bool = False,
               back_image_path: str | None = None, upload_backs: bool = True) -> None:
        try:
            from playwright.sync_api import sync_playwright, Error as PWError
        except ImportError:
            raise ImportError(
                "Playwright n'est pas installé.\n"
                "Exécute dans un terminal :\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        os.makedirs(DEBUG_DIR, exist_ok=True)

        fronts, backs = self._build_slots(cards, global_back=back_image_path)
        total = len(fronts)
        has_backs = any(b is not None for b in backs)
        mpc_qty = self._mpc_quantity(total)

        def cb(current, label):
            if progress_callback:
                progress_callback(current, total, label)
            print(f"[MPC] {label}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                slow_mo=50,
                args=["--start-maximized"],
            )
            page = browser.new_page(viewport=None)
            page.set_default_timeout(30_000)
            # Accepte tous les dialog JS (confirm, alert, prompt) — critique pour setNextStep().
            # MPC affiche un confirm() lors du passage d'étape ; sans accept(), la navigation
            # ne se déclenche jamais et expect_navigation timeout.
            page.on("dialog", lambda dialog: dialog.accept())
            page.on("console", lambda msg: print(f"[BROWSER:{msg.type}] {msg.text[:200]}") if msg.type in ("error", "warning") else None)
            page.on("pageerror", lambda err: print(f"[BROWSER:pageerror] {str(err)[:300]}"))

            def _log_request(request):
                url = request.url
                if "makeplayingcards.com" not in url:
                    return
                # Ignorer analytics Google et ressources statiques
                if any(x in url for x in ("google-analytics", "googletagmanager", "facebook", ".png", ".js", ".css", ".jpg", ".gif", "favicon")):
                    return
                method = request.method
                body = (request.post_data or "") if method == "POST" else ""
                short_url = url.split("makeplayingcards.com")[-1][:100]
                if method == "POST" and ("dn_playingcards_mode_nf" in url or "dn_update_transition_data" in url):
                    print(f"[NET] POST {short_url}")
                    try:
                        params = _urlparse.parse_qs(body, keep_blank_values=True)
                        skip = {"__VIEWSTATE", "__VIEWSTATEGENERATOR"}
                        for k in sorted(params):
                            if k in skip:
                                continue
                            v = params[k][0] if len(params[k]) == 1 else params[k]
                            limit = 2000 if k == "hidd_image_list" else 300
                            print(f"  [{k}] = {str(v)[:limit]}")
                    except Exception:
                        print(f"  raw: {body[:300]}")
                elif method in ("GET", "POST"):
                    print(f"[NET] {method} {short_url}")
                    if body:
                        print(f"  body: {body[:200]}")
            page.on("request", _log_request)

            # Intercepte dn_product_analysis_photo → capture source de chaque slot assigné.
            # Intercepte dn_update_transition_data → apprend la valeur réelle de hiddLayer.
            _front_sources: dict = {}   # slot_idx → {"ID": pid, "Exp": "png", "Path": cdn_url}
            _back_sources: dict = {}
            _in_backs = [False]
            _natural_layer: dict = {}   # "front"/"back" → valeur réelle de hiddLayer

            def _capture_slot_source(request):
                if request.method != "POST":
                    return
                url = request.url
                if "dn_product_analysis_photo" in url:
                    try:
                        body = request.post_data or ""
                        params = _urlparse.parse_qs(body, keep_blank_values=True)
                        idx_list = params.get("photoindex")
                        src_list = params.get("source")
                        if not idx_list or not src_list:
                            return
                        idx = int(idx_list[0])
                        src = _json.loads(src_list[0])
                        if idx >= 0 and src.get("ID"):
                            if _in_backs[0]:
                                _back_sources[idx] = src
                            else:
                                _front_sources[idx] = src
                    except Exception:
                        pass
                elif "dn_update_transition_data" in url:
                    try:
                        body = request.post_data or ""
                        params = _urlparse.parse_qs(body, keep_blank_values=True)
                        layer_val = params.get("hiddLayer", [None])[0]
                        if layer_val is not None:
                            side = "back" if _in_backs[0] else "front"
                            _natural_layer.setdefault(side, layer_val)
                    except Exception:
                        pass

            page.on("request", _capture_slot_source)

            self._path_to_pid = {}

            try:
                # --- 1. Login MPC (optionnel) ---
                if login:
                    cb(0, "Connexion MPC…")
                    self._login_mpc(page)
                    self._screenshot(page, "01_after_login")

                # --- 2. Produit ---
                cb(0, "Ouverture de MPC…")
                page.goto(MPC_PRODUCT_URL, wait_until="domcontentloaded")
                self._accept_cookies(page)
                self._screenshot(page, "02_product_page")

                # --- 3. Start Design ---
                cb(0, "Lancement du design…")
                self._start_design(page)
                self._screenshot(page, "02_after_start_design")

                # --- 3. Attendre que l'éditeur iframe soit prêt ---
                cb(0, f"Préparation éditeur : {mpc_qty} cartes, stock {self.stock}…")
                self._prepare_editor(page, mpc_qty)
                self._screenshot(page, "03_editor_ready")

                # --- 4. Attendre l'UI d'upload dans l'iframe ---
                cb(0, "Chargement de l'éditeur MPC…")
                self._wait_editor(page)
                self._screenshot(page, "04_editor_loaded")

                # --- 5. Upload fronts ---
                for i, slot in enumerate(fronts):
                    cb(i + 1, f"Front {i+1}/{total} — {slot['name']}")
                    self._upload_and_place(page, i, slot["path"])

                # Capturer frame + layer fronts avant toute navigation
                front_frame = self._find_editor_frame(page, timeout=5_000)
                front_layer = _natural_layer.get("front", "front")

                # --- 6. Upload backs ---
                non_none_backs = [b for b in backs if b is not None]
                unique_backs = list(dict.fromkeys(non_none_backs))  # préserve l'ordre
                global_back = len(unique_backs) == 1

                back_frame = None
                back_layer = "back"

                if has_backs and upload_backs:
                    cb(total, "Basculement verso…")
                    self._advance_to_back(page, frame=front_frame, sources=_front_sources, layer=front_layer)
                    # mode=1 (same image) pour endos global — MPC assigne auto à tous les slots.
                    # mode=0 (different images) pour backs DFC/individuels.
                    # Approche identique à mpc-autofill : same_images() vs different_images().
                    back_mode = 1 if global_back else 0
                    self._wait_editor(page, mode=back_mode)
                    _in_backs[0] = True  # Basculer le capteur de sources vers les backs

                    if global_back:
                        cb(total, f"Endos global : {os.path.basename(unique_backs[0])}")
                        self._upload_same_back_to_all(page, unique_backs[0])
                    else:
                        for i, back_path in enumerate(backs):
                            if back_path is None:
                                continue
                            cb(i + 1, f"Back {i+1}/{total} — {fronts[i]['name']}")
                            self._upload_and_place(page, i, back_path)

                    # Capturer frame + layer backs avant navigation vers révision
                    back_frame = self._find_editor_frame(page, timeout=5_000)
                    back_layer = _natural_layer.get("back", "back")

                # Avancer vers la révision (skip étape 4 "Add text to back")
                # Passer le frame et les sources capturées pour forcer la sauvegarde
                # si setNextStep échoue et qu'on tombe en fallback __doPostBack.
                cb(total, "Avancement vers la page de révision…")
                nav_frame = back_frame if back_frame else front_frame
                nav_sources = _back_sources if back_frame else _front_sources
                nav_layer = back_layer if back_frame else front_layer
                self._click_next_step(page, frame=nav_frame, sources=nav_sources, layer=nav_layer)
                page.wait_for_timeout(2_000)
                if "dn_texteditor" in page.url:
                    step_name = "front" if "dn_texteditor_front" in page.url else "back"
                    print(f"[MPC] Étape 'Add text to {step_name}' → skip automatique")
                    self._click_next_step(page)
                    page.wait_for_timeout(2_000)
                print(f"[MPC] Page de révision : {page.url}")

                # Attendre que la page de révision charge les thumbnails
                try:
                    page.wait_for_load_state("networkidle", timeout=30_000)
                except Exception:
                    pass
                # Scroll progressif pour déclencher le lazy-loading des thumbnails
                try:
                    total_h = page.evaluate("() => document.body.scrollHeight")
                    step = 400
                    pos = 0
                    while pos < total_h:
                        page.evaluate(f"window.scrollTo(0, {pos})")
                        page.wait_for_timeout(150)
                        pos += step
                    page.evaluate("window.scrollTo(0, 0)")
                except Exception:
                    pass
                page.wait_for_timeout(3_000)

                cb(total, "Upload terminé — finalisez la commande dans le navigateur")
                self._screenshot(page, "05_done")

                try:
                    page.wait_for_timeout(3_600_000)
                except PWError:
                    pass

            except PWError:
                print("[MPC] Navigateur fermé par l'utilisateur.")
            except Exception as e:
                self._screenshot(page, "error")
                print(f"[MPC] Erreur : {e}")
                raise
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # CONSTRUCTION DES SLOTS
    # ------------------------------------------------------------------

    def _build_slots(self, cards, global_back: str | None = None):
        fronts, backs = [], []
        for card in cards:
            path = self._best_path(card.image_path)
            back_path = None
            # 1. Endos spécifique à la carte (DFC face1 ou override manuel)
            if getattr(card, "back_image_path", None):
                back_path = self._best_path(card.back_image_path)
            # 2. Endos global du deck
            if back_path is None and global_back:
                back_path = global_back
            for _ in range(card.count):
                fronts.append({"name": card.name, "path": path})
                backs.append(back_path)

        return fronts, backs

    def _best_path(self, path):
        if path.endswith("_1200dpi.png"):
            return path
        upscaled = path.replace(".png", "_1200dpi.png")
        return upscaled if os.path.exists(upscaled) else path

    @staticmethod
    def _mpc_quantity(total: int) -> int:
        return max(18, math.ceil(total / 18) * 18)

    @staticmethod
    def total_card_slots(cards) -> int:
        return sum(card.count for card in cards)

    # ------------------------------------------------------------------
    # FRAME HELPERS
    # ------------------------------------------------------------------

    def _get_editor_frame(self, page):
        """Retourne le frame de l'éditeur (iframe dn_playingcards_mode), ignoré si vide."""
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            if "dn_playingcards_mode" in frame.url:
                return frame
        # Fallback par nom, uniquement si l'URL est chargée
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            if frame.name == "sysifm_loginFrame" and frame.url:
                return frame
        return None

    def _wait_for_loaded_frame(self, page, timeout=30_000):
        """
        Attend et retourne le frame dn_playingcards_mode avec du contenu réel
        (bodyLength > 500). Ignore les frames vides ou en cours de chargement.
        """
        steps = max(1, timeout // 1_000)
        for _ in range(steps):
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                if "dn_playingcards_mode" not in frame.url:
                    continue
                try:
                    length = frame.evaluate(
                        "() => document.body ? document.body.innerHTML.length : 0"
                    )
                    if length > 500:
                        return frame
                except Exception:
                    pass
            page.wait_for_timeout(1_000)
        return None

    # ------------------------------------------------------------------
    # NAVIGATION ET CONFIGURATION
    # ------------------------------------------------------------------

    def _login_mpc(self, page, wait_seconds: int = 120):
        """
        Navigue vers la page de connexion MPC, attend que l'utilisateur se connecte.
        Reprend dès la connexion détectée ou après wait_seconds secondes.
        """
        page.goto("https://www.makeplayingcards.com/", wait_until="domcontentloaded")
        self._accept_cookies(page)

        # Déjà connecté ?
        try:
            already = page.evaluate(
                "() => !!document.querySelector('#sysheader_signout, [href*=\"signout\"]')"
            )
            if already:
                print("[MPC] Déjà connecté à MPC")
                return
        except Exception:
            pass

        # Naviguer vers la page de connexion en cliquant sur "My Account" / "Sign In"
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=6_000):
                page.locator(
                    "#sysheader_myaccount, a[href*='my-account'], a[href*='login'], "
                    "a:has-text('Sign In'), a:has-text('My Account'), a:has-text('Log in')"
                ).first.click(timeout=4_000)
            print(f"[MPC] Page de connexion : {page.url}")
        except Exception:
            print("[MPC] Navigation vers login échouée — rester sur la page d'accueil")

        print(f"[MPC] Connectez-vous dans le navigateur. Reprise automatique dès la connexion (max {wait_seconds}s)…")

        try:
            page.wait_for_selector(
                "#sysheader_signout, [href*='signout'], [href*='logout']",
                timeout=wait_seconds * 1_000,
            )
            print("[MPC] Connexion détectée !")
        except Exception:
            print("[MPC] Continuation sans connexion (timeout)")

    def _accept_cookies(self, page):
        for sel in [
            "#onetrust-accept-btn-handler",
            "#btn_accept",
            "button:has-text('Accept All')",
            "button:has-text('Accept')",
            "a:has-text('Accept')",
        ]:
            try:
                page.locator(sel).click(timeout=2_500)
                return
            except Exception:
                continue

    def _start_design(self, page):
        """Clique sur Start Design et attend la navigation vers l'éditeur."""
        origin = page.url

        # Essai 1 : clic sur le bouton visible
        for sel in [
            "a[onclick*='doPersonalize']",
            "a:has-text('Start Designing')",
            "a:has-text('Design It')",
            "a:has-text('Add Your Design')",
            ".btn-personalize",
        ]:
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                    page.locator(sel).first.click(timeout=4_000)
                print(f"[MPC] Start Design (clic) → {page.url}")
                return
            except Exception:
                continue

        # Essai 2 : JS doPersonalize + attente de n'importe quelle navigation
        try:
            page.evaluate(f"doPersonalize('{MPC_PROCESS_URL}')")
            page.wait_for_url(lambda url: url != origin, timeout=15_000)
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
            print(f"[MPC] doPersonalize → {page.url}")
            return
        except Exception as e:
            print(f"[MPC] doPersonalize échoué : {e}")

        # Essai 3 : navigation directe UNIQUEMENT si on est encore sur la page produit
        if origin in page.url:
            print("[MPC] Navigation directe (dernier recours)…")
            page.goto(MPC_PROCESS_URL, wait_until="domcontentloaded")
            print(f"[MPC] → {page.url}")
        else:
            print(f"[MPC] Déjà navigué vers : {page.url}")

    def _prepare_editor(self, page, mpc_qty: int):
        """
        Config MPC via approche mpcfill (chilli-axe/mpc-autofill) :
          1. Sélectionne le tier de quantité via dro_total_count
          2. Tape la quantité dans txt_card_number → déclenche onkeyup → renderPacking()
          3. Attend que setMode et oRenderFeature soient définis dans l'iframe
          4. Appelle setMode('ImageText', 0) — gère mode + soumission + avancement
          5. Répète setMode sur chaque page d'avancement jusqu'à atteindre l'éditeur
        """
        print(f"[MPC] Éditeur sur : {page.url}")

        try:
            page.wait_for_function("typeof oDesign !== 'undefined'", timeout=10_000)
            print("[MPC] oDesign disponible")
        except Exception:
            print("[MPC] oDesign non détecté")

        frame = self._wait_for_loaded_frame(page, timeout=30_000)
        if not frame:
            print("[MPC] ⚠ Frame config initial non chargé")
            return

        print(f"[MPC] Config initiale — {frame.url}")
        self._dump_frame_dom(frame, "03_config_step1")

        # Sauvegarder _oc_initial et _pieces_initial depuis step1
        try:
            if self._oc_initial is None:
                self._oc_initial = frame.evaluate(
                    "() => { const oc = document.getElementById('hidd_original_count'); return oc ? oc.value : null; }"
                )
                print(f"[MPC] _oc_initial = {self._oc_initial!r}")
            hpci_val = frame.evaluate("""() => {
                try {
                    const v = document.getElementById('hidd_packing_condition_info');
                    return v ? JSON.parse(v.value) : null;
                } catch(e) { return null; }
            }""")
            if self._pieces_initial is None and hpci_val and hpci_val.get('Pieces') is not None:
                self._pieces_initial = hpci_val['Pieces']
                print(f"[MPC] _pieces_initial = {self._pieces_initial!r}")
        except Exception as e:
            print(f"[MPC] ⚠ Diag step1: {e}")

        # Sélectionne le tier dans dro_total_count
        self._set_quantity_js(frame, mpc_qty)
        page.wait_for_timeout(300)

        # Tape la quantité dans txt_card_number → déclenche onkeyup="renderPacking()"
        # (mpcfill : qty.clear() + qty.send_keys(str(order.details.quantity)))
        _nav_kw = ("detached", "context", "navigation", "closed", "destroyed", "target")
        try:
            txt = frame.locator("#txt_card_number")
            txt.fill("")
            txt.press_sequentially(str(mpc_qty))
            print(f"[MPC] txt_card_number ← {mpc_qty} (renderPacking via onkeyup)")
            page.wait_for_timeout(1_500)
        except Exception as e:
            if any(k in str(e).lower() for k in _nav_kw):
                print("[MPC] txt_card_number → navigation prématurée")
            else:
                print(f"[MPC] ⚠ txt_card_number: {e}")

        # Appelle setMode sur le frame courant ; retourne True si navigation déclenchée
        def _call_set_mode(f):
            try:
                f.wait_for_function(
                    "typeof setMode === 'function' && typeof oRenderFeature === 'object'",
                    timeout=12_000,
                )
                print("[MPC] setMode + oRenderFeature prêts")
            except Exception as e:
                print(f"[MPC] ⚠ Attente setMode/oRenderFeature: {e}")
            try:
                f.evaluate("setMode('ImageText', 0)")
                print("[MPC] setMode('ImageText', 0) appelé")
                return False
            except Exception as e:
                if any(k in str(e).lower() for k in _nav_kw):
                    print("[MPC] setMode → navigation OK")
                    return True
                print(f"[MPC] ⚠ setMode: {e}")
                return False

        _call_set_mode(frame)
        page.wait_for_timeout(3_000)

        # Attendre l'éditeur ; appeler setMode sur chaque page d'avancement
        for attempt in range(6):
            for f in page.frames:
                if self._frame_has_editor(f):
                    print(f"[MPC] Éditeur prêt (tentative {attempt}) — {f.url}")
                    return

            frame = self._wait_for_loaded_frame(page, timeout=8_000)
            if not frame:
                print(f"[MPC] ⚠ Frame non chargé (tentative {attempt + 1})")
                page.wait_for_timeout(2_000)
                continue

            print(f"[MPC] Avancement {attempt + 1} — {frame.url}")
            self._dump_frame_dom(frame, f"03_advance{attempt + 1}")

            if self._frame_has_editor(frame):
                print(f"[MPC] Éditeur prêt (avancement {attempt + 1})")
                return

            _call_set_mode(frame)
            page.wait_for_timeout(3_000)

        print("[MPC] ⚠ Éditeur non atteint après setMode")

    def _frame_has_editor(self, frame) -> bool:
        """Retourne True si le frame contient l'UI d'upload (pas la page de config)."""
        try:
            return frame.evaluate("""() => !!(
                document.getElementById('uploadId') ||
                document.querySelector('[id^="fmItem0"]') ||
                document.querySelector('[id^="bnbox0"]')
            )""")
        except Exception:
            return False

    def _click_next_step(self, page, frame=None, sources: dict | None = None, layer: str | None = None) -> bool:
        """Avance d'une étape via oDesign.setNextStep() — même logique que _advance_to_back."""
        # Attendre fin spinner
        try:
            page.wait_for_selector("#sysdiv_wait", state="hidden", timeout=120_000)
        except Exception:
            pass

        # Essai 1 : setNextStep() — dialog accept géré par handler global
        try:
            page.wait_for_function(
                "typeof oDesign !== 'undefined' && typeof oDesign.setNextStep === 'function'",
                timeout=5_000,
            )
            with page.expect_navigation(wait_until="domcontentloaded", timeout=600_000):
                page.evaluate("oDesign.setNextStep()")
            print(f"[MPC] (setNextStep) → {page.url}")
            return True
        except Exception:
            pass

        # Essai 2 : forcer btn visible + clic
        for ctx in ([page, frame] if frame and frame != page.main_frame else [page]):
            try:
                ctx.evaluate("""() => {
                    const btn = document.getElementById('btn_next_step');
                    if (btn) { btn.style.display = ''; btn.style.visibility = 'visible'; btn.disabled = false; btn.removeAttribute('disabled'); }
                }""")
            except Exception:
                pass
        for ctx in ([page, frame] if frame and frame != page.main_frame else [page]):
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=600_000):
                    ctx.locator("#btn_next_step").first.click(force=True, timeout=5_000)
                print(f"[MPC] (#btn_next_step) → {page.url}")
                return True
            except Exception:
                pass

        # Essai 3 : __doPostBack
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=600_000):
                page.evaluate("__doPostBack('btn_next_step','')")
            print(f"[MPC] (__doPostBack) → {page.url}")
            return True
        except Exception as e:
            print(f"[MPC] ⚠ _click_next_step: {e}")
            return False

    def _find_editor_frame(self, page, timeout=90_000, mode: int = 0):
        """
        Attend et retourne le frame contenant l'UI d'upload.
        mode=0 : setMode('ImageText', 0) — images différentes par slot (fronts, backs DFC)
        mode=1 : setMode('ImageText', 1) — même image pour tous les slots (endos global)
        Approche mpc-autofill : setMode dans le frame de sélection, puis wait éditeur.
        """
        poll_ms = 2_000
        steps = max(1, timeout // poll_ms)
        _nav_kw = ("detached", "context", "navigation", "closed", "destroyed", "target")
        mode_called_for = set()

        for i in range(steps):
            # Auto-skip étapes 'Add text to front/back' (étapes 2 et 4)
            if "dn_texteditor" in page.url:
                step_name = "front" if "dn_texteditor_front" in page.url else "back"
                print(f"[MPC] Étape 'Add text to {step_name}' détectée → skip automatique")
                self._click_next_step(page)
                page.wait_for_timeout(2_000)
                continue

            for frame in page.frames:
                if self._frame_has_editor(frame):
                    return frame

            # Chercher le frame de sélection de mode (dn_playingcards_mode_nf / _nb)
            # et appeler setMode avec le bon mode (0=different, 1=same)
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                frame_url = frame.url
                if "dn_playingcards_mode_n" in frame_url and frame_url not in mode_called_for:
                    try:
                        has_set_mode = frame.evaluate("typeof setMode === 'function'")
                        if has_set_mode:
                            mode_called_for.add(frame_url)
                            frame.evaluate(f"setMode('ImageText', {mode})")
                            side = "back" if "_nb" in frame_url else "front"
                            mode_label = "same" if mode == 1 else "different"
                            print(f"[MPC] setMode ImageText {mode_label} ({mode}) → éditeur {side}")
                            page.wait_for_timeout(3_000)
                            break
                    except Exception as e:
                        if any(k in str(e).lower() for k in _nav_kw):
                            print(f"[MPC] setMode → navigation détectée")
                        else:
                            print(f"[MPC] ⚠ setMode mode frame: {e}")

            if i % 5 == 0:
                elapsed = i * poll_ms // 1000
                urls = [f.url[:80] for f in page.frames if f.url]
                print(f"[MPC] En attente upload UI… ({elapsed}s) — frames :")
                for u in urls:
                    print(f"  · {u}")
            page.wait_for_timeout(poll_ms)
        print("[MPC] ⚠ Upload UI non détecté après timeout")
        for frame in page.frames:
            if frame.url:
                name = frame.url.split('/')[-1].split('?')[0][:20]
                self._dump_frame_dom(frame, f"04_timeout_{name}")
        self._screenshot(page, "04_upload_timeout")
        return None

    def _set_quantity_js(self, frame, mpc_qty: int):
        """Sélectionne la quantité via JS pour contourner le popupmask."""
        try:
            available = frame.evaluate("""() => {
                const sel = document.getElementById('dro_total_count');
                if (!sel) return [];
                return [...sel.options].map(o => parseInt(o.value)).filter(v => !isNaN(v));
            }""")
            if not available:
                print("[MPC] ⚠ dro_total_count non trouvé — valeur par défaut")
                return
            valid = [v for v in available if v >= mpc_qty]
            deck_size = min(valid) if valid else max(available)
            # Save initial hidd_original_count from step1 (product default, e.g. '55')
            # renderPacking() uses this to compute Pieces — must stay at product default.
            if self._oc_initial is None:
                self._oc_initial = frame.evaluate(
                    "() => { const oc = document.getElementById('hidd_original_count'); return oc ? oc.value : null; }"
                )
            oc_js = repr(self._oc_initial) if self._oc_initial is not None else 'null'
            frame.evaluate(f"""() => {{
                const sel = document.getElementById('dro_total_count');
                if (sel) sel.value = '{deck_size}';
                if (typeof setTotalCount === 'function') setTotalCount();
                const hc = document.getElementById('hidd_totalcount');
                if (hc) hc.value = '{deck_size}';
                const oc = document.getElementById('hidd_original_count');
                if (oc && {oc_js} !== null) oc.value = {oc_js};
                const tn = document.getElementById('txt_card_number');
                if (tn) tn.value = '{deck_size}';
            }}""")
            print(f"[MPC] Quantité : {deck_size} slots (pour {mpc_qty} cartes)")
        except Exception as e:
            print(f"[MPC] ⚠ Sélection quantité : {e}")

    def _dump_page_info(self, page, label: str) -> None:
        """Sauvegarde les éléments interactifs de la page principale."""
        import json
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)

            # Attendre que le body se remplisse
            for i in range(10):
                length = page.evaluate("() => document.body ? document.body.innerHTML.length : 0")
                if length > 500:
                    break
                page.wait_for_timeout(1_000)

            info = page.evaluate("""() => ({
                url: window.location.href,
                title: document.title,
                bodyLength: document.body ? document.body.innerHTML.length : 0,
                inputs: [...document.querySelectorAll('input')].map(e => ({
                    id: e.id, name: e.name, type: e.type, visible: e.offsetParent !== null
                })),
                selects: [...document.querySelectorAll('select')].map(e => ({
                    id: e.id, name: e.name,
                    options: [...e.options].map(o => ({value: o.value, text: o.text}))
                })),
                buttons: [...document.querySelectorAll('button,input[type=button],a[onclick]')].map(e => ({
                    tag: e.tagName, id: e.id,
                    text: (e.innerText || e.value || '').trim().substring(0,60),
                    onclick: (e.getAttribute('onclick') || '').substring(0,100),
                    visible: e.offsetParent !== null
                })),
                iframes: [...document.querySelectorAll('iframe')].map(e => ({
                    id: e.id, name: e.name, src: e.src
                })),
                allIds: [...document.querySelectorAll('[id]')].map(e => e.id).filter(Boolean).slice(0,100)
            })""")

            path = os.path.join(DEBUG_DIR, f"{label}_dom.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
            print(f"[MPC] Main DOM → {path} (bodyLength={info.get('bodyLength',0)})")
        except Exception as e:
            print(f"[MPC] Erreur dump DOM : {e}")

    def _dump_frame_dom(self, frame, label: str) -> None:
        """Sauvegarde le DOM de l'iframe éditeur."""
        import json
        try:
            info = frame.evaluate("""() => ({
                url: window.location.href,
                bodyLength: document.body ? document.body.innerHTML.length : 0,
                bodySnippet: document.body ? document.body.innerHTML.substring(0, 30000) : '',
                inputs: [...document.querySelectorAll('input')].map(e => ({
                    id: e.id, name: e.name, type: e.type, visible: e.offsetParent !== null
                })),
                selects: [...document.querySelectorAll('select')].map(e => ({
                    id: e.id, name: e.name,
                    options: [...e.options].map(o => ({value: o.value, text: o.text}))
                })),
                allIds: [...document.querySelectorAll('[id]')].map(e => e.id).filter(Boolean).slice(0, 150)
            })""")
            path = os.path.join(DEBUG_DIR, f"{label}_dom.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
            print(f"[MPC] Frame DOM → {path} (bodyLength={info.get('bodyLength',0)})")
            print(f"[MPC] Frame allIds[:20]: {info.get('allIds', [])[:20]}")
        except Exception as e:
            print(f"[MPC] Erreur dump frame : {e}")

    def _wait_editor(self, page, timeout=90_000, mode: int = 0):
        """Attend le chargement de l'UI d'upload et retourne le frame.
        mode=0 : images différentes (fronts, backs DFC)
        mode=1 : même image pour tous (endos global) — mpc-autofill same_images()
        """
        print("[MPC] Attente UI upload…")
        frame = self._find_editor_frame(page, timeout=timeout, mode=mode)
        if frame:
            print(f"[MPC] Upload UI prêt → {frame.url[:100]}")
            self._dump_frame_dom(frame, "04_upload_ready")
            self._screenshot(page, "04_editor_loaded")
        return frame

    def _advance_to_back(self, page, frame=None, sources: dict | None = None, layer: str | None = None):
        """Avance de l'étape Customize Front vers Customize Back.

        IMPORTANT : chaque applyDragPhoto ne sauvegarde qu'un seul slot côté serveur.
        Après N uploads, le serveur ne connaît que le dernier slot → btn_next_step reste
        désactivé. _post_complete_sources DOIT être appelé EN PREMIER pour envoyer tous les
        slots avant que setNextStep() ne vérifie la visibilité de btn_next_step.

        Ordre :
          1. Attendre que le dernier AJAX soit terminé (sysdiv_wait caché)
          2. _post_complete_sources — sauvegarde tous les slots côté serveur (OBLIGATOIRE)
          3. oDesign.setNextStep() — le confirm() dialog est accepté par le handler global
          4. Fallback : btn_next_step visible + clic forcé
          5. Dernier recours : __doPostBack
        """
        print("[MPC] Avancement vers les backs…")

        # 1. Attendre que le dernier AJAX (applyDragPhoto) soit terminé
        try:
            page.wait_for_selector("#sysdiv_wait", state="hidden", timeout=120_000)
            print("[MPC] MPC idle — sysdiv_wait caché")
        except Exception:
            print("[MPC] ⚠ sysdiv_wait non caché après 120s — tentative quand même")

        # 2. Sauvegarder TOUS les slots côté serveur.
        # Obligatoire : chaque applyDragPhoto ne POST qu'un seul slot à
        # dn_update_transition_data.aspx — le serveur ne connaît que le dernier slot
        # après N uploads. Sans ce POST, btn_next_step reste désactivé et setNextStep()
        # ne déclenche aucune navigation même si le dialog confirm() est accepté.
        if sources and frame:
            nat_layer = layer or "front"
            print(f"[MPC] Sauvegarde {nat_layer} ({len(sources)} slots) → serveur MPC…")
            self._post_complete_sources(page, frame, sources, nat_layer)
            page.wait_for_timeout(3_000)

        # 3. oDesign.setNextStep() — le confirm() dialog est géré par page.on("dialog", accept).
        # expect_navigation AVANT evaluate() pour capturer les navigations immédiates.
        try:
            page.wait_for_function(
                "typeof oDesign !== 'undefined' && typeof oDesign.setNextStep === 'function'",
                timeout=10_000,
            )
            print("[MPC] oDesign.setNextStep() — attente navigation (max 10 min)…")
            with page.expect_navigation(wait_until="domcontentloaded", timeout=600_000):
                page.evaluate("oDesign.setNextStep()")
            print(f"[MPC] (setNextStep) → {page.url}")
            page.wait_for_timeout(2_000)
            return
        except Exception as e:
            print(f"[MPC] ⚠ setNextStep: {e}")

        # 4. Forcer btn_next_step visible/activé + clic forcé
        for ctx in ([page, frame] if frame and frame != page.main_frame else [page]):
            try:
                ctx.evaluate("""() => {
                    const btn = document.getElementById('btn_next_step');
                    if (btn) {
                        btn.style.display = '';
                        btn.style.visibility = 'visible';
                        btn.style.opacity = '1';
                        btn.disabled = false;
                        btn.removeAttribute('disabled');
                    }
                }""")
            except Exception:
                pass
        page.wait_for_timeout(500)

        for ctx in ([page, frame] if frame and frame != page.main_frame else [page]):
            try:
                print("[MPC] Clic forcé #btn_next_step…")
                with page.expect_navigation(wait_until="domcontentloaded", timeout=600_000):
                    ctx.locator("#btn_next_step").first.click(force=True, timeout=5_000)
                print(f"[MPC] (#btn_next_step clic) → {page.url}")
                page.wait_for_timeout(2_000)
                return
            except Exception as e:
                print(f"[MPC] ⚠ btn_next_step clic: {e}")

        # 5. Dernier recours : __doPostBack
        try:
            print("[MPC] __doPostBack btn_next_step…")
            with page.expect_navigation(wait_until="domcontentloaded", timeout=600_000):
                page.evaluate("__doPostBack('btn_next_step','')")
            print(f"[MPC] (__doPostBack) → {page.url}")
        except Exception as e:
            print(f"[MPC] ⚠ __doPostBack: {e}")

        page.wait_for_timeout(2_000)

    # ------------------------------------------------------------------
    # UPLOAD ET PLACEMENT DANS UN SLOT (IFRAME)
    # ------------------------------------------------------------------

    def _upload_same_back_to_all(self, page, image_path: str) -> None:
        """Endos global en mode 1 (same image) — approche mpc-autofill same_images().
        Le mode a déjà été sélectionné par _wait_editor(mode=1).
        Un seul upload + applyDragPhoto slot 0 suffit :
        MPC réplique automatiquement à toutes les cartes en mode 1.
        """
        frame = self._find_editor_frame(page, timeout=15_000)
        if not frame:
            print("[MPC] ⚠ Frame éditeur introuvable pour endos global")
            return

        self._wait_upload_complete(frame, page)
        pids_before = set(self._get_pid_list(frame))
        try:
            frame.locator("#uploadId").set_input_files(image_path)
        except Exception as e:
            print(f"[MPC] Erreur upload endos global : {e}")
            return
        page.wait_for_timeout(1_000)
        self._wait_upload_complete(frame, page)
        self._wait_spinner(frame, timeout=15_000)

        pids_after = self._get_pid_list(frame)
        new_pids = [p for p in pids_after if p not in pids_before]
        pid = new_pids[-1] if new_pids else (pids_after[-1] if pids_after else "")
        if not pid:
            print("[MPC] ⚠ pid introuvable pour endos global")
            return

        # applyDragPhoto slot 0 — en mode 1, slot 0 est le seul slot visible.
        # MPC réplique automatiquement à toutes les cartes (même image pour tous).
        # mpc-autofill fait la même chose : insert_image() appelle applyDragPhoto
        # uniquement pour les slots dont getElement3() retourne un élément non-null.
        self._apply_drag_photo(frame, page, 0, pid)
        print(f"[MPC] ✓ Endos global pid={pid[:8]}… → slot 0 (mode same image, MPC réplique)")

    def _upload_and_place(self, page, slot_index: int, image_path: str):
        """Upload (si nécessaire) et assigne l'image au slot via applyDragPhoto.
        Approche mpc-autofill : upload_image() + insert_image() avec applyDragPhoto.
        Pas de btn_updateTransitionData — setNextStep() sauvegarde tout en avançant.
        """
        print(f"[MPC] Slot {slot_index} ← {os.path.basename(image_path)}")

        frame = self._find_editor_frame(page, timeout=10_000)
        if not frame:
            print(f"[MPC] ⚠ Frame éditeur non disponible pour slot {slot_index}")
            return

        pid = self._path_to_pid.get(image_path)
        if not pid:
            self._wait_upload_complete(frame, page)
            pids_before = set(self._get_pid_list(frame))
            try:
                frame.locator("#uploadId").set_input_files(image_path)
            except Exception as e:
                print(f"[MPC] Erreur upload slot {slot_index} : {e}")
                return
            page.wait_for_timeout(1_000)
            self._wait_upload_complete(frame, page)
            self._wait_spinner(frame, timeout=15_000)
            pids_after = self._get_pid_list(frame)
            new_pids = [p for p in pids_after if p not in pids_before]
            pid = new_pids[-1] if new_pids else (pids_after[-1] if pids_after else "")
            if pid:
                self._path_to_pid[image_path] = pid
                print(f"[MPC] Upload OK pid={pid[:8]}…")
        else:
            print(f"[MPC] Image déjà uploadée (pid={pid[:8]}…) — réutilisation")

        if not pid:
            print(f"[MPC] ⚠ pid introuvable slot {slot_index}")
            return

        self._apply_drag_photo(frame, page, slot_index, pid)

    # ------------------------------------------------------------------
    # HELPERS mpc-autofill (PageLayout.prototype.applyDragPhoto)
    # ------------------------------------------------------------------

    def _get_pid_list(self, frame) -> list[str]:
        """Retourne la liste des pids déjà uploadés via oDesignImage.dn_getImageList()."""
        try:
            result = frame.evaluate("() => oDesignImage.dn_getImageList()")
            if result:
                return [p for p in result.split(";") if p]
        except Exception:
            pass
        return []

    def _wait_upload_complete(self, frame, page, timeout: int = 30_000) -> None:
        """Attend que oDesignImage.UploadStatus ne soit plus 'Uploading'."""
        steps = max(1, timeout // 500)
        for _ in range(steps):
            try:
                if not frame.evaluate("() => oDesignImage.UploadStatus === 'Uploading'"):
                    return
            except Exception:
                return
            page.wait_for_timeout(500)

    def _apply_drag_photo(self, frame, page, slot_index: int, pid: str) -> None:
        """Assigne pid au slot via PageLayout.prototype.applyDragPhoto (approche mpc-autofill)."""
        try:
            result = frame.evaluate(f"""() => {{
                const el = PageLayout.prototype.getElement3("dnImg", {slot_index});
                if (!el) return 'null';
                PageLayout.prototype.applyDragPhoto(el, 0, "{pid}");
                return 'ok';
            }}""")
            if result == 'null':
                print(f"[MPC] ⚠ getElement3 null pour slot {slot_index} — image non assignée")
                return
            # mpc-autofill : wait() après CHAQUE applyDragPhoto (visible → hidden sur sysdiv_wait).
            self._wait_sysdiv(frame, page, timeout=30_000)
            print(f"[MPC] ✓ Slot {slot_index} rempli (pid={pid[:8]}…)")
        except Exception as e:
            print(f"[MPC] ⚠ applyDragPhoto slot {slot_index} : {e}")

    def _post_complete_sources(self, page, frame, sources: dict, layer: str) -> None:
        """POST hidd_image_list complet à dn_update_transition_data.aspx via fetch().

        Construit la liste complète à partir des sources capturées depuis
        dn_product_analysis_photo.aspx (fires pour TOUS les slots, frais ET en cache).
        Garantit que les slots assignés via pid en cache sont sauvegardés sur le serveur,
        ce que les callbacks naturels des uploads frais ne font pas pour eux.
        """
        if not sources:
            print(f"[MPC] _post_complete_sources {layer}: aucune source capturée")
            return

        max_idx = max(sources.keys())
        image_list = [sources.get(i, {}) for i in range(max_idx + 1)]
        image_list_str = _json.dumps(image_list, separators=(",", ":"))
        js_image_list = _json.dumps(image_list_str)   # JS string literal

        ssid = ""
        frame_url = frame.url
        if "ssid=" in frame_url:
            ssid = frame_url.split("ssid=")[-1].split("&")[0]

        print(f"[MPC] Sauvegarde {layer} : {len(sources)} slots, hiddLayer={layer!r}, ssid={ssid[:12]}…")
        try:
            status = frame.evaluate(f"""
                async () => {{
                    try {{
                        const vs = document.getElementById('__VIEWSTATE');
                        const vsg = document.getElementById('__VIEWSTATEGENERATOR');
                        const p = new URLSearchParams();
                        p.set('__EVENTTARGET', 'btn_updateTransitionData');
                        p.set('__EVENTARGUMENT', '');
                        p.set('__VIEWSTATE', vs ? vs.value : '');
                        p.set('__VIEWSTATEGENERATOR', vsg ? vsg.value : '');
                        p.set('hiddLayer', '{layer}');
                        p.set('hidd_image_list', {js_image_list});
                        const resp = await fetch(
                            '/design/dn_update_transition_data.aspx?ssid={ssid}',
                            {{
                                method: 'POST',
                                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                                credentials: 'include',
                                body: p.toString()
                            }}
                        );
                        return resp.status + ' ' + resp.statusText;
                    }} catch (e) {{
                        return 'error: ' + String(e);
                    }}
                }}
            """)
            page.wait_for_timeout(1_000)
            print(f"[MPC] ✓ {layer} sauvegardé → {status}")
        except Exception as e:
            print(f"[MPC] ⚠ _post_complete_sources {layer}: {e}")

    # ------------------------------------------------------------------
    # DEBUG
    # ------------------------------------------------------------------

    def _wait_sysdiv(self, frame, page, timeout=20_000) -> None:
        """Attend que #sysdiv_wait disparaisse — pattern mpc-autofill wait().

        Attend d'abord que le spinner APPARAISSE (l'AJAX a démarré), puis qu'il
        DISPARAISSE (opération terminée). Si le spinner n'apparaît pas dans la
        fenêtre d'attente initiale, l'opération était très rapide — on continue.
        Identique au pattern Selenium de mpc-autofill :
            find_element(sysdiv_wait) → invisibility_of_element
        """
        # Attendre que le spinner APPARAISSE — prouve que l'AJAX a bien démarré
        try:
            page.wait_for_selector("#sysdiv_wait", state="visible", timeout=300)
        except Exception:
            pass  # Pas apparu → opération instantanée, continuer
        # Attendre que le spinner DISPARAISSE — opération terminée
        try:
            page.wait_for_selector("#sysdiv_wait", state="hidden", timeout=timeout)
            return
        except Exception:
            pass
        # Fallback iframe
        try:
            frame.wait_for_selector("#sysdiv_wait", state="hidden", timeout=timeout)
        except Exception:
            pass

    def _wait_spinner(self, ctx, timeout=20_000):
        try:
            ctx.wait_for_selector("#sysdiv_wait", state="hidden", timeout=timeout)
        except Exception:
            pass

    def _screenshot(self, page, name: str):
        try:
            path = os.path.join(DEBUG_DIR, f"{name}.png")
            page.screenshot(path=path)
        except Exception:
            pass
