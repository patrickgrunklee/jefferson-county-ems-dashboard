"""
Sensitivity chart: median and P90 response time vs K=2-6.
Two views:
  - Secondary calls only (left axis) — shows the range of improvement
  - All-calls weighted (callout box) — shows the aggregate impact is small

Output: secondary_sensitivity_single.png
"""
import os, sys, json
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

def haversine(la1, lo1, la2, lo2):
    R = 3958.8
    la1,lo1,la2,lo2 = map(radians,[la1,lo1,la2,lo2])
    a = sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 2*R*atan2(sqrt(a),sqrt(1-a))

K_RANGE = [2, 3, 4, 5, 6]

# ── Load base data ─────────────────────────────────────────────────────────
print("Loading data...")
candidates       = load_candidates()
bg_demand, pop_w = load_bg_demand()
tm               = fetch_cand_bg_matrix(candidates, bg_demand)
demand_w         = allocate_total_demand_to_bgs(bg_demand, pop_w)

rt_data     = m.rt_clean
auth        = m.AUTH_EMS_CALLS
detail      = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_detail_jeffco.csv"))
sec_df      = detail[detail["Concurrent_Count"] >= 1]
dept_coords = {s["name"]: (s["lat"], s["lon"]) for s in EXISTING_STATIONS}

# Per-dept RT arrays
# primary_rts = all calls MINUS the concurrent ones (true primary-only distribution)
# secondary_rts = only calls where a 2nd unit was needed (concurrent_count >= 1)
dept_stats = {}
for dept in auth:
    all_drt = rt_data[rt_data["Department"] == dept]["RT"].dropna().values
    dsec    = sec_df[sec_df["Dept"] == dept]["Response_Min"].dropna().values
    if len(all_drt) == 0: continue
    # Primary = all actual RT values; secondary = concurrent-call RT values.
    # For the proposed scenario, we keep ALL primary RTs unchanged and
    # replace each secondary call's RT with the county network drive time.
    dept_stats[dept] = {
        "primary_rts": all_drt,          # full distribution (primary calls dominate)
        "sec_rts":     dsec,             # actual RT when own 2nd unit responded
        "sec_n":       len(dsec),
        "coords":      dept_coords.get(dept),
    }

def build_rt_array(dept_stats, county_rt_map):
    """
    Build the full county call-RT array for a given scenario:
      - Primary calls: unchanged actual NFIRS RT values
      - Secondary calls: replaced with county_rt for that dept
        (or actual own-2nd-unit RT if no county RT available)

    This models: "keep 80-90% of calls the same, substitute new RT
    for the 10-20% overflow calls that would go to the county network."
    """
    all_rts = []
    for dept, s in dept_stats.items():
        # Always include the full primary RT distribution
        all_rts.extend(s["primary_rts"].tolist())
        # For secondary calls: use county RT if available, else actual
        c_rt = county_rt_map.get(dept)
        if c_rt is not None and s["sec_n"] > 0:
            all_rts.extend([c_rt] * s["sec_n"])
        else:
            all_rts.extend(s["sec_rts"].tolist())
    return np.array(all_rts)

# Baseline
base_arr    = build_rt_array(dept_stats, {})
base_median = float(np.median(base_arr))
base_p90    = float(np.percentile(base_arr, 90))
print(f"Baseline: median={base_median:.2f}  P90={base_p90:.2f}  (n={len(base_arr):,} calls)")

# Current secondary-only benchmark
sec_all = sec_df["Response_Min"].dropna()
cur_sec_median = float(sec_all.median())
cur_sec_p90    = float(sec_all.quantile(0.90))
print(f"Current secondary-only: median={cur_sec_median:.1f}  P90={cur_sec_p90:.1f}  (n={len(sec_all)})")

# ── Run P-Median for each K ────────────────────────────────────────────────
print(f"\nRunning P-Median for K={K_RANGE}...")
results = {}
for k in K_RANGE:
    print(f"  K={k}...", end=" ", flush=True)
    res = solve_pmedian_pop(tm, candidates, bg_demand, k, demand_w)
    if res is None:
        print("FAILED"); continue

    open_ids = [i for i, c in enumerate(candidates)
                if any(abs(c["lat"]-s["lat"])<1e-4 and abs(c["lon"]-s["lon"])<1e-4
                       for s in res["open_stations"])]

    # Secondary-only RT distribution (BG-level)
    bg_rts = np.array([min(tm[i,j] for i in open_ids) for j in range(len(bg_demand))], dtype=float)
    w      = demand_w / demand_w.sum()
    sort_i = np.argsort(bg_rts)
    cumw   = np.cumsum(w[sort_i])
    def wpct(p):
        idx = np.searchsorted(cumw, p/100.0)
        return bg_rts[sort_i][min(idx, len(bg_rts)-1)]
    sec_med = wpct(50)
    sec_p90 = wpct(90)

    # All-calls weighted (county RT substituted for secondary)
    county_rt_map = {}
    for dept, s in dept_stats.items():
        if s["coords"] and s["sec_n"] > 0:
            lat, lon = s["coords"]
            best_bj = min(range(len(bg_demand)),
                          key=lambda j: haversine(lat, lon, bg_demand[j]["lat"], bg_demand[j]["lon"]))
            county_rt_map[dept] = min(tm[i, best_bj] for i in open_ids)
    arr     = build_rt_array(dept_stats, county_rt_map)
    wtd_med = float(np.median(arr))
    wtd_p90 = float(np.percentile(arr, 90))

    results[k] = {"sec_med": sec_med, "sec_p90": sec_p90,
                  "wtd_med": wtd_med, "wtd_p90": wtd_p90}
    print(f"sec_median={sec_med:.1f}  sec_P90={sec_p90:.1f}  |  "
          f"all_median={wtd_med:.2f}  all_P90={wtd_p90:.2f}")

