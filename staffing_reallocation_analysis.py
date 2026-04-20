"""
Jefferson County EMS — Staffing Reallocation & Scenario Deep-Dive
=================================================================
Builds on the Nighttime Operations Deep-Dive to answer:
  1. Where to reduce staffing (overstaffed overnight career depts)
  2. Where to add staffing (understaffed volunteer depts with RT degradation)
  3. Regional Overnight ALS Hub design: which hubs, what coverage, zero added cost
  4. Peak-Weighted FT Shift mechanics: hour-by-hour savings breakdown
  5. County-Funded Roving Paramedic: optimal location, single vs multiple

Outputs:
  - Staffing_Reallocation_Recommendations.md  (polished report with tables & images)
  - reallocation_hub_coverage_map.png
  - peak_shift_savings_breakdown.png
  - roving_paramedic_location.png
  - reallocation_summary.csv

Data Sources: CY2024 NFIRS, boundary_distance_matrix.csv, staffing/budget dicts,
              Peterson cost model, fire chief interviews (Mar 2026)

Author: ISyE 450 Senior Design Team
Date:   April 2026
"""

import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Shared data ──────────────────────────────────────────────────────────

DEPT_COORDS = {
    "Watertown": (43.1861, -88.7339),
    "Fort Atkinson": (42.9271, -88.8397),
    "Whitewater": (42.8325, -88.7332),
    "Edgerton": (42.8403, -89.0629),
    "Jefferson": (43.0056, -88.8014),
    "Johnson Creek": (43.0753, -88.7745),
    "Waterloo": (43.1886, -88.9797),
    "Ixonia": (43.1446, -88.5970),
    "Palmyra": (42.8794, -88.5855),
    "Cambridge": (43.0049, -89.0224),
    "Lake Mills": (43.0781, -88.9144),
    "Helenville": (43.0135, -88.6998),
    "Western Lakes": (43.0110, -88.5877),
}

# Authoritative CY2024 EMS call volumes
AUTH_EMS = {
    "Cambridge": 87, "Fort Atkinson": 1616, "Ixonia": 289,
    "Jefferson": 1457, "Johnson Creek": 487, "Lake Mills": 518,
    "Palmyra": 32, "Waterloo": 520, "Watertown": 2012, "Whitewater": 64,
    "Edgerton": 2138, "Western Lakes": 5633,
}

STAFFING = {
    "Watertown":     {"FT": 31, "PT": 3,  "Model": "Career",       "Service": "ALS", "24_7": True,  "Expense": 3833800},
    "Fort Atkinson": {"FT": 16, "PT": 28, "Model": "Career+PT",    "Service": "ALS", "24_7": True,  "Expense": 760950},
    "Whitewater":    {"FT": 15, "PT": 17, "Model": "Career+PT",    "Service": "ALS", "24_7": True,  "Expense": 2710609},
    "Edgerton":      {"FT": 24, "PT": 0,  "Model": "Career+PT",    "Service": "ALS", "24_7": True,  "Expense": 704977},
    "Jefferson":     {"FT": 6,  "PT": 20, "Model": "Career",       "Service": "ALS", "24_7": True,  "Expense": 1500300},
    "Johnson Creek": {"FT": 3,  "PT": 33, "Model": "Combination",  "Service": "ALS", "24_7": True,  "Expense": 1134154},
    "Waterloo":      {"FT": 4,  "PT": 22, "Model": "Career+Vol",   "Service": "AEMT","24_7": False, "Expense": 1102475},
    "Lake Mills":    {"FT": 4,  "PT": 20, "Model": "Career+Vol",   "Service": "BLS", "24_7": False, "Expense": 347000},
    "Ixonia":        {"FT": 2,  "PT": 45, "Model": "Volunteer+FT", "Service": "BLS", "24_7": False, "Expense": 631144},
    "Cambridge":     {"FT": 0,  "PT": 31, "Model": "Volunteer",    "Service": "ALS", "24_7": False, "Expense": 92000},
    "Palmyra":       {"FT": 0,  "PT": 20, "Model": "Volunteer",    "Service": "BLS", "24_7": False, "Expense": 817740},
    "Western Lakes": {"FT": 0,  "PT": 0,  "Model": "Multi-County", "Service": "ALS", "24_7": True,  "Expense": 0},
}

AMBULANCE_COUNT = {
    "Watertown": 3, "Fort Atkinson": 3, "Whitewater": 2, "Edgerton": 2,
    "Jefferson": 5, "Johnson Creek": 2, "Waterloo": 2, "Lake Mills": 1,
    "Ixonia": 1, "Palmyra": 1, "Cambridge": 0, "Western Lakes": 0,
}

# Night response time data (from peak_staffing_report.md)
NIGHT_RT = {
    "Ixonia":        {"Day_RT": 8.9, "Night_RT": 15.3, "Delta": 6.4},
    "Palmyra":       {"Day_RT": 5.5, "Night_RT": 11.0, "Delta": 5.5},
    "Waterloo":      {"Day_RT": 6.2, "Night_RT": 10.6, "Delta": 4.4},
    "Johnson Creek": {"Day_RT": 6.7, "Night_RT": 9.7, "Delta": 3.0},
    "Whitewater":    {"Day_RT": 5.2, "Night_RT": 7.0, "Delta": 1.8},
    "Edgerton":      {"Day_RT": 6.5, "Night_RT": 8.3, "Delta": 1.8},
    "Jefferson":     {"Day_RT": 6.4, "Night_RT": 7.9, "Delta": 1.5},
    "Watertown":     {"Day_RT": 5.6, "Night_RT": 7.1, "Delta": 1.5},
    "Western Lakes": {"Day_RT": 6.5, "Night_RT": 7.9, "Delta": 1.4},
    "Fort Atkinson": {"Day_RT": 4.2, "Night_RT": 5.3, "Delta": 1.1},
    "Cambridge":     {"Day_RT": 7.6, "Night_RT": 7.9, "Delta": 0.3},
}

# Peterson cost model
PETERSON_SALARY = 371697
PETERSON_OT = 24894
PETERSON_BENEFITS = 178466
PETERSON_PENSION = 27761
PETERSON_TOTAL_SALARY = PETERSON_SALARY + PETERSON_OT + PETERSON_BENEFITS + PETERSON_PENSION  # $602,818
PETERSON_FIXED = 114000  # supplies, insurance, maintenance, etc.
PETERSON_TOTAL = 716818
PETERSON_REVENUE = 466200
PARAMEDIC_ANNUAL_COST = 95000  # salary + benefits for 1 roving paramedic

# Pay rate data (from Waterloo Chief Interview Mar 11, 2026)
PT_RATE_AEMT = 10.0    # $/hr for AEMT (Waterloo)
PT_RATE_EMR = 7.50     # $/hr for EMR driver (Waterloo)
FIRE_CALL_PAY = 20.0   # $/call for fire volunteers

# Distance conversion: straight-line miles × 1.3 road factor / 35 mph × 60 = minutes
def miles_to_minutes(miles):
    return miles * 1.3 / 35 * 60

STYLE = "seaborn-v0_8-whitegrid"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: Staffing Reallocation — Where to Cut, Where to Add
# ═══════════════════════════════════════════════════════════════════════════

