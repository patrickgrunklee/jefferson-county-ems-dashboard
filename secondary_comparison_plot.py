"""
Side-by-side visual comparison of the secondary-ambulance pipeline
BEFORE (all-district NFIRS) vs AFTER (Jefferson-only) the 2026-04-19
geo-correction.

Reads:
  - concurrent_call_results.csv + _jeffco variant
  - secondary_network_solutions.csv + _jeffco variant
  - secondary_staffing_scenarios.csv + _jeffco variant

Writes:
  - secondary_comparison_plot.png  (4-panel composite)
"""
from __future__ import annotations
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

ORIG_COL = "#95a5a6"
JEFF_COL = "#2980b9"


def _load_pair(fname_base: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    orig = pd.read_csv(os.path.join(SCRIPT_DIR, f"{fname_base}.csv"))
    jeff = pd.read_csv(os.path.join(SCRIPT_DIR, f"{fname_base}_jeffco.csv"))
    return orig, jeff


def panel_calls_by_dept(ax):
    orig, jeff = _load_pair("concurrent_call_results")
    df = orig[["Dept", "EMS_Calls_2024"]].rename(columns={"EMS_Calls_2024": "Orig"})
    df = df.merge(jeff[["Dept", "EMS_Calls_2024"]].rename(columns={"EMS_Calls_2024": "Jeff"}), on="Dept", how="outer").fillna(0)
    df = df.sort_values("Orig", ascending=True)
    y = np.arange(len(df))
    ax.barh(y - 0.18, df["Orig"], 0.36, color=ORIG_COL, label="Before (all-district)")
    ax.barh(y + 0.18, df["Jeff"], 0.36, color=JEFF_COL, label="After (Jefferson-only)")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Dept"], fontsize=9)
    ax.set_xlabel("EMS calls in 2024 (from NFIRS, micro pipeline input)")
    ax.set_title("EMS calls entering the secondary-ambulance pipeline",
                 fontsize=11, fontweight="bold", loc="left")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for i, (o, j) in enumerate(zip(df["Orig"], df["Jeff"])):
        if o > 0:
            ax.text(o + 50, i - 0.18, f"{int(o):,}", va="center", fontsize=7.5, color=ORIG_COL)
        if j > 0:
            ax.text(j + 50, i + 0.18, f"{int(j):,}", va="center", fontsize=7.5, color=JEFF_COL)


def panel_secondary_events(ax):
    orig, jeff = _load_pair("concurrent_call_results")
    df = orig[["Dept", "Secondary_Events"]].rename(columns={"Secondary_Events": "Orig"})
    df = df.merge(jeff[["Dept", "Secondary_Events"]].rename(columns={"Secondary_Events": "Jeff"}), on="Dept", how="outer").fillna(0)
    df = df.sort_values("Orig", ascending=True)
    y = np.arange(len(df))
    ax.barh(y - 0.18, df["Orig"], 0.36, color=ORIG_COL, label="Before")
    ax.barh(y + 0.18, df["Jeff"], 0.36, color=JEFF_COL, label="After")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Dept"], fontsize=9)
    ax.set_xlabel("Concurrent-call (secondary-demand) events")
    ax.set_title("Secondary-demand events per dept",
                 fontsize=11, fontweight="bold", loc="left")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    # Annotate biggest dropouts
    for i, (dept, o, j) in enumerate(zip(df["Dept"], df["Orig"], df["Jeff"])):
        if o > 0 and (o - j) >= 300:
            ax.text(o + 15, i - 0.18, f"{int(o)} → {int(j)}",
                    va="center", fontsize=8, color="#c0392b", fontweight="bold")
    total_orig = int(df["Orig"].sum())
    total_jeff = int(df["Jeff"].sum())
    pct = 100 * (total_orig - total_jeff) / total_orig if total_orig else 0
    ax.text(0.02, 0.04,
            f"Total: {total_orig:,} → {total_jeff:,}  ({pct:.0f}% of inflated demand was cross-county)",
            transform=ax.transAxes, fontsize=9, color="#c0392b", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fdecea", edgecolor="#c0392b"))


def panel_k3_recommendation(ax):
    orig, jeff = _load_pair("secondary_network_solutions")

    def pick(df):
        sub = df[(df["K"] == 3) & (df["Objective"] == "MCLP")].copy()
        sub = sub[sub["T"].astype(str) == "14"]
        return sub.iloc[0] if len(sub) else None

    o, j = pick(orig), pick(jeff)
    metrics = ["Avg RT (min)", "Max RT (min)", "Demand covered (%)"]
    orig_vals = [o["Avg_RT"], o["Max_RT"], o["Demand_Pct_Covered"]]
    jeff_vals = [j["Avg_RT"], j["Max_RT"], j["Demand_Pct_Covered"]]

    x = np.arange(len(metrics))
    w = 0.38
    b1 = ax.bar(x - w/2, orig_vals, w, color=ORIG_COL, label="Before")
    b2 = ax.bar(x + w/2, jeff_vals, w, color=JEFF_COL, label="After")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=9)
    ax.set_ylabel("Value")
    ax.set_title("K=3 MCLP recommendation — before vs after filter",
                 fontsize=11, fontweight="bold", loc="left")
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for rect, v in list(zip(b1, orig_vals)) + list(zip(b2, jeff_vals)):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.6,
                f"{v:.1f}", ha="center", fontsize=9, color="#333")


