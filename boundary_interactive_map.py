"""
Jefferson County EMS — Interactive Isochrone & Boundary Map
===========================================================
Generates an HTML map with:
  - Real road basemap (OpenStreetMap + optional satellite)
  - EMS district boundaries (from county GIS)
  - Drive-time isochrones (8/14/20 min from ORS)
  - Station markers with popups
  - Layer controls to toggle each layer on/off

Opens in any browser. No server needed.
"""

import json
import os
import folium
from folium.plugins import GroupedLayerControl

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── File paths ─────────────────────────────────────────────────────────────
ISOCHRONE_FILE = os.path.join(SCRIPT_DIR, "boundary_isochrones.geojson")
EMS_DISTRICTS_FILE = os.path.join(SCRIPT_DIR, "jefferson_ems_districts.geojson")
COUNTY_BOUNDARY_FILE = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
STATIONS_FILE = os.path.join(SCRIPT_DIR, "jefferson_stations.geojson")

# ── Station data (same as boundary_optimization.py) ───────────────────────
STATIONS = [
    {"Dept": "Watertown",     "EMS_Calls": 1947, "FT": 31, "PT":  3, "Pop": 23000, "Level": "ALS",  "Model": "Career",      "Expense": 3833800, "Cross": True,  "Lat": 43.1861, "Lon": -88.7339},
    {"Dept": "Fort Atkinson", "EMS_Calls": 1621, "FT": 16, "PT": 28, "Pop": 16300, "Level": "ALS",  "Model": "Career+PT",   "Expense":  760950, "Cross": False, "Lat": 42.9271, "Lon": -88.8397},
    {"Dept": "Whitewater",    "EMS_Calls": 1448, "FT": 15, "PT": 17, "Pop":  4296, "Level": "ALS",  "Model": "Career+PT",   "Expense": 2710609, "Cross": True,  "Lat": 42.8325, "Lon": -88.7332},
    {"Dept": "Edgerton",      "EMS_Calls": 2035, "FT": 24, "PT":  0, "Pop":  3763, "Level": "ALS",  "Model": "Career+PT",   "Expense":  704977, "Cross": True,  "Lat": 42.8403, "Lon": -89.0629},
    {"Dept": "Jefferson",     "EMS_Calls":   91, "FT":  6, "PT": 20, "Pop":  7800, "Level": "ALS",  "Model": "Career",      "Expense": 1500300, "Cross": False, "Lat": 43.0056, "Lon": -88.8014},
    {"Dept": "Johnson Creek", "EMS_Calls":  454, "FT":  3, "PT": 40, "Pop":  3367, "Level": "ALS",  "Model": "Volunteer",   "Expense": 1134154, "Cross": False, "Lat": 43.0753, "Lon": -88.7745},
    {"Dept": "Waterloo",      "EMS_Calls":  403, "FT":  4, "PT": 22, "Pop":  4415, "Level": "AEMT", "Model": "Career+Vol",  "Expense": 1102475, "Cross": True,  "Lat": 43.1886, "Lon": -88.9797},
    {"Dept": "Lake Mills",    "EMS_Calls": None, "FT":  4, "PT": 20, "Pop":  8700, "Level": "BLS",  "Model": "Career+Vol",  "Expense":  347000, "Cross": False, "Lat": 43.0781, "Lon": -88.9144},
    {"Dept": "Ixonia",        "EMS_Calls":  260, "FT":  2, "PT": 45, "Pop":  5078, "Level": "BLS",  "Model": "Volunteer+FT","Expense":  631144, "Cross": False, "Lat": 43.1446, "Lon": -88.5970},
    {"Dept": "Palmyra",       "EMS_Calls":  105, "FT":  0, "PT": 20, "Pop":  3341, "Level": "BLS",  "Model": "Volunteer",   "Expense":  817740, "Cross": False, "Lat": 42.8794, "Lon": -88.5855},
    {"Dept": "Cambridge",     "EMS_Calls":   64, "FT":  0, "PT": 31, "Pop":  1650, "Level": "ALS",  "Model": "Volunteer",   "Expense":   92000, "Cross": True,  "Lat": 43.0049, "Lon": -89.0224},
    {"Dept": "Helenville",    "EMS_Calls": None, "FT":  0, "PT": 13, "Pop":  1500, "Level": "BLS",  "Model": "Volunteer",   "Expense":    None, "Cross": False, "Lat": 43.0135, "Lon": -88.6998},
    {"Dept": "Western Lakes", "EMS_Calls": None, "FT":  0, "PT":  0, "Pop":  2974, "Level": "ALS",  "Model": "Career+PT",   "Expense":    None, "Cross": True,  "Lat": 43.0110, "Lon": -88.5877},
]

