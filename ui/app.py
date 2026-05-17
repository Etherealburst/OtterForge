"""
ui/app.py
---------
Fenêtre principale d'OtterForge.
Orchestre tous les composants UI et les modules engine.

Threading : la recherche Scryfall tourne dans un thread séparé pour éviter
de freezer l'interface pendant les appels réseau. Les mises à jour UI
sont toujours faites via self.after() — seule méthode thread-safe avec Tkinter.
"""

import os
import re
import glob
import json
import zipfile
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

from ui.toolbar import Toolbar
from ui.statusbar import StatusBar
from ui.workspace import Workspace
from ui.deck_sidebar import DeckSidebar
from ui.card_search import CardSearch
from ui.card_inspector import CardInspectorPanel
from ui.deck_tabs import DeckTabs
from ui.card_back_picker import CardBackPickerDialog
from ui.dialogs.import_confirm_dialog import ImportConfirmDialog
from ui.dialogs.export_dialog import ExportModeDialog
from ui.dialogs.mpc_upload_dialog import MPCUploadDialog

from engine.deck_manager import DeckManager
from engine.models import Card
from engine.scryfall_downloader import ScryfallDownloader
from engine.mpc_print_engine import MPCPrintEngine
from engine.batch_importer import BatchImporter
from engine.upscaler import ImageUpscaler
from engine.mpc_uploader import MPCUploader

from config import OUTPUT_DIR, DECKS_DIR


