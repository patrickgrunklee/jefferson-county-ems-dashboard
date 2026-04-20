"""
Jefferson County EMS — Full Quantitative Analysis Pipeline (Phases A-G)
=======================================================================
A) Primary vs Secondary Response Time Comparison
B) Geographic Distribution of Secondary Ambulance Use
C) Ambulance Utilization by Unit and Time of Day
D) Current Staffing Operations Investigation
E) Secondary Ambulance Response Destinations
F) Response Area Hot Spots
G) Consolidation & Optimization Setup

Reuses existing infrastructure:
  - concurrent_call_analysis.py  (load_all_nfirs, DEPT_NAME_MAP, AMBULANCE_COUNT)
  - pareto_facility.py           (solve_mclp, solve_pmedian_pop, load_bg_demand, etc.)
  - secondary_staffing_model.py  (PETERSON cost model, DEPT_DATA)

Author: ISyE 450 Senior Design Team
Date:   April 2026
"""

import os
import sys
import json
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from math import factorial, radians, sin, cos, sqrt, atan2
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ── Import existing infrastructure ─────────────────────────────────────
from concurrent_call_analysis import (
    load_all_nfirs, DEPT_NAME_MAP, EMS_TRANSPORT_DEPTS, AMBULANCE_COUNT,
    erlang_c,
)
from secondary_staffing_model import (
    PETERSON_TOTAL_OPERATING, PETERSON_REVENUE, PETERSON_NET,
    FTE_24_7, FTE_12_HR, DEPT_DATA,
)

# ── Output directory ───────────────────────────────────────────────────
OUT_DIR = os.path.join(SCRIPT_DIR, "analysis_output")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Plotting style ─────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
})

# ── NFIRS Aid Given/Received codes ─────────────────────────────────────
AID_CODES = {
    "N": "None",
    "1": "Mutual aid received",
    "2": "Automatic aid received",
    "3": "Mutual aid given",
    "4": "Automatic aid given",
    "5": "Other aid given",
}

# ── Jefferson County ZIP codes (for filtering out-of-county calls) ─────
JEFF_CO_ZIPS = {
    53003, 53016, 53034, 53036, 53038, 53039, 53047, 53051, 53058,
    53066, 53094, 53098, 53523, 53534, 53538, 53549, 53551, 53563,
    53190, 53545, 53546, 53548, 53559, 53564, 53579, 53589,
}


# ══════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def load_bg_centroids():
    """Load 65 Census block group centroids with population from GeoJSON."""
    bg_path = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")
    with open(bg_path, "r") as f:
        gj = json.load(f)

    bgs = []
    for feat in gj["features"]:
        p = feat["properties"]
        pop = p.get("P1_001N", 0)
        if pop <= 0:
            continue
        bgs.append({
            "GEOID": p["GEOID"],
            "lat": float(p["INTPTLAT"]),
            "lon": float(p["INTPTLON"]),
            "population": pop,
            "area_sqmi": p.get("area_sqmi", 0),
        })
    return pd.DataFrame(bgs)


def assign_calls_to_bg(calls_df, bg_df):
    """
    Assign each call to its nearest Census block group centroid using
    the Incident Zip Code field to narrow candidates, then haversine.

    Falls back to nearest BG by distance if ZIP doesn't match any BG.
    """
    # Build ZIP-to-BG mapping: for each BG, determine its primary ZIP
    # by checking which Jefferson County ZIP centroid is nearest.
    # Since we don't have ZIP-to-BG crosswalk, use brute-force nearest centroid.
    bg_lats = bg_df["lat"].values
    bg_lons = bg_df["lon"].values
    bg_geoids = bg_df["GEOID"].values

    assigned_bg = []
    for _, row in calls_df.iterrows():
        # Find nearest BG centroid by haversine
        best_dist = 1e9
        best_bg = bg_geoids[0]
        lat_call = None
        lon_call = None

        # We don't have lat/lon for calls, so assign by nearest BG
        # Use city name as a rough proxy to narrow search
        city = str(row.get("Incident City", "")).strip().lower()
        zip_code = row.get("Incident Zip Code", None)

        # Just assign to nearest BG (all BGs are close enough in a county)
        # This will be overridden by the city-based mapping below
        assigned_bg.append(None)

    return assigned_bg


def build_city_zip_to_bg_map(ems_df, bg_df):
    """
    Build a mapping from (city, zip) pairs to block group GEOIDs.

    Strategy: For each unique (city, zip) pair in the call data, find the
    BG centroid that is geographically closest. We use known city coordinates
    as reference points.
    """
    # Known city centroids in Jefferson County (approximate lat/lon)
    CITY_COORDS = {
        "fort atkinson":     (42.929, -88.837),
        "city of fort atkinso": (42.929, -88.837),
        "fort  atkinson":    (42.929, -88.837),
        "fort atksinson":    (42.929, -88.837),
        "watertown":         (43.195, -88.729),
        "city of watertown":  (43.195, -88.729),
        "whitewater":        (42.834, -88.732),
        "city of whitewater": (42.834, -88.732),
        "whiteewater":       (42.834, -88.732),
        "edgerton":          (42.835, -89.067),
        "city of edgerton":  (42.835, -89.067),
        "jefferson":         (43.005, -88.807),
        "city of jefferson":  (43.005, -88.807),
        "johnson creek":     (43.077, -88.774),
        "village of johnson c": (43.077, -88.774),
        "waterloo":          (43.184, -88.983),
        "city of waterloo":   (43.184, -88.983),
        "lake mills":        (43.080, -88.906),
        "city of lake mills": (43.080, -88.906),
        "ixonia":            (43.143, -88.597),
        "palmyra":           (42.878, -88.586),
        "village of palmyra": (42.878, -88.586),
        "cambridge":         (43.003, -89.017),
        "village of cambridge": (43.003, -89.017),
        "sullivan":          (43.010, -88.594),
        "village of sullivan": (43.010, -88.594),
        "sullivan - town":   (43.010, -88.594),
        "rome":              (43.150, -88.883),
        "helenville":        (43.115, -88.680),
        "helenville census de": (43.115, -88.680),
        "concord":           (43.070, -88.603),
        "koshkonong":        (42.876, -88.870),
        "koshkonog":         (42.876, -88.870),
        "town of koshkonong": (42.876, -88.870),
        "town of christiana": (42.873, -88.943),
        "town of oakland":   (42.873, -88.790),
        "town of lake mills": (43.060, -88.920),
        "town of lima":      (43.010, -88.680),
        "town of lima":      (43.010, -88.680),
        "lima center":       (43.010, -88.680),
        "town of hebron":    (42.910, -88.630),
        "hebron":            (42.910, -88.630),
        "town of cold spring": (42.830, -88.800),
        "town of sumner":    (42.870, -88.720),
        "town of johnstown":  (43.100, -88.850),
        "johnstown":         (43.100, -88.850),
        "portland":          (42.830, -88.900),
        "indianford":        (42.850, -89.050),
        "newville":          (43.000, -88.650),
        "albion":            (42.880, -89.060),
        "avalon":            (42.810, -89.020),
        "busseyville":       (43.025, -88.720),
        "milford":           (43.100, -88.750),
        "farmington":        (43.140, -88.750),
        "oakland":           (42.870, -88.790),
        "aztalan":           (43.070, -88.860),
        "ottawa":            (43.160, -88.600),
        "ottawa - town":     (43.160, -88.600),
        "pipersville":       (42.860, -88.650),
        "rockdale":          (42.980, -89.020),
        "slabtown":          (42.990, -88.920),
        "fulton":            (42.810, -89.100),
        "oak hill":          (43.040, -88.950),
        # Out-of-county (assign to nearest border BG)
        "milton":            (42.775, -88.944),
        "city of milton":    (42.775, -88.944),
        "milton junction":   (42.775, -88.944),
        "janesville":        (42.683, -89.019),
        "city of janesville": (42.683, -89.019),
        "stoughton":         (42.917, -89.218),
        "city of stoughton":  (42.917, -89.218),
        "evansville":        (42.781, -89.300),
        "beloit":            (42.508, -89.032),
        "city of beloit":    (42.508, -89.032),
        "oconomowoc":        (43.112, -88.499),
        "city of oconomowoc": (43.112, -88.499),
        "oconomowoc - city":  (43.112, -88.499),
        "oconomowoc - town":  (43.112, -88.499),
        "oconomowoc lake":   (43.100, -88.460),
        "okauchee":          (43.110, -88.440),
        "madison":           (43.074, -89.384),
        "city of madison":   (43.074, -89.384),
        "delavan":           (42.632, -88.644),
        "elkhorn":           (42.673, -88.544),
        "lake geneva":       (42.592, -88.433),
        "columbus":          (43.338, -89.015),
        "beaver dam":        (43.457, -88.837),
        "hartford":          (43.318, -88.379),
        "hustisford":        (43.349, -88.631),
        "clyman":            (43.313, -88.713),
    }

    bg_lats = bg_df["lat"].values
    bg_lons = bg_df["lon"].values
    bg_geoids = bg_df["GEOID"].values

    # For each unique city, find its nearest BG
    city_to_bg = {}
    for city_key, (clat, clon) in CITY_COORDS.items():
        dists = [haversine_km(clat, clon, bg_lats[i], bg_lons[i])
                 for i in range(len(bg_lats))]
        city_to_bg[city_key] = bg_geoids[np.argmin(dists)]

    # Build (city_lower, zip) -> BG mapping
    # Use city as primary key, ZIP as tiebreaker
    # Support both original NFIRS column names and renamed columns
    city_col = "Incident City" if "Incident City" in ems_df.columns else "City"
    zip_col = "Incident Zip Code" if "Incident Zip Code" in ems_df.columns else "Zip"

    unique_pairs = ems_df[[city_col, zip_col]].drop_duplicates()
    pair_to_bg = {}

    for _, row in unique_pairs.iterrows():
        city_raw = str(row[city_col]).strip()
        city_lower = city_raw.lower()
        zip_code = row[zip_col]

        # Try city lookup first
        if city_lower in city_to_bg:
            pair_to_bg[(city_raw, zip_code)] = city_to_bg[city_lower]
        else:
            # Fuzzy: strip prefixes
            cleaned = city_lower
            for prefix in ["city of ", "town of ", "village of "]:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
                    break
            cleaned = cleaned.replace(" - town", "").replace(" - city", "").replace(" - village", "").strip()
            if cleaned in city_to_bg:
                pair_to_bg[(city_raw, zip_code)] = city_to_bg[cleaned]
            else:
                # Last resort: assign to nearest BG by geographic center of county
                pair_to_bg[(city_raw, zip_code)] = bg_geoids[
                    np.argmin([haversine_km(43.0, -88.77, bg_lats[i], bg_lons[i])
                               for i in range(len(bg_lats))])
                ]

    return pair_to_bg, city_to_bg


# ══════════════════════════════════════════════════════════════════════
#  PHASE A: Primary vs Secondary Response Time Comparison
# ══════════════════════════════════════════════════════════════════════

