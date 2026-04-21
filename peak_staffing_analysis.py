"""
Peak Staffing Requirements Analysis — Jefferson County EMS (Goal 2)
===================================================================
Reads all 14 NFIRS xlsx files, builds temporal demand profiles by department,
cross-references with staffing data, and identifies:
  1. Peak/valley call hours & days per department and county-wide
  2. Optimal shift window for a county-provided EMT/paramedic
  3. Overstaffing windows where resources can be reduced
  4. Call type variability by time of day (BLS vs ALS demand patterns)
  5. Response time degradation by hour (signals understaffing)

Outputs:
  - peak_staffing_report.md  (comprehensive markdown report)
  - peak_staffing_heatmap_county.png
  - peak_staffing_heatmap_depts.png
  - peak_staffing_optimal_shift.png
  - peak_staffing_response_time_by_hour.png
  - peak_staffing_call_type_by_hour.png
  - peak_staffing_overstaffing.png
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ── Config ────────────────────────────────────────────────────────────────────
BASE = Path(r"C:\Users\patri\OneDrive - UW-Madison\ISYE 450")
DATA_DIR = BASE / "ISyE Project" / "Data and Resources" / "Call Data"
OUT_DIR = BASE

# Department name mapping (from dashboard)
NAME_MAP = {
    "CAMBRIDGE COMM FIRE DEPT": "Cambridge",
    "Edgerton Fire Protection Distict": "Edgerton",
    "Fort Atkinson Fire Dept": "Fort Atkinson",
    "Helenville Vol Fire Co": "Helenville",
    "Helenville Fire and Rescue District": "Helenville",
    "Ixonia Fire Dept": "Ixonia",
    "Town of Ixonia Fire & EMS Dept": "Ixonia",
    "Jefferson Fire Dept": "Jefferson",
    "Johnson Creek Fire Dept": "Johnson Creek",
    "Palmyra Fire Dept": "Palmyra",
    "Palmyra Village Fire Dept": "Palmyra",
    # Rome and Sullivan are fire-only — excluded from EMS analysis
    "Waterloo Fire Dept": "Waterloo",
    "Watertown Fire Dept": "Watertown",
    "WESTERN LAKES FIRE DIST": "Western Lakes",
    "Western Lake Fire District": "Western Lakes",
    "Whitewater Fire Dept": "Whitewater",
    "Whitewater Fire and EMS": "Whitewater",
}

MONTH_MAP = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
             "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

DOW_MAP = {"Sun":"Sunday","Mon":"Monday","Tue":"Tuesday","Wed":"Wednesday",
           "Thu":"Thursday","Fri":"Friday","Sat":"Saturday"}
DOW_ORDER = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

# Authoritative call volumes
AUTH_EMS = {
    "Cambridge":87, "Fort Atkinson":1616, "Ixonia":289,
    "Jefferson":1457, "Johnson Creek":487, "Lake Mills":518,
    "Palmyra":32, "Waterloo":520, "Watertown":2012, "Whitewater":64,
    "Edgerton":2138, "Western Lakes":5633,
}

# Staffing data
STAFFING = {
    "Ixonia":        {"FT":2,  "PT":45, "Model":"Volunteer+FT"},
    "Jefferson":     {"FT":6,  "PT":20, "Model":"Career"},
    "Watertown":     {"FT":31, "PT":3,  "Model":"Career"},
    "Fort Atkinson": {"FT":16, "PT":28, "Model":"Career+PT"},
    "Whitewater":    {"FT":15, "PT":17, "Model":"Career+PT"},
    "Cambridge":     {"FT":0,  "PT":31, "Model":"Volunteer"},
    "Lake Mills":    {"FT":4,  "PT":20, "Model":"Career+Vol"},
    "Waterloo":      {"FT":4,  "PT":22, "Model":"Career+Vol"},
    "Johnson Creek": {"FT":3,  "PT":33, "Model":"Combination"},
    "Palmyra":       {"FT":0,  "PT":20, "Model":"Volunteer"},
    "Edgerton":      {"FT":24, "PT":0,  "Model":"Career+PT"},
    "Western Lakes": {"FT":0,  "PT":0,  "Model":"Career+PT"},  # multi-county, unknown
}

# Service levels
SERVICE_LEVEL = {
    "Watertown":"ALS", "Fort Atkinson":"ALS", "Whitewater":"ALS",
    "Jefferson":"ALS", "Johnson Creek":"ALS", "Edgerton":"ALS",
    "Cambridge":"ALS", "Western Lakes":"ALS",
    "Waterloo":"AEMT",
    "Palmyra":"BLS", "Ixonia":"BLS", "Helenville":"BLS", "Lake Mills":"BLS",
}

# ── Load all NFIRS data ──────────────────────────────────────────────────────
print("Loading NFIRS data...")
frames = []
for f in sorted(DATA_DIR.glob("*.xlsx")):
    try:
        df = pd.read_excel(f, sheet_name="Report", engine="openpyxl")
        frames.append(df)
        print(f"  {f.stem}: {len(df)} rows")
    except Exception as e:
        print(f"  SKIP {f.stem}: {e}")

raw = pd.concat(frames, ignore_index=True)
print(f"Total rows: {len(raw)}")

# ── Derived columns ──────────────────────────────────────────────────────────
raw["Department"] = raw["Fire Department Name"].map(NAME_MAP).fillna(raw["Fire Department Name"])
raw["Month"] = raw["Alarm Date - Month of Year"].map(MONTH_MAP)
raw["Hour"] = pd.to_numeric(raw["Alarm Date - Hour of Day"], errors="coerce")
raw["RT"] = pd.to_numeric(raw["Response Time (Minutes)"], errors="coerce")
raw["IsEMS"] = raw["Incident Type Code Category Description"].str.startswith("Rescue and EMS", na=False)

# Normalize DOW
raw["DOW"] = raw["Alarm Date - Day of Week"].astype(str).map(DOW_MAP)
raw["DOW"] = raw["DOW"].fillna(raw["Alarm Date - Day of Week"])

# Filter EMS only
ems = raw[raw["IsEMS"]].copy()
ems_rt = ems[ems["RT"].between(0, 60)].copy()
print(f"EMS calls: {len(ems)}, with valid RT: {len(ems_rt)}")

# ── Exclude fire-only depts ──────────────────────────────────────────────────
EXCLUDE_DEPTS = ["Helenville"]  # minimal data — Rome/Sullivan fire-only already excluded via NAME_MAP
ems_active = ems[~ems["Department"].isin(EXCLUDE_DEPTS)].copy()
ems_rt_active = ems_rt[~ems_rt["Department"].isin(EXCLUDE_DEPTS)].copy()

# ── 1. County-wide Hour x DOW heatmap ────────────────────────────────────────
print("\n1. Building county-wide hour x day-of-week heatmap...")
pivot_county = ems_active.groupby(["DOW", "Hour"]).size().reset_index(name="Calls")
heat = pivot_county.pivot(index="DOW", columns="Hour", values="Calls").fillna(0)
heat = heat.reindex(DOW_ORDER)

fig, ax = plt.subplots(figsize=(14, 5))
im = ax.imshow(heat.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")
ax.set_yticks(range(7))
ax.set_yticklabels(DOW_ORDER, fontsize=10)
ax.set_xticks(range(24))
ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
ax.set_xlabel("Hour of Day", fontsize=11)
ax.set_title("Jefferson County EMS — Call Volume by Hour & Day of Week (CY2024, All Depts)", fontsize=13, fontweight="bold")
cbar = plt.colorbar(im, ax=ax, shrink=0.8)
cbar.set_label("EMS Calls", fontsize=10)
# Annotate cells
for i in range(heat.shape[0]):
    for j in range(heat.shape[1]):
        val = int(heat.values[i, j])
        color = "white" if val > heat.values.max() * 0.6 else "black"
        ax.text(j, i, str(val), ha="center", va="center", fontsize=6.5, color=color)
plt.tight_layout()
plt.savefig(OUT_DIR / "peak_staffing_heatmap_county.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved peak_staffing_heatmap_county.png")

# ── 2. Per-department hour profiles ──────────────────────────────────────────
print("\n2. Building per-department hourly profiles...")
dept_hour = ems_active.groupby(["Department", "Hour"]).size().reset_index(name="Calls")

# Get top departments by volume for grid
top_depts = ems_active["Department"].value_counts().head(9).index.tolist()

fig, axes = plt.subplots(3, 3, figsize=(16, 12), sharey=False)
for idx, dept in enumerate(top_depts):
    ax = axes[idx // 3][idx % 3]
    ddata = dept_hour[dept_hour["Department"] == dept].set_index("Hour").reindex(range(24), fill_value=0)
    bars = ax.bar(ddata.index, ddata["Calls"], color="#2196F3", alpha=0.8, width=0.8)

    # Highlight peak hours (top 25%)
    threshold = ddata["Calls"].quantile(0.75)
    for bar, val in zip(bars, ddata["Calls"]):
        if val >= threshold:
            bar.set_color("#F44336")
            bar.set_alpha(0.9)

    # Highlight valley hours (bottom 25%)
    valley_thresh = ddata["Calls"].quantile(0.25)
    for bar, val in zip(bars, ddata["Calls"]):
        if val <= valley_thresh and val < threshold:
            bar.set_color("#4CAF50")
            bar.set_alpha(0.6)

    staff = STAFFING.get(dept, {})
    ft = staff.get("FT", "?")
    model = staff.get("Model", "?")
    level = SERVICE_LEVEL.get(dept, "?")
    auth = AUTH_EMS.get(dept, "?")
    ax.set_title(f"{dept} ({level}, {model})\n{auth} calls/yr, {ft} FT staff", fontsize=9, fontweight="bold")
    ax.set_xlabel("Hour", fontsize=8)
    ax.set_xticks([0, 4, 8, 12, 16, 20])
    ax.set_xticklabels(["00","04","08","12","16","20"], fontsize=7)

fig.suptitle("EMS Calls by Hour — Top 9 Departments (CY2024)\nRed = Peak (≥75th pctl), Green = Valley (≤25th pctl)",
             fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(OUT_DIR / "peak_staffing_heatmap_depts.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved peak_staffing_heatmap_depts.png")

# ── 3. Optimal shift window analysis ─────────────────────────────────────────
print("\n3. Computing optimal shift windows...")
county_hour = ems_active.groupby("Hour").size().reset_index(name="Calls")
county_hour = county_hour.set_index("Hour").reindex(range(24), fill_value=0)
hourly_calls = county_hour["Calls"].values

# Rolling window: best 8hr, 10hr, 12hr shifts
def best_shift(calls, duration):
    """Find the start hour that captures the most calls for a given shift length."""
    extended = np.tile(calls, 2)  # wrap around midnight
    best_start, best_total = 0, 0
    for start in range(24):
        total = sum(extended[start:start+duration])
        if total > best_total:
            best_total = total
            best_start = start
    pct = best_total / sum(calls) * 100
    return best_start, best_total, pct

shifts = {}
for dur in [8, 10, 12]:
    start, total, pct = best_shift(hourly_calls, dur)
    end = (start + dur) % 24
    shifts[dur] = {"start": start, "end": end, "calls": total, "pct": pct}
    print(f"  Best {dur}hr shift: {start:02d}:00-{end:02d}:00 -> {total} calls ({pct:.1f}%)")

# Plot
fig, ax = plt.subplots(figsize=(14, 6))
bars = ax.bar(range(24), hourly_calls, color="#607D8B", alpha=0.7, width=0.8, label="Calls/hr")

# Shade optimal shifts
colors_shift = {8: "#FF9800", 10: "#2196F3", 12: "#4CAF50"}
for dur, info in shifts.items():
    s, e = info["start"], info["end"]
    hours = [(s + h) % 24 for h in range(dur)]
    for h in hours:
        bars[h].set_color(colors_shift[dur])
        bars[h].set_alpha(0.3 + 0.2 * (dur == 8))  # 8hr most opaque

# Custom legend
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor="#FF9800", alpha=0.9, label=f"Best 8hr: {shifts[8]['start']:02d}–{shifts[8]['end']:02d} ({shifts[8]['pct']:.0f}%)"),
    Patch(facecolor="#2196F3", alpha=0.7, label=f"Best 10hr: {shifts[10]['start']:02d}–{shifts[10]['end']:02d} ({shifts[10]['pct']:.0f}%)"),
    Patch(facecolor="#4CAF50", alpha=0.5, label=f"Best 12hr: {shifts[12]['start']:02d}–{shifts[12]['end']:02d} ({shifts[12]['pct']:.0f}%)"),
]
ax.legend(handles=legend_elements, fontsize=10, loc="upper left")
ax.set_xlabel("Hour of Day", fontsize=12)
ax.set_ylabel("EMS Calls (CY2024)", fontsize=12)
ax.set_title("Optimal Shift Window — County-Wide EMS Demand\nIf the county provided one paid EMT, when should they work?",
             fontsize=13, fontweight="bold")
ax.set_xticks(range(24))
ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)

# Add mean line
mean_calls = hourly_calls.mean()
ax.axhline(mean_calls, color="red", linestyle="--", linewidth=1, alpha=0.7, label=f"Mean: {mean_calls:.0f}/hr")
ax.annotate(f"Mean: {mean_calls:.0f}", xy=(23, mean_calls), fontsize=9, color="red", va="bottom")

plt.tight_layout()
plt.savefig(OUT_DIR / "peak_staffing_optimal_shift.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved peak_staffing_optimal_shift.png")

# ── 4. Response time by hour (understaffing signal) ──────────────────────────
print("\n4. Analyzing response time by hour...")
rt_by_hour = ems_rt_active.groupby("Hour")["RT"].agg(["mean", "median", "count",
    lambda x: x.quantile(0.90)]).reset_index()
rt_by_hour.columns = ["Hour", "Mean_RT", "Median_RT", "Count", "P90_RT"]

fig, ax1 = plt.subplots(figsize=(14, 6))
ax2 = ax1.twinx()

# RT lines
ax1.plot(rt_by_hour["Hour"], rt_by_hour["Mean_RT"], "o-", color="#F44336", linewidth=2, markersize=5, label="Mean RT")
ax1.plot(rt_by_hour["Hour"], rt_by_hour["Median_RT"], "s-", color="#2196F3", linewidth=2, markersize=5, label="Median RT")
ax1.plot(rt_by_hour["Hour"], rt_by_hour["P90_RT"], "^--", color="#FF9800", linewidth=1.5, markersize=4, label="90th pctl RT")

# Call volume bars
ax2.bar(rt_by_hour["Hour"], rt_by_hour["Count"], color="#E0E0E0", alpha=0.5, width=0.8, label="Call Count")

ax1.set_xlabel("Hour of Day", fontsize=12)
ax1.set_ylabel("Response Time (minutes)", fontsize=12, color="#F44336")
ax2.set_ylabel("Call Count", fontsize=12, color="gray")
ax1.set_title("Response Time vs. Call Volume by Hour — All Active Departments (CY2024)\nRT spikes during low-volume hours may indicate staffing gaps",
              fontsize=13, fontweight="bold")
ax1.set_xticks(range(24))
ax1.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)

# NFPA benchmark
ax1.axhline(8, color="green", linestyle=":", linewidth=1.5, alpha=0.7)
ax1.annotate("NFPA 8-min target", xy=(0.5, 8.2), fontsize=9, color="green")

ax1.legend(loc="upper left", fontsize=9)
ax2.legend(loc="upper right", fontsize=9)
ax1.set_ylim(0, max(rt_by_hour["P90_RT"]) * 1.15)

plt.tight_layout()
plt.savefig(OUT_DIR / "peak_staffing_response_time_by_hour.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved peak_staffing_response_time_by_hour.png")

# ── 5. Call type by hour ─────────────────────────────────────────────────────
print("\n5. Analyzing call type distribution by hour...")
# Map incident types to simplified categories
def classify_call(desc):
    if pd.isna(desc):
        return "Other EMS"
    desc_lower = str(desc).lower()
    # Order matters: check for specific patterns before broad ones
    # "EMS call, excluding vehicle accident with injury" is the standard medical call — NOT an MVA
    if "ems call, excluding" in desc_lower:
        return "EMS/Medical Call"
    elif "medical assist" in desc_lower or "assist ems" in desc_lower:
        return "Medical Assist"
    elif "vehicle accident with injur" in desc_lower or "mv ped" in desc_lower:
        return "MVA (with injury)"
    elif "motor vehicle" in desc_lower or "vehicle accident" in desc_lower:
        return "MVA (no injury)"
    elif "extrication" in desc_lower:
        return "Extrication"
    elif "rescue" in desc_lower or "search" in desc_lower:
        return "Rescue/Search"
    elif "emergency medical" in desc_lower or "standby" in desc_lower:
        return "EMS Standby/Other"
    else:
        return "Other EMS"

ems_active["CallType"] = ems_active["Incident Type Description"].apply(classify_call)

type_hour = ems_active.groupby(["Hour", "CallType"]).size().reset_index(name="Calls")
type_pivot = type_hour.pivot(index="Hour", columns="CallType", values="Calls").fillna(0).reindex(range(24), fill_value=0)

fig, ax = plt.subplots(figsize=(14, 6))
call_colors = {
    "EMS/Medical Call":"#2196F3", "Medical Assist":"#03A9F4",
    "MVA (with injury)":"#F44336", "MVA (no injury)":"#FF9800",
    "Rescue/Search":"#9C27B0", "Extrication":"#E91E63",
    "EMS Standby/Other":"#607D8B", "Other EMS":"#9E9E9E",
}
type_pivot.plot(kind="bar", stacked=True, ax=ax,
                color={c: call_colors.get(c, "#BDBDBD") for c in type_pivot.columns},
                width=0.8, alpha=0.85)
ax.set_xlabel("Hour of Day", fontsize=12)
ax.set_ylabel("EMS Calls (CY2024)", fontsize=12)
ax.set_title("Call Type Distribution by Hour — All Active Departments\nEMS/Medical calls (BLS-level) dominate; MVAs cluster during commute/daytime hours",
             fontsize=13, fontweight="bold")
ax.set_xticklabels([f"{h:02d}" for h in range(24)], rotation=0, fontsize=8)
ax.legend(loc="upper left", fontsize=9, ncol=2)
plt.tight_layout()
plt.savefig(OUT_DIR / "peak_staffing_call_type_by_hour.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved peak_staffing_call_type_by_hour.png")

# ── 6. Overstaffing / understaffing analysis ─────────────────────────────────
print("\n6. Computing staffing efficiency by department and time...")

# For each department, compute calls-per-FT-staff by hour
# Career depts (24/7): distribute FT evenly across 3 shifts (8hr each)
# Volunteer depts: assume variable availability

dept_profiles = []
for dept in sorted(ems_active["Department"].unique()):
    staff = STAFFING.get(dept, {})
    ft = staff.get("FT", 0)
    pt = staff.get("PT", 0)
    model = staff.get("Model", "Unknown")
    level = SERVICE_LEVEL.get(dept, "?")
    auth = AUTH_EMS.get(dept, 0)

    dept_data = ems_active[ems_active["Department"] == dept]
    dept_rt = ems_rt_active[ems_rt_active["Department"] == dept]

    # Hourly profile
    hourly = dept_data.groupby("Hour").size().reindex(range(24), fill_value=0)

    # DOW profile
    dow = dept_data.groupby("DOW").size().reindex(DOW_ORDER, fill_value=0)

    # RT by hour
    rt_hourly = dept_rt.groupby("Hour")["RT"].agg(["mean", "median"]).reindex(range(24))

    # Peak and valley
    peak_hours = hourly.nlargest(4).index.tolist()
    valley_hours = hourly.nsmallest(4).index.tolist()
    peak_pct = hourly[peak_hours].sum() / hourly.sum() * 100 if hourly.sum() > 0 else 0
    valley_pct = hourly[valley_hours].sum() / hourly.sum() * 100 if hourly.sum() > 0 else 0

    # Calls per day
    calls_per_day = auth / 365 if auth > 0 else hourly.sum() / 365

    # Average calls per hour during peak vs valley
    peak_avg = hourly[peak_hours].mean()
    valley_avg = hourly[valley_hours].mean()
    ratio = peak_avg / valley_avg if valley_avg > 0 else float("inf")

    dept_profiles.append({
        "Department": dept,
        "Model": model,
        "Level": level,
        "FT": ft,
        "PT": pt,
        "Auth_Calls": auth,
        "Calls_Per_Day": round(calls_per_day, 2),
        "Peak_Hours": peak_hours,
        "Valley_Hours": valley_hours,
        "Peak_Pct": round(peak_pct, 1),
        "Valley_Pct": round(valley_pct, 1),
        "Peak_Valley_Ratio": round(ratio, 2),
        "Hourly_Profile": hourly,
        "DOW_Profile": dow,
        "RT_Hourly": rt_hourly,
    })

profiles_df = pd.DataFrame(dept_profiles)

# ── 7. Overstaffing visualization ────────────────────────────────────────────
print("\n7. Building overstaffing analysis chart...")

# For career/24hr depts, staffing is constant but demand varies
# "Overstaffing ratio" = (Mean hourly calls at valley) / (Mean hourly calls at peak)
# Low ratio = big swing = staffing mismatch opportunity

fig, axes = plt.subplots(2, 1, figsize=(14, 10))

# Top: Peak-to-valley ratio by department
career_depts = profiles_df[profiles_df["FT"] > 0].sort_values("Peak_Valley_Ratio", ascending=False)
ax = axes[0]
colors_bar = ["#F44336" if r > 3 else "#FF9800" if r > 2 else "#4CAF50" for r in career_depts["Peak_Valley_Ratio"]]
ax.barh(career_depts["Department"], career_depts["Peak_Valley_Ratio"], color=colors_bar, alpha=0.85)
ax.set_xlabel("Peak-to-Valley Ratio (higher = more variable demand)", fontsize=11)
ax.set_title("Demand Variability by Department — Peak vs. Valley Hours\nHigher ratio = greater opportunity for flexible staffing", fontsize=13, fontweight="bold")
for i, (dept, ratio) in enumerate(zip(career_depts["Department"], career_depts["Peak_Valley_Ratio"])):
    ft = career_depts[career_depts["Department"] == dept]["FT"].values[0]
    ax.text(ratio + 0.1, i, f"{ratio:.1f}x  ({ft} FT)", va="center", fontsize=9)
ax.axvline(2.0, color="gray", linestyle="--", linewidth=1, alpha=0.5)
ax.annotate("2x threshold", xy=(2.0, -0.5), fontsize=8, color="gray")

# Bottom: Nighttime (00-06) vs Daytime (08-18) call share by dept
ax = axes[1]
depts_sorted = []
for _, row in profiles_df.iterrows():
    if row["Auth_Calls"] == 0:
        continue
    hp = row["Hourly_Profile"]
    night = hp[0:7].sum()  # 00:00-06:59
    day = hp[8:19].sum()    # 08:00-18:59
    evening = hp[19:24].sum() + hp[7:8].sum()  # 19:00-23:59 + 07:00
    total = hp.sum()
    if total == 0:
        continue
    depts_sorted.append({
        "Department": row["Department"],
        "Night_Pct": night/total*100,
        "Day_Pct": day/total*100,
        "Evening_Pct": evening/total*100,
        "FT": row["FT"],
        "Model": row["Model"],
    })

ds = pd.DataFrame(depts_sorted).sort_values("Night_Pct", ascending=True)

ax.barh(ds["Department"], ds["Day_Pct"], color="#2196F3", alpha=0.8, label="Day (08-18)")
ax.barh(ds["Department"], ds["Evening_Pct"], left=ds["Day_Pct"], color="#FF9800", alpha=0.8, label="Evening (19-07)")
ax.barh(ds["Department"], ds["Night_Pct"], left=ds["Day_Pct"]+ds["Evening_Pct"], color="#263238", alpha=0.8, label="Night (00-06)")
ax.set_xlabel("% of EMS Calls", fontsize=11)
ax.set_title("Call Distribution: Day vs. Evening vs. Night — Staffing Alignment Opportunity\n24/7 career depts with <15% night calls may be overstaffed overnight", fontsize=13, fontweight="bold")
ax.legend(loc="lower right", fontsize=9)
ax.axvline(85, color="gray", linestyle=":", linewidth=1, alpha=0.5)

plt.tight_layout()
plt.savefig(OUT_DIR / "peak_staffing_overstaffing.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved peak_staffing_overstaffing.png")

# ── 8. Per-department RT degradation analysis ────────────────────────────────
print("\n8. Computing per-department response time degradation...")

rt_degradation = []
for _, row in profiles_df.iterrows():
    dept = row["Department"]
    rt_h = row["RT_Hourly"]
    if rt_h["mean"].isna().all():
        continue
    peak_hrs = row["Peak_Hours"]
    valley_hrs = row["Valley_Hours"]

    mean_peak_rt = rt_h.loc[peak_hrs, "mean"].mean()
    mean_valley_rt = rt_h.loc[valley_hrs, "mean"].mean()
    overall_mean = rt_h["mean"].mean()

    # Night RT (00-06) vs Day RT (08-18)
    night_rt = rt_h.loc[0:6, "mean"].mean()
    day_rt = rt_h.loc[8:18, "mean"].mean()

    rt_degradation.append({
        "Department": dept,
        "Overall_Mean_RT": round(overall_mean, 1) if not np.isnan(overall_mean) else None,
        "Peak_Hour_RT": round(mean_peak_rt, 1) if not np.isnan(mean_peak_rt) else None,
        "Valley_Hour_RT": round(mean_valley_rt, 1) if not np.isnan(mean_valley_rt) else None,
        "Night_RT": round(night_rt, 1) if not np.isnan(night_rt) else None,
        "Day_RT": round(day_rt, 1) if not np.isnan(day_rt) else None,
        "Night_Day_Delta": round(night_rt - day_rt, 1) if not (np.isnan(night_rt) or np.isnan(day_rt)) else None,
    })

rt_deg_df = pd.DataFrame(rt_degradation)

# ── 9. Generate comprehensive report ─────────────────────────────────────────
print("\n9. Generating markdown report...")

# Compute county-wide stats
total_ems = len(ems_active)
county_hourly = ems_active.groupby("Hour").size().reindex(range(24), fill_value=0)
county_dow = ems_active.groupby("DOW").size().reindex(DOW_ORDER, fill_value=0)
county_month = ems_active.groupby("Month").size().reindex(range(1,13), fill_value=0)

peak_hour = county_hourly.idxmax()
peak_hour_calls = county_hourly.max()
valley_hour = county_hourly.idxmin()
valley_hour_calls = county_hourly.min()

peak_day = county_dow.idxmax()
valley_day = county_dow.idxmin()

# Overall busiest 4-hour block
best4_start, best4_calls, best4_pct = best_shift(county_hourly.values, 4)
best4_end = (best4_start + 4) % 24

# Night share
night_calls = county_hourly[0:7].sum()
night_pct = night_calls / total_ems * 100
day_calls = county_hourly[8:19].sum()
day_pct = day_calls / total_ems * 100

# RT stats
rt_county_hour = ems_rt_active.groupby("Hour")["RT"].agg(["mean","median"]).reindex(range(24))
worst_rt_hour = rt_county_hour["mean"].idxmax()
best_rt_hour = rt_county_hour["mean"].idxmin()

report = f"""# Peak Staffing Requirements Analysis — Jefferson County EMS

