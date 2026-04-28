"""
2x2 Mockup — four visualization options for the secondary ambulance network
isochrone presentation. All four panels use the K=3 PMed solution so the
user can compare visual styles, not scenarios.

  Panel 1 (TL): Hub-and-spoke — coverage zones (convex hull) + drive lines
  Panel 2 (TR): Best response-time choropleth (gridded, single colormap)
  Panel 3 (BL): Delta map — only NEWLY covered area highlighted
  Panel 4 (BR): Small multiples — K=3/4/5/6 at single threshold

Output: _mockup_visualization_options.png
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
from shapely.geometry import shape, Point
from scipy.spatial import ConvexHull
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR, "isochrone_cache")
COUNTY_GJ  = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv")

CLR_NEW      = "#1F2A44"
CLR_EXISTING = "#4A9B9B"
CLR_OUTLINE  = "#2B2B2B"
CLR_FILL     = "#FAFAFA"

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


def draw_county(ax, county_geo, lw=1.4, fill=True):
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            if fill:
                ax.fill(xs, ys, color=CLR_FILL, zorder=1)
            ax.plot(xs, ys, color=CLR_OUTLINE, linewidth=lw, zorder=2.5)


def plot_iso_polygon(ax, geom, fill, alpha, edge=None, lw=0.0, zorder=3):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color=fill, alpha=alpha, zorder=zorder, linewidth=0)
            if edge and lw > 0:
                ax.plot(xs, ys, color=edge, linewidth=lw, alpha=0.6,
                        zorder=zorder + 0.1)


def iso_shape(iso, key):
    if iso is None or key not in iso: return None
    return shape(iso[key]["geometry"])


def min_rt_at_point(pt, iso_shapes_per_station):
    """Return min response time (minutes) from any station's isochrones at a point.
       iso_shapes_per_station: list of dicts {'8': shp, '14': shp, '20': shp}.
       Returns 6 if in any 8-min poly, 11 if in 14, 17 if in 20, 25 otherwise."""
    best = 25
    for shps in iso_shapes_per_station:
        if shps.get("8") and shps["8"].contains(pt):
            return 6
        if shps.get("14") and shps["14"].contains(pt):
            best = min(best, 11)
        elif shps.get("20") and shps["20"].contains(pt):
            best = min(best, 17)
    return best


# ── Panel 1: Hub-and-spoke ──────────────────────────────────────────────
def panel_hub_spoke(ax, county_geo, k3_names):
    draw_county(ax, county_geo)

    # Coverage zones — convex hull around each hub's 14-min isochrone vertices,
    # tinted in three different hub colors so each hub's territory reads.
    HUB_COLORS = ["#5B8DEF", "#E27A4D", "#3C9D74"]
    served_by = {}  # dept_name -> hub_name

    # For each non-hub dept, assign to nearest hub by lat/lon.
    for sta in STATIONS:
        if sta["name"] in k3_names: continue
        best_hub, best_d = None, 1e9
        for h in k3_names:
            hs = STA_BY_NAME[h]
            d = (sta["lat"]-hs["lat"])**2 + ((sta["lon"]-hs["lon"])/1.34)**2
            if d < best_d:
                best_d = d; best_hub = h
        served_by[sta["name"]] = best_hub

    # Coverage zone fills: convex hull over all dept locations served by that hub.
    for i, h in enumerate(k3_names):
        members = [STA_BY_NAME[h]] + [STA_BY_NAME[d] for d, hh in served_by.items() if hh == h]
        if len(members) < 3: continue
        pts = np.array([[m["lon"], m["lat"]] for m in members])
        try:
            hull = ConvexHull(pts)
            poly = pts[hull.vertices]
            ax.fill(poly[:, 0], poly[:, 1], color=HUB_COLORS[i], alpha=0.18, zorder=2.7)
            ax.plot(np.append(poly[:, 0], poly[0, 0]),
                    np.append(poly[:, 1], poly[0, 1]),
                    color=HUB_COLORS[i], lw=1.6, alpha=0.7, zorder=2.8)
        except Exception:
            pass

    # Spoke lines hub -> served dept with drive-time labels (rough)
    for dept, hub in served_by.items():
        d, h = STA_BY_NAME[dept], STA_BY_NAME[hub]
        ax.plot([h["lon"], d["lon"]], [h["lat"], d["lat"]],
                color="#444", lw=0.8, alpha=0.55, zorder=3, linestyle="--")
        # rough drive time
        miles = np.hypot((h["lat"]-d["lat"])*69, (h["lon"]-d["lon"])*53)
        mins = round(miles * 1.3 / 35 * 60)
        mx, my = (h["lon"]+d["lon"])/2, (h["lat"]+d["lat"])/2
        ax.annotate(f"{mins} min", (mx, my), fontsize=6.5, color="#222",
                    ha="center", va="center", zorder=4,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.2))

    # Stations: hubs as squares, others as circles
    for sta in STATIONS:
        if sta["name"] in k3_names:
            i = k3_names.index(sta["name"])
            ax.scatter(sta["lon"], sta["lat"], marker="s", s=180,
                       c=HUB_COLORS[i], edgecolors="white", linewidths=1.5,
                       zorder=8)
            ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                        xytext=(0, 14), textcoords="offset points",
                        fontsize=8, color="#1a1a1a", fontweight="bold",
                        ha="center", zorder=9)
        else:
            ax.scatter(sta["lon"], sta["lat"], marker="o", s=55,
                       c=CLR_EXISTING, edgecolors="white", linewidths=1, zorder=7)
            ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                        xytext=(7, 4), textcoords="offset points",
                        fontsize=6.5, color="#333", zorder=9)

    # Legend
    handles = [
        Line2D([0],[0], marker='s', color='w', markerfacecolor=HUB_COLORS[0],
               markersize=11, label='Hub (proposed secondary)'),
        Line2D([0],[0], marker='o', color='w', markerfacecolor=CLR_EXISTING,
               markersize=8, label='Existing primary station'),
        Line2D([0],[0], color='#444', lw=1, linestyle='--', label='Hub→served dept'),
    ]
    ax.legend(handles=handles, loc='lower left', fontsize=7.5, framealpha=0.92)

    ax.set_title("Option 1 — Hub-and-Spoke\n(coverage zones + drive-time spokes)",
                 fontsize=11, fontweight="bold", color="#222")


# ── Panel 2: Best response-time choropleth ──────────────────────────────
def panel_choropleth(ax, county_geo, k3_names):
    draw_county(ax, county_geo, fill=False)

    # Build grid over county bounding box
    xs = np.linspace(-89.15, -88.55, 70)
    ys = np.linspace(42.78, 43.22, 60)
    XX, YY = np.meshgrid(xs, ys)

    iso_shapes = []
    for n in k3_names:
        iso = load_iso(n)
        iso_shapes.append({k: iso_shape(iso, k) for k in ("8", "14", "20")})

    # County mask
    county_polys = [shape(f["geometry"]) for f in county_geo["features"]]
    def in_county(pt):
        return any(p.contains(pt) for p in county_polys)

    Z = np.full(XX.shape, np.nan)
    for i in range(XX.shape[0]):
        for j in range(XX.shape[1]):
            pt = Point(XX[i, j], YY[i, j])
            if not in_county(pt): continue
            Z[i, j] = min_rt_at_point(pt, iso_shapes)

    # Discrete colormap: 6, 11, 17, 25 → green, yellow, orange, red
    cmap = LinearSegmentedColormap.from_list(
        "rt", ["#1A9850", "#F4D35E", "#F28C28", "#B30000"], N=4)
    bounds = [0, 8, 14, 20, 30]
    norm = BoundaryNorm(bounds, cmap.N)

    pc = ax.pcolormesh(XX, YY, Z, cmap=cmap, norm=norm, alpha=0.85, zorder=2.6,
                       shading="auto")
    cb = plt.colorbar(pc, ax=ax, fraction=0.035, pad=0.02, ticks=[4, 11, 17, 25])
    cb.ax.set_yticklabels(["≤8", "≤14", "≤20", ">20"], fontsize=8)
    cb.set_label("Best response time (min)", fontsize=8)

    # Stations on top
    for sta in STATIONS:
        if sta["name"] in k3_names:
            ax.scatter(sta["lon"], sta["lat"], marker="s", s=130,
                       c=CLR_NEW, edgecolors="white", linewidths=1.4, zorder=8)
        else:
            ax.scatter(sta["lon"], sta["lat"], marker="o", s=40,
                       c=CLR_EXISTING, edgecolors="white", linewidths=0.8, zorder=7)

    ax.set_title("Option 2 — Best Response-Time Choropleth\n"
                 "(single layer, no overlapping watercolor)",
                 fontsize=11, fontweight="bold", color="#222")


# ── Panel 3: Delta map (newly covered) ──────────────────────────────────
def panel_delta(ax, county_geo, k3_names):
    draw_county(ax, county_geo, fill=False)

    # Baseline: ALL existing primary stations
    base_shapes = []
    for n in [s["name"] for s in STATIONS]:
        iso = load_iso(n)
        base_shapes.append({k: iso_shape(iso, k) for k in ("8", "14", "20")})
    # Combined: baseline + K=3 secondaries (which are also existing stations after snap)
    # Since K=3 are subset of STATIONS, "newly covered" comes from upgrading the
    # threshold. Show: baseline ≤14 vs combined ≤8 around K=3 hubs (i.e. now reachable
    # by a SECOND ambulance within 8 min).
    sec_shapes = []
    for n in k3_names:
        iso = load_iso(n)
        sec_shapes.append({k: iso_shape(iso, k) for k in ("8", "14", "20")})

    xs = np.linspace(-89.15, -88.55, 70)
    ys = np.linspace(42.78, 43.22, 60)
    XX, YY = np.meshgrid(xs, ys)
    county_polys = [shape(f["geometry"]) for f in county_geo["features"]]
    def in_county(pt): return any(p.contains(pt) for p in county_polys)

    # Z = 0 (out), 1 (covered by primary 14-min only),
    #     2 (covered by primary AND secondary 14-min — "two-deep coverage")
    #     3 (newly within 14 min thanks to secondary; was >14 from primary)
    Z = np.zeros(XX.shape)
    for i in range(XX.shape[0]):
        for j in range(XX.shape[1]):
            pt = Point(XX[i, j], YY[i, j])
            if not in_county(pt):
                Z[i, j] = -1; continue
            base_rt = min_rt_at_point(pt, base_shapes)
            sec_rt  = min_rt_at_point(pt, sec_shapes)
            if base_rt <= 14 and sec_rt <= 14:
                Z[i, j] = 2  # two-deep
            elif base_rt <= 14:
                Z[i, j] = 1  # primary only
            elif sec_rt <= 14:
                Z[i, j] = 3  # newly covered
            else:
                Z[i, j] = 0  # gap

    cmap = LinearSegmentedColormap.from_list(
        "delta", ["#EEEEEE", "#D8D8D8", "#7B4FA8", "#1F0A38"], N=4)
    bounds = [-0.5, 0.5, 1.5, 2.5, 3.5]
    norm = BoundaryNorm(bounds, cmap.N)

    Zplot = np.where(Z < 0, np.nan, Z)
    ax.pcolormesh(XX, YY, Zplot, cmap=cmap, norm=norm, alpha=0.92, zorder=2.6,
                  shading="auto")

    for sta in STATIONS:
        if sta["name"] in k3_names:
            ax.scatter(sta["lon"], sta["lat"], marker="s", s=130,
                       c=CLR_NEW, edgecolors="white", linewidths=1.4, zorder=8)
        else:
            ax.scatter(sta["lon"], sta["lat"], marker="o", s=40,
                       c=CLR_EXISTING, edgecolors="white", linewidths=0.8, zorder=7)

    handles = [
        mpatches.Patch(color="#EEEEEE", label="Coverage gap (>14 min)"),
        mpatches.Patch(color="#D8D8D8", label="Primary only (1 ambulance ≤14)"),
        mpatches.Patch(color="#7B4FA8", label="Two-deep (2 ambulances ≤14)"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, framealpha=0.92)

    ax.set_title("Option 3 — Delta / Two-Deep Coverage\n"
                 "(highlights surge capacity, not redundant primary)",
                 fontsize=11, fontweight="bold", color="#222")


# ── Panel 4: Small multiples K=3,4,5,6 at single 14-min threshold ───────
def panel_small_multiples(parent_gs, fig, county_geo, sols):
    inner = GridSpecFromSubplotSpec(2, 2, subplot_spec=parent_gs,
                                    wspace=0.1, hspace=0.25)
    K_list = [3, 4, 5, 6]
    for idx, K in enumerate(K_list):
        ax = fig.add_subplot(inner[idx // 2, idx % 2])
        draw_county(ax, county_geo, lw=0.9, fill=True)
        names = get_k_solution(K, sols)
        for n in names:
            iso = load_iso(n)
            geom = iso.get("14", {}).get("geometry") if iso else None
            if geom:
                plot_iso_polygon(ax, geom, fill="#5E2F8A", alpha=0.55,
                                 edge="#1F0A38", lw=0.8, zorder=3)
        for sta in STATIONS:
            if sta["name"] in names:
                ax.scatter(sta["lon"], sta["lat"], marker="s", s=42,
                           c=CLR_NEW, edgecolors="white", linewidths=0.6, zorder=8)
            else:
                ax.scatter(sta["lon"], sta["lat"], marker="o", s=10,
                           c=CLR_EXISTING, zorder=7, alpha=0.7)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"K = {K}  ({len(names)} hubs)", fontsize=9,
                     fontweight="semibold", color="#222")
        ax.set_xlim(-89.15, -88.55); ax.set_ylim(42.78, 43.22)
        ax.set_aspect("equal")
        for sp in ax.spines.values():
            sp.set_color("#999"); sp.set_linewidth(0.5)


def style_axes(ax):
    ax.set_xlim(-89.15, -88.55); ax.set_ylim(42.78, 43.22)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#999"); sp.set_linewidth(0.6)


def build():
    print("Loading data...")
    county_geo = json.load(open(COUNTY_GJ))
    sols = pd.read_csv(SOLUTIONS_CSV)
    k3_names = get_k_solution(3, sols)
    print(f"  K=3 hubs: {k3_names}")

    fig = plt.figure(figsize=(17, 14), facecolor="white")
    gs = GridSpec(2, 2, figure=fig, wspace=0.08, hspace=0.18,
                  left=0.04, right=0.97, top=0.92, bottom=0.04)

    print("Building panel 1 — hub-and-spoke...")
    ax1 = fig.add_subplot(gs[0, 0])
    panel_hub_spoke(ax1, county_geo, k3_names); style_axes(ax1)

    print("Building panel 2 — choropleth (this samples a grid; ~30s)...")
    ax2 = fig.add_subplot(gs[0, 1])
    panel_choropleth(ax2, county_geo, k3_names); style_axes(ax2)

    print("Building panel 3 — delta map...")
    ax3 = fig.add_subplot(gs[1, 0])
    panel_delta(ax3, county_geo, k3_names); style_axes(ax3)

    print("Building panel 4 — small multiples...")
    panel_small_multiples(gs[1, 1], fig, county_geo, sols)
    # add panel-level title
    fig.text(0.74, 0.475, "Option 4 — Small Multiples (K=3/4/5/6 @ 14 min)",
             fontsize=11, fontweight="bold", color="#222", ha="center")

    fig.suptitle(
        "Visualization Mockup — 4 Options for Secondary Ambulance Coverage (K=3 example)",
        fontsize=14, fontweight="bold", y=0.97, color="#111")

    out = os.path.join(SCRIPT_DIR, "_mockup_visualization_options.png")
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    build()