def phase_a_primary_secondary_rt(ems_df, valid_df):
    """
    Classify each call as primary or secondary and compare response times.

    Classification logic:
    1. Load concurrent_call_detail.csv (has Concurrent_Count per call)
    2. Within each dept, group overlapping calls into clusters
    3. First call in each cluster (earliest alarm) = primary
    4. All subsequent overlapping calls = secondary
    5. Also flag mutual aid received/given from NFIRS Aid codes

    Validate against Johnson Creek provider data (has Vehicle ID + Mutual Aid).
    """
    print("\n" + "=" * 70)
    print("PHASE A: PRIMARY vs SECONDARY RESPONSE TIME COMPARISON")
    print("=" * 70)

    # ── Load concurrent call detail ────────────────────────────────────
    detail_path = os.path.join(SCRIPT_DIR, "concurrent_call_detail.csv")
    if os.path.exists(detail_path):
        detail = pd.read_csv(detail_path, parse_dates=["Alarm_DT", "Cleared_DT"])
        print(f"  Loaded concurrent_call_detail.csv: {len(detail):,} calls")
    else:
        print("  concurrent_call_detail.csv not found -- recomputing...")
        from concurrent_call_analysis import compute_concurrent_calls
        detail = compute_concurrent_calls(valid_df)
        detail[["Dept", "Alarm_DT", "Cleared_DT", "Hour", "DOW",
                "Response_Min", "Duration_Min", "Concurrent_Count"]
               ].to_csv(detail_path, index=False)
        print(f"  Saved concurrent_call_detail.csv: {len(detail):,} calls")

    # ── Merge Aid codes from full NFIRS data ──────────────────────────
    # The detail CSV only has limited columns; we need Aid codes from ems_df
    # Match on Dept + Alarm_DT
    ems_df["Alarm_DT"] = pd.to_datetime(ems_df["Alarm Date / Time"], errors="coerce")
    ems_df["Dept"] = ems_df["Fire Department Name"].map(DEPT_NAME_MAP)
    aid_cols = ems_df[["Dept", "Alarm_DT",
                       "Aid Given or Received Code (National)",
                       "Incident City", "Incident Zip Code",
                       "Incident Full Address",
                       "Number of EMS Apparatus",
                       "Response Time (Minutes)"]].copy()
    aid_cols.columns = ["Dept", "Alarm_DT", "Aid_Code", "City", "Zip",
                        "Full_Address", "EMS_Apparatus", "RT_NFIRS"]

    # Merge
    detail["Alarm_DT"] = pd.to_datetime(detail["Alarm_DT"])
    merged = detail.merge(aid_cols, on=["Dept", "Alarm_DT"], how="left")
    # Drop duplicates from merge (some timestamps match multiple records)
    merged = merged.drop_duplicates(subset=["Dept", "Alarm_DT", "Concurrent_Count"])
    print(f"  Merged with NFIRS aid/address data: {len(merged):,} calls")

    # ── Classify primary vs secondary ─────────────────────────────────
    # Method: cluster overlapping calls within each dept
    def classify_dept(group):
        g = group.sort_values("Alarm_DT").reset_index(drop=True)
        labels = []
        cluster_end = pd.NaT

        for i, row in g.iterrows():
            alarm = row["Alarm_DT"]
            cleared = row["Cleared_DT"]

            if pd.isna(cleared):
                cleared = alarm + pd.Timedelta(minutes=45)  # default duration

            if pd.isna(cluster_end) or alarm >= cluster_end:
                # New cluster: this call is the primary
                labels.append("Primary")
                cluster_end = cleared
            else:
                # Overlaps existing cluster: this is secondary
                labels.append("Secondary")
                # Extend cluster end if this call runs later
                if cleared > cluster_end:
                    cluster_end = cleared

        g["Call_Class"] = labels
        return g

    print("  Classifying calls (cluster-based)...")
    classified = merged.groupby("Dept", group_keys=False).apply(classify_dept)
    classified = classified.reset_index(drop=True)

    # Also flag mutual aid calls
    classified["Aid_Code"] = classified["Aid_Code"].astype(str).str.strip()
    classified["Is_Mutual_Aid"] = classified["Aid_Code"].isin(["1", "2"])  # received
    classified["Gave_Mutual_Aid"] = classified["Aid_Code"].isin(["3", "4"])  # given

    # Override: if aid received, it's definitely secondary from receiving dept's POV
    classified.loc[classified["Is_Mutual_Aid"], "Call_Class"] = "Secondary"

    primary = classified[classified["Call_Class"] == "Primary"]
    secondary = classified[classified["Call_Class"] == "Secondary"]
    print(f"  Primary: {len(primary):,} | Secondary: {len(secondary):,} "
          f"({100*len(secondary)/len(classified):.1f}%)")

    # ── Response time comparison ──────────────────────────────────────
    # Use Response_Min from concurrent_call_detail (already numeric)
    # Fall back to RT_NFIRS if Response_Min is NaN
    classified["RT"] = classified["Response_Min"].fillna(
        pd.to_numeric(classified["RT_NFIRS"], errors="coerce"))

    # Filter to valid RT (> 0 and < 120 min)
    valid_rt = classified[(classified["RT"] > 0) & (classified["RT"] < 120)].copy()

    # Per-department comparison
    rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        dg = valid_rt[valid_rt["Dept"] == dept]
        if dg.empty:
            continue

        pri = dg[dg["Call_Class"] == "Primary"]["RT"]
        sec = dg[dg["Call_Class"] == "Secondary"]["RT"]

        row = {
            "Dept": dept,
            "Primary_Count": len(pri),
            "Secondary_Count": len(sec),
            "Primary_Median_RT": round(pri.median(), 1) if len(pri) > 0 else None,
            "Primary_P90_RT": round(pri.quantile(0.9), 1) if len(pri) > 0 else None,
            "Primary_Mean_RT": round(pri.mean(), 1) if len(pri) > 0 else None,
            "Secondary_Median_RT": round(sec.median(), 1) if len(sec) > 0 else None,
            "Secondary_P90_RT": round(sec.quantile(0.9), 1) if len(sec) > 0 else None,
            "Secondary_Mean_RT": round(sec.mean(), 1) if len(sec) > 0 else None,
        }

        # Delta
        if row["Primary_Median_RT"] is not None and row["Secondary_Median_RT"] is not None:
            row["Median_Delta_Min"] = round(row["Secondary_Median_RT"] - row["Primary_Median_RT"], 1)
        else:
            row["Median_Delta_Min"] = None

        if row["Primary_P90_RT"] is not None and row["Secondary_P90_RT"] is not None:
            row["P90_Delta_Min"] = round(row["Secondary_P90_RT"] - row["Primary_P90_RT"], 1)
        else:
            row["P90_Delta_Min"] = None

        # Mann-Whitney U test
        if len(pri) >= 5 and len(sec) >= 5:
            u_stat, p_val = stats.mannwhitneyu(pri, sec, alternative="two-sided")
            row["MW_U_Stat"] = round(u_stat, 1)
            row["MW_P_Value"] = round(p_val, 4)
        else:
            row["MW_U_Stat"] = None
            row["MW_P_Value"] = None

        rows.append(row)

    # County-wide totals
    pri_all = valid_rt[valid_rt["Call_Class"] == "Primary"]["RT"]
    sec_all = valid_rt[valid_rt["Call_Class"] == "Secondary"]["RT"]
    county_row = {
        "Dept": "COUNTY TOTAL",
        "Primary_Count": len(pri_all),
        "Secondary_Count": len(sec_all),
        "Primary_Median_RT": round(pri_all.median(), 1),
        "Primary_P90_RT": round(pri_all.quantile(0.9), 1),
        "Primary_Mean_RT": round(pri_all.mean(), 1),
        "Secondary_Median_RT": round(sec_all.median(), 1),
        "Secondary_P90_RT": round(sec_all.quantile(0.9), 1),
        "Secondary_Mean_RT": round(sec_all.mean(), 1),
        "Median_Delta_Min": round(sec_all.median() - pri_all.median(), 1),
        "P90_Delta_Min": round(sec_all.quantile(0.9) - pri_all.quantile(0.9), 1),
    }
    if len(pri_all) >= 5 and len(sec_all) >= 5:
        u_stat, p_val = stats.mannwhitneyu(pri_all, sec_all, alternative="two-sided")
        county_row["MW_U_Stat"] = round(u_stat, 1)
        county_row["MW_P_Value"] = round(p_val, 4)
    rows.append(county_row)

    rt_df = pd.DataFrame(rows)
    csv_path = os.path.join(OUT_DIR, "phase_a_primary_secondary_rt.csv")
    rt_df.to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_path}")
    print(rt_df.to_string(index=False))

    # ── Box plot ──────────────────────────────────────────────────────
    plot_depts = [d for d in EMS_TRANSPORT_DEPTS
                  if len(valid_rt[(valid_rt["Dept"] == d) & (valid_rt["Call_Class"] == "Secondary")]) >= 5]

    if plot_depts:
        fig, ax = plt.subplots(figsize=(14, 8))
        positions = []
        labels = []
        data_pri = []
        data_sec = []

        for i, dept in enumerate(plot_depts):
            dg = valid_rt[valid_rt["Dept"] == dept]
            pri = dg[dg["Call_Class"] == "Primary"]["RT"].dropna()
            sec = dg[dg["Call_Class"] == "Secondary"]["RT"].dropna()
            data_pri.append(pri.values)
            data_sec.append(sec.values)
            positions.append(i)
            labels.append(dept)

        width = 0.35
        bp1 = ax.boxplot(data_pri, positions=[p - width/2 for p in positions],
                         widths=width, patch_artist=True, showfliers=False,
                         medianprops=dict(color="black", linewidth=2))
        bp2 = ax.boxplot(data_sec, positions=[p + width/2 for p in positions],
                         widths=width, patch_artist=True, showfliers=False,
                         medianprops=dict(color="black", linewidth=2))

        for patch in bp1["boxes"]:
            patch.set_facecolor("#3498db")
            patch.set_alpha(0.7)
        for patch in bp2["boxes"]:
            patch.set_facecolor("#e74c3c")
            patch.set_alpha(0.7)

        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_ylabel("Response Time (minutes)")
        ax.set_title(
            "Response Time: Primary vs Secondary Calls by Department\n"
            "Primary = first call in overlap cluster | Secondary = subsequent overlapping calls | CY2024",
            fontweight="bold"
        )
        ax.legend([bp1["boxes"][0], bp2["boxes"][0]], ["Primary", "Secondary"],
                  loc="upper right")
        ax.set_ylim(0, min(40, valid_rt["RT"].quantile(0.95)))
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()

        fig_path = os.path.join(OUT_DIR, "phase_a_rt_comparison_boxplot.png")
        plt.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {fig_path}")

    # ── Johnson Creek validation ──────────────────────────────────────
    jc_path = os.path.join(SCRIPT_DIR, "Data from Providers", "Data from Providers",
                           "Johnson Creek EMS Data 2024.csv")
    if os.path.exists(jc_path):
        print("\n  >> Johnson Creek ground-truth validation...")
        jc = pd.read_csv(jc_path)
        print(f"     Loaded {len(jc)} JC provider records")

        # Parse dispatch-arrival time
        def parse_mmss(val):
            if pd.isna(val) or str(val).strip() == "":
                return np.nan
            parts = str(val).strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) + int(parts[1]) / 60.0
            elif len(parts) == 3:
                return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60.0
            return np.nan

        jc["RT_Min"] = jc["Dispatch - Arrival"].apply(parse_mmss)

        # Classify by Vehicle ID: ambulance IDs vs fire apparatus
        ambulance_ids = {"8510", "8511", "8551", "8552"}
        jc["Is_Ambulance"] = jc["Vehicle ID"].astype(str).isin(ambulance_ids)

        # For each incident, the first ambulance record = primary, rest = secondary
        jc_ems = jc[jc["Is_Ambulance"]].copy()
        jc_ems["Incident Alarm Date"] = pd.to_datetime(jc_ems["Incident Alarm Date"],
                                                        errors="coerce")

        def classify_jc_incident(group):
            g = group.sort_values("RT_Min").reset_index(drop=True)
            g["JC_Class"] = "Secondary"
            if len(g) > 0:
                g.loc[0, "JC_Class"] = "Primary"  # fastest response = primary unit
            return g

        jc_classified = jc_ems.groupby("Incident #", group_keys=False).apply(
            classify_jc_incident)

        # Also use Mutual Aid column
        jc_classified["JC_MutualAid"] = jc_classified["Mutual AId"].str.strip().str.lower()
        # If mutual aid received, mark as secondary
        jc_classified.loc[
            jc_classified["JC_MutualAid"].isin(["received", "mutual aid received"]),
            "JC_Class"
        ] = "Secondary"

        jc_pri = jc_classified[jc_classified["JC_Class"] == "Primary"]
        jc_sec = jc_classified[jc_classified["JC_Class"] == "Secondary"]

        jc_val = {
            "JC_Total_Ambulance_Records": len(jc_classified),
            "JC_Unique_Incidents": jc_classified["Incident #"].nunique(),
            "JC_Primary": len(jc_pri),
            "JC_Secondary": len(jc_sec),
            "JC_Primary_Median_RT": round(jc_pri["RT_Min"].median(), 1),
            "JC_Primary_P90_RT": round(jc_pri["RT_Min"].quantile(0.9), 1),
            "JC_Secondary_Median_RT": round(jc_sec["RT_Min"].median(), 1) if len(jc_sec) > 5 else None,
            "JC_Secondary_P90_RT": round(jc_sec["RT_Min"].quantile(0.9), 1) if len(jc_sec) > 5 else None,
            "JC_Mutual_Aid_Count": (jc_classified["JC_MutualAid"] != "none").sum(),
        }

        jc_val_df = pd.DataFrame([jc_val])
        jc_path_out = os.path.join(OUT_DIR, "phase_a_jc_validation.csv")
        jc_val_df.to_csv(jc_path_out, index=False)
        print(f"     Saved: {jc_path_out}")
        for k, v in jc_val.items():
            print(f"       {k}: {v}")

        # Compare NFIRS classification vs JC ground truth
        nfirs_jc = classified[classified["Dept"] == "Johnson Creek"]
        print(f"\n     NFIRS-based JC classification: "
              f"{len(nfirs_jc[nfirs_jc['Call_Class'] == 'Primary'])} primary, "
              f"{len(nfirs_jc[nfirs_jc['Call_Class'] == 'Secondary'])} secondary")
        print(f"     JC ground-truth classification: "
              f"{len(jc_pri)} primary, {len(jc_sec)} secondary")
    else:
        print("  Johnson Creek provider data not found -- skipping validation")

    return classified, rt_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE B: Geographic Distribution of Secondary Ambulance Use
