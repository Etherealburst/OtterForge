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
import sys
import re
import glob
import json
import zipfile
import threading
import tkinter as tk
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
from ui.dialogs.import_source_dialog import ImportSourceDialog
from ui.dialogs.folder_import_dialog import FolderImportDialog, find_images_in_folder, group_images_by_card_name
from ui.dialogs.artwork_picker_dialog import ArtworkPickerDialog
from ui.dialogs.export_dialog import ExportModeDialog
from ui.dialogs.mpc_upload_dialog import MPCUploadDialog
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.home_print_dialog import HomePrintDialog

from engine.deck_manager import DeckManager
from engine.models import Card
from engine.scryfall_downloader import ScryfallDownloader
from engine.mpc_print_engine import MPCPrintEngine
from engine.batch_importer import BatchImporter
from engine.upscaler import ImageUpscaler
from engine.mpc_uploader import MPCUploader
from engine.proxy_watermark import ProxyWatermark

from config import CACHE_DIR, OUTPUT_DIR, DECKS_DIR, BASE_DIR, OTTERFORGE_DEFAULT_BACK


def _asset_path(name: str) -> str:
    """Resolve a bundled asset — sys._MEIPASS in exe, project root in dev."""
    base = getattr(sys, "_MEIPASS", os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    return os.path.join(base, name)


def _app_base_class():
    """Retourne (BaseClass, TkinterDnD_module) avec mixin DnD si disponible."""
    try:
        from tkinterdnd2 import TkinterDnD
        class _Base(ctk.CTk, TkinterDnD.DnDWrapper):
            pass
        return _Base, TkinterDnD
    except ImportError:
        return ctk.CTk, None

_AppBase, _TkDnD = _app_base_class()


class OtterForgeApp(_AppBase):
    """
    Fenêtre principale d'OtterForge.
    Instancie tous les composants UI et les modules engine.
    Sert de point de coordination (Controller) entre UI et Engine.
    """

    def __init__(self):
        super().__init__()
        if _TkDnD is not None:
            self.TkdndVersion = _TkDnD._require(self)

        self.title("OtterForge")

        # Icône fenêtre + barre des tâches (ICO multi-résolution)
        _logo_path = _asset_path("assets/OtterForge_Image.jpg")
        _ico_path  = _asset_path("assets/otterforge_icon.ico")
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
        self._watermark = ProxyWatermark()

        # Charge les decks sauvegardés, ou crée un deck par défaut
        self._load_saved_decks()

        # One-time background fix: re-apply watermarks on cached 1200dpi files
        # that had bleed-unaware positions (bug pre-v2.0.1 — see proxy_watermark.py).
        threading.Thread(target=self._fix_stale_1200dpi_watermarks, daemon=True).start()

        # Verrou pour éviter les recherches simultanées
        self._search_lock = threading.Lock()
        self._cache_bytes: int = self._compute_cache_size()

        # Flag upload MPC en cours (vérifié à la fermeture)
        self._upload_in_progress = False

        # Préférences utilisateur persistées (MPC dialog, etc.)
        self._user_config = self._load_user_config()

        # Historique Undo/Redo — snapshots de l'état du deck actif
        self._undo_stack: list[tuple[int, list[dict]]] = []  # (deck_index, cards_snapshot)
        self._redo_stack: list[tuple[int, list[dict]]] = []
        _MAX_UNDO = 20
        self._max_undo = _MAX_UNDO

        # Image d'endos — restaurée depuis le deck actif, sinon OtterForge default
        _active = self.deck_manager.active_deck()
        self.deck_back_image: str | None = _active.back_image if _active else None
        if not self.deck_back_image and os.path.exists(OTTERFORGE_DEFAULT_BACK):
            self.deck_back_image = OTTERFORGE_DEFAULT_BACK

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
        # tk.PanedWindow gère le sash sidebar↔workspace en C natif (smooth drag)
        # ------------------------------------------------------------------
        self.main_frame = tk.PanedWindow(
            self, orient="horizontal",
            bd=0, sashwidth=6, sashpad=2, sashrelief="flat",
            background="#3a3548",
            opaqueresize=True,
        )
        self.main_frame.pack(fill="both", expand=True)

        self.sidebar = DeckSidebar(self.main_frame, app=self)
        self.main_frame.add(self.sidebar, minsize=160, width=DeckSidebar.WIDTH, stretch="never")

        # Pane droit : workspace + séparateur + inspector, gérés par pack
        _right = tk.Frame(self.main_frame, bg="#1c1a20")
        self.main_frame.add(_right, minsize=400, stretch="always")

        self.workspace = Workspace(_right, app=self)
        self.workspace.pack(side="left", fill="both", expand=True)

        ctk.CTkFrame(_right, width=1, fg_color="#28252e",
                     corner_radius=0).pack(side="right", fill="y")

        self.inspector = CardInspectorPanel(_right, app=self)
        self.inspector.pack(side="right", fill="y")

        self.main_frame.bind("<ButtonRelease-1>", self._on_sash_released)

        # Bouton flottant pour ré-afficher la sidebar quand elle est cachée
        self._sidebar_unhide_btn = ctk.CTkButton(
            self.main_frame,
            text="▶",
            width=18, height=60,
            fg_color="#28252e",
            hover_color="#c04828",
            text_color="#c04828",
            font=ctk.CTkFont(size=11),
            corner_radius=0,
            command=self.toggle_sidebar,
        )
        self._sidebar_unhide_btn.place_forget()  # caché par défaut

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
        self.bind_all("<Control-b>", lambda e: self.toggle_sidebar())

        # ------------------------------------------------------------------
        # RESTAURATION ÉTAT SIDEBAR (après layout initial)
        # ------------------------------------------------------------------
        _saved_sb_state = self._user_config.get("sidebar_state")
        _saved_sb_width = self._user_config.get("sidebar_width")
        if _saved_sb_state:
            def _restore_sidebar():
                try:
                    self.sidebar.set_state(_saved_sb_state)
                    if _saved_sb_state == "normal":
                        w = _saved_sb_width or DeckSidebar.WIDTH
                        self.main_frame.paneconfigure(
                            self.sidebar, minsize=160, width=w)
                    elif _saved_sb_state == "compact":
                        self.main_frame.paneconfigure(
                            self.sidebar,
                            minsize=DeckSidebar.COMPACT_WIDTH,
                            width=DeckSidebar.COMPACT_WIDTH)
                    elif _saved_sb_state == "hidden":
                        self.main_frame.paneconfigure(
                            self.sidebar, minsize=1, width=1)
                        self._sidebar_unhide_btn.place(x=0, rely=0.4, anchor="nw")
                except Exception:
                    pass
            self.after(300, _restore_sidebar)

    # ======================================================================
    # SIDEBAR TOGGLE
    # ======================================================================

    def toggle_sidebar(self) -> None:
        """Cycle sidebar through normal → compact → hidden → normal."""
        _cycle = {'normal': 'compact', 'compact': 'hidden', 'hidden': 'normal'}
        next_state = _cycle[self.sidebar._state]
        self.sidebar.set_state(next_state)
        if next_state == 'normal':
            self.main_frame.paneconfigure(
                self.sidebar, minsize=160, width=DeckSidebar.WIDTH)
            self._sidebar_unhide_btn.place_forget()
        elif next_state == 'compact':
            self.main_frame.paneconfigure(
                self.sidebar, minsize=DeckSidebar.COMPACT_WIDTH, width=DeckSidebar.COMPACT_WIDTH)
            self._sidebar_unhide_btn.place_forget()
        elif next_state == 'hidden':
            self.main_frame.paneconfigure(self.sidebar, minsize=1, width=1)
            self.after(50, lambda: self._sidebar_unhide_btn.place(x=0, rely=0.4, anchor="nw"))

    def _on_sash_released(self, event) -> None:
        """After a manual sash drag, sync sidebar content state with actual width."""
        w = self.sidebar.winfo_width()
        self.sidebar._current_w = w
        self._user_config["sidebar_width"] = w
        threshold = DeckSidebar.COMPACT_WIDTH + 20
        if w <= threshold:
            if self.sidebar._state != 'compact':
                self.sidebar.set_state('compact')
                self.main_frame.paneconfigure(
                    self.sidebar,
                    minsize=DeckSidebar.COMPACT_WIDTH,
                    width=DeckSidebar.COMPACT_WIDTH,
                )
        else:
            if self.sidebar._state != 'normal':
                self.sidebar.set_state('normal')
                self.main_frame.paneconfigure(self.sidebar, minsize=160)

    # ======================================================================
    # SETTINGS HELPERS
    # ======================================================================

    @property
    def _watermark_enabled(self) -> bool:
        return bool(self._user_config.get("settings", {}).get("proxy_watermark", True))

    @property
    def _artwork_mode(self) -> str:
        return self._user_config.get("settings", {}).get("custom_artwork_mode", "name_only")

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
            self.statusbar.set_status("Search in progress, please wait…")
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
                # Pass set_code so "Name s:SET" fetches the right printing
                card_json = self.scryfall.get_card(parsed["name"], set_code=parsed.get("set"))

            if not card_json:
                self.after(0, self._on_search_error, f"Card not found: {label!r}")
                return

            face_paths = self.scryfall.download_all_face_images(card_json)

            if not face_paths:
                self.after(0, self._on_search_error, f"Image not found: {label!r}")
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
                        self.after(0, self.statusbar.set_status, f"Upscaling: {fname}…")
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

            # Apply proxy watermark to each final image if enabled.
            # Also stamp the native PNG (workspace displays that for performance).
            if self._watermark_enabled:
                for fp in final_paths:
                    if os.path.exists(fp):
                        self._watermark.apply(fp, card_json)
                        if fp.endswith("_1200dpi.png"):
                            native = fp.replace("_1200dpi.png", ".png")
                            if os.path.exists(native):
                                self._watermark.apply(native, card_json)

            # Face0 = recto de la carte ; face1 = verso DFC (back_image_path)
            face_name = faces[0]["name"] if faces else card_json["name"]
            card = Card(face_name, final_paths[0])
            card.count = parsed.get("count", 1)
            if len(final_paths) > 1:
                card.back_image_path = final_paths[1]

            # Incrémenter le compteur de cache pour les fichiers nouvellement créés
            for p in final_paths:
                try:
                    self._cache_bytes += os.path.getsize(p)
                except Exception:
                    pass

            self.after(0, self._on_search_success, [card], target_deck_index)

        except Exception as e:
            self.after(0, self._on_search_error, f"Error: {e}")

        finally:
            self._search_lock.release()

    def _on_search_success(self, cards: list, target_deck_index: int = 0) -> None:
        """Appelé dans le thread UI après une recherche et upscaling réussis."""
        self._push_undo_snapshot()

        # Capture deck size before add so we can detect truly new entries vs count merges
        if target_deck_index < len(self.deck_manager.decks):
            pre_count = len(self.deck_manager.decks[target_deck_index].cards)
        else:
            pre_count = 0

        for card in cards:
            self.deck_manager.add_card(card, deck_index=target_deck_index)

        # N'actualiser le workspace/sidebar que si le deck cible est toujours affiché
        if target_deck_index < len(self.deck_manager.decks):
            target_deck = self.deck_manager.decks[target_deck_index]
            if self.deck_manager.active_index == target_deck_index:
                # Watermark apply() modified files on disk — invalidate PIL cache so
                # the next load reads the updated images, not the stale cached copies.
                self.workspace._pil_cache.clear()
                self.workspace.load_cards(target_deck.cards, scroll_to_bottom=True)
                self.sidebar.refresh()
            self.deck_manager.save_deck_at(target_deck, self._deck_path(target_deck.name))

        self.inspector.refresh_stats()
        self._update_statusbar_info()
        names = " + ".join(c.name for c in cards)
        self.statusbar.hide_progress()
        self.statusbar.set_status(f"Added: {names}")
        self.search.add_btn.configure(state="normal", text="Add to Deck")

    def _on_search_error(self, message: str) -> None:
        """Appelé dans le thread UI en cas d'erreur de recherche."""
        self.statusbar.hide_progress()
        self.statusbar.set_status(message)
        self.search.add_btn.configure(state="normal", text="Add to Deck")
        messagebox.showwarning("Error", message)

    # ======================================================================
    # TOOLBAR — SAVE DECK
    # ======================================================================

    def save_deck(self) -> None:
        """Ouvre un dialogue de sauvegarde et enregistre le deck en JSON."""
        deck = self.deck_manager.active_deck()
        if not deck:
            return

        if not messagebox.askyesno("Save Deck", "Save the active deck?"):
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
        self.statusbar.set_status(f"Deck saved: {os.path.basename(path)}")

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

        # Vérifier le nom avant chargement pour détecter les doublons
        try:
            with open(path, "r", encoding="utf-8") as f:
                incoming_name = json.load(f).get("name", "")
        except Exception:
            incoming_name = ""

        if incoming_name:
            existing_idx = next(
                (i for i, d in enumerate(self.deck_manager.decks)
                 if d.name == incoming_name), None
            )
            if existing_idx is not None:
                if not messagebox.askyesno(
                    "Deck already open",
                    f'A deck named "{incoming_name}" is already loaded.\nReplace it?'
                ):
                    return
                self.deck_manager.delete_deck(existing_idx)

        deck = self.deck_manager.load_deck(path)
        self.deck_tabs.render()
        self._sync_back_from_active_deck()
        self._refresh_ui()
        self.statusbar.set_status(f"Deck loaded: {deck.name}")

    # ======================================================================
    # TOOLBAR — EXPORT TXT DECK
    # ======================================================================

    def export_txt_deck(self) -> None:
        """Exporte le deck actif en fichier texte au format Moxfield/Arena."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            self.statusbar.set_status("No cards to export")
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
            self.statusbar.set_status(f"Deck exported: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    # ======================================================================
    # TOOLBAR — IMPORT TXT DECK
    # ======================================================================

    def import_txt_deck(self) -> None:
        """Importe un deck depuis un fichier TXT ou un dossier d'images."""
        source_dlg = ImportSourceDialog(self)
        self.wait_window(source_dlg)
        if not source_dlg.result:
            return

        if source_dlg.result == "folder":
            self._import_from_folder()
            return

        # ── TXT flow ──────────────────────────────────────────────────────────
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

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

        self.statusbar.set_status("Importing TXT…")

        thread = threading.Thread(
            target=self._import_txt_worker,
            args=(path,),
            daemon=True,
        )
        thread.start()

    def _import_from_folder(self) -> None:
        """Ouvre un sélecteur de dossier et lance l'import d'images."""
        folder = filedialog.askdirectory(title="Select folder with card images")
        if not folder:
            return

        images = find_images_in_folder(folder)
        if not images:
            messagebox.showinfo("Import Folder", "No images found in this folder.")
            return

        # Group by normalized card name; show picker for conflicts (same name, multiple files).
        groups = group_images_by_card_name(images)
        conflict_groups = {name: paths for name, paths in groups.items() if len(paths) > 1}

        image_entries: list[tuple[str, str]] = []  # (card_name, image_path)

        if conflict_groups:
            picker = ArtworkPickerDialog(self, conflict_groups)
            self.wait_window(picker)
            if picker.cancelled:
                return
            for norm_name, paths in groups.items():
                selected = picker.selections.get(norm_name, paths) if norm_name in conflict_groups else paths
                for path in selected:
                    image_entries.append((norm_name, path))
        else:
            for norm_name, paths in groups.items():
                for path in paths:
                    image_entries.append((norm_name, path))

        if not image_entries:
            return

        dlg = FolderImportDialog(self, folder, len(image_entries), self.upscaler.is_available())
        self.wait_window(dlg)
        if not dlg.result:
            return

        self.statusbar.set_status(f"Importing {len(image_entries)} image(s)…")
        thread = threading.Thread(
            target=self._import_folder_worker,
            args=(image_entries, dlg.result),
            daemon=True,
        )
        thread.start()

    def _import_folder_worker(self, image_entries: list[tuple[str, str]], mode: str) -> None:
        """Thread: process images from a folder and add them to the active deck.

        image_entries: list of (card_name, image_path) — name is already normalized.
        mode: 'upload' = use images as-is (with optional watermark)
              'upscale' = run Real-ESRGAN ×4 then watermark
        """
        self.after(0, self.statusbar.show_progress)
        total = len(image_entries)
        cards: list[dict] = []

        for i, (name, img_path) in enumerate(image_entries):
            self.after(0, self.statusbar.set_status, f"Processing ({i+1}/{total}): {name}")
            self.after(0, self.statusbar.update_progress, i + 1, total)

            final_path = img_path

            if mode == "upscale":
                out_path = os.path.splitext(img_path)[0] + "_1200dpi.png"
                if os.path.exists(out_path):
                    final_path = out_path
                else:
                    try:
                        final_path = self.upscaler.upscale_to_1200dpi(img_path, out_path)
                    except Exception as e:
                        print(f"[App] Folder upscale failed for {name!r}: {e} -- using original")
                        final_path = img_path

            if self._watermark_enabled:
                self._watermark.apply(final_path)
                # If upscaled, also stamp the source image so workspace display shows the watermark
                if final_path != img_path and final_path.endswith("_1200dpi.png") and os.path.exists(img_path):
                    self._watermark.apply(img_path)

            cards.append({"name": name, "image_path": os.path.normpath(final_path), "count": 1})

        self.after(0, self._on_folder_import_complete, cards)

    def _on_folder_import_complete(self, cards: list[dict]) -> None:
        """Appelé dans le thread UI après l'import dossier."""
        try:
            if cards:
                self._push_undo_snapshot()
                self.deck_manager.add_cards_bulk(cards)
                self._refresh_ui()
                self.inspector.refresh_stats()
        finally:
            self.statusbar.hide_progress()

        self.statusbar.set_status(f"{len(cards)} image(s) imported from folder")

        if cards:
            self._auto_save()
            messagebox.showinfo("Folder Import", f"{len(cards)} image(s) imported successfully.")

    def _import_txt_worker(self, path: str) -> None:
        """Exécuté dans un thread séparé pour l'import TXT batch."""
        self.after(0, self.statusbar.show_progress)

        def progress(current: int, total: int, card_label: str):
            self.after(0, self.statusbar.set_status, f"Downloading ({current}/{total}): {card_label}")
            self.after(0, self.statusbar.update_progress, current, total)

        def upscale_progress(current: int, total: int, card_label: str):
            self.after(0, self.statusbar.set_status, f"Upscaling ({current}/{total}): {card_label}")
            self.after(0, self.statusbar.update_progress, current, total)

        def watermark_progress(current: int, total: int, card_label: str):
            self.after(0, self.statusbar.set_status, f"Watermark ({current}/{total}): {card_label}")
            self.after(0, self.statusbar.update_progress, current, total)

        watermark = self._watermark if self._watermark_enabled else None

        try:
            cards, skipped = self.batch_importer.import_txt(
                path,
                progress_callback=progress,
                upscale_callback=upscale_progress,
                watermark=watermark,
                watermark_callback=watermark_progress if watermark else None,
            )
            self.after(0, self._on_import_complete, cards, skipped)
        except Exception as e:
            self.after(0, self.statusbar.set_status, f"Import error: {e}")
            self.after(0, self.statusbar.hide_progress)

    def _on_import_complete(self, cards: list, skipped: list) -> None:
        """Appelé dans le thread UI après l'import TXT."""
        try:
            if cards:
                self._push_undo_snapshot()
                self.deck_manager.add_cards_bulk(cards)
                self._refresh_ui()
                self.inspector.refresh_stats()
        finally:
            self.statusbar.hide_progress()

        status = f"{len(cards)} card(s) imported"
        if skipped:
            status += f" — {len(skipped)} skipped"
        self.statusbar.set_status(status)

        if not cards:
            self.statusbar.set_status("No cards imported" + (f" — {len(skipped)} skipped" if skipped else ""))
            if skipped:
                self._show_skipped_report(skipped)
            return

        self._auto_save()
        msg = f"{len(cards)} card(s) imported successfully."
        if skipped:
            msg += f"\n{len(skipped)} card(s) skipped."
        messagebox.showinfo("Import complete", msg)

        if skipped:
            self._show_skipped_report(skipped)


    def _show_skipped_report(self, skipped: list) -> None:
        """Affiche une fenêtre listant les cartes ignorées avec leur raison."""
        window = ctk.CTkToplevel(self)
        window.title("Skipped cards")
        window.geometry("520x400")
        window.grab_set()
        window.focus_set()

        ctk.CTkLabel(
            window,
            text=f"⚠️  {len(skipped)} card(s) could not be imported:",
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
                text_color="#a09aaa",
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=(0, 8), pady=4)

        ctk.CTkButton(window, text="Close", command=window.destroy).pack(pady=12)

    # ======================================================================
    # TOOLBAR — EXPORT PRINT SHEETS
    # ======================================================================

    def export_print_sheets(self) -> None:
        """Lance la génération des feuilles MPC dans un thread séparé."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            self.statusbar.set_status("No cards to export")
            return

        dlg = ExportModeDialog(self)
        self.wait_window(dlg)
        export_mode = dlg.result
        if not export_mode:
            return

        self.statusbar.show_indeterminate("Generating sheets…")

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
            self.after(0, self.statusbar.set_status, f"Export error: {e}")

    def _on_export_complete(self, sheets: list, output_dir: str, zip_path: str | None, mode: str) -> None:
        """Appelé dans le thread UI après la génération."""
        self.statusbar.hide_progress()
        self.statusbar.set_status(f"{len(sheets)} sheet(s) generated → {output_dir}")

        if mode == "sheets":
            msg = f"{len(sheets)} sheet(s) generated in:\n{output_dir}"
        elif mode == "zip":
            msg = f"ZIP ready for MPC:\n{zip_path}"
        else:
            msg = f"{len(sheets)} sheet(s) generated in:\n{output_dir}\n\nZIP ready for MPC:\n{zip_path}"

        messagebox.showinfo("Export complete", msg)

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
            f"Card back: {os.path.basename(self.deck_back_image)}"
        )

    # ======================================================================
    # TOOLBAR — UPLOAD TO MPC
    # ======================================================================

    def upload_to_mpc(self) -> None:
        """Ouvre le dialog de configuration MPC puis lance l'automation Playwright."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            messagebox.showwarning("Upload to MPC", "The deck is empty.")
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
        self.statusbar.set_status("Opening MPC…")
        self._upload_in_progress = True

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

        raw_cache = os.path.join(CACHE_DIR, "scryfall", "_mpcfill_cardback.png")
        mpc300 = raw_cache.replace(".png", "_mpc300.png")
        if os.path.exists(mpc300):
            return mpc300

        # Build source list: Scryfall CDN first, Wikimedia as reliable fallback
        sources = []
        try:
            resp = _req.get(
                "https://api.scryfall.com/cards/named",
                params={"exact": "Lightning Bolt"},
                headers={"User-Agent": "OtterForge/2.0 (personal proxy tool)"},
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
        if fill_black_lotus and not back_image:
            self.after(0, self.statusbar.set_status, "Downloading MTG card back (MPCFILL)…")
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
            self.after(0, messagebox.showerror, "Playwright missing", str(e))
            self.after(0, self.statusbar.hide_progress)
        except Exception as e:
            msg = str(e)
            if "closed" in msg.lower() or "target" in msg.lower():
                self.after(0, self._on_mpc_upload_done)
            else:
                self.after(0, messagebox.showerror, "MPC error", msg)
                self.after(0, self.statusbar.hide_progress)

    def _on_mpc_upload_done(self) -> None:
        self._upload_in_progress = False
        self.statusbar.hide_progress()
        self.statusbar.set_status("MPC upload complete")

    # ======================================================================
    # TOOLBAR — UPSCALE CACHE BATCH
    # ======================================================================

    def upscale_cache_batch(self) -> None:
        """Lance l'upscaling Real-ESRGAN sur toutes les images du cache sans _1200dpi."""
        if not self.upscaler.is_available():
            messagebox.showwarning(
                "Real-ESRGAN not found",
                f"Real-ESRGAN executable not found.\nConfigured path: {self.upscaler.exe_path}\n\n"
                "Update the path in Settings → Upscaling.",
            )
            return

        cache_dir = os.path.join(CACHE_DIR, "scryfall")
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
            self.statusbar.set_status("Cache already upscaled — no files to process")
            return

        if not messagebox.askyesno(
            "Upscale cache",
            f"{len(to_upscale)} image(s) to upscale.\nThis may take several minutes.\nContinue?",
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
            self.after(0, self.statusbar.set_status, f"Upscale complete: {total} image(s)")
            self.after(0, self._update_statusbar_info)

        threading.Thread(target=_worker, daemon=True).start()

    # ======================================================================
    # TOOLBAR — PURGE CACHE
    # ======================================================================

    def purge_cache(self) -> None:
        """Vide le cache Scryfall après confirmation. Affiche la taille actuelle."""
        cache_dir = os.path.join(CACHE_DIR, "scryfall")
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
            size_str = f"{total_bytes / 1_073_741_824:.1f} GB"
        elif total_bytes >= 1_048_576:
            size_str = f"{total_bytes / 1_048_576:.0f} MB"
        else:
            size_str = f"{total_bytes / 1024:.0f} KB"

        if not messagebox.askyesno(
            "Clear cache",
            f"The cache contains {len(files)} file(s) ({size_str}).\n\n"
            "Delete all Scryfall image files?\n"
            "Images will be re-downloaded on next import.",
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
        self.statusbar.set_status(f"Cache cleared: {deleted} file(s) deleted")

    # ======================================================================
    # PARAMÈTRES
    # ======================================================================

    def open_settings(self) -> None:
        """Ouvre le dialog de paramètres et applique les changements."""
        current = self._user_config.get("settings", {})
        dlg = SettingsDialog(self, current, self.upscaler)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        folder_keys = ("cache_dir", "output_dir", "decks_dir")
        old = self._user_config.get("settings", {})
        self._user_config["settings"] = dlg.result
        self._save_user_config()

        # Apply Real-ESRGAN immediately (both upscaler instances)
        new_exe = os.path.join(
            dlg.result.get("realesrgan_dir", ""),
            "realesrgan-ncnn-vulkan.exe",
        )
        self.upscaler.exe_path = new_exe
        self.batch_importer.upscaler.exe_path = new_exe

        folders_changed = any(
            dlg.result.get(k) != old.get(k) and dlg.result.get(k)
            for k in folder_keys
        )
        if folders_changed:
            messagebox.showinfo(
                "Settings",
                "Folder changes take effect on next startup.",
            )
        else:
            self.statusbar.set_status("Settings saved")

    def open_home_print_dialog(self) -> None:
        """Ouvre le dialog d'impression à domicile."""
        deck = self.deck_manager.active_deck()
        if not deck or not deck.cards:
            self.statusbar.set_status("No cards to print")
            return
        dlg = HomePrintDialog(self, deck.cards)
        self.wait_window(dlg)
        if dlg.result:
            self.statusbar.set_status("Print sheets generated")

    # ======================================================================
    # IMAGES CUSTOM (locale)
    # ======================================================================

    def open_card_creator(self) -> None:
        """Ouvre le Card Creator (formulaire complet + preview live)."""
        from ui.card_creator_panel import CardCreatorPanel
        CardCreatorPanel(self)

    def open_full_custom_dialog(self) -> None:
        """Ouvre le dialog de création de carte 100% custom."""
        _FullCustomDialog(self, upscaler=self.upscaler)

    def _full_custom_worker(self, artwork_path: str, card_name: str,
                            color: str, layout: str, mana_cost: str,
                            type_line: str, rules_text: str,
                            pt: str, upscale: bool) -> None:
        """Thread: crée une carte 100% custom avec FrameBuilder (pas de Scryfall template)."""
        from engine.frame_builder import render_card
        try:
            # Download MTG fonts on first use (background, non-blocking for card gen)
            try:
                from engine.font_manager import prefetch_all as _pf
                import threading as _t
                _t.Thread(target=_pf, daemon=True).start()
            except Exception:
                pass
            custom_cache = os.path.join(BASE_DIR, "cache", "custom")
            os.makedirs(custom_cache, exist_ok=True)

            safe = card_name
            for ch in r'\/:*?"<>|':
                safe = safe.replace(ch, "-")
            safe = safe.strip().replace(" ", "_")[:40]
            forged_path = os.path.join(custom_cache, f"{safe}_forged.png")

            self.after(0, self.statusbar.set_status, f"Génération du frame: {card_name}…")
            final_path = render_card(
                art_path   = artwork_path,
                name       = card_name,
                mana_cost  = mana_cost,
                type_line  = type_line,
                rules_text = rules_text,
                pt         = pt,
                color      = color,
                layout     = layout,
                output_path= forged_path,
            )

            if upscale and self.upscaler.is_available():
                self.after(0, self.statusbar.set_status, f"Upscaling: {card_name}…")
                upscaled = os.path.join(custom_cache, f"{safe}_forged_1200dpi.png")
                try:
                    final_path = self.upscaler.upscale_to_1200dpi(final_path, upscaled)
                except Exception as e:
                    print(f"[App] Forge upscale failed: {e}")

            if self._watermark_enabled:
                self._watermark.apply(final_path, is_custom=True)

            self.after(0, self._add_custom_card, card_name, os.path.normpath(final_path))
        except Exception as e:
            print(f"[App] Full custom worker error: {e}")
            self.after(0, self.statusbar.hide_progress)
            self.after(0, self.statusbar.set_status, f"Erreur forge: {e}")

    def add_custom_image_dialog(self) -> None:
        """Ouvre un sélecteur de fichier(s) pour ajouter une ou plusieurs images custom."""
        paths = filedialog.askopenfilenames(
            title="Choose custom card image(s)",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        if len(paths) == 1:
            self.add_custom_image(paths[0])
        else:
            self._add_custom_images_batch(list(paths))

    def add_custom_image(self, path: str) -> None:
        """Crée une carte custom depuis un fichier image local et l'ajoute au deck actif."""
        mode = self._artwork_mode
        _CustomNameDialog(
            self, os.path.basename(path),
            upscaler=self.upscaler,
            callback=lambda n, up: self._add_custom_image_named(path, n, mode, up),
        )

    def _add_custom_image_named(self, path: str, name: str, mode: str,
                                upscale: bool = False) -> None:
        """Appelé après la saisie du nom dans le dialog custom."""
        if not name:
            return
        if mode == "name_only":
            if upscale and self.upscaler.is_available():
                self.statusbar.show_indeterminate(f"Upscaling: {name}…")
                threading.Thread(
                    target=self._custom_name_only_worker,
                    args=(path, name),
                    daemon=True,
                ).start()
            else:
                self._add_custom_card(name, os.path.normpath(path))
        else:
            self.statusbar.set_status(f"Fetching card data for {name!r}…")
            self.statusbar.show_indeterminate(f"Fetching: {name}…")
            threading.Thread(
                target=self._custom_image_worker,
                args=(path, name, mode, upscale),
                daemon=True,
            ).start()

    def _custom_name_only_worker(self, orig_path: str, card_name: str) -> None:
        """Thread: copie en cache + upscale Real-ESRGAN pour le mode name_only."""
        import shutil
        try:
            custom_cache = os.path.join(BASE_DIR, "cache", "custom")
            os.makedirs(custom_cache, exist_ok=True)
            safe = card_name
            for ch in r'\/:*?"<>|':
                safe = safe.replace(ch, "-")
            safe = safe.strip().replace(" ", "_")[:40]

            base_path = os.path.join(custom_cache, f"{safe}_custom.png")
            shutil.copy2(orig_path, base_path)

            self.after(0, self.statusbar.set_status, f"Upscaling: {card_name}…")
            upscaled_path = os.path.join(custom_cache, f"{safe}_custom_1200dpi.png")
            try:
                final_path = self.upscaler.upscale_to_1200dpi(base_path, upscaled_path)
            except Exception as e:
                print(f"[App] Upscale failed for {card_name!r}: {e} — using original")
                final_path = base_path

            if self._watermark_enabled:
                self._watermark.apply(final_path, is_custom=True)

            self.after(0, self._add_custom_card, card_name, os.path.normpath(final_path))
        except Exception as e:
            print(f"[App] Custom name-only worker error: {e}")
            self.after(0, self.statusbar.hide_progress)
            self.after(0, self.statusbar.set_status, f"Error: {e}")

    def _add_custom_images_batch(self, paths: list) -> None:
        """Ouvre le dialog de confirmation pour un import en lot."""
        _CustomBatchDialog(
            self, paths, upscaler=self.upscaler,
            callback=lambda up: self._start_batch_worker(paths, up),
        )

    def _start_batch_worker(self, paths: list, upscale: bool) -> None:
        mode = self._artwork_mode
        self.statusbar.show_indeterminate(f"Import lot: 0/{len(paths)}…")
        threading.Thread(
            target=self._custom_batch_worker,
            args=(paths, mode, upscale),
            daemon=True,
        ).start()

    def _custom_batch_worker(self, paths: list, mode: str, upscale: bool) -> None:
        """Thread: traite une liste d'images customs en lot."""
        import shutil
        custom_cache = os.path.join(BASE_DIR, "cache", "custom")
        os.makedirs(custom_cache, exist_ok=True)
        results, skipped = [], []

        for i, path in enumerate(paths):
            card_name = os.path.splitext(os.path.basename(path))[0]
            self.after(0, self.statusbar.set_status,
                       f"Import lot {i+1}/{len(paths)}: {card_name}…")
            try:
                safe = card_name
                for ch in r'\/:*?"<>|':
                    safe = safe.replace(ch, "-")
                safe = safe.strip().replace(" ", "_")[:40]

                card_json = None
                if mode in ("frame_overlay", "fetch_metadata"):
                    card_json = self.scryfall.get_card(card_name)

                ext = os.path.splitext(path)[1] or ".png"
                if mode == "frame_overlay" and card_json:
                    frame_path = self.scryfall.download_image(card_json, folder=custom_cache)
                    if frame_path:
                        overlay_out = os.path.join(custom_cache, f"{safe}_overlay.png")
                        final_path = self._overlay_artwork_on_frame(path, frame_path, overlay_out)
                    else:
                        final_path = os.path.join(custom_cache, f"{safe}_custom{ext}")
                        shutil.copy2(path, final_path)
                elif mode == "fetch_metadata" and card_json:
                    final_path = os.path.join(custom_cache, f"{safe}_custom{ext}")
                    shutil.copy2(path, final_path)
                else:
                    final_path = os.path.join(custom_cache, f"{safe}_custom{ext}")
                    shutil.copy2(path, final_path)
                    card_json = None

                if upscale and self.upscaler.is_available():
                    base = os.path.splitext(final_path)[0]
                    upscaled = base + "_1200dpi.png"
                    self.after(0, self.statusbar.set_status,
                               f"Upscaling {i+1}/{len(paths)}: {card_name}…")
                    try:
                        final_path = self.upscaler.upscale_to_1200dpi(final_path, upscaled)
                    except Exception as e:
                        print(f"[App] Batch upscale failed for {card_name!r}: {e}")

                if self._watermark_enabled:
                    self._watermark.apply(final_path, card_json, is_custom=True)

                results.append({
                    "name": card_name,
                    "image_path": os.path.normpath(final_path),
                    "count": 1,
                })
            except Exception as e:
                print(f"[App] Batch error for {card_name!r}: {e}")
                skipped.append(card_name)

        self.after(0, self._on_batch_custom_complete, results, skipped)

    def _on_batch_custom_complete(self, cards: list, skipped: list) -> None:
        self.statusbar.hide_progress()
        if cards:
            self._push_undo_snapshot()
            self.deck_manager.add_cards_bulk(cards)
            deck = self.deck_manager.active_deck()
            if deck:
                self.workspace.load_cards(deck.cards)
            if hasattr(self, "deck_sidebar"):
                self.deck_sidebar.refresh()
        msg = f"{len(cards)} image(s) importée(s)."
        if skipped:
            names = ", ".join(skipped[:3])
            msg += f" {len(skipped)} ignorée(s): {names}"
            if len(skipped) > 3:
                msg += f" (+{len(skipped) - 3})"
        self.statusbar.set_status(msg)

    def _custom_image_worker(self, orig_path: str, card_name: str, mode: str,
                             upscale: bool = False) -> None:
        """Thread: fetch Scryfall data, process custom artwork, optionally upscale."""
        import shutil
        try:
            custom_cache = os.path.join(BASE_DIR, "cache", "custom")
            os.makedirs(custom_cache, exist_ok=True)

            card_json = self.scryfall.get_card(card_name)
            if not card_json:
                print(f"[App] Custom artwork: {card_name!r} not found on Scryfall — fallback name_only")
                self.after(0, self._add_custom_card, card_name, os.path.normpath(orig_path))
                return

            safe = card_name
            for ch in r'\/:*?"<>|':
                safe = safe.replace(ch, "-")
            safe = safe.strip().replace(" ", "_")[:40]
            ext = os.path.splitext(orig_path)[1] or ".png"

            if mode == "frame_overlay":
                frame_path = self.scryfall.download_image(card_json, folder=custom_cache)
                if frame_path:
                    overlay_out = os.path.join(custom_cache, f"{safe}_overlay.png")
                    final_path = self._overlay_artwork_on_frame(orig_path, frame_path, overlay_out)
                else:
                    final_path = os.path.join(custom_cache, f"{safe}_custom{ext}")
                    shutil.copy2(orig_path, final_path)
            else:
                final_path = os.path.join(custom_cache, f"{safe}_custom{ext}")
                shutil.copy2(orig_path, final_path)

            # Optionally upscale via Real-ESRGAN before watermarking
            if upscale and self.upscaler.is_available():
                self.after(0, self.statusbar.set_status, f"Upscaling: {card_name}…")
                base = os.path.splitext(final_path)[0]
                upscaled_path = base + "_1200dpi.png"
                try:
                    final_path = self.upscaler.upscale_to_1200dpi(final_path, upscaled_path)
                except Exception as e:
                    print(f"[App] Upscale failed for {card_name!r}: {e} — using processed image")

            if self._watermark_enabled:
                self._watermark.apply(final_path, card_json, is_custom=True)

            self.after(0, self._add_custom_card, card_name, os.path.normpath(final_path))
        except Exception as e:
            print(f"[App] Custom image worker error: {e}")
            self.after(0, self.statusbar.hide_progress)
            self.after(0, self.statusbar.set_status, f"Error processing custom image: {e}")

    @staticmethod
    def _overlay_artwork_on_frame(artwork_path: str, frame_path: str, output_path: str) -> str:
        """Paste custom artwork into the art box area of a Scryfall card image.

        Art box proportions for standard MTG normal layout (745×1040 Scryfall PNG):
          left=4%, right=96%, top=9%, bottom=52%
        Returns output_path.
        """
        from PIL import Image as _Image
        try:
            frame = _Image.open(frame_path).convert("RGB")
            art   = _Image.open(artwork_path).convert("RGB")
            fw, fh = frame.size

            ax0 = int(fw * 0.04)
            ax1 = int(fw * 0.96)
            ay0 = int(fh * 0.09)
            ay1 = int(fh * 0.52)
            box_w = ax1 - ax0
            box_h = ay1 - ay0

            # Scale-to-cover: artwork fills the entire art box (cropped at edges, not letterboxed)
            scale = max(box_w / art.width, box_h / art.height)
            new_w = round(art.width  * scale)
            new_h = round(art.height * scale)
            art_resized = art.resize((new_w, new_h), _Image.LANCZOS)
            crop_x = (new_w - box_w) // 2
            crop_y = (new_h - box_h) // 2
            art_cropped = art_resized.crop((crop_x, crop_y, crop_x + box_w, crop_y + box_h))
            frame.paste(art_cropped, (ax0, ay0))
            frame.save(output_path, "PNG", compress_level=9, optimize=True)
            print(f"[App] Frame overlay saved → {output_path}")
            return output_path
        except Exception as e:
            print(f"[App] Frame overlay failed: {e} — using original artwork")
            import shutil
            shutil.copy2(artwork_path, output_path)
            return output_path

    def _add_custom_card(self, name: str, final_path: str) -> None:
        """Add a custom card to the active deck (must be called on main thread)."""
        card = Card(name, final_path)
        card.is_custom = True

        self._push_undo_snapshot()
        deck = self.deck_manager.active_deck()
        pre_count = len(deck.cards) if deck else 0
        self.deck_manager.add_card(card)

        deck = self.deck_manager.active_deck()
        if deck:
            new_entries = deck.cards[pre_count:]
            if new_entries:
                self.workspace.append_cards(new_entries, scroll_to_bottom=True)
            self.sidebar.refresh()
            self._auto_save()

        self._update_statusbar_info()
        self.statusbar.hide_progress()
        self.statusbar.set_status(f"Image added: {name}")

    # ======================================================================
    # SYNC CARD BACK + REFRESH UI
    # ======================================================================

    def _sync_back_from_active_deck(self) -> None:
        """Restaure deck_back_image depuis le deck actif et met à jour l'aperçu."""
        deck = self.deck_manager.active_deck()
        self.deck_back_image = deck.back_image if deck else None
        if not self.deck_back_image and os.path.exists(OTTERFORGE_DEFAULT_BACK):
            self.deck_back_image = OTTERFORGE_DEFAULT_BACK
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
            self.statusbar.set_status("Nothing to undo")
            return
        deck = self.deck_manager.active_deck()
        if deck:
            self._redo_stack.append((self.deck_manager.active_index, [c.to_dict() for c in deck.cards]))
        deck_index, snapshot = self._undo_stack.pop()
        self._restore_snapshot(deck_index, snapshot)
        self.statusbar.set_status("Undone (Ctrl+Z)")

    def _redo(self) -> None:
        if not self._redo_stack:
            self.statusbar.set_status("Nothing to redo")
            return
        deck = self.deck_manager.active_deck()
        if deck:
            self._undo_stack.append((self.deck_manager.active_index, [c.to_dict() for c in deck.cards]))
        deck_index, snapshot = self._redo_stack.pop()
        self._restore_snapshot(deck_index, snapshot)
        self.statusbar.set_status("Redone (Ctrl+Y)")

    def _refresh_ui(self) -> None:
        """Met à jour le workspace et la sidebar selon le deck actif."""
        deck = self.deck_manager.active_deck()
        if deck:
            self.workspace.load_cards(deck.cards)
        self.sidebar.refresh()
        self._update_statusbar_info()

    def _fix_stale_1200dpi_watermarks(self) -> None:
        """One-time background fix: re-apply watermarks on cached _1200dpi.png files
        that had bleed-unaware positions (bug pre-v2.0.1).

        _draw() used to compute stamp positions as fractions of the full 3288×4488
        canvas (including 144 px black bleed on each side), placing the watermark
        ~3% left and ~3% up relative to the actual card content. Fixed in v2.0.1 by
        making _draw() work in card-content coordinates. This one-time pass re-applies
        the watermark to already-cached files without requiring re-download/re-upscale.

        Writes cache/scryfall/.wm_bleed_v2 as a sentinel so subsequent startups skip.
        """
        marker = os.path.join(CACHE_DIR, "scryfall", ".wm_bleed_v2")
        if os.path.exists(marker):
            return

        from ui.card_inspector import _load_card_meta

        processed = 0
        seen: set[str] = set()

        for deck in self.deck_manager.decks:
            for card in deck.cards:
                paths = [card.image_path]
                if getattr(card, "back_image_path", None):
                    paths.append(card.back_image_path)
                for path in paths:
                    if not path or path in seen or not path.endswith("_1200dpi.png"):
                        continue
                    # Only fix files that have a clean _orig source to draw from.
                    # Files without _orig cannot be safely re-watermarked (no clean source).
                    orig = path.replace("_1200dpi.png", "_1200dpi_orig.png")
                    if not os.path.exists(orig):
                        continue
                    seen.add(path)
                    card_json = _load_card_meta(path)
                    try:
                        self._watermark.apply(
                            path,
                            card_json=card_json,
                            offset=card.watermark_offset,
                            nfs_offset=card.watermark_nfs_offset,
                            bg=getattr(card, "watermark_bg", "transparent"),
                        )
                    except Exception as e:
                        print(f"[WM fix] {os.path.basename(path)}: {e}")
                    else:
                        processed += 1

        try:
            open(marker, "w").close()
        except Exception:
            pass
        if processed:
            print(f"[WM] Bleed fix: re-applied watermark to {processed} cached 1200dpi image(s)")

    def _compute_cache_size(self) -> int:
        cache_dir = os.path.join(CACHE_DIR, "scryfall")
        try:
            return sum(
                os.path.getsize(os.path.join(cache_dir, f))
                for f in os.listdir(cache_dir)
                if os.path.isfile(os.path.join(cache_dir, f))
            )
        except Exception:
            return 0

    def _update_statusbar_info(self) -> None:
        """Met à jour le label info de la statusbar (cartes + taille cache)."""
        deck = self.deck_manager.active_deck()
        card_count = sum(c.count for c in deck.cards) if deck else 0
        self.statusbar.update_info(card_count, self._cache_bytes)

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

        skipped = []
        for path in files:
            try:
                self.deck_manager.load_deck(path)
            except Exception as e:
                print(f"[App] Erreur chargement deck {path!r} : {e}")
                skipped.append(os.path.basename(path))

        if not self.deck_manager.decks:
            self.deck_manager.create_deck("New Deck")

        if skipped:
            names = ", ".join(skipped[:3])
            suffix = f" (+{len(skipped)-3} autres)" if len(skipped) > 3 else ""
            self.after(500, lambda: self.statusbar.set_status(
                f"Attention : {len(skipped)} deck(s) ignoré(s) au chargement : {names}{suffix}"
            ))

    # ======================================================================
    # FERMETURE
    # ======================================================================

    def on_close(self) -> None:
        """Gère la fermeture propre de l'application."""
        if self._upload_in_progress:
            if not messagebox.askyesno(
                "Upload in progress",
                "An MPC upload is in progress.\nClose anyway? The upload will be interrupted.",
            ):
                return
        if not messagebox.askyesno("Close OtterForge", "Close OtterForge?"):
            return
        try:
            if self.state() != "zoomed":
                self._user_config["window_geometry"] = self.geometry()
            else:
                self._user_config.pop("window_geometry", None)
            self._user_config["sidebar_state"] = self.sidebar._state
            self._user_config["sidebar_width"] = self.sidebar.winfo_width()
            self._save_user_config()
        except Exception:
            pass
        self.destroy()
        sys.exit(0)

    # ======================================================================
    # PERSISTANCE DE LA CONFIGURATION UTILISATEUR
    # ======================================================================

    _CONFIG_USER_PATH = os.path.join(BASE_DIR, "config_user.json")

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


# ── Custom image name dialog ───────────────────────────────────────────────────

# ── Custom text overlay helper ────────────────────────────────────────────────

def _apply_custom_overlays(image_path: str, card_name: str,
                           type_line: str, pt: str) -> None:
    """Overlay custom name, type line, and P/T text on a card image in-place.

    Positions are expressed as fractions of the card dimensions so they work
    on any Scryfall image size (typically 745×1040 px).
    """
    from PIL import Image as _Image, ImageDraw as _Draw
    from engine.proxy_watermark import _load_font, _outlined_text

    try:
        img = _Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"[ForgeOverlay] Cannot open {image_path!r}: {e}")
        return

    w, h = img.size
    draw = _Draw.Draw(img)

    # ── Card name bar ──────────────────────────────────────────────────────
    if card_name:
        nx0, ny0 = int(w * 0.051), int(h * 0.038)
        ny1 = int(h * 0.075)
        bar_h = max(1, ny1 - ny0)
        font_sz = max(10, int(bar_h * 0.72))
        font = _load_font(font_sz)
        try:
            bb = font.getbbox(card_name)
            ty = ny0 + (bar_h - (bb[3] - bb[1])) // 2 - bb[1]
        except Exception:
            ty = ny0 + 2
        _outlined_text(draw, (nx0 + 6, ty), card_name, font,
                       fill=(255, 255, 255), outline=(0, 0, 0), epaisseur=2)

    # ── Type line bar ──────────────────────────────────────────────────────
    if type_line:
        tx0, ty0 = int(w * 0.051), int(h * 0.535)
        ty1 = int(h * 0.564)
        bar_h = max(1, ty1 - ty0)
        font_sz = max(8, int(bar_h * 0.65))
        font = _load_font(font_sz)
        try:
            bb = font.getbbox(type_line)
            text_y = ty0 + (bar_h - (bb[3] - bb[1])) // 2 - bb[1]
        except Exception:
            text_y = ty0 + 2
        _outlined_text(draw, (tx0 + 6, text_y), type_line, font,
                       fill=(255, 255, 255), outline=(0, 0, 0), epaisseur=2)

    # ── P/T box ────────────────────────────────────────────────────────────
    if pt:
        pcx, pcy = int(w * 0.893), int(h * 0.850)
        font_sz = max(9, int(h * 0.026))
        font = _load_font(font_sz)
        try:
            bb = font.getbbox(pt)
            px = pcx - (bb[2]-bb[0]) // 2 - bb[0]
            py = pcy - (bb[3]-bb[1]) // 2 - bb[1]
        except Exception:
            px, py = pcx - len(pt)*font_sz//3, pcy - font_sz//2
        _outlined_text(draw, (px, py), pt, font,
                       fill=(255, 255, 255), outline=(0, 0, 0), epaisseur=2)

    img.save(image_path, "PNG", compress_level=6)
    print(f"[ForgeOverlay] Applied overlays → {os.path.basename(image_path)}")


# ── Dialogs custom ────────────────────────────────────────────────────────────

class _CustomBatchDialog(ctk.CTkToplevel):
    """Confirmation dialog for batch custom image import."""

    def __init__(self, app, paths: list, callback, upscaler=None) -> None:
        super().__init__(app)
        self._callback = callback
        self._upscaler_available = upscaler is not None and upscaler.is_available()

        self.title("Import lot d'images")
        self.resizable(False, False)
        self.grab_set()
        self.lift()

        h = 290 if self._upscaler_available else 250
        self.update_idletasks()
        try:
            from customtkinter import ScalingTracker as _ST
            _scale = _ST.get_window_scaling(app)
        except Exception:
            _scale = 1.0
        _pw = round(380 * _scale)
        _ph = round(h   * _scale)
        px = app.winfo_rootx() + (app.winfo_width()  - _pw) // 2
        py = app.winfo_rooty() + (app.winfo_height() - _ph) // 2
        self.geometry(f"380x{h}+{px}+{py}")

        ctk.CTkLabel(
            self, text=f"{len(paths)} image(s) sélectionnée(s)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f0ece4",
        ).pack(padx=16, pady=(14, 6), anchor="w")

        preview_lines = []
        for p in paths[:5]:
            preview_lines.append(f"  {os.path.splitext(os.path.basename(p))[0]}")
        if len(paths) > 5:
            preview_lines.append(f"  … et {len(paths) - 5} autre(s)")
        ctk.CTkLabel(
            self, text="\n".join(preview_lines),
            font=ctk.CTkFont(size=10), text_color="#a09aaa",
            justify="left", anchor="w",
        ).pack(padx=16, fill="x")

        ctk.CTkLabel(
            self,
            text="Le nom de chaque fichier sera utilisé comme nom de carte.",
            font=ctk.CTkFont(size=9), text_color="#6a6478",
            wraplength=348, justify="left",
        ).pack(padx=16, pady=(8, 0), anchor="w")

        self._upscale_var = ctk.BooleanVar(value=False)
        if self._upscaler_available:
            ctk.CTkCheckBox(
                self,
                text="Upscaler avec Real-ESRGAN  (×4 — 1200 DPI)",
                variable=self._upscale_var,
                font=ctk.CTkFont(size=11),
                checkbox_width=18, checkbox_height=18,
            ).pack(padx=16, pady=(10, 0), anchor="w")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=16, pady=(14, 0), fill="x")
        ctk.CTkButton(btn_row, text="Annuler", width=88, height=28,
                      fg_color="#28252e", hover_color="#34303e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Importer", width=100, height=28,
                      fg_color="#c04828", hover_color="#a83820",
                      command=self._apply).pack(side="right", padx=(0, 8))

    def _apply(self) -> None:
        upscale = self._upscale_var.get()
        self.destroy()
        self._callback(upscale)


class _CustomNameDialog(ctk.CTkToplevel):
    """Styled dialog to enter a card name (and optionally upscale) for custom image import."""

    def __init__(self, app, filename: str, callback, upscaler=None) -> None:
        super().__init__(app)
        self._callback = callback
        self._upscaler_available = upscaler is not None and upscaler.is_available()

        self.title("Custom image")
        self.resizable(False, False)
        self.grab_set()
        self.lift()

        h = 250 if self._upscaler_available else 205
        self.update_idletasks()
        try:
            from customtkinter import ScalingTracker as _ST
            _scale = _ST.get_window_scaling(app)
        except Exception:
            _scale = 1.0
        _pw = round(350 * _scale)
        _ph = round(h   * _scale)
        px = app.winfo_rootx() + (app.winfo_width()  - _pw) // 2
        py = app.winfo_rooty() + (app.winfo_height() - _ph) // 2
        self.geometry(f"350x{h}+{px}+{py}")

        ctk.CTkLabel(
            self, text=filename,
            font=ctk.CTkFont(size=9), text_color="#a09aaa",
            wraplength=318, justify="left",
        ).pack(padx=16, pady=(14, 6), anchor="w")

        ctk.CTkLabel(
            self, text="Nom de la carte :",
            font=ctk.CTkFont(size=11), anchor="w",
        ).pack(padx=16, fill="x")

        self._entry = ctk.CTkEntry(self, width=318, font=ctk.CTkFont(size=12))
        self._entry.pack(padx=16, pady=(4, 0))
        self._entry.focus_set()
        self._entry.bind("<Return>", lambda e: self._apply())

        self._upscale_var = ctk.BooleanVar(value=False)
        if self._upscaler_available:
            ctk.CTkCheckBox(
                self,
                text="Upscaler avec Real-ESRGAN  (×4 — 1200 DPI)",
                variable=self._upscale_var,
                font=ctk.CTkFont(size=11),
                checkbox_width=18, checkbox_height=18,
            ).pack(padx=16, pady=(10, 0), anchor="w")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=16, pady=(12, 0), fill="x")
        ctk.CTkButton(btn_row, text="Annuler", width=88, height=28,
                      fg_color="#28252e", hover_color="#34303e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Ajouter", width=88, height=28,
                      fg_color="#c04828", hover_color="#a83820",
                      command=self._apply).pack(side="right", padx=(0, 8))

    def _apply(self) -> None:
        name   = self._entry.get().strip()
        upscale = self._upscale_var.get()
        self.destroy()
        self._callback(name, upscale)


class _FullCustomDialog(ctk.CTkToplevel):
    """Dialog for creating a fully custom proxy card via FrameBuilder (no Scryfall template)."""

    def __init__(self, app, upscaler=None) -> None:
        super().__init__(app)
        self._app = app
        self._upscaler_available = upscaler is not None and upscaler.is_available()
        self._artwork_path = ""

        self.title("+Forge — Carte custom")
        self.resizable(False, True)
        self.grab_set()
        self.lift()

        W = 520
        h = 665 if self._upscaler_available else 630
        self.update_idletasks()
        try:
            from customtkinter import ScalingTracker as _ST
            _scale = _ST.get_window_scaling(app)
        except Exception:
            _scale = 1.0
        _pw = round(W * _scale)
        _ph = round(h * _scale)
        px = app.winfo_rootx() + (app.winfo_width()  - _pw) // 2
        py = app.winfo_rooty() + (app.winfo_height() - _ph) // 2
        self.geometry(f"{W}x{h}+{px}+{py}")

        # ── Scrollable content area ───────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=(0, 0))

        # Restore scroll wheel on Windows
        def _focus_scroll(e=None):
            for attr in ("_parent_canvas", "_canvas"):
                w = getattr(scroll, attr, None)
                if w:
                    w.focus_set()
                    break
        scroll.bind("<Enter>", _focus_scroll, add="+")

        PAD = 16

        def _lbl(parent, text, size=11, color="#f0ece4"):
            ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=size),
                         text_color=color, anchor="w").pack(
                padx=PAD, pady=(10, 2), fill="x")

        def _entry(parent, width=None):
            v = ctk.StringVar()
            e = ctk.CTkEntry(parent, textvariable=v,
                             width=width or (W - PAD * 2),
                             font=ctk.CTkFont(size=11))
            e.pack(padx=PAD, fill="x" if width is None else None,
                   anchor="w" if width else None)
            return v, e

        # ── Artwork ───────────────────────────────────────────────────────────
        _lbl(scroll, "Artwork * :")
        art_row = ctk.CTkFrame(scroll, fg_color="transparent")
        art_row.pack(padx=PAD, fill="x")
        self._art_var = ctk.StringVar(value="Aucun fichier sélectionné")
        ctk.CTkEntry(art_row, textvariable=self._art_var, state="disabled",
                     width=320, font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkButton(art_row, text="Browse…", width=88, height=28,
                      fg_color="#28252e", hover_color="#3a3548",
                      command=self._browse_artwork).pack(side="left", padx=(6, 0))

        # ── Nom ───────────────────────────────────────────────────────────────
        _lbl(scroll, "Nom de la carte * :")
        self._name_var, self._name_entry = _entry(scroll)
        self._name_entry.focus_set()

        # ── Couleur du frame ──────────────────────────────────────────────────
        _lbl(scroll, "Couleur du frame :")
        from engine.frame_builder import COLOR_LABELS
        color_options = list(COLOR_LABELS.values())
        self._color_var = ctk.StringVar(value=color_options[0])
        ctk.CTkOptionMenu(
            scroll, variable=self._color_var,
            values=color_options,
            width=W - PAD * 2, height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#28252e", button_color="#3a3548",
        ).pack(padx=PAD, fill="x")

        # ── Style de carte ────────────────────────────────────────────────────
        _lbl(scroll, "Style de carte :")
        from engine.frame_builder import LAYOUT_LABELS
        layout_options = list(LAYOUT_LABELS.values())
        self._layout_var = ctk.StringVar(value=layout_options[0])
        ctk.CTkOptionMenu(
            scroll, variable=self._layout_var,
            values=layout_options,
            width=W - PAD * 2, height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#28252e", button_color="#3a3548",
        ).pack(padx=PAD, fill="x")
        ctk.CTkLabel(scroll,
                     text="Borderless : artwork plein cadre  |  Art étendu : artwork couvre la zone art+bordures  |  Règles transp. : fond texte invisible",
                     font=ctk.CTkFont(size=9), text_color="#6a6478",
                     wraplength=W - PAD * 2, justify="left",
                     anchor="w").pack(padx=PAD, fill="x")

        # ── Coût de mana ──────────────────────────────────────────────────────
        _lbl(scroll, "Coût de mana (optionnel) :")
        mana_row = ctk.CTkFrame(scroll, fg_color="transparent")
        mana_row.pack(padx=PAD, fill="x")
        self._mana_var = ctk.StringVar()
        ctk.CTkEntry(mana_row, textvariable=self._mana_var,
                     width=200, font=ctk.CTkFont(size=13),
                     placeholder_text="{2}{W}{W}").pack(side="left")

        # Légende — fond encadré pour être visible
        mana_hint = ctk.CTkFrame(scroll, fg_color="#211e28",
                                 border_color="#3a3548", border_width=1,
                                 corner_radius=6)
        mana_hint.pack(padx=PAD, pady=(4, 0), fill="x")
        ctk.CTkLabel(mana_hint,
                     text="Couleurs  :  W  U  B  R  G",
                     font=ctk.CTkFont(size=11), text_color="#c4bfb8",
                     anchor="w").pack(padx=10, pady=(8, 2), fill="x")
        ctk.CTkLabel(mana_hint,
                     text="Générique :  0  1  2  3  4  5  6  7  8  …  15",
                     font=ctk.CTkFont(size=11), text_color="#c4bfb8",
                     anchor="w").pack(padx=10, pady=(0, 2), fill="x")
        ctk.CTkLabel(mana_hint,
                     text="Spéciaux  :  X  C  T (tour)  S (neige)  P (phyrexian)",
                     font=ctk.CTkFont(size=11), text_color="#c4bfb8",
                     anchor="w").pack(padx=10, pady=(0, 2), fill="x")
        ctk.CTkLabel(mana_hint,
                     text="Format    :  {2}{W}{W}  ou  2WW  (les {} sont optionnels)",
                     font=ctk.CTkFont(size=11), text_color="#a09aaa",
                     anchor="w").pack(padx=10, pady=(0, 8), fill="x")

        # ── Type line ─────────────────────────────────────────────────────────
        _lbl(scroll, "Type line (optionnel) :")
        self._type_var, _ = _entry(scroll)
        ctk.CTkLabel(scroll, text="ex : Legendary Creature — Human Wizard",
                     font=ctk.CTkFont(size=9), text_color="#6a6478",
                     anchor="w").pack(padx=PAD, fill="x")

        # ── Texte de règles ───────────────────────────────────────────────────
        _lbl(scroll, "Texte de règles (optionnel) :")
        self._rules_textbox = ctk.CTkTextbox(
            scroll, width=W - PAD * 2, height=110,
            font=ctk.CTkFont(size=11),
            fg_color="#1c1a20", border_color="#34303e", border_width=1,
        )
        self._rules_textbox.pack(padx=PAD, fill="x")
        ctk.CTkLabel(scroll,
                     text="Symboles inline : {W} {U} {B} {R} {G} {T} {X} — Saut de ligne : Entrée",
                     font=ctk.CTkFont(size=9), text_color="#6a6478",
                     anchor="w").pack(padx=PAD, fill="x")

        # ── P/T ───────────────────────────────────────────────────────────────
        _lbl(scroll, "Puissance / Endurance (optionnel) :")
        pt_row = ctk.CTkFrame(scroll, fg_color="transparent")
        pt_row.pack(padx=PAD, fill="x")
        self._pt_var = ctk.StringVar()
        ctk.CTkEntry(pt_row, textvariable=self._pt_var, width=110,
                     font=ctk.CTkFont(size=11),
                     placeholder_text="ex : 4/4").pack(side="left")
        ctk.CTkLabel(pt_row, text="  (vide = non-créature)",
                     font=ctk.CTkFont(size=9), text_color="#6a6478").pack(side="left")

        # ── Polices MTG ───────────────────────────────────────────────────────
        font_row = ctk.CTkFrame(scroll, fg_color="#211e28",
                                border_color="#3a3548", border_width=1,
                                corner_radius=6)
        font_row.pack(padx=PAD, pady=(8, 0), fill="x")
        self._font_status = ctk.CTkLabel(
            font_row, text="Polices MTG : vérification…",
            font=ctk.CTkFont(size=10), text_color="#a09aaa", anchor="w")
        self._font_status.pack(side="left", padx=10, pady=6, fill="x", expand=True)
        ctk.CTkButton(
            font_row, text="Télécharger", width=100, height=26,
            font=ctk.CTkFont(size=10),
            fg_color="#28252e", hover_color="#3a3548",
            command=self._download_fonts,
        ).pack(side="right", padx=6, pady=6)
        self.after(100, self._check_fonts)

        # ── Upscale ───────────────────────────────────────────────────────────
        self._upscale_var = ctk.BooleanVar(value=False)
        if self._upscaler_available:
            ctk.CTkCheckBox(
                scroll,
                text="Upscaler avec Real-ESRGAN  (×4 — 1200 DPI)",
                variable=self._upscale_var,
                font=ctk.CTkFont(size=11),
                checkbox_width=18, checkbox_height=18,
            ).pack(padx=PAD, pady=(12, 0), anchor="w")

        # ── Buttons (fixed bottom, outside scroll) ─────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="#1c1a20", height=52)
        btn_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        btn_frame.pack_propagate(False)
        ctk.CTkButton(btn_frame, text="Annuler", width=100, height=34,
                      fg_color="#28252e", hover_color="#34303e",
                      command=self.destroy).pack(side="right", padx=(0, PAD), pady=9)
        ctk.CTkButton(btn_frame, text="Créer", width=120, height=34,
                      fg_color="#c04828", hover_color="#a83820",
                      command=self._apply).pack(side="right", padx=(0, 8), pady=9)

    def _check_fonts(self) -> None:
        """Update font status label."""
        try:
            from engine.font_manager import is_available
            if is_available('name') and is_available('rules'):
                self._font_status.configure(
                    text="Polices MTG : Beleren + MPlantin installées",
                    text_color="#6abf6a")
            else:
                self._font_status.configure(
                    text="Polices MTG : non installées (Palatino utilisé)",
                    text_color="#c09040")
        except Exception:
            self._font_status.configure(
                text="Polices MTG : non vérifiées",
                text_color="#a09aaa")

    def _download_fonts(self) -> None:
        """Download MTG fonts in background and update status."""
        self._font_status.configure(
            text="Téléchargement en cours…", text_color="#4090c0")
        import threading as _t

        def _worker():
            try:
                from engine.font_manager import prefetch_all
                results = prefetch_all()
                ok = sum(1 for v in results.values() if v)
                total = len(results)
                if ok == total:
                    msg = f"Polices MTG : {ok}/{total} installées"
                    color = "#6abf6a"
                else:
                    msg = f"Polices MTG : {ok}/{total} — vérifier connexion"
                    color = "#c09040"
                self.after(0, self._font_status.configure, {"text": msg, "text_color": color})
            except Exception as e:
                self.after(0, self._font_status.configure,
                           {"text": f"Erreur: {e}", "text_color": "#c04828"})

        _t.Thread(target=_worker, daemon=True).start()

    def _browse_artwork(self) -> None:
        path = filedialog.askopenfilename(
            title="Choisir une image d'artwork",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if path:
            self._artwork_path = path
            fname = os.path.basename(path)
            self._art_var.set(fname if len(fname) <= 46 else "…" + fname[-44:])

    def _apply(self) -> None:
        art    = self._artwork_path
        name   = self._name_var.get().strip()
        color  = self._color_var.get().strip()
        layout = self._layout_var.get().strip()
        mana   = self._mana_var.get().strip()
        tl     = self._type_var.get().strip()
        rules  = self._rules_textbox.get("1.0", "end").strip()
        pt     = self._pt_var.get().strip()
        up     = self._upscale_var.get()

        if not art:
            self._art_var.set("← Sélectionne un artwork d'abord !")
            return
        if not name:
            self._name_entry.focus_set()
            return

        self.destroy()
        self._app.statusbar.show_indeterminate(f"+Forge: {name}…")
        import threading as _t
        _t.Thread(
            target=self._app._full_custom_worker,
            args=(art, name, color, layout, mana, tl, rules, pt, up),
            daemon=True,
        ).start()
