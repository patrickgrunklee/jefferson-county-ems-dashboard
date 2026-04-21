"""
Generate a light-mode presentation map of Jefferson County EMS districts.
Outputs: slide_map.html (interactive) + slide_map.png (screenshot for slides).

Shows:
 - Municipality boundaries colored by EMS department
 - Station markers sized by call volume
 - Department labels
 - Clean, light basemap suitable for presentations
"""

import json, math, os
import folium
from folium.features import GeoJsonTooltip

BASE = os.path.dirname(os.path.abspath(__file__))
GEOJSON = os.path.join(BASE, "jefferson_county.geojson")

# ── Department → NAMELSAD mapping (mirrors dashboard) ────────────────────────
DEPT_TO_NAMELSAD = {
    "Waterloo":      ["Waterloo city", "Waterloo town"],
    "Johnson Creek": ["Johnson Creek village", "Aztalan town", "Farmington town", "Milford town"],
    "Ixonia":        ["Ixonia town", "Lac La Belle village"],
    "Watertown":     ["Watertown city", "Watertown town"],
    "Lake Mills":    ["Lake Mills city", "Lake Mills town"],
    "Cambridge":     ["Cambridge village"],
    "Jefferson":     ["Jefferson city", "Jefferson town", "Hebron town"],
    # Sullivan town + village are fire-only served by Sullivan VFD; EMS by Western Lakes.
    "Western Lakes": ["Oakland town", "Concord town", "Sullivan town", "Sullivan village"],
    # Sumner town shared w/ Edgerton; Fort Atkinson has larger pop share
    "Fort Atkinson": ["Fort Atkinson city", "Koshkonong town", "Sumner town"],
    # Cold Spring town was formerly under Rome VFD (fire-only); EMS by Whitewater
    "Whitewater":    ["Whitewater city", "Cold Spring town"],
    "Palmyra":       ["Palmyra village", "Palmyra town"],
    "Edgerton":      [],
    "Helenville":    [],
}

# Reverse lookup
namelsad_to_dept = {}
for dept, names in DEPT_TO_NAMELSAD.items():
    for n in names:
        namelsad_to_dept[n] = dept

# ── Station coordinates & 2024 NFIRS call volumes ────────────────────────────
STATIONS = {
    #  dept:          (lat,       lon,      total_calls)  — from county_ems_comparison_data.xlsx
    "Cambridge":     (43.0038, -89.0177,    197),
    "Edgerton":      (42.8335, -89.0694,   2472),
    "Fort Atkinson": (42.9271, -88.8399,   2076),
    "Helenville":    (43.0119, -88.6995,     16),
    "Ixonia":        (43.1449, -88.6003,    338),
    "Jefferson":     (43.0026, -88.8075,    238),
    "Johnson Creek": (43.0819, -88.7759,    636),
    "Lake Mills":    (43.0783, -88.9113,      0),  # No NFIRS data submitted
    "Palmyra":       (42.8778, -88.5862,     35),
    "Waterloo":      (43.1815, -88.9904,    520),
    "Watertown":     (43.1959, -88.7235,   2719),
    "Western Lakes": (43.0295, -88.5968,   6581),
    "Whitewater":    (42.8321, -88.7333,   1812),
}

max_calls = max(v[2] for v in STATIONS.values())

# ── Color palette — distinct, presentation-friendly, colorblind-safe ─────────
DEPT_COLORS = {
    "Cambridge":     "#4e79a7",  # steel blue
    "Edgerton":      "#f28e2b",  # orange
    "Fort Atkinson": "#e15759",  # red
    "Helenville":    "#76b7b2",  # teal
    "Ixonia":        "#59a14f",  # green
    "Jefferson":     "#edc948",  # gold
    "Johnson Creek": "#b07aa1",  # purple
    "Lake Mills":    "#ff9da7",  # pink
    "Palmyra":       "#9c755f",  # brown
    "Waterloo":      "#8cd17d",  # light green
    "Watertown":     "#a0cbe8",  # light blue
    "Western Lakes": "#d4a6c8",  # lavender
    "Whitewater":    "#fabfd2",  # light pink
}
DEFAULT_COLOR = "#d9d9d9"  # unassigned areas

# ── Load GeoJSON and inject department ────────────────────────────────────────
with open(GEOJSON) as f:
    geo = json.load(f)

for feat in geo["features"]:
    p = feat["properties"]
    namelsad = p.get("NAMELSAD", p.get("NAME", ""))
    dept = namelsad_to_dept.get(namelsad, None)
    p["dept"] = dept or ""

# ── Build map ─────────────────────────────────────────────────────────────────
m = folium.Map(
    location=[43.02, -88.78],
    zoom_start=10,
    tiles=None,  # we add our own
    width="100%",
    height="100%",
)