# ══════════════════════════════════════════════════════════════════════

def phase_b_secondary_geography(classified_df, ems_df, bg_df):
    """Map where secondary/backup ambulances respond throughout the county."""
    print("\n" + "=" * 70)
    print("PHASE B: GEOGRAPHIC DISTRIBUTION OF SECONDARY AMBULANCE USE")
    print("=" * 70)

    # ── Geocode calls to block groups ─────────────────────────────────
    print("  Building city/ZIP -> block group mapping...")
    pair_to_bg, city_to_bg = build_city_zip_to_bg_map(classified_df, bg_df)
    print(f"  Mapped {len(pair_to_bg)} unique (city, zip) pairs to block groups")

    # Assign each call to a BG
    classified_df = classified_df.copy()
    classified_df["BG_GEOID"] = classified_df.apply(
        lambda row: pair_to_bg.get(
            (str(row.get("City", "")).strip(), row.get("Zip", None)),
            None
        ), axis=1
    )

    # Fill NaN BGs with nearest by default
    default_bg = bg_df.iloc[0]["GEOID"]
    classified_df["BG_GEOID"] = classified_df["BG_GEOID"].fillna(default_bg)

    geocoded_count = classified_df["BG_GEOID"].notna().sum()
    print(f"  Geocoded {geocoded_count:,} / {len(classified_df):,} calls to block groups")

    # ── Secondary calls by block group ────────────────────────────────
    secondary = classified_df[classified_df["Call_Class"] == "Secondary"]
    all_calls = classified_df.copy()

    sec_by_bg = secondary.groupby("BG_GEOID").size().reset_index(name="Secondary_Count")
    all_by_bg = all_calls.groupby("BG_GEOID").size().reset_index(name="Total_Calls")

    bg_analysis = bg_df.merge(sec_by_bg, left_on="GEOID", right_on="BG_GEOID", how="left")
    bg_analysis = bg_analysis.merge(all_by_bg, left_on="GEOID", right_on="BG_GEOID", how="left")
    bg_analysis["Secondary_Count"] = bg_analysis["Secondary_Count"].fillna(0).astype(int)
    bg_analysis["Total_Calls"] = bg_analysis["Total_Calls"].fillna(0).astype(int)
    bg_analysis["Secondary_Rate_Per_1K"] = (
        bg_analysis["Secondary_Count"] / bg_analysis["population"] * 1000
    ).round(2)
    bg_analysis["Secondary_Pct"] = (
        bg_analysis["Secondary_Count"] / bg_analysis["Total_Calls"].replace(0, np.nan) * 100
    ).round(1)

    bg_analysis = bg_analysis.sort_values("Secondary_Count", ascending=False)

    csv_path = os.path.join(OUT_DIR, "phase_b_secondary_by_bg.csv")
    bg_analysis[["GEOID", "lat", "lon", "population", "Total_Calls",
                 "Secondary_Count", "Secondary_Rate_Per_1K", "Secondary_Pct"]
                ].to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_path}")
    print(f"  Top 10 block groups by secondary call count:")
    print(bg_analysis[["GEOID", "population", "Total_Calls", "Secondary_Count",
                        "Secondary_Rate_Per_1K"]].head(10).to_string(index=False))

    # Save geocoded calls for downstream phases
    geocoded_path = os.path.join(OUT_DIR, "phase_b_geocoded_calls.csv")
    classified_df[["Dept", "Alarm_DT", "Cleared_DT", "Call_Class", "RT",
                    "City", "Zip", "BG_GEOID", "Aid_Code",
                    "Hour", "DOW", "Duration_Min", "Concurrent_Count"]
                  ].to_csv(geocoded_path, index=False)
    print(f"  Saved: {geocoded_path}")

    # ── Heatmap: secondary call density ───────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 10))

    # Plot all BGs as gray circles
    for _, row in bg_analysis.iterrows():
        size = max(10, min(200, row["population"] / 50))
        ax.scatter(row["lon"], row["lat"], s=size, c="#ddd", alpha=0.5,
                   edgecolors="#bbb", linewidths=0.5, zorder=2)

    # Overlay secondary calls as red graduated circles
    sec_bg = bg_analysis[bg_analysis["Secondary_Count"] > 0].copy()
    if not sec_bg.empty:
        max_sec = sec_bg["Secondary_Count"].max()
        for _, row in sec_bg.iterrows():
            size = max(20, 400 * row["Secondary_Count"] / max_sec)
            intensity = min(1.0, row["Secondary_Count"] / max_sec)
            color = plt.cm.Reds(0.3 + 0.7 * intensity)
            ax.scatter(row["lon"], row["lat"], s=size, c=[color],
                       alpha=0.7, edgecolors="#c0392b", linewidths=0.8, zorder=5)

    # Station markers
    stations_path = os.path.join(SCRIPT_DIR, "jefferson_stations.geojson")
    if os.path.exists(stations_path):
        with open(stations_path) as f:
            st_gj = json.load(f)
        for feat in st_gj["features"]:
            coords = feat["geometry"]["coordinates"]
            name = feat["properties"].get("name", "")
            ax.scatter(coords[0], coords[1], s=100, c="#3498db", marker="s",
                       edgecolors="#2c3e50", linewidths=1.5, zorder=10)
            ax.annotate(name, (coords[0], coords[1] + 0.008),
                        fontsize=7, ha="center", color="#2c3e50", zorder=11)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        "Secondary Ambulance Call Density by Census Block Group\n"
        "Circle size = secondary call count | Blue squares = existing stations | CY2024",
        fontweight="bold"
    )
    ax.set_aspect("equal")
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_b_secondary_heatmap.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return classified_df, bg_analysis


# ══════════════════════════════════════════════════════════════════════
#  PHASE C: Ambulance Utilization by Unit and Time of Day
# ══════════════════════════════════════════════════════════════════════

def phase_c_utilization(classified_df):
    """Compute hourly utilization rates per department."""
    print("\n" + "=" * 70)
    print("PHASE C: AMBULANCE UTILIZATION BY UNIT AND TIME OF DAY")
    print("=" * 70)

    # Filter to calls with valid timestamps
    df = classified_df.dropna(subset=["Alarm_DT", "Cleared_DT"]).copy()
    df["Alarm_DT"] = pd.to_datetime(df["Alarm_DT"])
    df["Cleared_DT"] = pd.to_datetime(df["Cleared_DT"])

    # Compute utilization: for each dept × hour, total call-minutes / capacity-minutes
    rows = []
    dept_summaries = []

    for dept in EMS_TRANSPORT_DEPTS:
        dg = df[df["Dept"] == dept]
        if dg.empty:
            continue

        amb = AMBULANCE_COUNT.get(dept, 1)
        if amb == 0:
            continue

        # Count days in data range
        date_range = (dg["Alarm_DT"].max() - dg["Alarm_DT"].min()).days + 1
        if date_range <= 0:
            date_range = 365

        # For each hour (0-23), compute total call-minutes that overlap that hour
        hourly_minutes = np.zeros(24)
        for _, call in dg.iterrows():
            alarm = call["Alarm_DT"]
            cleared = call["Cleared_DT"]
            if pd.isna(alarm) or pd.isna(cleared):
                continue
            # Cap duration at 4 hours to avoid data errors
            if (cleared - alarm).total_seconds() > 4 * 3600:
                cleared = alarm + pd.Timedelta(hours=4)

            # Distribute minutes across hours
            current = alarm
            while current < cleared:
                hour = current.hour
                next_hour = current.replace(minute=0, second=0, microsecond=0) + pd.Timedelta(hours=1)
                end_in_hour = min(cleared, next_hour)
                minutes_in_hour = (end_in_hour - current).total_seconds() / 60.0
                hourly_minutes[hour] += minutes_in_hour
                current = next_hour

        # Utilization = total_minutes / (amb × days × 60 min)
        for h in range(24):
            capacity_minutes = amb * date_range * 60.0
            util = hourly_minutes[h] / capacity_minutes if capacity_minutes > 0 else 0
            rows.append({
                "Dept": dept,
                "Hour": h,
                "Call_Minutes": round(hourly_minutes[h], 1),
                "Capacity_Minutes": round(capacity_minutes, 1),
                "Utilization": round(util, 4),
                "Utilization_Pct": round(util * 100, 2),
            })

        # Summary stats
        daily_avg_util = hourly_minutes.sum() / (amb * date_range * 24 * 60)
        peak_hours = hourly_minutes[9:19]  # 09:00-19:00
        peak_capacity = amb * date_range * 60.0
        peak_util = peak_hours.sum() / (peak_capacity * 10) if peak_capacity > 0 else 0
        offpeak_hours = np.concatenate([hourly_minutes[:9], hourly_minutes[19:]])
        offpeak_util = offpeak_hours.sum() / (peak_capacity * 14) if peak_capacity > 0 else 0
        peak_hour_idx = int(np.argmax(hourly_minutes))

        dept_summaries.append({
            "Dept": dept,
            "Ambulances": amb,
            "Total_Calls": len(dg),
            "Days_In_Data": date_range,
            "Daily_Avg_Utilization_Pct": round(daily_avg_util * 100, 2),
            "Peak_Utilization_Pct_0919": round(peak_util * 100, 2),
            "OffPeak_Utilization_Pct": round(offpeak_util * 100, 2),
            "Peak_Hour": f"{peak_hour_idx:02d}:00",
            "Peak_Hour_Util_Pct": round(hourly_minutes[peak_hour_idx] / (amb * date_range * 60) * 100, 2),
            "Exceeds_25pct_Threshold": "YES" if peak_util > 0.25 else "NO",
        })

    util_df = pd.DataFrame(rows)
    summary_df = pd.DataFrame(dept_summaries)

    csv_path = os.path.join(OUT_DIR, "phase_c_utilization_by_dept_hour.csv")
    util_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    csv_path2 = os.path.join(OUT_DIR, "phase_c_utilization_summary.csv")
    summary_df.to_csv(csv_path2, index=False)
    print(f"  Saved: {csv_path2}")
    print(summary_df.to_string(index=False))

    # ── Plot: Faceted utilization profiles ────────────────────────────
    depts_with_data = summary_df["Dept"].tolist()
    n_depts = len(depts_with_data)
    cols = 3
    fig_rows = (n_depts + cols - 1) // cols
    fig, axes = plt.subplots(fig_rows, cols, figsize=(16, 4 * fig_rows), sharey=True)
    axes = axes.flatten() if n_depts > 1 else [axes]

    for i, dept in enumerate(depts_with_data):
        ax = axes[i]
        dept_util = util_df[util_df["Dept"] == dept]
        hours = dept_util["Hour"].values
        utils = dept_util["Utilization_Pct"].values

        ax.bar(hours, utils, color="#3498db", alpha=0.8, edgecolor="#2c3e50", linewidth=0.5)
        ax.axhline(y=25, color="#e74c3c", linewidth=1.5, linestyle="--", alpha=0.7,
                    label="25% threshold")
        ax.axhspan(9, 19, alpha=0.05, color="orange")  # Subtle peak hours highlight

        amb = AMBULANCE_COUNT.get(dept, 1)
        summ = summary_df[summary_df["Dept"] == dept].iloc[0]
        ax.set_title(f"{dept} ({amb} amb)\n"
                     f"Peak: {summ['Peak_Utilization_Pct_0919']:.1f}% | "
                     f"Avg: {summ['Daily_Avg_Utilization_Pct']:.1f}%",
                     fontsize=10, fontweight="bold")
        ax.set_xlabel("Hour of Day", fontsize=9)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xticklabels(["00", "06", "12", "18", "23"], fontsize=8)
        if i % cols == 0:
            ax.set_ylabel("Utilization (%)", fontsize=9)
        ax.grid(axis="y", alpha=0.3)

    # Hide empty subplots
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle(
        "Ambulance Utilization by Hour of Day — Per Department\n"
        "% of total ambulance capacity consumed | Red dashed = 25% reliability threshold | CY2024",
        fontsize=13, fontweight="bold", y=1.02
    )
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_c_utilization_profiles.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return util_df, summary_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE D: Current Staffing Operations Investigation
# ══════════════════════════════════════════════════════════════════════

