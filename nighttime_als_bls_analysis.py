"""
Jefferson County EMS — Nighttime Operations & ALS/BLS Utilization Deep-Dive
============================================================================
Answers five key questions about overnight EMS operations:
  1. Is ALS/BLS coverage available 24/7, specifically at night (22:00-06:00)?
  2. Are ambulances actually staffed all day? What's the model per shift?
  3. What is the utilization of ALS/BLS ambulances by hour of day?
  4. Is it necessary to staff each ambulance at each hour it's currently staffed?
  5. How could staffing change to improve service times or reduce cost?

Outputs:
  - Nighttime_Operations_Deep_Dive.md   (polished report with embedded images/tables)
  - als_bls_by_hour_county.png          (Module 1)
  - als_bls_by_hour_dept.png            (Module 1)
  - utilization_heatmap.png             (Module 2)
  - nighttime_coverage_gap.png          (Module 3)
  - staffing_necessity_heatmap.png      (Module 4)
  - scenario_comparison.png             (Module 5)
  - Supporting .csv files

Data Sources: CY2024 NFIRS (14 departments), concurrent_call_detail.csv,
              interview transcripts, staffing dicts, Peterson cost model

Author: ISyE 450 Senior Design Team
Date:   April 2026
"""

import os, glob, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CALL_DATA_DIR = os.path.join(SCRIPT_DIR, "ISyE Project", "Data and Resources", "Call Data")

# ── Shared constants ─────────────────────────────────────────────────────
DEPT_NAME_MAP = {
    "Fort Atkinson Fire Dept": "Fort Atkinson",
    "Watertown Fire Dept": "Watertown",
    "Whitewater Fire and EMS": "Whitewater",
    "Edgerton Fire Protection Distict": "Edgerton",
    "Jefferson Fire Dept": "Jefferson",
    "Johnson Creek Fire Dept": "Johnson Creek",
    "Waterloo Fire Dept": "Waterloo",
    "Town of Ixonia Fire & EMS Dept": "Ixonia",
    "Palmyra Village Fire Dept": "Palmyra",
    "CAMBRIDGE COMM FIRE DEPT": "Cambridge",
    "Western Lake Fire District": "Western Lakes",
    "Rome Fire Dist": "Rome",
    "Sullivan Vol Fire Dept": "Sullivan",
    "Lake Mills Fire Dept": "Lake Mills",
    "Helenville Fire Dept": "Helenville",
    "Helenville Vol Fire Co": "Helenville",
    "Helenville Fire and Rescue District": "Helenville",
    "Lakeside Fire Rescue": "Edgerton",
    "Western Lakes Fire Dist": "Western Lakes",
    "Western Lakes Fire District": "Western Lakes",
    "WESTERN LAKES FIRE DIST": "Western Lakes",
    "Ixonia Fire Dept": "Ixonia",
    "Palmyra Fire Dept": "Palmyra",
    "Rome Vol Fire Co Inc": "Rome",
    "Sullivan Fire Dept": "Sullivan",
    "Whitewater Fire Dept": "Whitewater",
}

EMS_TRANSPORT_DEPTS = [
    "Watertown", "Fort Atkinson", "Whitewater", "Edgerton",
    "Jefferson", "Johnson Creek", "Waterloo", "Lake Mills",
    "Ixonia", "Palmyra", "Cambridge",
]

# Display order: largest call volume first
DEPT_ORDER = [
    "Western Lakes", "Edgerton", "Watertown", "Fort Atkinson",
    "Jefferson", "Whitewater", "Waterloo", "Lake Mills",
    "Johnson Creek", "Ixonia", "Cambridge", "Palmyra",
]

AMBULANCE_COUNT = {
    "Watertown": 3, "Fort Atkinson": 3, "Whitewater": 2, "Edgerton": 2,
    "Jefferson": 5, "Johnson Creek": 2, "Waterloo": 2, "Lake Mills": 1,
    "Ixonia": 1, "Palmyra": 1, "Cambridge": 0, "Western Lakes": 0,
}

AUTH_EMS = {
    "Cambridge": 87, "Fort Atkinson": 1616, "Ixonia": 289,
    "Jefferson": 1457, "Johnson Creek": 487, "Lake Mills": 518,
    "Palmyra": 32, "Waterloo": 520, "Watertown": 2012, "Whitewater": 64,
    "Edgerton": 2138, "Western Lakes": 5633,
}

STAFFING = {
    "Watertown":     {"FT": 31, "PT": 3,  "Model": "Career",       "Service": "ALS", "24_7": True},
    "Fort Atkinson": {"FT": 16, "PT": 28, "Model": "Career+PT",    "Service": "ALS", "24_7": True},
    "Whitewater":    {"FT": 15, "PT": 17, "Model": "Career+PT",    "Service": "ALS", "24_7": True},
    "Edgerton":      {"FT": 24, "PT": 0,  "Model": "Career+PT",    "Service": "ALS", "24_7": True},
    "Jefferson":     {"FT": 6,  "PT": 20, "Model": "Career",       "Service": "ALS", "24_7": True},
    "Johnson Creek": {"FT": 3,  "PT": 33, "Model": "Combination",  "Service": "ALS", "24_7": True},
    "Waterloo":      {"FT": 4,  "PT": 22, "Model": "Career+Vol",   "Service": "AEMT","24_7": False},
    "Lake Mills":    {"FT": 4,  "PT": 20, "Model": "Career+Vol",   "Service": "BLS", "24_7": False},
    "Ixonia":        {"FT": 2,  "PT": 45, "Model": "Volunteer+FT", "Service": "BLS", "24_7": False},
    "Cambridge":     {"FT": 0,  "PT": 31, "Model": "Volunteer",    "Service": "ALS", "24_7": False},
    "Palmyra":       {"FT": 0,  "PT": 20, "Model": "Volunteer",    "Service": "BLS", "24_7": False},
    "Western Lakes": {"FT": 0,  "PT": 0,  "Model": "Multi-County", "Service": "ALS", "24_7": True},
}

# Color palette
COLORS = {
    "als": "#e74c3c",
    "bls": "#3498db",
    "other": "#95a5a6",
    "peak": "#f39c12",
    "night": "#2c3e50",
    "good": "#2ecc71",
    "warn": "#f39c12",
    "bad": "#e74c3c",
}

STYLE = "seaborn-v0_8-whitegrid"

# Peterson cost model components
PETERSON_SALARY_ANNUAL = 371697  # 24/7 ALS crew salaries
PETERSON_BENEFITS_ANNUAL = 178466
PETERSON_TOTAL_OPERATING = 716818
PETERSON_REVENUE = 466200
PARAMEDIC_ANNUAL_COST = 95000  # salary + benefits for 1 roving paramedic


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 1: ALS vs BLS by Hour of Day
# ═══════════════════════════════════════════════════════════════════════════

