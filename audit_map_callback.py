import sys
import re
sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/patri/OneDrive - UW-Madison/ISYE 450/ems_dashboard_app.py', encoding='utf-8') as f:
    src = f.read()

# Find every @app.callback block and check if it touches map outputs
print("=== Callbacks that touch map components ===")
for m in re.finditer(r'@app\.callback.*?def \w+\(', src, re.DOTALL):
    block = m.group()
    if any(x in block for x in ['map-markers', 'map-legend', 'map-geojson', 'leaflet-map']):
        print(block[:500])
        print("---")

# Check for trackViewport
print("\ntrackViewport in source:", 'trackViewport' in src)

# Check for any viewport Input
vp_inputs = re.findall(r'Input\([^)]*viewport[^)]*\)', src)
print("viewport Input calls:", vp_inputs)

# Check for zoom in Input
zoom_inputs = re.findall(r'Input\([^)]*["\']zoom["\'][^)]*\)', src)
print("zoom prop Input calls:", zoom_inputs)

# Check for zoomend in Input
ze_inputs = re.findall(r'Input\([^)]*zoomend[^)]*\)', src)
print("zoomend Input calls:", ze_inputs)

# Check for any badge/tier text
badge_strs = re.findall(r'(Department View|City.Town View|ZIP.*?View|tier.badge|map-tier)', src)
print("badge/tier strings:", badge_strs)

# Check if CITY_DATA and ZIP_DATA are actually used inside update_map
cb_start = src.find('def update_map(')
cb_end = src.find('\n@app.callback', cb_start)
cb_body = src[cb_start:cb_end]
print("\n=== update_map body (first 1200 chars) ===")
print(cb_body[:1200])