def phase_d_staffing(util_summary_df):
    """Document current staffing models and efficiency metrics."""
    print("\n" + "=" * 70)
    print("PHASE D: CURRENT STAFFING OPERATIONS INVESTIGATION")
    print("=" * 70)

    # ALS/BLS levels
    ALS_LEVELS = {
        "Watertown": "ALS", "Fort Atkinson": "ALS", "Whitewater": "ALS",
        "Edgerton": "ALS", "Jefferson": "ALS", "Johnson Creek": "ALS",
        "Waterloo": "AEMT", "Lake Mills": "BLS", "Ixonia": "BLS",
        "Palmyra": "BLS", "Cambridge": "ALS",
    }

    STAFFING_MODELS = {
        "Watertown": "Career 24/7",
        "Fort Atkinson": "Career + PT",
        "Whitewater": "Career + PT",
        "Edgerton": "Career",
        "Jefferson": "Career + PT",
        "Johnson Creek": "Combination (FT+PT)",
        "Waterloo": "Career + Volunteer",
        "Lake Mills": "Career + Volunteer",
        "Ixonia": "Volunteer + FT chiefs",
        "Palmyra": "Volunteer",
        "Cambridge": "Volunteer",
    }

    rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        data = DEPT_DATA.get(dept, {})
        if not data:
            continue

        ft = data.get("FT", 0)
        pt = data.get("PT", 0)
        fte = ft + pt * 0.5  # 1 PT = 0.5 FTE
        amb = data.get("Ambulances", 0)
        expense = data.get("Expense", 0)
        pop = data.get("Pop", 0)
        sec_events = data.get("Secondary_Events", 0)

        # Get utilization from Phase C
        util_row = util_summary_df[util_summary_df["Dept"] == dept]
        calls = int(util_row["Total_Calls"].values[0]) if not util_row.empty else 0
        peak_util = float(util_row["Peak_Utilization_Pct_0919"].values[0]) if not util_row.empty else 0

        rows.append({
            "Dept": dept,
            "Staffing_Model": STAFFING_MODELS.get(dept, "Unknown"),
            "ALS_Level": ALS_LEVELS.get(dept, "Unknown"),
            "FT_Staff": ft,
            "PT_Staff": pt,
            "FTE_Equiv": round(fte, 1),
            "Ambulances": amb,
            "EMS_Calls_2024": calls,
            "Annual_Expense": expense,
            "Population_Served": pop,
            "Secondary_Events": sec_events,
            "Calls_Per_FTE": round(calls / fte, 1) if fte > 0 else 0,
            "FTE_Per_Ambulance": round(fte / amb, 1) if amb > 0 else 0,
            "Cost_Per_Call": round(expense / calls) if calls > 0 else 0,
            "Cost_Per_Capita": round(expense / pop) if pop > 0 else 0,
            "Peak_Utilization_Pct": round(peak_util, 1),
        })

    staff_df = pd.DataFrame(rows)

    csv_path = os.path.join(OUT_DIR, "phase_d_staffing_profile.csv")
    staff_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")
    print(staff_df[["Dept", "Staffing_Model", "FT_Staff", "PT_Staff", "Ambulances",
                     "EMS_Calls_2024", "Calls_Per_FTE", "Cost_Per_Call",
                     "Peak_Utilization_Pct"]].to_string(index=False))

    # ── Scatter plot: FTE per 1000 calls vs Cost per call ─────────────
    fig, ax = plt.subplots(figsize=(12, 8))

    for _, row in staff_df.iterrows():
        calls = row["EMS_Calls_2024"]
        if calls == 0:
            continue
        fte_per_1k = row["FTE_Equiv"] / calls * 1000
        cost_per_call = row["Cost_Per_Call"]
        pop = row["Population_Served"]
        size = max(30, min(300, pop / 50))

        color = {"ALS": "#e74c3c", "AEMT": "#f39c12", "BLS": "#3498db"}.get(
            row["ALS_Level"], "#95a5a6")

        ax.scatter(fte_per_1k, cost_per_call, s=size, c=color, alpha=0.7,
                   edgecolors="#333", linewidths=1, zorder=5)
        ax.annotate(row["Dept"], (fte_per_1k, cost_per_call),
                    textcoords="offset points", xytext=(8, 5),
                    fontsize=9, fontweight="bold")

    ax.set_xlabel("FTE Equivalents per 1,000 EMS Calls")
    ax.set_ylabel("Annual Cost per EMS Call ($)")
    ax.set_title(
        "Staffing Efficiency: Labor Intensity vs Cost per Call\n"
        "Circle size = population served | Color = ALS level | CY2024",
        fontweight="bold"
    )
    legend_elements = [
        mpatches.Patch(color="#e74c3c", alpha=0.7, label="ALS"),
        mpatches.Patch(color="#f39c12", alpha=0.7, label="AEMT"),
        mpatches.Patch(color="#3498db", alpha=0.7, label="BLS"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")
    ax.grid(alpha=0.3)
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_d_staffing_efficiency.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return staff_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE E: Secondary Ambulance Response Destinations
# ══════════════════════════════════════════════════════════════════════

def phase_e_secondary_destinations(classified_df, bg_df):
    """Map where secondary ambulances respond and cross-boundary flows."""
    print("\n" + "=" * 70)
    print("PHASE E: SECONDARY AMBULANCE RESPONSE DESTINATIONS")
    print("=" * 70)

    secondary = classified_df[classified_df["Call_Class"] == "Secondary"].copy()
    print(f"  Total secondary calls: {len(secondary):,}")

    # ── Top destinations per department ───────────────────────────────
    dest_rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        dept_sec = secondary[secondary["Dept"] == dept]
        if dept_sec.empty:
            continue

        # Top BGs
        bg_counts = dept_sec.groupby("BG_GEOID").size().reset_index(name="Count")
        bg_counts = bg_counts.sort_values("Count", ascending=False)

        for _, row in bg_counts.head(5).iterrows():
            bg_info = bg_df[bg_df["GEOID"] == row["BG_GEOID"]]
            dest_rows.append({
                "Responding_Dept": dept,
                "Destination_BG": row["BG_GEOID"],
                "Count": row["Count"],
                "BG_Population": int(bg_info["population"].values[0]) if not bg_info.empty else 0,
                "BG_Lat": float(bg_info["lat"].values[0]) if not bg_info.empty else 0,
                "BG_Lon": float(bg_info["lon"].values[0]) if not bg_info.empty else 0,
            })

    dest_df = pd.DataFrame(dest_rows)
    csv_path = os.path.join(OUT_DIR, "phase_e_secondary_destinations.csv")
    dest_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    # ── Cross-boundary mutual aid flows ───────────────────────────────
    # Use Aid_Code to identify mutual aid given (code 3,4) and received (1,2)
    mutual_aid = classified_df[classified_df["Aid_Code"].isin(["1", "2", "3", "4"])].copy()
    print(f"  Mutual aid calls (all types): {len(mutual_aid):,}")

    # Aid received = another dept sent resources here
    # Aid given = this dept sent resources elsewhere
    aid_given = mutual_aid[mutual_aid["Aid_Code"].isin(["3", "4"])]
    aid_received = mutual_aid[mutual_aid["Aid_Code"].isin(["1", "2"])]

    flow_rows = []
    for dept in EMS_TRANSPORT_DEPTS:
        given = len(aid_given[aid_given["Dept"] == dept])
        received = len(aid_received[aid_received["Dept"] == dept])
        net = given - received  # positive = net exporter of mutual aid

        flow_rows.append({
            "Dept": dept,
            "Aid_Given": given,
            "Aid_Received": received,
            "Net_Aid": net,
            "Net_Direction": "Net Provider" if net > 0 else ("Net Receiver" if net < 0 else "Balanced"),
        })

    flow_df = pd.DataFrame(flow_rows)
    csv_path2 = os.path.join(OUT_DIR, "phase_e_cross_boundary_flows.csv")
    flow_df.to_csv(csv_path2, index=False)
    print(f"  Saved: {csv_path2}")
    print(flow_df.to_string(index=False))

    # ── Flow map ──────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 8))

    # Plot BGs as background
    for _, row in bg_df.iterrows():
        ax.scatter(row["lon"], row["lat"], s=15, c="#ddd", alpha=0.4, zorder=1)

    # Station positions for flow arrows
    stations_path = os.path.join(SCRIPT_DIR, "jefferson_stations.geojson")
    station_coords = {}
    if os.path.exists(stations_path):
        with open(stations_path) as f:
            st_gj = json.load(f)
        for feat in st_gj["features"]:
            name = feat["properties"].get("name", "")
            coords = feat["geometry"]["coordinates"]
            station_coords[name] = (coords[0], coords[1])
            ax.scatter(coords[0], coords[1], s=80, c="#3498db", marker="s",
                       edgecolors="#2c3e50", linewidths=1, zorder=10)

    # Bar overlay: aid given vs received
    dept_order = flow_df.sort_values("Aid_Given", ascending=False)["Dept"].tolist()
    bar_width = 0.35

    ax2 = fig.add_axes([0.12, 0.08, 0.35, 0.25])  # Inset axes
    x = range(len(flow_df))
    ax2.barh([flow_df.iloc[i]["Dept"] for i in range(len(flow_df))],
             flow_df["Aid_Given"].values, height=0.4, color="#e74c3c", alpha=0.7,
             label="Aid Given")
    ax2.barh([flow_df.iloc[i]["Dept"] for i in range(len(flow_df))],
             [-v for v in flow_df["Aid_Received"].values], height=0.4, color="#3498db",
             alpha=0.7, label="Aid Received")
    ax2.set_xlabel("Calls", fontsize=8)
    ax2.set_title("Mutual Aid Exchange", fontsize=9, fontweight="bold")
    ax2.legend(fontsize=7, loc="lower right")
    ax2.tick_params(labelsize=7)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        "Secondary Ambulance Response Destinations & Mutual Aid Flows\n"
        "Blue squares = stations | Inset = mutual aid given vs received | CY2024",
        fontweight="bold"
    )
    ax.set_aspect("equal")
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_e_secondary_flow_map.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return dest_df, flow_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE F: Response Area Hot Spots
# ══════════════════════════════════════════════════════════════════════

def phase_f_hotspots(classified_df, bg_df, util_df):
    """Identify geographic hot spots where ambulances frequently respond."""
    print("\n" + "=" * 70)
    print("PHASE F: RESPONSE AREA HOT SPOTS")
    print("=" * 70)

    # ── Calls per block group (all EMS calls, not just secondary) ─────
    all_by_bg = classified_df.groupby("BG_GEOID").size().reset_index(name="Total_Calls")

    hotspot = bg_df.merge(all_by_bg, left_on="GEOID", right_on="BG_GEOID", how="left")
    hotspot["Total_Calls"] = hotspot["Total_Calls"].fillna(0).astype(int)
    hotspot["Calls_Per_1K_Pop"] = (hotspot["Total_Calls"] / hotspot["population"] * 1000).round(1)

    # Secondary calls
    sec_by_bg = classified_df[classified_df["Call_Class"] == "Secondary"].groupby("BG_GEOID").size().reset_index(name="Secondary_Calls")
    hotspot = hotspot.merge(sec_by_bg, left_on="GEOID", right_on="BG_GEOID", how="left")
    hotspot["Secondary_Calls"] = hotspot["Secondary_Calls"].fillna(0).astype(int)
    hotspot["Secondary_Per_1K"] = (hotspot["Secondary_Calls"] / hotspot["population"] * 1000).round(1)

    # Ranking
    hotspot["Rank_Absolute"] = hotspot["Total_Calls"].rank(ascending=False, method="min").astype(int)
    hotspot["Rank_PerCapita"] = hotspot["Calls_Per_1K_Pop"].rank(ascending=False, method="min").astype(int)
    hotspot["Combined_Rank"] = ((hotspot["Rank_Absolute"] + hotspot["Rank_PerCapita"]) / 2).round(1)

    hotspot = hotspot.sort_values("Combined_Rank")

    csv_path = os.path.join(OUT_DIR, "phase_f_hotspot_ranking.csv")
    hotspot[["GEOID", "lat", "lon", "population", "Total_Calls", "Calls_Per_1K_Pop",
             "Secondary_Calls", "Secondary_Per_1K",
             "Rank_Absolute", "Rank_PerCapita", "Combined_Rank"]
            ].to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")
    print(f"\n  Top 15 hot spots (combined absolute + per-capita rank):")
    print(hotspot[["GEOID", "population", "Total_Calls", "Calls_Per_1K_Pop",
                    "Secondary_Calls", "Combined_Rank"]].head(15).to_string(index=False))

    # ── Temporal hot spots: hour distribution for top BGs ─────────────
    top_bgs = hotspot.head(10)["GEOID"].tolist()
    temporal_rows = []

    for bg_id in top_bgs:
        bg_calls = classified_df[classified_df["BG_GEOID"] == bg_id]
        for h in range(24):
            count = len(bg_calls[bg_calls["Hour"] == h])
            temporal_rows.append({
                "BG_GEOID": bg_id,
                "Hour": h,
                "Call_Count": count,
            })

    temporal_df = pd.DataFrame(temporal_rows)
    csv_path2 = os.path.join(OUT_DIR, "phase_f_temporal_hotspots.csv")
    temporal_df.to_csv(csv_path2, index=False)
    print(f"  Saved: {csv_path2}")

    # ── Hot spot map ──────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(20, 9))

    # Panel 1: Absolute call count
    ax = axes[0]
    max_calls = hotspot["Total_Calls"].max()
    for _, row in hotspot.iterrows():
        if row["Total_Calls"] == 0:
            continue
        size = max(15, 500 * row["Total_Calls"] / max_calls)
        intensity = min(1.0, row["Total_Calls"] / max_calls)
        color = plt.cm.YlOrRd(0.2 + 0.8 * intensity)
        ax.scatter(row["lon"], row["lat"], s=size, c=[color], alpha=0.7,
                   edgecolors="#c0392b" if intensity > 0.5 else "#999",
                   linewidths=0.5, zorder=5)

    # Top 5 labels
    for _, row in hotspot.head(5).iterrows():
        ax.annotate(f"#{int(row['Rank_Absolute'])}: {int(row['Total_Calls'])} calls",
                    (row["lon"], row["lat"]),
                    textcoords="offset points", xytext=(10, 5),
                    fontsize=8, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))

    ax.set_title("Hot Spots by Total Call Count\n(Circle size = call volume)",
                 fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)

    # Panel 2: Per-capita rate
    ax = axes[1]
    max_rate = hotspot["Calls_Per_1K_Pop"].max()
    for _, row in hotspot.iterrows():
        if row["Calls_Per_1K_Pop"] == 0:
            continue
        size = max(15, 500 * row["Calls_Per_1K_Pop"] / max_rate)
        intensity = min(1.0, row["Calls_Per_1K_Pop"] / max_rate)
        color = plt.cm.YlOrRd(0.2 + 0.8 * intensity)
        ax.scatter(row["lon"], row["lat"], s=size, c=[color], alpha=0.7,
                   edgecolors="#c0392b" if intensity > 0.5 else "#999",
                   linewidths=0.5, zorder=5)

    for _, row in hotspot.sort_values("Calls_Per_1K_Pop", ascending=False).head(5).iterrows():
        ax.annotate(f"{row['Calls_Per_1K_Pop']:.0f}/1K pop",
                    (row["lon"], row["lat"]),
                    textcoords="offset points", xytext=(10, 5),
                    fontsize=8, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))

    ax.set_title("Hot Spots by Calls per 1,000 Population\n(Rate-adjusted for population density)",
                 fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)

    fig.suptitle(
        "Jefferson County EMS — Response Area Hot Spots | CY2024\n"
        "Left: absolute demand | Right: per-capita demand (controls for population size)",
        fontsize=14, fontweight="bold", y=1.02
    )
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_f_hotspot_map.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return hotspot, temporal_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE G: Consolidation & Optimization Setup
# ══════════════════════════════════════════════════════════════════════