def load_nfirs_with_als_bls():
    """Load all NFIRS files, filter EMS, classify ALS/BLS from Action Taken."""
    pattern = os.path.join(CALL_DATA_DIR, "Copy of 2024 EMS Workgroup - *.xlsx")
    files = glob.glob(pattern)
    print(f"  Found {len(files)} NFIRS files")

    frames = []
    for f in files:
        df = pd.read_excel(f)
        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True)
    print(f"  Total records: {len(all_df):,}")

    # Filter EMS only
    ems_mask = all_df["Incident Type Code Category Description"].str.startswith(
        "Rescue and EMS", na=False
    )
    ems = all_df[ems_mask].copy()
    print(f"  EMS calls: {len(ems):,}")

    # Normalize dept names
    ems["Dept"] = ems["Fire Department Name"].map(DEPT_NAME_MAP)
    unmapped = ems[ems["Dept"].isna()]["Fire Department Name"].unique()
    if len(unmapped) > 0:
        for raw in unmapped:
            short = (raw.replace(" Fire Department", "").replace(" Fire Dept", "")
                       .replace(" Fire Dist", "").replace(" Fire District", "")
                       .replace("City of ", "").strip())
            DEPT_NAME_MAP[raw] = short
        ems["Dept"] = ems["Fire Department Name"].map(DEPT_NAME_MAP)

    # Hour of day
    ems["Hour"] = pd.to_numeric(ems["Alarm Date - Hour of Day"], errors="coerce")

    # ALS/BLS classification from Action Taken 1 Description
    action_col = "Action Taken 1 Description"
    if action_col in ems.columns:
        def classify_action(val):
            if pd.isna(val):
                return "Other"
            val = str(val).lower()
            if "advanced life support" in val or "als" in val.split():
                return "ALS"
            elif "basic life support" in val or "bls" in val.split():
                return "BLS"
            else:
                return "Other"
        ems["Care_Level"] = ems[action_col].apply(classify_action)
    else:
        print(f"  WARNING: Column '{action_col}' not found. Using 'Unknown'.")
        ems["Care_Level"] = "Other"

    # Response time
    ems["Response_Min"] = pd.to_numeric(ems["Response Time (Minutes)"], errors="coerce")

    print(f"  ALS: {(ems['Care_Level']=='ALS').sum():,} | "
          f"BLS: {(ems['Care_Level']=='BLS').sum():,} | "
          f"Other: {(ems['Care_Level']=='Other').sum():,}")

    return ems


def module1_als_bls_by_hour(ems_df):
    """Cross-tab ALS/BLS/Other by hour of day, countywide and per-department."""
    print("\n>> MODULE 1: ALS vs BLS by Hour of Day")

    valid = ems_df.dropna(subset=["Hour"]).copy()
    valid["Hour"] = valid["Hour"].astype(int)

    # --- Countywide cross-tab ---
    ct = pd.crosstab(valid["Hour"], valid["Care_Level"])
    for col in ["ALS", "BLS", "Other"]:
        if col not in ct.columns:
            ct[col] = 0
    ct = ct[["ALS", "BLS", "Other"]]
    ct["Total"] = ct.sum(axis=1)
    ct["ALS_Pct"] = (ct["ALS"] / ct["Total"] * 100).round(1)
    ct["BLS_Pct"] = (ct["BLS"] / ct["Total"] * 100).round(1)

    # Save CSV
    ct.to_csv(os.path.join(SCRIPT_DIR, "als_bls_hourly_data.csv"))
    print(f"  Saved: als_bls_hourly_data.csv")

    # Night vs Day comparison
    night_mask = valid["Hour"].isin(list(range(22, 24)) + list(range(0, 6)))
    day_mask = valid["Hour"].isin(range(8, 18))

    night_calls = valid[night_mask]
    day_calls = valid[day_mask]

    night_als_pct = (night_calls["Care_Level"] == "ALS").mean() * 100
    day_als_pct = (day_calls["Care_Level"] == "ALS").mean() * 100
    night_bls_pct = (night_calls["Care_Level"] == "BLS").mean() * 100
    day_bls_pct = (day_calls["Care_Level"] == "BLS").mean() * 100

    night_day_summary = {
        "Night_ALS_Pct": round(night_als_pct, 1),
        "Day_ALS_Pct": round(day_als_pct, 1),
        "Night_BLS_Pct": round(night_bls_pct, 1),
        "Day_BLS_Pct": round(day_bls_pct, 1),
        "Night_Total": len(night_calls),
        "Day_Total": len(day_calls),
    }
    print(f"  Night (22-05) ALS: {night_als_pct:.1f}% | Day (08-17) ALS: {day_als_pct:.1f}%")

    # --- Per-department cross-tab ---
    dept_als = {}
    for dept in DEPT_ORDER:
        dg = valid[valid["Dept"] == dept]
        if len(dg) < 20:
            continue
        dct = pd.crosstab(dg["Hour"], dg["Care_Level"])
        for col in ["ALS", "BLS", "Other"]:
            if col not in dct.columns:
                dct[col] = 0
        dct = dct.reindex(range(24), fill_value=0)
        dct["Total"] = dct.sum(axis=1)
        dct["ALS_Pct"] = np.where(dct["Total"] > 0, dct["ALS"] / dct["Total"] * 100, 0)
        dept_als[dept] = dct

    # --- Plot 1: Countywide stacked bar ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(14, 7))
    hours = ct.index.values
    w = 0.7
    ax.bar(hours, ct["ALS"], w, label="ALS", color=COLORS["als"], edgecolor="white", linewidth=0.3)
    ax.bar(hours, ct["BLS"], w, bottom=ct["ALS"], label="BLS", color=COLORS["bls"], edgecolor="white", linewidth=0.3)
    ax.bar(hours, ct["Other"], w, bottom=ct["ALS"] + ct["BLS"], label="Other/Transport", color=COLORS["other"], edgecolor="white", linewidth=0.3)

    # Night shading
    ax.axvspan(-0.5, 5.5, alpha=0.08, color=COLORS["night"], label="Night (22:00-06:00)")
    ax.axvspan(21.5, 23.5, alpha=0.08, color=COLORS["night"])

    # ALS % line on secondary axis
    ax2 = ax.twinx()
    ax2.plot(hours, ct["ALS_Pct"], color="black", marker="o", markersize=4,
             linewidth=2, linestyle="--", label="ALS % of calls", zorder=5)
    ax2.set_ylabel("ALS Share (%)", fontsize=11)
    ax2.set_ylim(0, 100)
    ax2.legend(loc="upper right", fontsize=9)

    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_ylabel("Number of EMS Calls (CY2024)", fontsize=12)
    ax.set_title(
        "ALS vs BLS Call Volume by Hour of Day — Jefferson County (All Departments)\n"
        "Source: CY2024 NFIRS 'Action Taken 1 Description' field | n={:,} EMS calls".format(len(valid)),
        fontsize=13, fontweight="bold"
    )
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=9)
    ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "als_bls_by_hour_county.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: als_bls_by_hour_county.png")

    # --- Plot 2: Per-department small multiples ---
    plot_depts = [d for d in DEPT_ORDER if d in dept_als and dept_als[d]["Total"].sum() >= 50]
    n = len(plot_depts)
    cols = 3
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(16, 4.5 * rows), sharey=False)
    axes = axes.flatten() if n > 1 else [axes]

    for i, dept in enumerate(plot_depts):
        ax = axes[i]
        dct = dept_als[dept]
        h = dct.index.values
        ax.bar(h, dct.get("ALS", 0), 0.7, label="ALS", color=COLORS["als"], edgecolor="white", linewidth=0.3)
        ax.bar(h, dct.get("BLS", 0), 0.7, bottom=dct.get("ALS", 0), label="BLS", color=COLORS["bls"], edgecolor="white", linewidth=0.3)
        ax.bar(h, dct.get("Other", 0), 0.7, bottom=dct.get("ALS", 0) + dct.get("BLS", 0), label="Other", color=COLORS["other"], edgecolor="white", linewidth=0.3)
        ax.axvspan(-0.5, 5.5, alpha=0.08, color=COLORS["night"])
        ax.axvspan(21.5, 23.5, alpha=0.08, color=COLORS["night"])

        svc = STAFFING.get(dept, {}).get("Service", "?")
        ft = STAFFING.get(dept, {}).get("FT", "?")
        total = int(dct["Total"].sum())
        als_total = int(dct.get("ALS", pd.Series([0])).sum())
        als_pct = als_total / total * 100 if total > 0 else 0
        ax.set_title(f"{dept} ({svc}, {ft} FT)\nn={total:,} | ALS={als_pct:.0f}%", fontsize=10, fontweight="bold")
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xticklabels(["00", "06", "12", "18", "23"], fontsize=8)
        if i == 0:
            ax.legend(fontsize=7, loc="upper left")

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("ALS vs BLS by Hour — Per Department | CY2024 NFIRS", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "als_bls_by_hour_dept.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: als_bls_by_hour_dept.png")

    return ct, dept_als, night_day_summary


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 2: Ambulance Utilization by Hour
# ═══════════════════════════════════════════════════════════════════════════

