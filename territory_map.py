"""
Jefferson County EMS — Territory / Service Area Maps
=====================================================
Assigns each Census block group to its nearest optimal station (by ORS
drive time), then renders color-coded territory polygons.

Generates: territory_K11.png, territory_K12.png
"""

import numpy as np
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.colorbar import ColorbarBase

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WATER_GEOJSON = os.path.join(SCRIPT_DIR, "jefferson_water_bodies.geojson")

# Key lake label positions (manually placed for readability)
LAKE_LABELS = {
    "Lake Koshkonong": {"lat": 42.875, "lon": -88.915, "fontsize": 9},
    "Rock Lake":       {"lat": 43.085, "lon": -88.920, "fontsize": 7},
}

# ── Station coordinates (P-Median optimal from pareto_results.csv) ────────
CONFIGS = {
    11: {
        "coords": [
            (42.8925, -88.7817), (42.8925, -88.6617), (42.8925, -88.6017),
            (42.9525, -88.8417), (43.0125, -88.9617), (43.0125, -88.7817),
            (43.0725, -88.8417), (43.0725, -88.6017), (43.1325, -88.5417),
            (43.1925, -88.9617), (43.1925, -88.7217),
        ],
        "avg_rt": 8.31, "max_rt": 20.07,
    },
    12: {
        "coords": [
            (42.8925, -88.7817), (42.8925, -88.6617), (42.8925, -88.6017),
            (42.9525, -88.8417), (42.9525, -88.6017), (43.0125, -88.9617),
            (43.0125, -88.7817), (43.0725, -88.8417), (43.0725, -88.6017),
            (43.1325, -88.5417), (43.1925, -88.9617), (43.1925, -88.7217),
        ],
        "avg_rt": 8.12, "max_rt": 17.85,
    },
}

# Existing stations for reference overlay
EXISTING_STATIONS = [
    {"name": "Watertown",     "lat": 43.1861, "lon": -88.7339, "level": "ALS"},
    {"name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397, "level": "ALS"},
    {"name": "Whitewater",    "lat": 42.8325, "lon": -88.7332, "level": "ALS"},
    {"name": "Edgerton",      "lat": 42.8403, "lon": -89.0629, "level": "ALS"},
    {"name": "Jefferson",     "lat": 43.0056, "lon": -88.8014, "level": "ALS"},
    {"name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745, "level": "ALS"},
    {"name": "Waterloo",      "lat": 43.1886, "lon": -88.9797, "level": "AEMT"},
    {"name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144, "level": "BLS"},
    {"name": "Ixonia",        "lat": 43.1446, "lon": -88.5970, "level": "BLS"},
    {"name": "Palmyra",       "lat": 42.8794, "lon": -88.5855, "level": "BLS"},
    {"name": "Cambridge",     "lat": 43.0049, "lon": -89.0224, "level": "ALS"},
    {"name": "Helenville",    "lat": 43.0135, "lon": -88.6998, "level": "BLS"},
    {"name": "Western Lakes", "lat": 43.0110, "lon": -88.5877, "level": "ALS"},
]

# 12 distinct colors for territories (qualitative palette)
TERRITORY_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
    "#1abc9c", "#e67e22", "#2980b9", "#27ae60", "#c0392b",
    "#8e44ad", "#16a085",
]


def load_water_bodies():
    """Load Census TIGER water body polygons for Jefferson County."""
    if not os.path.exists(WATER_GEOJSON):
        return None
    with open(WATER_GEOJSON, "r") as f:
        return json.load(f)


def _draw_water(ax, water_gj):
    """Draw water bodies with light blue diagonal-hatch fill."""
    if water_gj is None:
        return
    for feat in water_gj["features"]:
        geom = feat["geometry"]
        name = feat["properties"].get("FULLNAME") or ""
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


def load_data():
    """Load BG GeoJSON, candidate list, and candidate-to-BG drive time matrix."""
    bg_path = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")
    with open(bg_path, "r") as f:
        bg_gj = json.load(f)

    cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                         "cand_bg_drive_time_matrix.json")
    with open(cache, "r") as f:
        tm_data = json.load(f)
    tm = np.array(tm_data["matrix"])  # shape (60, 65)

    cand_cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                              "candidate_drive_time_matrix.json")
    with open(cand_cache, "r") as f:
        cand_data = json.load(f)
    candidates = cand_data["candidates"]

    return bg_gj, candidates, tm


def match_coords_to_candidates(coords, candidates):
    """Find candidate indices closest to each optimal station coordinate."""
    indices = []
    for lat, lon in coords:
        best_i, best_d = 0, 999
        for i, c in enumerate(candidates):
            d = abs(c["lat"] - lat) + abs(c["lon"] - lon)
            if d < best_d:
                best_d = d
                best_i = i
        indices.append(best_i)
    return indices


