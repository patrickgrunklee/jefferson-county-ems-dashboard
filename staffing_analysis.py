"""
Jefferson County EMS — Labor Operations & Staffing Analysis
Uses provider-level call data from 6 municipalities (CY2024)
"""
import pandas as pd
import numpy as np

DATA_DIR = "Data from Providers/Data from Providers"

##############################################################################
# 1. PARSE ALL PROVIDER DATA
##############################################################################
dfs = {}

# --- EDGERTON ---
df = pd.read_csv(f"{DATA_DIR}/Edgerton EMS_Incidents.csv")
df["datetime"] = pd.to_datetime(df["Incident Date Time"], format="mixed", dayfirst=False)
df["dept"] = "Edgerton"
dfs["Edgerton"] = df[["datetime", "dept"]].dropna()

# --- JEFFERSON ---
df = pd.read_excel(f"{DATA_DIR}/Jefferson Fire Dept 2024 EMS Call Data.xlsx", header=None)
df = df.iloc[1:].reset_index(drop=True)
df.columns = [
    "Date", "Dispatch_Time", "Enroute_Time", "Page_to_Enroute",
    "Arrived_Time", "Page_to_Arrived", "Month_Num", "Month",
    "Year", "City", "Township", "Message",
]
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

def combine_dt_jeff(row):
    try:
        d = row["Date"]
        t = row["Dispatch_Time"]
        if pd.isna(d) or pd.isna(t):
            return pd.NaT
        if isinstance(t, str):
            parts = t.split(":")
            return d.replace(hour=int(parts[0]), minute=int(parts[1]))
        elif hasattr(t, "hour"):
            return d.replace(hour=t.hour, minute=t.minute)
        return pd.NaT
    except Exception:
        return pd.NaT

df["datetime"] = df.apply(combine_dt_jeff, axis=1)
df["dept"] = "Jefferson"
dfs["Jefferson"] = df[["datetime", "dept"]].dropna()

# --- JOHNSON CREEK ---
df = pd.read_csv(f"{DATA_DIR}/Johnson Creek EMS Data 2024.csv")
df["datetime"] = pd.to_datetime(df["Incident Alarm Date"], format="mixed", dayfirst=False)
df["dept"] = "Johnson Creek"
dfs["Johnson Creek"] = df[["datetime", "dept"]].dropna()

# --- LAKE MILLS ---
df = pd.read_csv(f"{DATA_DIR}/Lake Mills Ryan Bros EMS Data 2024.csv")
df["datetime"] = pd.to_datetime(
    df["Incident Unit Notified By Dispatch Date Time (eTimes.03)"],
    format="mixed", dayfirst=False,
)
df["dept"] = "Lake Mills"
dfs["Lake Mills"] = df[["datetime", "dept"]].dropna()

# --- WATERLOO ---
df = pd.read_excel(f"{DATA_DIR}/Waterloo Call Data.xlsx")
df["Date"] = pd.to_datetime(df["Incident Date"], errors="coerce")

def combine_dt_waterloo(row):
    try:
        d = row["Date"]
        t = row["Time"]
        if pd.isna(d) or pd.isna(t):
            return pd.NaT
        if isinstance(t, str):
            parts = t.split(":")
            return d.replace(hour=int(parts[0]), minute=int(parts[1]))
        elif hasattr(t, "hour"):
            return d.replace(hour=t.hour, minute=t.minute)
        return pd.NaT
    except Exception:
        return pd.NaT

df["datetime"] = df.apply(combine_dt_waterloo, axis=1)
df["dept"] = "Waterloo"
dfs["Waterloo"] = df[["datetime", "dept"]].dropna()

# --- WHITEWATER ---
df = pd.read_excel(
    f"{DATA_DIR}/Whitewater Fire Dept Call Data for Koshkonong and Cold Springs ONLY.xlsx"
)
df["datetime"] = pd.to_datetime(df["Incident Date"], errors="coerce")
df["dept"] = "Whitewater"
dfs["Whitewater"] = df[["datetime", "dept"]].dropna()

##############################################################################
# 2. COMBINE & COMPUTE TEMPORAL FEATURES
##############################################################################
all_calls = pd.concat(dfs.values(), ignore_index=True)
all_calls["hour"] = all_calls["datetime"].dt.hour
all_calls["day_of_week"] = all_calls["datetime"].dt.day_name()
all_calls["month"] = all_calls["datetime"].dt.month

