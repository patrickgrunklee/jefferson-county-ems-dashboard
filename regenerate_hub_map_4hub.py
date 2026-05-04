"""
Regional Overnight ALS Hub Coverage — 4-Hub Graph (Presentation Theme)

Clean graph: 4 hub nodes (Watertown, Fort Atkinson, Edgerton, Western Lakes),
all other departments as small gray nodes, edges colored to match the assigned
hub. No coverage shading, no county fill — district outlines only.

Matches pitch deck palette (red / blue / green / orange + gray on white).
"""

import os, json, warnings
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import shape, MultiPolygon, Polygon

warnings.filterwarnings("ignore")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Pitch deck palette ──────────────────────────────────────────────────
RED    = "#B22222"
BLUE   = "#2C7FB8"
GREEN  = "#228B22"
ORANGE = "#D95F0E"
NAVY   = "#111111"
GRAY   = "#777777"
GRAY_L = "#CCCCCC"

plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 10,
    "axes.edgecolor": GRAY_L,
    "axes.labelcolor": NAVY,
    "xtick.color": GRAY,
    "ytick.color": GRAY,
})

# ── Geometry ────────────────────────────────────────────────────────────
DEPT_COORDS = {
    "Watertown":     (43.1861, -88.7339),
    "Fort Atkinson": (42.9271, -88.8397),
    "Edgerton":      (42.8403, -89.0629),
    "Western Lakes": (43.0110, -88.5877),
    "Whitewater":    (42.8325, -88.7332),
    "Jefferson":     (43.0056, -88.8014),
    "Johnson Creek": (43.0753, -88.7745),
    "Waterloo":      (43.1886, -88.9797),
    "Ixonia":        (43.1446, -88.5970),
    "Palmyra":       (42.8794, -88.5855),
    "Cambridge":     (43.0049, -89.0224),
    "Lake Mills":    (43.0781, -88.9144),
}

HUBS = {
    "Watertown":     RED,
    "Fort Atkinson": BLUE,
    "Edgerton":      GREEN,
    "Western Lakes": ORANGE,
}

# Per-node label offset (in points) — keeps labels clear of the lines they
# share an endpoint with. Tuned manually so every label reads unambiguously.
LABEL_OFFSET = {
    "Watertown":     ( 18,  10),
    "Fort Atkinson": ( 18, -18),
    "Edgerton":      ( 14,   0),
    "Western Lakes": ( 14,   0),
    "Waterloo":      (  0,  12),
    "Ixonia":        ( 12,   0),
    "Johnson Creek": ( 12,  -4),
    "Jefferson":     ( 12,   8),
    "Lake Mills":    (-12,  10),
    "Whitewater":    (  0, -14),
    "Cambridge":     (  0,  12),
    "Palmyra":       ( 12,  -4),
}
# Default horizontal alignment per offset sign
def _ha(off): return "left" if off[0] > 0 else ("right" if off[0] < 0 else "center")
def _va(off): return "bottom" if off[1] > 0 else ("top" if off[1] < 0 else "center")

# ── Hub assignments ─────────────────────────────────────────────────────
# Edgerton and Western Lakes cover only themselves (standalone hubs).
# Helenville is excluded from the map.
assignments = {
    "Waterloo":      "Watertown",
    "Ixonia":        "Watertown",
    "Johnson Creek": "Watertown",
    "Jefferson":     "Fort Atkinson",
    "Lake Mills":    "Fort Atkinson",
    "Whitewater":    "Fort Atkinson",
    "Cambridge":     "Fort Atkinson",
    "Palmyra":       "Fort Atkinson",
}
NEED_COVERAGE = list(assignments.keys())

# ── Boundaries ──────────────────────────────────────────────────────────
def load_polys(path):
    with open(path) as f:
        gj = json.load(f)
    polys = []
    for feat in gj.get("features", [gj]):
        s = shape(feat.get("geometry", feat))
        if isinstance(s, MultiPolygon):
            polys.extend(s.geoms)
        elif isinstance(s, Polygon):
            polys.append(s)
    return polys

county = load_polys(os.path.join(SCRIPT_DIR, "jefferson_county.geojson"))
districts = load_polys(os.path.join(SCRIPT_DIR, "jefferson_ems_districts.geojson"))

# ── Plot ────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(13, 11))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

# District outlines (no fill)
for poly in districts:
    x, y = poly.exterior.xy
    ax.plot(list(x), list(y), color=GRAY_L, linewidth=0.8, zorder=1)

# County outline (slightly darker, no fill)
for poly in county:
    x, y = poly.exterior.xy
    ax.plot(list(x), list(y), color=GRAY, linewidth=1.4, zorder=2)

# Edges: dept → assigned hub (drawn first, sit under nodes)
for dept, hub in assignments.items():
    lat1, lon1 = DEPT_COORDS[dept]
    lat2, lon2 = DEPT_COORDS[hub]
    ax.plot([lon1, lon2], [lat1, lat2], "-", color=HUBS[hub],
            linewidth=2.5, alpha=0.9, solid_capstyle="round", zorder=3)

# Non-hub nodes (small white dots with gray ring) — sit on top of lines
for dept in NEED_COVERAGE:
    lat, lon = DEPT_COORDS[dept]
    ax.plot(lon, lat, "o", color="white", markersize=11,
            markeredgecolor=NAVY, markeredgewidth=1.5, zorder=6)
    off = LABEL_OFFSET.get(dept, (10, 6))
    ax.annotate(dept, (lon, lat), fontsize=9, color=NAVY,
                fontweight="bold",
                textcoords="offset points", xytext=off,
                ha=_ha(off), va=_va(off), zorder=7)

# Hub nodes (large filled circles, hub color)
for hub, color in HUBS.items():
    lat, lon = DEPT_COORDS[hub]
    ax.plot(lon, lat, "o", color=color, markersize=26,
            markeredgecolor=NAVY, markeredgewidth=2.0, zorder=8)
    off = LABEL_OFFSET.get(hub, (16, 8))
    ax.annotate(hub, (lon, lat), fontsize=12,
                fontweight="heavy", fontfamily="Franklin Gothic Heavy",
                color=NAVY,
                textcoords="offset points", xytext=off,
                ha=_ha(off), va=_va(off), zorder=9)

# Legend (4 hub colors, minimal)
legend_items = [
    plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c,
               markeredgecolor=NAVY, markersize=13, label=f"{name}")
    for name, c in HUBS.items()
]
leg = ax.legend(handles=legend_items, loc="upper right", fontsize=10,
                frameon=True, edgecolor=GRAY_L, facecolor="white",
                framealpha=0.95, title="Hubs", title_fontsize=11)
leg.get_title().set_fontweight("bold")

# Axis formatting (minimal)
ax.set_xticks([])
ax.set_yticks([])
for spine in ax.spines.values():
    spine.set_visible(False)

# Heavy bold black title — Franklin Gothic Heavy is the heaviest sans-serif
# available on this system; matches the deck's bold-headline look.
ax.set_title("Regional Hub Network",
             fontsize=26, fontweight="heavy",
             fontfamily="Franklin Gothic Heavy",
             color=NAVY, pad=16, loc="left")

plt.tight_layout()
out_path = os.path.join(SCRIPT_DIR, "reallocation_hub_coverage_map_4hub.png")
plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close()
print(f"Saved: {out_path}")
print("\nHub assignments:")
for dept, hub in sorted(assignments.items()):
    print(f"  {dept:15s} -> {hub}")
