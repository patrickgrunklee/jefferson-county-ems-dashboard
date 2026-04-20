"""
County EMS Comparison: Portage County vs Jefferson County (Consolidated)
========================================================================
Compares EMS data from the 2024 Portage County Public Safety Annual Report against
consolidated municipal EMS data from Jefferson County's 14 EMS service areas.

- Portage County: Countywide EMS system under Sheriff's Office (since 2018)
- Jefferson County: Fragmented municipal EMS coverage (14 separate providers)
"""

import os
import glob
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION
# ============================================================
BASE_DIR = Path(r"c:\Users\patri\OneDrive - UW-Madison\ISYE 450\ISyE Project")
CALL_DATA_DIR = BASE_DIR / "Data and Resources" / "Call Data"
OUTPUT_DIR = BASE_DIR / "Comparison Output"

# --- Population Constants ---
JEFF_POP = 85000
PORTAGE_POP = 70521

# --- DataFrame Column Name Constants ---
C_MUNI = "Municipality"
C_INC_CAT = "Incident Type Code (Category)"
C_INC_DESC = "Incident Type Description"
C_INC_CAT_DESC = "Incident Type Code Category Description"
C_RESP_TIME = "Response Time (Minutes)"
C_EMS_PERS = "Number of EMS Personnel"
C_TOTAL_PERS = "Number of Total Personnel"
C_EMS_APP = "Number of EMS Apparatus"
C_TOTAL_APP = "Number of Total Apparatus"
C_ALARM_HOUR = "Alarm Date - Hour of Day"
C_ALARM_DOW = "Alarm Date - Day of Week"
C_ALARM_MONTH = "Alarm Date - Month of Year"

# --- Temporal Ordering ---
DOW_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ============================================================
# DATA (Hardcoded from Portage County PDF)
# ============================================================
PORTAGE_DATA = {
    "system": {
        "Area (sq mi)": 823,
        "Population": PORTAGE_POP,
        "Ambulance Providers": 4,
        "EMR Groups": 11,
        "EMS Level": "Paramedic (ALS)",
        "Funding Model": "County EMS Levy",
        "2024 Total Billable Calls": 3993,
        "2024 ALS Calls": 2542,
        "2024 BLS Calls": 1451,
        "2024 Gross Charges": 5841808,
        "2024 Revenue Collected": 2050116,
    },
    "call_volume_trend": {
        2014: {"ALS": 2398, "BLS": 717, "Total": 3219},
        2015: {"ALS": 2444, "BLS": 646, "Total": 3090},
        2016: {"ALS": 2180, "BLS": 705, "Total": 2885},
        2017: {"ALS": 2307, "BLS": 754, "Total": 3061},
        2018: {"ALS": 2016, "BLS": 837, "Total": 2853},
        2019: {"ALS": 1999, "BLS": 931, "Total": 3289},
        2020: {"ALS": 2239, "BLS": 1060, "Total": 3299},
        2021: {"ALS": 2618, "BLS": 958, "Total": 3576},
        2022: {"ALS": 2669, "BLS": 939, "Total": 3610},
        2023: {"ALS": 2843, "BLS": 978, "Total": 3821},
        2024: {"ALS": 2542, "BLS": 1451, "Total": 3993},
    },
    "revenue_trend": {
        2014: {"Charges": 3367301, "Revenue": 1651161},
        2015: {"Charges": 3587984, "Revenue": 1262976},
        2016: {"Charges": 3337591, "Revenue": 1418409},
        2017: {"Charges": 3168373, "Revenue": 1420885},
        2018: {"Charges": 2797730, "Revenue": 1284207},
        2019: {"Charges": 3844132, "Revenue": 1406912},
        2020: {"Charges": 4564068, "Revenue": 1428855},
        2021: {"Charges": 5042275, "Revenue": 1541664},
        2022: {"Charges": 4974374, "Revenue": 1762862},
        2023: {"Charges": 5174607, "Revenue": 1737124},
        2024: {"Charges": 5841808, "Revenue": 2050116},
    },
    "payor_mix_2024": {
        "Medicare": {"pct": 40.38, "calls": 2219, "charges": 3288008, "payments": 855299, "avg_per_trip": 389.82},
        "Private Insurance": {"pct": 8.72, "calls": 479, "charges": 665704, "payments": 243753, "avg_per_trip": 700.61},
        "Private Pay": {"pct": 42.66, "calls": 2344, "charges": 1087676, "payments": 134867, "avg_per_trip": 45.55},
        "Medicaid": {"pct": 6.72, "calls": 369, "charges": 485916, "payments": 120674, "avg_per_trip": 318.25},
        "Family Contract": {"pct": 1.53, "calls": 84, "charges": 117952, "payments": 66651, "avg_per_trip": 394.19},
    },
    "dispatch_2024": {
        "Ambulance Assist/Requests": 2795,
        "Total CAD/Calls for Service": 53166,
    }
}

