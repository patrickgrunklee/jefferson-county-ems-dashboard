"""
Jefferson County EMS — Countywide Secondary Ambulance Discrete-Event Simulation
================================================================================
Replays every CY2024 EMS call through two systems:
  A) CURRENT:  Each department uses its own fleet (actual 2024 outcomes)
  B) PROPOSED: Each dept keeps 1 primary ambulance; all secondary capacity
               replaced by K county-wide ALS units at optimized locations

Key Indicators:
  - Utilization of all ambulances (primary + secondary)
  - Response time when a secondary ambulance is used
  - Coverage at 10-min and 14-min thresholds
  - Queue events (all units busy)

Reuses:
  - concurrent_call_analysis.py  (load_all_nfirs, AMBULANCE_COUNT, DEPT_NAME_MAP)
  - facility_location.py         (STATIONS — 13 primary stations)
  - pareto_facility.py           (load_candidates, load_bg_demand)
  - full_ems_analysis.py         (build_city_zip_to_bg_map, load_bg_centroids, CITY_COORDS)
  - isochrone_cache/             (pre-computed ORS drive-time matrices)

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
from math import radians, sin, cos, sqrt, atan2
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from concurrent_call_analysis import (
    load_all_nfirs, DEPT_NAME_MAP, EMS_TRANSPORT_DEPTS, AMBULANCE_COUNT,
)
from facility_location import STATIONS as EXISTING_STATIONS

# ── Output directory ─────────────────────────────────────────────────────
OUT_DIR = os.path.join(SCRIPT_DIR, "simulation_output")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Plot style ───────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
})

# ── Constants ────────────────────────────────────────────────────────────
# Current secondary inventory: total fleet minus 1 primary per dept
CURRENT_SECONDARY = {
    dept: max(0, AMBULANCE_COUNT.get(dept, 0) - 1)
    for dept in EMS_TRANSPORT_DEPTS
}
TOTAL_CURRENT_SECONDARY = sum(CURRENT_SECONDARY.values())  # = 10

# Dispatch delay assumptions (minutes)
DISPATCH_DELAY_CAREER = 1.5    # Career departments: turnout time
DISPATCH_DELAY_VOLUNTEER = 4.0 # Volunteer departments: page + response
DISPATCH_DELAY_COUNTY = 1.5    # Proposed county units: all career-staffed

VOLUNTEER_DEPTS = {"Ixonia", "Palmyra", "Cambridge", "Helenville", "Sullivan", "Rome"}

# Station name -> index in EXISTING_STATIONS list (for drive-time matrix lookup)
STATION_IDX = {s["name"]: s["id"] for s in EXISTING_STATIONS}

# Hours in a year (for utilization calculations)
HOURS_PER_YEAR = 365.25 * 24


# ══════════════════════════════════════════════════════════════════════════
#  DATA LOADING & GEOCODING
# ══════════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
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
        })
    return pd.DataFrame(bgs)


# City coordinates for geocoding (from full_ems_analysis.py)
CITY_COORDS = {
    "fort atkinson": (42.929, -88.837), "city of fort atkinso": (42.929, -88.837),
    "fort  atkinson": (42.929, -88.837), "fort atksinson": (42.929, -88.837),
    "watertown": (43.195, -88.729), "city of watertown": (43.195, -88.729),
    "whitewater": (42.834, -88.732), "city of whitewater": (42.834, -88.732),
    "whiteewater": (42.834, -88.732),
    "edgerton": (42.835, -89.067), "city of edgerton": (42.835, -89.067),
    "jefferson": (43.005, -88.807), "city of jefferson": (43.005, -88.807),
    "johnson creek": (43.077, -88.774), "village of johnson c": (43.077, -88.774),
    "waterloo": (43.184, -88.983), "city of waterloo": (43.184, -88.983),
    "lake mills": (43.080, -88.906), "city of lake mills": (43.080, -88.906),
    "ixonia": (43.143, -88.597),
    "palmyra": (42.878, -88.586), "village of palmyra": (42.878, -88.586),
    "cambridge": (43.003, -89.017), "village of cambridge": (43.003, -89.017),
    "sullivan": (43.010, -88.594), "village of sullivan": (43.010, -88.594),
    "rome": (43.150, -88.883),
    "helenville": (43.115, -88.680),
    "concord": (43.070, -88.603),
    "koshkonong": (42.876, -88.870), "town of koshkonong": (42.876, -88.870),
    "town of christiana": (42.873, -88.943),
    "town of oakland": (42.873, -88.790),
    "town of lake mills": (43.060, -88.920),
    "town of lima": (43.010, -88.680),
    "town of hebron": (42.910, -88.630), "hebron": (42.910, -88.630),
    "town of cold spring": (42.830, -88.800),
    "town of sumner": (42.870, -88.720),
    "town of johnstown": (43.100, -88.850), "johnstown": (43.100, -88.850),
    "portland": (42.830, -88.900),
    "indianford": (42.850, -89.050),
    "albion": (42.880, -89.060),
    "avalon": (42.810, -89.020),
    "busseyville": (43.025, -88.720),
    "milford": (43.100, -88.750),
    "farmington": (43.140, -88.750),
    "oakland": (42.870, -88.790),
    "aztalan": (43.070, -88.860),
    "ottawa": (43.160, -88.600),
    "rockdale": (42.980, -89.020),
    "fulton": (42.810, -89.100),
    "milton": (42.775, -88.944), "city of milton": (42.775, -88.944),
    "janesville": (42.683, -89.019),
    "stoughton": (42.917, -89.218),
    "oconomowoc": (43.112, -88.499),
    "madison": (43.074, -89.384),
    "delavan": (42.632, -88.644),
    "elkhorn": (42.673, -88.544),
    "columbus": (43.338, -89.015),
    "beaver dam": (43.457, -88.837),
    "hartford": (43.318, -88.379),
}


def build_geocoding_map(bg_df):
    """Build city_lower -> nearest BG GEOID mapping."""
    bg_lats = bg_df["lat"].values
    bg_lons = bg_df["lon"].values
    bg_geoids = bg_df["GEOID"].values

    city_to_bg = {}
    for city_key, (clat, clon) in CITY_COORDS.items():
        dists = [haversine_km(clat, clon, bg_lats[i], bg_lons[i])
                 for i in range(len(bg_lats))]
        city_to_bg[city_key] = bg_geoids[np.argmin(dists)]
    return city_to_bg


def geocode_call(city_raw, zip_code, city_to_bg, bg_df):
    """Map a call's city/zip to a block group index."""
    city_lower = str(city_raw).strip().lower()

    if city_lower in city_to_bg:
        geoid = city_to_bg[city_lower]
    else:
        cleaned = city_lower
        for prefix in ["city of ", "town of ", "village of "]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        cleaned = cleaned.replace(" - town", "").replace(" - city", "").strip()
        if cleaned in city_to_bg:
            geoid = city_to_bg[cleaned]
        else:
            # Fallback: center of county
            geoid = city_to_bg.get("jefferson", bg_df["GEOID"].iloc[0])

    # Convert GEOID to BG index
    idx = bg_df.index[bg_df["GEOID"] == geoid]
    return int(idx[0]) if len(idx) > 0 else 0


