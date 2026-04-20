"""
Jefferson County EMS — Municipal Boundary & Labor Optimization Analysis
=======================================================================
Diagnostic analysis: Identifies structural staffing overhead vs. call-demand-
justified labor, station coverage overlap, and consolidation scenario modeling.

NOT prescriptive — quantifies the problem so the Working Group can draw conclusions.

Author: ISyE 450 Senior Design Team
Date: March 2026
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon
from math import radians, sin, cos, sqrt, atan2
import json
import os
import time
import requests
import warnings
warnings.filterwarnings("ignore")

# Load ORS API key from .env file
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isochrone_cache")

# ==============================================================================
# 1. RAW DATA — All from ems_dashboard_app.py + contract files + chief interview
# ==============================================================================

# Department master table (EMS-providing departments only)
# Sources: FY2025 budgets, MABAS asset filings, 2024 NFIRS call data
departments = pd.DataFrame([
    # Dept             | FT | PT | EMS_Calls_2024 | Total_Calls | Pop_Served | Expense    | Model       | Level | Ambulances | Lat       | Lon        | Cross_County
    {"Dept": "Watertown",     "FT": 31, "PT":  3, "EMS_Calls": 1947, "Total_Calls": 2719, "Pop": 23000, "Expense": 3833800, "Model": "Career",      "Level": "ALS",  "Ambulances": 3, "Lat": 43.1861, "Lon": -88.7339, "Cross_County": True,  "Cross_Note": "Straddles Jefferson/Dodge county line; ~36% pop in Dodge Co."},
    {"Dept": "Fort Atkinson", "FT": 16, "PT": 28, "EMS_Calls": 1621, "Total_Calls": 2076, "Pop": 16300, "Expense":  760950, "Model": "Career+PT",   "Level": "ALS",  "Ambulances": 3, "Lat": 42.9271, "Lon": -88.8397, "Cross_County": False, "Cross_Note": "Interior — fully within Jefferson Co."},
    {"Dept": "Whitewater",    "FT": 15, "PT": 17, "EMS_Calls": 1448, "Total_Calls": 1812, "Pop":  4296, "Expense": 2710609, "Model": "Career+PT",   "Level": "ALS",  "Ambulances": 2, "Lat": 42.8325, "Lon": -88.7332, "Cross_County": True,  "Cross_Note": "Straddles Jefferson/Walworth/Rock; Jeff Co. portion only 4,296 of ~15K total"},
    {"Dept": "Edgerton",      "FT": 24, "PT":  0, "EMS_Calls": 2035, "Total_Calls": 2472, "Pop":  3763, "Expense":  704977, "Model": "Career+PT",   "Level": "ALS",  "Ambulances": 2, "Lat": 42.8403, "Lon": -89.0629, "Cross_County": True,  "Cross_Note": "Lakeside Fire-Rescue: Rock/Dane/Jefferson; Jeff Co. pop is small fraction of 25K+ district"},
    {"Dept": "Jefferson",     "FT":  6, "PT": 20, "EMS_Calls":   91, "Total_Calls":  238, "Pop":  7800, "Expense": 1500300, "Model": "Career",      "Level": "ALS",  "Ambulances": 5, "Lat": 43.0056, "Lon": -88.8014, "Cross_County": False, "Cross_Note": "Interior — City of Jefferson + surrounding towns"},
    {"Dept": "Johnson Creek", "FT":  3, "PT": 40, "EMS_Calls":  454, "Total_Calls":  636, "Pop":  3367, "Expense": 1134154, "Model": "Volunteer",   "Level": "ALS",  "Ambulances": 2, "Lat": 43.0753, "Lon": -88.7745, "Cross_County": False, "Cross_Note": "Interior — Village + Town of Aztalan portions"},
    {"Dept": "Waterloo",      "FT":  4, "PT": 22, "EMS_Calls":  403, "Total_Calls":  520, "Pop":  4415, "Expense": 1102475, "Model": "Career+Vol",  "Level": "AEMT", "Ambulances": 2, "Lat": 43.1886, "Lon": -88.9797, "Cross_County": True,  "Cross_Note": "Corner of Jefferson/Dodge/Dane/Columbia; serves parts of all 4 counties"},
    {"Dept": "Lake Mills",    "FT":  4, "PT": 20, "EMS_Calls":  None,"Total_Calls":  None,"Pop":  8700, "Expense":  347000, "Model": "Career+Vol",  "Level": "BLS",  "Ambulances": 1, "Lat": 43.0781, "Lon": -88.9144, "Cross_County": False, "Cross_Note": "Interior — City + Town of Lake Mills (Ryan Brothers contract for ALS)"},
    {"Dept": "Ixonia",        "FT":  2, "PT": 45, "EMS_Calls":  260, "Total_Calls":  338, "Pop":  5078, "Expense":  631144, "Model": "Volunteer+FT","Level": "BLS",  "Ambulances": 1, "Lat": 43.1446, "Lon": -88.5970, "Cross_County": False, "Cross_Note": "Interior — Town of Ixonia"},
    {"Dept": "Palmyra",       "FT":  0, "PT": 20, "EMS_Calls":  105, "Total_Calls":  140, "Pop":  3341, "Expense":  817740, "Model": "Volunteer",   "Level": "BLS",  "Ambulances": 1, "Lat": 42.8794, "Lon": -88.5855, "Cross_County": False, "Cross_Note": "Interior — Village + Town of Palmyra"},
    {"Dept": "Cambridge",     "FT":  0, "PT": 31, "EMS_Calls":   64, "Total_Calls":  197, "Pop":  1650, "Expense":   92000, "Model": "Volunteer",   "Level": "ALS",  "Ambulances": 0, "Lat": 43.0049, "Lon": -89.0224, "Cross_County": True,  "Cross_Note": "Straddles Jefferson/Dane; Village withdrew from EMS Commission 2025"},
    # Note: Helenville has no ambulances — served by Jefferson EMS. Included for geographic coverage.
    {"Dept": "Helenville",    "FT":  0, "PT": 13, "EMS_Calls":  None,"Total_Calls":  None,"Pop":  1500, "Expense":   None,  "Model": "Volunteer",   "Level": "BLS",  "Ambulances": 0, "Lat": 43.0135, "Lon": -88.6998, "Cross_County": False, "Cross_Note": "Interior — no ambulance; EMS served by Jefferson"},
    # Western Lakes: multi-county (Waukesha primary), small Jeff Co. footprint
    {"Dept": "Western Lakes", "FT":  0, "PT":  0, "EMS_Calls":  None,"Total_Calls":  None,"Pop":  2974, "Expense":   None,  "Model": "Career+PT",   "Level": "ALS",  "Ambulances": 0, "Lat": 43.0110, "Lon": -88.5877, "Cross_County": True,  "Cross_Note": "Primary base in Waukesha Co.; serves Sullivan/Rome in Jeff Co."},
])

# ==============================================================================
# 2. LABOR CAPACITY MODEL
# ==============================================================================

def compute_labor_model(df):
    """
    For each department, compute:
    - min_fte_24_7: Minimum FTEs needed for 24/7 2-person ambulance coverage
    - demand_fte: FTEs justified by actual call volume
    - structural_overhead: The gap (labor that exists to meet minimums, not demand)

    Key assumptions (documented):
    - 24/7 coverage requires 3 shifts × 2 crew = 6 FTE minimum (before relief factor)
    - Relief factor of 1.2 accounts for vacation/sick/training → 7.2 FTE practical minimum
    - Demand benchmark: ~1,200 responses/FTE/year for a busy urban system (NFPA/ICMA)
      but rural WI is lower-volume; we use 800 calls/FTE/year as a generous benchmark
    - Each call averages ~1 hour (response + scene + transport + turnaround)
    """

    MIN_CREW = 2           # WI state minimum per ambulance response
    SHIFTS = 3             # 24-hour coverage = 3 × 8-hr shifts (or 2 × 12-hr)
    RELIEF_FACTOR = 1.2    # Account for PTO, sick, training (~20% overhead)
    CALLS_PER_FTE_YEAR = 800  # Generous benchmark for rural/suburban EMS

    # Minimum FTEs for 24/7 single-ambulance coverage
    min_fte = MIN_CREW * SHIFTS * RELIEF_FACTOR  # = 7.2

    results = []
    for _, row in df.iterrows():
        ems_calls = row["EMS_Calls"]

        # Skip departments without call data
        if pd.isna(ems_calls):
            results.append({
                "Dept": row["Dept"],
                "Min_FTE_24_7": min_fte,
                "Demand_FTE": None,
                "Structural_Overhead_FTE": None,
                "Actual_FT": row["FT"],
                "Actual_Total": row["FT"] + row["PT"],
                "Calls_Per_FT": None,
                "Utilization_Pct": None,
                "Note": "No call data available"
            })
            continue

        # FTEs justified by call demand
        # Each call ≈ 1 hr → calls/year ÷ 2080 working hrs/FTE = demand FTEs
        # But minimum 2 people per call, so demand_fte = (calls × avg_hours × crew) / 2080
        avg_call_duration_hrs = 1.0  # conservative: includes response + scene + transport + turnaround
        demand_fte = (ems_calls * avg_call_duration_hrs * MIN_CREW) / 2080

        # Structural overhead = minimum floor minus what demand justifies
        overhead = max(0, min_fte - demand_fte)

        # Actual utilization
        calls_per_ft = ems_calls / max(row["FT"], 1)

        # What % of the 24/7 capacity is actually used by calls?
        # Available crew-hours per year = min_fte × 2080
        # Used crew-hours = calls × duration × crew_size
        available_hrs = min_fte * 2080
        used_hrs = ems_calls * avg_call_duration_hrs * MIN_CREW
        utilization_pct = (used_hrs / available_hrs) * 100

        results.append({
            "Dept": row["Dept"],
            "Min_FTE_24_7": min_fte,
            "Demand_FTE": round(demand_fte, 2),
            "Structural_Overhead_FTE": round(overhead, 2),
            "Actual_FT": row["FT"],
            "Actual_Total": row["FT"] + row["PT"],
            "Calls_Per_FT": round(calls_per_ft, 1),
            "Utilization_Pct": round(utilization_pct, 1),
            "Cross_County": row["Cross_County"],
            "Note": row["Cross_Note"] if row["Cross_County"] else ""
        })

    return pd.DataFrame(results)


# ==============================================================================
# 3. GEOGRAPHIC DISTANCE & COVERAGE MODEL
# ==============================================================================

def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points in miles."""
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def compute_distance_matrix(df):
    """Compute pairwise distances between all stations (miles)."""
    n = len(df)
    names = df["Dept"].values
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                dist[i, j] = haversine_miles(
                    df.iloc[i]["Lat"], df.iloc[i]["Lon"],
                    df.iloc[j]["Lat"], df.iloc[j]["Lon"]
                )
    return pd.DataFrame(dist, index=names, columns=names).round(2)