def assign_territories(tm, open_indices):
    """Assign each BG (column) to its nearest open station (row).
    Returns: array of shape (n_bg,) with station assignment index (0..K-1),
             array of shape (n_bg,) with drive time to nearest station."""
    n_bg = tm.shape[1]
    assignments = np.zeros(n_bg, dtype=int)
    drive_times = np.zeros(n_bg)

    for j in range(n_bg):
        best_k, best_t = 0, np.inf
        for k, i in enumerate(open_indices):
            if tm[i, j] < best_t:
                best_t = tm[i, j]
                best_k = k
        assignments[j] = best_k
        drive_times[j] = best_t

    return assignments, drive_times


def _get_neighbor_pairs(assignments, features_with_pop):
    """Find pairs of adjacent BGs that belong to different territories.
    Uses a simple centroid-distance heuristic (BGs within ~0.04 deg are neighbors)."""
    from itertools import combinations
    border_pairs = set()
    n = len(features_with_pop)
    for a in range(n):
        for b in range(a + 1, n):
            if assignments[a] == assignments[b]:
                continue
            fa = features_with_pop[a][1]["properties"]
            fb = features_with_pop[b][1]["properties"]
            la, lo_a = float(fa["INTPTLAT"]), float(fa["INTPTLON"])
            lb, lo_b = float(fb["INTPTLAT"]), float(fb["INTPTLON"])
            if abs(la - lb) < 0.045 and abs(lo_a - lo_b) < 0.045:
                border_pairs.add((a, b))
    return border_pairs


