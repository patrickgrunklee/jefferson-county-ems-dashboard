"""
Shows the true county-wide RT impact of secondary consolidation.
Primary call RTs stay fixed; secondary calls (10-20% per dept) get
the county network RT substituted in. Shows how little the aggregate
median and P90 move — and where the P90 does shift.

Output: secondary_aggregate_impact.png
"""
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from math import radians, sin, cos, sqrt, atan2
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from pareto_facility import load_candidates, load_bg_demand, fetch_cand_bg_matrix, solve_pmedian_pop
from secondary_network_model import allocate_total_demand_to_bgs
from facility_location import STATIONS as EXISTING_STATIONS
import ems_dashboard_app as m

def haversine(la1, lo1, la2, lo2):
    R = 3958.8
    la1,lo1,la2,lo2 = map(radians,[la1,lo1,la2,lo2])
    a = sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 2*R*atan2(sqrt(a),sqrt(1-a))

# ── Load data ──────────────────────────────────────────────────────────────
print("Loading data...")
candidates   = load_candidates()
bg_demand, pop_w = load_bg_demand()
tm           = fetch_cand_bg_matrix(candidates, bg_demand)
demand_w     = allocate_total_demand_to_bgs(bg_demand, pop_w)

rt_data     = m.rt_clean
detail      = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_detail_jeffco.csv"))
sec_df      = detail[detail["Concurrent_Count"] >= 1]
dept_coords = {s["name"]: (s["lat"], s["lon"]) for s in EXISTING_STATIONS}

# Build per-dept arrays
dept_stats = {}
for dept in m.AUTH_EMS_CALLS:
    drt  = rt_data[rt_data["Department"] == dept]["RT"].dropna().values
    dsec = sec_df[sec_df["Dept"] == dept]["Response_Min"].dropna().values
    if len(drt) == 0: continue
    dept_stats[dept] = {
        "primary_rts": drt,
        "sec_rts":     dsec,
        "sec_n":       len(dsec),
        "coords":      dept_coords.get(dept),
    }

def build_county_array(county_rt_map):
    """Primary RTs unchanged + secondary calls replaced with county network RT."""
    arr = []
    for dept, s in dept_stats.items():
        arr.extend(s["primary_rts"].tolist())
        c_rt = county_rt_map.get(dept)
        if c_rt is not None and s["sec_n"] > 0:
            arr.extend([c_rt] * s["sec_n"])
        else:
            arr.extend(s["sec_rts"].tolist())
    return np.array(arr)

# Baseline
base_arr = build_county_array({})
n_total  = len(base_arr)
n_sec    = sum(s["sec_n"] for s in dept_stats.values())
print(f"Total calls: {n_total:,}  |  Secondary: {n_sec} ({100*n_sec/n_total:.1f}%)")
print(f"Baseline: median={np.median(base_arr):.2f}  P90={np.percentile(base_arr,90):.2f}")

# Solve K=3,4,5 and build county arrays
SCENARIOS = {"Baseline (current)": base_arr}
for k in [3, 4, 5]:
    print(f"  K={k}...", end=" ", flush=True)
    res = solve_pmedian_pop(tm, candidates, bg_demand, k, demand_w)
    if res is None: print("FAILED"); continue
    open_ids = [i for i, c in enumerate(candidates)
                if any(abs(c["lat"]-s["lat"])<1e-4 and abs(c["lon"]-s["lon"])<1e-4
                       for s in res["open_stations"])]
    county_rt_map = {}
    for dept, s in dept_stats.items():
        if s["coords"] and s["sec_n"] > 0:
            lat, lon = s["coords"]
            bj = min(range(len(bg_demand)),
                     key=lambda j: haversine(lat,lon,bg_demand[j]["lat"],bg_demand[j]["lon"]))
            county_rt_map[dept] = min(tm[i, bj] for i in open_ids)
    arr = build_county_array(county_rt_map)
    SCENARIOS[f"County K={k}"] = arr
    print(f"median={np.median(arr):.2f}  P90={np.percentile(arr,90):.2f}")

# ── Compute percentile profiles ────────────────────────────────────────────
PCTS = [50, 75, 90, 95, 96, 97, 98, 99]
pct_data = {}
for label, arr in SCENARIOS.items():
    pct_data[label] = [float(np.percentile(arr, p)) for p in PCTS]

