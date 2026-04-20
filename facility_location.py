"""
Jefferson County EMS — Optimal Facility Location Model
=======================================================
Set Covering + P-Median formulation:
  - Given: candidate station locations (existing 13 stations)
  - Given: demand points (population-weighted grid across the county)
  - Constraint: every demand point must be within T minutes of an open station
  - Objective: minimize the number of open stations (set covering)
  - Secondary: for a given K stations, minimize avg response time (p-median)

Uses real road-network drive times via OpenRouteService Matrix API.
Solves with PuLP (free CBC integer programming solver).

Author: ISyE 450 Senior Design Team
Date: March 2026
"""

import numpy as np
import pandas as pd
import json
import os
import time
import requests
import warnings
warnings.filterwarnings("ignore")

import pulp

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load .env ──────────────────────────────────────────────────────────────
def _load_env():
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")


def _get_solver(time_limit=120):
    """Pick the best available solver: Gurobi > CBC."""
    try:
        solver = pulp.GUROBI_CMD(msg=0, timeLimit=time_limit)
        if solver.available():
            print("  Solver: Gurobi (via GUROBI_CMD)")
            return solver
    except Exception:
        pass
    print("  Solver: CBC (PuLP built-in)")
    return pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit)

# ── Station data ───────────────────────────────────────────────────────────
STATIONS = [
    {"id": 0,  "name": "Watertown",     "lat": 43.1861, "lon": -88.7339, "level": "ALS",  "calls": 1947, "pop": 23000, "expense": 3833800, "cross_county": True},
    {"id": 1,  "name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397, "level": "ALS",  "calls": 1621, "pop": 16300, "expense":  760950, "cross_county": False},
    {"id": 2,  "name": "Whitewater",    "lat": 42.8325, "lon": -88.7332, "level": "ALS",  "calls": 1448, "pop":  4296, "expense": 2710609, "cross_county": True},
    {"id": 3,  "name": "Edgerton",      "lat": 42.8403, "lon": -89.0629, "level": "ALS",  "calls": 2035, "pop":  3763, "expense":  704977, "cross_county": True},
    {"id": 4,  "name": "Jefferson",     "lat": 43.0056, "lon": -88.8014, "level": "ALS",  "calls":   91, "pop":  7800, "expense": 1500300, "cross_county": False},
    {"id": 5,  "name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745, "level": "ALS",  "calls":  454, "pop":  3367, "expense": 1134154, "cross_county": False},
    {"id": 6,  "name": "Waterloo",      "lat": 43.1886, "lon": -88.9797, "level": "AEMT", "calls":  403, "pop":  4415, "expense": 1102475, "cross_county": True},
    {"id": 7,  "name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144, "level": "BLS",  "calls": None, "pop":  8700, "expense":  347000, "cross_county": False},
    {"id": 8,  "name": "Ixonia",        "lat": 43.1446, "lon": -88.5970, "level": "BLS",  "calls":  260, "pop":  5078, "expense":  631144, "cross_county": False},
    {"id": 9,  "name": "Palmyra",       "lat": 42.8794, "lon": -88.5855, "level": "BLS",  "calls":  105, "pop":  3341, "expense":  817740, "cross_county": False},
    {"id": 10, "name": "Cambridge",     "lat": 43.0049, "lon": -89.0224, "level": "ALS",  "calls":   64, "pop":  1650, "expense":   92000, "cross_county": True},
    {"id": 11, "name": "Helenville",    "lat": 43.0135, "lon": -88.6998, "level": "BLS",  "calls": None, "pop":  1500, "expense":    None, "cross_county": False},
    {"id": 12, "name": "Western Lakes", "lat": 43.0110, "lon": -88.5877, "level": "ALS",  "calls": None, "pop":  2974, "expense":    None, "cross_county": True},
]


def load_block_group_demand(bg_geojson_path=None):
    """
    Load Census Block Group centroids as demand points, with population weights.
    Uses jefferson_bg_density.geojson (produced by population_density_bg_map.py).

    Returns:
        demand_points: list of dicts with id, lat, lon (block group centroids)
        pop_weights:   numpy array of population per block group
    """
    if bg_geojson_path is None:
        bg_geojson_path = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")

    if not os.path.exists(bg_geojson_path):
        print(f"  [WARN] Block group file not found: {bg_geojson_path}")
        print("         Run population_density_bg_map.py first to generate it.")
        return None, None

    with open(bg_geojson_path, "r") as f:
        gj = json.load(f)

    demand_points = []
    populations = []
    for i, feat in enumerate(gj["features"]):
        props = feat["properties"]
        pop = props.get("P1_001N", 0)
        if pop <= 0:
            continue  # skip unpopulated block groups

        # Use the block group centroid (INTPTLAT/INTPTLON if available, else compute)
        if "INTPTLAT" in props and "INTPTLON" in props:
            lat = float(props["INTPTLAT"])
            lon = float(props["INTPTLON"])
        else:
            # Compute centroid from geometry
            from shapely.geometry import shape
            centroid = shape(feat["geometry"]).centroid
            lat, lon = centroid.y, centroid.x

        demand_points.append({
            "id": i,
            "lat": lat,
            "lon": lon,
            "geoid": props.get("GEOID_BG", f"BG_{i}"),
            "population": pop,
        })
        populations.append(pop)

    pop_weights = np.array(populations, dtype=float)
    total_pop = int(pop_weights.sum())
    print(f"  Loaded {len(demand_points)} block groups, total pop = {total_pop:,}")
    return demand_points, pop_weights


def fetch_drive_time_matrix_bg(stations, bg_demand_points):
    """
    Get drive times from stations to block group centroids.
    Separate cache from the grid-based matrix.
    """
    cache_file = os.path.join(SCRIPT_DIR, "isochrone_cache",
                              "bg_drive_time_matrix.json")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    if os.path.exists(cache_file):
        print("  Loading cached block-group drive-time matrix...")
        with open(cache_file, "r") as f:
            data = json.load(f)
        return np.array(data["matrix"]), data["stations"], data["demand_points"]

    if not ORS_API_KEY or ORS_API_KEY == "your_key_here":
        print("  [SKIP] No ORS API key -- cannot fetch matrix")
        return None, None, None

    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}

    n_stations = len(stations)
    n_demand = len(bg_demand_points)
    max_dest_per_batch = min(50 - n_stations, 3500 // n_stations)

    print(f"  Fetching: {n_stations} stations x {n_demand} block groups "
          f"({max_dest_per_batch}/batch)")

    full_matrix = np.full((n_stations, n_demand), np.inf)

    for batch_start in range(0, n_demand, max_dest_per_batch):
        batch_end = min(batch_start + max_dest_per_batch, n_demand)
        batch = bg_demand_points[batch_start:batch_end]

        locations = [[s["lon"], s["lat"]] for s in stations]
        locations += [[d["lon"], d["lat"]] for d in batch]

        payload = {
            "locations": locations,
            "sources": list(range(n_stations)),
            "destinations": list(range(n_stations, n_stations + len(batch))),
            "metrics": ["duration"], "units": "m",
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    durations = resp.json()["durations"]
                    for i in range(n_stations):
                        for j in range(len(batch)):
                            val = durations[i][j]
                            if val is not None:
                                full_matrix[i, batch_start + j] = val / 60.0
                    pct = (batch_end / n_demand) * 100
                    print(f"    Batch {batch_start}-{batch_end}: OK ({pct:.0f}%)")
                    break
                elif resp.status_code == 429:
                    print(f"    Rate limited -- waiting 60s (attempt {attempt+1})")
                    time.sleep(60)
                else:
                    print(f"    Batch FAILED: {resp.status_code} {resp.text[:100]}")
                    break
            except Exception as e:
                print(f"    Error: {e}")
                break
        time.sleep(2)

    cache_data = {
        "matrix": full_matrix.tolist(),
        "stations": [{"id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"]}
                     for s in stations],
        "demand_points": bg_demand_points,
    }
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    print(f"  Cached to {cache_file}")
    return full_matrix, stations, bg_demand_points


def generate_demand_grid(county_geojson_path, grid_spacing_deg=0.01):
    """
    Generate a grid of demand points across Jefferson County.
    Each point = a potential call location that needs coverage.

    Uses the union of all EMS district polygons as the true county boundary
    (jefferson_county.geojson is incomplete — only a small fragment).

    grid_spacing_deg=0.01 ~ 0.45 miles between points (good resolution).
    """
    from shapely.geometry import shape, Point
    from shapely.ops import unary_union

    # Build county polygon from union of all EMS districts (authoritative)
    ems_file = os.path.join(SCRIPT_DIR, "jefferson_ems_districts.geojson")
    if os.path.exists(ems_file):
        with open(ems_file, "r") as f:
            ems_geo = json.load(f)
        polys = [shape(feat["geometry"]) for feat in ems_geo["features"]]
        raw = unary_union(polys).buffer(0)  # buffer(0) fixes topology
        # Extend ~2 miles beyond county boundary — facilities naturally serve
        # beyond their own county lines. Reference: Waterloo FD serves parts
        # of 4 counties (Jefferson, Dodge, Dane, Columbia) from its station
        # at the NW corner of Jefferson Co. 5 of 13 depts are cross-county.
        BUFFER_DEG = 0.03  # ~2 miles at this latitude
        poly = raw.buffer(BUFFER_DEG)
        print(f"  County boundary: union of {len(polys)} EMS districts + {BUFFER_DEG} deg buffer")
    else:
        # Fallback to county GeoJSON
        with open(county_geojson_path, "r") as f:
            county = json.load(f)
        if county["type"] == "FeatureCollection":
            poly = shape(county["features"][0]["geometry"])
        else:
            poly = shape(county["geometry"])
        print("  County boundary: jefferson_county.geojson (fallback)")

    # Generate grid within bounding box
    minx, miny, maxx, maxy = poly.bounds
    print(f"  Bounds: lon [{minx:.4f}, {maxx:.4f}] lat [{miny:.4f}, {maxy:.4f}]")

    points = []
    idx = 0
    lat = miny
    while lat <= maxy:
        lon = minx
        while lon <= maxx:
            pt = Point(lon, lat)
            if poly.contains(pt):
                points.append({"id": idx, "lat": lat, "lon": lon})
                idx += 1
            lon += grid_spacing_deg
        lat += grid_spacing_deg

    print(f"  Generated {len(points)} demand points within county boundary")
    return points


def fetch_drive_time_matrix(stations, demand_points):
    """
    Get drive times from every station to every demand point using ORS Matrix API.
    Caches result to disk.

    Returns: numpy array of shape (n_stations, n_demand) with values in minutes.
             None values = unreachable.
    """
    cache_file = os.path.join(SCRIPT_DIR, "isochrone_cache", "drive_time_matrix.json")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    if os.path.exists(cache_file):
        print("  Loading cached drive-time matrix...")
        with open(cache_file, "r") as f:
            data = json.load(f)
        return np.array(data["matrix"]), data["stations"], data["demand_points"]

    if not ORS_API_KEY or ORS_API_KEY == "your_key_here":
        print("  [SKIP] No ORS API key -- cannot fetch matrix")
        return None, None, None

    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json",
    }

    n_stations = len(stations)
    n_demand = len(demand_points)

    # ORS Matrix API limit: max 3500 total elements (sources * destinations)
    # and max 50 total locations per request.
    # Strategy: batch demand points, all stations as sources in each batch.
    # Max destinations per batch = floor(50 - n_stations)
    max_dest_per_batch = 50 - n_stations
    if max_dest_per_batch < 1:
        print("  ERROR: Too many stations for ORS batch limit")
        return None, None, None

    # Also limited to 3500 elements per request
    max_dest_per_batch = min(max_dest_per_batch, 3500 // n_stations)

    print(f"  Fetching drive times: {n_stations} stations x {n_demand} demand points")
    print(f"  Batch size: {max_dest_per_batch} destinations per request")

    full_matrix = np.full((n_stations, n_demand), np.inf)

    for batch_start in range(0, n_demand, max_dest_per_batch):
        batch_end = min(batch_start + max_dest_per_batch, n_demand)
        batch_demand = demand_points[batch_start:batch_end]

        # Build locations array: stations first, then demand points
        locations = [[s["lon"], s["lat"]] for s in stations]
        locations += [[d["lon"], d["lat"]] for d in batch_demand]

        sources = list(range(n_stations))
        destinations = list(range(n_stations, n_stations + len(batch_demand)))

        payload = {
            "locations": locations,
            "sources": sources,
            "destinations": destinations,
            "metrics": ["duration"],
            "units": "m",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                durations = data["durations"]  # n_stations x len(batch)

                for i in range(n_stations):
                    for j in range(len(batch_demand)):
                        val = durations[i][j]
                        if val is not None:
                            full_matrix[i, batch_start + j] = val / 60.0  # seconds -> minutes

                pct = (batch_end / n_demand) * 100
                print(f"    Batch {batch_start}-{batch_end}: OK ({pct:.0f}%)")
            elif resp.status_code == 429:
                print(f"    Rate limited at batch {batch_start} -- waiting 60s")
                time.sleep(60)
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    durations = data["durations"]
                    for i in range(n_stations):
                        for j in range(len(batch_demand)):
                            val = durations[i][j]
                            if val is not None:
                                full_matrix[i, batch_start + j] = val / 60.0
                    print(f"    Batch {batch_start}-{batch_end}: OK after retry")
                else:
                    print(f"    Batch FAILED after retry: {resp.status_code}")
            else:
                print(f"    Batch {batch_start}-{batch_end}: FAILED ({resp.status_code}: {resp.text[:120]})")
        except Exception as e:
            print(f"    Batch {batch_start}-{batch_end}: ERROR ({e})")

        time.sleep(2)  # rate limit

    # Cache
    cache_data = {
        "matrix": full_matrix.tolist(),
        "stations": stations,
        "demand_points": demand_points,
    }
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    print(f"  Cached matrix to {cache_file}")

    return full_matrix, stations, demand_points


# ==============================================================================
# OPTIMIZATION MODELS
# ==============================================================================

def solve_set_covering(time_matrix, stations, demand_points, max_time_min):
    """
    Set Covering Problem:
    Find the MINIMUM number of stations to open such that every demand point
    is within max_time_min minutes of at least one open station.

    Args:
        time_matrix: (n_stations, n_demand) array of drive times in minutes
        stations: list of station dicts
        demand_points: list of demand point dicts
        max_time_min: maximum allowed response time (constraint)

    Returns:
        dict with solution details
    """
    n_stations = len(stations)
    n_demand = len(demand_points)

    # Decision variables: x[i] = 1 if station i is open
    prob = pulp.LpProblem("EMS_Set_Covering", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_stations)]

    # Objective: minimize number of open stations
    prob += pulp.lpSum(x)

    # Constraints: every demand point must be covered by at least one open station
    uncoverable = 0
    for j in range(n_demand):
        # Which stations can cover this demand point?
        covering_stations = [i for i in range(n_stations) if time_matrix[i, j] <= max_time_min]
        if len(covering_stations) == 0:
            uncoverable += 1
            continue  # no station can reach this point in time -- skip
        prob += pulp.lpSum([x[i] for i in covering_stations]) >= 1

    # Solve
    solver = _get_solver(time_limit=60)
    prob.solve(solver)

    if prob.status != 1:
        return {"status": "INFEASIBLE", "max_time": max_time_min}

    open_stations = [stations[i] for i in range(n_stations) if x[i].varValue > 0.5]
    closed_stations = [stations[i] for i in range(n_stations) if x[i].varValue < 0.5]

    return {
        "status": "OPTIMAL",
        "max_time_min": max_time_min,
        "stations_needed": len(open_stations),
        "open_stations": open_stations,
        "closed_stations": closed_stations,
        "demand_points_total": n_demand,
        "demand_uncoverable": uncoverable,
        "coverage_pct": ((n_demand - uncoverable) / n_demand) * 100,
    }


def solve_p_median(time_matrix, stations, demand_points, p, pop_weights=None):
    """
    P-Median Problem:
    Open exactly P stations to minimize total (population-weighted) response time.

    Args:
        time_matrix: (n_stations, n_demand) array
        stations: list of station dicts
        demand_points: list of demand point dicts
        p: number of stations to open
        pop_weights: optional array of weights per demand point (default: uniform)

    Returns:
        dict with solution details
    """
    n_stations = len(stations)
    n_demand = len(demand_points)

    if pop_weights is None:
        pop_weights = np.ones(n_demand)

    prob = pulp.LpProblem("EMS_P_Median", pulp.LpMinimize)

    # x[i] = 1 if station i is open
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_stations)]

    # y[i][j] = fraction of demand j assigned to station i.
    # Continuous relaxation is exact for p-median when x is binary
    # (integrality of y is guaranteed by LP theory). Much faster to solve.
    y = [[pulp.LpVariable(f"y_{i}_{j}", lowBound=0, upBound=1)
          for j in range(n_demand)] for i in range(n_stations)]

    # Objective: minimize weighted response time
    prob += pulp.lpSum([
        pop_weights[j] * time_matrix[i, j] * y[i][j]
        for i in range(n_stations)
        for j in range(n_demand)
        if time_matrix[i, j] < np.inf
    ])

    # Constraint: open exactly p stations
    prob += pulp.lpSum(x) == p

    # Constraint: each demand point assigned to exactly one station
    for j in range(n_demand):
        reachable = [i for i in range(n_stations) if time_matrix[i, j] < np.inf]
        if reachable:
            prob += pulp.lpSum([y[i][j] for i in reachable]) == 1

    # Constraint: can only assign to open stations
    for i in range(n_stations):
        for j in range(n_demand):
            if time_matrix[i, j] < np.inf:
                prob += y[i][j] <= x[i]

    # Solve
    solver = _get_solver(time_limit=300)  # p-median is harder — allow 5 min
    prob.solve(solver)

    if prob.status != 1:
        return {"status": "INFEASIBLE", "p": p}

    open_stations = [stations[i] for i in range(n_stations) if x[i].varValue > 0.5]

    # Compute metrics
    assignments = {}
    total_weighted_time = 0
    max_time = 0
    for j in range(n_demand):
        for i in range(n_stations):
            if time_matrix[i, j] < np.inf and y[i][j].varValue > 0.5:
                assignments[j] = stations[i]["name"]
                total_weighted_time += pop_weights[j] * time_matrix[i, j]
                max_time = max(max_time, time_matrix[i, j])
                break

    avg_time = total_weighted_time / pop_weights.sum() if pop_weights.sum() > 0 else 0

    return {
        "status": "OPTIMAL",
        "p": p,
        "open_stations": open_stations,
        "avg_response_min": round(avg_time, 2),
        "max_response_min": round(max_time, 2),
        "assigned": len(assignments),
        "total_demand": n_demand,
    }


def solve_mclp(time_matrix, stations, demand_points, p, max_time_min,
               pop_weights=None):
    """
    Maximal Covering Location Problem (MCLP):
    Open exactly P stations to MAXIMIZE the population covered within
    max_time_min minutes.

    Args:
        time_matrix: (n_stations, n_demand) array of drive times in minutes
        stations: list of station dicts
        demand_points: list of demand point dicts
        p: number of stations to open
        max_time_min: response time threshold (minutes)
        pop_weights: population weight per demand point (required for meaningful results)

    Returns:
        dict with solution details including population covered
    """
    n_stations = len(stations)
    n_demand = len(demand_points)

    if pop_weights is None:
        pop_weights = np.ones(n_demand)

    total_pop = pop_weights.sum()

    prob = pulp.LpProblem("EMS_MCLP", pulp.LpMaximize)

    # x[i] = 1 if station i is open
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_stations)]

    # z[j] = 1 if demand point j is covered (within max_time_min of any open station)
    z = [pulp.LpVariable(f"z_{j}", cat="Binary") for j in range(n_demand)]

    # Objective: maximize population covered
    prob += pulp.lpSum([pop_weights[j] * z[j] for j in range(n_demand)])

    # Constraint: open exactly p stations
    prob += pulp.lpSum(x) == p

    # Constraint: demand j can only be covered if at least one covering station is open
    for j in range(n_demand):
        covering = [i for i in range(n_stations) if time_matrix[i, j] <= max_time_min]
        if covering:
            prob += z[j] <= pulp.lpSum([x[i] for i in covering])
        else:
            prob += z[j] == 0  # no station can reach this point in time

    # Solve
    solver = _get_solver(time_limit=120)
    prob.solve(solver)

    if prob.status != 1:
        return {"status": "INFEASIBLE", "p": p, "max_time_min": max_time_min}

    open_stations = [stations[i] for i in range(n_stations) if x[i].varValue > 0.5]
    covered_mask = [j for j in range(n_demand) if z[j].varValue > 0.5]
    pop_covered = sum(pop_weights[j] for j in covered_mask)
    pop_uncovered = total_pop - pop_covered

    return {
        "status": "OPTIMAL",
        "p": p,
        "max_time_min": max_time_min,
        "open_stations": open_stations,
        "pop_covered": int(pop_covered),
        "pop_uncovered": int(pop_uncovered),
        "pop_total": int(total_pop),
        "pct_covered": round(100 * pop_covered / total_pop, 1) if total_pop > 0 else 0,
        "demand_covered": len(covered_mask),
        "demand_total": n_demand,
    }


