"""
engine/deck_manager.py
----------------------
Gestion des decks : création, switch, ajout de cartes, save/load JSON.
"""

import json
import os
from engine.models import Card


class Deck:
    """Représente un deck Magic (nom + liste de cartes)."""

    def __init__(self, name: str):
        self.name = name
        self.cards: list[Card] = []
        self.back_image: str | None = None

    def __repr__(self):
        return f"Deck(name={self.name!r}, cards={len(self.cards)})"


class DeckManager:
    """
    Gère la liste des decks ouverts et le deck actif.
    Fournit les opérations CRUD : création, switch, save, load, ajout bulk.
    """

    def __init__(self):
        self.decks: list[Deck] = []
        self.active_index: int = 0

    # ------------------------------------------------------------------
    # ACCÈS AU DECK ACTIF
    # ------------------------------------------------------------------

    def active_deck(self) -> Deck | None:
        """Retourne le deck actif, ou None si aucun deck n'existe."""
        if not self.decks:
            return None
        return self.decks[self.active_index]

    # ------------------------------------------------------------------
    # CRÉER / SWITCHER
    # ------------------------------------------------------------------

    def create_deck(self, name: str) -> Deck:
        """Crée un nouveau deck vide et le définit comme actif."""
        deck = Deck(name)
        self.decks.append(deck)
        self.active_index = len(self.decks) - 1
        return deck

    def set_active(self, index: int) -> None:
        """Change le deck actif par index. Ignore si l'index est invalide."""
        if 0 <= index < len(self.decks):
            self.active_index = index

    def rename_deck(self, index: int, new_name: str) -> None:
        """Renomme le deck à l'index donné."""
        if 0 <= index < len(self.decks):
            self.decks[index].name = new_name

    def delete_deck(self, index: int) -> None:
        """Supprime le deck à l'index donné. Impossible si c'est le seul deck."""
        if len(self.decks) <= 1 or not (0 <= index < len(self.decks)):
            return
        self.decks.pop(index)
        if self.active_index >= len(self.decks):
            self.active_index = len(self.decks) - 1

    # ------------------------------------------------------------------
    # AJOUTER DES CARTES
    # ------------------------------------------------------------------

    @staticmethod
    def _card_name_key(name: str) -> str:
        """Retourne la clé de comparaison pour un nom de carte.
        Pour les DFC, ne retient que la face recto (avant ' // ').
        Permet de fusionner 'Delver of Secrets' et 'Delver of Secrets // Insectile Aberration'.
        """
        return name.split(" // ")[0].strip().lower()

    def add_card(self, card: Card) -> None:
        """
        Ajoute une carte au deck actif.
        Si une carte du même nom existe déjà, incrémente son count.
        Met aussi à jour back_image_path si la nouvelle carte en a un (DFC).
        Comparaison insensible à la casse et tolérante aux noms DFC complets ('A // B' == 'A').
        """
        deck = self.active_deck()
        if not deck:
            return

        key = self._card_name_key(card.name)
        for existing in deck.cards:
            if self._card_name_key(existing.name) == key:
                existing.count += card.count
                if card.back_image_path:
                    existing.back_image_path = card.back_image_path
                return

        deck.cards.append(card)

    def add_cards_bulk(self, cards: list[dict]) -> None:
        """
        Ajoute plusieurs cartes à la fois depuis une liste de dicts.
        Format attendu : [{"name": str, "image_path": str, "count": int, "back_image_path": str|None}]
        Fusionne par nom (même logique que add_card) : pas de doublons si la carte existe déjà.
        """
        if not self.active_deck():
            return

        for c in cards:
            card = Card(c["name"], c["image_path"])
            card.count = c.get("count", 1)
            card.back_image_path = c.get("back_image_path")
            self.add_card(card)

    # ------------------------------------------------------------------
    # SAVE / LOAD JSON
    # ------------------------------------------------------------------

    def save_deck(self, path: str) -> None:
        """Sauvegarde le deck actif en JSON."""
        deck = self.active_deck()
        if deck:
            self.save_deck_at(deck, path)

    def save_deck_at(self, deck: "Deck", path: str) -> None:
        """Sauvegarde un deck spécifique en JSON."""
        data = {
            "name": deck.name,
            "back_image": deck.back_image,
            "cards": [c.to_dict() for c in deck.cards],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_deck(self, path: str) -> Deck:
        """
        Charge un deck depuis un fichier JSON et le définit comme actif.
        Retourne le deck chargé.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        deck = Deck(data["name"])
        deck.back_image = data.get("back_image")

        skipped = 0
        for c in data["cards"]:
            # Ignorer les faces DFC (face1+) — stockées dans back_image_path de la face0
            if "_face1" in c.get("image_path", ""):
                continue
            image_path = c["image_path"]
            # Résoudre le chemin réel : upscalé si disponible, sinon natif
            if not os.path.exists(image_path) and image_path.endswith("_1200dpi.png"):
                native = image_path.replace("_1200dpi.png", ".png")
                if os.path.exists(native):
                    image_path = native
            if not os.path.exists(image_path):
                skipped += 1
                continue
            card = Card(c["name"], image_path)
            card.count = c.get("count", 1)
            # Résoudre back_image_path : fallback natif si l'upscalé est absent
            bp = c.get("back_image_path")
            if bp:
                if not os.path.exists(bp) and bp.endswith("_1200dpi.png"):
                    bp_native = bp.replace("_1200dpi.png", ".png")
                    bp = bp_native if os.path.exists(bp_native) else None
                elif bp and not os.path.exists(bp):
                    bp = None
            card.back_image_path = bp
            deck.cards.append(card)
        if skipped:
            print(f"[DeckManager] {skipped} carte(s) ignorée(s) — fichiers image introuvables")

        self.decks.append(deck)
        self.active_index = len(self.decks) - 1

        return deck