def find_nearest_station(dept_name):
    """Find the EXISTING_STATIONS index for a department."""
    if dept_name in STATION_IDX:
        return STATION_IDX[dept_name]
    # Fuzzy match
    for s in EXISTING_STATIONS:
        if dept_name.lower() in s["name"].lower() or s["name"].lower() in dept_name.lower():
            return s["id"]
    return 0  # fallback to first station


# ══════════════════════════════════════════════════════════════════════════
#  LOAD DRIVE-TIME MATRICES
# ══════════════════════════════════════════════════════════════════════════

def load_drive_time_matrices():
    """Load pre-computed ORS drive-time matrices."""
    # 13 existing stations × 65 block groups
    existing_path = os.path.join(SCRIPT_DIR, "isochrone_cache",
                                 "existing_bg_drive_time_matrix.json")
    with open(existing_path) as f:
        existing_tm = np.array(json.load(f)["matrix"])
    print(f"  Existing station matrix: {existing_tm.shape}")

    # 60 candidate sites × 65 block groups
    cand_path = os.path.join(SCRIPT_DIR, "isochrone_cache",
                             "cand_bg_drive_time_matrix.json")
    with open(cand_path) as f:
        cand_tm = np.array(json.load(f)["matrix"])
    print(f"  Candidate site matrix: {cand_tm.shape}")

    # Load candidate metadata for coordinate matching
    cand_meta_path = os.path.join(SCRIPT_DIR, "isochrone_cache",
                                  "candidate_drive_time_matrix.json")
    with open(cand_meta_path) as f:
        cand_meta = json.load(f)
    candidates = cand_meta["candidates"]

    return existing_tm, cand_tm, candidates


# ══════════════════════════════════════════════════════════════════════════
#  PARSE HUB LOCATIONS FROM PHASE H SWEEP
# ══════════════════════════════════════════════════════════════════════════

def parse_hub_locations(k_value):
    """Parse the optimal hub locations for a given K from phase_h_k_sweep_results.csv."""
    sweep_path = os.path.join(SCRIPT_DIR, "analysis_output", "phase_h_k_sweep_results.csv")
    sweep_df = pd.read_csv(sweep_path)

    row = sweep_df[sweep_df["K"] == k_value]
    if row.empty:
        raise ValueError(f"No solution found for K={k_value}")

    stations_str = row.iloc[0]["Stations"]
    # Parse "(lat,lon) | (lat,lon) | ..." format
    coords = re.findall(r'\(([-\d.]+),([-\d.]+)\)', stations_str)
    hubs = [{"lat": float(lat), "lon": float(lon)} for lat, lon in coords]
    return hubs


def hub_to_candidate_idx(hub, candidates, tol=0.005):
    """Find the candidate index matching a hub's coordinates."""
    for i, c in enumerate(candidates):
        if abs(c["lat"] - hub["lat"]) < tol and abs(c["lon"] - hub["lon"]) < tol:
            return i
    # Fallback: find nearest candidate
    dists = [haversine_km(hub["lat"], hub["lon"], c["lat"], c["lon"]) for c in candidates]
    return int(np.argmin(dists))


# ══════════════════════════════════════════════════════════════════════════
#  PREPARE CALL TIMELINE
# ══════════════════════════════════════════════════════════════════════════