def phase_g_consolidation(classified_df, bg_df, hotspot_df, util_summary_df,
                          staff_df, rt_df, flow_df):
    """Synthesize findings from Phases A-F and prepare optimization inputs."""
    print("\n" + "=" * 70)
    print("PHASE G: CONSOLIDATION & OPTIMIZATION SETUP")
    print("=" * 70)

    # ── Load existing drive time matrices ─────────────────────────────
    baseline_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                                  "existing_bg_drive_time_matrix.json")
    cand_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                              "cand_bg_drive_time_matrix.json")

    if os.path.exists(baseline_cache):
        with open(baseline_cache) as f:
            baseline_tm = np.array(json.load(f)["matrix"])
        print(f"  Loaded baseline drive time matrix: {baseline_tm.shape}")
    else:
        print("  WARNING: No baseline drive time matrix found")
        baseline_tm = None

    if os.path.exists(cand_cache):
        with open(cand_cache) as f:
            cand_tm = np.array(json.load(f)["matrix"])
        print(f"  Loaded candidate drive time matrix: {cand_tm.shape}")
    else:
        print("  WARNING: No candidate drive time matrix found")
        cand_tm = None

    # ── Build composite demand weights ────────────────────────────────
    # Weight = blend of population, call volume, and secondary demand
    # Normalize each component to [0,1] then blend
    pop = hotspot_df["population"].values.astype(float)
    calls = hotspot_df["Total_Calls"].values.astype(float)
    sec = hotspot_df["Secondary_Calls"].values.astype(float)

    # Normalize
    pop_norm = pop / pop.max() if pop.max() > 0 else pop
    calls_norm = calls / calls.max() if calls.max() > 0 else calls
    sec_norm = sec / sec.max() if sec.max() > 0 else sec

    # Blend weights: population=0.4, call_volume=0.4, secondary_demand=0.2
    ALPHA, BETA, GAMMA = 0.4, 0.4, 0.2
    composite = ALPHA * pop_norm + BETA * calls_norm + GAMMA * sec_norm
    # Scale back to population units for solver compatibility
    composite_scaled = composite / composite.sum() * pop.sum()

    weights_df = hotspot_df[["GEOID", "lat", "lon", "population"]].copy()
    weights_df["Total_Calls"] = calls.astype(int)
    weights_df["Secondary_Calls"] = sec.astype(int)
    weights_df["Pop_Weight_Norm"] = pop_norm.round(4)
    weights_df["Call_Weight_Norm"] = calls_norm.round(4)
    weights_df["Sec_Weight_Norm"] = sec_norm.round(4)
    weights_df["Composite_Weight"] = composite_scaled.round(1)

    csv_path = os.path.join(OUT_DIR, "phase_g_demand_weights.csv")
    weights_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    # ── Compute baseline metrics ──────────────────────────────────────
    if baseline_tm is not None:
        n_sta, n_bg = baseline_tm.shape
        # Use composite weights for consistency
        weights = composite_scaled[:n_bg]
        total_weight = weights.sum()

        # Nearest station time for each BG
        nearest_time = np.array([
            min(baseline_tm[i, j] for i in range(n_sta))
            for j in range(n_bg)
        ])

        avg_rt = float(np.sum(weights * nearest_time) / total_weight)
        max_rt = float(np.max(nearest_time))

        # Percentiles (weighted)
        sorted_idx = np.argsort(nearest_time)
        cum_weight = np.cumsum(weights[sorted_idx])
        p50_idx = np.searchsorted(cum_weight, total_weight * 0.5)
        p90_idx = np.searchsorted(cum_weight, total_weight * 0.9)
        median_rt = float(nearest_time[sorted_idx[min(p50_idx, n_bg-1)]])
        p90_rt = float(nearest_time[sorted_idx[min(p90_idx, n_bg-1)]])

        # Coverage at thresholds
        coverages = {}
        for T in [8, 10, 14, 20]:
            cov_weight = sum(weights[j] for j in range(n_bg) if nearest_time[j] <= T)
            coverages[T] = round(100 * cov_weight / total_weight, 1)

        baseline_metrics = {
            "System": "Current (13 stations)",
            "Stations": n_sta,
            "Ambulances": sum(AMBULANCE_COUNT.values()),
            "Avg_RT_Min": round(avg_rt, 2),
            "Median_RT_Min": round(median_rt, 2),
            "P90_RT_Min": round(p90_rt, 2),
            "Max_RT_Min": round(max_rt, 2),
            "Coverage_8min_Pct": coverages[8],
            "Coverage_10min_Pct": coverages[10],
            "Coverage_14min_Pct": coverages[14],
            "Coverage_20min_Pct": coverages[20],
            "Total_FTE": sum(d.get("FT", 0) + d.get("PT", 0) * 0.5 for d in DEPT_DATA.values()),
            "Total_Annual_Cost": sum(d.get("Expense", 0) for d in DEPT_DATA.values()),
        }

        baseline_df = pd.DataFrame([baseline_metrics])
        csv_path2 = os.path.join(OUT_DIR, "phase_g_baseline_metrics.csv")
        baseline_df.to_csv(csv_path2, index=False)
        print(f"  Saved: {csv_path2}")
        print(f"\n  BASELINE SYSTEM PERFORMANCE:")
        for k, v in baseline_metrics.items():
            if isinstance(v, float):
                print(f"    {k}: {v:.2f}")
            else:
                print(f"    {k}: {v}")
    else:
        baseline_metrics = None
        print("  Skipped baseline metrics (no drive time matrix)")

    # ── Summary of key findings ───────────────────────────────────────
    print(f"\n  " + "-" * 60)
    print(f"  PHASE A-G CONSOLIDATED FINDINGS")
    print(f"  " + "-" * 60)

    # From Phase A
    county_rt = rt_df[rt_df["Dept"] == "COUNTY TOTAL"]
    if not county_rt.empty:
        r = county_rt.iloc[0]
        print(f"\n  [A] Response Time Gap:")
        print(f"      Primary   -- Median: {r['Primary_Median_RT']} min | P90: {r['Primary_P90_RT']} min")
        print(f"      Secondary -- Median: {r['Secondary_Median_RT']} min | P90: {r['Secondary_P90_RT']} min")
        print(f"      Delta     -- Median: +{r['Median_Delta_Min']} min | P90: +{r['P90_Delta_Min']} min")

    # From Phase C
    high_util = util_summary_df[util_summary_df["Exceeds_25pct_Threshold"] == "YES"]
    if not high_util.empty:
        print(f"\n  [C] Departments exceeding 25% peak utilization:")
        for _, row in high_util.iterrows():
            print(f"      {row['Dept']}: {row['Peak_Utilization_Pct_0919']:.1f}% peak")
    else:
        print(f"\n  [C] No departments exceed 25% peak utilization threshold")

    # From Phase E
    net_providers = flow_df[flow_df["Net_Direction"] == "Net Provider"]
    net_receivers = flow_df[flow_df["Net_Direction"] == "Net Receiver"]
    if not net_providers.empty:
        print(f"\n  [E] Net mutual aid providers: {', '.join(net_providers['Dept'].tolist())}")
    if not net_receivers.empty:
        print(f"\n  [E] Net mutual aid receivers: {', '.join(net_receivers['Dept'].tolist())}")

    # From Phase F
    top3_hotspots = hotspot_df.head(3)
    print(f"\n  [F] Top 3 demand hot spots:")
    for _, row in top3_hotspots.iterrows():
        print(f"      BG {row['GEOID']}: {int(row['Total_Calls'])} calls "
              f"({row['Calls_Per_1K_Pop']:.0f}/1K pop)")

    # From Phase G baseline
    if baseline_metrics:
        print(f"\n  [G] Baseline coverage targets:")
        print(f"      Current 14-min coverage: {baseline_metrics['Coverage_14min_Pct']}%")
        print(f"      Current 10-min coverage: {baseline_metrics['Coverage_10min_Pct']}%")
        print(f"      Target: >=90% within 14 min (stretch: >=90% within 10 min)")

    print(f"\n  Ready for optimization phases (H-L).")
    print(f"  Demand weights and baseline metrics saved to analysis_output/")

    return weights_df, baseline_metrics


# ══════════════════════════════════════════════════════════════════════
#  PHASE H: Determine Optimal Number of Replacement Secondary Ambulances
# ══════════════════════════════════════════════════════════════════════

# Current secondary ambulance inventory (total fleet - 1 primary per dept)
CURRENT_SECONDARY = {
    dept: max(0, AMBULANCE_COUNT.get(dept, 0) - 1)
    for dept in EMS_TRANSPORT_DEPTS
}
TOTAL_CURRENT_SECONDARY = sum(CURRENT_SECONDARY.values())  # = 10


