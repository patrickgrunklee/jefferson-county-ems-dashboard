"""
Jefferson County EMS — Staffing & Secondary Network Dashboard
Run:  python staffing_dashboard.py
Then open http://127.0.0.1:8051 in your browser.

Goal 1: Regional secondary ambulance network (placement, coverage, cost)
Goal 2: Peak staffing — where/when to deploy county-funded EMTs

Data: CY2024 NFIRS call records, Phase 1-4 analysis outputs
"""

import os, glob, json
import numpy as np
import pandas as pd
from math import factorial
from dash import Dash, dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ── Paths ────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
CALL_DIR = os.path.join(BASE, "ISyE Project", "Data and Resources", "Call Data")

# ── Department config ────────────────────────────────────────────────────
NAME_MAP = {
    "CAMBRIDGE COMM FIRE DEPT":          "Cambridge",
    "Edgerton Fire Protection Distict":  "Edgerton",
    "Fort Atkinson Fire Dept":           "Fort Atkinson",
    "Town of Ixonia Fire & EMS Dept":    "Ixonia",
    "Jefferson Fire Dept":               "Jefferson",
    "Johnson Creek Fire Dept":           "Johnson Creek",
    "Palmyra Village Fire Dept":         "Palmyra",
    "Rome Fire Dist":                    "Rome",
    "Sullivan Vol Fire Dept":            "Sullivan",
    "Waterloo Fire Dept":                "Waterloo",
    "Watertown Fire Dept":               "Watertown",
    "Western Lake Fire District":        "Western Lakes",
    "Whitewater Fire and EMS":           "Whitewater",
}

EMS_DEPTS = [
    "Edgerton", "Watertown", "Whitewater", "Fort Atkinson",
    "Waterloo", "Johnson Creek", "Ixonia", "Jefferson", "Palmyra", "Cambridge",
]

AMBULANCE_COUNT = {
    "Watertown": 3, "Fort Atkinson": 3, "Whitewater": 2, "Edgerton": 2,
    "Jefferson": 5, "Johnson Creek": 2, "Waterloo": 2,
    "Ixonia": 1, "Palmyra": 1, "Cambridge": 0,
}

DEPT_COORDS = {
    "Watertown": (43.1861, -88.7339), "Fort Atkinson": (42.9271, -88.8397),
    "Whitewater": (42.8325, -88.7332), "Edgerton": (42.8403, -89.0629),
    "Jefferson": (43.0056, -88.8014), "Johnson Creek": (43.0753, -88.7745),
    "Waterloo": (43.1886, -88.9797), "Ixonia": (43.1446, -88.5970),
    "Palmyra": (42.8794, -88.5855), "Cambridge": (43.0049, -89.0224),
    "Lake Mills": (43.0781, -88.9144), "Helenville": (43.0135, -88.6998),
    "Western Lakes": (43.0110, -88.5877),
}

STAFFING = {
    "Watertown":     {"FT": 31, "PT":  3, "Model": "Career",       "Level": "ALS"},
    "Fort Atkinson": {"FT": 16, "PT": 28, "Model": "Career+PT",    "Level": "ALS"},
    "Whitewater":    {"FT": 15, "PT": 17, "Model": "Career+PT",    "Level": "ALS"},
    "Edgerton":      {"FT": 24, "PT":  0, "Model": "Career+PT",    "Level": "ALS"},
    "Jefferson":     {"FT":  6, "PT": 20, "Model": "Career",       "Level": "ALS"},
    "Johnson Creek": {"FT":  3, "PT": 33, "Model": "Combination",  "Level": "ALS"},
    "Waterloo":      {"FT":  4, "PT": 22, "Model": "Career+Vol",   "Level": "AEMT"},
    "Ixonia":        {"FT":  2, "PT": 45, "Model": "Volunteer+FT", "Level": "BLS"},
    "Palmyra":       {"FT":  0, "PT": 20, "Model": "Volunteer",    "Level": "BLS"},
    "Cambridge":     {"FT":  0, "PT": 31, "Model": "Volunteer",    "Level": "ALS"},
}

DOW_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Peterson cost model
PETERSON_OPERATING = 716818
PETERSON_REVENUE = 466200
PETERSON_NET = PETERSON_OPERATING - PETERSON_REVENUE


# ── Erlang-C ─────────────────────────────────────────────────────────────
def erlang_c(lam, mu, c):
    if c == 0 or lam <= 0 or mu <= 0:
        return 1.0 if c == 0 and lam > 0 else 0.0
    rho = lam / (c * mu)
    if rho >= 1.0:
        return 1.0
    a = lam / mu
    sum_terms = sum(a**k / factorial(k) for k in range(c))
    last_term = (a**c / factorial(c)) * (1 / (1 - rho))
    p0 = 1.0 / (sum_terms + last_term)
    return ((a**c / factorial(c)) * (1 / (1 - rho))) * p0


# ── Call type classifier ─────────────────────────────────────────────────
def classify_call(desc):
    if pd.isna(desc):
        return "Other EMS"
    d = str(desc).lower()
    if "ems call, excluding" in d:
        return "Medical (BLS)"
    elif "medical assist" in d or "assist ems" in d:
        return "Medical Assist"
    elif "vehicle accident with injur" in d or "mv ped" in d:
        return "MVA w/ Injury (ALS)"
    elif "motor vehicle" in d or "vehicle accident" in d:
        return "MVA (BLS)"
    elif "emergency medical" in d or "standby" in d:
        return "EMS Standby"
    elif "rescue" in d or "extrication" in d or "search" in d:
        return "Rescue/Extrication (ALS)"
    else:
        return "Other EMS"


# ── Load data ────────────────────────────────────────────────────────────
print("Loading NFIRS data...")
_frames = []
for f in glob.glob(os.path.join(CALL_DIR, "Copy of 2024 EMS Workgroup - *.xlsx")):
    _frames.append(pd.read_excel(f))
_raw = pd.concat(_frames, ignore_index=True).copy()
_raw["Dept"] = _raw["Fire Department Name"].map(NAME_MAP)
_raw = _raw.dropna(subset=["Dept"]).copy()

# EMS only
_ems = _raw[_raw["Incident Type Code Category Description"].str.startswith("Rescue and EMS", na=False)].copy()
_ems["Hour"] = pd.to_numeric(_ems["Alarm Date - Hour of Day"], errors="coerce")
_ems["DOW"] = _ems["Alarm Date - Day of Week"]
_ems["RT"] = pd.to_numeric(_ems["Response Time (Minutes)"], errors="coerce")
_ems["Duration_Min"] = pd.to_numeric(_ems["Incident Duration (Minutes)"], errors="coerce")
_ems["Alarm_DT"] = pd.to_datetime(_ems["Alarm Date / Time"], errors="coerce")
_ems["Cleared_DT"] = pd.to_datetime(_ems["Last Unit Cleared Date / Time"], errors="coerce")
_ems["CallType"] = _ems["Incident Type Description"].apply(classify_call)
_ems = _ems[_ems["Dept"].isin(EMS_DEPTS)].copy()

print(f"  {len(_ems):,} EMS calls across {_ems['Dept'].nunique()} departments")

# Precompute per-department stats
_dept_stats = {}
for dept in EMS_DEPTS:
    dg = _ems[_ems["Dept"] == dept]
    if dg.empty:
        continue
    hourly = dg.groupby("Hour").size().reindex(range(24), fill_value=0)

    # Daily counts per hour for control limits
    dg2 = dg.copy()
    dg2["Date"] = dg2["Alarm_DT"].dt.date
    daily_h = dg2.groupby(["Date", "Hour"]).size().unstack(fill_value=0).reindex(columns=range(24), fill_value=0)
    mean_h = daily_h.mean()
    std_h = daily_h.std()

    # DOW profile
    dow = dg.groupby("DOW").size().reindex(DOW_ORDER, fill_value=0)

    # Call types by hour
    ct_h = dg.groupby(["Hour", "CallType"]).size().unstack(fill_value=0).reindex(range(24), fill_value=0)

    # Duration
    mean_dur = dg["Duration_Min"].dropna().mean()
    if np.isnan(mean_dur) or mean_dur <= 0:
        mean_dur = 45.0

    _dept_stats[dept] = {
        "total": len(dg),
        "hourly_total": hourly,
        "mean_daily": mean_h,
        "std_daily": std_h,
        "ucl": mean_h + 2 * std_h,
        "lcl": (mean_h - 2 * std_h).clip(lower=0),
        "dow": dow,
        "calltype_hourly": ct_h,
        "mean_duration_min": mean_dur,
        "amb": AMBULANCE_COUNT.get(dept, 1),
    }

