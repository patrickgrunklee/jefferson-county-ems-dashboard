"""
Jefferson County EMS — Concurrent Call (Secondary Demand) Analysis
=================================================================
Quantifies how often each department's primary ambulance is already busy
when a new EMS call arrives. This is the foundational diagnostic for
secondary ambulance demand.

Inputs:  14 NFIRS Excel files (CY2024)
Outputs:
  - concurrent_call_results.csv        per-department summary
  - concurrent_hourly_heatmap.png      24×7 heatmap of concurrent call peaks
  - secondary_demand_by_dept.png       bar chart of secondary call volume
  - erlang_c_results.csv               P(wait) per department

Author: ISyE 450 Senior Design Team
Date:   March 2026
"""

import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from math import factorial
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CALL_DATA_DIR = os.path.join(SCRIPT_DIR, "ISyE Project", "Data and Resources", "Call Data")

# ── Department name normalization ────────────────────────────────────────
# NFIRS "Fire Department Name" → canonical short name
DEPT_NAME_MAP = {
    # Exact NFIRS "Fire Department Name" values from 2024 data
    "Fort Atkinson Fire Dept":              "Fort Atkinson",
    "Watertown Fire Dept":                  "Watertown",
    "Whitewater Fire and EMS":              "Whitewater",
    "Edgerton Fire Protection Distict":     "Edgerton",   # typo in NFIRS data
    "Jefferson Fire Dept":                  "Jefferson",
    "Johnson Creek Fire Dept":              "Johnson Creek",
    "Waterloo Fire Dept":                   "Waterloo",
    "Town of Ixonia Fire & EMS Dept":       "Ixonia",
    "Palmyra Village Fire Dept":            "Palmyra",
    "CAMBRIDGE COMM FIRE DEPT":             "Cambridge",
    "Western Lake Fire District":           "Western Lakes",
    "Rome Fire Dist":                       "Rome",
    "Sullivan Vol Fire Dept":               "Sullivan",
    # Fallbacks for possible alternative spellings
    "Lake Mills Fire Dept":                 "Lake Mills",
    "Helenville Fire Dept":                 "Helenville",
    "Lakeside Fire Rescue":                 "Edgerton",
    "Western Lakes Fire Dist":              "Western Lakes",
    "Western Lakes Fire District":          "Western Lakes",
}

# Departments that actually run ambulances (EMS transport)
EMS_TRANSPORT_DEPTS = [
    "Watertown", "Fort Atkinson", "Whitewater", "Edgerton",
    "Jefferson", "Johnson Creek", "Waterloo", "Lake Mills",
    "Ixonia", "Palmyra", "Cambridge",
]

# Number of frontline ambulances per department (from boundary_optimization.py)
AMBULANCE_COUNT = {
    "Watertown": 3, "Fort Atkinson": 3, "Whitewater": 2, "Edgerton": 2,
    "Jefferson": 3, "Johnson Creek": 2, "Waterloo": 2, "Lake Mills": 1,
    "Ixonia": 1, "Palmyra": 1, "Cambridge": 0,
}


# ── Load & clean NFIRS data ────────────────────────────────────────────
def load_all_nfirs():
    """Load all 14 NFIRS Excel files, filter to EMS-only, normalize dept names."""
    pattern = os.path.join(CALL_DATA_DIR, "Copy of 2024 EMS Workgroup - *.xlsx")
    files = glob.glob(pattern)
    print(f"  Found {len(files)} NFIRS files")

    frames = []
    for f in files:
        df = pd.read_excel(f)
        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True)
    print(f"  Total records: {len(all_df):,}")

    # Filter to EMS calls only
    ems_mask = all_df["Incident Type Code Category Description"].str.startswith(
        "Rescue and EMS", na=False
    )
    ems = all_df[ems_mask].copy()
    print(f"  EMS calls only: {len(ems):,}")

    # Normalize department names
    ems["Dept"] = ems["Fire Department Name"].map(DEPT_NAME_MAP)
    unmapped = ems[ems["Dept"].isna()]["Fire Department Name"].unique()
    if len(unmapped) > 0:
        # Try fuzzy fallback: use raw name but strip " Fire Dept" etc.
        for raw in unmapped:
            short = (raw.replace(" Fire Department", "")
                       .replace(" Fire Dept", "")
                       .replace(" Fire Dist", "")
                       .replace(" Fire District", "")
                       .replace("City of ", "")
                       .strip())
            DEPT_NAME_MAP[raw] = short
        ems["Dept"] = ems["Fire Department Name"].map(DEPT_NAME_MAP)
        still_unmapped = ems[ems["Dept"].isna()]["Fire Department Name"].unique()
        if len(still_unmapped) > 0:
            print(f"  WARNING: Unmapped depts: {still_unmapped}")

    # Parse datetimes
    ems["Alarm_DT"] = pd.to_datetime(ems["Alarm Date / Time"], errors="coerce")
    ems["Cleared_DT"] = pd.to_datetime(ems["Last Unit Cleared Date / Time"], errors="coerce")
    ems["Hour"] = ems["Alarm Date - Hour of Day"]
    ems["DOW"] = ems["Alarm Date - Day of Week"]
    ems["Response_Min"] = pd.to_numeric(ems["Response Time (Minutes)"], errors="coerce")
    ems["Duration_Min"] = pd.to_numeric(ems["Incident Duration (Minutes)"], errors="coerce")

    # Drop rows without alarm or cleared time (can't compute overlap)
    valid = ems.dropna(subset=["Alarm_DT", "Cleared_DT"]).copy()
    print(f"  With valid Alarm+Cleared timestamps: {len(valid):,}")

    return ems, valid