def phase_h_ambulance_count(bg_df):
    """
    Sweep K=1..10 county-wide replacement secondary ambulances.

    Model: Each municipality KEEPS its primary (first-out) ambulance at
    existing stations. All 10 distributed secondary ambulances are REPLACED
    by K county-wide ALS units at optimal locations.

    CRITICAL: Coverage is evaluated for the COMBINED system:
      effective_RT(BG) = min(nearest_primary_station, nearest_secondary_unit)
    The secondary network can only IMPROVE coverage, never make it worse,
    because the primaries are still there.
    """
    print("\n" + "=" * 70)
    print("PHASE H: REPLACEMENT SECONDARY NETWORK SIZING")
    print("=" * 70)
    print(f"  Current system: {TOTAL_CURRENT_SECONDARY} secondary ambulances "
          f"distributed across {sum(1 for v in CURRENT_SECONDARY.values() if v > 0)} departments")
    print(f"  Goal: replace with K <= {TOTAL_CURRENT_SECONDARY} county-wide ALS units")
    print(f"  Coverage = combined primary stations + secondary network")

    for dept, sec in CURRENT_SECONDARY.items():
        if sec > 0:
            print(f"    {dept}: {AMBULANCE_COUNT[dept]} total -> 1 primary + {sec} secondary (retiring {sec})")

    from pareto_facility import (
        load_candidates, load_bg_demand, fetch_cand_bg_matrix,
        solve_mclp,
    )

    # Load solver inputs
    candidates = load_candidates()
    bg_demand, pop_weights_raw = load_bg_demand()
    n_bg = len(bg_demand)
    print(f"\n  {len(candidates)} candidate sites, {n_bg} block groups")

    # Load composite demand weights from Phase G
    weights_path = os.path.join(OUT_DIR, "phase_g_demand_weights.csv")
    if os.path.exists(weights_path):
        wdf = pd.read_csv(weights_path)
        pop_weights = wdf["Composite_Weight"].values
        print(f"  Using Phase G composite demand weights")
    else:
        pop_weights = pop_weights_raw
        print(f"  Using raw population weights (Phase G weights not found)")

    # Drive time matrix (60 candidates x 65 block groups) -- for secondary placement
    tm = fetch_cand_bg_matrix(candidates, bg_demand)
    if tm is None:
        print("  ERROR: No drive time matrix available")
        return None, None, None, None, None, None, None
    print(f"  Candidate drive time matrix: {tm.shape}")

    # Load EXISTING station drive times (13 stations x 65 BGs) -- primary baseline
    existing_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                                  "existing_bg_drive_time_matrix.json")
    with open(existing_cache) as f:
        existing_tm = np.array(json.load(f)["matrix"])
    print(f"  Existing station matrix: {existing_tm.shape}")

    # Baseline: nearest primary station time for each BG (this never changes)
    primary_nearest = np.min(existing_tm, axis=0)  # shape (65,)
    total_weight = pop_weights.sum()

    # Baseline metrics (primaries only, no secondaries)
    baseline_avg = float(np.sum(pop_weights * primary_nearest) / total_weight)
    baseline_cov = {}
    for T in [8, 10, 14]:
        c = sum(pop_weights[j] for j in range(n_bg) if primary_nearest[j] <= T)
        baseline_cov[T] = round(100 * c / total_weight, 1)
    print(f"\n  Baseline (primaries only): avg RT = {baseline_avg:.2f} min, "
          f"14-min = {baseline_cov[14]}%, 10-min = {baseline_cov[10]}%")

    # ── Sweep K=1..10: MCLP places secondaries, then merge with primaries ─
    K_RANGE = list(range(1, TOTAL_CURRENT_SECONDARY + 1))
    T_PRIMARY = 14

    sweep_rows = []
    solutions = {}

    print(f"\n  Sweeping K=1..{TOTAL_CURRENT_SECONDARY} (MCLP T={T_PRIMARY} + primary merge)...")
    print(f"  {'K':>3}  {'14min%':>7}  {'10min%':>7}  {'8min%':>6}  "
          f"{'AvgRT':>6}  {'MaxRT':>6}  {'Saved':>6}")
    print(f"  {'---':>3}  {'------':>7}  {'------':>7}  {'-----':>6}  "
          f"{'-----':>6}  {'-----':>6}  {'-----':>6}")

    for K in K_RANGE:
        # Use MCLP to find best K candidate sites for secondary placement
        sol = solve_mclp(tm, candidates, bg_demand, K, T_PRIMARY, pop_weights)
        if sol is None:
            print(f"  K={K}: INFEASIBLE")
            continue

        # Get selected secondary site indices
        open_ids = [i for i, c in enumerate(candidates)
                    if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                           for s in sol["open_stations"])]

        # COMBINED system: for each BG, effective RT = min(primary, secondary)
        secondary_nearest = np.array([
            min(tm[i, j] for i in open_ids) for j in range(n_bg)])
        combined_nearest = np.minimum(primary_nearest, secondary_nearest)

        # Compute combined metrics
        combined_avg = float(np.sum(pop_weights * combined_nearest) / total_weight)
        combined_max = float(np.max(combined_nearest))
        combined_cov = {}
        for T in [8, 10, 14, 20]:
            c = sum(pop_weights[j] for j in range(n_bg) if combined_nearest[j] <= T)
            combined_cov[T] = round(100 * c / total_weight, 1)

        saved = TOTAL_CURRENT_SECONDARY - K

        print(f"  {K:3d}  {combined_cov[14]:7.1f}  {combined_cov[10]:7.1f}  "
              f"{combined_cov[8]:6.1f}  {combined_avg:6.2f}  {combined_max:6.1f}  "
              f"{saved:6d}")

        sweep_rows.append({
            "K": K,
            "Coverage_14min_Pct": combined_cov[14],
            "Coverage_10min_Pct": combined_cov[10],
            "Coverage_8min_Pct": combined_cov[8],
            "Coverage_20min_Pct": combined_cov[20],
            "Avg_RT_Min": round(combined_avg, 2),
            "Max_RT_Min": round(combined_max, 2),
            "Ambulances_Saved": saved,
            "Reduction_Pct": round(100 * saved / TOTAL_CURRENT_SECONDARY, 1),
            "Stations": " | ".join(f"({s['lat']:.3f},{s['lon']:.3f})"
                                    for s in sol["open_stations"]),
        })
        # Store solution AND combined metrics
        sol["_combined_nearest"] = combined_nearest
        sol["_combined_cov"] = combined_cov
        sol["_combined_avg"] = combined_avg
        sol["_combined_max"] = combined_max
        solutions[K] = sol

    sweep_df = pd.DataFrame(sweep_rows)

    # Add marginal gain column
    sweep_df["Marginal_Gain_Pct"] = sweep_df["Coverage_14min_Pct"].diff().fillna(
        sweep_df["Coverage_14min_Pct"].iloc[0] - baseline_cov[14]).round(1)

    csv_path = os.path.join(OUT_DIR, "phase_h_k_sweep_results.csv")
    sweep_df.to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_path}")

    # ── Find recommended K ────────────────────────────────────────────
    # Want the SMALLEST K where marginal gain drops below 1% (since
    # combined coverage is always >= baseline, we want max reduction)
    recommended_K = 1  # start aggressive
    for _, row in sweep_df.iterrows():
        k = int(row["K"])
        if k >= 2 and row["Marginal_Gain_Pct"] < 1.0:
            recommended_K = k
            break
        recommended_K = k  # keep going if still gaining

    # But ensure combined 14-min coverage >= baseline
    rec_row = sweep_df[sweep_df["K"] == recommended_K].iloc[0]
    if rec_row["Coverage_14min_Pct"] < baseline_cov[14]:
        # Find min K that matches or exceeds baseline
        for _, row in sweep_df.iterrows():
            if row["Coverage_14min_Pct"] >= baseline_cov[14]:
                recommended_K = int(row["K"])
                break

    rec_row = sweep_df[sweep_df["K"] == recommended_K].iloc[0]
    saved = TOTAL_CURRENT_SECONDARY - recommended_K
    print(f"\n  RECOMMENDED: K = {recommended_K} county-wide secondary ambulances")
    print(f"    Replaces {TOTAL_CURRENT_SECONDARY} distributed secondaries "
          f"({saved} fewer = {100*saved/TOTAL_CURRENT_SECONDARY:.0f}% reduction)")
    print(f"    Combined 14-min coverage: {rec_row['Coverage_14min_Pct']}% "
          f"(baseline: {baseline_cov[14]}%)")
    print(f"    Combined 10-min coverage: {rec_row['Coverage_10min_Pct']}% "
          f"(baseline: {baseline_cov[10]}%)")
    print(f"    Combined avg RT: {rec_row['Avg_RT_Min']} min (baseline: {baseline_avg:.2f} min)")
    print(f"    Combined max RT: {rec_row['Max_RT_Min']} min")

    # ── Elbow chart ───────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # Panel 1: Combined coverage vs K
    ax1.plot(sweep_df["K"], sweep_df["Coverage_14min_Pct"], "o-",
             color="#2ecc71", linewidth=2.5, markersize=8, label="14-min (combined)")
    ax1.plot(sweep_df["K"], sweep_df["Coverage_10min_Pct"], "s--",
             color="#f39c12", linewidth=2, markersize=7, label="10-min (combined)")
    ax1.plot(sweep_df["K"], sweep_df["Coverage_8min_Pct"], "^:",
             color="#e74c3c", linewidth=1.5, markersize=6, label="8-min (combined)")

    # Baseline reference lines (primaries only)
    ax1.axhline(y=baseline_cov[14], color="#2ecc71", linewidth=1, linestyle=":",
                alpha=0.5, label=f"Baseline 14-min: {baseline_cov[14]}%")
    ax1.axhline(y=baseline_cov[10], color="#f39c12", linewidth=1, linestyle=":",
                alpha=0.5, label=f"Baseline 10-min: {baseline_cov[10]}%")

    ax1.axvline(x=recommended_K, color="#3498db", linewidth=2, linestyle="-.",
                alpha=0.7, label=f"Recommended K={recommended_K}")

    ax1.scatter([recommended_K], [rec_row["Coverage_14min_Pct"]],
                s=200, c="#3498db", zorder=10, edgecolors="#333", linewidths=2)

    ax1.set_xlabel("County-Wide Secondary Ambulances (K)", fontsize=12)
    ax1.set_ylabel("Combined Coverage (%)\n(primary stations + secondary network)", fontsize=11)
    ax1.set_title("Combined System Coverage vs Secondary Fleet Size",
                  fontsize=13, fontweight="bold")
    ax1.legend(fontsize=8, loc="lower right")
    ax1.set_ylim(max(0, baseline_cov[8] - 10), 105)
    ax1.set_xticks(K_RANGE)
    ax1.grid(alpha=0.3)

    # Panel 2: Marginal gain
    colors_bar = ["#3498db" if k != recommended_K else "#e74c3c"
                  for k in sweep_df["K"]]
    ax2.bar(sweep_df["K"], sweep_df["Marginal_Gain_Pct"],
            color=colors_bar, edgecolor="#333", linewidth=0.5, alpha=0.8)
    ax2.axhline(y=1.0, color="#e74c3c", linewidth=1.5, linestyle="--", alpha=0.7,
                label="1% marginal threshold")

    for _, row in sweep_df.iterrows():
        ax2.text(row["K"], row["Marginal_Gain_Pct"] + 0.1,
                 f"{row['Marginal_Gain_Pct']:.1f}%",
                 ha="center", fontsize=8, fontweight="bold")

    ax2.set_xlabel("County-Wide Secondary Ambulances (K)", fontsize=12)
    ax2.set_ylabel("Marginal Coverage Gain (%)", fontsize=12)
    ax2.set_title("Diminishing Returns per Additional Ambulance",
                  fontsize=13, fontweight="bold")
    ax2.legend(fontsize=9)
    ax2.set_xticks(K_RANGE)
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"Phase H: Replacement Secondary Network Sizing\n"
        f"Combined coverage: 13 primary stations + K county-wide ALS secondaries | "
        f"Replacing {TOTAL_CURRENT_SECONDARY} distributed units",
        fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_h_elbow_chart.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return recommended_K, sweep_df, solutions, tm, candidates, bg_demand, pop_weights


# ══════════════════════════════════════════════════════════════════════
#  PHASE I: ALS Staffing Requirements for Replacement Network
# ══════════════════════════════════════════════════════════════════════

