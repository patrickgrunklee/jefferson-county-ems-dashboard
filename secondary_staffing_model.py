"""
Jefferson County EMS — Secondary Ambulance Staffing & Cost Model
================================================================
What does it cost to staff the recommended secondary ambulance network?
Compares 24/7, peak-hours-only, and hybrid scenarios using the Peterson
cost model as the baseline.

Inputs:
  - secondary_network_solutions.csv (Phase 2)
  - concurrent_call_results.csv (Phase 1)
  - Peterson cost model ($716K operating / 24/7 ALS crew, $466K revenue offset)

Outputs:
  - secondary_staffing_scenarios.csv   3 scenarios with full cost breakdowns
  - staffing_waterfall.png             waterfall chart for recommended scenario
  - current_vs_consolidated.png        comparison chart
  - fte_transition.csv                 department-by-department staffing transition

Author: ISyE 450 Senior Design Team
Date:   March 2026
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Jefferson-only mode — reads _jeffco inputs, writes _jeffco outputs
JEFFCO_MODE = "--jeffco" in sys.argv
OUTPUT_SUFFIX = "_jeffco" if JEFFCO_MODE else ""

# ── Peterson Cost Model (from ems_dashboard_app.py line ~1924) ──────────
# Source: 25-1210 JC EMS Workgroup Cost Projection.pdf (Chief Bruce Peterson, FAFD)
PETERSON = {
    "Salaries":       371697,
    "Overtime":        24894,
    "Benefits":       178466,
    "WRS_Pension":     27761,
    "EMS_Supplies":    28000,
    "Clothing":         3000,
    "Amb_Maint":        7000,
    "Amb_Equip":        2000,
    "Insurance":       67500,
    "Equip_Maint":       500,
    "Training":         1000,
    "Admin":            5000,
}
PETERSON_TOTAL_OPERATING = sum(PETERSON.values())  # ~$716,818
PETERSON_REVENUE = 466200  # 700 calls × $666 avg collected
PETERSON_NET = PETERSON_TOTAL_OPERATING - PETERSON_REVENUE

# FTE assumptions
FTE_24_7 = 7.2    # 2 crew × 3 shifts × 1.2 relief factor
FTE_12_HR = 4.8   # 2 crew × 2 shifts × 1.2 relief
FTE_CREW_SIZE = 2  # minimum crew per ambulance response

# ── Current department data ─────────────────────────────────────────────
DEPT_DATA = {
    "Watertown":     {"FT": 31, "PT":  3, "Ambulances": 3, "Expense": 3833800, "Pop": 23000, "Secondary_Events": 656},
    "Fort Atkinson": {"FT": 16, "PT": 28, "Ambulances": 3, "Expense":  760950, "Pop": 16300, "Secondary_Events": 209},
    "Whitewater":    {"FT": 15, "PT": 17, "Ambulances": 2, "Expense": 2710609, "Pop":  4296, "Secondary_Events": 421},
    "Edgerton":      {"FT": 24, "PT":  0, "Ambulances": 2, "Expense":  704977, "Pop":  3763, "Secondary_Events": 768},
    "Jefferson":     {"FT":  6, "PT": 20, "Ambulances": 3, "Expense": 1500300, "Pop":  7800, "Secondary_Events":   2},
    "Johnson Creek": {"FT":  3, "PT": 40, "Ambulances": 2, "Expense": 1134154, "Pop":  3367, "Secondary_Events":  59},
    "Waterloo":      {"FT":  4, "PT": 22, "Ambulances": 2, "Expense": 1102475, "Pop":  4415, "Secondary_Events":  93},
    "Ixonia":        {"FT":  2, "PT": 45, "Ambulances": 1, "Expense":  631144, "Pop":  5078, "Secondary_Events":  32},
    "Palmyra":       {"FT":  0, "PT": 20, "Ambulances": 1, "Expense":  817740, "Pop":  3341, "Secondary_Events":   0},
}


# ── Scenario definitions ───────────────────────────────────────────────
def compute_scenario_a(k):
    """Scenario A: All K secondaries staffed 24/7 ALS."""
    operating = k * PETERSON_TOTAL_OPERATING
    revenue = k * PETERSON_REVENUE
    net = operating - revenue
    fte = k * FTE_24_7

    return {
        "Scenario": f"A: All {k} stations 24/7 ALS",
        "K": k,
        "Total_Operating": round(operating),
        "Total_Revenue": round(revenue),
        "Net_Cost": round(net),
        "Total_FTE": round(fte, 1),
        "Cost_Per_Station": round(PETERSON_NET),
        "Coverage_Model": "24/7",
        "Notes": f"{k} × Peterson model ($716K operating, $466K revenue = $250K net each)",
    }


def compute_scenario_b(k):
    """Scenario B: All K secondaries staffed peak-hours only (08:00-20:00, 12hr)."""
    # Peak-only scaling: salary/OT/benefits = 12hr/24hr = 50% of those line items
    # But minimum shift coverage = 2 shifts (day + swing) not 3 → salary ~ 67% of 24/7
    # Fixed costs (insurance, supplies, equipment) stay the same
    salary_items = PETERSON["Salaries"] + PETERSON["Overtime"] + PETERSON["Benefits"] + PETERSON["WRS_Pension"]
    fixed_items = (PETERSON["EMS_Supplies"] + PETERSON["Clothing"] + PETERSON["Amb_Maint"] +
                   PETERSON["Amb_Equip"] + PETERSON["Insurance"] + PETERSON["Equip_Maint"] +
                   PETERSON["Training"] + PETERSON["Admin"])

    # 12hr = 2 shifts instead of 3 → salary portion × (2/3)
    salary_scaled = salary_items * (2 / 3)
    operating_per = salary_scaled + fixed_items
    # Revenue reduced: only covering ~60% of calls (peak hours capture ~65% of demand)
    revenue_per = PETERSON_REVENUE * 0.65
    net_per = operating_per - revenue_per

    operating = k * operating_per
    revenue = k * revenue_per
    net = operating - revenue
    fte = k * FTE_12_HR

    return {
        "Scenario": f"B: All {k} stations peak-only (08-20)",
        "K": k,
        "Total_Operating": round(operating),
        "Total_Revenue": round(revenue),
        "Net_Cost": round(net),
        "Total_FTE": round(fte, 1),
        "Cost_Per_Station": round(net_per),
        "Coverage_Model": "Peak 12hr",
        "Notes": f"Salary × 2/3, fixed costs same, revenue × 0.65 (peak call share)",
    }


def compute_scenario_c(k):
    """Scenario C: Highest-demand secondary 24/7, rest peak-only (hybrid)."""
    if k < 2:
        return compute_scenario_a(k)

    # 1 station 24/7
    a1 = compute_scenario_a(1)
    # Remaining peak-only
    b_rest = compute_scenario_b(k - 1)

    operating = a1["Total_Operating"] + b_rest["Total_Operating"]
    revenue = a1["Total_Revenue"] + b_rest["Total_Revenue"]
    net = operating - revenue
    fte = a1["Total_FTE"] + b_rest["Total_FTE"]

    return {
        "Scenario": f"C: Hybrid — 1 × 24/7 + {k-1} × peak-only",
        "K": k,
        "Total_Operating": round(operating),
        "Total_Revenue": round(revenue),
        "Net_Cost": round(net),
        "Total_FTE": round(fte, 1),
        "Cost_Per_Station": round(net / k),
        "Coverage_Model": "Hybrid",
        "Notes": f"Central station 24/7 ($250K net), others peak-only",
    }


# ── Current distributed secondary cost estimate ────────────────────────
def estimate_current_secondary_cost():
    """
    Estimate what departments currently spend on secondary ambulance capacity.
    This includes: PT staff on-call for 2nd+ ambulance, maintenance/insurance
    on backup ambulances, overhead of maintaining surge capacity.

    Conservative estimate: departments with >1 ambulance dedicate ~15-25%
    of their total budget to secondary capacity (2nd+ unit maintenance,
    PT on-call pay, extra insurance).
    """
    rows = []
    total_secondary_cost = 0

    for dept, data in DEPT_DATA.items():
        amb = data["Ambulances"]
        exp = data["Expense"]
        if exp is None:
            continue

        if amb <= 1:
            # Single-ambulance dept: no secondary capacity
            secondary_pct = 0
        elif amb == 2:
            # 2nd ambulance: ~15-20% of budget (maintenance, PT coverage, insurance)
            secondary_pct = 0.18
        else:
            # 3+ ambulances: ~20-25% (multiple backup units)
            secondary_pct = 0.22

        secondary_cost = exp * secondary_pct
        total_secondary_cost += secondary_cost

        rows.append({
            "Dept": dept,
            "Ambulances": amb,
            "Total_Expense": exp,
            "Est_Secondary_Pct": f"{secondary_pct:.0%}",
            "Est_Secondary_Cost": round(secondary_cost),
            "Secondary_Events": data["Secondary_Events"],
            "Cost_Per_Event": round(secondary_cost / max(data["Secondary_Events"], 1)),
        })

    return pd.DataFrame(rows), total_secondary_cost


# ── FTE transition table ──────────────────────────────────────────────
def compute_fte_transition(k):
    """
    Map current distributed PT/on-call positions involved in secondary
    coverage to proposed consolidated FT positions.
    """
    rows = []
    for dept, data in DEPT_DATA.items():
        amb = data["Ambulances"]
        pt = data["PT"]
        sec_events = data["Secondary_Events"]

        if amb <= 1:
            # No secondary ambulance — no PT dedicated to backup
            pt_secondary = 0
        else:
            # Estimate PT staff primarily covering 2nd+ ambulance
            # Assumption: departments with 2 ambulances have ~30-40% of PT
            # on-call for the 2nd unit
            pt_secondary = round(pt * 0.35) if amb == 2 else round(pt * 0.45)

        rows.append({
            "Dept": dept,
            "Current_FT": data["FT"],
            "Current_PT": pt,
            "PT_On_Secondary": pt_secondary,
            "Secondary_Events_Yr": sec_events,
            "Current_Ambulances": amb,
            "Proposed_Primary_Amb": min(amb, 1),  # Keep 1 primary
            "Note": "Retains primary ambulance" if amb > 0 else "No change",
        })

    df = pd.DataFrame(rows)

    # Summary: total PT that could transition
    total_pt_secondary = df["PT_On_Secondary"].sum()
    proposed_fte = k * FTE_24_7  # for scenario A
    proposed_fte_peak = k * FTE_12_HR  # for scenario B

    return df, total_pt_secondary, proposed_fte, proposed_fte_peak


# ── Plotting ───────────────────────────────────────────────────────────
def plot_waterfall(scenario, k):
    """Waterfall chart for the recommended staffing scenario."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # Build waterfall items from Peterson model × K
    items = list(PETERSON.keys()) + ["Total_Operating", "Revenue_Offset", "Net_Cost"]
    values = [v * k for v in PETERSON.values()]
    total_op = sum(values)
    revenue = PETERSON_REVENUE * k
    net = total_op - revenue

    values.append(0)  # placeholder for total
    values.append(-revenue)
    values.append(0)  # placeholder for net

    measures = ["relative"] * len(PETERSON) + ["total", "relative", "total"]
    labels = [
        "Salaries", "Overtime", "Benefits", "WRS Pension",
        "EMS Supplies", "Clothing", "Amb Maint", "Amb Equip",
        "Insurance", "Equip Maint", "Training", "Admin",
        "Total Operating", f"Revenue\n({k}×700 calls)", "Net Cost"
    ]

    # Manual waterfall
    running = 0
    bottoms = []
    heights = []
    colors = []

    for i, (label, val, meas) in enumerate(zip(labels, values, measures)):
        if meas == "total":
            bottoms.append(0)
            if label == "Net Cost":
                heights.append(net)
                colors.append("#e74c3c" if net > 0 else "#2ecc71")
            else:
                heights.append(total_op)
                colors.append("#3498db")
        elif val < 0:
            bottoms.append(running + val)
            heights.append(-val)
            colors.append("#2ecc71")
            running += val
        else:
            bottoms.append(running)
            heights.append(val)
            colors.append("#e74c3c" if val > 100000 else "#f39c12")
            running += val

    bars = ax.bar(range(len(labels)), heights, bottom=bottoms, color=colors,
                  edgecolor="#333", linewidth=0.5, width=0.7)

    # Value labels
    for i, (b, h) in enumerate(zip(bottoms, heights)):
        if abs(h) > 10000:
            y = b + h / 2
            ax.text(i, y, f"${h:,.0f}", ha="center", va="center",
                    fontsize=8, fontweight="bold", color="white")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Annual Cost ($)", fontsize=12)
    ax.set_title(
        f"Secondary Ambulance Network: {scenario['Scenario']}\n"
        f"Peterson Cost Model × {k} stations | "
        f"Net: ${net:,.0f}/yr | {scenario['Total_FTE']} FTE",
        fontsize=13, fontweight="bold"
    )

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    fname = f"staffing_waterfall{OUTPUT_SUFFIX}.png"
    fpath = os.path.join(SCRIPT_DIR, fname)
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")


