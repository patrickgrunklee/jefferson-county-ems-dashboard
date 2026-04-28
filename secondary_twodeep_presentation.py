"""
Two-Deep Coverage / Delta Map — presentation-ready version of Option 3.

Visualizes the *marginal benefit* of the proposed K-station secondary
network: where can a SECOND ambulance arrive within 14 min when the
primary is already on a call?

Class assignment per grid cell:
  0  Coverage gap     — neither primary nor secondary reaches in 14 min
  1  Primary only     — primary covers ≤14 min; secondary does not (no surge)
  2  Two-deep coverage — both primary and secondary reach in ≤14 min
                          (this is the actual concurrent-call benefit)

Renders one figure per K in {3, 4, 5, 6}.

Output: secondary_twodeep_K{3,4,5,6}_presentation.png
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

CLR_NEW      = "#1F2A44"
CLR_EXISTING = "#4A9B9B"
CLR_OUTLINE  = "#2B2B2B"

# 0 = gap (light gray), 1 = primary only (medium gray), 2 = two-deep (purple)
CLASS_COLORS = ["#F2F2F2", "#C8C8C8", "#5E2F8A"]
CLASS_LABELS = [
    "Coverage gap (>14 min from any unit)",
    "Single-deep — primary only ≤14 min\n(concurrent call → drop-out risk)",
    "Two-deep — both primary AND secondary ≤14 min\n(surge capacity for concurrent calls)",
]

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


def covered_within_14(pt, prepared_shapes):
    """Returns True if any of the prepared 14-min isochrones contains pt."""
    for ps in prepared_shapes:
        if ps is not None and ps.contains(pt):
            return True
    return False


def draw_county(ax, county_geo):
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            ax.plot(xs, ys, color=CLR_OUTLINE, linewidth=1.8, zorder=4.5)


def render(K, sols, county_geo, county_polys_prepared, county_polys_raw):
    sec_names = get_k_solution(K, sols)
    print(f"  K={K} secondaries: {sec_names}")

    # Primary baseline = ALL existing primary stations (each station on duty
    # 24/7 or otherwise running its own ambulance during the day).
    # The secondary network adds a SECOND ambulance at K of the existing sites.
    primary_14 = []
    for sta in STATIONS:
        iso = load_iso(sta["name"])
        s14 = iso_shape(iso, "14")
        if s14 is not None: primary_14.append(prep(s14))

    secondary_14 = []
    for n in sec_names:
        iso = load_iso(n)
        s14 = iso_shape(iso, "14")
        if s14 is not None: secondary_14.append(prep(s14))

    # Dense grid
    gx = np.linspace(-89.16, -88.55, 220)
    gy = np.linspace(42.78, 43.23, 180)
    XX, YY = np.meshgrid(gx, gy)
    Z = np.full(XX.shape, np.nan)

    cnt_gap = cnt_single = cnt_two = 0
    for i in range(XX.shape[0]):
        for j in range(XX.shape[1]):
            pt = Point(XX[i, j], YY[i, j])
            if not any(p.contains(pt) for p in county_polys_prepared):
                continue
            p_ok = covered_within_14(pt, primary_14)
            s_ok = covered_within_14(pt, secondary_14)
            if p_ok and s_ok:
                Z[i, j] = 2; cnt_two += 1
            elif p_ok:
                Z[i, j] = 1; cnt_single += 1
            else:
                Z[i, j] = 0; cnt_gap += 1

    total_in = cnt_gap + cnt_single + cnt_two
    pct_two  = 100.0 * cnt_two / max(total_in, 1)
    pct_gap  = 100.0 * cnt_gap / max(total_in, 1)

    fig, ax = plt.subplots(figsize=(13, 11), facecolor="white")
    ax.set_facecolor("white")

    for poly in county_polys_raw:
        if poly.geom_type == "Polygon":
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, color="#FAFAFA", zorder=1)

    cmap = ListedColormap(CLASS_COLORS)
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)
    ax.pcolormesh(XX, YY, Z, cmap=cmap, norm=norm, alpha=0.92,
                  zorder=2.6, shading="auto")

    draw_county(ax, county_geo)

    # Stations
    for sta in STATIONS:
        if sta["name"] in sec_names:
            ax.scatter(sta["lon"], sta["lat"], marker="s", s=260,
                       c=CLR_NEW, edgecolors="white", linewidths=1.8, zorder=8)
        else:
            ax.scatter(sta["lon"], sta["lat"], marker="o", s=110,
                       c=CLR_EXISTING, edgecolors="white", linewidths=1.0, zorder=7)
        ox, oy, ha = LABEL_OFFSETS.get(sta["name"], (10, 5, "left"))
        ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                    xytext=(ox, oy), textcoords="offset points",
                    fontsize=9, color="#111",
                    fontweight="bold" if sta["name"] in sec_names else "semibold",
                    ha=ha, va="center", zorder=9,
                    bbox=dict(boxstyle="round,pad=0.18",
                              facecolor="white", edgecolor="none", alpha=0.85))

    # Legend
    legend_handles = [mpatches.Patch(color=c, label=l)
                      for c, l in zip(CLASS_COLORS, CLASS_LABELS)]
    legend_handles += [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=CLR_NEW,
               markeredgecolor="white", markersize=13,
               label=f"Hub with secondary ambulance (×{len(sec_names)})"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=CLR_EXISTING,
               markeredgecolor="white", markersize=10, label="Existing primary station"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=9,
              framealpha=0.95, edgecolor="#bbb",
              title=f"Concurrent-call coverage @ 14-min response (K={K})",
              title_fontsize=10, handlelength=2.2)

    # Stat box
    stats_txt = (f"K = {K} hubs\n"
                 f"Two-deep area:   {pct_two:4.1f}% of county\n"
                 f"Coverage gap:    {pct_gap:4.1f}% of county")
    ax.text(0.99, 0.985, stats_txt,
            transform=ax.transAxes, fontsize=10, fontweight="semibold",
            color="#111", ha="right", va="top", family="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#888", alpha=0.95))

    ax.set_title(
        f"Two-Deep Coverage — Concurrent Call Surge Capacity (K = {K})\n"
        f"Purple = where a 2nd ambulance can arrive ≤14 min "
        f"while the 1st is on a call",
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
             "Source: ORS isochrones (driving-car, 14-min), all 12 existing primary stations + "
             "K-station PMed secondary network. CY2024 NFIRS demand weighting.",
             fontsize=7.5, color="#666")

    out = os.path.join(SCRIPT_DIR, f"secondary_twodeep_K{K}_presentation.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.1)
    plt.close(fig)
    print(f"    saved: {out}  (two-deep {pct_two:.1f}%, gap {pct_gap:.1f}%)")


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