# ── Concurrent call computation ─────────────────────────────────────────
def compute_concurrent_calls(valid_df):
    """
    For each call, count how many OTHER calls in the same department
    have overlapping [Alarm, Cleared] time windows.
    """
    results = []

    for dept, group in valid_df.groupby("Dept"):
        if dept not in EMS_TRANSPORT_DEPTS:
            continue

        g = group.sort_values("Alarm_DT").reset_index(drop=True)
        n = len(g)
        alarms = g["Alarm_DT"].values
        cleared = g["Cleared_DT"].values
        concurrent = np.zeros(n, dtype=int)

        # Sweep-line approach: for each call i, count calls j where
        # alarm_j < cleared_i AND cleared_j > alarm_i (overlap condition)
        # Use sorted order + early exit for efficiency
        for i in range(n):
            a_i, c_i = alarms[i], cleared[i]
            count = 0
            # Look backward from i
            for j in range(i - 1, -1, -1):
                if cleared[j] <= a_i:
                    # Call j ended before call i started — and all earlier calls
                    # also ended before (since sorted by alarm time, but cleared
                    # times can vary, so we can't break early). However, we can
                    # skip very old calls.
                    if (a_i - alarms[j]) > np.timedelta64(24, 'h'):
                        break
                    continue
                if alarms[j] < c_i:
                    count += 1
            # Look forward from i
            for j in range(i + 1, n):
                if alarms[j] >= c_i:
                    break  # all future calls start after this one clears
                count += 1
            concurrent[i] = count

        g = g.copy()
        g["Concurrent_Count"] = concurrent
        results.append(g)

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


def summarize_concurrent(detail_df):
    """Per-department summary of concurrent call statistics."""
    rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        dg = detail_df[detail_df["Dept"] == dept]
        if dg.empty:
            continue
        total_calls = len(dg)
        secondary = (dg["Concurrent_Count"] >= 1).sum()
        pct = 100 * secondary / total_calls if total_calls > 0 else 0
        max_conc = dg["Concurrent_Count"].max()
        mean_conc = dg["Concurrent_Count"].mean()
        amb = AMBULANCE_COUNT.get(dept, 1)

        # Calls where concurrent >= ambulance count (ALL ambulances busy)
        all_busy = (dg["Concurrent_Count"] >= amb).sum()
        pct_all_busy = 100 * all_busy / total_calls if total_calls > 0 else 0

        rows.append({
            "Dept": dept,
            "EMS_Calls_2024": total_calls,
            "Secondary_Events": secondary,
            "Pct_Concurrent": round(pct, 1),
            "Max_Concurrent": max_conc,
            "Mean_Concurrent": round(mean_conc, 2),
            "Ambulances": amb,
            "All_Busy_Events": all_busy,
            "Pct_All_Busy": round(pct_all_busy, 1),
        })
    return pd.DataFrame(rows).sort_values("Secondary_Events", ascending=False)


# ── Hourly profile ──────────────────────────────────────────────────────
DOW_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def compute_hourly_profile(detail_df):
    """Compute concurrent call rate by hour × day-of-week (county-wide)."""
    # Only look at calls that had at least 1 concurrent
    sec = detail_df[detail_df["Concurrent_Count"] >= 1].copy()

    # Pivot: rows=hour (0-23), cols=DOW
    pivot = sec.groupby(["Hour", "DOW"]).size().unstack(fill_value=0)
    # Normalize by total calls in that hour-dow cell
    total_pivot = detail_df.groupby(["Hour", "DOW"]).size().unstack(fill_value=0)

    rate = (pivot / total_pivot.replace(0, np.nan) * 100).fillna(0)

    # Reorder columns to Mon-Sun
    for dow in DOW_ORDER:
        if dow not in rate.columns:
            rate[dow] = 0
    rate = rate[DOW_ORDER]
    rate = rate.sort_index()

    return rate, sec