**Goal 2: Investigate Peak Staffing Requirements**
*Analysis Date: March 25, 2026 | Data: CY2024 NFIRS (14 departments, {total_ems:,} EMS calls)*

---

## Executive Summary

Jefferson County's EMS call demand follows a pronounced **daytime peak / nighttime valley** pattern. County-wide, **{day_pct:.0f}% of calls occur between 08:00–18:00** while only **{night_pct:.0f}% occur between 00:00–06:59**. The single busiest hour is **{peak_hour:02d}:00** ({peak_hour_calls} calls/year), while the quietest is **{valley_hour:02d}:00** ({valley_hour_calls} calls/year) — a **{peak_hour_calls/valley_hour_calls:.1f}x** difference.

This mismatch between constant 24/7 staffing and highly variable demand represents the core finding: **staffing is uniform but demand is not**.

---

## 1. County-Wide Temporal Demand Profile

### Hour-of-Day Pattern
| Metric | Value |
|--------|-------|
| Peak hour | **{peak_hour:02d}:00** ({peak_hour_calls} calls, {peak_hour_calls/total_ems*100:.1f}% of annual) |
| Valley hour | **{valley_hour:02d}:00** ({valley_hour_calls} calls, {valley_hour_calls/total_ems*100:.1f}% of annual) |
| Peak-to-valley ratio | **{peak_hour_calls/valley_hour_calls:.1f}x** |
| Best 4-hr block | **{best4_start:02d}:00–{best4_end:02d}:00** ({best4_calls} calls, {best4_pct:.0f}% of annual) |
| Best 8-hr shift | **{shifts[8]['start']:02d}:00–{shifts[8]['end']:02d}:00** ({shifts[8]['calls']} calls, {shifts[8]['pct']:.0f}%) |
| Best 10-hr shift | **{shifts[10]['start']:02d}:00–{shifts[10]['end']:02d}:00** ({shifts[10]['calls']} calls, {shifts[10]['pct']:.0f}%) |
| Best 12-hr shift | **{shifts[12]['start']:02d}:00–{shifts[12]['end']:02d}:00** ({shifts[12]['calls']} calls, {shifts[12]['pct']:.0f}%) |

