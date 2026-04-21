"""
Jefferson County EMS - Interactive Dashboard
Generates a standalone HTML file with Plotly charts comparing all municipalities.
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import os
import json

# ── 1. Load Call Data ─────────────────────────────────────────────────────────
CALL_DIR = "c:/Users/patri/OneDrive - UW-Madison/ISYE 450/ISyE Project/Data and Resources/Call Data/"
files = [f for f in os.listdir(CALL_DIR) if f.endswith(".xlsx")]

dfs = []
for f in files:
    df = pd.read_excel(CALL_DIR + f, engine="openpyxl")
    dfs.append(df)

combined = pd.concat(dfs, ignore_index=True)

# Clean department names to shorter labels
name_map = {
    "CAMBRIDGE COMM FIRE DEPT": "Cambridge",
    "Edgerton Fire Protection Distict": "Edgerton",
    "Fort Atkinson Fire Dept": "Fort Atkinson",
    "Helenville Fire and Rescue District": "Helenville",
    "Town of Ixonia Fire & EMS Dept": "Ixonia",
    "Jefferson Fire Dept": "Jefferson",
    "Johnson Creek Fire Dept": "Johnson Creek",
    "Palmyra Village Fire Dept": "Palmyra",
    # Rome and Sullivan are fire-only — not EMS providers, excluded from analysis
    "Waterloo Fire Dept": "Waterloo",
    "Watertown Fire Dept": "Watertown",
    "Western Lake Fire District": "Western Lakes",
    "Whitewater Fire and EMS": "Whitewater",
}
combined["Department"] = combined["Fire Department Name"].map(name_map).fillna(combined["Fire Department Name"])

# EMS-only subset
ems = combined[combined["Incident Type Code Category Description"].str.startswith("Rescue and EMS", na=False)].copy()

# Response time: cap outliers at 60 min for meaningful stats
rt_clean = combined[combined["Response Time (Minutes)"].between(0, 60)].copy()
ems_rt = ems[ems["Response Time (Minutes)"].between(0, 60)].copy()

# ── 2. Budget Data (manually compiled from PDFs) ──────────────────────────────
budget = pd.DataFrame([
    # municipality, fy, total_expense, total_revenue, net_tax_supported, staffing_model
    {"Municipality": "Ixonia",         "FY": 2024, "Total_Expense": 631144,  "Total_Revenue": 479881,  "Net": 151263,   "Model": "Volunteer+FT"},
    {"Municipality": "Jefferson",      "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Career"},
    {"Municipality": "Watertown",      "FY": 2025, "Total_Expense": 3833800, "Total_Revenue": 886081,  "Net": 2947719,  "Model": "Career"},
    {"Municipality": "Fort Atkinson",  "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Career+PT"},
    {"Municipality": "Whitewater",     "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Career+PT"},
    {"Municipality": "Cambridge",      "FY": 2025, "Total_Expense": 92000,   "Total_Revenue": 0,       "Net": 92000,    "Model": "Volunteer"},
    {"Municipality": "Lake Mills",     "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Career+Vol"},
    {"Municipality": "Waterloo",       "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Career+Vol"},
    {"Municipality": "Johnson Creek",  "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Volunteer"},
    {"Municipality": "Palmyra",        "FY": 2025, "Total_Expense": None,    "Total_Revenue": None,    "Net": None,     "Model": "Volunteer"},
])

# EMS billing rates (2025, resident BLS & ALS transport where available)
billing = pd.DataFrame([
    {"Municipality": "Jefferson",     "BLS_Resident": 1900, "ALS1_Resident": 2150, "ALS2_Resident": 2225, "Mileage": 30},
    {"Municipality": "Fort Atkinson", "BLS_Resident": 1500, "ALS1_Resident": 1700, "ALS2_Resident": 1900, "Mileage": 26},
    {"Municipality": "Watertown",     "BLS_Resident": 1100, "ALS1_Resident": 1300, "ALS2_Resident": 1500, "Mileage": 22},
])

# ── 3. Derived Metrics ────────────────────────────────────────────────────────
# Call volume by department
call_vol = combined.groupby("Department").size().reset_index(name="Total_Calls")
ems_vol  = ems.groupby("Department").size().reset_index(name="EMS_Calls")
call_vol = call_vol.merge(ems_vol, on="Department", how="left")
call_vol["EMS_Pct"] = (call_vol["EMS_Calls"] / call_vol["Total_Calls"] * 100).round(1)
call_vol = call_vol.sort_values("Total_Calls", ascending=False)

# Response time by department (median & 90th percentile)
rt_stats = rt_clean.groupby("Department")["Response Time (Minutes)"].agg(
    Median_RT="median", P90_RT=lambda x: x.quantile(0.9), Count="count"
).reset_index().sort_values("Median_RT")

# EMS response time stats
ems_rt_stats = ems_rt.groupby("Department")["Response Time (Minutes)"].agg(
    Median_RT="median", P90_RT=lambda x: x.quantile(0.9)
).reset_index().sort_values("Median_RT")

# Call volume by hour of day (heat map data)
hour_dept = combined.groupby(["Department", "Alarm Date - Hour of Day"]).size().reset_index(name="Calls")

# Call volume by day of week
dow_order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
dow_dept = combined.groupby(["Department", "Alarm Date - Day of Week"]).size().reset_index(name="Calls")

# Incident type breakdown by department
inc_type = combined.groupby(["Department", "Incident Type Code Category Description"]).size().reset_index(name="Calls")
inc_type_short = inc_type.copy()
inc_type_short["Category"] = inc_type_short["Incident Type Code Category Description"].str.extract(r"^([^(]+)")[0].str.strip()

# Mutual aid
aid = combined[combined["Aid Given or Received Description"].notna()].groupby(
    ["Department", "Aid Given or Received Description"]).size().reset_index(name="Count")

# Month of year trends
combined["Month"] = pd.to_numeric(combined["Alarm Date - Month of Year"], errors="coerce")
month_trend = combined.groupby(["Department", "Month"]).size().reset_index(name="Calls")

# ── 4. Color palette ──────────────────────────────────────────────────────────
depts_sorted = sorted(combined["Department"].unique())
colors = px.colors.qualitative.Plotly + px.colors.qualitative.Set2
color_map = {d: colors[i % len(colors)] for i, d in enumerate(depts_sorted)}

# ── 5. Build Figures ──────────────────────────────────────────────────────────

# --- Fig 1: Total Call Volume (bar) ---
fig_vol = go.Figure()
fig_vol.add_trace(go.Bar(
    x=call_vol["Department"], y=call_vol["Total_Calls"],
    name="Total Calls", marker_color="#1f77b4",
    text=call_vol["Total_Calls"], textposition="outside"
))
fig_vol.add_trace(go.Bar(
    x=call_vol["Department"], y=call_vol["EMS_Calls"],
    name="EMS/Rescue Calls", marker_color="#ff7f0e",
    text=call_vol["EMS_Calls"], textposition="outside"
))
fig_vol.update_layout(
    title="2024 Call Volume by Department — Total vs. EMS/Rescue",
    barmode="group", xaxis_tickangle=-30,
    yaxis_title="Number of Incidents",
    legend=dict(orientation="h", y=1.05),
    height=500
)

# --- Fig 2: EMS % of total calls (bar) ---
fig_emspct = px.bar(
    call_vol.sort_values("EMS_Pct", ascending=False),
    x="Department", y="EMS_Pct",
    text="EMS_Pct",
    title="EMS/Rescue as % of Total Calls by Department",
    labels={"EMS_Pct": "EMS %"},
    color="EMS_Pct",
    color_continuous_scale="Blues"
)
fig_emspct.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_emspct.update_layout(height=450, coloraxis_showscale=False, xaxis_tickangle=-30)

# --- Fig 3: Response Time — Median & P90 ---
fig_rt = go.Figure()
fig_rt.add_trace(go.Bar(
    x=rt_stats["Department"], y=rt_stats["Median_RT"],
    name="Median (minutes)", marker_color="#2ca02c",
    text=rt_stats["Median_RT"].round(1), textposition="outside"
))
fig_rt.add_trace(go.Bar(
    x=rt_stats["Department"], y=rt_stats["P90_RT"],
    name="90th Percentile (minutes)", marker_color="#d62728",
    text=rt_stats["P90_RT"].round(1), textposition="outside"
))
fig_rt.add_hline(y=8, line_dash="dash", line_color="orange",
                 annotation_text="8-min benchmark", annotation_position="right")
fig_rt.update_layout(
    title="Response Times by Department (All Incidents, capped 0-60 min)",
    barmode="group", xaxis_tickangle=-30,
    yaxis_title="Minutes", height=500,
    legend=dict(orientation="h", y=1.05)
)

# --- Fig 4: EMS-only Response Time ---
fig_ems_rt = go.Figure()
fig_ems_rt.add_trace(go.Bar(
    x=ems_rt_stats["Department"], y=ems_rt_stats["Median_RT"],
    name="Median", marker_color="#9467bd",
    text=ems_rt_stats["Median_RT"].round(1), textposition="outside"
))
fig_ems_rt.add_trace(go.Bar(
    x=ems_rt_stats["Department"], y=ems_rt_stats["P90_RT"],
    name="90th Percentile", marker_color="#e377c2",
    text=ems_rt_stats["P90_RT"].round(1), textposition="outside"
))
fig_ems_rt.add_hline(y=8, line_dash="dash", line_color="orange",
                     annotation_text="8-min benchmark", annotation_position="right")
fig_ems_rt.update_layout(
    title="EMS/Rescue Response Times by Department",
    barmode="group", xaxis_tickangle=-30,
    yaxis_title="Minutes", height=500,
    legend=dict(orientation="h", y=1.05)
)

# --- Fig 5: Calls by Hour of Day (heat map) ---
# Pivot
hour_pivot = hour_dept.pivot_table(index="Department", columns="Alarm Date - Hour of Day", values="Calls", fill_value=0)
fig_heat_hour = go.Figure(go.Heatmap(
    z=hour_pivot.values,
    x=[f"{h:02d}:00" for h in hour_pivot.columns],
    y=hour_pivot.index.tolist(),
    colorscale="YlOrRd",
    text=hour_pivot.values,
    texttemplate="%{text}",
    hovertemplate="Department: %{y}<br>Hour: %{x}<br>Calls: %{z}<extra></extra>"
))
fig_heat_hour.update_layout(
    title="Call Volume Heat Map — Hour of Day",
    xaxis_title="Hour of Day", yaxis_title="Department",
    height=500
)

# --- Fig 6: Calls by Day of Week ---
dow_pivot = dow_dept.pivot_table(index="Department", columns="Alarm Date - Day of Week", values="Calls", fill_value=0)
# Reorder columns
present_dow = [d for d in dow_order if d in dow_pivot.columns]
dow_pivot = dow_pivot.reindex(columns=present_dow, fill_value=0)

fig_heat_dow = go.Figure(go.Heatmap(
    z=dow_pivot.values,
    x=dow_pivot.columns.tolist(),
    y=dow_pivot.index.tolist(),
    colorscale="Blues",
    text=dow_pivot.values,
    texttemplate="%{text}",
    hovertemplate="Department: %{y}<br>Day: %{x}<br>Calls: %{z}<extra></extra>"
))
fig_heat_dow.update_layout(
    title="Call Volume Heat Map — Day of Week",
    xaxis_title="Day of Week", yaxis_title="Department",
    height=500
)

# --- Fig 7: Incident Type Breakdown (stacked bar) ---
inc_pivot = inc_type.pivot_table(
    index="Department", columns="Incident Type Code Category Description", values="Calls", fill_value=0
)
inc_pct = inc_pivot.div(inc_pivot.sum(axis=1), axis=0) * 100

cat_colors = px.colors.qualitative.Set2
categories = [c for c in inc_pct.columns]

fig_inc = go.Figure()
for i, cat in enumerate(categories):
    short = cat.split("(")[0].strip()
    fig_inc.add_trace(go.Bar(
        name=short,
        x=inc_pct.index.tolist(),
        y=inc_pct[cat].round(1),
        marker_color=cat_colors[i % len(cat_colors)],
        text=inc_pct[cat].apply(lambda v: f"{v:.0f}%" if v > 3 else ""),
        textposition="inside"
    ))
fig_inc.update_layout(
    title="Incident Type Breakdown by Department (% of Total)",
    barmode="stack", xaxis_tickangle=-30,
    yaxis_title="Percentage (%)",
    legend=dict(orientation="h", yanchor="bottom", y=-0.5, x=0),
    height=550
)

# --- Fig 8: Monthly Call Trends ---
month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
month_trend["Month_Name"] = month_trend["Month"].map(month_names)
month_pivot = month_trend.pivot_table(index="Month", columns="Department", values="Calls", fill_value=0)

fig_monthly = go.Figure()
for dept in month_pivot.columns:
    fig_monthly.add_trace(go.Scatter(
        x=[month_names.get(m, m) for m in month_pivot.index],
        y=month_pivot[dept],
        name=dept,
        mode="lines+markers",
        line=dict(color=color_map.get(dept))
    ))
fig_monthly.update_layout(
    title="Monthly Call Volume Trends by Department",
    xaxis_title="Month", yaxis_title="Number of Calls",
    legend=dict(orientation="h", yanchor="top", y=-0.15, x=0),
    height=500
)

# --- Fig 9: Mutual Aid Summary ---
fig_aid = px.bar(
    aid, x="Department", y="Count", color="Aid Given or Received Description",
    title="Mutual Aid Activity by Department",
    barmode="group",
    color_discrete_sequence=px.colors.qualitative.Pastel
)
fig_aid.update_layout(height=450, xaxis_tickangle=-30,
                      legend=dict(orientation="h", y=1.1))

# --- Fig 10: EMS Billing Rate Comparison ---
fig_bill = go.Figure()
for svc, col, clr in [("BLS Transport", "BLS_Resident", "#1f77b4"),
                       ("ALS1 Transport", "ALS1_Resident", "#ff7f0e"),
                       ("ALS2 Transport", "ALS2_Resident", "#2ca02c")]:
    fig_bill.add_trace(go.Bar(
        name=svc,
        x=billing["Municipality"],
        y=billing[col],
        text=billing[col].apply(lambda v: f"${v:,}"),
        textposition="outside",
        marker_color=clr
    ))
fig_bill.update_layout(
    title="2025 EMS Billing Rates Comparison (Resident, per Transport)",
    barmode="group",
    yaxis_title="Rate ($)",
    height=450,
    legend=dict(orientation="h", y=1.05)
)

# --- Fig 11: Summary KPI table ---
summary_df = call_vol.merge(rt_stats[["Department","Median_RT","P90_RT"]], on="Department", how="left")
summary_df = summary_df.rename(columns={
    "Total_Calls": "Total Calls",
    "EMS_Calls": "EMS Calls",
    "EMS_Pct": "EMS %",
    "Median_RT": "Median RT (min)",
    "P90_RT": "P90 RT (min)"
})
summary_df["Median RT (min)"] = summary_df["Median RT (min)"].round(1)
summary_df["P90 RT (min)"]    = summary_df["P90 RT (min)"].round(1)

fig_table = go.Figure(go.Table(
    header=dict(
        values=["<b>Department</b>","<b>Total Calls</b>","<b>EMS Calls</b>",
                "<b>EMS %</b>","<b>Median RT (min)</b>","<b>P90 RT (min)</b>"],
        fill_color="#2c5f8a", font=dict(color="white", size=12),
        align="center"
    ),
    cells=dict(
        values=[
            summary_df["Department"],
            summary_df["Total Calls"],
            summary_df["EMS Calls"],
            summary_df["EMS %"].apply(lambda v: f"{v:.1f}%"),
            summary_df["Median RT (min)"],
            summary_df["P90 RT (min)"]
        ],
        fill_color=[["#f0f4f8" if i%2==0 else "white" for i in range(len(summary_df))]]*6,
        align="center", font=dict(size=11)
    )
))
fig_table.update_layout(title="County-Wide EMS Summary KPIs", height=500)

# ── 6. Assemble HTML ──────────────────────────────────────────────────────────
def fig_to_html(fig, include_plotlyjs="cdn"):
    return fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs)

html_parts = ["""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Jefferson County EMS Dashboard</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f7fb; margin: 0; padding: 0; }
  header { background: #1a3a5c; color: white; padding: 22px 32px; }
  header h1 { margin: 0; font-size: 1.8em; }
  header p  { margin: 6px 0 0; opacity: .8; font-size: .95em; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 20px 24px; }
  .card { background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.08);
          padding: 16px; }
  .card.wide { grid-column: 1 / -1; }
  h2.section { color: #1a3a5c; padding: 16px 24px 4px; margin: 0; font-size: 1.1em;
               text-transform: uppercase; letter-spacing: .05em; }
  .note { background: #e8f0fe; border-left: 4px solid #2c5f8a; padding: 10px 16px;
          margin: 0 24px 8px; border-radius: 0 4px 4px 0; font-size: .9em; color: #333; }
  footer { text-align: center; padding: 20px; color: #888; font-size: .85em; }
</style>
</head>
<body>
<header>
  <h1>Jefferson County EMS — County-Wide Analysis Dashboard</h1>
  <p>2024 Call Data &bull; 14 Departments &bull; 17,808 Incidents &bull; ISyE 450 Senior Design</p>
</header>

<h2 class="section">Call Volume & Service Mix</h2>
<p class="note">Data source: 2024 EMS Workgroup call exports from Wisconsin NFIRS. All 14 Jefferson County departments included.</p>
"""]

# Section 1 — Volume
html_parts.append('<div class="grid">')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_vol, "cdn")}</div>')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_emspct, False)}</div>')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_inc, False)}</div>')
html_parts.append('</div>')

# Section 2 — Response Times
html_parts.append('<h2 class="section">Response Time Analysis</h2>')
html_parts.append('<p class="note">Response times capped at 60 minutes to exclude data entry outliers. Orange dashed line = 8-minute clinical benchmark.</p>')
html_parts.append('<div class="grid">')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_rt, False)}</div>')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_ems_rt, False)}</div>')
html_parts.append('</div>')

# Section 3 — Temporal Patterns
html_parts.append('<h2 class="section">Temporal Call Patterns</h2>')
html_parts.append('<div class="grid">')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_heat_hour, False)}</div>')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_heat_dow, False)}</div>')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_monthly, False)}</div>')
html_parts.append('</div>')

# Section 4 — Mutual Aid & Billing
html_parts.append('<h2 class="section">Mutual Aid & Financial Rates</h2>')
html_parts.append('<div class="grid">')
html_parts.append(f'<div class="card">{fig_to_html(fig_aid, False)}</div>')
html_parts.append(f'<div class="card">{fig_to_html(fig_bill, False)}</div>')
html_parts.append('</div>')

# Section 5 — KPI Table
html_parts.append('<h2 class="section">Summary KPI Table</h2>')
html_parts.append('<div class="grid">')
html_parts.append(f'<div class="card wide">{fig_to_html(fig_table, False)}</div>')
html_parts.append('</div>')

html_parts.append("""
<footer>Jefferson County EMS Study &bull; UW-Madison ISyE 450 &bull; Generated 2026-03-01</footer>
</body></html>""")

out_path = "c:/Users/patri/OneDrive - UW-Madison/ISYE 450/jefferson_county_ems_dashboard.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(html_parts))

print(f"Dashboard written to: {out_path}")
print(f"Total incidents plotted: {len(combined):,}")
print(f"EMS incidents: {len(ems):,}")