def estimate_drive_time_min(distance_miles, avg_speed_mph=35):
    """
    Estimate drive time from straight-line distance.
    Rural roads are not straight — apply a 1.3x road winding factor.
    Average emergency response speed: 35 mph (rural mix of highway + back roads).
    """
    ROAD_FACTOR = 1.3  # roads are ~30% longer than straight-line
    road_distance = distance_miles * ROAD_FACTOR
    return (road_distance / avg_speed_mph) * 60  # convert to minutes


def find_coverage_overlaps(dist_matrix, threshold_miles=8.0):
    """
    Find station pairs within threshold distance (potential coverage overlap).
    8 miles ≈ 10-minute drive at 35 mph with winding factor.
    These are candidates for consolidation — one station could potentially
    cover the other's territory.
    """
    overlaps = []
    names = dist_matrix.index.tolist()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = dist_matrix.iloc[i, j]
            if d <= threshold_miles:
                drive_min = estimate_drive_time_min(d)
                overlaps.append({
                    "Station_A": names[i],
                    "Station_B": names[j],
                    "Distance_Miles": round(d, 2),
                    "Est_Drive_Min": round(drive_min, 1),
                    "Within_NFPA_1720": drive_min <= 14,  # NFPA 1720 rural = 14 min
                })
    return pd.DataFrame(overlaps).sort_values("Distance_Miles")