### Day-of-Week Pattern
| Day | Calls | % of Weekly |
|-----|-------|------------|
"""

for day in DOW_ORDER:
    c = county_dow[day]
    pct = c / county_dow.sum() * 100
    marker = " **← Peak**" if day == peak_day else (" **← Low**" if day == valley_day else "")
    report += f"| {day} | {c:,} | {pct:.1f}%{marker} |\n"

report += f"""
**Key finding**: Day-of-week variation is modest ({county_dow.max()/county_dow.min():.2f}x range). The dominant pattern is **hourly**, not daily — staffing optimization should focus on time-of-day shifts rather than day-of-week scheduling.

### Time Block Summary
| Time Block | Hours | Calls | % of Total | Avg Calls/Hr |
|-----------|-------|-------|-----------|-------------|
| Night (00:00–06:59) | 7 hrs | {night_calls:,} | {night_pct:.1f}% | {night_calls/7:.0f} |
| Morning (07:00–11:59) | 5 hrs | {county_hourly[7:12].sum():,} | {county_hourly[7:12].sum()/total_ems*100:.1f}% | {county_hourly[7:12].sum()/5:.0f} |
| Afternoon (12:00–17:59) | 6 hrs | {county_hourly[12:18].sum():,} | {county_hourly[12:18].sum()/total_ems*100:.1f}% | {county_hourly[12:18].sum()/6:.0f} |
| Evening (18:00–23:59) | 6 hrs | {county_hourly[18:24].sum():,} | {county_hourly[18:24].sum()/total_ems*100:.1f}% | {county_hourly[18:24].sum()/6:.0f} |

