"""One-shot PNG export of the UW-styled Hourly Demand chart.

Pulls the same function + data the staffing dashboard uses so the exported
image is identical to what the dashboard renders.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("sd", ROOT / "staffing_dashboard.py")
sd = importlib.util.module_from_spec(spec)
sys.modules["sd"] = sd
spec.loader.exec_module(sd)

fig = sd.update_county_stacked(0)
# Bump size so text is crisp when screenshotted
fig.update_layout(width=1400, height=760)
out = ROOT / "hourly_demand_by_department_UW.png"
fig.write_image(str(out), scale=2)
print(f"Saved: {out}")