def prepare_call_timeline(bg_df, city_to_bg):
    """Load all NFIRS data, classify, and build a sorted call timeline."""
    print("\n" + "=" * 70)
    print("PREPARING CALL TIMELINE")
    print("=" * 70)

    # Load raw NFIRS data (returns tuple: full ems df, valid-timestamps df)
    ems_all, valid_all = load_all_nfirs()
    print(f"  Total NFIRS records: {len(ems_all):,}")

    # Filter to EMS transport departments with valid timestamps
    valid = valid_all[valid_all["Dept"].isin(EMS_TRANSPORT_DEPTS)].copy()

    # Ensure Cleared > Alarm
    valid = valid[valid["Cleared_DT"] > valid["Alarm_DT"]].copy()

    # Use pre-parsed RT from load_all_nfirs
    if "Response_Min" in valid.columns:
        valid["RT_Min"] = valid["Response_Min"]
    else:
        valid["RT_Min"] = np.nan

    # Use pre-parsed duration; fall back to computed
    if "Duration_Min" not in valid.columns or valid["Duration_Min"].isna().all():
        valid["Duration_Min"] = (valid["Cleared_DT"] - valid["Alarm_DT"]).dt.total_seconds() / 60.0

    # Cap unreasonable durations (>6 hours -> set to 45 min default)
    valid.loc[valid["Duration_Min"] > 360, "Duration_Min"] = 45.0
    valid.loc[valid["Duration_Min"] <= 0, "Duration_Min"] = 45.0
    valid.loc[valid["Duration_Min"].isna(), "Duration_Min"] = 45.0

    # Geocode each call to a block group
    city_col = "Incident City" if "Incident City" in valid.columns else None
    zip_col = "Incident Zip Code" if "Incident Zip Code" in valid.columns else None

    bg_indices = []
    for _, row in valid.iterrows():
        city = row[city_col] if city_col else ""
        zc = row[zip_col] if zip_col else ""
        bg_idx = geocode_call(city, zc, city_to_bg, bg_df)
        bg_indices.append(bg_idx)

    valid["BG_Idx"] = bg_indices

    # Sort by alarm time
    valid = valid.sort_values("Alarm_DT").reset_index(drop=True)

    print(f"  Valid calls for simulation: {len(valid):,}")
    print(f"  Departments: {valid['Dept'].nunique()}")
    print(f"  Date range: {valid['Alarm_DT'].min()} to {valid['Alarm_DT'].max()}")
    print(f"  Median duration: {valid['Duration_Min'].median():.1f} min")
    print(f"  Median RT (where available): {valid['RT_Min'].median():.1f} min")

    return valid


# ══════════════════════════════════════════════════════════════════════════
#  SIMULATE CURRENT SYSTEM
# ══════════════════════════════════════════════════════════════════════════

def simulate_current_system(calls_df, existing_tm):
    """
    Simulate the current fragmented system.
    Each department has AMBULANCE_COUNT[dept] units.
    Dispatch in order: first available ambulance from the department.
    If all busy -> secondary (mutual aid) call, use actual NFIRS RT.
    """
    print("\n" + "=" * 70)
    print("SIMULATING CURRENT SYSTEM (CY2024 Replay)")
    print("=" * 70)

    results = []
    # Track busy-until time for each ambulance per department
    dept_ambulances = {}
    for dept in EMS_TRANSPORT_DEPTS:
        count = AMBULANCE_COUNT.get(dept, 0)
        dept_ambulances[dept] = [pd.NaT] * max(count, 1)  # at least 1 virtual unit

    # Utilization tracking: total busy-minutes per department
    dept_busy_min = {dept: 0.0 for dept in EMS_TRANSPORT_DEPTS}

    for _, call in calls_df.iterrows():
        dept = call["Dept"]
        alarm = call["Alarm_DT"]
        duration = call["Duration_Min"]
        cleared = alarm + pd.Timedelta(minutes=duration)
        bg_idx = call["BG_Idx"]
        actual_rt = call["RT_Min"]

        ambulances = dept_ambulances.get(dept, [pd.NaT])

        # Find first available ambulance
        available = [i for i, busy_until in enumerate(ambulances)
                     if pd.isna(busy_until) or alarm >= busy_until]

        if available:
            # Primary response
            unit_idx = available[0]
            ambulances[unit_idx] = cleared
            dept_busy_min[dept] += duration

            # RT: use actual NFIRS RT if available, else estimate from drive-time matrix
            station_idx = find_nearest_station(dept)
            if pd.notna(actual_rt) and actual_rt > 0:
                rt = actual_rt
            else:
                rt = existing_tm[station_idx, bg_idx] if bg_idx < existing_tm.shape[1] else 10.0

            results.append({
                "Alarm_DT": alarm, "Dept": dept, "BG_Idx": bg_idx,
                "Call_Class": "Primary", "RT_Min": rt,
                "Duration_Min": duration, "Unit_Type": "dept_primary",
                "Wait_Min": 0.0,
            })
        else:
            # ALL ambulances busy -> secondary/mutual aid call
            # Under current system, actual RT from NFIRS (whatever happened)
            # Mark the earliest-freeing ambulance as handling it after it clears
            earliest_idx = int(np.argmin([t.timestamp() if pd.notna(t) else 1e18
                                          for t in ambulances]))
            wait = max(0, (ambulances[earliest_idx] - alarm).total_seconds() / 60.0)
            ambulances[earliest_idx] = cleared
            dept_busy_min[dept] += duration

            if pd.notna(actual_rt) and actual_rt > 0:
                rt = actual_rt
            else:
                station_idx = find_nearest_station(dept)
                rt = existing_tm[station_idx, bg_idx] + 2.0  # penalty estimate
                if bg_idx >= existing_tm.shape[1]:
                    rt = 12.0

            results.append({
                "Alarm_DT": alarm, "Dept": dept, "BG_Idx": bg_idx,
                "Call_Class": "Secondary", "RT_Min": rt,
                "Duration_Min": duration, "Unit_Type": "dept_secondary",
                "Wait_Min": wait,
            })

    results_df = pd.DataFrame(results)

    # Compute utilization
    primary_count = results_df[results_df["Call_Class"] == "Primary"].shape[0]
    secondary_count = results_df[results_df["Call_Class"] == "Secondary"].shape[0]
    total_ambulances = sum(AMBULANCE_COUNT.get(d, 0) for d in EMS_TRANSPORT_DEPTS)

    print(f"  Total calls simulated: {len(results_df):,}")
    print(f"  Primary: {primary_count:,} | Secondary: {secondary_count:,} "
          f"({100 * secondary_count / len(results_df):.1f}%)")
    print(f"  Total ambulances: {total_ambulances}")

    # Per-dept utilization
    print(f"\n  {'Dept':<16} {'Calls':>6} {'2nd':>5} {'Util%':>6} {'MedRT':>6} {'P90RT':>6}")
    print(f"  {'-'*16} {'-'*6} {'-'*5} {'-'*6} {'-'*6} {'-'*6}")
    for dept in sorted(EMS_TRANSPORT_DEPTS):
        dept_calls = results_df[results_df["Dept"] == dept]
        dept_sec = dept_calls[dept_calls["Call_Class"] == "Secondary"]
        n_amb = max(1, AMBULANCE_COUNT.get(dept, 1))
        util = 100 * dept_busy_min[dept] / (n_amb * HOURS_PER_YEAR * 60)
        med_rt = dept_calls["RT_Min"].median()
        p90_rt = dept_calls["RT_Min"].quantile(0.9)
        print(f"  {dept:<16} {len(dept_calls):6d} {len(dept_sec):5d} "
              f"{util:6.1f} {med_rt:6.1f} {p90_rt:6.1f}")

    return results_df, dept_busy_min


