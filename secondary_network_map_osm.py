"""
OSM-style secondary ambulance network map using TIGER road data.

Plots the K=3 Jefferson-only MCLP T=14 recommended solution on a real
road-network basemap (TIGER/Line roads + county boundary + water bodies).

Outputs:
  - secondary_network_osm_K3_jeffco.png   (recommended K=3 solution)
  - secondary_network_osm_K2_jeffco.png   (K=2 for comparison)
"""

import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, FancyArrowPatch
from shapely.geometry import Point
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Data paths ────────────────────────────────────────────────────────────
ROADS_SHP      = os.path.join(SCRIPT_DIR, "tiger_roads", "tl_2023_55055_roads.shp")
COUNTY_GJ      = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
WATER_GJ       = os.path.join(SCRIPT_DIR, "jefferson_water_bodies.geojson")
SOLUTIONS_CSV  = os.path.join(SCRIPT_DIR, "secondary_network_solutions_jeffco.csv")
CONCURRENT_CSV = os.path.join(SCRIPT_DIR, "concurrent_call_results_jeffco.csv")
ALLOC_CSV      = os.path.join(SCRIPT_DIR, "secondary_allocation_table_jeffco.csv")

# ── Existing primary station locations ───────────────────────────────────
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

# ── Palette ───────────────────────────────────────────────────────────────
ROAD_COLORS = {
    "I":   ("#e8705a", 1.6),   # Interstate
    "U":   ("#e8a25a", 1.2),   # US highway
    "S":   ("#e8c85a", 1.0),   # State highway
    "C":   ("#cccccc", 0.6),   # County road
    "L":   ("#dddddd", 0.4),   # Local road
    "M":   ("#eeeeee", 0.3),   # Municipal
}

SEC_COLORS = ["#e74c3c", "#e67e22", "#8e44ad"]   # up to 3 secondary stations
DEMAND_CMAP = plt.cm.YlOrRd


def load_roads():
    roads = gpd.read_file(ROADS_SHP).to_crs("EPSG:4326")
    # Classify by MTFCC
    def road_class(mtfcc):
        if mtfcc in ("S1100",):                return "I"
        if mtfcc in ("S1200",):                return "U"
        if mtfcc in ("S1300",):                return "S"
        if mtfcc in ("S1400",):                return "C"
        if mtfcc in ("S1500", "S1630"):        return "L"
        return "M"
    roads["cls"] = roads["MTFCC"].apply(road_class)
    return roads


def parse_stations_from_row(row):
    """Parse '(lat,lon) | (lat,lon)' string into list of (lat,lon) tuples."""
    parts = str(row["Stations"]).split("|")
    result = []
    for p in parts:
        p = p.strip().strip("()")
        lat, lon = p.split(",")
        result.append((float(lat.strip()), float(lon.strip())))
    return result


def zone_label(i, total):
    if total == 2:
        return ["South", "North"][i]
    if total == 3:
        return ["South", "Central", "North"][i]
    return f"SEC-{i+1}"


