"""
Generate a slide-ready version of boundary_isochrone_map.png
— Cleaner labels (dept name only, no call counts)
— Compact legend with clear grouping
— No axis labels (lat/lon removed)
— Higher DPI, presentation-sized figure
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import json
import os
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "isochrone_cache")

# ── Station data (same as boundary_optimization.py) ───────────────────────
departments = pd.DataFrame([
    {"Dept": "Watertown",     "EMS_Calls": 1947, "Pop": 23000, "Level": "ALS",  "Lat": 43.1861, "Lon": -88.7339, "Cross_County": True},
    {"Dept": "Fort Atkinson", "EMS_Calls": 1621, "Pop": 16300, "Level": "ALS",  "Lat": 42.9271, "Lon": -88.8397, "Cross_County": False},
    {"Dept": "Whitewater",    "EMS_Calls": 1448, "Pop":  4296, "Level": "ALS",  "Lat": 42.8325, "Lon": -88.7332, "Cross_County": True},
    {"Dept": "Edgerton",      "EMS_Calls": 2035, "Pop":  3763, "Level": "ALS",  "Lat": 42.8403, "Lon": -89.0629, "Cross_County": True},
    {"Dept": "Jefferson",     "EMS_Calls":   91, "Pop":  7800, "Level": "ALS",  "Lat": 43.0056, "Lon": -88.8014, "Cross_County": False},
    {"Dept": "Johnson Creek", "EMS_Calls":  454, "Pop":  3367, "Level": "ALS",  "Lat": 43.0753, "Lon": -88.7745, "Cross_County": False},
    {"Dept": "Waterloo",      "EMS_Calls":  403, "Pop":  4415, "Level": "AEMT", "Lat": 43.1886, "Lon": -88.9797, "Cross_County": True},
    {"Dept": "Lake Mills",    "EMS_Calls":  None,"Pop":  8700, "Level": "BLS",  "Lat": 43.0781, "Lon": -88.9144, "Cross_County": False},
    {"Dept": "Ixonia",        "EMS_Calls":  260, "Pop":  5078, "Level": "BLS",  "Lat": 43.1446, "Lon": -88.5970, "Cross_County": False},
    {"Dept": "Palmyra",       "EMS_Calls":  105, "Pop":  3341, "Level": "BLS",  "Lat": 42.8794, "Lon": -88.5855, "Cross_County": False},
    {"Dept": "Cambridge",     "EMS_Calls":   64, "Pop":  1650, "Level": "ALS",  "Lat": 43.0049, "Lon": -89.0224, "Cross_County": True},
    {"Dept": "Helenville",    "EMS_Calls":  None,"Pop":  1500, "Level": "BLS",  "Lat": 43.0135, "Lon": -88.6998, "Cross_County": False},
    {"Dept": "Western Lakes", "EMS_Calls":  None,"Pop":  2974, "Level": "ALS",  "Lat": 43.0110, "Lon": -88.5877, "Cross_County": True},
])


def load_cached_isochrones():
    """Load isochrones from the cache directory."""
    isochrones = {}
    if not os.path.exists(CACHE_DIR):
        # Fall back to the combined GeoJSON
        iso_file = os.path.join(SCRIPT_DIR, "boundary_isochrones.geojson")
        if os.path.exists(iso_file):
            with open(iso_file, "r") as f:
                geo = json.load(f)
            for feat in geo["features"]:
                dept = feat["properties"].get("department", "Unknown")
                thresh = str(feat["properties"].get("threshold_min", "?"))
                isochrones.setdefault(dept, {})[thresh] = feat
        return isochrones

    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".geojson"):
            continue
        parts = fname.replace(".geojson", "").split("_")
        # Format: DeptName_8min.geojson or DeptName_14min.geojson etc.
        thresh = parts[-1].replace("min", "")
        dept = " ".join(parts[:-1])
        fpath = os.path.join(CACHE_DIR, fname)
        with open(fpath, "r") as f:
            feat = json.load(f)
        isochrones.setdefault(dept, {})[thresh] = feat

    return isochrones


def generate_slide():
    # Try loading from combined GeoJSON first (more reliable)
    iso_file = os.path.join(SCRIPT_DIR, "boundary_isochrones.geojson")
    if os.path.exists(iso_file):
        with open(iso_file, "r") as f:
            geo = json.load(f)
        isochrones = {}
        for feat in geo["features"]:
            dept = feat["properties"].get("department", "Unknown")
            thresh = str(feat["properties"].get("threshold_min", "?"))
            isochrones.setdefault(dept, {})[thresh] = feat
    else:
        isochrones = load_cached_isochrones()

    if not isochrones:
        print("ERROR: No isochrone data found. Run boundary_optimization.py first.")
        return

    fig, ax = plt.subplots(figsize=(14, 12))

    # ── Isochrone polygons (largest first) ────────────────────────────────
    threshold_colors = {
        "8":  ("#e74c3c", 0.25),
        "14": ("#f39c12", 0.15),
        "20": ("#2ecc71", 0.10),
    }

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
                exterior = poly_coords[0]
                xs = [c[0] for c in exterior]
                ys = [c[1] for c in exterior]
                ax.fill(xs, ys, color=color, alpha=alpha, zorder=1)
                ax.plot(xs, ys, color=color, alpha=alpha + 0.1,
                        linewidth=0.3, zorder=2)

    # ── Station markers (simple dots, no labels) ────────────────────────
    for _, row in departments.iterrows():
        ax.scatter(row["Lon"], row["Lat"], s=60, c="#333333",
                   edgecolors="white", linewidths=1.5, zorder=10, alpha=0.9)

    # ── Clean up axes ─────────────────────────────────────────────────────
    ax.set_aspect("equal")
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.tick_params(left=False, bottom=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # ── Legend (simple, large text) ──────────────────────────────────────
    zone_elements = [
        mpatches.Patch(color="#e74c3c", alpha=0.35, label="8 min"),
        mpatches.Patch(color="#f39c12", alpha=0.25, label="14 min"),
        mpatches.Patch(color="#2ecc71", alpha=0.20, label="20 min"),
    ]

    leg = ax.legend(
        handles=zone_elements,
        loc="lower right",
        fontsize=14,
        framealpha=0.95,
        edgecolor="#cccccc",
        handlelength=2.5,
        handleheight=1.5,
    )

    plt.tight_layout()
    out = os.path.join(SCRIPT_DIR, "slide_isochrone_coverage.png")
    plt.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  [OK] Saved: {out}")


if __name__ == "__main__":
    generate_slide()