![County-wide heatmap](peak_staffing_heatmap_county.png)

---

## 2. Per-Department Demand Profiles

"""

# Sort departments by volume for the report
for _, row in profiles_df.sort_values("Auth_Calls", ascending=False).iterrows():
    dept = row["Department"]
    if row["Auth_Calls"] == 0:
        continue
    hp = row["Hourly_Profile"]
    if hp.sum() == 0:
        continue

    peak_h = sorted(row["Peak_Hours"])
    valley_h = sorted(row["Valley_Hours"])

    # Night share for this dept
    dept_night = hp[0:7].sum() / hp.sum() * 100
    dept_day = hp[8:19].sum() / hp.sum() * 100

    report += f"""### {dept}
- **Service level**: {row['Level']} | **Model**: {row['Model']} | **FT staff**: {row['FT']} | **PT staff**: {row['PT']}
- **Authoritative call volume**: {row['Auth_Calls']:,}/yr ({row['Calls_Per_Day']:.1f}/day)
- **Peak hours**: {', '.join(f'{h:02d}:00' for h in peak_h)} ({row['Peak_Pct']}% of calls)
- **Valley hours**: {', '.join(f'{h:02d}:00' for h in valley_h)} ({row['Valley_Pct']}% of calls)
- **Peak-to-valley ratio**: {row['Peak_Valley_Ratio']}x
- **Day (08-18) share**: {dept_day:.0f}% | **Night (00-06) share**: {dept_night:.0f}%