print(f"Total calls parsed: {len(all_calls)}")
print(f"\nCalls per department:")
for dept, count in all_calls.groupby("dept").size().sort_values(ascending=False).items():
    print(f"  {dept}: {count}")

##############################################################################
# 3. KNOWN STAFFING DATA (from dashboard / budget)
##############################################################################
staffing = {
    "Edgerton":      {"FT": 24, "PT": 0,  "Model": "Career+PT",    "Ambulances": 2, "Auth_Calls": 2138},
    "Jefferson":     {"FT": 6,  "PT": 20, "Model": "Career",        "Ambulances": 5, "Auth_Calls": 1457},
    "Johnson Creek": {"FT": 3,  "PT": 33, "Model": "Combination",   "Ambulances": 2, "Auth_Calls": 487},
    "Lake Mills":    {"FT": 4,  "PT": 20, "Model": "Career+Vol",    "Ambulances": 3, "Auth_Calls": 518},
    "Waterloo":      {"FT": 4,  "PT": 22, "Model": "Career+Vol",    "Ambulances": 2, "Auth_Calls": 520},
    "Whitewater":    {"FT": 15, "PT": 17, "Model": "Career+PT",     "Ambulances": 4, "Auth_Calls": 64},
}

print("\n" + "=" * 80)
print("STAFFING OVERVIEW vs CALL VOLUME")
print("=" * 80)
print(f"{'Dept':<16} {'FT':>3} {'PT':>3} {'Total':>5} {'Model':<14} {'Calls':>6} {'Calls/FT':>9} {'Calls/Staff':>11} {'Amb':>3} {'Calls/Amb':>9}")
print("-" * 95)
for dept in sorted(staffing.keys()):
    s = staffing[dept]
    total = s["FT"] + s["PT"]
    calls = s["Auth_Calls"]
    cft = f"{calls/s['FT']:.0f}" if s["FT"] > 0 else "N/A"
    cstaff = f"{calls/total:.0f}" if total > 0 else "N/A"
    camb = f"{calls/s['Ambulances']:.0f}" if s["Ambulances"] > 0 else "N/A"
    print(f"{dept:<16} {s['FT']:>3} {s['PT']:>3} {total:>5} {s['Model']:<14} {calls:>6} {cft:>9} {cstaff:>11} {s['Ambulances']:>3} {camb:>9}")

##############################################################################
# 4. HOURLY DISTRIBUTION — OVERALL
##############################################################################
print("\n" + "=" * 80)
print("HOURLY CALL DISTRIBUTION — ALL DEPARTMENTS COMBINED")
print("=" * 80)

hourly_all = all_calls.groupby("hour").size()
hourly_pct = (hourly_all / hourly_all.sum() * 100).round(1)

for h in range(24):
    pct = hourly_pct.get(h, 0)
    bar = "#" * int(pct * 2)
    print(f"  {h:02d}:00  {pct:5.1f}%  {bar}")

peak_threshold = hourly_pct.mean() + hourly_pct.std()
low_threshold = hourly_pct.mean() - hourly_pct.std()
peak_hours = sorted(hourly_pct[hourly_pct >= peak_threshold].index.tolist())
off_peak = sorted(hourly_pct[hourly_pct <= low_threshold].index.tolist())
print(f"\nPEAK hours (>{peak_threshold:.1f}%): {[f'{h:02d}:00' for h in peak_hours]}")
print(f"OFF-PEAK hours (<{low_threshold:.1f}%): {[f'{h:02d}:00' for h in off_peak]}")

day_calls = all_calls[(all_calls["hour"] >= 6) & (all_calls["hour"] < 18)]
night_calls = all_calls[(all_calls["hour"] < 6) | (all_calls["hour"] >= 18)]
print(f"\nDay (06:00-17:59): {len(day_calls)} calls ({len(day_calls)/len(all_calls)*100:.1f}%)")
print(f"Night (18:00-05:59): {len(night_calls)} calls ({len(night_calls)/len(all_calls)*100:.1f}%)")

##############################################################################
# 5. HOURLY DISTRIBUTION — PER DEPARTMENT
##############################################################################
print("\n" + "=" * 80)
print("HOURLY PATTERNS — PER DEPARTMENT")
print("=" * 80)