# ── Erlang-C queueing model ────────────────────────────────────────────
def erlang_c(lam, mu, c):
    """
    Erlang-C formula: probability that all c servers are busy.

    lam: arrival rate (calls per hour)
    mu:  service rate (1 / mean_service_time in hours)
    c:   number of servers (ambulances)

    Returns P(wait) — probability a new call must wait.
    """
    if c == 0 or lam <= 0 or mu <= 0:
        return np.nan
    rho = lam / (c * mu)
    if rho >= 1.0:
        return 1.0  # system overloaded

    a = lam / mu  # offered load (Erlangs)

    # P0: probability all servers idle
    # Sum of (a^k / k!) for k=0..c-1, plus (a^c / c!) * 1/(1-rho)
    sum_terms = sum(a**k / factorial(k) for k in range(c))
    last_term = (a**c / factorial(c)) * (1 / (1 - rho))
    p0 = 1.0 / (sum_terms + last_term)

    # Erlang-C value
    ec = ((a**c / factorial(c)) * (1 / (1 - rho))) * p0
    return ec


def compute_erlang_c(detail_df):
    """
    For each department, compute Erlang-C P(wait) at current ambulance staffing.
    Also compute P(wait) during peak hours (09:00-19:00).
    """
    rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        dg = detail_df[detail_df["Dept"] == dept]
        if dg.empty:
            continue

        amb = AMBULANCE_COUNT.get(dept, 1)
        if amb == 0:
            rows.append({
                "Dept": dept, "Ambulances": 0,
                "Calls_Per_Day": np.nan, "Mean_Duration_Min": np.nan,
                "Lambda_AllDay": np.nan, "Lambda_Peak_9_19": np.nan,
                "Mu": np.nan,
                "P_Wait_AllDay": np.nan, "P_Wait_Peak": np.nan,
            })
            continue

        # Mean service time (call duration in hours)
        mean_dur_hrs = dg["Duration_Min"].dropna().mean() / 60.0
        if mean_dur_hrs <= 0 or np.isnan(mean_dur_hrs):
            mean_dur_hrs = 0.75  # default 45 min

        mu = 1.0 / mean_dur_hrs  # service rate per server

        # Arrival rate: calls per hour over the year
        total_calls = len(dg)
        hours_in_year = 365 * 24
        lam_all = total_calls / hours_in_year

        # Peak hours (09:00 - 19:00) = 10 hrs/day × 365 days = 3650 hrs
        peak = dg[(dg["Hour"] >= 9) & (dg["Hour"] < 19)]
        peak_calls = len(peak)
        peak_hours = 365 * 10
        lam_peak = peak_calls / peak_hours if peak_hours > 0 else 0

        p_wait_all = erlang_c(lam_all, mu, amb)
        p_wait_peak = erlang_c(lam_peak, mu, amb)

        rows.append({
            "Dept": dept,
            "Ambulances": amb,
            "Calls_Per_Day": round(total_calls / 365, 1),
            "Mean_Duration_Min": round(mean_dur_hrs * 60, 1),
            "Lambda_AllDay": round(lam_all, 4),
            "Lambda_Peak_9_19": round(lam_peak, 4),
            "Mu": round(mu, 4),
            "P_Wait_AllDay": round(p_wait_all, 4) if not np.isnan(p_wait_all) else np.nan,
            "P_Wait_Peak": round(p_wait_peak, 4) if not np.isnan(p_wait_peak) else np.nan,
        })

    return pd.DataFrame(rows)


