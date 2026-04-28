"""
Remake of secondary_aggregate_impact.py with K=3,4,5,6 and clearer visuals.

Shows where baseline and scenarios diverge — the P50-P90 region is unchanged
(too few secondary calls to move it), while the tail (P95-P99) deviates.

Layout:
  Panel 1: Full percentile profile P50-P99 (wide view, shows "they're identical until the tail")
  Panel 2: Zoomed tail P90-P99 (where the action is — scenarios separate here)
  Panel 3: Delta from baseline (signed change at each percentile)

Output: secondary_aggregate_impact_v2.png
"""
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from math import radians, sin, cos, sqrt, atan2
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from pareto_facility import load_candidates, load_bg_demand, fetch_cand_bg_matrix, solve_pmedian_pop
from secondary_network_model import allocate_total_demand_to_bgs
from facility_location import STATIONS as EXISTING_STATIONS
import ems_dashboard_app as m

K_RANGE = [3, 4, 5, 6]

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
    arr = []
    for dept, s in dept_stats.items():
        arr.extend(s["primary_rts"].tolist())
        c_rt = county_rt_map.get(dept)
        if c_rt is not None and s["sec_n"] > 0:
            arr.extend([c_rt] * s["sec_n"])
        else:
            arr.extend(s["sec_rts"].tolist())
    return np.array(arr)

base_arr = build_county_array({})
n_total  = len(base_arr)
n_sec    = sum(s["sec_n"] for s in dept_stats.values())
print(f"Total calls: {n_total:,}  |  Secondary: {n_sec} ({100*n_sec/n_total:.1f}%)")
print(f"Baseline: median={np.median(base_arr):.2f}  P90={np.percentile(base_arr,90):.2f}")

SCENARIOS = {"Baseline (current)": base_arr}
for k in K_RANGE:
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
    print(f"median={np.median(arr):.2f}  P90={np.percentile(arr,90):.2f}  P99={np.percentile(arr,99):.2f}")

# ── Percentile profiles ────────────────────────────────────────────────────
PCTS_FULL = [50, 60, 70, 75, 80, 85, 90, 92, 94, 95, 96, 97, 98, 99]
PCTS_TAIL = [90, 91, 92, 93, 94, 95, 96, 97, 98, 99]
pct_full  = {lbl: [float(np.percentile(arr, p)) for p in PCTS_FULL] for lbl, arr in SCENARIOS.items()}
pct_tail  = {lbl: [float(np.percentile(arr, p)) for p in PCTS_TAIL] for lbl, arr in SCENARIOS.items()}

# ── Styling: distinct colors + differentiated line styles ────────────────
STYLE = {
    "Baseline (current)": dict(color="#111111", linestyle="-",  linewidth=3.2, marker="o", markersize=8,  alpha=1.0, zorder=6),
    "County K=3":         dict(color="#e74c3c", linestyle="--", linewidth=2.3, marker="s", markersize=7,  alpha=0.92, zorder=5),
    "County K=4":         dict(color="#f39c12", linestyle=":",  linewidth=2.6, marker="D", markersize=7,  alpha=0.92, zorder=4),
    "County K=5":         dict(color="#27ae60", linestyle="-.", linewidth=2.3, marker="^", markersize=7,  alpha=0.92, zorder=3),
    "County K=6":         dict(color="#2980b9", linestyle=(0,(5,1,1,1,1,1)), linewidth=2.3, marker="v", markersize=7,  alpha=0.92, zorder=2),
}

fig = plt.figure(figsize=(18, 7.2))
fig.patch.set_facecolor("white")
gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.0, 1.0], wspace=0.28)
ax1 = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1])
ax3 = fig.add_subplot(gs[2])

def _spine(ax):
    for sp in ("top","right"): ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=10)

# ── Panel 1: Full profile ────────────────────────────────────────────────
for lbl, vals in pct_full.items():
    ax1.plot(PCTS_FULL, vals, label=lbl, **STYLE[lbl])

ax1.axvspan(90, 100, color="#e74c3c", alpha=0.05, zorder=0)
ax1.text(90.3, ax1.get_ylim()[1] * 0.02 + min(min(v) for v in pct_full.values()),
         "Tail region\n(zoomed →)", fontsize=9, color="#e74c3c", alpha=0.8, va="bottom")

