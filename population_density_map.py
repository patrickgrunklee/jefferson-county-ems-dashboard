"""
Jefferson County — Population Density Map (per square mile)
===========================================================
Uses Census 2020 POP100 and AREALAND from ZCTA GeoJSON.
Produces an interactive Folium choropleth clipped to Jefferson Co ZCTAs.

Author: ISyE 450 Senior Design Team
Date: March 2026
"""

import json
import folium
import branca.colormap as cm
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────
AREA_ZCTA   = "jefferson_area_zcta.geojson"   # full ZCTAs with AREALAND
JEFF_ZCTA   = "jefferson_zcta.geojson"         # Jefferson Co ZCTA list
COUNTY_BDRY = "jefferson_county.geojson"       # municipal subdivisions (county outline)
STATIONS    = "jefferson_stations.geojson"      # fire/EMS stations
OUTPUT      = "population_density_map.html"

SQ_MI = 2_589_988.11  # square meters per square mile

# ── Load data ────────────────────────────────────────────────────────────
with open(AREA_ZCTA, "r") as f:
    area_gj = json.load(f)
with open(JEFF_ZCTA, "r") as f:
    jeff_gj = json.load(f)
with open(COUNTY_BDRY, "r") as f:
    county_gj = json.load(f)

# Load stations if available
try:
    with open(STATIONS, "r") as f:
        stations_gj = json.load(f)
    has_stations = True
except FileNotFoundError:
    has_stations = False

# ── Identify Jefferson County ZCTAs ──────────────────────────────────────
jeff_zctas = {feat["properties"]["ZCTA5"] for feat in jeff_gj["features"]}

# ── Compute density and build filtered GeoJSON ──────────────────────────
density_features = []
density_data = {}

for feat in area_gj["features"]:
    p = feat["properties"]
    zcta = p["ZCTA5"]
    if zcta not in jeff_zctas:
        continue

    pop = p["POP100"]
    area_sqmi = float(p["AREALAND"]) / SQ_MI
    density = pop / area_sqmi if area_sqmi > 0 else 0

    # Enrich properties
    feat["properties"]["density_sqmi"] = round(density, 1)
    feat["properties"]["area_sqmi"] = round(area_sqmi, 2)
    feat["properties"]["population"] = pop

    density_features.append(feat)
    density_data[zcta] = density

# Build filtered GeoJSON
density_geojson = {
    "type": "FeatureCollection",
    "features": density_features,
}

# ── Color scale ──────────────────────────────────────────────────────────
densities = [v for v in density_data.values() if v > 0]
vmin = 0
vmax = 800  # cap for readability (a few urban ZCTAs are >1000)

colormap = cm.LinearColormap(
    colors=["#ffffcc", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#0c2c84"],
    vmin=vmin,
    vmax=vmax,
    caption="Population Density (people per sq mi) — Census 2020",
)

def style_function(feature):
    d = feature["properties"].get("density_sqmi", 0)
    return {
        "fillColor": colormap(min(d, vmax)),
        "color": "#333",
        "weight": 1,
        "fillOpacity": 0.7,
    }

def highlight_function(feature):
    return {
        "weight": 3,
        "color": "#000",
        "fillOpacity": 0.85,
    }

# ── Build map ────────────────────────────────────────────────────────────
center = [43.00, -88.77]  # Jefferson County center
m = folium.Map(location=center, zoom_start=10, tiles="cartodbpositron")

# ZCTA choropleth layer
zcta_layer = folium.GeoJson(
    density_geojson,
    name="Population Density by ZIP Code",
    style_function=style_function,
    highlight_function=highlight_function,
    tooltip=folium.GeoJsonTooltip(
        fields=["ZCTA5", "population", "area_sqmi", "density_sqmi"],
        aliases=["ZIP Code:", "Population:", "Area (sq mi):", "Density (per sq mi):"],
        localize=True,
        sticky=True,
        style="font-size: 13px;",
    ),
)
zcta_layer.add_to(m)

# County municipal boundaries overlay (thin outline)
county_style = {
    "fillColor": "transparent",
    "color": "#d32f2f",
    "weight": 2,
    "dashArray": "5 3",
}
county_layer = folium.GeoJson(
    county_gj,
    name="Municipal Boundaries",
    style_function=lambda x: county_style,
    tooltip=folium.GeoJsonTooltip(
        fields=["NAMELSAD"],
        aliases=["Municipality:"],
        sticky=True,
        style="font-size: 13px;",
    ),
)
county_layer.add_to(m)

# EMS/Fire stations
if has_stations:
    station_group = folium.FeatureGroup(name="EMS/Fire Stations")
    for feat in stations_gj["features"]:
        p = feat["properties"]
        coords = feat["geometry"]["coordinates"]
        name = p.get("name", p.get("Name", "Station"))
        folium.CircleMarker(
            location=[coords[1], coords[0]],
            radius=6,
            color="#d32f2f",
            fill=True,
            fill_color="#ff5252",
            fill_opacity=0.9,
            popup=name,
            tooltip=name,
        ).add_to(station_group)
    station_group.add_to(m)

# Add colormap legend
colormap.add_to(m)

# Layer control
folium.LayerControl(collapsed=False).add_to(m)

# Title
title_html = """
<div style="position: fixed; top: 10px; left: 60px; z-index: 1000;
            background: white; padding: 10px 18px; border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-family: Arial, sans-serif;">
    <h3 style="margin: 0 0 4px 0; color: #1a237e;">Jefferson County — Population Density</h3>
    <p style="margin: 0; font-size: 12px; color: #555;">
        Census 2020 &nbsp;|&nbsp; People per square mile by ZIP code (ZCTA)
    </p>
</div>
"""
m.get_root().html.add_child(folium.Element(title_html))

# ── Save ─────────────────────────────────────────────────────────────────
m.save(OUTPUT)
print(f"Saved: {OUTPUT}")
print(f"  {len(density_features)} ZCTAs mapped")
print(f"  Density range: {min(densities):.0f} - {max(densities):.0f} per sq mi")
print(f"  Median density: {sorted(densities)[len(densities)//2]:.0f} per sq mi")