# ============================================================
# FUNCTIONS
# ============================================================

def load_jefferson_data():
    """Loads and consolidates all Jefferson County call data from Excel files."""
    print("=" * 70)
    print("LOADING JEFFERSON COUNTY MUNICIPAL EMS DATA")
    print("=" * 70)

    jeff_files = sorted(glob.glob(os.path.join(CALL_DATA_DIR, "*.xlsx")))
    if not jeff_files:
        print(f"ERROR: No Excel files found in {CALL_DATA_DIR}")
        return None, None

    all_jeff = []
    dept_summary = []

    for f in jeff_files:
        name = os.path.basename(f).replace("Copy of 2024 EMS Workgroup - ", "").replace(".xlsx", "")
        df = pd.read_excel(f, sheet_name=0, engine="openpyxl")
        df[C_MUNI] = name
        all_jeff.append(df)

        # Summarize per department
        n_calls = len(df)
        ems_mask = df[C_INC_CAT].astype(str).str.strip().isin(["3"])
        n_ems = ems_mask.sum()

        # Response time
        resp_times = pd.to_numeric(df.get(C_RESP_TIME), errors="coerce").dropna()
        avg_resp = resp_times.mean() if not resp_times.empty else np.nan
        median_resp = resp_times.median() if not resp_times.empty else np.nan

        # EMS-specific response time
        ems_resp = pd.to_numeric(df.loc[ems_mask, C_RESP_TIME], errors="coerce").dropna() if C_RESP_TIME in df and not df.loc[ems_mask].empty else pd.Series()
        avg_ems_resp = ems_resp.mean() if not ems_resp.empty else np.nan
        median_ems_resp = ems_resp.median() if not ems_resp.empty else np.nan

        # Personnel
        avg_ems_pers = pd.to_numeric(df.get(C_EMS_PERS), errors="coerce").mean()

        dept_summary.append({
            C_MUNI: name,
            "Total Calls": n_calls,
            "EMS Calls (Cat 3)": n_ems,
            "Non-EMS Calls": n_calls - n_ems,
            "Avg Response Time (min)": round(avg_resp, 1) if not np.isnan(avg_resp) else None,
            "Median Response Time (min)": round(median_resp, 1) if not np.isnan(median_resp) else None,
            "Avg EMS Response Time (min)": round(avg_ems_resp, 1) if not np.isnan(avg_ems_resp) else None,
            "Median EMS Response Time (min)": round(median_ems_resp, 1) if not np.isnan(median_ems_resp) else None,
            "Avg EMS Personnel per Call": round(avg_ems_pers, 1) if not np.isnan(avg_ems_pers) else None,
        })

    dept_df = pd.DataFrame(dept_summary)
    jeff_combined = pd.concat(all_jeff, ignore_index=True)

    print("\nJefferson County - Municipal Breakdown:")
    print(dept_df.to_string(index=False))
    print(f"\nTotal Jefferson County Calls (all types): {len(jeff_combined)}")
    return jeff_combined, dept_df