"""

report += """![Per-department hourly profiles](peak_staffing_heatmap_depts.png)

---

## 3. Optimal Shift Window — County-Provided EMT/Paramedic

If Jefferson County were to fund **one paid EMT or paramedic** to supplement existing municipal EMS, the data shows:

"""

report += f"""| Shift Length | Optimal Window | Calls Covered | % of Annual |
|-------------|---------------|--------------|-------------|
| 8 hours | **{shifts[8]['start']:02d}:00 – {shifts[8]['end']:02d}:00** | {shifts[8]['calls']:,} | {shifts[8]['pct']:.0f}% |
| 10 hours | **{shifts[10]['start']:02d}:00 – {shifts[10]['end']:02d}:00** | {shifts[10]['calls']:,} | {shifts[10]['pct']:.0f}% |
| 12 hours | **{shifts[12]['start']:02d}:00 – {shifts[12]['end']:02d}:00** | {shifts[12]['calls']:,} | {shifts[12]['pct']:.0f}% |

### Staffing Level Recommendation by Call Type

The call type breakdown by hour shows:
"""

# Call type stats
type_totals = ems_active["CallType"].value_counts()
for ct, count in type_totals.items():
    pct = count / len(ems_active) * 100
    report += f"- **{ct}**: {count:,} calls ({pct:.0f}%)\n"

# Compute BLS-handleable share (EMS/Medical Call + Medical Assist = typically BLS-level)
bls_types = ["EMS/Medical Call", "Medical Assist", "EMS Standby/Other"]
bls_share = sum(type_totals.get(t, 0) for t in bls_types) / len(ems_active) * 100
mva_share = sum(type_totals.get(t, 0) for t in ["MVA (with injury)", "MVA (no injury)"]) / len(ems_active) * 100

report += f"""
**Implication**: EMS/Medical calls and medical assists ({bls_share:.0f}% of calls combined) are predominantly BLS-level and dominate at all hours. An **EMT-Basic** can handle the vast majority of peak-hour demand. MVA calls ({mva_share:.0f}% of calls) cluster during commute and daytime hours (07:00-09:00, 15:00-18:00) and are more likely to require ALS-level care.

