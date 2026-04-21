"""
ORS isochrone response-time maps for Jefferson County secondary ambulance network.

Modes (pass as CLI arg):
  --jeffco        K=2,3  MCLP T=14  from secondary_network_solutions_jeffco.csv
  --total-demand  K=3,4  P-Median   from secondary_network_solutions_totaldemand.csv
  (default)       K=2,3  MCLP T=14  from secondary_network_solutions.csv

Fetches real road-network drive-time polygons from OpenRouteService at
8 / 14 / 20 min thresholds, cached to isochrone_cache/SEC_{mode}_K{k}_{i}.json.
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

# Mode selection
TOTAL_DEMAND_MODE = "--total-demand" in sys.argv
JEFFCO_MODE       = "--jeffco"       in sys.argv

if TOTAL_DEMAND_MODE:
    MODE_SUFFIX   = "totaldemand"
    SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv")
    K_VALUES      = [3, 4]
    USE_PMED      = True    # P-Median is the primary objective for total-demand
elif JEFFCO_MODE:
    MODE_SUFFIX   = "jeffco"
    SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_jeffco.csv")
    K_VALUES      = [2, 3]
    USE_PMED      = False
else:
    MODE_SUFFIX   = "jeffco"
    SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_jeffco.csv")
    K_VALUES      = [2, 3]
    USE_PMED      = False

# Load ORS key from .env
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

SOLUTIONS_CSV  = os.path.join(SCRIPT_DIR, "secondary_network_solutions_jeffco.csv")
CONCURRENT_CSV = os.path.join(SCRIPT_DIR, "concurrent_call_results_jeffco.csv")
COUNTY_GJ      = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")

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
    {"name": "Helenville",    "lat": 43.0135, "lon": -88.6998},
    {"name": "Western Lakes", "lat": 43.0110, "lon": -88.5877},
]

# Isochrone layering: outermost → innermost (so small overlays large)
THRESHOLDS = [
    ("20", "#fee8c8", 0.28, "#e34a33", 0.5,  "≤ 20 min"),
    ("14", "#fc8d59", 0.42, "#d7301f", 0.6,  "≤ 14 min  (90% benchmark)"),
    ("8",  "#b30000", 0.60, "#7f0000", 0.8,  "≤ 8 min   (NFPA target)"),
]

SEC_COLORS = ["#e74c3c", "#e67e22", "#8e44ad"]

ZONE_LABELS = {2: ["South", "North"], 3: ["South", "Central", "North"]}


def fetch_isochrone(cache_id, lat, lon):
    cache_file = os.path.join(CACHE_DIR, f"SEC_{MODE_SUFFIX}_{cache_id}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    if not ORS_API_KEY:
        raise RuntimeError("No ORS_API_KEY found in .env")
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "locations": [[lon, lat]],
        "range": [8 * 60, 14 * 60, 20 * 60],
        "range_type": "time",
        "smoothing": 5,
    }
    print(f"    Fetching ORS isochrone for {cache_id} @ ({lat:.4f},{lon:.4f})...")
    resp = requests.post(ORS_URL, json=payload, headers=headers, timeout=60)
    if resp.status_code == 429:
        print("    Rate-limited — waiting 65s...")
        time.sleep(65)
        resp = requests.post(ORS_URL, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"ORS error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    iso = {}
    for feat in data.get("features", []):
        val_min = str(int(feat["properties"]["value"] / 60))
        iso[val_min] = feat
    with open(cache_file, "w") as f:
        json.dump(iso, f)
    time.sleep(2)   # polite delay between calls
    return iso


def plot_polygon(ax, geom, **kwargs):
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    else:
        polys = geom["coordinates"]
    for poly in polys:
        for ring in poly:
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, **kwargs)
            ax.plot(xs, ys, color=kwargs.get("edgecolor","#999"),
                    linewidth=kwargs.get("linewidth", 0.4), alpha=0.6)


def parse_stations(row):
    parts = str(row["Stations"]).split("|")
    result = []
    for p in parts:
        p = p.strip().strip("()")
        lat, lon = p.split(",")
        result.append((float(lat.strip()), float(lon.strip())))
    return result


def build_map(k, solutions, concurrent):
    if USE_PMED:
        sol = solutions[(solutions["K"] == k) & (solutions["Objective"] == "PMed")]
    else:
        sol = solutions[
            (solutions["K"] == k) &
            (solutions["Objective"] == "MCLP") &
            (solutions["T"].astype(str) == "14")
        ]
    if sol.empty:
        print(f"  No solution for K={k}, skipping.")
        return
    sol = sol.iloc[0]
    sec_pts = parse_stations(sol)
    labels  = ZONE_LABELS.get(k, [f"SEC-{i+1}" for i in range(k)])

    # Fetch isochrones
    isochrones = []
    for i, (lat, lon) in enumerate(sec_pts):
        cache_id = f"K{k}_sec{i+1}"
        iso = fetch_isochrone(cache_id, lat, lon)
        isochrones.append(iso)

    # Load county boundary
    county_geo = json.load(open(COUNTY_GJ))

    fig, ax = plt.subplots(figsize=(15, 12))
    ax.set_facecolor("#e8f4f8")   # light blue background (looks like OSM water)

    # County fill
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else [c for c in geom["coordinates"]]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color="#f5f0e8", zorder=1)
            ax.plot(xs, ys, color="#888", linewidth=0.8, zorder=2)

    # Isochrone layers — outermost first so smaller overlays
    for thresh, fill_color, alpha, edge_color, lw, _ in THRESHOLDS:
        for iso in isochrones:
            if thresh in iso:
                plot_polygon(ax, iso[thresh]["geometry"],
                             color=fill_color, alpha=alpha,
                             edgecolor=edge_color, linewidth=lw, zorder=3)

    # Existing primary stations
    for sta in STATIONS:
        ax.scatter(sta["lon"], sta["lat"], marker="s", s=70,
                   c="#444", edgecolors="white", linewidths=0.8, zorder=6)
        # callout for high-demand depts
        conc_row = concurrent[concurrent["Dept"] == sta["name"]]
        if not conc_row.empty and conc_row.iloc[0]["Secondary_Events"] >= 50:
            r = conc_row.iloc[0]
            ax.annotate(
                f"{sta['name']}\n{int(r['Secondary_Events'])} secondary\n({r['Pct_Concurrent']:.0f}%)",
                (sta["lon"], sta["lat"]),
                xytext=(20, 20), textcoords="offset points",
                fontsize=7.5, color="#c0392b", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor="#c0392b", linewidth=0.9, alpha=0.93),
                arrowprops=dict(arrowstyle="-|>", color="#c0392b",
                                lw=0.8, mutation_scale=10),
                zorder=8
            )
        else:
            ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                        xytext=(4, 5), textcoords="offset points",
                        fontsize=6.5, color="#333",
                        path_effects=[pe.withStroke(linewidth=1.5, foreground="white")],
                        zorder=7)

    # Secondary stations
    for i, ((lat, lon), label) in enumerate(zip(sec_pts, labels)):
        col = SEC_COLORS[i % len(SEC_COLORS)]
        ax.scatter(lon, lat, marker="*", s=700,
                   c=col, edgecolors="white", linewidths=1.5, zorder=9)
        ax.annotate(f"SEC-{i+1}: {label}",
                    (lon, lat), xytext=(0, -26), textcoords="offset points",
                    ha="center", fontsize=9, fontweight="bold", color=col,
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                              edgecolor=col, linewidth=1.3, alpha=0.95),
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")],
                    zorder=10)

    # Stats box
    ax.text(0.015, 0.03,
            f"K={k} secondary stations  |  MCLP T=14 min  |  Avg RT: {sol['Avg_RT']:.1f} min\n"
            f"Demand covered ≤14 min: {sol['Demand_Pct_Covered']:.1f}%   |   Max RT: {sol['Max_RT']:.1f} min\n"
            f"Source: Jefferson-only NFIRS 2024 (Megan 2026-04-19)  |  Drive times: ORS road network",
            transform=ax.transAxes, fontsize=8.5, va="bottom",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#aaa", alpha=0.95),
            zorder=11)

    # Legend
    legend_handles = []
    for thresh, fill_color, alpha, edge_color, lw, label in THRESHOLDS:
        legend_handles.append(Patch(facecolor=fill_color, alpha=alpha + 0.1,
                                    edgecolor=edge_color, label=label))
    for i, label in enumerate(labels):
        col = SEC_COLORS[i % len(SEC_COLORS)]
        legend_handles.append(
            Line2D([0], [0], marker="*", color="w", markerfacecolor=col,
                   markeredgecolor="white", markersize=16,
                   label=f"SEC-{i+1}: {label} (proposed)")
        )
    legend_handles.append(
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#444",
               markeredgecolor="white", markersize=9,
               label="Existing primary station")
    )
    ax.legend(handles=legend_handles, loc="upper left", fontsize=9,
              framealpha=0.95, edgecolor="#bbb", title="Drive-time coverage",
              title_fontsize=9)

    # Bounds
    lons = [s["lon"] for s in STATIONS]
    lats = [s["lat"] for s in STATIONS]
    ax.set_xlim(min(lons) - 0.08, max(lons) + 0.08)
    ax.set_ylim(min(lats) - 0.06, max(lats) + 0.06)
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)
    ax.tick_params(labelsize=9)
    ax.set_aspect("equal")

    obj_label = ("P-Median (minimize avg RT)" if USE_PMED else "MCLP T=14 min")
    demand_label = ("Total call volume — Megan 2026-04-19 auth" if TOTAL_DEMAND_MODE
                    else "Jefferson-only concurrent events")
    ax.set_title(
        f"Jefferson County EMS — Regional Secondary Ambulance Network  (K={k} Stations)\n"
        f"ORS Road-Network Drive-Time Coverage  |  {obj_label}  |  {demand_label}  |  CY2024",
        fontsize=12, fontweight="bold", pad=14
    )

    out = os.path.join(SCRIPT_DIR, f"secondary_isochrone_map_K{k}_{MODE_SUFFIX}.png")
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {os.path.basename(out)}")


def main():
    solutions  = pd.read_csv(SOLUTIONS_CSV)
    # Concurrent CSV only needed for secondary-demand callout annotations
    conc_path = os.path.join(SCRIPT_DIR, f"concurrent_call_results_{MODE_SUFFIX}.csv")
    if not os.path.exists(conc_path):
        conc_path = os.path.join(SCRIPT_DIR, "concurrent_call_results_jeffco.csv")
    concurrent = pd.read_csv(conc_path) if os.path.exists(conc_path) else pd.DataFrame()

    for k in K_VALUES:
        print(f"\n>> Building K={k} isochrone map ({MODE_SUFFIX})...")
        build_map(k, solutions, concurrent)
    print("\nDone.")


if __name__ == "__main__":
    main()