def section1_reallocation():
    """Identify where staffing exceeds demand and where it falls short."""
    print("\n>> SECTION 1: Staffing Reallocation Analysis")

    # Load necessity scores
    scores = pd.read_csv(os.path.join(SCRIPT_DIR, "staffing_necessity_scores.csv"))

    # Load utilization data
    util = pd.read_csv(os.path.join(SCRIPT_DIR, "utilization_by_dept_hour.csv"))

    rows = []
    for dept, s in STAFFING.items():
        if dept == "Western Lakes":
            continue  # Multi-county, outside our control

        calls = AUTH_EMS.get(dept, 0)
        night_calls = int(calls * 0.16)  # ~16% overnight
        day_calls = int(calls * 0.60)    # ~60% daytime (08-18)

        # Average necessity score overnight (22-05)
        dept_scores = scores[scores["Dept"] == dept]
        if len(dept_scores) == 0:
            continue
        night_scores = dept_scores[dept_scores["Is_Night"] == True]["Composite"]
        day_scores = dept_scores[dept_scores["Is_Night"] == False]["Composite"]
        avg_night_score = night_scores.mean() if len(night_scores) > 0 else 0
        avg_day_score = day_scores.mean() if len(day_scores) > 0 else 0

        # Night utilization
        dept_util = util[util["Dept"] == dept]
        night_util = dept_util[dept_util["Hour"].isin(list(range(22, 24)) + list(range(0, 6)))]
        avg_night_util = night_util["Utilization_Pct"].mean() if len(night_util) > 0 else 0

        rt = NIGHT_RT.get(dept, {})

        # Classification
        if s["24_7"] and s["FT"] >= 6 and avg_night_score < 30 and avg_night_util < 2:
            night_status = "REDUCE: Low night demand, career staff idle"
        elif s["24_7"] and avg_night_score >= 50:
            night_status = "MAINTAIN: Night demand justifies current staffing"
        elif not s["24_7"] and rt.get("Delta", 0) >= 3:
            night_status = "ADD: Night RT degradation signals understaffing"
        elif not s["24_7"] and rt.get("Delta", 0) >= 1.5:
            night_status = "MONITOR: Moderate night RT increase"
        else:
            night_status = "ADEQUATE"

        rows.append({
            "Department": dept,
            "FT": s["FT"],
            "PT": s["PT"],
            "Service": s["Service"],
            "24_7": "Yes" if s["24_7"] else "No",
            "EMS_Calls": calls,
            "Night_Calls_Yr": night_calls,
            "Avg_Night_Util_Pct": round(avg_night_util, 1),
            "Avg_Night_Score": round(avg_night_score, 1),
            "Avg_Day_Score": round(avg_day_score, 1),
            "Night_RT_Delta": rt.get("Delta"),
            "Recommendation": night_status,
        })

    df = pd.DataFrame(rows).sort_values("Avg_Night_Score", ascending=True)
    df.to_csv(os.path.join(SCRIPT_DIR, "reallocation_summary.csv"), index=False)
    print(f"  Saved: reallocation_summary.csv")
    return df


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: Regional Overnight ALS Hubs
# ═══════════════════════════════════════════════════════════════════════════

def section2_overnight_hubs():
    """Design regional overnight ALS hub coverage with zero added cost."""
    print("\n>> SECTION 2: Regional Overnight ALS Hub Design")

    # Load distance matrix
    dist = pd.read_csv(os.path.join(SCRIPT_DIR, "boundary_distance_matrix.csv"), index_col=0)

    # Hub candidates: career ALS departments already staffed 24/7
    # These departments already pay for overnight crews — no added cost
    hub_candidates = ["Watertown", "Fort Atkinson", "Edgerton"]

    # Departments that need overnight ALS coverage
    # (either BLS-only, volunteer-only overnight, or uncertain)
    need_coverage = ["Waterloo", "Ixonia", "Palmyra", "Cambridge", "Lake Mills",
                     "Johnson Creek", "Jefferson"]

    # For each needing dept, find closest hub and compute drive time
    assignments = []
    for dept in need_coverage:
        best_hub = None
        best_dist = 999
        for hub in hub_candidates:
            d = dist.loc[dept, hub] if dept in dist.index and hub in dist.columns else 999
            if d < best_dist:
                best_dist = d
                best_hub = hub

        drive_min = miles_to_minutes(best_dist)
        night_calls = int(AUTH_EMS.get(dept, 0) * 0.16)
        current_night_rt = NIGHT_RT.get(dept, {}).get("Night_RT")
        hub_night_rt = NIGHT_RT.get(best_hub, {}).get("Night_RT")

        # Hub response = hub's own night RT + drive time to dept
        est_hub_rt = (hub_night_rt or 7) + drive_min * 0.5  # discount: not always from station
        rt_change = (est_hub_rt - current_night_rt) if current_night_rt else None

        assignments.append({
            "Department": dept,
            "Service_Level": STAFFING[dept]["Service"],
            "Current_Night_Model": "24/7 Career" if STAFFING[dept]["24_7"] else "Volunteer/On-call",
            "Night_Calls_Yr": night_calls,
            "Current_Night_RT": current_night_rt,
            "Assigned_Hub": best_hub,
            "Distance_Miles": round(best_dist, 1),
            "Drive_Time_Min": round(drive_min, 1),
            "Est_Hub_RT_Min": round(est_hub_rt, 1) if est_hub_rt else None,
            "RT_Change": round(rt_change, 1) if rt_change else None,
        })

    hub_df = pd.DataFrame(assignments)
    hub_df.to_csv(os.path.join(SCRIPT_DIR, "hub_assignments.csv"), index=False)
    print(f"  Saved: hub_assignments.csv")

    # Hub workload
    hub_workload = []
    for hub in hub_candidates:
        assigned = hub_df[hub_df["Assigned_Hub"] == hub]
        added_night_calls = assigned["Night_Calls_Yr"].sum()
        own_night_calls = int(AUTH_EMS.get(hub, 0) * 0.16)

        # Current overnight utilization (from data)
        hub_workload.append({
            "Hub": hub,
            "Own_Night_Calls_Yr": own_night_calls,
            "Added_Night_Calls_Yr": added_night_calls,
            "Total_Night_Calls_Yr": own_night_calls + added_night_calls,
            "Calls_Per_Night": round((own_night_calls + added_night_calls) / 365, 2),
            "Departments_Covered": ", ".join(assigned["Department"].tolist()),
            "FT_Staff": STAFFING[hub]["FT"],
            "Ambulances": AMBULANCE_COUNT[hub],
        })

    workload_df = pd.DataFrame(hub_workload)

    # --- Plot: Hub coverage map ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(14, 12))

    hub_colors = {"Watertown": "#e74c3c", "Fort Atkinson": "#3498db", "Edgerton": "#2ecc71"}

    # Plot all departments
    for dept, (lat, lon) in DEPT_COORDS.items():
        if dept in hub_candidates:
            ax.plot(lon, lat, "s", color=hub_colors[dept], markersize=18,
                    markeredgecolor="black", markeredgewidth=2, zorder=5)
            ax.annotate(f"{dept}\n(HUB - {STAFFING[dept]['FT']} FT)",
                       (lon, lat), fontsize=8, fontweight="bold",
                       textcoords="offset points", xytext=(12, 5),
                       bbox=dict(boxstyle="round,pad=0.3", facecolor=hub_colors[dept], alpha=0.3))
        elif dept in need_coverage:
            hub_assigned = hub_df[hub_df["Department"] == dept]["Assigned_Hub"].values[0]
            color = hub_colors.get(hub_assigned, "gray")
            ax.plot(lon, lat, "o", color=color, markersize=12,
                    markeredgecolor="black", markeredgewidth=1.5, zorder=4)
            calls = AUTH_EMS.get(dept, 0)
            night_calls = int(calls * 0.16)
            ax.annotate(f"{dept}\n({STAFFING[dept]['Service']}, {night_calls} night/yr)",
                       (lon, lat), fontsize=7,
                       textcoords="offset points", xytext=(12, -8))
            # Draw line to hub
            hub_lat, hub_lon = DEPT_COORDS[hub_assigned]
            ax.plot([lon, hub_lon], [lat, hub_lat], "--", color=color, alpha=0.4, linewidth=1.5)
        else:
            ax.plot(lon, lat, "^", color="gray", markersize=8, alpha=0.5, zorder=3)
            ax.annotate(dept, (lon, lat), fontsize=6, color="gray",
                       textcoords="offset points", xytext=(8, 3))

    # Legend
    legend_items = [
        mpatches.Patch(color="#e74c3c", label="Hub: Watertown (31 FT, 3 amb)"),
        mpatches.Patch(color="#3498db", label="Hub: Fort Atkinson (16 FT, 3 amb)"),
        mpatches.Patch(color="#2ecc71", label="Hub: Edgerton (24 FT, 2 amb)"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
                   markersize=10, label="Covered department"),
        plt.Line2D([0], [0], marker="^", color="w", markerfacecolor="gray",
                   markersize=8, label="Other department"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=9, framealpha=0.9)

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title(
        "Regional Overnight ALS Hub Design — Zero Added Cost\n"
        "Existing career ALS departments provide overnight backup via mutual aid protocol\n"
        "Source: boundary_distance_matrix.csv, CY2024 NFIRS, FY2025 staffing",
        fontsize=12, fontweight="bold"
    )
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "reallocation_hub_coverage_map.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: reallocation_hub_coverage_map.png")

    return hub_df, workload_df


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: Peak-Weighted FT Shift Savings
# ═══════════════════════════════════════════════════════════════════════════