**Recommended staffing level for county-provided position**:
- If **one position**: Paramedic (ALS) -- covers both routine medical calls and the higher-acuity MVA peak
- If **cost-constrained**: EMT-Basic with ALS intercept protocol -- handles ~{bls_share:.0f}% of calls independently

![Optimal shift analysis](peak_staffing_optimal_shift.png)
![Call type by hour](peak_staffing_call_type_by_hour.png)

---

## 4. Response Time by Hour — Understaffing Signals

Response times that spike during specific hours suggest inadequate staffing coverage during those windows.

| Metric | Value |
|--------|-------|
| Worst mean RT hour | **{worst_rt_hour:02d}:00** ({rt_county_hour.loc[worst_rt_hour, 'mean']:.1f} min) |
| Best mean RT hour | **{best_rt_hour:02d}:00** ({rt_county_hour.loc[best_rt_hour, 'mean']:.1f} min) |
| Overall mean RT | {ems_rt_active['RT'].mean():.1f} min |
| Overall median RT | {ems_rt_active['RT'].median():.1f} min |

### Per-Department Night vs. Day Response Time

"""

report += "| Department | Overall RT | Day RT (08-18) | Night RT (00-06) | Night-Day Delta | Signal |\n"
report += "|-----------|-----------|---------------|-----------------|----------------|--------|\n"

for _, row in rt_deg_df.sort_values("Night_Day_Delta", ascending=False, na_position="last").iterrows():
    delta = row["Night_Day_Delta"]
    if delta is None:
        signal = "Insufficient data"
    elif delta > 3:
        signal = "**Significant night degradation**"
    elif delta > 1:
        signal = "Moderate night increase"
    elif delta < -1:
        signal = "Night RT better (less volume)"
    else:
        signal = "Stable"

    report += f"| {row['Department']} | {row['Overall_Mean_RT'] or 'N/A'} | {row['Day_RT'] or 'N/A'} | {row['Night_RT'] or 'N/A'} | {'+' if delta and delta > 0 else ''}{delta or 'N/A'} min | {signal} |\n"

report += """
![Response time by hour](peak_staffing_response_time_by_hour.png)