for dept in sorted(all_calls["dept"].unique()):
    dept_data = all_calls[all_calls["dept"] == dept]
    dept_hourly = dept_data.groupby("hour").size()
    dept_pct = (dept_hourly / dept_hourly.sum() * 100).round(1)
    day_n = len(dept_data[(dept_data["hour"] >= 6) & (dept_data["hour"] < 18)])
    night_n = len(dept_data) - day_n
    peak_hrs = dept_pct.nlargest(3)
    low_hrs = dept_pct.nsmallest(3)
    print(f"\n  {dept} ({len(dept_data)} calls | FT={staffing.get(dept,{}).get('FT','?')}, PT={staffing.get(dept,{}).get('PT','?')}):")
    print(f"    Day/Night: {day_n} ({day_n/len(dept_data)*100:.0f}%) / {night_n} ({night_n/len(dept_data)*100:.0f}%)")
    print(f"    Peak hours:  {', '.join([f'{h:02d}:00 ({v:.1f}%)' for h, v in peak_hrs.items()])}")
    print(f"    Quiet hours: {', '.join([f'{h:02d}:00 ({v:.1f}%)' for h, v in low_hrs.items()])}")

    # Hourly histogram
    for h in range(24):
        pct = dept_pct.get(h, 0)
        bar = "#" * int(pct * 2)
        print(f"      {h:02d}:00  {pct:5.1f}%  {bar}")

##############################################################################
# 6. DAY OF WEEK DISTRIBUTION
##############################################################################
print("\n" + "=" * 80)
print("DAY OF WEEK DISTRIBUTION — ALL DEPARTMENTS")
print("=" * 80)

dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
dow_all = all_calls.groupby("day_of_week").size().reindex(dow_order)
dow_pct = (dow_all / dow_all.sum() * 100).round(1)
for day in dow_order:
    bar = "#" * int(dow_pct[day] * 3)
    print(f"  {day:10s}  {dow_pct[day]:5.1f}%  {bar}")

##############################################################################
# 7. DAILY CALL VOLUME STATISTICS (concurrent call risk)
##############################################################################
print("\n" + "=" * 80)
print("DAILY CALL VOLUME STATISTICS")
print("=" * 80)

for dept in sorted(all_calls["dept"].unique()):
    dept_data = all_calls[all_calls["dept"] == dept]
    daily = dept_data.groupby(dept_data["datetime"].dt.date).size()
    zero_days = 366 - len(daily)
    print(f"\n  {dept} (auth calls: {staffing.get(dept,{}).get('Auth_Calls','?')}, data rows: {len(dept_data)}):")
    print(f"    Mean:   {daily.mean():.1f} calls/day")
    print(f"    Median: {daily.median():.1f}")
    print(f"    Max:    {daily.max()} calls (on {daily.idxmax()})")
    print(f"    P90:    {daily.quantile(0.90):.0f} | P95: {daily.quantile(0.95):.0f} | P99: {daily.quantile(0.99):.0f}")
    print(f"    Zero-call days: {zero_days} of 366 ({zero_days/366*100:.0f}%)")
    print(f"    Days with 3+ calls: {(daily >= 3).sum()} ({(daily >= 3).sum()/len(daily)*100:.0f}%)")
    print(f"    Days with 5+ calls: {(daily >= 5).sum()} ({(daily >= 5).sum()/len(daily)*100:.0f}%)")

##############################################################################
# 8. PEAK HOUR STAFFING GAP ANALYSIS
##############################################################################
print("\n" + "=" * 80)
print("STAFFING GAP ANALYSIS — PEAK DEMAND vs CURRENT STAFF")
print("=" * 80)

# Estimate: avg call duration ~45 min for transport, ~30 min for non-transport
# Use 45 min average (conservative)
AVG_CALL_DURATION_HRS = 0.75  # 45 minutes

