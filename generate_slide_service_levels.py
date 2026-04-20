"""
Generate a presentation-ready pie chart showing EMS service levels
across Jefferson County municipalities. White background for UW slides.
"""
import plotly.graph_objects as go

# ── Data from ALS_LEVELS in dashboard ─────────────────────────────────────
# 13 EMS providers (excluding Rome & Sullivan which are fire-only)
service_levels = {
    "ALS (Advanced Life Support)": [
        "Watertown", "Fort Atkinson", "Whitewater", "Jefferson",
        "Johnson Creek", "Edgerton", "Cambridge", "Western Lakes"
    ],
    "AEMT (Advanced EMT)": [
        "Waterloo"
    ],
    "BLS (Basic Life Support)": [
        "Palmyra", "Ixonia", "Helenville", "Lake Mills"
    ],
}

labels = list(service_levels.keys())
values = [len(v) for v in service_levels.values()]
munis_text = [", ".join(v) for v in service_levels.values()]

# UW-compatible colors
colors = ["#C5050C", "#0479A8", "#646569"]  # UW Red, Teal, Gray

fig = go.Figure(go.Pie(
    labels=labels,
    values=values,
    marker=dict(colors=colors, line=dict(color="white", width=2)),
    textinfo="label+value",
    textfont=dict(size=14, color="white", family="Inter, Segoe UI, Arial"),
    hovertemplate="<b>%{label}</b><br>Departments: %{value}<br>%{customdata}<extra></extra>",
    customdata=munis_text,
    hole=0.35,
    sort=False,  # keep ALS first (largest slice at top)
))

# Add center text
fig.add_annotation(
    text="<b>13</b><br>EMS<br>Providers",
    x=0.5, y=0.5, font=dict(size=16, color="#333", family="Inter, Segoe UI, Arial"),
    showarrow=False, xref="paper", yref="paper",
)

fig.update_layout(
    title=dict(
        text=(
            "<b>EMS Service Levels by Municipality</b><br>"
            "<span style='font-size:13px;color:#666'>Jefferson County — 13 EMS providers</span>"
        ),
        font=dict(size=18, color="#222", family="Inter, Segoe UI, Arial"),
        x=0.5, xanchor="center",
    ),
    legend=dict(
        orientation="h",
        yanchor="top", y=-0.05,
        xanchor="center", x=0.5,
        font=dict(size=12, color="#333"),
    ),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=40, r=40, t=80, b=80),
    height=500,
    width=600,
)

fig.write_image("slide_ems_service_levels.png", scale=3)
print("Saved: slide_ems_service_levels.png")
fig.show()