def make_map(k, ax, roads, county, water, solutions, concurrent, alloc):
    """Draw one K solution on ax."""

    # ── Background ─────────────────────────────────────────────────────
    # County fill
    county.plot(ax=ax, color="#f5f0e8", edgecolor="#999", linewidth=1.2, zorder=1)

    # Water bodies
    if water is not None and len(water) > 0:
        water.plot(ax=ax, color="#c8e0f0", edgecolor="#a0c8e8", linewidth=0.5, zorder=2)

    # Roads layered by class
    for cls in ["M", "L", "C", "S", "U", "I"]:
        col, lw = ROAD_COLORS[cls]
        sub = roads[roads["cls"] == cls]
        if len(sub):
            sub.plot(ax=ax, color=col, linewidth=lw, zorder=3)

    # ── Demand dots (block groups, sized by secondary events) ──────────
    if alloc is not None and len(alloc):
        d_max = alloc["Secondary_Demand"].max()
        if d_max > 0:
            sizes = (alloc["Secondary_Demand"] / d_max * 220 + 20).clip(lower=10)
            colors = DEMAND_CMAP(alloc["Secondary_Demand"] / d_max)
            ax.scatter(alloc["BG_Lon"], alloc["BG_Lat"],
                       s=sizes, c=colors, alpha=0.55, zorder=4,
                       linewidths=0, label="_nolegend_")

    # ── Primary stations ───────────────────────────────────────────────
    for sta in STATIONS:
        ax.plot(sta["lon"], sta["lat"], "s",
                color="#555", markersize=7, markeredgecolor="#222",
                markeredgewidth=0.6, zorder=6)
        ax.annotate(sta["name"],
                    (sta["lon"], sta["lat"]),
                    xytext=(4, 4), textcoords="offset points",
                    fontsize=6.5, color="#333",
                    path_effects=[pe.withStroke(linewidth=1.5, foreground="white")],
                    zorder=7)

    # ── Secondary station placements ───────────────────────────────────
    sol_row = solutions[
        (solutions["K"] == k) &
        (solutions["Objective"] == "MCLP") &
        (solutions["T"].astype(str) == "14")
    ]
    if sol_row.empty:
        sol_row = solutions[(solutions["K"] == k) & (solutions["Objective"] == "PMed")]
    if sol_row.empty:
        return

    sol_row = sol_row.iloc[0]
    sec_stations = parse_stations_from_row(sol_row)
    labels = [zone_label(i, len(sec_stations)) for i in range(len(sec_stations))]

    for i, ((lat, lon), label) in enumerate(zip(sec_stations, labels)):
        col = SEC_COLORS[i % len(SEC_COLORS)]
        ax.plot(lon, lat, "*", color=col, markersize=22,
                markeredgecolor="white", markeredgewidth=1.5, zorder=9)
        ax.annotate(f"SEC-{i+1}\n{label}",
                    (lon, lat), xytext=(0, -22), textcoords="offset points",
                    ha="center", fontsize=8, fontweight="bold", color=col,
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                              edgecolor=col, linewidth=1.2, alpha=0.92),
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")],
                    zorder=10)

    # ── Concurrency callouts ────────────────────────────────────────────
    top = concurrent.sort_values("Secondary_Events", ascending=False).head(3)
    for _, row in top.iterrows():
        sta = next((s for s in STATIONS if s["name"] == row["Dept"]), None)
        if sta:
            ax.annotate(
                f"{row['Dept']}\n{int(row['Secondary_Events'])} secondary\n({row['Pct_Concurrent']:.0f}% concurrent)",
                (sta["lon"], sta["lat"]),
                xytext=(28, 28), textcoords="offset points",
                fontsize=7, color="#c0392b",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#fff5f5",
                          edgecolor="#c0392b", linewidth=0.9, alpha=0.92),
                arrowprops=dict(arrowstyle="-|>", color="#c0392b",
                                lw=0.9, mutation_scale=10),
                zorder=11
            )

    # ── Stats box ──────────────────────────────────────────────────────
    obj = sol_row["Objective"]
    avg_rt = sol_row["Avg_RT"]
    cov = sol_row["Demand_Pct_Covered"]
    ax.text(0.02, 0.04,
            f"K={k} secondary stations  |  MCLP T=14 min\n"
            f"Avg RT: {avg_rt:.1f} min  |  Demand covered: {cov:.1f}%\n"
            f"Source: Jefferson-only NFIRS 2024 (Megan 2026-04-19)",
            transform=ax.transAxes, fontsize=8, va="bottom",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#bbb", alpha=0.92),
            zorder=12)

    # ── Legend ─────────────────────────────────────────────────────────
    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#555",
               markeredgecolor="#222", markersize=8, label="Existing primary station"),
    ]
    for i, label in enumerate(labels):
        col = SEC_COLORS[i % len(SEC_COLORS)]
        legend_elements.append(
            Line2D([0], [0], marker="*", color="w", markerfacecolor=col,
                   markersize=14, label=f"SEC-{i+1}: {label} (new)")
        )
    legend_elements += [
        Patch(facecolor="#f5c97a", alpha=0.6, label="High secondary demand"),
        Patch(facecolor="#fef9e7", alpha=0.6, label="Low secondary demand"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=8,
              framealpha=0.93, edgecolor="#ccc")

    # ── Axis styling ───────────────────────────────────────────────────
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    ax.tick_params(labelsize=8)

    # Tight bounds to county
    bounds = county.total_bounds  # minx, miny, maxx, maxy
    pad_x = (bounds[2] - bounds[0]) * 0.03
    pad_y = (bounds[3] - bounds[1]) * 0.03
    ax.set_xlim(bounds[0] - pad_x, bounds[2] + pad_x)
    ax.set_ylim(bounds[1] - pad_y, bounds[3] + pad_y)


def build_maps():
    print("Loading basemap data...")
    roads  = load_roads()
    county = gpd.read_file(COUNTY_GJ).to_crs("EPSG:4326")
    water  = gpd.read_file(WATER_GJ).to_crs("EPSG:4326") if os.path.exists(WATER_GJ) else None

    print("Loading analysis data...")
    solutions  = pd.read_csv(SOLUTIONS_CSV)
    concurrent = pd.read_csv(CONCURRENT_CSV)
    alloc      = pd.read_csv(ALLOC_CSV) if os.path.exists(ALLOC_CSV) else None

    for k in (2, 3):
        print(f"Building K={k} OSM map...")
        fig, ax = plt.subplots(figsize=(13, 10))
        make_map(k, ax, roads, county, water, solutions, concurrent, alloc)
        ax.set_title(
            f"Regional Secondary Ambulance Network — K={k} Stations\n"
            f"Jefferson County EMS | Jefferson-Only Call Volume | CY2024",
            fontsize=13, fontweight="bold", pad=12
        )
        out = os.path.join(SCRIPT_DIR, f"secondary_network_osm_K{k}_jeffco.png")
        fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"  Saved: {os.path.basename(out)}")

    print("Done.")


if __name__ == "__main__":
    build_maps()
