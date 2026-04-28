"""
Weighted average RT per dept: baseline (own 2nd unit) vs county network K=3,4,5.
Weights = (primary calls × primary RT + secondary calls × secondary RT) / total calls.
Shows the true per-dept impact of consolidation on overall EMS response time.

Output: secondary_weighted_rt_impact.png
"""
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import ems_dashboard_app as m

rt     = m.rt_clean
auth   = m.AUTH_EMS_CALLS
detail = pd.read_csv(os.path.join(SCRIPT_DIR, "concurrent_call_detail_jeffco.csv"))
sec    = detail[detail["Concurrent_Count"] >= 1]

# County RT per dept for K=3,4,5 (nearest station ORS drive time)
COUNTY_RT = {
    "Fort Atkinson": {3: 5.9,  4: 5.9,  5: 5.9},
    "Jefferson":     {3: 14.3, 4: 5.1,  5: 5.1},
    "Johnson Creek": {3: 1.6,  4: 1.6,  5: 1.6},
    "Waterloo":      {3: 26.0, 4: 26.0, 5: 6.0},
    "Watertown":     {3: 1.7,  4: 1.7,  5: 1.7},
}

rows = []
for dept, crt in COUNTY_RT.items():
    dept_rt  = rt[rt["Department"] == dept]["RT"].dropna()
    dept_sec = sec[sec["Dept"] == dept]["Response_Min"].dropna()
    if len(dept_rt) == 0:
        continue

    pri_calls = len(dept_rt) - len(dept_sec)
    sec_calls = len(dept_sec)
    total     = pri_calls + sec_calls
    pri_med   = dept_rt.median()
    sec_med   = dept_sec.median() if len(dept_sec) > 0 else np.nan
    sec_pct   = 100 * sec_calls / total if total > 0 else 0

    wtd_base = (pri_calls * pri_med + sec_calls * sec_med) / total if len(dept_sec) > 0 else pri_med
    wtd = {K: (pri_calls * pri_med + sec_calls * c) / total for K, c in crt.items()}

    rows.append({
        "Dept": dept, "Total": total,
        "Pri_calls": pri_calls, "Sec_calls": sec_calls, "Sec_pct": sec_pct,
        "Pri_med": pri_med, "Sec_med": sec_med,
        "Base": wtd_base,
        "K3": wtd[3], "K4": wtd[4], "K5": wtd[5],
        "Delta_K3": wtd[3] - wtd_base,
        "Delta_K4": wtd[4] - wtd_base,
        "Delta_K5": wtd[5] - wtd_base,
    })

df = pd.DataFrame(rows).sort_values("Total", ascending=True)

# County-wide weighted aggregate
total_calls_all = sum(r["Total"] for _, r in df.iterrows())
agg = {}
for col, label in [("Base","Baseline"), ("K3","K=3"), ("K4","K=4"), ("K5","K=5")]:
    agg[label] = sum(r["Total"] * r[col] for _, r in df.iterrows()) / total_calls_all

print("Per-dept weighted RT impact:")
print(df[["Dept","Total","Sec_pct","Base","K3","K4","K5","Delta_K3","Delta_K4","Delta_K5"]].round(1).to_string(index=False))
print("\nCounty-wide aggregate weighted RT:")
for k,v in agg.items():
    print(f"  {k}: {v:.2f} min")

# ── Plot ───────────────────────────────────────────────────────────────────
C_BASE = "#2980b9"
C_K3   = "#e67e22"
C_K4   = "#27ae60"
C_K5   = "#8e44ad"
C_POS  = "#e74c3c"
C_NEG  = "#27ae60"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
fig.patch.set_facecolor("white")

def _spine(ax):
    for sp in ("top","right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555", labelsize=10)

depts  = df["Dept"].tolist()
y      = np.arange(len(depts))
w      = 0.18

# ── Panel 1: Absolute weighted RT ─────────────────────────────────────────
for i, (col, col_c, label, off) in enumerate([
    ("Base", C_BASE, "Baseline (own 2nd unit)", 1.5*w),
    ("K3",   C_K3,  "County K=3",               0.5*w),
    ("K4",   C_K4,  "County K=4",              -0.5*w),
    ("K5",   C_K5,  "County K=5",              -1.5*w),
]):
    vals = df[col].tolist()
    ax1.barh(y + off, vals, w, color=col_c, label=label,
             edgecolor="white", alpha=0.88, zorder=3)
    for j, v in enumerate(vals):
        ax1.text(0.2, y[j] + off, f"{v:.1f}", va="center",
                 fontsize=8, color="white", fontweight="bold")

