"""
Visualizes call-volume-weighted NFPA 1720 compliance for Jefferson County
primary EMS units. Shows what % of actual calls are served within the
zone-appropriate response time standard.

Output: primary_nfpa_compliance.png
"""
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import ems_dashboard_app as m

rt   = m.rt_clean
auth = m.AUTH_EMS_CALLS

NFPA = {
    'Watertown':     ('Urban',    9),
    'Fort Atkinson': ('Urban',    9),
    'Jefferson':     ('Suburban', 10),
    'Whitewater':    ('Suburban', 10),
    'Johnson Creek': ('Suburban', 10),
    'Waterloo':      ('Suburban', 10),
    'Lake Mills':    ('Suburban', 10),
    'Ixonia':        ('Rural',    14),
    'Edgerton':      ('Rural',    14),
    'Western Lakes': ('Rural',    14),
    'Cambridge':     ('Rural',    14),
    'Palmyra':       ('Rural',    14),
}

ZONE_COLORS = {
    'Urban':    '#e74c3c',
    'Suburban': '#e67e22',
    'Rural':    '#3498db',
}
ZONE_TARGETS = {'Urban': 0.90, 'Suburban': 0.80, 'Rural': 0.80}
ZONE_THRESH  = {'Urban': 9,    'Suburban': 10,    'Rural': 14}

total_calls = sum(auth.values())

rows = []
for dept, (zone, thresh) in NFPA.items():
    dept_calls = auth.get(dept, 0)
    drt = rt[rt['Department'] == dept]['RT']
    if len(drt) == 0:
        pct = None
    else:
        pct = float((drt <= thresh).mean())
    rows.append({
        'Dept': dept, 'Zone': zone, 'Threshold': thresh,
        'Calls': dept_calls,
        'Pct': pct,
        'Compliant': dept_calls * pct if pct is not None else None,
        'NonCompliant': dept_calls * (1 - pct) if pct is not None else None,
    })

df = pd.DataFrame(rows).sort_values('Calls', ascending=True)

# County aggregate
known = df.dropna(subset=['Compliant'])
county_pct = known['Compliant'].sum() / known['Calls'].sum() * 100

# ── Plot ───────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7),
                                gridspec_kw={'width_ratios': [2.2, 1]})
fig.patch.set_facecolor('white')

def _spine(ax):
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.spines['left'].set_color('#ccc')
    ax.spines['bottom'].set_color('#ccc')
    ax.tick_params(colors='#555', labelsize=10)

# ── Left: stacked horizontal bar per dept ─────────────────────────────────
y = np.arange(len(df))

for i, (_, row) in enumerate(df.iterrows()):
    zone  = row['Zone']
    col   = ZONE_COLORS[zone]
    calls = row['Calls']
    if row['Pct'] is None:
        ax1.barh(i, calls, 0.6, color='#cccccc', edgecolor='white')
        ax1.text(calls + 30, i, 'No RT data', va='center', fontsize=8.5, color='#999')
        continue
    comp  = row['Compliant']
    nonc  = row['NonCompliant']
    ax1.barh(i, comp, 0.6, color=col,     edgecolor='white', alpha=0.85)
    ax1.barh(i, nonc, 0.6, color=col,     edgecolor='white', alpha=0.25,
             left=comp)
    # % label inside compliant bar
    pct_label = f"{row['Pct']*100:.0f}%"
    ax1.text(comp / 2, i, pct_label, va='center', ha='center',
             fontsize=9, color='white', fontweight='bold')
    # call count at end
    ax1.text(calls + 30, i,
             f"{int(calls):,} calls",
             va='center', fontsize=8.5, color='#555')
    # NFPA target marker
    target = ZONE_TARGETS[zone]
    target_x = calls * target
    ax1.plot(target_x, i, '|', color='black', markersize=14,
             markeredgewidth=1.5, zorder=5)

