"""Shark Tank pitch — Slide 3: The IE Intervention concept diagram.

Simple conceptual "before/after" block diagram. No map, no data — just a
clean illustration of the model: primaries stay local, secondaries go regional.

Output: pitch_slide3_concept.png (1920x1080)
"""
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import matplotlib.patheffects as pe

ROOT = Path(__file__).parent

fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
fig.patch.set_facecolor("white")
ax.set_xlim(0, 100); ax.set_ylim(0, 60)
ax.axis("off")

# Title
fig.suptitle(
    "The IE Intervention: Hybrid Local + Regional Model",
    fontsize=28, fontweight="bold", color="#111", y=0.95,
)
fig.text(0.5, 0.89,
         "Primaries stay local · Secondaries go regional · Dispatch routes to closest unit",
         fontsize=15, color="#2C7FB8", ha="center", style="italic")

# ---- LEFT: Current state ----
ax.text(25, 52, "TODAY", fontsize=22, fontweight="bold", color="#B22222",
        ha="center", va="center")
ax.text(25, 49, "12 independent departments", fontsize=13, color="#555",
        ha="center", va="center", style="italic")

# 5 small dept boxes (each with its own primary + secondary)
dept_names = ["Dept A", "Dept B", "Dept C", "Dept D", "Dept E"]
dx_positions = [6, 16, 26, 36, 46]
for i, (name, x) in enumerate(zip(dept_names, dx_positions)):
    # Dept box
    box = FancyBboxPatch((x - 4, 18), 8, 26,
                         boxstyle="round,pad=0.02,rounding_size=0.3",
                         facecolor="#FFF5F5", edgecolor="#B22222",
                         linewidth=1.5)
    ax.add_patch(box)
    ax.text(x, 41, name, fontsize=11, fontweight="bold",
            color="#B22222", ha="center")
    # Primary ambulance icon
    ax.text(x, 34, "[A]", fontsize=18, fontweight="bold", ha="center", va="center",
            color="#B22222",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#B22222", linewidth=1.5))
    ax.text(x, 30, "Primary", fontsize=9, color="#333", ha="center")
    # Secondary ambulance icon (faded — "idle 85% of time")
    ax.text(x, 24, "[A]", fontsize=18, fontweight="bold", ha="center", va="center",
            color="#888",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#BBB", linewidth=1.5))
    ax.text(x, 19, "Backup\n(idle 85%)", fontsize=9, color="#999",
            ha="center", style="italic")

# Pain-point callout
ax.text(25, 10,
        "Each department funds, staffs, and maintains its own backup.\n"
        "Still: 41 all-busy events / year countywide.",
        fontsize=13, color="#B22222", ha="center", va="center",
        fontweight="bold", style="italic",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF5F5",
                  edgecolor="#B22222", linewidth=1.5))

# ---- DIVIDER arrow ----
arrow = FancyArrowPatch((52, 30), (58, 30),
                        arrowstyle="->,head_width=2,head_length=3",
                        color="#444", linewidth=3, mutation_scale=1)
ax.add_patch(arrow)

# ---- RIGHT: Proposed state ----
ax.text(78, 52, "PROPOSED", fontsize=22, fontweight="bold", color="#2C7FB8",
        ha="center", va="center")
ax.text(78, 49, "Local primaries + 4 shared regionals", fontsize=13,
        color="#555", ha="center", va="center", style="italic")

# Same 5 dept boxes, primaries only
r_positions = [62, 68, 74, 80, 86]
for name, x in zip(dept_names, r_positions):
    box = FancyBboxPatch((x - 2.8, 34), 5.6, 10,
                         boxstyle="round,pad=0.02,rounding_size=0.3",
                         facecolor="#F0F8FF", edgecolor="#2C7FB8",
                         linewidth=1.3)
    ax.add_patch(box)
    ax.text(x, 42, name, fontsize=9, fontweight="bold",
            color="#2C7FB8", ha="center")
    ax.text(x, 38, "[A]", fontsize=13, fontweight="bold", ha="center", va="center",
            color="#2C7FB8",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                      edgecolor="#2C7FB8", linewidth=1.2))

ax.text(74, 30, "← Primaries stay local (autonomy preserved) →",
        fontsize=11, color="#2C7FB8", ha="center",
        style="italic", fontweight="bold")

# Regional stations row — 4 blue stars
reg_positions = [65, 71, 77, 83]
for i, x in enumerate(reg_positions, 1):
    ax.plot(x, 22, "*", markersize=42, color="#B22222",
            markeredgecolor="white", markeredgewidth=2)
    ax.text(x, 17, f"SEC-{i}", fontsize=11, fontweight="bold",
            color="#B22222", ha="center",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")])

ax.text(74, 11,
        "4 regional secondary stations shared across all 12 departments.\n"
        "Dispatch routes whichever ambulance reaches the patient fastest.",
        fontsize=13, color="#2C7FB8", ha="center", va="center",
        fontweight="bold", style="italic",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#F0F8FF",
                  edgecolor="#2C7FB8", linewidth=1.5))

# ---- IE methodology footer ----
fig.text(0.5, 0.045,
         "Methodology: P-Median facility location (Amazon logistics) · "
         "Erlang-C queuing (call-center staffing) · "
         "OpenRouteService drive-time validation",
         fontsize=11, color="#555", ha="center", style="italic")

out = ROOT / "pitch_slide3_concept.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: {out}")