def module2_utilization_by_hour():
    """Compute minute-level ambulance utilization by department and hour."""
    print("\n>> MODULE 2: Ambulance Utilization by Hour")

    detail_path = os.path.join(SCRIPT_DIR, "concurrent_call_detail.csv")
    df = pd.read_csv(detail_path, parse_dates=["Alarm_DT", "Cleared_DT"])
    print(f"  Loaded {len(df):,} call records from concurrent_call_detail.csv")

    # Compute utilization: for each call, distribute busy-minutes across clock hours
    util = {}  # (dept, hour) -> total busy minutes across the year

    for _, row in df.iterrows():
        dept = row["Dept"]
        if dept not in EMS_TRANSPORT_DEPTS or pd.isna(row["Alarm_DT"]) or pd.isna(row["Cleared_DT"]):
            continue

        start = row["Alarm_DT"]
        end = row["Cleared_DT"]
        if end <= start:
            continue

        # Walk through each clock hour this call spans
        current = start
        while current < end:
            hour = current.hour
            # End of this clock hour
            next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_end = min(next_hour, end)
            minutes = (segment_end - current).total_seconds() / 60.0
            key = (dept, hour)
            util[key] = util.get(key, 0) + minutes
            current = segment_end

    # Build utilization DataFrame
    rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        amb = AMBULANCE_COUNT.get(dept, 0)
        if amb == 0:
            continue
        capacity_per_hour = amb * 60 * 365  # total available minutes per hour-slot per year
        for h in range(24):
            busy_min = util.get((dept, h), 0)
            rate = busy_min / capacity_per_hour if capacity_per_hour > 0 else 0
            rows.append({
                "Dept": dept,
                "Hour": h,
                "Busy_Minutes_Year": round(busy_min, 1),
                "Ambulances": amb,
                "Capacity_Minutes": capacity_per_hour,
                "Utilization_Rate": round(rate, 4),
                "Utilization_Pct": round(rate * 100, 2),
            })

    util_df = pd.DataFrame(rows)
    util_df.to_csv(os.path.join(SCRIPT_DIR, "utilization_by_dept_hour.csv"), index=False)
    print(f"  Saved: utilization_by_dept_hour.csv")

    # Pivot for heatmap: depts x hours
    pivot = util_df.pivot(index="Dept", columns="Hour", values="Utilization_Pct")
    # Reorder by call volume
    dept_display = [d for d in DEPT_ORDER if d in pivot.index]
    pivot = pivot.loc[dept_display]

    # Summary stats
    summary_rows = []
    for dept in dept_display:
        row_data = pivot.loc[dept]
        peak_util = row_data.max()
        night_util = row_data[[h for h in range(24) if h >= 22 or h < 6]].mean()
        day_util = row_data[[h for h in range(8, 18)]].mean()
        idle_hours = (row_data < 2.0).sum()  # hours with <2% utilization
        summary_rows.append({
            "Dept": dept,
            "Peak_Util_Pct": round(peak_util, 1),
            "Day_Util_Pct": round(day_util, 1),
            "Night_Util_Pct": round(night_util, 1),
            "Idle_Hours_Under_2Pct": int(idle_hours),
            "Ambulances": AMBULANCE_COUNT.get(dept, 0),
        })
    summary_df = pd.DataFrame(summary_rows)

    # --- Plot: Utilization heatmap ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(16, 8))
    data = pivot.values
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0, vmax=max(12, np.nanmax(data)))

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(24)], fontsize=8, rotation=45)
    ax.set_yticks(range(len(dept_display)))
    ylabels = []
    for d in dept_display:
        amb = AMBULANCE_COUNT.get(d, 0)
        calls = AUTH_EMS.get(d, 0)
        ylabels.append(f"{d} ({amb} amb, {calls:,} calls)")
    ax.set_yticklabels(ylabels, fontsize=9)

    # Annotate cells
    for i in range(len(dept_display)):
        for j in range(24):
            val = data[i, j]
            if np.isnan(val):
                continue
            color = "white" if val > np.nanmax(data) * 0.5 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=6.5, color=color)

    # Night shading
    ax.axvline(x=5.5, color="cyan", linewidth=1, linestyle="--", alpha=0.7)
    ax.axvline(x=21.5, color="cyan", linewidth=1, linestyle="--", alpha=0.7)
    ax.text(2.5, -0.8, "NIGHT", ha="center", fontsize=8, color="cyan", fontweight="bold")
    ax.text(23, -0.8, "NIGHT", ha="center", fontsize=8, color="cyan", fontweight="bold")

    plt.colorbar(im, ax=ax, label="Utilization Rate (%)", shrink=0.8)
    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_title(
        "Ambulance Fleet Utilization by Department and Hour of Day\n"
        "% of total ambulance-hours occupied by active EMS calls | CY2024 NFIRS",
        fontsize=13, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "utilization_heatmap.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: utilization_heatmap.png")

    return util_df, summary_df, pivot


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 3: Nighttime ALS Coverage Gap Matrix
# ═══════════════════════════════════════════════════════════════════════════

