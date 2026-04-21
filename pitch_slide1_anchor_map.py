"""Shark Tank pitch — Slide 1: Anchor map (squint-test optimized).

A clean, projection-ready version of the K=4 regional secondary ambulance
network. Reuses cached ORS isochrone polygons (no API calls) and the county
boundary GeoJSON. Removes chart junk; emphasizes the 4 proposed regional
stations + 14-min coverage overlay.

Reads:
  isochrone_cache/SEC_totaldemand_K4_sec{1..4}.json  (cached ORS responses)
  secondary_network_solutions_totaldemand.csv        (K=4 station coords)
  jefferson_county.geojson                           (county outline)

Output: pitch_slide1_anchor_map.png  (1920x1080, print-ready)
"""
from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe

ROOT = Path(__file__).parent
CACHE = ROOT / "isochrone_cache"

# ---- Station placements (K=4 P-Median, total-demand model) ----
# Row 9 from secondary_network_solutions_totaldemand.csv:
# 4,PMed,PMed,10.78,42.96,74.7,, "(42.9525,-88.8417) | (43.0125,-88.7817) | (43.0725,-88.7817) | (43.1925,-88.7217)"
STATIONS = [
    {"label": "SEC-1\nSouth",         "lat": 42.9525, "lon": -88.8417, "place": "Fort Atkinson corridor"},
    {"label": "SEC-2\nCenter-South",  "lat": 43.0125, "lon": -88.7817, "place": "Jefferson area"},
    {"label": "SEC-3\nCenter-North",  "lat": 43.0725, "lon": -88.7817, "place": "Johnson Creek area"},
    {"label": "SEC-4\nNorth",         "lat": 43.1925, "lon": -88.7217, "place": "Watertown / Ixonia corridor"},
]