# ══════════════════════════════════════════════════════════════════════════
#  SIMULATE PROPOSED COUNTYWIDE SYSTEM
# ══════════════════════════════════════════════════════════════════════════

def simulate_proposed_system(calls_df, existing_tm, cand_tm, candidates,
                             hub_locations, K):
    """
    Simulate the proposed countywide secondary system.
    Each department keeps 1 primary ambulance.
    K county-wide ALS units at optimal locations handle all secondary calls.
    """
    print(f"\n" + "=" * 70)
    print(f"SIMULATING PROPOSED SYSTEM (K={K} County-Wide Secondary Units)")
    print("=" * 70)

    # Map hubs to candidate indices for drive-time lookup
    hub_cand_ids = [hub_to_candidate_idx(h, candidates) for h in hub_locations]
    print(f"  Hub locations:")
    for i, (h, cid) in enumerate(zip(hub_locations, hub_cand_ids)):
        print(f"    Unit {i+1}: ({h['lat']:.4f}, {h['lon']:.4f}) -> candidate idx {cid}")

    results = []

    # Each dept has exactly 1 primary ambulance
    dept_primary_busy = {dept: pd.NaT for dept in EMS_TRANSPORT_DEPTS}

    # K county-wide secondary units
    secondary_busy = [pd.NaT] * K

    # Utilization tracking
    dept_primary_busy_min = {dept: 0.0 for dept in EMS_TRANSPORT_DEPTS}
    secondary_busy_min = [0.0] * K
    secondary_call_count = [0] * K

    queue_events = 0

    for _, call in calls_df.iterrows():
        dept = call["Dept"]
        alarm = call["Alarm_DT"]
        duration = call["Duration_Min"]
        cleared = alarm + pd.Timedelta(minutes=duration)
        bg_idx = call["BG_Idx"]
        actual_rt = call["RT_Min"]

        # Check if primary ambulance is available
        primary_avail = pd.isna(dept_primary_busy[dept]) or alarm >= dept_primary_busy[dept]

        if primary_avail:
            # Dispatch primary
            dept_primary_busy[dept] = cleared
            dept_primary_busy_min[dept] += duration

            station_idx = find_nearest_station(dept)
            if pd.notna(actual_rt) and actual_rt > 0:
                rt = actual_rt
            else:
                rt = existing_tm[station_idx, bg_idx] if bg_idx < existing_tm.shape[1] else 10.0

            results.append({
                "Alarm_DT": alarm, "Dept": dept, "BG_Idx": bg_idx,
                "Call_Class": "Primary", "RT_Min": rt,
                "Duration_Min": duration, "Unit_Type": "dept_primary",
                "Unit_ID": f"{dept}_P1",
                "Wait_Min": 0.0,
            })
        else:
            # Primary is busy -> dispatch nearest available county-wide secondary
            avail_secondary = [
                i for i in range(K)
                if pd.isna(secondary_busy[i]) or alarm >= secondary_busy[i]
            ]

            if avail_secondary:
                # Find nearest available secondary unit by drive time to this BG
                best_unit = None
                best_rt = float("inf")
                for idx in avail_secondary:
                    cand_idx = hub_cand_ids[idx]
                    if bg_idx < cand_tm.shape[1]:
                        drive = cand_tm[cand_idx, bg_idx]
                    else:
                        drive = 15.0  # fallback
                    total_rt = drive + DISPATCH_DELAY_COUNTY
                    if total_rt < best_rt:
                        best_rt = total_rt
                        best_unit = idx

                secondary_busy[best_unit] = cleared
                secondary_busy_min[best_unit] += duration
                secondary_call_count[best_unit] += 1

                results.append({
                    "Alarm_DT": alarm, "Dept": dept, "BG_Idx": bg_idx,
                    "Call_Class": "Secondary", "RT_Min": best_rt,
                    "Duration_Min": duration, "Unit_Type": "county_secondary",
                    "Unit_ID": f"SEC_{best_unit + 1}",
                    "Wait_Min": 0.0,
                })
            else:
                # ALL units busy — queue event
                queue_events += 1
                # Find the unit that frees up soonest
                free_times = [
                    (secondary_busy[i].timestamp() if pd.notna(secondary_busy[i]) else 1e18, i)
                    for i in range(K)
                ]
                _, best_unit = min(free_times)
                wait = max(0, (secondary_busy[best_unit] - alarm).total_seconds() / 60.0)

                cand_idx = hub_cand_ids[best_unit]
                drive = cand_tm[cand_idx, bg_idx] if bg_idx < cand_tm.shape[1] else 15.0
                total_rt = drive + DISPATCH_DELAY_COUNTY + wait

                secondary_busy[best_unit] = cleared
                secondary_busy_min[best_unit] += duration
                secondary_call_count[best_unit] += 1

                results.append({
                    "Alarm_DT": alarm, "Dept": dept, "BG_Idx": bg_idx,
                    "Call_Class": "Secondary", "RT_Min": total_rt,
                    "Duration_Min": duration, "Unit_Type": "county_secondary_queued",
                    "Unit_ID": f"SEC_{best_unit + 1}",
                    "Wait_Min": wait,
                })

    results_df = pd.DataFrame(results)

    primary_count = results_df[results_df["Call_Class"] == "Primary"].shape[0]
    secondary_count = results_df[results_df["Call_Class"] == "Secondary"].shape[0]

    print(f"  Total calls simulated: {len(results_df):,}")
    print(f"  Primary: {primary_count:,} | Secondary: {secondary_count:,} "
          f"({100 * secondary_count / len(results_df):.1f}%)")
    print(f"  Queue events (all units busy): {queue_events}")

    # Per-secondary-unit stats
    print(f"\n  {'Unit':<8} {'Calls':>6} {'Util%':>6} {'MedRT':>6} {'P90RT':>6}")
    print(f"  {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
    for i in range(K):
        util = 100 * secondary_busy_min[i] / (HOURS_PER_YEAR * 60)
        unit_calls = results_df[results_df["Unit_ID"] == f"SEC_{i+1}"]
        sec_calls = unit_calls[unit_calls["Call_Class"] == "Secondary"]
        med_rt = sec_calls["RT_Min"].median() if len(sec_calls) > 0 else 0
        p90_rt = sec_calls["RT_Min"].quantile(0.9) if len(sec_calls) > 0 else 0
        print(f"  SEC_{i+1:<3} {secondary_call_count[i]:6d} {util:6.1f} {med_rt:6.1f} {p90_rt:6.1f}")

    return results_df, secondary_busy_min, secondary_call_count, queue_events


# ══════════════════════════════════════════════════════════════════════════
#  COMPARE KPIs
# ══════════════════════════════════════════════════════════════════════════

def compare_systems(current_df, proposed_df, K, queue_events):
    """Compare KPIs between current and proposed systems."""
    print(f"\n" + "=" * 70)
    print("KPI COMPARISON: CURRENT vs PROPOSED")
    print("=" * 70)

    cur_sec = current_df[current_df["Call_Class"] == "Secondary"]
    pro_sec = proposed_df[proposed_df["Call_Class"] == "Secondary"]

    kpis = []

    def add_kpi(name, cur_val, pro_val, fmt=".1f"):
        delta = pro_val - cur_val
        kpis.append({
            "KPI": name,
            "Current": round(cur_val, 2),
            "Proposed": round(pro_val, 2),
            "Delta": round(delta, 2),
        })
        sign = "+" if delta > 0 else ""
        print(f"  {name:<40} {cur_val:>8{fmt}} {pro_val:>8{fmt}} {sign}{delta:{fmt}}")

    print(f"  {'KPI':<40} {'Current':>8} {'Proposed':>8} {'Delta':>8}")
    print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*8}")

    add_kpi("Total Calls", len(current_df), len(proposed_df), "d")
    add_kpi("Secondary Calls", len(cur_sec), len(pro_sec), "d")
    add_kpi("Secondary %", 100 * len(cur_sec) / len(current_df),
            100 * len(pro_sec) / len(proposed_df))

    if len(cur_sec) > 0 and len(pro_sec) > 0:
        add_kpi("Median Secondary RT (min)", cur_sec["RT_Min"].median(),
                pro_sec["RT_Min"].median())
        add_kpi("Mean Secondary RT (min)", cur_sec["RT_Min"].mean(),
                pro_sec["RT_Min"].mean())
        add_kpi("P90 Secondary RT (min)", cur_sec["RT_Min"].quantile(0.9),
                pro_sec["RT_Min"].quantile(0.9))
        add_kpi("Max Secondary RT (min)", cur_sec["RT_Min"].max(),
                pro_sec["RT_Min"].max())

        # Coverage thresholds
        for threshold in [10, 14]:
            cur_cov = 100 * (cur_sec["RT_Min"] <= threshold).mean()
            pro_cov = 100 * (pro_sec["RT_Min"] <= threshold).mean()
            add_kpi(f"Secondary within {threshold} min (%)", cur_cov, pro_cov)

    # Overall system RT (primary + secondary)
    add_kpi("Overall Median RT (min)", current_df["RT_Min"].median(),
            proposed_df["RT_Min"].median())
    add_kpi("Overall P90 RT (min)", current_df["RT_Min"].quantile(0.9),
            proposed_df["RT_Min"].quantile(0.9))

    # Queue events
    cur_queue = current_df[current_df["Wait_Min"] > 0].shape[0]
    pro_queue = proposed_df[proposed_df["Wait_Min"] > 0].shape[0]
    add_kpi("Calls with Wait (queue)", cur_queue, pro_queue, "d")

    # Utilization
    total_cur_amb = sum(AMBULANCE_COUNT.get(d, 0) for d in EMS_TRANSPORT_DEPTS)
    cur_total_busy = current_df["Duration_Min"].sum()
    cur_util = 100 * cur_total_busy / (total_cur_amb * HOURS_PER_YEAR * 60)

    total_pro_amb = len(EMS_TRANSPORT_DEPTS) + K  # 1 primary per dept + K secondary
    pro_total_busy = proposed_df["Duration_Min"].sum()
    pro_util = 100 * pro_total_busy / (total_pro_amb * HOURS_PER_YEAR * 60)
    add_kpi("System Utilization (%)", cur_util, pro_util)

    add_kpi("Total Ambulance Units", total_cur_amb, total_pro_amb, "d")

    kpi_df = pd.DataFrame(kpis)
    kpi_path = os.path.join(OUT_DIR, "simulation_results_summary.csv")
    kpi_df.to_csv(kpi_path, index=False)
    print(f"\n  Saved: {kpi_path}")

    return kpi_df


