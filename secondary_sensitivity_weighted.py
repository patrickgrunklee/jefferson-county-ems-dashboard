"""
Sensitivity chart using call-volume weighted RT per dept (primary + secondary combined).
Shows true county-wide weighted median and P90 vs K=2-6, with current baseline marked.

Weighted RT = (primary_calls * primary_median_RT + secondary_calls * county_RT) / total_calls
Aggregated county-wide by call volume share.

Output: secondary_sensitivity_weighted.png
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

K_RANGE = [2, 3, 4, 5, 6]

# ── Load base data ─────────────────────────────────────────────────────────
print("Loading data...")
candidates       = load_candidates()
bg_demand, pop_w = load_bg_demand()
tm               = fetch_cand_bg_matrix(candidates, bg_demand)
demand_w         = allocate_total_demand_to_bgs(bg_demand, pop_w)

rt     = m.rt_clean
auth   = m.AUTH_EMS_CALLS
detail = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_detail_jeffco.csv"))
sec_df = detail[detail["Concurrent_Count"] >= 1]

# Per-dept primary RT distribution and secondary call counts
dept_coords = {s["name"]: (s["lat"], s["lon"]) for s in EXISTING_STATIONS}

def haversine(la1, lo1, la2, lo2):
    R = 3958.8
    la1,lo1,la2,lo2 = map(radians,[la1,lo1,la2,lo2])
    a = sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 2*R*atan2(sqrt(a),sqrt(1-a))

# Build per-dept RT arrays (all primary calls with RT data)
dept_stats = {}
for dept in auth:
    dept_rt  = rt[rt["Department"] == dept]["RT"].dropna().values
    dept_sec = sec_df[sec_df["Dept"] == dept]["Response_Min"].dropna().values
    if len(dept_rt) == 0:
        continue
    dept_stats[dept] = {
        "pri_rts":  dept_rt,
        "sec_rts":  dept_sec,
        "pri_n":    len(dept_rt) - len(dept_sec),
        "sec_n":    len(dept_sec),
        "total":    len(dept_rt),
        "coords":   dept_coords.get(dept),
    }

# ── For each K, compute county-wide weighted median and P90 ───────────────
print(f"\nRunning P-Median for K={K_RANGE}...")

def county_rt_to_dept(open_ids, dept_lat, dept_lon):
    """ORS drive time from nearest open station to dept centroid."""
    best_bj = min(range(len(bg_demand)),
                  key=lambda j: haversine(dept_lat, dept_lon,
                                          bg_demand[j]["lat"], bg_demand[j]["lon"]))
    return min(tm[i, best_bj] for i in open_ids)

# Baseline: use actual secondary RT from own 2nd unit
def build_call_rt_array(dept_stats, county_rt_map):
    """
    For each dept, build a synthetic array of per-call RTs:
      - primary calls: sampled from actual primary RT distribution
      - secondary calls: county_rt for that dept (or actual if no county map)
    Returns flat array of all call RTs weighted by volume.
    """
    all_rts = []
    for dept, stats in dept_stats.items():
        # Primary: use actual RT values
        pri_rts = stats["pri_rts"]
        all_rts.extend(pri_rts.tolist())
        # Secondary: use county RT if available, else actual
        c_rt = county_rt_map.get(dept)
        if c_rt is not None and stats["sec_n"] > 0:
            all_rts.extend([c_rt] * stats["sec_n"])
        elif stats["sec_n"] > 0:
            all_rts.extend(stats["sec_rts"].tolist())
    return np.array(all_rts)

# Baseline (own 2nd unit — use actual secondary RT)
baseline_rts = build_call_rt_array(dept_stats, county_rt_map={})
base_median  = float(np.median(baseline_rts))
base_p90     = float(np.percentile(baseline_rts, 90))
print(f"  Baseline: median={base_median:.1f}  P90={base_p90:.1f}  (n={len(baseline_rts):,} calls)")

results = {}
for k in K_RANGE:
    print(f"  K={k}...", end=" ", flush=True)
    res = solve_pmedian_pop(tm, candidates, bg_demand, k, demand_w)
    if res is None:
        print("FAILED"); continue

    open_ids = [i for i, c in enumerate(candidates)
                if any(abs(c["lat"]-s["lat"]) < 1e-4 and abs(c["lon"]-s["lon"]) < 1e-4
                       for s in res["open_stations"])]

    # County RT to each dept centroid
    county_rt_map = {}
    for dept, stats in dept_stats.items():
        if stats["coords"] and stats["sec_n"] > 0:
            lat, lon = stats["coords"]
            county_rt_map[dept] = county_rt_to_dept(open_ids, lat, lon)

    # Build full call RT array with county network serving secondary calls
    proposed_rts = build_call_rt_array(dept_stats, county_rt_map)
    med = float(np.median(proposed_rts))
    p90 = float(np.percentile(proposed_rts, 90))

    results[k] = {"median": med, "p90": p90}
    print(f"median={med:.1f}  P90={p90:.1f}")

K_vals  = [k for k in K_RANGE if k in results]
medians = [results[k]["median"] for k in K_vals]
p90s    = [results[k]["p90"]    for k in K_vals]

# ── Plot ───────────────────────────────────────────────────────────────────
C_MED = "#2980b9"
C_P90 = "#8e44ad"

fig, ax = plt.subplots(figsize=(10, 6))
fig.patch.set_facecolor("white")

ax.plot(K_vals, medians, "o-", color=C_MED, linewidth=2.5, markersize=10,
        label="Median RT (proposed)", zorder=3)
ax.plot(K_vals, p90s,    "^-", color=C_P90, linewidth=2.5, markersize=10,
        label="P90 RT (proposed)", zorder=3)

for k, med, p90 in zip(K_vals, medians, p90s):
    ax.text(k, med - 0.15, f"{med:.1f}", ha="center", fontsize=10,
            color=C_MED, fontweight="bold")
    ax.text(k, p90 + 0.12, f"{p90:.1f}", ha="center", fontsize=10,
            color=C_P90, fontweight="bold")

# Current baseline lines
ax.axhline(base_median, color=C_MED, linewidth=1.8, linestyle="--", alpha=0.55, zorder=2)
ax.axhline(base_p90,    color=C_P90, linewidth=1.8, linestyle="--", alpha=0.55, zorder=2)
xlim_r = K_vals[-1] + 0.12
ax.text(xlim_r, base_median + 0.06,
        f"Current median {base_median:.1f} min", fontsize=8.5, color=C_MED, alpha=0.85)
ax.text(xlim_r, base_p90 + 0.06,
        f"Current P90 {base_p90:.1f} min",    fontsize=8.5, color=C_P90, alpha=0.85)

# NFPA reference lines
ax.axhline(9,  color="#e74c3c", linewidth=1.0, linestyle=":", alpha=0.45)
ax.axhline(14, color="#3498db", linewidth=1.0, linestyle=":", alpha=0.45)
ax.text(xlim_r, 9.06,  "Urban 9 min (NFPA)",  fontsize=7.5, color="#e74c3c", alpha=0.7)
ax.text(xlim_r, 14.06, "Rural 14 min (NFPA)", fontsize=7.5, color="#3498db", alpha=0.7)

ax.set_xticks(K_vals)
ax.set_xlabel("Number of Secondary Ambulance Stations", fontsize=12)
ax.set_ylabel("County-Wide Weighted Response Time (minutes)", fontsize=12)
ax.set_title(
    "Jefferson County EMS — Secondary Network Sensitivity\n"
    "Call-volume weighted RT (primary + secondary combined)  |  CY2024",
    fontsize=13, fontweight="bold", pad=12
)
ax.legend(fontsize=11, frameon=False, loc="upper right")
ax.set_xlim(K_vals[0] - 0.3, K_vals[-1] + 1.1)
rng = max(max(p90s), base_p90)
ax.set_ylim(max(0, min(medians) - 1), rng + 1.5)
ax.grid(axis="y", alpha=0.2, color="#ccc")
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
ax.spines["left"].set_color("#ccc")
ax.spines["bottom"].set_color("#ccc")
ax.tick_params(colors="#555", labelsize=11)

fig.text(0.5, 0.005,
         "Weighted by actual call volume per dept  |  "
         "Secondary calls = 10-22% of total per dept  |  "
         "Current = dept own 2nd unit  |  Proposed = county P-Median network",
         ha="center", fontsize=8, color="#999", style="italic")

plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_sensitivity_weighted.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")
