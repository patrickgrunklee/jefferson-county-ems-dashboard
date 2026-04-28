"""
Sensitivity analysis charts for Jefferson County secondary ambulance network.
Scans K=2 through 6, runs P-Median on total call volume demand weights.

For each K extracts:
  - Per-BG response time distribution → median, mean, P90
  - % of secondary (concurrent) calls covered within 14 min

Two clean presentation charts (no recommendation lines):
  Chart 1: Median / Mean / P90 response time vs K
  Chart 2: % of secondary calls covered vs K

Output: secondary_sensitivity_charts.png
"""

import os, sys, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from pareto_facility import (
    load_candidates, load_bg_demand, fetch_cand_bg_matrix,
    solve_pmedian_pop,
)
from facility_location import STATIONS as EXISTING_STATIONS
from jefferson_geo_filter import AUTHORITATIVE_2024
from secondary_network_model import SERVICE_AREA_POP, allocate_total_demand_to_bgs

K_RANGE = [2, 3, 4, 5, 6]

# NFPA 1720 zone thresholds (RT min, compliance percentile)
NFPA_ZONES = {
    "Urban":    {"threshold": 9,  "pctile": 0.90, "density_min": 1000},
    "Suburban": {"threshold": 10, "pctile": 0.80, "density_min": 500},
    "Rural":    {"threshold": 14, "pctile": 0.80, "density_min": 0},
}
COVER_THRESHOLD_MIN = 14   # secondary call "covered" if RT <= 14 min

# ── Load base data ─────────────────────────────────────────────────────────
print("Loading data...")
candidates       = load_candidates()
bg_demand, pop_w = load_bg_demand()
tm               = fetch_cand_bg_matrix(candidates, bg_demand)
demand_w         = allocate_total_demand_to_bgs(bg_demand, pop_w)

# Load BG density zones from geojson
with open(os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")) as f:
    bg_geo = json.load(f)
import json as _json

bg_zones = []
for feat in bg_geo["features"]:
    d = feat["properties"]["density_sqmi"]
    if d >= 1000:
        bg_zones.append("Urban")
    elif d >= 500:
        bg_zones.append("Suburban")
    else:
        bg_zones.append("Rural")
bg_zones = np.array(bg_zones)
print(f"  BG zones — Urban: {(bg_zones=='Urban').sum()}  "
      f"Suburban: {(bg_zones=='Suburban').sum()}  "
      f"Rural: {(bg_zones=='Rural').sum()}")

# Secondary concurrent calls per dept (Jefferson-only)
conc = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_results_jeffco.csv"))
total_secondary = conc["Secondary_Events"].sum()
print(f"  Total secondary events (Jefferson-only): {total_secondary}")

# ── Run P-Median for each K and collect RT distributions ──────────────────
print(f"\nRunning P-Median for K={K_RANGE}...")

results = {}
for k in K_RANGE:
    print(f"  K={k}...", end=" ", flush=True)
    # Pass demand_w as pop_weights so the P-Median minimizes demand-weighted RT
    res = solve_pmedian_pop(tm, candidates, bg_demand, k, demand_w)
    if res is None:
        print("FAILED")
        continue

    open_ids = [i for i, cand in enumerate(candidates)
                if any(abs(cand["lat"] - s["lat"]) < 1e-4 and
                       abs(cand["lon"] - s["lon"]) < 1e-4
                       for s in res["open_stations"])]

    # Per-BG response time to nearest open station
    bg_rts = np.array([
        min(tm[i, j] for i in open_ids)
        for j in range(len(bg_demand))
    ], dtype=float)

    # Population-weighted RT percentiles
    # Weight each BG RT by its demand (total call volume proxy)
    w = demand_w.copy()
    w_sum = w.sum()
    if w_sum == 0:
        w = np.ones(len(bg_rts))
        w_sum = w.sum()
    w_norm = w / w_sum

    # Weighted percentiles via sorting
    valid = ~np.isnan(bg_rts)
    rts_v = bg_rts[valid]
    w_v   = w_norm[valid]
    sort_idx = np.argsort(rts_v)
    rts_sorted = rts_v[sort_idx]
    w_sorted   = w_v[sort_idx]
    cumw = np.cumsum(w_sorted)

    def wpctile(p):
        idx = np.searchsorted(cumw, p / 100.0)
        return rts_sorted[min(idx, len(rts_sorted) - 1)]

    w_median = wpctile(50)
    w_mean   = np.sum(rts_v * w_v)
    w_p90    = wpctile(90)

    # Secondary call coverage: fraction of secondary events whose BG RT <= threshold
    from secondary_network_model import allocate_demand_to_bgs
    sec_w = allocate_demand_to_bgs(conc, bg_demand, pop_w)
    sec_total = sec_w.sum()
    covered_sec = sec_w[bg_rts <= COVER_THRESHOLD_MIN].sum()
    pct_sec_covered = 100 * covered_sec / sec_total if sec_total > 0 else 0

    # NFPA 1720 compliance per zone
    # For each zone: what % of that zone's population is served within the threshold?
    nfpa_compliance = {}
    for zone, spec in NFPA_ZONES.items():
        zone_mask = bg_zones == zone
        if zone_mask.sum() == 0:
            nfpa_compliance[zone] = np.nan
            continue
        zone_pop = pop_w[zone_mask].sum()
        # Pop served within zone's threshold
        served_pop = pop_w[zone_mask & (bg_rts <= spec["threshold"])].sum()
        nfpa_compliance[zone] = 100 * served_pop / zone_pop if zone_pop > 0 else 0

    results[k] = {
        "median_rt": w_median,
        "mean_rt":   w_mean,
        "p90_rt":    w_p90,
        "pct_sec_covered": pct_sec_covered,
        "nfpa": nfpa_compliance,
        "open_stations": res["open_stations"],
    }
    print(f"median={w_median:.1f} mean={w_mean:.1f} P90={w_p90:.1f} | "
          f"sec_cov={pct_sec_covered:.1f}% | "
          f"NFPA Urban={nfpa_compliance['Urban']:.0f}% "
          f"Sub={nfpa_compliance['Suburban']:.0f}% "
          f"Rural={nfpa_compliance['Rural']:.0f}%")

K_vals       = [k for k in K_RANGE if k in results]
median_vals  = [results[k]["median_rt"]       for k in K_vals]
mean_vals    = [results[k]["mean_rt"]         for k in K_vals]
p90_vals     = [results[k]["p90_rt"]          for k in K_vals]
sec_cov_vals = [results[k]["pct_sec_covered"] for k in K_vals]
urban_vals   = [results[k]["nfpa"]["Urban"]    for k in K_vals]
sub_vals     = [results[k]["nfpa"]["Suburban"] for k in K_vals]
rural_vals   = [results[k]["nfpa"]["Rural"]    for k in K_vals]

# ── Plot ───────────────────────────────────────────────────────────────────
C_MED    = "#2980b9"
C_MEAN   = "#e67e22"
C_P90    = "#8e44ad"
C_SEC    = "#27ae60"
C_URBAN  = "#e74c3c"
C_SUB    = "#e67e22"
C_RURAL  = "#3498db"

fig, axes = plt.subplots(1, 3, figsize=(20, 7))
fig.patch.set_facecolor("white")
ax1, ax2, ax3 = axes

def _spine(ax):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=11)

