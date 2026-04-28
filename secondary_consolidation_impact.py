"""
Models the impact of removing dept-level secondary ambulances and replacing
them with a county-wide K=3 or K=4 secondary network.

For each dept that currently has 2+ ambulances:
  - Current: secondary calls served by dept's own 2nd unit (actual NFIRS RT)
  - Proposed: secondary calls served by nearest county station (ORS drive-time)

Shows per-dept RT change and aggregate county-wide impact.

Output: secondary_consolidation_impact.png
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

from pareto_facility import load_candidates, load_bg_demand, fetch_cand_bg_matrix
from facility_location import STATIONS as EXISTING_STATIONS
import ems_dashboard_app as m

# ── Load data ──────────────────────────────────────────────────────────────
print("Loading data...")
candidates       = load_candidates()
bg_demand, pop_w = load_bg_demand()
tm               = fetch_cand_bg_matrix(candidates, bg_demand)
sol              = pd.read_csv(os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv"))
detail           = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_detail_jeffco.csv"))
auth             = m.AUTH_EMS_CALLS

# ── Helpers ────────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    lat1,lon1,lat2,lon2 = map(radians,[lat1,lon1,lat2,lon2])
    dlat,dlon = lat2-lat1, lon2-lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2*R*atan2(sqrt(a),sqrt(1-a))

def parse_stations(row):
    parts = str(row["Stations"]).split("|")
    result = []
    for p in parts:
        p = p.strip().strip("()")
        lat, lon = p.split(",")
        result.append((float(lat.strip()), float(lon.strip())))
    return result

def nearest_county_rt(dept_lat, dept_lon, county_stations):
    """ORS-based drive time from nearest county station to dept centroid."""
    best_rt = float("inf")
    for slat, slon in county_stations:
        best_ci = min(range(len(candidates)),
                      key=lambda i: haversine(slat, slon, candidates[i]["lat"], candidates[i]["lon"]))
        best_bj = min(range(len(bg_demand)),
                      key=lambda j: haversine(dept_lat, dept_lon, bg_demand[j]["lat"], bg_demand[j]["lon"]))
        rt = tm[best_ci, best_bj]
        if rt < best_rt:
            best_rt = rt
    return best_rt

dept_coords = {s["name"]: (s["lat"], s["lon"]) for s in EXISTING_STATIONS}

# ── Depts with secondary capacity (2+ ambulances) ─────────────────────────
ASSET = m.ASSET_DATA
multi_amb = ASSET[ASSET["Ambulances"] >= 2]["Municipality"].tolist()

# ── Secondary call RT data from concurrent detail ─────────────────────────
sec_calls = detail[detail["Concurrent_Count"] >= 1].copy()

# ── Build comparison for K=3 and K=4 ──────────────────────────────────────
rows = []
for K in [3, 4, 5]:
    sol_row = sol[(sol["K"] == K) & (sol["Objective"] == "PMed")].iloc[0]
    county_stations = parse_stations(sol_row)

    for dept in sorted(multi_amb):
        dept_sec = sec_calls[sec_calls["Dept"] == dept]
        n_sec    = len(dept_sec)
        if n_sec == 0:
            continue

        # Current: actual RT when 2nd unit responded
        current_median = dept_sec["Response_Min"].median()
        current_mean   = dept_sec["Response_Min"].mean()
        current_p90    = dept_sec["Response_Min"].quantile(0.90)

        # Proposed: county station drive time to dept centroid
        dlat, dlon = dept_coords.get(dept, (None, None))
        if dlat is None:
            continue
        county_rt = nearest_county_rt(dlat, dlon, county_stations)

        rows.append({
            "K":              K,
            "Dept":           dept,
            "Auth_Calls":     auth.get(dept, 0),
            "Sec_Calls":      n_sec,
            "Current_Median": round(current_median, 1),
            "Current_Mean":   round(current_mean, 1),
            "Current_P90":    round(current_p90, 1),
            "County_RT":      round(county_rt, 1),
            "Delta_Median":   round(county_rt - current_median, 1),
            "Delta_Mean":     round(county_rt - current_mean, 1),
        })

df = pd.DataFrame(rows)
print(df[["K","Dept","Sec_Calls","Current_Median","County_RT","Delta_Median"]].to_string(index=False))

# ── County-wide weighted impact ────────────────────────────────────────────
for K in [3, 4, 5]:
    kdf = df[df["K"] == K]
    total_sec = kdf["Sec_Calls"].sum()
    wt_current = (kdf["Sec_Calls"] * kdf["Current_Median"]).sum() / total_sec
    wt_county  = (kdf["Sec_Calls"] * kdf["County_RT"]).sum()   / total_sec
    print(f"K={K}: Weighted median RT -- Current {wt_current:.1f} min -> County {wt_county:.1f} min "
          f"(delta {wt_county - wt_current:+.1f} min) across {total_sec:.0f} secondary calls")

# ── Plot ───────────────────────────────────────────────────────────────────
C_CURRENT = "#2980b9"
C_POS     = "#e74c3c"
C_NEG     = "#27ae60"

# Dept colors for line chart
DEPT_COLORS = {
    "Fort Atkinson": "#e74c3c",
    "Jefferson":     "#8e44ad",
    "Johnson Creek": "#27ae60",
    "Waterloo":      "#e67e22",
    "Watertown":     "#2980b9",
}

fig, axes = plt.subplots(1, 3, figsize=(22, 8))
fig.patch.set_facecolor("white")

def _spine(ax):
    for sp in ("top","right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=10)

dept_order = df[df["K"]==3].sort_values("Sec_Calls", ascending=True)["Dept"].tolist()
y = np.arange(len(dept_order))
k3 = df[df["K"]==3].set_index("Dept")
k4 = df[df["K"]==4].set_index("Dept")
k5 = df[df["K"]==5].set_index("Dept")
K_sets = {3: k3, 4: k4, 5: k5}

# ── Panel 1: Current vs K=3/4/5 county RT (grouped bars) ──────────────────
ax1 = axes[0]
w = 0.2
K_colors = {3: "#e67e22", 4: "#27ae60", 5: "#8e44ad"}
K_labels = {3: "County K=3", 4: "County K=4", 5: "County K=5"}
offsets  = {3: w, 4: 0, 5: -w}

current_meds = [k3.loc[d,"Current_Median"] for d in dept_order]
ax1.barh(y + 1.5*w, current_meds, w, color=C_CURRENT,
         label="Current (own 2nd unit)", edgecolor="white", zorder=3)
for i, dept in enumerate(dept_order):
    ax1.text(0.3, i + 1.5*w, f"{current_meds[i]:.1f}",
             va="center", fontsize=8, color="white", fontweight="bold")

for K, offset in offsets.items():
    rts = [K_sets[K].loc[d,"County_RT"] for d in dept_order]
    ax1.barh(y + offset, rts, w, color=K_colors[K],
             label=K_labels[K], edgecolor="white", alpha=0.85, zorder=3)
    for i, rt in enumerate(rts):
        ax1.text(0.3, i + offset, f"{rt:.1f}",
                 va="center", fontsize=8, color="white", fontweight="bold")

# n= labels
for i, dept in enumerate(dept_order):
    n = int(k3.loc[dept,"Sec_Calls"])
    ax1.text(28, i, f"n={n}", va="center", fontsize=8, color="#777")

ax1.set_yticks(y)
ax1.set_yticklabels(dept_order, fontsize=10)
ax1.set_xlabel("Median Response Time (minutes)", fontsize=11)
ax1.set_title("Secondary Call RT:\nCurrent vs County Network (K=3,4,5)",
              fontsize=12, fontweight="bold", pad=10)
ax1.legend(fontsize=8.5, frameon=False, loc="lower right")
ax1.set_xlim(0, 30)
ax1.axvline(8,  color="#e74c3c", linewidth=0.8, linestyle=":", alpha=0.5)
ax1.axvline(14, color="#3498db", linewidth=0.8, linestyle=":", alpha=0.5)
_spine(ax1)

# ── Panel 2: Line chart — RT delta trajectory per dept across K ───────────
ax2 = axes[1]
K_vals_plot = [3, 4, 5]

for dept in dept_order:
    deltas = [K_sets[K].loc[dept,"Delta_Median"] for K in K_vals_plot]
    col = DEPT_COLORS.get(dept, "#555")
    ax2.plot(K_vals_plot, deltas, "o-", color=col, linewidth=2.2,
             markersize=8, label=dept, zorder=3)
    # label at K=5
    ax2.text(5.08, deltas[-1], dept, va="center", fontsize=8.5,
             color=col, fontweight="bold")
    # annotate Waterloo's K=5 point since it's the key story
    if dept == "Waterloo":
        ax2.annotate(f"{deltas[-1]:+.1f} min\nat K=5",
                     xy=(5, deltas[-1]),
                     xytext=(4.4, deltas[-1] - 4),
                     fontsize=8.5, color=col, fontweight="bold",
                     arrowprops=dict(arrowstyle="-|>", color=col, lw=0.9))

ax2.axhline(0, color="#333", linewidth=1.2, linestyle="-", alpha=0.4)
ax2.fill_between([2.5, 5.5], 0, 25,  color="#e74c3c", alpha=0.04)
ax2.fill_between([2.5, 5.5], -10, 0, color="#27ae60", alpha=0.04)
ax2.text(2.6, 22,  "Slower than current", fontsize=8, color="#e74c3c", alpha=0.7)
ax2.text(2.6, -8,  "Faster than current", fontsize=8, color="#27ae60", alpha=0.7)

ax2.set_xticks(K_vals_plot)
ax2.set_xticklabels([f"K={k}" for k in K_vals_plot], fontsize=11)
ax2.set_xlabel("Number of County Secondary Stations", fontsize=11)
ax2.set_ylabel("Change in Median RT vs Current (min)", fontsize=11)
ax2.set_title("RT Change Trajectory per Dept\n(+ = slower, - = faster than current 2nd unit)",
              fontsize=12, fontweight="bold", pad=10)
ax2.set_xlim(2.5, 5.8)
ax2.grid(axis="y", alpha=0.2, color="#ccc")
_spine(ax2)

# ── Panel 3: County-wide weighted aggregate RT by K ───────────────────────
ax3 = axes[2]
agg_rows = []
for K in K_vals_plot:
    kdf = df[df["K"]==K]
    total_sec = kdf["Sec_Calls"].sum()
    wt_current = (kdf["Sec_Calls"] * kdf["Current_Median"]).sum() / total_sec
    wt_county  = (kdf["Sec_Calls"] * kdf["County_RT"]).sum()     / total_sec
    agg_rows.append({"K": K, "Current": wt_current, "County": wt_county,
                     "Delta": wt_county - wt_current})
agg = pd.DataFrame(agg_rows)

x = np.arange(len(K_vals_plot))
w2 = 0.35
ax3.bar(x - w2/2, agg["Current"], w2, color=C_CURRENT,
        label="Current (own 2nd unit)", edgecolor="white", alpha=0.85)
ax3.bar(x + w2/2, agg["County"],  w2,
        color=[K_colors[k] for k in K_vals_plot],
        label="County network", edgecolor="white", alpha=0.85)

for i, row in agg.iterrows():
    ax3.text(i - w2/2, row["Current"] + 0.2, f"{row['Current']:.1f}",
             ha="center", fontsize=9, color=C_CURRENT, fontweight="bold")
    col = K_colors[row["K"]]
    ax3.text(i + w2/2, row["County"]  + 0.2, f"{row['County']:.1f}",
             ha="center", fontsize=9, color=col, fontweight="bold")
    ax3.text(i, max(row["Current"], row["County"]) + 0.8,
             f"{row['Delta']:+.1f} min", ha="center", fontsize=9,
             color=C_POS if row["Delta"] > 0 else C_NEG, fontweight="bold")

ax3.set_xticks(x)
ax3.set_xticklabels([f"K={k}" for k in K_vals_plot], fontsize=11)
ax3.set_xlabel("Number of County Secondary Stations", fontsize=11)
ax3.set_ylabel("Call-Volume Weighted Median RT (minutes)", fontsize=11)
ax3.set_title("County-Wide Aggregate\nWeighted Median RT: Current vs County Network",
              fontsize=12, fontweight="bold", pad=10)
ax3.set_ylim(0, 12)

legend_els = [
    mpatches.Patch(color=C_CURRENT, label="Current (dept 2nd unit)"),
    mpatches.Patch(color=K_colors[3], label="County K=3"),
    mpatches.Patch(color=K_colors[4], label="County K=4"),
    mpatches.Patch(color=K_colors[5], label="County K=5"),
]
ax3.legend(handles=legend_els, fontsize=8.5, frameon=False)
ax3.text(0.03, 0.04,
         f"Weighted by secondary call volume per dept\n"
         f"Total secondary events: {int(df[df.K==3].Sec_Calls.sum())} calls/yr",
         transform=ax3.transAxes, fontsize=8, color="#777",
         bbox=dict(boxstyle="round,pad=0.3", facecolor="#f9f9f9",
                   edgecolor="#ddd", alpha=0.9))
ax3.grid(axis="y", alpha=0.2, color="#ccc")
_spine(ax3)

fig.suptitle(
    "Jefferson County EMS — Secondary Ambulance Consolidation Impact by Fleet Size\n"
    "What happens to secondary call RT when dept 2nd units are replaced by a county network?",
    fontsize=13, fontweight="bold", y=1.01
)
plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_consolidation_impact.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")