ax1.set_xlabel("Percentile", fontsize=11)
ax1.set_ylabel("Response Time (minutes)", fontsize=11)
ax1.set_title("Full County RT Percentile Profile\n(P50 - P99)",
              fontsize=12, fontweight="bold", pad=10)
ax1.legend(fontsize=9.5, frameon=False, loc="upper left")
ax1.grid(alpha=0.2, color="#ccc")
_spine(ax1)

# ── Panel 2: Zoomed tail ─────────────────────────────────────────────────
for lbl, vals in pct_tail.items():
    ax2.plot(PCTS_TAIL, vals, label=lbl, **STYLE[lbl])
    # Label at P99 end
    ax2.text(99.25, vals[-1], f"{vals[-1]:.1f}", fontsize=9,
             color=STYLE[lbl]["color"], fontweight="bold", va="center")

ax2.set_xlabel("Percentile", fontsize=11)
ax2.set_ylabel("Response Time (minutes)", fontsize=11)
ax2.set_title("Zoomed Tail (P90 - P99)\nWhere scenarios diverge",
              fontsize=12, fontweight="bold", pad=10)
ax2.set_xlim(89.5, 100.5)
ax2.grid(alpha=0.2, color="#ccc")
_spine(ax2)

# ── Panel 3: Delta from baseline ─────────────────────────────────────────
base_vals = pct_full["Baseline (current)"]
for lbl, vals in pct_full.items():
    if lbl == "Baseline (current)": continue
    deltas = [v - b for v, b in zip(vals, base_vals)]
    style  = dict(STYLE[lbl]); style["linewidth"] = style.get("linewidth", 2.0) + 0.2
    ax3.plot(PCTS_FULL, deltas, label=lbl, **style)
    ax3.text(99.4, deltas[-1], f"{deltas[-1]:+.1f}",
             fontsize=9.5, color=STYLE[lbl]["color"], fontweight="bold", va="center")

ax3.axhline(0, color="#333", linewidth=1.2, alpha=0.5, zorder=1)
ax3.fill_between([49, 101], 0, 5,  color="#e74c3c", alpha=0.05, zorder=0)
ax3.fill_between([49, 101], -5, 0, color="#27ae60", alpha=0.05, zorder=0)
ax3.text(50.3, 4.6,  "Worse than baseline (slower)", fontsize=8.5, color="#e74c3c", alpha=0.75)
ax3.text(50.3, -4.7, "Better than baseline (faster)", fontsize=8.5, color="#27ae60", alpha=0.75)

ax3.set_xlabel("Percentile", fontsize=11)
ax3.set_ylabel("Change vs Baseline (minutes)", fontsize=11)
ax3.set_title("Delta from Baseline\n(+ = slower, - = faster)",
              fontsize=12, fontweight="bold", pad=10)
ax3.legend(fontsize=9.5, frameon=False, loc="upper left")
ax3.grid(alpha=0.2, color="#ccc")
ax3.set_xlim(49, 102)
_spine(ax3)

fig.suptitle(
    "Jefferson County EMS — County-Wide RT Distribution: Baseline vs Consolidation Scenarios K=3-6\n"
    "Primary calls (96%) unchanged  |  Secondary overflow (4%) re-routed through county network  |  CY2024",
    fontsize=13, fontweight="bold", y=1.02
)

fig.text(0.5, -0.01,
         f"n={n_total:,} total calls  |  {n_sec} secondary overflow calls ({100*n_sec/n_total:.1f}%)  |  "
         "P50-P90 identical across all scenarios (secondary subset too small to shift)  |  "
         "K=5/K=6 hold the tail at baseline; K=3/K=4 degrade P99 ~+3 min (Waterloo gap)",
         ha="center", fontsize=8.5, color="#777", style="italic")

plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_aggregate_impact_v2.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")

# ── Export percentile data (panels 1 & 2) to CSV ─────────────────────────
df_full = pd.DataFrame(pct_full, index=PCTS_FULL).round(2)
df_full.index.name = "Percentile"
df_full.insert(0, "Panel", "Full (P50-P99)")

df_tail = pd.DataFrame(pct_tail, index=PCTS_TAIL).round(2)
df_tail.index.name = "Percentile"
df_tail.insert(0, "Panel", "Tail zoom (P90-P99)")

out_csv = os.path.join(SCRIPT_DIR, "secondary_aggregate_impact_v2.csv")
pd.concat([df_full, df_tail]).to_csv(out_csv)
print(f"Saved: {out_csv}")