# ==============================================================================
# VISUALIZATION
# ==============================================================================

def plot_optimal_stations(stations_all, solution, demand_points, max_time, time_matrix=None):
    """Plot the optimal station selection with coverage areas."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(14, 12))

    open_names = {s["name"] for s in solution["open_stations"]}

    # Plot demand points colored by nearest open station response time
    if time_matrix is not None:
        open_ids = [s["id"] for s in solution["open_stations"]]
        for j, dp in enumerate(demand_points):
            best_time = min(time_matrix[i, j] for i in open_ids)
            if best_time <= 8:
                color = "#2ecc71"
            elif best_time <= 14:
                color = "#f39c12"
            elif best_time <= 20:
                color = "#e74c3c"
            else:
                color = "#888888"
            ax.scatter(dp["lon"], dp["lat"], s=8, c=color, alpha=0.4, zorder=1)

    # Plot all stations
    for s in stations_all:
        is_open = s["name"] in open_names
        marker = "o" if is_open else "x"
        color = "#2ecc71" if is_open else "#e74c3c"
        size = 200 if is_open else 80
        edge = "#333" if not s["cross_county"] else "#e67e22"

        ax.scatter(s["lon"], s["lat"], s=size, c=color, marker=marker,
                  edgecolors=edge, linewidths=2, zorder=10)

        label = s["name"]
        if is_open:
            label = f">> {s['name']} <<"
        ax.annotate(label,
                   (s["lon"], s["lat"] + 0.008),
                   fontsize=8, ha="center", va="bottom", fontweight="bold" if is_open else "normal",
                   color="#2ecc71" if is_open else "#999",
                   bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85),
                   zorder=11)

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title(
        f"Optimal Station Placement: {solution['stations_needed']} Stations Needed\n"
        f"Constraint: Every point in county within {max_time} min drive\n"
        f"Coverage: {solution['coverage_pct']:.1f}% | "
        f"Uncoverable: {solution['demand_uncoverable']} points",
        fontsize=13, fontweight="bold",
    )

    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ecc71",
               markersize=12, label="OPEN station (selected)"),
        Line2D([0], [0], marker="x", color="#e74c3c",
               markersize=10, markeredgewidth=2, label="CLOSED station"),
        mpatches.Patch(color="#2ecc71", alpha=0.4, label="<= 8 min coverage"),
        mpatches.Patch(color="#f39c12", alpha=0.4, label="8-14 min coverage"),
        mpatches.Patch(color="#e74c3c", alpha=0.4, label="14-20 min coverage"),
        mpatches.Patch(color="#888888", alpha=0.4, label="> 20 min (gap)"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    ax.set_aspect("equal")
    plt.tight_layout()
    filename = os.path.join(SCRIPT_DIR, f"facility_optimal_{max_time}min.png")
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [OK] Saved: {filename}")


# ==============================================================================
# MOVEABLE FACILITY SCENARIOS
# ==============================================================================

def generate_candidate_grid(grid_spacing_deg=0.03):
    """
    Generate candidate station locations on a grid across the county.
    These are theoretical sites where a NEW station COULD be placed.

    grid_spacing_deg=0.03 ~ 1.4 miles spacing (coarser than demand to limit
    ORS API calls, but dense enough to find good placements).
    """
    from shapely.geometry import shape, Point
    from shapely.ops import unary_union

    ems_file = os.path.join(SCRIPT_DIR, "jefferson_ems_districts.geojson")
    with open(ems_file, "r") as f:
        ems_geo = json.load(f)
    polys = [shape(feat["geometry"]) for feat in ems_geo["features"]]
    poly = unary_union(polys).buffer(0.01)  # small buffer for road access

    minx, miny, maxx, maxy = poly.bounds
    candidates = []
    idx = 0
    lat = miny
    while lat <= maxy:
        lon = minx
        while lon <= maxx:
            if poly.contains(Point(lon, lat)):
                candidates.append({"id": idx, "name": f"CAND_{idx}", "lat": lat,
                                   "lon": lon, "level": "NEW", "calls": None,
                                   "pop": None, "expense": None,
                                   "cross_county": False})
                idx += 1
            lon += grid_spacing_deg
        lat += grid_spacing_deg

    print(f"  Generated {len(candidates)} candidate sites on {grid_spacing_deg}-deg grid")
    return candidates


def fetch_candidate_matrix(candidates, demand_points):
    """
    Get drive times from candidate sites to demand points.
    Separate cache from the existing-station matrix.
    """
    cache_file = os.path.join(SCRIPT_DIR, "isochrone_cache",
                              "candidate_drive_time_matrix.json")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    if os.path.exists(cache_file):
        print("  Loading cached candidate matrix...")
        with open(cache_file, "r") as f:
            data = json.load(f)
        return np.array(data["matrix"]), data["candidates"], data["demand_points"]

    if not ORS_API_KEY:
        print("  [SKIP] No ORS API key")
        return None, None, None

    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}

    n_cand = len(candidates)
    n_demand = len(demand_points)
    max_dest_per_batch = min(50 - n_cand, 3500 // max(n_cand, 1))

    if max_dest_per_batch < 1:
        # Too many candidates for single batch — batch by source groups
        print(f"  Too many candidates ({n_cand}) for ORS batch limit.")
        print("  Splitting into source-batched requests...")
        return _fetch_candidate_matrix_source_batched(
            candidates, demand_points, url, headers, cache_file)

    print(f"  Fetching: {n_cand} candidates x {n_demand} demand ({max_dest_per_batch}/batch)")
    full_matrix = np.full((n_cand, n_demand), np.inf)

    for batch_start in range(0, n_demand, max_dest_per_batch):
        batch_end = min(batch_start + max_dest_per_batch, n_demand)
        batch_demand = demand_points[batch_start:batch_end]

        locations = [[c["lon"], c["lat"]] for c in candidates]
        locations += [[d["lon"], d["lat"]] for d in batch_demand]

        payload = {
            "locations": locations,
            "sources": list(range(n_cand)),
            "destinations": list(range(n_cand, n_cand + len(batch_demand))),
            "metrics": ["duration"], "units": "m",
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    durations = resp.json()["durations"]
                    for i in range(n_cand):
                        for j in range(len(batch_demand)):
                            val = durations[i][j]
                            if val is not None:
                                full_matrix[i, batch_start + j] = val / 60.0
                    pct = (batch_end / n_demand) * 100
                    print(f"    Batch {batch_start}-{batch_end}: OK ({pct:.0f}%)")
                    break
                elif resp.status_code == 429:
                    print(f"    Rate limited — waiting 60s (attempt {attempt+1})")
                    time.sleep(60)
                else:
                    print(f"    Batch FAILED: {resp.status_code} {resp.text[:100]}")
                    break
            except Exception as e:
                print(f"    Error: {e}")
                break
        time.sleep(2)

    cache_data = {"matrix": full_matrix.tolist(), "candidates": candidates,
                  "demand_points": demand_points}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    print(f"  Cached to {cache_file}")
    return full_matrix, candidates, demand_points


def _fetch_candidate_matrix_source_batched(candidates, demand_points, url, headers, cache_file):
    """
    When too many candidates for a single ORS request, batch by SOURCES.
    Each request: subset of candidates (sources) x subset of demand (destinations).
    ORS limit: 50 total locations, 3500 elements per request.
    """
    n_cand = len(candidates)
    n_demand = len(demand_points)
    full_matrix = np.full((n_cand, n_demand), np.inf)

    # How many sources per batch?  sources + destinations <= 50
    # We want enough destinations per batch to be efficient.
    # Strategy: 10 sources, 40 destinations per request.
    SRC_BATCH = 10
    DST_BATCH = 40

    total_requests = ((n_cand + SRC_BATCH - 1) // SRC_BATCH) * \
                     ((n_demand + DST_BATCH - 1) // DST_BATCH)
    print(f"  Source-batched: {n_cand} cand x {n_demand} demand = ~{total_requests} requests")

    req_count = 0
    for src_start in range(0, n_cand, SRC_BATCH):
        src_end = min(src_start + SRC_BATCH, n_cand)
        src_batch = candidates[src_start:src_end]
        n_src = len(src_batch)

        for dst_start in range(0, n_demand, DST_BATCH):
            dst_end = min(dst_start + DST_BATCH, n_demand)
            dst_batch = demand_points[dst_start:dst_end]
            n_dst = len(dst_batch)

            locations = [[c["lon"], c["lat"]] for c in src_batch]
            locations += [[d["lon"], d["lat"]] for d in dst_batch]

            payload = {
                "locations": locations,
                "sources": list(range(n_src)),
                "destinations": list(range(n_src, n_src + n_dst)),
                "metrics": ["duration"], "units": "m",
            }

            for attempt in range(3):
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=60)
                    if resp.status_code == 200:
                        durations = resp.json()["durations"]
                        for i in range(n_src):
                            for j in range(n_dst):
                                val = durations[i][j]
                                if val is not None:
                                    full_matrix[src_start + i, dst_start + j] = val / 60.0
                        break
                    elif resp.status_code == 429:
                        print(f"    Rate limited — waiting 60s (attempt {attempt+1})")
                        time.sleep(60)
                    else:
                        print(f"    FAILED: {resp.status_code}")
                        break
                except Exception as e:
                    print(f"    Error: {e}")
                    break
            time.sleep(2)
            req_count += 1

            if req_count % 20 == 0:
                pct = req_count / total_requests * 100
                print(f"    Progress: {req_count}/{total_requests} requests ({pct:.0f}%)")

    cache_data = {"matrix": full_matrix.tolist(), "candidates": candidates,
                  "demand_points": demand_points}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    print(f"  Cached to {cache_file}")
    return full_matrix, candidates, demand_points


def plot_moveable_solution(existing_stations, candidates, solution, demand_points,
                           time_matrix, p, scenario_label=""):
    """Plot moveable-facility result: new optimal locations vs existing stations."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(14, 12))

    open_ids = {s["id"] for s in solution["open_stations"]}

    # Color demand points by nearest open station
    if time_matrix is not None:
        open_indices = [i for i, c in enumerate(candidates) if c["id"] in open_ids]
        for j, dp in enumerate(demand_points):
            best_time = min(time_matrix[i, j] for i in open_indices)
            if best_time <= 8:
                color = "#2ecc71"
            elif best_time <= 14:
                color = "#f39c12"
            elif best_time <= 20:
                color = "#e74c3c"
            else:
                color = "#888888"
            ax.scatter(dp["lon"], dp["lat"], s=6, c=color, alpha=0.3, zorder=1)

    # Plot existing stations (reference)
    for s in existing_stations:
        ax.scatter(s["lon"], s["lat"], s=80, c="#bbbbbb", marker="s",
                   edgecolors="#666", linewidths=1.5, zorder=5, alpha=0.7)
        ax.annotate(s["name"], (s["lon"], s["lat"] + 0.006),
                    fontsize=7, ha="center", color="#999", zorder=6)

    # Plot optimal NEW locations
    for s in solution["open_stations"]:
        ax.scatter(s["lon"], s["lat"], s=250, c="#e74c3c", marker="*",
                   edgecolors="#333", linewidths=1.5, zorder=10)
        ax.annotate(f"NEW ({s['lat']:.3f}, {s['lon']:.3f})",
                    (s["lon"], s["lat"] - 0.008),
                    fontsize=7, ha="center", va="top", fontweight="bold",
                    color="#c0392b",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.9),
                    zorder=11)

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title(
        f"Moveable Facility: Optimal {p} NEW Station Locations\n"
        f"{scenario_label}"
        f"Avg response: {solution['avg_response_min']:.1f} min | "
        f"Max: {solution['max_response_min']:.1f} min",
        fontsize=12, fontweight="bold",
    )

    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#e74c3c",
               markersize=15, label="OPTIMAL new location"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#bbb",
               markersize=10, label="Existing station (reference)"),
        mpatches.Patch(color="#2ecc71", alpha=0.4, label="<= 8 min"),
        mpatches.Patch(color="#f39c12", alpha=0.4, label="8-14 min"),
        mpatches.Patch(color="#e74c3c", alpha=0.4, label="14-20 min"),
        mpatches.Patch(color="#888888", alpha=0.4, label="> 20 min"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
    ax.set_aspect("equal")
    plt.tight_layout()

    fname = os.path.join(SCRIPT_DIR, f"facility_moveable_K{p}.png")
    plt.savefig(fname, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [OK] Saved: {fname}")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — OPTIMAL FACILITY LOCATION MODEL")
    print("=" * 70)

    county_file = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")

    # ── Step 1: Generate demand grid ──────────────────────────────────────
    print("\n>> STEP 1: Generating demand points")
    print("-" * 50)
    demand_points = generate_demand_grid(county_file, grid_spacing_deg=0.02)

    # ── Step 2: Get drive-time matrix (existing stations) ─────────────────
    print("\n>> STEP 2: Computing drive-time matrix (existing stations -> demand)")
    print("-" * 50)
    time_matrix, _, _ = fetch_drive_time_matrix(STATIONS, demand_points)

    if time_matrix is None:
        print("  Cannot proceed without drive-time matrix.")
        return

    # ── Step 3: Set Covering at multiple thresholds ───────────────────────
    print("\n>> STEP 3: Set Covering — Minimum stations by response time")
    print("-" * 50)
    print("  (Using existing 13 station locations only)\n")

    results = []
    for max_time in [8, 10, 12, 14, 16, 20]:
        sol = solve_set_covering(time_matrix, STATIONS, demand_points, max_time)
        if sol["status"] == "OPTIMAL":
            open_names = [s["name"] for s in sol["open_stations"]]
            closed_names = [s["name"] for s in sol["closed_stations"]]
            print(f"  {max_time:2d}-min standard: {sol['stations_needed']} stations needed "
                  f"({sol['coverage_pct']:.1f}% coverage)")
            print(f"    OPEN:   {', '.join(open_names)}")
            if closed_names:
                print(f"    CLOSE:  {', '.join(closed_names)}")
            print()

            sol["threshold"] = max_time
            results.append(sol)

            if max_time in (14, 20):
                plot_optimal_stations(STATIONS, sol, demand_points, max_time, time_matrix)
        else:
            print(f"  {max_time:2d}-min standard: INFEASIBLE")

    # ── Step 4: P-Median (existing stations) ──────────────────────────────
    print("\n>> STEP 4: P-Median — Best K existing stations")
    print("-" * 50)
    print("  For each K, which existing stations minimize avg response time?\n")

    pmed_results = []
    for p in range(3, min(10, len(STATIONS))):
        sol = solve_p_median(time_matrix, STATIONS, demand_points, p)
        if sol["status"] == "OPTIMAL":
            open_names = [s["name"] for s in sol["open_stations"]]
            print(f"  K={p}: avg={sol['avg_response_min']:.1f} min, "
                  f"max={sol['max_response_min']:.1f} min")
            print(f"    Stations: {', '.join(open_names)}")
            pmed_results.append(sol)
        else:
            print(f"  K={p}: could not solve")

    # ── Step 4B: Population-weighted P-Median (block group demand) ───────
    print("\n>> STEP 4B: Population-Weighted P-Median (Block Group Centroids)")
    print("-" * 50)
    bg_demand, bg_pop_weights = load_block_group_demand()

    bg_time_matrix = None
    mclp_results = []
    pmed_pop_results = []

    if bg_demand is not None:
        print("  Fetching drive times for block group centroids...")
        bg_time_matrix, _, _ = fetch_drive_time_matrix_bg(STATIONS, bg_demand)

        if bg_time_matrix is not None:
            # Population-weighted P-Median
            print("\n  Population-weighted P-Median (minimize pop-weighted avg response):\n")
            for p in range(3, min(10, len(STATIONS))):
                sol = solve_p_median(bg_time_matrix, STATIONS, bg_demand, p,
                                     pop_weights=bg_pop_weights)
                if sol["status"] == "OPTIMAL":
                    open_names = [s["name"] for s in sol["open_stations"]]
                    print(f"  K={p}: avg={sol['avg_response_min']:.1f} min (pop-weighted), "
                          f"max={sol['max_response_min']:.1f} min")
                    print(f"    Stations: {', '.join(open_names)}")
                    pmed_pop_results.append(sol)

            # MCLP — Maximize population covered
            print("\n  MCLP — Maximize Population Covered:\n")
            for max_t in [8, 10, 14, 20]:
                for p in [5, 7, 9, 13]:
                    sol = solve_mclp(bg_time_matrix, STATIONS, bg_demand, p,
                                     max_t, pop_weights=bg_pop_weights)
                    if sol["status"] == "OPTIMAL":
                        print(f"  T={max_t:2d} min, K={p:2d}: "
                              f"{sol['pct_covered']:.1f}% pop covered "
                              f"({sol['pop_covered']:,} / {sol['pop_total']:,})")
                        open_names = [s["name"] for s in sol["open_stations"]]
                        print(f"    Stations: {', '.join(open_names)}")
                        mclp_results.append(sol)
    else:
        print("  [SKIP] Block group data not available.")
        print("  Run population_density_bg_map.py first.")

    # ── Step 5: MOVEABLE FACILITY — theoretical new locations ─────────────
    print("\n\n" + "=" * 70)
    print("SCENARIO B: MOVEABLE FACILITIES — Optimal NEW station placement")
    print("=" * 70)
    print("  If we could place stations ANYWHERE in the county (ignoring")
    print("  existing buildings), where would the optimal locations be?")
    print("  Reference: Waterloo FD serves 4 counties from NW corner —")
    print("  facilities naturally extend beyond county boundaries.\n")

    candidates = generate_candidate_grid(grid_spacing_deg=0.06)
    cand_matrix, _, _ = fetch_candidate_matrix(candidates, demand_points)

    cand_pmed_results = []
    if cand_matrix is not None:
        print()
        for p in [3, 5, 7, 9]:
            print(f"  --- Moveable K={p} ---")
            sol = solve_p_median(cand_matrix, candidates, demand_points, p)
            if sol["status"] == "OPTIMAL":
                print(f"  avg={sol['avg_response_min']:.1f} min, "
                      f"max={sol['max_response_min']:.1f} min")
                for s in sol["open_stations"]:
                    print(f"    -> ({s['lat']:.4f}, {s['lon']:.4f})")

                # Compare to existing-station p-median
                existing_pmed = [r for r in pmed_results if r["p"] == p]
                if existing_pmed:
                    delta = existing_pmed[0]["avg_response_min"] - sol["avg_response_min"]
                    print(f"  Improvement over existing: {delta:.1f} min avg")

                plot_moveable_solution(STATIONS, candidates, sol, demand_points,
                                       cand_matrix, p,
                                       scenario_label="Stations can be placed anywhere | ")
                cand_pmed_results.append(sol)
            else:
                print(f"  K={p}: could not solve")
            print()
    else:
        print("  [SKIP] Could not compute candidate matrix")

    # ── Step 6: Summary ──────────────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("SUMMARY: RESPONSE-TIME-CONSTRAINED FACILITY OPTIMIZATION")
    print("=" * 70)

    print("""
  SCENARIO A — Existing stations (select/deselect from 13 current locations):

    Current state: 13 station locations, 10 with ambulances.
    Question: How many are actually NEEDED to cover the county?
    """)

    if results:
        print("    Response Time | Min Stations | Coverage")
        print("    " + "-" * 45)
        for r in results:
            print(f"    {r['max_time_min']:>6d} min    |  {r['stations_needed']:>5d}       | {r['coverage_pct']:>6.1f}%")

    print("""
  SCENARIO B — Moveable facilities (place stations anywhere on the map):

    What if we could redesign the station network from scratch?
    (Theoretical lower bound — identifies where coverage gaps exist)
    """)

    print("""
  CAVEATS (both scenarios):
    - Cross-county obligations not modeled (Waterloo serves 4 counties,
      Watertown straddles Jefferson/Dodge, etc.)
    - No simultaneous-call coverage (no backup station requirement)
    - ALS vs BLS level differences not modeled
    - Volunteer availability constraints not included
    - Political/contractual boundaries ignored
    - The Working Group should use these as DIAGNOSTIC context, not
      as a direct implementation plan.
    """)

    # Save results
    summary = []
    for r in results:
        summary.append({
            "Scenario": "A_Existing",
            "Response_Time_Min": r["max_time_min"],
            "Stations_Needed": r["stations_needed"],
            "Coverage_Pct": round(r["coverage_pct"], 1),
            "Open_Stations": ", ".join(s["name"] for s in r["open_stations"]),
            "Closed_Stations": ", ".join(s["name"] for s in r["closed_stations"]),
        })
    csv_path = os.path.join(SCRIPT_DIR, "facility_location_results.csv")
    pd.DataFrame(summary).to_csv(csv_path, index=False)
    print(f"  [OK] Saved: {csv_path}")

    # ── Step 7: Interactive map ──────────────────────────────────────────
    print("\n>> STEP 7: Building interactive map")
    print("-" * 50)
    build_interactive_map(
        existing_stations=STATIONS,
        demand_points=demand_points,
        time_matrix=time_matrix,
        results=results,
        pmed_results=pmed_results,
        candidates=candidates,
        cand_matrix=cand_matrix,
        cand_pmed_results=cand_pmed_results,
    )

    print("\n  Done.")


def build_interactive_map(existing_stations, demand_points, time_matrix,
                          results, pmed_results, candidates=None, cand_matrix=None,
                          cand_pmed_results=None):
    """
    Build an interactive Folium map combining all optimization results.
    Layers: existing stations, set covering solutions, p-median solutions,
    moveable facility solutions, demand point coverage heatmap.
    """
    import folium
    from folium.plugins import MarkerCluster

    center = [43.02, -88.77]
    m = folium.Map(location=center, zoom_start=10, tiles=None)

    # Basemaps
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        name="OpenStreetMap", attr="OSM contributors",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        name="Light (CartoDB)", attr="CartoDB",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Satellite (Esri)", attr="Esri",
    ).add_to(m)

    # ── EMS district boundaries (background) ─────────────────────────────
    ems_file = os.path.join(SCRIPT_DIR, "jefferson_ems_districts.geojson")
    if os.path.exists(ems_file):
        districts = folium.FeatureGroup(name="EMS District Boundaries", show=True)
        with open(ems_file, "r") as f:
            ems_geo = json.load(f)
        COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                   "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
                   "#aec7e8", "#ffbb78"]
        for i, feat in enumerate(ems_geo["features"]):
            c = COLORS[i % len(COLORS)]
            label = feat["properties"].get("MAPLABEL", f"District {i+1}")
            folium.GeoJson(
                feat,
                style_function=lambda x, c=c: {"fillColor": c, "fillOpacity": 0.06,
                                                 "color": c, "weight": 2},
                tooltip=folium.Tooltip(label, sticky=True),
            ).add_to(districts)
        districts.add_to(m)

    # ── Existing stations ─────────────────────────────────────────────────
    LEVEL_COLORS = {"ALS": "#e74c3c", "AEMT": "#f39c12", "BLS": "#3498db"}
    existing_group = folium.FeatureGroup(name="Existing Stations (13)", show=True)
    for s in existing_stations:
        color = LEVEL_COLORS.get(s["level"], "#888")
        calls_str = str(s["calls"]) if s["calls"] else "N/A"
        exp_str = f"${s['expense']:,.0f}" if s["expense"] else "N/A"
        cross = " (CROSS-COUNTY)" if s["cross_county"] else ""
        popup = (f"<b>{s['name']}{cross}</b><br>"
                 f"Level: {s['level']}<br>"
                 f"Calls: {calls_str}<br>"
                 f"Expense: {exp_str}<br>"
                 f"Pop: {s['pop']:,}")
        folium.CircleMarker(
            [s["lat"], s["lon"]], radius=10,
            color="#e67e22" if s["cross_county"] else "#333",
            weight=3 if s["cross_county"] else 2,
            fill=True, fill_color=color, fill_opacity=0.9,
            popup=folium.Popup(popup, max_width=250),
            tooltip=f"{s['name']} ({s['level']})",
        ).add_to(existing_group)
    existing_group.add_to(m)

    # ── Set Covering solutions (key thresholds) ──────────────────────────
    for r in results:
        t = r["max_time_min"]
        if t not in (14, 16, 20):
            continue
        open_names = {s["name"] for s in r["open_stations"]}
        group = folium.FeatureGroup(
            name=f"Set Cover: {t}-min ({r['stations_needed']} stations, "
                 f"{r['coverage_pct']:.0f}%)",
            show=False,
        )
        for s in existing_stations:
            is_open = s["name"] in open_names
            color = "#2ecc71" if is_open else "#e74c3c"
            icon = "check" if is_open else "times"
            folium.Marker(
                [s["lat"], s["lon"]],
                icon=folium.Icon(color="green" if is_open else "red", icon=icon,
                                 prefix="fa"),
                tooltip=f"{'OPEN' if is_open else 'CLOSED'}: {s['name']}",
            ).add_to(group)
        group.add_to(m)

    # ── P-Median solutions (existing stations) ───────────────────────────
    for sol in pmed_results:
        if sol["p"] not in (5, 7, 9):
            continue
        open_names = {s["name"] for s in sol["open_stations"]}
        group = folium.FeatureGroup(
            name=f"P-Median K={sol['p']}: avg {sol['avg_response_min']:.1f} min "
                 f"(existing)",
            show=False,
        )
        for s in existing_stations:
            is_open = s["name"] in open_names
            if is_open:
                folium.CircleMarker(
                    [s["lat"], s["lon"]], radius=14,
                    color="#2ecc71", weight=3, fill=True,
                    fill_color="#2ecc71", fill_opacity=0.7,
                    tooltip=f"SELECTED: {s['name']}",
                ).add_to(group)
        group.add_to(m)

    # ── Moveable facility solutions ──────────────────────────────────────
    if cand_pmed_results:
        for sol in cand_pmed_results:
            p = sol["p"]
            group = folium.FeatureGroup(
                name=f"MOVEABLE K={p}: avg {sol['avg_response_min']:.1f} min (new sites)",
                show=False,
            )
            for s in sol["open_stations"]:
                folium.Marker(
                    [s["lat"], s["lon"]],
                    icon=folium.Icon(color="red", icon="star", prefix="fa"),
                    tooltip=f"NEW OPTIMAL ({s['lat']:.3f}, {s['lon']:.3f})",
                    popup=folium.Popup(
                        f"<b>Optimal New Station</b><br>"
                        f"Lat: {s['lat']:.4f}<br>Lon: {s['lon']:.4f}<br>"
                        f"Scenario: {p} stations, "
                        f"avg {sol['avg_response_min']:.1f} min",
                        max_width=250,
                    ),
                ).add_to(group)
            group.add_to(m)

    # ── Demand coverage heatmap (best existing-station coverage) ─────────
    if time_matrix is not None:
        coverage_group = folium.FeatureGroup(name="Demand Coverage (all 13 stations)", show=False)
        for j, dp in enumerate(demand_points):
            best = min(time_matrix[i, j] for i in range(len(existing_stations)))
            if best <= 8:
                c, label = "#2ecc71", "<=8 min"
            elif best <= 14:
                c, label = "#f39c12", "8-14 min"
            elif best <= 20:
                c, label = "#e74c3c", "14-20 min"
            else:
                c, label = "#888", ">20 min"
            folium.CircleMarker(
                [dp["lat"], dp["lon"]], radius=2,
                color=c, fill=True, fill_color=c, fill_opacity=0.5,
                weight=0,
                tooltip=f"{label} ({best:.1f} min)",
            ).add_to(coverage_group)
        coverage_group.add_to(m)

    # ── Layer control ─────────────────────────────────────────────────────
    folium.LayerControl(collapsed=False).add_to(m)

    # ── Title ─────────────────────────────────────────────────────────────
    title_html = """
    <div style="position:fixed; top:10px; left:60px; z-index:9999;
                background:white; padding:10px 16px; border-radius:8px;
                box-shadow:0 2px 6px rgba(0,0,0,0.3); font-family:Arial,sans-serif;">
        <h3 style="margin:0 0 4px 0;">Jefferson County EMS - Facility Location Optimization</h3>
        <p style="margin:0; font-size:12px; color:#666;">
            Scenarios: Existing Stations (Set Cover + P-Median) |
            Moveable Facilities (Optimal New Placement)<br>
            Solver: Gurobi | Drive times: ORS road network | Demand: 0.02-deg grid
        </p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # ── Legend ─────────────────────────────────────────────────────────────
    legend_html = """
    <div style="position:fixed; bottom:30px; right:10px; z-index:9999;
                background:white; padding:12px 16px; border-radius:8px;
                box-shadow:0 2px 6px rgba(0,0,0,0.3); font-family:Arial,sans-serif;
                font-size:12px; line-height:1.6;">
        <b>Existing Stations</b><br>
        <span style="color:#e74c3c;">&#9679;</span> ALS
        <span style="color:#f39c12;">&#9679;</span> AEMT
        <span style="color:#3498db;">&#9679;</span> BLS<br>
        <span style="color:#e67e22;">&#9675;</span> Cross-county dept<br>
        <hr style="margin:6px 0;">
        <b>Optimization Results</b><br>
        <span style="color:#2ecc71;">&#9679;</span> Selected (open)<br>
        <span style="color:#e74c3c;">&#10005;</span> Not selected (closed)<br>
        <span style="color:#e74c3c;">&#9733;</span> NEW optimal location<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    output = os.path.join(SCRIPT_DIR, "facility_location_map.html")
    m.save(output)
    print(f"  [OK] Saved interactive map: {output}")
    return output


if __name__ == "__main__":
    main()
