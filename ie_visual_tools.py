"""
Jefferson County EMS -Industrial Engineering Visual Tools
Generates diagnostic, process, planning, and comparison diagrams
and compiles them into a single PDF document.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
import os, math

OUT = os.path.join(os.path.dirname(__file__), "ie_diagrams")
os.makedirs(OUT, exist_ok=True)

# ── Color palette ───────────────────────────────────────────────────
C_BLUE   = "#2563EB"
C_RED    = "#DC2626"
C_GREEN  = "#16A34A"
C_AMBER  = "#D97706"
C_PURPLE = "#7C3AED"
C_TEAL   = "#0D9488"
C_GRAY   = "#6B7280"
C_PINK   = "#DB2777"
C_LIGHT  = "#F3F4F6"
C_BG     = "#FFFFFF"

DEPT_COLORS = {
    "Watertown": "#2563EB", "Fort Atkinson": "#16A34A", "Whitewater": "#7C3AED",
    "Edgerton": "#DC2626", "Jefferson": "#D97706", "Johnson Creek": "#0D9488",
    "Waterloo": "#DB2777", "Ixonia": "#6366F1", "Palmyra": "#EA580C",
    "Cambridge": "#64748B", "Lake Mills": "#0EA5E9", "Western Lakes": "#8B5CF6",
}

# ── Data ────────────────────────────────────────────────────────────
DEPTS = ["Watertown","Fort Atkinson","Whitewater","Edgerton","Jefferson",
         "Johnson Creek","Waterloo","Ixonia","Palmyra","Cambridge","Lake Mills"]

CALLS_2024 = dict(zip(DEPTS, [2012,1616,64,2138,1457,487,520,289,32,87,518]))
POP        = dict(zip(DEPTS, [16524,18629,4925,492,11192,5601,4603,5988,2957,342,11095]))
FT_STAFF   = dict(zip(DEPTS, [31,16,15,24,6,3,4,2,0,0,4]))
PT_STAFF   = dict(zip(DEPTS, [3,28,17,0,20,33,22,45,20,31,20]))
AMBULANCES = dict(zip(DEPTS, [3,3,2,2,5,2,2,1,1,0,3]))
ALS_LEVEL  = dict(zip(DEPTS, ["ALS","ALS","ALS","ALS","ALS","ALS","AEMT","BLS","BLS","ALS","BLS"]))
COST_CALL  = dict(zip(DEPTS, [1971,470,1872,347,16487,2498,2770,2446,25554,None,None]))
TOTAL_EXP  = dict(zip(DEPTS, [3833800,760950,2710609,704977,1500300,1134154,1102475,631144,817740,92000,347000]))
REV_PCT    = dict(zip(DEPTS, [21.3,93.8,23.1,None,48.8,25.4,18.1,19.8,17.1,0,2.3]))
RT_MEDIAN  = dict(zip(DEPTS, [5.0,4.0,5.0,6.0,7.0,7.0,7.0,10.0,5.0,None,None]))
RT_P90     = dict(zip(DEPTS, [9.0,8.0,10.0,12.0,11.0,11.4,11.2,16.0,10.4,None,None]))
SEC_PCT    = dict(zip(DEPTS, [33.7,12.9,29.1,37.7,2.2,13.0,23.1,12.3,0,6.2,None]))
UTIL_PCT   = dict(zip(DEPTS, [5.54,2.13,6.90,11.28,0.08,2.58,3.06,3.22,3.58,None,None]))
PEAK_UTIL  = dict(zip(DEPTS, [8.05,3.33,9.66,16.5,0.23,4.33,5.14,5.64,10.14,None,None]))

CALLS_FTE  = {"Watertown":59.8,"Fort Atkinson":53.9,"Whitewater":61.6,"Edgerton":84.7,
              "Jefferson":5.7,"Johnson Creek":19.7,"Waterloo":26.5,"Ixonia":10.5,"Palmyra":3.2}

# ────────────────────────────────────────────────────────────────────
# 1. AFFINITY DIAGRAM
# ────────────────────────────────────────────────────────────────────
def draw_affinity():
    fig, ax = plt.subplots(figsize=(16, 11))
    ax.set_xlim(0, 16); ax.set_ylim(0, 11)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(8, 10.6, "Affinity Diagram -Jefferson County EMS Issues",
            ha="center", va="center", fontsize=18, fontweight="bold", color="#1E293B")
    ax.text(8, 10.2, "Stakeholder interviews, budget data, and operational analysis grouped into themed clusters",
            ha="center", va="center", fontsize=10, color=C_GRAY, style="italic")

    groups = [
        ("Staffing &\nWorkforce", C_BLUE, [
            "106 FT + 259 PT across 12 depts",
            "Volunteer recruitment declining",
            "Paramedics deployed to BLS calls",
            "60-70% of calls are BLS-level",
            "Min 7.2 FTE needed for 24/7 coverage",
            "Jefferson: only 6 FT for 1,457 calls",
        ]),
        ("Financial\nSustainability", C_RED, [
            "County avg 27% revenue recovery",
            "Cost/call: $347 to $25,554",
            "Fort Atkinson self-sustaining (94%)",
            "EMS revenue funds fire depts",
            "No county-level EMS levy exists",
            "$13.6M total county EMS spend",
        ]),
        ("Coverage &\nResponse Time", C_GREEN, [
            "Median RT: 5-10 min (varies by dept)",
            "Ixonia P90 = 16 min (worst)",
            "64.9% coverage within 8 min",
            "Secondary demand 30-38% (top 3)",
            "Ixonia all-busy 12.3% of time",
            "10 hospitals across 4 counties",
        ]),
        ("Governance &\nContracts", C_PURPLE, [
            "13 independent agencies",
            "No unified medical direction",
            "Contract terms vary widely",
            "Auto-renew vs explicit renegotiation",
            "Territory boundaries set 'years ago'",
            "Cambridge withdrew EMS (2025)",
        ]),
        ("Equipment &\nAssets", C_AMBER, [
            "22 ambulances county-wide",
            "Most <5% daily utilization",
            "10-yr first-line / 20-yr backup cycle",
            "5 ambulances in Jefferson alone",
            "Ixonia: 1 ambulance, BLS only",
            "Replacement costs $200K-$350K+",
        ]),
    ]

    col_w, row_h = 2.9, 0.48
    x_positions = [0.3, 3.4, 6.5, 9.6, 12.7]

    for i, (title, color, items) in enumerate(groups):
        x = x_positions[i]
        # Header
        rect = FancyBboxPatch((x, 8.6), col_w, 1.1, boxstyle="round,pad=0.08",
                              facecolor=color, edgecolor="none", alpha=0.9)
        ax.add_patch(rect)
        ax.text(x + col_w/2, 9.15, title, ha="center", va="center",
                fontsize=11, fontweight="bold", color="white")

        # Sticky notes
        for j, item in enumerate(items):
            y = 8.0 - j * (row_h + 0.12)
            note_color = "#FEF3C7" if j % 2 == 0 else "#DBEAFE"
            shadow = FancyBboxPatch((x+0.04, y-0.02), col_w, row_h,
                                   boxstyle="round,pad=0.05",
                                   facecolor="#D1D5DB", edgecolor="none", alpha=0.4)
            ax.add_patch(shadow)
            note = FancyBboxPatch((x, y), col_w, row_h,
                                  boxstyle="round,pad=0.05",
                                  facecolor=note_color, edgecolor="#9CA3AF",
                                  linewidth=0.5, alpha=0.95)
            ax.add_patch(note)
            ax.text(x + 0.12, y + row_h/2, item, ha="left", va="center",
                    fontsize=7.0, color="#1E293B", wrap=True)

    # Source line
    ax.text(8, 0.15, "Sources: Departmental budgets (FY2024-25), NFIRS call data (CY2024), Chief interviews (Mar 2026), WI DOA population estimates",
            ha="center", va="center", fontsize=7, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "01_affinity_diagram.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [1/12] Affinity Diagram")


# ────────────────────────────────────────────────────────────────────
# 2. FISHBONE (ISHIKAWA) DIAGRAM
# ────────────────────────────────────────────────────────────────────
def draw_fishbone():
    fig, ax = plt.subplots(figsize=(18, 10))
    ax.set_xlim(-1, 19); ax.set_ylim(-1, 10)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(9, 9.6, "Fishbone Diagram -Why Are EMS Coverage Gaps Persistent?",
            ha="center", fontsize=17, fontweight="bold", color="#1E293B")

    # Spine
    ax.annotate("", xy=(17.5, 4.5), xytext=(0.5, 4.5),
                arrowprops=dict(arrowstyle="-|>", lw=3, color="#374151"))

    # Effect box
    effect = FancyBboxPatch((15.0, 3.4), 3.8, 2.2, boxstyle="round,pad=0.15",
                            facecolor="#FEE2E2", edgecolor=C_RED, linewidth=2)
    ax.add_patch(effect)
    ax.text(16.9, 4.5, "Inconsistent\nEMS Coverage\nAcross County",
            ha="center", va="center", fontsize=11, fontweight="bold", color=C_RED)

    bones = [
        (3.0, "Staffing", C_BLUE, [
            "Volunteer decline nationwide",
            "Paramedics on BLS calls (60-70%)",
            "PT/on-call pay too low ($7.50-10/hr)",
            "Min 7.2 FTE for 24/7; many below",
        ]),
        (6.5, "Funding", C_RED, [
            "No county EMS levy mechanism",
            "EMS revenue cross-subsidizes fire",
            "27% avg revenue recovery",
            "Cost/call varies 74x ($347-$25.5K)",
        ]),
        (10.0, "Geography", C_GREEN, [
            "860 sq mi rural county",
            "10 hospitals across 4 counties",
            "Territory boundaries decades old",
            "Ixonia: BLS-only, 10 min median RT",
        ]),
        (3.0, "Governance", C_PURPLE, [
            "13 independent agencies",
            "No unified medical direction",
            "Multiple doctors = inconsistent protocols",
            "Cambridge withdrew (2025)",
        ]),
        (6.5, "Equipment", C_AMBER, [
            "22 ambulances, most <5% utilized",
            "Jefferson: 5 ambulances, 91 calls",
            "Replacement timing uncoordinated",
            "BLS vs ALS capability mismatch",
        ]),
        (10.0, "Demand", C_TEAL, [
            "Secondary demand 30-38% (top depts)",
            "Ixonia all-busy 12.3% of time",
            "Peak hours strain small depts",
            "Call volume growing (collections +21%)",
        ]),
    ]

    for idx, (x, title, color, causes) in enumerate(bones):
        is_top = idx < 3
        y_dir = 1 if is_top else -1
        y_base = 4.5
        y_end = 8.5 if is_top else 0.5

        # Main bone
        ax.plot([x, x+2], [y_end, y_base], lw=2.2, color=color, zorder=2)

        # Category label
        label_y = y_end + 0.3*y_dir
        ax.text(x+1, label_y, title, ha="center", va="center",
                fontsize=12, fontweight="bold", color=color,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor=color, linewidth=1.5))

        # Sub-causes
        for j, cause in enumerate(causes):
            frac = 0.2 + j * 0.2
            cx = x + 2*frac
            cy = y_end + (y_base - y_end) * frac
            offset_x = -1.4 if j % 2 == 0 else 1.4
            tx = cx + offset_x
            ty = cy + 0.05 * y_dir

            ax.plot([cx, tx], [cy, ty], lw=0.8, color=color, alpha=0.6)
            ax.text(tx, ty + 0.15*y_dir, cause, ha="center", va="center",
                    fontsize=6.8, color="#374151",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="#F9FAFB",
                              edgecolor=color, alpha=0.7, linewidth=0.5))

    ax.text(9, -0.7, "Sources: NFIRS CY2024 call data, FY2025 budgets, Chief interviews (Waterloo 3/11/26, Johnson Creek 3/13/26)",
            ha="center", fontsize=7, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "02_fishbone_diagram.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [2/12] Fishbone Diagram")


# ────────────────────────────────────────────────────────────────────
# 3. FIVE-WHY ANALYSIS
# ────────────────────────────────────────────────────────────────────
def draw_five_why():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14); ax.set_ylim(0, 10)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(7, 9.6, "5-Why Analysis -Secondary Ambulance Coverage Gaps",
            ha="center", fontsize=16, fontweight="bold", color="#1E293B")

    levels = [
        ("PROBLEM", "Citizens in high-demand areas wait too long\nwhen primary ambulance is unavailable",
         C_RED, "#FEE2E2"),
        ("WHY 1", "Secondary ambulance response is 1-3 min slower\nand unavailable 12-38% of time in busy districts",
         C_AMBER, "#FEF3C7"),
        ("WHY 2", "Each department independently staffs its own backup\nambulance with part-time/volunteer crews",
         C_PURPLE, "#F3E8FF"),
        ("WHY 3", "No regional coordination mechanism exists —\n13 agencies operate as independent systems",
         C_BLUE, "#DBEAFE"),
        ("WHY 4", "Historical territory boundaries predate modern call volumes\nand were never designed for secondary coverage",
         C_TEAL, "#CCFBF1"),
        ("ROOT\nCAUSE", "No county-level governance structure to coordinate\nambulance placement, staffing, or mutual aid dispatch",
         C_RED, "#FEE2E2"),
    ]

    box_w, box_h = 10.0, 1.0
    x_start = 2.0
    y_start = 8.6
    gap = 1.42

    for i, (label, text, color, bg) in enumerate(levels):
        y = y_start - i * gap
        # Box
        rect = FancyBboxPatch((x_start, y), box_w, box_h,
                              boxstyle="round,pad=0.12",
                              facecolor=bg, edgecolor=color, linewidth=2)
        ax.add_patch(rect)
        # Label pill
        lbl = FancyBboxPatch((x_start+0.2, y+0.2), 1.5, 0.6,
                              boxstyle="round,pad=0.08",
                              facecolor=color, edgecolor="none")
        ax.add_patch(lbl)
        ax.text(x_start+0.95, y+0.5, label, ha="center", va="center",
                fontsize=8.5, fontweight="bold", color="white")
        # Text
        ax.text(x_start+2.2, y+0.5, text, ha="left", va="center",
                fontsize=9.5, color="#1E293B")

        # Arrow
        if i < len(levels) - 1:
            ax.annotate("", xy=(7, y - 0.08), xytext=(7, y - gap + box_h + 0.08),
                        arrowprops=dict(arrowstyle="-|>", lw=1.5, color=C_GRAY))
            ax.text(7.4, y - gap/2 + box_h/2 - 0.05, "Why?",
                    ha="left", va="center", fontsize=10, fontweight="bold",
                    color=C_GRAY, style="italic")

    # Data evidence callout
    evidence = ("Evidence: Edgerton 37.7%, Watertown 33.7%, Whitewater 29.1% secondary demand;\n"
                "Ixonia all-busy 12.3%; Cambridge 100% all-busy (withdrew 2025)")
    ax.text(7, 0.25, evidence, ha="center", va="center", fontsize=7.5,
            color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "03_five_why.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [3/12] 5-Why Analysis")


# ────────────────────────────────────────────────────────────────────
# 4. PARETO CHART
# ────────────────────────────────────────────────────────────────────
def draw_pareto():
    fig, ax1 = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(C_BG)

    # Sort by secondary demand events (absolute)
    dept_sec = {
        "Edgerton":768, "Watertown":656, "Whitewater":421,
        "Fort Atkinson":209, "Waterloo":93, "Johnson Creek":59,
        "Ixonia":32, "Cambridge":4, "Jefferson":2, "Palmyra":0,
    }
    sorted_d = sorted(dept_sec.items(), key=lambda x: -x[1])
    labels = [d[0] for d in sorted_d]
    values = [d[1] for d in sorted_d]
    total = sum(values)
    cumulative = np.cumsum(values) / total * 100

    colors = [DEPT_COLORS.get(l, C_GRAY) for l in labels]
    bars = ax1.bar(range(len(labels)), values, color=colors, alpha=0.85, zorder=3)
    ax1.set_ylabel("Secondary Ambulance Events (CY2024)", fontsize=11, color="#374151")
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax1.set_title("Pareto Chart -Secondary Ambulance Demand by Department",
                  fontsize=14, fontweight="bold", color="#1E293B", pad=15)

    # Bar labels
    for bar, val in zip(bars, values):
        if val > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                     str(val), ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    # Cumulative line
    ax2 = ax1.twinx()
    ax2.plot(range(len(labels)), cumulative, "o-", color=C_RED, lw=2, markersize=6, zorder=4)
    ax2.set_ylabel("Cumulative %", fontsize=11, color=C_RED)
    ax2.set_ylim(0, 105)
    ax2.axhline(80, ls="--", color=C_RED, alpha=0.4, lw=1)
    ax2.text(len(labels)-1.5, 82, "80% line", fontsize=8, color=C_RED, alpha=0.6)

    # Annotate 80% point
    for i, c in enumerate(cumulative):
        if c >= 80:
            ax2.annotate(f"{c:.0f}%", (i, c), textcoords="offset points",
                        xytext=(10, -15), fontsize=9, color=C_RED, fontweight="bold")
            break

    ax1.grid(axis="y", alpha=0.2)
    ax1.set_axisbelow(True)

    fig.text(0.5, 0.01, "Source: Phase A concurrent call analysis, CY2024 NFIRS data  |  "
             "3 departments account for 82% of all secondary demand",
             ha="center", fontsize=8, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "04_pareto_chart.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [4/12] Pareto Chart")


# ────────────────────────────────────────────────────────────────────
# 5. VALUE STREAM MAP
# ────────────────────────────────────────────────────────────────────
def draw_vsm():
    fig, ax = plt.subplots(figsize=(18, 9))
    ax.set_xlim(0, 18); ax.set_ylim(0, 9)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(9, 8.7, "Value Stream Map -EMS Call Response Process",
            ha="center", fontsize=16, fontweight="bold", color="#1E293B")

    steps = [
        ("911 Call\nReceived", "0-1 min", "Dispatch\nCenter", C_BLUE),
        ("Unit\nDispatched", "0.5-2 min", "Closest\nAvailable Unit", C_BLUE),
        ("En Route\nResponse", "3-8 min", "Primary\nAmbulance", C_GREEN),
        ("On Scene\nAssessment", "5-15 min", "Crew\nAssessment", C_TEAL),
        ("Patient\nTransport", "10-30 min", "To Hospital\n(1 of 10)", C_PURPLE),
        ("Hospital\nHandoff", "15-45 min", "Transfer\nof Care", C_AMBER),
        ("Billing &\nCollection", "30-180 days", "Revenue\nRecovery", C_RED),
    ]

    box_w, box_h = 2.0, 1.5
    y_center = 4.5
    x_positions = [0.5 + i*2.45 for i in range(7)]

    for i, (title, time, detail, color) in enumerate(steps):
        x = x_positions[i]
        # Process box
        rect = FancyBboxPatch((x, y_center - box_h/2), box_w, box_h,
                              boxstyle="round,pad=0.1",
                              facecolor="white", edgecolor=color, linewidth=2)
        ax.add_patch(rect)
        ax.text(x + box_w/2, y_center + 0.25, title, ha="center", va="center",
                fontsize=9, fontweight="bold", color=color)
        ax.text(x + box_w/2, y_center - 0.35, detail, ha="center", va="center",
                fontsize=7.5, color=C_GRAY)

        # Time box below
        time_rect = FancyBboxPatch((x+0.3, y_center - box_h/2 - 0.7), box_w-0.6, 0.45,
                                   boxstyle="round,pad=0.06",
                                   facecolor="#F3F4F6", edgecolor="#D1D5DB", linewidth=0.5)
        ax.add_patch(time_rect)
        ax.text(x + box_w/2, y_center - box_h/2 - 0.48, time,
                ha="center", va="center", fontsize=8, color="#374151", fontweight="bold")

        # Arrow
        if i < len(steps) - 1:
            ax.annotate("", xy=(x_positions[i+1], y_center),
                        xytext=(x + box_w, y_center),
                        arrowprops=dict(arrowstyle="-|>", lw=1.5, color="#9CA3AF"))

    # Waste / problem callouts (top)
    wastes = [
        (1.5, "Dispatch may not know\nwhich unit is closest"),
        (6.4, "Secondary response +1-3 min\nif primary unavailable"),
        (8.8, "BLS crew may need ALS\n→ intercept or re-dispatch"),
        (13.7, "10 hospitals in 4 counties\n= long transport times"),
        (16.2, "27% avg recovery\n= $10M+ unrealized revenue"),
    ]
    for wx, wtext in wastes:
        ax.annotate(wtext, xy=(wx, y_center + box_h/2 + 0.1),
                    xytext=(wx, y_center + box_h/2 + 1.4),
                    fontsize=7, ha="center", color=C_RED,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="#FEE2E2",
                              edgecolor=C_RED, linewidth=0.5),
                    arrowprops=dict(arrowstyle="-|>", color=C_RED, lw=0.8))

    # Total timeline
    ax.plot([0.5, 17.2], [2.0, 2.0], lw=1, color=C_GRAY, ls="--")
    ax.text(0.5, 1.7, "Value-Add Time", fontsize=8, color=C_GREEN, fontweight="bold")
    ax.text(0.5, 1.4, "~45 min (scene + transport)", fontsize=8, color=C_GREEN)
    ax.text(9, 1.7, "Total Lead Time", fontsize=8, color=C_RED, fontweight="bold")
    ax.text(9, 1.4, "~60-90 min (call to hospital handoff) + 30-180 days (billing)", fontsize=8, color=C_RED)

    ax.text(9, 0.8, "Source: Phase A-G analysis pipeline, CY2024 NFIRS data, Chief interviews (Mar 2026)",
            ha="center", fontsize=7, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "05_value_stream_map.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [5/12] Value Stream Map")


# ────────────────────────────────────────────────────────────────────
# 6. SWIMLANE PROCESS FLOW
# ────────────────────────────────────────────────────────────────────
def draw_swimlane():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16); ax.set_ylim(0, 10)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(8, 9.7, "Swimlane Diagram -EMS Call Dispatch & Response Flow",
            ha="center", fontsize=15, fontweight="bold", color="#1E293B")

    lanes = [
        ("Dispatch Center", C_BLUE, 8.4),
        ("Primary Ambulance", C_GREEN, 6.4),
        ("Secondary / Mutual Aid", C_AMBER, 4.4),
        ("Hospital", C_PURPLE, 2.4),
    ]
    lane_h = 1.6

    for name, color, y in lanes:
        ax.fill_between([1.5, 15.5], y, y + lane_h, color=color, alpha=0.06)
        ax.plot([1.5, 15.5], [y, y], color=color, lw=0.5, alpha=0.3)
        ax.plot([1.5, 15.5], [y+lane_h, y+lane_h], color=color, lw=0.5, alpha=0.3)
        ax.text(0.75, y + lane_h/2, name, ha="center", va="center",
                fontsize=9, fontweight="bold", color=color, rotation=90)

    def pbox(x, y, text, color, w=1.8, h=0.7):
        r = FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.08",
                           facecolor="white", edgecolor=color, linewidth=1.5)
        ax.add_patch(r)
        ax.text(x, y, text, ha="center", va="center", fontsize=7.5, color="#1E293B")

    def diamond(x, y, text, color, w=1.6, h=0.65):
        pts = np.array([[x, y+h/2], [x+w/2, y], [x, y-h/2], [x-w/2, y], [x, y+h/2]])
        ax.fill(pts[:, 0], pts[:, 1], facecolor="#FEF3C7", edgecolor=color, linewidth=1.5)
        ax.text(x, y, text, ha="center", va="center", fontsize=7, color="#1E293B")

    def arrow(x1, y1, x2, y2, label=""):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", lw=1, color="#6B7280"))
        if label:
            mx, my = (x1+x2)/2, (y1+y2)/2
            ax.text(mx+0.1, my+0.1, label, fontsize=6.5, color=C_GRAY, style="italic")

    # Dispatch lane
    pbox(2.5, 9.2, "911 Call\nReceived", C_BLUE)
    pbox(4.8, 9.2, "Identify\nClosest Unit", C_BLUE)
    diamond(7.3, 9.2, "Primary\nAvailable?", C_BLUE)

    # Primary lane
    pbox(9.5, 7.2, "Dispatch\nPrimary", C_GREEN)
    pbox(11.5, 7.2, "En Route\n(3-8 min)", C_GREEN)
    pbox(13.5, 7.2, "On Scene\nAssessment", C_GREEN)

    # Secondary lane
    pbox(9.5, 5.2, "Request\nMutual Aid", C_AMBER)
    pbox(11.5, 5.2, "Secondary\nEn Route (+1-3 min)", C_AMBER, w=2.2)
    diamond(13.5, 5.2, "ALS\nNeeded?", C_AMBER)

    # Hospital lane
    pbox(11.5, 3.2, "Transport\n(10-30 min)", C_PURPLE)
    pbox(13.5, 3.2, "Hospital\nHandoff", C_PURPLE)
    pbox(15.0, 3.2, "Billing\n(30-180d)", C_PURPLE, w=1.4)

    # Arrows - dispatch
    arrow(3.4, 9.2, 4.0, 9.2)
    arrow(5.7, 9.2, 6.5, 9.2)
    # Yes path
    arrow(8.1, 9.2, 8.6, 7.2, "Yes")
    ax.plot([8.1, 8.6], [9.2, 7.2], lw=0, alpha=0)  # invisible
    # No path
    arrow(7.3, 8.55, 7.3, 5.85)
    ax.text(7.0, 6.8, "No", fontsize=7, color=C_RED, fontweight="bold")

    # Primary flow
    arrow(9.5, 8.55, 9.5, 7.55)
    arrow(10.4, 7.2, 10.5, 7.2)
    arrow(12.5, 7.2, 12.6, 7.2)
    arrow(13.5, 6.85, 11.5, 3.55)

    # Secondary flow
    arrow(7.3, 5.55, 8.6, 5.2)
    arrow(10.6, 5.2, 10.4, 5.2)
    arrow(12.6, 5.2, 12.7, 5.2)
    arrow(13.5, 4.88, 11.5, 3.55)

    # Hospital flow
    arrow(12.4, 3.2, 12.6, 3.2)
    arrow(14.2, 3.2, 14.3, 3.2)

    # Red callout
    ax.text(5.5, 4.9, "30-38% of calls in\ntop 3 depts trigger\nthis path", ha="center",
            fontsize=7.5, color=C_RED, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEE2E2",
                      edgecolor=C_RED, linewidth=0.8))
    ax.annotate("", xy=(7.3, 5.5), xytext=(6.4, 5.2),
                arrowprops=dict(arrowstyle="-|>", color=C_RED, lw=0.8))

    ax.text(8, 1.5, "Source: NFIRS CY2024 dispatch data, Phase A concurrent call analysis, Chief interviews",
            ha="center", fontsize=7, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "06_swimlane.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [6/12] Swimlane Diagram")


# ────────────────────────────────────────────────────────────────────
# 7. RACI MATRIX
# ────────────────────────────────────────────────────────────────────
def draw_raci():
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(0.5, 0.97, "RACI Matrix -Regional Secondary Ambulance Network Implementation",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=14, fontweight="bold", color="#1E293B")

    roles = ["County\nBoard", "EMS\nWorking\nGroup", "Dept\nChiefs", "Medical\nDirector", "Dispatch\nCenter", "ISyE\nTeam"]
    tasks = [
        "Authorize county EMS study",
        "Define secondary coverage zones",
        "Select ambulance placement sites",
        "Establish unified medical protocols",
        "Develop dispatch routing rules",
        "Hire county-funded EMTs",
        "Negotiate IGA modifications",
        "Implement peak staffing plan",
        "Monitor KPI dashboard",
        "Annual performance review",
    ]

    # R=Responsible, A=Accountable, C=Consulted, I=Informed
    matrix = [
        ["A","R","C","I","I","C"],
        ["I","A","R","C","C","R"],
        ["I","A","R","C","C","R"],
        ["I","C","C","R,A","I","I"],
        ["I","C","C","C","R,A","C"],
        ["A","R","C","I","I","I"],
        ["A","R","R","I","I","C"],
        ["I","A","R","C","R","R"],
        ["I","R","C","I","I","A"],
        ["A","R","C","C","C","I"],
    ]

    raci_colors = {"R": C_BLUE, "A": C_RED, "C": C_AMBER, "I": C_GRAY, "R,A": C_PURPLE}
    raci_bg = {"R": "#DBEAFE", "A": "#FEE2E2", "C": "#FEF3C7", "I": "#F3F4F6", "R,A": "#F3E8FF"}

    n_rows, n_cols = len(tasks), len(roles)
    cell_w, cell_h = 1.5, 0.65
    x_start, y_start = 4.0, 7.5

    # Column headers
    for j, role in enumerate(roles):
        x = x_start + j * cell_w + cell_w/2
        rect = FancyBboxPatch((x_start + j*cell_w + 0.05, y_start + 0.05),
                              cell_w - 0.1, 0.8,
                              boxstyle="round,pad=0.05",
                              facecolor=C_BLUE, edgecolor="none", alpha=0.9)
        ax.add_patch(rect)
        ax.text(x, y_start + 0.45, role, ha="center", va="center",
                fontsize=7.5, fontweight="bold", color="white")

    # Rows
    for i, task in enumerate(tasks):
        y = y_start - (i + 1) * cell_h
        bg = "#F9FAFB" if i % 2 == 0 else "white"
        ax.fill_between([0.2, x_start + n_cols * cell_w], y, y + cell_h,
                       color=bg, alpha=0.5)
        ax.text(x_start - 0.2, y + cell_h/2, task, ha="right", va="center",
                fontsize=8, color="#374151")

        for j, val in enumerate(matrix[i]):
            x = x_start + j * cell_w + cell_w/2
            color = raci_colors.get(val, C_GRAY)
            bg_c = raci_bg.get(val, "#F3F4F6")
            pill = FancyBboxPatch((x - 0.35, y + 0.1), 0.7, cell_h - 0.2,
                                  boxstyle="round,pad=0.06",
                                  facecolor=bg_c, edgecolor=color, linewidth=1)
            ax.add_patch(pill)
            ax.text(x, y + cell_h/2, val, ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    # Legend
    legend_y = y_start - (n_rows + 1) * cell_h - 0.3
    legend_items = [
        ("R", "Responsible", C_BLUE), ("A", "Accountable", C_RED),
        ("C", "Consulted", C_AMBER), ("I", "Informed", C_GRAY),
    ]
    for k, (code, label, color) in enumerate(legend_items):
        lx = 4.0 + k * 2.5
        ax.text(lx, legend_y, f"{code} = {label}", fontsize=9, color=color, fontweight="bold")

    ax.set_xlim(-0.5, 14); ax.set_ylim(legend_y - 0.5, y_start + 1.2)

    fig.savefig(os.path.join(OUT, "07_raci_matrix.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [7/12] RACI Matrix")


# ────────────────────────────────────────────────────────────────────
# 8. FACILITY LOCATION MATRIX (Weighted Scoring)
# ────────────────────────────────────────────────────────────────────
def draw_facility_matrix():
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(0.5, 0.97, "Facility Location Matrix -Secondary Ambulance Placement Scoring",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=14, fontweight="bold", color="#1E293B")

    criteria = [
        ("Coverage gap severity", 0.30),
        ("Secondary call volume", 0.25),
        ("Response time improvement", 0.20),
        ("Existing infrastructure", 0.15),
        ("Cost efficiency", 0.10),
    ]

    # Candidate sites with scores (1-5)
    sites = {
        "Edgerton\n(Hwy 73/I-90)":   [5, 5, 4, 4, 3],
        "Whitewater-\nPalmyra Corridor": [4, 3, 5, 2, 3],
        "Ixonia\nFire Station":       [5, 2, 4, 5, 4],
        "Waterloo-\nJefferson Link":    [3, 3, 3, 3, 4],
        "Lake Mills\n(I-94 Corridor)":  [3, 3, 3, 4, 3],
    }

    weights = [c[1] for c in criteria]
    crit_names = [c[0] for c in criteria]

    cell_w, cell_h = 1.8, 0.6
    x_start, y_start = 4.0, 6.5
    n_crit = len(criteria)

    # Header row - criteria
    for j, (name, w) in enumerate(criteria):
        x = x_start + j * cell_w + cell_w/2
        rect = FancyBboxPatch((x_start + j*cell_w + 0.05, y_start + 0.6),
                              cell_w - 0.1, 1.0,
                              boxstyle="round,pad=0.05",
                              facecolor=C_BLUE, edgecolor="none", alpha=0.9)
        ax.add_patch(rect)
        ax.text(x, y_start + 1.1, name, ha="center", va="center",
                fontsize=7.5, fontweight="bold", color="white")
        ax.text(x, y_start + 0.75, f"Weight: {w:.0%}", ha="center", va="center",
                fontsize=7, color="#DBEAFE")

    # Weighted score column
    ws_x = x_start + n_crit * cell_w + cell_w/2
    rect = FancyBboxPatch((x_start + n_crit*cell_w + 0.05, y_start + 0.6),
                          cell_w - 0.1, 1.0,
                          boxstyle="round,pad=0.05",
                          facecolor=C_RED, edgecolor="none", alpha=0.9)
    ax.add_patch(rect)
    ax.text(ws_x, y_start + 1.1, "Weighted", ha="center", va="center",
            fontsize=8, fontweight="bold", color="white")
    ax.text(ws_x, y_start + 0.75, "Score", ha="center", va="center",
            fontsize=7, color="#FEE2E2")

    # Rank column
    rk_x = x_start + (n_crit+1) * cell_w + cell_w/2
    rect = FancyBboxPatch((x_start + (n_crit+1)*cell_w + 0.05, y_start + 0.6),
                          cell_w - 0.1, 1.0,
                          boxstyle="round,pad=0.05",
                          facecolor=C_GREEN, edgecolor="none", alpha=0.9)
    ax.add_patch(rect)
    ax.text(rk_x, y_start + 1.1, "Rank", ha="center", va="center",
            fontsize=8, fontweight="bold", color="white")

    # Compute weighted scores
    site_scores = {}
    for name, scores in sites.items():
        ws = sum(s * w for s, w in zip(scores, weights))
        site_scores[name] = ws

    ranked = sorted(site_scores.items(), key=lambda x: -x[1])
    rank_map = {name: i+1 for i, (name, _) in enumerate(ranked)}

    # Data rows
    for i, (site_name, scores) in enumerate(sites.items()):
        y = y_start - (i) * (cell_h + 0.15)
        bg = "#F0FDF4" if rank_map[site_name] == 1 else ("#FEF3C7" if rank_map[site_name] == 2 else "white")

        # Site name
        ax.text(x_start - 0.2, y + cell_h/2, site_name, ha="right", va="center",
                fontsize=8.5, fontweight="bold" if rank_map[site_name] <= 2 else "normal",
                color="#1E293B")

        for j, score in enumerate(scores):
            x = x_start + j * cell_w + cell_w/2
            # Color intensity by score
            intensity = score / 5
            color = plt.cm.RdYlGn(0.2 + intensity * 0.6)
            pill = FancyBboxPatch((x - 0.4, y + 0.05), 0.8, cell_h - 0.1,
                                  boxstyle="round,pad=0.05",
                                  facecolor=color, edgecolor="none", alpha=0.7)
            ax.add_patch(pill)
            ax.text(x, y + cell_h/2, str(score), ha="center", va="center",
                    fontsize=10, fontweight="bold", color="#1E293B")

        # Weighted score
        ws = site_scores[site_name]
        pill = FancyBboxPatch((ws_x - 0.5, y + 0.05), 1.0, cell_h - 0.1,
                              boxstyle="round,pad=0.05",
                              facecolor="#FEE2E2" if rank_map[site_name] == 1 else "#F3F4F6",
                              edgecolor=C_RED if rank_map[site_name] == 1 else "#D1D5DB",
                              linewidth=1)
        ax.add_patch(pill)
        ax.text(ws_x, y + cell_h/2, f"{ws:.2f}", ha="center", va="center",
                fontsize=10, fontweight="bold", color=C_RED if rank_map[site_name] <= 2 else "#374151")

        # Rank
        rank = rank_map[site_name]
        medal = {1: "#1", 2: "#2", 3: "#3"}.get(rank, str(rank))
        ax.text(rk_x, y + cell_h/2, medal if rank <= 3 else str(rank),
                ha="center", va="center", fontsize=12 if rank <= 3 else 10)

    # Scale legend
    leg_y = y_start - len(sites) * (cell_h + 0.15) - 0.5
    ax.text(4.0, leg_y, "Scale:  1 = Poor  |  2 = Below Avg  |  3 = Average  |  4 = Good  |  5 = Excellent",
            fontsize=8, color=C_GRAY)
    ax.text(4.0, leg_y - 0.35,
            "Source: Phase B-G analysis (hotspot ranking, utilization, coverage gaps, existing station locations)",
            fontsize=7, color=C_GRAY, style="italic")

    ax.set_xlim(-0.5, 18); ax.set_ylim(leg_y - 0.8, y_start + 2.0)

    fig.savefig(os.path.join(OUT, "08_facility_matrix.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [8/12] Facility Location Matrix")


# ────────────────────────────────────────────────────────────────────
# 9. RADAR / SPIDER CHART
# ────────────────────────────────────────────────────────────────────
def draw_radar():
    categories = ["Calls/FTE", "Response\nTime", "Revenue\nRecovery", "Ambulance\nUtilization",
                  "ALS\nCapability", "Cost\nEfficiency"]
    N = len(categories)
    angles = [n / float(N) * 2 * math.pi for n in range(N)]
    angles += angles[:1]

    # Normalize each metric to 0-1 (higher = better)
    def norm(val, vmin, vmax, invert=False):
        if val is None: return 0
        n = (val - vmin) / (vmax - vmin) if vmax != vmin else 0.5
        return 1 - n if invert else n

    radar_depts = ["Watertown","Fort Atkinson","Edgerton","Johnson Creek","Waterloo","Ixonia","Palmyra"]

    als_score = {"ALS": 1.0, "AEMT": 0.6, "BLS": 0.3}

    data = {}
    for d in radar_depts:
        cfte = CALLS_FTE.get(d, 0)
        rt = RT_MEDIAN.get(d)
        rev = REV_PCT.get(d)
        util = UTIL_PCT.get(d)
        als = als_score.get(ALS_LEVEL.get(d, "BLS"), 0.3)
        cc = COST_CALL.get(d)

        vals = [
            norm(cfte, 0, 85),
            norm(rt, 4, 12, invert=True),
            norm(rev if rev else 0, 0, 100),
            norm(util if util else 0, 0, 12),
            als,
            norm(cc if cc else 25000, 300, 25000, invert=True),
        ]
        data[d] = vals + vals[:1]

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(C_BG)

    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10, fontweight="bold")
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=7, color=C_GRAY)
    ax.set_title("Radar Chart -Department Performance Comparison",
                 fontsize=14, fontweight="bold", color="#1E293B", pad=30)

    colors = [DEPT_COLORS.get(d, C_GRAY) for d in radar_depts]
    for i, (dept, vals) in enumerate(data.items()):
        ax.plot(angles, vals, "o-", linewidth=2, label=dept, color=colors[i], markersize=4)
        ax.fill(angles, vals, alpha=0.06, color=colors[i])

    ax.legend(loc="lower right", bbox_to_anchor=(1.3, -0.05), fontsize=9,
              frameon=True, facecolor="white", edgecolor="#D1D5DB")

    fig.text(0.5, 0.02, "Source: CY2024 NFIRS data, FY2025 budgets  |  All metrics normalized 0-100% (higher = better)",
             ha="center", fontsize=8, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "09_radar_chart.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print("  [9/12] Radar Chart")


# ────────────────────────────────────────────────────────────────────
# 10. PRIORITY MATRIX (Urgency vs Impact)
# ────────────────────────────────────────────────────────────────────
def draw_priority_matrix():
    fig, ax = plt.subplots(figsize=(11, 9))
    fig.patch.set_facecolor(C_BG)

    ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    ax.set_xlabel("Urgency (Coverage Gap Severity)", fontsize=12, fontweight="bold", labelpad=10)
    ax.set_ylabel("Impact (Potential Improvement)", fontsize=12, fontweight="bold", labelpad=10)
    ax.set_title("Priority Matrix -Where Secondary Coverage Is Most Needed",
                 fontsize=14, fontweight="bold", color="#1E293B", pad=15)

    # Quadrant shading
    ax.fill_between([5, 10], 5, 10, color="#DCFCE7", alpha=0.4)  # High-High
    ax.fill_between([0, 5], 5, 10, color="#FEF3C7", alpha=0.4)   # Low-High
    ax.fill_between([5, 10], 0, 5, color="#FEF3C7", alpha=0.4)   # High-Low
    ax.fill_between([0, 5], 0, 5, color="#F3F4F6", alpha=0.4)    # Low-Low

    ax.axhline(5, color="#D1D5DB", lw=1, ls="--")
    ax.axvline(5, color="#D1D5DB", lw=1, ls="--")

    # Quadrant labels
    ax.text(7.5, 9.5, "HIGH PRIORITY\n(Act Now)", ha="center", fontsize=10,
            fontweight="bold", color=C_GREEN, alpha=0.7)
    ax.text(2.5, 9.5, "PLAN\n(Strategic)", ha="center", fontsize=10,
            fontweight="bold", color=C_AMBER, alpha=0.7)
    ax.text(7.5, 0.5, "QUICK WIN\n(Low Effort)", ha="center", fontsize=10,
            fontweight="bold", color=C_AMBER, alpha=0.7)
    ax.text(2.5, 0.5, "LOW PRIORITY\n(Monitor)", ha="center", fontsize=10,
            fontweight="bold", color=C_GRAY, alpha=0.5)

    # Departments positioned by urgency & impact
    points = [
        ("Edgerton", 9, 8.5, 768),
        ("Watertown", 8, 7.5, 656),
        ("Whitewater", 7.5, 7, 421),
        ("Fort Atkinson", 4, 6, 209),
        ("Ixonia", 8, 5.5, 32),
        ("Waterloo", 6, 5, 93),
        ("Johnson Creek", 5, 4.5, 59),
        ("Cambridge", 7, 3, 4),
        ("Jefferson", 2, 3.5, 2),
        ("Palmyra", 3, 2, 0),
    ]

    for dept, x, y, events in points:
        size = max(80, events * 0.8)
        color = DEPT_COLORS.get(dept, C_GRAY)
        ax.scatter(x, y, s=size, color=color, alpha=0.7, edgecolors="white", linewidth=1.5, zorder=5)
        ax.annotate(f"{dept}\n({events} events)", (x, y),
                   textcoords="offset points", xytext=(12, 8),
                   fontsize=8, color="#1E293B", fontweight="bold",
                   arrowprops=dict(arrowstyle="-", color="#9CA3AF", lw=0.5))

    ax.text(5, -0.8, "Source: Phase A concurrent call analysis, CY2024  |  "
            "Bubble size = secondary ambulance events  |  "
            "Urgency = gap frequency + all-busy rate; Impact = population served + call volume",
            ha="center", fontsize=7, color=C_GRAY, style="italic",
            transform=ax.transData)

    ax.grid(alpha=0.15)

    fig.savefig(os.path.join(OUT, "10_priority_matrix.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print(" [10/12] Priority Matrix")


# ────────────────────────────────────────────────────────────────────
# 11. PDCA CYCLE DIAGRAM
# ────────────────────────────────────────────────────────────────────
def draw_pdca():
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.set_xlim(-6, 6); ax.set_ylim(-6, 6)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)

    ax.text(0, 5.5, "PDCA Cycle -Regional Secondary Ambulance Network",
            ha="center", fontsize=16, fontweight="bold", color="#1E293B")
    ax.text(0, 5.0, "Continuous improvement framework for implementation",
            ha="center", fontsize=10, color=C_GRAY, style="italic")

    quadrants = [
        ("PLAN", C_BLUE, 45, 135, [
            "Define secondary coverage zones",
            "Score facility locations (IE matrix)",
            "Model optimal EMT placement",
            "Set KPI targets (RT, utilization)",
        ]),
        ("DO", C_GREEN, -45, 45, [
            "Deploy county EMTs (Edgerton first)",
            "Implement dispatch routing rules",
            "Establish unified medical protocols",
            "Launch KPI dashboard monitoring",
        ]),
        ("CHECK", C_AMBER, 225, 315, [
            "Monitor response times weekly",
            "Track secondary demand reduction",
            "Compare actual vs target KPIs",
            "Collect crew & patient feedback",
        ]),
        ("ACT", C_RED, 135, 225, [
            "Adjust EMT placement by data",
            "Expand to next priority district",
            "Update facility scoring matrix",
            "Revise protocols & routing rules",
        ]),
    ]

    R = 3.2
    for name, color, a1, a2, items in quadrants:
        theta1, theta2 = min(a1, a2), max(a1, a2)
        wedge = mpatches.Wedge((0, 0), R, theta1, theta2,
                               facecolor=color, alpha=0.15, edgecolor=color, linewidth=2)
        ax.add_patch(wedge)

        mid_angle = (a1 + a2) / 2
        rad = math.radians(mid_angle)
        tx = R * 0.48 * math.cos(rad)
        ty = R * 0.48 * math.sin(rad)
        ax.text(tx, ty, name, ha="center", va="center",
                fontsize=20, fontweight="bold", color=color, alpha=0.8)

        # Items outside
        item_r = R + 1.0
        for j, item in enumerate(items):
            frac = (j + 0.5) / len(items)
            angle = a1 + (a2 - a1) * frac
            irad = math.radians(angle)
            ix = item_r * math.cos(irad)
            iy = item_r * math.sin(irad)

            # Extend further
            ex = (item_r + 1.2) * math.cos(irad)
            ey = (item_r + 1.2) * math.sin(irad)

            ax.plot([ix*0.85, ix], [iy*0.85, iy], color=color, lw=0.8, alpha=0.5)
            ha = "left" if ix > 0 else "right"
            ax.text(ex, ey, f"• {item}", ha=ha, va="center",
                    fontsize=8, color="#374151",
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                              edgecolor=color, alpha=0.7, linewidth=0.5))

    # Center circle
    center = plt.Circle((0, 0), 0.8, facecolor="white", edgecolor="#374151", linewidth=2)
    ax.add_patch(center)
    ax.text(0, 0.15, "PDCA", ha="center", va="center", fontsize=14, fontweight="bold", color="#1E293B")
    ax.text(0, -0.25, "Cycle", ha="center", va="center", fontsize=10, color=C_GRAY)

    # Rotation arrows (curved)
    for angle in [0, 90, 180, 270]:
        rad = math.radians(angle)
        ax.annotate("",
                    xy=(1.5*math.cos(math.radians(angle+35)), 1.5*math.sin(math.radians(angle+35))),
                    xytext=(1.5*math.cos(math.radians(angle-10)), 1.5*math.sin(math.radians(angle-10))),
                    arrowprops=dict(arrowstyle="-|>", color="#6B7280", lw=1.5,
                                   connectionstyle="arc3,rad=0.3"))

    ax.text(0, -5.7, "Source: ISyE 450 project methodology  |  Applied to Jefferson County EMS secondary ambulance network implementation",
            ha="center", fontsize=7, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "11_pdca_cycle.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print(" [11/12] PDCA Cycle")


# ────────────────────────────────────────────────────────────────────
# 12. GANTT CHART (Implementation Timeline)
# ────────────────────────────────────────────────────────────────────
def draw_gantt():
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor(C_BG)

    tasks = [
        ("Phase 1: Analysis & Planning", "2026-01", "2026-04", C_BLUE, "ISyE Team"),
        ("  Data collection & dashboard", "2026-01", "2026-03", C_BLUE, ""),
        ("  Root cause analysis", "2026-02", "2026-04", C_BLUE, ""),
        ("  Facility scoring & recommendation", "2026-03", "2026-04", C_BLUE, ""),
        ("Phase 2: Design", "2026-04", "2026-07", C_GREEN, "Working Group"),
        ("  Define secondary coverage zones", "2026-04", "2026-06", C_GREEN, ""),
        ("  Unified medical protocol design", "2026-05", "2026-07", C_GREEN, ""),
        ("  Dispatch routing rules", "2026-05", "2026-07", C_GREEN, ""),
        ("Phase 3: Pilot", "2026-07", "2026-12", C_AMBER, "Dept Chiefs"),
        ("  Deploy county EMTs (Edgerton)", "2026-07", "2026-09", C_AMBER, ""),
        ("  Monitor KPIs & adjust", "2026-08", "2026-12", C_AMBER, ""),
        ("  Expand to Whitewater/Ixonia", "2026-10", "2026-12", C_AMBER, ""),
        ("Phase 4: Scale", "2027-01", "2027-06", C_PURPLE, "County Board"),
        ("  Full network deployment", "2027-01", "2027-04", C_PURPLE, ""),
        ("  Annual review & PDCA cycle", "2027-04", "2027-06", C_PURPLE, ""),
    ]

    months = ["Jan'26","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec",
              "Jan'27","Feb","Mar","Apr","May","Jun"]
    month_nums = list(range(len(months)))

    def month_to_num(s):
        y, m = s.split("-")
        return (int(y) - 2026) * 12 + int(m) - 1

    n = len(tasks)
    for i, (name, start, end, color, owner) in enumerate(tasks):
        y = n - i - 1
        s = month_to_num(start)
        e = month_to_num(end)
        is_phase = not name.startswith("  ")
        alpha = 0.9 if is_phase else 0.6
        height = 0.7 if is_phase else 0.5
        yoff = (0.7 - height) / 2

        bar = FancyBboxPatch((s, y + yoff), e - s, height,
                             boxstyle="round,pad=0.08",
                             facecolor=color, edgecolor="white" if is_phase else "none",
                             linewidth=1.5 if is_phase else 0, alpha=alpha)
        ax.add_patch(bar)

        # Task name
        ax.text(s - 0.2, y + 0.35, name.strip(), ha="right", va="center",
                fontsize=8 if is_phase else 7,
                fontweight="bold" if is_phase else "normal",
                color="#1E293B" if is_phase else "#6B7280")

        if owner:
            ax.text(e + 0.2, y + 0.35, owner, ha="left", va="center",
                    fontsize=7, color=color, style="italic")

    # Today marker
    today_m = 3  # April 2026
    ax.axvline(today_m, color=C_RED, lw=1.5, ls="--", alpha=0.6, zorder=5)
    ax.text(today_m, n + 0.3, "Today\n(Apr '26)", ha="center", fontsize=8,
            color=C_RED, fontweight="bold")

    ax.set_xlim(-8, 18)
    ax.set_ylim(-0.5, n + 1)
    ax.set_xticks(month_nums)
    ax.set_xticklabels(months, fontsize=7.5, rotation=45, ha="right")
    ax.set_yticks([])
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)

    ax.set_title("Implementation Gantt Chart -Regional Secondary Ambulance Network",
                 fontsize=14, fontweight="bold", color="#1E293B", pad=15)

    fig.text(0.5, 0.01, "Source: ISyE 450 project charter & recommendation plan  |  Timeline illustrative, subject to Working Group approval",
             ha="center", fontsize=7, color=C_GRAY, style="italic")

    fig.savefig(os.path.join(OUT, "12_gantt_chart.png"), dpi=200, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none")
    plt.close(fig)
    print(" [12/12] Gantt Chart")


# ────────────────────────────────────────────────────────────────────
# COMPILE PDF
# ────────────────────────────────────────────────────────────────────
def compile_pdf():
    from fpdf import FPDF

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(107, 114, 128)
            self.cell(0, 8, "Jefferson County EMS - Industrial Engineering Visual Tools", align="C")
            self.ln(4)
            self.set_draw_color(209, 213, 219)
            self.line(10, 14, self.w - 10, 14)
            self.ln(6)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(156, 163, 175)
            self.cell(0, 10, f"ISyE 450 Senior Design  |  Page {self.page_no()}/{{nb}}  |  April 2026", align="C")

    pdf = PDF("L", "mm", "Letter")  # Landscape
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Title page
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 15, "Industrial Engineering Visual Tools", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(107, 114, 128)
    pdf.cell(0, 10, "Jefferson County EMS Operational Analysis", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, "ISyE 450 Senior Design  |  University of Wisconsin-Madison", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "April 2026", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(15)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(55, 65, 81)

    toc = [
        ("1", "Affinity Diagram", "Stakeholder issues grouped into themed clusters"),
        ("2", "Fishbone (Ishikawa) Diagram", "Root causes of persistent EMS coverage gaps"),
        ("3", "5-Why Analysis", "Causal chain for secondary ambulance gaps"),
        ("4", "Pareto Chart", "80/20 analysis of secondary ambulance demand"),
        ("5", "Value Stream Map", "End-to-end EMS call response process"),
        ("6", "Swimlane Diagram", "Dispatch & response flow across organizational lanes"),
        ("7", "RACI Matrix", "Responsibility assignment for implementation"),
        ("8", "Facility Location Matrix", "Weighted scoring for ambulance placement"),
        ("9", "Radar Chart", "Multi-dimensional department performance comparison"),
        ("10", "Priority Matrix", "Urgency vs. impact for secondary coverage needs"),
        ("11", "PDCA Cycle", "Continuous improvement framework"),
        ("12", "Gantt Chart", "Implementation timeline"),
    ]

    for num, title, desc in toc:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(10, 7, num + ".")
        pdf.cell(70, 7, title)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 7, f"-{desc}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(55, 65, 81)

    # Diagram pages
    diagrams = [
        ("01_affinity_diagram.png", "1. Affinity Diagram",
         "Stakeholder issues from interviews, budgets, and operational data grouped into five themed clusters: "
         "Staffing & Workforce, Financial Sustainability, Coverage & Response Time, Governance & Contracts, "
         "and Equipment & Assets. Each sticky note represents a specific finding from primary data sources."),
        ("02_fishbone_diagram.png", "2. Fishbone (Ishikawa) Diagram",
         "Root cause analysis of why EMS coverage gaps persist across Jefferson County. Six causal categories "
         "(Staffing, Funding, Geography, Governance, Equipment, Demand) branch into specific contributing factors "
         "identified through data analysis and chief interviews."),
        ("03_five_why.png", "3. 5-Why Analysis",
         "Traces the causal chain from the observable problem (long wait times when primary ambulance unavailable) "
         "through five levels to the root cause: no county-level governance structure to coordinate ambulance "
         "placement, staffing, or mutual aid dispatch."),
        ("04_pareto_chart.png", "4. Pareto Chart",
         "Shows that Edgerton (768), Watertown (656), and Whitewater (421) account for 82% of all secondary "
         "ambulance events county-wide. The 80/20 principle suggests focusing the regional secondary network "
         "on these three districts first for maximum impact."),
        ("05_value_stream_map.png", "5. Value Stream Map",
         "Maps the end-to-end EMS call response process from 911 call through billing, identifying waste at each "
         "step. Key findings: dispatch lacks real-time unit location data, secondary response adds 1-3 minutes, "
         "BLS/ALS mismatch creates re-dispatch waste, and only 27% of billed revenue is collected."),
        ("06_swimlane.png", "6. Swimlane Diagram",
         "Shows the EMS call flow across four organizational lanes (Dispatch, Primary Ambulance, Secondary/Mutual "
         "Aid, Hospital). Highlights that 30-38% of calls in top departments trigger the secondary path, adding "
         "complexity and response time delays."),
        ("07_raci_matrix.png", "7. RACI Matrix",
         "Defines clear responsibility assignments for the regional secondary ambulance network implementation "
         "across six stakeholder groups. The County Board authorizes and funds; the EMS Working Group leads "
         "coordination; Department Chiefs execute operationally."),
        ("08_facility_matrix.png", "8. Facility Location Matrix",
         "Weighted scoring model for secondary ambulance placement candidates. Five criteria weighted by "
         "importance (coverage gap severity 30%, secondary volume 25%, RT improvement 20%, infrastructure 15%, "
         "cost 10%). Edgerton and Ixonia score highest."),
        ("09_radar_chart.png", "9. Radar Chart",
         "Multi-dimensional comparison of seven departments across six performance metrics. Reveals that no single "
         "department excels on all dimensions -Fort Atkinson leads cost efficiency and revenue recovery, while "
         "Edgerton leads calls/FTE and utilization but has the highest secondary demand."),
        ("10_priority_matrix.png", "10. Priority Matrix",
         "Plots departments on urgency (coverage gap frequency) vs. impact (potential improvement from secondary "
         "coverage). Edgerton, Watertown, and Whitewater fall in the high-priority quadrant, confirming Pareto "
         "findings and supporting phased implementation starting with these districts."),
        ("11_pdca_cycle.png", "11. PDCA Cycle",
         "Continuous improvement framework for implementation. Plan: define zones and score locations. "
         "Do: deploy county EMTs starting with Edgerton. Check: monitor KPIs weekly. "
         "Act: adjust placement by data and expand to next district."),
        ("12_gantt_chart.png", "12. Implementation Gantt Chart",
         "Four-phase timeline from analysis (Jan-Apr 2026) through full deployment (Jun 2027). "
         "Current status: completing Phase 1 analysis. Phase 2 design begins upon Working Group approval. "
         "Pilot targets Edgerton as first deployment site (Jul 2026)."),
    ]

    for fname, title, description in diagrams:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 10, title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        img_path = os.path.join(OUT, fname)
        if os.path.exists(img_path):
            # Landscape Letter: 279.4 x 215.9 mm; usable ~259 x 150
            pdf.image(img_path, x=15, w=249)

        pdf.ln(3)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(75, 85, 99)
        pdf.multi_cell(0, 5, description)

    out_path = os.path.join(os.path.dirname(__file__), "IE_Visual_Tools_Jefferson_County_EMS.pdf")
    pdf.output(out_path)
    print(f"\n  PDF saved: {out_path}")
    return out_path


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating IE Visual Tools diagrams...\n")
    draw_affinity()
    draw_fishbone()
    draw_five_why()
    draw_pareto()
    draw_vsm()
    draw_swimlane()
    draw_raci()
    draw_facility_matrix()
    draw_radar()
    draw_priority_matrix()
    draw_pdca()
    draw_gantt()
    print("\nCompiling PDF...")
    compile_pdf()
    print("\nDone!")