LEVEL_COLORS = {
    "ALS": "#e74c3c",
    "AEMT": "#f39c12",
    "BLS": "#3498db",
}

ISO_COLORS = {
    8:  "#e74c3c",
    14: "#f39c12",
    20: "#27ae60",
}

# Distinct colors for EMS district boundaries
DISTRICT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78",
]


def build_map():
    # Center on Jefferson County
    center = [43.02, -88.77]
    m = folium.Map(
        location=center,
        zoom_start=10,
        tiles=None,  # we'll add tiles manually for layer control
    )

    # ── Basemap tiles ──────────────────────────────────────────────────────
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        name="OpenStreetMap (Roads)",
        attr="OpenStreetMap contributors",
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Satellite (Esri)",
        attr="Esri, Maxar, Earthstar Geographics",
    ).add_to(m)

    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        name="Light (CartoDB)",
        attr="CartoDB",
    ).add_to(m)

    # ── County boundary ────────────────────────────────────────────────────
    if os.path.exists(COUNTY_BOUNDARY_FILE):
        county_group = folium.FeatureGroup(name="County Boundary", show=True)
        with open(COUNTY_BOUNDARY_FILE, "r") as f:
            county_geo = json.load(f)
        folium.GeoJson(
            county_geo,
            style_function=lambda x: {
                "fillColor": "transparent",
                "color": "#333333",
                "weight": 3,
                "dashArray": "8 4",
            },
            name="County Boundary",
        ).add_to(county_group)
        county_group.add_to(m)

    # ── EMS district boundaries ────────────────────────────────────────────
    if os.path.exists(EMS_DISTRICTS_FILE):
        districts_group = folium.FeatureGroup(name="EMS District Boundaries", show=True)
        with open(EMS_DISTRICTS_FILE, "r") as f:
            ems_geo = json.load(f)

        # Assign a color per district
        for i, feat in enumerate(ems_geo["features"]):
            color = DISTRICT_COLORS[i % len(DISTRICT_COLORS)]
            label = feat["properties"].get("MAPLABEL", f"District {i+1}")

            folium.GeoJson(
                feat,
                style_function=lambda x, c=color: {
                    "fillColor": c,
                    "fillOpacity": 0.08,
                    "color": c,
                    "weight": 2.5,
                },
                tooltip=folium.Tooltip(label, sticky=True),
            ).add_to(districts_group)

        districts_group.add_to(m)

    # ── Isochrone layers (one group per threshold) ─────────────────────────
    if os.path.exists(ISOCHRONE_FILE):
        with open(ISOCHRONE_FILE, "r") as f:
            iso_geo = json.load(f)

        for thresh_min in [20, 14, 8]:
            show_default = thresh_min in (8, 14)
            group = folium.FeatureGroup(
                name=f"Drive-time: {thresh_min} min",
                show=show_default,
            )
            color = ISO_COLORS.get(thresh_min, "#888888")
            opacity = {8: 0.25, 14: 0.15, 20: 0.08}.get(thresh_min, 0.1)

            for feat in iso_geo["features"]:
                if feat["properties"].get("threshold_min") != thresh_min:
                    continue
                dept = feat["properties"].get("department", "Unknown")

                folium.GeoJson(
                    feat,
                    style_function=lambda x, c=color, o=opacity: {
                        "fillColor": c,
                        "fillOpacity": o,
                        "color": c,
                        "weight": 1,
                        "opacity": 0.4,
                    },
                    tooltip=folium.Tooltip(
                        f"{dept} - {thresh_min} min drive",
                        sticky=True,
                    ),
                ).add_to(group)

            group.add_to(m)

    # ── Station markers ────────────────────────────────────────────────────
    stations_group = folium.FeatureGroup(name="EMS Stations", show=True)

    for s in STATIONS:
        color = LEVEL_COLORS.get(s["Level"], "#888888")
        calls_str = str(s["EMS_Calls"]) if s["EMS_Calls"] is not None else "N/A"
        expense_str = f"${s['Expense']:,.0f}" if s["Expense"] is not None else "N/A"
        cross_str = " (CROSS-COUNTY)" if s["Cross"] else ""

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 220px;">
            <h4 style="margin:0 0 8px 0; color:{color};">{s['Dept']}{cross_str}</h4>
            <table style="font-size:12px; border-collapse:collapse;">
                <tr><td style="padding:2px 8px 2px 0;"><b>Service Level:</b></td><td>{s['Level']}</td></tr>
                <tr><td style="padding:2px 8px 2px 0;"><b>Staffing Model:</b></td><td>{s['Model']}</td></tr>
                <tr><td style="padding:2px 8px 2px 0;"><b>FT / PT Staff:</b></td><td>{s['FT']} / {s['PT']}</td></tr>
                <tr><td style="padding:2px 8px 2px 0;"><b>EMS Calls (2024):</b></td><td>{calls_str}</td></tr>
                <tr><td style="padding:2px 8px 2px 0;"><b>Pop Served:</b></td><td>{s['Pop']:,}</td></tr>
                <tr><td style="padding:2px 8px 2px 0;"><b>Total Expense:</b></td><td>{expense_str}</td></tr>
            </table>
        </div>
        """

        # Icon size scaled by call volume
        radius = 8 if s["EMS_Calls"] is None else max(6, min(18, s["EMS_Calls"] / 150))

        folium.CircleMarker(
            location=[s["Lat"], s["Lon"]],
            radius=radius,
            color="#333" if not s["Cross"] else "#e67e22",
            weight=3 if s["Cross"] else 2,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=folium.Tooltip(
                f"{s['Dept']} ({s['Level']}) - {calls_str} calls",
                sticky=True,
            ),
        ).add_to(stations_group)

    stations_group.add_to(m)

    # ── Layer control ──────────────────────────────────────────────────────
    folium.LayerControl(collapsed=False).add_to(m)

    # ── Title overlay ──────────────────────────────────────────────────────
    title_html = """
    <div style="position:fixed; top:10px; left:60px; z-index:9999;
                background:white; padding:10px 16px; border-radius:8px;
                box-shadow:0 2px 6px rgba(0,0,0,0.3); font-family:Arial,sans-serif;">
        <h3 style="margin:0 0 4px 0;">Jefferson County EMS - Drive-Time Coverage</h3>
        <p style="margin:0; font-size:12px; color:#666;">
            Isochrones: OpenRouteService (OSM road network) |
            Districts: Jefferson Co. GIS |
            Data: CY2024 NFIRS / FY2025 Budgets
        </p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # ── Legend ──────────────────────────────────────────────────────────────
    legend_html = """
    <div style="position:fixed; bottom:30px; right:10px; z-index:9999;
                background:white; padding:12px 16px; border-radius:8px;
                box-shadow:0 2px 6px rgba(0,0,0,0.3); font-family:Arial,sans-serif;
                font-size:12px; line-height:1.6;">
        <b>Station Service Level</b><br>
        <span style="color:#e74c3c;">&#9679;</span> ALS (Paramedic)<br>
        <span style="color:#f39c12;">&#9679;</span> AEMT<br>
        <span style="color:#3498db;">&#9679;</span> BLS (Basic)<br>
        <span style="color:#e67e22;">&#9675;</span> Cross-county dept<br>
        <hr style="margin:6px 0;">
        <b>Drive-Time Zones</b><br>
        <span style="background:#e74c3c; opacity:0.5; padding:0 8px;">&nbsp;</span> 8 min (NFPA 1710)<br>
        <span style="background:#f39c12; opacity:0.5; padding:0 8px;">&nbsp;</span> 14 min (NFPA 1720)<br>
        <span style="background:#27ae60; opacity:0.5; padding:0 8px;">&nbsp;</span> 20 min (extended)<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ── Save ───────────────────────────────────────────────────────────────
    output = os.path.join(SCRIPT_DIR, "boundary_coverage_map.html")
    m.save(output)
    print(f"  [OK] Saved: {output}")
    print(f"       Open in browser to explore interactively.")
    return output


if __name__ == "__main__":
    print("=" * 60)
    print("BUILDING INTERACTIVE COVERAGE MAP")
    print("=" * 60)
    build_map()