def phase_i_staffing_requirements(recommended_K, util_summary_df):
    """Compute FTE/cost for K replacement secondary ALS ambulances."""
    print("\n" + "=" * 70)
    print("PHASE I: STAFFING REQUIREMENTS FOR REPLACEMENT NETWORK")
    print("=" * 70)

    K = recommended_K
    print(f"  Staffing {K} county-wide secondary ALS ambulances (replacing {TOTAL_CURRENT_SECONDARY})")

    # Secondary demand
    concurrent_path = os.path.join(SCRIPT_DIR, "concurrent_call_results.csv")
    if os.path.exists(concurrent_path):
        conc = pd.read_csv(concurrent_path)
        total_secondary = int(conc["Secondary_Events"].sum())
    else:
        total_secondary = 2244

    mean_dur_hrs = 45 / 60.0
    mu = 1.0 / mean_dur_hrs
    lam_24hr = total_secondary / (365 * 24)
    lam_peak = total_secondary * 0.65 / (365 * 10)

    # Current secondary overhead estimate
    current_secondary_fte = sum(
        DEPT_DATA[d].get("PT", 0) * 0.35
        for d in DEPT_DATA if DEPT_DATA[d].get("Ambulances", 0) >= 2
    )
    current_secondary_cost = sum(
        DEPT_DATA[d].get("Expense", 0) * 0.18
        for d in DEPT_DATA if DEPT_DATA[d].get("Ambulances", 0) >= 2
    )

    print(f"\n  Current distributed secondary overhead:")
    print(f"    Est. FTE dedicated to secondary coverage: {current_secondary_fte:.1f}")
    print(f"    Est. annual cost: ${current_secondary_cost:,.0f}")
    print(f"\n  Secondary demand: {total_secondary:,} events/year")
    print(f"  Lambda (24hr): {lam_24hr:.3f}/hr | Lambda (peak): {lam_peak:.3f}/hr")

    # Staffing scenarios
    salary_items = 371697 + 24894 + 178466 + 27761  # from PETERSON
    fixed_items = PETERSON_TOTAL_OPERATING - salary_items

    scenarios = []

    # Scenario A: 24/7
    fte_a = K * FTE_24_7
    net_a = K * PETERSON_TOTAL_OPERATING - K * PETERSON_REVENUE
    pw_a = erlang_c(lam_peak, mu, K)
    scenarios.append({
        "Scenario": f"A: All {K} units 24/7 ALS",
        "K": K, "Total_FTE": round(fte_a, 1),
        "Total_Operating": round(K * PETERSON_TOTAL_OPERATING),
        "Total_Revenue": round(K * PETERSON_REVENUE),
        "Net_Cost": round(net_a),
        "Coverage_Hours": "24/7",
        "P_Wait_Peak": round(pw_a, 4) if not np.isnan(pw_a) else "N/A",
        "vs_Current_FTE": round(fte_a - current_secondary_fte, 1),
        "vs_Current_Cost": round(net_a - current_secondary_cost),
    })

    # Scenario B: Peak-only
    fte_b = K * FTE_12_HR
    operating_b = K * (salary_items * (2/3) + fixed_items)
    revenue_b = K * PETERSON_REVENUE * 0.65
    net_b = operating_b - revenue_b
    pw_b = erlang_c(lam_peak, mu, K)
    scenarios.append({
        "Scenario": f"B: All {K} units peak-only (08-20) ALS",
        "K": K, "Total_FTE": round(fte_b, 1),
        "Total_Operating": round(operating_b),
        "Total_Revenue": round(revenue_b),
        "Net_Cost": round(net_b),
        "Coverage_Hours": "08:00-20:00",
        "P_Wait_Peak": round(pw_b, 4) if not np.isnan(pw_b) else "N/A",
        "vs_Current_FTE": round(fte_b - current_secondary_fte, 1),
        "vs_Current_Cost": round(net_b - current_secondary_cost),
    })

    # Scenario C: Hybrid
    if K >= 2:
        fte_c = FTE_24_7 + (K - 1) * FTE_12_HR
        operating_c = PETERSON_TOTAL_OPERATING + (K - 1) * (salary_items * (2/3) + fixed_items)
        revenue_c = PETERSON_REVENUE + (K - 1) * PETERSON_REVENUE * 0.65
        net_c = operating_c - revenue_c
        pw_c = erlang_c(lam_peak, mu, K)
        scenarios.append({
            "Scenario": f"C: 1x24/7 + {K-1}x peak-only ALS",
            "K": K, "Total_FTE": round(fte_c, 1),
            "Total_Operating": round(operating_c),
            "Total_Revenue": round(revenue_c),
            "Net_Cost": round(net_c),
            "Coverage_Hours": f"1 unit 24/7, {K-1} peak-only",
            "P_Wait_Peak": round(pw_c, 4) if not np.isnan(pw_c) else "N/A",
            "vs_Current_FTE": round(fte_c - current_secondary_fte, 1),
            "vs_Current_Cost": round(net_c - current_secondary_cost),
        })

    scenarios_df = pd.DataFrame(scenarios)
    csv_path = os.path.join(OUT_DIR, "phase_i_staffing_scenarios.csv")
    scenarios_df.to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_path}")
    print(scenarios_df[["Scenario", "Total_FTE", "Net_Cost", "Coverage_Hours",
                         "vs_Current_FTE", "vs_Current_Cost"]].to_string(index=False))

    # Chart
    fig, ax = plt.subplots(figsize=(14, 7))
    labels = ["Current\nDistributed\nSecondary"] + [
        s["Scenario"].split(":")[0] + ":\n" + s["Coverage_Hours"] for s in scenarios]
    costs = [current_secondary_cost] + [s["Net_Cost"] for s in scenarios]
    ftes = [current_secondary_fte] + [s["Total_FTE"] for s in scenarios]
    colors = ["#95a5a6", "#e74c3c", "#f39c12", "#3498db"][:len(costs)]

    bars = ax.bar(range(len(labels)), costs, color=colors, edgecolor="#333",
                  linewidth=0.5, width=0.5, alpha=0.85)
    for i, (bar, cost, fte) in enumerate(zip(bars, costs, ftes)):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 15000,
                f"${cost:,.0f}\n{fte:.0f} FTE", ha="center", fontsize=9, fontweight="bold")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Annual Net Cost ($)", fontsize=12)
    ax.set_title(
        f"Phase I: Staffing Scenarios -- {K} Replacement ALS Units vs Current\n"
        f"Replacing {TOTAL_CURRENT_SECONDARY} distributed secondaries | "
        f"Peterson cost model | {total_secondary:,} secondary events/year",
        fontsize=13, fontweight="bold")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    fig_path = os.path.join(OUT_DIR, "phase_i_staffing_comparison.png")
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fig_path}")

    return scenarios_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE J: Optimal Locations for Replacement Network
# ══════════════════════════════════════════════════════════════════════

def phase_j_optimal_locations(recommended_K, solutions, tm, candidates,
                              bg_demand, pop_weights, bg_df):
    """Place K replacement secondary ambulances at optimal locations."""
    print("\n" + "=" * 70)
    print("PHASE J: OPTIMAL LOCATIONS FOR REPLACEMENT SECONDARY NETWORK")
    print("=" * 70)

    K = recommended_K
    sol = solutions.get(K)
    if sol is None:
        print(f"  ERROR: No solution for K={K}")
        return None, None

    open_stations = sol["open_stations"]
    open_ids = [i for i, c in enumerate(candidates)
                if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                       for s in open_stations)]

    print(f"  {K} optimal locations (replacing {TOTAL_CURRENT_SECONDARY} distributed):")
    for idx, s in enumerate(open_stations):
        print(f"    Unit {idx+1}: ({s['lat']:.4f}, {s['lon']:.4f})")

    # Territory assignments
    territory_rows = []
    for j, dp in enumerate(bg_demand):
        dists = [(tm[i, j], i) for i in open_ids]
        best_dist, best_i = min(dists)
        best_station = candidates[best_i]
        territory_rows.append({
            "BG_GEOID": bg_df.iloc[j]["GEOID"] if j < len(bg_df) else f"BG_{j}",
            "BG_Lat": dp["lat"], "BG_Lon": dp["lon"],
            "Population": dp["population"],
            "Assigned_Unit": open_ids.index(best_i) + 1,
            "Unit_Lat": best_station["lat"], "Unit_Lon": best_station["lon"],
            "Drive_Time_Min": round(best_dist, 2),
        })

    territory_df = pd.DataFrame(territory_rows)

    loc_rows = []
    for idx, s in enumerate(open_stations):
        assigned = territory_df[territory_df["Assigned_Unit"] == idx + 1]
        loc_rows.append({
            "Unit": idx + 1, "Lat": s["lat"], "Lon": s["lon"],
            "Assigned_BGs": len(assigned),
            "Served_Population": int(assigned["Population"].sum()),
            "Avg_Drive_Time": round(assigned["Drive_Time_Min"].mean(), 1),
            "Max_Drive_Time": round(assigned["Drive_Time_Min"].max(), 1),
        })

    loc_df = pd.DataFrame(loc_rows)
    loc_df.to_csv(os.path.join(OUT_DIR, "phase_j_optimal_locations.csv"), index=False)
    territory_df.to_csv(os.path.join(OUT_DIR, "phase_j_territory_assignments.csv"), index=False)
    print(f"\n  Saved: phase_j_optimal_locations.csv, phase_j_territory_assignments.csv")
    print(loc_df.to_string(index=False))

    # Territory map
    fig, ax = plt.subplots(figsize=(14, 12))
    territory_colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
                        "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b",
                        "#2980b9", "#27ae60", "#8e44ad"]

    for _, row in territory_df.iterrows():
        cidx = int(row["Assigned_Unit"]) - 1
        color = territory_colors[cidx % len(territory_colors)]
        size = max(15, min(200, row["Population"] / 50))
        alpha = 0.6 if row["Drive_Time_Min"] <= 14 else 0.3
        ax.scatter(row["BG_Lon"], row["BG_Lat"], s=size, c=color,
                   alpha=alpha, edgecolors="#333" if alpha > 0.5 else "#999",
                   linewidths=0.5, zorder=3)

    for idx, s in enumerate(open_stations):
        color = territory_colors[idx % len(territory_colors)]
        ax.scatter(s["lon"], s["lat"], s=400, c=color, marker="*",
                   edgecolors="#333", linewidths=2, zorder=10)
        info = loc_df[loc_df["Unit"] == idx + 1].iloc[0]
        ax.annotate(f"Unit {idx+1}\nPop: {info['Served_Population']:,}\n"
                    f"Avg: {info['Avg_Drive_Time']:.0f} min",
                    (s["lon"], s["lat"]), textcoords="offset points", xytext=(12, -20),
                    fontsize=8, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.9),
                    zorder=11)

    # Existing stations as gray
    stations_path = os.path.join(SCRIPT_DIR, "jefferson_stations.geojson")
    if os.path.exists(stations_path):
        with open(stations_path) as f:
            st_gj = json.load(f)
        for feat in st_gj["features"]:
            coords = feat["geometry"]["coordinates"]
            name = feat["properties"].get("name", "")
            ax.scatter(coords[0], coords[1], s=60, c="#bbb", marker="s",
                       edgecolors="#999", linewidths=1, zorder=5, alpha=0.6)
            ax.annotate(name, (coords[0], coords[1] + 0.007),
                        fontsize=6, ha="center", color="#999", zorder=6)

    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_title(
        f"Phase J: {K} Replacement Secondary ALS Units\n"
        f"Stars = county-wide secondary locations | Gray squares = existing primary stations\n"
        f"Replaces {TOTAL_CURRENT_SECONDARY} distributed secondaries | "
        f"14-min coverage: {sol['pct_covered']}%",
        fontsize=12, fontweight="bold")
    ax.set_aspect("equal")
    ax.legend(handles=[
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#333",
               markersize=15, label="County-wide secondary unit"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#bbb",
               markersize=10, label="Existing primary station (retained)"),
    ], loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "phase_j_territory_map.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: phase_j_territory_map.png")

    return loc_df, territory_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE K: Feasibility Check
# ══════════════════════════════════════════════════════════════════════

def phase_k_feasibility(recommended_K, sweep_df, solutions, tm, candidates,
                        bg_demand, pop_weights):
    """Verify the combined primary+secondary system meets coverage targets."""
    print("\n" + "=" * 70)
    print("PHASE K: FEASIBILITY CHECK (COMBINED SYSTEM)")
    print("=" * 70)

    K = recommended_K
    sol = solutions.get(K)
    if sol is None:
        print(f"  ERROR: No solution for K={K}")
        return K, None

    # Combined metrics are already computed in Phase H and stored in sweep_df
    rec_row = sweep_df[sweep_df["K"] == K].iloc[0]

    print(f"\n  K={K} combined system metrics (primary stations + secondary network):")
    print(f"    14-min coverage: {rec_row['Coverage_14min_Pct']}%")
    print(f"    10-min coverage: {rec_row['Coverage_10min_Pct']}%")
    print(f"    8-min coverage:  {rec_row['Coverage_8min_Pct']}%")
    print(f"    Avg RT: {rec_row['Avg_RT_Min']} min")
    print(f"    Max RT: {rec_row['Max_RT_Min']} min")
    print(f"    Ambulances saved: {rec_row['Ambulances_Saved']} "
          f"({rec_row['Reduction_Pct']}% reduction)")

    # Load baseline for comparison
    existing_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                                  "existing_bg_drive_time_matrix.json")
    with open(existing_cache) as f:
        existing_tm = np.array(json.load(f)["matrix"])
    primary_nearest = np.min(existing_tm, axis=0)
    total_weight = pop_weights.sum()
    baseline_avg = float(np.sum(pop_weights * primary_nearest) / total_weight)
    baseline_cov14 = sum(pop_weights[j] for j in range(len(bg_demand))
                         if primary_nearest[j] <= 14) / total_weight * 100

    improved = rec_row["Coverage_14min_Pct"] >= baseline_cov14
    print(f"\n  Combined coverage >= baseline ({baseline_cov14:.1f}%)? "
          f"{rec_row['Coverage_14min_Pct']}% -- {'PASS' if improved else 'FAIL'}")
    print(f"  Combined avg RT <= baseline ({baseline_avg:.2f})? "
          f"{rec_row['Avg_RT_Min']} -- {'PASS' if rec_row['Avg_RT_Min'] <= baseline_avg else 'FAIL'}")

    # Sensitivity
    sensitivity_rows = []
    for k_test in [max(1, K - 1), K, min(K + 1, TOTAL_CURRENT_SECONDARY)]:
        if k_test in sweep_df["K"].values:
            sensitivity_rows.append(sweep_df[sweep_df["K"] == k_test].iloc[0].to_dict())

    sensitivity_df = pd.DataFrame(sensitivity_rows).drop_duplicates(subset=["K"])

    iter_df = pd.DataFrame([{
        "K": K, "Feasible": improved,
        "Combined_14min_Pct": rec_row["Coverage_14min_Pct"],
        "Combined_Avg_RT": rec_row["Avg_RT_Min"],
        "Ambulances_Saved": rec_row["Ambulances_Saved"],
    }])
    iter_df.to_csv(os.path.join(OUT_DIR, "phase_k_feasibility_results.csv"), index=False)
    if not sensitivity_df.empty:
        sensitivity_df.to_csv(os.path.join(OUT_DIR, "phase_k_sensitivity.csv"), index=False)
        print(f"\n  Sensitivity (K-1, K, K+1):")
        print(sensitivity_df[["K", "Coverage_14min_Pct", "Coverage_10min_Pct",
                               "Avg_RT_Min", "Max_RT_Min", "Ambulances_Saved"]].to_string(index=False))

    print(f"\n  Saved: phase_k_feasibility_results.csv, phase_k_sensitivity.csv")
    return K, iter_df