# ── Plot: percentile profile chart ────────────────────────────────────────
COLORS = {
    "Baseline (current)": "#2c3e50",
    "County K=3":         "#e67e22",
    "County K=4":         "#27ae60",
    "County K=5":         "#8e44ad",
}
STYLES = {
    "Baseline (current)": "-",
    "County K=3":         "--",
    "County K=4":         "--",
    "County K=5":         "-.",
}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
fig.patch.set_facecolor("white")

def _spine(ax):
    for sp in ("top","right"): ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=10)

# ── Panel 1: Full percentile profile ──────────────────────────────────────
for label, vals in pct_data.items():
    ax1.plot(PCTS, vals, STYLES[label], color=COLORS[label],
             linewidth=2.5 if label == "Baseline (current)" else 2.0,
             markersize=7, marker="o", label=label, zorder=3,
             alpha=1.0 if label in ("Baseline (current)", "County K=5") else 0.7)

ax1.axvspan(95, 100, color="#e74c3c", alpha=0.06)
ax1.text(95.2, ax1.get_ylim()[1] if ax1.get_ylim()[1] > 0 else 30,
         "Secondary calls\nlive here\n(P95-P99)",
         fontsize=8.5, color="#e74c3c", va="top")

ax1.set_xlabel("Percentile", fontsize=12)
ax1.set_ylabel("Response Time (minutes)", fontsize=12)
ax1.set_title("Full County RT Percentile Profile\nBaseline vs County Network",
              fontsize=12, fontweight="bold", pad=10)
ax1.legend(fontsize=9.5, frameon=False)
ax1.grid(alpha=0.2, color="#ccc")
_spine(ax1)

# ── Panel 2: Delta from baseline at each percentile ────────────────────────
base_vals = pct_data["Baseline (current)"]
for label, vals in pct_data.items():
    if label == "Baseline (current)": continue
    deltas = [v - b for v, b in zip(vals, base_vals)]
    ax2.plot(PCTS, deltas, STYLES[label], color=COLORS[label],
             linewidth=2.2, markersize=8, marker="o", label=label,
             alpha=1.0 if label == "County K=5" else 0.75)
    # Annotate last point
    ax2.text(PCTS[-1] + 0.3, deltas[-1], f"{deltas[-1]:+.1f}",
             fontsize=9, color=COLORS[label], fontweight="bold", va="center")

ax2.axhline(0, color="#333", linewidth=1.2, alpha=0.4)
ax2.fill_between([49, 101], 0, 5,  color="#e74c3c", alpha=0.04)
ax2.fill_between([49, 101], -5, 0, color="#27ae60", alpha=0.04)
ax2.text(50.3, 4.5,  "Worse than baseline", fontsize=8.5, color="#e74c3c", alpha=0.7)
ax2.text(50.3, -4.5, "Better than baseline", fontsize=8.5, color="#27ae60", alpha=0.7)

ax2.set_xlabel("Percentile", fontsize=12)
ax2.set_ylabel("Change in RT vs Baseline (minutes)", fontsize=12)
ax2.set_title("RT Change vs Baseline by Percentile\n(+ = slower, - = faster)",
              fontsize=12, fontweight="bold", pad=10)
ax2.legend(fontsize=9.5, frameon=False, loc="lower left")
ax2.grid(alpha=0.2, color="#ccc")
_spine(ax2)

fig.suptitle(
    "Jefferson County EMS — County-Wide RT Distribution: Before vs After Secondary Consolidation\n"
    "Primary calls (96%) unchanged  |  Secondary overflow (4%) get county network RT  |  CY2024",
    fontsize=13, fontweight="bold", y=1.01
)
fig.text(0.5, 0.01,
         f"n={n_total:,} total calls  |  {n_sec} secondary overflow calls ({100*n_sec/n_total:.1f}%)  |  "
         "P50-P90 unchanged across all scenarios — secondary calls too small to shift these percentiles  |  "
         "K=5 keeps P95-P99 at baseline; K=3/K=4 degrade tail due to Waterloo (+18 min without nearby station)",
         ha="center", fontsize=8, color="#777", style="italic")

plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_aggregate_impact.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")
