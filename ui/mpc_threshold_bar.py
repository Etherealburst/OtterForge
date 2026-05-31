"""
ui/mpc_threshold_bar.py
-----------------------
Widget autonome affichant la barre visuelle des seuils MPC (lots de 18).
"""

import tkinter as tk
import customtkinter as ctk


class MPCThresholdBar(ctk.CTkFrame):
    """Affiche la barre de seuils MPC avec légende.

    Args:
        total: nombre de cartes dans le deck.
        mpc_qty: quantité MPC (multiple de 18 >= total).
    """

    def __init__(self, master, total: int, mpc_qty: int, **kwargs):
        super().__init__(master, fg_color="#28252e", corner_radius=8, **kwargs)
        self._build(total, mpc_qty)

    def _build(self, total: int, mpc_qty: int) -> None:
        ctk.CTkLabel(
            self,
            text="MPC Thresholds (batches of 18)",
            font=ctk.CTkFont(size=10),
            text_color="#a09aaa",
        ).pack(anchor="w", padx=12, pady=(8, 2))

        canvas = tk.Canvas(self, height=52, bg="#28252e", highlightthickness=0)
        canvas.pack(fill="x", padx=12, pady=(0, 4))

        canvas.update_idletasks()
        W = canvas.winfo_width() or 396

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

        canvas.create_rectangle(x_of(lo), bar_y, x_of(hi), bar_y + bar_h,
                                 fill="#34303e", outline="")
        canvas.create_rectangle(x_of(lo), bar_y, x_of(min(total, hi)), bar_y + bar_h,
                                 fill="#2D6A4F", outline="")
        if total < mpc_qty:
            canvas.create_rectangle(x_of(total), bar_y, x_of(mpc_qty), bar_y + bar_h,
                                     fill="#8B3A00", outline="")

        for t in thresholds:
            x = x_of(t)
            is_batch = (t == mpc_qty)
            color = "#E8A838" if is_batch else "#606060"
            canvas.create_line(x, bar_y - 4, x, bar_y + bar_h + 4, fill=color, width=1)
            canvas.create_text(x, bar_y + bar_h + 12, text=str(t),
                                fill="#E8A838" if is_batch else "gray60",
                                font=("Arial", 8, "bold" if is_batch else "normal"))

        if lo < total <= hi:
            xc = x_of(total)
            canvas.create_line(xc, bar_y - 6, xc, bar_y + bar_h + 6,
                                fill="white", width=2)
            canvas.create_text(xc, bar_y - 11, text=str(total),
                                fill="white", font=("Arial", 8, "bold"))

        empty = mpc_qty - total
        if empty == 0:
            legend = f"Perfect batch — {mpc_qty} slots, 0 empty"
            color = "#2D6A4F"
        else:
            legend = f"Batch: {mpc_qty} slots   •   {total} filled   •   {empty} empty"
            color = "#E8A838"

        ctk.CTkLabel(
            self,
            text=legend,
            font=ctk.CTkFont(size=10),
            text_color=color,
        ).pack(pady=(0, 8))
