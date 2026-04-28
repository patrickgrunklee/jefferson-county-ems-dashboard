"""
Presentation-ready secondary ambulance isochrone maps (K=3, 4, 5).

Watercolor style (adapted from generate_slide_isochrone.py):
  - White background, no basemap noise
  - Simple county outline for orientation
  - Low-alpha isochrone fills in theme reds (<=8, <=14, <=20)
  - Existing stations: teal CIRCLES
  - Proposed stations: dark navy SQUARES
  - Legend: 3 bands + 2 marker types. No title, no footer.

Output: secondary_isochrone_map_K{3,4,5}_presentation.png
"""
import os, sys, json, time, requests
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR, "isochrone_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv")
COUNTY_GJ     = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
K_VALUES      = [3, 4, 5, 6]
MODE_SUFFIX   = "totaldemand"

# Theme colors
CLR_NEW_STATION      = "#1F2A44"   # dark navy square
CLR_EXISTING_STATION = "#4A9B9B"   # teal circle
CLR_COUNTY_OUTLINE   = "#2B2B2B"   # near-black
CLR_COUNTY_FILL      = "#FAFAFA"   # very light gray

# Existing-primary isochrones — red gradient, faded so secondary reads on top
# (minute_key, fill, alpha, edge, lw, label)
PRIMARY_THRESHOLDS = [
    ("20", "#F8B4B4", 0.18, "#D15454", 0.20, "Primary <= 20 min"),
    ("14", "#E63939", 0.18, "#9C1818", 0.22, "Primary <= 14 min"),
    ("8",  "#7A0000", 0.22, "#4A0000", 0.28, "Primary <=  8 min"),
]

# Proposed-secondary isochrones — purple gradient, punchier so it stands out
THRESHOLDS = [
    ("20", "#DCC8EC", 0.45, "#A77FCC", 0.30, "Secondary <= 20 min"),
    ("14", "#8E5EBF", 0.50, "#5E2F8A", 0.35, "Secondary <= 14 min"),
    ("8",  "#3D1568", 0.62, "#1F0A38", 0.40, "Secondary <=  8 min"),
]

# ORS API
env_path = os.path.join(SCRIPT_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
ORS_URL = "https://api.openrouteservice.org/v2/isochrones/driving-car"

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
    # Helenville excluded — first-responder agency, 0 ambulances; transport via Jefferson EMS.
]