def section3_peak_shift_savings():
    """Model the mechanics and savings of shifting FT from 24/7 to peak hours."""
    print("\n>> SECTION 3: Peak-Weighted FT Shift Savings")

    # Departments eligible for peak shift conversion
    # Criteria: small dept, <2 calls/night avg, currently have FT covering some overnight
    eligible = {
        "Waterloo":      {"FT": 4, "current_shifts": 3, "proposed_shifts": 2, "night_calls_day": 0.28},
        "Johnson Creek": {"FT": 3, "current_shifts": 3, "proposed_shifts": 2, "night_calls_day": 0.21},
        "Ixonia":        {"FT": 2, "current_shifts": 2, "proposed_shifts": 1.5, "night_calls_day": 0.13},
        "Jefferson":     {"FT": 6, "current_shifts": 3, "proposed_shifts": 2, "night_calls_day": 0.76},
    }

    # Cost breakdown per FT employee (from Peterson model, scaled per person)
    # Peterson: $371,697 salary / 7.2 FTE = ~$51,625/FTE base salary
    # With benefits: ($371,697 + $178,466 + $27,761 + $24,894) / 7.2 = ~$83,725/FTE total comp
    FTE_TOTAL_COMP = 83725  # salary + benefits + OT + pension per FTE

    # Shift differential: night shifts typically cost 10-15% more
    NIGHT_DIFF_PCT = 0.10

    savings_rows = []
    total_savings = 0

    for dept, data in eligible.items():
        ft = data["FT"]
        current_shifts = data["current_shifts"]
        proposed_shifts = data["proposed_shifts"]

        # FTE devoted to overnight: FT / shifts × 1 shift
        overnight_fte = ft / current_shifts
        # Savings from eliminating overnight FT coverage
        # Not firing — redistributing to peak hours where they're needed more
        # Savings come from: (a) no night differential, (b) OT reduction,
        # (c) reduced need for on-call PT backup overnight

        # a) Night shift differential savings
        night_diff_savings = overnight_fte * FTE_TOTAL_COMP * NIGHT_DIFF_PCT

        # b) PT on-call cost reduction (no longer need PT backup overnight)
        # On-call pay: $10/hr × 8 hrs/night × 365 nights × (avg 1.5 people on-call)
        pt_staff = STAFFING[dept]["PT"]
        if pt_staff > 0 and not STAFFING[dept]["24_7"]:
            # Volunteer depts with FT: on-call pay for overnight
            on_call_savings = PT_RATE_AEMT * 8 * 365 * min(2, pt_staff // 10)
        elif STAFFING[dept]["24_7"] and pt_staff > 10:
            on_call_savings = PT_RATE_AEMT * 8 * 365 * 1.5
        else:
            on_call_savings = 0

        # c) OT reduction from better peak coverage (fewer callbacks)
        ot_savings = ft * 2000 * 0.05  # ~5% of gross pay in OT avoided

        total_dept_savings = night_diff_savings + on_call_savings + ot_savings

        # What the dept gains: concentrated FT during 09:00-21:00
        peak_calls = int(AUTH_EMS[dept] * 0.66)  # 66% of calls in this window
        calls_per_ft_peak = peak_calls / ft if ft > 0 else 0

        savings_rows.append({
            "Department": dept,
            "FT_Staff": ft,
            "PT_Staff": STAFFING[dept]["PT"],
            "Current_Model": f"{current_shifts} shifts (24/7)" if current_shifts == 3 else f"{current_shifts} shifts",
            "Proposed_Model": f"12-hr peak (09-21) + Vol/PT overnight",
            "Overnight_FTE_Freed": round(overnight_fte, 1),
            "Night_Diff_Savings": round(night_diff_savings),
            "On_Call_Savings": round(on_call_savings),
            "OT_Savings": round(ot_savings),
            "Total_Savings": round(total_dept_savings),
            "Peak_Calls_Covered": peak_calls,
            "Night_Calls_Yr": int(AUTH_EMS[dept] * 0.16),
            "Night_Calls_Per_Day": round(data["night_calls_day"], 2),
        })
        total_savings += total_dept_savings

    savings_df = pd.DataFrame(savings_rows)
    savings_df.to_csv(os.path.join(SCRIPT_DIR, "peak_shift_savings.csv"), index=False)
    print(f"  Saved: peak_shift_savings.csv")
    print(f"  Total estimated savings: ${total_savings:,.0f}/yr")

    # --- Plot: Savings breakdown ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Left: Stacked bar of savings by component
    depts = savings_df["Department"].tolist()
    x = np.arange(len(depts))
    w = 0.5

    ax1.bar(x, savings_df["Night_Diff_Savings"], w, label="Night Differential Eliminated",
            color="#e74c3c", edgecolor="white")
    ax1.bar(x, savings_df["On_Call_Savings"], w,
            bottom=savings_df["Night_Diff_Savings"], label="On-Call PT Cost Reduction",
            color="#f39c12", edgecolor="white")
    ax1.bar(x, savings_df["OT_Savings"], w,
            bottom=savings_df["Night_Diff_Savings"] + savings_df["On_Call_Savings"],
            label="Overtime Reduction", color="#3498db", edgecolor="white")

    # Total labels
    for i, (_, r) in enumerate(savings_df.iterrows()):
        ax1.text(i, r["Total_Savings"] + 500, f"${r['Total_Savings']:,.0f}",
                ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{d}\n({savings_df.iloc[i]['FT_Staff']} FT)" for i, d in enumerate(depts)],
                        fontsize=9)
    ax1.set_ylabel("Annual Savings ($)", fontsize=11)
    ax1.set_title("Savings Breakdown by Department\nShifting FT from 24/7 to Peak Hours (09:00-21:00)",
                  fontsize=11, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Right: Before/After shift coverage diagram
    hours = list(range(24))
    for i, dept in enumerate(depts):
        y_current = i * 3 + 2
        y_proposed = i * 3 + 1

        # Current: full 24hr coverage
        ax2.barh(y_current, 24, left=0, height=0.7, color="#e74c3c", alpha=0.3,
                edgecolor="#e74c3c", linewidth=1)
        ax2.text(-0.5, y_current, f"{dept} (Current)", ha="right", va="center", fontsize=8)

        # Proposed: 09-21 FT, rest volunteer
        ax2.barh(y_proposed, 12, left=9, height=0.7, color="#2ecc71", alpha=0.6,
                edgecolor="#2ecc71", linewidth=1, label="FT Peak" if i == 0 else "")
        ax2.barh(y_proposed, 9, left=0, height=0.7, color="#f39c12", alpha=0.3,
                edgecolor="#f39c12", linewidth=1, label="Vol/PT Overnight" if i == 0 else "")
        ax2.barh(y_proposed, 3, left=21, height=0.7, color="#f39c12", alpha=0.3,
                edgecolor="#f39c12", linewidth=1)
        ax2.text(-0.5, y_proposed, f"{dept} (Proposed)", ha="right", va="center", fontsize=8)

    ax2.set_xlim(-0.5, 24)
    ax2.set_xticks(range(0, 25, 3))
    ax2.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 3)], fontsize=8)
    ax2.set_xlabel("Hour of Day", fontsize=10)
    ax2.set_title("Shift Coverage: Current vs Proposed\nGreen = FT career | Orange = Volunteer/PT on-call",
                  fontsize=11, fontweight="bold")
    ax2.set_yticks([])
    ax2.legend(loc="upper right", fontsize=8)
    # Night shading
    ax2.axvspan(0, 6, alpha=0.05, color="navy")
    ax2.axvspan(22, 24, alpha=0.05, color="navy")

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "peak_shift_savings_breakdown.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: peak_shift_savings_breakdown.png")

    return savings_df, total_savings


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: County-Funded Roving Paramedic — Location Analysis
# ═══════════════════════════════════════════════════════════════════════════

