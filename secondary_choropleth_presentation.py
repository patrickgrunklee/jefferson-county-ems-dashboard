"""
Best Response-Time Choropleth — presentation-ready version of Option 2.

For each grid cell inside Jefferson County, computes the minimum response
time achievable from any station in the proposed secondary network.
Renders one figure per K in {3, 4, 5, 6}.

Single discrete colormap (≤8, ≤14, ≤20, >20). No overlapping watercolor.

Output: secondary_choropleth_K{3,4,5,6}_presentation.png
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.colors import ListedColormap, BoundaryNorm
from shapely.geometry import shape, Point
from shapely.prepared import prep
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR     = os.path.join(SCRIPT_DIR, "isochrone_cache")
COUNTY_GJ     = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv")

CLR_NEW      = "#1F2A44"   # proposed station — dark navy square
CLR_EXISTING = "#4A9B9B"   # existing primary station — teal circle
CLR_OUTLINE  = "#2B2B2B"

# Discrete RT classes: ≤8, ≤14, ≤20, >20
RT_COLORS = ["#2E8B57", "#F4D35E", "#E67E22", "#9B1C1C"]
RT_LABELS = ["≤ 8 min", "≤ 14 min", "≤ 20 min", "> 20 min"]

STATIONS = [
    {"name": "Watertown",     "lat": 43.1861, "lon": -88.7339},
    {"name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397},
    {"name": "Whitewater",    "lat": 42.8325, "lon": -88.7332},
    {"name": "Edgerton",      "lat": 42.8403, "lon": -89.0629},
    {"name": "Jefferson",     "lat": 43.0056, "lon": -88.8014},
    {"name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745},
    {"name": "Waterloo",      "lat": 43.1886, "lon": -88.9797},
    {"name": "Ixonia",        "lat": 43.1446, "lon": -88.5970},
    {"name": "Palmyra",       "lat": 42.8794, "lon": -88.5855},
    {"name": "Cambridge",     "lat": 43.0049, "lon": -89.0224},
    {"name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144},
    {"name": "Western Lakes", "lat": 43.0110, "lon": -88.5877},
]
STA_BY_NAME = {s["name"]: s for s in STATIONS}

LABEL_OFFSETS = {
    "Helenville":    (-9, -12, "right"),
    "Jefferson":     (-9, -12, "right"),
    "Johnson Creek": (10, -4, "left"),
    "Waterloo":      (10, 5, "left"),
    "Lake Mills":    (-9, 6, "right"),
    "Western Lakes": (10, -4, "left"),
    "Ixonia":        (10, -4, "left"),
    "Watertown":     (10, 6, "left"),
    "Fort Atkinson": (10, -10, "left"),
    "Cambridge":     (-9, 6, "right"),
    "Palmyra":       (10, -4, "left"),
    "Edgerton":      (10, -4, "left"),
    "Whitewater":    (10, -4, "left"),
}


def load_iso(name):
    p = os.path.join(CACHE_DIR, name.replace(" ", "_") + ".json")
    if not os.path.exists(p): return None
    with open(p) as f: return json.load(f)


def parse_stations_field(s):
    return [tuple(float(v.strip()) for v in p.strip().strip("()").split(","))
            for p in str(s).split("|")]


def snap_to_existing(lat, lon, used):
    ranked = sorted(STATIONS,
                    key=lambda S: (S["lat"]-lat)**2 + ((S["lon"]-lon)/1.34)**2)
    for cand in ranked:
        if cand["name"] not in used:
            return cand["name"]
    return ranked[0]["name"]


def get_k_solution(k, sols):
    sol = sols[(sols["K"] == k) & (sols["Objective"] == "PMed")]
    if sol.empty: return []
    raw = parse_stations_field(sol.iloc[0]["Stations"])
    used, names = set(), []
    for la, lo in raw:
        n = snap_to_existing(la, lo, used)
        used.add(n); names.append(n)
    return names


def iso_shape(iso, key):
    if iso is None or key not in iso: return None
    return shape(iso[key]["geometry"])


def min_rt_class(pt, prepared_shapes):
    """Return discrete class index 0=≤8, 1=≤14, 2=≤20, 3=>20."""
    best = 3
    for ps in prepared_shapes:
        if ps["8"] is not None and ps["8"].contains(pt):
            return 0
        if best > 1 and ps["14"] is not None and ps["14"].contains(pt):
            best = 1
        elif best > 2 and ps["20"] is not None and ps["20"].contains(pt):
            best = 2
    return best


def draw_county(ax, county_geo):
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            ax.plot(xs, ys, color=CLR_OUTLINE, linewidth=1.8, zorder=4.5)


def render(K, sols, county_geo, county_polys_prepared, county_polys_raw):
    names = get_k_solution(K, sols)
    print(f"  K={K} hubs: {names}")

    # Collect prepared isochrones for each proposed station
    prepared = []
    for n in names:
        iso = load_iso(n)
        prepared.append({
            "8":  prep(iso_shape(iso, "8"))  if iso_shape(iso, "8")  else None,
            "14": prep(iso_shape(iso, "14")) if iso_shape(iso, "14") else None,
            "20": prep(iso_shape(iso, "20")) if iso_shape(iso, "20") else None,
        })

    # Dense grid
    gx = np.linspace(-89.16, -88.55, 220)
    gy = np.linspace(42.78, 43.23, 180)
    XX, YY = np.meshgrid(gx, gy)
    Z = np.full(XX.shape, np.nan)

    for i in range(XX.shape[0]):
        for j in range(XX.shape[1]):
            pt = Point(XX[i, j], YY[i, j])
            inside = any(p.contains(pt) for p in county_polys_prepared)
            if not inside: continue
            Z[i, j] = min_rt_class(pt, prepared)

    fig, ax = plt.subplots(figsize=(13, 11), facecolor="white")
    ax.set_facecolor("white")

    # County background fill (very light) for context
    for poly in county_polys_raw:
        if poly.geom_type == "Polygon":
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, color="#FAFAFA", zorder=1)

    cmap = ListedColormap(RT_COLORS)
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    pc = ax.pcolormesh(XX, YY, Z, cmap=cmap, norm=norm, alpha=0.88,
                       zorder=2.6, shading="auto")

    draw_county(ax, county_geo)

    # Stations: existing teal circles, proposed dark squares (some overlap by design — snap)
    for sta in STATIONS:
        if sta["name"] in names:
            ax.scatter(sta["lon"], sta["lat"], marker="s", s=240,
                       c=CLR_NEW, edgecolors="white", linewidths=1.8, zorder=8)
        else:
            ax.scatter(sta["lon"], sta["lat"], marker="o", s=110,
                       c=CLR_EXISTING, edgecolors="white", linewidths=1.0, zorder=7)
        ox, oy, ha = LABEL_OFFSETS.get(sta["name"], (10, 5, "left"))
        ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                    xytext=(ox, oy), textcoords="offset points",
                    fontsize=9, color="#111",
                    fontweight="bold" if sta["name"] in names else "semibold",
                    ha=ha, va="center", zorder=9,
                    bbox=dict(boxstyle="round,pad=0.18",
                              facecolor="white", edgecolor="none", alpha=0.85))

    # Legend (RT bins + station markers)
    legend_handles = [mpatches.Patch(color=c, label=l)
                      for c, l in zip(RT_COLORS, RT_LABELS)]
    legend_handles += [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=CLR_NEW,
               markeredgecolor="white", markersize=12, label="Proposed secondary"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=CLR_EXISTING,
               markeredgecolor="white", markersize=10, label="Existing primary"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=9.5,
              framealpha=0.95, edgecolor="#bbb", ncol=2,
              title=f"Best response time achievable\nfrom proposed network (K={K})",
              title_fontsize=10)

    # Demand-covered annotation
    sol_row = sols[(sols["K"] == K) & (sols["Objective"] == "PMed")].iloc[0]
    avg_rt = sol_row.get("Avg_RT", float("nan"))
    ax.text(0.99, 0.985,
            f"K = {K} hubs   |   demand-weighted avg RT = {avg_rt:.1f} min",
            transform=ax.transAxes, fontsize=10.5, fontweight="bold",
            color="#111", ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#888", alpha=0.95))

    ax.set_title(
        f"Secondary Ambulance Network — Best Response Time (K = {K})\n"
        f"Each cell colored by fastest reachable time from any proposed hub",
        fontsize=13, fontweight="bold", color="#111", pad=12)

    ax.set_xlim(-89.16, -88.55); ax.set_ylim(42.78, 43.23)
    ax.set_aspect("equal")
    ax.grid(True, color="#cfcfcf", linewidth=0.4, alpha=0.5, zorder=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=8.5, colors="#555", length=4, width=0.6)
    ax.set_xlabel("Longitude", fontsize=9.5, color="#444")
    ax.set_ylabel("Latitude",  fontsize=9.5, color="#444")
    for sp in ax.spines.values():
        sp.set_color("#999"); sp.set_linewidth(0.6)

    fig.text(0.012, 0.012,
             "Source: ORS isochrones (driving-car), CY2024 NFIRS demand, "
             "secondary_network_solutions_totaldemand.csv (PMed objective)",
             fontsize=7.5, color="#666")

    out = os.path.join(SCRIPT_DIR, f"secondary_choropleth_K{K}_presentation.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.1)
    plt.close(fig)
    print(f"    saved: {out}")


def build():
    print("Loading data...")
    county_geo = json.load(open(COUNTY_GJ))
    county_polys_raw = [shape(f["geometry"]) for f in county_geo["features"]]
    county_polys_prepared = [prep(p) for p in county_polys_raw]
    sols = pd.read_csv(SOLUTIONS_CSV)

    for K in [3, 4, 5, 6]:
        print(f"Rendering K={K}...")
        render(K, sols, county_geo, county_polys_prepared, county_polys_raw)


if __name__ == "__main__":
    build()