def panel_staffing_scenarios(ax):
    orig, jeff = _load_pair("secondary_staffing_scenarios")
    scenarios = orig["Scenario"].tolist()
    short = [s.split(":")[0].strip() for s in scenarios]  # "A","B","C"
    x = np.arange(len(scenarios))
    w = 0.38
    b1 = ax.bar(x - w/2, orig["Net_Cost"] / 1000, w, color=ORIG_COL, label="Before")
    b2 = ax.bar(x + w/2, jeff["Net_Cost"] / 1000, w, color=JEFF_COL, label="After")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{a}\n{s.split(':',1)[1][:26] + '...' if len(s.split(':',1)[1]) > 28 else s.split(':',1)[1]}"
                         for a, s in zip(short, scenarios)],
                        fontsize=8)
    ax.set_ylabel("Net cost ($K/year)")
    ax.set_title("Staffing scenarios — identical (call volume doesn't drive cost)",
                 fontsize=11, fontweight="bold", loc="left")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for rect, v in list(zip(b1, orig["Net_Cost"])) + list(zip(b2, jeff["Net_Cost"])):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height()/1000 + 8,
                f"${v/1000:.0f}K", ha="center", fontsize=8.5, color="#333")
    # Note: identical values
    ax.text(0.5, 0.95,
            "Net cost, operating cost, and FTE are identical in both runs.",
            transform=ax.transAxes, fontsize=8, ha="center", va="top",
            style="italic", color="#666")


def build_composite():
    fig = plt.figure(figsize=(16, 11))
    gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.22,
                          left=0.06, right=0.97, top=0.92, bottom=0.06)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])

    panel_calls_by_dept(ax1)
    panel_secondary_events(ax2)
    panel_k3_recommendation(ax3)
    panel_staffing_scenarios(ax4)

    fig.suptitle(
        "Secondary-Ambulance Pipeline: Before vs After Jefferson-Geography Correction (2026-04-19)",
        fontsize=14, fontweight="bold", y=0.97,
    )
    fig.text(0.5, 0.935,
             "Before = all-district NFIRS (includes Waukesha, Rock, Walworth, Dodge Co. calls)   "
             "|   After = Jefferson County only (per Megan 2026-04-19 authoritative totals)",
             ha="center", fontsize=9.5, color="#555")

    out = os.path.join(SCRIPT_DIR, "secondary_comparison_plot.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    build_composite()