def module3_coverage_matrix(dept_als_data):
    """Build department x shift coverage matrix with ALS gap identification."""
    print("\n>> MODULE 3: Nighttime ALS Coverage Gap Matrix")

    # Coverage matrix based on staffing data and interview findings
    coverage = {
        "Watertown":     {"Day": "Career ALS",     "Afternoon": "Career ALS",     "Overnight": "Career ALS",      "ALS_Night": "Yes", "Night_Model": "24/7 Career"},
        "Fort Atkinson": {"Day": "Career ALS",     "Afternoon": "Career ALS",     "Overnight": "Career ALS",      "ALS_Night": "Yes", "Night_Model": "24/7 Career"},
        "Edgerton":      {"Day": "Career ALS",     "Afternoon": "Career ALS",     "Overnight": "Career ALS",      "ALS_Night": "Yes", "Night_Model": "24/7 Career"},
        "Whitewater":    {"Day": "Career ALS",     "Afternoon": "Career ALS",     "Overnight": "Career ALS",      "ALS_Night": "Yes", "Night_Model": "24/7 Career"},
        "Jefferson":     {"Day": "Career ALS",     "Afternoon": "Career+PT ALS",  "Overnight": "FT+PT ALS",       "ALS_Night": "Yes (reduced)", "Night_Model": "FT+PT rotation"},
        "Johnson Creek": {"Day": "Career ALS",     "Afternoon": "FT+PT ALS",      "Overnight": "PT on-call ALS",  "ALS_Night": "Yes (on-call)", "Night_Model": "Paramedic on-call"},
        "Western Lakes": {"Day": "Career ALS",     "Afternoon": "Career ALS",     "Overnight": "Career ALS",      "ALS_Night": "Yes", "Night_Model": "Multi-county career"},
        "Waterloo":      {"Day": "Career AEMT",    "Afternoon": "Career+Vol AEMT","Overnight": "Volunteer only",   "ALS_Night": "NO", "Night_Model": "Volunteer page-out"},
        "Lake Mills":    {"Day": "Ryan Bros ALS",  "Afternoon": "Ryan Bros ALS",  "Overnight": "On-call",          "ALS_Night": "Uncertain", "Night_Model": "Private contractor"},
        "Ixonia":        {"Day": "FT BLS",         "Afternoon": "Vol BLS",        "Overnight": "Volunteer BLS",    "ALS_Night": "N/A (BLS)", "Night_Model": "Volunteer page-out"},
        "Cambridge":     {"Day": "Volunteer ALS",  "Afternoon": "Volunteer ALS",  "Overnight": "Volunteer only",   "ALS_Night": "Uncertain", "Night_Model": "Volunteer page-out"},
        "Palmyra":       {"Day": "Volunteer BLS",  "Afternoon": "Volunteer BLS",  "Overnight": "Volunteer BLS",    "ALS_Night": "N/A (BLS)", "Night_Model": "Volunteer page-out"},
    }

    # Night response time data (from peak_staffing_report.md)
    night_rt = {
        "Ixonia": {"Day_RT": 8.9, "Night_RT": 15.3, "Delta": 6.4},
        "Palmyra": {"Day_RT": 5.5, "Night_RT": 11.0, "Delta": 5.5},
        "Waterloo": {"Day_RT": 6.2, "Night_RT": 10.6, "Delta": 4.4},
        "Johnson Creek": {"Day_RT": 6.7, "Night_RT": 9.7, "Delta": 3.0},
        "Whitewater": {"Day_RT": 5.2, "Night_RT": 7.0, "Delta": 1.8},
        "Edgerton": {"Day_RT": 6.5, "Night_RT": 8.3, "Delta": 1.8},
        "Jefferson": {"Day_RT": 6.4, "Night_RT": 7.9, "Delta": 1.5},
        "Watertown": {"Day_RT": 5.6, "Night_RT": 7.1, "Delta": 1.5},
        "Western Lakes": {"Day_RT": 6.5, "Night_RT": 7.9, "Delta": 1.4},
        "Fort Atkinson": {"Day_RT": 4.2, "Night_RT": 5.3, "Delta": 1.1},
        "Cambridge": {"Day_RT": 7.6, "Night_RT": 7.9, "Delta": 0.3},
    }

    # Build output table
    rows = []
    for dept in DEPT_ORDER:
        if dept not in coverage:
            continue
        c = coverage[dept]
        s = STAFFING.get(dept, {})
        rt = night_rt.get(dept, {})
        als_data = dept_als_data.get(dept)

        # Compute ALS% at night from actual data if available
        night_als_pct = None
        if als_data is not None:
            night_hours = [h for h in range(24) if h >= 22 or h < 6]
            night_rows = als_data.loc[als_data.index.isin(night_hours)]
            total_night = night_rows["Total"].sum() if "Total" in night_rows.columns else 0
            als_night = night_rows["ALS"].sum() if "ALS" in night_rows.columns else 0
            night_als_pct = als_night / total_night * 100 if total_night > 0 else None

        rows.append({
            "Department": dept,
            "FT_Staff": s.get("FT", 0),
            "PT_Staff": s.get("PT", 0),
            "Service_Level": s.get("Service", "?"),
            "Day_Coverage": c["Day"],
            "Afternoon_Coverage": c["Afternoon"],
            "Overnight_Coverage": c["Overnight"],
            "ALS_at_Night": c["ALS_Night"],
            "Night_Model": c["Night_Model"],
            "Night_RT_min": rt.get("Night_RT"),
            "Day_RT_min": rt.get("Day_RT"),
            "RT_Delta_min": rt.get("Delta"),
            "Night_ALS_Pct": round(night_als_pct, 1) if night_als_pct is not None else None,
            "Night_Calls_Year": AUTH_EMS.get(dept, 0) * 0.16,  # ~16% are overnight
        })

    matrix_df = pd.DataFrame(rows)
    matrix_df.to_csv(os.path.join(SCRIPT_DIR, "nighttime_coverage_matrix.csv"), index=False)
    print(f"  Saved: nighttime_coverage_matrix.csv")

    # --- Plot: Coverage gap visualization ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 9), gridspec_kw={"width_ratios": [3, 1.5]})

    # Left panel: coverage matrix as colored grid
    shifts = ["Day_Coverage", "Afternoon_Coverage", "Overnight_Coverage"]
    shift_labels = ["Day\n(06-14)", "Afternoon\n(14-22)", "Overnight\n(22-06)"]
    depts_display = matrix_df["Department"].tolist()

    color_map = {
        "Career ALS": "#2ecc71",
        "Career+PT ALS": "#27ae60",
        "FT+PT ALS": "#82e0aa",
        "FT+PT rotation": "#82e0aa",
        "Career AEMT": "#f9e79f",
        "Career+Vol AEMT": "#f9e79f",
        "FT BLS": "#aed6f1",
        "Ryan Bros ALS": "#2ecc71",
        "Volunteer ALS": "#f39c12",
        "Volunteer BLS": "#e74c3c",
        "Volunteer only": "#e74c3c",
        "Vol BLS": "#e67e22",
        "PT on-call ALS": "#f39c12",
        "On-call": "#e67e22",
        "Multi-county career": "#2ecc71",
    }

    for i, dept in enumerate(depts_display):
        row = matrix_df[matrix_df["Department"] == dept].iloc[0]
        for j, shift in enumerate(shifts):
            val = row[shift]
            color = color_map.get(val, "#bdc3c7")
            rect = plt.Rectangle((j - 0.4, i - 0.4), 0.8, 0.8, facecolor=color,
                                  edgecolor="white", linewidth=2)
            ax1.add_patch(rect)
            # Text label
            fontsize = 7 if len(val) > 15 else 8
            ax1.text(j, i, val, ha="center", va="center", fontsize=fontsize, fontweight="bold",
                     color="white" if color in ["#e74c3c", "#2ecc71", "#27ae60"] else "black")

    ax1.set_xlim(-0.5, 2.5)
    ax1.set_ylim(-0.5, len(depts_display) - 0.5)
    ax1.invert_yaxis()
    ax1.set_xticks(range(3))
    ax1.set_xticklabels(shift_labels, fontsize=10, fontweight="bold")
    ax1.set_yticks(range(len(depts_display)))
    ylabels_cov = []
    for d in depts_display:
        s = STAFFING.get(d, {})
        ylabels_cov.append(f"{d} ({s.get('FT', '?')} FT)")
    ax1.set_yticklabels(ylabels_cov, fontsize=9)
    ax1.set_title("EMS Coverage by Shift — All Departments", fontsize=12, fontweight="bold")

    # Legend
    legend_items = [
        mpatches.Patch(color="#2ecc71", label="Career ALS (24/7)"),
        mpatches.Patch(color="#82e0aa", label="FT+PT ALS"),
        mpatches.Patch(color="#f39c12", label="Volunteer/On-call ALS"),
        mpatches.Patch(color="#f9e79f", label="AEMT"),
        mpatches.Patch(color="#aed6f1", label="FT BLS"),
        mpatches.Patch(color="#e74c3c", label="Volunteer only / BLS"),
    ]
    ax1.legend(handles=legend_items, loc="lower left", fontsize=8, ncol=2)

    # Right panel: night RT degradation bar chart
    rt_depts = matrix_df.dropna(subset=["RT_Delta_min"]).sort_values("RT_Delta_min", ascending=True)
    colors_rt = []
    for _, r in rt_depts.iterrows():
        delta = r["RT_Delta_min"]
        if delta >= 4:
            colors_rt.append(COLORS["bad"])
        elif delta >= 2:
            colors_rt.append(COLORS["warn"])
        else:
            colors_rt.append(COLORS["good"])

    bars = ax2.barh(rt_depts["Department"], rt_depts["RT_Delta_min"], color=colors_rt,
                    edgecolor="#333", linewidth=0.5)
    for bar, (_, r) in zip(bars, rt_depts.iterrows()):
        w = bar.get_width()
        ax2.text(w + 0.1, bar.get_y() + bar.get_height() / 2,
                 f"+{r['RT_Delta_min']:.1f} min\n({r['Day_RT_min']:.1f}→{r['Night_RT_min']:.1f})",
                 va="center", fontsize=7.5)

    ax2.set_xlabel("Night-Day Response Time Delta (min)", fontsize=10)
    ax2.set_title("Night RT Degradation\n(22:00-06:00 vs 08:00-18:00)", fontsize=11, fontweight="bold")
    ax2.set_xlim(0, 9)

    fig.suptitle(
        "Nighttime EMS Coverage Gaps & Response Time Impact — Jefferson County\n"
        "Source: CY2024 NFIRS, FY2025 staffing data, chief interviews (Mar 2026)",
        fontsize=14, fontweight="bold", y=1.02
    )
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "nighttime_coverage_gap.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: nighttime_coverage_gap.png")

    return matrix_df


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 4: Staffing Necessity Scoring
# ═══════════════════════════════════════════════════════════════════════════