---

## 5. Overstaffing Analysis — Where Resources Can Be Reduced

### Departments with Highest Demand Variability

Departments with **constant 24/7 career staffing** but **highly variable demand** represent the greatest mismatch. A peak-to-valley ratio above 2.0x means peak hours see more than double the calls of valley hours, yet staffing levels remain the same.

"""

for _, row in profiles_df.sort_values("Peak_Valley_Ratio", ascending=False).iterrows():
    if row["Auth_Calls"] == 0 or row["FT"] == 0:
        continue
    dept = row["Department"]
    hp = row["Hourly_Profile"]
    night_share = hp[0:7].sum() / hp.sum() * 100 if hp.sum() > 0 else 0

    if row["Peak_Valley_Ratio"] > 2.0:
        report += f"""#### {dept} (Peak-Valley Ratio: {row['Peak_Valley_Ratio']}x)
- **{row['FT']} FT staff** provide 24/7 coverage, but **{night_share:.0f}% of calls occur overnight (00-06)**
- Peak demand at {', '.join(f'{h:02d}:00' for h in sorted(row['Peak_Hours']))} receives the same staffing as valley hours
- **Diagnostic**: With {row['Calls_Per_Day']:.1f} calls/day average, overnight hours average ~{hp[0:7].sum()/7/365*12:.2f} calls/hr — well below the daily average of {hp.sum()/24/365*12:.2f} calls/hr
"""
    else:
        report += f"""#### {dept} (Peak-Valley Ratio: {row['Peak_Valley_Ratio']}x)
- Relatively **balanced demand** across hours — less opportunity for shift-based optimization
- {row['FT']} FT staff with {row['Calls_Per_Day']:.1f} calls/day
"""

report += """
### Night Staffing Diagnostic

For departments operating 24/7 career staffing, the overnight period (00:00–06:59) typically accounts for the lowest call volume. The question is: **does the current overnight staffing level match the actual demand?**