# ══════════════════════════════════════════════════════════════════════════
#  VISUALIZATION
# ══════════════════════════════════════════════════════════════════════════

def plot_rt_distributions(current_df, proposed_df, K):
    """Plot response time distributions for secondary calls."""
    cur_sec = current_df[current_df["Call_Class"] == "Secondary"]["RT_Min"].dropna()
    pro_sec = proposed_df[proposed_df["Call_Class"] == "Secondary"]["RT_Min"].dropna()

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Panel 1: Overlapping histograms
    ax = axes[0]
    bins = np.arange(0, 35, 1)
    ax.hist(cur_sec, bins=bins, alpha=0.6, color="#e74c3c", label="Current System",
            edgecolor="white", linewidth=0.5, density=True)
    ax.hist(pro_sec, bins=bins, alpha=0.6, color="#3498db", label=f"Proposed (K={K})",
            edgecolor="white", linewidth=0.5, density=True)
    ax.axvline(cur_sec.median(), color="#e74c3c", linestyle="--", linewidth=2,
               label=f"Current Median: {cur_sec.median():.1f} min")
    ax.axvline(pro_sec.median(), color="#3498db", linestyle="--", linewidth=2,
               label=f"Proposed Median: {pro_sec.median():.1f} min")
    ax.set_xlabel("Response Time (minutes)")
    ax.set_ylabel("Density")
    ax.set_title("Secondary Call Response Time Distribution")
    ax.legend(fontsize=9)
    ax.set_xlim(0, 30)

    # Panel 2: CDF comparison
    ax = axes[1]
    for data, label, color in [
        (cur_sec, "Current", "#e74c3c"),
        (pro_sec, f"Proposed (K={K})", "#3498db")
    ]:
        sorted_data = np.sort(data)
        cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        ax.plot(sorted_data, cdf * 100, color=color, linewidth=2, label=label)

    for t, ls in [(10, "--"), (14, ":")]:
        ax.axvline(t, color="#999", linestyle=ls, alpha=0.5)
        ax.text(t + 0.3, 5, f"{t} min", fontsize=8, color="#666")

    ax.set_xlabel("Response Time (minutes)")
    ax.set_ylabel("Cumulative % of Secondary Calls")
    ax.set_title("Cumulative Distribution — Secondary Response Times")
    ax.legend(fontsize=9)
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 105)
    ax.grid(alpha=0.3)

    fig.suptitle(
        f"Secondary Ambulance Response Time: Current System vs "
        f"Proposed Countywide ({K} Units)\n"
        f"Simulation of {len(current_df):,} CY2024 EMS calls",
        fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    path = os.path.join(OUT_DIR, "simulation_rt_distributions.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_hourly_profile(proposed_df, K):
    """Show when secondary units are dispatched by hour of day."""
    sec = proposed_df[proposed_df["Call_Class"] == "Secondary"].copy()
    sec["Hour"] = sec["Alarm_DT"].dt.hour

    fig, ax = plt.subplots(figsize=(12, 5))
    hourly = sec.groupby("Hour").size()
    hours = range(24)
    counts = [hourly.get(h, 0) for h in hours]

    ax.bar(hours, counts, color="#3498db", edgecolor="white", linewidth=0.5, alpha=0.8)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Secondary Dispatches (CY2024)")
    ax.set_title(f"Proposed Countywide Secondary Dispatch Profile (K={K})\n"
                 f"{sec.shape[0]:,} secondary calls across {K} county-wide units",
                 fontsize=12, fontweight="bold")
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours])
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(OUT_DIR, "simulation_hourly_profile.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_utilization(secondary_busy_min, secondary_call_count, hub_locations, K):
    """Per-unit utilization breakdown."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    units = [f"SEC_{i+1}" for i in range(K)]
    utils = [100 * secondary_busy_min[i] / (HOURS_PER_YEAR * 60) for i in range(K)]
    calls = secondary_call_count

    # Bar chart: utilization
    colors = ["#e74c3c" if u > 15 else "#f39c12" if u > 10 else "#2ecc71" for u in utils]
    ax1.barh(units, utils, color=colors, edgecolor="white", linewidth=0.5)
    ax1.set_xlabel("Utilization (%)")
    ax1.set_title("Unit Utilization (% of year busy)")
    for i, (u, c) in enumerate(zip(utils, calls)):
        ax1.text(u + 0.2, i, f"{u:.1f}% ({c} calls)", va="center", fontsize=9)
    ax1.set_xlim(0, max(utils) * 1.4 if utils else 20)

    # Bar chart: call count
    ax2.barh(units, calls, color="#3498db", edgecolor="white", linewidth=0.5)
    ax2.set_xlabel("Calls Served (CY2024)")
    ax2.set_title("Calls per Secondary Unit")
    for i, c in enumerate(calls):
        ax2.text(c + 1, i, str(c), va="center", fontsize=9)
    ax2.set_xlim(0, max(calls) * 1.3 if calls else 100)

    fig.suptitle(f"Proposed {K}-Unit Countywide Secondary Network — Utilization",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(OUT_DIR, "simulation_utilization.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # Save CSV
    util_df = pd.DataFrame({
        "Unit": units,
        "Lat": [h["lat"] for h in hub_locations],
        "Lon": [h["lon"] for h in hub_locations],
        "Calls_Served": calls,
        "Busy_Hours": [secondary_busy_min[i] / 60 for i in range(K)],
        "Utilization_Pct": [round(u, 2) for u in utils],
        "Calls_Per_Day": [round(c / 365.25, 2) for c in calls],
    })
    csv_path = os.path.join(OUT_DIR, "simulation_utilization.csv")
    util_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")


def plot_hub_map(hub_locations, bg_df, cand_tm, candidates, K,
                 secondary_call_count, secondary_busy_min):
    """Static map of proposed hub locations with territories."""
    fig, ax = plt.subplots(figsize=(14, 12))

    hub_cand_ids = [hub_to_candidate_idx(h, candidates) for h in hub_locations]
    n_bg = len(bg_df)

    # Color each BG by its nearest secondary hub
    territory_colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
                        "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b"]

    for j in range(n_bg):
        bg_lat = bg_df.iloc[j]["lat"]
        bg_lon = bg_df.iloc[j]["lon"]
        bg_pop = bg_df.iloc[j]["population"]

        # Find nearest hub
        best_hub = 0
        best_drive = float("inf")
        for i, cid in enumerate(hub_cand_ids):
            drive = cand_tm[cid, j] if j < cand_tm.shape[1] else 999
            if drive < best_drive:
                best_drive = drive
                best_hub = i

        color = territory_colors[best_hub % len(territory_colors)]
        size = max(15, min(200, bg_pop / 50))
        alpha = 0.7 if best_drive <= 14 else 0.3
        ax.scatter(bg_lon, bg_lat, s=size, c=color, alpha=alpha,
                   edgecolors="#333" if alpha > 0.5 else "#999",
                   linewidths=0.5, zorder=3)

    # Existing primary stations (gray squares)
    for s in EXISTING_STATIONS:
        ax.scatter(s["lon"], s["lat"], s=80, c="#bbbbbb", marker="s",
                   edgecolors="#666", linewidths=1, zorder=5, alpha=0.6)
        ax.annotate(s["name"], (s["lon"], s["lat"] + 0.006),
                    fontsize=6.5, ha="center", color="#999", zorder=6)

    # Proposed secondary hubs (red stars)
    for i, h in enumerate(hub_locations):
        color = territory_colors[i % len(territory_colors)]
        ax.scatter(h["lon"], h["lat"], s=500, c=color, marker="*",
                   edgecolors="#333", linewidths=2, zorder=10)

        calls = secondary_call_count[i]
        util = 100 * secondary_busy_min[i] / (HOURS_PER_YEAR * 60)
        cpd = calls / 365.25

        ax.annotate(
            f"SEC-{i+1}\n{calls} calls/yr\n{cpd:.1f}/day | {util:.1f}%",
            (h["lon"], h["lat"]),
            textcoords="offset points", xytext=(15, -20),
            fontsize=8, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.9),
            zorder=11)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        f"Proposed Countywide Secondary Ambulance Network: {K} Units\n"
        f"Stars = county-wide secondary hubs | Gray squares = existing primary stations (retained)\n"
        f"Block groups colored by nearest secondary hub | Size proportional to population",
        fontsize=12, fontweight="bold")
    ax.set_aspect("equal")

    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#333",
               markersize=15, label="County-wide secondary hub (proposed)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#bbb",
               markersize=10, label="Existing primary station (retained)"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
    plt.tight_layout()

    path = os.path.join(OUT_DIR, "simulation_hub_map.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════
#  SENSITIVITY ANALYSIS ACROSS FLEET SIZES
# ══════════════════════════════════════════════════════════════════════════

def sensitivity_analysis(calls_df, existing_tm, cand_tm, candidates,
                         k_values=(3, 4, 5, 6, 8, 10)):
    """Run simulation for multiple K values and compare."""
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS: Fleet Size Sweep")
    print("=" * 70)

    rows = []
    for K in k_values:
        try:
            hubs = parse_hub_locations(K)
        except Exception as e:
            print(f"  K={K}: Skipped ({e})")
            continue

        results_df, sec_busy, sec_calls, queue = simulate_proposed_system(
            calls_df, existing_tm, cand_tm, candidates, hubs, K)

        sec_df = results_df[results_df["Call_Class"] == "Secondary"]
        n_sec = len(sec_df)

        total_pro_amb = len(EMS_TRANSPORT_DEPTS) + K
        total_busy = results_df["Duration_Min"].sum()
        sys_util = 100 * total_busy / (total_pro_amb * HOURS_PER_YEAR * 60)
        max_unit_util = max(100 * sec_busy[i] / (HOURS_PER_YEAR * 60) for i in range(K))

        rows.append({
            "K": K,
            "Secondary_Calls": n_sec,
            "Median_Secondary_RT": round(sec_df["RT_Min"].median(), 2) if n_sec > 0 else None,
            "P90_Secondary_RT": round(sec_df["RT_Min"].quantile(0.9), 2) if n_sec > 0 else None,
            "Mean_Secondary_RT": round(sec_df["RT_Min"].mean(), 2) if n_sec > 0 else None,
            "Pct_Within_10min": round(100 * (sec_df["RT_Min"] <= 10).mean(), 1) if n_sec > 0 else None,
            "Pct_Within_14min": round(100 * (sec_df["RT_Min"] <= 14).mean(), 1) if n_sec > 0 else None,
            "Queue_Events": queue,
            "System_Utilization_Pct": round(sys_util, 2),
            "Max_Unit_Utilization_Pct": round(max_unit_util, 2),
            "Total_Ambulances": total_pro_amb,
        })

    sens_df = pd.DataFrame(rows)
    csv_path = os.path.join(OUT_DIR, "simulation_sensitivity.csv")
    sens_df.to_csv(csv_path, index=False)
    print(f"\n  Saved: {csv_path}")

    # Plot sensitivity
    if len(sens_df) >= 2:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # Panel 1: Response time vs K
        ax = axes[0, 0]
        ax.plot(sens_df["K"], sens_df["Median_Secondary_RT"], "o-", color="#3498db",
                linewidth=2, markersize=8, label="Median RT")
        ax.plot(sens_df["K"], sens_df["P90_Secondary_RT"], "s--", color="#e74c3c",
                linewidth=2, markersize=7, label="P90 RT")
        ax.set_xlabel("County-Wide Secondary Units (K)")
        ax.set_ylabel("Response Time (min)")
        ax.set_title("Secondary Response Time vs Fleet Size")
        ax.legend()
        ax.grid(alpha=0.3)

        # Panel 2: Coverage vs K
        ax = axes[0, 1]
        ax.plot(sens_df["K"], sens_df["Pct_Within_10min"], "o-", color="#f39c12",
                linewidth=2, markersize=8, label="Within 10 min")
        ax.plot(sens_df["K"], sens_df["Pct_Within_14min"], "s-", color="#2ecc71",
                linewidth=2, markersize=8, label="Within 14 min")
        ax.set_xlabel("County-Wide Secondary Units (K)")
        ax.set_ylabel("% Secondary Calls Covered")
        ax.set_title("Coverage Thresholds vs Fleet Size")
        ax.legend()
        ax.grid(alpha=0.3)

        # Panel 3: Utilization vs K
        ax = axes[1, 0]
        ax.plot(sens_df["K"], sens_df["Max_Unit_Utilization_Pct"], "o-", color="#9b59b6",
                linewidth=2, markersize=8, label="Max Unit Utilization")
        ax.plot(sens_df["K"], sens_df["System_Utilization_Pct"], "s--", color="#1abc9c",
                linewidth=2, markersize=7, label="System Utilization")
        ax.set_xlabel("County-Wide Secondary Units (K)")
        ax.set_ylabel("Utilization (%)")
        ax.set_title("Utilization vs Fleet Size")
        ax.legend()
        ax.grid(alpha=0.3)

        # Panel 4: Queue events vs K
        ax = axes[1, 1]
        ax.bar(sens_df["K"], sens_df["Queue_Events"], color="#e74c3c", alpha=0.7,
               edgecolor="white")
        for _, row in sens_df.iterrows():
            ax.text(row["K"], row["Queue_Events"] + 0.5, str(int(row["Queue_Events"])),
                    ha="center", fontsize=9, fontweight="bold")
        ax.set_xlabel("County-Wide Secondary Units (K)")
        ax.set_ylabel("Queue Events (all units busy)")
        ax.set_title("Queue Events vs Fleet Size")
        ax.grid(axis="y", alpha=0.3)

        fig.suptitle(
            "Sensitivity Analysis: Countywide Secondary Network Performance\n"
            f"Simulation of {len(calls_df):,} CY2024 EMS calls | "
            f"Each dept keeps 1 primary ambulance",
            fontsize=13, fontweight="bold", y=1.02)
        plt.tight_layout()
        path = os.path.join(OUT_DIR, "simulation_sensitivity.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")

    return sens_df


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — COUNTYWIDE SECONDARY AMBULANCE SIMULATION")
    print("=" * 70)

    # ── Load infrastructure ──────────────────────────────────────────
    bg_df = load_bg_centroids()
    print(f"  Block groups: {len(bg_df)}")

    city_to_bg = build_geocoding_map(bg_df)
    print(f"  City-to-BG mappings: {len(city_to_bg)}")

    existing_tm, cand_tm, candidates = load_drive_time_matrices()

    # ── Build call timeline ──────────────────────────────────────────
    calls_df = prepare_call_timeline(bg_df, city_to_bg)

    # ── Simulate current system ──────────────────────────────────────
    current_results, cur_busy = simulate_current_system(calls_df, existing_tm)

    # ── Simulate proposed system (recommended K=10) ──────────────────
    DEFAULT_K = 10
    hub_locations = parse_hub_locations(DEFAULT_K)
    proposed_results, sec_busy, sec_calls, queue = simulate_proposed_system(
        calls_df, existing_tm, cand_tm, candidates, hub_locations, DEFAULT_K)

    # ── Compare KPIs ─────────────────────────────────────────────────
    kpi_df = compare_systems(current_results, proposed_results, DEFAULT_K, queue)

    # ── Visualizations ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS")
    print("=" * 70)

    plot_rt_distributions(current_results, proposed_results, DEFAULT_K)
    plot_hourly_profile(proposed_results, DEFAULT_K)
    plot_utilization(sec_busy, sec_calls, hub_locations, DEFAULT_K)
    plot_hub_map(hub_locations, bg_df, cand_tm, candidates, DEFAULT_K,
                 sec_calls, sec_busy)

    # ── Sensitivity analysis ─────────────────────────────────────────
    sens_df = sensitivity_analysis(
        calls_df, existing_tm, cand_tm, candidates,
        k_values=[3, 4, 5, 6, 8, 10])

    # ── Print final summary ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print(f"\n  Output directory: {OUT_DIR}")
    print(f"  Files generated:")
    for f in sorted(os.listdir(OUT_DIR)):
        print(f"    - {f}")

    print(f"\n  Key results (K={DEFAULT_K}):")
    for _, row in kpi_df.iterrows():
        print(f"    {row['KPI']}: {row['Current']} -> {row['Proposed']} (delta {row['Delta']})")

    return kpi_df, sens_df


if __name__ == "__main__":
    main()
