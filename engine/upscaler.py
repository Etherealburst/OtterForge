"""
engine/upscaler.py
------------------
Upscaling d'images de cartes via Real-ESRGAN (×4, 1200 DPI).
Utilise l'exécutable realesrgan-ncnn-vulkan via subprocess.

Prérequis :
  - Real-ESRGAN extrait dans C:/Users/Samuel/Documents/MTG/Real-ESGRAN/
  - L'exécutable realesrgan-ncnn-vulkan.exe doit être présent dans ce dossier
"""

import os
import subprocess

from PIL import Image

from config import REALESRGAN_DIR

REALESRGAN_EXE = os.path.join(REALESRGAN_DIR, "realesrgan-ncnn-vulkan.exe")
REALESRGAN_MODEL = "realesrgan-x4plus"  # modèle ×4 — meilleure qualité pour cartes

# Dimensions MPC à 1200 DPI — carte standard avec fond perdu (bleed)
# Bleed : 0.12" × 1200 DPI = 144 px de chaque côté
# Zone de coupe (trim) = intérieur du pointillé rouge = 3000×4200 px
# Zone totale avec bleed = 3288×4488 px
MPC_TARGET_W  = 3288
MPC_TARGET_H  = 4488
MPC_BLEED_PX  = 144          # 0.12" × 1200 DPI
MPC_TRIM_W    = MPC_TARGET_W - 2 * MPC_BLEED_PX   # 3000 px
MPC_TRIM_H    = MPC_TARGET_H - 2 * MPC_BLEED_PX   # 4200 px

# Dimensions MPC à 300 DPI (images Scryfall natives sans upscaling)
MPC_TARGET_W_300 = 822        # 2.74" × 300 DPI
MPC_TARGET_H_300 = 1122       # 3.74" × 300 DPI
MPC_BLEED_300    = 36         # 0.12" × 300 DPI
MPC_TRIM_W_300   = MPC_TARGET_W_300 - 2 * MPC_BLEED_300   # 750 px
MPC_TRIM_H_300   = MPC_TARGET_H_300 - 2 * MPC_BLEED_300   # 1050 px


class ImageUpscaler:
    """
    Upscale une image de carte ×4 via Real-ESRGAN (1200 DPI).
    Remplace le rééchantillonnage Lanczos par une vraie super-résolution IA.
    """

    def is_available(self) -> bool:
        """Vérifie que l'exécutable Real-ESRGAN est bien présent."""
        return os.path.isfile(REALESRGAN_EXE)

    def upscale_to_1200dpi(self, image_path: str, output_path: str) -> str:
        """
        Upscale une image ×4 via Real-ESRGAN et la sauvegarde à output_path.
        Retourne le chemin du fichier de sortie.
        Lève une exception si Real-ESRGAN est introuvable ou échoue.
        """
        if not self.is_available():
            raise FileNotFoundError(
                f"Real-ESRGAN introuvable : {REALESRGAN_EXE}\n"
                "Vérifie que le dossier Real-ESRGAN est bien à :\n"
                f"{REALESRGAN_DIR}"
            )

        cmd = [
            REALESRGAN_EXE,
            "-i", image_path,
            "-o", output_path,
            "-n", REALESRGAN_MODEL,
            "-s", "4",          # facteur ×4
            "-f", "png",        # format de sortie
        ]

        print(f"[ImageUpscaler] Upscaling : {os.path.basename(image_path)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Real-ESRGAN a échoué pour {image_path!r}\n"
                f"stderr : {result.stderr}"
            )

        self._fit_to_mpc(output_path)
        print(f"[ImageUpscaler] OK → {output_path}")
        return output_path

    def _fit_to_mpc(self, image_path: str) -> None:
        """Scale-to-fit dans la zone de coupe + fond noir pour le bleed (3288×4488 px).

        Approche correcte pour MPC :
          - La carte (contenu + bordure) tient entièrement dans la zone de coupe (3000×4200).
          - Les 144 px de chaque côté (fond perdu) sont remplis en noir.
          - Résultat : aucun contenu ne dépasse le pointillé rouge (ligne de coupe).
        """
        img = Image.open(image_path)
        w, h = img.size
        if (w, h) == (MPC_TARGET_W, MPC_TARGET_H):
            return

        # Scale-to-fit dans la zone de coupe (pas de crop)
        scale = min(MPC_TRIM_W / w, MPC_TRIM_H / h)
        new_w = round(w * scale)
        new_h = round(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Canvas noir (fond perdu) à la taille complète avec bleed
        canvas = Image.new("RGB", (MPC_TARGET_W, MPC_TARGET_H), (0, 0, 0))
        x_off = (MPC_TARGET_W - new_w) // 2
        y_off = (MPC_TARGET_H - new_h) // 2
        canvas.paste(img.convert("RGB"), (x_off, y_off))
        canvas.save(image_path, "PNG")
        print(f"[ImageUpscaler] Bleed ajouté → {MPC_TARGET_W}×{MPC_TARGET_H} px "
              f"(carte : {new_w}×{new_h}, offset : {x_off},{y_off})")

    def fit_native_to_mpc_300(self, input_path: str, output_path: str) -> str:
        """Adapte une image Scryfall native (745×1040) au format MPC 300 DPI (822×1122) avec bleed.

        Même logique que _fit_to_mpc : scale-to-fit dans la zone de coupe + fond noir.
        Utilisé quand Real-ESRGAN n'est pas disponible.
        Retourne output_path.
        """
        img = Image.open(input_path)
        w, h = img.size

        if (w, h) == (MPC_TARGET_W_300, MPC_TARGET_H_300) and input_path == output_path:
            return output_path

        scale = min(MPC_TRIM_W_300 / w, MPC_TRIM_H_300 / h)
        new_w = round(w * scale)
        new_h = round(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        canvas = Image.new("RGB", (MPC_TARGET_W_300, MPC_TARGET_H_300), (0, 0, 0))
        x_off = (MPC_TARGET_W_300 - new_w) // 2
        y_off = (MPC_TARGET_H_300 - new_h) // 2
        canvas.paste(img.convert("RGB"), (x_off, y_off))
        canvas.save(output_path, "PNG")
        print(f"[ImageUpscaler] 300 DPI bleed → {output_path}")
        return output_path

    # Alias pour compatibilité avec l'ancien code
    def upscale_to_900dpi(self, image_path: str, output_path: str) -> str:
        """Alias vers upscale_to_1200dpi — conservé pour compatibilité."""
        return self.upscale_to_1200dpi(image_path, output_path)
