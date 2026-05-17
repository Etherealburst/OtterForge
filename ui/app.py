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
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.after(0, lambda: self.state("zoomed"))  # plein écran après init

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

        ctk.CTkFrame(self.main_frame, width=1, fg_color="#1a1820",
                     corner_radius=0).pack(side="left", fill="y")

        self.workspace = Workspace(self.main_frame, app=self)
        self.workspace.pack(side="left", fill="both", expand=True)

        ctk.CTkFrame(self.main_frame, width=1, fg_color="#1a1820",
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
        self.search.add_btn.configure(state="disabled")

        thread = threading.Thread(
            target=self._search_worker,
            args=(parsed,),
            daemon=True,
        )
        thread.start()

    def _search_worker(self, parsed: dict) -> None:
        """
        Exécuté dans un thread séparé.
        parsed : dict issu de batch_importer.parse_line() avec clés name/set/collector_number/count.
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

            self.after(0, self._on_search_success, [card])

        except Exception as e:
            self.after(0, self._on_search_error, f"Erreur : {e}")

        finally:
            self._search_lock.release()

    def _on_search_success(self, cards: list) -> None:
        """Appelé dans le thread UI après une recherche et upscaling réussis."""
        for card in cards:
            self.deck_manager.add_card(card)
        deck = self.deck_manager.active_deck()
        if deck:
            self.workspace.load_cards(deck.cards, scroll_to_bottom=True)
        self.sidebar.refresh()
        self.inspector.refresh_stats()
        self._auto_save()
        names = " + ".join(c.name for c in cards)
        self.statusbar.hide_progress()
        self.statusbar.set_status(f"Ajouté : {names}")
        self.search.add_btn.configure(state="normal")

    def _on_search_error(self, message: str) -> None:
        """Appelé dans le thread UI en cas d'erreur de recherche."""
        self.statusbar.hide_progress()
        self.statusbar.set_status(message)
        self.search.add_btn.configure(state="normal")
        messagebox.showwarning("Erreur", message)

    # ======================================================================
    # TOOLBAR — SAVE DECK
    # ======================================================================

    def save_deck(self) -> None:
        """Ouvre un dialogue de sauvegarde et enregistre le deck en JSON."""
        deck = self.deck_manager.active_deck()
        if not deck:
            return

        if not messagebox.askyesno("Save Deck", "Do you want to save your deck?"):
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

        if not self._confirm_import_dialog(path, len(parsed)):
            return

        self.statusbar.set_status("Import TXT en cours...")

        thread = threading.Thread(
            target=self._import_txt_worker,
            args=(path,),
            daemon=True,
        )
        thread.start()

    def _confirm_import_dialog(self, path: str, card_count: int) -> bool:
        """Affiche une boîte de dialogue de confirmation avant l'import. Retourne True si confirmé."""
        result = {"ok": False}

        dialog = ctk.CTkToplevel(self)
        dialog.title("Import Deck")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()
        dialog.transient(self)

        # Centrage par rapport à la fenêtre principale
        self.update_idletasks()
        px, py = self.winfo_x(), self.winfo_y()
        pw, ph = self.winfo_width(), self.winfo_height()
        dw, dh = 420, 260
        dialog.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

        # --- Contenu ---
        padx = 28

        ctk.CTkLabel(
            dialog, text="Are you sure you want to import this deck?",
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=360,
        ).pack(pady=(24, 16))

        # Infos fichier + nombre de cartes
        fname = os.path.basename(path)
        ctk.CTkLabel(
            dialog, text=f"File : {fname}",
            font=ctk.CTkFont(size=11), text_color="#5a5060",
        ).pack(padx=padx)

        ctk.CTkLabel(
            dialog, text=f"Cards found : {card_count} entr{'y' if card_count == 1 else 'ies'}",
            font=ctk.CTkFont(size=12),
        ).pack(padx=padx, pady=(6, 0))

        # Estimation du temps
        if card_count > 0:
            upscaler_on = self.upscaler.is_available()
            secs_per_card = 12 if upscaler_on else 2
            total_secs = card_count * secs_per_card
            mins, secs = divmod(total_secs, 60)
            if mins > 0:
                time_str = f"~{mins} min {secs} sec" if secs else f"~{mins} min"
            else:
                time_str = f"~{total_secs} sec"
            quality = "with upscaling to 1200 DPI" if upscaler_on else "download only, no upscaling"
            eta_text = f"Estimated time : {time_str}  ({quality})"
        else:
            eta_text = "No cards detected in this file."

        ctk.CTkLabel(
            dialog, text=eta_text,
            font=ctk.CTkFont(size=11), text_color="#5a5060",
            wraplength=360,
        ).pack(padx=padx, pady=(4, 20))

        # Boutons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        def on_yes():
            result["ok"] = True
            dialog.destroy()

        def on_no():
            dialog.destroy()

        ctk.CTkButton(
            btn_frame, text="Yes", width=110, height=36,
            font=ctk.CTkFont(size=13),
            command=on_yes,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame, text="No", width=110, height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#581e10", hover_color="#3a1a10",
            command=on_no,
        ).pack(side="left", padx=10)

        dialog.bind("<Return>", lambda e: on_yes())
        dialog.bind("<Escape>", lambda e: on_no())

        self.wait_window(dialog)
        return result["ok"]

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
            self.deck_manager.add_cards_bulk(cards)
            self._refresh_ui()
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
        msg = f"{len(cards)} card(s) imported successfully."
        if skipped:
            msg += f"\n{len(skipped)} card(s) skipped."
        messagebox.showinfo("Import completed", msg)

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
            row = ctk.CTkFrame(frame, fg_color="#131118")
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

        export_mode = self._ask_export_mode()
        if not export_mode:
            return

        self.statusbar.show_indeterminate("Génération des feuilles...")

        thread = threading.Thread(
            target=self._export_worker,
            args=(list(deck.cards), deck.name, export_mode),
            daemon=True,
        )
        thread.start()

    def _ask_export_mode(self) -> str | None:
        """
        Affiche un dialog demandant le mode d'export.
        Retourne 'sheets', 'zip', 'both', ou None si annulé.
        """
        result = {"mode": None}

        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Print Sheets")
        dialog.geometry("300x200")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(
            dialog,
            text="What do you want to export?",
            font=ctk.CTkFont(size=13),
        ).pack(pady=(20, 16))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=4)

        def choose(mode):
            result["mode"] = mode
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Sheets only", width=200,
                      command=lambda: choose("sheets")).pack(pady=4)
        ctk.CTkButton(btn_frame, text="ZIP only", width=200,
                      command=lambda: choose("zip")).pack(pady=4)
        ctk.CTkButton(btn_frame, text="Both", width=200,
                      command=lambda: choose("both")).pack(pady=4)

        ctk.CTkButton(dialog, text="Cancel", fg_color="#581e10", hover_color="#3a1a10",
                      command=dialog.destroy).pack(pady=(8, 0))

        self.wait_window(dialog)
        return result["mode"]

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
            msg = f"{len(sheets)} sheet(s) generated in:\n{output_dir}"
        elif mode == "zip":
            msg = f"ZIP ready for MPC:\n{zip_path}"
        else:
            msg = f"{len(sheets)} sheet(s) generated in:\n{output_dir}\n\nZIP ready for MPC:\n{zip_path}"

        messagebox.showinfo("Export completed", msg)

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
        config = {"headless": False, "stock": "S30", "login": False,
                  "upload_backs": has_backs, "confirmed": False}

        dialog = ctk.CTkToplevel(self)
        dialog.title("Upload to MPC")
        dialog.geometry("440x550")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.focus_set()

        ctk.CTkLabel(
            dialog,
            text="Upload to MakePlayingCards.com",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            dialog,
            text=f"Deck : {deck.name}   •   {total_slots} carte(s)",
            font=ctk.CTkFont(size=11),
            text_color="#5a5060",
        ).pack(pady=(0, 6))

        # --- Visualisation des seuils MPC ---
        self._add_mpc_threshold_bar(dialog, total_slots, mpc_qty)

        # --- Temps estimé ---
        _est_fronts = total_slots * 35
        _est_backs = total_slots * 20 if has_backs else 0
        _est_total_min = max(1, (_est_fronts + _est_backs + 180) // 60)
        _eta_parts = [f"fronts ~{max(1, _est_fronts // 60)} min"]
        if has_backs:
            _eta_parts.append(f"backs ~{max(1, _est_backs // 60)} min")
        ctk.CTkLabel(
            dialog,
            text=f"Temps estimé : ~{_est_total_min} min  ({' + '.join(_eta_parts)})",
            font=ctk.CTkFont(size=10),
            text_color="gray60",
        ).pack(pady=(0, 6))

        # Avertissement slots vides
        if empty_slots > 0:
            warn_frame = ctk.CTkFrame(dialog, fg_color="#2a1010", corner_radius=6)
            warn_frame.pack(padx=20, fill="x", pady=(0, 8))
            ctk.CTkLabel(
                warn_frame,
                text=f"⚠  {empty_slots} slot(s) vide(s) — ils apparaîtront à la fin de la commande MPC.",
                font=ctk.CTkFont(size=10),
                text_color="#c4bfb8",
                wraplength=380,
                justify="left",
            ).pack(padx=10, pady=6)

        # Choix du stock
        stock_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        stock_frame.pack(padx=24, anchor="w", pady=(0, 6))
        ctk.CTkLabel(stock_frame, text="Card stock :", font=ctk.CTkFont(size=11)).pack(
            side="left", padx=(0, 8)
        )
        stock_var = ctk.StringVar(value="S30")
        for s in ("S30", "S33"):
            ctk.CTkRadioButton(
                stock_frame, text=s, variable=stock_var, value=s,
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=6)

        # Connexion MPC
        login_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            dialog,
            text="Se connecter à MPC (2 min pour login, optionnel)",
            variable=login_var,
            font=ctk.CTkFont(size=11),
        ).pack(padx=24, anchor="w", pady=(0, 4))

        # Mode navigateur
        headless_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            dialog,
            text="Mode arrière-plan (navigateur invisible)",
            variable=headless_var,
            font=ctk.CTkFont(size=11),
        ).pack(padx=24, anchor="w", pady=(0, 6))

        # Upload backs
        back_label = ""
        if self.deck_back_image:
            back_label = f" ({os.path.basename(self.deck_back_image)})"
        elif not has_backs:
            back_label = " (aucun endos détecté)"
        upload_backs_var = ctk.BooleanVar(value=has_backs)
        ctk.CTkCheckBox(
            dialog,
            text=f"Uploader les endos{back_label}",
            variable=upload_backs_var,
            state="normal" if has_backs else "disabled",
            font=ctk.CTkFont(size=11),
        ).pack(padx=24, anchor="w", pady=(0, 12))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()

        def on_start():
            if empty_slots > 0:
                if not messagebox.askyesno(
                    "Slots vides",
                    f"Votre deck contient {total_slots} carte(s), mais MPC requiert {mpc_qty} slots.\n\n"
                    f"{empty_slots} slot(s) resteront vides à la fin de la commande.\n\n"
                    "Continuer quand même ?",
                    parent=dialog,
                ):
                    return
            config["headless"] = headless_var.get()
            config["stock"] = stock_var.get()
            config["login"] = login_var.get()
            config["upload_backs"] = upload_backs_var.get()
            config["confirmed"] = True
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Démarrer l'upload", width=170,
                      command=on_start).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Annuler", width=100,
                      fg_color="#581e10", hover_color="#3a1a10",
                      command=dialog.destroy).pack(side="left", padx=6)

        self.wait_window(dialog)
        if not config["confirmed"]:
            return

        cards = list(deck.cards)
        self.statusbar.show_progress()
        self.statusbar.set_status("Ouverture de MPC…")

        threading.Thread(
            target=self._mpc_upload_worker,
            args=(cards, config["headless"], config["stock"], config["login"],
                  total_slots, self.deck_back_image, config["upload_backs"]),
            daemon=True,
        ).start()

    def _add_mpc_threshold_bar(self, parent, total: int, mpc_qty: int) -> None:
        """Affiche la barre visuelle des seuils MPC dans le dialog."""
        import tkinter as tk

        frame = ctk.CTkFrame(parent, fg_color="#1a1820", corner_radius=8)
        frame.pack(padx=20, fill="x", pady=(0, 8))

        ctk.CTkLabel(
            frame,
            text="Seuils MPC (lots de 18)",
            font=ctk.CTkFont(size=10),
            text_color="#5a5060",
        ).pack(anchor="w", padx=12, pady=(8, 2))

        # Canvas pour la barre de progression
        canvas = tk.Canvas(frame, height=52, bg="#1a1820", highlightthickness=0)
        canvas.pack(fill="x", padx=12, pady=(0, 4))

        canvas.update_idletasks()
        W = canvas.winfo_width() or 396

        # Afficher 5 seuils centrés sur le batch actuel
        current_tier = mpc_qty // 18
        first_tier = max(1, current_tier - 2)
        tiers = list(range(first_tier, first_tier + 6))
        thresholds = [t * 18 for t in tiers]
        lo, hi = thresholds[0] - 18, thresholds[-1]

        pad_x = 10
        bar_w = W - pad_x * 2
        bar_y, bar_h = 20, 14

        def x_of(val):
            return pad_x + int(bar_w * (val - lo) / (hi - lo))

        # Fond gris
        canvas.create_rectangle(x_of(lo), bar_y, x_of(hi), bar_y + bar_h,
                                 fill="#252030", outline="")

        # Portion remplie (cartes du deck)
        canvas.create_rectangle(x_of(lo), bar_y, x_of(min(total, hi)), bar_y + bar_h,
                                 fill="#2D6A4F", outline="")

        # Portion vide dans le batch actuel (slots non remplis)
        if total < mpc_qty:
            canvas.create_rectangle(x_of(total), bar_y, x_of(mpc_qty), bar_y + bar_h,
                                     fill="#8B3A00", outline="")

        # Marqueurs de seuil + labels
        for t in thresholds:
            x = x_of(t)
            is_batch = (t == mpc_qty)
            color = "#E8A838" if is_batch else "#606060"
            canvas.create_line(x, bar_y - 4, x, bar_y + bar_h + 4, fill=color, width=1)
            canvas.create_text(x, bar_y + bar_h + 12, text=str(t),
                                fill="#E8A838" if is_batch else "gray60",
                                font=("Arial", 8, "bold" if is_batch else "normal"))

        # Marqueur de position actuelle du deck
        if lo < total <= hi:
            xc = x_of(total)
            canvas.create_line(xc, bar_y - 6, xc, bar_y + bar_h + 6,
                                fill="white", width=2)
            canvas.create_text(xc, bar_y - 11, text=str(total),
                                fill="white", font=("Arial", 8, "bold"))

        # Légende sous la barre
        empty = mpc_qty - total
        if empty == 0:
            legend = f"Batch parfait — {mpc_qty} slots, 0 vide"
            color = "#2D6A4F"
        else:
            legend = f"Batch : {mpc_qty} slots   •   {total} remplis   •   {empty} vides"
            color = "#E8A838"

        ctk.CTkLabel(
            frame,
            text=legend,
            font=ctk.CTkFont(size=10),
            text_color=color,
        ).pack(pady=(0, 8))

    def _mpc_upload_worker(self, cards: list, headless: bool, stock: str,
                           login: bool, total: int, back_image: str | None,
                           upload_backs: bool = True) -> None:
        """Thread : lance l'automation MPC et met à jour la progress bar."""
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
        self.statusbar.hide_progress()
        self.statusbar.set_status("Upload MPC terminé")

    # ======================================================================
    # SYNC CARD BACK + REFRESH UI
    # ======================================================================

    def _sync_back_from_active_deck(self) -> None:
        """Restaure deck_back_image depuis le deck actif et met à jour l'aperçu."""
        deck = self.deck_manager.active_deck()
        self.deck_back_image = deck.back_image if deck else None
        self.workspace.update_back_preview(self.deck_back_image)

    def _refresh_ui(self) -> None:
        """Met à jour le workspace et la sidebar selon le deck actif."""
        deck = self.deck_manager.active_deck()
        if deck:
            self.workspace.load_cards(deck.cards)
        self.sidebar.refresh()

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
        if not messagebox.askyesno("Fermer OtterForge", "Fermer OtterForge ?"):
            return
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