# ── Chart 1: RT percentiles ────────────────────────────────────────────────
ax1.plot(K_vals, median_vals, "o-", color=C_MED,  linewidth=2.5, markersize=9,
         label="Median RT")
ax1.plot(K_vals, mean_vals,   "s-", color=C_MEAN, linewidth=2.5, markersize=9,
         label="Mean RT")
ax1.plot(K_vals, p90_vals,    "^-", color=C_P90,  linewidth=2.5, markersize=9,
         label="P90 RT")

for k, med, mn, p90 in zip(K_vals, median_vals, mean_vals, p90_vals):
    ax1.text(k, med - 1.0, f"{med:.1f}", ha="center", fontsize=9,
             color=C_MED,  fontweight="bold")
    ax1.text(k, mn  + 0.5, f"{mn:.1f}",  ha="center", fontsize=9,
             color=C_MEAN, fontweight="bold")
    ax1.text(k, p90 + 0.5, f"{p90:.1f}", ha="center", fontsize=9,
             color=C_P90,  fontweight="bold")

# NFPA 1720 threshold reference lines
ax1.axhline(9,  color=C_URBAN, linewidth=1.1, linestyle=":", alpha=0.7)
ax1.axhline(10, color=C_SUB,   linewidth=1.1, linestyle=":", alpha=0.7)
ax1.axhline(14, color=C_RURAL, linewidth=1.1, linestyle=":", alpha=0.7)
xlim_r = K_vals[-1] + 0.15
ax1.text(xlim_r, 9.15,  "Urban 9 min",    fontsize=8, color=C_URBAN)
ax1.text(xlim_r, 10.15, "Suburban 10 min", fontsize=8, color=C_SUB)
ax1.text(xlim_r, 14.15, "Rural 14 min",    fontsize=8, color=C_RURAL)

ax1.set_xticks(K_vals)
ax1.set_xlabel("Number of Secondary Ambulance Stations", fontsize=12)
ax1.set_ylabel("Response Time (minutes)", fontsize=12)
ax1.set_title("Response Time Distribution\nvs Number of Stations",
              fontsize=13, fontweight="bold", pad=10)