# ── Plotting ────────────────────────────────────────────────────────────
def plot_heatmap(rate_df, detail_df):
    """24×7 heatmap of concurrent call rate (%)."""
    fig, ax = plt.subplots(figsize=(10, 8))

    data = rate_df.values
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto",
                   vmin=0, vmax=min(50, data.max()))

    ax.set_xticks(range(len(DOW_ORDER)))
    ax.set_xticklabels(DOW_ORDER, fontsize=11)
    ax.set_yticks(range(24))
    ax.set_yticklabels([f"{h:02d}:00" for h in range(24)], fontsize=9)

    ax.set_xlabel("Day of Week", fontsize=12)
    ax.set_ylabel("Hour of Day", fontsize=12)
    ax.set_title(
        "EMS Concurrent Call Rate by Hour × Day (County-Wide)\n"
        "% of calls with ≥1 other active call in same department | CY2024 NFIRS",
        fontsize=13, fontweight="bold"
    )

    # Add text annotations
    for i in range(24):
        for j in range(len(DOW_ORDER)):
            val = data[i, j]
            color = "white" if val > data.max() * 0.6 else "black"
            ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                    fontsize=7.5, color=color, fontweight="bold")

    plt.colorbar(im, ax=ax, label="Concurrent Rate (%)", shrink=0.8)
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "concurrent_hourly_heatmap.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: concurrent_hourly_heatmap.png")


def plot_secondary_by_dept(summary_df):
    """Bar chart: secondary call events by department."""
    df = summary_df.sort_values("Secondary_Events", ascending=True)

    fig, ax = plt.subplots(figsize=(10, 7))

    colors = []
    for _, row in df.iterrows():
        if row["Pct_Concurrent"] >= 15:
            colors.append("#e74c3c")
        elif row["Pct_Concurrent"] >= 8:
            colors.append("#f39c12")
        else:
            colors.append("#2ecc71")

    bars = ax.barh(df["Dept"], df["Secondary_Events"], color=colors, edgecolor="#333",
                   linewidth=0.5)

    # Annotate with % and all-busy count
    for bar, (_, row) in zip(bars, df.iterrows()):
        w = bar.get_width()
        label = f"  {int(w)} ({row['Pct_Concurrent']:.0f}%)"
        if row["All_Busy_Events"] > 0:
            label += f" | All busy: {int(row['All_Busy_Events'])}"
        ax.text(w + 5, bar.get_y() + bar.get_height() / 2,
                label, va="center", fontsize=9)

    ax.set_xlabel("Secondary Demand Events (≥1 concurrent call)", fontsize=12)
    ax.set_title(
        "Secondary Ambulance Demand by Department\n"
        "Calls arriving while primary unit already on scene | CY2024 NFIRS",
        fontsize=13, fontweight="bold"
    )

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#e74c3c", edgecolor="#333", label="≥15% concurrent"),
        Patch(facecolor="#f39c12", edgecolor="#333", label="8-15% concurrent"),
        Patch(facecolor="#2ecc71", edgecolor="#333", label="<8% concurrent"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=10)

    ax.set_xlim(0, df["Secondary_Events"].max() * 1.35)
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "secondary_demand_by_dept.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: secondary_demand_by_dept.png")


# ── Main ────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — CONCURRENT CALL ANALYSIS")
    print("=" * 70)

    # 1. Load data
    print("\n>> Loading NFIRS data...")
    all_ems, valid = load_all_nfirs()

    # 2. Compute concurrent calls
    print("\n>> Computing concurrent calls (sweep-line algorithm)...")
    detail = compute_concurrent_calls(valid)
    print(f"  Processed {len(detail):,} calls across {detail['Dept'].nunique()} departments")

    # 3. Summarize
    print("\n>> Summarizing per department...")
    summary = summarize_concurrent(detail)
    csv_path = os.path.join(SCRIPT_DIR, "concurrent_call_results.csv")
    summary.to_csv(csv_path, index=False)
    print(f"  Saved: concurrent_call_results.csv")
    print()
    print(summary.to_string(index=False))

    # 4. Hourly profile
    print("\n>> Computing hourly concurrent profile...")
    rate, _ = compute_hourly_profile(detail)

    # 5. Erlang-C
    print("\n>> Computing Erlang-C queueing model...")
    erlang_df = compute_erlang_c(detail)
    erlang_path = os.path.join(SCRIPT_DIR, "erlang_c_results.csv")
    erlang_df.to_csv(erlang_path, index=False)
    print(f"  Saved: erlang_c_results.csv")
    print()
    print(erlang_df.to_string(index=False))

    # 6. Plots
    print("\n>> Generating plots...")
    plot_heatmap(rate, detail)
    plot_secondary_by_dept(summary)

    # 7. Save detail for downstream phases
    detail_path = os.path.join(SCRIPT_DIR, "concurrent_call_detail.csv")
    detail[["Dept", "Alarm_DT", "Cleared_DT", "Hour", "DOW",
            "Response_Min", "Duration_Min", "Concurrent_Count"]
           ].to_csv(detail_path, index=False)
    print(f"  Saved: concurrent_call_detail.csv (for Phase 2/4)")

    print("\n" + "=" * 70)
    print("PHASE 1 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