def plot_comparison(scenarios_df, current_cost):
    """Bar chart comparing scenarios vs current distributed cost."""
    fig, ax = plt.subplots(figsize=(12, 7))

    labels = ["Current\nDistributed"] + [s.replace(": ", "\n") for s in scenarios_df["Scenario"]]
    net_costs = [current_cost] + scenarios_df["Net_Cost"].tolist()
    ftes = [None] + scenarios_df["Total_FTE"].tolist()

    colors = ["#95a5a6"] + ["#e74c3c", "#f39c12", "#3498db"][:len(scenarios_df)]

    bars = ax.bar(range(len(labels)), net_costs, color=colors, edgecolor="#333",
                  linewidth=0.5, width=0.6)

    for i, (bar, cost) in enumerate(zip(bars, net_costs)):
        label_text = f"${cost:,.0f}"
        if ftes[i] is not None:
            label_text += f"\n{ftes[i]} FTE"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 10000,
                label_text, ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Annual Net Cost ($)", fontsize=12)
    ax.set_title(
        "Secondary Ambulance Network: Cost Comparison\n"
        "Current distributed overhead vs consolidated regional scenarios",
        fontsize=13, fontweight="bold"
    )
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.grid(axis="y", alpha=0.3)

    # Add note
    ax.text(0.02, 0.98,
            "Current = est. 18-22% of dept budgets for 2nd+ ambulance overhead\n"
            "Scenarios based on Peterson cost model ($716K operating, $466K revenue/station)",
            transform=ax.transAxes, fontsize=8, va="top",
            bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    plt.tight_layout()

    fname = f"current_vs_consolidated{OUTPUT_SUFFIX}.png"
    fpath = os.path.join(SCRIPT_DIR, fname)
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")


# ── Main ───────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — SECONDARY AMBULANCE STAFFING MODEL")
    print("=" * 70)

    # Recommended K from Phase 2 (default K=3 based on 86% coverage elbow)
    K = 3

    # Load Phase 2 solutions for context
    sol_path = os.path.join(SCRIPT_DIR, f"secondary_network_solutions{OUTPUT_SUFFIX}.csv")
    if os.path.exists(sol_path):
        solutions = pd.read_csv(sol_path)
        print(f"\n>> Phase 2 solutions loaded ({len(solutions)} rows)")
        # T column may be mixed int/str from CSV
        solutions["T"] = solutions["T"].apply(lambda x: int(x) if str(x).isdigit() else x)
        match = solutions[(solutions['K'] == K) & (solutions['T'] == 14)]
        if not match.empty:
            print(f"   Recommended K={K}: MCLP T=14 covers "
                  f"{match['Demand_Pct_Covered'].values[0]:.0f}% of secondary demand")

    # Peterson baseline
    print(f"\n>> Peterson 24/7 ALS Cost Model:")
    print(f"   Operating: ${PETERSON_TOTAL_OPERATING:,.0f}")
    print(f"   Revenue:   ${PETERSON_REVENUE:,.0f}")
    print(f"   Net:       ${PETERSON_NET:,.0f}")

    # Current distributed cost
    print(f"\n>> Estimating current distributed secondary costs...")
    current_df, current_total = estimate_current_secondary_cost()
    print(current_df[["Dept", "Ambulances", "Est_Secondary_Cost",
                       "Secondary_Events", "Cost_Per_Event"]].to_string(index=False))
    print(f"\n   Total estimated current secondary overhead: ${current_total:,.0f}")

    # Three scenarios
    print(f"\n>> Computing staffing scenarios for K={K}...")
    print("-" * 50)

    scenarios = [
        compute_scenario_a(K),
        compute_scenario_b(K),
        compute_scenario_c(K),
    ]

    scenarios_df = pd.DataFrame(scenarios)
    print()
    print(scenarios_df[["Scenario", "Total_Operating", "Total_Revenue",
                         "Net_Cost", "Total_FTE", "Coverage_Model"]].to_string(index=False))

    # Save
    csv_name = f"secondary_staffing_scenarios{OUTPUT_SUFFIX}.csv"
    csv_path = os.path.join(SCRIPT_DIR, csv_name)
    scenarios_df.to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_name}")

    # FTE transition
    print(f"\n>> Computing FTE transition...")
    fte_df, total_pt_sec, proposed_a, proposed_b = compute_fte_transition(K)
    print(fte_df[["Dept", "Current_FT", "Current_PT", "PT_On_Secondary",
                   "Secondary_Events_Yr"]].to_string(index=False))
    print(f"\n   Current PT on secondary duty (est.): {total_pt_sec}")
    print(f"   Proposed FTE for {K} stations (24/7): {proposed_a:.1f}")
    print(f"   Proposed FTE for {K} stations (peak): {proposed_b:.1f}")

    fte_name = f"fte_transition{OUTPUT_SUFFIX}.csv"
    fte_path = os.path.join(SCRIPT_DIR, fte_name)
    fte_df.to_csv(fte_path, index=False)
    print(f"  Saved: {fte_name}")

    # Plots
    print(f"\n>> Generating charts...")
    # Waterfall for Scenario C (hybrid — most likely recommendation)
    plot_waterfall(scenarios[2], K)
    plot_comparison(scenarios_df, current_total)

    print("\n" + "=" * 70)
    print("PHASE 3 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