# Precompute COUNTYWIDE combined stats
_county_hourly = _ems.groupby("Hour").size().reindex(range(24), fill_value=0)
_county_dow = _ems.groupby("DOW").size().reindex(DOW_ORDER, fill_value=0)
_county_ct_hourly = _ems.groupby(["Hour", "CallType"]).size().unstack(fill_value=0).reindex(range(24), fill_value=0)
_county_total = len(_ems)

# County daily-by-hour for SPC
_ems_d = _ems.copy()
_ems_d["Date"] = _ems_d["Alarm_DT"].dt.date
_county_daily_h = _ems_d.groupby(["Date", "Hour"]).size().unstack(fill_value=0).reindex(columns=range(24), fill_value=0)
_county_mean_h = _county_daily_h.mean()
_county_std_h = _county_daily_h.std()
_county_ucl = _county_mean_h + 2 * _county_std_h
_county_lcl = (_county_mean_h - 2 * _county_std_h).clip(lower=0)

# Per-department hourly breakdown for stacked area
_dept_hourly_all = {}
for dept in EMS_DEPTS:
    if dept in _dept_stats:
        _dept_hourly_all[dept] = _dept_stats[dept]["hourly_total"]

# Load secondary network solutions
_solutions = pd.read_csv(os.path.join(BASE, "secondary_network_solutions.csv"))
_solutions["T"] = _solutions["T"].apply(lambda x: int(x) if str(x).isdigit() else x)

# Load shift values for EMT optimization
_shift_vals = pd.read_csv(os.path.join(BASE, "peak_staffing_shift_values.csv"))

# Load staffing scenarios
_scenarios = pd.read_csv(os.path.join(BASE, "secondary_staffing_scenarios.csv"))

print("Data loaded. Starting dashboard...")


# ── Dash App ─────────────────────────────────────────────────────────────
app = Dash(__name__, title="Jefferson Co. EMS — Staffing & Network Analysis")

COLORS = {
    "bg": "#0f1117", "card": "#1a1d23", "text": "#e0e0e0",
    "accent": "#3b82f6", "red": "#ef4444", "green": "#22c55e",
    "orange": "#f59e0b", "purple": "#a855f7", "cyan": "#06b6d4",
    "muted": "#6b7280", "border": "#2d3748",
}

CARD_STYLE = {
    "backgroundColor": COLORS["card"], "borderRadius": "8px",
    "padding": "20px", "marginBottom": "16px",
    "border": f"1px solid {COLORS['border']}",
}

app.layout = html.Div(style={"backgroundColor": COLORS["bg"], "minHeight": "100vh",
                              "padding": "20px", "fontFamily": "system-ui, -apple-system, sans-serif",
                              "color": COLORS["text"]}, children=[

    # Header
    html.Div(style={"textAlign": "center", "marginBottom": "24px"}, children=[
        html.H1("Jefferson County EMS — Staffing & Network Dashboard",
                style={"color": COLORS["accent"], "marginBottom": "4px", "fontSize": "28px"}),
        html.P("ISyE 450 Senior Design | CY2024 NFIRS Data | Goals 1 & 2",
               style={"color": COLORS["muted"], "fontSize": "14px"}),
    ]),

    # ═══════════════════════════════════════════════════════════════════
    # GOAL 2: Peak Staffing
    # ═══════════════════════════════════════════════════════════════════
    html.Div(style=CARD_STYLE, children=[
        html.H2("Goal 2: Peak Staffing — Where & When to Deploy County EMTs",
                style={"color": COLORS["cyan"], "marginBottom": "8px"}),
        html.P("Use the slider to explore: if the county funds N EMTs, which departments "
               "and shifts get the most care-quality improvement?",
               style={"color": COLORS["muted"], "fontSize": "13px", "marginBottom": "16px"}),

        # Slider
        html.Div(style={"display": "flex", "alignItems": "center", "gap": "20px",
                         "marginBottom": "20px"}, children=[
            html.Label("County-Funded EMTs:", style={"fontWeight": "bold", "fontSize": "16px"}),
            dcc.Slider(id="emt-slider", min=1, max=5, step=1, value=1,
                       marks={i: {"label": str(i), "style": {"color": COLORS["text"], "fontSize": "14px"}}
                              for i in range(1, 6)},
                       tooltip={"placement": "bottom"}),
        ]),

        # Optimal assignment display
        html.Div(id="emt-assignment-cards",
                 style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"}),

        # Summary stat
        html.Div(id="emt-summary", style={"color": COLORS["muted"], "fontSize": "13px",
                                           "marginBottom": "16px"}),
    ]),

    # ═══════════════════════════════════════════════════════════════════
    # ALL MUNICIPALITIES COMBINED
    # ═══════════════════════════════════════════════════════════════════
    html.Div(style={**CARD_STYLE, "marginTop": "32px"}, children=[
        html.H2("All Municipalities Combined -- Countywide EMS Demand",
                style={"color": COLORS["green"], "marginBottom": "4px"}),
        html.P(f"{_county_total:,} EMS calls across {len(_dept_stats)} departments | CY2024 NFIRS",
               style={"color": COLORS["muted"], "fontSize": "13px", "marginBottom": "0px"}),
    ]),

    # Row 1: Combined hourly profile + Combined call types by hour
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="county-hourly-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="county-calltype-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Row 2: DOW + Shift breakdown pie
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="county-dow-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="county-shift-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Row 3: Stacked area (dept contribution by hour) + Staffing comparison table
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="county-stacked-dept-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="county-staffing-table", config={"displayModeBar": False}),
        ]),
    ]),

    # ═══════════════════════════════════════════════════════════════════
    # LABOR OPERATIONS INVESTIGATION
    # ═══════════════════════════════════════════════════════════════════
    html.Div(style={**CARD_STYLE, "marginTop": "32px"}, children=[
        html.H2("Labor Operations Investigation",
                style={"color": COLORS["purple"], "marginBottom": "4px"}),
        html.P("How efficiently is each municipality using its EMS labor? "
               "Where are the biggest mismatches between staffing levels and actual demand?",
               style={"color": COLORS["muted"], "fontSize": "13px", "marginBottom": "0px"}),
    ]),

    # Row: Labor utilization bar + Night vs Day mismatch
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="labor-utilization-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="night-day-mismatch-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Row: PT workforce sizing + Calls per FTE comparison
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="pt-efficiency-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="calls-per-fte-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Row: Peak-valley ratio + Staffing model comparison
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="peak-valley-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="staffing-model-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Department selector
    html.Div(style={**CARD_STYLE, "marginTop": "32px"}, children=[
        html.H3("Department Deep Dive", style={"color": COLORS["text"], "marginBottom": "8px"}),
        html.P("Select a department to see hourly demand, call types, and Erlang-C analysis.",
               style={"color": COLORS["muted"], "fontSize": "13px", "marginBottom": "12px"}),
        dcc.Dropdown(
            id="dept-dropdown",
            options=[{"label": f"{d} ({STAFFING[d]['Level']}, {AMBULANCE_COUNT.get(d, 0)} amb)",
                      "value": d} for d in EMS_DEPTS if d in _dept_stats],
            value="Edgerton",
            style={"backgroundColor": COLORS["card"], "color": "#000",
                   "borderColor": COLORS["border"]},
        ),
    ]),

    # Row: Hourly profile + Call types
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="hourly-profile-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="calltype-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Row: DOW profile + Erlang-C by hour
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="dow-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="erlang-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # County-wide marginal heatmap
    html.Div(style=CARD_STYLE, children=[
        html.H3("All Departments: Marginal Value of +1 Crew by Hour",
                style={"color": COLORS["text"], "marginBottom": "4px"}),
        html.P("Darker = adding one ambulance crew at that department-hour reduces P(wait) more. "
               "This is where patients benefit most from additional resources.",
               style={"color": COLORS["muted"], "fontSize": "12px", "marginBottom": "8px"}),
        dcc.Graph(id="marginal-heatmap", config={"displayModeBar": False}),
    ]),

    # ═══════════════════════════════════════════════════════════════════
    # GOAL 1: Secondary Network
    # ═══════════════════════════════════════════════════════════════════
    html.Div(style={**CARD_STYLE, "marginTop": "32px"}, children=[
        html.H2("Goal 1: Regional Secondary Ambulance Network",
                style={"color": COLORS["orange"], "marginBottom": "8px"}),
        html.P("When a department's primary ambulance is on a call, a regional secondary "
               "responds. How many stations and where?",
               style={"color": COLORS["muted"], "fontSize": "13px", "marginBottom": "16px"}),

        # K slider
        html.Div(style={"display": "flex", "alignItems": "center", "gap": "20px",
                         "marginBottom": "20px"}, children=[
            html.Label("Secondary Stations:", style={"fontWeight": "bold", "fontSize": "16px"}),
            dcc.Slider(id="k-slider", min=2, max=5, step=1, value=3,
                       marks={i: {"label": str(i), "style": {"color": COLORS["text"], "fontSize": "14px"}}
                              for i in range(2, 6)},
                       tooltip={"placement": "bottom"}),
        ]),
    ]),

    # Row: Coverage chart + Cost comparison
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="coverage-chart", config={"displayModeBar": False}),
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="cost-chart", config={"displayModeBar": False}),
        ]),
    ]),

    # Secondary demand by dept
    html.Div(style=CARD_STYLE, children=[
        dcc.Graph(id="secondary-demand-chart", config={"displayModeBar": False}),
    ]),

    # Network map
    html.Div(style=CARD_STYLE, children=[
        dcc.Graph(id="network-map", config={"displayModeBar": False}),
    ]),

    # Concurrent call heatmap (county-wide)
    html.Div(style=CARD_STYLE, children=[
        html.H3("When Does Secondary Demand Peak?",
                style={"color": COLORS["text"], "marginBottom": "4px"}),
        html.P("Concurrent call rate by hour and day — shows when primary ambulances are most "
               "likely to be busy and secondary response is needed.",
               style={"color": COLORS["muted"], "fontSize": "12px", "marginBottom": "8px"}),
        dcc.Graph(id="concurrent-heatmap", config={"displayModeBar": False}),
    ]),

    # Footer
    html.Div(style={"textAlign": "center", "padding": "20px", "color": COLORS["muted"],
                     "fontSize": "12px"}, children=[
        html.P("Data: CY2024 NFIRS (14 departments) | FY2025 budgets | Peterson cost model (Dec 2025)"),
        html.P("Erlang-C queueing model | MCLP/P-Median facility location (PuLP) | ORS drive times"),
    ]),
])