def main():
    """Main execution function."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Load Jefferson County Data
    jeff_combined, dept_df = load_jefferson_data()
    if jeff_combined is None:
        return

    jeff_ems_mask = jeff_combined[C_INC_CAT].astype(str).str.strip().isin(["3"])
    jeff_ems = jeff_combined[jeff_ems_mask]

    jeff_total_calls = len(jeff_combined)
    jeff_ems_calls = len(jeff_ems)

    resp_all = pd.to_numeric(jeff_combined[C_RESP_TIME], errors="coerce").dropna()
    jeff_avg_resp_all = resp_all.mean()
    jeff_median_resp_all = resp_all.median()

    resp_ems = pd.to_numeric(jeff_ems[C_RESP_TIME], errors="coerce").dropna()
    jeff_avg_resp_ems = resp_ems.mean()
    jeff_median_resp_ems = resp_ems.median()

    jeff_call_types = jeff_combined.groupby(C_INC_CAT_DESC).size().sort_values(ascending=False)
    jeff_hourly = jeff_combined[C_ALARM_HOUR].value_counts().sort_index()
    jeff_dow = jeff_combined[C_ALARM_DOW].value_counts().reindex(DOW_ORDER, fill_value=0)
    jeff_monthly = jeff_combined[C_ALARM_MONTH].value_counts().reindex(MONTH_ORDER, fill_value=0)
    jeff_avg_ems_pers = pd.to_numeric(jeff_combined[C_EMS_PERS], errors="coerce").mean()
    jeff_avg_total_pers = pd.to_numeric(jeff_combined[C_TOTAL_PERS], errors="coerce").mean()
    jeff_avg_ems_app = pd.to_numeric(jeff_combined[C_EMS_APP], errors="coerce").mean()
    jeff_avg_total_app = pd.to_numeric(jeff_combined[C_TOTAL_APP], errors="coerce").mean()
    jeff_ems_types = jeff_ems[C_INC_DESC].value_counts().head(15)

    portage_system = PORTAGE_DATA['system']
    portage_system["Collection Rate"] = round(portage_system['2024 Revenue Collected'] / portage_system['2024 Gross Charges'] * 100, 1)
    portage_system["Avg Revenue per Billable Call"] = round(portage_system['2024 Revenue Collected'] / portage_system['2024 Total Billable Calls'], 2)

    print(f"Population: {PORTAGE_POP:,}")
    print(f"Area: {portage_system['Area (sq mi)']} sq mi")
    print(f"System: Countywide under Sheriff's Office (since 2018)")
    print(f"Ambulance Providers: {portage_system['Ambulance Providers']}")
    print(f"EMR Groups: {portage_system['EMR Groups']}")
    print(f"EMS Level: {portage_system['EMS Level']}")
    print(f"\n2024 Billable Call Volume: {portage_system['2024 Total Billable Calls']:,}")
    print(f"  ALS: {portage_system['2024 ALS Calls']:,}")
    print(f"  BLS: {portage_system['2024 BLS Calls']:,}")
    print(f"\n2024 Financial:")
    print(f"  Gross Charges: ${portage_system['2024 Gross Charges']:,.0f}")
    print(f"  Revenue Collected: ${portage_system['2024 Revenue Collected']:,.0f}")
    print(f"  Collection Rate: {portage_system['Collection Rate']}%")
    print(f"  Avg Revenue per Billable Call: ${portage_system['Avg Revenue per Billable Call']:,.2f}")

    # 4. Build Comparison Table
    print("\n" + "=" * 70)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 70)

    comparison = {
        "Metric": [
            "Population (est.)", "Land Area (sq mi)", "Population Density (per sq mi)",
            "Number of EMS Providers", "EMS Model", "Funding Model", "Total Calls (2024)",
            "EMS/Rescue Calls (2024)", "Calls per 1,000 Population", "EMS Calls per 1,000 Population",
            "Avg Response Time - All (min)", "Median Response Time - All (min)",
            "Avg Response Time - EMS (min)", "Median Response Time - EMS (min)",
            "Avg EMS Personnel per Call", "Avg Total Personnel per Call", "Avg EMS Apparatus per Call",
        ],
        "Portage County (2024)": [
            f"{PORTAGE_POP:,}", f"{portage_system['Area (sq mi)']}", f"{PORTAGE_POP / portage_system['Area (sq mi)']:.1f}",
            f"{portage_system['Ambulance Providers']} ambulance + {portage_system['EMR Groups']} EMR groups",
            "Countywide (Sheriff's Office)", portage_system['Funding Model'],
            f"{portage_system['2024 Total Billable Calls']:,}",
            f"{portage_system['2024 ALS Calls'] + portage_system['2024 BLS Calls']:,} (billable)",
            f"{portage_system['2024 Total Billable Calls'] / PORTAGE_POP * 1000:.1f}",
            f"{portage_system['2024 Total Billable Calls'] / PORTAGE_POP * 1000:.1f} (billable)",
            "N/A (not in report)", "N/A (not in report)", "N/A (not in report)", "N/A (not in report)",
            "N/A (not in report)", "N/A (not in report)", "N/A (not in report)",
        ],
        "Jefferson County (Consolidated, 2024)": [
            f"{JEFF_POP:,}", "583", f"{JEFF_POP / 583:.1f}", "14 municipal providers",
            "Fragmented Municipal", "Per capita / Equalized value contracts",
            f"{jeff_total_calls:,}", f"{jeff_ems_calls:,}",
            f"{jeff_total_calls / JEFF_POP * 1000:.1f}", f"{jeff_ems_calls / JEFF_POP * 1000:.1f}",
            f"{jeff_avg_resp_all:.1f}", f"{jeff_median_resp_all:.1f}", f"{jeff_avg_resp_ems:.1f}",
            f"{jeff_median_resp_ems:.1f}", f"{jeff_avg_ems_pers:.1f}", f"{jeff_avg_total_pers:.1f}",
            f"{jeff_avg_ems_app:.1f}",
        ],
    }
    comp_df = pd.DataFrame(comparison)
    print(comp_df.to_string(index=False))

    # 5. Response Time Analysis
    print("\n" + "=" * 70)
    print("JEFFERSON COUNTY - RESPONSE TIME BY MUNICIPALITY")
    print("=" * 70)
    resp_by_muni = dept_df[[C_MUNI, "Total Calls", "EMS Calls (Cat 3)",
                            "Avg Response Time (min)", "Median Response Time (min)",
                            "Avg EMS Response Time (min)", "Median EMS Response Time (min)"]].copy()
    resp_by_muni = resp_by_muni.sort_values("Total Calls", ascending=False)
    print(resp_by_muni.to_string(index=False))

    # 6. Generate Visualizations
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS...")
    print("=" * 70)

    plt.style.use("seaborn-v0_8-whitegrid")
    colors_portage = "#2196F3"
    colors_jefferson = "#FF9800"

    # --- Figure 1: Call Volume Comparison ---
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Portage County vs Jefferson County EMS Comparison (2024)", fontsize=16, fontweight="bold")

    # 1a: Total call volume bar comparison
    ax = axes[0, 0]
    categories = ["Total Calls", "EMS/Rescue Calls"]
    portage_vals = [portage_system["2024 Total Billable Calls"], portage_system["2024 Total Billable Calls"]]
    jeff_vals = [jeff_total_calls, jeff_ems_calls]
    x = np.arange(len(categories))
    w = 0.35
    ax.bar(x - w/2, portage_vals, w, label="Portage County", color=colors_portage, edgecolor="white")
    ax.bar(x + w/2, jeff_vals, w, label="Jefferson County", color=colors_jefferson, edgecolor="white")
    ax.set_ylabel("Number of Calls")
    ax.set_title("Call Volume Comparison (2024)")
    ax.set_xticks(x, labels=[c.replace(" ", "\n") for c in categories])
    ax.legend()
    for i, (p, j) in enumerate(zip(portage_vals, jeff_vals)):
        ax.text(i - w/2, p + 50, f"{p:,}", ha="center", va="bottom", fontsize=9)
        ax.text(i + w/2, j + 50, f"{j:,}", ha="center", va="bottom", fontsize=9)

    # 1b: Calls per 1,000 population
    ax = axes[0, 1]
    portage_pc = [portage_system["2024 Total Billable Calls"] / PORTAGE_POP * 1000]
    jeff_pc = [jeff_total_calls / JEFF_POP * 1000]
    jeff_ems_pc = [jeff_ems_calls / JEFF_POP * 1000]
    bars = ax.bar(
        ["Portage\n(Billable Calls)", "Jefferson\n(All Calls)", "Jefferson\n(EMS Only)"],
        [portage_pc[0], jeff_pc[0], jeff_ems_pc[0]],
        color=[colors_portage, colors_jefferson, "#E65100"],
        edgecolor="white",
    )
    ax.set_ylabel("Calls per 1,000 Population")
    ax.set_title("Call Rate per Capita (2024)")
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=10)

    # 1c: Jefferson County calls by municipality
    ax = axes[1, 0]
    muni_data = dept_df.sort_values("Total Calls", ascending=True)
    bars = ax.barh(muni_data[C_MUNI], muni_data["Total Calls"], color=colors_jefferson, edgecolor="white")
    ax.barh(muni_data[C_MUNI], muni_data["EMS Calls (Cat 3)"], color="#E65100", edgecolor="white", alpha=0.7)
    ax.set_xlabel("Number of Calls")
    ax.set_title("Jefferson County - Calls by Municipality (2024)")
    ax.legend(["Total Calls", "EMS Calls"], loc="lower right")
    for bar, total in zip(bars, muni_data["Total Calls"]):
        ax.text(bar.get_width() + 20, bar.get_y() + bar.get_height()/2,
                f"{total:,}", ha="left", va="center", fontsize=8)

    # 1d: Portage County call volume trend
    ax = axes[1, 1]
    years = list(PORTAGE_DATA['call_volume_trend'].keys())
    totals = [PORTAGE_DATA['call_volume_trend'][y]["Total"] for y in years]
    als = [PORTAGE_DATA['call_volume_trend'][y]["ALS"] for y in years]
    bls = [PORTAGE_DATA['call_volume_trend'][y]["BLS"] for y in years]
    ax.plot(years, totals, "o-", color=colors_portage, linewidth=2, label="Total")
    ax.plot(years, als, "s--", color="#1565C0", linewidth=1.5, label="ALS")
    ax.plot(years, bls, "^--", color="#64B5F6", linewidth=1.5, label="BLS")
    ax.set_xlabel("Year")
    ax.set_ylabel("Billable Calls")
    ax.set_title("Portage County - Call Volume Trend (2014-2024)")
    ax.legend()
    ax.set_xticks(years)
    ax.set_xticklabels([str(y) for y in years], rotation=45, ha="right")
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_call_volume_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 01_call_volume_comparison.png")

    # --- Figure 2: Response Time Analysis (Jefferson County) ---
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Jefferson County - Response Time Analysis (2024)", fontsize=16, fontweight="bold")

    # 2a: Response time by municipality
    ax = axes[0, 0]
    rt_data = dept_df.dropna(subset=["Avg EMS Response Time (min)"]).sort_values("Avg EMS Response Time (min)", ascending=True)
    bars = ax.barh(rt_data[C_MUNI], rt_data["Avg EMS Response Time (min)"], color=colors_jefferson, edgecolor="white")
    ax.set_xlabel("Average EMS Response Time (minutes)")
    ax.set_title("Average EMS Response Time by Municipality")
    ax.axvline(x=jeff_avg_resp_ems, color="red", linestyle="--", label=f"County Avg: {jeff_avg_resp_ems:.1f} min")
    ax.legend()
    for bar, val in zip(bars, rt_data["Avg EMS Response Time (min)"]):
        if val is not None:
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                    f"{val:.1f}", ha="left", va="center", fontsize=9)

    # 2b: Response time distribution (histogram)
    ax = axes[0, 1]
    resp_all_vals = pd.to_numeric(jeff_combined[C_RESP_TIME], errors="coerce").dropna()
    resp_all_vals = resp_all_vals[resp_all_vals <= 60]  # cap at 60 min for viz
    ax.hist(resp_all_vals, bins=30, color=colors_jefferson, edgecolor="white", alpha=0.7, label="All Calls")
    resp_ems_vals = pd.to_numeric(jeff_ems[C_RESP_TIME], errors="coerce").dropna()
    resp_ems_vals = resp_ems_vals[resp_ems_vals <= 60]
    ax.hist(resp_ems_vals, bins=30, color="#E65100", edgecolor="white", alpha=0.6, label="EMS Calls")
    ax.set_xlabel("Response Time (minutes)")
    ax.set_ylabel("Frequency")
    ax.set_title("Response Time Distribution")
    ax.legend()
    ax.axvline(x=jeff_avg_resp_all, color="orange", linestyle="--", alpha=0.8)
    ax.axvline(x=jeff_avg_resp_ems, color="red", linestyle="--", alpha=0.8)

    # 2c: Response time by hour of day
    ax = axes[1, 0]
    jeff_combined["resp_min"] = pd.to_numeric(jeff_combined[C_RESP_TIME], errors="coerce")
    hourly_resp = jeff_combined.groupby(C_ALARM_HOUR)["resp_min"].mean()
    hourly_resp.index = hourly_resp.index.astype(int)
    hourly_resp = hourly_resp.sort_index()
    ax.plot(hourly_resp.index, hourly_resp.values, "o-", color=colors_jefferson, linewidth=2)
    ax.fill_between(hourly_resp.index, hourly_resp.values, alpha=0.2, color=colors_jefferson)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Average Response Time (minutes)")
    ax.set_title("Average Response Time by Hour of Day")
    ax.set_xticks(range(0, 24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)

    # 2d: Response time percentiles by municipality
    ax = axes[1, 1]
    pct_data = []
    for name, group in jeff_combined.groupby(C_MUNI):
        rt = pd.to_numeric(group[C_RESP_TIME], errors="coerce").dropna()
        if len(rt) > 5:
            pct_data.append({
                C_MUNI: name,
                "P50": rt.quantile(0.5),
                "P75": rt.quantile(0.75),
                "P90": rt.quantile(0.90),
            })
    pct_df = pd.DataFrame(pct_data).sort_values("P90", ascending=True)
    x = np.arange(len(pct_df))
    w = 0.25
    ax.barh(x - w, pct_df["P50"], w, label="50th percentile", color="#4CAF50", edgecolor="white")
    ax.barh(x, pct_df["P75"], w, label="75th percentile", color=colors_jefferson, edgecolor="white")
    ax.barh(x + w, pct_df["P90"], w, label="90th percentile", color="#E65100", edgecolor="white")
    ax.set_yticks(x)
    ax.set_yticklabels(pct_df[C_MUNI], fontsize=8)
    ax.set_xlabel("Response Time (minutes)")
    ax.set_title("Response Time Percentiles by Municipality")
    ax.legend(loc="lower right")

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_response_time_analysis.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 02_response_time_analysis.png")

    # --- Figure 3: Call Patterns ---
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Jefferson County - Call Patterns (2024)", fontsize=16, fontweight="bold")

    # 3a: Call type distribution
    ax = axes[0, 0]
    top_types = jeff_call_types.head(7)
    colors_pie = plt.cm.Set2(np.linspace(0, 1, len(top_types)))
    wedges, texts, autotexts = ax.pie(
        top_types.values, labels=None, autopct="%1.1f%%",
        colors=colors_pie, startangle=90, pctdistance=0.85
    )
    ax.legend(
        [f"{t[:35]}..." if len(t) > 35 else t for t in top_types.index],
        loc="center left", bbox_to_anchor=(-0.3, 0.5), fontsize=7
    )
    ax.set_title("Call Type Distribution")

    # 3b: Hourly call volume
    ax = axes[0, 1]
    hours = range(24)
    jeff_hourly_reindex = jeff_hourly.reindex(hours, fill_value=0)
    ax.bar(hours, jeff_hourly_reindex.values, color=colors_jefferson, edgecolor="white")
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Number of Calls")
    ax.set_title("Calls by Hour of Day")
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=8)

    # 3c: Day of week
    ax = axes[1, 0]
    ax.bar(jeff_dow.index, jeff_dow.values, color=colors_jefferson, edgecolor="white")
    ax.set_xlabel("Day of Week")
    ax.set_ylabel("Number of Calls")
    ax.set_title("Calls by Day of Week")

    # 3d: Monthly volume
    ax = axes[1, 1]
    ax.bar(jeff_monthly.index, jeff_monthly.values, color=colors_jefferson, edgecolor="white")
    ax.set_xlabel("Month")
    ax.set_ylabel("Number of Calls")
    ax.set_title("Calls by Month")
    ax.set_xticklabels(MONTH_ORDER, rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_call_patterns.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 03_call_patterns.png")

    # --- Figure 4: Financial Comparison ---
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Portage County EMS - Financial Analysis (2024)", fontsize=16, fontweight="bold")

    # 4a: Charges vs Revenue trend
    ax = axes[0, 0]
    rev_years = list(PORTAGE_DATA['revenue_trend'].keys())
    charges = [PORTAGE_DATA['revenue_trend'][y]["Charges"] for y in rev_years]
    revenues = [PORTAGE_DATA['revenue_trend'][y]["Revenue"] for y in rev_years]
    ax.plot(rev_years, charges, "o-", color="#F44336", linewidth=2, label="Gross Charges")
    ax.plot(rev_years, revenues, "s-", color="#4CAF50", linewidth=2, label="Revenue Collected")
    ax.fill_between(rev_years, revenues, charges, alpha=0.1, color="red")
    ax.set_xlabel("Year")
    ax.set_ylabel("Dollars ($)")
    ax.set_title("Portage County - Charges vs Revenue (2014-2024)")
    ax.legend()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.set_xticks(rev_years)
    ax.set_xticklabels([str(y) for y in rev_years], rotation=45, ha="right")

    # 4b: Collection rate trend
    ax = axes[0, 1]
    coll_rates = [PORTAGE_DATA['revenue_trend'][y]["Revenue"] / PORTAGE_DATA['revenue_trend'][y]["Charges"] * 100 for y in rev_years]
    ax.bar(rev_years, coll_rates, color=colors_portage, edgecolor="white")
    ax.set_xlabel("Year")
    ax.set_ylabel("Collection Rate (%)")
    ax.set_title("Portage County - Collection Rate Trend")
    ax.set_ylim(0, 60)
    for yr, rate in zip(rev_years, coll_rates):
        ax.text(yr, rate + 1, f"{rate:.0f}%", ha="center", fontsize=8)
    ax.set_xticks(rev_years)
    ax.set_xticklabels([str(y) for y in rev_years], rotation=45, ha="right")

    # 4c: 2024 Payor mix
    ax = axes[1, 0]
    payors = list(PORTAGE_DATA['payor_mix_2024'].keys())
    payor_pcts = [PORTAGE_DATA['payor_mix_2024'][p]["pct"] for p in payors]
    payor_colors = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#607D8B"]
    wedges, texts, autotexts = ax.pie(
        payor_pcts, labels=payors, autopct="%1.1f%%",
        colors=payor_colors, startangle=90
    )
    ax.set_title("Portage County - 2024 Payor Mix")

    # 4d: Average collected per trip by payor
    ax = axes[1, 1]
    avg_per_trip = [PORTAGE_DATA['payor_mix_2024'][p]["avg_per_trip"] for p in payors]
    bars = ax.bar(payors, avg_per_trip, color=payor_colors, edgecolor="white")
    ax.set_ylabel("Average Collected per Trip ($)")
    ax.set_title("Portage County - Avg Revenue per Trip by Payor (2024)")
    ax.set_xticklabels(payors, rotation=30, ha="right")
    for bar, val in zip(bars, avg_per_trip):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                f"${val:,.0f}", ha="center", fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "04_financial_analysis.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 04_financial_analysis.png")

    # --- Figure 5: System Structure Comparison ---
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle("System Structure Comparison", fontsize=16, fontweight="bold")

    # 5a: Calls share by municipality (Jefferson)
    ax = axes[0]
    muni_shares = dept_df.set_index(C_MUNI)["Total Calls"].sort_values(ascending=False)
    top5 = muni_shares.head(5)
    other = pd.Series({"Other (9 depts)": muni_shares.iloc[5:].sum()})
    plot_data = pd.concat([top5, other])
    colors_share = plt.cm.Set3(np.linspace(0, 1, len(plot_data)))
    wedges, texts, autotexts = ax.pie(
        plot_data.values, labels=plot_data.index, autopct="%1.1f%%",
        colors=colors_share, startangle=90
    )
    ax.set_title("Jefferson County\nCall Distribution by Provider")

    # 5b: Key metrics comparison as table
    ax = axes[1]
    ax.axis("off")
    key_metrics = [
        ["Metric", "Portage County", "Jefferson County"],
        ["Population", f"{PORTAGE_POP:,}", f"{JEFF_POP:,}"],
        ["Area (sq mi)", "823", "583"],
        ["Pop. Density (/sq mi)", f"{portage_system['Population']/portage_system['Area (sq mi)']:.0f}", f"{JEFF_POP/583:.0f}"],
        ["EMS Model", "Countywide", "14 Providers"],
        ["Funding", "County Levy", "Municipal Contracts"],
        ["2024 Total Calls", f"{portage_system['2024 Total Billable Calls']:,}", f"{jeff_total_calls:,}"],
        ["Calls per 1K Pop.", f"{portage_system['2024 Total Billable Calls']/PORTAGE_POP*1000:.1f}", f"{jeff_total_calls/JEFF_POP*1000:.1f}"],
        ["EMS Calls per 1K Pop.", f"{portage_system['2024 Total Billable Calls']/PORTAGE_POP*1000:.1f}", f"{jeff_ems_calls/JEFF_POP*1000:.1f}"],
        ["2024 Charges", f"${portage_system['2024 Gross Charges']:,.0f}", "N/A"],
        ["2024 Revenue", f"${portage_system['2024 Revenue Collected']:,.0f}", "N/A"],
        ["Revenue/Call", f"${portage_system['Avg Revenue per Billable Call']:,.0f}", "N/A"],
        ["Avg Resp. Time (EMS)", "N/A", f"{jeff_avg_resp_ems:.1f} min"],
        ["Median Resp. Time (EMS)", "N/A", f"{jeff_median_resp_ems:.1f} min"],
    ]

    table = ax.table(cellText=key_metrics[1:], colLabels=key_metrics[0],
                     cellLoc="center", loc="center",
                     colWidths=[0.35, 0.3, 0.3])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.1, 1.5)
    # Header styling
    for j in range(3):
        table[0, j].set_facecolor("#333333")
        table[0, j].set_text_props(color="white", fontweight="bold")
    # Alternate row colors
    for i in range(1, len(key_metrics)):
        for j in range(3):
            if i % 2 == 0:
                table[i, j].set_facecolor("#f0f0f0")
    ax.set_title("Key Metrics Summary", pad=20)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "05_system_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 05_system_comparison.png")

    # 7. Save Data to Excel
    print("\n" + "=" * 70)
    print("SAVING DATA TO EXCEL...")
    print("=" * 70)

    output_xlsx = os.path.join(OUTPUT_DIR, "county_ems_comparison_data.xlsx")
    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        comp_df.to_excel(writer, sheet_name="Comparison", index=False)
        dept_df.to_excel(writer, sheet_name="Jeff_Municipal_Breakdown", index=False)
        jeff_call_types.reset_index().rename(columns={"index": "Call Type", 0: "Count"}).to_excel(writer, sheet_name="Jeff_Call_Types", index=False)
        jeff_ems_types.reset_index().to_excel(writer, sheet_name="Jeff_EMS_Incident_Types", index=False)

        portage_vol_df = pd.DataFrame(PORTAGE_DATA['call_volume_trend']).T
        portage_vol_df.index.name = "Year"
        portage_vol_df.to_excel(writer, sheet_name="Portage_Call_Volume_Trend")

        portage_rev_df = pd.DataFrame(PORTAGE_DATA['revenue_trend']).T
        portage_rev_df.index.name = "Year"
        portage_rev_df["Collection_Rate_Pct"] = portage_rev_df["Revenue"] / portage_rev_df["Charges"] * 100
        portage_rev_df.to_excel(writer, sheet_name="Portage_Revenue_Trend")

        payor_df = pd.DataFrame(PORTAGE_DATA['payor_mix_2024']).T
        payor_df.index.name = "Payor"
        payor_df.to_excel(writer, sheet_name="Portage_Payor_Mix_2024")

        if 'pct_df' in locals() and pct_df is not None:
            pct_df.to_excel(writer, sheet_name="Jeff_Response_Percentiles", index=False)

    print(f"  Saved: {output_xlsx}")

    # 8. Summary
    print("\n" + "=" * 70)
    print("ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"""
    KEY FINDINGS:

    1. SYSTEM STRUCTURE
       - Portage County operates a UNIFIED countywide EMS system under the
         Sheriff's Office with {portage_system['Ambulance Providers']} ambulance providers and {portage_system['EMR Groups']} EMR groups.
       - Jefferson County has a FRAGMENTED system with 14 separate municipal
         EMS providers, each with their own contracts and service areas.

    2. CALL VOLUME (2024)
       - Portage County: {portage_system['2024 Total Billable Calls']:,} billable ambulance calls
         ({portage_system['2024 Total Billable Calls']/PORTAGE_POP*1000:.1f} per 1,000 pop)
       - Jefferson County: {jeff_total_calls:,} total calls ({jeff_ems_calls:,} EMS/rescue)
         ({jeff_total_calls/JEFF_POP*1000:.1f} total / {jeff_ems_calls/JEFF_POP*1000:.1f} EMS per 1,000 pop)

    3. RESPONSE TIMES
       - Portage County: Not reported in annual report
       - Jefferson County (consolidated):
         * Avg EMS Response Time: {jeff_avg_resp_ems:.1f} minutes
         * Median EMS Response Time: {jeff_median_resp_ems:.1f} minutes
         * Significant variation across municipalities

    4. FINANCIAL (Portage County only - Jefferson data not available)
       - 2024 Gross Charges: ${portage_system['2024 Gross Charges']:,.0f}
       - 2024 Revenue Collected: ${portage_system['2024 Revenue Collected']:,.0f}
       - Collection Rate: {portage_system['Collection Rate']}%
       - Avg Revenue per Call: ${portage_system['Avg Revenue per Billable Call']:,.2f}
       - 40.4% Medicare, 42.7% Private Pay, 8.7% Private Insurance

    5. LARGEST JEFFERSON COUNTY PROVIDERS (by call volume):
    """)

    for _, row in dept_df.sort_values("Total Calls", ascending=False).head(5).iterrows():
        pct = row["Total Calls"] / jeff_total_calls * 100
        print(f"   - {row[C_MUNI]}: {row['Total Calls']:,} calls ({pct:.1f}%)")

    print(f"""
    6. DATA LIMITATIONS
       - Portage County data is from a PDF annual report with aggregate metrics.
         Individual call-level data (response times, etc.) is NOT available.
       - Jefferson County data is incident-level NFIRS data that includes both
         fire and EMS calls. Financial data is NOT included.
       - Direct financial comparison is not possible with available data.
       - Jefferson County population is estimated at {JEFF_POP:,}.

    OUTPUT FILES:
      - {OUTPUT_DIR / "01_call_volume_comparison.png"}
      - {OUTPUT_DIR / "02_response_time_analysis.png"}
      - {OUTPUT_DIR / "03_call_patterns.png"}
      - {OUTPUT_DIR / "04_financial_analysis.png"}
      - {OUTPUT_DIR / "05_system_comparison.png"}
      - {output_xlsx}
    """)

if __name__ == "__main__":
    main()