K_vals   = [k for k in K_RANGE if k in results]
sec_meds = [results[k]["sec_med"] for k in K_vals]
sec_p90s = [results[k]["sec_p90"] for k in K_vals]
wtd_meds = [results[k]["wtd_med"] for k in K_vals]
wtd_p90s = [results[k]["wtd_p90"] for k in K_vals]

# ── Plot ───────────────────────────────────────────────────────────────────
C_MED  = "#2980b9"
C_P90  = "#8e44ad"
C_WMED = "#27ae60"
C_WP90 = "#e67e22"

fig, ax = plt.subplots(figsize=(12, 7))
fig.patch.set_facecolor("white")
ax2 = ax.twinx()

# Left axis — secondary-only (large range, main story)
ax.plot(K_vals, sec_meds, "o-", color=C_MED, linewidth=2.5, markersize=10,
        label="Secondary calls — Median RT", zorder=3)
ax.plot(K_vals, sec_p90s, "^-", color=C_P90, linewidth=2.5, markersize=10,
        label="Secondary calls — P90 RT", zorder=3)

for k, med, p90 in zip(K_vals, sec_meds, sec_p90s):
    ax.text(k, med - 0.9, f"{med:.1f}", ha="center", fontsize=10,
            color=C_MED, fontweight="bold")
    ax.text(k, p90 + 0.6, f"{p90:.1f}", ha="center", fontsize=10,
            color=C_P90, fontweight="bold")

# Current secondary benchmarks
ax.axhline(cur_sec_median, color=C_MED, linewidth=1.5, linestyle="--", alpha=0.45)
ax.axhline(cur_sec_p90,    color=C_P90, linewidth=1.5, linestyle="--", alpha=0.45)
xlim_r = K_vals[-1] + 0.12
ax.text(xlim_r, cur_sec_median + 0.3,
        f"Current median\n{cur_sec_median:.0f} min", fontsize=8, color=C_MED, alpha=0.8)
ax.text(xlim_r, cur_sec_p90 + 0.3,
        f"Current P90\n{cur_sec_p90:.0f} min", fontsize=8, color=C_P90, alpha=0.8)

# NFPA lines
ax.axhline(9,  color="#e74c3c", linewidth=1.0, linestyle=":", alpha=0.4)
ax.axhline(14, color="#3498db", linewidth=1.0, linestyle=":", alpha=0.4)
ax.text(xlim_r, 9.15,  "Urban 9 min\n(NFPA 1720)", fontsize=7.5, color="#e74c3c", alpha=0.65)
ax.text(xlim_r, 14.15, "Rural 14 min\n(NFPA 1720)", fontsize=7.5, color="#3498db", alpha=0.65)

ax.set_ylabel("Response Time — Secondary Calls Only (minutes)", fontsize=11, color="#333")
ax.set_ylim(3, 30)

# Right axis — all-calls weighted (small range, context)
ax2.plot(K_vals, wtd_meds, "s--", color=C_WMED, linewidth=2.0, markersize=8,
         label="All calls weighted — Median RT", zorder=3, alpha=0.9)
ax2.plot(K_vals, wtd_p90s, "D--", color=C_WP90, linewidth=2.0, markersize=8,
         label="All calls weighted — P90 RT", zorder=3, alpha=0.9)

ax2.axhline(base_median, color=C_WMED, linewidth=1.2, linestyle=":", alpha=0.4)
ax2.axhline(base_p90,    color=C_WP90, linewidth=1.2, linestyle=":", alpha=0.4)

for k, wm, wp in zip(K_vals, wtd_meds, wtd_p90s):
    ax2.text(k, wm + 0.07, f"{wm:.1f}", ha="center", fontsize=9,
             color=C_WMED, fontweight="bold")
    ax2.text(k, wp - 0.25, f"{wp:.1f}", ha="center", fontsize=9,
             color=C_WP90, fontweight="bold")

ax2.text(xlim_r, base_median - 0.1,
         f"Current\n{base_median:.1f} min", fontsize=7.5, color=C_WMED, alpha=0.75)
ax2.text(xlim_r, base_p90 + 0.1,
         f"Current\n{base_p90:.1f} min", fontsize=7.5, color=C_WP90, alpha=0.75)

ax2.set_ylabel("Response Time — All Calls Weighted (minutes)", fontsize=11, color="#555")
ax2.set_ylim(3, 14)
ax2.tick_params(axis="y", labelsize=10)
ax2.spines["right"].set_color("#ccc")

# Combined legend
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2,
          fontsize=9.5, frameon=False, loc="upper right")

ax.set_xticks(K_vals)
ax.set_xlabel("Number of Secondary Ambulance Stations", fontsize=12)
ax.set_title(
    "Jefferson County EMS — Secondary Network Sensitivity\n"
    "Secondary-only RT (left axis)  vs  All-calls weighted RT (right axis)  |  CY2024",
    fontsize=13, fontweight="bold", pad=12
)
ax.set_xlim(K_vals[0] - 0.3, K_vals[-1] + 1.1)
ax.grid(axis="y", alpha=0.15, color="#ccc")
for sp in ("top",): ax.spines[sp].set_visible(False)
ax2.spines["top"].set_visible(False)
ax.spines["left"].set_color("#ccc")
ax.spines["bottom"].set_color("#ccc")
ax.tick_params(colors="#555", labelsize=11)

fig.text(0.5, 0.005,
         "Left axis: secondary overflow calls only (571/yr, 4% of total)  |  "
         "Right axis: all 14,317 calls weighted — small change because primary calls dominate  |  "
         "Current dashed = dept own co-located 2nd unit",
         ha="center", fontsize=8, color="#999", style="italic")

plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_sensitivity_single.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")
