"""
Generate a presentation-ready Efficiency Matrix chart (light theme, larger text).
Outputs: slide_efficiency.png (static image for slides).

Reproduces the Revenue Recovery vs. Cost per EMS Call bubble chart from the dashboard
but with a white background, larger fonts, and slide-friendly sizing.
"""

import plotly.graph_objects as go
import math

FONT = "'Inter', 'Segoe UI', system-ui, Arial, sans-serif"

# ── Data (from dashboard _build_util_df output) ──────────────────────────────
# Each row: Municipality, Cost_Per_EMS_Call, Revenue_Recovery %, EMS_Calls, Service_Level
DATA = [
    # Municipality         Cost/EMS  RevRecov%  EMS_Calls  ServiceLevel
    ("Ixonia",              2427,     19.8,       260,      "AEMT"),
    ("Jefferson",          16487,     48.8,        91,      "ALS"),
    ("Watertown",           1969,     21.3,      1947,      "ALS"),
    ("Fort Atkinson",        469,     93.8,      1621,      "ALS"),
    ("Whitewater",          1872,     23.1,      1448,      "ALS"),
    ("Cambridge",           1437,      0.0,        64,      "ALS"),
    ("Lake Mills",          None,      2.3,      None,      "BLS"),  # skip — no EMS call data
    ("Waterloo",            2735,     18.1,       403,      "ALS"),
    ("Johnson Creek",       2498,     25.4,       454,      "ALS"),
    ("Palmyra",             6867,     17.1,        32,      "BLS"),
]
# Edgerton: multi-county, EMS_Revenue=None → skip
# Rome and Sullivan are fire-only (not EMS providers) — excluded entirely from analysis
# Helenville: 0 EMS calls → skip
# Western Lakes: 5403 EMS calls, Cost/EMS = ~123, RevRecov ~22% — huge outlier on call volume
# Lake Mills: EMS_Calls from KPI = 0 (no NFIRS), skip

# Filter out rows with missing cost data
DATA = [(m, c, r, e, s) for m, c, r, e, s in DATA if c is not None and e is not None]

max_ems = max(d[3] for d in DATA)

# ── Service level colors (same hues as dashboard, slightly adjusted for light bg) ─
SVC_COLORS = {
    "ALS":  "#E8833A",  # warm orange
    "AEMT": "#4A90D9",  # medium blue
    "BLS":  "#10B981",  # emerald green
}

# ── Manual label offsets for crowded cluster ──────────────────────────────────
# (dx, dy in data coords offset from the point, anchor)
LABEL_POS = {
    "Ixonia":        (0, 1300,  "center"),
    "Jefferson":     (0, 1000,  "center"),
    "Watertown":     (-10, 500, "right"),
    "Fort Atkinson": (0, 1000,  "center"),
    "Whitewater":    (8, -1100, "center"),
    "Cambridge":     (0, -800,  "center"),
    "Waterloo":      (-10, 1200,"right"),
    "Johnson Creek": (8, 1000,  "center"),
    "Palmyra":       (0, 800,   "center"),
}

# ── Build figure ──────────────────────────────────────────────────────────────
fig = go.Figure()

# Main scatter (bubbles only — labels added as annotations)
fig.add_trace(go.Scatter(
    x=[d[2] for d in DATA],
    y=[d[1] for d in DATA],
    mode="markers",
    marker=dict(
        size=[(d[3] / max_ems * 55 + 14) for d in DATA],
        color=[SVC_COLORS.get(d[4], "#999") for d in DATA],
        line=dict(width=1.5, color="#555"),
        opacity=0.85,
    ),
    hovertemplate=(
        "<b>%{text}</b><br>"
        "Cost/EMS Call: $%{y:,.0f}<br>"
        "Revenue Recovery: %{x:.1f}%<br>"
        "<extra></extra>"
    ),
    text=[d[0] for d in DATA],
    showlegend=False,
))

# Add labels as annotations with manual offsets
for name, cost, rec, ems, svc in DATA:
    dx, dy, anchor = LABEL_POS.get(name, (0, 600, "bottom center"))
    fig.add_annotation(
        x=rec + dx, y=cost + dy,
        text=f"<b>{name}</b>",
        showarrow=False,
        font=dict(size=14, color="#222", family=FONT),
        xanchor="center",
    )

# Legend proxies for service level
for lvl, col in SVC_COLORS.items():
    if any(d[4] == lvl for d in DATA):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=14, color=col, line=dict(color="#555", width=1)),
            name=lvl, showlegend=True,
        ))

# ── Layout: light theme, large text ──────────────────────────────────────────
fig.update_layout(
    title=dict(
        text=(
            "Efficiency Matrix: Revenue Recovery vs. Cost per EMS Call<br>"
            "<sup>Bubble size = EMS call volume  ·  Color = service level</sup>"
        ),
        font=dict(family=FONT, size=22, color="#222"),
        x=0.02, xanchor="left",
    ),
    font=dict(family=FONT, size=14, color="#333"),
    plot_bgcolor="white",
    paper_bgcolor="white",
    width=1100,
    height=700,
    margin=dict(l=90, r=50, t=100, b=110),
    xaxis=dict(
        title=dict(text="Revenue Recovery (%)", font=dict(size=18, color="#444")),
        tickfont=dict(size=15, color="#444"),
        ticksuffix="%",
        showgrid=False,
        showline=True,
        linecolor="#ccc",
        zeroline=False,
    ),
    yaxis=dict(
        title=dict(text="Cost per EMS Call ($)", font=dict(size=18, color="#444")),
        tickfont=dict(size=15, color="#444"),
        tickprefix="$",
        showgrid=False,
        showline=True,
        linecolor="#ccc",
        zeroline=False,
    ),
    legend=dict(
        orientation="h",
        yanchor="top", y=-0.10,
        xanchor="left", x=0,
        title=dict(text="Service Level:  ", font=dict(size=15, color="#666")),
        bgcolor="rgba(255,255,255,0.9)",
        bordercolor="#ccc",
        borderwidth=1,
        font=dict(size=15),
        itemsizing="constant",
    ),
)

# ── Export ────────────────────────────────────────────────────────────────────
import os
BASE = os.path.dirname(os.path.abspath(__file__))
out_png = os.path.join(BASE, "slide_efficiency.png")
out_html = os.path.join(BASE, "slide_efficiency.html")

fig.write_html(out_html)
print(f"Saved interactive: {out_html}")

try:
    fig.write_image(out_png, scale=2)  # 2x for retina-quality
    print(f"Saved PNG: {out_png}")
except Exception as e:
    print(f"PNG export failed ({e}).")
    print("Install kaleido: pip install kaleido")
    print(f"Or open {out_html} in browser and screenshot.")