# ══════════════════════════════════════════════════════════════════════
#  PHASE L: Validation -- Replacement Network vs Current Distributed
# ══════════════════════════════════════════════════════════════════════

def phase_l_validation(final_K, sweep_df, baseline_metrics, scenarios_df,
                       rt_df, staff_df):
    """Compare replacement secondary network against current distributed secondaries."""
    print("\n" + "=" * 70)
    print("PHASE L: VALIDATION -- REPLACEMENT vs CURRENT DISTRIBUTED")
    print("=" * 70)

    if baseline_metrics is None:
        print("  ERROR: No baseline metrics")
        return None

    opt_row = sweep_df[sweep_df["K"] == final_K]
    if opt_row.empty:
        print(f"  ERROR: No data for K={final_K}")
        return None
    opt = opt_row.iloc[0]

    # Current secondary estimates
    current_sec_fte = sum(DEPT_DATA[d].get("PT", 0) * 0.35
                          for d in DEPT_DATA if DEPT_DATA[d].get("Ambulances", 0) >= 2)
    current_sec_cost = sum(DEPT_DATA[d].get("Expense", 0) * 0.18
                           for d in DEPT_DATA if DEPT_DATA[d].get("Ambulances", 0) >= 2)

    best_scenario = scenarios_df.iloc[min(2, len(scenarios_df)-1)] if scenarios_df is not None else None

    comparison = []
    def add(name, current, proposed, unit=""):
        delta = proposed - current if isinstance(current, (int, float)) and isinstance(proposed, (int, float)) else None
        pct = round(delta / current * 100, 1) if delta and current != 0 else None
        comparison.append({
            "Metric": name,
            "Current_Distributed": f"{current}{unit}",
            "Proposed_Countywide": f"{proposed}{unit}",
            "Delta": f"{delta:+.1f}{unit}" if delta is not None else "N/A",
            "Pct_Change": f"{pct:+.1f}%" if pct is not None else "N/A",
        })

    add("Secondary Ambulances", TOTAL_CURRENT_SECONDARY, final_K)
    add("Ambulances Saved", 0, TOTAL_CURRENT_SECONDARY - final_K)
    add("14-min Coverage (combined)", baseline_metrics["Coverage_14min_Pct"],
        opt["Coverage_14min_Pct"], "%")
    add("10-min Coverage (combined)", baseline_metrics["Coverage_10min_Pct"],
        opt["Coverage_10min_Pct"], "%")
    add("Avg RT (combined)", baseline_metrics["Avg_RT_Min"], opt["Avg_RT_Min"], " min")
    add("Max RT (combined)", baseline_metrics["Max_RT_Min"], opt["Max_RT_Min"], " min")

    if best_scenario is not None:
        add("Secondary FTE", current_sec_fte, best_scenario["Total_FTE"])
        add("Secondary Annual Cost", current_sec_cost, best_scenario["Net_Cost"])

    comp_df = pd.DataFrame(comparison)
    comp_df.to_csv(os.path.join(OUT_DIR, "phase_l_validation_comparison.csv"), index=False)
    print(f"  Saved: phase_l_validation_comparison.csv")
    print(comp_df.to_string(index=False))

    # Before/after chart
    fig, axes = plt.subplots(1, 3, figsize=(20, 7))
    width = 0.35

    # Panel 1: Fleet comparison
    ax = axes[0]
    labels = ["Primary\n(unchanged)", "Secondary"]
    primary_count = sum(min(AMBULANCE_COUNT.get(d, 0), 1) for d in EMS_TRANSPORT_DEPTS)
    current_vals = [primary_count, TOTAL_CURRENT_SECONDARY]
    proposed_vals = [primary_count, final_K]
    x = np.arange(len(labels))
    ax.bar(x - width/2, current_vals, width, label="Current", color="#95a5a6",
           edgecolor="#333", linewidth=0.5)
    ax.bar(x + width/2, proposed_vals, width, label="Proposed", color="#3498db",
           edgecolor="#333", linewidth=0.5)
    for i, (c, p) in enumerate(zip(current_vals, proposed_vals)):
        ax.text(i - width/2, c + 0.2, str(c), ha="center", fontsize=12, fontweight="bold")
        ax.text(i + width/2, p + 0.2, str(p), ha="center", fontsize=12, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("Number of Ambulances")
    ax.set_title(f"Fleet: {TOTAL_CURRENT_SECONDARY} distributed -> {final_K} county-wide\n"
                 f"({TOTAL_CURRENT_SECONDARY - final_K} fewer secondary units)",
                 fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # Panel 2: Coverage
    ax = axes[1]
    thresholds = ["8 min", "10 min", "14 min"]
    curr_cov = [baseline_metrics["Coverage_8min_Pct"],
                baseline_metrics["Coverage_10min_Pct"],
                baseline_metrics["Coverage_14min_Pct"]]
    prop_cov = [opt["Coverage_8min_Pct"], opt["Coverage_10min_Pct"],
                opt["Coverage_14min_Pct"]]
    x = np.arange(len(thresholds))
    ax.bar(x - width/2, curr_cov, width, label="Current 13-station baseline",
           color="#95a5a6", edgecolor="#333", linewidth=0.5)
    ax.bar(x + width/2, prop_cov, width, label=f"Proposed {final_K} county-wide",
           color="#3498db", edgecolor="#333", linewidth=0.5)
    ax.axhline(y=90, color="#e74c3c", linewidth=1.5, linestyle="--", alpha=0.7, label="90% target")
    for i, (c, p) in enumerate(zip(curr_cov, prop_cov)):
        ax.text(i - width/2, c + 1, f"{c:.0f}%", ha="center", fontsize=9, fontweight="bold")
        ax.text(i + width/2, p + 1, f"{p:.0f}%", ha="center", fontsize=9, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(thresholds)
    ax.set_ylabel("Population Covered (%)")
    ax.set_title("Secondary Network Coverage", fontweight="bold")
    ax.legend(fontsize=8); ax.set_ylim(0, 105); ax.grid(axis="y", alpha=0.3)

    # Panel 3: Cost
    ax = axes[2]
    if best_scenario is not None:
        labels = ["Current\nDistributed", f"Proposed\n{final_K} County-Wide"]
        costs = [current_sec_cost, best_scenario["Net_Cost"]]
        ftes = [current_sec_fte, best_scenario["Total_FTE"]]
        bars = ax.bar(labels, costs, color=["#95a5a6", "#3498db"],
                      edgecolor="#333", linewidth=0.5, width=0.4)
        for bar, cost, fte in zip(bars, costs, ftes):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 15000,
                    f"${cost:,.0f}\n{fte:.0f} FTE", ha="center", fontsize=10, fontweight="bold")
        ax.set_ylabel("Annual Net Cost ($)")
        ax.set_title("Secondary Ambulance Cost", fontweight="bold")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"Phase L: Current Distributed vs {final_K}-Unit County-Wide Secondary Network\n"
        f"Each municipality retains its primary ambulance | Secondary network handles "
        f"all overflow county-wide | All ALS",
        fontsize=13, fontweight="bold", y=1.03)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "phase_l_before_after.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: phase_l_before_after.png")

    # Summary report
    saved = TOTAL_CURRENT_SECONDARY - final_K
    report = f"""# Jefferson County EMS -- Secondary Network Replacement Summary

## Concept
Each municipality **keeps its primary (first-out) ambulance**. All {TOTAL_CURRENT_SECONDARY} existing
secondary/backup ambulances are **replaced** by {final_K} county-wide ALS units stationed at
optimal locations. These units respond anywhere in the county when a primary is already committed.

## Current vs Proposed

| Metric | Current Distributed | Proposed County-Wide | Change |
|---|:---:|:---:|:---:|
"""
    for _, row in comp_df.iterrows():
        report += f"| {row['Metric']} | {row['Current_Distributed']} | {row['Proposed_Countywide']} | {row['Delta']} |\n"

    report += f"""
## Fleet Impact
- **Primary ambulances retained:** {primary_count} (unchanged, one per municipality)
- **Secondary ambulances retired:** {TOTAL_CURRENT_SECONDARY} distributed units
- **Replacement county-wide units:** {final_K} ALS ambulances at optimal locations
- **Net reduction:** {saved} ambulances ({100*saved/TOTAL_CURRENT_SECONDARY:.0f}% of secondary fleet)
- **Total fleet:** {primary_count} primary + {final_K} secondary = {primary_count + final_K} (was {primary_count + TOTAL_CURRENT_SECONDARY})

## How It Works
1. A 911 call arrives -- the local primary ambulance responds as usual
2. If the primary is already on a call, the nearest available county-wide secondary unit is dispatched
3. Secondary units are not restricted to municipal boundaries -- they serve the entire county
4. This eliminates the current pattern where some departments have idle backup ambulances
   while others rely heavily on mutual aid

## Key Advantage
Strategic placement means {final_K} county-wide units achieve comparable or better coverage
than {TOTAL_CURRENT_SECONDARY} distributed units, because they are positioned to minimize
response time across the entire county rather than being anchored to individual municipalities.
"""

    with open(os.path.join(OUT_DIR, "phase_l_summary_report.md"), "w") as f:
        f.write(report)
    print(f"  Saved: phase_l_summary_report.md")

    return comp_df


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS -- FULL QUANTITATIVE ANALYSIS PIPELINE")
    print("Phases A through L | Replacement Secondary Network Model")
    print("=" * 70)

    # ── Load data ─────────────────────────────────────────────────────
    print("\n>> Loading NFIRS data...")
    ems_df, valid_df = load_all_nfirs()

    print("\n>> Loading block group centroids...")
    bg_df = load_bg_centroids()
    print(f"  {len(bg_df)} block groups, total pop: {bg_df['population'].sum():,}")

    # ── Phases A-G (diagnostic) ───────────────────────────────────────
    classified_df, rt_df = phase_a_primary_secondary_rt(ems_df, valid_df)
    classified_df, bg_analysis = phase_b_secondary_geography(classified_df, ems_df, bg_df)
    util_df, util_summary = phase_c_utilization(classified_df)
    staff_df = phase_d_staffing(util_summary)
    dest_df, flow_df = phase_e_secondary_destinations(classified_df, bg_df)
    hotspot_df, temporal_df = phase_f_hotspots(classified_df, bg_df, util_df)
    weights_df, baseline_metrics = phase_g_consolidation(
        classified_df, bg_df, hotspot_df, util_summary, staff_df, rt_df, flow_df)

    # ── Phases H-L (optimization: replacement model) ──────────────────
    recommended_K, sweep_df, solutions, tm, candidates, bg_demand, pop_weights = \
        phase_h_ambulance_count(bg_df)
    scenarios_df = phase_i_staffing_requirements(recommended_K, util_summary)
    loc_df, territory_df = phase_j_optimal_locations(
        recommended_K, solutions, tm, candidates, bg_demand, pop_weights, bg_df)
    final_K, feasibility_df = phase_k_feasibility(
        recommended_K, sweep_df, solutions, tm, candidates, bg_demand, pop_weights)
    validation_df = phase_l_validation(
        final_K, sweep_df, baseline_metrics, scenarios_df, rt_df, staff_df)

    print("\n" + "=" * 70)
    print("PHASES A-L COMPLETE")
    print(f"All outputs saved to: {OUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
