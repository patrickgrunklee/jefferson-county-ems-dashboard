"""
Generate a presentation-ready 2-color stacked bar chart:
  Fire apparatus (red) vs EMS apparatus (orange)
  White background, suitable for UW-branded slides.
"""
import plotly.graph_objects as go

# ── Data from MABAS Division 118 filings ──────────────────────────────────
data = [
    # Municipality,       Fire, EMS (ambulances)
    ("Jefferson",          11,   5),
    ("Fort Atkinson",      12,   3),
    ("Whitewater",          9,   4),
    ("Lake Mills",          9,   3),
    ("Watertown",           8,   3),
    ("Waterloo",            8,   2),
    ("Cambridge",           9,   0),
    ("Johnson Creek",       8,   2),
    ("Ixonia",              6,   1),
    ("Sullivan",            6,   0),
    ("Helenville",          6,   0),
    ("Rome",                6,   0),
    ("Palmyra",             4,   1),
    ("Western Lakes",       0,   0),
]

# Sort by total apparatus descending (for horizontal bar, ascending means
# biggest at top)
data.sort(key=lambda r: r[1] + r[2])

# Exclude Western Lakes (0 units)
data = [r for r in data if r[1] + r[2] > 0]

munis = [r[0] for r in data]
fire  = [r[1] for r in data]
ems   = [r[2] for r in data]

# ── UW-branded colors ─────────────────────────────────────────────────────
UW_RED   = "#C5050C"   # UW-Madison Badger Red
EMS_BLUE = "#0479A8"   # Complementary teal-blue for EMS

fig = go.Figure()

fig.add_trace(go.Bar(
    y=munis, x=fire,
    name="Fire Apparatus",
    orientation="h",
    marker_color=UW_RED,
    text=fire, textposition="inside",
    textfont=dict(color="white", size=13, family="Inter, Segoe UI, Arial"),
    hovertemplate="<b>%{y}</b><br>Fire: %{x}<extra></extra>",
))

fig.add_trace(go.Bar(
    y=munis, x=ems,
    name="EMS Apparatus (Ambulances)",
    orientation="h",
    marker_color=EMS_BLUE,
    text=[e if e > 0 else "" for e in ems],
    textposition="inside",
    textfont=dict(color="white", size=13, family="Inter, Segoe UI, Arial"),
    hovertemplate="<b>%{y}</b><br>EMS: %{x}<extra></extra>",
))

fig.update_layout(
    barmode="stack",
    title=dict(
        text=(
            "<b>Total Apparatus Fleet by Municipality</b><br>"
            "<span style='font-size:13px;color:#666'>Fire vs EMS units — MABAS Division 118 filings</span>"
        ),
        font=dict(size=18, color="#222", family="Inter, Segoe UI, Arial"),
        x=0.0, xanchor="left",
    ),
    xaxis=dict(
        title=dict(text="Number of Units", font=dict(size=13, color="#444")),
        tickfont=dict(size=12, color="#444"),
        gridcolor="#E5E5E5",
        zeroline=False,
    ),
    yaxis=dict(
        title=dict(text=""),
        tickfont=dict(size=13, color="#333"),
        automargin=True,
    ),
    legend=dict(
        orientation="h",
        yanchor="top", y=-0.12,
        xanchor="center", x=0.5,
        font=dict(size=13, color="#333"),
    ),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=130, r=40, t=80, b=60),
    height=480,
    width=700,
    bargap=0.25,
)

# Save as PNG for slide insertion
fig.write_image("slide_fleet_fire_vs_ems.png", scale=3)
print("Saved: slide_fleet_fire_vs_ems.png")

# Also open interactive
fig.show()