# ---- Existing primary ambulance stations (for context layer) ----
PRIMARIES = [
    {"name": "Watertown",     "lat": 43.1861, "lon": -88.7339},
    {"name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397},
    {"name": "Jefferson",     "lat": 43.0056, "lon": -88.8014},
    {"name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745},
    {"name": "Waterloo",      "lat": 43.1886, "lon": -88.9797},
    {"name": "Ixonia",        "lat": 43.1446, "lon": -88.5970},
    {"name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144},
    {"name": "Cambridge",     "lat": 43.0049, "lon": -89.0224},
    {"name": "Palmyra",       "lat": 42.8794, "lon": -88.5855},
]

# ---- Load county boundary (file contains 27 sub-features/townships) ----
with open(ROOT / "jefferson_county.geojson") as f:
    county_geo = json.load(f)

def iter_outer_rings(county_geo):
    """Yield each feature's outer-ring coordinates."""
    for feat in county_geo["features"]:
        g = feat["geometry"]
        if g["type"] == "Polygon":
            yield g["coordinates"][0]
        elif g["type"] == "MultiPolygon":
            for poly in g["coordinates"]:
                yield poly[0]

# ---- Load cached isochrones ----
# Cache format: {"8": Feature, "14": Feature, "20": Feature} where each Feature
# has geometry.type = "Polygon" (or "MultiPolygon") in lon/lat.
def extract_rings(feat):
    g = feat["geometry"]
    rings = []
    if g["type"] == "Polygon":
        rings.append(g["coordinates"][0])
    elif g["type"] == "MultiPolygon":
        for poly in g["coordinates"]:
            rings.append(poly[0])
    return rings

def load_iso(path):
    with open(path) as f:
        data = json.load(f)
    return {
        "8":  extract_rings(data["8"])  if "8"  in data else [],
        "14": extract_rings(data["14"]) if "14" in data else [],
        "20": extract_rings(data["20"]) if "20" in data else [],
    }

iso_data = []
for i in range(1, 5):
    p = CACHE / f"SEC_totaldemand_K4_sec{i}.json"
    iso_data.append(load_iso(p))

# ---- Figure ----
fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
fig.patch.set_facecolor("white")
ax.set_facecolor("#F5F5F2")

# County fill + faint township outlines
all_rings = list(iter_outer_rings(county_geo))
for ring in all_rings:
    xs = [pt[0] for pt in ring]
    ys = [pt[1] for pt in ring]
    ax.fill(xs, ys, facecolor="white", edgecolor="#CCC", linewidth=0.6, zorder=1)

# Heavy outer county boundary — drawn by taking the union of all township edges
# (we just overplot every ring's edge with a darker pen; the interior township
# lines end up muted by the light-gray above)
for ring in all_rings:
    xs = [pt[0] for pt in ring]
    ys = [pt[1] for pt in ring]
    ax.plot(xs, ys, color="#AAA", lw=0.5, zorder=2)

# 14-min isochrones (main coverage layer — lighter outer ring)
iso_color = "#2C7FB8"
for iso in iso_data:
    for ring in iso["14"]:
        xs = [pt[0] for pt in ring]
        ys = [pt[1] for pt in ring]
        ax.fill(xs, ys, facecolor=iso_color, alpha=0.20, edgecolor=iso_color,
                linewidth=1.2, zorder=3)

# 8-min inner ring (high-speed coverage — denser blue)
for iso in iso_data:
    for ring in iso["8"]:
        xs = [pt[0] for pt in ring]
        ys = [pt[1] for pt in ring]
        ax.fill(xs, ys, facecolor=iso_color, alpha=0.40, edgecolor="none", zorder=4)

# Existing primaries (small gray dots — context, not focus)
for p in PRIMARIES:
    ax.plot(p["lon"], p["lat"], "o", markersize=9, color="#888",
            markeredgecolor="white", markeredgewidth=1.5, zorder=6)

# Proposed regional secondary stations (BIG red stars)
for s in STATIONS:
    ax.plot(s["lon"], s["lat"], "*", markersize=38, color="#B22222",
            markeredgecolor="white", markeredgewidth=2.5, zorder=10)

# Labels for the 4 regional stations
offsets = [
    (+0.015, -0.025),  # SEC-1 label below-right
    (+0.018, +0.010),  # SEC-2 label right
    (-0.020, +0.022),  # SEC-3 label upper-left
    (+0.015, +0.015),  # SEC-4 label upper-right
]
for s, (dx, dy) in zip(STATIONS, offsets):
    ax.text(s["lon"] + dx, s["lat"] + dy, s["label"],
            fontsize=14, fontweight="bold", color="#B22222",
            ha="left", va="center",
            path_effects=[pe.withStroke(linewidth=4, foreground="white")],
            zorder=11)

# ---- Bounds (use known Jefferson County extents so small debris polys don't skew) ----
lon_min, lon_max = -89.02, -88.54
lat_min, lat_max = 42.84, 43.22
pad_x = (lon_max - lon_min) * 0.04
pad_y = (lat_max - lat_min) * 0.04
ax.set_xlim(lon_min - pad_x, lon_max + pad_x)
ax.set_ylim(lat_min - pad_y, lat_max + pad_y)
ax.set_aspect(1.35)
ax.set_xticks([]); ax.set_yticks([])
for sp in ax.spines.values(): sp.set_visible(False)

# ---- Headline ----
fig.suptitle(
    "When Seconds Matter: Optimizing EMS Coverage in Jefferson County",
    fontsize=28, fontweight="bold", color="#111", y=0.965,
)
fig.text(0.5, 0.905,
         "4 regional secondary ambulances → 75% of concurrent-call demand covered within 14 minutes",
         fontsize=16, color="#2C7FB8", ha="center", style="italic")

# ---- Legend ----
legend_elements = [
    Line2D([0], [0], marker="*", color="w", markerfacecolor="#B22222",
           markeredgecolor="white", markersize=22,
           label="Proposed regional secondary (×4)"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="#888",
           markeredgecolor="white", markersize=10,
           label="Existing primary station"),
    Patch(facecolor=iso_color, alpha=0.32, label="≤8 min drive (road network)"),
    Patch(facecolor=iso_color, alpha=0.22, label="≤14 min drive (road network)"),
]
leg = ax.legend(handles=legend_elements, loc="lower left", fontsize=13,
                frameon=True, facecolor="white", edgecolor="#ccc",
                framealpha=0.95, borderpad=1.0, labelspacing=0.9)
leg.get_frame().set_linewidth(1.2)

# ---- Footer ----
fig.text(0.5, 0.025,
         "ISyE 450 Capstone · Jefferson County EMS Working Group · "
         "P-Median optimization on 2024 demand (n=8,396 EMS calls) · "
         "Drive times from OpenRouteService road network",
         fontsize=10, color="#777", ha="center", style="italic")

out = ROOT / "pitch_slide1_anchor_map.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"Saved: {out}")