def plot_territory_map(K, coords, bg_gj, candidates, tm, avg_rt, max_rt):
    """Generate territory map: response-time gradient fill + territory boundary lines."""
    open_indices = match_coords_to_candidates(coords, candidates)
    assignments, drive_times = assign_territories(tm, open_indices)

    # Filter to BGs with pop > 0
    features_with_pop = []
    for i, feat in enumerate(bg_gj["features"]):
        pop = feat["properties"].get("P1_001N", 0)
        if pop > 0:
            features_with_pop.append((i, feat))

    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_facecolor("#f5f5f0")
    fig.patch.set_facecolor("white")

    # Response-time color map: green (fast) -> yellow -> orange -> red (slow)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rt", ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"])
    vmin, vmax = 0, 22  # minutes
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    # ── Pass 1: Draw BG polygons colored by drive time ────────────────────
    for bg_idx, (orig_idx, feat) in enumerate(features_with_pop):
        geom = feat["geometry"]
        dt = drive_times[bg_idx]
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

    # ── Pass 1.5: Draw water bodies (hatched light blue) ─────────────────
    water_gj = load_water_bodies()
    _draw_water(ax, water_gj)

    # ── Pass 2: Draw thick territory boundary lines ───────────────────────
    # For each BG edge that borders a different territory, draw it bold
    for bg_idx, (orig_idx, feat) in enumerate(features_with_pop):
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            poly_list = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            poly_list = geom["coordinates"]
        else:
            continue

        # Check if this BG borders a different territory
        my_territory = assignments[bg_idx]
        is_border = False
        clat = float(feat["properties"]["INTPTLAT"])
        clon = float(feat["properties"]["INTPTLON"])
        for other_idx, (_, other_feat) in enumerate(features_with_pop):
            if other_idx == bg_idx or assignments[other_idx] == my_territory:
                continue
            olat = float(other_feat["properties"]["INTPTLAT"])
            olon = float(other_feat["properties"]["INTPTLON"])
            if abs(clat - olat) < 0.045 and abs(clon - olon) < 0.045:
                is_border = True
                break

        if is_border:
            for poly_coords in poly_list:
                exterior = poly_coords[0]
                xs = [c[0] for c in exterior]
                ys = [c[1] for c in exterior]
                ax.plot(xs, ys, color="#222222", linewidth=2.0, zorder=4, alpha=0.7)

    # ── Drive time labels at centroids ────────────────────────────────────
    for bg_idx, (orig_idx, feat) in enumerate(features_with_pop):
        dt = drive_times[bg_idx]
        clat = float(feat["properties"]["INTPTLAT"])
        clon = float(feat["properties"]["INTPTLON"])
        pop = feat["properties"].get("P1_001N", 0)
        ax.text(clon, clat, f"{dt:.0f}", fontsize=6, ha="center", va="center",
                fontweight="bold", color="#111",  zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                          alpha=0.75, edgecolor="none"))

    # ── Existing stations (grey reference) ────────────────────────────────
    for s in EXISTING_STATIONS:
        ax.scatter(s["lon"], s["lat"], s=50, c="#aaaaaa", marker="s",
                   edgecolors="#777", linewidths=1, zorder=9, alpha=0.5)
        ax.annotate(s["name"], (s["lon"], s["lat"] + 0.007),
                    fontsize=5.5, ha="center", color="#888", zorder=10, alpha=0.7)

    # ── Optimal stations (black stars with territory number) ──────────────
    for k, (lat, lon) in enumerate(coords):
        ax.scatter(lon, lat, s=350, c="black", marker="*",
                   edgecolors="white", linewidths=1.5, zorder=15)
        ax.annotate(
            f"#{k+1}",
            (lon, lat - 0.012),
            fontsize=8, ha="center", va="top", fontweight="bold",
            color="white",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#333",
                      edgecolor="white", alpha=0.9, linewidth=1),
            zorder=16,
        )

    # ── Compute stats ─────────────────────────────────────────────────────
    pop_weights = []
    for i, feat in enumerate(bg_gj["features"]):
        pop = feat["properties"].get("P1_001N", 0)
        if pop > 0:
            pop_weights.append(pop)
    pop_weights = np.array(pop_weights, dtype=float)
    total_pop = pop_weights.sum()

    cov_8 = 100 * sum(pop_weights[j] for j in range(len(pop_weights))
                       if drive_times[j] <= 8) / total_pop
    cov_14 = 100 * sum(pop_weights[j] for j in range(len(pop_weights))
                        if drive_times[j] <= 14) / total_pop

    # ── Colorbar ──────────────────────────────────────────────────────────
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.02, aspect=25)
    cbar.set_label("Drive Time to Nearest Station (min)", fontsize=11)
    cbar.ax.axhline(y=8, color="black", linewidth=1.5, linestyle="--")
    cbar.ax.axhline(y=14, color="black", linewidth=1.5, linestyle="--")
    # Add threshold labels on colorbar
    cbar.ax.text(1.5, 8, " 8 min (NFPA 1710)", va="center", fontsize=8,
                 fontweight="bold", transform=cbar.ax.get_yaxis_transform())
    cbar.ax.text(1.5, 14, " 14 min (NFPA 1720)", va="center", fontsize=8,
                 fontweight="bold", transform=cbar.ax.get_yaxis_transform())

    # ── Title ─────────────────────────────────────────────────────────────
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title(
        f"Jefferson County EMS — K={K} P-Median: Service Territories & Response Time\n"
        f"Block groups colored by drive time | Bold lines = territory boundaries\n"
        f"Pop-wtd avg RT: {avg_rt:.1f} min | Max: {max_rt:.1f} min | "
        f"8-min cov: {cov_8:.0f}% | 14-min cov: {cov_14:.0f}%",
        fontsize=12, fontweight="bold",
    )

    # ── Legend ─────────────────────────────────────────────────────────────
    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="black",
               markeredgecolor="white", markersize=14, label="Optimal station"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#aaa",
               markersize=8, label="Existing station (ref)"),
        Line2D([0], [0], color="#222", linewidth=2.5,
               label="Territory boundary"),
        Line2D([0], [0], color="#ccc", linewidth=0.5,
               label="Block group boundary"),
        mpatches.Patch(facecolor="#b3d9f2", edgecolor="#6baed6",
                       hatch="//", alpha=0.55, label="Water body"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9,
              framealpha=0.95, edgecolor="#cccccc")

    # ── Footnote about white gaps ─────────────────────────────────────────
    fig.text(
        0.5, 0.01,
        "Note: White gaps within territories indicate areas with limited road-network access\n"
        "(sparse rural farmland, water bodies such as Rock Lake / Lake Koshkonong, or wetlands).\n"
        "These areas have no routable path within the displayed drive-time thresholds from the assigned station.",
        ha="center", va="bottom", fontsize=8, fontstyle="italic", color="#555555",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#f9f9f0", edgecolor="#cccccc", alpha=0.9),
    )

    ax.set_aspect("equal")
    ax.autoscale_view()
    plt.tight_layout(rect=[0, 0.05, 1, 1])

    fname = f"territory_K{K}.png"
    fpath = os.path.join(SCRIPT_DIR, fname)
    plt.savefig(fpath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {fname}")


if __name__ == "__main__":
    import sys

    requested = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [11, 12]

    print("=" * 60)
    print("JEFFERSON COUNTY EMS — SERVICE TERRITORY MAPS")
    print("=" * 60)

    bg_gj, candidates, tm = load_data()

    for K in requested:
        if K not in CONFIGS:
            print(f"\n  K={K}: not configured, skipping")
            continue
        cfg = CONFIGS[K]
        print(f"\n>> Generating K={K} territory map...")
        plot_territory_map(K, cfg["coords"], bg_gj, candidates, tm,
                           cfg["avg_rt"], cfg["max_rt"])

    print("\nDone!")