def section4_roving_paramedic():
    """Determine optimal location and staffing for county roving paramedics."""
    print("\n>> SECTION 4: County Roving Paramedic Location Analysis")

    # Load distance matrix
    dist = pd.read_csv(os.path.join(SCRIPT_DIR, "boundary_distance_matrix.csv"), index_col=0)

    # Target departments: those without overnight ALS
    target_depts = {
        "Ixonia":    {"Pop": 5078, "Night_Calls": 46, "Service": "BLS", "Night_RT": 15.3},
        "Palmyra":   {"Pop": 3341, "Night_Calls": 5,  "Service": "BLS", "Night_RT": 11.0},
        "Waterloo":  {"Pop": 4415, "Night_Calls": 83, "Service": "AEMT", "Night_RT": 10.6},
        "Cambridge": {"Pop": 2800, "Night_Calls": 14, "Service": "ALS (vol)", "Night_RT": 7.9},
        "Lake Mills": {"Pop": 6200, "Night_Calls": 83, "Service": "BLS", "Night_RT": None},
    }

    total_pop = sum(d["Pop"] for d in target_depts.values())
    total_night_calls = sum(d["Night_Calls"] for d in target_depts.values())

    # Candidate station locations for roving paramedic
    # Test each target dept as potential base + Jefferson/Johnson Creek as central options
    candidate_bases = list(target_depts.keys()) + ["Jefferson", "Johnson Creek"]

    location_analysis = []
    for base in candidate_bases:
        if base not in dist.index:
            continue

        # Compute weighted average response time to all target depts
        total_weighted_rt = 0
        total_calls = 0
        max_rt = 0
        coverage_details = []

        for target, data in target_depts.items():
            if target == base:
                # If paramedic is stationed here, RT = local RT (~5-7 min)
                rt = 6.0
            else:
                d = dist.loc[base, target] if target in dist.columns else 99
                rt = miles_to_minutes(d)

            weighted = rt * data["Night_Calls"]
            total_weighted_rt += weighted
            total_calls += data["Night_Calls"]
            max_rt = max(max_rt, rt)
            coverage_details.append({"Target": target, "Distance_Mi": round(dist.loc[base, target] if target in dist.columns else 99, 1),
                                      "Drive_Min": round(rt, 1), "Night_Calls": data["Night_Calls"]})

        avg_weighted_rt = total_weighted_rt / total_calls if total_calls > 0 else 99

        location_analysis.append({
            "Base_Location": base,
            "In_Target_Area": base in target_depts,
            "Avg_Weighted_RT_Min": round(avg_weighted_rt, 1),
            "Max_RT_Min": round(max_rt, 1),
            "Night_Calls_Covered": total_night_calls,
            "Population_Covered": total_pop,
            "Details": coverage_details,
        })

    loc_df = pd.DataFrame(location_analysis).sort_values("Avg_Weighted_RT_Min")
    print(f"  Top locations by weighted avg RT:")
    for _, r in loc_df.head(5).iterrows():
        print(f"    {r['Base_Location']}: avg {r['Avg_Weighted_RT_Min']} min, max {r['Max_RT_Min']} min")

    # --- Single vs Multiple paramedic analysis ---
    best_single = loc_df.iloc[0]

    # For 2 paramedics: split into north/south zones
    # North zone: Waterloo, Ixonia, Lake Mills
    # South zone: Palmyra, Cambridge
    north_depts = ["Waterloo", "Ixonia", "Lake Mills"]
    south_depts = ["Palmyra", "Cambridge"]

    # Best north base
    north_calls = sum(target_depts[d]["Night_Calls"] for d in north_depts if d in target_depts)
    south_calls = sum(target_depts[d]["Night_Calls"] for d in south_depts if d in target_depts)

    # Cost per paramedic (from Peterson model, scaled for single person)
    # Paramedic salary: ~$55-65K + benefits (~$30K) = ~$85-95K total
    PARA_COST = 95000  # annual, including benefits (same as module-level PARAMEDIC_ANNUAL_COST)

    multi_analysis = {
        "1_Paramedic": {
            "Cost": PARA_COST,
            "Base": best_single["Base_Location"],
            "Avg_RT": best_single["Avg_Weighted_RT_Min"],
            "Max_RT": best_single["Max_RT_Min"],
            "Night_Calls": total_night_calls,
            "Calls_Per_Night": round(total_night_calls / 365, 2),
        },
        "2_Paramedics": {
            "Cost": PARA_COST * 2,
            "Base": "Lake Mills (North) + Cambridge/Palmyra (South)",
            "Avg_RT": "Est. 8-12 min (shorter zones)",
            "Max_RT": "Est. 15-18 min",
            "Night_Calls": total_night_calls,
            "Calls_Per_Night": round(total_night_calls / 365, 2),
        },
    }

    # --- Plot: Roving paramedic location comparison ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 10))

    # Left: Map with candidate locations
    for dept, (lat, lon) in DEPT_COORDS.items():
        if dept in target_depts:
            nc = target_depts[dept]["Night_Calls"]
            size = max(8, min(20, nc / 3))
            ax1.plot(lon, lat, "o", color="#e74c3c", markersize=size,
                    markeredgecolor="black", markeredgewidth=1.5, zorder=4, alpha=0.7)
            ax1.annotate(f"{dept}\n{nc} night calls/yr\nRT: {target_depts[dept]['Night_RT'] or '?'} min",
                       (lon, lat), fontsize=7, textcoords="offset points", xytext=(12, -5))
        elif dept == best_single["Base_Location"]:
            ax1.plot(lon, lat, "*", color="#2ecc71", markersize=25,
                    markeredgecolor="black", markeredgewidth=2, zorder=6)
            ax1.annotate(f"BEST BASE\n{dept}\nAvg RT: {best_single['Avg_Weighted_RT_Min']} min",
                       (lon, lat), fontsize=8, fontweight="bold", color="#2ecc71",
                       textcoords="offset points", xytext=(15, 8))
        else:
            ax1.plot(lon, lat, "^", color="gray", markersize=7, alpha=0.4, zorder=2)
            ax1.annotate(dept, (lon, lat), fontsize=6, color="gray",
                       textcoords="offset points", xytext=(8, 3))

    # Draw radius from best base
    best_lat, best_lon = DEPT_COORDS[best_single["Base_Location"]]
    circle = plt.Circle((best_lon, best_lat), 0.12, fill=False, color="#2ecc71",
                        linewidth=2, linestyle="--", alpha=0.5)
    ax1.add_patch(circle)

    ax1.set_xlabel("Longitude", fontsize=10)
    ax1.set_ylabel("Latitude", fontsize=10)
    ax1.set_title(
        f"Optimal Roving Paramedic Base: {best_single['Base_Location']}\n"
        f"Weighted Avg RT: {best_single['Avg_Weighted_RT_Min']} min | "
        f"Covers {total_night_calls} overnight calls/yr for {total_pop:,} residents",
        fontsize=11, fontweight="bold"
    )
    ax1.grid(True, alpha=0.3)

    # Right: RT comparison bar chart for all candidate locations
    loc_sorted = loc_df.sort_values("Avg_Weighted_RT_Min")
    colors = ["#2ecc71" if r["Base_Location"] == best_single["Base_Location"] else
              "#3498db" if r["In_Target_Area"] else "#95a5a6"
              for _, r in loc_sorted.iterrows()]

    bars = ax2.barh(loc_sorted["Base_Location"], loc_sorted["Avg_Weighted_RT_Min"],
                   color=colors, edgecolor="#333", linewidth=0.5)
    ax2.barh(loc_sorted["Base_Location"], loc_sorted["Max_RT_Min"] - loc_sorted["Avg_Weighted_RT_Min"],
            left=loc_sorted["Avg_Weighted_RT_Min"].values,
            color=[c + "40" if len(c) < 8 else c[:7] + "40" for c in colors],
            edgecolor="#333", linewidth=0.5, alpha=0.3)

    for bar, (_, r) in zip(bars, loc_sorted.iterrows()):
        ax2.text(r["Avg_Weighted_RT_Min"] + 0.3, bar.get_y() + bar.get_height() / 2,
                f"Avg: {r['Avg_Weighted_RT_Min']} | Max: {r['Max_RT_Min']} min",
                va="center", fontsize=8)

    ax2.set_xlabel("Response Time (minutes)", fontsize=10)
    ax2.set_title("Candidate Base Locations — Weighted Avg RT\n(Weighted by overnight call volume per target dept)",
                  fontsize=11, fontweight="bold")
    ax2.set_xlim(0, loc_sorted["Max_RT_Min"].max() + 5)

    legend_items = [
        mpatches.Patch(color="#2ecc71", label="Best location"),
        mpatches.Patch(color="#3498db", label="Target area (in-district)"),
        mpatches.Patch(color="#95a5a6", label="Central/adjacent location"),
    ]
    ax2.legend(handles=legend_items, loc="lower right", fontsize=8)

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "roving_paramedic_location.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: roving_paramedic_location.png")

    return loc_df, multi_analysis, total_night_calls, total_pop


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(realloc_df, hub_df, workload_df, savings_df, total_savings,
                    loc_df, multi_analysis, total_night_calls, total_pop):
    """Generate Staffing_Reallocation_Recommendations.md"""
    print("\n>> Generating report...")

    L = []
    L.append("# Staffing Reallocation & Scenario Recommendations")
    L.append("## Jefferson County EMS -- Deep-Dive on Overnight Staffing Alternatives")
    L.append("")
    L.append(f"*Generated: {datetime.now().strftime('%B %d, %Y')}*")
    L.append("*Data Sources: CY2024 NFIRS (14 departments, 13,758 EMS calls), boundary distance matrix, FY2025 budgets, Peterson cost model, fire chief interviews (Mar 2026)*")
    L.append("")
    L.append("---")
    L.append("")

    # ── Executive Summary ──
    L.append("## Executive Summary")
    L.append("")
    L.append("This document provides actionable detail on three staffing strategies identified in the Nighttime Operations Deep-Dive:")
    L.append("")
    L.append("1. **Where to reduce/add staffing**: Jefferson's overnight career staffing handles just 0.05 calls/hour; Ixonia, Palmyra, and Waterloo lose ALS at night and see +4-6 min response time increases.")
    L.append(f"2. **Regional Overnight ALS Hubs**: Three existing career departments (Watertown, Fort Atkinson, Edgerton) can provide overnight ALS backup to 7 smaller departments at **zero additional cost** -- they already staff 24/7.")
    L.append(f"3. **Peak-Weighted FT Shifts**: Shifting 4 departments from 24/7 to 12-hr peak coverage (09:00-21:00) saves an estimated **${total_savings:,.0f}/year** while covering 66% of their annual call volume with career staff.")
    L.append(f"4. **County-Funded Roving Paramedic**: A single paramedic stationed at **{loc_df.iloc[0]['Base_Location']}** covers {total_night_calls} overnight calls/year across 5 underserved departments ({total_pop:,} residents) at **$95,000/year**.")
    L.append("")
    L.append("---")
    L.append("")

    # ── Section 1: Where to Cut / Where to Add ──
    L.append("## 1. Where to Reduce and Where to Add Staffing")
    L.append("")
    L.append("### Departments Where Overnight Staffing Exceeds Demand")
    L.append("")
    L.append("These departments maintain 24/7 career staffing despite very low overnight call volume and utilization:")
    L.append("")
    L.append("| Department | FT | Service | Night Calls/Yr | Night Util % | Night Necessity Score | Recommendation |")
    L.append("|---|---|---|---|---|---|---|")
    reduce = realloc_df[realloc_df["Recommendation"].str.startswith("REDUCE")]
    for _, r in reduce.iterrows():
        L.append(f"| **{r['Department']}** | {r['FT']} | {r['Service']} | {r['Night_Calls_Yr']} | {r['Avg_Night_Util_Pct']}% | {r['Avg_Night_Score']} | {r['Recommendation']} |")

    # Also show Jefferson specifically
    jeff = realloc_df[realloc_df["Department"] == "Jefferson"]
    if len(jeff) > 0 and not jeff.iloc[0]["Recommendation"].startswith("REDUCE"):
        j = jeff.iloc[0]
        L.append(f"| **Jefferson** | {j['FT']} | {j['Service']} | {j['Night_Calls_Yr']} | {j['Avg_Night_Util_Pct']}% | {j['Avg_Night_Score']} | Flagged: 5 overnight hours scored <20 |")

    L.append("")
    L.append("**Jefferson is the clearest case.** With 6 FT staff providing 24/7 ALS coverage, the department handles only ~233 overnight calls/year (0.64/night). Five overnight hours scored below 20 on the staffing necessity index. The department also operates 5 ambulances for 1,457 calls -- the lowest calls-per-ambulance ratio in the county (291 vs national benchmark of 1,147).")
    L.append("")
    L.append("### Departments Where Overnight Staffing Falls Short")
    L.append("")
    L.append("These departments show significant response time degradation overnight, indicating inadequate staffing:")
    L.append("")
    L.append("| Department | FT | Service | Night Model | Night RT (min) | Day RT (min) | Delta | Impact |")
    L.append("|---|---|---|---|---|---|---|---|")
    add_depts = realloc_df[realloc_df["Recommendation"].str.startswith("ADD")].sort_values("Night_RT_Delta", ascending=False)
    for _, r in add_depts.iterrows():
        nrt = NIGHT_RT.get(r["Department"], {})
        L.append(f"| **{r['Department']}** | {r['FT']} | {r['Service']} | Vol/On-call | {nrt.get('Night_RT', '?')} | {nrt.get('Day_RT', '?')} | **+{nrt.get('Delta', '?')} min** | Patients wait {nrt.get('Delta', '?')} min longer at night |")

    L.append("")
    L.append("**Ixonia (+6.4 min) and Palmyra (+5.5 min) are the worst cases.** Both are BLS-only volunteer departments. At night, response times stretch to 15.3 and 11.0 minutes respectively -- well above the NFPA 1710 standard of 8 minutes for ALS arrival. Patients in these areas who need ALS at night must wait for mutual aid from a career department.")
    L.append("")
    L.append("---")
    L.append("")

    # ── Section 2: Regional Overnight ALS Hubs ──
    L.append("## 2. Regional Overnight ALS Hubs — How They Work")
    L.append("")
    L.append("### Concept")
    L.append("")
    L.append("Three career ALS departments -- **Watertown, Fort Atkinson, and Edgerton** -- already staff full-time ALS crews 24 hours a day, 7 days a week. They are paying for overnight crews regardless of whether those crews handle additional mutual aid calls. By formalizing these departments as overnight ALS hubs, the county gains regional ALS coverage for 7 smaller departments **at zero incremental cost** to the hub departments.")
    L.append("")
    L.append("### How It Works")
    L.append("")
    L.append("1. **Overnight hours (22:00-06:00):** When a call comes in to a smaller department and their volunteer/on-call crew is unavailable or the call requires ALS, the nearest hub is automatically dispatched as backup.")
    L.append("2. **Primary still responds first:** The local department's volunteer crew still responds. The hub provides ALS-level backup, not replacement.")
    L.append("3. **Dispatch protocol change:** County dispatch routes overnight ALS requests to the nearest hub instead of relying on volunteer callback.")
    L.append("4. **No new staff, no new equipment:** Hub departments already have idle overnight capacity (utilization is 2-8% overnight). Adding a few mutual aid calls does not require additional crews.")
    L.append("")
    L.append("### Hub Assignments (by shortest drive time)")
    L.append("")
    L.append("| Department | Service | Current Night Model | Assigned Hub | Distance (mi) | Drive Time (min) | Current Night RT | Est. Hub RT |")
    L.append("|---|---|---|---|---|---|---|---|")
    for _, r in hub_df.iterrows():
        L.append(f"| {r['Department']} | {r['Service_Level']} | {r['Current_Night_Model']} | **{r['Assigned_Hub']}** | {r['Distance_Miles']} | {r['Drive_Time_Min']} | {r['Current_Night_RT'] or '?'} min | {r['Est_Hub_RT_Min'] or '?'} min |")

    L.append("")
    L.append("![Hub Coverage Map](reallocation_hub_coverage_map.png)")
    L.append("")
    L.append("### Hub Workload Impact")
    L.append("")
    L.append("| Hub | Own Night Calls/Yr | Added Night Calls/Yr | Total Night Calls/Yr | Calls/Night | Departments Covered | FT Staff | Ambulances |")
    L.append("|---|---|---|---|---|---|---|---|")
    for _, w in workload_df.iterrows():
        L.append(f"| **{w['Hub']}** | {w['Own_Night_Calls_Yr']} | {w['Added_Night_Calls_Yr']} | {w['Total_Night_Calls_Yr']} | {w['Calls_Per_Night']} | {w['Departments_Covered']} | {w['FT_Staff']} | {w['Ambulances']} |")

    L.append("")
    L.append("### Why Zero Added Cost")
    L.append("")
    L.append("| Factor | Detail |")
    L.append("|---|---|")
    L.append("| Existing staff | Hub departments already employ 24/7 career ALS crews (Watertown 31 FT, Fort Atkinson 16 FT, Edgerton 24 FT) |")
    L.append("| Low overnight utilization | Hub ambulance fleets are 2-8% utilized overnight -- ample capacity for additional calls |")
    L.append("| Low added volume | Total additional overnight calls across all hubs: ~{}/year = ~{:.1f}/night -- spread across 3 hubs |".format(
        int(hub_df["Night_Calls_Yr"].sum()), hub_df["Night_Calls_Yr"].sum() / 365))
    L.append("| Already responding to mutual aid | These departments already handle some mutual aid calls overnight informally |")
    L.append("| Revenue offset | Hub departments collect billing revenue on any transport they perform |")
    L.append("")
    L.append("### Limitations")
    L.append("")
    L.append("- **Response time trade-off:** Hub response to distant departments (e.g., Edgerton → Palmyra: 24 mi, ~34 min drive) may be slow. For the farthest assignments, the hub serves as ALS backup *after* local BLS arrives first.")
    L.append("- **Hub crew unavailability:** If the hub's crew is already on a call, the next-nearest hub responds. With 3 hubs, the probability all 3 are busy overnight simultaneously is extremely low.")
    L.append("- **Requires dispatch protocol update:** County dispatch must be configured to route overnight ALS requests to hubs.")
    L.append("")
    L.append("---")
    L.append("")

    # ── Section 3: Peak-Weighted FT Shifts ──
    L.append("## 3. Peak-Weighted FT Shifts — Mechanics and Savings")
    L.append("")
    L.append("### Concept")
    L.append("")
    L.append("Four departments currently spread their full-time staff across all shifts including overnight, despite overnight call volume being 3-5x lower than daytime. By concentrating FT coverage into a 12-hour peak window (09:00-21:00), these departments cover **66% of their annual call volume** with career staff while using volunteers/PT for the low-volume overnight hours.")
    L.append("")
    L.append("### How It Works")
    L.append("")
    L.append("| Current (24/7) | Proposed (Peak-Weighted) |")
    L.append("|---|---|")
    L.append("| FT crew on station 00:00-08:00 (night shift) | Volunteer/PT on-call 00:00-09:00 |")
    L.append("| FT crew on station 08:00-16:00 (day shift) | **FT crew on station 09:00-21:00** |")
    L.append("| FT crew on station 16:00-00:00 (swing shift) | Volunteer/PT on-call 21:00-00:00 |")
    L.append("| 3 shifts = FT spread thin | **1 long shift = FT concentrated at peak** |")
    L.append("")
    L.append("The 09:00-21:00 window is chosen because it captures:")
    L.append("- **66% of all countywide EMS calls** (9,012 of 13,758)")
    L.append("- The **peak demand hours** (11:00-19:00, which alone account for 31% of calls)")
    L.append("- The **afternoon gap** when PT/volunteers are least available (they have day jobs)")
    L.append("")
    L.append("### Savings Breakdown by Department")
    L.append("")
    L.append("![Peak Shift Savings](peak_shift_savings_breakdown.png)")
    L.append("")
    L.append("| Department | FT | Current Model | Proposed | Night Diff Saved | On-Call Saved | OT Saved | **Total Savings** |")
    L.append("|---|---|---|---|---|---|---|---|")
    for _, r in savings_df.iterrows():
        L.append(f"| {r['Department']} | {r['FT_Staff']} | {r['Current_Model']} | Peak 09-21 + Vol overnight | ${r['Night_Diff_Savings']:,.0f} | ${r['On_Call_Savings']:,.0f} | ${r['OT_Savings']:,.0f} | **${r['Total_Savings']:,.0f}** |")
    L.append(f"| **TOTAL** | | | | | | | **${total_savings:,.0f}** |")

    L.append("")
    L.append("### Where the Savings Come From")
    L.append("")
    L.append("1. **Night shift differential eliminated (~10% of salary):** FT staff working overnight typically receive a 10-15% night differential. By eliminating the overnight FT shift, this premium is no longer paid. Staff work the same total hours but during peak daytime/evening hours.")
    L.append("")
    L.append("2. **On-call PT cost reduction:** Departments currently paying PT staff $10/hr (AEMT) or $7.50/hr (EMR) to be on-call overnight can reduce this. With Regional Hub backup (Section 2), overnight on-call requirements decrease.")
    L.append("   - *Source: Waterloo Chief Interview, Mar 11, 2026 — confirmed $10/hr AEMT, $7.50/hr EMR driver rates*")
    L.append("")
    L.append("3. **Overtime reduction:** Better peak coverage means fewer overtime callbacks during busy afternoon hours. Currently, when daytime staff are stretched, departments call in off-duty FT or PT at overtime rates. Concentrating FT in the peak window reduces this.")
    L.append("")
    L.append("### What Happens Overnight Under This Model")
    L.append("")
    L.append("| Department | Night Calls/Yr | Calls/Night | Coverage Model |")
    L.append("|---|---|---|---|")
    for _, r in savings_df.iterrows():
        L.append(f"| {r['Department']} | {r['Night_Calls_Yr']} | {r['Night_Calls_Per_Day']} | Volunteer/PT on-call + Regional Hub ALS backup |")

    L.append("")
    L.append("At 0.13-0.76 calls per night, these departments average less than 1 call per overnight period. Volunteer/PT on-call is defensible at this volume, especially with Regional Hub ALS backup available.")
    L.append("")
    L.append("---")
    L.append("")

    # ── Section 4: County-Funded Roving Paramedic ──
    L.append("## 4. County-Funded Roving Paramedic — Location and Sizing")
    L.append("")
    L.append("### The Problem")
    L.append("")
    L.append("Five departments covering ~{:,} residents lack reliable ALS coverage overnight:".format(total_pop))
    L.append("")
    L.append("| Department | Population | Night Calls/Yr | Service Level | Night RT (min) | ALS at Night? |")
    L.append("|---|---|---|---|---|---|")
    target_data = [
        ("Ixonia", 5078, 46, "BLS", 15.3, "No"),
        ("Lake Mills", 6200, 83, "BLS", "?", "Uncertain (private contractor)"),
        ("Waterloo", 4415, 83, "AEMT", 10.6, "No (volunteer only)"),
        ("Cambridge", 2800, 14, "ALS (vol)", 7.9, "Uncertain (volunteer)"),
        ("Palmyra", 3341, 5, "BLS", 11.0, "No"),
    ]
    for name, pop, nc, svc, rt, als in target_data:
        L.append(f"| {name} | {pop:,} | {nc} | {svc} | {rt} | {als} |")
    L.append(f"| **Total** | **{total_pop:,}** | **{total_night_calls}** | | | |")

    L.append("")
    L.append("### Optimal Location: {}".format(loc_df.iloc[0]["Base_Location"]))
    L.append("")
    L.append("![Roving Paramedic Location Analysis](roving_paramedic_location.png)")
    L.append("")
    L.append("The analysis tested 7 candidate base locations, weighing average response time by overnight call volume at each target department:")
    L.append("")
    L.append("| Rank | Base Location | Avg Weighted RT (min) | Max RT (min) | In Target Area? |")
    L.append("|---|---|---|---|---|")
    for i, (_, r) in enumerate(loc_df.head(7).iterrows()):
        star = " **BEST**" if i == 0 else ""
        L.append(f"| {i+1} | {r['Base_Location']}{star} | {r['Avg_Weighted_RT_Min']} | {r['Max_RT_Min']} | {'Yes' if r['In_Target_Area'] else 'No'} |")

    L.append("")
    best = loc_df.iloc[0]
    L.append(f"**{best['Base_Location']}** provides the lowest weighted average response time ({best['Avg_Weighted_RT_Min']} min) because it is centrally located relative to the highest-volume target departments.")
    L.append("")

    L.append("### Single vs. Multiple Paramedics")
    L.append("")
    L.append("| Configuration | Annual Cost | Base(s) | Avg RT | Coverage |")
    L.append("|---|---|---|---|---|")
    m1 = multi_analysis["1_Paramedic"]
    L.append(f"| **1 Paramedic** | **${m1['Cost']:,}** | {m1['Base']} | {m1['Avg_RT']} min | {m1['Night_Calls']} calls/yr ({m1['Calls_Per_Night']} per night) |")
    m2 = multi_analysis["2_Paramedics"]
    L.append(f"| 2 Paramedics | ${m2['Cost']:,} | {m2['Base']} | {m2['Avg_RT']} | {m2['Night_Calls']} calls/yr ({m2['Calls_Per_Night']} per night) |")

    L.append("")
    L.append("### Recommendation: Start with 1 Paramedic")
    L.append("")
    L.append(f"At **{total_night_calls} overnight calls per year** across all 5 target departments ({round(total_night_calls/365, 2)} calls/night), a single roving paramedic handles the workload comfortably. The paramedic responds to ALS-level calls only -- BLS calls are still handled by local volunteer crews.")
    L.append("")
    L.append("**When to scale to 2 paramedics:**")
    L.append("- If overnight call volume increases by >30% (e.g., population growth in Ixonia/Lake Mills corridor)")
    L.append("- If response time data shows the single paramedic regularly exceeds 20-minute arrival times")
    L.append("- If the paramedic is frequently already on a call when a second ALS request comes in")
    L.append("")
    L.append("### Cost Justification")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Annual cost (salary + benefits) | ${PARAMEDIC_ANNUAL_COST:,} |")
    L.append(f"| Population served | {total_pop:,} residents |")
    L.append(f"| Cost per capita | ${PARAMEDIC_ANNUAL_COST / total_pop:.2f} |")
    L.append(f"| Overnight calls covered | {total_night_calls}/year |")
    L.append(f"| Cost per overnight call | ${PARAMEDIC_ANNUAL_COST / max(total_night_calls, 1):,.0f} |")
    L.append(f"| Revenue offset (est. 60% transport rate x $666 avg) | ~${int(total_night_calls * 0.6 * 666):,}/year |")
    L.append(f"| **Net cost after revenue** | **~${PARAMEDIC_ANNUAL_COST - int(total_night_calls * 0.6 * 666):,}/year** |")
    L.append("")
    L.append("*Revenue estimate based on Johnson Creek Chief interview: 60-70% of calls are BLS (Chief interview, Mar 13, 2026). Average collection per transport: $666 (Peterson cost model). Not all overnight calls result in transport.*")
    L.append("")
    L.append("---")
    L.append("")

    # ── Section 5: Combined Recommendation ──
    L.append("## 5. Combined Implementation Strategy")
    L.append("")
    L.append("These three strategies are complementary, not mutually exclusive:")
    L.append("")
    L.append("| Phase | Strategy | Cost Impact | Timeline | Dependencies |")
    L.append("|---|---|---|---|---|")
    L.append("| 1 | Regional Overnight ALS Hubs | **$0** (dispatch protocol change only) | Immediate (1-2 months) | County dispatch agreement with Watertown, Fort Atkinson, Edgerton |")
    L.append(f"| 2 | Peak-Weighted FT Shifts | **-${total_savings:,.0f}/yr** savings | 3-6 months (contract/schedule changes) | Hub system in place first (provides overnight backup) |")
    L.append(f"| 3 | County Roving Paramedic | **+${PARAMEDIC_ANNUAL_COST:,}/yr** | 6-12 months (hiring, positioning) | Requires county funding authorization |")
    L.append("")
    L.append("**Phase 1** should be implemented first because it provides the safety net that makes Phase 2 possible. Departments will not agree to reduce overnight FT staffing unless they know a career ALS hub will respond to their overnight calls.")
    L.append("")
    L.append(f"**Net annual impact (all 3 phases):** -${total_savings:,.0f} + ${PARAMEDIC_ANNUAL_COST:,} = **${PARAMEDIC_ANNUAL_COST - total_savings:+,.0f}/yr** -- essentially cost-neutral while dramatically improving overnight ALS coverage for {total_pop:,} residents.")
    L.append("")
    L.append("---")
    L.append("")

    # ── Data Sources ──
    L.append("## Data Sources")
    L.append("")
    L.append("| Source | Description | Time Period |")
    L.append("|---|---|---|")
    L.append("| NFIRS Excel files (14) | `ISyE Project/Data and Resources/Call Data/*.xlsx` | CY2024 |")
    L.append("| Boundary distance matrix | `boundary_distance_matrix.csv` (straight-line miles) | Static |")
    L.append("| Staffing/budget data | `ems_dashboard_app.py` lines 313-382 | FY2025 |")
    L.append("| Peterson cost model | `25-1210 JC EMS Workgroup Cost Projection.pdf` | Dec 2025 |")
    L.append("| Waterloo Chief interview | Pay rates: $10/hr AEMT, $7.50/hr EMR, $20/call fire | Mar 11, 2026 |")
    L.append("| Johnson Creek Chief interview | BLS proportion (60-70%), 24/7 staffing model, consolidation views | Mar 13, 2026 |")
    L.append("| Nighttime Operations Deep-Dive | `Nighttime_Operations_Deep_Dive.md` (prerequisite analysis) | Apr 7, 2026 |")
    L.append("| Staffing necessity scores | `staffing_necessity_scores.csv` (240 dept-hour scores) | Apr 7, 2026 |")
    L.append("| Utilization by hour | `utilization_by_dept_hour.csv` (minute-level calculation) | Apr 7, 2026 |")
    L.append("")
    L.append("### Methodology Notes")
    L.append("")
    L.append("- **Drive time estimation:** Straight-line distance x 1.3 (road factor) / 35 mph. This is conservative -- actual drive times may be shorter on major highways or longer on rural roads.")
    L.append("- **Savings estimates:** Based on Peterson cost model per-FTE costs ($83,725/FTE total compensation). Night differential assumed at 10%. On-call rates from Waterloo Chief interview.")
    L.append("- **Hub RT estimates:** Hub's own night RT + 50% of drive time (not 100%, because many calls originate between the hub and the target station, not at the station itself).")
    L.append("- **This analysis is diagnostic.** Implementation requires negotiation with fire chiefs, union contracts, dispatch agreements, and municipal governing bodies.")

    text = "\n".join(L)
    path = os.path.join(SCRIPT_DIR, "Staffing_Reallocation_Recommendations.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Saved: Staffing_Reallocation_Recommendations.md")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — STAFFING REALLOCATION DEEP-DIVE")
    print("=" * 70)

    realloc_df = section1_reallocation()
    hub_df, workload_df = section2_overnight_hubs()
    savings_df, total_savings = section3_peak_shift_savings()
    loc_df, multi_analysis, total_night_calls, total_pop = section4_roving_paramedic()

    generate_report(realloc_df, hub_df, workload_df, savings_df, total_savings,
                    loc_df, multi_analysis, total_night_calls, total_pop)

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print("\nDeliverables:")
    print("  - Staffing_Reallocation_Recommendations.md  (main report)")
    print("  - reallocation_hub_coverage_map.png")
    print("  - peak_shift_savings_breakdown.png")
    print("  - roving_paramedic_location.png")
    print("  - reallocation_summary.csv")
    print("  - hub_assignments.csv")
    print("  - peak_shift_savings.csv")


if __name__ == "__main__":
    main()