ax1.legend(fontsize=10, frameon=False, loc="upper right")
ax1.grid(axis="y", alpha=0.2, color="#ccc")
ax1.set_xlim(K_vals[0] - 0.3, K_vals[-1] + 0.7)
_spine(ax1)

# ── Chart 2: Secondary call coverage ──────────────────────────────────────
bars = ax2.bar(K_vals, sec_cov_vals,
               color=C_SEC, edgecolor="white", linewidth=0.8,
               width=0.55, zorder=3)
for bar, v in zip(bars, sec_cov_vals):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
             f"{v:.1f}%", ha="center", fontsize=11,
             color=C_SEC, fontweight="bold")

ax2.set_xticks(K_vals)
ax2.set_xlabel("Number of Secondary Ambulance Stations", fontsize=12)
ax2.set_ylabel("Secondary Calls Covered ≤ 14 min (%)", fontsize=12)
ax2.set_title(f"% Secondary Calls Covered\nvs Number of Stations",
              fontsize=13, fontweight="bold", pad=10)
ax2.set_ylim(0, 105)
ax2.grid(axis="y", alpha=0.2, color="#ccc", zorder=0)
ax2.text(0.03, 0.04,
         f"Secondary demand: {total_secondary:.0f} concurrent events/yr\n"
         f"(Jefferson-only NFIRS 2024  |  covered = RT ≤ 14 min)",
         transform=ax2.transAxes, fontsize=8.5, color="#777",
         bbox=dict(boxstyle="round,pad=0.4", facecolor="#f9f9f9",
                   edgecolor="#ddd", alpha=0.9))
_spine(ax2)

# ── Chart 3: NFPA 1720 zone compliance ────────────────────────────────────
w = 0.25
x = np.arange(len(K_vals))
ax3.bar(x - w, urban_vals, w, color=C_URBAN, label="Urban (≥1,000/sqmi)  →  9 min / 90%",
        edgecolor="white", zorder=3)
ax3.bar(x,     sub_vals,   w, color=C_SUB,   label="Suburban (500–999/sqmi)  →  10 min / 80%",
        edgecolor="white", zorder=3)
ax3.bar(x + w, rural_vals, w, color=C_RURAL, label="Rural (<500/sqmi)  →  14 min / 80%",
        edgecolor="white", zorder=3)

# NFPA compliance thresholds
ax3.axhline(90, color=C_URBAN, linewidth=1.1, linestyle="--", alpha=0.5)
ax3.axhline(80, color=C_SUB,   linewidth=1.1, linestyle="--", alpha=0.5)

# Annotate bars
for i, (u, s, r) in enumerate(zip(urban_vals, sub_vals, rural_vals)):
    ax3.text(i - w, u + 0.8, f"{u:.0f}%", ha="center", fontsize=8,
             color=C_URBAN, fontweight="bold")
    ax3.text(i,     s + 0.8, f"{s:.0f}%", ha="center", fontsize=8,
             color=C_SUB,   fontweight="bold")
    ax3.text(i + w, r + 0.8, f"{r:.0f}%", ha="center", fontsize=8,
             color=C_RURAL, fontweight="bold")

ax3.set_xticks(x)
ax3.set_xticklabels([f"K={k}" for k in K_vals], fontsize=11)
ax3.set_xlabel("Number of Secondary Ambulance Stations", fontsize=12)
ax3.set_ylabel("Population Served Within NFPA Threshold (%)", fontsize=12)
ax3.set_title("NFPA 1720 Zone Compliance\nvs Number of Stations",
              fontsize=13, fontweight="bold", pad=10)
ax3.set_ylim(0, 110)
ax3.legend(fontsize=8.5, frameon=False, loc="lower right")
ax3.grid(axis="y", alpha=0.2, color="#ccc", zorder=0)
ax3.text(0.03, 0.97,
         "NFPA 1720 standards (secondary response):\n"
         "Urban ≥1,000/sqmi: 9 min, 90% of calls\n"
         "Suburban 500–999/sqmi: 10 min, 80% of calls\n"
         "Rural <500/sqmi: 14 min, 80% of calls\n"
         "--- lines = compliance targets",
         transform=ax3.transAxes, fontsize=8, color="#555", va="top",
         bbox=dict(boxstyle="round,pad=0.4", facecolor="#f9f9f9",
                   edgecolor="#ddd", alpha=0.92))
_spine(ax3)

fig.suptitle(
    "Jefferson County EMS — Secondary Ambulance Network Sensitivity Analysis\n"
    "P-Median on total call volume (8,396 calls, Jefferson County only, CY2024)",
    fontsize=13, fontweight="bold", y=1.01
)
plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_sensitivity_charts.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")
