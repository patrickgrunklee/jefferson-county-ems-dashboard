"""
Jefferson County — Block Group Population Density Map
=====================================================
Downloads Census TIGER block group boundaries + 2020 Decennial population,
joins them, computes density per sq mi, and builds an interactive Folium map.

Author: ISyE 450 Senior Design Team
Date: March 2026
"""

import geopandas as gpd
import pandas as pd
import requests
import json
import folium
import branca.colormap as cm
import os
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(SCRIPT_DIR)

TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER2022/BG/tl_2022_55_bg.zip"
POP_URL   = ("https://api.census.gov/data/2020/dec/pl"
             "?get=NAME,P1_001N&for=block%20group:*&in=state:55%20county:055")

COUNTY_BDRY = os.path.join(SCRIPT_DIR, "jefferson_county.geojson")
STATIONS    = os.path.join(SCRIPT_DIR, "jefferson_stations.geojson")
OUTPUT_GJ   = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")
OUTPUT_HTML = os.path.join(SCRIPT_DIR, "population_density_bg_map.html")

SQ_MI = 2_589_988.11  # sq meters per sq mile

# ── 1. Download & filter TIGER block groups ──────────────────────────────
print("Downloading TIGER block group shapefile for Wisconsin...")
gdf = gpd.read_file(TIGER_URL)
gdf_jeff = gdf[gdf["COUNTYFP"] == "055"].copy()
gdf_jeff["GEOID_BG"] = (
    gdf_jeff["STATEFP"] + gdf_jeff["COUNTYFP"] +
    gdf_jeff["TRACTCE"] + gdf_jeff["BLKGRPCE"]
)
print(f"  {len(gdf_jeff)} block groups in Jefferson County")

# ── 2. Pull 2020 Decennial population ────────────────────────────────────
print("Fetching 2020 Census population by block group...")
resp = requests.get(POP_URL)
resp.raise_for_status()
data = resp.json()
cols, rows = data[0], data[1:]
df_pop = pd.DataFrame(rows, columns=cols)
df_pop["GEOID_BG"] = (
    df_pop["state"] + df_pop["county"] +
    df_pop["tract"] + df_pop["block group"]
)
df_pop["P1_001N"] = df_pop["P1_001N"].astype(int)
print(f"  {len(df_pop)} block groups with population data")

# ── 3. Join geometry + population ────────────────────────────────────────
gdf_joined = gdf_jeff.merge(df_pop[["GEOID_BG", "P1_001N"]], on="GEOID_BG", how="left")
gdf_joined["P1_001N"] = gdf_joined["P1_001N"].fillna(0).astype(int)
gdf_joined["ALAND"] = gdf_joined["ALAND"].astype(float)
gdf_joined["area_sqmi"] = gdf_joined["ALAND"] / SQ_MI
gdf_joined["density_sqmi"] = gdf_joined.apply(
    lambda r: round(r["P1_001N"] / r["area_sqmi"], 1) if r["area_sqmi"] > 0 else 0,
    axis=1,
)

# Convert to WGS84 for Folium
gdf_joined = gdf_joined.to_crs(epsg=4326)

# Save GeoJSON for reuse
gdf_joined.to_file(OUTPUT_GJ, driver="GeoJSON")
print(f"  Saved: {os.path.basename(OUTPUT_GJ)}")

# ── 4. Build Folium map ─────────────────────────────────────────────────
densities = gdf_joined.loc[gdf_joined["density_sqmi"] > 0, "density_sqmi"].tolist()
print(f"  Density range: {min(densities):.0f} - {max(densities):.0f} per sq mi")
print(f"  Median: {sorted(densities)[len(densities)//2]:.0f} per sq mi")

vmin, vmax = 0, 1200  # cap for color readability

colormap = cm.LinearColormap(
    colors=["#ffffcc", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#0c2c84"],
    vmin=vmin,
    vmax=vmax,
    caption="Population Density (people per sq mi) -- Census 2020 Block Groups",
)

def style_fn(feature):
    d = feature["properties"].get("density_sqmi", 0)
    return {
        "fillColor": colormap(min(d, vmax)),
        "color": "#555",
        "weight": 0.8,
        "fillOpacity": 0.75,
    }

def highlight_fn(feature):
    return {"weight": 3, "color": "#000", "fillOpacity": 0.9}


center = [43.00, -88.77]
m = folium.Map(location=center, zoom_start=10, tiles="cartodbpositron")

# Block group choropleth
with open(OUTPUT_GJ, "r") as f:
    bg_geojson = json.load(f)

folium.GeoJson(
    bg_geojson,
    name="Pop. Density (Block Groups)",
    style_function=style_fn,
    highlight_function=highlight_fn,
    tooltip=folium.GeoJsonTooltip(
        fields=["GEOID_BG", "P1_001N", "area_sqmi", "density_sqmi"],
        aliases=["Block Group:", "Population:", "Area (sq mi):", "Density (per sq mi):"],
        localize=True,
        sticky=True,
        style="font-size: 13px;",
    ),
).add_to(m)

# County municipal boundaries
try:
    with open(COUNTY_BDRY, "r") as f:
        county_gj = json.load(f)
    folium.GeoJson(
        county_gj,
        name="Municipal Boundaries",
        style_function=lambda x: {
            "fillColor": "transparent",
            "color": "#d32f2f",
            "weight": 2,
            "dashArray": "5 3",
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["NAMELSAD"],
            aliases=["Municipality:"],
            sticky=True,
            style="font-size: 13px;",
        ),
    ).add_to(m)
except FileNotFoundError:
    pass

# EMS/Fire stations
try:
    with open(STATIONS, "r") as f:
        stations_gj = json.load(f)
    sg = folium.FeatureGroup(name="EMS/Fire Stations")
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
        ).add_to(sg)
    sg.add_to(m)
except FileNotFoundError:
    pass

colormap.add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

title_html = """
<div style="position: fixed; top: 10px; left: 60px; z-index: 1000;
            background: white; padding: 10px 18px; border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-family: Arial, sans-serif;">
    <h3 style="margin: 0 0 4px 0; color: #1a237e;">Jefferson County -- Population Density</h3>
    <p style="margin: 0; font-size: 12px; color: #555;">
        Census 2020 Decennial &nbsp;|&nbsp; People per square mile by Block Group
    </p>
</div>
"""
m.get_root().html.add_child(folium.Element(title_html))

m.save(OUTPUT_HTML)
print(f"  Saved: {os.path.basename(OUTPUT_HTML)}")
print("Done!")