def load_primary_iso(name):
    """Load cached existing-station isochrone dict (keys '8','14','20')."""
    path = os.path.join(CACHE_DIR, name.replace(" ", "_") + ".json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def fetch_isochrone(cache_id, lat, lon):
    cache_file = os.path.join(CACHE_DIR, f"SEC_{MODE_SUFFIX}_{cache_id}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    if not ORS_API_KEY:
        raise RuntimeError("No ORS_API_KEY in .env")
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "locations": [[lon, lat]],
        "range":     [8*60, 14*60, 20*60],
        "range_type":"time",
        "smoothing": 5,
    }
    resp = requests.post(ORS_URL, json=payload, headers=headers, timeout=60)
    if resp.status_code == 429:
        time.sleep(65)
        resp = requests.post(ORS_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    iso = {}
    for feat in resp.json().get("features", []):
        iso[str(int(feat["properties"]["value"] / 60))] = feat
    with open(cache_file, "w") as f:
        json.dump(iso, f)
    time.sleep(2)
    return iso


def parse_stations(row):
    parts = str(row["Stations"]).split("|")
    return [tuple(float(v.strip()) for v in p.strip().strip("()").split(","))
            for p in parts]


def plot_polygon(ax, geom, fill, alpha, edge, lw, zorder):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color=fill, alpha=alpha, zorder=zorder,
                    linewidth=0)
            ax.plot(xs, ys, color=edge, linewidth=lw, alpha=0.55,
                    zorder=zorder + 0.1)


def _snap_to_existing(lat, lon):
    """Snap a P-Median grid point to its nearest existing station.
    Returns (snapped_lat, snapped_lon, station_name).
    Lat/lon are unprojected so we use a flat-earth approximation
    (rough scaling 1 deg lat ≈ 1.34 deg lon at 43°N) which is
    plenty accurate for nearest-neighbor inside Jefferson Co.
    """
    best = None
    best_d2 = float("inf")
    for sta in STATIONS:
        dlat = (sta["lat"] - lat)
        dlon = (sta["lon"] - lon) / 1.34
        d2 = dlat * dlat + dlon * dlon
        if d2 < best_d2:
            best_d2 = d2
            best = sta
    return best["lat"], best["lon"], best["name"]


def build_map(k, solutions, isolated=False):
    """Render presentation map for K secondary stations.

    Optimizer points are snapped to the nearest existing station so the
    proposed-station squares co-locate with existing primary stations.
    This reflects the deck's framing: each city keeps its primary, and
    the secondary plan adds a second ambulance AT one of the existing
    stations rather than at an unbuilt grid point.

    isolated=False: primary (red wash) + secondary (purple) overlay.
    isolated=True : secondary (purple) only.
    """
    sol = solutions[(solutions["K"] == k) & (solutions["Objective"] == "PMed")]
    if sol.empty:
        print(f"  No PMed solution for K={k}"); return
    sol = sol.iloc[0]
    raw_pts = parse_stations(sol)

    # Snap each optimizer point to nearest existing station.
    snapped = []
    seen = set()
    for lat, lon in raw_pts:
        s_lat, s_lon, s_name = _snap_to_existing(lat, lon)
        if s_name in seen:
            # Two grid points snapped to the same station — fall back to
            # the next-nearest station that hasn't been used yet.
            ranked = sorted(
                STATIONS,
                key=lambda S: ((S["lat"] - lat) ** 2 +
                               ((S["lon"] - lon) / 1.34) ** 2)
            )
            for cand in ranked:
                if cand["name"] not in seen:
                    s_lat, s_lon, s_name = cand["lat"], cand["lon"], cand["name"]
                    break
        seen.add(s_name)
        snapped.append((s_lat, s_lon, s_name))
    print(f"    K={k} snapped to: {[n for _,_,n in snapped]}")

    sec_pts = [(la, lo) for la, lo, _ in snapped]

    # Reuse primary-station isochrone cache instead of re-querying ORS —
    # the snapped points ARE existing stations.
    isos = []
    for _, _, name in snapped:
        iso = load_primary_iso(name)
        if iso is None:
            # Shouldn't happen for the 12-station set, but fall back to ORS.
            iso = fetch_isochrone(f"K{k}_snapped_{name.replace(' ', '_')}",
                                  *next((s["lat"], s["lon"]) for s in STATIONS
                                        if s["name"] == name))
        isos.append(iso)

    county_geo = json.load(open(COUNTY_GJ))

    fig, ax = plt.subplots(figsize=(14, 11.5))
    ax.set_facecolor("white")

    # County — very light fill + dark outline
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color=CLR_COUNTY_FILL, zorder=1)
            ax.plot(xs, ys, color=CLR_COUNTY_OUTLINE, linewidth=1.6, zorder=2.5)

    # Existing-primary isochrones — faded red wash underneath ("what stays the same").
    # Skipped in isolated mode so the proposed secondary coverage reads alone.
    if not isolated:
        primary_isos = {sta["name"]: load_primary_iso(sta["name"]) for sta in STATIONS}
        primary_isos = {kk: v for kk, v in primary_isos.items() if v is not None}
        for thresh, fill, alpha, edge, lw, _ in PRIMARY_THRESHOLDS:
            for iso in primary_isos.values():
                if thresh in iso:
                    plot_polygon(ax, iso[thresh]["geometry"],
                                 fill=fill, alpha=alpha,
                                 edge=edge, lw=lw, zorder=2.6)

    # Proposed-secondary isochrones — purple, on top of the primary wash
    for thresh, fill, alpha, edge, lw, _ in THRESHOLDS:
        for iso in isos:
            if thresh in iso:
                plot_polygon(ax, iso[thresh]["geometry"],
                             fill=fill, alpha=alpha,
                             edge=edge, lw=lw, zorder=3)

    # Existing primary stations — teal CIRCLES + city label
    # Collision avoidance: try 4 candidate offsets (NE, NW, SE, SW), pick the
    # one furthest from any proposed square.
    CANDIDATES = [
        ( 10,  10, "left"),    # NE
        (-10,  10, "right"),   # NW
        ( 10, -12, "left"),    # SE
        (-10, -12, "right"),   # SW
    ]
    dx_thresh, dy_thresh = 0.050, 0.030    # zone the label must avoid per square

    for sta in STATIONS:
        ax.scatter(sta["lon"], sta["lat"], marker="o", s=110,
                   c=CLR_EXISTING_STATION, edgecolors=CLR_EXISTING_STATION,
                   linewidths=0, zorder=8)

        # Estimate label width in data units (fontsize 8.5, ~0.0011 deg/char)
        label_width_deg = max(len(sta["name"]) * 0.0012, 0.012)

        best_offset, best_score = None, -1
        for ox, oy, ha in CANDIDATES:
            # Convert point offset roughly to data deg: ~0.0007 deg per point
            dx_data = ox * 0.0008
            dy_data = oy * 0.0008
            # Label center in data coords
            lx = sta["lon"] + dx_data + (label_width_deg/2 if ox > 0 else -label_width_deg/2)
            ly = sta["lat"] + dy_data
            # Score = min distance to any proposed square (bigger = safer)
            min_dist = float("inf")
            for (plat, plon) in sec_pts:
                # "distance" scaled by threshold ratios
                ddx = (plon - lx) / dx_thresh
                ddy = (plat - ly) / dy_thresh
                d = (ddx**2 + ddy**2) ** 0.5
                if d < min_dist: min_dist = d
            if min_dist > best_score:
                best_score = min_dist
                best_offset = (ox, oy, ha)

        ox, oy, ha = best_offset
        ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                    xytext=(ox, oy), textcoords="offset points",
                    fontsize=8.5, color="#1a1a1a", fontweight="semibold",
                    ha=ha, va="center", zorder=9)

    # Proposed secondary stations — navy SQUARES (outline = fill)
    for lat, lon in sec_pts:
        ax.scatter(lon, lat, marker="s", s=200,
                   c=CLR_NEW_STATION, edgecolors=CLR_NEW_STATION,
                   linewidths=0, zorder=10)

    # Legend — placed BELOW the map to avoid covering any city label.
    handles = []
    if not isolated:
        # Overlay version: primary trio + secondary trio + both markers.
        for thresh, fill, alpha, edge, lw, label in PRIMARY_THRESHOLDS:
            handles.append(Patch(facecolor=fill, alpha=alpha + 0.25,
                                 edgecolor=edge, linewidth=lw, label=label))
        handles.append(Line2D([0], [0], marker="o", color="w",
                              markerfacecolor=CLR_EXISTING_STATION,
                              markeredgecolor=CLR_EXISTING_STATION,
                              markersize=11, markeredgewidth=0,
                              label="Existing station"))
        for thresh, fill, alpha, edge, lw, label in THRESHOLDS:
            handles.append(Patch(facecolor=fill, alpha=alpha + 0.15,
                                 edgecolor=edge, linewidth=lw, label=label))
        handles.append(Line2D([0], [0], marker="s", color="w",
                              markerfacecolor=CLR_NEW_STATION,
                              markeredgecolor=CLR_NEW_STATION,
                              markersize=12, markeredgewidth=0,
                              label="Proposed station"))
        ncol = 4
    else:
        # Isolated version: only secondary trio + both markers.
        # Strip the "Secondary" prefix since there are no primary bands here.
        for thresh, fill, alpha, edge, lw, label in THRESHOLDS:
            short = label.replace("Secondary ", "")
            handles.append(Patch(facecolor=fill, alpha=alpha + 0.15,
                                 edgecolor=edge, linewidth=lw, label=short))
        handles.append(Line2D([0], [0], marker="o", color="w",
                              markerfacecolor=CLR_EXISTING_STATION,
                              markeredgecolor=CLR_EXISTING_STATION,
                              markersize=11, markeredgewidth=0,
                              label="Existing station"))
        handles.append(Line2D([0], [0], marker="s", color="w",
                              markerfacecolor=CLR_NEW_STATION,
                              markeredgecolor=CLR_NEW_STATION,
                              markersize=12, markeredgewidth=0,
                              label="Proposed station"))
        ncol = 5
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.08),
              fontsize=10, ncol=ncol, framealpha=0.95, edgecolor="#bbb",
              frameon=True, handlelength=2.0, handleheight=1.2,
              columnspacing=1.4)

    # Bounds — frame the county with a little padding
    lons = [s["lon"] for s in STATIONS]
    lats = [s["lat"] for s in STATIONS]
    ax.set_xlim(min(lons) - 0.08, max(lons) + 0.08)
    ax.set_ylim(min(lats) - 0.05, max(lats) + 0.05)
    ax.set_aspect("equal")

    # Coordinate-graph styling: lat/lon ticks, subtle grid, thin border
    ax.grid(True, which="major", color="#cfcfcf", linewidth=0.5, alpha=0.55, zorder=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="major", labelsize=9, colors="#555",
                   length=4, width=0.6, direction="out")
    ax.set_xlabel("Longitude", fontsize=10, color="#444", labelpad=6)
    ax.set_ylabel("Latitude",  fontsize=10, color="#444", labelpad=6)
    for sp_name, sp in ax.spines.items():
        sp.set_visible(True)
        sp.set_color("#999")
        sp.set_linewidth(0.6)

    suffix = "_isolated" if isolated else ""
    out = os.path.join(SCRIPT_DIR,
                       f"secondary_isochrone_map_K{k}_presentation{suffix}.png")
    fig.savefig(out, dpi=220, bbox_inches="tight", facecolor="white", pad_inches=0.1)
    plt.close(fig)
    print(f"  Saved: {os.path.basename(out)}")


def main():
    solutions = pd.read_csv(SOLUTIONS_CSV)
    for k in K_VALUES:
        print(f"\n>> K={k}...")
        build_map(k, solutions, isolated=False)
        build_map(k, solutions, isolated=True)
    print("\nDone.")


if __name__ == "__main__":
    main()