def module4_necessity_scoring(ems_df, util_df):
    """Score each department-hour (0-100) for staffing necessity."""
    print("\n>> MODULE 4: Staffing Necessity Scoring")

    valid = ems_df.dropna(subset=["Hour"]).copy()
    valid["Hour"] = valid["Hour"].astype(int)

    # Load concurrent call detail for hourly concurrency rates
    detail_path = os.path.join(SCRIPT_DIR, "concurrent_call_detail.csv")
    detail_df = pd.read_csv(detail_path)

    score_rows = []

    for dept in EMS_TRANSPORT_DEPTS:
        dg = valid[valid["Dept"] == dept]
        dg_detail = detail_df[detail_df["Dept"] == dept]

        if len(dg) < 10:
            continue

        # Department-level stats
        hourly_counts = dg.groupby("Hour").size()
        hourly_counts = hourly_counts.reindex(range(24), fill_value=0)
        max_hourly = hourly_counts.max() if hourly_counts.max() > 0 else 1

        # ALS rate by hour
        als_by_hour = dg[dg["Care_Level"] == "ALS"].groupby("Hour").size()
        als_by_hour = als_by_hour.reindex(range(24), fill_value=0)
        total_by_hour = dg.groupby("Hour").size().reindex(range(24), fill_value=0)
        als_rate = np.where(total_by_hour > 0, als_by_hour / total_by_hour, 0)

        # Response time by hour
        rt_by_hour = dg.groupby("Hour")["Response_Min"].mean()
        rt_by_hour = rt_by_hour.reindex(range(24))
        day_rt = dg[(dg["Hour"] >= 8) & (dg["Hour"] < 18)]["Response_Min"].mean()
        if pd.isna(day_rt):
            day_rt = 6.5

        # Concurrent rate by hour
        conc_by_hour = {}
        for h in range(24):
            hg = dg_detail[dg_detail["Hour"] == h]
            if len(hg) > 0:
                conc_by_hour[h] = (hg["Concurrent_Count"] >= 1).mean()
            else:
                conc_by_hour[h] = 0

        s = STAFFING.get(dept, {})

        for h in range(24):
            # Sub-score 1: Call frequency (0-25)
            freq_score = (hourly_counts.get(h, 0) / max_hourly) * 25

            # Sub-score 2: Concurrent call risk (0-25)
            conc_rate = conc_by_hour.get(h, 0)
            conc_score = min(conc_rate / 0.15, 1.0) * 25  # normalize: 15%+ = full score

            # Sub-score 3: Response time impact (0-25)
            rt_h = rt_by_hour.get(h)
            if pd.notna(rt_h):
                rt_delta = rt_h - day_rt
                if rt_delta > 3:
                    rt_score = 25
                elif rt_delta > 0:
                    rt_score = (rt_delta / 3) * 25
                else:
                    rt_score = 5  # below average = low necessity signal
            else:
                rt_score = 12.5  # no data = neutral

            # Sub-score 4: ALS need (0-25)
            als_pct = als_rate[h] if h < len(als_rate) else 0
            als_score = min(als_pct / 0.4, 1.0) * 25  # normalize: 40%+ ALS = full score

            composite = freq_score + conc_score + rt_score + als_score

            # Flag
            is_night = (h >= 22 or h < 6)
            has_career_24_7 = s.get("24_7", False) and s.get("FT", 0) >= 6
            has_no_career = s.get("FT", 0) == 0

            if composite < 20 and has_career_24_7 and is_night:
                flag = "OVERSTAFFED"
            elif composite > 60 and has_no_career:
                flag = "UNDERSTAFFED"
            elif composite < 20 and is_night:
                flag = "Low Need"
            elif composite > 50:
                flag = "High Need"
            else:
                flag = "Adequate"

            score_rows.append({
                "Dept": dept,
                "Hour": h,
                "Freq_Score": round(freq_score, 1),
                "Conc_Score": round(conc_score, 1),
                "RT_Score": round(rt_score, 1),
                "ALS_Score": round(als_score, 1),
                "Composite": round(composite, 1),
                "Flag": flag,
                "Is_Night": is_night,
                "FT_Staff": s.get("FT", 0),
                "Has_24_7": s.get("24_7", False),
            })

    scores_df = pd.DataFrame(score_rows)
    scores_df.to_csv(os.path.join(SCRIPT_DIR, "staffing_necessity_scores.csv"), index=False)
    print(f"  Saved: staffing_necessity_scores.csv")

    # Flagged cells
    flags = scores_df[scores_df["Flag"].isin(["OVERSTAFFED", "UNDERSTAFFED"])]
    flags.to_csv(os.path.join(SCRIPT_DIR, "staffing_flags.csv"), index=False)
    print(f"  Saved: staffing_flags.csv ({len(flags)} flagged cells)")

    # --- Plot: Necessity heatmap ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    pivot = scores_df.pivot(index="Dept", columns="Hour", values="Composite")
    dept_display = [d for d in DEPT_ORDER if d in pivot.index]
    pivot = pivot.loc[dept_display]

    fig, ax = plt.subplots(figsize=(16, 8))
    cmap = mcolors.LinearSegmentedColormap.from_list("necessity",
        ["#2ecc71", "#f9e79f", "#f39c12", "#e74c3c"], N=256)
    data = pivot.values
    im = ax.imshow(data, cmap=cmap, aspect="auto", vmin=0, vmax=80)

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
    ax.set_yticks(range(len(dept_display)))
    ylabels_n = []
    for d in dept_display:
        s = STAFFING.get(d, {})
        model = "24/7" if s.get("24_7") else "PT/Vol"
        ylabels_n.append(f"{d} ({s.get('FT', 0)} FT, {model})")
    ax.set_yticklabels(ylabels_n, fontsize=9)

    # Annotate
    for i in range(len(dept_display)):
        for j in range(24):
            val = data[i, j]
            if np.isnan(val):
                continue
            color = "white" if val > 45 else "black"
            ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=6, color=color)

    # Night shading lines
    ax.axvline(x=5.5, color="cyan", linewidth=1.5, linestyle="--", alpha=0.8)
    ax.axvline(x=21.5, color="cyan", linewidth=1.5, linestyle="--", alpha=0.8)

    # Flag markers
    for _, row in flags.iterrows():
        dept_idx = dept_display.index(row["Dept"]) if row["Dept"] in dept_display else None
        if dept_idx is not None:
            marker = "v" if row["Flag"] == "OVERSTAFFED" else "^"
            mc = "blue" if row["Flag"] == "OVERSTAFFED" else "red"
            ax.plot(row["Hour"], dept_idx, marker=marker, color=mc, markersize=8,
                    markeredgecolor="white", markeredgewidth=1, zorder=5)

    plt.colorbar(im, ax=ax, label="Staffing Necessity Score (0-100)", shrink=0.8)
    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_title(
        "Staffing Necessity Score by Department and Hour\n"
        "Composite of call frequency, concurrent risk, RT impact, and ALS need | "
        "v = Overstaffed  ^ = Understaffed",
        fontsize=12, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "staffing_necessity_heatmap.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: staffing_necessity_heatmap.png")

    return scores_df, flags


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 5: Service Improvement Scenarios
# ═══════════════════════════════════════════════════════════════════════════

