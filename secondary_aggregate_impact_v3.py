"""
v3: Broader secondary definition — ANY non-primary unit run (2nd/3rd/4th vehicle),
not just concurrent-overlap dispatches. Matches the 13.13% / 1,102 calls used
on the utilization dashboard.

Assumption: each muni keeps its primary vehicle, gives up secondary/backup units.
Those 1,102 calls get re-routed through the county network.

Source: muni_utilization_export.csv provides Primary_Calls / Secondary_Calls per dept.
Per-call RTs sampled from observed primary/secondary distributions where available;
imputed depts use their own primary RT distribution as proxy for secondary.

Output: secondary_aggregate_impact_v3.png, secondary_aggregate_impact_v3.csv
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
RNG     = np.random.default_rng(42)

def haversine(la1, lo1, la2, lo2):
    R = 3958.8
    la1,lo1,la2,lo2 = map(radians,[la1,lo1,la2,lo2])
    a = sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 2*R*atan2(sqrt(a),sqrt(1-a))

# ── Load utilization breakdown (authoritative Primary/Secondary split) ───
print("Loading data...")
util = pd.read_csv(os.path.join(SCRIPT_DIR, "muni_utilization_export.csv"))
util = util[util["Department"] != "COUNTY TOTAL"].copy()
util["Primary_Calls"]   = util["Primary_Calls"].astype(int)
util["Secondary_Calls"] = util["Secondary_Calls"].astype(int)

# ── Load concurrent detail for dept secondary RT distributions ──────────
detail = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_detail_jeffco.csv"))
sec_detail = detail[detail["Concurrent_Count"] >= 1]

# Per-dept observed primary & secondary RT distributions from rt_clean
rt_data = m.rt_clean
dept_coords = {s["name"]: (s["lat"], s["lon"]) for s in EXISTING_STATIONS}

dept_stats = {}
for _, row in util.iterrows():
    dept = row["Department"]
    n_primary_auth   = int(row["Primary_Calls"])
    n_secondary_auth = int(row["Secondary_Calls"])

    dept_rt_all = rt_data[rt_data["Department"] == dept]["RT"].dropna().values
    dept_rt_sec = sec_detail[sec_detail["Dept"] == dept]["Response_Min"].dropna().values

    if len(dept_rt_all) == 0:
        # No RT data at all — use county fallback (median 5, P90 11, P99 22)
        # Build synthetic from overall county distribution
        dept_rt_all = rt_data["RT"].dropna().values

    dept_stats[dept] = {
        "n_primary":   n_primary_auth,
        "n_secondary": n_secondary_auth,
        "pri_rt_pool": dept_rt_all,             # sample primary RTs from here
        "sec_rt_pool": dept_rt_sec if len(dept_rt_sec) >= 3 else dept_rt_all,
        "coords":      dept_coords.get(dept),
    }

def build_county_array(county_rt_map):
    """
    Primary calls: sampled from dept's primary RT pool (unchanged across scenarios).
    Secondary calls: replaced with county network RT if provided, else sampled
    from observed secondary RT distribution.
    """
    arr = []
    for dept, s in dept_stats.items():
        # Primary: sample n_primary RTs from pri_rt_pool
        if s["n_primary"] > 0:
            pri_sample = RNG.choice(s["pri_rt_pool"], size=s["n_primary"], replace=True)
            arr.extend(pri_sample.tolist())
        # Secondary: either county network RT or observed secondary sample
        if s["n_secondary"] > 0:
            c_rt = county_rt_map.get(dept)
            if c_rt is not None:
                arr.extend([c_rt] * s["n_secondary"])
            else:
                sec_sample = RNG.choice(s["sec_rt_pool"], size=s["n_secondary"], replace=True)
                arr.extend(sec_sample.tolist())
    return np.array(arr)

# Need demand weights & candidates for P-Median solve
candidates   = load_candidates()
bg_demand, pop_w = load_bg_demand()
tm           = fetch_cand_bg_matrix(candidates, bg_demand)
demand_w     = allocate_total_demand_to_bgs(bg_demand, pop_w)

# Baseline
base_arr = build_county_array({})
n_total  = len(base_arr)
n_sec    = sum(s["n_secondary"] for s in dept_stats.values())
print(f"Total calls: {n_total:,}  |  Secondary (broader defn): {n_sec} ({100*n_sec/n_total:.1f}%)")
print(f"Baseline: median={np.median(base_arr):.2f}  P90={np.percentile(base_arr,90):.2f}  P99={np.percentile(base_arr,99):.2f}")

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
        if s["coords"] and s["n_secondary"] > 0:
            lat, lon = s["coords"]
            bj = min(range(len(bg_demand)),
                     key=lambda j: haversine(lat,lon,bg_demand[j]["lat"],bg_demand[j]["lon"]))
            county_rt_map[dept] = min(tm[i, bj] for i in open_ids)
    arr = build_county_array(county_rt_map)
    SCENARIOS[f"County K={k}"] = arr
    print(f"median={np.median(arr):.2f}  P90={np.percentile(arr,90):.2f}  P99={np.percentile(arr,99):.2f}")

# ── Percentile profiles ────────────────────────────────────────────────
PCTS_FULL = [50, 60, 70, 75, 80, 85, 90, 92, 94, 95, 96, 97, 98, 99]
PCTS_TAIL = [90, 91, 92, 93, 94, 95, 96, 97, 98, 99]
pct_full  = {lbl: [float(np.percentile(arr, p)) for p in PCTS_FULL] for lbl, arr in SCENARIOS.items()}
pct_tail  = {lbl: [float(np.percentile(arr, p)) for p in PCTS_TAIL] for lbl, arr in SCENARIOS.items()}

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

for lbl, vals in pct_full.items():
    ax1.plot(PCTS_FULL, vals, label=lbl, **STYLE[lbl])
ax1.axvspan(90, 100, color="#e74c3c", alpha=0.05, zorder=0)
ax1.set_xlabel("Percentile", fontsize=11)
ax1.set_ylabel("Response Time (minutes)", fontsize=11)
ax1.set_title("Full County RT Percentile Profile\n(P50 - P99)", fontsize=12, fontweight="bold", pad=10)
ax1.legend(fontsize=9.5, frameon=False, loc="upper left")
ax1.grid(alpha=0.2, color="#ccc")
_spine(ax1)

for lbl, vals in pct_tail.items():
    ax2.plot(PCTS_TAIL, vals, label=lbl, **STYLE[lbl])
    ax2.text(99.25, vals[-1], f"{vals[-1]:.1f}", fontsize=9, color=STYLE[lbl]["color"], fontweight="bold", va="center")
ax2.set_xlabel("Percentile", fontsize=11)
ax2.set_ylabel("Response Time (minutes)", fontsize=11)
ax2.set_title("Zoomed Tail (P90 - P99)\nWhere scenarios diverge", fontsize=12, fontweight="bold", pad=10)
ax2.set_xlim(89.5, 100.5)
ax2.grid(alpha=0.2, color="#ccc")
_spine(ax2)

base_vals = pct_full["Baseline (current)"]
for lbl, vals in pct_full.items():
    if lbl == "Baseline (current)": continue
    deltas = [v - b for v, b in zip(vals, base_vals)]
    style  = dict(STYLE[lbl]); style["linewidth"] = style.get("linewidth", 2.0) + 0.2
    ax3.plot(PCTS_FULL, deltas, label=lbl, **style)
    ax3.text(99.4, deltas[-1], f"{deltas[-1]:+.1f}", fontsize=9.5, color=STYLE[lbl]["color"], fontweight="bold", va="center")
ax3.axhline(0, color="#333", linewidth=1.2, alpha=0.5, zorder=1)
ax3.fill_between([49, 101], 0, 8,  color="#e74c3c", alpha=0.05, zorder=0)
ax3.fill_between([49, 101], -8, 0, color="#27ae60", alpha=0.05, zorder=0)
ax3.text(50.3, 7.3,  "Worse than baseline (slower)", fontsize=8.5, color="#e74c3c", alpha=0.75)
ax3.text(50.3, -7.5, "Better than baseline (faster)", fontsize=8.5, color="#27ae60", alpha=0.75)
ax3.set_xlabel("Percentile", fontsize=11)
ax3.set_ylabel("Change vs Baseline (minutes)", fontsize=11)
ax3.set_title("Delta from Baseline\n(+ = slower, - = faster)", fontsize=12, fontweight="bold", pad=10)
ax3.legend(fontsize=9.5, frameon=False, loc="upper left")
ax3.grid(alpha=0.2, color="#ccc")
ax3.set_xlim(49, 102)
_spine(ax3)

fig.suptitle(
    "Jefferson County EMS — County-Wide RT: Baseline vs Consolidation Scenarios K=3-6\n"
    "Primary unit stays local (86.9%)  |  Secondary unit (13.1%, 1,102 calls) re-routed through county network  |  CY2024",
    fontsize=13, fontweight="bold", y=1.02
)
fig.text(0.5, -0.01,
         f"n={n_total:,} total calls  |  {n_sec:,} secondary calls ({100*n_sec/n_total:.1f}%) = 2nd/3rd/4th vehicle runs  |  "
         "Source: muni_utilization_export.csv + concurrent_call_detail_jeffco.csv  |  "
         "Primary RTs sampled from observed dept distribution (unchanged across scenarios); secondary RTs replaced with P-Median county network travel time",
         ha="center", fontsize=8.5, color="#777", style="italic")

plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_aggregate_impact_v3.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")

# CSV export
df_full = pd.DataFrame(pct_full, index=PCTS_FULL).round(2)
df_full.index.name = "Percentile"
df_full.insert(0, "Panel", "Full (P50-P99)")
df_tail = pd.DataFrame(pct_tail, index=PCTS_TAIL).round(2)
df_tail.index.name = "Percentile"
df_tail.insert(0, "Panel", "Tail zoom (P90-P99)")
out_csv = os.path.join(SCRIPT_DIR, "secondary_aggregate_impact_v3.csv")
pd.concat([df_full, df_tail]).to_csv(out_csv)
print(f"Saved: {out_csv}")