ax1.set_yticks(y)
ax1.set_yticklabels(df['Dept'], fontsize=10)
ax1.set_xlabel('Number of Calls', fontsize=11)
ax1.set_title('Primary Unit NFPA 1720 Compliance\nby Department  |  CY2024',
              fontsize=13, fontweight='bold', pad=10)

# Zone legend
legend_els = [
    Patch(facecolor=ZONE_COLORS['Urban'],    alpha=0.85, label=f"Urban    (>=1,000/sqmi)  ->  <=9 min,  90% target"),
    Patch(facecolor=ZONE_COLORS['Suburban'], alpha=0.85, label=f"Suburban (500-999/sqmi)  ->  <=10 min, 80% target"),
    Patch(facecolor=ZONE_COLORS['Rural'],    alpha=0.85, label=f"Rural    (<500/sqmi)     ->  <=14 min, 80% target"),
    Patch(facecolor='#cccccc',               alpha=0.85, label="No RT data available"),
]
ax1.legend(handles=legend_els, fontsize=8.5, frameon=False,
           loc='lower right', title='NFPA 1720 Zones', title_fontsize=9)
ax1.text(0.01, 0.01,
         "Colored bar = compliant calls  |  Faded bar = non-compliant\n"
         "| mark = NFPA target threshold (90% or 80% of dept calls)",
         transform=ax1.transAxes, fontsize=8, color='#777')
ax1.set_xlim(0, df['Calls'].max() * 1.18)
_spine(ax1)

# ── Right: county aggregate donut ─────────────────────────────────────────
compliant_total    = known['Compliant'].sum()
noncompliant_total = known['Calls'].sum() - compliant_total
no_data_total      = df[df['Pct'].isna()]['Calls'].sum()

sizes  = [compliant_total, noncompliant_total, no_data_total]
colors = ['#27ae60', '#e74c3c', '#cccccc']
labels = [f"Compliant\n{compliant_total:,.0f} calls",
          f"Non-compliant\n{noncompliant_total:,.0f} calls",
          f"No RT data\n{no_data_total:,.0f} calls"]
wedges, _ = ax2.pie(sizes, colors=colors, startangle=90,
                    wedgeprops=dict(width=0.55, edgecolor='white', linewidth=2))

# Center text
ax2.text(0, 0.08,  f"{county_pct:.1f}%",
         ha='center', va='center', fontsize=28, fontweight='bold', color='#27ae60')
ax2.text(0, -0.22, "of calls served\nwithin NFPA\nzone standard",
         ha='center', va='center', fontsize=10, color='#555')

ax2.set_title('County-Wide Weighted\nCompliance  |  CY2024',
              fontsize=13, fontweight='bold', pad=10)

legend_els2 = [
    Patch(facecolor='#27ae60', label=f"Compliant ({compliant_total:,.0f} calls)"),
    Patch(facecolor='#e74c3c', label=f"Non-compliant ({noncompliant_total:,.0f} calls)"),
    Patch(facecolor='#cccccc', label=f"No RT data ({no_data_total:,.0f} calls, Lake Mills)"),
]
ax2.legend(handles=legend_els2, fontsize=8.5, frameon=False,
           loc='lower center', bbox_to_anchor=(0.5, -0.18))

ax2.text(0, -0.62,
         "Note: NFPA 1720 standards apply to primary response units.\n"
         "No formal standard exists for secondary/backup ambulances.\n"
         "Zone thresholds applied by each dept's dominant density class.",
         ha='center', fontsize=8, color='#888', style='italic',
         transform=ax2.transAxes)

fig.suptitle(
    "Jefferson County EMS — Primary Response NFPA 1720 Compliance\n"
    "Call-volume weighted  |  Zone-appropriate thresholds  |  CY2024 NFIRS",
    fontsize=13, fontweight='bold', y=1.01
)
plt.tight_layout()
out = os.path.join(SCRIPT_DIR, 'primary_nfpa_compliance.png')
fig.savefig(out, dpi=160, bbox_inches='tight', facecolor='white')
plt.close(fig)
print(f"Saved: {out}")
print(f"County-wide weighted compliance: {county_pct:.1f}%")