# Secondary % annotation on right
for j, (_, row) in enumerate(df.iterrows()):
    ax1.text(ax1.get_xlim()[1] if ax1.get_xlim()[1] > 0 else 15,
             y[j], f"{row['Sec_pct']:.0f}% overflow\n({int(row['Sec_calls'])} calls)",
             va="center", fontsize=7.5, color="#777")

ax1.set_yticks(y)
ax1.set_yticklabels(depts, fontsize=10)
ax1.set_xlabel("Call-Volume Weighted Median RT (minutes)", fontsize=11)
ax1.set_title("Weighted Average RT per Dept\n(primary + secondary calls combined)",
              fontsize=12, fontweight="bold", pad=10)
ax1.legend(fontsize=8.5, frameon=False, loc="lower right")
ax1.set_xlim(0, 14)
_spine(ax1)

# ── Panel 2: Delta from baseline ──────────────────────────────────────────
for col, col_c, label, off in [
    ("Delta_K3", C_K3, "County K=3", 0.25*w*3),
    ("Delta_K4", C_K4, "County K=4", 0),
    ("Delta_K5", C_K5, "County K=5", -0.25*w*3),
]:
    deltas = df[col].tolist()
    colors = [C_POS if d > 0.05 else (C_NEG if d < -0.05 else "#aaa") for d in deltas]
    bars = ax2.barh(y + off, deltas, w*2, color=colors,
                    edgecolor="white", alpha=0.8, zorder=3)
    for j, d in enumerate(deltas):
        offset = 0.08 if d >= 0 else -0.08
        ax2.text(d + offset, y[j] + off, f"{d:+.2f}",
                 va="center", fontsize=8,
                 color=C_POS if d > 0.05 else (C_NEG if d < -0.05 else "#888"),
                 fontweight="bold")

ax2.axvline(0, color="#333", linewidth=1.2, alpha=0.5)
ax2.fill_between([-5, 5], -0.5, len(depts)-0.5, alpha=0)  # invisible, just sets range
ax2.text(0.35,  0.97, "Slower than baseline", transform=ax2.transAxes,
         fontsize=8.5, color=C_POS, va="top", ha="left")
ax2.text(-0.02, 0.97, "Faster than baseline", transform=ax2.transAxes,
         fontsize=8.5, color=C_NEG, va="top", ha="right")

ax2.set_yticks(y)
ax2.set_yticklabels(depts, fontsize=10)
ax2.set_xlabel("Change in Weighted Median RT vs Baseline (minutes)", fontsize=11)
ax2.set_title("RT Impact of Consolidation\n(weighted by call volume — secondary = ~10-22% of total)",
              fontsize=12, fontweight="bold", pad=10)

legend_els = [
    mpatches.Patch(color=C_K3, alpha=0.85, label=f"K=3  (county-wide wtd: {agg['K=3']:.2f} min)"),
    mpatches.Patch(color=C_K4, alpha=0.85, label=f"K=4  (county-wide wtd: {agg['K=4']:.2f} min)"),
    mpatches.Patch(color=C_K5, alpha=0.85, label=f"K=5  (county-wide wtd: {agg['K=5']:.2f} min)"),
    mpatches.Patch(color=C_BASE, alpha=0.85, label=f"Baseline (wtd: {agg['Baseline']:.2f} min)"),
]
ax2.legend(handles=legend_els, fontsize=8.5, frameon=False, loc="lower right")
ax2.set_xlim(-3, 5)
ax2.grid(axis="x", alpha=0.2, color="#ccc")
_spine(ax2)

fig.suptitle(
    "Jefferson County EMS — True RT Impact of Secondary Consolidation\n"
    "Weighted by actual call volume: secondary calls are 10-22% of total per dept",
    fontsize=13, fontweight="bold", y=1.01
)
plt.tight_layout()
out = os.path.join(SCRIPT_DIR, "secondary_weighted_rt_impact.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved: {out}")
