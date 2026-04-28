"""
Regional Overnight ALS Hub Coverage Map — presentation-ready.

Visualizes the proposed regional overnight ALS hub design. The hubs are
EXISTING 24/7 career ALS departments — Watertown (North) and Fort Atkinson
(South) — whose on-duty paramedics provide overnight ALS intercept for
surrounding volunteer / on-call depts. Key framing:

  - NOT new staff. Watertown and Fort Atkinson already have 24/7 paramedics
    on the clock overnight. This formalizes mutual aid so they back up
    Lake Mills, Waterloo, Ixonia, Cambridge, Palmyra.
  - The hub paramedic intercepts the local BLS/AEMT crew on scene. Local
    ambulance still transports the patient.
  - Zero added county cost — leverages existing career staff hours.

The map shows BOTH:
  (1) WHICH cities/depts the hub covers (city-by-city callout list)
  (2) The geographic EXTENT — isochrone gradient from the hub base so
      readers can see how fast the paramedic reaches each city.

Renders two figures:
  - roving_paramedic_K1_presentation.png  (single hub @ Watertown)
  - roving_paramedic_K2_presentation.png  (Watertown + Fort Atkinson split)

Source: Staffing_Reallocation_Recommendations.md, reallocation_hub_coverage_map_2hub.png,
boundary_distance_matrix.csv, ORS isochrones.
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from shapely.geometry import shape
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR, "isochrone_cache")
COUNTY_GJ  = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
DIST_CSV   = os.path.join(SCRIPT_DIR, "boundary_distance_matrix.csv")

# Theme
CLR_ROVER       = "#C0392B"   # red — existing 24/7 ALS hub dept
CLR_ALS_HAVE    = "#4A9B9B"   # teal — already has 24/7 ALS
CLR_TARGET      = "#E67E22"   # orange — underserved, gains rover ALS
CLR_OUTLINE     = "#2B2B2B"
CLR_FILL        = "#FAFAFA"

# Three response-time tiers from the rover base — light to dark red
TIERS = [
    ("8",  "≤ 8 min",  "#FBC8C0", 0.55, "#C0392B"),
    ("14", "≤ 14 min", "#F09080", 0.42, "#A52A1A"),
    ("20", "≤ 20 min", "#D8604F", 0.28, "#7A1F12"),
]

STATIONS = {
    "Watertown":     {"lat": 43.1861, "lon": -88.7339, "als": True,  "247": True,  "transport": True},
    "Fort Atkinson": {"lat": 42.9271, "lon": -88.8397, "als": True,  "247": True,  "transport": True},
    "Whitewater":    {"lat": 42.8325, "lon": -88.7332, "als": True,  "247": True,  "transport": True},
    "Edgerton":      {"lat": 42.8403, "lon": -89.0629, "als": True,  "247": True,  "transport": True},
    "Jefferson":     {"lat": 43.0056, "lon": -88.8014, "als": True,  "247": True,  "transport": True},
    "Johnson Creek": {"lat": 43.0753, "lon": -88.7745, "als": True,  "247": True,  "transport": True},
    "Western Lakes": {"lat": 43.0110, "lon": -88.5877, "als": True,  "247": True,  "transport": True},
    # 5 target depts (no 24/7 ALS today)
    "Waterloo":      {"lat": 43.1886, "lon": -88.9797, "als": False, "247": False, "transport": True},
    "Lake Mills":    {"lat": 43.0781, "lon": -88.9144, "als": False, "247": False, "transport": True},
    "Ixonia":        {"lat": 43.1446, "lon": -88.5970, "als": False, "247": False, "transport": True},
    "Cambridge":     {"lat": 43.0049, "lon": -89.0224, "als": False, "247": False, "transport": True},
    "Palmyra":       {"lat": 42.8794, "lon": -88.5855, "als": False, "247": False, "transport": True},
}

# 5 underserved target departments — same as staffing_reallocation_analysis.py
TARGET_DEPTS = {
    "Lake Mills": {"pop": 6200, "night_calls": 83, "service": "BLS"},
    "Waterloo":   {"pop": 4415, "night_calls": 83, "service": "AEMT"},
    "Ixonia":     {"pop": 5078, "night_calls": 46, "service": "BLS"},
    "Cambridge":  {"pop": 2800, "night_calls": 14, "service": "ALS (volunteer)"},
    "Palmyra":    {"pop": 3341, "night_calls": 5,  "service": "BLS"},
}


def load_iso(name):
    p = os.path.join(CACHE_DIR, name.replace(" ", "_") + ".json")
    if not os.path.exists(p): return None
    with open(p) as f: return json.load(f)


def plot_iso_polygon(ax, geom, fill, alpha, edge=None, lw=0.0, zorder=3):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color=fill, alpha=alpha, zorder=zorder, linewidth=0)
            if edge and lw > 0:
                ax.plot(xs, ys, color=edge, linewidth=lw, alpha=0.6,
                        zorder=zorder + 0.1)


def draw_county(ax, county_geo, fill=True):
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            if fill:
                ax.fill(xs, ys, color=CLR_FILL, zorder=1)
            ax.plot(xs, ys, color=CLR_OUTLINE, linewidth=1.7, zorder=2.5)


def rt_to_dept(base, dept, dist_df):
    """Drive minutes from base station to dept using boundary_distance_matrix."""
    if base == dept: return 6.0  # local response from own base
    try:
        miles = dist_df.loc[base, dept]
        return round(miles * 1.3 / 35 * 60, 1)
    except Exception:
        return None


def render(bases, label, dist_df, county_geo, out_filename, title, subtitle):
    fig, (ax_map, ax_panel) = plt.subplots(
        1, 2, figsize=(18, 11.5), facecolor="white",
        gridspec_kw={"width_ratios": [2.2, 1.0], "wspace": 0.05}
    )

    draw_county(ax_map, county_geo, fill=True)

    # Isochrone gradient from each rover base — outer to inner so the inner
    # tiers stack on top. Use cached isochrones for the base station.
    for tier_key, tier_label, fill, alpha, edge in reversed(TIERS):
        for base in bases:
            iso = load_iso(base)
            if iso is None or tier_key not in iso: continue
            plot_iso_polygon(ax_map, iso[tier_key]["geometry"],
                             fill=fill, alpha=alpha, edge=edge, lw=0.6, zorder=3)

    # Stations
    for name, s in STATIONS.items():
        x, y = s["lon"], s["lat"]
        if name in bases:
            # ALS hub base — big red square (matches reallocation_hub_coverage_map_2hub style)
            ax_map.scatter(x, y, marker="s", s=620, c=CLR_ROVER,
                           edgecolors="white", linewidths=2.2, zorder=10)
            ax_map.scatter(x, y, marker="P", s=200, c="white", zorder=10.5)
            ax_map.annotate(f"ALS HUB\n{name}", (x, y),
                            xytext=(0, -32), textcoords="offset points",
                            fontsize=10, color="white", fontweight="bold",
                            ha="center", va="top", zorder=11,
                            bbox=dict(boxstyle="round,pad=0.32",
                                      facecolor=CLR_ROVER, edgecolor="white", lw=1.3))
        elif name in TARGET_DEPTS:
            t = TARGET_DEPTS[name]
            ax_map.scatter(x, y, marker="o", s=180, c=CLR_TARGET,
                           edgecolors="white", linewidths=1.6, zorder=8)
            ax_map.annotate(
                f"{name}\n{t['night_calls']} night calls/yr · {t['service']}",
                (x, y), xytext=(11, -3), textcoords="offset points",
                fontsize=8.5, color="#222", fontweight="semibold",
                ha="left", va="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.25",
                          facecolor="white", edgecolor=CLR_TARGET,
                          alpha=0.92, lw=1.0))
        else:
            # Existing 24/7 ALS dept — already covered, faint teal
            ax_map.scatter(x, y, marker="o", s=85, c=CLR_ALS_HAVE,
                           edgecolors="white", linewidths=1.0,
                           zorder=6, alpha=0.72)
            ax_map.annotate(name, (x, y),
                            xytext=(7, 4), textcoords="offset points",
                            fontsize=7.5, color="#444", alpha=0.8, zorder=6.5)

    ax_map.set_xlim(-89.18, -88.55)
    ax_map.set_ylim(42.78, 43.24)
    ax_map.set_aspect("equal")
    ax_map.grid(True, color="#dcdcdc", linewidth=0.4, alpha=0.55, zorder=0.5)
    ax_map.set_axisbelow(True)
    ax_map.tick_params(axis="both", labelsize=8.5, colors="#555", length=4, width=0.6)
    ax_map.set_xlabel("Longitude", fontsize=9.5, color="#444")
    ax_map.set_ylabel("Latitude",  fontsize=9.5, color="#444")
    for sp in ax_map.spines.values():
        sp.set_color("#999"); sp.set_linewidth(0.6)

    # Map legend
    legend_handles = [
        mpatches.Patch(facecolor=TIERS[0][2], alpha=TIERS[0][3] + 0.15,
                       edgecolor=TIERS[0][4], label="Rover reaches ≤ 8 min"),
        mpatches.Patch(facecolor=TIERS[1][2], alpha=TIERS[1][3] + 0.15,
                       edgecolor=TIERS[1][4], label="Rover reaches ≤ 14 min"),
        mpatches.Patch(facecolor=TIERS[2][2], alpha=TIERS[2][3] + 0.15,
                       edgecolor=TIERS[2][4], label="Rover reaches ≤ 20 min"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=CLR_ROVER,
               markeredgecolor="white", markersize=14,
               label=f"ALS hub — existing 24/7 career dept ({len(bases)} hub{'s' if len(bases) > 1 else ''})"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=CLR_TARGET,
               markeredgecolor="white", markersize=11,
               label="Underserved dept (gains ALS via hub intercept)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=CLR_ALS_HAVE,
               markeredgecolor="white", markersize=9, alpha=0.7,
               label="Has 24/7 ALS today (rover not needed)"),
    ]
    ax_map.legend(handles=legend_handles, loc="lower left", fontsize=8.5,
                  framealpha=0.95, edgecolor="#bbb",
                  title=label, title_fontsize=9.5)

    ax_map.set_title(title, fontsize=13.5, fontweight="bold", color="#111", pad=10)
    if subtitle:
        ax_map.text(0.5, 1.013, subtitle, transform=ax_map.transAxes,
                    ha="center", fontsize=10, color="#444", style="italic")

    # ── Right-hand callout panel: city-by-city coverage ────────────────────
    ax_panel.set_xlim(0, 1); ax_panel.set_ylim(0, 1)
    ax_panel.axis("off")

    ax_panel.text(0.04, 0.97, "City-by-City Coverage",
                  fontsize=14, fontweight="bold", color="#111", va="top")
    ax_panel.text(0.04, 0.93, "Drive minutes from ALS hub to each underserved dept",
                  fontsize=8.5, color="#555", style="italic", va="top")

    # Compute best (closest) base→dept RT for each target dept
    rows = []
    for dept, t in TARGET_DEPTS.items():
        best_rt = None; best_base = None
        for b in bases:
            r = rt_to_dept(b, dept, dist_df)
            if r is None: continue
            if best_rt is None or r < best_rt:
                best_rt = r; best_base = b
        rows.append((dept, t, best_rt, best_base))

    # Sort by RT ascending
    rows.sort(key=lambda r: (r[2] if r[2] is not None else 99))

    y = 0.86
    row_h = 0.095

    # Header row
    ax_panel.text(0.04, y, "City",          fontsize=9, fontweight="bold", color="#111")
    ax_panel.text(0.43, y, "Night calls/yr", fontsize=9, fontweight="bold", color="#111")
    ax_panel.text(0.72, y, "Rover RT",      fontsize=9, fontweight="bold", color="#111")
    y -= 0.025
    ax_panel.plot([0.04, 0.96], [y, y], color="#aaa", lw=0.8, transform=ax_panel.transAxes)
    y -= 0.04

    total_pop = total_calls = 0
    for dept, t, rt, b in rows:
        # background tint by RT band
        if rt is None: tint = "#EEE"
        elif rt <= 8:  tint = "#D8F2D8"
        elif rt <= 14: tint = "#FFF1B8"
        elif rt <= 20: tint = "#FFD9C2"
        else:          tint = "#F4C7C0"

        ax_panel.add_patch(FancyBboxPatch(
            (0.03, y - 0.022), 0.94, row_h - 0.018,
            boxstyle="round,pad=0.005", linewidth=0,
            facecolor=tint, alpha=0.85,
            transform=ax_panel.transAxes, zorder=1))

        ax_panel.text(0.05, y + 0.018, dept, fontsize=10.5,
                      fontweight="bold", color="#111", zorder=2)
        ax_panel.text(0.05, y - 0.005, f"{t['service']} · pop {t['pop']:,}",
                      fontsize=7.8, color="#444", zorder=2)
        ax_panel.text(0.45, y + 0.005, f"{t['night_calls']}",
                      fontsize=11, fontweight="semibold", color="#111", zorder=2)
        if rt is None:
            ax_panel.text(0.74, y + 0.005, "—", fontsize=11, color="#666", zorder=2)
        else:
            label_rt = f"{rt:.1f} min"
            if b not in (None,) and len(bases) > 1:
                label_rt += f"\nfrom {b}"
            ax_panel.text(0.74, y + 0.005, label_rt, fontsize=10,
                          fontweight="semibold", color="#111", zorder=2)
        y -= row_h
        total_pop += t["pop"]; total_calls += t["night_calls"]

    # Footer summary
    y -= 0.02
    ax_panel.plot([0.04, 0.96], [y, y], color="#aaa", lw=0.8, transform=ax_panel.transAxes)
    y -= 0.045
    ax_panel.text(0.04, y, "Total residents covered",
                  fontsize=9, color="#444")
    ax_panel.text(0.96, y, f"{total_pop:,}", fontsize=11, fontweight="bold",
                  color="#111", ha="right")
    y -= 0.038
    ax_panel.text(0.04, y, "Total overnight calls/yr intercepted",
                  fontsize=9, color="#444")
    ax_panel.text(0.96, y, f"{total_calls}", fontsize=11, fontweight="bold",
                  color="#111", ha="right")
    y -= 0.038
    ax_panel.text(0.04, y, f"Added county cost",
                  fontsize=9, color="#444")
    ax_panel.text(0.96, y, "$0 / yr", fontsize=11, fontweight="bold",
                  color="#0B6B3A", ha="right")
    y -= 0.038
    ax_panel.text(0.04, y, f"Mechanism",
                  fontsize=9, color="#444")
    mech = f"existing 24/7 ALS staff" if len(bases) == 1 else "existing 24/7 ALS staff (×2)"
    ax_panel.text(0.96, y, mech, fontsize=10, fontweight="semibold",
                  color="#111", ha="right")
    y -= 0.05

    # Note box
    note = ("ALS hub = on-duty paramedic from existing career dept\n"
            "(Watertown / Fort Atkinson). Hub crew intercepts the local\n"
            "BLS / AEMT crew on scene to provide ALS care. Local ambulance\n"
            "still transports the patient — hub does not absorb transports.")
    ax_panel.text(0.04, y, note, fontsize=8, color="#333",
                  va="top", style="italic",
                  bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF8E1",
                            edgecolor="#D4B95E", linewidth=0.7))

    fig.text(0.012, 0.012,
             "Source: Staffing_Reallocation_Recommendations.md, "
             "boundary_distance_matrix.csv, ORS isochrones (driving-car). "
             "5 target depts = those without 24/7 ALS staffing.",
             fontsize=7.5, color="#666")

    out = os.path.join(SCRIPT_DIR, out_filename)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.12)
    plt.close(fig)
    print(f"  saved: {out}")


def build():
    print("Loading data...")
    county_geo = json.load(open(COUNTY_GJ))
    dist = pd.read_csv(DIST_CSV, index_col=0)

    # ── Scenario 1: single hub @ Watertown ────────────────────────────────
    print("Rendering 1-hub (Watertown)...")
    render(
        bases=["Watertown"],
        label="Regional ALS Hub — 1 base (zero added cost)",
        dist_df=dist,
        county_geo=county_geo,
        out_filename="roving_paramedic_K1_presentation.png",
        title="Regional Overnight ALS Hub — Single Base @ Watertown",
        subtitle="Watertown's on-duty ALS crew intercepts overnight calls across the northern corridor"
    )

    # ── Scenario 2: two hubs — Watertown (North) + Fort Atkinson (South) ──
    # Matches the original Regional Overnight ALS Hub Design (2hub) image:
    # both bases are existing 24/7 career ALS depts, so no new positions.
    print("Rendering 2-hub (Watertown + Fort Atkinson)...")
    render(
        bases=["Watertown", "Fort Atkinson"],
        label="Regional ALS Hubs — 2 bases (zero added cost)",
        dist_df=dist,
        county_geo=county_geo,
        out_filename="roving_paramedic_K2_presentation.png",
        title="Regional Overnight ALS Hubs — Watertown North + Fort Atkinson South",
        subtitle="Existing 24/7 career ALS depts back up volunteer crews overnight via formal mutual aid"
    )


if __name__ == "__main__":
    build()
