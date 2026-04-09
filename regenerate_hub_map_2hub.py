"""
Regional Overnight ALS Hub Coverage Map — 2-Hub Version (No Edgerton)
Watertown (North) and Fort Atkinson (South) only.
"""

import os, json, warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy.spatial import ConvexHull
from shapely.geometry import shape, MultiPolygon, Polygon
import pandas as pd

warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Data ────────────────────────────────────────────────────────────────

DEPT_COORDS = {
    "Watertown": (43.1861, -88.7339),
    "Fort Atkinson": (42.9271, -88.8397),
    "Whitewater": (42.8325, -88.7332),
    "Edgerton": (42.8403, -89.0629),
    "Jefferson": (43.0056, -88.8014),
    "Johnson Creek": (43.0753, -88.7745),
    "Waterloo": (43.1886, -88.9797),
    "Ixonia": (43.1446, -88.5970),
    "Palmyra": (42.8794, -88.5855),
    "Cambridge": (43.0049, -89.0224),
    "Lake Mills": (43.0781, -88.9144),
    "Helenville": (43.0135, -88.6998),
    "Western Lakes": (43.0110, -88.5877),
}

AUTH_EMS = {
    "Cambridge": 87, "Fort Atkinson": 1616, "Ixonia": 289,
    "Jefferson": 1457, "Johnson Creek": 487, "Lake Mills": 518,
    "Palmyra": 32, "Waterloo": 520, "Watertown": 2012, "Whitewater": 64,
    "Edgerton": 2138, "Western Lakes": 5633,
}

STAFFING = {
    "Watertown":     {"FT": 31, "PT": 3,  "Service": "ALS", "24_7": True},
    "Fort Atkinson": {"FT": 16, "PT": 28, "Service": "ALS", "24_7": True},
    "Whitewater":    {"FT": 15, "PT": 17, "Service": "ALS", "24_7": True},
    "Edgerton":      {"FT": 24, "PT": 0,  "Service": "ALS", "24_7": True},
    "Jefferson":     {"FT": 6,  "PT": 20, "Service": "ALS", "24_7": True},
    "Johnson Creek": {"FT": 3,  "PT": 33, "Service": "ALS", "24_7": True},
    "Waterloo":      {"FT": 4,  "PT": 22, "Service": "AEMT","24_7": False},
    "Lake Mills":    {"FT": 4,  "PT": 20, "Service": "BLS", "24_7": False},
    "Ixonia":        {"FT": 2,  "PT": 45, "Service": "BLS", "24_7": False},
    "Cambridge":     {"FT": 0,  "PT": 31, "Service": "ALS", "24_7": False},
    "Palmyra":       {"FT": 0,  "PT": 20, "Service": "BLS", "24_7": False},
    "Western Lakes": {"FT": 0,  "PT": 0,  "Service": "ALS", "24_7": True},
}

AMBULANCE_COUNT = {
    "Watertown": 3, "Fort Atkinson": 3, "Whitewater": 2, "Edgerton": 2,
    "Jefferson": 5, "Johnson Creek": 2, "Waterloo": 2, "Lake Mills": 1,
    "Ixonia": 1, "Palmyra": 1, "Cambridge": 0, "Western Lakes": 0,
}

# 2 hubs only — Edgerton removed
HUB_CANDIDATES = ["Watertown", "Fort Atkinson"]
NEED_COVERAGE = ["Waterloo", "Ixonia", "Palmyra", "Cambridge", "Lake Mills",
                 "Johnson Creek", "Jefferson"]

# Load distance matrix
dist_path = os.path.join(SCRIPT_DIR, "boundary_distance_matrix.csv")
dist = pd.read_csv(dist_path, index_col=0)

def miles_to_minutes(miles):
    return miles * 1.3 / 35 * 60

# Compute assignments (closest of the 2 hubs)
assignments = {}
for dept in NEED_COVERAGE:
    best_hub, best_dist_val = None, 999
    for hub in HUB_CANDIDATES:
        d = dist.loc[dept, hub] if dept in dist.index and hub in dist.columns else 999
        if d < best_dist_val:
            best_dist_val = d
            best_hub = hub
    drive_min = miles_to_minutes(best_dist_val)
    assignments[dept] = {"hub": best_hub, "dist_mi": round(best_dist_val, 1),
                         "drive_min": round(drive_min, 1)}

# ── Load county boundary ────────────────────────────────────────────────

with open(os.path.join(SCRIPT_DIR, "jefferson_county.geojson")) as f:
    county_gj = json.load(f)