class OtterForgeApp(ctk.CTk):
    """
    Fenêtre principale d'OtterForge.
    Instancie tous les composants UI et les modules engine.
    Sert de point de coordination (Controller) entre UI et Engine.
    """

    def __init__(self):
        super().__init__()

        self.title("OtterForge")

        # Icône fenêtre + barre des tâches (ICO multi-résolution)
        _logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "OtterForge_Image.jpg")
        _ico_path  = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "otterforge_icon.ico"))
        try:
            from PIL import Image
            if not os.path.exists(_ico_path):
                _pil = Image.open(_logo_path).convert("RGBA")
                _pil.save(_ico_path, format="ICO",
                          sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
            self.after(0, lambda: self.iconbitmap(_ico_path))
        except Exception:
            pass

        self.minsize(900, 600)
        # Restaure la géométrie sauvegardée, sinon démarre en zoomed
        saved_geo = self._load_user_config().get("window_geometry")
        if saved_geo:
            try:
                self.geometry(saved_geo)
            except Exception:
                self.geometry("1280x800")
                self.after(0, lambda: self.state("zoomed"))
        else:
            self.geometry("1280x800")
            self.after(0, lambda: self.state("zoomed"))

        # ------------------------------------------------------------------
        # ENGINE
        # ------------------------------------------------------------------
        self.deck_manager = DeckManager()
        self.scryfall = ScryfallDownloader()
        self.print_engine = MPCPrintEngine()
        self.batch_importer = BatchImporter()
        self.upscaler = ImageUpscaler()

        # Charge les decks sauvegardés, ou crée un deck par défaut
        self._load_saved_decks()

        # Verrou pour éviter les recherches simultanées
        self._search_lock = threading.Lock()

        # Flag upload MPC en cours (vérifié à la fermeture)
        self._upload_in_progress = False

        # Préférences utilisateur persistées (MPC dialog, etc.)
        self._user_config = self._load_user_config()

        # Historique Undo/Redo — snapshots de l'état du deck actif
        self._undo_stack: list[tuple[int, list[dict]]] = []  # (deck_index, cards_snapshot)
        self._redo_stack: list[tuple[int, list[dict]]] = []
        _MAX_UNDO = 20
        self._max_undo = _MAX_UNDO

        # Image d'endos — restaurée depuis le deck actif s'il en a une
        _active = self.deck_manager.active_deck()
        self.deck_back_image: str | None = _active.back_image if _active else None

        # ------------------------------------------------------------------
        # UI — TOOLBAR (haut)
        # ------------------------------------------------------------------
        self.toolbar = Toolbar(self)
        self.toolbar.pack(side="top", fill="x")

        # ------------------------------------------------------------------
        # UI — ONGLETS DE DECKS (sous toolbar)
        # ------------------------------------------------------------------
        self.deck_tabs = DeckTabs(self)
        self.deck_tabs.pack(side="top", fill="x")

        # ------------------------------------------------------------------
        # UI — BARRE DE RECHERCHE (sous onglets)
        # ------------------------------------------------------------------
        self.search = CardSearch(self)
        self.search.pack(side="top", fill="x")

        # ------------------------------------------------------------------
        # UI — ZONE PRINCIPALE (sidebar + workspace + preview)
        # ------------------------------------------------------------------
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True)

        # app=self passé explicitement pour que les composants accèdent
        # à deck_manager, sidebar, etc. sans passer par master (qui est main_frame)
        self.sidebar = DeckSidebar(self.main_frame, app=self)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkFrame(self.main_frame, width=1, fg_color="#28252e",
                     corner_radius=0).pack(side="left", fill="y")

        self.workspace = Workspace(self.main_frame, app=self)
        self.workspace.pack(side="left", fill="both", expand=True)

        ctk.CTkFrame(self.main_frame, width=1, fg_color="#28252e",
                     corner_radius=0).pack(side="right", fill="y")

        self.inspector = CardInspectorPanel(self.main_frame, app=self)
        self.inspector.pack(side="right", fill="y")

        # ------------------------------------------------------------------
        # UI — STATUS BAR (bas)
        # ------------------------------------------------------------------
        self.statusbar = StatusBar(self)
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.set_status("Ready")

        # Charge les cartes du deck actif (progressif, en arrière-plan)
        deck = self.deck_manager.active_deck()
        if deck and deck.cards:
            self.workspace.load_cards(deck.cards)
        self.sidebar.refresh()
        self.deck_tabs.render()
        self._update_statusbar_info()

        # ------------------------------------------------------------------
        # RACCOURCIS CLAVIER GLOBAUX
        # ------------------------------------------------------------------
        self.bind_all("<Control-f>", lambda e: self.search.entry.focus_set())
        self.bind_all("<Control-i>", lambda e: self.import_txt_deck())
        self.bind_all("<Control-s>", lambda e: self.save_deck())
        self.bind_all("<Control-p>", lambda e: self.export_print_sheets())
        self.bind_all("<Control-z>", lambda e: self._undo())
        self.bind_all("<Control-y>", lambda e: self._redo())

    # ======================================================================
    # RECHERCHE ET AJOUT DE CARTE — THREAD-SAFE
    # ======================================================================

    def search_and_add_card(self, query: str) -> None:
        """
        Lance la recherche Scryfall dans un thread séparé.
        Supporte les formats :
          "Card Name"                  → recherche fuzzy par nom
          "s:SET cn:NUM"               → recherche exacte set + collector
          "Card Name s:SET cn:NUM"     → exacte avec fallback nom
          "1 Card Name (SET) NUM"      → ligne Moxfield collée directement
        """
        parsed = self.batch_importer.parse_line(query)
        if not parsed:
            return

        if not self._search_lock.acquire(blocking=False):
            self.statusbar.set_status("Recherche en cours, patiente...")
            return

        label = parsed.get("name") or f"s:{parsed.get('set')} cn:{parsed.get('collector_number')}"
        self.statusbar.show_indeterminate(f"Searching: {label}...")
        self.search.add_btn.configure(state="disabled", text="...")

        # Capturer l'index du deck actif maintenant pour le thread (évite la race condition)
        target_deck_index = self.deck_manager.active_index

        thread = threading.Thread(
            target=self._search_worker,
            args=(parsed, target_deck_index),
            daemon=True,
        )
        thread.start()

    def _search_worker(self, parsed: dict, target_deck_index: int = 0) -> None:
        """
        Exécuté dans un thread séparé.
        parsed : dict issu de batch_importer.parse_line() avec clés name/set/collector_number/count.
        target_deck_index : index du deck actif au moment du clic (évite la race condition).
        NE PAS modifier de widgets directement ici — utiliser self.after().
        """
        try:
            label = parsed.get("name") or f"s:{parsed.get('set')} cn:{parsed.get('collector_number')}"

            # Résoudre la carte : set+cn en priorité (exact), puis nom fuzzy
            card_json = None
            if parsed.get("set") and parsed.get("collector_number"):
                card_json = self.scryfall.get_card_by_set(parsed["set"], parsed["collector_number"])
                if not card_json and parsed.get("name"):
                    print(f"[App] set/cn introuvable, essai par nom : {parsed['name']!r}")
                    card_json = self.scryfall.get_card(parsed["name"])
            elif parsed.get("name"):
                card_json = self.scryfall.get_card(parsed["name"])

            if not card_json:
                self.after(0, self._on_search_error, f"Carte introuvable : {label!r}")
                return

            face_paths = self.scryfall.download_all_face_images(card_json)

            if not face_paths:
                self.after(0, self._on_search_error, f"Image introuvable : {label!r}")
                return

            faces = card_json.get("card_faces", [])

            # Upscale toutes les faces disponibles
            final_paths = []
            for i, image_path in enumerate(face_paths):
                fname = (faces[i]["name"] if faces and i < len(faces) else card_json["name"])
                final_path = image_path
                if self.upscaler.is_available():
                    upscaled_path = image_path.replace(".png", "_1200dpi.png")
                    if os.path.exists(upscaled_path):
                        final_path = upscaled_path
                    else:
                        self.after(0, self.statusbar.set_status, f"Upscaling : {fname}...")
                        try:
                            final_path = self.upscaler.upscale_to_1200dpi(image_path, upscaled_path)
                        except Exception as e:
                            print(f"[App] Upscaling échoué pour {fname!r} : {e} — fallback 300 DPI")
                            mpc300_path = image_path.replace(".png", "_mpc300.png")
                            try:
                                final_path = self.upscaler.fit_native_to_mpc_300(image_path, mpc300_path)
                            except Exception:
                                final_path = image_path
                else:
                    mpc300_path = image_path.replace(".png", "_mpc300.png")
                    if os.path.exists(mpc300_path):
                        final_path = mpc300_path
                    else:
                        try:
                            final_path = self.upscaler.fit_native_to_mpc_300(image_path, mpc300_path)
                        except Exception:
                            final_path = image_path
                final_paths.append(final_path)

            # Face0 = recto de la carte ; face1 = verso DFC (back_image_path)
            face_name = faces[0]["name"] if faces else card_json["name"]
            card = Card(face_name, final_paths[0])
            card.count = parsed.get("count", 1)
            if len(final_paths) > 1:
                card.back_image_path = final_paths[1]

            self.after(0, self._on_search_success, [card], target_deck_index)

        except Exception as e:
            self.after(0, self._on_search_error, f"Erreur : {e}")

        finally:
            self._search_lock.release()

    def _on_search_success(self, cards: list, target_deck_index: int = 0) -> None:
        """Appelé dans le thread UI après une recherche et upscaling réussis."""
        self._push_undo_snapshot()
        for card in cards:
            self.deck_manager.add_card(card, deck_index=target_deck_index)

        # N'actualiser le workspace/sidebar que si le deck cible est toujours affiché
        if target_deck_index < len(self.deck_manager.decks):
            target_deck = self.deck_manager.decks[target_deck_index]
            if self.deck_manager.active_index == target_deck_index:
                self.workspace.load_cards(target_deck.cards, scroll_to_bottom=True)
                self.sidebar.refresh()
            self.deck_manager.save_deck_at(target_deck, self._deck_path(target_deck.name))

        self.inspector.refresh_stats()
        self._update_statusbar_info()
        names = " + ".join(c.name for c in cards)
        self.statusbar.hide_progress()
        self.statusbar.set_status(f"Ajouté : {names}")
        self.search.add_btn.configure(state="normal", text="Add to Deck")

    def _on_search_error(self, message: str) -> None:
        """Appelé dans le thread UI en cas d'erreur de recherche."""
        self.statusbar.hide_progress()
        self.statusbar.set_status(message)
        self.search.add_btn.configure(state="normal", text="Add to Deck")
        messagebox.showwarning("Erreur", message)

    # ======================================================================
    # TOOLBAR — SAVE DECK
    # ======================================================================

    def save_deck(self) -> None:
        """Ouvre un dialogue de sauvegarde et enregistre le deck en JSON."""
        deck = self.deck_manager.active_deck()
        if not deck:
            return

        if not messagebox.askyesno("Sauvegarder", "Sauvegarder le deck actif ?"):
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=DECKS_DIR,
            initialfile=f"{deck.name}.json",
        )
        if not path:
            return

        self.deck_manager.save_deck(path)
        self.statusbar.set_status(f"Deck sauvegardé : {os.path.basename(path)}")

    # ======================================================================
    # TOOLBAR — LOAD DECK
    # ======================================================================

    def load_deck_file(self) -> None:
        """Ouvre un dialogue et charge un deck depuis un fichier JSON."""
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=DECKS_DIR,
        )
        if not path:
            return

        deck = self.deck_manager.load_deck(path)
        self.deck_tabs.render()
        self._sync_back_from_active_deck()
        self._refresh_ui()
        self.statusbar.set_status(f"Deck chargé : {deck.name}")

    # ======================================================================
    # TOOLBAR — EXPORT TXT DECK
    # ======================================================================

    def export_txt_deck(self) -> None:
        """Exporte le deck actif en fichier texte au format Moxfield/Arena."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            self.statusbar.set_status("Aucune carte à exporter")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{deck.name}.txt",
        )
        if not path:
            return

        lines = []
        for card in deck.cards:
            lines.append(f"{card.count} {card.name}")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.statusbar.set_status(f"Deck exporté : {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Erreur export", str(e))

    # ======================================================================
    # TOOLBAR — IMPORT TXT DECK
    # ======================================================================

    def import_txt_deck(self) -> None:
        """Importe un deck depuis un fichier TXT."""
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        # Parse le fichier pour compter les entrées avant de demander confirmation
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            parsed = [p for p in (self.batch_importer.parse_line(l) for l in lines) if p]
        except Exception:
            parsed = []

        dialog = ImportConfirmDialog(self, path, len(parsed), self.upscaler.is_available())
        self.wait_window(dialog)
        if not dialog.result:
            return

        self.statusbar.set_status("Import TXT en cours...")

        thread = threading.Thread(
            target=self._import_txt_worker,
            args=(path,),
            daemon=True,
        )
        thread.start()

    def _import_txt_worker(self, path: str) -> None:
        """Exécuté dans un thread séparé pour l'import TXT batch."""
        self.after(0, self.statusbar.show_progress)

        def progress(current: int, total: int, card_label: str):
            self.after(0, self.statusbar.set_status, f"Importing ({current}/{total}) : {card_label}")
            self.after(0, self.statusbar.update_progress, current, total)

        try:
            cards, skipped = self.batch_importer.import_txt(path, progress_callback=progress)
            self.after(0, self._on_import_complete, cards, skipped)
        except Exception as e:
            self.after(0, self.statusbar.set_status, f"Erreur import : {e}")
            self.after(0, self.statusbar.hide_progress)

    def _on_import_complete(self, cards: list, skipped: list) -> None:
        """Appelé dans le thread UI après l'import TXT."""
        if cards:
            self._push_undo_snapshot()
            self.deck_manager.add_cards_bulk(cards)
            self._refresh_ui()  # appelle _update_statusbar_info
            self.inspector.refresh_stats()

        status = f"{len(cards)} carte(s) importée(s)"
        if skipped:
            status += f" — {len(skipped)} ignorée(s)"
        self.statusbar.set_status(status)

        self.statusbar.hide_progress()

        if not cards:
            self.statusbar.set_status("Aucune carte importée")
            return

        self._auto_save()
        msg = f"{len(cards)} carte(s) importée(s) avec succès."
        if skipped:
            msg += f"\n{len(skipped)} carte(s) ignorée(s)."
        messagebox.showinfo("Import terminé", msg)

        if skipped:
            self._show_skipped_report(skipped)


    def _show_skipped_report(self, skipped: list) -> None:
        """Affiche une fenêtre listant les cartes ignorées avec leur raison."""
        window = ctk.CTkToplevel(self)
        window.title("Cartes ignorées")
        window.geometry("520x400")
        window.grab_set()
        window.focus_set()

        ctk.CTkLabel(
            window,
            text=f"⚠️  {len(skipped)} carte(s) n'ont pas pu être importée(s) :",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(16, 8), padx=16, anchor="w")

        frame = ctk.CTkScrollableFrame(window)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for item in skipped:
            row = ctk.CTkFrame(frame, fg_color="#221f28")
            row.pack(fill="x", pady=3, padx=2)

            ctk.CTkLabel(
                row,
                text=item["raw"],
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=(8, 4), pady=4)

            ctk.CTkLabel(
                row,
                text=f"→  {item['reason']}",
                anchor="w",
                text_color="#5a5060",
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=(0, 8), pady=4)

        ctk.CTkButton(window, text="Fermer", command=window.destroy).pack(pady=12)

    # ======================================================================
    # TOOLBAR — EXPORT PRINT SHEETS
    # ======================================================================

    def export_print_sheets(self) -> None:
        """Lance la génération des feuilles MPC dans un thread séparé."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            self.statusbar.set_status("Aucune carte à exporter")
            return

        dlg = ExportModeDialog(self)
        self.wait_window(dlg)
        export_mode = dlg.result
        if not export_mode:
            return

        self.statusbar.show_indeterminate("Génération des feuilles...")

        thread = threading.Thread(
            target=self._export_worker,
            args=(list(deck.cards), deck.name, export_mode),
            daemon=True,
        )
        thread.start()

    def _export_worker(self, cards: list, deck_name: str, mode: str) -> None:
        """Exécuté dans un thread séparé. mode = 'sheets' | 'zip' | 'both'."""
        try:
            output_dir = f"{OUTPUT_DIR}/sheets"
            sheets = self.print_engine.generate_sheets(cards, output_dir)

            zip_path = None
            if sheets and mode in ("zip", "both"):
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', deck_name)
                zip_path = os.path.join(OUTPUT_DIR, "exports", f"{safe_name}.zip")
                os.makedirs(os.path.dirname(zip_path), exist_ok=True)
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for sheet in sheets:
                        zf.write(sheet, os.path.basename(sheet))

            self.after(0, self._on_export_complete, sheets, output_dir, zip_path, mode)
        except Exception as e:
            self.after(0, self.statusbar.set_status, f"Erreur export : {e}")

    def _on_export_complete(self, sheets: list, output_dir: str, zip_path: str | None, mode: str) -> None:
        """Appelé dans le thread UI après la génération."""
        self.statusbar.hide_progress()
        self.statusbar.set_status(f"{len(sheets)} feuille(s) générée(s) → {output_dir}")

        if mode == "sheets":
            msg = f"{len(sheets)} feuille(s) générée(s) dans :\n{output_dir}"
        elif mode == "zip":
            msg = f"ZIP prêt pour MPC :\n{zip_path}"
        else:
            msg = f"{len(sheets)} feuille(s) générée(s) dans :\n{output_dir}\n\nZIP prêt pour MPC :\n{zip_path}"

        messagebox.showinfo("Export terminé", msg)

    # ======================================================================
    # TOOLBAR — CHOOSE CARD BACK
    # ======================================================================

    def choose_card_back(self) -> None:
        """Ouvre le sélecteur d'endos et met à jour l'aperçu dans le workspace."""
        dialog = CardBackPickerDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.deck_back_image = dialog.result
        deck = self.deck_manager.active_deck()
        if deck:
            deck.back_image = self.deck_back_image
            self._auto_save()
        self.workspace.update_back_preview(self.deck_back_image)
        # Si on est déjà en mode Faces+Backs, recharger pour afficher le dos immédiatement
        if self.workspace._show_backs and deck and deck.cards:
            self.workspace.load_cards(deck.cards)
        self.statusbar.set_status(
            f"Endos : {os.path.basename(self.deck_back_image)}"
        )

    # ======================================================================
    # TOOLBAR — UPLOAD TO MPC
    # ======================================================================

    def upload_to_mpc(self) -> None:
        """Ouvre le dialog de configuration MPC puis lance l'automation Playwright."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            messagebox.showwarning("Upload to MPC", "Le deck est vide.")
            return

        total_slots = MPCUploader.total_card_slots(deck.cards)
        mpc_qty = MPCUploader._mpc_quantity(total_slots)
        empty_slots = mpc_qty - total_slots

        has_backs = bool(self.deck_back_image) or any(
            getattr(c, "back_image_path", None) or "_face0" in c.image_path
            for c in deck.cards
        )
        mpc_prefs = self._user_config.get("mpc", {})
        mpc_dlg = MPCUploadDialog(
            self,
            deck_name=deck.name,
            total_slots=total_slots,
            mpc_qty=mpc_qty,
            has_backs=has_backs,
            deck_back_image=self.deck_back_image,
            mpc_prefs=mpc_prefs,
        )
        self.wait_window(mpc_dlg)
        config = mpc_dlg.result
        if not config:
            return

        self._user_config["mpc"] = {k: config[k] for k in ("headless", "stock", "login", "upload_backs")}
        self._save_user_config()

        cards = list(deck.cards)
        has_non_dfc = any(not getattr(c, "back_image_path", None) for c in deck.cards)
        fill_black_lotus = not self.deck_back_image and has_non_dfc

        self.statusbar.show_progress()
        self.statusbar.set_status("Ouverture de MPC…")

        threading.Thread(
            target=self._mpc_upload_worker,
            args=(cards, config["headless"], config["stock"], config["login"],
                  total_slots, self.deck_back_image, config["upload_backs"], fill_black_lotus),
            daemon=True,
        ).start()

    def _get_black_lotus_path(self) -> str | None:
        """Downloads the standard MTG card back design and returns its local path."""
        import io
        import requests as _req
        from PIL import Image as _Image

        raw_cache = os.path.join("cache", "scryfall", "_mpcfill_cardback.png")
        mpc300 = raw_cache.replace(".png", "_mpc300.png")
        if os.path.exists(mpc300):
            return mpc300

        # Build source list: Scryfall CDN first, Wikimedia as reliable fallback
        sources = []
        try:
            resp = _req.get(
                "https://api.scryfall.com/cards/named",
                params={"exact": "Lightning Bolt"},
                timeout=8,
            )
            resp.raise_for_status()
            back_id = resp.json().get("card_back_id", "0aeebaf5-8c7d-4636-9e82-8c27447861f7")
            for size in ("large", "normal"):
                sources.append(
                    f"https://c2.scryfall.com/file/scryfall-card-backs/{size}/{back_id[:2]}/{back_id}.jpg"
                )
        except Exception:
            back_id = "0aeebaf5-8c7d-4636-9e82-8c27447861f7"
            sources.append(f"https://c2.scryfall.com/file/scryfall-card-backs/large/{back_id[:2]}/{back_id}.jpg")
        sources.append("https://upload.wikimedia.org/wikipedia/en/a/aa/Magic_the_gathering-card_back.jpg")

        img = None
        for url in sources:
            try:
                resp2 = _req.get(url, timeout=20, headers={"User-Agent": "OtterForge/2.0"})
                resp2.raise_for_status()
                img = _Image.open(io.BytesIO(resp2.content))
                print(f"[App] MTG card back téléchargé : {url[:80]}")
                break
            except Exception:
                continue

        if img is None:
            print("[App] Impossible de télécharger le card back MTG")
            return None

        os.makedirs(os.path.dirname(raw_cache), exist_ok=True)
        img.save(raw_cache, "PNG")

        if os.path.exists(mpc300):
            return mpc300
        return self.batch_importer._apply_300dpi_bleed(raw_cache)

    def _mpc_upload_worker(self, cards: list, headless: bool, stock: str,
                           login: bool, total: int, back_image: str | None,
                           upload_backs: bool = True, fill_black_lotus: bool = False) -> None:
        """Thread : lance l'automation MPC et met à jour la progress bar."""
        self._upload_in_progress = True

        if fill_black_lotus and not back_image:
            self.after(0, self.statusbar.set_status, "Téléchargement card back MTG (MPCFILL)…")
            back_image = self._get_black_lotus_path()
            if back_image:
                print(f"[App] MTG card back : {back_image}")
            else:
                print("[App] Card back introuvable — upload sans card back")

        def progress(current: int, total_: int, label: str) -> None:
            self.after(0, self.statusbar.set_status, label)
            if total_ > 0:
                self.after(0, self.statusbar.update_progress, current, total_)

        try:
            uploader = MPCUploader(headless=headless, stock=stock)
            uploader.upload(cards, progress_callback=progress, login=login,
                            back_image_path=back_image, upload_backs=upload_backs)
            self.after(0, self._on_mpc_upload_done)
        except ImportError as e:
            self.after(0, messagebox.showerror, "Playwright manquant", str(e))
            self.after(0, self.statusbar.hide_progress)
        except Exception as e:
            # Navigateur fermé ou erreur réseau : on affiche juste un message discret
            msg = str(e)
            if "closed" in msg.lower() or "target" in msg.lower():
                self.after(0, self._on_mpc_upload_done)
            else:
                self.after(0, messagebox.showerror, "Erreur MPC", msg)
                self.after(0, self.statusbar.hide_progress)

    def _on_mpc_upload_done(self) -> None:
        self._upload_in_progress = False
        self.statusbar.hide_progress()
        self.statusbar.set_status("Upload MPC terminé")

    # ======================================================================
    # TOOLBAR — UPSCALE CACHE BATCH
    # ======================================================================

    def upscale_cache_batch(self) -> None:
        """Lance l'upscaling Real-ESRGAN sur toutes les images du cache sans _1200dpi."""
        if not self.upscaler.is_available():
            messagebox.showwarning(
                "Real-ESRGAN introuvable",
                "Real-ESRGAN n'est pas installé.\nChemin attendu : " + str(
                    os.path.join(r"C:\Users\Samuel\Documents\MTG\Real-ESGRAN", "realesrgan-ncnn-vulkan.exe")
                ),
            )
            return

        cache_dir = os.path.join("cache", "scryfall")
        try:
            all_files = [
                os.path.join(cache_dir, f)
                for f in os.listdir(cache_dir)
                if f.endswith(".png") and not f.endswith("_1200dpi.png") and not f.endswith("_mpc300.png")
            ]
        except Exception:
            all_files = []

        to_upscale = [
            f for f in all_files
            if not os.path.exists(f.replace(".png", "_1200dpi.png"))
        ]

        if not to_upscale:
            self.statusbar.set_status("Cache déjà upscalé — aucun fichier à traiter")
            return

        if not messagebox.askyesno(
            "Upscale cache",
            f"{len(to_upscale)} image(s) à upscaler.\nCela peut prendre plusieurs minutes.\nContinuer ?",
        ):
            return

        self.statusbar.show_progress()
        total = len(to_upscale)

        def _worker():
            for i, path in enumerate(to_upscale, 1):
                label = os.path.basename(path)
                self.after(0, self.statusbar.set_status, f"Upscaling ({i}/{total}) : {label}")
                self.after(0, self.statusbar.update_progress, i, total)
                try:
                    self.upscaler.upscale_to_1200dpi(path, path.replace(".png", "_1200dpi.png"))
                except Exception as e:
                    print(f"[App] Upscaling échoué pour {label} : {e}")
            self.after(0, self.statusbar.hide_progress)
            self.after(0, self.statusbar.set_status, f"Upscale terminé : {total} image(s)")
            self.after(0, self._update_statusbar_info)

        threading.Thread(target=_worker, daemon=True).start()

    # ======================================================================
    # TOOLBAR — PURGE CACHE
    # ======================================================================

    def purge_cache(self) -> None:
        """Vide le cache Scryfall après confirmation. Affiche la taille actuelle."""
        cache_dir = os.path.join("cache", "scryfall")
        try:
            files = [
                os.path.join(cache_dir, f)
                for f in os.listdir(cache_dir)
                if os.path.isfile(os.path.join(cache_dir, f))
            ]
        except Exception:
            files = []

        total_bytes = sum(os.path.getsize(f) for f in files)
        if total_bytes >= 1_073_741_824:
            size_str = f"{total_bytes / 1_073_741_824:.1f} Go"
        elif total_bytes >= 1_048_576:
            size_str = f"{total_bytes / 1_048_576:.0f} Mo"
        else:
            size_str = f"{total_bytes / 1024:.0f} Ko"

        if not messagebox.askyesno(
            "Vider le cache",
            f"Le cache contient {len(files)} fichier(s) ({size_str}).\n\n"
            "Supprimer tous les fichiers image Scryfall ?\n"
            "Les images seront re-téléchargées lors du prochain import.",
        ):
            return

        deleted = 0
        for f in files:
            try:
                os.remove(f)
                deleted += 1
            except Exception:
                pass

        self._update_statusbar_info()
        self.statusbar.set_status(f"Cache vidé : {deleted} fichier(s) supprimé(s)")

    # ======================================================================
    # SYNC CARD BACK + REFRESH UI
    # ======================================================================

    def _sync_back_from_active_deck(self) -> None:
        """Restaure deck_back_image depuis le deck actif et met à jour l'aperçu."""
        deck = self.deck_manager.active_deck()
        self.deck_back_image = deck.back_image if deck else None
        self.workspace.update_back_preview(self.deck_back_image)

    # ======================================================================
    # UNDO / REDO
    # ======================================================================

    def _push_undo_snapshot(self) -> None:
        """Capture l'état actuel du deck actif dans le stack undo."""
        deck = self.deck_manager.active_deck()
        if not deck:
            return
        snapshot = [c.to_dict() for c in deck.cards]
        self._undo_stack.append((self.deck_manager.active_index, snapshot))
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore_snapshot(self, deck_index: int, snapshot: list[dict]) -> None:
        """Restaure un snapshot de deck."""
        import copy
        from engine.models import Card
        if deck_index >= len(self.deck_manager.decks):
            return
        deck = self.deck_manager.decks[deck_index]
        cards = []
        for d in snapshot:
            c = Card(d["name"], d["image_path"])
            c.count = d.get("count", 1)
            c.back_image_path = d.get("back_image_path")
            cards.append(c)
        deck.cards = cards
        self.deck_manager.set_active(deck_index)
        self.deck_tabs.render()
        self._refresh_ui()
        self._auto_save()

    def _undo(self) -> None:
        if not self._undo_stack:
            self.statusbar.set_status("Rien à annuler")
            return
        deck = self.deck_manager.active_deck()
        if deck:
            self._redo_stack.append((self.deck_manager.active_index, [c.to_dict() for c in deck.cards]))
        deck_index, snapshot = self._undo_stack.pop()
        self._restore_snapshot(deck_index, snapshot)
        self.statusbar.set_status("Annulé (Ctrl+Z)")

    def _redo(self) -> None:
        if not self._redo_stack:
            self.statusbar.set_status("Rien à rétablir")
            return
        deck = self.deck_manager.active_deck()
        if deck:
            self._undo_stack.append((self.deck_manager.active_index, [c.to_dict() for c in deck.cards]))
        deck_index, snapshot = self._redo_stack.pop()
        self._restore_snapshot(deck_index, snapshot)
        self.statusbar.set_status("Rétabli (Ctrl+Y)")

    def _refresh_ui(self) -> None:
        """Met à jour le workspace et la sidebar selon le deck actif."""
        deck = self.deck_manager.active_deck()
        if deck:
            self.workspace.load_cards(deck.cards)
        self.sidebar.refresh()
        self._update_statusbar_info()

    def _update_statusbar_info(self) -> None:
        """Met à jour le label info de la statusbar (cartes + taille cache)."""
        deck = self.deck_manager.active_deck()
        card_count = sum(c.count for c in deck.cards) if deck else 0
        cache_dir = os.path.join("cache", "scryfall")
        try:
            cache_bytes = sum(
                os.path.getsize(os.path.join(cache_dir, f))
                for f in os.listdir(cache_dir)
                if os.path.isfile(os.path.join(cache_dir, f))
            )
        except Exception:
            cache_bytes = 0
        self.statusbar.update_info(card_count, cache_bytes)

    # ======================================================================
    # AUTO-SAVE
    # ======================================================================

    def _deck_path(self, name: str) -> str:
        """Retourne le chemin de sauvegarde d'un deck d'après son nom."""
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        return os.path.join(DECKS_DIR, f"{safe}.json")

    def _auto_save(self) -> None:
        """Sauvegarde silencieuse du deck actif dans decks/."""
        deck = self.deck_manager.active_deck()
        if deck:
            self.deck_manager.save_deck_at(deck, self._deck_path(deck.name))

    def _delete_deck_file(self, name: str) -> None:
        """Supprime le fichier JSON d'un deck s'il existe."""
        path = self._deck_path(name)
        if os.path.exists(path):
            os.remove(path)

    def _load_saved_decks(self) -> None:
        """Charge tous les decks JSON depuis decks/ au démarrage."""
        files = sorted(glob.glob(os.path.join(DECKS_DIR, "*.json")))
        if not files:
            self.deck_manager.create_deck("New Deck")
            return
        for path in files:
            try:
                self.deck_manager.load_deck(path)
            except Exception as e:
                print(f"[App] Erreur chargement deck {path!r} : {e}")
        if not self.deck_manager.decks:
            self.deck_manager.create_deck("New Deck")

    # ======================================================================
    # FERMETURE
    # ======================================================================

    def on_close(self) -> None:
        """Gère la fermeture propre de l'application."""
        if self._upload_in_progress:
            if not messagebox.askyesno(
                "Upload en cours",
                "Un upload MPC est en cours.\nFermer quand même ? L'upload sera interrompu.",
            ):
                return
        if not messagebox.askyesno("Fermer OtterForge", "Fermer OtterForge ?"):
            return
        try:
            if self.state() != "zoomed":
                self._user_config["window_geometry"] = self.geometry()
            else:
                self._user_config.pop("window_geometry", None)
            self._save_user_config()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    # ======================================================================
    # PERSISTANCE DE LA CONFIGURATION UTILISATEUR
    # ======================================================================

    _CONFIG_USER_PATH = "config_user.json"

    def _load_user_config(self) -> dict:
        try:
            with open(self._CONFIG_USER_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_user_config(self) -> None:
        try:
            with open(self._CONFIG_USER_PATH, "w", encoding="utf-8") as f:
                json.dump(self._user_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[App] Impossible de sauvegarder config_user.json : {e}")
