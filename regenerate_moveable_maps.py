"""
Regenerate K=7 and K=9 moveable facility maps using REAL ORS road-network
isochrone polygons — same technique as boundary_isochrone_map.png.

Fetches isochrone polygons from OpenRouteService for each optimal station,
caches them to disk, then renders transparent overlapping drive-time zones.
"""

import numpy as np
import json
import os
import time as _time
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "isochrone_cache")
WATER_GEOJSON = os.path.join(SCRIPT_DIR, "jefferson_water_bodies.geojson")

# Key lake label positions (manually placed for readability)
LAKE_LABELS = {
    "Lake Koshkonong": {"lat": 42.875, "lon": -88.915, "fontsize": 9},
    "Rock Lake":       {"lat": 43.085, "lon": -88.920, "fontsize": 7},
}

# ── Load .env for ORS API key ────────────────────────────────────────────
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


# ── Existing station data (reference overlay) ────────────────────────────
STATIONS = [
    {"name": "Watertown",     "lat": 43.1861, "lon": -88.7339, "level": "ALS",  "calls": 1947},
    {"name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397, "level": "ALS",  "calls": 1621},
    {"name": "Whitewater",    "lat": 42.8325, "lon": -88.7332, "level": "ALS",  "calls": 1448},
    {"name": "Edgerton",      "lat": 42.8403, "lon": -89.0629, "level": "ALS",  "calls": 2035},
    {"name": "Jefferson",     "lat": 43.0056, "lon": -88.8014, "level": "ALS",  "calls": 91},
    {"name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745, "level": "ALS",  "calls": 454},
    {"name": "Waterloo",      "lat": 43.1886, "lon": -88.9797, "level": "AEMT", "calls": 403},
    {"name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144, "level": "BLS",  "calls": None},
    {"name": "Ixonia",        "lat": 43.1446, "lon": -88.5970, "level": "BLS",  "calls": 260},
    {"name": "Palmyra",       "lat": 42.8794, "lon": -88.5855, "level": "BLS",  "calls": 105},
    {"name": "Cambridge",     "lat": 43.0049, "lon": -89.0224, "level": "ALS",  "calls": 64},
    {"name": "Helenville",    "lat": 43.0135, "lon": -88.6998, "level": "BLS",  "calls": None},
    {"name": "Western Lakes", "lat": 43.0110, "lon": -88.5877, "level": "ALS",  "calls": None},
]

# ── Optimal coordinates from Gurobi P-Median solve ──────────────────────
K7_COORDS = [
    (42.8925, -88.6017),
    (42.9525, -88.8417),
    (43.0125, -89.0217),
    (43.0725, -88.6617),
    (43.1925, -88.9617),
    (43.1925, -88.7817),
    (43.1925, -88.6017),
]

K9_COORDS = [
    (42.8925, -88.7817),
    (42.8925, -88.6017),
    (42.9525, -89.0817),
    (42.9525, -88.8417),
    (43.0125, -88.6017),
    (43.0725, -88.8417),
    (43.1925, -88.9617),
    (43.1925, -88.7217),
    (43.2525, -88.5417),
]

# K=11 P-Median optimal (from pareto_results.csv: avg_rt=8.31, max_rt=20.07)
K11_COORDS = [
    (42.8925, -88.7817),
    (42.8925, -88.6617),
    (42.8925, -88.6017),
    (42.9525, -88.8417),
    (43.0125, -88.9617),
    (43.0125, -88.7817),
    (43.0725, -88.8417),
    (43.0725, -88.6017),
    (43.1325, -88.5417),
    (43.1925, -88.9617),
    (43.1925, -88.7217),
]

# K=12 P-Median optimal (from pareto_results.csv: avg_rt=8.12, max_rt=17.85)
K12_COORDS = [
    (42.8925, -88.7817),
    (42.8925, -88.6617),
    (42.8925, -88.6017),
    (42.9525, -88.8417),
    (42.9525, -88.6017),
    (43.0125, -88.9617),
    (43.0125, -88.7817),
    (43.0725, -88.8417),
    (43.0725, -88.6017),
    (43.1325, -88.5417),
    (43.1925, -88.9617),
    (43.1925, -88.7217),
]


def _load_water():
    """Load Census TIGER water body polygons for Jefferson County."""
    if not os.path.exists(WATER_GEOJSON):
        return None
    with open(WATER_GEOJSON, "r") as f:
        return json.load(f)


def _draw_water(ax, water_gj):
    """Draw water bodies with light blue diagonal-hatch fill."""
    from matplotlib.patches import Polygon as MplPolygon
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

    # Label key lakes
    for label, pos in LAKE_LABELS.items():
        ax.annotate(
            label, (pos["lon"], pos["lat"]),
            fontsize=pos["fontsize"], fontstyle="italic", fontweight="bold",
            color="#2171b5", ha="center", va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      alpha=0.7, edgecolor="#6baed6", linewidth=0.5),
        )


# ── Fetch real ORS isochrone polygons ─────────────────────────────────────
def fetch_isochrones_for_stations(coords, label_prefix, thresholds_min=(8, 14, 20, 25, 30, 40)):
    """
    Fetch real road-network isochrone polygons from OpenRouteService
    for each station coordinate. Caches each station to disk.

    Returns: dict {station_index: {threshold_str: GeoJSON feature, ...}, ...}
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    url = "https://api.openrouteservice.org/v2/isochrones/driving-car"
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json",
    }
    thresholds_sec = [t * 60 for t in thresholds_min]

    results = {}
    for i, (lat, lon) in enumerate(coords):
        n_thresh = len(thresholds_min)
        cache_key = f"{label_prefix}_S{i+1}_{lat:.4f}_{lon:.4f}_{n_thresh}t"
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")

        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                cached = json.load(f)
            # Only use cache if it has all requested thresholds
            needed = {str(t) for t in thresholds_min}
            if needed.issubset(set(cached.keys())):
                results[i] = cached
                print(f"    Station #{i+1} ({lat:.4f}, {lon:.4f}): loaded from cache ({len(cached)} thresholds)")
                continue
            else:
                print(f"    Station #{i+1} ({lat:.4f}, {lon:.4f}): cache incomplete, re-fetching...")

        if not ORS_API_KEY:
            print(f"    Station #{i+1}: SKIP (no API key)")
            continue

        payload = {
            "locations": [[lon, lat]],
            "range": thresholds_sec,
            "range_type": "time",
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    iso_data = {}
                    for feat in data.get("features", []):
                        val_sec = feat["properties"]["value"]
                        val_min = str(int(val_sec / 60))
                        iso_data[val_min] = feat
                    results[i] = iso_data
                    with open(cache_file, "w") as f:
                        json.dump(iso_data, f)
                    print(f"    Station #{i+1} ({lat:.4f}, {lon:.4f}): OK ({len(iso_data)} thresholds)")
                    break
                elif resp.status_code == 429:
                    print(f"    Station #{i+1}: rate limited — waiting 60s (attempt {attempt+1})")
                    _time.sleep(60)
                else:
                    print(f"    Station #{i+1}: FAILED ({resp.status_code}: {resp.text[:100]})")
                    break
            except Exception as e:
                print(f"    Station #{i+1}: ERROR ({e})")
                break

        _time.sleep(3)  # ORS free tier rate limit

    return results


# ── Plot isochrone map (matching boundary_isochrone_map.png style) ────────
def plot_isochrone_map(coords, isochrones, K, avg_rt, max_rt, filename):
    """
    Render real ORS isochrone polygons exactly like boundary_isochrone_map.png:
    - Transparent overlapping polygons (green 20-min, orange 14-min, red 8-min)
    - White background
    - Existing stations as colored reference dots
    - Optimal stations as red stars
    """
    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    # Color scheme: core thresholds match reference, extended ones in grey tones
    threshold_colors = {
        "40": ("#b0b0b0", 0.06),  # light grey — extreme fringe
        "30": ("#9e9e9e", 0.08),  # grey
        "25": ("#8a8a8a", 0.10),  # darker grey
        "20": ("#2ecc71", 0.12),  # green, extended coverage
        "14": ("#f39c12", 0.18),  # orange, NFPA 1720 rural
        "8":  ("#e74c3c", 0.28),  # red, NFPA 1710 career
    }

    # Plot isochrone polygons — largest threshold first so smaller ones overlay
    for thresh in ["40", "30", "25", "20", "14", "8"]:
        color, alpha = threshold_colors[thresh]
        for station_idx, iso_data in isochrones.items():
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

    # ── Existing stations (reference) ─────────────────────────────────────
    level_colors = {"ALS": "#e74c3c", "AEMT": "#f39c12", "BLS": "#3498db"}

    for s in STATIONS:
        c = level_colors.get(s["level"], "#95a5a6")
        calls_str = f'{s["calls"]} calls' if s["calls"] else "? calls"
        edgecolor = "white"
        linewidth = 1.5

        ax.scatter(s["lon"], s["lat"], s=80, c=c,
                   edgecolors=edgecolor, linewidths=linewidth, zorder=10, alpha=0.6)

        ax.annotate(
            f'{s["name"]}\n({calls_str})',
            (s["lon"], s["lat"] + 0.008),
            fontsize=7, ha="center", va="bottom", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85),
            zorder=11,
        )

    # ── Optimal NEW stations (prominent red stars) ────────────────────────
    for i, (lat, lon) in enumerate(coords):
        ax.scatter(lon, lat, s=350, c="#e74c3c", marker="*",
                   edgecolors="#333333", linewidths=1.5, zorder=15)
        ax.annotate(
            f"Optimal #{i+1}",
            (lon, lat - 0.012),
            fontsize=8, ha="center", va="top", fontweight="bold",
            color="#c0392b",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#e74c3c", alpha=0.9, linewidth=1.5),
            zorder=16,
        )

    # ── Title & legend ────────────────────────────────────────────────────
    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title(
        f"Jefferson County EMS — Moveable Facility K={K}: Optimal Station Placement\n"
        f"Source: OpenRouteService isochrones (OSM road network) | P-Median optimization (Gurobi)\n"
        f"Red = 8 min | Orange = 14 min | Green = 20 min | Grey = 25 / 30 / 40 min\n"
        f"Avg response: {avg_rt:.1f} min | Max: {max_rt:.1f} min",
        fontsize=12, fontweight="bold",
    )

    legend_elements = [
        mpatches.Patch(color="#e74c3c", alpha=0.35, label="8-min drive (NFPA 1710)"),
        mpatches.Patch(color="#f39c12", alpha=0.25, label="14-min drive (NFPA 1720 rural)"),
        mpatches.Patch(color="#2ecc71", alpha=0.20, label="20-min drive (extended)"),
        mpatches.Patch(color="#8a8a8a", alpha=0.15, label="25-min drive"),
        mpatches.Patch(color="#9e9e9e", alpha=0.12, label="30-min drive"),
        mpatches.Patch(color="#b0b0b0", alpha=0.10, label="40-min drive"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#e74c3c",
               markeredgecolor="#333", markersize=15, label=f"Optimal K={K} location"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c",
               markersize=10, label="ALS station (existing)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db",
               markersize=10, label="BLS station (existing)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#f39c12",
               markersize=10, label="AEMT station (existing)"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9,
              framealpha=0.9, edgecolor="#cccccc")

    ax.set_aspect("equal")
    plt.tight_layout()
    out = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  [OK] Saved: {out}")


# ── Plot isochrone map WITH territory boundary overlay ────────────────────
def plot_isochrone_with_territories(coords, isochrones, K, avg_rt, max_rt, filename):
    """Isochrone map where each station's drive-time rings are CLIPPED to its
    service territory so colors never bleed across boundary lines."""
    from shapely.geometry import shape as shapely_shape
    from shapely.ops import unary_union

    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    threshold_colors = {
        "40": ("#b0b0b0", 0.06),
        "30": ("#9e9e9e", 0.08),
        "25": ("#8a8a8a", 0.10),
        "20": ("#2ecc71", 0.12),
        "14": ("#f39c12", 0.18),
        "8":  ("#e74c3c", 0.28),
    }

    # ── Build territory polygons (dissolved BGs per station) ──────────────
    bg_path = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")
    cand_bg_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                                  "cand_bg_drive_time_matrix.json")
    cand_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                               "candidate_drive_time_matrix.json")

    with open(bg_path, "r") as f:
        bg_gj = json.load(f)
    with open(cand_bg_cache, "r") as f:
        bg_tm = np.array(json.load(f)["matrix"])
    with open(cand_cache, "r") as f:
        cand_data = json.load(f)
    candidates = cand_data["candidates"]

    # Match optimal coords to candidate indices
    open_indices = []
    for lat, lon in coords:
        best_i, best_d = 0, 999
        for i, c in enumerate(candidates):
            d = abs(c["lat"] - lat) + abs(c["lon"] - lon)
            if d < best_d:
                best_d = d
                best_i = i
        open_indices.append(best_i)

    # Assign each BG to nearest station
    features_with_pop = []
    for i, feat in enumerate(bg_gj["features"]):
        if feat["properties"].get("P1_001N", 0) > 0:
            features_with_pop.append(feat)

    n_bg = len(features_with_pop)
    assignments = np.zeros(n_bg, dtype=int)
    for j in range(n_bg):
        best_k, best_t = 0, np.inf
        for k, ci in enumerate(open_indices):
            if bg_tm[ci, j] < best_t:
                best_t = bg_tm[ci, j]
                best_k = k
        assignments[j] = best_k

    # Dissolve BGs into territory shapes (with small buffer to close gaps)
    territory_shapes = {}
    for k in range(K):
        polys = []
        for bg_idx, feat in enumerate(features_with_pop):
            if assignments[bg_idx] != k:
                continue
            try:
                shp = shapely_shape(feat["geometry"]).buffer(0)
                polys.append(shp)
            except Exception:
                continue
        if polys:
            # Small buffer to merge touching BGs, then un-buffer
            merged = unary_union(polys).buffer(0.002).buffer(-0.001)
            territory_shapes[k] = merged

    # ── Helper to draw a shapely geometry ─────────────────────────────────
    def _fill_geom(geom, color, alpha):
        if geom.is_empty:
            return
        if geom.geom_type == "Polygon":
            xs, ys = geom.exterior.xy
            ax.fill(xs, ys, color=color, alpha=alpha, zorder=1)
        elif geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                xs, ys = poly.exterior.xy
                ax.fill(xs, ys, color=color, alpha=alpha, zorder=1)

    # ── Plot isochrone rings CLIPPED to each station's territory ──────────
    for thresh in ["40", "30", "25", "20", "14", "8"]:
        color, alpha = threshold_colors[thresh]
        for station_idx, iso_data in isochrones.items():
            if thresh not in iso_data:
                continue
            # Get the territory clip shape for this station
            clip_shape = territory_shapes.get(station_idx)

            feat = iso_data[thresh]
            iso_geom = shapely_shape(feat["geometry"]).buffer(0)

            if clip_shape is not None:
                # Clip isochrone to territory
                clipped = iso_geom.intersection(clip_shape)
                _fill_geom(clipped, color, alpha)
            else:
                # Fallback: draw unclipped (shouldn't happen normally)
                _fill_geom(iso_geom, color, alpha)

    # ── Draw territory boundary perimeters ────────────────────────────────
    for k, terr_shape in territory_shapes.items():
        def _draw_boundary(geom):
            if geom.geom_type == "Polygon":
                xs, ys = geom.exterior.xy
                ax.plot(xs, ys, color="#1a1a1a", linewidth=2.5, zorder=7,
                        alpha=0.85, solid_capstyle="round")
            elif geom.geom_type == "MultiPolygon":
                for poly in geom.geoms:
                    xs, ys = poly.exterior.xy
                    ax.plot(xs, ys, color="#1a1a1a", linewidth=2.5, zorder=7,
                            alpha=0.85, solid_capstyle="round")
        _draw_boundary(terr_shape)

    # ── Water bodies (hatched light blue) ──────────────────────────────────
    _draw_water(ax, _load_water())

    # ── Existing stations (reference) ─────────────────────────────────────
    level_colors = {"ALS": "#e74c3c", "AEMT": "#f39c12", "BLS": "#3498db"}
    for s in STATIONS:
        c = level_colors.get(s["level"], "#95a5a6")
        calls_str = f'{s["calls"]} calls' if s["calls"] else "? calls"
        ax.scatter(s["lon"], s["lat"], s=80, c=c,
                   edgecolors="white", linewidths=1.5, zorder=10, alpha=0.6)
        ax.annotate(
            f'{s["name"]}\n({calls_str})',
            (s["lon"], s["lat"] + 0.008),
            fontsize=7, ha="center", va="bottom", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85),
            zorder=11,
        )

    # ── Optimal stations ──────────────────────────────────────────────────
    for i, (lat, lon) in enumerate(coords):
        ax.scatter(lon, lat, s=350, c="#e74c3c", marker="*",
                   edgecolors="#333333", linewidths=1.5, zorder=15)
        ax.annotate(
            f"Optimal #{i+1}",
            (lon, lat - 0.012),
            fontsize=8, ha="center", va="top", fontweight="bold",
            color="#c0392b",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#e74c3c", alpha=0.9, linewidth=1.5),
            zorder=16,
        )

    # ── Title & legend ────────────────────────────────────────────────────
    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title(
        f"Jefferson County EMS — Moveable Facility K={K}: Optimal Placement + Service Territories\n"
        f"Source: ORS isochrones clipped to service territories | P-Median optimization\n"
        f"Red = 8 min | Orange = 14 min | Green = 20 min | Grey = 25 / 30 / 40 min\n"
        f"Avg response: {avg_rt:.1f} min | Max: {max_rt:.1f} min",
        fontsize=12, fontweight="bold",
    )

    legend_elements = [
        mpatches.Patch(color="#e74c3c", alpha=0.35, label="8-min drive (NFPA 1710)"),
        mpatches.Patch(color="#f39c12", alpha=0.25, label="14-min drive (NFPA 1720 rural)"),
        mpatches.Patch(color="#2ecc71", alpha=0.20, label="20-min drive (extended)"),
        mpatches.Patch(color="#8a8a8a", alpha=0.15, label="25 / 30 / 40-min drive"),
        Line2D([0], [0], color="#1a1a1a", linewidth=2.5,
               label="Service territory boundary"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#e74c3c",
               markeredgecolor="#333", markersize=15, label=f"Optimal K={K} location"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c",
               markersize=10, label="ALS station (existing)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db",
               markersize=10, label="BLS station (existing)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#f39c12",
               markersize=10, label="AEMT station (existing)"),
        mpatches.Patch(facecolor="#b3d9f2", edgecolor="#6baed6",
                       hatch="//", alpha=0.55, label="Water body"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9,
              framealpha=0.9, edgecolor="#cccccc")

    # ── Footnote about white gaps ──────────────────────────────────────
    fig.text(
        0.5, 0.01,
        "Note: White gaps within territories indicate areas with limited road-network access\n"
        "(sparse rural farmland, water bodies such as Rock Lake / Lake Koshkonong, or wetlands).\n"
        "These areas have no routable path within the displayed drive-time thresholds from the assigned station.",
        ha="center", va="bottom", fontsize=8, fontstyle="italic", color="#555555",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#f9f9f0", edgecolor="#cccccc", alpha=0.9),
    )

    ax.set_aspect("equal")
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    out = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  [OK] Saved: {out}")


# ── Compute avg/max response from cached drive-time matrix ───────────────
def compute_stats(coords, label_prefix):
    """Load candidate matrix and compute response stats for these stations."""
    cache = os.path.join(SCRIPT_DIR, "isochrone_cache", "candidate_drive_time_matrix.json")
    with open(cache, "r") as f:
        data = json.load(f)
    cand_matrix = np.array(data["matrix"])
    candidates = data["candidates"]
    demand_points = data["demand_points"]

    # Match coords to candidate indices
    indices = []
    for lat, lon in coords:
        best_i, best_d = 0, 999
        for i, c in enumerate(candidates):
            d = abs(c["lat"] - lat) + abs(c["lon"] - lon)
            if d < best_d:
                best_d = d
                best_i = i
        indices.append(best_i)

    # Min response per demand point
    n_demand = len(demand_points)
    resp = np.full(n_demand, np.inf)
    for j in range(n_demand):
        for i in indices:
            if cand_matrix[i, j] < resp[j]:
                resp[j] = cand_matrix[i, j]

    return np.mean(resp), np.max(resp)


# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # Allow selecting which K values to generate via CLI args
    # e.g.: python regenerate_moveable_maps.py 11 12
    requested = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [7, 9, 11, 12]

    ALL_CONFIGS = {
        7:  ("K7",  K7_COORDS),
        9:  ("K9",  K9_COORDS),
        11: ("K11", K11_COORDS),
        12: ("K12", K12_COORDS),
    }

    print("=" * 60)
    print("Fetching REAL ORS road-network isochrones for optimal stations")
    print(f"Generating maps for K = {requested}")
    print("=" * 60)

    for K in requested:
        if K not in ALL_CONFIGS:
            print(f"\n>> K={K}: no coordinates defined, skipping")
            continue
        label, coords = ALL_CONFIGS[K]
        print(f"\n>> K={K}: Fetching isochrones for {len(coords)} stations...")
        iso = fetch_isochrones_for_stations(coords, f"moveable_{label}")
        avg_rt, max_rt = compute_stats(coords, label)
        print(f"  Stats: avg={avg_rt:.1f} min, max={max_rt:.1f} min")

        print(f"\n  Generating K={K} detailed map...")
        plot_isochrone_map(coords, iso, K=K, avg_rt=avg_rt, max_rt=max_rt,
                           filename=f"facility_moveable_{label}_detailed.png")

        print(f"  Generating K={K} territory map...")
        plot_isochrone_with_territories(coords, iso, K=K, avg_rt=avg_rt, max_rt=max_rt,
                                         filename=f"facility_moveable_{label}_territories.png")

    print("\nDone!")