county_polys = []
for feat in county_gj.get("features", [county_gj]):
    geom = feat.get("geometry", feat)
    s = shape(geom)
    if isinstance(s, MultiPolygon):
        county_polys.extend(list(s.geoms))
    elif isinstance(s, Polygon):
        county_polys.append(s)

# ── Colors & labels ─────────────────────────────────────────────────────

HUB_COLORS = {
    "Watertown": "#c0392b",
    "Fort Atkinson": "#2471a3",
}
HUB_LIGHT = {
    "Watertown": "#f5b7b1",
    "Fort Atkinson": "#aed6f1",
}
HUB_LABELS = {
    "Watertown": "North Hub",
    "Fort Atkinson": "South Hub",
}

LABEL_OFFSETS = {
    "Watertown":     (18, 10),
    "Fort Atkinson": (18, -16),
    "Edgerton":      (-16, -14),
    "Whitewater":    (12, -14),
    "Jefferson":     (-60, 18),
    "Johnson Creek": (16, -18),
    "Waterloo":      (-22, 12),
    "Ixonia":        (16, 10),
    "Palmyra":       (16, -10),
    "Cambridge":     (-22, -14),
    "Lake Mills":    (-22, 14),
    "Helenville":    (12, -10),
    "Western Lakes": (16, -12),
}

# ── Build the map ───────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(18, 15))
fig.patch.set_facecolor("white")
ax.set_facecolor("#f8f9fa")

# County boundary
for poly in county_polys:
    x, y = poly.exterior.xy
    ax.fill(list(x), list(y), facecolor="#eef2f7", edgecolor="#7f8c8d",
            linewidth=2.0, alpha=0.5, zorder=1)

# Hub coverage zones (convex hulls)
for hub in HUB_CANDIDATES:
    hub_lat, hub_lon = DEPT_COORDS[hub]
    zone_points = [(hub_lon, hub_lat)]
    for dept, info in assignments.items():
        if info["hub"] == hub:
            lat, lon = DEPT_COORDS[dept]
            zone_points.append((lon, lat))
    if len(zone_points) >= 3:
        pts = np.array(zone_points)
        hull = ConvexHull(pts)
        hull_pts = pts[hull.vertices]
        hull_pts = np.vstack([hull_pts, hull_pts[0]])
        cx, cy = pts.mean(axis=0)
        expanded = []
        for p in hull_pts:
            dx, dy = p[0] - cx, p[1] - cy
            expanded.append((p[0] + dx * 0.15, p[1] + dy * 0.15))
        expanded = np.array(expanded)
        ax.fill(expanded[:, 0], expanded[:, 1],
                facecolor=HUB_LIGHT[hub], edgecolor=HUB_COLORS[hub],
                linewidth=1.5, alpha=0.15, linestyle="--", zorder=2)

# Connection lines with drive time labels
for dept, info in assignments.items():
    hub = info["hub"]
    lat, lon = DEPT_COORDS[dept]
    hub_lat, hub_lon = DEPT_COORDS[hub]
    color = HUB_COLORS[hub]
    ax.plot([lon, hub_lon], [lat, hub_lat], "-", color=color, alpha=0.35,
            linewidth=2.5, zorder=3)
    mid_lon = (lon + hub_lon) / 2
    mid_lat = (lat + hub_lat) / 2
    ax.annotate(f"{info['drive_min']:.0f} min",
                (mid_lon, mid_lat), fontsize=7, color=color,
                fontweight="bold", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                          edgecolor=color, alpha=0.85),
                zorder=8)

