"""Export the data behind the 'Hourly Demand by Department' chart.

Uses the exact same in-memory objects the dashboard builds (_dept_hourly_all),
so the CSV matches the chart 1:1. Writes two shapes:
  - long  : Dept, Hour, Calls      (one row per dept-hour)
  - wide  : Hour, <Dept>, ...      (one row per hour, dept columns)
"""
import importlib.util
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("sd", ROOT / "staffing_dashboard.py")
sd = importlib.util.module_from_spec(spec)
sys.modules["sd"] = sd
spec.loader.exec_module(sd)

long_rows = []
for dept, series in sd._dept_hourly_all.items():
    for hour, n in series.items():
        long_rows.append({"Dept": dept, "Hour": int(hour), "Calls": int(n)})
long_df = pd.DataFrame(long_rows).sort_values(["Dept", "Hour"]).reset_index(drop=True)

wide_df = long_df.pivot(index="Hour", columns="Dept", values="Calls").fillna(0).astype(int)
wide_df["Total"] = wide_df.sum(axis=1)
wide_df = wide_df.reset_index()

long_out = ROOT / "hourly_demand_by_department_long.csv"
wide_out = ROOT / "hourly_demand_by_department_wide.csv"
long_df.to_csv(long_out, index=False)
wide_df.to_csv(wide_out, index=False)
print(f"Saved: {long_out.name}  ({len(long_df)} rows)")
print(f"Saved: {wide_out.name}  ({len(wide_df)} rows x {wide_df.shape[1]} cols)")
print(f"\nTotal EMS calls in chart: {long_df['Calls'].sum():,}")