# ═══════════════════════════════════════════════════════════════════════
# CALLBACKS — All Municipalities Combined
# ═══════════════════════════════════════════════════════════════════════

@app.callback(
    Output("county-hourly-chart", "figure"),
    Input("emt-slider", "value"),  # dummy trigger on load
)
def update_county_hourly(_):
    hours = list(range(24))
    fig = go.Figure()

    # Bar: total calls per hour
    fig.add_trace(go.Bar(
        x=hours, y=_county_mean_h.values, name="Mean calls/day/hr",
        marker_color=COLORS["accent"], opacity=0.8,
    ))
    # UCL / LCL
    fig.add_trace(go.Scatter(
        x=hours, y=_county_ucl.values, name="UCL (mu+2sigma)",
        mode="lines", line=dict(color=COLORS["red"], dash="dash", width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=hours, y=_county_lcl.values, name="LCL (mu-2sigma)",
        mode="lines", line=dict(color=COLORS["green"], dash="dot", width=1),
    ))

    # Peak shading
    fig.add_vrect(x0=10.5, x1=18.5, fillcolor=COLORS["orange"], opacity=0.07,
                  line_width=0, annotation_text="Peak 11-18", annotation_position="top left",
                  annotation_font_color=COLORS["orange"])

    # Overnight shading
    fig.add_vrect(x0=-0.5, x1=5.5, fillcolor=COLORS["cyan"], opacity=0.04,
                  line_width=0, annotation_text="Low", annotation_position="top center",
                  annotation_font_color=COLORS["cyan"])

    pct = _county_hourly / _county_hourly.sum() * 100
    peak_pct = sum(pct.get(h, 0) for h in range(11, 19))

    fig.update_layout(
        title=dict(text="Countywide Hourly EMS Demand<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"{_county_total:,} calls | Peak 11:00-18:00 = {peak_pct:.0f}% of all calls | "
                        f"SPC control limits shown</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="Calls per Hour (daily avg)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.15), margin=dict(t=70, b=60),
        xaxis=dict(dtick=2),
    )
    return fig


@app.callback(
    Output("county-calltype-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_county_calltype(_):
    ct = _county_ct_hourly
    fig = go.Figure()

    type_colors = {
        "Medical (BLS)": COLORS["accent"], "Medical Assist": COLORS["cyan"],
        "MVA w/ Injury (ALS)": COLORS["red"], "MVA (BLS)": COLORS["orange"],
        "Rescue/Extrication (ALS)": COLORS["purple"], "EMS Standby": COLORS["muted"],
        "Other EMS": "#555",
    }

    for col in ct.columns:
        fig.add_trace(go.Bar(x=ct.index, y=ct[col], name=col,
                             marker_color=type_colors.get(col, "#888")))

    fig.update_layout(
        barmode="stack",
        title=dict(text="Countywide Call Types by Hour<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"BLS medical calls dominate; ALS peaks during daytime hours</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="Calls (annual total)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.2, font_size=10), margin=dict(t=70, b=80),
        xaxis=dict(dtick=2),
    )
    return fig


@app.callback(
    Output("county-dow-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_county_dow(_):
    avg = _county_dow.mean()
    colors = [COLORS["red"] if v > avg * 1.05 else COLORS["green"] if v < avg * 0.95
              else COLORS["accent"] for v in _county_dow.values]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=_county_dow.index, y=_county_dow.values, marker_color=colors))
    fig.add_hline(y=avg, line_dash="dash", line_color=COLORS["muted"],
                  annotation_text=f"Mean: {avg:.0f}/day", annotation_font_color=COLORS["muted"])

    weekday_total = sum(_county_dow.get(d, 0) for d in DOW_ORDER[:5])
    weekend_total = sum(_county_dow.get(d, 0) for d in DOW_ORDER[5:])
    wd_pct = weekday_total / (weekday_total + weekend_total) * 100

    fig.update_layout(
        title=dict(text="Countywide Day-of-Week Profile<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Nearly flat: weekday {wd_pct:.0f}% vs weekend {100-wd_pct:.0f}% | "
                        f"No staffing change needed by day</span>",
                   font_size=15),
        xaxis_title="Day of Week", yaxis_title="EMS Calls (annual)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40),
    )
    return fig


@app.callback(
    Output("county-shift-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_county_shift(_):
    day = sum(_county_hourly.get(h, 0) for h in range(6, 14))
    aft = sum(_county_hourly.get(h, 0) for h in range(14, 22))
    ngt = sum(_county_hourly.get(h, 0) for h in list(range(22, 24)) + list(range(0, 6)))
    total = day + aft + ngt

    labels = ["Day (06-14)", "Afternoon (14-22)", "Overnight (22-06)"]
    values = [day, aft, ngt]
    pcts = [v / total * 100 for v in values]
    shift_colors = [COLORS["accent"], COLORS["orange"], COLORS["cyan"]]

    fig = go.Figure()

    # Donut chart
    fig.add_trace(go.Pie(
        labels=[f"{l}<br>{p:.0f}%" for l, p in zip(labels, pcts)],
        values=values,
        hole=0.55,
        marker=dict(colors=shift_colors),
        textinfo="label+value",
        textfont_size=12,
        hovertemplate="%{label}: %{value:,} calls<extra></extra>",
    ))

    # Center annotation
    fig.add_annotation(
        text=f"<b>{total:,}</b><br>total calls",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16, color=COLORS["text"]),
    )

    ratio = aft / ngt if ngt > 0 else 0
    fig.update_layout(
        title=dict(text="Countywide Shift Distribution<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Afternoon is {ratio:.1f}x busier than overnight | "
                        f"Staff should weight toward afternoon</span>",
                   font_size=15),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=20), showlegend=False,
    )
    return fig


@app.callback(
    Output("county-stacked-dept-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_county_stacked(_):
    fig = go.Figure()

    dept_colors = {
        "Edgerton": COLORS["red"], "Watertown": COLORS["accent"],
        "Whitewater": COLORS["purple"], "Fort Atkinson": COLORS["green"],
        "Jefferson": COLORS["orange"], "Johnson Creek": COLORS["cyan"],
        "Waterloo": "#f472b6", "Ixonia": "#a3e635",
        "Palmyra": "#fbbf24", "Cambridge": "#94a3b8",
    }

    hours = list(range(24))
    for dept in EMS_DEPTS:
        if dept not in _dept_hourly_all:
            continue
        h = _dept_hourly_all[dept]
        fig.add_trace(go.Bar(
            x=hours, y=[h.get(hr, 0) for hr in hours],
            name=dept, marker_color=dept_colors.get(dept, "#888"),
        ))

    fig.update_layout(
        barmode="stack",
        title=dict(text="Hourly Demand by Department (Stacked)<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Shows which departments drive demand at each hour</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="EMS Calls (annual total)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.2, font_size=10), margin=dict(t=70, b=80),
        xaxis=dict(dtick=2),
    )
    return fig


@app.callback(
    Output("county-staffing-table", "figure"),
    Input("emt-slider", "value"),
)
def update_county_staffing_table(_):
    rows_dept = []
    rows_calls = []
    rows_ft = []
    rows_pt = []
    rows_amb = []
    rows_cpa = []
    rows_cft = []
    rows_model = []
    rows_verdict = []

    for dept in sorted(_dept_stats.keys()):
        s = STAFFING.get(dept, {})
        ft = s.get("FT", 0)
        pt = s.get("PT", 0)
        amb = AMBULANCE_COUNT.get(dept, 0)
        calls = _dept_stats[dept]["total"]
        cpa = calls / amb if amb > 0 else 0
        cft = calls / ft if ft > 0 else 0

        # Verdict
        if cpa < 100 and amb > 1:
            verdict = "OVER-AMB"
        elif ft < 3 and calls > 300:
            verdict = "CREW GAP"
        elif pt > 20 and calls < 600:
            verdict = "PT OVERSIZED"
        elif cpa > 500:
            verdict = "WELL-UTILIZED"
        else:
            verdict = "ADEQUATE"

        rows_dept.append(dept)
        rows_calls.append(calls)
        rows_ft.append(ft)
        rows_pt.append(pt)
        rows_amb.append(amb)
        rows_cpa.append(f"{cpa:.0f}")
        rows_cft.append(f"{cft:.0f}" if ft > 0 else "N/A")
        rows_model.append(s.get("Model", "?"))
        rows_verdict.append(verdict)

    verdict_colors = {
        "OVER-AMB": COLORS["red"], "CREW GAP": COLORS["orange"],
        "PT OVERSIZED": COLORS["orange"], "WELL-UTILIZED": COLORS["green"],
        "ADEQUATE": COLORS["accent"],
    }
    cell_colors = [[verdict_colors.get(v, COLORS["muted"]) for v in rows_verdict]]

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["Department", "Calls", "FT", "PT", "Amb", "Calls/Amb", "Calls/FT", "Model", "Verdict"],
            fill_color=COLORS["bg"],
            font=dict(color=COLORS["text"], size=12),
            align="center", line_color=COLORS["border"],
        ),
        cells=dict(
            values=[rows_dept, rows_calls, rows_ft, rows_pt, rows_amb,
                    rows_cpa, rows_cft, rows_model, rows_verdict],
            fill_color=[
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                [COLORS["card"]] * len(rows_dept),
                cell_colors[0],
            ],
            font=dict(color=COLORS["text"], size=11),
            align="center", line_color=COLORS["border"],
            height=28,
        ),
    )])

    fig.update_layout(
        title=dict(text="Staffing Overview & Assessment<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"NFIRS call counts | Verdict based on calls/ambulance and FT crew coverage</span>",
                   font_size=15),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=10, l=10, r=10), height=400,
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# CALLBACKS — Labor Operations Investigation
# ═══════════════════════════════════════════════════════════════════════

@app.callback(
    Output("labor-utilization-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_labor_utilization(_):
    """% of paid crew-hours actually spent on EMS calls vs idle/available."""
    rows = []
    for dept in sorted(_dept_stats.keys()):
        s = STAFFING.get(dept, {})
        ft = s.get("FT", 0)
        amb = AMBULANCE_COUNT.get(dept, 0)
        calls = _dept_stats[dept]["total"]
        mean_dur = _dept_stats[dept]["mean_duration_min"]

        # Crew-hours used: calls × duration × 2 crew per call
        used_hrs = calls * (mean_dur / 60) * 2

        # Available crew-hours: for 24/7 depts, minimum is 2 crew × 8760 hrs/yr
        # For volunteer depts, use FT × 2080 (work hours/yr) + PT × 520 (est ~10 hrs/wk)
        if ft >= 6:  # career 24/7
            available_hrs = 2 * 8760  # 2 crew around the clock
        elif ft > 0:
            available_hrs = ft * 2080 + s.get("PT", 0) * 520
        else:
            available_hrs = s.get("PT", 0) * 520

        util_pct = (used_hrs / available_hrs * 100) if available_hrs > 0 else 0

        rows.append({
            "Dept": dept, "Calls": calls, "Used_Hrs": used_hrs,
            "Available_Hrs": available_hrs, "Util_Pct": util_pct,
            "FT": ft, "Amb": amb,
        })

    df = pd.DataFrame(rows).sort_values("Util_Pct", ascending=True)

    fig = go.Figure()
    colors = [COLORS["red"] if u < 5 else COLORS["orange"] if u < 15
              else COLORS["green"] for u in df["Util_Pct"]]

    fig.add_trace(go.Bar(
        y=df["Dept"], x=df["Util_Pct"], orientation="h",
        marker_color=colors, opacity=0.85,
        text=[f"{u:.1f}% ({int(c)} calls, {int(h)} crew-hrs used)"
              for u, c, h in zip(df["Util_Pct"], df["Calls"], df["Used_Hrs"])],
        textposition="outside", textfont_size=10,
    ))

    fig.update_layout(
        title=dict(text="Labor Utilization Rate by Department<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"% of available crew-hours spent on EMS calls | "
                        f"Low % = staff mostly idle/available</span>",
                   font_size=15),
        xaxis_title="Utilization (%)", xaxis=dict(range=[0, max(df["Util_Pct"]) * 1.4]),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40, l=120), height=400, showlegend=False,
    )
    return fig


@app.callback(
    Output("night-day-mismatch-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_night_day_mismatch(_):
    """For each dept: % of calls at night (00-06) vs staffing model."""
    rows = []
    for dept in sorted(_dept_stats.keys()):
        h = _dept_stats[dept]["hourly_total"]
        total = h.sum()
        if total == 0:
            continue
        night = sum(h.get(hr, 0) for hr in range(0, 7))
        day = sum(h.get(hr, 0) for hr in range(8, 19))
        evening = total - night - day

        s = STAFFING.get(dept, {})
        is_24_7 = s.get("FT", 0) >= 6
        rows.append({
            "Dept": dept,
            "Night_Pct": night / total * 100,
            "Day_Pct": day / total * 100,
            "Evening_Pct": evening / total * 100,
            "Is_24_7": is_24_7,
            "Night_Calls": night,
            "FT": s.get("FT", 0),
        })

    df = pd.DataFrame(rows).sort_values("Night_Pct", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(y=df["Dept"], x=df["Day_Pct"], name="Day (08-18)",
                         orientation="h", marker_color=COLORS["accent"]))
    fig.add_trace(go.Bar(y=df["Dept"], x=df["Evening_Pct"], name="Evening/Other",
                         orientation="h", marker_color=COLORS["orange"]))
    fig.add_trace(go.Bar(y=df["Dept"], x=df["Night_Pct"], name="Night (00-06)",
                         orientation="h", marker_color="#1e293b"))

    # Mark 24/7 depts
    for _, row in df.iterrows():
        if row["Is_24_7"]:
            fig.add_annotation(x=100, y=row["Dept"], text="24/7",
                             showarrow=False, font=dict(color=COLORS["red"], size=10),
                             xanchor="left", xshift=5)

    fig.update_layout(
        barmode="stack",
        title=dict(text="Night vs Day Call Distribution<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"24/7 career depts pay full overnight staff for minimal night demand</span>",
                   font_size=15),
        xaxis_title="% of EMS Calls",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.15), margin=dict(t=70, b=60, l=120), height=400,
    )
    return fig


@app.callback(
    Output("pt-efficiency-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_pt_efficiency(_):
    """Calls per PT employee — shows oversized volunteer rosters."""
    rows = []
    for dept in sorted(_dept_stats.keys()):
        s = STAFFING.get(dept, {})
        pt = s.get("PT", 0)
        ft = s.get("FT", 0)
        calls = _dept_stats[dept]["total"]
        if pt == 0:
            continue
        calls_per_pt = calls / pt
        rows.append({
            "Dept": dept, "PT": pt, "FT": ft, "Calls": calls,
            "Calls_Per_PT": calls_per_pt,
        })

    df = pd.DataFrame(rows).sort_values("Calls_Per_PT", ascending=True)

    fig = go.Figure()

    # Bubble chart: x=PT count, y=calls/PT, size=total calls
    fig.add_trace(go.Scatter(
        x=df["PT"], y=df["Calls_Per_PT"],
        mode="markers+text", text=df["Dept"],
        textposition="top center", textfont=dict(size=10, color=COLORS["text"]),
        marker=dict(
            size=df["Calls"].clip(lower=50) / 15,
            color=df["Calls_Per_PT"],
            colorscale="RdYlGn", showscale=True,
            colorbar=dict(title="Calls/PT"),
            line=dict(width=1, color=COLORS["border"]),
        ),
        hovertemplate="<b>%{text}</b><br>PT staff: %{x}<br>"
                      "Calls/PT: %{y:.1f}<br>Total calls: %{marker.size}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="Part-Time Workforce Efficiency<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Large PT rosters with few calls/PT = opportunity to consolidate</span>",
                   font_size=15),
        xaxis_title="Number of PT Staff", yaxis_title="EMS Calls per PT Employee",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40), height=400, showlegend=False,
    )
    return fig


@app.callback(
    Output("calls-per-fte-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_calls_per_fte(_):
    """Normalized calls per FTE (FT + 0.25×PT) — apples-to-apples comparison."""
    rows = []
    for dept in sorted(_dept_stats.keys()):
        s = STAFFING.get(dept, {})
        ft = s.get("FT", 0)
        pt = s.get("PT", 0)
        calls = _dept_stats[dept]["total"]
        amb = AMBULANCE_COUNT.get(dept, 0)

        # FTE = FT + 0.25 × PT (PT ~10 hrs/wk = 25% of FT)
        fte = ft + 0.25 * pt
        calls_per_fte = calls / fte if fte > 0 else 0
        cost_per_call = None  # would need expense data

        rows.append({
            "Dept": dept, "FT": ft, "PT": pt, "FTE": round(fte, 1),
            "Calls": calls, "Calls_Per_FTE": round(calls_per_fte, 1),
            "Amb": amb, "Model": s.get("Model", "?"),
        })

    df = pd.DataFrame(rows).sort_values("Calls_Per_FTE", ascending=True)

    fig = go.Figure()
    colors = [COLORS["red"] if c < 30 else COLORS["orange"] if c < 80
              else COLORS["green"] for c in df["Calls_Per_FTE"]]

    fig.add_trace(go.Bar(
        y=df["Dept"], x=df["Calls_Per_FTE"], orientation="h",
        marker_color=colors, opacity=0.85,
        text=[f"{c:.0f} calls/FTE ({row['FTE']} FTE = {row['FT']}FT + {row['PT']}PT×0.25)"
              for c, (_, row) in zip(df["Calls_Per_FTE"], df.iterrows())],
        textposition="outside", textfont_size=9,
    ))

    # Benchmark line
    median_val = df["Calls_Per_FTE"].median()
    fig.add_vline(x=median_val, line_dash="dash", line_color=COLORS["muted"],
                  annotation_text=f"Median: {median_val:.0f}",
                  annotation_font_color=COLORS["muted"])

    fig.update_layout(
        title=dict(text="Calls per FTE by Department<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"FTE = FT + 0.25 x PT | Lower = less productive labor allocation</span>",
                   font_size=15),
        xaxis_title="EMS Calls per FTE (annual)",
        xaxis=dict(range=[0, max(df["Calls_Per_FTE"]) * 1.5]),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40, l=120), height=400, showlegend=False,
    )
    return fig


@app.callback(
    Output("peak-valley-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_peak_valley(_):
    """Peak-to-valley ratio: how much demand swings within each dept's day."""
    rows = []
    for dept in sorted(_dept_stats.keys()):
        h = _dept_stats[dept]["hourly_total"]
        if h.sum() == 0:
            continue
        peak_4 = h.nlargest(4).mean()
        valley_4 = h.nsmallest(4).mean()
        ratio = peak_4 / valley_4 if valley_4 > 0 else float("inf")
        peak_hrs = sorted(h.nlargest(4).index.tolist())
        valley_hrs = sorted(h.nsmallest(4).index.tolist())

        rows.append({
            "Dept": dept, "Ratio": min(ratio, 20),
            "Peak_Hrs": ", ".join(f"{hr:02d}" for hr in peak_hrs),
            "Valley_Hrs": ", ".join(f"{hr:02d}" for hr in valley_hrs),
            "FT": STAFFING.get(dept, {}).get("FT", 0),
        })

    df = pd.DataFrame(rows).sort_values("Ratio", ascending=True)

    fig = go.Figure()
    colors = [COLORS["red"] if r > 4 else COLORS["orange"] if r > 2.5
              else COLORS["green"] for r in df["Ratio"]]

    fig.add_trace(go.Bar(
        y=df["Dept"], x=df["Ratio"], orientation="h",
        marker_color=colors, opacity=0.85,
        text=[f"{r:.1f}x | Peak: {p} | Valley: {v}"
              for r, p, v in zip(df["Ratio"], df["Peak_Hrs"], df["Valley_Hrs"])],
        textposition="outside", textfont_size=9,
    ))

    fig.add_vline(x=2.5, line_dash="dash", line_color=COLORS["muted"],
                  annotation_text="2.5x threshold",
                  annotation_font_color=COLORS["muted"])

    fig.update_layout(
        title=dict(text="Peak-to-Valley Demand Ratio<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Higher = bigger swing between busiest and quietest hours | "
                        f"Staffing stays flat but demand doesn't</span>",
                   font_size=15),
        xaxis_title="Peak / Valley Ratio (top-4 hrs avg / bottom-4 hrs avg)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40, l=120), height=400, showlegend=False,
    )
    return fig


@app.callback(
    Output("staffing-model-chart", "figure"),
    Input("emt-slider", "value"),
)
def update_staffing_model(_):
    """Compare staffing models: career vs volunteer vs hybrid on key metrics."""
    rows = []
    for dept in sorted(_dept_stats.keys()):
        s = STAFFING.get(dept, {})
        ft = s.get("FT", 0)
        pt = s.get("PT", 0)
        calls = _dept_stats[dept]["total"]
        amb = AMBULANCE_COUNT.get(dept, 0)
        mean_dur = _dept_stats[dept]["mean_duration_min"]
        model = s.get("Model", "?")

        # Categorize
        if "Career" in model and "Vol" not in model and "PT" not in model:
            category = "Career"
        elif "Volunteer" in model:
            category = "Volunteer"
        else:
            category = "Hybrid"

        rows.append({
            "Dept": dept, "Category": category, "Model": model,
            "Calls": calls, "FT": ft, "PT": pt, "Amb": amb,
            "Calls_Per_Day": calls / 365,
            "Mean_Duration": mean_dur,
        })

    df = pd.DataFrame(rows)

    cat_colors = {"Career": COLORS["accent"], "Hybrid": COLORS["orange"], "Volunteer": COLORS["green"]}

    fig = go.Figure()
    for cat in ["Career", "Hybrid", "Volunteer"]:
        sub = df[df["Category"] == cat]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["Calls_Per_Day"], y=sub["FT"] + sub["PT"],
            mode="markers+text", text=sub["Dept"],
            textposition="top center", textfont=dict(size=10),
            marker=dict(size=sub["Amb"] * 8 + 10, color=cat_colors[cat],
                        line=dict(width=1, color=COLORS["border"]), opacity=0.8),
            name=cat,
            hovertemplate="<b>%{text}</b><br>Calls/day: %{x:.1f}<br>"
                          "Total staff: %{y}<br>Model: " + cat + "<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Staffing Model Comparison<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Bubble size = ambulances | Career depts have more staff per call</span>",
                   font_size=15),
        xaxis_title="Calls per Day", yaxis_title="Total Staff (FT + PT)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.15), margin=dict(t=70, b=60), height=400,
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════
# CALLBACKS — Goal 2
# ═══════════════════════════════════════════════════════════════════════

@app.callback(
    [Output("emt-assignment-cards", "children"),
     Output("emt-summary", "children")],
    Input("emt-slider", "value"),
)
def update_emt_assignments(n_emts):
    top = _shift_vals.head(n_emts)
    cards = []
    for i, (_, row) in enumerate(top.iterrows()):
        dept = row["Dept"]
        shift = row["Shift"]
        val = row["Marginal_Value"]
        calls = int(row["Annual_Calls_Shift"])
        info = STAFFING.get(dept, {})
        level = info.get("Level", "?")

        color = COLORS["green"] if i == 0 else COLORS["cyan"] if i < 3 else COLORS["muted"]
        cards.append(
            html.Div(style={
                "backgroundColor": COLORS["bg"], "borderRadius": "8px", "padding": "14px",
                "border": f"2px solid {color}", "minWidth": "180px", "textAlign": "center",
            }, children=[
                html.Div(f"EMT #{i+1}", style={"color": color, "fontWeight": "bold",
                                                  "fontSize": "12px", "marginBottom": "4px"}),
                html.Div(dept, style={"fontSize": "18px", "fontWeight": "bold", "color": COLORS["text"]}),
                html.Div(shift, style={"fontSize": "14px", "color": COLORS["muted"]}),
                html.Div(f"{level} | ~{calls} calls/yr",
                         style={"fontSize": "12px", "color": COLORS["muted"], "marginTop": "4px"}),
                html.Div(f"Value: {val:.4f}",
                         style={"fontSize": "11px", "color": color, "marginTop": "4px"}),
            ])
        )

    total_val = top["Marginal_Value"].sum()
    summary = (f"Total marginal value: {total_val:.4f} | "
               f"Each unit of marginal value = reduction in probability that a patient "
               f"must wait because all ambulances are busy (Erlang-C model)")

    return cards, summary


@app.callback(
    Output("hourly-profile-chart", "figure"),
    Input("dept-dropdown", "value"),
)
def update_hourly_profile(dept):
    if dept not in _dept_stats:
        return go.Figure()

    s = _dept_stats[dept]
    hours = list(range(24))
    mean = s["mean_daily"]
    ucl = s["ucl"]
    lcl = s["lcl"]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=hours, y=mean, name="Mean calls/day/hr",
                         marker_color=COLORS["accent"], opacity=0.8))
    fig.add_trace(go.Scatter(x=hours, y=ucl, name="UCL (mu+2sigma)",
                             mode="lines", line=dict(color=COLORS["red"], dash="dash", width=1.5)))
    fig.add_trace(go.Scatter(x=hours, y=lcl, name="LCL (mu-2sigma)",
                             mode="lines", line=dict(color=COLORS["green"], dash="dot", width=1)))

    # Shade peak hours
    fig.add_vrect(x0=7.5, x1=19.5, fillcolor=COLORS["orange"], opacity=0.05,
                  line_width=0, annotation_text="Peak 08-20", annotation_position="top left",
                  annotation_font_color=COLORS["orange"])

    amb = s["amb"]
    total = s["total"]
    fig.update_layout(
        title=dict(text=f"{dept} — Hourly EMS Demand Profile<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"{total} calls/yr | {amb} ambulances | SPC control limits shown</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="Calls per Hour (daily avg)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.15), margin=dict(t=70, b=60),
        xaxis=dict(dtick=2),
    )
    return fig


@app.callback(
    Output("calltype-chart", "figure"),
    Input("dept-dropdown", "value"),
)
def update_calltype(dept):
    if dept not in _dept_stats:
        return go.Figure()

    ct = _dept_stats[dept]["calltype_hourly"]
    fig = go.Figure()

    type_colors = {
        "Medical (BLS)": COLORS["accent"], "Medical Assist": COLORS["cyan"],
        "MVA w/ Injury (ALS)": COLORS["red"], "MVA (BLS)": COLORS["orange"],
        "Rescue/Extrication (ALS)": COLORS["purple"], "EMS Standby": COLORS["muted"],
        "Other EMS": "#555",
    }

    for col in ct.columns:
        fig.add_trace(go.Bar(x=ct.index, y=ct[col], name=col,
                             marker_color=type_colors.get(col, "#888")))

    fig.update_layout(
        barmode="stack",
        title=dict(text=f"{dept} — Call Types by Hour<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"BLS-level calls dominate at all hours; ALS peaks during daytime</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="Calls (annual total)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.2, font_size=10), margin=dict(t=70, b=80),
        xaxis=dict(dtick=2),
    )
    return fig


@app.callback(
    Output("dow-chart", "figure"),
    Input("dept-dropdown", "value"),
)
def update_dow(dept):
    if dept not in _dept_stats:
        return go.Figure()

    dow = _dept_stats[dept]["dow"]
    avg = dow.mean()

    fig = go.Figure()
    colors = [COLORS["red"] if v > avg * 1.1 else COLORS["green"] if v < avg * 0.9
              else COLORS["accent"] for v in dow.values]
    fig.add_trace(go.Bar(x=dow.index, y=dow.values, marker_color=colors))
    fig.add_hline(y=avg, line_dash="dash", line_color=COLORS["muted"],
                  annotation_text=f"Mean: {avg:.0f}", annotation_font_color=COLORS["muted"])

    fig.update_layout(
        title=dict(text=f"{dept} — Day-of-Week Profile<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Red = above avg, Green = below avg</span>",
                   font_size=15),
        xaxis_title="Day of Week", yaxis_title="EMS Calls (annual)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40),
    )
    return fig


@app.callback(
    Output("erlang-chart", "figure"),
    Input("dept-dropdown", "value"),
)
def update_erlang(dept):
    if dept not in _dept_stats:
        return go.Figure()

    s = _dept_stats[dept]
    amb = s["amb"]
    mu = 1.0 / (s["mean_duration_min"] / 60.0)
    hours = list(range(24))

    p_current = []
    p_plus1 = []
    for h in hours:
        lam = s["hourly_total"].get(h, 0) / 365.0
        pc = erlang_c(lam, mu, amb) * 100
        pp = erlang_c(lam, mu, amb + 1) * 100
        p_current.append(pc)
        p_plus1.append(pp)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hours, y=p_current, name=f"Current ({amb} amb)",
                             mode="lines+markers", line=dict(color=COLORS["red"], width=2),
                             marker=dict(size=5)))
    fig.add_trace(go.Scatter(x=hours, y=p_plus1, name=f"+1 Crew ({amb+1} amb)",
                             mode="lines+markers", line=dict(color=COLORS["green"], width=2),
                             marker=dict(size=5)))

    # Fill between
    fig.add_trace(go.Scatter(
        x=hours + hours[::-1],
        y=p_current + p_plus1[::-1],
        fill="toself", fillcolor="rgba(239,68,68,0.1)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))

    fig.add_vrect(x0=7.5, x1=19.5, fillcolor=COLORS["orange"], opacity=0.05, line_width=0)

    fig.update_layout(
        title=dict(text=f"{dept} — Erlang-C: P(wait) by Hour<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Shaded area = care improvement from adding 1 crew | "
                        f"Avg call duration: {s['mean_duration_min']:.0f} min</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="P(all ambulances busy) %",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.15), margin=dict(t=70, b=60),
        xaxis=dict(dtick=2), yaxis=dict(rangemode="tozero"),
    )
    return fig


@app.callback(
    Output("marginal-heatmap", "figure"),
    Input("emt-slider", "value"),
)
def update_marginal_heatmap(n_emts):
    # Compute marginal value for all depts × hours
    rows = []
    for dept in EMS_DEPTS:
        if dept not in _dept_stats:
            continue
        s = _dept_stats[dept]
        amb = s["amb"]
        mu = 1.0 / (s["mean_duration_min"] / 60.0)
        for h in range(24):
            lam = s["hourly_total"].get(h, 0) / 365.0
            if lam <= 0:
                rows.append({"Dept": dept, "Hour": h, "Delta": 0})
                continue
            pc = erlang_c(lam, mu, amb)
            pp = erlang_c(lam, mu, amb + 1)
            rows.append({"Dept": dept, "Hour": h, "Delta": pc - pp})

    df = pd.DataFrame(rows)
    pivot = df.pivot(index="Dept", columns="Hour", values="Delta")
    pivot["Total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Total", ascending=True).drop(columns="Total")
    pivot = pivot.reindex(columns=range(24))

    # Highlight assigned slots
    top = _shift_vals.head(n_emts)
    annotations = []
    for _, row in top.iterrows():
        dept_idx = list(pivot.index).index(row["Dept"]) if row["Dept"] in pivot.index else None
        if dept_idx is not None:
            shift_hours = list(range(8, 20)) if "Day" in row["Shift"] else list(range(20, 24)) + list(range(0, 8))
            for h in shift_hours:
                annotations.append(dict(
                    x=h, y=row["Dept"], text="*", showarrow=False,
                    font=dict(color="white", size=10),
                ))

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=[f"{h:02d}" for h in range(24)], y=pivot.index,
        colorscale="YlOrRd", colorbar=dict(title="ΔP(wait)"),
        hovertemplate="Dept: %{y}<br>Hour: %{x}:00<br>ΔP(wait): %{z:.5f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=f"Marginal Value of +1 Crew by Department × Hour<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"★ = assigned EMTs ({n_emts} selected) | "
                        f"Higher ΔP(wait) = more care improvement</span>",
                   font_size=15),
        xaxis_title="Hour of Day", yaxis_title="",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        annotations=annotations, height=400, margin=dict(t=70, b=40),
    )

    # Add vertical lines for peak hours
    fig.add_vline(x=7.5, line_dash="dash", line_color=COLORS["orange"], opacity=0.4)
    fig.add_vline(x=19.5, line_dash="dash", line_color=COLORS["orange"], opacity=0.4)

    return fig


# ═══════════════════════════════════════════════════════════════════════
# CALLBACKS — Goal 1
# ═══════════════════════════════════════════════════════════════════════

@app.callback(
    Output("coverage-chart", "figure"),
    Input("k-slider", "value"),
)
def update_coverage(k):
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # MCLP T=14
    mclp14 = _solutions[(_solutions["Objective"] == "MCLP") & (_solutions["T"] == 14)].sort_values("K")
    fig.add_trace(go.Scatter(
        x=mclp14["K"], y=mclp14["Demand_Pct_Covered"],
        mode="lines+markers+text", name="14-min coverage",
        text=[f"{v:.0f}%" for v in mclp14["Demand_Pct_Covered"]],
        textposition="top center", textfont_size=12,
        line=dict(color=COLORS["green"], width=3), marker=dict(size=10),
    ), secondary_y=False)

    # MCLP T=10
    mclp10 = _solutions[(_solutions["Objective"] == "MCLP") & (_solutions["T"] == 10)].sort_values("K")
    fig.add_trace(go.Scatter(
        x=mclp10["K"], y=mclp10["Demand_Pct_Covered"],
        mode="lines+markers+text", name="10-min coverage",
        text=[f"{v:.0f}%" for v in mclp10["Demand_Pct_Covered"]],
        textposition="bottom center", textfont_size=11,
        line=dict(color=COLORS["orange"], width=2, dash="dash"), marker=dict(size=8),
    ), secondary_y=False)

    # Avg RT (P-Median)
    pmed = _solutions[_solutions["Objective"] == "PMed"].sort_values("K")
    fig.add_trace(go.Scatter(
        x=pmed["K"], y=pmed["Avg_RT"],
        mode="lines+markers", name="Avg RT (P-Median)",
        line=dict(color=COLORS["cyan"], width=2), marker=dict(size=8),
    ), secondary_y=True)

    # Highlight selected K
    fig.add_vline(x=k, line_dash="dot", line_color=COLORS["accent"], opacity=0.7,
                  annotation_text=f"K={k}", annotation_font_color=COLORS["accent"])

    fig.update_layout(
        title=dict(text="Secondary Network: Coverage vs Stations<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Elbow at K=3 (86% coverage within 14 min)</span>",
                   font_size=15),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        legend=dict(orientation="h", y=-0.2), margin=dict(t=70, b=80),
        xaxis=dict(dtick=1, title="Number of Secondary Stations"),
    )
    fig.update_yaxes(title_text="Secondary Demand Covered (%)", secondary_y=False)
    fig.update_yaxes(title_text="Avg Response Time (min)", secondary_y=True)

    return fig


@app.callback(
    Output("cost-chart", "figure"),
    Input("k-slider", "value"),
)
def update_cost(k):
    # Compute scenarios for selected K
    def scenario_a(k):
        op = k * PETERSON_OPERATING
        rev = k * PETERSON_REVENUE
        return {"Scenario": f"24/7 ALS\n({k} stations)", "Operating": op, "Revenue": rev, "Net": op - rev,
                "FTE": k * 7.2}

    def scenario_b(k):
        salary = (371697 + 24894 + 178466 + 27761) * (2/3)
        fixed = 28000 + 3000 + 7000 + 2000 + 67500 + 500 + 1000 + 5000
        op = k * (salary + fixed)
        rev = k * PETERSON_REVENUE * 0.65
        return {"Scenario": f"Peak-Only\n08-20 ({k} sta)", "Operating": op, "Revenue": rev, "Net": op - rev,
                "FTE": k * 4.8}

    def scenario_c(k):
        if k < 2:
            return scenario_a(k)
        a = scenario_a(1)
        b = scenario_b(k - 1)
        return {"Scenario": f"Hybrid\n1×24/7 + {k-1}×peak", "Operating": a["Operating"] + b["Operating"],
                "Revenue": a["Revenue"] + b["Revenue"],
                "Net": a["Net"] + b["Net"], "FTE": a["FTE"] + b["FTE"]}

    scenarios = [scenario_a(k), scenario_b(k), scenario_c(k)]

    fig = go.Figure()
    names = [s["Scenario"] for s in scenarios]
    nets = [s["Net"] for s in scenarios]
    ftes = [s["FTE"] for s in scenarios]
    colors_bar = [COLORS["red"], COLORS["orange"], COLORS["green"]]

    fig.add_trace(go.Bar(
        x=names, y=nets, marker_color=colors_bar, opacity=0.85,
        text=[f"${n:,.0f}<br>{f:.1f} FTE" for n, f in zip(nets, ftes)],
        textposition="outside", textfont_size=12,
    ))

    fig.update_layout(
        title=dict(text=f"Staffing Cost Scenarios for K={k} Stations<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Based on Peterson cost model ($717K operating, $466K revenue/station)</span>",
                   font_size=15),
        yaxis_title="Annual Net Cost ($)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        showlegend=False, margin=dict(t=70, b=40),
        yaxis=dict(tickprefix="$", tickformat=","),
    )
    return fig


@app.callback(
    Output("secondary-demand-chart", "figure"),
    Input("k-slider", "value"),
)
def update_secondary_demand(_):
    # Load concurrent results
    conc = pd.read_csv(os.path.join(BASE, "concurrent_call_results.csv"))
    conc = conc.sort_values("Secondary_Events", ascending=True)

    colors = [COLORS["red"] if p >= 25 else COLORS["orange"] if p >= 12
              else COLORS["green"] for p in conc["Pct_Concurrent"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=conc["Dept"], x=conc["Secondary_Events"], orientation="h",
        marker_color=colors, opacity=0.85,
        text=[f"{int(e)} ({p:.0f}%) | All busy: {int(ab)}"
              for e, p, ab in zip(conc["Secondary_Events"], conc["Pct_Concurrent"],
                                   conc["All_Busy_Events"])],
        textposition="outside", textfont_size=10,
    ))

    fig.update_layout(
        title=dict(text="Secondary Demand by Department<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"Calls arriving while primary ambulance already on scene | CY2024</span>",
                   font_size=15),
        xaxis_title="Secondary Demand Events (calls with >= 1 concurrent)",
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=40, l=120), height=400,
    )
    return fig


@app.callback(
    Output("network-map", "figure"),
    Input("k-slider", "value"),
)
def update_network_map(k):
    # Get MCLP T=14 solution for this K
    sol_row = _solutions[(_solutions["Objective"] == "MCLP") & (_solutions["T"] == 14) & (_solutions["K"] == k)]
    if sol_row.empty:
        sol_row = _solutions[(_solutions["Objective"] == "PMed") & (_solutions["K"] == k)]

    fig = go.Figure()

    # Existing stations
    for dept, (lat, lon) in DEPT_COORDS.items():
        amb = AMBULANCE_COUNT.get(dept, 0)
        info = STAFFING.get(dept, {})
        fig.add_trace(go.Scattermapbox(
            lat=[lat], lon=[lon], mode="markers+text",
            marker=dict(size=10 + amb * 3, color=COLORS["accent"], opacity=0.6),
            text=[dept], textposition="top center",
            textfont=dict(size=10, color=COLORS["text"]),
            name=f"{dept} ({amb} amb)", showlegend=False,
            hovertemplate=f"<b>{dept}</b><br>{info.get('Level', '?')} | {amb} ambulances<br>"
                          f"{info.get('FT', '?')} FT + {info.get('PT', '?')} PT<extra></extra>",
        ))

    # Secondary stations from solution
    if not sol_row.empty:
        stations_str = sol_row.iloc[0]["Stations"]
        parts = [s.strip().strip("()") for s in stations_str.split("|")]
        lats_sorted = []
        for i, p in enumerate(parts):
            lat, lon = [float(x) for x in p.split(",")]
            lats_sorted.append((lat, lon, i))
        lats_sorted.sort(key=lambda x: x[0], reverse=True)

        zone_names = ["North", "Central", "South"] if len(parts) == 3 else \
                     ["North", "South"] if len(parts) == 2 else \
                     [f"Zone {j+1}" for j in range(len(parts))]
        if len(parts) == 4:
            zone_names = ["North", "Central-1", "Central-2", "South"]
        elif len(parts) == 5:
            zone_names = ["North", "North-Central", "Central", "South-Central", "South"]

        for rank, (lat, lon, orig_idx) in enumerate(lats_sorted):
            zn = zone_names[rank] if rank < len(zone_names) else f"Zone {rank+1}"
            fig.add_trace(go.Scattermapbox(
                lat=[lat], lon=[lon], mode="markers+text",
                marker=dict(size=20, color=COLORS["red"], symbol="star"),
                text=[f"SEC-{rank+1} ({zn})"], textposition="bottom center",
                textfont=dict(size=11, color=COLORS["red"]),
                name=f"Secondary {rank+1}: {zn}", showlegend=False,
                hovertemplate=f"<b>Secondary Station {rank+1}</b><br>"
                              f"Zone: {zn}<br>({lat:.3f}, {lon:.3f})<extra></extra>",
            ))

    cov = sol_row.iloc[0]["Demand_Pct_Covered"] if not sol_row.empty else "?"
    avg_rt = sol_row.iloc[0]["Avg_RT"] if not sol_row.empty else "?"

    fig.update_layout(
        mapbox=dict(
            style="carto-positron",
            center=dict(lat=43.01, lon=-88.78),
            zoom=9.5,
        ),
        title=dict(text=f"Secondary Network: {k} Stations (MCLP T=14)<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"{cov}% secondary demand within 14 min | Avg RT: {avg_rt} min</span>",
                   font_size=15),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        margin=dict(t=70, b=20, l=20, r=20), height=500,
    )
    return fig


@app.callback(
    Output("concurrent-heatmap", "figure"),
    Input("dept-dropdown", "value"),
)
def update_concurrent_heatmap(_):
    # Compute from raw data: concurrent rate by hour × DOW (county-wide)
    valid = _ems.dropna(subset=["Alarm_DT", "Cleared_DT"]).copy()

    # Quick concurrent detection: for each dept, use sorted alarms
    conc_flags = []
    for dept, group in valid.groupby("Dept"):
        g = group.sort_values("Alarm_DT")
        alarms = g["Alarm_DT"].values
        cleared = g["Cleared_DT"].values
        n = len(g)
        is_conc = np.zeros(n, dtype=bool)
        for i in range(n):
            for j in range(i + 1, n):
                if alarms[j] >= cleared[i]:
                    break
                is_conc[i] = True
                is_conc[j] = True
        g = g.copy()
        g["IsConc"] = is_conc
        conc_flags.append(g)

    cf = pd.concat(conc_flags)

    total = cf.groupby(["Hour", "DOW"]).size().unstack(fill_value=0)
    conc_count = cf[cf["IsConc"]].groupby(["Hour", "DOW"]).size().unstack(fill_value=0)
    rate = (conc_count / total.replace(0, np.nan) * 100).fillna(0)

    for d in DOW_ORDER:
        if d not in rate.columns:
            rate[d] = 0
    rate = rate[DOW_ORDER].sort_index()

    fig = go.Figure(data=go.Heatmap(
        z=rate.values, x=DOW_ORDER,
        y=[f"{h:02d}:00" for h in range(24)],
        colorscale="YlOrRd", colorbar=dict(title="% Concurrent"),
        hovertemplate="Day: %{x}<br>Hour: %{y}<br>Rate: %{z:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text="County-Wide Concurrent Call Rate (Hour × Day)<br>"
                        f"<span style='font-size:12px;color:{COLORS['muted']}'>"
                        f"% of EMS calls with another active call in same department</span>",
                   font_size=15),
        template="plotly_dark", paper_bgcolor=COLORS["card"], plot_bgcolor=COLORS["card"],
        height=500, margin=dict(t=70, b=40),
    )
    return fig


# ── Run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=False, port=8051)
