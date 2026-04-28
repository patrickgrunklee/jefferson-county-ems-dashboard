"""
Baseline state isochrone map — all 13 existing primary stations rendered
in the same presentation style as secondary_isochrone_map_K{3,4,5,6}_presentation.

Watercolor reds, county outline, municipal/township boundaries, city labels,
lat/lon axes. Intended to sit next to the K=3-6 proposed scenarios in the deck.

Output: baseline_isochrone_map_presentation.png
"""
import os, json, time, requests
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
COUNTY_GJ  = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")

# Theme (same as K=3-6 maps)
CLR_EXISTING_STATION = "#4A9B9B"
CLR_COUNTY_OUTLINE   = "#2B2B2B"
CLR_COUNTY_FILL      = "#FAFAFA"

THRESHOLDS = [
    ("20", "#F8B4B4", 0.42, "#D15454", 0.30, "<= 20 min"),
    ("14", "#E63939", 0.42, "#9C1818", 0.35, "<= 14 min"),
    ("8",  "#7A0000", 0.55, "#4A0000", 0.40, "<=  8 min"),
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
    # Helenville excluded — first-responder agency, 0 ambulances; transport via Jefferson EMS.
]


def load_station_iso(name):
    """Load cached isochrone dict for a station (keys '8','14','20')."""
    fname = name.replace(" ", "_") + ".json"
    path  = os.path.join(CACHE_DIR, fname)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def plot_polygon(ax, geom, fill, alpha, edge, lw, zorder):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color=fill, alpha=alpha, zorder=zorder, linewidth=0)
            ax.plot(xs, ys, color=edge, linewidth=lw, alpha=0.45,
                    zorder=zorder + 0.1)


def build():
    county_geo = json.load(open(COUNTY_GJ))
    fig, ax = plt.subplots(figsize=(14, 11.5))
    ax.set_facecolor("white")

    # County fill + outline
    for feat in county_geo["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0] if geom["type"] == "MultiPolygon" else poly
            xs = [pt[0] for pt in ring]
            ys = [pt[1] for pt in ring]
            ax.fill(xs, ys, color=CLR_COUNTY_FILL, zorder=1)
            ax.plot(xs, ys, color=CLR_COUNTY_OUTLINE, linewidth=1.6, zorder=2.5)

    # Isochrone layers for all 13 existing stations (outer -> inner)
    isos = {}
    for sta in STATIONS:
        iso = load_station_iso(sta["name"])
        if iso is not None:
            isos[sta["name"]] = iso

    for thresh, fill, alpha, edge, lw, _ in THRESHOLDS:
        for name, iso in isos.items():
            if thresh in iso:
                plot_polygon(ax, iso[thresh]["geometry"],
                             fill=fill, alpha=alpha,
                             edge=edge, lw=lw, zorder=3)

    # Existing stations — teal circles + city labels (simple NE offset,
    # no proposed-square collisions to avoid here)
    for sta in STATIONS:
        ax.scatter(sta["lon"], sta["lat"], marker="o", s=110,
                   c=CLR_EXISTING_STATION, edgecolors=CLR_EXISTING_STATION,
                   linewidths=0, zorder=8)
        # Manual offsets for a few that crowd each other
        custom = {
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
        ox, oy, ha = custom.get(sta["name"], (10, 5, "left"))
        ax.annotate(sta["name"], (sta["lon"], sta["lat"]),
                    xytext=(ox, oy), textcoords="offset points",
                    fontsize=8.5, color="#1a1a1a", fontweight="semibold",
                    ha=ha, va="center", zorder=9)

    # Legend — 3 bands + 1 marker type
    handles = []
    for thresh, fill, alpha, edge, lw, label in THRESHOLDS:
        handles.append(Patch(facecolor=fill, alpha=alpha + 0.2,
                             edgecolor=edge, linewidth=lw, label=label))
    handles.append(Line2D([0], [0], marker="o", color="w",
                          markerfacecolor=CLR_EXISTING_STATION,
                          markeredgecolor=CLR_EXISTING_STATION,
                          markersize=12, markeredgewidth=0,
                          label="Existing station"))
    ax.legend(handles=handles, loc="upper left", fontsize=12,
              framealpha=0.95, edgecolor="#bbb", frameon=True,
              handlelength=2.3, handleheight=1.3)

    # Bounds
    lons = [s["lon"] for s in STATIONS]
    lats = [s["lat"] for s in STATIONS]
    ax.set_xlim(min(lons) - 0.08, max(lons) + 0.08)
    ax.set_ylim(min(lats) - 0.05, max(lats) + 0.05)
    ax.set_aspect("equal")

    # Coordinate-graph chrome
    ax.grid(True, which="major", color="#cfcfcf", linewidth=0.5, alpha=0.55, zorder=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="major", labelsize=9, colors="#555",
                   length=4, width=0.6, direction="out")
    ax.set_xlabel("Longitude", fontsize=10, color="#444", labelpad=6)
    ax.set_ylabel("Latitude",  fontsize=10, color="#444", labelpad=6)
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_color("#999"); sp.set_linewidth(0.6)

    out = os.path.join(SCRIPT_DIR, "baseline_isochrone_map_presentation.png")
    fig.savefig(out, dpi=220, bbox_inches="tight", facecolor="white", pad_inches=0.1)
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    build()
