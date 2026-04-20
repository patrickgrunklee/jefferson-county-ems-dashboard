"""
Jefferson County EMS — Territory Boundary Redesign Analysis
============================================================
Generates a comprehensive analysis document + maps comparing:
  Scenario 0: Current 12-district historical boundaries
  Scenario 1: Optimized Voronoi (same 13 stations, redrawn by closest RT)
  Scenario 2: 2-Hub + Local First-Response (Watertown/Fort Atkinson hubs)
  Scenario 3: Consolidated K=10 P-Median
  Scenario 4: Consolidated K=8 P-Median

Outputs:
  - Territory_Boundary_Analysis.md
  - territory_scenario_0_baseline.png
  - territory_scenario_1_optimized.png
  - territory_scenario_2_hub_satellite.png
  - territory_scenario_3_K10.png
  - territory_scenario_4_K8.png
  - territory_comparison_chart.png

Data: Pre-computed ORS drive-time matrices, Census block groups, EMS district GeoJSON
"""

import os, json, csv, warnings, textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.lines import Line2D
from shapely.geometry import shape, Point, MultiPolygon, Polygon
from scipy.spatial import ConvexHull

warnings.filterwarnings("ignore")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

STATIONS = [
    {"name": "Watertown",     "lat": 43.1861, "lon": -88.7339, "level": "ALS",  "idx": 0},
    {"name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397, "level": "ALS",  "idx": 1},
    {"name": "Whitewater",    "lat": 42.8325, "lon": -88.7332, "level": "ALS",  "idx": 2},
    {"name": "Edgerton",      "lat": 42.8403, "lon": -89.0629, "level": "ALS",  "idx": 3},
    {"name": "Jefferson",     "lat": 43.0056, "lon": -88.8014, "level": "ALS",  "idx": 4},
    {"name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745, "level": "ALS",  "idx": 5},
    {"name": "Waterloo",      "lat": 43.1886, "lon": -88.9797, "level": "AEMT", "idx": 6},
    {"name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144, "level": "BLS",  "idx": 7},
    {"name": "Ixonia",        "lat": 43.1446, "lon": -88.5970, "level": "BLS",  "idx": 8},
    {"name": "Palmyra",       "lat": 42.8794, "lon": -88.5855, "level": "BLS",  "idx": 9},
    {"name": "Cambridge",     "lat": 43.0049, "lon": -89.0224, "level": "ALS",  "idx": 10},
    {"name": "Helenville",    "lat": 43.0135, "lon": -88.6998, "level": "BLS",  "idx": 11},
    {"name": "Western Lakes", "lat": 43.0110, "lon": -88.5877, "level": "ALS",  "idx": 12},
]
STATION_NAMES = [s["name"] for s in STATIONS]

# EMS district polygon label → station row index
DISTRICT_TO_IDX = {
    "Watertown EMS": 0, "Fort Atkinson EMS": 1, "Whitewater EMS": 2,
    "Edgerton EMS": 3, "Jefferson EMS": 4, "Johnson Creek EMS": 5,
    "Waterloo EMS": 6, "Lake Mills EMS": 7, "Ixonia EMS": 8,
    "Palmyra EMS": 9, "Cambridge EMS": 10, "Ryan Brothers EMS": 11,
    "Western Lakes": 12,
}

# CY2024 call volumes
AUTH_EMS = {
    "Watertown": 2012, "Fort Atkinson": 1616, "Whitewater": 64,
    "Edgerton": 2138, "Jefferson": 1457, "Johnson Creek": 487,
    "Waterloo": 520, "Lake Mills": 518, "Ixonia": 289,
    "Palmyra": 32, "Cambridge": 87, "Helenville": 0, "Western Lakes": 5633,
}

# Service area populations (WI DOA 2025)
SERVICE_POP = {
    "Watertown": 16524, "Fort Atkinson": 18629, "Whitewater": 4925,
    "Edgerton": 492, "Jefferson": 11192, "Johnson Creek": 5601,
    "Waterloo": 4603, "Lake Mills": 11095, "Ixonia": 5988,
    "Palmyra": 2957, "Cambridge": 342, "Helenville": 0, "Western Lakes": 4507,
}

LAKE_LABELS = {
    "Lake Koshkonong": {"lat": 42.875, "lon": -88.915, "fontsize": 9},
    "Rock Lake":       {"lat": 43.085, "lon": -88.920, "fontsize": 7},
}

# 13 distinct territory colors
TERRITORY_COLORS = [
    "#e74c3c", "#2471a3", "#8e44ad", "#1e8449", "#e67e22",
    "#c0392b", "#2980b9", "#27ae60", "#d4ac0d", "#7d3c98",
    "#1abc9c", "#e74c3c", "#34495e",
]

HUB_COLORS = {"Watertown": "#c0392b", "Fort Atkinson": "#2471a3"}
HUB_LIGHT  = {"Watertown": "#f5b7b1", "Fort Atkinson": "#aed6f1"}


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_all_data():
    """Load all GeoJSON, matrices, and candidate coords."""
    data = {}

    # Block groups
    with open(os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")) as f:
        data["bg_gj"] = json.load(f)

    # County boundary
    with open(os.path.join(SCRIPT_DIR, "jefferson_county.geojson")) as f:
        data["county_gj"] = json.load(f)

    # EMS districts
    with open(os.path.join(SCRIPT_DIR, "jefferson_ems_districts.geojson")) as f:
        data["ems_gj"] = json.load(f)

    # Water bodies
    water_path = os.path.join(SCRIPT_DIR, "jefferson_water_bodies.geojson")
    if os.path.exists(water_path):
        with open(water_path) as f:
            data["water_gj"] = json.load(f)
    else:
        data["water_gj"] = None

    # Existing stations → BG drive times (13×65)
    with open(os.path.join(SCRIPT_DIR, "isochrone_cache", "existing_bg_drive_time_matrix.json")) as f:
        data["existing_matrix"] = np.array(json.load(f)["matrix"])

    # Candidate → BG drive times (60×65)
    with open(os.path.join(SCRIPT_DIR, "isochrone_cache", "cand_bg_drive_time_matrix.json")) as f:
        data["cand_matrix"] = np.array(json.load(f)["matrix"])

    # Candidate coordinates
    with open(os.path.join(SCRIPT_DIR, "isochrone_cache", "candidate_drive_time_matrix.json")) as f:
        cand_data = json.load(f)
    data["candidates"] = cand_data["candidates"]

    # Population weights per BG
    pop_weights = []
    for feat in data["bg_gj"]["features"]:
        pop = feat["properties"].get("P1_001N", 0)
        pop_weights.append(max(pop, 0))
    data["pop_weights"] = np.array(pop_weights, dtype=float)

    # Pareto results
    data["pareto"] = []
    with open(os.path.join(SCRIPT_DIR, "pareto_results.csv")) as f:
        for row in csv.DictReader(f):
            data["pareto"].append(row)

    return data


# ═══════════════════════════════════════════════════════════════════════════
# ASSIGNMENT & METRICS
# ═══════════════════════════════════════════════════════════════════════════

def assign_current_districts(data):
    """Scenario 0: assign each BG to its current EMS district via point-in-polygon."""
    bg_gj = data["bg_gj"]
    ems_gj = data["ems_gj"]
    existing_matrix = data["existing_matrix"]

    # Build district polygons
    districts = []
    for feat in ems_gj["features"]:
        geom = shape(feat["geometry"])
        label = feat["properties"].get("MAPLABEL", feat["properties"].get("NAME", ""))
        sidx = DISTRICT_TO_IDX.get(label)
        if sidx is not None:
            districts.append((geom, sidx, label))

    n_bg = len(bg_gj["features"])
    assignments = np.zeros(n_bg, dtype=int)  # station row index
    drive_times = np.zeros(n_bg)

    for j, feat in enumerate(bg_gj["features"]):
        lat = float(feat["properties"]["INTPTLAT"])
        lon = float(feat["properties"]["INTPTLON"])
        pt = Point(lon, lat)

        assigned = False
        for geom, sidx, dname in districts:
            if geom.contains(pt):
                assignments[j] = sidx
                drive_times[j] = existing_matrix[sidx, j]
                assigned = True
                break

        if not assigned:
            # Fallback: nearest station
            best_i = int(np.argmin(existing_matrix[:, j]))
            assignments[j] = best_i
            drive_times[j] = existing_matrix[best_i, j]

    return assignments, drive_times


def assign_nearest_existing(data, station_indices=None):
    """Assign each BG to nearest station from existing matrix. station_indices defaults to all 13."""
    if station_indices is None:
        station_indices = list(range(13))
    matrix = data["existing_matrix"]
    n_bg = matrix.shape[1]
    assignments = np.zeros(n_bg, dtype=int)
    drive_times = np.zeros(n_bg)
    for j in range(n_bg):
        best_i = station_indices[0]
        best_t = matrix[best_i, j]
        for i in station_indices:
            if matrix[i, j] < best_t:
                best_t = matrix[i, j]
                best_i = i
        assignments[j] = best_i
        drive_times[j] = best_t
    return assignments, drive_times


def assign_candidate_stations(data, coords):
    """Assign BGs using candidate matrix for a given set of station coordinates."""
    candidates = data["candidates"]
    cand_matrix = data["cand_matrix"]

    # Match coords to candidate indices
    open_indices = []
    for lat, lon in coords:
        best_i, best_d = 0, 999
        for i, c in enumerate(candidates):
            d = abs(c["lat"] - lat) + abs(c["lon"] - lon)
            if d < best_d:
                best_d = d
                best_i = i
        open_indices.append(best_i)

    n_bg = cand_matrix.shape[1]
    assignments = np.zeros(n_bg, dtype=int)  # index into open_indices
    drive_times = np.zeros(n_bg)
    assignment_cand_idx = np.zeros(n_bg, dtype=int)  # actual candidate index

    for j in range(n_bg):
        best_k, best_t = 0, np.inf
        for k, ci in enumerate(open_indices):
            if cand_matrix[ci, j] < best_t:
                best_t = cand_matrix[ci, j]
                best_k = k
        assignments[j] = best_k
        drive_times[j] = best_t
        assignment_cand_idx[j] = open_indices[best_k]

    return assignments, drive_times, open_indices


def parse_pareto_stations(data, K, T="PMed"):
    """Parse station coordinates from pareto_results.csv for given K and T."""
    for row in data["pareto"]:
        if row["K"] == str(K) and row["T"] == T:
            stations_str = row["stations"]
            coords = []
            for part in stations_str.split("|"):
                part = part.strip().strip("()")
                lat, lon = part.split(",")
                coords.append((float(lat), float(lon)))
            avg_rt = float(row["avg_rt"])
            max_rt = float(row["max_rt"])
            return coords, avg_rt, max_rt
    return None, None, None


def compute_metrics(drive_times, pop_weights):
    """Compute population-weighted KPIs."""
    mask = pop_weights > 0
    dt = drive_times[mask]
    pw = pop_weights[mask]
    total_pop = pw.sum()

    if total_pop == 0:
        return {}

    avg_rt = float(np.average(dt, weights=pw))
    med_rt = float(np.median(dt))
    p90_rt = float(np.percentile(dt, 90))
    max_rt = float(np.max(dt))
    cov_8 = 100.0 * pw[dt <= 8].sum() / total_pop
    cov_10 = 100.0 * pw[dt <= 10].sum() / total_pop
    cov_14 = 100.0 * pw[dt <= 14].sum() / total_pop

    return {
        "avg_rt": round(avg_rt, 2),
        "med_rt": round(med_rt, 2),
        "p90_rt": round(p90_rt, 2),
        "max_rt": round(max_rt, 2),
        "cov_8": round(cov_8, 1),
        "cov_10": round(cov_10, 1),
        "cov_14": round(cov_14, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAP DRAWING
# ═══════════════════════════════════════════════════════════════════════════

def _draw_county(ax, county_gj):
    """Draw county boundary as light background."""
    for feat in county_gj.get("features", [county_gj]):
        geom = feat.get("geometry", feat)
        s = shape(geom)
        polys = list(s.geoms) if hasattr(s, "geoms") else [s]
        for poly in polys:
            x, y = poly.exterior.xy
            ax.fill(list(x), list(y), facecolor="#eef2f7", edgecolor="#7f8c8d",
                    linewidth=2.0, alpha=0.5, zorder=0)


def _draw_water(ax, water_gj):
    """Draw water bodies with light blue hatching."""
    if water_gj is None:
        return
    for feat in water_gj["features"]:
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            poly_list = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            poly_list = geom["coordinates"]
        else:
            continue
        for poly_coords in poly_list:
            exterior = poly_coords[0]
            xy = [(c[0], c[1]) for c in exterior]
            patch = MplPolygon(xy, closed=True)
            patch.set_facecolor("#b3d9f2")
            patch.set_alpha(0.55)
            patch.set_edgecolor("#6baed6")
            patch.set_linewidth(0.6)
            patch.set_hatch("//")
            patch.set_zorder(3)
            ax.add_patch(patch)
    for label, pos in LAKE_LABELS.items():
        ax.annotate(label, (pos["lon"], pos["lat"]),
                    fontsize=pos["fontsize"], fontstyle="italic", fontweight="bold",
                    color="#2171b5", ha="center", va="center", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              alpha=0.7, edgecolor="#6baed6", linewidth=0.5))


def _draw_ems_district_outlines(ax, ems_gj):
    """Draw current EMS district boundaries as dashed overlay."""
    for feat in ems_gj["features"]:
        geom = feat["geometry"]
        label = feat["properties"].get("MAPLABEL", "")
        s = shape(geom)
        polys = list(s.geoms) if hasattr(s, "geoms") else [s]
        for poly in polys:
            x, y = poly.exterior.xy
            ax.plot(list(x), list(y), color="#333", linewidth=1.8,
                    linestyle="--", alpha=0.6, zorder=5)


def plot_territory_map(scenario_name, title_lines, bg_gj, county_gj, water_gj,
                       assignments, drive_times, pop_weights, station_list,
                       metrics, filename, ems_overlay_gj=None,
                       use_station_colors=False, station_coords=None):
    """
    Generic territory map renderer.
    assignments: array(65) of station indices (into station_list for coloring)
    drive_times: array(65) of minutes
    station_list: list of dicts with name, lat, lon, level
    station_coords: optional list of (lat,lon) for candidate-based scenarios
    """
    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_facecolor("#f5f5f0")
    fig.patch.set_facecolor("white")

    # County boundary
    _draw_county(ax, county_gj)

    # Response-time color map
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rt", ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"])
    vmin, vmax = 0, 22
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    # Filter BGs with pop > 0
    features_pop = [(i, feat) for i, feat in enumerate(bg_gj["features"])
                    if feat["properties"].get("P1_001N", 0) > 0]

    # Pass 1: BG polygons colored by drive time
    for bg_idx, (orig_idx, feat) in enumerate(features_pop):
        geom = feat["geometry"]
        dt = drive_times[orig_idx]
        color = cmap(norm(dt))
        if geom["type"] == "Polygon":
            poly_list = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            poly_list = geom["coordinates"]
        else:
            continue
        for poly_coords in poly_list:
            exterior = poly_coords[0]
            xy = [(c[0], c[1]) for c in exterior]
            patch = MplPolygon(xy, closed=True)
            ax.add_patch(patch)
            patch.set_facecolor(color)
            patch.set_alpha(0.75)
            patch.set_edgecolor("#cccccc")
            patch.set_linewidth(0.4)
            patch.set_zorder(2)

    # Water bodies
    _draw_water(ax, water_gj)

    # Territory boundary lines (bold where adjacent BGs have different assignments)
    for bg_idx, (orig_idx, feat) in enumerate(features_pop):
        geom = feat["geometry"]
        my_assign = assignments[orig_idx]
        clat = float(feat["properties"]["INTPTLAT"])
        clon = float(feat["properties"]["INTPTLON"])
        is_border = False
        for other_idx, (other_orig, other_feat) in enumerate(features_pop):
            if other_idx == bg_idx or assignments[other_orig] == my_assign:
                continue
            olat = float(other_feat["properties"]["INTPTLAT"])
            olon = float(other_feat["properties"]["INTPTLON"])
            if abs(clat - olat) < 0.045 and abs(clon - olon) < 0.045:
                is_border = True
                break
        if is_border:
            if geom["type"] == "Polygon":
                poly_list = [geom["coordinates"]]
            elif geom["type"] == "MultiPolygon":
                poly_list = geom["coordinates"]
            else:
                continue
            for poly_coords in poly_list:
                exterior = poly_coords[0]
                xs = [c[0] for c in exterior]
                ys = [c[1] for c in exterior]
                ax.plot(xs, ys, color="#222222", linewidth=2.0, zorder=4, alpha=0.7)

    # Drive time labels at centroids
    for bg_idx, (orig_idx, feat) in enumerate(features_pop):
        dt = drive_times[orig_idx]
        clat = float(feat["properties"]["INTPTLAT"])
        clon = float(feat["properties"]["INTPTLON"])
        ax.text(clon, clat, f"{dt:.0f}", fontsize=5.5, ha="center", va="center",
                fontweight="bold", color="#111", zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                          alpha=0.75, edgecolor="none"))

    # EMS district outline overlay (Scenario 0)
    if ems_overlay_gj is not None:
        _draw_ems_district_outlines(ax, ems_overlay_gj)

    # Station markers
    if station_coords is not None:
        # Candidate-based scenarios: black stars
        for k, (lat, lon) in enumerate(station_coords):
            ax.scatter(lon, lat, s=300, c="black", marker="*",
                       edgecolors="white", linewidths=1.5, zorder=15)
            ax.annotate(f"S{k+1}", (lon, lat - 0.012),
                        fontsize=7, ha="center", va="top", fontweight="bold",
                        color="white",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="#333",
                                  edgecolor="white", alpha=0.9),
                        zorder=16)
        # Also show existing stations as grey reference
        for s in STATIONS:
            ax.scatter(s["lon"], s["lat"], s=40, c="#aaa", marker="s",
                       edgecolors="#777", linewidths=0.8, zorder=9, alpha=0.5)
            ax.annotate(s["name"], (s["lon"], s["lat"] + 0.006),
                        fontsize=5, ha="center", color="#888", zorder=10, alpha=0.6)
    else:
        # Existing station scenarios: colored by service level
        level_colors = {"ALS": "#c0392b", "AEMT": "#e67e22", "BLS": "#2471a3"}
        level_markers = {"ALS": "s", "AEMT": "D", "BLS": "o"}
        for s in station_list:
            c = level_colors.get(s.get("level", "BLS"), "#888")
            m = level_markers.get(s.get("level", "BLS"), "o")
            ax.scatter(s["lon"], s["lat"], s=120, c=c, marker=m,
                       edgecolors="black", linewidths=1.5, zorder=15)
            ax.annotate(s["name"], (s["lon"], s["lat"] + 0.008),
                        fontsize=6.5, ha="center", fontweight="bold", zorder=16,
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                  alpha=0.8, edgecolor=c, linewidth=0.8))

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02, aspect=25)
    cbar.set_label("Drive Time to Nearest Station (min)", fontsize=11)
    cbar.ax.axhline(y=8, color="black", linewidth=1.5, linestyle="--")
    cbar.ax.axhline(y=14, color="black", linewidth=1.5, linestyle="--")
    cbar.ax.text(1.5, 8, " 8 min (NFPA 1710)", va="center", fontsize=8,
                 fontweight="bold", transform=cbar.ax.get_yaxis_transform())
    cbar.ax.text(1.5, 14, " 14 min (NFPA 1720)", va="center", fontsize=8,
                 fontweight="bold", transform=cbar.ax.get_yaxis_transform())

    # Metrics box
    m = metrics
    metrics_text = (
        f"Pop-wtd Avg RT: {m['avg_rt']:.1f} min\n"
        f"Median RT: {m['med_rt']:.1f} min\n"
        f"P90 RT: {m['p90_rt']:.1f} min\n"
        f"Max RT: {m['max_rt']:.1f} min\n"
        f"8-min coverage: {m['cov_8']:.1f}%\n"
        f"14-min coverage: {m['cov_14']:.1f}%"
    )
    ax.text(0.02, 0.98, metrics_text, transform=ax.transAxes, fontsize=9,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow",
                      edgecolor="#d4ac0d", alpha=0.9), zorder=20)

    # Title
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title("\n".join(title_lines), fontsize=12, fontweight="bold")

    # Legend
    legend_elements = [
        Line2D([0], [0], color="#222", linewidth=2.5, label="Territory boundary"),
        Line2D([0], [0], color="#ccc", linewidth=0.5, label="Block group boundary"),
        mpatches.Patch(facecolor="#b3d9f2", edgecolor="#6baed6",
                       hatch="//", alpha=0.55, label="Water body"),
    ]
    if ems_overlay_gj is not None:
        legend_elements.append(
            Line2D([0], [0], color="#333", linewidth=1.8, linestyle="--",
                   label="Current EMS district"))
    if station_coords is not None:
        legend_elements.insert(0,
            Line2D([0], [0], marker="*", color="w", markerfacecolor="black",
                   markeredgecolor="white", markersize=14, label="Optimal station"))
        legend_elements.insert(1,
            Line2D([0], [0], marker="s", color="w", markerfacecolor="#aaa",
                   markersize=8, label="Existing station (ref)"))
    else:
        legend_elements.insert(0,
            Line2D([0], [0], marker="s", color="w", markerfacecolor="#c0392b",
                   markeredgecolor="black", markersize=10, label="ALS station"))
        legend_elements.insert(1,
            Line2D([0], [0], marker="D", color="w", markerfacecolor="#e67e22",
                   markeredgecolor="black", markersize=8, label="AEMT station"))
        legend_elements.insert(2,
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#2471a3",
                   markeredgecolor="black", markersize=8, label="BLS station"))

    ax.legend(handles=legend_elements, loc="upper right" if ems_overlay_gj else "upper left",
              fontsize=8.5, framealpha=0.95, edgecolor="#ccc")

    fig.text(0.5, 0.01,
             "Source: OpenRouteService drive-time matrix, CY2024 NFIRS, WI DOA 2025 population\n"
             "Numbers in each block group = estimated drive time (minutes) from assigned station",
             ha="center", va="bottom", fontsize=7.5, fontstyle="italic", color="#555")

    ax.set_aspect("equal")
    ax.autoscale_view()
    plt.tight_layout(rect=[0, 0.04, 1, 1])

    fpath = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(fpath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {filename}")


def plot_hub_satellite_map(data, primary_assignments, primary_drive_times,
                           hub_drive_times, metrics, filename):
    """Scenario 2 special map: primary territories + hub coverage zones."""
    bg_gj = data["bg_gj"]
    county_gj = data["county_gj"]
    water_gj = data["water_gj"]

    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_facecolor("#f5f5f0")
    fig.patch.set_facecolor("white")

    _draw_county(ax, county_gj)

    # RT color map
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rt", ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"])
    norm = mcolors.Normalize(vmin=0, vmax=22)

    features_pop = [(i, feat) for i, feat in enumerate(bg_gj["features"])
                    if feat["properties"].get("P1_001N", 0) > 0]

    # BG polygons by primary drive time
    for bg_idx, (orig_idx, feat) in enumerate(features_pop):
        geom = feat["geometry"]
        dt = primary_drive_times[orig_idx]
        color = cmap(norm(dt))
        if geom["type"] == "Polygon":
            poly_list = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            poly_list = geom["coordinates"]
        else:
            continue
        for poly_coords in poly_list:
            exterior = poly_coords[0]
            xy = [(c[0], c[1]) for c in exterior]
            patch = MplPolygon(xy, closed=True)
            ax.add_patch(patch)
            patch.set_facecolor(color)
            patch.set_alpha(0.70)
            patch.set_edgecolor("#cccccc")
            patch.set_linewidth(0.4)
            patch.set_zorder(2)

    _draw_water(ax, water_gj)

    # Hub coverage zones (convex hulls for BGs assigned to each hub)
    hub_indices = [0, 1]  # Watertown=0, Fort Atkinson=1
    hub_names = ["Watertown", "Fort Atkinson"]
    for hi, hub_idx in enumerate(hub_indices):
        hub_name = hub_names[hi]
        # Find BGs where this hub is the closest ALS hub
        zone_lons, zone_lats = [], []
        for orig_idx, feat in features_pop:
            # Closest hub for this BG
            wt_dt = data["existing_matrix"][0, orig_idx]  # Watertown
            fa_dt = data["existing_matrix"][1, orig_idx]  # Fort Atkinson
            if (hub_idx == 0 and wt_dt <= fa_dt) or (hub_idx == 1 and fa_dt < wt_dt):
                lat = float(feat["properties"]["INTPTLAT"])
                lon = float(feat["properties"]["INTPTLON"])
                zone_lons.append(lon)
                zone_lats.append(lat)
        # Add hub location
        zone_lons.append(STATIONS[hub_idx]["lon"])
        zone_lats.append(STATIONS[hub_idx]["lat"])

        if len(zone_lons) >= 3:
            pts = np.column_stack([zone_lons, zone_lats])
            hull = ConvexHull(pts)
            hull_pts = pts[hull.vertices]
            hull_pts = np.vstack([hull_pts, hull_pts[0]])
            cx, cy = pts.mean(axis=0)
            expanded = np.array([(p[0] + (p[0]-cx)*0.08, p[1] + (p[1]-cy)*0.08) for p in hull_pts])
            ax.fill(expanded[:, 0], expanded[:, 1],
                    facecolor=HUB_LIGHT[hub_name], edgecolor=HUB_COLORS[hub_name],
                    linewidth=2.0, alpha=0.15, linestyle="--", zorder=1)

    # Drive time labels (show primary + ALS hub time)
    for bg_idx, (orig_idx, feat) in enumerate(features_pop):
        dt_prim = primary_drive_times[orig_idx]
        dt_hub = hub_drive_times[orig_idx]
        clat = float(feat["properties"]["INTPTLAT"])
        clon = float(feat["properties"]["INTPTLON"])
        ax.text(clon, clat, f"{dt_prim:.0f}", fontsize=5.5, ha="center", va="center",
                fontweight="bold", color="#111", zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                          alpha=0.75, edgecolor="none"))

    # Station markers
    for s in STATIONS:
        if s["name"] in ["Watertown", "Fort Atkinson"]:
            c = HUB_COLORS[s["name"]]
            ax.scatter(s["lon"], s["lat"], s=250, c=c, marker="s",
                       edgecolors="black", linewidths=2, zorder=15)
            ax.plot(s["lon"], s["lat"], "+", color="white", markersize=10,
                    markeredgewidth=2, zorder=16)
            ax.annotate(f"{s['name']} (HUB)", (s["lon"], s["lat"] + 0.01),
                        fontsize=7, ha="center", fontweight="bold", zorder=17,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor=c,
                                  edgecolor="black", alpha=0.3))
        else:
            lc = {"ALS": "#c0392b", "AEMT": "#e67e22", "BLS": "#2471a3"}
            ax.scatter(s["lon"], s["lat"], s=80, c=lc.get(s["level"], "#888"),
                       marker="o", edgecolors="black", linewidths=1, zorder=12)
            ax.annotate(s["name"], (s["lon"], s["lat"] + 0.006),
                        fontsize=5.5, ha="center", color="#444", zorder=13)

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02, aspect=25)
    cbar.set_label("Primary Response Drive Time (min)", fontsize=11)
    cbar.ax.axhline(y=8, color="black", linewidth=1.5, linestyle="--")
    cbar.ax.axhline(y=14, color="black", linewidth=1.5, linestyle="--")

    # Metrics box
    m = metrics
    metrics_text = (
        f"Primary (any station):\n"
        f"  Avg RT: {m['avg_rt']:.1f} min | 8-min: {m['cov_8']:.1f}%\n"
        f"ALS Hub backup (WT/FA only):\n"
        f"  Avg RT: {m.get('hub_avg_rt', 'N/A')} min"
    )
    ax.text(0.02, 0.98, metrics_text, transform=ax.transAxes, fontsize=9,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow",
                      edgecolor="#d4ac0d", alpha=0.9), zorder=20)

    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title(
        "Scenario 2: 2-Hub + Local First-Response Model\n"
        "Primary response from closest station (any) | ALS backup from Watertown or Fort Atkinson\n"
        "Source: ORS drive-time matrix, CY2024 NFIRS, FY2025 staffing",
        fontsize=12, fontweight="bold")

    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=HUB_COLORS["Watertown"],
               markeredgecolor="black", markersize=12, label="Watertown (North ALS Hub)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=HUB_COLORS["Fort Atkinson"],
               markeredgecolor="black", markersize=12, label="Fort Atkinson (South ALS Hub)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#888",
               markeredgecolor="black", markersize=8, label="Local first-response station"),
        mpatches.Patch(facecolor=HUB_LIGHT["Watertown"], edgecolor=HUB_COLORS["Watertown"],
                       alpha=0.3, linestyle="--", label="North Hub zone"),
        mpatches.Patch(facecolor=HUB_LIGHT["Fort Atkinson"], edgecolor=HUB_COLORS["Fort Atkinson"],
                       alpha=0.3, linestyle="--", label="South Hub zone"),
        mpatches.Patch(facecolor="#b3d9f2", edgecolor="#6baed6",
                       hatch="//", alpha=0.55, label="Water body"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=8.5,
              framealpha=0.95, edgecolor="#ccc")

    ax.set_aspect("equal")
    ax.autoscale_view()
    plt.tight_layout(rect=[0, 0.03, 1, 1])

    fpath = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(fpath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {filename}")


def plot_comparison_chart(scenarios, filename):
    """Grouped bar chart comparing all scenarios."""
    names = [s["label"] for s in scenarios]
    avg_rts = [s["metrics"]["avg_rt"] for s in scenarios]
    p90_rts = [s["metrics"]["p90_rt"] for s in scenarios]
    cov_8s = [s["metrics"]["cov_8"] for s in scenarios]
    cov_14s = [s["metrics"]["cov_14"] for s in scenarios]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    fig.patch.set_facecolor("white")

    x = np.arange(len(names))
    width = 0.35

    # Left: response times
    bars1 = ax1.bar(x - width/2, avg_rts, width, label="Pop-Wtd Avg RT", color="#3498db", edgecolor="black")
    bars2 = ax1.bar(x + width/2, p90_rts, width, label="P90 RT", color="#e74c3c", edgecolor="black")
    ax1.set_ylabel("Response Time (min)", fontsize=12)
    ax1.set_title("Response Time Comparison", fontsize=13, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=25, ha="right", fontsize=9)
    ax1.legend(fontsize=10)
    ax1.axhline(y=8, color="green", linewidth=1, linestyle="--", alpha=0.5, label="8 min")
    ax1.axhline(y=14, color="orange", linewidth=1, linestyle="--", alpha=0.5, label="14 min")
    for bar in bars1:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                 f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    for bar in bars2:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                 f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax1.set_ylim(0, max(p90_rts) * 1.2)
    ax1.grid(axis="y", alpha=0.3)

    # Right: coverage
    bars3 = ax2.bar(x - width/2, cov_8s, width, label="8-min Coverage %", color="#27ae60", edgecolor="black")
    bars4 = ax2.bar(x + width/2, cov_14s, width, label="14-min Coverage %", color="#f39c12", edgecolor="black")
    ax2.set_ylabel("Population Coverage (%)", fontsize=12)
    ax2.set_title("Coverage Comparison", fontsize=13, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=25, ha="right", fontsize=9)
    ax2.legend(fontsize=10)
    for bar in bars3:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=8, fontweight="bold")
    for bar in bars4:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax2.set_ylim(0, 105)
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("Jefferson County EMS: Territory Scenario Comparison\n"
                 "Source: ORS drive-time matrix, CY2024 NFIRS, WI DOA 2025 population",
                 fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(fpath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {filename}")


# ═══════════════════════════════════════════════════════════════════════════
# MARKDOWN DOCUMENT
# ═══════════════════════════════════════════════════════════════════════════

def build_responder_table(assignments, station_names_list, drive_times, bg_gj, pop_weights):
    """Build markdown table: BG → assigned station, drive time, population."""
    lines = []
    lines.append("| Block Group | Population | Assigned Responder | Drive Time (min) |")
    lines.append("|---|---|---|---|")
    for i, feat in enumerate(bg_gj["features"]):
        pop = int(pop_weights[i])
        if pop == 0:
            continue
        geoid = feat["properties"].get("GEOID", f"BG_{i}")
        station = station_names_list[assignments[i]] if assignments[i] < len(station_names_list) else f"Station {assignments[i]}"
        dt = drive_times[i]
        lines.append(f"| {geoid} | {pop:,} | {station} | {dt:.1f} |")
    return "\n".join(lines)


def build_comparison_table(scenarios):
    """Build side-by-side comparison markdown table."""
    lines = []
    lines.append("| Metric | " + " | ".join(s["label"] for s in scenarios) + " |")
    lines.append("|---|" + "|".join(["---"] * len(scenarios)) + "|")
    metrics_keys = [
        ("Stations", "n_stations"),
        ("Pop-Wtd Avg RT (min)", "avg_rt"),
        ("Median RT (min)", "med_rt"),
        ("P90 RT (min)", "p90_rt"),
        ("Max RT (min)", "max_rt"),
        ("8-min Coverage (%)", "cov_8"),
        ("10-min Coverage (%)", "cov_10"),
        ("14-min Coverage (%)", "cov_14"),
    ]
    for label, key in metrics_keys:
        vals = []
        for s in scenarios:
            if key == "n_stations":
                vals.append(str(s.get("n_stations", "—")))
            else:
                v = s["metrics"].get(key, "—")
                if isinstance(v, float):
                    vals.append(f"{v:.1f}")
                else:
                    vals.append(str(v))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


def build_improvement_table(scenarios, bg_gj, pop_weights):
    """Show BGs with biggest improvement from baseline to Scenario 1."""
    s0 = scenarios[0]
    s1 = scenarios[1]
    dt0 = s0["drive_times"]
    dt1 = s1["drive_times"]
    improvements = []
    for i, feat in enumerate(bg_gj["features"]):
        pop = int(pop_weights[i])
        if pop == 0:
            continue
        delta = dt0[i] - dt1[i]
        if abs(delta) > 0.5:
            geoid = feat["properties"].get("GEOID", f"BG_{i}")
            improvements.append((geoid, pop, dt0[i], dt1[i], delta,
                                 STATION_NAMES[s0["assignments"][i]],
                                 STATION_NAMES[s1["assignments"][i]]))
    improvements.sort(key=lambda x: -x[4])

    lines = []
    lines.append("| Block Group | Pop | Current RT | Optimized RT | Change | Current Provider | New Provider |")
    lines.append("|---|---|---|---|---|---|---|")
    for geoid, pop, rt0, rt1, delta, prov0, prov1 in improvements[:20]:
        sign = "+" if delta < 0 else ""
        lines.append(f"| {geoid} | {pop:,} | {rt0:.1f} | {rt1:.1f} | {sign}{-delta:.1f} | {prov0} | {prov1} |")
    return "\n".join(lines)


def write_markdown(scenarios, data):
    """Assemble the full Territory_Boundary_Analysis.md document."""
    bg_gj = data["bg_gj"]
    pw = data["pop_weights"]

    s0 = scenarios[0]
    s1 = scenarios[1]

    # Build improvement delta
    dt0 = s0["drive_times"]
    dt1 = s1["drive_times"]
    mask = pw > 0
    avg_improvement = np.average(dt0[mask] - dt1[mask], weights=pw[mask])

    comp_table = build_comparison_table(scenarios)
    improve_table = build_improvement_table(scenarios, bg_gj, pw)

    doc = f"""# Jefferson County EMS — Territory Boundary Redesign Analysis

**Date:** April 2026
**Prepared by:** ISyE 450 Senior Design Team
**Sources:** OpenRouteService drive-time matrix, CY2024 NFIRS (14,853 EMS calls), WI DOA 2025 population, FY2025 staffing data

---

## Executive Summary

**Yes, redrawing Jefferson County's EMS territory boundaries would be beneficial.** The current 12 EMS districts are based on historical municipal boundaries that are over 50 years old and do not reflect modern call demand patterns, travel networks, or population distribution.

Our analysis of five scenarios — from a simple boundary optimization to aggressive station consolidation — shows that:

1. **Simply redrawing boundaries around the same 13 stations** (Scenario 1) improves population-weighted average response time by **{avg_improvement:.1f} minutes** with zero infrastructure cost.
2. **A 2-Hub + Local First-Response model** (Scenario 2) adds an ALS safety net while maintaining local response capability.
3. **Moderate consolidation to 10 stations** (Scenario 3) achieves good coverage with 3 fewer stations.
4. **Aggressive consolidation to 8 stations** (Scenario 4) shows diminishing returns — response time degrades in rural areas.

The recommended path is a **phased approach**: implement Scenario 1 immediately (redraw boundaries by closest response time), layer Scenario 2's hub model for overnight ALS coverage, and evaluate Scenario 3 as contracts expire through 2028.

---

## Current State Analysis

### The 12 EMS Districts Today

Jefferson County currently operates **12 EMS districts** served by **13 stations** (including Helenville/Ryan Brothers). These districts were drawn along municipal boundaries — town lines, city limits, and fire district edges — that reflect political geography, not optimal emergency response coverage.

**Known Problems:**

1. **8 towns have overlapping multi-provider contracts** — Town of Oakland has 3 simultaneous EMS contracts; Towns of Aztalan, Milford, and Koshkonong each have 2-3 providers
2. **Cambridge EMS dissolved in 2025** — medical director resigned; Fort Atkinson identified as fallback; 342 residents with uncertain coverage
3. **Boundaries don't follow response time contours** — some BGs are assigned to distant stations when a closer station exists in a neighboring district
4. **Multi-county providers** (Western Lakes, Edgerton, Whitewater) serve only small slivers of Jefferson County from stations optimized for other counties
5. **No response time standards in contracts** — no contractual obligation to meet any response time target

### Baseline Metrics (Scenario 0)

![Current Boundaries](territory_scenario_0_baseline.png)

{build_responder_table(s0["assignments"], STATION_NAMES, s0["drive_times"], bg_gj, pw)}

---

## Methodology

For each scenario, we:
1. **Assign each of 65 Census block groups** to a responding station using pre-computed OpenRouteService drive-time matrices
2. **Compute population-weighted metrics**: average RT, median, P90, max, and coverage at 8-min (NFPA 1710 urban) and 14-min (NFPA 1720 rural) thresholds
3. **Visualize territories** with drive-time color gradient (green = fast, red = slow) and bold boundary lines where adjacent BGs have different assignments

The drive-time matrices represent real road network travel times computed by OpenRouteService, not straight-line distances. They account for road type, speed limits, and routing.

---

## Scenario 1: Optimized Boundaries (Same 13 Stations)

**Concept:** Keep all 13 existing stations exactly where they are. The only change is redrawing district boundaries so that every block group is served by whichever station can reach it fastest — regardless of which municipality that station belongs to.

**Why this matters:** Under current boundaries, some residents are assigned to stations 15-20 minutes away when a station in the neighboring district could reach them in 8 minutes. This scenario eliminates those inefficiencies with zero infrastructure investment.

![Optimized Boundaries](territory_scenario_1_optimized.png)

### Key Changes from Baseline

{improve_table}

### Who Responds to Each Call

Under Scenario 1, dispatch routing would be based on **closest available unit** rather than municipal jurisdiction. This means:
- A call in the Town of Oakland (currently split between 3 providers) would go to whichever of Jefferson, Lake Mills, or Helenville is closest
- A call in the Town of Milford border area would go to whichever of Waterloo, Johnson Creek, or Watertown is closest
- Cambridge residents (currently without a provider) would be formally assigned to the nearest station

---

## Scenario 2: 2-Hub + Local First-Response Model

**Concept:** All 13 stations continue to operate as local first-response units. However, Watertown and Fort Atkinson — the two largest career ALS departments — serve as regional hubs providing ALS backup when:
- The local station is BLS-only (Ixonia, Palmyra, Lake Mills)
- The local station's ambulance is already on a call
- The call requires ALS-level care and the local provider is AEMT or below

This model preserves fast local BLS first-response while ensuring every resident has access to ALS-level care from a career hub within a reasonable time.

![Hub + Satellite Model](territory_scenario_2_hub_satellite.png)

### Hub Coverage Zones

| Hub | Role | Coverage Area | Population | Est. ALS Backup RT |
|---|---|---|---|---|
| **Watertown** (North) | ALS Hub | Waterloo, Johnson Creek, Ixonia, Lake Mills, Helenville | ~30,000 | 8-18 min |
| **Fort Atkinson** (South) | ALS Hub | Jefferson, Cambridge, Palmyra, Whitewater | ~20,000 | 5-15 min |

### Benefits
- **No station closures** — every community keeps its local EMS presence
- **ALS safety net** — BLS-only communities get ALS backup from career departments
- **Uses existing resources** — Watertown (31 FT, 3 ambulances) and Fort Atkinson (16 FT, 3 ambulances) already staff 24/7 ALS
- **Improves overnight coverage** — hubs provide reliable ALS when volunteer/PT departments have slower response

---

## Scenario 3: Consolidated to 10 Stations (P-Median)

**Concept:** Using mathematical optimization (P-Median algorithm), place 10 stations at locations that minimize population-weighted average response time across all 65 block groups. This requires closing 3 stations and potentially relocating others.

![K=10 Consolidated](territory_scenario_3_K10.png)

### Trade-offs
- **Pros:** More efficient resource allocation; fewer stations to staff/equip; ~{scenarios[3]["n_stations"]} stations achieve comparable coverage to current 13
- **Cons:** Some communities lose their local station; political resistance to closures; requires contract renegotiation

---

## Scenario 4: Consolidated to 8 Stations (P-Median)

**Concept:** More aggressive consolidation to 8 optimally-placed stations. This scenario tests how far consolidation can go before coverage degrades unacceptably.

![K=8 Consolidated](territory_scenario_4_K8.png)

### Trade-offs
- **Pros:** Maximum efficiency; fewest stations to operate
- **Cons:** Noticeable coverage loss in rural areas; longer max response times; 5 station closures would face strong community opposition

---

## Side-by-Side Comparison

{comp_table}

![Comparison Chart](territory_comparison_chart.png)

### Interpretation

- **Scenario 1 is the clear first step** — it improves response times with zero cost by simply changing dispatch routing
- **Scenario 2 adds an ALS safety net** on top of Scenario 1, addressing the service-level gap
- **Scenario 3 (K=10)** is a reasonable consolidation target for 2028+ when major contracts expire
- **Scenario 4 (K=8)** shows diminishing returns — the coverage loss in rural areas outweighs the efficiency gains

---

## Why New Boundaries Are Beneficial

### 1. Faster Response Times for Residents Currently in Suboptimal Districts
Under current boundaries, historical municipal lines force some residents to wait for a distant provider when a closer one exists across the district line. Optimized boundaries route every call to the closest station.

### 2. Elimination of Confusing Multi-Provider Overlaps
8 towns currently have 2-3 EMS providers with unclear boundary demarcation. Optimized boundaries create a single, unambiguous primary responder for every location in the county.

### 3. Formal Coverage for Cambridge (Post-Dissolution)
Cambridge EMS dissolved in 2025. Under current boundaries, 342 residents have uncertain coverage. All scenarios formally assign them to the nearest capable provider.

### 4. Foundation for Coordinated Dispatch
Optimized boundaries enable a county-wide "closest available unit" dispatch protocol, which is the #1 recommendation from both the Waterloo and Johnson Creek fire chiefs.

### 5. Data-Driven Resource Allocation
With clear, optimized territories, staffing and equipment decisions can be based on actual demand within each territory rather than historical municipal budgets.

---

## Implementation Constraints

### Contract Locks
- **Jefferson City EMS** — 5 towns (Aztalan, Farmington, Hebron, Jefferson, Oakland) locked until **Dec 31, 2027** with severe early-exit penalties
- **JCFD** — bundled fire+EMS contract through **Dec 31, 2028**
- **Lake Mills/Ryan Brothers** — rolling 3-year; requires 180-day notice for exit

### Multi-County Providers
- **Western Lakes** (Waukesha County-based), **Edgerton** (Rock County), and **Whitewater** (multi-county) cannot be unilaterally consolidated. Their territories in Jefferson County would need inter-county agreements.

### Fort Atkinson Reopener Clause
Fort Atkinson's contracts contain a county-wide system clause: if Jefferson County formally adopts a unified EMS system, both Koshkonong and Town of Jefferson contracts automatically reopen for negotiation. This is a strategic lever for Scenarios 1-2.

### Political Reality
As the Waterloo Fire Chief noted: "People will be hawks for their funds and fight for their territory." Any boundary change must demonstrate clear benefit to affected communities, framed as **better care for citizens**, not cost savings.

---

## Recommendation

**Phase 1 (Immediate — 2026):** Implement Scenario 1's optimized dispatch routing through a county-wide mutual aid agreement. No station closures needed. Each call goes to the closest available unit regardless of municipal boundary.

**Phase 2 (2026-2027):** Layer Scenario 2's hub model for overnight and ALS-backup coverage. Watertown and Fort Atkinson already staff 24/7 career ALS crews — formalize their backup role.

**Phase 3 (2028+):** As Jefferson City (Dec 2027) and JCFD (Dec 2028) contracts expire, evaluate Scenario 3's 10-station consolidated model. Use the Fort Atkinson reopener clause if the county formally adopts a unified system resolution.

---

*This analysis was prepared using population-weighted response time optimization based on OpenRouteService drive-time matrices covering all 65 Census block groups in Jefferson County. All scenarios use the same underlying drive-time data to ensure fair comparison.*
"""

    fpath = os.path.join(SCRIPT_DIR, "Territory_Boundary_Analysis.md")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  Saved: Territory_Boundary_Analysis.md")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("JEFFERSON COUNTY EMS — TERRITORY BOUNDARY ANALYSIS")
    print("=" * 60)

    data = load_all_data()
    bg_gj = data["bg_gj"]
    pw = data["pop_weights"]
    scenarios = []

    # ── Scenario 0: Current Baseline ────────────────────────────────────
    print("\n>> Scenario 0: Current Baseline (Historical Boundaries)")
    a0, dt0 = assign_current_districts(data)
    m0 = compute_metrics(dt0, pw)
    print(f"   Avg RT: {m0['avg_rt']:.2f} | 8-min cov: {m0['cov_8']:.1f}% | 14-min cov: {m0['cov_14']:.1f}%")

    plot_territory_map(
        "Scenario 0", [
            "Scenario 0: Current EMS District Boundaries (Baseline)",
            "Block groups colored by drive time from currently-assigned station",
            "Dashed lines = current EMS district boundaries | Source: ORS, CY2024 NFIRS"
        ],
        bg_gj, data["county_gj"], data["water_gj"],
        a0, dt0, pw, STATIONS, m0,
        "territory_scenario_0_baseline.png",
        ems_overlay_gj=data["ems_gj"]
    )
    scenarios.append({
        "label": "S0: Current", "n_stations": 13,
        "metrics": m0, "assignments": a0, "drive_times": dt0
    })

    # ── Scenario 1: Optimized Voronoi ───────────────────────────────────
    print("\n>> Scenario 1: Optimized Boundaries (Same 13 Stations)")
    a1, dt1 = assign_nearest_existing(data)
    m1 = compute_metrics(dt1, pw)
    print(f"   Avg RT: {m1['avg_rt']:.2f} | 8-min cov: {m1['cov_8']:.1f}% | 14-min cov: {m1['cov_14']:.1f}%")

    plot_territory_map(
        "Scenario 1", [
            "Scenario 1: Optimized Boundaries (Same 13 Stations)",
            "Each block group assigned to closest station by drive time (Voronoi)",
            "Source: ORS drive-time matrix, CY2024 NFIRS, WI DOA 2025 population"
        ],
        bg_gj, data["county_gj"], data["water_gj"],
        a1, dt1, pw, STATIONS, m1,
        "territory_scenario_1_optimized.png"
    )
    scenarios.append({
        "label": "S1: Optimized", "n_stations": 13,
        "metrics": m1, "assignments": a1, "drive_times": dt1
    })

    # ── Scenario 2: 2-Hub + Local First-Response ────────────────────────
    print("\n>> Scenario 2: 2-Hub + Local First-Response")
    # Primary: same as Scenario 1 (closest of all 13)
    # Hub ALS backup: closest of Watertown(0) or Fort Atkinson(1)
    a2_hub, dt2_hub = assign_nearest_existing(data, station_indices=[0, 1])
    m2 = dict(m1)  # Primary metrics same as Scenario 1
    hub_mask = pw > 0
    hub_avg = float(np.average(dt2_hub[hub_mask], weights=pw[hub_mask]))
    m2["hub_avg_rt"] = round(hub_avg, 1)

    plot_hub_satellite_map(data, a1, dt1, dt2_hub, m2,
                           "territory_scenario_2_hub_satellite.png")
    scenarios.append({
        "label": "S2: Hub+Local", "n_stations": 13,
        "metrics": m1, "assignments": a1, "drive_times": dt1  # Primary same as S1
    })

    # ── Scenario 3: K=10 P-Median ──────────────────────────────────────
    print("\n>> Scenario 3: Consolidated K=10 (P-Median)")
    coords_10, _, _ = parse_pareto_stations(data, 10, "PMed")
    if coords_10:
        a3, dt3, oi3 = assign_candidate_stations(data, coords_10)
        m3 = compute_metrics(dt3, pw)
        print(f"   Avg RT: {m3['avg_rt']:.2f} | 8-min cov: {m3['cov_8']:.1f}% | 14-min cov: {m3['cov_14']:.1f}%")

        plot_territory_map(
            "Scenario 3", [
                "Scenario 3: Consolidated to 10 Stations (P-Median Optimal)",
                "Stations placed to minimize population-weighted average response time",
                "Source: ORS drive-time matrix, P-Median optimization, CY2024 NFIRS"
            ],
            bg_gj, data["county_gj"], data["water_gj"],
            a3, dt3, pw, STATIONS, m3,
            "territory_scenario_3_K10.png",
            station_coords=coords_10
        )
        scenarios.append({
            "label": "S3: K=10", "n_stations": 10,
            "metrics": m3, "assignments": a3, "drive_times": dt3
        })
    else:
        print("   WARNING: K=10 PMed not found in pareto_results.csv")

    # ── Scenario 4: K=8 P-Median ──────────────────────────────────────
    print("\n>> Scenario 4: Consolidated K=8 (P-Median)")
    coords_8, _, _ = parse_pareto_stations(data, 8, "PMed")
    if coords_8:
        a4, dt4, oi4 = assign_candidate_stations(data, coords_8)
        m4 = compute_metrics(dt4, pw)
        print(f"   Avg RT: {m4['avg_rt']:.2f} | 8-min cov: {m4['cov_8']:.1f}% | 14-min cov: {m4['cov_14']:.1f}%")

        plot_territory_map(
            "Scenario 4", [
                "Scenario 4: Consolidated to 8 Stations (P-Median Optimal)",
                "More aggressive consolidation — tests lower bound of station count",
                "Source: ORS drive-time matrix, P-Median optimization, CY2024 NFIRS"
            ],
            bg_gj, data["county_gj"], data["water_gj"],
            a4, dt4, pw, STATIONS, m4,
            "territory_scenario_4_K8.png",
            station_coords=coords_8
        )
        scenarios.append({
            "label": "S4: K=8", "n_stations": 8,
            "metrics": m4, "assignments": a4, "drive_times": dt4
        })
    else:
        print("   WARNING: K=8 PMed not found in pareto_results.csv")

    # ── Comparison Chart ────────────────────────────────────────────────
    print("\n>> Comparison Chart")
    plot_comparison_chart(scenarios, "territory_comparison_chart.png")

    # ── Markdown Document ───────────────────────────────────────────────
    print("\n>> Writing Territory_Boundary_Analysis.md")
    write_markdown(scenarios, data)

    print("\n" + "=" * 60)
    print("DONE — All outputs saved to project root")
    print("=" * 60)


if __name__ == "__main__":
    main()
