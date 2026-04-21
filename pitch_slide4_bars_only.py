"""Shark Tank pitch — Slide 4 LEFT-PANEL ONLY (Before bar chart).

Stripped-down bar chart of all-busy events by department. The right-side KPI
cards are built as native PowerPoint shapes in build_pitch_deck.py, so this
PNG is just the chart portion.

Output: pitch_slide4_bars_only.png
"""
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent

cc = pd.read_csv(ROOT / "concurrent_call_results_jeffco.csv")
cc = cc[cc["Ambulances"] > 0]
cc = cc[cc["All_Busy_Events"] > 0]
cc = cc.sort_values("All_Busy_Events", ascending=True)
total_all_busy = int(cc["All_Busy_Events"].sum())

fig, ax = plt.subplots(figsize=(9.5, 6.5), dpi=120)
fig.patch.set_facecolor("white")
ax.set_facecolor("#FAFAFA")

colors = ["#B22222" if v >= 10 else "#D95F0E" if v >= 5 else "#E8A87C"
          for v in cc["All_Busy_Events"]]
bars = ax.barh(cc["Dept"], cc["All_Busy_Events"], color=colors,
               edgecolor="white", linewidth=1.5, height=0.7)

for bar, v in zip(bars, cc["All_Busy_Events"]):
    ax.text(v + 0.5, bar.get_y() + bar.get_height() / 2,
            f"{int(v)}", va="center", ha="left",
            fontsize=18, fontweight="bold", color="#222")

ax.set_xlim(0, max(cc["All_Busy_Events"]) * 1.30)
ax.set_xlabel("All-busy events per year (CY2024)",
              fontsize=14, fontweight="bold", labelpad=10)
ax.tick_params(axis="y", labelsize=16)
ax.tick_params(axis="x", labelsize=12)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("#888")
ax.spines["bottom"].set_color("#888")
ax.grid(axis="x", alpha=0.3, linestyle="--")

# Subtle Ixonia annotation in the empty space to the far right
ixonia_y = list(cc["Dept"]).index("Ixonia")
ax.text(24, ixonia_y, "≈ once every\n2.5 weeks",
        fontsize=11, fontweight="bold", color="#B22222",
        ha="left", va="center", style="italic")

plt.tight_layout()
out = ROOT / "pitch_slide4_bars_only.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: {out}")
print(f"Total all-busy: {total_all_busy}")
