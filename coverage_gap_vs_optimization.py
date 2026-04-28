"""
Coverage Gap Analysis — Where the Optimization Actually Places Capacity.

Shows the disconnect between (a) the depts with REAL overnight ALS gaps
and (b) the hubs the secondary ambulance P-Median optimizer selects.

Output: coverage_gap_vs_optimization.png
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
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
COUNTY_GJ     = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
SOLUTIONS_CSV = os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv")

# Service tier ranking — higher = better overnight ALS reliability
SERVICE_RANK  = {"BLS": 1, "AEMT": 2, "ALS-vol": 3, "ALS-24/7": 4}
TIER_COLORS   = {
    "BLS":      "#C0392B",   # red — biggest gap
    "AEMT":     "#E67E22",   # orange — medium gap
    "ALS-vol":  "#F1C40F",   # yellow — has cap but unreliable
    "ALS-24/7": "#27AE60",   # green — no gap
}
TIER_LABELS   = {
    "BLS":      "BLS only — major ALS gap",
    "AEMT":     "AEMT, no 24/7 — partial gap",
    "ALS-vol":  "ALS volunteer, no 24/7 — overnight gap",
    "ALS-24/7": "24/7 career ALS — no gap",
}

DEPTS = {
    "Watertown":     {"lat": 43.1861, "lon": -88.7339, "service": "ALS-24/7", "calls": 2012, "night_calls": 321},
    "Fort Atkinson": {"lat": 42.9271, "lon": -88.8397, "service": "ALS-24/7", "calls": 1616, "night_calls": 258},
    "Whitewater":    {"lat": 42.8325, "lon": -88.7332, "service": "ALS-24/7", "calls":   64, "night_calls":  10},
    "Edgerton":      {"lat": 42.8403, "lon": -89.0629, "service": "ALS-24/7", "calls": 2138, "night_calls": 342},
    "Jefferson":     {"lat": 43.0056, "lon": -88.8014, "service": "ALS-24/7", "calls": 1457, "night_calls": 233},
    "Johnson Creek": {"lat": 43.0753, "lon": -88.7745, "service": "ALS-24/7", "calls":  487, "night_calls":  77},
    "Western Lakes": {"lat": 43.0110, "lon": -88.5877, "service": "ALS-24/7", "calls":  263, "night_calls":  42},
    "Waterloo":      {"lat": 43.1886, "lon": -88.9797, "service": "AEMT",     "calls":  520, "night_calls":  83},
    "Lake Mills":    {"lat": 43.0781, "lon": -88.9144, "service": "BLS",      "calls":  518, "night_calls":  83},
    "Ixonia":        {"lat": 43.1446, "lon": -88.5970, "service": "BLS",      "calls":  289, "night_calls":  46},
    "Cambridge":     {"lat": 43.0049, "lon": -89.0224, "service": "ALS-vol",  "calls":   87, "night_calls":  14},
    "Palmyra":       {"lat": 42.8794, "lon": -88.5855, "service": "BLS",      "calls":   32, "night_calls":   5},
}


def parse_stations_field(s):
    return [tuple(float(v.strip()) for v in p.strip().strip("()").split(","))
            for p in str(s).split("|")]


def snap_to_existing(lat, lon, used):
    items = list(DEPTS.items())
    items.sort(key=lambda kv: (kv[1]["lat"]-lat)**2 + ((kv[1]["lon"]-lon)/1.34)**2)
    for name, _ in items:
        if name not in used:
            return name
    return items[0][0]


def get_k_hubs(K, sols):
    sol = sols[(sols["K"] == K) & (sols["Objective"] == "PMed")]
    if sol.empty: return []
    raw = parse_stations_field(sol.iloc[0]["Stations"])
    used, names = set(), []
    for la, lo in raw:
        n = snap_to_existing(la, lo, used)
        used.add(n); names.append(n)
    return names


def is_gap(service):
    return service != "ALS-24/7"


def build():
    sols = pd.read_csv(SOLUTIONS_CSV)
    K_LIST = [3, 4, 5, 6]
    hub_by_K = {K: set(get_k_hubs(K, sols)) for K in K_LIST}

    fig = plt.figure(figsize=(17, 10), facecolor="white")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 1.0], wspace=0.18,
                          left=0.045, right=0.985, top=0.90, bottom=0.07)

    # ── LEFT: Map showing current ALS status ────────────────────────────
    ax_map = fig.add_subplot(gs[0, 0])
    county_geo = json.load(open(COUNTY_GJ))
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]; ys = [pt[1] for pt in ring]
            ax_map.fill(xs, ys, color="#FAFAFA", zorder=1)
            ax_map.plot(xs, ys, color="#2B2B2B", linewidth=1.6, zorder=2.5)

    label_offsets = {
        "Helenville":    (-9, -12, "right"),
        "Jefferson":     (-9, -12, "right"),
        "Johnson Creek": (12, -3, "left"),
        "Waterloo":      (12, 6, "left"),
        "Lake Mills":    (-10, 8, "right"),
        "Western Lakes": (12, -3, "left"),
        "Ixonia":        (12, -3, "left"),
        "Watertown":     (12, 8, "left"),
        "Fort Atkinson": (12, -10, "left"),
        "Cambridge":     (-10, 8, "right"),
        "Palmyra":       (12, -3, "left"),
        "Edgerton":      (12, -3, "left"),
        "Whitewater":    (12, -3, "left"),
    }

    for name, d in DEPTS.items():
        color = TIER_COLORS[d["service"]]
        size = 60 + d["night_calls"] * 0.6
        edgec = "#3C0000" if is_gap(d["service"]) else "#0F4D2A"
        ax_map.scatter(d["lon"], d["lat"], s=size, c=color, edgecolors=edgec,
                       linewidths=1.4, zorder=8, alpha=0.92)
        ox, oy, ha = label_offsets.get(name, (10, 5, "left"))
        ax_map.annotate(
            f"{name}\n{d['night_calls']} night calls/yr",
            (d["lon"], d["lat"]),
            xytext=(ox, oy), textcoords="offset points",
            fontsize=8, color="#111",
            fontweight="bold" if is_gap(d["service"]) else "normal",
            ha=ha, va="center", zorder=9,
            bbox=dict(boxstyle="round,pad=0.18",
                      facecolor="white", edgecolor=color, alpha=0.92, lw=0.9))

    legend_handles = [
        mpatches.Patch(color=TIER_COLORS[t], label=TIER_LABELS[t])
        for t in ["BLS", "AEMT", "ALS-vol", "ALS-24/7"]
    ]
    ax_map.legend(handles=legend_handles, loc="lower left", fontsize=8.5,
                  framealpha=0.95, edgecolor="#bbb",
                  title="Current overnight ALS service",
                  title_fontsize=9.5)

    ax_map.set_title("Current State — Which depts actually have an ALS gap?",
                     fontsize=12, fontweight="bold", color="#111", pad=10)
    ax_map.set_xlim(-89.16, -88.55); ax_map.set_ylim(42.78, 43.23)
    ax_map.set_aspect("equal")
    ax_map.grid(True, color="#dcdcdc", linewidth=0.4, alpha=0.5)
    ax_map.tick_params(axis="both", labelsize=8, colors="#555", length=4, width=0.5)
    ax_map.set_xlabel("Longitude", fontsize=9, color="#444")
    ax_map.set_ylabel("Latitude",  fontsize=9, color="#444")
    for sp in ax_map.spines.values():
        sp.set_color("#999"); sp.set_linewidth(0.6)

    # ── RIGHT: Coverage matrix — depts × K-scenarios ────────────────────
    ax_mat = fig.add_subplot(gs[0, 1])
    ax_mat.set_xlim(0, 1); ax_mat.set_ylim(0, 1)
    ax_mat.axis("off")

    # Sort depts: gaps first (worst → best), then non-gaps by call volume
    ordered = sorted(
        DEPTS.items(),
        key=lambda kv: (SERVICE_RANK[kv[1]["service"]], -kv[1]["night_calls"])
    )

    # Title
    ax_mat.text(0.0, 0.985, "Where the optimizer places hubs",
                fontsize=12.5, fontweight="bold", color="#111", va="top")
    ax_mat.text(0.0, 0.945,
                "Filled square = K-scenario places a 2nd ambulance here.\n"
                "Are we covering the actual ALS gaps — or doubling up on already-covered depts?",
                fontsize=8.5, color="#444", style="italic", va="top")

    # Column headers
    col_x = {"K=3": 0.50, "K=4": 0.61, "K=5": 0.72, "K=6": 0.83}
    y_top = 0.86

    ax_mat.text(0.0, y_top, "Dept", fontsize=9.5, fontweight="bold")
    ax_mat.text(0.34, y_top, "Service today", fontsize=9.5, fontweight="bold")
    for col, x in col_x.items():
        ax_mat.text(x, y_top, col, fontsize=9.5, fontweight="bold", ha="center")
    ax_mat.text(0.96, y_top, "Real gap?",
                fontsize=9.5, fontweight="bold", ha="right")

    y = y_top - 0.018
    ax_mat.plot([0.0, 1.0], [y, y], color="#aaa", lw=0.7,
                transform=ax_mat.transAxes)

    row_h = 0.062
    y -= 0.025
    n_redundant = {K: 0 for K in K_LIST}
    n_fixes_gap = {K: 0 for K in K_LIST}

    for name, d in ordered:
        color = TIER_COLORS[d["service"]]
        gap = is_gap(d["service"])
        # Row background
        rowcolor = "#FFF4F1" if gap else "#F1FBF4"
        ax_mat.add_patch(FancyBboxPatch(
            (-0.005, y - 0.024), 1.01, row_h - 0.012,
            boxstyle="round,pad=0.003",
            linewidth=0, facecolor=rowcolor, alpha=0.9,
            transform=ax_mat.transAxes, zorder=1))

        ax_mat.text(0.005, y, name, fontsize=10,
                    fontweight="bold" if gap else "semibold", color="#111", zorder=2)
        # Service tier chip
        ax_mat.add_patch(FancyBboxPatch(
            (0.34, y - 0.014), 0.13, 0.028,
            boxstyle="round,pad=0.003",
            linewidth=0, facecolor=color, alpha=0.85,
            transform=ax_mat.transAxes, zorder=2))
        ax_mat.text(0.405, y, d["service"], fontsize=8.5,
                    color="white", fontweight="bold", ha="center",
                    va="center", zorder=3)

        for K in K_LIST:
            x = col_x[f"K={K}"]
            in_hubs = name in hub_by_K[K]
            if in_hubs:
                if gap:
                    fill = "#27AE60"; edge = "#0F4D2A"; mark = "✓"
                    n_fixes_gap[K] += 1
                else:
                    fill = "#888"; edge = "#444"; mark = "●"
                    n_redundant[K] += 1
                ax_mat.add_patch(FancyBboxPatch(
                    (x - 0.022, y - 0.015), 0.044, 0.030,
                    boxstyle="round,pad=0.003",
                    linewidth=1.0, edgecolor=edge, facecolor=fill,
                    transform=ax_mat.transAxes, zorder=2))
                ax_mat.text(x, y, mark, fontsize=10, color="white",
                            fontweight="bold", ha="center", va="center",
                            zorder=3)
            else:
                ax_mat.text(x, y, "—", fontsize=10, color="#bbb",
                            ha="center", va="center", zorder=2)

        ax_mat.text(0.96, y, "GAP" if gap else "—",
                    fontsize=9, ha="right", va="center",
                    color="#C0392B" if gap else "#7CB87C",
                    fontweight="bold", zorder=2)
        y -= row_h

    # Summary bar
    y -= 0.005
    ax_mat.plot([0.0, 1.0], [y, y], color="#aaa", lw=0.7,
                transform=ax_mat.transAxes)
    y -= 0.04
    ax_mat.text(0.0, y, "Hubs placed at GAP depts",
                fontsize=9.5, fontweight="bold", color="#0F4D2A", va="center")
    for K in K_LIST:
        x = col_x[f"K={K}"]
        n_total = n_fixes_gap[K] + n_redundant[K]
        ax_mat.text(x, y, f"{n_fixes_gap[K]}/{n_total}",
                    fontsize=10, fontweight="bold", color="#0F4D2A",
                    ha="center", va="center")
    y -= 0.04
    ax_mat.text(0.0, y, "Hubs that double-up on already-ALS depts",
                fontsize=9.5, fontweight="bold", color="#7A1F12", va="center")
    for K in K_LIST:
        x = col_x[f"K={K}"]
        n_total = n_fixes_gap[K] + n_redundant[K]
        ax_mat.text(x, y, f"{n_redundant[K]}/{n_total}",
                    fontsize=10, fontweight="bold", color="#7A1F12",
                    ha="center", va="center")

    # Callout / takeaway
    y -= 0.085
    callout = (
        "TAKEAWAY: The P-Median optimizer maximizes demand-weighted\n"
        "coverage, so it concentrates hubs at HIGH-VOLUME 24/7 ALS depts\n"
        "(Watertown, Fort Atkinson, Johnson Creek, Jefferson) — places that\n"
        "already have ALS. The actual ALS gaps (Lake Mills, Ixonia, Palmyra,\n"
        "Cambridge — and Waterloo at AEMT only) are LOW-volume and rarely\n"
        "selected. To FIX the gap rather than add surge capacity, the\n"
        "optimization needs a different objective: minimize population WITHOUT\n"
        "24/7 ALS within 14 min, instead of maximizing demand covered."
    )
    ax_mat.text(0.0, y, callout, fontsize=9, color="#111", va="top",
                bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF8E1",
                          edgecolor="#D4B95E", linewidth=0.9))

    fig.suptitle(
        "Coverage Gap vs. Optimization — Are we adding capacity where it's "
        "actually needed?",
        fontsize=14, fontweight="bold", color="#111", y=0.97
    )
    fig.text(
        0.012, 0.012,
        "Source: regenerate_hub_map_2hub.py (service tiers), CY2024 NFIRS night calls, "
        "secondary_network_solutions_totaldemand.csv (PMed solutions K=3-6).",
        fontsize=7.5, color="#666"
    )

    out = os.path.join(SCRIPT_DIR, "coverage_gap_vs_optimization.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.12)
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    build()