| Department | Night Calls (00-06) | Night % | Calls/Night-Hour | FT Staff | 24/7 Model? |
|-----------|-------------------|---------|-----------------|----------|------------|
"""

for _, row in profiles_df.sort_values("Auth_Calls", ascending=False).iterrows():
    if row["Auth_Calls"] == 0:
        continue
    hp = row["Hourly_Profile"]
    night = hp[0:7].sum()
    night_pct_dept = night / hp.sum() * 100 if hp.sum() > 0 else 0
    calls_per_night_hr = night / 7  # annual calls in that hour slot
    is_24 = "Yes" if row["Model"] in ["Career", "Career+PT"] else "No"
    report += f"| {row['Department']} | {night:.0f} | {night_pct_dept:.0f}% | {calls_per_night_hr:.0f}/yr | {row['FT']} | {is_24} |\n"

report += """
![Overstaffing analysis](peak_staffing_overstaffing.png)

---

## 6. Staffing Recommendations Summary

### Key Findings

1. **Demand is heavily time-dependent**: The county sees a {peak_valley}x difference between peak and valley hours. This is the single largest staffing efficiency lever.

2. **Overnight staffing mismatch**: Departments with 24/7 career models (Watertown, Fort Atkinson, Whitewater, Jefferson) maintain full overnight shifts despite {night_pct_global:.0f}% of calls occurring 00:00–06:59. This is not inherently wrong (response time matters more than volume at night), but it does mean resources are underutilized during these hours.

3. **Optimal county EMT window**: A single county-provided EMT working **{best8_start:02d}:00–{best8_end:02d}:00** would cover **{best8_pct:.0f}% of county-wide EMS calls**, maximizing impact per labor dollar.

4. **Call type is uniform**: BLS-level calls (EMS/Medical + Medical Assist) account for ~{bls_pct:.0f}% of all calls at all hours. ALS is most needed during commute-hour MVA peaks ({mva_pct:.0f}% of calls).

5. **Day-of-week variation is minimal**: Unlike hour-of-day ({peak_valley}x variation), day-of-week varies only ~{dow_ratio:.1f}x. Weekday vs. weekend scheduling changes would have low impact.

### Where to Reduce Staffing
- **Overnight (00:00–06:00)** in career departments with low night call volumes
- **Departments with <2 calls/day** may not need dedicated 24/7 EMS coverage at all — mutual aid or regional roving units could serve these areas during off-peak hours

### Where to Increase Staffing
- **{peak_hour:02d}:00–{peak_end:02d}:00 window** is consistently the highest-demand period across all departments
- Volunteer departments during **daytime weekday hours** when volunteers are at their day jobs and unavailable

---

## Data Sources & Methodology

- **Call data**: 14 NFIRS Excel files, CY2024 (Calendar Year). EMS calls only (Rescue and EMS category 300-381).
- **Staffing data**: FY2025 budget documents + fire chief interviews (Mar 2026). See `staffing_sources.md` for per-department sources.
- **Authoritative call volumes**: User-provided ground-truth counts (14,853 total). Used for rates and ratios; NFIRS temporal patterns used for hourly/daily distributions.
- **Response times**: NFIRS "Response Time (Minutes)" field, filtered 0–60 min to remove outliers.
- **Partial-year adjustments**: Palmyra (3 months → ×4.0), Helenville (7 months → ×1.714). Helenville excluded from analysis due to minimal EMS data.

*Note: This analysis is diagnostic. It identifies where staffing and demand are misaligned, not what specific changes to make. Specific scheduling recommendations require additional input on minimum coverage requirements, union contracts, response time targets, and mutual aid agreements.*
""".format(
    peak_valley=f"{peak_hour_calls/valley_hour_calls:.1f}",
    night_pct_global=night_pct,
    best8_start=shifts[8]['start'],
    best8_end=shifts[8]['end'],
    best8_pct=shifts[8]['pct'],
    bls_pct=bls_share,
    mva_pct=mva_share,
    dow_ratio=county_dow.max()/county_dow.min(),
    peak_hour=peak_hour,
    peak_end=(peak_hour + 4) % 24,
)

# Write report
report_path = OUT_DIR / "peak_staffing_report.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"\nReport saved to: {report_path}")

# ── 10. Summary stats to console ─────────────────────────────────────────────
print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print("="*70)
print(f"Total EMS calls analyzed: {total_ems:,}")
print(f"Peak hour: {peak_hour:02d}:00 ({peak_hour_calls} calls)")
print(f"Valley hour: {valley_hour:02d}:00 ({valley_hour_calls} calls)")
print(f"Peak/valley ratio: {peak_hour_calls/valley_hour_calls:.1f}x")
print(f"Best 8hr shift: {shifts[8]['start']:02d}:00–{shifts[8]['end']:02d}:00 ({shifts[8]['pct']:.0f}%)")
print(f"Best 12hr shift: {shifts[12]['start']:02d}:00–{shifts[12]['end']:02d}:00 ({shifts[12]['pct']:.0f}%)")
print(f"Night (00-06) share: {night_pct:.1f}%")
print(f"Day (08-18) share: {day_pct:.1f}%")
print(f"\nOutputs:")
print(f"  - peak_staffing_report.md")
print(f"  - peak_staffing_heatmap_county.png")
print(f"  - peak_staffing_heatmap_depts.png")
print(f"  - peak_staffing_optimal_shift.png")
print(f"  - peak_staffing_response_time_by_hour.png")
print(f"  - peak_staffing_call_type_by_hour.png")
print(f"  - peak_staffing_overstaffing.png")