# Light basemap — CartoDB Positron (clean, minimal labels)
folium.TileLayer(
    tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attr='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
    name="CartoDB Positron",
    max_zoom=19,
).add_to(m)


def style_function(feature):
    dept = feature["properties"].get("dept", "")
    return {
        "fillColor": DEPT_COLORS.get(dept, DEFAULT_COLOR),
        "color": "#555555",       # border
        "weight": 1.5,
        "fillOpacity": 0.50,
    }


def highlight_function(feature):
    return {
        "fillOpacity": 0.7,
        "weight": 3,
    }


# Add municipality polygons
folium.GeoJson(
    geo,
    name="Municipalities",
    style_function=style_function,
    highlight_function=highlight_function,
    tooltip=GeoJsonTooltip(
        fields=["dept", "NAMELSAD"],
        aliases=["Department:", "Municipality:"],
        style="font-size:13px; font-weight:bold;",
    ),
).add_to(m)

# ── Add station markers (sized by call volume) ───────────────────────────────
for dept, (lat, lon, calls) in STATIONS.items():
    # Radius: 5-18px scaled by sqrt of call volume
    radius = max(4, 5 + 13 * math.sqrt(calls / max_calls)) if calls > 0 else 4
    color = DEPT_COLORS.get(dept, "#333")
    label = f"{calls:,} calls" if calls > 0 else "No NFIRS data"

    folium.CircleMarker(
        location=[lat, lon],
        radius=radius,
        color="#333333",
        weight=1.5,
        fill=True,
        fill_color=color if calls > 0 else "#cccccc",
        fill_opacity=0.85 if calls > 0 else 0.5,
        tooltip=f"<b>{dept}</b><br>{label} (2024)",
    ).add_to(m)

    # Department label (offset slightly above the marker)
    folium.Marker(
        location=[lat + 0.012, lon],
        icon=folium.DivIcon(
            html=f'<div style="font-size:10px; font-weight:600; color:#222; '
                 f'text-align:center; white-space:nowrap; '
                 f'text-shadow: 1px 1px 2px #fff, -1px -1px 2px #fff, 1px -1px 2px #fff, -1px 1px 2px #fff;">'
                 f'{dept}</div>',
            icon_size=(120, 20),
            icon_anchor=(60, 10),
        ),
    ).add_to(m)

# ── Legend ─────────────────────────────────────────────────────────────────────
legend_html = """
<div style="
    position: fixed;
    bottom: 30px; left: 30px;
    background: white; border: 2px solid #888;
    border-radius: 6px; padding: 12px 16px;
    font-size: 12px; line-height: 1.6;
    z-index: 9999; max-height: 400px; overflow-y: auto;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
">
<b style="font-size:13px;">EMS Departments</b><br>
"""
# Sort by call volume descending for the legend
sorted_depts = sorted(STATIONS.items(), key=lambda x: -x[1][2])
for dept, (_, _, calls) in sorted_depts:
    c = DEPT_COLORS.get(dept, DEFAULT_COLOR)
    call_label = f"{calls:,}" if calls > 0 else "N/A"
    legend_html += (
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'background:{c};border:1px solid #555;margin-right:6px;'
        f'vertical-align:middle;border-radius:2px;"></span>'
        f'{dept} ({call_label})<br>'
    )
legend_html += """
<hr style="margin:6px 0;">
<span style="font-size:11px; color:#666;">
Circle size = call volume<br>
Polygons = municipality boundaries<br>
Source: 2024 NFIRS data
</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# ── Title ─────────────────────────────────────────────────────────────────────
title_html = """
<div style="
    position: fixed;
    top: 12px; left: 50%; transform: translateX(-50%);
    background: white; border: 2px solid #888;
    border-radius: 6px; padding: 8px 24px;
    font-size: 18px; font-weight: bold; color: #222;
    z-index: 9999;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
">
Jefferson County EMS — 15 Independent Departments
</div>
"""
m.get_root().html.add_child(folium.Element(title_html))

# ── Save ──────────────────────────────────────────────────────────────────────
out_html = os.path.join(BASE, "slide_map.html")
m.save(out_html)
print(f"Saved interactive map: {out_html}")
print("Open in browser, then screenshot for your slide (or use the PNG export below).")

# Attempt PNG export via selenium if available
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    import time

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--force-device-scale-factor=2")  # retina-quality

    driver = webdriver.Chrome(options=opts)
    driver.get(f"file:///{out_html.replace(os.sep, '/')}")
    time.sleep(3)  # let tiles load

    out_png = os.path.join(BASE, "slide_map.png")
    driver.save_screenshot(out_png)
    driver.quit()
    print(f"Saved PNG screenshot: {out_png}")
except Exception as e:
    print(f"PNG export skipped ({e}). Open {out_html} in a browser and screenshot manually.")