for dept in sorted(staffing.keys()):
    s = staffing[dept]
    dept_data = all_calls[all_calls["dept"] == dept]
    if len(dept_data) == 0:
        continue

    calls = s["Auth_Calls"]
    # Calls per hour at peak
    dept_hourly = dept_data.groupby("hour").size()
    dept_pct = dept_hourly / dept_hourly.sum()

    # Scale to authoritative call count
    calls_per_hour = dept_pct * calls / 365
    peak_hour = calls_per_hour.idxmax()
    peak_rate = calls_per_hour.max()

    # Concurrent units needed at peak = peak_rate * avg_duration
    peak_concurrent = peak_rate * AVG_CALL_DURATION_HRS
    # P95 day: on a busy day (P95 daily volume), peak hour concurrent
    daily = dept_data.groupby(dept_data["datetime"].dt.date).size()
    p95_daily = daily.quantile(0.95)
    p95_peak_concurrent = (p95_daily / 12) * AVG_CALL_DURATION_HRS  # peak 12 daytime hours

    # Available crews (2 per ambulance)
    amb = s["Ambulances"]
    # FT staff = available during day shifts; PT/Vol = supplement
    ft = s["FT"]
    pt = s["PT"]

    # Minimum crew = 2 per ambulance; FT staff / 3 shifts = FT on duty at any time
    ft_on_duty = ft / 3 if ft > 0 else 0
    crews_on_duty = ft_on_duty / 2  # 2-person crews

    print(f"\n  {dept}:")
    print(f"    Calls/day avg: {calls/365:.1f} | Peak hour ({peak_hour:02d}:00): {peak_rate:.2f} calls/hr")
    print(f"    Est. concurrent units at peak hour (avg day): {peak_concurrent:.2f}")
    print(f"    Est. concurrent units at peak hour (P95 day): {p95_peak_concurrent:.2f}")
    print(f"    Ambulances available: {amb}")
    print(f"    FT on duty (est, /3 shifts): {ft_on_duty:.1f} staff -> {crews_on_duty:.1f} crews")
    if peak_concurrent > amb:
        print(f"    >>> UNDERSTAFFED: peak demand ({peak_concurrent:.1f}) exceeds ambulance capacity ({amb})")
    elif peak_concurrent < amb * 0.3:
        print(f"    >>> OVERSTAFFED: peak demand ({peak_concurrent:.2f}) uses <30% of ambulance capacity ({amb})")
    else:
        print(f"    >>> ADEQUATE: peak demand within ambulance capacity")

    if crews_on_duty < 1 and calls / 365 > 0.5:
        print(f"    >>> CREW GAP: <1 FT crew on duty but averaging {calls/365:.1f} calls/day — relies heavily on PT/volunteers")

##############################################################################
# 9. SHIFT-BASED ANALYSIS (8hr shifts: 06-14, 14-22, 22-06)
##############################################################################
print("\n" + "=" * 80)
print("SHIFT-BASED CALL DISTRIBUTION (8-hr shifts)")
print("=" * 80)

def get_shift(hour):
    if 6 <= hour < 14:
        return "Day (06-14)"
    elif 14 <= hour < 22:
        return "Afternoon (14-22)"
    else:
        return "Night (22-06)"

all_calls["shift"] = all_calls["hour"].apply(get_shift)
shift_order = ["Day (06-14)", "Afternoon (14-22)", "Night (22-06)"]

for dept in sorted(all_calls["dept"].unique()):
    dept_data = all_calls[all_calls["dept"] == dept]
    shift_counts = dept_data.groupby("shift").size().reindex(shift_order, fill_value=0)
    shift_pct = (shift_counts / shift_counts.sum() * 100).round(1)
    auth = staffing.get(dept, {}).get("Auth_Calls", len(dept_data))
    print(f"\n  {dept} ({auth} auth calls):")
    for shift in shift_order:
        scaled = auth * shift_pct[shift] / 100
        print(f"    {shift:20s}: {shift_pct[shift]:5.1f}% (~{scaled:.0f} calls/yr, ~{scaled/365:.1f}/day)")

##############################################################################
# 10. JOHNSON CREEK: EMS vs NON-EMS FILTERING
##############################################################################
print("\n" + "=" * 80)
print("JOHNSON CREEK — CALL TYPE BREAKDOWN (includes non-EMS)")
print("=" * 80)
jc = pd.read_csv(f"{DATA_DIR}/Johnson Creek EMS Data 2024.csv")
if "Incident Type" in jc.columns:
    type_counts = jc["Incident Type"].value_counts()
    print(type_counts.to_string())
    ems_types = type_counts[type_counts.index.str.contains("EMS|Medical|Cardiac|Breathing|Stroke|Overdose|Sick|Fall|Trauma|chest|abdom", case=False, na=False)]
    print(f"\nLikely EMS calls: {ems_types.sum()} of {len(jc)} total ({ems_types.sum()/len(jc)*100:.0f}%)")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