# Plot departments
for dept, (lat, lon) in DEPT_COORDS.items():
    calls = AUTH_EMS.get(dept, 0)
    night_calls = int(calls * 0.16)
    svc = STAFFING.get(dept, {}).get("Service", "?")
    ft = STAFFING.get(dept, {}).get("FT", 0)
    is_24_7 = STAFFING.get(dept, {}).get("24_7", False)
    amb = AMBULANCE_COUNT.get(dept, 0)
    offset = LABEL_OFFSETS.get(dept, (12, 5))

    if dept in HUB_CANDIDATES:
        color = HUB_COLORS[dept]
        ax.plot(lon, lat, "s", color=color, markersize=22,
                markeredgecolor="black", markeredgewidth=2.5, zorder=10)
        ax.plot(lon, lat, "+", color="white", markersize=12,
                markeredgewidth=2.5, zorder=11)
        label = (f"{dept} — {HUB_LABELS[dept]}\n"
                 f"{svc} | {ft} FT | {amb} ambulances\n"
                 f"{calls:,} calls/yr ({night_calls} overnight)")
        ax.annotate(label, (lon, lat), fontsize=8.5, fontweight="bold",
                    textcoords="offset points", xytext=offset,
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=color,
                              edgecolor="black", alpha=0.2),
                    zorder=12)

    elif dept in NEED_COVERAGE:
        hub = assignments[dept]["hub"]
        color = HUB_COLORS[hub]
        marker_size = max(8, min(16, 8 + calls / 300))
        ax.plot(lon, lat, "o", color=color, markersize=marker_size,
                markeredgecolor="black", markeredgewidth=1.5, zorder=7)
        model = "24/7" if is_24_7 else "Vol/On-call"
        label = f"{dept}\n{svc} | {model} | {night_calls} night/yr"
        ax.annotate(label, (lon, lat), fontsize=7,
                    textcoords="offset points", xytext=offset,
                    arrowprops=dict(arrowstyle="-", color=color, alpha=0.4,
                                   lw=0.8),
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor=color, alpha=0.8),
                    zorder=9)
    else:
        # Not in hub system — gray triangle
        ax.plot(lon, lat, "^", color="#bdc3c7", markersize=9, alpha=0.7,
                markeredgecolor="#7f8c8d", markeredgewidth=1, zorder=5)
        ax.annotate(dept, (lon, lat), fontsize=7, color="#7f8c8d",
                    textcoords="offset points", xytext=offset, zorder=6)

# ── Legend ───────────────────────────────────────────────────────────────

legend_items = [
    plt.Line2D([0], [0], marker="s", color="w", markerfacecolor=HUB_COLORS["Watertown"],
               markersize=14, markeredgecolor="black", markeredgewidth=1.5,
               label=f"Watertown — North Hub (31 FT, 3 amb)"),
    plt.Line2D([0], [0], marker="s", color="w", markerfacecolor=HUB_COLORS["Fort Atkinson"],
               markersize=14, markeredgecolor="black", markeredgewidth=1.5,
               label=f"Fort Atkinson — South Hub (16 FT, 3 amb)"),
    plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#888",
               markersize=10, markeredgecolor="black", markeredgewidth=1,
               label="Covered department (color = assigned hub)"),
    plt.Line2D([0], [0], marker="^", color="w", markerfacecolor="#bdc3c7",
               markersize=9, markeredgecolor="#7f8c8d", markeredgewidth=1,
               label="Not in hub system (24/7 career or multi-county)"),
    plt.Line2D([0], [0], linestyle="-", color="#888", alpha=0.5, linewidth=2,
               label="Connection line (label = est. drive time)"),
    mpatches.Patch(facecolor="#aed6f1", edgecolor="#2471a3", alpha=0.3,
                   linestyle="--", label="Hub coverage zone"),
]
ax.legend(handles=legend_items, loc="lower left", fontsize=9,
          framealpha=0.95, edgecolor="#ccc", fancybox=True,
          title="Legend", title_fontsize=10)

# ── Axis formatting ─────────────────────────────────────────────────────

ax.set_xlabel("Longitude", fontsize=12)
ax.set_ylabel("Latitude", fontsize=12)
ax.set_title(
    "Regional Overnight ALS Hub Design — 2 Hubs, Zero Added Cost\n"
    "Existing career ALS departments provide overnight backup via mutual aid protocol\n"
    "Source: boundary_distance_matrix.csv, CY2024 NFIRS (14,853 calls), FY2025 staffing",
    fontsize=13, fontweight="bold", pad=15
)
ax.grid(True, alpha=0.2, linestyle="--")
ax.tick_params(labelsize=10)

# Summary stats box
n_covered = len(NEED_COVERAGE)
total_night = sum(int(AUTH_EMS.get(d, 0) * 0.16) for d in NEED_COVERAGE)
summary = (f"Coverage Summary\n"
           f"2 hubs serve {n_covered} departments\n"
           f"~{total_night:,} overnight calls/yr covered\n"
           f"Zero added cost — uses existing 24/7 crews")
props = dict(boxstyle="round,pad=0.6", facecolor="lightyellow",
             edgecolor="#d4ac0d", alpha=0.9)
ax.text(0.98, 0.98, summary, transform=ax.transAxes, fontsize=9,
        verticalalignment="top", horizontalalignment="right",
        bbox=props, zorder=15)

plt.tight_layout()
out_path = os.path.join(SCRIPT_DIR, "reallocation_hub_coverage_map_2hub.png")
plt.savefig(out_path, dpi=180, bbox_inches="tight", facecolor="white")
plt.close()
print(f"Saved: {out_path}")