# ==============================================================================
# 3b. REAL DRIVE-TIME ISOCHRONES (OpenRouteService API)
# ==============================================================================

def fetch_isochrones(dept_df, thresholds_min=(8, 14, 20)):
    """
    Fetch real road-network drive-time isochrones from OpenRouteService.
    Results are cached to disk so we only hit the API once per station.

    Args:
        dept_df: DataFrame with Dept, Lat, Lon columns
        thresholds_min: tuple of drive-time thresholds in minutes

    Returns:
        dict: {dept_name: {threshold_min: GeoJSON polygon feature, ...}, ...}
    """
    if not ORS_API_KEY or ORS_API_KEY == "your_key_here":
        print("  [SKIP] No ORS API key found in .env -- skipping isochrone fetch")
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)
    url = "https://api.openrouteservice.org/v2/isochrones/driving-car"
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json",
    }
    thresholds_sec = [t * 60 for t in thresholds_min]

    results = {}
    for _, row in dept_df.iterrows():
        dept = row["Dept"]
        cache_file = os.path.join(CACHE_DIR, f"{dept.replace(' ', '_')}.json")

        # Use cache if available
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                results[dept] = json.load(f)
            print(f"    {dept}: loaded from cache")
            continue

        # Call ORS API
        payload = {
            "locations": [[row["Lon"], row["Lat"]]],
            "range": thresholds_sec,
            "range_type": "time",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # Parse features into {threshold: feature} dict
                iso_data = {}
                for feat in data.get("features", []):
                    val_sec = feat["properties"]["value"]
                    val_min = val_sec / 60
                    iso_data[str(int(val_min))] = feat
                results[dept] = iso_data

                # Cache to disk
                with open(cache_file, "w") as f:
                    json.dump(iso_data, f)
                print(f"    {dept}: fetched OK ({len(iso_data)} thresholds)")
            elif resp.status_code == 429:
                print(f"    {dept}: rate limited (429) -- waiting 60s and retrying")
                time.sleep(60)
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    iso_data = {}
                    for feat in data.get("features", []):
                        val_sec = feat["properties"]["value"]
                        val_min = val_sec / 60
                        iso_data[str(int(val_min))] = feat
                    results[dept] = iso_data
                    with open(cache_file, "w") as f:
                        json.dump(iso_data, f)
                    print(f"    {dept}: fetched OK after retry")
                else:
                    print(f"    {dept}: FAILED after retry ({resp.status_code})")
            else:
                print(f"    {dept}: FAILED ({resp.status_code}: {resp.text[:100]})")
        except Exception as e:
            print(f"    {dept}: ERROR ({e})")

        # Rate limit: ORS free tier = 20 req/min
        time.sleep(3)

    return results


def compute_real_drive_times(dept_df, isochrones):
    """
    For each station pair, determine if Station B falls within Station A's
    isochrone polygons. This gives us real drive-time overlap data.

    Returns DataFrame with station pairs and which thresholds they fall within.
    """
    if isochrones is None:
        return None

    from shapely.geometry import shape, Point

    pairs = []
    for _, row_a in dept_df.iterrows():
        dept_a = row_a["Dept"]
        if dept_a not in isochrones:
            continue

        for _, row_b in dept_df.iterrows():
            dept_b = row_b["Dept"]
            if dept_a == dept_b:
                continue

            pt_b = Point(row_b["Lon"], row_b["Lat"])

            within_min = None
            # Check from smallest threshold to largest
            for thresh in sorted(isochrones[dept_a].keys(), key=int):
                feat = isochrones[dept_a][thresh]
                poly = shape(feat["geometry"])
                if poly.contains(pt_b):
                    within_min = int(thresh)
                    break

            if within_min is not None:
                pairs.append({
                    "From": dept_a,
                    "To": dept_b,
                    "Real_Drive_Min": within_min,
                    "Within_8min": within_min <= 8,
                    "Within_14min": within_min <= 14,
                    "Within_20min": within_min <= 20,
                })

    if not pairs:
        return None
    return pd.DataFrame(pairs)


def plot_isochrone_map(dept_df, isochrones):
    """
    Map with real road-network drive-time polygons instead of circles.
    Shows 8-min (red), 14-min (orange), 20-min (green) coverage zones.
    """
    if isochrones is None:
        print("  [SKIP] No isochrone data -- skipping isochrone map")
        return

    fig, ax = plt.subplots(figsize=(16, 14))

    # Color scheme: tightest threshold = most intense
    threshold_colors = {
        "8":  ("#e74c3c", 0.25),  # red, NFPA 1710 career
        "14": ("#f39c12", 0.15),  # orange, NFPA 1720 rural
        "20": ("#2ecc71", 0.10),  # green, extended coverage
    }

    # Plot isochrone polygons (largest first so smaller ones overlay)
    for thresh in ["20", "14", "8"]:
        color, alpha = threshold_colors.get(thresh, ("#cccccc", 0.1))
        for dept, iso_data in isochrones.items():
            if thresh not in iso_data:
                continue
            feat = iso_data[thresh]
            geom = feat["geometry"]

            if geom["type"] == "Polygon":
                coords_list = [geom["coordinates"]]
            elif geom["type"] == "MultiPolygon":
                coords_list = geom["coordinates"]
            else:
                continue

            for poly_coords in coords_list:
                exterior = poly_coords[0]  # outer ring
                xs = [c[0] for c in exterior]
                ys = [c[1] for c in exterior]
                ax.fill(xs, ys, color=color, alpha=alpha, zorder=1)
                ax.plot(xs, ys, color=color, alpha=alpha + 0.1,
                        linewidth=0.5, zorder=2)

    # Color by service level
    level_colors = {
        "ALS": "#e74c3c",
        "AEMT": "#f39c12",
        "BLS": "#3498db",
        "N/A": "#95a5a6",
    }

    # Plot stations on top
    for _, row in dept_df.iterrows():
        c = level_colors.get(row["Level"], "#95a5a6")
        size = 100 if pd.isna(row["EMS_Calls"]) else max(60, row["EMS_Calls"] / 4)
        edgecolor = "#e67e22" if row["Cross_County"] else "white"
        linewidth = 3 if row["Cross_County"] else 1.5

        ax.scatter(row["Lon"], row["Lat"], s=size, c=c,
                  edgecolors=edgecolor, linewidths=linewidth, zorder=10, alpha=0.9)

        ax.annotate(
            f'{row["Dept"]}\n({row["EMS_Calls"] if not pd.isna(row["EMS_Calls"]) else "?"} calls)',
            (row["Lon"], row["Lat"] + 0.008),
            fontsize=7, ha="center", va="bottom", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85),
            zorder=11,
        )

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title(
        "Jefferson County EMS — Real Road-Network Drive-Time Coverage\n"
        "Source: OpenRouteService isochrones (OSM road network)\n"
        "Red = 8 min (NFPA 1710 career) | Orange = 14 min (NFPA 1720 rural) | Green = 20 min",
        fontsize=12, fontweight="bold",
    )

    legend_elements = [
        mpatches.Patch(color="#e74c3c", alpha=0.35, label="8-min drive (NFPA 1710)"),
        mpatches.Patch(color="#f39c12", alpha=0.25, label="14-min drive (NFPA 1720 rural)"),
        mpatches.Patch(color="#2ecc71", alpha=0.20, label="20-min drive (extended)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c",
               markersize=10, label="ALS station"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db",
               markersize=10, label="BLS station"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor="#e67e22", markeredgewidth=2, markersize=10,
               label="Cross-county dept"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    ax.set_aspect("equal")
    plt.tight_layout()
    plt.savefig("boundary_isochrone_map.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [OK] Saved: boundary_isochrone_map.png")

    # Also save combined isochrones as a single GeoJSON for use in other tools
    all_features = []
    for dept, iso_data in isochrones.items():
        for thresh, feat in iso_data.items():
            feat_copy = dict(feat)
            feat_copy["properties"] = dict(feat_copy.get("properties", {}))
            feat_copy["properties"]["department"] = dept
            feat_copy["properties"]["threshold_min"] = int(thresh)
            all_features.append(feat_copy)
    geojson_out = {"type": "FeatureCollection", "features": all_features}
    with open("boundary_isochrones.geojson", "w") as f:
        json.dump(geojson_out, f)
    print("  [OK] Saved: boundary_isochrones.geojson (for QGIS/ArcGIS import)")


# ==============================================================================
# 4. CONSOLIDATION SCENARIO MODELING
# ==============================================================================

def model_consolidation_scenarios(dept_df, labor_df, dist_matrix):
    """
    Model hypothetical consolidation scenarios.
    For each scenario: combine call volumes, compute required FTEs under
    a single unified service area, and compare to current separate staffing.

    Only models INTERIOR departments (non-cross-county) for clean analysis.
    Cross-county departments flagged separately since they have external obligations.
    """

    MIN_FTE_24_7 = 7.2  # single ambulance 24/7
    MIN_CREW = 2
    AVG_CALL_HRS = 1.0

    # Define scenarios based on geographic proximity and service gaps
    scenarios = [
        {
            "Name": "Central Consolidation",
            "Depts": ["Jefferson", "Johnson Creek", "Helenville"],
            "Rationale": "Jefferson (91 EMS calls) + Johnson Creek (454) + Helenville (no ambulance) are within 6-8 miles. Jefferson has 5 ambulances but only 91 EMS calls.",
        },
        {
            "Name": "North-Central Merger",
            "Depts": ["Lake Mills", "Johnson Creek"],
            "Rationale": "Lake Mills and Johnson Creek are ~6 miles apart. Lake Mills contracts Ryan Brothers for ALS; Johnson Creek runs own ALS. Combined service could share ALS resources.",
        },
        {
            "Name": "Southeast Consolidation",
            "Depts": ["Palmyra", "Ixonia"],
            "Rationale": "Both are BLS volunteer departments with low call volumes (105 and 260 EMS calls). Palmyra cost/call is $5,841. However, they are ~17 miles apart — geographic constraint.",
        },
        {
            "Name": "Interior Ring Unification",
            "Depts": ["Jefferson", "Johnson Creek", "Lake Mills", "Helenville"],
            "Rationale": "Consolidate the entire interior ring into one service area. All within ~10 miles of Jefferson FD. Combined pop ~21K.",
        },
        {
            "Name": "Full County Model (excl. cross-county)",
            "Depts": ["Jefferson", "Johnson Creek", "Lake Mills", "Ixonia", "Palmyra", "Helenville"],
            "Rationale": "All interior-only departments under one unified EMS system. Cross-county depts (Watertown, Whitewater, Waterloo, Edgerton, Cambridge) continue independently.",
        },
    ]

    results = []
    for s in scenarios:
        depts_in = s["Depts"]

        # Current state
        mask = dept_df["Dept"].isin(depts_in)
        subset = dept_df[mask]

        current_ft = subset["FT"].sum()
        current_total = (subset["FT"] + subset["PT"]).sum()

        # Current total expense
        current_expense = subset["Expense"].dropna().sum()

        # Combined call volume (skip NaN)
        combined_ems = subset["EMS_Calls"].dropna().sum()
        combined_pop = subset["Pop"].sum()

        # How many ambulances does the combined area need?
        # Rule of thumb: 1 ambulance unit per ~2,500 EMS calls/year (NFPA/ICMA)
        # Plus: need enough geographic coverage so no point is >14 min from a station
        ambulances_by_demand = max(1, int(np.ceil(combined_ems / 2500)))

        # Geographic coverage: count unique stations needed
        # (simplified: 1 station per ~10-mile radius)
        stations_in = subset[["Lat", "Lon"]].values
        # How spread out are they?
        if len(stations_in) > 1:
            max_spread = 0
            for i in range(len(stations_in)):
                for j in range(i+1, len(stations_in)):
                    d = haversine_miles(stations_in[i][0], stations_in[i][1],
                                       stations_in[j][0], stations_in[j][1])
                    max_spread = max(max_spread, d)
            # Need enough stations so max gap is <10 miles
            stations_needed = max(1, int(np.ceil(max_spread / 10)))
        else:
            stations_needed = 1

        # Consolidated FTE requirement
        # Each staffed station needs min 7.2 FTE for 24/7
        # But stations can cross-staff if close enough
        consolidated_min_fte = stations_needed * MIN_FTE_24_7

        # Demand-based FTE
        demand_fte = (combined_ems * AVG_CALL_HRS * MIN_CREW) / 2080

        # The actual need is the MAX of geographic minimum and demand
        consolidated_fte = max(consolidated_min_fte, demand_fte)

        # Current separate minimum: each dept independently needs 7.2 FTE floor
        # (only count depts that currently provide ambulance service)
        ambulance_depts = subset[subset["Ambulances"] > 0]
        current_separate_min = len(ambulance_depts) * MIN_FTE_24_7

        # Potential FTE reduction
        fte_reduction = current_separate_min - consolidated_fte

        results.append({
            "Scenario": s["Name"],
            "Departments": ", ".join(depts_in),
            "Rationale": s["Rationale"],
            "Combined_Pop": int(combined_pop),
            "Combined_EMS_Calls": int(combined_ems) if combined_ems > 0 else "N/A",
            "Current_Separate_Min_FTE": round(current_separate_min, 1),
            "Consolidated_Min_FTE": round(consolidated_fte, 1),
            "FTE_Reduction": round(fte_reduction, 1),
            "Current_FT_Staff": current_ft,
            "Current_Total_Staff": current_total,
            "Current_Total_Expense": int(current_expense) if current_expense > 0 else "N/A",
            "Stations_Needed": stations_needed,
            "Max_Spread_Miles": round(max_spread, 1) if len(stations_in) > 1 else 0,
        })

    return pd.DataFrame(results)


# ==============================================================================
# 5. VISUALIZATION
# ==============================================================================

def plot_labor_capacity(labor_df):
    """Bar chart: minimum staffing floor vs demand-justified FTEs by department."""

    df = labor_df.dropna(subset=["Demand_FTE"]).sort_values("Demand_FTE", ascending=True)

    fig, ax = plt.subplots(figsize=(14, 8))

    y_pos = np.arange(len(df))
    bar_height = 0.35

    # Minimum staffing floor (same for all — 7.2 FTE)
    bars1 = ax.barh(y_pos + bar_height/2, df["Min_FTE_24_7"], bar_height,
                    color="#e74c3c", alpha=0.8, label="Min FTE for 24/7 Coverage (staffing floor)")

    # Demand-justified FTEs
    bars2 = ax.barh(y_pos - bar_height/2, df["Demand_FTE"], bar_height,
                    color="#2ecc71", alpha=0.8, label="FTE Justified by Call Demand")

    # Add actual FT staff markers
    for i, (_, row) in enumerate(df.iterrows()):
        ax.plot(row["Actual_FT"], y_pos[i], "ko", markersize=8, zorder=5)

    # Mark cross-county departments
    for i, (_, row) in enumerate(df.iterrows()):
        if row.get("Cross_County", False):
            ax.annotate("*", (df["Min_FTE_24_7"].max() + 0.5, y_pos[i]),
                       fontsize=14, fontweight="bold", color="#e67e22",
                       ha="left", va="center")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(df["Dept"], fontsize=11)
    ax.set_xlabel("Full-Time Equivalents (FTE)", fontsize=12)
    ax.set_title("Structural Staffing Overhead: Minimum Floor vs. Call-Demand-Justified FTEs\n"
                 "Jefferson County EMS Departments (CY2024 Call Data, FY2025 Staffing)",
                 fontsize=13, fontweight="bold")

    # Custom legend
    handles = [
        mpatches.Patch(color="#e74c3c", alpha=0.8, label="Min FTE for 24/7 (7.2 per station)"),
        mpatches.Patch(color="#2ecc71", alpha=0.8, label="FTE justified by call demand"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="k", markersize=8, label="Actual FT staff"),
        Line2D([0], [0], marker="$*$", color="#e67e22", markersize=10, linestyle="None", label="Cross-county dept (external obligations)"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=10)

    # Add utilization % annotation
    for i, (_, row) in enumerate(df.iterrows()):
        if row["Utilization_Pct"] is not None:
            ax.annotate(f'{row["Utilization_Pct"]}% util.',
                       (row["Min_FTE_24_7"] + 1, y_pos[i] + bar_height/2),
                       fontsize=9, color="#555", va="center")

    ax.axvline(x=7.2, color="#e74c3c", linestyle="--", alpha=0.3, linewidth=1)
    ax.set_xlim(0, max(df["Min_FTE_24_7"].max(), df["Actual_FT"].max()) + 5)

    plt.tight_layout()
    plt.savefig("boundary_labor_capacity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [OK] Saved: boundary_labor_capacity.png")


def plot_utilization_gauge(labor_df):
    """Utilization % chart — how much of 24/7 capacity is actually used."""

    df = labor_df.dropna(subset=["Utilization_Pct"]).sort_values("Utilization_Pct", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 7))

    colors = []
    for pct in df["Utilization_Pct"]:
        if pct < 5:
            colors.append("#e74c3c")    # Critical underuse
        elif pct < 10:
            colors.append("#f39c12")    # Low
        elif pct < 20:
            colors.append("#f1c40f")    # Moderate
        else:
            colors.append("#2ecc71")    # Reasonable

    bars = ax.barh(df["Dept"], df["Utilization_Pct"], color=colors, edgecolor="white")

    # Add cross-county markers
    for i, (_, row) in enumerate(df.iterrows()):
        if row.get("Cross_County", False):
            ax.annotate(" * cross-county",
                       (row["Utilization_Pct"] + 0.5, i),
                       fontsize=8, color="#e67e22", va="center")

    for i, (_, row) in enumerate(df.iterrows()):
        ax.annotate(f'  {row["Utilization_Pct"]}%  ({int(row["Demand_FTE"]* 2080 / 2):.0f} calls)',
                   (row["Utilization_Pct"], i), fontsize=9, va="center")

    ax.set_xlabel("% of 24/7 Capacity Used by Actual EMS Calls", fontsize=12)
    ax.set_title("EMS Crew Utilization Rate — How Much of 24/7 Staffing Is Used?\n"
                 "Lower = more structural overhead (staffing for minimums, not demand)",
                 fontsize=13, fontweight="bold")

    # Legend for colors
    legend_elements = [
        mpatches.Patch(color="#e74c3c", label="< 5% — extreme underuse"),
        mpatches.Patch(color="#f39c12", label="5–10% — low utilization"),
        mpatches.Patch(color="#f1c40f", label="10–20% — moderate"),
        mpatches.Patch(color="#2ecc71", label="> 20% — reasonable for EMS"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    ax.set_xlim(0, max(df["Utilization_Pct"]) * 1.4)
    plt.tight_layout()
    plt.savefig("boundary_utilization.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [OK] Saved: boundary_utilization.png")


def plot_station_map(dept_df, overlaps_df):
    """Map of station locations with coverage circles and overlap connections."""

    fig, ax = plt.subplots(figsize=(14, 12))

    # Color by type
    color_map = {
        "ALS": "#e74c3c",
        "AEMT": "#f39c12",
        "BLS": "#3498db",
        "N/A": "#95a5a6",
    }

    # Plot stations
    for _, row in dept_df.iterrows():
        c = color_map.get(row["Level"], "#95a5a6")

        # Size by call volume (or small if no data)
        size = 100 if pd.isna(row["EMS_Calls"]) else max(50, row["EMS_Calls"] / 5)

        # Border for cross-county
        edgecolor = "#e67e22" if row["Cross_County"] else "white"
        linewidth = 3 if row["Cross_County"] else 1

        ax.scatter(row["Lon"], row["Lat"], s=size, c=c,
                  edgecolors=edgecolor, linewidths=linewidth, zorder=5, alpha=0.85)

        # Label
        offset_y = 0.008
        ax.annotate(f'{row["Dept"]}\n({row["EMS_Calls"] if not pd.isna(row["EMS_Calls"]) else "?"} calls)',
                   (row["Lon"], row["Lat"] + offset_y),
                   fontsize=8, ha="center", va="bottom", fontweight="bold",
                   bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))

        # Draw 5-mile radius circle (approximate: 1 degree lat ≈ 69 miles)
        circle_radius_deg = 5.0 / 69.0  # 5 miles in degrees lat
        circle = plt.Circle((row["Lon"], row["Lat"]), circle_radius_deg,
                           fill=False, color=c, linestyle="--", alpha=0.3, linewidth=1)
        ax.add_patch(circle)

    # Draw overlap connections
    for _, row in overlaps_df.iterrows():
        a = dept_df[dept_df["Dept"] == row["Station_A"]].iloc[0]
        b = dept_df[dept_df["Dept"] == row["Station_B"]].iloc[0]

        color = "#2ecc71" if row["Est_Drive_Min"] <= 10 else "#f39c12"
        ax.plot([a["Lon"], b["Lon"]], [a["Lat"], b["Lat"]],
               color=color, linewidth=2, alpha=0.5, linestyle="-", zorder=2)

        # Distance label at midpoint
        mid_lon = (a["Lon"] + b["Lon"]) / 2
        mid_lat = (a["Lat"] + b["Lat"]) / 2
        ax.annotate(f'{row["Distance_Miles"]}mi\n~{row["Est_Drive_Min"]}min',
                   (mid_lon, mid_lat), fontsize=7, ha="center", va="center",
                   bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.9))

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title("Jefferson County EMS Station Locations & Coverage Overlap\n"
                 "Dashed circles = 5-mile radius | Lines = stations within 8 miles (potential overlap)\n"
                 "Orange border = cross-county department (external service obligations)",
                 fontsize=12, fontweight="bold")

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=10, label="ALS"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#f39c12", markersize=10, label="AEMT"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db", markersize=10, label="BLS"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#95a5a6", markersize=10, label="Fire only / N/A"),
        Line2D([0], [0], color="#2ecc71", linewidth=2, label="≤10 min drive overlap"),
        Line2D([0], [0], color="#f39c12", linewidth=2, label="10–14 min drive overlap"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white", markeredgecolor="#e67e22",
               markeredgewidth=2, markersize=10, label="Cross-county dept"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    ax.set_aspect("equal")
    plt.tight_layout()
    plt.savefig("boundary_station_map.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [OK] Saved: boundary_station_map.png")


def plot_consolidation_scenarios(scenarios_df):
    """Compare FTE requirements: current separate vs consolidated."""

    df = scenarios_df.copy()

    fig, ax = plt.subplots(figsize=(14, 8))

    y_pos = np.arange(len(df))
    bar_height = 0.35

    bars1 = ax.barh(y_pos + bar_height/2, df["Current_Separate_Min_FTE"], bar_height,
                    color="#e74c3c", alpha=0.8, label="Current: Separate min FTEs (each dept independent)")
    bars2 = ax.barh(y_pos - bar_height/2, df["Consolidated_Min_FTE"], bar_height,
                    color="#2ecc71", alpha=0.8, label="Consolidated: Combined min FTEs")

    # Add reduction labels
    for i, (_, row) in enumerate(df.iterrows()):
        if row["FTE_Reduction"] > 0:
            ax.annotate(f'v {row["FTE_Reduction"]} FTE',
                       (row["Current_Separate_Min_FTE"] + 0.5, y_pos[i] + bar_height/2),
                       fontsize=10, fontweight="bold", color="#e74c3c", va="center")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([f'{row["Scenario"]}\n({row["Departments"]})' for _, row in df.iterrows()],
                       fontsize=9)
    ax.set_xlabel("Minimum Full-Time Equivalents Required", fontsize=12)
    ax.set_title("Consolidation Scenarios: Potential FTE Reduction\n"
                 "Structural staffing floors eliminated through shared coverage",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", fontsize=10)

    plt.tight_layout()
    plt.savefig("boundary_consolidation_scenarios.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  [OK] Saved: boundary_consolidation_scenarios.png")


# ==============================================================================
# 6. MAIN — RUN ANALYSIS
# ==============================================================================

def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — BOUNDARY & LABOR OPTIMIZATION ANALYSIS")
    print("=" * 70)

    # ── Step 1: Labor Capacity Model ─────────────────────────────────────────
    print("\n>> STEP 1: Labor Capacity Model")
    print("-" * 50)

    labor = compute_labor_model(departments)

    # Print summary table
    display_cols = ["Dept", "Min_FTE_24_7", "Demand_FTE", "Structural_Overhead_FTE",
                    "Actual_FT", "Utilization_Pct"]
    print(labor[display_cols].to_string(index=False))

    # County-wide summary
    valid = labor.dropna(subset=["Demand_FTE"])
    total_demand_fte = valid["Demand_FTE"].sum()

    # Count departments that independently staff ambulances
    ambulance_depts = departments[departments["Ambulances"] > 0]
    total_min_floors = len(ambulance_depts) * 7.2
    total_overhead = total_min_floors - total_demand_fte

    print(f"\n  COUNTY-WIDE SUMMARY:")
    print(f"  • Departments with ambulances: {len(ambulance_depts)}")
    print(f"  • Combined minimum staffing floors: {total_min_floors:.1f} FTE")
    print(f"  • Combined demand-justified FTEs: {total_demand_fte:.1f} FTE")
    print(f"  • Structural overhead (floor - demand): {total_overhead:.1f} FTE")
    print(f"  • Overhead as % of total: {(total_overhead / total_min_floors) * 100:.0f}%")

    # ── Step 2: Distance Matrix & Coverage Overlap ────────────────────────────
    print("\n\n>> STEP 2: Station Distance Matrix & Coverage Overlap")
    print("-" * 50)

    dist_matrix = compute_distance_matrix(departments)
    print("\nPairwise distances (miles) — showing closest neighbors:")

    # For each station, show the 3 closest
    for dept in departments["Dept"]:
        row = dist_matrix.loc[dept].drop(dept).sort_values()
        top3 = row.head(3)
        neighbors = ", ".join([f"{n} ({d:.1f}mi)" for n, d in top3.items()])
        print(f"  {dept:16s} → {neighbors}")

    overlaps = find_coverage_overlaps(dist_matrix, threshold_miles=8.0)
    print(f"\n  Stations within 8 miles (potential overlap): {len(overlaps)} pairs")
    if len(overlaps) > 0:
        print(overlaps.to_string(index=False))

    # ── Step 2b: Real Drive-Time Isochrones (ORS API) ──────────────────────
    print("\n\n>> STEP 2b: Real Road-Network Isochrones (OpenRouteService)")
    print("-" * 50)

    isochrones = fetch_isochrones(departments, thresholds_min=(8, 14, 20))

    real_drive = compute_real_drive_times(departments, isochrones)
    if real_drive is not None:
        print(f"\n  Real drive-time reachability ({len(real_drive)} directed pairs):")
        # Show which stations can reach each other within thresholds
        within_8 = real_drive[real_drive["Within_8min"]]
        within_14 = real_drive[real_drive["Within_14min"] & ~real_drive["Within_8min"]]
        if len(within_8) > 0:
            print(f"\n  Within 8 min (NFPA 1710 career standard):")
            for _, r in within_8.iterrows():
                print(f"    {r['From']:16s} -> {r['To']}")
        if len(within_14) > 0:
            print(f"\n  Within 8-14 min (NFPA 1720 rural standard):")
            for _, r in within_14.iterrows():
                print(f"    {r['From']:16s} -> {r['To']}")
    else:
        print("  No isochrone data available (set ORS_API_KEY in .env)")

    # ── Step 3: Consolidation Scenarios ───────────────────────────────────────
    print("\n\n>> STEP 3: Consolidation Scenario Modeling")
    print("-" * 50)

    scenarios = model_consolidation_scenarios(departments, labor, dist_matrix)
    for _, s in scenarios.iterrows():
        print(f"\n  -- {s['Scenario']}")
        print(f"     Departments: {s['Departments']}")
        print(f"     Combined population: {s['Combined_Pop']:,}")
        print(f"     Combined EMS calls: {s['Combined_EMS_Calls']}")
        print(f"     Current separate min FTE: {s['Current_Separate_Min_FTE']}")
        print(f"     Consolidated min FTE: {s['Consolidated_Min_FTE']}")
        print(f"     FTE reduction potential: {s['FTE_Reduction']}")
        print(f"     Stations needed for coverage: {s['Stations_Needed']}")
        print(f"     Max geographic spread: {s['Max_Spread_Miles']} miles")
        print(f"     Rationale: {s['Rationale']}")

    # ── Step 4: Cross-County Department Analysis ──────────────────────────────
    print("\n\n>> STEP 4: Cross-County Boundary Departments")
    print("-" * 50)
    print("  These departments serve areas in multiple counties.")
    print("  Their staffing floors may be justified by external obligations,")
    print("  not just Jefferson County demand. Consolidation analysis must")
    print("  account for their cross-county service commitments.\n")

    cross = departments[departments["Cross_County"] == True]
    for _, row in cross.iterrows():
        labor_row = labor[labor["Dept"] == row["Dept"]].iloc[0]
        print(f"  * {row['Dept']}")
        print(f"    {row['Cross_Note']}")
        print(f"    EMS Calls: {row['EMS_Calls'] if not pd.isna(row['EMS_Calls']) else 'N/A'} | "
              f"FT Staff: {row['FT']} | Pop: {row['Pop']:,}")
        if labor_row["Utilization_Pct"] is not None:
            print(f"    Utilization: {labor_row['Utilization_Pct']}% of 24/7 capacity")
        print()

    # ── Step 5: Generate Visualizations ───────────────────────────────────────
    print("\n>> STEP 5: Generating Visualizations")
    print("-" * 50)

    plot_labor_capacity(labor)
    plot_utilization_gauge(labor)
    plot_station_map(departments, overlaps)
    plot_isochrone_map(departments, isochrones)
    plot_consolidation_scenarios(scenarios)

    # ── Step 6: Key Findings Summary ──────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("KEY FINDINGS (DIAGNOSTIC — NOT PRESCRIPTIVE)")
    print("=" * 70)

    print(f"""
1. STRUCTURAL STAFFING OVERHEAD
   • {len(ambulance_depts)} independent ambulance services each require a minimum
     staffing floor of ~7.2 FTE for 24/7 coverage = {total_min_floors:.0f} FTE county-wide.
   • Actual call demand justifies only {total_demand_fte:.1f} FTE.
   • {total_overhead:.0f} FTE ({(total_overhead / total_min_floors) * 100:.0f}%) exist to meet minimums, not demand.

2. EXTREME UNDERUTILIZATION (Interior Departments)
   • Cambridge: 64 EMS calls/year → {labor[labor['Dept']=='Cambridge']['Utilization_Pct'].values[0] if len(labor[labor['Dept']=='Cambridge'].dropna(subset=['Utilization_Pct'])) > 0 else 'N/A'}% of 24/7 capacity
   • Jefferson: 91 EMS calls/year → 1.2% of 24/7 capacity, yet has 5 ambulances and 6 FT
   • Palmyra: 105 EMS calls/year → $5,841 cost per call

3. GEOGRAPHIC OVERLAP
   • {len(overlaps)} station pairs are within 8 miles of each other.
   • Several interior departments could be covered from a single consolidated station.

4. CROSS-COUNTY COMPLEXITY
   • 5 departments (Watertown, Whitewater, Waterloo, Edgerton, Cambridge)
     serve areas outside Jefferson County.
   • Their staffing cannot be evaluated purely on Jeff Co. demand.
   • Waterloo serves 4 counties from a corner position — unique constraint.

5. CONSOLIDATION POTENTIAL
   • Interior departments (Jefferson, Johnson Creek, Lake Mills, Ixonia, Palmyra,
     Helenville) are the clearest candidates for boundary optimization.
   • Full interior consolidation could reduce staffing floors from
     {scenarios[scenarios['Scenario']=='Full County Model (excl. cross-county)']['Current_Separate_Min_FTE'].values[0]:.0f} FTE to
     {scenarios[scenarios['Scenario']=='Full County Model (excl. cross-county)']['Consolidated_Min_FTE'].values[0]:.0f} FTE.

NOTE: These findings quantify the structural problem. They are NOT recommendations
to merge departments. The Working Group should evaluate political, contractual,
and operational feasibility.
""")

    # Save full results to CSV for further analysis
    labor.to_csv("boundary_labor_analysis.csv", index=False)
    dist_matrix.to_csv("boundary_distance_matrix.csv")
    scenarios.to_csv("boundary_consolidation_scenarios.csv", index=False)
    if len(overlaps) > 0:
        overlaps.to_csv("boundary_coverage_overlaps.csv", index=False)

    print("  [OK] Saved CSV outputs: boundary_labor_analysis.csv, boundary_distance_matrix.csv,")
    print("    boundary_consolidation_scenarios.csv, boundary_coverage_overlaps.csv")
    print("\n  Done.")


if __name__ == "__main__":
    main()
