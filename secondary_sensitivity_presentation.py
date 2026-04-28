"""
Presentation-quality sensitivity analysis charts for the Jefferson County
secondary ambulance network recommendation.

4-panel figure showing:
  1. Coverage (%) vs number of stations — all 3 objectives
  2. Average response time vs number of stations — P-Median
  3. Marginal gain per additional station (coverage + RT)
  4. Cost vs coverage — staffing scenario comparison

Output: secondary_sensitivity_presentation.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load data ─────────────────────────────────────────────────────────────
sol  = pd.read_csv(os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv"))
scen = pd.read_csv(os.path.join(SCRIPT_DIR, "secondary_staffing_scenarios_jeffco.csv"))

# Extract series by objective
sol["T_str"] = sol["T"].astype(str)
mclp10 = sol[(sol.Objective == "MCLP") & (sol.T_str == "10")].sort_values("K").reset_index(drop=True)
mclp14 = sol[(sol.Objective == "MCLP") & (sol.T_str == "14")].sort_values("K").reset_index(drop=True)
pmed   = sol[sol.Objective == "PMed"].sort_values("K").reset_index(drop=True)

K = pmed["K"].values
cov_pmed   = pmed["Demand_Pct_Covered"].values
cov_14     = mclp14["Demand_Pct_Covered"].values
cov_10     = mclp10["Demand_Pct_Covered"].values
rt_pmed    = pmed["Avg_RT"].values
rt_max     = pmed["Max_RT"].values

# Marginal gains
d_cov_pmed = np.diff(cov_pmed)
d_rt_pmed  = np.diff(rt_pmed)
K_mid = K[1:]   # midpoints between K values

# Cost data — extend to K=2,3,4,5 by scaling per-station cost
cost_per_station_247  = 250618   # Peterson net cost per station, 24/7 ALS
cost_per_station_peak = 212849   # peak-only net
cost_per_station_hyb  = 225438   # hybrid

K_cost = np.array([2, 3, 4, 5])
net_247  = K_cost * cost_per_station_247
net_peak = K_cost * cost_per_station_peak
net_hyb  = K_cost * cost_per_station_hyb

# Coverage at each K for cost chart
cov_at_K = {k: v for k, v in zip(K, cov_pmed)}

# ── Style ──────────────────────────────────────────────────────────────────
C_BLUE   = "#2980b9"
C_ORANGE = "#e67e22"
C_RED    = "#c0392b"
C_GREEN  = "#27ae60"
C_GRAY   = "#7f8c8d"
C_LIGHT  = "#ecf0f1"
C_GOLD   = "#f39c12"

REC_K = 4   # recommended number of stations

def _spine(ax):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=10)

def _rec_line(ax, vertical=True):
    """Draw a vertical dashed line at the recommended K."""
    if vertical:
        ax.axvline(REC_K, color=C_RED, linewidth=1.4, linestyle="--", alpha=0.7, zorder=0)

# ── Build figure ───────────────────────────────────────────────────────────
fig = plt.figure(figsize=(16, 11))
fig.patch.set_facecolor("white")
gs = fig.add_gridspec(2, 2, hspace=0.42, wspace=0.32,
                      left=0.07, right=0.97, top=0.88, bottom=0.08)
ax1 = fig.add_subplot(gs[0, 0])
ax2 = fig.add_subplot(gs[0, 1])
ax3 = fig.add_subplot(gs[1, 0])
ax4 = fig.add_subplot(gs[1, 1])

# ── Panel 1: Coverage vs K ─────────────────────────────────────────────────
ax1.plot(K, cov_pmed, "o-", color=C_BLUE,   linewidth=2.2, markersize=8,
         label="P-Median (minimize avg RT)")
ax1.plot(K, cov_14,   "s-", color=C_ORANGE, linewidth=2.2, markersize=8,
         label="MCLP — 14 min threshold")
ax1.plot(K, cov_10,   "^-", color=C_GRAY,   linewidth=2.2, markersize=8,
         label="MCLP — 10 min threshold")

# Annotate recommended K
ax1.axvspan(REC_K - 0.15, REC_K + 0.15, color=C_RED, alpha=0.08, zorder=0)
_rec_line(ax1)
ax1.annotate("Recommended\nK = 4", xy=(REC_K, cov_pmed[K == REC_K][0]),
             xytext=(REC_K + 0.25, cov_pmed[K == REC_K][0] - 6),
             fontsize=9, color=C_RED, fontweight="bold",
             arrowprops=dict(arrowstyle="-|>", color=C_RED, lw=1.0))

# Annotate each point
for k, c in zip(K, cov_pmed):
    ax1.text(k, c + 1.2, f"{c:.0f}%", ha="center", fontsize=8.5,
             color=C_BLUE, fontweight="bold")

ax1.set_xlabel("Number of Secondary Stations (K)", fontsize=11)
ax1.set_ylabel("Demand Covered ≤ threshold (%)", fontsize=11)
ax1.set_title("Coverage vs Fleet Size", fontsize=13, fontweight="bold", pad=10)
ax1.set_xticks(K)
ax1.set_ylim(25, 95)
ax1.legend(fontsize=9, frameon=False, loc="upper left")
ax1.grid(axis="y", alpha=0.25, color="#ccc")
_spine(ax1)

# ── Panel 2: Avg RT vs K ───────────────────────────────────────────────────
ax2.fill_between(K, rt_max, rt_pmed, alpha=0.12, color=C_BLUE, label="RT range (avg–max)")
ax2.plot(K, rt_pmed, "o-", color=C_BLUE, linewidth=2.5, markersize=9,
         label="Avg response time (P-Median)", zorder=3)
ax2.plot(K, rt_max,  "s--", color=C_GRAY, linewidth=1.3, markersize=6,
         label="Max response time", alpha=0.7)

# NFPA 8-min benchmark line
ax2.axhline(8, color=C_GREEN, linewidth=1.3, linestyle=":", alpha=0.8)
ax2.text(5.05, 8.2, "NFPA 8-min\ntarget", fontsize=8, color=C_GREEN, va="bottom")

# 14-min benchmark
ax2.axhline(14, color=C_ORANGE, linewidth=1.3, linestyle=":", alpha=0.8)
ax2.text(5.05, 14.2, "14-min\nbenchmark", fontsize=8, color=C_ORANGE, va="bottom")

_rec_line(ax2)
for k, r in zip(K, rt_pmed):
    ax2.text(k, r - 0.8, f"{r:.1f} min", ha="center", fontsize=8.5,
             color=C_BLUE, fontweight="bold")

ax2.set_xlabel("Number of Secondary Stations (K)", fontsize=11)
ax2.set_ylabel("Response Time (minutes)", fontsize=11)
ax2.set_title("Average Response Time vs Fleet Size", fontsize=13, fontweight="bold", pad=10)
ax2.set_xticks(K)
ax2.set_ylim(5, 52)
ax2.legend(fontsize=9, frameon=False, loc="upper right")
ax2.grid(axis="y", alpha=0.25, color="#ccc")
_spine(ax2)

# ── Panel 3: Marginal gain ─────────────────────────────────────────────────
bar_w = 0.35
x = np.arange(len(K_mid))

bars1 = ax3.bar(x - bar_w/2, d_cov_pmed, bar_w,
                color=[C_BLUE if k < REC_K else C_GRAY for k in K_mid],
                label="Coverage gain (pp)", edgecolor="white", linewidth=0.5)

ax3_r = ax3.twinx()
bars2 = ax3_r.bar(x + bar_w/2, np.abs(d_rt_pmed), bar_w,
                  color=[C_ORANGE if k < REC_K else C_GOLD for k in K_mid],
                  label="RT reduction (min)", edgecolor="white", linewidth=0.5,
                  alpha=0.85)

# Annotate bars
for bar, v in zip(bars1, d_cov_pmed):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
             f"+{v:.1f}pp", ha="center", fontsize=9, color=C_BLUE, fontweight="bold")
for bar, v in zip(bars2, np.abs(d_rt_pmed)):
    ax3_r.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
               f"−{v:.1f}m", ha="center", fontsize=9, color=C_ORANGE, fontweight="bold")

# Elbow label
elbow_idx = list(K_mid).index(REC_K) if REC_K in K_mid else None
if elbow_idx is not None:
    ax3.annotate("← Elbow\n(diminishing\nreturns after K=4)",
                 xy=(elbow_idx - bar_w/2, d_cov_pmed[elbow_idx]),
                 xytext=(elbow_idx - 0.6, d_cov_pmed[elbow_idx] + 2.5),
                 fontsize=8.5, color=C_RED, fontweight="bold",
                 arrowprops=dict(arrowstyle="-|>", color=C_RED, lw=0.9))

ax3.set_xticks(x)
ax3.set_xticklabels([f"K={k-1}→{k}" for k in K_mid], fontsize=10)
ax3.set_xlabel("Station Added", fontsize=11)
ax3.set_ylabel("Coverage gain (percentage points)", fontsize=11, color=C_BLUE)
ax3_r.set_ylabel("Avg RT reduction (minutes)", fontsize=11, color=C_ORANGE)
ax3.set_title("Marginal Gain per Additional Station", fontsize=13, fontweight="bold", pad=10)
ax3.tick_params(axis="y", colors=C_BLUE)
ax3_r.tick_params(axis="y", colors=C_ORANGE)
ax3.grid(axis="y", alpha=0.2, color="#ccc")

legend_els = [
    mpatches.Patch(color=C_BLUE,   label="Coverage gain (pp, left axis)"),
    mpatches.Patch(color=C_ORANGE, label="RT reduction (min, right axis)"),
    mpatches.Patch(color=C_GRAY,   label="Post-elbow (diminishing returns)"),
]
ax3.legend(handles=legend_els, fontsize=8.5, frameon=False, loc="upper right")
for sp in ("top",): ax3.spines[sp].set_visible(False)
ax3_r.spines["top"].set_visible(False)

# ── Panel 4: Cost vs Coverage ──────────────────────────────────────────────
cov_vals = np.array([cov_at_K.get(k, np.nan) for k in K_cost])

ax4.plot(cov_vals, net_247  / 1e6, "o-", color=C_RED,    linewidth=2.2,
         markersize=8, label="24/7 ALS (all stations)")
ax4.plot(cov_vals, net_hyb  / 1e6, "s-", color=C_BLUE,   linewidth=2.2,
         markersize=8, label="Hybrid (1×24/7 + rest peak)")
ax4.plot(cov_vals, net_peak / 1e6, "^-", color=C_GREEN,  linewidth=2.2,
         markersize=8, label="Peak-only (08:00–20:00)")

# Annotate K values
for k, c, c247, cpeak, chyb in zip(K_cost, cov_vals,
                                     net_247/1e6, net_peak/1e6, net_hyb/1e6):
    ax4.text(c + 0.4, c247 + 0.02, f"K={k}", fontsize=8.5,
             color=C_RED, fontweight="bold")

# Highlight recommended K=4
rec_cov = cov_at_K.get(REC_K, None)
if rec_cov:
    ax4.axvline(rec_cov, color=C_RED, linewidth=1.3, linestyle="--", alpha=0.6)
    ax4.text(rec_cov + 0.3, 0.28, f"K={REC_K}\nrecommended",
             fontsize=8.5, color=C_RED, fontweight="bold")

ax4.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x:.1f}M"))
ax4.set_xlabel("Demand Covered ≤ 14 min (%, P-Median)", fontsize=11)
ax4.set_ylabel("Net Annual Cost (after billing revenue)", fontsize=11)
ax4.set_title("Cost vs Coverage — Staffing Scenarios", fontsize=13, fontweight="bold", pad=10)
ax4.legend(fontsize=9, frameon=False, loc="upper left")
ax4.grid(alpha=0.25, color="#ccc")
_spine(ax4)

# ── Supertitle & footnote ──────────────────────────────────────────────────
fig.suptitle(
    "Jefferson County EMS — Secondary Ambulance Network Sensitivity Analysis",
    fontsize=15, fontweight="bold", y=0.95
)
fig.text(0.5, 0.022,
         "Demand weights: Megan's authoritative 2024 call volumes (8,396 calls, Jefferson-County geography only)  |  "
         "Optimization: P-Median minimizes population-weighted avg RT  |  "
         "Cost: Peterson model ($716K operating / $466K revenue per 24/7 ALS station)",
         ha="center", fontsize=8, color="#777", style="italic")

out = os.path.join(SCRIPT_DIR, "secondary_sensitivity_presentation.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: {out}")