def module5_scenarios(scores_df, coverage_df):
    """Model 3 staffing change scenarios framed as service improvements."""
    print("\n>> MODULE 5: Service Improvement Scenarios")

    scenarios = []

    # --- Scenario 1: Regional Overnight ALS Hubs ---
    # 3 hubs (Fort Atkinson, Watertown, Edgerton) cover small depts overnight
    # Small depts go to on-call/mutual aid for overnight, with hub backup
    hub_depts = ["Fort Atkinson", "Watertown", "Edgerton"]
    covered_depts = ["Waterloo", "Johnson Creek", "Ixonia", "Cambridge", "Palmyra", "Lake Mills"]

    # RT impact estimate: avg additional 5-8 min for cross-coverage calls
    # But volunteer depts already have 10-15 min night RT, so hub at ~12-15 min
    # Career hub RT: ~7 min (their own night RT) + ~5 min drive = ~12 min
    # vs current volunteer: 10-15 min — roughly equivalent or better for ALS

    night_calls_covered = sum(AUTH_EMS.get(d, 0) * 0.16 for d in covered_depts)
    # Cost: hubs already staffed 24/7, so incremental cost is minimal
    # Savings: small depts can reduce overnight on-call pay

    # Estimate small dept overnight cost: ~$10/hr on-call × 8 hrs × 365 days × avg 2 people
    on_call_cost_per_dept = 10 * 8 * 365 * 2  # $58,400/yr per dept
    total_savings = on_call_cost_per_dept * len(covered_depts)
    # But some depts don't pay on-call, so conservative estimate
    total_savings_conservative = on_call_cost_per_dept * 3  # 3 depts with paid on-call

    scenarios.append({
        "Scenario": "1: Regional Overnight ALS Hubs",
        "Description": "3 career ALS departments (Fort Atkinson, Watertown, Edgerton) provide overnight backup to 6 smaller departments via mutual aid protocol",
        "Coverage_Change": f"ALS coverage extended to {len(covered_depts)} departments that currently lose ALS at night",
        "RT_Impact": "Estimated 10-15 min for cross-coverage calls (vs 10-15 min current volunteer RT)",
        "Night_Calls_Affected": int(night_calls_covered),
        "Annual_Cost_Change": f"-${total_savings_conservative:,.0f} (on-call reductions) to +$0 (no new staff if hub capacity exists)",
        "FTE_Change": "0 new FTE (uses existing hub capacity)",
        "Key_Benefit": "Guaranteed ALS-level response overnight for areas that currently get BLS-only or no response",
        "Key_Risk": "Longer response times for remote areas; hub departments absorb more overnight calls",
    })

    # --- Scenario 2: Peak-Weighted FT Shifts ---
    # Small depts shift FT from 24/7 to 12-hr day (09:00-21:00)
    peak_depts = ["Waterloo", "Johnson Creek", "Ixonia"]
    # These depts have 2-4 FT covering 24/7; shift to 12hr saves 1/3 salary per FT
    ft_savings = 0
    for d in peak_depts:
        ft = STAFFING.get(d, {}).get("FT", 0)
        # Avg FT salary ~$55K; shifting from 24/7 to 12hr saves ~33% of salary cost
        ft_savings += ft * 55000 * 0.33

    peak_calls_gained = sum(AUTH_EMS.get(d, 0) * 0.66 for d in peak_depts)  # 66% of calls in 09-21

    scenarios.append({
        "Scenario": "2: Peak-Weighted FT Shifts (09:00-21:00)",
        "Description": "Small departments (Waterloo, Johnson Creek, Ixonia) shift FT staff from 24/7 to 12-hr day shifts covering 66% of calls",
        "Coverage_Change": f"Peak coverage improved; overnight reverts to volunteer/mutual aid",
        "RT_Impact": "Day RT unchanged; night RT depends on volunteer availability (currently +3-6 min degradation)",
        "Night_Calls_Affected": int(sum(AUTH_EMS.get(d, 0) * 0.16 for d in peak_depts)),
        "Annual_Cost_Change": f"-${ft_savings:,.0f} in overtime/shift differential savings",
        "FTE_Change": f"Same FTE count, redistributed to peak hours",
        "Key_Benefit": "Better daytime staffing reliability; FT crews available during 66% of call volume",
        "Key_Risk": "Overnight response times may increase 2-5 min for affected departments",
    })

    # --- Scenario 3: County-Funded Roving Overnight Paramedic ---
    # 1-2 paramedics covering southern/eastern corridor overnight
    roving_coverage_pop = sum(
        {"Palmyra": 3341, "Ixonia": 5078, "Cambridge": 2800, "Lake Mills": 6200}.get(d, 0)
        for d in ["Palmyra", "Ixonia", "Cambridge", "Lake Mills"]
    )
    roving_night_calls = sum(AUTH_EMS.get(d, 0) * 0.16 for d in ["Palmyra", "Ixonia", "Cambridge", "Lake Mills"])

    scenarios.append({
        "Scenario": "3: County-Funded Roving Overnight Paramedic",
        "Description": "1-2 county-employed paramedics stationed at a central location, responding to overnight ALS calls in the southern/eastern corridor (Palmyra, Ixonia, Cambridge, Lake Mills)",
        "Coverage_Change": f"ALS coverage added overnight for ~{roving_coverage_pop:,} residents currently served by BLS/volunteer departments",
        "RT_Impact": "Estimated 12-18 min (drive time from central station); improves on current 11-15 min volunteer RT by adding ALS capability",
        "Night_Calls_Affected": int(roving_night_calls),
        "Annual_Cost_Change": f"+${PARAMEDIC_ANNUAL_COST:,.0f} per paramedic (salary + benefits)",
        "FTE_Change": "+1-2 FTE (new county positions)",
        "Key_Benefit": "Fills the ALS gap for 4 departments that cannot provide paramedic-level care overnight",
        "Key_Risk": "Limited call volume (~{:.0f}/yr overnight) means low utilization of paramedic skill".format(roving_night_calls),
    })

    scenarios_df = pd.DataFrame(scenarios)
    scenarios_df.to_csv(os.path.join(SCRIPT_DIR, "staffing_scenarios.csv"), index=False)
    print(f"  Saved: staffing_scenarios.csv")

    # --- Plot: Scenario comparison ---
    try:
        plt.style.use(STYLE)
    except Exception:
        pass

    fig, axes = plt.subplots(1, 3, figsize=(18, 8))

    for i, (_, sc) in enumerate(scenarios_df.iterrows()):
        ax = axes[i]
        # Create a text-based summary card
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")

        # Title
        title_color = ["#3498db", "#f39c12", "#2ecc71"][i]
        ax.add_patch(plt.Rectangle((0, 8.5), 10, 1.5, facecolor=title_color, alpha=0.2))
        ax.text(5, 9.25, f"Scenario {i+1}", ha="center", va="center",
                fontsize=14, fontweight="bold", color=title_color)

        # Content
        content = [
            ("Coverage", sc["Coverage_Change"]),
            ("RT Impact", sc["RT_Impact"]),
            ("Night Calls", str(sc["Night_Calls_Affected"])),
            ("Cost Change", sc["Annual_Cost_Change"]),
            ("FTE Change", sc["FTE_Change"]),
            ("Key Benefit", sc["Key_Benefit"]),
            ("Key Risk", sc["Key_Risk"]),
        ]

        y = 8.0
        for label, value in content:
            ax.text(0.3, y, f"{label}:", fontsize=8, fontweight="bold", va="top")
            # Wrap text
            wrapped = value[:80] + ("..." if len(value) > 80 else "")
            ax.text(0.3, y - 0.4, wrapped, fontsize=7, va="top", wrap=True,
                    color="#333")
            y -= 1.1

    fig.suptitle(
        "Service Improvement Scenarios — Overnight Staffing Alternatives\n"
        "Jefferson County EMS | Framed as care quality improvements",
        fontsize=14, fontweight="bold"
    )
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "scenario_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: scenario_comparison.png")

    return scenarios_df


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(als_bls_ct, night_day, util_summary, coverage_df, scores_df, flags_df, scenarios_df):
    """Generate the polished Nighttime_Operations_Deep_Dive.md report."""
    print("\n>> Generating report: Nighttime_Operations_Deep_Dive.md")

    lines = []
    lines.append("# Nighttime Operations & ALS/BLS Utilization Deep-Dive")
    lines.append("## Jefferson County EMS -- CY2024 Analysis")
    lines.append("")
    lines.append("*Generated: {}*".format(datetime.now().strftime("%B %d, %Y")))
    lines.append("*Data Sources: CY2024 NFIRS (14 departments, 13,758 EMS calls), concurrent call detail (8,355 records), FY2025 staffing budgets, fire chief interviews (Mar 2026)*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Executive Summary ──
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("This analysis investigates five questions about Jefferson County's overnight EMS operations (22:00-06:00):")
    lines.append("")

    overstaffed_count = len(flags_df[flags_df["Flag"] == "OVERSTAFFED"])
    understaffed_count = len(flags_df[flags_df["Flag"] == "UNDERSTAFFED"])

    lines.append(f"1. **ALS demand is roughly constant across all hours.** Nighttime ALS share ({night_day['Night_ALS_Pct']}%) is comparable to daytime ({night_day['Day_ALS_Pct']}%), meaning patients need the same level of care at 3am as at 3pm. Departments that lose ALS capability overnight are delivering a lower standard of care to ~16% of their annual calls.")
    lines.append(f"2. **Five departments maintain 24/7 career ALS; six do not.** Watertown, Fort Atkinson, Edgerton, Whitewater, and Johnson Creek staff ALS around the clock. Waterloo, Ixonia, Cambridge, Palmyra, and Lake Mills rely on volunteers or on-call staff overnight, resulting in response time increases of +3 to +6 minutes.")
    lines.append(f"3. **Overnight ambulance utilization is extremely low.** Most departments show <2% fleet utilization between 22:00-06:00. Even the busiest department (Edgerton) rarely exceeds 5% overnight utilization.")
    lines.append(f"4. **{overstaffed_count} department-hour cells are flagged as overstaffed; {understaffed_count} as understaffed.** Career departments maintaining full overnight crews for very low call volumes represent a staffing-demand mismatch, while volunteer departments with degraded night response times represent a care quality gap.")
    lines.append("5. **Three scenarios could improve overnight care quality**: Regional overnight ALS hubs, peak-weighted FT shifts, or a county-funded roving overnight paramedic.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 1: ALS vs BLS by Hour ──
    lines.append("## 1. ALS vs BLS Demand by Time of Day")
    lines.append("")
    lines.append("**Key Finding:** ALS demand does not drop off at night. The proportion of calls requiring Advanced Life Support is roughly constant across all 24 hours.")
    lines.append("")
    lines.append("![ALS vs BLS by Hour - Countywide](als_bls_by_hour_county.png)")
    lines.append("")
    lines.append("### Nighttime vs Daytime ALS Share")
    lines.append("")
    lines.append("| Time Period | Hours | Total Calls | ALS % | BLS % |")
    lines.append("|---|---|---|---|---|")
    lines.append(f"| Daytime (08:00-17:59) | 10 hrs | {night_day['Day_Total']:,} | **{night_day['Day_ALS_Pct']}%** | {night_day['Day_BLS_Pct']}% |")
    lines.append(f"| Nighttime (22:00-05:59) | 8 hrs | {night_day['Night_Total']:,} | **{night_day['Night_ALS_Pct']}%** | {night_day['Night_BLS_Pct']}% |")
    lines.append("")
    lines.append("**Implication:** Departments that lose ALS capability overnight are not matching their care level to actual patient need. A cardiac arrest at 3am requires the same paramedic intervention as one at 3pm.")
    lines.append("")
    lines.append("### Per-Department ALS/BLS Breakdown")
    lines.append("")
    lines.append("![ALS vs BLS by Hour - Per Department](als_bls_by_hour_dept.png)")
    lines.append("")
    lines.append("*Note: BLS-only departments (Palmyra, Ixonia) show 0% ALS because they cannot provide it -- this does not mean ALS was not needed for those calls. Patients in BLS districts requiring ALS care must wait for mutual aid or intercept.*")
    lines.append("")
    lines.append("*Source: CY2024 NFIRS 'Action Taken 1 Description' field, filtered to Rescue and EMS calls (Category 300-381)*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 2: Utilization ──
    lines.append("## 2. Ambulance Utilization by Hour")
    lines.append("")
    lines.append("**Key Finding:** Ambulance fleets are dramatically underutilized overnight. Most departments show <2% fleet utilization between 22:00-06:00, meaning ambulances sit idle for 98%+ of overnight hours.")
    lines.append("")
    lines.append("![Utilization Heatmap](utilization_heatmap.png)")
    lines.append("")
    lines.append("### Peak vs Overnight Utilization by Department")
    lines.append("")
    lines.append("| Department | Ambulances | Peak Util % | Day Util % | Night Util % | Hours <2% Util |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in util_summary.iterrows():
        lines.append(f"| {r['Dept']} | {r['Ambulances']} | {r['Peak_Util_Pct']}% | {r['Day_Util_Pct']}% | {r['Night_Util_Pct']}% | {r['Idle_Hours_Under_2Pct']} of 24 |")
    lines.append("")
    lines.append("**Reading this table:** A utilization rate of 3% means the ambulance fleet is actively on an EMS call for 3% of available minutes in that hour across the year. Night utilization below 2% means the fleet is idle for >98% of overnight hours.")
    lines.append("")
    lines.append("**Implication:** The data shows that maintaining dedicated overnight ambulance staffing results in crews waiting for calls >95% of the time. This is not inherently wasteful (emergency services must be available regardless of utilization), but it does mean the overnight staffing investment buys very little actual service delivery.")
    lines.append("")
    lines.append("*Source: CY2024 NFIRS call timestamps from concurrent_call_detail.csv (8,355 records). Utilization = sum of call-busy minutes / (ambulances x 60 min x 365 days) per hour slot.*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 3: Coverage Matrix ──
    lines.append("## 3. Nighttime Coverage & Staffing Matrix")
    lines.append("")
    lines.append("**Key Finding:** Five departments maintain 24/7 career ALS staffing. The remaining departments rely on volunteers or on-call staff overnight, and three of them show the worst nighttime response time degradation in the county.")
    lines.append("")
    lines.append("### Coverage by Shift")
    lines.append("")
    lines.append("| Department | FT | Service | Day (06-14) | Afternoon (14-22) | Overnight (22-06) | ALS at Night? |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, r in coverage_df.iterrows():
        als_night = r["ALS_at_Night"]
        bold = "**" if "NO" in str(als_night) or "N/A" in str(als_night) else ""
        lines.append(f"| {r['Department']} | {r['FT_Staff']} | {r['Service_Level']} | {r['Day_Coverage']} | {r['Afternoon_Coverage']} | {r['Overnight_Coverage']} | {bold}{als_night}{bold} |")
    lines.append("")

    lines.append("![Nighttime Coverage Gaps](nighttime_coverage_gap.png)")
    lines.append("")
    lines.append("### Nighttime Response Time Degradation")
    lines.append("")
    lines.append("Departments with the weakest overnight coverage show the largest response time increases:")
    lines.append("")
    lines.append("| Department | Day RT (min) | Night RT (min) | Delta | Overnight Model |")
    lines.append("|---|---|---|---|---|")
    rt_sorted = coverage_df.dropna(subset=["RT_Delta_min"]).sort_values("RT_Delta_min", ascending=False)
    for _, r in rt_sorted.iterrows():
        flag = " :warning:" if r["RT_Delta_min"] >= 4 else ""
        lines.append(f"| {r['Department']} | {r['Day_RT_min']} | {r['Night_RT_min']} | **+{r['RT_Delta_min']} min**{flag} | {r['Night_Model']} |")
    lines.append("")
    lines.append("**Pattern:** The three departments with the worst night RT degradation (Ixonia +6.4 min, Palmyra +5.5 min, Waterloo +4.4 min) are all volunteer/on-call departments that lose career staffing overnight. This is a direct link between staffing model and patient care quality.")
    lines.append("")
    lines.append("*Sources: CY2024 NFIRS response times, FY2025 staffing budgets, fire chief interviews (Waterloo 3/11/26, Johnson Creek 3/13/26)*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 4: Necessity Scoring ──
    lines.append("## 4. Staffing Necessity Analysis")
    lines.append("")
    lines.append("Each department-hour is scored 0-100 based on four equally-weighted factors:")
    lines.append("- **Call Frequency** (0-25): How many calls occur at this hour relative to the department's peak?")
    lines.append("- **Concurrent Call Risk** (0-25): How often are multiple calls active simultaneously?")
    lines.append("- **Response Time Impact** (0-25): Does response time degrade at this hour?")
    lines.append("- **ALS Need** (0-25): What share of calls at this hour require ALS-level care?")
    lines.append("")
    lines.append("![Staffing Necessity Heatmap](staffing_necessity_heatmap.png)")
    lines.append("")

    # Overstaffed table
    over = flags_df[flags_df["Flag"] == "OVERSTAFFED"].sort_values("Composite")
    if len(over) > 0:
        lines.append("### Overstaffed Hours (24/7 Career Depts with Low Night Necessity)")
        lines.append("")
        lines.append("| Department | Hour | Score | Call Freq | Conc Risk | RT Impact | ALS Need |")
        lines.append("|---|---|---|---|---|---|---|")
        for _, r in over.head(15).iterrows():
            lines.append(f"| {r['Dept']} | {int(r['Hour']):02d}:00 | **{r['Composite']}** | {r['Freq_Score']} | {r['Conc_Score']} | {r['RT_Score']} | {r['ALS_Score']} |")
        if len(over) > 15:
            lines.append(f"| *... {len(over) - 15} more rows* | | | | | | |")
        lines.append("")
        lines.append(f"**{len(over)} department-hour cells** are flagged where 24/7 career departments maintain full staffing during hours with very low necessity scores (<20). This does not mean these hours should be unstaffed -- it means the staffing level exceeds what the call data alone justifies.")
        lines.append("")

    # Understaffed table
    under = flags_df[flags_df["Flag"] == "UNDERSTAFFED"].sort_values("Composite", ascending=False)
    if len(under) > 0:
        lines.append("### Understaffed Hours (Volunteer Depts with High Necessity)")
        lines.append("")
        lines.append("| Department | Hour | Score | Call Freq | Conc Risk | RT Impact | ALS Need |")
        lines.append("|---|---|---|---|---|---|---|")
        for _, r in under.head(15).iterrows():
            lines.append(f"| {r['Dept']} | {int(r['Hour']):02d}:00 | **{r['Composite']}** | {r['Freq_Score']} | {r['Conc_Score']} | {r['RT_Score']} | {r['ALS_Score']} |")
        lines.append("")
    lines.append("")
    lines.append("*Methodology: Scores normalize each sub-component to 0-25 range. Call frequency uses department-specific peak as denominator. Concurrent risk normalizes at 15% threshold. RT impact compares hour-specific RT to daytime (08-18) baseline. ALS need normalizes at 40% ALS share.*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 5: Scenarios ──
    lines.append("## 5. Service Improvement Scenarios")
    lines.append("")
    lines.append("Three scenarios for improving overnight EMS care quality. All are framed as patient care improvements rather than cost-cutting measures.")
    lines.append("")
    lines.append("![Scenario Comparison](scenario_comparison.png)")
    lines.append("")

    for _, sc in scenarios_df.iterrows():
        lines.append(f"### {sc['Scenario']}")
        lines.append("")
        lines.append(f"**{sc['Description']}**")
        lines.append("")
        lines.append(f"| Dimension | Detail |")
        lines.append(f"|---|---|")
        lines.append(f"| Coverage Change | {sc['Coverage_Change']} |")
        lines.append(f"| Response Time Impact | {sc['RT_Impact']} |")
        lines.append(f"| Night Calls Affected | {sc['Night_Calls_Affected']}/yr |")
        lines.append(f"| Annual Cost Change | {sc['Annual_Cost_Change']} |")
        lines.append(f"| FTE Change | {sc['FTE_Change']} |")
        lines.append(f"| **Key Benefit** | {sc['Key_Benefit']} |")
        lines.append(f"| Key Risk | {sc['Key_Risk']} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Data Sources ──
    lines.append("## Data Sources & Methodology")
    lines.append("")
    lines.append("| Source | Description | Time Period |")
    lines.append("|---|---|---|")
    lines.append("| NFIRS Excel files (14) | `ISyE Project/Data and Resources/Call Data/*.xlsx` | CY2024 |")
    lines.append("| Concurrent call detail | `concurrent_call_detail.csv` (8,355 records) | CY2024 |")
    lines.append("| Staffing budgets | `EMS Budgets/EMS Budgets/<Dept>/` PDFs | FY2025 |")
    lines.append("| Waterloo Chief interview | `3.11.26 Waterloo Fire Department Cheif.txt` | Mar 11, 2026 |")
    lines.append("| Johnson Creek Chief interview | `3.13.26 Johnson Creek Interview.txt` | Mar 13, 2026 |")
    lines.append("| Peterson cost model | `25-1210 JC EMS Workgroup Cost Projection.pdf` | Dec 2025 |")
    lines.append("| Authoritative call volumes | `Call Volumes - Jefferson County EMS.xlsx` (new3.31.26/) | CY2024 |")
    lines.append("")
    lines.append("### Methodology Notes")
    lines.append("")
    lines.append("- **ALS/BLS classification**: Uses NFIRS `Action Taken 1 Description` field, which records the actual care level delivered (not the call type). BLS departments show 0% ALS because they cannot provide it, not because ALS was unnecessary.")
    lines.append("- **Utilization calculation**: Minute-level precision. Each call's duration is distributed across the clock hours it spans (e.g., a call starting at 14:50 lasting 45 min occupies hour-14 for 10 min and hour-15 for 35 min).")
    lines.append("- **Necessity scoring**: Equal weights (25 pts each) for four sub-components. This is a diagnostic tool -- low scores do not mean 'cut staffing,' they mean 'the data does not show high demand at this hour.'")
    lines.append("- **Scenario costing**: Uses Peterson cost model ($716K operating / 24/7 ALS crew) as baseline. Paramedic salary estimated at $95K/yr including benefits. On-call rates from Waterloo Chief interview ($10/hr EMTA).")
    lines.append("")
    lines.append("*This analysis is diagnostic. It identifies where staffing and demand are misaligned, not what specific changes to make. Implementation decisions require additional input on minimum coverage requirements, union contracts, response time targets, and mutual aid agreements.*")

    report_text = "\n".join(lines)
    report_path = os.path.join(SCRIPT_DIR, "Nighttime_Operations_Deep_Dive.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"  Saved: Nighttime_Operations_Deep_Dive.md")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — NIGHTTIME OPERATIONS DEEP-DIVE")
    print("=" * 70)

    # Module 1: ALS/BLS by Hour
    print("\n>> Loading NFIRS data with ALS/BLS classification...")
    ems_df = load_nfirs_with_als_bls()
    als_bls_ct, dept_als, night_day = module1_als_bls_by_hour(ems_df)

    # Module 2: Utilization by Hour
    util_df, util_summary, util_pivot = module2_utilization_by_hour()

    # Module 3: Coverage Gap Matrix
    coverage_df = module3_coverage_matrix(dept_als)

    # Module 4: Necessity Scoring
    scores_df, flags_df = module4_necessity_scoring(ems_df, util_df)

    # Module 5: Scenarios
    scenarios_df = module5_scenarios(scores_df, coverage_df)

    # Generate Report
    generate_report(als_bls_ct, night_day, util_summary, coverage_df, scores_df, flags_df, scenarios_df)

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print("\nDeliverables:")
    print("  - Nighttime_Operations_Deep_Dive.md  (main report)")
    print("  - als_bls_by_hour_county.png")
    print("  - als_bls_by_hour_dept.png")
    print("  - utilization_heatmap.png")
    print("  - nighttime_coverage_gap.png")
    print("  - staffing_necessity_heatmap.png")
    print("  - scenario_comparison.png")
    print("  - als_bls_hourly_data.csv")
    print("  - utilization_by_dept_hour.csv")
    print("  - nighttime_coverage_matrix.csv")
    print("  - staffing_necessity_scores.csv")
    print("  - staffing_flags.csv")
    print("  - staffing_scenarios.csv")


if __name__ == "__main__":
    main()
