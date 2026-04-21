"""
Jefferson County EMS — Dash Interactive Dashboard
Run:  python ems_dashboard_app.py
Then open http://127.0.0.1:8050 in your browser.

Data sources (all live-linked, no baked-in HTML):
  - ISyE Project/Data and Resources/Call Data/*.xlsx   (NFIRS call records)
  - ISyE Project/Comparison Output/county_ems_comparison_data.xlsx
  - jefferson_county.geojson  (Census TIGER 2023 boundaries)
"""

import os, json, math, hashlib, tempfile, time as _time, copy
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go
import plotly.express as px
import dash_leaflet as dl
from dash_extensions.javascript import assign
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output, dash_table, no_update
from functools import lru_cache

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE     = os.path.dirname(os.path.abspath(__file__))
CALL_DIR = os.path.join(BASE, "ISyE Project", "Data and Resources", "Call Data")
COMPARE_XL = os.path.join(BASE, "ISyE Project", "Comparison Output", "county_ems_comparison_data.xlsx")
GEOJSON  = os.path.join(BASE, "jefferson_county.geojson")
GEOJSON_EMS   = os.path.join(BASE, "jefferson_ems_districts.geojson")
GEOJSON_FIRE  = os.path.join(BASE, "jefferson_fire_districts.geojson")
GEOJSON_STATIONS = os.path.join(BASE, "jefferson_stations.geojson")
GEOJSON_HELEN = os.path.join(BASE, "jefferson_helenville_responders.geojson")
GEOJSON_ZCTA  = os.path.join(BASE, "jefferson_zcta.geojson")
CONTRACT_XL = os.path.join(BASE, "ISyE Project", "Data and Resources",
                           "EMS Contract Details for all Towns in Jefferson County.xlsx")
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "jeff_ems_cache")

# ── 1. Load & merge call data (with parquet cache) ────────────────────────────

NAME_MAP = {
    "CAMBRIDGE COMM FIRE DEPT":            "Cambridge",
    "Edgerton Fire Protection Distict":    "Edgerton",
    "Fort Atkinson Fire Dept":             "Fort Atkinson",
    "Helenville Fire and Rescue District": "Helenville",
    "Town of Ixonia Fire & EMS Dept":      "Ixonia",
    "Jefferson Fire Dept":                 "Jefferson",
    "Johnson Creek Fire Dept":             "Johnson Creek",
    "Palmyra Village Fire Dept":           "Palmyra",
    # Rome Fire Dist and Sullivan Vol Fire Dept are FIRE-ONLY — no EMS role.
    # Neighboring EMS agencies (Whitewater, Fort Atkinson, Edgerton, Western Lakes,
    # Jefferson) handle EMS calls in those towns. Omitted from all EMS analysis.
    "Waterloo Fire Dept":                  "Waterloo",
    "Watertown Fire Dept":                 "Watertown",
    # NOTE: Western Lake Fire District (Waukesha Co. HQ) serves Sullivan/Concord/
    # Palmyra/Ixonia area of Jefferson Co. Its NFIRS file has 6,581 all-district
    # calls (2024); only 263 are Jefferson-Co. incidents per Megan 2026-04-19.
    # AUTH_EMS_CALLS reflects the Jefferson-only 263; analyses using NFIRS data
    # directly apply jefferson_geo_filter.filter_to_jefferson() to drop Waukesha.
    "Western Lake Fire District":          "Western Lakes",
    "Whitewater Fire and EMS":             "Whitewater",
}

# Columns we actually need from the raw NFIRS data
_KEEP_COLS = [
    "Fire Department Name",
    "Alarm Date - Month of Year",
    "Alarm Date - Hour of Day",
    "Alarm Date - Day of Week",
    "Response Time (Minutes)",
    "Incident Type Code Category Description",
    "Aid Given or Received Description",
    "Incident City",
    "Incident Zip Code",
]

# NFIRS files store "Alarm Date - Month of Year" as 3-letter string abbreviations
# ("Jan", "Feb", ...) — pd.to_numeric() coerces these all to NaN.
# Use an explicit mapping instead.
_MONTH_STR_TO_INT = {
    "Jan": 1, "Feb": 2, "Mar": 3,  "Apr": 4,  "May": 5,  "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9,  "Oct": 10, "Nov": 11, "Dec": 12,
}

# NFIRS files store "Alarm Date - Day of Week" as 3-letter abbreviations
# ("Sun", "Mon", ...) — normalize to full names for consistent display.
_DOW_STR_TO_FULL = {
    "Sun": "Sunday", "Mon": "Monday", "Tue": "Tuesday",
    "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday",
    # Also accept full names in case some files differ
    "Sunday": "Sunday", "Monday": "Monday", "Tuesday": "Tuesday",
    "Wednesday": "Wednesday", "Thursday": "Thursday", "Friday": "Friday", "Saturday": "Saturday",
}

def _xlsx_fingerprint():
    """Hash of xlsx file names + mtimes for cache invalidation."""
    parts = []
    for f in sorted(os.listdir(CALL_DIR)):
        if f.endswith(".xlsx"):
            fp = os.path.join(CALL_DIR, f)
            parts.append(f"{f}:{os.path.getmtime(fp):.0f}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()

def _load_call_data():
    """Load call data from parquet cache or fall back to xlsx."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(_CACHE_DIR, "call_data.parquet")
    hash_file  = os.path.join(_CACHE_DIR, "call_data.hash")
    current_hash = _xlsx_fingerprint()

    # Try parquet cache
    if os.path.exists(cache_file) and os.path.exists(hash_file):
        with open(hash_file) as fh:
            cached_hash = fh.read().strip()
        if cached_hash == current_hash:
            print("Loading call data from cache...")
            t0 = _time.time()
            df = pd.read_parquet(cache_file)
            print(f"  cached load: {_time.time()-t0:.2f}s")
            return df

    # Full load from xlsx
    print("Loading call data from Excel (first run or data changed)...")
    t0 = _time.time()
    dfs = []
    for f in sorted(os.listdir(CALL_DIR)):
        if f.endswith(".xlsx"):
            dfs.append(pd.read_excel(os.path.join(CALL_DIR, f), engine="openpyxl"))
    df = pd.concat(dfs, ignore_index=True)
    print(f"  xlsx load: {_time.time()-t0:.2f}s")

    # Apply transforms before caching
    # Drop fire-only departments (Rome Fire Dist, Sullivan Vol Fire Dept) — no EMS role
    _FIRE_ONLY = ("Rome Fire Dist", "Sullivan Vol Fire Dept")
    df = df[~df["Fire Department Name"].isin(_FIRE_ONLY)].copy()
    df["Department"] = df["Fire Department Name"].map(NAME_MAP).fillna(df["Fire Department Name"])
    # Month column is stored as 3-letter abbreviation strings ("Jan".."Dec") — map to 1..12
    df["Month"]      = df["Alarm Date - Month of Year"].map(_MONTH_STR_TO_INT)
    df["Hour"]       = pd.to_numeric(df["Alarm Date - Hour of Day"],   errors="coerce")
    df["RT"]         = pd.to_numeric(df["Response Time (Minutes)"],    errors="coerce")
    df["IsEMS"]      = df["Incident Type Code Category Description"].str.startswith("Rescue and EMS", na=False)

    # Keep only needed columns + derived columns
    keep = [c for c in _KEEP_COLS if c in df.columns] + ["Department","Month","Hour","RT","IsEMS"]
    df = df[keep]

    # Write cache
    try:
        df.to_parquet(cache_file, index=False)
        with open(hash_file, "w") as fh:
            fh.write(current_hash)
        print("  cache saved for next startup")
    except Exception as e:
        print(f"  cache write failed (non-fatal): {e}")

    return df

raw = _load_call_data()

# Drop fire-only depts even when reloading from an older cache (pre-cleanup parquet)
_FIRE_ONLY_DEPT_NAMES = ("Rome Fire Dist", "Sullivan Vol Fire Dept")
if "Fire Department Name" in raw.columns:
    raw = raw[~raw["Fire Department Name"].isin(_FIRE_ONLY_DEPT_NAMES)].copy()

# If loaded from cache, derived columns already exist; if from xlsx, they were just created.
# Ensure derived columns exist (cache path)
if "Department" not in raw.columns:
    raw["Department"] = raw["Fire Department Name"].map(NAME_MAP).fillna(raw["Fire Department Name"])
    # Month column is stored as 3-letter abbreviation strings ("Jan".."Dec") — map to 1..12
    raw["Month"]      = raw["Alarm Date - Month of Year"].map(_MONTH_STR_TO_INT)
    raw["Hour"]       = pd.to_numeric(raw["Alarm Date - Hour of Day"],   errors="coerce")
    raw["RT"]         = pd.to_numeric(raw["Response Time (Minutes)"],    errors="coerce")
    raw["IsEMS"]      = raw["Incident Type Code Category Description"].str.startswith("Rescue and EMS", na=False)

# Normalize DOW abbreviations to full weekday names — NFIRS files use 3-letter strings
# ("Sun", "Mon", ...) but the heatmap expects full names for the reindex step.
# Map first, then fill any unmapped values with the original string (preserve unknown values).
if "Alarm Date - Day of Week" in raw.columns:
    _dow_orig = raw["Alarm Date - Day of Week"].astype(str)
    _dow_mapped = _dow_orig.map(_DOW_STR_TO_FULL)
    raw["Alarm Date - Day of Week"] = _dow_mapped.where(_dow_mapped.notna(), _dow_orig)

rt_clean = raw[raw["RT"].between(0, 60)].copy()

print(f"  {len(raw):,} total incidents, {raw['Department'].nunique()} departments")

# ── Partial-year data extrapolation ───────────────────────────────────────────
# Some NFIRS files contain fewer than 12 months of call data but budgets are
# full-year contract values.  We extrapolate call counts to 12 months so that
# cost-per-call ratios are apples-to-apples.
# Detected via analysis of "Alarm Date - Month of Year" column per file:
#   Palmyra    → 3 months (Jan, Feb, Mar)  → multiply by 12/3 = 4.0
#   Helenville → 7 months (Mar–Sep)        → multiply by 12/7 ≈ 1.714
_PARTIAL_YEAR_MONTHS = {"Palmyra": 3, "Helenville": 7}

def _extrapolate_annual(counts_series, dept_series):
    """Scale raw NFIRS counts to 12-month estimate for departments with partial data."""
    result = counts_series.copy()
    for dept, months in _PARTIAL_YEAR_MONTHS.items():
        mask = dept_series == dept
        result.loc[mask] = (counts_series.loc[mask] / months * 12).round(0)
    return result

# ── Authoritative 2024 Call Volumes (Megan 2026-04-19) ──────────────────────
# Fire+EMS combined, Jefferson-County geography only. Supersedes prior NFIRS-
# derived totals that included out-of-county calls (Western Lakes district
# spans Waukesha Co., Edgerton/Lakeside spans Rock Co., Whitewater spans
# Walworth Co.). Pre-correction snapshot preserved at git commit 9b7d477.
AUTH_EMS_CALLS = {
    "Cambridge":      197,   # was 87 (EMS-only); Megan: 197 fire+EMS combined
    "Fort Atkinson":  1616,
    "Ixonia":         338,   # was 289; Megan email correction
    "Jefferson":      1457,
    "Johnson Creek":  1090,  # was 487 (EMS-only); Megan: 1090 fire+EMS combined
    "Lake Mills":     518,
    "Palmyra":        32,
    "Waterloo":       520,
    "Watertown":      2012,
    "Whitewater":     64,    # Koshkonong & Cold Springs contracts only
    "Edgerton":       289,   # was 2138 (all-district NFIRS); Megan: 289 Jefferson-only
    "Western Lakes":  263,   # was 5633 (all-district NFIRS); Megan: 263 Jefferson-only
}
_AUTH_COUNTY_TOTAL = sum(AUTH_EMS_CALLS.values())  # 8,396

# ── Call volume notes (documents data-source caveats per dept) ─────────────
# Drives asterisk footnotes on call volume tables so readers see the lineage.
CALL_VOLUME_NOTES = {
    "Cambridge":     "Megan 2026-04-19: 197 fire+EMS combined, confirmed with "
                     "Cambridge 2024 Annual Report.",
    "Ixonia":        "Megan 2026-04-19: 338. Prior dataset (289) had non-EMS "
                     "calls pre-filtered for another project.",
    "Johnson Creek": "Megan 2026-04-19: 1,090 fire+EMS combined, confirmed with "
                     "department. Prior NFIRS figure (487) was underreported.",
    "Waterloo":      "Megan 2026-04-19: 520 fire+EMS combined. Provider CSV "
                     "(379 rows) is EMS-only subset.",
    "Edgerton":      "Megan 2026-04-19: 289 Jefferson-County calls ONLY, "
                     "provided directly by department. Prior NFIRS figure (2,138) "
                     "included the full Lakeside FPD jurisdiction (mostly Rock Co.).",
    "Western Lakes": "Megan 2026-04-19: 263 Jefferson-County calls ONLY, "
                     "filtered from their all-district dataset. Prior figure "
                     "(5,633) included Waukesha-Co. responses.",
}

# ── Data quality notes (affect incident-level/micro analyses, not macro KPIs) ─
# Macro KPIs use AUTH_EMS_CALLS (Megan's authoritative totals) directly.
# Micro analyses (hourly patterns, address-level, concurrent-call, secondary-
# network) may diverge from macro totals for the depts below.
DATA_QUALITY_NOTES = {
    "Edgerton":       "INCIDENT-LEVEL DATA UNAVAILABLE. NFIRS export yields only "
                      "~26 Jefferson-area records out of Megan's 289 authoritative "
                      "total. Macro KPIs reflect 289; hourly/address/concurrent "
                      "analyses are not possible for Edgerton.",
    "Western Lakes":  "Incident-level filter yields 281 records vs 263 target "
                      "(+6.8%). Muni-boundary ambiguity (Sullivan town/village, "
                      "Concord town) drives the delta. Macro KPI uses 263.",
    "Fort Atkinson":  "Macro KPI 1,616 (Megan). NFIRS has 2,076 Jefferson-Co. "
                      "incidents; micro analyses may over-count by ~26%. Gap "
                      "possibly due to excluded service/hazardous-condition "
                      "records in Megan's count.",
    "Watertown":      "Macro KPI 2,012 (Megan). City jurisdiction crosses into "
                      "Dodge Co.; NFIRS shows 2,719 total. Per-ZIP/per-address "
                      "analyses may show Dodge-Co. addresses.",
    "Waterloo":       "Macro KPI 520 (Megan, fire+EMS). Provider CSV 379 rows is "
                      "EMS-only. Hourly/address analyses use the EMS-only subset.",
}

# ── High-frequency call addresses (from Looker Studio PDFs, 2024) ───────────
# Top-volume addresses that may indicate nursing facilities, hospitals, or
# institutional callers worth investigating for community paramedicine outreach.
HIGH_FREQ_ADDRESSES = {
    # Format: (address, calls, note, lat, lon)  — lat/lon geocoded via Nominatim.
    # Minimum 5 calls per address. Edgerton excluded (Looker data join error).
    "Fort Atkinson": [
        ("430 Wilcox St",       184, "Care facility",  42.93370, -88.82998),
        ("525 Memorial Dr",      76, "",                42.93428, -88.82443),
        ("737 Reena Ave",        73, "",                42.94041, -88.86390),
        ("1 W Milwaukee Ave",    46, "",                42.92677, -88.83717),
        ("915 S Main St",        28, "",                42.91656, -88.83684),
        ("217 S Water St E",     23, "",                42.92750, -88.83360),
        ("1055 East St",         21, "",                42.91479, -88.83059),
    ],
    "Watertown": [
        ("121 Hospital Dr",     128, "Hospital",        43.19911, -88.69889),
        ("1020 Hill St",         90, "Care facility",   43.20190, -88.70750),
        ("1301 E Main St",       68, "",                43.19064, -88.71092),
        ("1121 Highland Ave",    55, "",                43.20236, -88.70860),
        ("1047 Hill St",         51, "",                43.20190, -88.70667),
        ("700 Welsh Rd",         45, "",                43.20658, -88.75879),
        ("106 Jones St",         25, "",                43.19585, -88.72355),
    ],
    "Johnson Creek": [
        ("1 Hartwig Dr",         43, "",                43.08338, -88.76660),
        ("W5095 River Dr",       26, "",                43.18084, -88.72831),
        ("N7855 Little Coffee Rd",13,"",                43.16500, -88.74000),
        ("440 Wright Rd",         9, "",                43.08180, -88.75990),
        ("1275 Remmel Dr",        9, "",                43.09206, -88.75912),
        ("1 Bobcat Ln",           8, "",                43.08169, -88.77051),
    ],
    "Lake Mills": [
        ("300 O'Neil St",        14, "",                43.08338, -88.90227),
        ("144 E Prospect St",    10, "",                43.08577, -88.90823),
        ("901 Mulberry St",       9, "",                43.08522, -88.90281),
        ("403 O'Neil St",         8, "",                43.08276, -88.90125),
        ("228 Water St",          7, "",                43.07855, -88.91090),
        ("200 E Tyranena Park Rd",7, "",                43.08919, -88.90616),
    ],
    "Whitewater": [
        ("N346 Twinkling Star Rd",8, "",                42.85222, -88.79576),
        ("N374 Twinkling Star Rd",5, "",                42.84911, -88.79660),
    ],
    # Departments below 5-call threshold or no address data: Cambridge, Ixonia, Palmyra, Waterloo, Jefferson
    # Edgerton excluded — Looker report shows Fort Atkinson addresses (data join error)
    # Western Lakes addresses truncated in PDF bar chart — excluded pending full data
}

# ── Filter to EMS-only scope ─────────────────────────────────────────────────
# The project focuses exclusively on EMS calls. Filter raw NFIRS to EMS rows only.
raw = raw[raw["IsEMS"]].copy()
rt_clean = raw[raw["RT"].between(0, 60)].copy()

print(f"  {len(raw):,} EMS incidents after filtering, {raw['Department'].nunique()} departments")

# ── Pre-aggregated summary tables (callbacks filter these instead of raw) ─────
_dept_vol = raw.groupby("Department").agg(
    Total=("Department", "size"),
    EMS=("Department", "size"),  # All rows are EMS now
).reset_index()

_dept_hour = raw.groupby(["Department", "Hour"]).size().reset_index(name="Calls")
_dept_month = raw.groupby(["Department", "Month"]).size().reset_index(name="Calls")
_dept_dow = raw.groupby(["Department", "Alarm Date - Day of Week"]).size().reset_index(name="Calls")
_dept_inc_type = raw.groupby(["Department", "Incident Type Code Category Description"]).size().reset_index(name="Calls")
_dept_aid = raw.groupby(["Department", "Aid Given or Received Description"]).size().reset_index(name="Calls")

# ── Computed globals for dynamic KPI cards ────────────────────────────────────
_total_ems_calls = _AUTH_COUNTY_TOTAL           # Authoritative total: 8,396 (corrected 2026-04-19)
_avg_rt          = f"{rt_clean['RT'].mean():.1f} min"
_med_rt          = f"{rt_clean['RT'].median():.1f} min"
_n_depts         = len(AUTH_EMS_CALLS)          # 12 EMS-providing communities
_ems_rt_clean    = rt_clean.copy()              # All rows are EMS now
_pct_ems_over8   = f"{100*(_ems_rt_clean['RT'] > 8).sum()/len(_ems_rt_clean):.1f}%"

# ── 2. Load comparison workbook ───────────────────────────────────────────────
xl = pd.ExcelFile(COMPARE_XL)
comparison   = xl.parse("Comparison")          # FIX 9: loaded but previously unused
muni_kpi     = xl.parse("Jeff_Municipal_Breakdown")
rt_pct       = xl.parse("Jeff_Response_Percentiles")

# ── Exclude fire-only departments from EMS provider tables ────────────────────
# Rome Fire District and Sullivan VFD are FIRE-ONLY — they operate no ambulances.
# EMS in those areas is provided by Western Lakes Fire Department.
# Their rows appear in the Excel sheets because NFIRS records list them as the
# responding department for fire apparatus that assisted at EMS incidents.
# Keeping them in muni_kpi / rt_pct would imply they are EMS providers, which
# is factually incorrect. Geographic/map references (Town of Sullivan, ZIP 53178)
# are unaffected — only EMS provider listings are excluded here.
_EMS_FIRE_ONLY = {"Rome", "Sullivan"}
muni_kpi = muni_kpi[~muni_kpi["Municipality"].isin(_EMS_FIRE_ONLY)].reset_index(drop=True)
rt_pct   = rt_pct[~rt_pct["Municipality"].isin(_EMS_FIRE_ONLY)].reset_index(drop=True)
call_types   = xl.parse("Jeff_Call_Types")
portage_vol  = xl.parse("Portage_Call_Volume_Trend")
portage_rev  = xl.parse("Portage_Revenue_Trend")
portage_pay  = xl.parse("Portage_Payor_Mix_2024")

# ── 3. Budget data (from PDFs — hand-compiled) ────────────────────────────────
budget = pd.DataFrame([
    # Ixonia: FY2024. EMS_Revenue = LifeQuest patient billing only (not total fund revenue $479,881).
    # Total fund revenue includes town contracts ($180k), state dues, fund balance drawdown.
    {"Municipality": "Ixonia",        "FY": 2024, "Total_Expense": 631144,  "EMS_Revenue": 125000,  "Net_Tax": 151263,  "Model": "Volunteer+FT",  "Staff_FT": 2,  "Staff_PT": 45},

    # Jefferson: FY2025. General Fund EMS ($876,300) + Referendum Fund 31 ($624,000).
    # EMS_Revenue = patient billing $600k + misc $30k + ambulance contracts $102k.
    # Net_Tax = levy covering EMS operations deficit (operations portion only).
    # Source: 2025 Budget Document for Council + April 2023 Referendum Fact Sheet.
    {"Municipality": "Jefferson",     "FY": 2025, "Total_Expense": 1500300, "EMS_Revenue": 732000,  "Net_Tax": 144300,  "Model": "Career",        "Staff_FT": 6,  "Staff_PT": 20},

    # Watertown: FY2025. Staffing updated from 2024 Annual Report:
    # 27 shift FF/EMS + 4 admin = 31 FT sworn; 3 PT inspectors.
    # Source: Watertown EMS Annual Report 2024.
    {"Municipality": "Watertown",     "FY": 2025, "Total_Expense": 3833800, "EMS_Revenue": 817000,  "Net_Tax": 2947719, "Model": "Career",         "Staff_FT": 31, "Staff_PT": 3},

    # Fort Atkinson: FY2025. EMS Fund only (Fund 7, self-funding via billing + contracts).
    # General Fund fire ($286,500) excluded. Net_Tax = 0 (EMS fund is self-sustaining).
    # Staffing: 15 FT + 1 Chief = 16 FT sworn, 28 PT. Source: FAFD 2024 Annual Report.
    {"Municipality": "Fort Atkinson", "FY": 2025, "Total_Expense": 760950,  "EMS_Revenue": 713850,  "Net_Tax": 0,       "Model": "Career+PT",     "Staff_FT": 16, "Staff_PT": 28},

    # Whitewater: FY2025. Full Fire & EMS Fund 249.
    # Net_Tax = General Fund levy transfer to Fire/EMS ($1,370,114).
    # Staffing from McMahon staffing analysis Jan 2025: 15 FT + 17 PT/POC.
    {"Municipality": "Whitewater",    "FY": 2025, "Total_Expense": 2710609, "EMS_Revenue": 625000,  "Net_Tax": 1370114, "Model": "Career+PT",     "Staff_FT": 15, "Staff_PT": 17},

    # Cambridge: FY2025. ALS-capable combination dept (confirmed active paramedic hiring as of 2025).
    # NOTE: Cambridge Village + Town of Oakland voted Dec 2023 to withdraw from the Cambridge
    # Fire/EMS Commission (effective 2025). EMS Medical Director resigned Mar 2025;
    # Fort Atkinson identified as fallback provider. Service continuity uncertain post-2025.
    # Billing via EMS-MC (800) 948-7991. Source: Cambridge Community Fire/EMS District website.
    {"Municipality": "Cambridge",     "FY": 2025, "Total_Expense": 92000,   "EMS_Revenue": 0,        "Net_Tax": 92000,   "Model": "Volunteer",     "Staff_FT": 0,  "Staff_PT": 31},

    # Lake Mills: FY2025. General Fund EMS contract payment to Lake Mills Fire Dept.
    # EMS_Revenue = ambulance billing ($5k current + $3k prior yr). Very low collection.
    # Net_Tax = full General Fund transfer ($347,000 contract payment).
    # Source: City of Lake Mills 2025 Budget All Funds + 2024 Summary Financial Report.
    {"Municipality": "Lake Mills",    "FY": 2025, "Total_Expense": 347000,  "EMS_Revenue": 8000,    "Net_Tax": 347000,  "Model": "Career+Vol",    "Staff_FT": 4,  "Staff_PT": 20},

    # Waterloo: FY2025. Fire Dept Fund 220 (balanced). Tax shares from City + Towns = Net_Tax.
    # EMS_Revenue = EMS runs billing (commercial budget figure).
    # Staffing corrected per Waterloo Fire Chief interview (Mar 11 2026): 4 FT (EMS primary),
    # 22 PT/per-call EMS-eligible (10 EMS-only + 12 cross-trained); 20 fire-only not counted.
    # PT are mainly per-call volunteers — small share of budget. Chief says need 6 FT for 24/7.
    # Source: City of Waterloo fire_dept_2025.pdf + Chief interview 3/11/26.
    {"Municipality": "Waterloo",      "FY": 2025, "Total_Expense": 1102475, "EMS_Revenue": 200000,  "Net_Tax": 557475,  "Model": "Career+Vol",    "Staff_FT": 4,  "Staff_PT": 22},

    # Johnson Creek: FY2025. Fire-EMS Fund 210 total. ALS (Paramedic) — 24/7 ALS ambulance confirmed.
    # 3 FT (incl. chief who is paramedic), 18-20 PT EMS, 12-15 paid-on-call fire-only (~33 mid-est).
    # 2nd ambulance staffed as-needed (nearby staff respond from home). ~750 calls/yr per chief (NFIRS shows 636).
    # EMS_Revenue = EMS runs billing ($230,500) + prior year collections ($58,000).
    # Source: adopted-2025-budget-november-11-2024-web.pdf + Chief interview Mar 13 2026.
    {"Municipality": "Johnson Creek", "FY": 2025, "Total_Expense": 1134154, "EMS_Revenue": 288600,  "Net_Tax": 472352,  "Model": "Combination",   "Staff_FT": 3,  "Staff_PT": 33},

    # Palmyra: FY2025. Fire & Rescue Fund 800 (debt service excluded from Total_Expense).
    # EMS_Revenue = gross $200k minus $60k uncollectible write-off = $140k net.
    # Net_Tax = village levy $252,613 + town contribution $250,178. BLS transport only;
    # ALS intercept provided by Western Lakes Fire District. Billing via EMS-MC.
    # Source: 2025-Revenues.pdf + 2025-Expenses.pdf.
    {"Municipality": "Palmyra",       "FY": 2025, "Total_Expense": 817740,  "EMS_Revenue": 140000,  "Net_Tax": 502791,  "Model": "Volunteer",     "Staff_FT": 0,  "Staff_PT": 20},

    # Edgerton (Lakeside Fire-Rescue): FY2024-25. ALS/Paramedic level. Multi-county district
    # (Rock, Dane, Jefferson). 11 municipalities, 220 sq mi, pop >25,000.
    # 2024 call volume: 2,257 confirmed (lakesidefirerescuewi.gov). 24 FT team members confirmed.
    # West division EMS budget ~$704,977; east division ~$2.2M total. Levy ~$1.35M.
    # Total_Expense = partial west division EMS figure only (full multi-division budget not public).
    # Billing via Digitech (833) 532-2205. Source: lakesidefirerescuewi.gov + Gazette Extra.
    {"Municipality": "Edgerton",      "FY": 2025, "Total_Expense": 704977,  "EMS_Revenue": None,    "Net_Tax": None,    "Model": "Career+PT",     "Staff_FT": 24, "Staff_PT": None},
])

billing = pd.DataFrame([
    # Rates confirmed from 2025 published fee schedules (local PDF). Others not publicly posted.
    {"Municipality": "Jefferson",     "BLS": 1900, "ALS1": 2150, "ALS2": 2225, "Mileage": 30},
    {"Municipality": "Fort Atkinson", "BLS": 1500, "ALS1": 1700, "ALS2": 1900, "Mileage": 26},
    {"Municipality": "Watertown",     "BLS": 1100, "ALS1": 1300, "ALS2": 1500, "Mileage": 22},
])
# WI peer municipality billing rates for benchmarking context (2025 published fee schedules).
# Sources: municipal websites fetched Mar 2026. These are NOT Jefferson County departments.
# Note: 11 of 14 Jefferson Co. depts do not publish rates online; these benchmarks provide
# context for what "typical" WI rates look like. Rates are billed (list price), not collected.
wi_billing_benchmarks = pd.DataFrame([
    {"Municipality": "Waukesha",        "BLS": 2100, "ALS1": 2200, "ALS2": 2400, "Mileage": 25,
     "Source": "waukesha-wi.gov (eff. Jan 2023)", "Note": "Soft billing — residents not charged after insurance"},
    {"Municipality": "Fitch-Rona",      "BLS": 1693, "ALS1": 1693, "ALS2": None, "Mileage": 26,
     "Source": "fitchronaems.com (2026 schedule)", "Note": "Combined BLS/ALS rate; non-res $1,812"},
    {"Municipality": "Madison",         "BLS": 1410, "ALS1": 1410, "ALS2": None, "Mileage": 16,
     "Source": "cityofmadison.com (2022-2026)", "Note": "Flat rate, no BLS/ALS distinction"},
    {"Municipality": "Richfield",       "BLS":  700, "ALS1":  850, "ALS2": 1100, "Mileage": 19,
     "Source": "richfieldwi.gov (eff. Jan 2025)", "Note": "Volunteer dept; non-res +$100-150"},
    {"Municipality": "Brookfield",      "BLS": 1500, "ALS1": None, "ALS2": None, "Mileage": None,
     "Source": "ci.brookfield.wi.us (2025)", "Note": "Suburban benchmark (prior research)"},
])

# ── 3c. Billing Revenue — Actual Net Collections (EMS|MC / Chief Association) ─
# Source: "Jefferson County Chief Association Agency Data 2025.xlsx" (new3.31.26/)
# These are actual net collections from the billing vendor, NOT budget estimates.
# 9 agencies reporting. Missing: Cambridge, Western Lakes, Whitewater.
BILLING_COLLECTIONS = pd.DataFrame([
    {"Agency": "Jefferson",     "Collections_2024":  667683.27, "Collections_2025":  789696.91},
    {"Agency": "Watertown",     "Collections_2024":  823865.88, "Collections_2025": 1004584.35},
    {"Agency": "Palmyra",       "Collections_2024":   63921.77, "Collections_2025":  104826.42},
    {"Agency": "Waterloo",      "Collections_2024":   12089.18, "Collections_2025":  268717.20},
    {"Agency": "Ixonia",        "Collections_2024":   99632.04, "Collections_2025":  148941.94},
    {"Agency": "Johnson Creek", "Collections_2024":  224779.84, "Collections_2025":  303297.11},
    {"Agency": "Edgerton",      "Collections_2024":  960738.03, "Collections_2025": 1239440.54},
    {"Agency": "Fort Atkinson", "Collections_2024":  594919.61, "Collections_2025":  791679.53},
    {"Agency": "Lake Mills",    "Collections_2024":   22755.88, "Collections_2025":   47789.73},
])
BILLING_COLLECTIONS["Change"]     = BILLING_COLLECTIONS["Collections_2025"] - BILLING_COLLECTIONS["Collections_2024"]
BILLING_COLLECTIONS["Pct_Change"] = ((BILLING_COLLECTIONS["Change"] / BILLING_COLLECTIONS["Collections_2024"]) * 100).round(1)

# ── 3d. Mill Rate Levy Projections (WI DOA population-based) ─────────────────
# Source: "Emergency Services Population - Jefferson County.xlsx" (new3.31.26/)
#   -> "Payment by Service Provider" sheet.
# Shows hypothetical county EMS levy amounts at different mill rates.
_MILL_RATES = [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0]
LEVY_BY_PROVIDER = pd.DataFrame([
    {"Provider": "Cambridge",     0.1:   4948, 0.2:   9896, 0.25:  12370, 0.3:  14844, 0.4:  19792, 0.5:  24740, 0.75:  37110, 1.0:  49479},
    {"Provider": "Edgerton",      0.1:   7118, 0.2:  14236, 0.25:  17795, 0.3:  21354, 0.4:  28472, 0.5:  35591, 0.75:  53386, 1.0:  71181},
    {"Provider": "Fort Atkinson", 0.1: 269519, 0.2: 539037, 0.25: 673796, 0.3: 808556, 0.4:1078074, 0.5:1347593, 0.75:2021389, 1.0:2695186},
    {"Provider": "Ixonia",        0.1:  86633, 0.2: 173265, 0.25: 216581, 0.3: 259898, 0.4: 346530, 0.5: 433163, 0.75: 649744, 1.0: 866325},
    {"Provider": "Jefferson",     0.1: 161922, 0.2: 323845, 0.25: 404806, 0.3: 485767, 0.4: 647689, 0.5: 809612, 0.75:1214418, 1.0:1619224},
    {"Provider": "Johnson Creek", 0.1:  81034, 0.2: 162067, 0.25: 202584, 0.3: 243101, 0.4: 324134, 0.5: 405168, 0.75: 607751, 1.0: 810335},
    {"Provider": "Palmyra",       0.1:  42781, 0.2:  85562, 0.25: 106952, 0.3: 128343, 0.4: 171124, 0.5: 213905, 0.75: 320857, 1.0: 427810},
    {"Provider": "Lake Mills",    0.1: 160519, 0.2: 321038, 0.25: 401298, 0.3: 481557, 0.4: 642076, 0.5: 802595, 0.75:1203893, 1.0:1605190},
    {"Provider": "Waterloo",      0.1:  66595, 0.2: 133190, 0.25: 166487, 0.3: 199784, 0.4: 266379, 0.5: 332974, 0.75: 499461, 1.0: 665948},
    {"Provider": "Watertown",     0.1: 239064, 0.2: 478128, 0.25: 597660, 0.3: 717192, 0.4: 956256, 0.5:1195320, 0.75:1792981, 1.0:2390641},
    {"Provider": "Western Lakes", 0.1:  65206, 0.2: 130412, 0.25: 163015, 0.3: 195618, 0.4: 260823, 0.5: 326029, 0.75: 489044, 1.0: 652059},
    {"Provider": "Whitewater",    0.1:  71253, 0.2: 142507, 0.25: 178133, 0.3: 213760, 0.4: 285013, 0.5: 356267, 0.75: 534400, 1.0: 712534},
])
_LEVY_COUNTY_TOTALS = {r: int(LEVY_BY_PROVIDER[r].sum()) for r in _MILL_RATES}

# ── 3e. Provider-Level Call Data Summary (new3.31.26/Data from Providers) ────
PROVIDER_CALL_SUMMARY = pd.DataFrame([
    {"Department": "Edgerton (Lakeside)", "Records": 289, "Data_Fields": "Date, Address, Transport Type, Care Level",
     "Care_Level": "ALS Ground Transport", "Has_RT": "No", "Source_File": "Edgerton EMS_Incidents.csv"},
    {"Department": "Jefferson",           "Records": 1457, "Data_Fields": "Date, Dispatch/Enroute/Arrival, City, Township",
     "Care_Level": "Mixed (ALS primary)", "Has_RT": "Yes", "Source_File": "Jefferson Fire Dept 2024 EMS Call Data.xlsx"},
    {"Department": "Johnson Creek",       "Records": 1090, "Data_Fields": "Date, Address, Type, Zone, Dispatch-Arrival, Mode",
     "Care_Level": "Mixed EMS types", "Has_RT": "Yes", "Source_File": "Johnson Creek EMS Data 2024.csv"},
    {"Department": "Lake Mills (Ryan Bros)", "Records": 518, "Data_Fields": "Date, Dispatch/Enroute, Address, Service Type, Care Level",
     "Care_Level": "ALS-Paramedic", "Has_RT": "Yes", "Source_File": "Lake Mills Ryan Bros EMS Data 2024.csv"},
    {"Department": "Waterloo",            "Records": 520, "Data_Fields": "Date, Time, Transport, Address, Care Level, RT",
     "Care_Level": "ALS-AEMT", "Has_RT": "Yes", "Source_File": "Waterloo Call Data.xlsx"},
    {"Department": "Whitewater (Jeff Co)", "Records": 64, "Data_Fields": "Date, Incident Type, Address, ZIP, District",
     "Care_Level": "Mixed", "Has_RT": "No", "Source_File": "Whitewater Fire Dept Call Data...xlsx"},
])

# ── ALS/BLS service level by department (from web research Mar 2026) ──────────
# Sources: department websites, Wisconsin EMS Association, NPI profiles, news reports.
# Confidence: High = confirmed from official source; Medium = inferred; Low = unknown.
ALS_LEVELS = {
    "Watertown":      {"Level": "ALS",  "Notes": "Career dept, full paramedic", "Confidence": "High"},
    "Fort Atkinson":  {"Level": "ALS",  "Notes": "ALS EMS Fund, self-sustaining", "Confidence": "High"},
    "Whitewater":     {"Level": "ALS",  "Notes": "Converted BLS→ALS 2023 via referendum", "Confidence": "High"},
    "Jefferson":      {"Level": "ALS",  "Notes": "Career dept w/ referendum staffing", "Confidence": "High"},
    "Johnson Creek":  {"Level": "ALS",  "Notes": "24/7 ALS ambulance confirmed", "Confidence": "High"},
    "Edgerton":       {"Level": "ALS",  "Notes": "Paramedic-level response (Lakeside Fire-Rescue)", "Confidence": "High"},
    "Cambridge":      {"Level": "ALS",  "Notes": "ALS capable; service disrupted 2025", "Confidence": "High"},
    "Waterloo":       {"Level": "AEMT", "Notes": "EMT+AEMT certified staff; between BLS and ALS", "Confidence": "Medium"},
    "Palmyra":        {"Level": "BLS",  "Notes": "BLS transport; ALS intercept via Western Lakes FD", "Confidence": "High"},
    "Ixonia":         {"Level": "BLS",  "Notes": "Likely BLS; LifeQuest/EMSMC billing", "Confidence": "Low"},
    "Helenville":     {"Level": "BLS",  "Notes": "All-volunteer (35 members); likely BLS", "Confidence": "Low"},
    "Lake Mills":     {"Level": "BLS",  "Notes": "LMFD BLS support; Ryan Brothers ALS under contract", "Confidence": "High"},
    "Western Lakes":  {"Level": "ALS",  "Notes": "Multi-county ALS; primary service area is Waukesha Co.", "Confidence": "High"},
}

# ── ALS/BLS action-type percentages (from Looker Studio PDFs, 2024) ─────────
# What % of calls result in ALS vs BLS-level care. Derived from "Primary Action Taken"
# or "Level of Care Provided" fields in each department's Looker Studio report.
# Departments not listed had no ALS/BLS split available in their report.
ALS_BLS_PCTS = {
    "Fort Atkinson":  {"ALS": 49.8, "BLS": 35.2, "Other": 15.0},
    "Edgerton":       {"ALS": 48.0, "BLS": 32.1, "Other": 19.9},
    "Ixonia":         {"ALS": 50.0, "BLS": 20.2, "Other": 29.8},
    "Watertown":      {"ALS": 49.8, "BLS": 28.3, "Other": 21.9},
    "Western Lakes":  {"ALS": 21.4, "BLS": 39.2, "Other": 39.4},
    "Lake Mills":     {"ALS": 46.3, "BLS": 19.7, "Critical Care": 19.1, "Other": 14.9},
    "Palmyra":        {"ALS": 0.0,  "BLS": 59.4, "Other": 40.6},
    "Waterloo":       {"ALS": 13.7, "BLS": 9.6, "Transport": 44.6, "First Aid": 18.2, "Other": 13.9},
}

# ── 3a. Service Area Population (WI DOA Preliminary 2025 Estimates) ──────────
# Source: "Emergency Services Population - Jefferson County.xlsx" (new3.31.26/)
#   → "Sorted by Provider" sheet — WI Dept of Administration Preliminary 2025 Estimates.
#   Populations assigned by responding EMS unit and municipality coverage ratio.
#   County total: 86,855.  Supersedes prior Census ACS / DOA estimates.
SERVICE_AREA_POP = {
    "Watertown":     16524,   # City of Watertown 14,628 + Town of Milford 746 + Town of Watertown 1,150
    "Fort Atkinson": 18629,   # City of Fort Atkinson 12,455 + T. Hebron 659 + T. Jefferson 349 + T. Koshkonong 3,486 + T. Oakland 1,183 + T. Sumner 497
    "Whitewater":     4925,   # City of Whitewater 4,029 + Town of Cold Spring 737 + Town of Koshkonong 159
    "Jefferson":     11192,   # City of Jefferson 7,806 + T. Aztalan 665 + T. Farmington 461 + T. Hebron 392 + T. Jefferson 1,700 + T. Oakland 166 + T. Sullivan 2
    "Lake Mills":    11095,   # City of Lake Mills 6,835 + T. Aztalan 396 + T. Lake Mills 1,983 + T. Oakland 1,881 (Ryan Brothers EMS)
    "Johnson Creek":  5601,   # Village of Johnson Creek 3,702 + T. Aztalan 312 + T. Farmington 940 + T. Milford 284 + T. Watertown 363
    "Cambridge":       342,   # Village of Cambridge 102 + Town of Lake Mills 240 (Jeff Co. portion only)
    "Palmyra":        2957,   # Village of Palmyra 1,717 + Town of Palmyra 1,240
    "Ixonia":         5988,   # Village of Lac La Belle 2 + T. Concord 444 + T. Ixonia 5,092 + T. Watertown 450
    "Edgerton":        492,   # Town of Koshkonong 159 + Town of Sumner 333 (Jeff Co. portion of Lakeside district)
    "Waterloo":       4603,   # City of Waterloo 3,644 + Town of Milford 81 + Town of Waterloo 878
    "Western Lakes":  4507,   # Village of Sullivan 657 + T. Concord 1,514 + T. Palmyra 2 + T. Sullivan 2,334
    "Helenville":     1500,   # Small district — estimated from GeoJSON area (not in DOA provider breakdown)
}
# Population data sources (for dashboard citation):
_POP_SOURCES = [
    ("Emergency Services Population - Jefferson County.xlsx (new3.31.26/)", "WI DOA Preliminary 2025 Estimates — Sorted by Provider sheet"),
    ("WI DOA 2025 Preliminary Municipal Estimates", "https://doa.wi.gov/DIR/Final_Ests_Muni_2025.xlsx"),
]

# ── Multi-provider coverage areas (from Emergency Services Population xlsx) ──
# Towns served by 2+ EMS providers — indicates mutual aid corridors and
# coverage overlap. Data from "Raw Data" sheet, WI DOA 2025 estimates.
# Format: municipality → [(provider, population_served), ...]
MULTI_PROVIDER_COVERAGE = {
    "Town of Aztalan":    [("Jefferson", 665), ("Johnson Creek", 312), ("Lake Mills", 396)],
    "Town of Concord":    [("Ixonia", 444), ("Western Lakes", 1514)],
    "Town of Farmington": [("Jefferson", 461), ("Johnson Creek", 940)],
    "Town of Hebron":     [("Fort Atkinson", 659), ("Jefferson", 392)],
    "Town of Ixonia":     [("Ixonia", 5092), ("Watertown", 0)],   # Ixonia primary; Watertown minor overlap
    "Town of Jefferson":  [("Fort Atkinson", 349), ("Jefferson", 1700)],
    "Town of Koshkonong": [("Edgerton", 159), ("Fort Atkinson", 3486), ("Whitewater", 159)],
    "Town of Lake Mills":  [("Cambridge", 240), ("Lake Mills", 1983)],
    "Town of Milford":    [("Johnson Creek", 284), ("Waterloo", 81), ("Watertown", 746)],
    "Town of Oakland":    [("Fort Atkinson", 1183), ("Jefferson", 166), ("Lake Mills", 1881)],
    "Town of Palmyra":    [("Palmyra", 1240), ("Western Lakes", 2)],
    "Town of Sullivan":   [("Jefferson", 2), ("Western Lakes", 2334)],
    "Town of Sumner":     [("Edgerton", 333), ("Fort Atkinson", 497)],
    "Town of Watertown":  [("Ixonia", 450), ("Johnson Creek", 363), ("Watertown", 1150)],
}

# ── Service Area Population table for Contracts tab ────────────────────────
# Derived from Emergency Services Population - Jefferson County.xlsx
# "Sorted by Provider" sheet — WI DOA Preliminary 2025 Estimates
_SVC_AREA_POP_DATA = {
    "Cambridge":     {"pop": 342,   "munis": "Village of Cambridge, Town of Lake Mills (partial)"},
    "Edgerton":      {"pop": 492,   "munis": "Town of Koshkonong (partial), Town of Sumner (partial)"},
    "Fort Atkinson": {"pop": 18629, "munis": "City of Fort Atkinson, Towns of Hebron, Jefferson, Koshkonong, Oakland, Sumner (partial)"},
    "Ixonia":        {"pop": 5988,  "munis": "Village of Lac La Belle, Towns of Concord (partial), Ixonia, Watertown (partial)"},
    "Jefferson":     {"pop": 11192, "munis": "City of Jefferson, Towns of Aztalan, Farmington, Hebron, Jefferson, Oakland, Sullivan (partial)"},
    "Johnson Creek": {"pop": 5601,  "munis": "Village of Johnson Creek, Towns of Aztalan, Farmington, Milford, Watertown (partial)"},
    "Palmyra":       {"pop": 2957,  "munis": "Village of Palmyra, Town of Palmyra"},
    "Lake Mills":    {"pop": 11095, "munis": "City of Lake Mills, Towns of Aztalan, Lake Mills, Oakland (partial) — Ryan Brothers EMS"},
    "Waterloo":      {"pop": 4603,  "munis": "City of Waterloo, Towns of Milford (partial), Waterloo"},
    "Watertown":     {"pop": 16524, "munis": "City of Watertown, Towns of Milford (partial), Watertown (partial)"},
    "Western Lakes": {"pop": 4507,  "munis": "Village of Sullivan, Towns of Concord (partial), Palmyra (partial), Sullivan"},
    "Whitewater":    {"pop": 4925,  "munis": "City of Whitewater (Jeff Co. portion), Towns of Cold Spring, Koshkonong (partial)"},
}
_COUNTY_POP = 86855
_SVC_AREA_POP_TABLE = [
    {"Provider": p,
     "Municipalities": d["munis"],
     "Population": f"{d['pop']:,}",
     "Pct_County": f"{d['pop'] / _COUNTY_POP * 100:.1f}%"}
    for p, d in sorted(_SVC_AREA_POP_DATA.items(), key=lambda x: x[1]["pop"], reverse=True)
]

def _get_fig_svc_area_pop():
    """Horizontal bar chart of service area population by EMS provider."""
    providers = sorted(_SVC_AREA_POP_DATA.keys(), key=lambda p: _SVC_AREA_POP_DATA[p]["pop"])
    pops = [_SVC_AREA_POP_DATA[p]["pop"] for p in providers]
    fig = go.Figure(go.Bar(
        y=providers, x=pops, orientation="h",
        marker_color=C_PRIMARY,
        text=[f"{p:,}" for p in pops],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Population: %{x:,}<extra></extra>",
    ))
    fig.update_layout(
        title="EMS Service Area Population by Provider — WI DOA 2025<br>"
              "<sup>Jefferson County only (86,855 total) · Some towns split between providers</sup>",
        xaxis_title="Service Area Population",
    )
    _apply_chart_style(fig, height=450, title_has_subtitle=True)
    fig.update_layout(
        margin=dict(l=120, r=80, t=70, b=30),
        yaxis=dict(tickfont=dict(size=12, color=C_TEXT)),
    )
    return fig

# ── External benchmarks (for reference lines on charts) ──────────────────────
# Sources documented inline; all confirmed from published reports.
_BENCH = {
    "wi_calls_per_1k":       254,     # WI statewide transports/1K pop (Northwestern EMS / DHS WARDS)
    "wi_ems_fee_per_capita":  36,     # WI average EMS user fee per capita (Northwestern EMS)
    "natl_cost_per_transport": 3127,  # CMS GADCS 2024 — mean govt cost per transport
    "natl_reimburse_per_transport": 1147,  # CMS GADCS 2024 — mean reimbursement per transport
    "nfpa_1710_als_min":      8,      # NFPA 1710 ALS arrival target (career depts, 90th pctl)
    "nfpa_1710_bls_min":      4,      # NFPA 1710 BLS/first-responder target
    "nfpa_1720_rural_min":   14,      # NFPA 1720 rural (vol depts, 80th pctl)
    "nfpa_1720_suburban_min": 10,     # NFPA 1720 suburban (vol depts, 80th pctl)
    "fa_actual_collected":   666,     # Fort Atkinson avg transport fee received (Peterson projection)
    "jeff_county_pop":       86855,   # WI DOA Preliminary 2025 Estimate (Emergency Services Population xlsx)
}
_BENCH_SOURCES = [
    ("Northwestern EMS — EMS in Wisconsin", "https://northwesternems.org/ems-in-wisconsin"),
    ("CMS GADCS Report (Dec 2024)", "https://www.cms.gov/files/document/medicare-ground-ambulance-data-collection-system-gadcs-report-year-1-and-year-2-cohort-analysis.pdf"),
    ("NFPA 1710 Standard (Career)", "https://www.emergent.tech/blog/nfpa-1710-response-times"),
    ("NFPA 1720 Standard (Volunteer)", "https://www.firehouse.com/careers-education/article/21238058/nfpa-standards-nfpa-1720-an-update-on-the-volunteer-deployment-standard"),
]

# ── 3b. MABAS Division 118 — Municipal Asset Inventory ──────────────────────
# Source: MABAS_Assets/*.xlsx (14 MABAS Division 118 FD Resource Lists)
# Each row = one department's apparatus fleet from their official MABAS filing.
# Ambulance detail includes unit ID, year, make/chassis, and body manufacturer.
ASSET_DATA = pd.DataFrame([
    {"Municipality": "Cambridge",     "Engines": 3, "Trucks_Ladders": 0, "Squads_Rescues": 1, "Tenders": 1, "Brush_ATV": 4, "Boats": 1, "Ambulances": 0,
     "Ambulance_Detail": "N/A — no EMS provider",
     "EMS_Personnel": 0, "Paramedics": 0, "AEMTs": 0, "EMTs": 0, "EMRs": 0,
     "Source_File": "Cambridge MABAS DIV 118 FD Resource List.xlsx"},
    {"Municipality": "Edgerton",     "Engines": 0, "Trucks_Ladders": 0, "Squads_Rescues": 0, "Tenders": 0, "Brush_ATV": 0, "Boats": 0, "Ambulances": 1,
     "Ambulance_Detail": "1 unit est. Jefferson-stationed (Koshkonong/Sumner area) — pending Peterson/Wegner callaround 2026-04-21. Full district fleet based in Milton (Rock Co.)",
     "EMS_Personnel": 0, "Paramedics": 0, "AEMTs": 0, "EMTs": 0, "EMRs": 0,
     "Source_File": "Edgerton (Lakeside FPD) — MABAS data not filed; estimate per 2026-04-20 assumption"},
    {"Municipality": "Fort Atkinson", "Engines": 3, "Trucks_Ladders": 1, "Squads_Rescues": 2, "Tenders": 2, "Brush_ATV": 2, "Boats": 2, "Ambulances": 3,
     "Ambulance_Detail": "Medic 8158 (2023 Ford/Lifeline ALS) | Rescue 8159 (2017 Ford/LSV) | Rescue 8157 (2004 Chevy/EDM BLS)",
     "EMS_Personnel": 30, "Paramedics": 9, "AEMTs": 6, "EMTs": 15, "EMRs": 0,
     "Source_File": "Fort Atkinson MABAS DIV 118 FD Resource List 2020.xlsx"},
    {"Municipality": "Helenville",    "Engines": 2, "Trucks_Ladders": 0, "Squads_Rescues": 1, "Tenders": 2, "Brush_ATV": 1, "Boats": 0, "Ambulances": 0,
     "Ambulance_Detail": "N/A — served by Jefferson EMS",
     "EMS_Personnel": 13, "Paramedics": 0, "AEMTs": 0, "EMTs": 4, "EMRs": 9,
     "Source_File": "Helenville MABAS DIV 118 FD Resource List (5-18-16).xlsx"},
    {"Municipality": "Ixonia",        "Engines": 2, "Trucks_Ladders": 0, "Squads_Rescues": 0, "Tenders": 2, "Brush_ATV": 2, "Boats": 0, "Ambulances": 1,
     "Ambulance_Detail": "Unit 8351 (2012 Ford F-550/Lifeline)",
     "EMS_Personnel": 14, "Paramedics": 5, "AEMTs": 5, "EMTs": 0, "EMRs": 4,
     "Source_File": "Ixonia Resource List 2020.xlsx"},
    {"Municipality": "Jefferson",     "Engines": 3, "Trucks_Ladders": 1, "Squads_Rescues": 1, "Tenders": 2, "Brush_ATV": 2, "Boats": 2, "Ambulances": 3,
     "Ambulance_Detail": "Rescue 754 (2021 Ford/Horton ALS) | Rescue 755 (2014 Ford/Horton) | Rescue 756 (2007 Ford/Horton) | Note: Intercept 799 + Backup 798 are ALS SUVs (paramedic intercept, not transport units)",
     "EMS_Personnel": 39, "Paramedics": 13, "AEMTs": 11, "EMTs": 15, "EMRs": 0,
     "Source_File": "Jefferson MABAS DIV 118 FD Resource List 2024.xlsx"},
    {"Municipality": "Johnson Creek", "Engines": 2, "Trucks_Ladders": 1, "Squads_Rescues": 1, "Tenders": 2, "Brush_ATV": 2, "Boats": 0, "Ambulances": 2,
     "Ambulance_Detail": "Units 703, 704 (details not filed in MABAS sheet)",
     "EMS_Personnel": 0, "Paramedics": 0, "AEMTs": 0, "EMTs": 0, "EMRs": 0,
     "Source_File": "Johnson Creek MABAS DIV 118 FD Resource List (Autosaved) 2016.xlsx"},
    {"Municipality": "Lake Mills",    "Engines": 3, "Trucks_Ladders": 1, "Squads_Rescues": 1, "Tenders": 1, "Brush_ATV": 1, "Boats": 2, "Ambulances": 0,
     "Ambulance_Detail": "No LMFD ambulances — Ryan Brothers EMS provides ALS transport under contract",
     "EMS_Personnel": 19, "Paramedics": 1, "AEMTs": 2, "EMTs": 12, "EMRs": 4,
     "Source_File": "Lake Mills 2020 MABAS INFO.xlsx"},
    {"Municipality": "Palmyra",       "Engines": 1, "Trucks_Ladders": 1, "Squads_Rescues": 0, "Tenders": 1, "Brush_ATV": 1, "Boats": 0, "Ambulances": 1,
     "Ambulance_Detail": "Rescue 717 (year/make not filed)",
     "EMS_Personnel": 16, "Paramedics": 1, "AEMTs": 5, "EMTs": 9, "EMRs": 1,
     "Source_File": "Palmyra Equipment List.xlsx"},
    {"Municipality": "Waterloo",      "Engines": 2, "Trucks_Ladders": 1, "Squads_Rescues": 0, "Tenders": 2, "Brush_ATV": 3, "Boats": 0, "Ambulances": 2,
     "Ambulance_Detail": "Rescue 3959 (2005 Freightliner/MedTech) | Rescue 3958 (2014 Freightliner/Horton)",
     "EMS_Personnel": 27, "Paramedics": 0, "AEMTs": 13, "EMTs": 10, "EMRs": 2,
     "Source_File": "Waterloo Fire & Rescue MABAS DIV 118.xlsx"},
    {"Municipality": "Watertown",     "Engines": 3, "Trucks_Ladders": 1, "Squads_Rescues": 0, "Tenders": 2, "Brush_ATV": 1, "Boats": 1, "Ambulances": 3,
     "Ambulance_Detail": "MED 54 (2023 Ford/Lifeline) | Med 52 (2006 International) | Med 53 (2014 Ford F450)",
     "EMS_Personnel": 29, "Paramedics": 22, "AEMTs": 1, "EMTs": 6, "EMRs": 0,
     "Source_File": "Watertown MABAS DIV 118 FD Resource List.xlsx"},
    {"Municipality": "Western Lakes", "Engines": 0, "Trucks_Ladders": 0, "Squads_Rescues": 0, "Tenders": 0, "Brush_ATV": 0, "Boats": 0, "Ambulances": 2,
     "Ambulance_Detail": "2 units est. Jefferson-stationed (Sullivan/Concord area) — pending Peterson/Wegner callaround 2026-04-21. Full district fleet larger (HQ in Oconomowoc, Waukesha Co.)",
     "EMS_Personnel": 0, "Paramedics": 0, "AEMTs": 0, "EMTs": 0, "EMRs": 0,
     "Source_File": "Western Lakes MABAS DIV 118 FD Resource List.xlsx"},
    {"Municipality": "Whitewater",    "Engines": 3, "Trucks_Ladders": 1, "Squads_Rescues": 1, "Tenders": 2, "Brush_ATV": 2, "Boats": 0, "Ambulances": 1,
     "Ambulance_Detail": "4 total ambulances but assumption: 1 serves Jefferson Co. contracts (Koshkonong/Cold Spring); remaining 3 based in Walworth Co.",
     "EMS_Personnel": 50, "Paramedics": 0, "AEMTs": 30, "EMTs": 20, "EMRs": 0,
     "Source_File": "Whitewater MABAS DIV 118 FD Resource List-WW.xlsx"},
])

# Ambulance detail records (individual units with year data for age analysis)
# Only includes units where year is known from the MABAS filings.
AMBULANCE_DETAIL = pd.DataFrame([
    {"Municipality": "Fort Atkinson", "Unit": "Medic 8158",  "Year": 2023, "Chassis": "Ford",          "Body": "Lifeline",  "Level": "ALS"},
    {"Municipality": "Fort Atkinson", "Unit": "Rescue 8159", "Year": 2017, "Chassis": "Ford",          "Body": "LSV",       "Level": "ALS"},
    {"Municipality": "Fort Atkinson", "Unit": "Rescue 8157", "Year": 2004, "Chassis": "Chevrolet",     "Body": "EDM",       "Level": "BLS"},
    {"Municipality": "Ixonia",        "Unit": "Unit 8351",   "Year": 2012, "Chassis": "Ford F-550",    "Body": "Lifeline",  "Level": "BLS"},
    {"Municipality": "Jefferson",     "Unit": "Rescue 754",  "Year": 2021, "Chassis": "Ford",          "Body": "Horton",    "Level": "ALS"},
    {"Municipality": "Jefferson",     "Unit": "Rescue 755",  "Year": 2014, "Chassis": "Ford",          "Body": "Horton",    "Level": "AEMT"},
    {"Municipality": "Jefferson",     "Unit": "Rescue 756",  "Year": 2007, "Chassis": "Ford E-350",    "Body": "Horton",    "Level": "BLS"},
    # Intercept 799 (2019 Ford) and Backup 798 (2009 Ford Explorer) are ALS paramedic intercept SUVs
    # — not transport ambulances; excluded from ambulance count per 2026-04-20 correction
    {"Municipality": "Waterloo",      "Unit": "Rescue 3959", "Year": 2005, "Chassis": "Freightliner",  "Body": "MedTech",   "Level": "AEMT"},
    {"Municipality": "Waterloo",      "Unit": "Rescue 3958", "Year": 2014, "Chassis": "Freightliner",  "Body": "Horton",    "Level": "AEMT"},
    {"Municipality": "Watertown",     "Unit": "MED 54",      "Year": 2023, "Chassis": "Ford F350",     "Body": "Lifeline",  "Level": "ALS"},
    {"Municipality": "Watertown",     "Unit": "Med 52",      "Year": 2006, "Chassis": "International", "Body": "N/A",       "Level": "ALS"},
    {"Municipality": "Watertown",     "Unit": "Med 53",      "Year": 2014, "Chassis": "Ford F450",     "Body": "N/A",       "Level": "ALS"},
])
AMBULANCE_DETAIL["Age"] = 2025 - AMBULANCE_DETAIL["Year"]

# ── 4. EMS district → Census subdivision mapping (matches reference district map) ─
# Each dept is assigned the Census subdivisions that fall within its service area.
# Sources: reference district map image + county EMS contract data.
# NAMELSAD used to distinguish city/town/village with same NAME.
DEPT_TO_NAMELSAD = {
    # NW quadrant
    "Waterloo":      ["Waterloo city", "Waterloo town"],
    # N central — Johnson Creek covers Milford/Farmington/Aztalan corridor
    "Johnson Creek": ["Johnson Creek village", "Aztalan town", "Farmington town", "Milford town"],
    # NE — Ixonia + Lac La Belle
    "Ixonia":        ["Ixonia town", "Lac La Belle village"],
    # Far north — Watertown covers city + town
    "Watertown":     ["Watertown city", "Watertown town"],
    # W — Lake Mills area (Ryan Brothers/Lake Mills EMS — no call file, shown grey)
    "Lake Mills":    ["Lake Mills city", "Lake Mills town"],
    # Cambridge extends slightly W across county line; Cambridge village is in Jefferson Co.
    "Cambridge":     ["Cambridge village"],
    # Central — Jefferson EMS covers Jefferson city + town + Hebron
    "Jefferson":     ["Jefferson city", "Jefferson town", "Hebron town"],
    # E central — Western Lakes covers Oakland + Concord + Palmyra town
    # Sullivan town + village are fire-only served by Sullivan VFD; EMS by Western Lakes.
    "Western Lakes": ["Oakland town", "Concord town", "Sullivan town", "Sullivan village"],
    # Fort Atkinson covers city + Koshkonong town + Sumner town (shared w/ Edgerton, larger pop share per DOA)
    "Fort Atkinson": ["Fort Atkinson city", "Koshkonong town", "Sumner town"],
    # SW — Whitewater city + Cold Spring town (formerly Rome VFD area, fire-only; EMS by Whitewater per DOA)
    "Whitewater":    ["Whitewater city", "Cold Spring town"],
    # Palmyra village + town (SE)
    "Palmyra":       ["Palmyra village", "Palmyra town"],
    # Edgerton (Lakeside) — primarily SE, Albion is in Dane Co so we use no polygon;
    # assign no cousub (they appear grey — district crosses county line)
    "Edgerton":      [],
    # Helenville — very small district, no dedicated cousub in Jefferson Co.
    "Helenville":    [],
}

# ── 5. GeoJSON + data enrichment ──────────────────────────────────────────────
with open(GEOJSON) as f:
    geojson_data = json.load(f)

# Additional map layers (ArcGIS Public Safety, downloaded Mar 2 2026)
with open(GEOJSON_EMS) as f:
    geojson_ems_districts = json.load(f)
with open(GEOJSON_FIRE) as f:
    geojson_fire_districts = json.load(f)
with open(GEOJSON_STATIONS) as f:
    geojson_stations = json.load(f)
with open(GEOJSON_HELEN) as f:
    geojson_helenville = json.load(f)
with open(GEOJSON_ZCTA) as f:
    geojson_zcta = json.load(f)

kpi_lookup = muni_kpi.set_index("Municipality").to_dict("index")
rt_lookup  = rt_pct.set_index("Municipality").to_dict("index")

# ── Edgerton alias: Excel sheet uses "Edgerton (Lakeside)" but budget/NAMELSAD use "Edgerton"
# Add both keys so lookups work regardless of which name is used.
if "Edgerton (Lakeside)" in kpi_lookup and "Edgerton" not in kpi_lookup:
    kpi_lookup["Edgerton"] = kpi_lookup["Edgerton (Lakeside)"]
if "Edgerton (Lakeside)" in rt_lookup and "Edgerton" not in rt_lookup:
    rt_lookup["Edgerton"] = rt_lookup["Edgerton (Lakeside)"]

# Build reverse map: NAMELSAD → dept
namelsad_to_dept = {}
for dept, namelsads in DEPT_TO_NAMELSAD.items():
    for n in namelsads:
        namelsad_to_dept[n] = dept

budget_lookup  = budget.set_index("Municipality").to_dict("index")
billing_lookup = billing.set_index("Municipality").to_dict("index")
asset_lookup   = ASSET_DATA.set_index("Municipality").to_dict("index")

for feat in geojson_data["features"]:
    p        = feat["properties"]
    namelsad = p.get("NAMELSAD", p["NAME"])
    dept     = namelsad_to_dept.get(namelsad, p["NAME"])
    kpi      = kpi_lookup.get(dept, {})
    rtp      = rt_lookup.get(dept, {})
    bud      = budget_lookup.get(dept, {})
    bil      = billing_lookup.get(dept, {})
    p["dept"]        = dept
    p["total_calls"] = kpi.get("Total Calls", "N/A")
    p["ems_calls"]   = kpi.get("EMS Calls (Cat 3)", "N/A")
    p["median_rt"]   = kpi.get("Median Response Time (min)", "N/A")
    p["ems_rt"]      = kpi.get("Median EMS Response Time (min)", "N/A")
    p["p90_rt"]      = rtp.get("P90", "N/A")
    p["p75_rt"]      = rtp.get("P75", "N/A")
    p["staffing"]    = bud.get("Model", "N/A")
    p["staff_ft"]    = bud.get("Staff_FT", "N/A")
    p["budget_exp"]  = f"${bud['Total_Expense']:,.0f}" if bud.get("Total_Expense") else "N/A"
    p["ems_revenue"] = f"${bud['EMS_Revenue']:,.0f}" if bud.get("EMS_Revenue") is not None and bud.get("EMS_Revenue") == bud.get("EMS_Revenue") else "N/A"
    p["bls_rate"]    = f"${bil['BLS']:,}" if bil.get("BLS") else "N/A"
    p["als1_rate"]   = f"${bil['ALS1']:,}" if bil.get("ALS1") else "N/A"
    _a = asset_lookup.get(dept, {})
    p["ambulances"]    = _a.get("Ambulances", 0) or 0
    p["ems_personnel"] = _a.get("EMS_Personnel", 0) or 0
    p["service_level"] = ALS_LEVELS.get(dept, {}).get("Level", "N/A")

# ── 5a-2. Enrich EMS district GeoJSON with dept names for choropleth coloring ──
_EMS_LABEL_TO_DEPT = {
    "Ixonia EMS": "Ixonia", "Watertown EMS": "Watertown", "Whitewater EMS": "Whitewater",
    "Western Lakes": "Western Lakes", "Palmyra EMS": "Palmyra",
    "Ryan Brothers EMS": "Lake Mills", "Waterloo EMS": "Waterloo",
    "Fort Atkinson EMS": "Fort Atkinson", "Edgerton EMS": "Edgerton",
    "Johnson Creek EMS": "Johnson Creek", "Jefferson EMS": "Jefferson",
    "Cambridge EMS": "Cambridge",
}
for feat in geojson_ems_districts["features"]:
    label = feat["properties"].get("MAPLABEL", "")
    feat["properties"]["dept"] = _EMS_LABEL_TO_DEPT.get(label, label)

# Precompute bounding boxes per department (for click-to-zoom & zoom-to-fit)
DEPT_BOUNDS = {}  # {dept_name: [[south, west], [north, east]]}
for _feat in geojson_data["features"]:
    _dept = _feat["properties"].get("dept", _feat["properties"]["NAME"])
    _coords = []
    _geom = _feat["geometry"]
    if _geom["type"] == "Polygon":
        for ring in _geom["coordinates"]:
            _coords.extend(ring)
    elif _geom["type"] == "MultiPolygon":
        for poly in _geom["coordinates"]:
            for ring in poly:
                _coords.extend(ring)
    if not _coords:
        continue
    lons = [c[0] for c in _coords]
    lats = [c[1] for c in _coords]
    _sw = [min(lats), min(lons)]
    _ne = [max(lats), max(lons)]
    if _dept in DEPT_BOUNDS:
        old_sw, old_ne = DEPT_BOUNDS[_dept]
        DEPT_BOUNDS[_dept] = [
            [min(old_sw[0], _sw[0]), min(old_sw[1], _sw[1])],
            [max(old_ne[0], _ne[0]), max(old_ne[1], _ne[1])],
        ]
    else:
        DEPT_BOUNDS[_dept] = [_sw, _ne]

_ALL_SW = [min(b[0][0] for b in DEPT_BOUNDS.values()), min(b[0][1] for b in DEPT_BOUNDS.values())]
_ALL_NE = [max(b[1][0] for b in DEPT_BOUNDS.values()), max(b[1][1] for b in DEPT_BOUNDS.values())]
COUNTY_BOUNDS = [_ALL_SW, _ALL_NE]

# ── 5b. Station / service-area coordinates for map markers ────────────────────
# Geocoded from actual fire station addresses (Nominatim OSM, verified 2025-03).
# Western Lakes HQ is in Waukesha Co; uses JeffCo service-area centroid instead.
STATION_COORDS = {
    "Cambridge":     (43.0038, -89.0177),
    "Edgerton":      (42.8335, -89.0694),
    "Fort Atkinson": (42.9271, -88.8399),
    "Helenville":    (43.0119, -88.6995),
    "Ixonia":        (43.1449, -88.6003),
    "Jefferson":     (43.0026, -88.8075),
    "Johnson Creek": (43.0819, -88.7759),
    "Lake Mills":    (43.0783, -88.9113),
    "Palmyra":       (42.8778, -88.5862),
    "Waterloo":      (43.1815, -88.9904),
    "Watertown":     (43.1959, -88.7235),
    "Western Lakes": (43.0295, -88.5968),
    "Whitewater":    (42.8321, -88.7333),
}
dept_centroids = STATION_COORDS  # alias for any downstream references

# Fixup: depts without GeoJSON polygons get a small box around their station
for _d, (_lat, _lon) in STATION_COORDS.items():
    if _d not in DEPT_BOUNDS:
        DEPT_BOUNDS[_d] = [[_lat - 0.04, _lon - 0.05], [_lat + 0.04, _lon + 0.05]]

# ── 5c. ZIP and City coordinate lookups + aggregation for zoom tiers ─────────

# Census 2020 ZCTA internal-point coordinates (52 ZIPs in Jefferson County area)
ZIP_COORDS = {
    "53003": (43.2123, -88.5196), "53016": (43.3111, -88.7177),
    "53018": (43.0478, -88.386),  "53027": (43.3163, -88.3711),
    "53029": (43.1466, -88.341),  "53036": (43.1797, -88.575),
    "53038": (43.0846, -88.791),  "53039": (43.3698, -88.7095),
    "53047": (43.2605, -88.6287), "53058": (43.1126, -88.4119),
    "53059": (43.2885, -88.525),  "53066": (43.1146, -88.4887),
    "53069": (43.1136, -88.4317), "53072": (43.08, -88.2666),
    "53078": (43.3179, -88.4695), "53089": (43.1455, -88.2383),
    "53094": (43.144, -88.732),   "53098": (43.2537, -88.7106),
    "53103": (42.8805, -88.2173), "53114": (42.6094, -88.7459),
    "53115": (42.6566, -88.6683), "53118": (42.9625, -88.4915),
    "53119": (42.8931, -88.4856), "53121": (42.7197, -88.5343),
    "53137": (43.0079, -88.6691), "53147": (42.5582, -88.4519),
    "53149": (42.8775, -88.3423), "53153": (42.9409, -88.4021),
    "53156": (42.8899, -88.5888), "53178": (43.0295, -88.5968),
    "53189": (42.9441, -88.291),  "53190": (42.8078, -88.7362),
    "53505": (42.6611, -88.8209), "53511": (42.5464, -89.1067),
    "53523": (42.9844, -89.0288), "53525": (42.544, -88.8466),
    "53531": (43.0624, -89.0884), "53534": (42.8608, -89.0933),
    "53536": (42.7612, -89.2679), "53538": (42.9089, -88.8716),
    "53545": (42.7387, -89.0402), "53546": (42.6522, -88.9482),
    "53548": (42.6893, -89.1313), "53549": (42.9845, -88.7656),
    "53551": (43.0795, -88.9161), "53559": (43.166, -89.0816),
    "53563": (42.781, -88.9335),  "53579": (43.296, -88.8677),
    "53589": (42.9248, -89.2059), "53594": (43.1833, -88.9712),
    "53916": (43.456, -88.8485),  "53925": (43.3267, -89.0571),
}

CITY_COORDS = {
    "Oconomowoc": (43.1117, -88.4993), "Watertown": (43.1943, -88.7242),
    "Fort Atkinson": (42.9289, -88.8371), "Whitewater": (42.8340, -88.7307),
    "Summit": (43.0623, -88.4704), "Milton": (42.7754, -88.9390),
    "Edgerton": (42.8335, -89.0694), "Dousman": (43.0147, -88.4728),
    "Johnson Creek": (43.0759, -88.7748), "Waterloo": (43.1839, -88.9884),
    "Ottawa": (42.9761, -88.4498), "Jefferson": (43.0056, -88.8073),
    "Merton": (43.1542, -88.3695), "Sullivan": (43.0131, -88.5882),
    "Ixonia": (43.1631, -88.5966), "Fulton": (42.8081, -89.1275),
    "Ashippun": (43.2244, -88.4774), "Concord": (43.0694, -88.5987),
    "Albion": (42.8803, -89.0692), "Cambridge": (43.0038, -89.0177),
    "Palmyra": (42.8778, -88.5862), "Delavan": (42.6331, -88.6461),
    "Oakland": (42.9799, -88.9535), "Janesville": (42.6830, -89.0227),
    "Christiana": (42.9799, -89.0718), "Hartford": (43.3177, -88.3789),
    "Portland": (43.2385, -88.9498), "Lake Mills": (43.0798, -88.9126),
    "Lebanon": (43.2400, -88.5959), "Helenville": (43.0168, -88.6991),
    "Okauchee": (43.1138, -88.4347), "Beloit": (42.5084, -89.0318),
    "Busseyville": (42.9500, -88.7500), "Newville": (42.9600, -88.6200),
}

# Normalize raw city names to canonical short names for aggregation
_CITY_NORM = {
    "Oconomowoc - City": "Oconomowoc", "Oconomowoc - Town": "Oconomowoc",
    "Summit - Village": "Summit", "City of Milton": "Milton",
    "City of Edgerton": "Edgerton", "Dousman - Village": "Dousman",
    "Village of Johnson C": "Johnson Creek", "City of Waterloo": "Waterloo",
    "Ottawa - Town": "Ottawa", "Merton - Town": "Merton",
    "Ashippun - Town": "Ashippun", "Village of Cambridge": "Cambridge",
    "City of Janesville": "Janesville", "Town of Oakland": "Oakland",
    "Town of Christiana": "Christiana", "City of Jefferson": "Jefferson",
    "Village of Palmyra": "Palmyra", "City of Watertown": "Watertown",
    "City of Beloit": "Beloit", "Sullivan - Town": "Sullivan",
    "City of Lake Mills": "Lake Mills", "Village of Marshall": "Marshall",
}

# Build derived columns for zoom tiers
if "Incident Zip Code" in raw.columns:
    raw["ZIP"] = raw["Incident Zip Code"].astype(str).str[:5]
else:
    raw["ZIP"] = "Unknown"
if "Incident City" in raw.columns:
    raw["CityNorm"] = raw["Incident City"].map(_CITY_NORM).fillna(raw["Incident City"])
else:
    raw["CityNorm"] = "Unknown"

# Aggregate by ZIP (dominant department per ZIP)
_zip_agg = (raw.groupby(["ZIP", "Department"])
    .agg(total_calls=("RT", "size"),
         ems_calls=("IsEMS", "sum"),
         median_rt=("RT", "median"))
    .reset_index())
_zip_agg = _zip_agg.sort_values("total_calls", ascending=False).drop_duplicates("ZIP", keep="first")
ZIP_DATA = []
for _, r in _zip_agg.iterrows():
    z = r["ZIP"]
    if z in ZIP_COORDS and r["total_calls"] >= 3:
        lat, lon = ZIP_COORDS[z]
        ZIP_DATA.append({
            "zip": z, "dept": r["Department"], "lat": lat, "lon": lon,
            "total_calls": int(r["total_calls"]), "ems_calls": int(r["ems_calls"]),
            "median_rt": round(r["median_rt"], 1) if pd.notna(r["median_rt"]) else "N/A",
        })

# Aggregate by City (dominant department per city)
_city_agg = (raw.groupby(["CityNorm", "Department"])
    .agg(total_calls=("RT", "size"),
         ems_calls=("IsEMS", "sum"),
         median_rt=("RT", "median"))
    .reset_index())
_city_agg = _city_agg.sort_values("total_calls", ascending=False).drop_duplicates("CityNorm", keep="first")
CITY_DATA = []
for _, r in _city_agg.iterrows():
    c = r["CityNorm"]
    if c in CITY_COORDS and r["total_calls"] >= 10:
        lat, lon = CITY_COORDS[c]
        CITY_DATA.append({
            "city": c, "dept": r["Department"], "lat": lat, "lon": lon,
            "total_calls": int(r["total_calls"]), "ems_calls": int(r["ems_calls"]),
            "median_rt": round(r["median_rt"], 1) if pd.notna(r["median_rt"]) else "N/A",
        })

_max_city_calls = max((d["total_calls"] for d in CITY_DATA), default=1)
_max_zip_calls = max((d["total_calls"] for d in ZIP_DATA), default=1)
print(f"  Zoom tiers: {len(CITY_DATA)} cities, {len(ZIP_DATA)} ZIPs")

# ── 6. dash-leaflet map helpers ──────────────────────────────────────────────

METRIC_META = {
    "total_calls":   {"label": "Total Calls",    "key": "Total Calls"},
    "ems_calls":     {"label": "EMS Calls",       "key": "EMS Calls (Cat 3)"},
    "median_rt":     {"label": "Median RT (min)", "key": "Median Response Time (min)"},
    "p90_rt":        {"label": "P90 RT (min)",    "key": "P90"},
    "ambulances":    {"label": "Ambulances",      "key": "Ambulances"},
    "ems_personnel": {"label": "EMS Personnel",   "key": "EMS_Personnel"},
}

# Call-volume range for circle scaling
_all_calls = {d: kpi_lookup.get(d, {}).get("Total Calls", 0) or 0 for d in STATION_COORDS}
_max_calls = max(_all_calls.values()) if _all_calls else 1

# Asset ranges for choropleth scaling
_all_amb  = {d: asset_lookup.get(d, {}).get("Ambulances", 0) or 0 for d in STATION_COORDS}
_max_amb  = max(_all_amb.values()) if _all_amb else 1
_all_pers = {d: asset_lookup.get(d, {}).get("EMS_Personnel", 0) or 0 for d in STATION_COORDS}
_max_pers = max(_all_pers.values()) if _all_pers else 1

_MIN_MARKER_PX = 6
_MAX_MARKER_PX = 28

def _marker_radius(total_calls):
    """Pixel-based radius (6-28px) proportional to sqrt(call volume)."""
    if not total_calls or total_calls == "N/A":
        return _MIN_MARKER_PX
    return _MIN_MARKER_PX + (_MAX_MARKER_PX - _MIN_MARKER_PX) * math.sqrt(float(total_calls) / _max_calls)

def _bubble_color_calls(val):
    """Blue gradient for call-volume metrics."""
    try:
        t = min(1.0, float(val) / _max_calls)
        r = int(198 + (8 - 198) * t)
        g = int(219 + (48 - 219) * t)
        b = int(239 + (107 - 239) * t)
        return f"rgb({r},{g},{b})"
    except (TypeError, ValueError):
        return "#aaaaaa"

def _bubble_color_rt(val):
    """Green-to-red gradient for response-time metrics."""
    try:
        t = min(1.0, float(val) / 15.0)
        r = int(33 + (215 - 33) * t)
        g = int(153 + (48 - 153) * t)
        b = int(33 + (39 - 33) * t)
        return f"rgb({r},{g},{b})"
    except (TypeError, ValueError):
        return "#aaaaaa"

def _bubble_color_asset(val, max_val):
    """Purple gradient for asset/personnel metrics (light→dark)."""
    try:
        t = min(1.0, float(val) / max_val) if max_val > 0 else 0
        r = int(209 + (88 - 209) * t)
        g = int(196 + (28 - 196) * t)
        b = int(233 + (135 - 233) * t)
        return f"rgb({r},{g},{b})"
    except (TypeError, ValueError):
        return "#aaaaaa"

def _choropleth_color(dept, metric):
    """Return hex fill color for a GeoJSON polygon given the active metric."""
    kpi = kpi_lookup.get(dept, {})
    rtp = rt_lookup.get(dept, {})
    ast = asset_lookup.get(dept, {})
    if metric in ("total_calls", "ems_calls"):
        val = kpi.get(METRIC_META[metric]["key"], 0) or 0
        return _bubble_color_calls(val)
    elif metric in ("median_rt", "p90_rt"):
        val = kpi.get("Median Response Time (min)", 0) if metric == "median_rt" else rtp.get("P90", 0)
        val = val or 0
        return _bubble_color_rt(val)
    elif metric == "ambulances":
        val = ast.get("Ambulances", 0) or 0
        return _bubble_color_asset(val, _max_amb)
    elif metric == "ems_personnel":
        val = ast.get("EMS_Personnel", 0) or 0
        return _bubble_color_asset(val, _max_pers)
    else:
        return "#aaaaaa"

def _compute_color_map(metric):
    """Return {dept_name: color_string} for all departments."""
    return {d: _choropleth_color(d, metric) for d in STATION_COORDS}

# JavaScript style function for Census subdivision GeoJSON — invisible by default,
# toggle-able via "Municipal Boundaries" checkbox (showMuniBorders in hideout)
_geojson_style = assign("""function(feature, context) {
    var showBorders = context.hideout.showMuniBorders || false;
    return {
        fillColor: 'transparent',
        color: showBorders ? '#334155' : 'transparent',
        weight: showBorders ? 1.5 : 0,
        fillOpacity: 0,
    };
}""")

# EMS district choropleth — the PRIMARY colored map layer.
# Reads hideout.colorMap keyed by dept name to fill each EMS district polygon.
_ems_district_style = assign("""function(feature, context) {
    var dept = feature.properties.dept || '';
    var cm = (context.hideout || {}).colorMap || {};
    return {
        fillColor: cm[dept] || '#CBD5E1',
        color: '#00838F',
        weight: 2.5,
        fillOpacity: 0.45,
    };
}""")
_ems_district_label = assign("""function(feature, layer) {
    var name = feature.properties.MAPLABEL || '';
    if (name) {
        layer.bindTooltip('<b>' + name + '</b>', {
            sticky: true, direction: 'top', opacity: 0.92
        });
    }
}""")
# Fire districts differ from EMS districts — shown for reference only
_fire_district_style = assign("""function(feature) {
    return {fillColor: '#FF5722', color: '#E64A19', weight: 1.5, fillOpacity: 0.10, dashArray: '4 3'};
}""")
_helenville_style = assign("""function(feature) {
    return {fillColor: '#FFEB3B', color: '#FBC02D', weight: 2, fillOpacity: 0.22, dashArray: '4 3'};
}""")
_zcta_style_static = assign("""function(feature) {
    return {fillColor: '#9C27B0', color: '#7B1FA2', weight: 1.5, fillOpacity: 0.10, dashArray: '5 3'};
}""")
_zcta_label = assign("""function(feature, layer) {
    var z = feature.properties.ZCTA5 || '';
    if (z) {
        layer.bindTooltip(z, {permanent: true, direction: 'center',
            className: 'zcta-label',
            offset: [0, 0]});
    }
}""")
# Dynamic ZCTA style: reads hideout.zipColorMap for metric-driven fill colors
_zcta_style_dynamic = assign("""function(feature, context) {
    var z = feature.properties.ZCTA5 || '';
    var cm = (context.hideout || {}).zipColorMap || {};
    var c = cm[z];
    if (c) {
        return {fillColor: c, color: 'rgba(71,21,110,0.65)', weight: 1, fillOpacity: 0.30, dashArray: ''};
    }
    return {fillColor: 'transparent', color: 'rgba(71,21,110,0.30)', weight: 0.5, fillOpacity: 0, dashArray: '4 3'};
}""")
# Dynamic ZCTA tooltip: only shown for ZIPs with data, kept minimal
_zcta_label_dynamic = assign("""function(feature, layer) {
    var p = feature.properties;
    var z = p.ZCTA5 || '';
    var calls = p._calls || 0;
    if (calls > 0) {
        var tip = '<b>' + z + '</b> &mdash; ' + calls + ' calls, ' + p._rt + ' min RT';
        layer.bindTooltip(tip, {sticky: true, direction: 'top', opacity: 0.92});
    }
}""")

def _build_zcta_data_geojson(zip_data_list, selected_depts):
    """Inject call data into ZCTA GeoJSON feature properties for client-side tooltips."""
    enriched = copy.deepcopy(geojson_zcta)
    # Build lookup: zip -> data dict
    zip_lookup = {}
    for zd in zip_data_list:
        if zd["dept"] in selected_depts:
            zip_lookup[zd["zip"]] = zd
    for feat in enriched["features"]:
        z = feat["properties"].get("ZCTA5", "")
        d = zip_lookup.get(z, {})
        feat["properties"]["_calls"] = d.get("total_calls", 0)
        feat["properties"]["_ems"] = d.get("ems_calls", 0)
        feat["properties"]["_rt"] = d.get("median_rt", "N/A")
        feat["properties"]["_dept"] = d.get("dept", "")
    return enriched

def _compute_zip_color_map(metric, zip_data_list, selected_depts):
    """Return {zip_code: color_string} for all ZIPs with data."""
    is_rt = "rt" in metric
    is_asset = metric in ("ambulances", "ems_personnel")
    filtered = [z for z in zip_data_list if z["dept"] in selected_depts and z["total_calls"] >= 3]
    if not filtered:
        return {}
    local_max = max(z["total_calls"] for z in filtered)
    result = {}
    for zd in filtered:
        z = zd["zip"]
        if is_asset:
            # Color ZIP boundaries by the parent department's asset value
            ast_d = asset_lookup.get(zd["dept"], {})
            asset_val = ast_d.get("Ambulances", 0) if metric == "ambulances" else ast_d.get("EMS_Personnel", 0)
            asset_val = asset_val or 0
            asset_max = _max_amb if metric == "ambulances" else _max_pers
            result[z] = _bubble_color_asset(asset_val, asset_max)
        elif is_rt:
            val = zd.get("median_rt", 0)
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0
            result[z] = _bubble_color_rt(val)
        else:
            val = zd["total_calls"] if metric == "total_calls" else zd.get("ems_calls", 0)
            t = min(1.0, float(val) / local_max) if local_max > 0 else 0
            r = int(198 + (8 - 198) * t)
            g = int(219 + (48 - 219) * t)
            b = int(239 + (107 - 239) * t)
            result[z] = f"rgb({r},{g},{b})"
    return result

# Pre-compute marker data list for the callback
MARKER_DATA = []
for _d, (_lat, _lon) in STATION_COORDS.items():
    _kpi = kpi_lookup.get(_d, {})
    _rtp = rt_lookup.get(_d, {})
    MARKER_DATA.append({
        "dept": _d, "lat": _lat, "lon": _lon,
        "total_calls": _kpi.get("Total Calls", 0) or 0,
        "ems_calls": _kpi.get("EMS Calls (Cat 3)", 0) or 0,
        "median_rt": _kpi.get("Median Response Time (min)", "N/A"),
        "ems_rt": _kpi.get("Median EMS Response Time (min)", "N/A"),
        "p75": _rtp.get("P75", "N/A"),
        "p90": _rtp.get("P90", "N/A"),
    })

def _build_popup_content(dept):
    """Return Dash html components for a marker popup."""
    kpi   = kpi_lookup.get(dept, {})
    rtp   = rt_lookup.get(dept, {})
    bud   = budget_lookup.get(dept, {})
    bil   = billing_lookup.get(dept, {})
    ast   = asset_lookup.get(dept, {})
    als_info = ALS_LEVELS.get(dept, {})
    pop   = SERVICE_AREA_POP.get(dept)
    total = kpi.get("Total Calls", "N/A")
    ems   = kpi.get("EMS Calls (Cat 3)", "N/A")
    med   = kpi.get("Median Response Time (min)", "N/A")
    ems_m = kpi.get("Median EMS Response Time (min)", "N/A")
    p75   = rtp.get("P75", "N/A")
    p90   = rtp.get("P90", "N/A")
    model = bud.get("Model", "N/A")
    ft    = bud.get("Staff_FT", "N/A")
    pt    = bud.get("Staff_PT", "N/A")
    exp   = f"${bud['Total_Expense']:,.0f}" if bud.get("Total_Expense") else "N/A"
    rev   = f"${bud['EMS_Revenue']:,.0f}" if isinstance(bud.get("EMS_Revenue"), (int, float)) and bud["EMS_Revenue"] == bud["EMS_Revenue"] else "N/A"
    bls   = f"${bil['BLS']:,}" if bil.get("BLS") else "N/A"
    als1  = f"${bil['ALS1']:,}" if bil.get("ALS1") else "N/A"
    als2  = f"${bil['ALS2']:,}" if bil.get("ALS2") else "N/A"
    miles = f"${bil['Mileage']}/mi" if bil.get("Mileage") else "N/A"
    pct   = f"{100*ems/total:.0f}%" if isinstance(ems,(int,float)) and isinstance(total,(int,float)) and total > 0 else "N/A"

    # Asset & service level fields
    svc_level  = als_info.get("Level", "N/A")
    amb_count  = ast.get("Ambulances", "N/A")
    ems_pers   = ast.get("EMS_Personnel", "N/A")
    paramedics = ast.get("Paramedics", "N/A")
    aemts      = ast.get("AEMTs", "N/A")
    emts       = ast.get("EMTs", "N/A")
    # Calls per ambulance (workload metric)
    if isinstance(ems, (int, float)) and isinstance(amb_count, (int, float)) and amb_count > 0:
        calls_per_amb = f"{ems / amb_count:,.0f}"
    else:
        calls_per_amb = "N/A"
    # EMS personnel per 1K pop
    if isinstance(ems_pers, (int, float)) and ems_pers > 0 and pop and pop > 0:
        pers_per_1k = f"{ems_pers / pop * 1000:,.1f}"
    else:
        pers_per_1k = "N/A"

    # Service level color badge
    _svc_colors = {"ALS": "#10B981", "AEMT": "#F7C143", "BLS": "#D94133", "N/A": "#6B7280"}
    svc_color = _svc_colors.get(svc_level, "#6B7280")

    _hdr = {"background": "#2E3238", "color": C_PRIMARY, "padding": "7px 12px",
            "fontWeight": "700", "fontSize": "14px", "borderRadius": "4px 4px 0 0"}
    _sec = {"background": "#1A1C1E", "padding": "3px 10px", "fontWeight": "600",
            "fontSize": "10px", "color": C_PRIMARY, "borderBottom": f"1px solid {C_BORDER}",
            "borderTop": f"1px solid {C_BORDER}"}
    _r1 = {"background": "#2E3238"}
    _td = {"padding": "2px 10px", "fontSize": "11px"}

    def _row(label, value, alt=False):
        s = {**_td, **(_r1 if alt else {})}
        return html.Tr([html.Td(html.B(label), style=s), html.Td(str(value), style=s)])

    def _row_badge(label, value, color, alt=False):
        """Row with a colored badge for service level."""
        s = {**_td, **(_r1 if alt else {})}
        badge = html.Span(value, style={
            "background": color, "color": "#fff", "padding": "1px 8px",
            "borderRadius": "3px", "fontSize": "10px", "fontWeight": "700",
        })
        return html.Tr([html.Td(html.B(label), style=s), html.Td(badge, style=s)])

    return html.Div([
        html.Div(dept, style=_hdr),
        html.Div("CALL VOLUME", style=_sec),
        html.Table([html.Tbody([_row("Total Calls", total, True), _row("EMS Calls", f"{ems} ({pct})")])],
                   style={"borderCollapse": "collapse", "width": "100%"}),
        html.Div("RESPONSE TIMES", style=_sec),
        html.Table([html.Tbody([_row("Median (all)", f"{med} min", True), _row("Median EMS", f"{ems_m} min"),
                    _row("P75", f"{p75} min", True), _row("P90", f"{p90} min")])],
                   style={"borderCollapse": "collapse", "width": "100%"}),
        html.Div("ASSETS & SERVICE LEVEL", style=_sec),
        html.Table([html.Tbody([_row_badge("Service Level", svc_level, svc_color, True),
                    _row("Ambulances", amb_count),
                    _row("EMS Calls / Amb", calls_per_amb, True),
                    _row("EMS Personnel", ems_pers),
                    _row("  Paramedics", paramedics, True),
                    _row("  AEMTs / EMTs", f"{aemts} / {emts}"),
                    _row("Per 1K Pop", pers_per_1k, True)])],
                   style={"borderCollapse": "collapse", "width": "100%"}),
        html.Div("STAFFING & BUDGET", style=_sec),
        html.Table([html.Tbody([_row("Model", model, True), _row("FT / PT Staff", f"{ft} FT / {pt} PT"),
                    _row("Total Expense", exp, True), _row("EMS Revenue", rev)])],
                   style={"borderCollapse": "collapse", "width": "100%"}),
        html.Div("BILLING RATES (2025)", style=_sec),
        html.Table([html.Tbody([_row("BLS", bls, True), _row("ALS-1", als1),
                    _row("ALS-2", als2, True), _row("Mileage", miles)])],
                   style={"borderCollapse": "collapse", "width": "100%"}),
    ], style={"fontFamily": "'Segoe UI',sans-serif", "minWidth": "220px", "maxWidth": "270px"})

print("Map helpers ready.")

# ── 7. Department list & colors ────────────────────────────────────────────────
ALL_DEPTS = sorted(raw["Department"].unique())
COLORS    = px.colors.qualitative.Plotly + px.colors.qualitative.Set2
CMAP      = {d: COLORS[i % len(COLORS)] for i, d in enumerate(ALL_DEPTS)}

MODEL_COLORS = {
    # Career+PT = best model → primary orange; Career = yellow; Volunteer variants = warm tones
    "Career":       "#F7C143",   # yellow-orange (C_YELLOW)
    "Career+PT":    "#F28C38",   # primary orange (C_PRIMARY) — best model
    "Volunteer+FT": "#10B981",   # emerald green (C_GREEN)
    "Career+Vol":   "#D94133",   # terracotta red (C_ORANGE)
    "Volunteer":    "#EF4444",   # bright red — highest cost model
}

# ── 8. App layout ─────────────────────────────────────────────────────────────
app = Dash(__name__, title="Jefferson County EMS Dashboard",
           suppress_callback_exceptions=True)
server = app.server  # expose Flask server for gunicorn

MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

# ── Design System ──────────────────────────────────────────────────────────────
# Dark dashboard palette (inspired by Power BI dark theme)
C_BG        = "#1A1C1E"   # primary background — deep charcoal-black
C_CARD      = "#24272B"   # card/container background — slightly lighter grey
C_NAVY      = "#1A1C1E"   # header bar — matches primary background
C_PRIMARY   = "#F28C38"   # primary accent — vibrant orange-gold
C_ORANGE    = "#D94133"   # secondary accent — muted red/terracotta
C_GREEN     = "#10B981"   # positive / success (emerald-500)
C_RED       = "#D94133"   # warning / negative — terracotta red
C_YELLOW    = "#F7C143"   # tertiary accent — bright yellow-orange
C_TEXT      = "#E0E0E0"   # primary text — off-white for readability
C_MUTED     = "#9CA3AF"   # secondary text — lighter muted for dark bg
C_BORDER    = "#5C5C5C"   # faint details — medium grey for grid/borders
C_SIDEBAR   = "#1A1C1E"   # sidebar — matches primary background
C_HDR_TABLE = "#F28C38"   # DataTable header — primary accent orange

FONT_STACK  = "'Inter', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif"

# Standard chart layout defaults — apply to every figure
_CHART_LAYOUT = dict(
    font        = dict(family=FONT_STACK, size=12, color=C_TEXT),
    plot_bgcolor= C_CARD,
    paper_bgcolor=C_CARD,
    margin      = dict(l=20, r=20, t=52, b=20),  # t=52 default; overridden per-chart
    hoverlabel  = dict(bgcolor="#2E3238", bordercolor=C_BORDER,
                       font_family=FONT_STACK, font_size=12,
                       font_color=C_TEXT),
    title       = dict(
        font=dict(family=FONT_STACK, size=14, color=C_TEXT),
        pad=dict(b=8),
    ),
    xaxis       = dict(
        gridcolor=C_BORDER, gridwidth=1,
        showline=False, zeroline=False,
        tickfont=dict(size=12, color=C_TEXT),
        title_font=dict(size=12, color=C_MUTED),
    ),
    yaxis       = dict(
        gridcolor=C_BORDER, gridwidth=1,
        showline=False, zeroline=False,
        tickfont=dict(size=12, color=C_TEXT),
        title_font=dict(size=12, color=C_MUTED),
    ),
)

def _apply_chart_style(fig, height=380, legend_below=False, title_has_subtitle=False):
    """Apply the standard modern chart style to any Plotly figure.

    Args:
        height: chart height in pixels
        legend_below: if True, place legend horizontally below chart; if False,
                      place it above the plot area (y=1.02, does not overlap title)
        title_has_subtitle: if True, increase top margin to 70px to prevent the
                            <br><sup>...</sup> subtitle line from being clipped by legend
    """
    t_margin = 70 if title_has_subtitle else 52
    layout_overrides = dict(**_CHART_LAYOUT)
    layout_overrides["margin"] = dict(l=20, r=20, t=t_margin, b=20)
    fig.update_layout(**layout_overrides, height=height)
    if legend_below:
        fig.update_layout(legend=dict(
            orientation="h",
            yanchor="top", y=-0.18,
            xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ))
    else:
        fig.update_layout(legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ))
    return fig

def _section_header(title):
    """Return a styled section title div with left accent bar."""
    return html.Div(title, style={
        "fontSize": "1.05rem",
        "fontWeight": "600",
        "color": C_TEXT,
        "borderLeft": f"4px solid {C_PRIMARY}",
        "paddingLeft": "10px",
        "marginBottom": "14px",
        "fontFamily": FONT_STACK,
    })

def _sub_header(title):
    """Return a smaller styled sub-section header."""
    return html.Div(title, style={
        "fontSize": "0.9rem",
        "fontWeight": "600",
        "color": C_MUTED,
        "borderLeft": f"3px solid {C_ORANGE}",
        "paddingLeft": "8px",
        "marginTop": "14px",
        "marginBottom": "8px",
        "fontFamily": FONT_STACK,
    })

def kpi_card(label, value, sub="", color=None, delta=None, delta_positive=True):
    """
    Modern KPI card with large bold number, label above, colored delta pill below.
    delta: string like "+12.3%" shown as a green/red pill badge.
    """
    accent = color if color else C_PRIMARY
    delta_badge = []
    if delta:
        badge_bg = C_GREEN if delta_positive else C_RED
        delta_badge = [html.Div(delta, style={
            "display": "inline-block",
            "background": badge_bg,
            "color": "white",
            "borderRadius": "999px",
            "padding": "1px 8px",
            "fontSize": "0.7rem",
            "fontWeight": "600",
            "marginTop": "4px",
        })]

    return html.Div([
        html.Div(label, style={
            "fontSize": "0.72rem",
            "fontWeight": "600",
            "color": C_MUTED,
            "textTransform": "uppercase",
            "letterSpacing": "0.05em",
            "marginBottom": "4px",
            "fontFamily": FONT_STACK,
        }),
        html.Div(value, style={
            "fontSize": "1.75rem",
            "fontWeight": "700",
            "color": accent,
            "lineHeight": "1.1",
            "fontFamily": FONT_STACK,
        }),
        html.Div(sub, style={
            "fontSize": "0.72rem",
            "color": C_MUTED,
            "marginTop": "3px",
            "fontFamily": FONT_STACK,
        }),
        *delta_badge,
    ], style={
        "background": C_CARD,
        "borderRadius": "12px",
        "padding": "20px 22px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.3)",
        "flex": "1",
        "minWidth": "140px",
        "fontFamily": FONT_STACK,
        "borderTop": f"3px solid {accent}",
    })

def _legal_finding_card(title, body, status_label, color):
    """Compact legal finding card with colored top-border and status pill."""
    return html.Div([
        html.Div([
            html.Span("", style={
                "display": "inline-block", "width": "8px", "height": "8px",
                "borderRadius": "50%", "backgroundColor": color,
                "marginRight": "8px", "verticalAlign": "middle",
            }),
            html.Span(title, style={
                "fontWeight": "700", "fontSize": "0.85rem",
                "color": C_TEXT, "fontFamily": FONT_STACK,
            }),
        ], style={"marginBottom": "8px"}),
        html.P(body, style={
            "fontSize": "0.8rem", "color": C_MUTED, "lineHeight": "1.6",
            "margin": "0 0 10px 0", "fontFamily": FONT_STACK,
        }),
        html.Div(status_label, style={
            "display": "inline-block", "background": color,
            "color": "white" if color != C_YELLOW else "#1A1C1E",
            "borderRadius": "999px", "padding": "2px 10px",
            "fontSize": "0.65rem", "fontWeight": "700",
            "letterSpacing": "0.05em", "textTransform": "uppercase",
        }),
    ], style={
        "flex": "1", "minWidth": "200px",
        "background": C_CARD, "borderRadius": "8px",
        "borderTop": f"3px solid {color}",
        "padding": "16px", "fontFamily": FONT_STACK,
        "boxShadow": "0 1px 4px rgba(0,0,0,0.25)",
    })

SIDEBAR_STYLE = {
    "width": "230px",
    "flexShrink": "0",
    "background": C_SIDEBAR,
    "padding": "0 0 24px 0",
    "color": "white",
    "overflowY": "auto",
    "height": "100vh",
    "position": "sticky",
    "top": "0",
    "fontFamily": FONT_STACK,
}
CONTENT_STYLE = {
    "flex": "1",
    "overflowY": "auto",
    "padding": "0",
    "background": C_BG,
    "fontFamily": FONT_STACK,
}
CARD = {
    "background": C_CARD,
    "borderRadius": "12px",
    "padding": "22px 24px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.3)",
    "marginBottom": "20px",
    "fontFamily": FONT_STACK,
}

# DataTable shared styling
_DT_STYLE_HEADER = {
    "backgroundColor": "#2E3238",
    "color": C_PRIMARY,
    "fontWeight": "600",
    "padding": "10px 12px",
    "fontFamily": FONT_STACK,
    "fontSize": "12px",
    "border": "none",
}
_DT_STYLE_CELL = {
    "padding": "8px 12px",
    "fontFamily": FONT_STACK,
    "fontSize": "13px",
    "color": C_TEXT,
    "backgroundColor": C_CARD,
    "borderRight": "none",
    "borderLeft": "none",
    "borderTop": f"1px solid {C_BORDER}",
    "borderBottom": f"1px solid {C_BORDER}",
}
_DT_STYLE_DATA_CONDITIONAL_BASE = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#2E3238"},
]

# ── Source Citation Helper ──────────────────────────────────────────────────────
def _source_citation(*sources):
    """
    Return a styled html.Div listing data sources at the bottom of a card section.

    Each source is either:
      - A plain string  → rendered as inline text (local file name or simple note)
      - A tuple (label, url) → rendered as a clickable html.A link

    Example:
        _source_citation(
            "NFIRS 2024 — 14 Excel files in ISyE Project/Data and Resources/Call Data/",
            ("Bayfield 2025 Budget Introduction",
             "https://www.bayfieldcounty.wi.gov/DocumentCenter/View/18161/2025-BUDGET-INTRODUCTION"),
        )
    """
    _sep_style = {"color": C_MUTED, "margin": "0 6px"}
    children = [
        html.Span("Sources: ", style={
            "fontWeight": "600",
            "color": C_MUTED,
            "fontSize": "11px",
            "fontFamily": FONT_STACK,
        })
    ]
    for i, src in enumerate(sources):
        if i > 0:
            children.append(html.Span(" | ", style=_sep_style))
        if isinstance(src, tuple):
            label, url = src
            children.append(html.A(
                label,
                href=url,
                target="_blank",
                rel="noopener noreferrer",
                style={
                    "color": C_PRIMARY,
                    "fontSize": "11px",
                    "fontFamily": FONT_STACK,
                    "textDecoration": "underline",
                }
            ))
        else:
            children.append(html.Span(src, style={
                "color": C_MUTED,
                "fontSize": "11px",
                "fontFamily": FONT_STACK,
            }))
    return html.Div(children, style={
        "marginTop": "14px",
        "paddingTop": "10px",
        "borderTop": f"1px solid {C_BORDER}",
        "lineHeight": "1.6",
    })

# ── Bayfield County Static Data (no callback needed — all hard-coded) ─────────
_df_bayfield_levy = pd.DataFrame({
    "Line Item": [
        "Agency Stabilization (9 × $20K)",
        "EMS Coordinator",
        "Emergency Medical Dispatch",
        "Residual",
    ],
    "Amount": [180_000, 145_000, 128_000, 5_000],
})

@lru_cache(maxsize=1)
def _get_fig_bayfield_levy():
    fig = go.Figure(go.Bar(
        x=_df_bayfield_levy["Amount"],
        y=_df_bayfield_levy["Line Item"],
        orientation="h",
        marker_color=[C_PRIMARY, C_GREEN, C_ORANGE, C_MUTED],
        text=[f"${v:,.0f}" for v in _df_bayfield_levy["Amount"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Amount: $%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(
            text="Bayfield County 2025 Countywide EMS Levy — $458,000"
                 "<br><sup>Source: Bayfield County 2025 Budget Introduction</sup>",
            font=dict(size=14),
        ),
        xaxis=dict(
            tickprefix="$",
            tickformat=",",
            range=[0, 210_000],
        ),
    )
    _apply_chart_style(fig, height=320)
    fig.update_layout(margin=dict(l=220, r=80, t=60, b=40))
    return fig

_df_jeff_bayfield_compare = pd.DataFrame([
    {
        "Metric":                   "EMS Agencies",
        "Jefferson County":         "12",
        "Bayfield County":          "9",
    },
    {
        "Metric":                   "County EMS Overlay Cost",
        "Jefferson County":         "Not established",
        "Bayfield County":          "$458,000/yr",
    },
    {
        "Metric":                   "Per-Agency Stipend",
        "Jefferson County":         "None",
        "Bayfield County":          "$20,000/yr",
    },
    {
        "Metric":                   "County EMS Coordinator",
        "Jefferson County":         "None",
        "Bayfield County":          "Yes ($145K/yr)",
    },
    {
        "Metric":                   "Centralized EMD Funding",
        "Jefferson County":         "Municipal (not county-funded)",
        "Bayfield County":          "County-funded ($128K/yr)",
    },
    {
        "Metric":                   "Revenue Recovery Rate",
        "Jefferson County":         "26.8%",
        "Bayfield County":          "N/A",
    },
    {
        "Metric":                   "Primary Staffing Model",
        "Jefferson County":         "Mixed (Career/PT/Vol)",
        "Bayfield County":          "Rural Volunteer",
    },
    {
        "Metric":                   "Levy Exception Used",
        "Jefferson County":         "Not yet",
        "Bayfield County":          "Yes — Wis. Stat. 66.0602(3)",
    },
    {
        "Metric":                   "Scaled Estimate for Jefferson",
        "Jefferson County":         "$540,000–$610,000/yr",
        "Bayfield County":          "N/A",
    },
])

# ── Section 15 Static Data (kept for future use — not displayed in current tabs) ─

# 15a: Cost/call with volume threshold indicator
# Source: savings_model.md 300-call table + utilization_analysis.md
_df_cost_threshold = pd.DataFrame([
    {"Municipality": "Palmyra",       "Cost_Per_Call": 25555, "EMS_Calls":    32},
    {"Municipality": "Jefferson",     "Cost_Per_Call":  1030, "EMS_Calls":  1457},
    {"Municipality": "Johnson Creek", "Cost_Per_Call":  2329, "EMS_Calls":   487},
    {"Municipality": "Ixonia",        "Cost_Per_Call":  2184, "EMS_Calls":   289},
    {"Municipality": "Waterloo",      "Cost_Per_Call":  2120, "EMS_Calls":   520},
    {"Municipality": "Watertown",     "Cost_Per_Call":  1905, "EMS_Calls":  2012},
    {"Municipality": "Cambridge",     "Cost_Per_Call":  1057, "EMS_Calls":    87},
    {"Municipality": "Lake Mills",    "Cost_Per_Call":   670, "EMS_Calls":   518},
    {"Municipality": "Fort Atkinson", "Cost_Per_Call":   471, "EMS_Calls":  1616},
    {"Municipality": "Edgerton",      "Cost_Per_Call":   330, "EMS_Calls":  2138},
])

# 15b: Cost Driver Magnitude
_df_savings = pd.DataFrame([
    {"Cost Driver": "Watertown Billing Rate Gap",                "Low_K": 400,  "High_K":  700, "Pending_Audit": False},
    {"Cost Driver": "Palmyra Sub-Threshold Transport",           "Low_K": 491,  "High_K":  572, "Pending_Audit": False},
    {"Cost Driver": "Cambridge Service Collapse",                "Low_K":  55,  "High_K":   64, "Pending_Audit": False},
    {"Cost Driver": "Lake Mills Revenue Leakage",                "Low_K":  70,  "High_K":  100, "Pending_Audit": False},
    {"Cost Driver": "Jefferson Cost/Call Disparity (if audited)","Low_K": 900,  "High_K": 1050, "Pending_Audit": True},
])

# Levy Exception Eligibility Table (used in Contracts & Legal tab)
# Source: savings_model.md EMS Levy Eligibility Analysis
_df_levy_elig = pd.DataFrame([
    {
        "Municipality / Scope": "County-Wide (all)",
        "Current Model":         "No county EMS levy",
        "Levy Exception Path":   "County EMS Levy",
        "Qualifying Statute":    "66.0602(3)(e)6",
        "Status":                "Eligible — Lafayette Co. precedent",
    },
    {
        "Municipality / Scope": "County-Wide (all)",
        "Current Model":         "No county EMS levy",
        "Levy Exception Path":   "AB 197 Regional Exemption",
        "Qualifying Statute":    "AB 197 (>=232 sq mi / >=8 munis)",
        "Status":                "Eligible — 570 sq mi, 12+ munis",
    },
    {
        "Municipality / Scope": "Fort Atkinson district",
        "Current Model":         "Self-operated + IGAs",
        "Levy Exception Path":   "Joint EMS District",
        "Qualifying Statute":    "66.0602(3)(h)",
        "Status":                "Ready — contracts expired, in renegotiation",
    },
    {
        "Municipality / Scope": "Jefferson City district",
        "Current Model":         "Self-operated + IGAs",
        "Levy Exception Path":   "Joint EMS District",
        "Qualifying Statute":    "66.0602(3)(h)",
        "Status":                "Locked until Jan 2028 (exclusivity clause)",
    },
    {
        "Municipality / Scope": "Lake Mills",
        "Current Model":         "Ryan Brothers contract",
        "Levy Exception Path":   "Contract -> membership required",
        "Qualifying Statute":    "66.0602(3)(h) — FAQ Q11",
        "Status":                "Ineligible until contract restructured",
    },
])


# ── Section 16 Static Data: EMS Contract Network Analysis ─────────────────────
# Source: contract_analysis.md — all 17 IGAs read in full (Mar 2026)

_df_contract_network = pd.DataFrame([
    {
        "Provider":        "Fort Atkinson EMS",
        "Service Area":    "Towns of Koshkonong (~$29K/yr), Jefferson (~$2.7K/yr)",
        "Service Type":    "ALS Transport",
        "Payment Model":   "Per-capita ($7.22 base + CPI-W, 2–6% cap)",
        "Contract Expires": "Dec 31, 2025",
        "Status":          "EXPIRED — No auto-renew; active renegotiation (Peterson cost model Dec 2025)",
    },
    {
        "Provider":        "City of Jefferson EMS",
        "Service Area":    "Towns of Aztalan, Farmington, Hebron, Jefferson, Oakland",
        "Service Type":    "ALS Transport",
        "Payment Model":   "Per-capita ($31–$40 escalating)",
        "Contract Expires": "Dec 31, 2027",
        "Status":          "Active — Exclusivity clause",
    },
    {
        "Provider":        "Johnson Creek JCFD",
        "Service Area":    "Towns of Aztalan, Farmington, Milford, Watertown",
        "Service Type":    "Fire + EMS Combined",
        "Payment Model":   "Equalized value allocation",
        "Contract Expires": "Dec 31, 2028",
        "Status":          "Active",
    },
    {
        "Provider":        "Lake Mills / Ryan Brothers",
        "Service Area":    "Towns of Aztalan, Lake Mills, Oakland (east)",
        "Service Type":    "Private ALS Transport",
        "Payment Model":   "Per-capita ($49.44 + 3–6%/yr)",
        "Contract Expires": "Rolling 3-year",
        "Status":          "Active — 180-day exit notice",
    },
    {
        "Provider":        "Waterloo EMS",
        "Service Area":    "Town of Milford (portion)",
        "Service Type":    "AEMT Transport",
        "Payment Model":   "Per-capita ($18→$22→$26, escalating)",
        "Contract Expires": "Dec 31, 2025",
        "Status":          "Likely auto-renewed 2026 at $26/cap (120-day opt-out deadline was Sept 2025)",
    },
    {
        "Provider":        "Ixonia Fire & EMS",
        "Service Area":    "Town of Watertown",
        "Service Type":    "Fire + EMS Combined",
        "Payment Model":   "$49,169/yr flat (budget formula: calls/pop/value — ⅓ each)",
        "Contract Expires": "Dec 31, 2025",
        "Status":          "Extension option to 2027 — unconfirmed",
    },
    {
        "Provider":        "Edgerton EFPD",
        "Service Area":    "Town of Koshkonong (small area)",
        "Service Type":    "Fire + EMS",
        "Payment Model":   "CPI + 2% indexed",
        "Contract Expires": "Auto-renews annually",
        "Status":          "Active (120-day non-renewal)",
    },
])

_df_self_vs_contract = pd.DataFrame([
    {
        "Municipality":    "Fort Atkinson",
        "EMS Model":       "Career+PT ALS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "Koshkonong, Jefferson Town",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "City of Jefferson",
        "EMS Model":       "Career ALS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "5 townships (Aztalan, Farmington, Hebron, Jefferson, Oakland)",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Johnson Creek (JCFD)",
        "EMS Model":       "Volunteer+PT ALS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "4 townships (Aztalan, Farmington, Milford, Watertown)",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Watertown",
        "EMS Model":       "Career ALS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "Milford (supplemental)",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Waterloo",
        "EMS Model":       "Career+Vol AEMT",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "Milford (portion)",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Ixonia",
        "EMS Model":       "Vol+FT BLS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "Town of Watertown",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Edgerton (EFPD)",
        "EMS Model":       "Career+PT ALS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "Koshkonong (small area)",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Whitewater",
        "EMS Model":       "Career+PT ALS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "—",
        "Contracts IN From": "—",
    },
    {
        "Municipality":    "Palmyra",
        "EMS Model":       "Volunteer BLS",
        "Self-Operated":   "Yes",
        "Contracts OUT To": "—",
        "Contracts IN From": "ALS intercept from Western Lakes",
    },
    {
        "Municipality":    "Cambridge",
        "EMS Model":       "Collapsed (2025)",
        "Self-Operated":   "Formerly",
        "Contracts OUT To": "—",
        "Contracts IN From": "Fort Atkinson (fallback)",
    },
    {
        "Municipality":    "Lake Mills",
        "EMS Model":       "BLS support only",
        "Self-Operated":   "Partial",
        "Contracts OUT To": "—",
        "Contracts IN From": "Ryan Brothers (private ALS)",
    },
])

# ── NEW: Chief Peterson 24/7 ALS Cost Model ──────────────────────────────────
# Source: 25-1210 JC EMS Workgroup Cost Projection.pdf (Chief Bruce Peterson, FAFD)
_PETERSON_COST_MODEL = {
    "labels": [
        "Salaries", "Overtime", "Benefits", "WRS (Pension)",
        "EMS Supplies", "Clothing", "Amb. Maint.", "Amb. Equip.",
        "Insurance", "Equip. Maint.", "Training", "Admin",
        "Total Operating",
        "EMS Revenue",
        "Net County Cost",
    ],
    "values": [
        371697, 24894, 178466, 27761,
        28000, 3000, 7000, 2000,
        67500, 500, 1000, 5000,
        0,        # total row
        -466200,  # revenue offset
        0,        # net total row
    ],
    "measures": [
        "relative", "relative", "relative", "relative",
        "relative", "relative", "relative", "relative",
        "relative", "relative", "relative", "relative",
        "total",
        "relative",
        "total",
    ],
    "notes": [
        "3 Paramedics @ $64,332 + 3 EMT-A @ $59,567",
        "130 hrs/employee/yr (FLSA + backfill)",
        "45% of wages (FICA, Medicare, Unemployment, Health)",
        "WRS employer contribution",
        "$40/call x 700 calls",
        "$500/employee x 6",
        "2 ambulances",
        "",
        "Liability, Ambulance, WC, Umbrella",
        "", "", "", "",
        "700 calls x $666 avg collected",
        "",
    ],
}

# ── NEW: Contract Per-Capita Escalation ──────────────────────────────────────
# Source: Jefferson City EMS contract 2024-2027; Waterloo fire and EMS contract;
#         FA Ambulance contract 2023; Lake Mills / Ryan Brothers IGAs; Ixonia IGA
_CONTRACT_ESCALATION = pd.DataFrame([
    {"Contract": "Jefferson City -> 5 Towns", "Year": 2023, "Rate": 28.00, "Status": "Active"},
    {"Contract": "Jefferson City -> 5 Towns", "Year": 2024, "Rate": 31.00, "Status": "Active"},
    {"Contract": "Jefferson City -> 5 Towns", "Year": 2025, "Rate": 34.00, "Status": "Active"},
    {"Contract": "Jefferson City -> 5 Towns", "Year": 2026, "Rate": 37.00, "Status": "Active"},
    {"Contract": "Jefferson City -> 5 Towns", "Year": 2027, "Rate": 40.00, "Status": "Active"},
    {"Contract": "Waterloo -> Milford",       "Year": 2023, "Rate": 18.00, "Status": "Auto-renewed"},
    {"Contract": "Waterloo -> Milford",       "Year": 2024, "Rate": 22.00, "Status": "Auto-renewed"},
    {"Contract": "Waterloo -> Milford",       "Year": 2025, "Rate": 26.00, "Status": "Auto-renewed"},
    {"Contract": "Fort Atkinson -> Towns",    "Year": 2023, "Rate": 7.22, "Status": "EXPIRED"},
    {"Contract": "Fort Atkinson -> Towns",    "Year": 2024, "Rate": 7.22, "Status": "EXPIRED"},
    {"Contract": "Fort Atkinson -> Towns",    "Year": 2025, "Rate": 7.22, "Status": "EXPIRED"},
    {"Contract": "Lake Mills / Ryan Bros",    "Year": 2024, "Rate": 48.00, "Status": "Active"},
    {"Contract": "Lake Mills / Ryan Bros",    "Year": 2025, "Rate": 49.44, "Status": "Active"},
    {"Contract": "Ixonia -> Watertown Twp",   "Year": 2025, "Rate": 44.10, "Status": "Expired (1-yr)"},
])

# ── NEW: Contract Expiration Timeline ────────────────────────────────────────
# Source: IGA contract text files (contract_analysis.md)
_CONTRACT_TIMELINE = pd.DataFrame([
    {"Contract": "Fort Atkinson -> Koshkonong",    "Start": "2023-01-01", "End": "2025-12-31", "Status": "EXPIRED"},
    {"Contract": "Fort Atkinson -> Jefferson Twp", "Start": "2023-01-01", "End": "2025-12-31", "Status": "EXPIRED"},
    {"Contract": "Oakland Amendment (expanded)",   "Start": "2025-01-01", "End": "2025-12-31", "Status": "EXPIRED"},
    {"Contract": "Ixonia -> Town of Watertown",    "Start": "2025-01-01", "End": "2025-12-31", "Status": "EXPIRED"},
    {"Contract": "Waterloo -> Town of Milford",    "Start": "2023-01-01", "End": "2026-12-31", "Status": "Auto-renewed"},
    {"Contract": "Edgerton -> Koshkonong (sliver)", "Start": "2023-01-01", "End": "2026-12-31", "Status": "Auto-renewed"},
    {"Contract": "Jefferson City -> 5 Towns",      "Start": "2024-01-01", "End": "2027-12-31", "Status": "Active"},
    {"Contract": "Johnson Creek -> 4 Townships",   "Start": "2024-01-01", "End": "2028-12-31", "Status": "Active"},
    {"Contract": "Lake Mills / Ryan Brothers",     "Start": "2024-01-01", "End": "2027-01-01", "Status": "Active (rolling 3-yr)"},
])
_CONTRACT_TIMELINE["Start"] = pd.to_datetime(_CONTRACT_TIMELINE["Start"])
_CONTRACT_TIMELINE["End"]   = pd.to_datetime(_CONTRACT_TIMELINE["End"])

def _get_contract_kpis():
    """Compute summary KPI values for the Contracts & Legal tab."""
    ct = _CONTRACT_TIMELINE
    expired = ct["Status"].str.contains("EXPIRED|Expired", case=False).sum()
    auto_renewed = ct["Status"].str.contains("Auto-renewed", case=False).sum()
    active = len(ct) - expired - auto_renewed
    latest_rates = _CONTRACT_ESCALATION.groupby("Contract")["Rate"].last()
    return {
        "total": str(len(ct)),
        "expired": str(expired),
        "active": str(active),
        "auto_renewed": str(auto_renewed),
        "providers": str(len(_df_contract_network)),
        "rate_min": f"${latest_rates.min():.2f}",
        "rate_max": f"${latest_rates.max():.2f}",
    }

_CONTRACT_KPIS = _get_contract_kpis()

# ── Secondary Network Simulation Data ────────────────────────────────────────
# Load simulation results if available (generated by secondary_simulation.py)
_SIM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation_output")
_SIM_KPI = None
_SIM_UTIL = None
_SIM_SENS = None
_SIM_HUBS = []
if os.path.isdir(_SIM_DIR):
    _kpi_path = os.path.join(_SIM_DIR, "simulation_results_summary.csv")
    _util_path = os.path.join(_SIM_DIR, "simulation_utilization.csv")
    _sens_path = os.path.join(_SIM_DIR, "simulation_sensitivity.csv")
    if os.path.exists(_kpi_path):
        _SIM_KPI = pd.read_csv(_kpi_path)
    if os.path.exists(_util_path):
        _SIM_UTIL = pd.read_csv(_util_path)
        _SIM_HUBS = [{"lat": r["Lat"], "lon": r["Lon"], "unit": r["Unit"],
                       "calls": r["Calls_Served"], "util": r["Utilization_Pct"],
                       "cpd": r["Calls_Per_Day"]}
                      for _, r in _SIM_UTIL.iterrows()]
    if os.path.exists(_sens_path):
        _SIM_SENS = pd.read_csv(_sens_path)

# Existing primary station coords for simulation map
_SIM_PRIMARY_STATIONS = [
    {"name": "Watertown",     "lat": 43.1861, "lon": -88.7339},
    {"name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397},
    {"name": "Whitewater",    "lat": 42.8325, "lon": -88.7332},
    {"name": "Edgerton",      "lat": 42.8403, "lon": -89.0629},
    {"name": "Jefferson",     "lat": 43.0056, "lon": -88.8014},
    {"name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745},
    {"name": "Waterloo",      "lat": 43.1886, "lon": -88.9797},
    {"name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144},
    {"name": "Ixonia",        "lat": 43.1446, "lon": -88.5970},
    {"name": "Palmyra",       "lat": 42.8794, "lon": -88.5855},
    {"name": "Cambridge",     "lat": 43.0049, "lon": -89.0224},
    {"name": "Helenville",    "lat": 43.0135, "lon": -88.6998},
    {"name": "Western Lakes", "lat": 43.0110, "lon": -88.5877},
]

# ── NEW: Ambulance Replacement Priority ──────────────────────────────────────
# Source: 2025 CIP documents, NFIRS apparatus records, 15-yr end-of-life standard
_AMBULANCE_REPLACE_PRIORITY = pd.DataFrame([
    {"Department": "Fort Atkinson", "Unit": "Rescue 8157", "Year": 2004, "Age": 21,
     "Risk": "CRITICAL", "Note": "6 yrs past 15-yr end-of-life", "CIP": "None on file"},
    {"Department": "Waterloo",      "Unit": "Rescue 3959", "Year": 2005, "Age": 20,
     "Risk": "CRITICAL", "Note": "5 yrs past 15-yr end-of-life", "CIP": "CIP 2025-2029 approved"},
    {"Department": "Watertown",     "Unit": "Med 52/4152", "Year": 2006, "Age": 19,
     "Risk": "HIGH",     "Note": "4 yrs past 15-yr end-of-life", "CIP": "None on file"},
    {"Department": "Jefferson",     "Unit": "Rescue 756",  "Year": 2007, "Age": 18,
     "Risk": "HIGH",     "Note": "3 yrs past 15-yr end-of-life", "CIP": "None on file"},
    {"Department": "Ixonia",        "Unit": "8351",        "Year": 2012, "Age": 13,
     "Risk": "MONITOR",  "Note": "Single-unit dept -- no backup if out of service", "CIP": "None on file"},
])

# ── Section 17 Static Data: Contract Windows & Structural Opportunities ───────
# Source: contract_analysis.md §B-D + savings_model.md cost magnitude data

_df_transition_roadmap = pd.DataFrame([
    {
        "Window":            "Near-term",
        "Timeline":          "0–6 months (Spring 2026)",
        "Observable Opportunity": "Fort Atkinson contracts expired Dec 31, 2025 — county-wide clause enables renegotiation; Palmyra transport at $5,841/call on 32 calls/yr (2024 authoritative)",
        "Key Departments":   "Fort Atkinson, Palmyra",
        "Scale of Identified Inefficiency": "$491K–$572K (Palmyra fixed-cost transport below viability threshold)",
        "Structural Context":      "FA contracts already expired; county-wide clause triggers on county resolution",
    },
    {
        "Window":            "Near-term",
        "Timeline":          "0–6 months (Spring 2026)",
        "Observable Opportunity": "Watertown BLS rate ($1,100) is lowest in county vs. FA ($1,500) and Jefferson ($1,900) — billing rate misalignment",
        "Key Departments":   "Watertown",
        "Scale of Identified Inefficiency": "$400K–$700K annual revenue gap vs. peer rates",
        "Structural Context": "Budget cycle 2026; rate comparison data available",
    },
    {
        "Window":            "Near-term",
        "Timeline":          "0–6 months (Fall 2026)",
        "Observable Opportunity": "County qualifies for 66.0602(3)(e)6 EMS levy exception but has never utilized it",
        "Key Departments":   "County-wide",
        "Scale of Identified Inefficiency": "$504K–$610K annual levy capacity (unused statutory path)",
        "Structural Context": "Lafayette County precedent (Resolution 26-23) exists",
    },
    {
        "Window":            "Medium-term",
        "Timeline":          "6–12 months (2026–2027)",
        "Observable Opportunity": "Jefferson City: 91 EMS calls on $1.5M budget may be NFIRS undercount; Lake Mills pays $347K but captures only $8K in revenue",
        "Key Departments":   "Jefferson, Lake Mills",
        "Scale of Identified Inefficiency": "TBD (Jefferson pending audit); $70K–$100K (Lake Mills revenue leakage)",
        "Structural Context": "Data audit needed for Jefferson; 180-day notice window for Ryan Brothers",
    },
    {
        "Window":            "Medium-term",
        "Timeline":          "12–24 months (2027–2028)",
        "Observable Opportunity": "All 5 Jefferson City township IGAs expire Dec 31, 2027 — exclusivity clause prevents earlier structural change",
        "Key Departments":   "Jefferson City district",
        "Scale of Identified Inefficiency": "$900K–$1.05M if data audit confirms cost/call disparity",
        "Structural Context": "Exclusivity clause expires naturally; no financial penalty at term end",
    },
    {
        "Window":            "Long-term",
        "Timeline":          "24–36 months (2028–2029)",
        "Observable Opportunity": "JCFD fire/EMS contract expires Dec 31, 2028 — bundled structure prevents independent EMS cost analysis",
        "Key Departments":   "JCFD, 4 townships",
        "Scale of Identified Inefficiency": "TBD (fire vs. EMS cost separation needed first)",
        "Structural Context": "Fire vs. EMS disaggregation is prerequisite for analysis",
    },
])

# ── Section 18 Static Data: EMS Levy Framework & Implementation ───────────────
# Source: savings_model.md §1, §3, §5 + Lafayette County Resolution 26-23

_df_levy_checklist = [
    "County EMS Committee reviews Wis. Stat. 66.0602(3)(e)6 and confirms eligibility  (Confirmed: 570 sq mi > 232; 12+ munis > 8)",
    "County attorney drafts resolution modeled on Lafayette County Resolution 26-23",
    "Resolution establishes 5-member EMS Advisory Subcommittee (county + towns + villages + cities + EMS districts)",
    "Subcommittee commissions independent EMS system study for long-term financing",
    "County Board adopts resolution at fall budget cycle (Fall 2026)",
    "Year 1 (FY2027): Distribute per-capita funds for EMS stabilization",
    "Year 2+ (FY2028+): Refine based on subcommittee recommendations and hybrid model progress",
]

# ── Cross-County Benchmarking Static Data (Section 19) ───────────────────────
# Source: cross_county_comparison.md Phase 2 -- March 2, 2026
# All peer data is hardcoded; NO new Excel reads.

# Panel 3A: 7-County System Structure Comparison Table
_df_cc_structure = pd.DataFrame([
    {"County": "Jefferson",  "Population": "84,700",  "Area (sq mi)": "570",   "# EMS Agencies": "14 (11 EMS transport)", "System Model": "Municipal independent (fragmented)",           "County Coordinator": "No",  "County Levy": "No",              "ALS Coverage": "Mixed (6 ALS, 1 AEMT, 2 BLS)",      "Data Confidence": "Confirmed"},
    {"County": "Portage",    "Population": "70,700",  "Area (sq mi)": "811",   "# EMS Agencies": "8-10 est.",            "System Model": "Hybrid in progress (county coordinator)",       "County Coordinator": "Yes", "County Levy": "Partial",         "ALS Coverage": "Mixed ALS/BLS",                      "Data Confidence": "Estimated"},
    {"County": "Bayfield",   "Population": "15,800",  "Area (sq mi)": "1,478", "# EMS Agencies": "9",                    "System Model": "Municipal + county overlay (levy+coordinator)", "County Coordinator": "Yes", "County Levy": "Yes ($458K)",     "ALS Coverage": "BLS-heavy; ALS via intercept",       "Data Confidence": "Confirmed"},
    {"County": "Walworth",   "Population": "105,000", "Area (sq mi)": "555",   "# EMS Agencies": "15",                   "System Model": "Mixed: vol/POC depts; study active",            "County Coordinator": "No",  "County Levy": "No ($400K capital)", "ALS Coverage": "Mostly ALS in larger depts",          "Data Confidence": "Confirmed"},
    {"County": "Washington", "Population": "140,000", "Area (sq mi)": "430",   "# EMS Agencies": "Unknown",              "System Model": "Hybrid emerging (West Bend ALS anchor)",        "County Coordinator": "No",  "County Levy": "No (proposed)",   "ALS Coverage": "ALS anchor (West Bend FD)",          "Data Confidence": "Mixed"},
    {"County": "Dodge",      "Population": "90,000",  "Area (sq mi)": "879",   "# EMS Agencies": "Unknown",              "System Model": "Municipal independent (dispatch-only county)",  "County Coordinator": "No",  "County Levy": "No",              "ALS Coverage": "Mixed (Beaver Dam ALS; rural BLS)",  "Data Confidence": "Estimated"},
    {"County": "Rock",       "Population": "165,000", "Area (sq mi)": "721",   "# EMS Agencies": "Unknown",              "System Model": "Hybrid: career FDs + hospital-based EMS",       "County Coordinator": "No",  "County Levy": "No",              "ALS Coverage": "ALS urban / BLS rural",              "Data Confidence": "Estimated"},
])
_CC_STRUCTURE_COND = _DT_STYLE_DATA_CONDITIONAL_BASE + [
    {"if": {"filter_query": '{County} = "Jefferson"'}, "fontWeight": "600", "color": C_PRIMARY},
]

# Panel 3B: Agencies per 10K population bar chart
_df_cc_agencies_raw = pd.DataFrame([
    {"County": "Portage",    "Agencies_per_10K": 1.27, "Status": "Estimated", "Notes": "~9 agencies est. / 70,700 pop"},
    {"County": "Walworth",   "Agencies_per_10K": 1.43, "Status": "Confirmed", "Notes": "15 depts / 105,000 pop"},
    {"County": "Jefferson",  "Agencies_per_10K": 1.65, "Status": "Confirmed", "Notes": "14 agencies / 84,700 pop"},
    {"County": "Bayfield",   "Agencies_per_10K": 5.70, "Status": "Confirmed", "Notes": "9 agencies / 15,800 pop -- rural density artifact"},
    {"County": "Washington", "Agencies_per_10K": None, "Status": "Missing",   "Notes": "Agency count not found"},
    {"County": "Dodge",      "Agencies_per_10K": None, "Status": "Missing",   "Notes": "Agency count not found"},
    {"County": "Rock",       "Agencies_per_10K": None, "Status": "Missing",   "Notes": "Agency count not found"},
])
_df_cc_agencies_sorted = pd.concat([
    _df_cc_agencies_raw[_df_cc_agencies_raw["Agencies_per_10K"].notna()].sort_values("Agencies_per_10K", ascending=True),
    _df_cc_agencies_raw[_df_cc_agencies_raw["Agencies_per_10K"].isna()],
]).reset_index(drop=True)

@lru_cache(maxsize=1)
def _get_fig_cc_agencies():
    bar_x, bar_colors, bar_text, y_labels, hover_notes = [], [], [], [], []
    for _, row in _df_cc_agencies_sorted.iterrows():
        y_labels.append(row["County"])
        hover_notes.append(row["Notes"])
        if row["Status"] == "Missing":
            bar_x.append(0.3); bar_colors.append("#5C5C5C"); bar_text.append("Data N/A")
        elif row["County"] == "Jefferson":
            bar_x.append(row["Agencies_per_10K"]); bar_colors.append(C_PRIMARY)
            bar_text.append(f"{row['Agencies_per_10K']:.2f}")
        elif row["County"] == "Bayfield":
            bar_x.append(row["Agencies_per_10K"]); bar_colors.append(C_MUTED)
            bar_text.append(f"{row['Agencies_per_10K']:.2f} (density artifact)")
        elif row["Status"] == "Estimated":
            bar_x.append(row["Agencies_per_10K"]); bar_colors.append(C_MUTED)
            bar_text.append(f"~{row['Agencies_per_10K']:.2f} est.")
        else:
            bar_x.append(row["Agencies_per_10K"]); bar_colors.append(C_MUTED)
            bar_text.append(f"{row['Agencies_per_10K']:.2f}")
    fig = go.Figure(go.Bar(
        x=bar_x, y=y_labels, orientation="h",
        marker_color=bar_colors, text=bar_text, textposition="outside",
        customdata=hover_notes,
        hovertemplate="<b>%{y}</b><br>Agencies/10K: %{x:.2f}<br>%{customdata}<extra></extra>",
    ))
    fig.add_vline(x=1.65, line_dash="dot", line_color=C_PRIMARY, line_width=1.5,
                  annotation_text="Jefferson 1.65", annotation_font_color=C_PRIMARY,
                  annotation_font_size=10, annotation_position="top right")
    fig.update_layout(
        title=dict(
            text="EMS Agencies per 10,000 Population -- Peer Counties<br>"
                 "<sup>Gray = data not available  \u00b7  Blue = Jefferson  "
                 "\u00b7  Bayfield high ratio is rural density artifact</sup>",
            font=dict(size=13),
        ),
        xaxis=dict(title="Agencies per 10,000 population", range=[0, 7.5],
                   gridcolor=C_BORDER, showline=False, zeroline=False, tickfont=dict(size=12, color=C_TEXT)),
    )
    _apply_chart_style(fig, height=360)
    fig.update_layout(margin=dict(l=100, r=100, t=70, b=40))
    return fig

# Panel 3C: Revenue recovery rates (all 10 Jefferson depts + Portage benchmarks)
_df_cc_recovery_raw = pd.DataFrame([
    {"Label": "Cambridge",            "Rate":  0.0, "Type": "Jefferson Dept",     "Note": "No billing program"},
    {"Label": "Edgerton",             "Rate":  0.0, "Type": "No Data",            "Note": "Partial budget only"},
    {"Label": "Lake Mills",           "Rate":  2.3, "Type": "Jefferson Dept",     "Note": "Ryan Brothers keeps billing"},
    {"Label": "Palmyra",              "Rate": 17.1, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Waterloo",             "Rate": 18.1, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Ixonia",               "Rate": 19.8, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Watertown",            "Rate": 21.3, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Whitewater",           "Rate": 23.1, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Johnson Creek",        "Rate": 25.4, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Portage Co. (current)","Rate": 35.0, "Type": "Portage Benchmark",  "Note": "Declining trend"},
    {"Label": "Jefferson City EMS",   "Rate": 48.8, "Type": "Jefferson Dept",     "Note": "Confirmed"},
    {"Label": "Portage Co. (10yr ago)","Rate": 49.0, "Type": "Portage Benchmark", "Note": "Historical high"},
    {"Label": "Fort Atkinson",        "Rate": 93.8, "Type": "Jefferson Dept",     "Note": "Self-sustaining"},
])
_df_cc_recovery_sorted = _df_cc_recovery_raw.sort_values("Rate", ascending=True).reset_index(drop=True)
_CC_RECOVERY_AGG = 26.8

_cc_rate_q = _df_cc_recovery_raw.loc[
    ~_df_cc_recovery_raw["Type"].isin(["No Data", "Portage Benchmark"]), "Rate"
].quantile([0.25, 0.75])

def _cc_bar_color(row):
    if row["Type"] == "No Data":           return "#5C5C5C"
    if row["Type"] == "Portage Benchmark": return "#A78BFA"
    if row["Rate"] >= _cc_rate_q[0.75]:    return C_GREEN
    if row["Rate"] >= _cc_rate_q[0.25]:    return C_PRIMARY
    return C_ORANGE

@lru_cache(maxsize=1)
def _get_fig_cc_recovery():
    df = _df_cc_recovery_sorted
    colors = [_cc_bar_color(row) for _, row in df.iterrows()]
    bar_text = []
    for _, row in df.iterrows():
        if row["Type"] == "No Data":            bar_text.append("N/A (partial budget)")
        elif row["Type"] == "Portage Benchmark":bar_text.append(f"{row['Rate']:.0f}% (Portage Co.)")
        else:                                   bar_text.append(f"{row['Rate']:.1f}%")
    fig = go.Figure(go.Bar(
        x=df["Rate"], y=df["Label"], orientation="h",
        marker_color=colors, text=bar_text, textposition="outside",
        customdata=df["Note"],
        hovertemplate="<b>%{y}</b><br>Recovery: %{x:.1f}%<br>%{customdata}<extra></extra>",
    ))
    fig.add_vline(x=_CC_RECOVERY_AGG, line_dash="dash", line_color=C_MUTED, line_width=2,
                  annotation_text=f"Jefferson Co. aggregate {_CC_RECOVERY_AGG}%",
                  annotation_font_color=C_MUTED, annotation_font_size=10, annotation_position="top right")
    fig.add_vline(x=80, line_dash="dot", line_color=C_GREEN, line_width=1.5,
                  annotation_text="Self-sustaining threshold 80%",
                  annotation_font_color=C_GREEN, annotation_font_size=10, annotation_position="top")
    for lbl, col in [("Above 80% (Self-sustaining)", C_GREEN), ("40-80% (Partial)", C_PRIMARY),
                     ("Below 40% (Tax-dependent)", C_ORANGE), ("Portage Co. Benchmark", "#A78BFA"),
                     ("Revenue N/A", "#5C5C5C")]:
        fig.add_trace(go.Bar(x=[None], y=[None], orientation="h",
                             marker_color=col, name=lbl, showlegend=True))
    fig.update_layout(
        title=dict(
            text="Revenue Recovery Rate: Jefferson County Departments + Portage Benchmark<br>"
                 "<sup>Green = self-sustaining (>80%)  \u00b7  Blue = partial (40-80%)  "
                 "\u00b7  Orange = tax-dependent (<40%)  \u00b7  Purple = Portage benchmark</sup>",
            font=dict(size=13),
        ),
        xaxis=dict(title="Revenue Recovery Rate (%)", ticksuffix="%", range=[0, 115],
                   gridcolor=C_BORDER, showline=False, zeroline=False, tickfont=dict(size=12, color=C_TEXT)),
        barmode="overlay",
    )
    _apply_chart_style(fig, height=540, legend_below=True, title_has_subtitle=True)
    fig.update_layout(margin=dict(l=170, r=80, t=85, b=100))
    return fig

_CC_RECOVERY_FOOTNOTE = (
    "Aggregate 26.8%: Edgerton expense ($704,977) is included in the denominator but "
    "EMS revenue is unknown (contributing $0 to numerator -- partial budget only). "
    "Excluding Edgerton from both sides yields 28.2%. "
    "Peer county revenue recovery data not available for Dodge, Rock, Walworth, or Washington. "
    "Open Records requests or WI EMS Data System (WEMSDS) query required."
)

# Panel 3D: Governance feature matrix
_df_cc_governance = pd.DataFrame([
    {"County": "Jefferson",  "EMS Coordinator": "No",          "County Levy": "No",            "Active Study": "Yes (Working Group, May 2025)", "Private EMS": "Yes (Ryan Brothers)", "Formal RT Stds": "No",      "Confidence": "Confirmed"},
    {"County": "Portage",    "EMS Coordinator": "Yes",          "County Levy": "Partial",       "Active Study": "Unknown",                       "Private EMS": "No",                  "Formal RT Stds": "Unknown", "Confidence": "Mixed"},
    {"County": "Bayfield",   "EMS Coordinator": "Yes ($145K)",  "County Levy": "Yes ($458K)",   "Active Study": "Yes (Advisory Committee)",      "Private EMS": "No",                  "Formal RT Stds": "Unknown", "Confidence": "Confirmed"},
    {"County": "Walworth",   "EMS Coordinator": "No",           "County Levy": "No ($400K cap)","Active Study": "Yes (WPF 2025 study)",          "Private EMS": "Yes (Delavan)",        "Formal RT Stds": "Unknown", "Confidence": "Confirmed"},
    {"County": "Washington", "EMS Coordinator": "No",           "County Levy": "No (proposed)", "Active Study": "Emerging",                      "Private EMS": "No (confirmed)",      "Formal RT Stds": "Unknown", "Confidence": "Confirmed"},
    {"County": "Dodge",      "EMS Coordinator": "No",           "County Levy": "No",            "Active Study": "No",                            "Private EMS": "Unknown",             "Formal RT Stds": "Unknown", "Confidence": "Estimated"},
    {"County": "Rock",       "EMS Coordinator": "No",           "County Levy": "No",            "Active Study": "No",                            "Private EMS": "Yes (Mercy Health)",  "Formal RT Stds": "Unknown", "Confidence": "Estimated"},
])
_GOV_YES_COLS = ["EMS Coordinator", "County Levy", "Active Study", "Private EMS", "Formal RT Stds"]
_CC_GOVERNANCE_COND = _DT_STYLE_DATA_CONDITIONAL_BASE + [
    {"if": {"filter_query": '{County} = "Jefferson"'}, "fontWeight": "600", "color": C_PRIMARY},
]

# ── Cross-County Asset Comparison (Section 19b) ─────────────────────────────
# Jefferson ambulance total from MABAS data; peer county figures from secondary
# research or marked "Unknown". Ambulances-per-10K derived from totals.
_JEFF_TOTAL_AMBULANCES = int(ASSET_DATA["Ambulances"].sum())
_JEFF_TOTAL_APPARATUS  = int(ASSET_DATA[["Engines","Trucks_Ladders","Squads_Rescues",
                                         "Tenders","Brush_ATV","Boats","Ambulances"]].sum().sum())
_JEFF_EMS_PERSONNEL    = int(ASSET_DATA["EMS_Personnel"].sum())

_df_cc_assets = pd.DataFrame([
    {"County": "Jefferson",  "Population": 84700,  "Ambulances": _JEFF_TOTAL_AMBULANCES,
     "Total_Apparatus": _JEFF_TOTAL_APPARATUS, "EMS_Personnel": _JEFF_EMS_PERSONNEL,
     "Status": "Confirmed", "Notes": f"MABAS Div 118: {_JEFF_TOTAL_AMBULANCES} ambulances across 14 depts"},
    {"County": "Portage",    "Population": 70700,  "Ambulances": None,
     "Total_Apparatus": None, "EMS_Personnel": None,
     "Status": "Missing", "Notes": "Consolidated county EMS — fleet data not public"},
    {"County": "Bayfield",   "Population": 15800,  "Ambulances": None,
     "Total_Apparatus": None, "EMS_Personnel": None,
     "Status": "Missing", "Notes": "9 agencies; individual fleet data not available"},
    {"County": "Walworth",   "Population": 105000, "Ambulances": None,
     "Total_Apparatus": None, "EMS_Personnel": None,
     "Status": "Missing", "Notes": "15 departments; WPF study does not include fleet data"},
    {"County": "Washington", "Population": 140000, "Ambulances": None,
     "Total_Apparatus": None, "EMS_Personnel": None,
     "Status": "Missing", "Notes": "Agency count unknown; fleet data not found"},
    {"County": "Dodge",      "Population": 90000,  "Ambulances": None,
     "Total_Apparatus": None, "EMS_Personnel": None,
     "Status": "Missing", "Notes": "Agency count unknown; fleet data not found"},
    {"County": "Rock",       "Population": 165000, "Ambulances": None,
     "Total_Apparatus": None, "EMS_Personnel": None,
     "Status": "Missing", "Notes": "Hospital-based EMS; fleet data not public"},
])
_df_cc_assets["Amb_per_10K"] = (_df_cc_assets["Ambulances"] / _df_cc_assets["Population"] * 10000).round(2)

@lru_cache(maxsize=1)
def _get_fig_cc_assets():
    """Cross-county asset comparison: Jefferson vs. peer counties."""
    # ── Chart 1: Jefferson internal ambulance distribution (by municipality) ──
    ad = ASSET_DATA[ASSET_DATA["Ambulances"] > 0].sort_values("Ambulances", ascending=True)
    fig_internal = go.Figure()
    fig_internal.add_trace(go.Bar(
        y=ad["Municipality"], x=ad["Ambulances"],
        orientation="h", marker_color=C_PRIMARY,
        text=ad["Ambulances"], textposition="outside",
        customdata=ad[["Ambulance_Detail"]].values,
        hovertemplate="<b>%{y}</b><br>Ambulances: %{x}<br>%{customdata[0]}<extra></extra>",
    ))
    fig_internal.update_layout(
        title=f"Jefferson County Ambulance Distribution ({_JEFF_TOTAL_AMBULANCES} Total)<br>"
              f"<sup>9 EMS-transporting departments — MABAS Division 118</sup>",
        xaxis_title="Ambulances", yaxis_title="",
    )
    _apply_chart_style(fig_internal, height=380, title_has_subtitle=True)
    fig_internal.update_layout(margin=dict(l=120, r=60, t=70, b=30))

    # ── Chart 2: Jefferson fleet composition breakdown (county-level donut) ───
    cats = ["Engines", "Trucks_Ladders", "Squads_Rescues", "Tenders", "Brush_ATV", "Boats", "Ambulances"]
    cat_labels = ["Engines", "Trucks/Ladders", "Squads/Rescues", "Tenders", "Brush/ATV", "Boats", "Ambulances"]
    cat_colors = [C_RED, C_YELLOW, "#60A5FA", C_GREEN, "#A78BFA", "#06B6D4", C_PRIMARY]
    totals = [int(ASSET_DATA[c].sum()) for c in cats]
    fig_comp = go.Figure(go.Pie(
        labels=cat_labels, values=totals,
        marker=dict(colors=cat_colors),
        textinfo="label+value",
        hovertemplate="<b>%{label}</b><br>Units: %{value}<br>%{percent}<extra></extra>",
        hole=0.4,
    ))
    fig_comp.update_layout(
        title=f"Jefferson County Fleet Composition ({_JEFF_TOTAL_APPARATUS} Total Units)<br>"
              f"<sup>All apparatus across 14 departments — MABAS Division 118</sup>",
    )
    _apply_chart_style(fig_comp, height=380, legend_below=True, title_has_subtitle=True)
    fig_comp.update_layout(margin=dict(l=20, r=20, t=70, b=60))

    # ── KPI summary data ────────────────────────────────────────────────────
    jeff_amb_per_10k = _JEFF_TOTAL_AMBULANCES / 84700 * 10000
    jeff_pers_per_10k = _JEFF_EMS_PERSONNEL / 84700 * 10000
    kpis = {
        "ambulances": str(_JEFF_TOTAL_AMBULANCES),
        "apparatus": str(_JEFF_TOTAL_APPARATUS),
        "ems_personnel": str(_JEFF_EMS_PERSONNEL),
        "amb_per_10k": f"{jeff_amb_per_10k:.1f}",
        "pers_per_10k": f"{jeff_pers_per_10k:.1f}",
        "depts_with_ambulances": str(int((ASSET_DATA["Ambulances"] > 0).sum())),
        "depts_without": str(int((ASSET_DATA["Ambulances"] == 0).sum())),
    }
    return fig_internal, fig_comp, kpis


# ── Tab styling ──────────────────────────────────────────────────────────────
_TAB_STYLE = {
    "padding": "10px 18px", "fontFamily": FONT_STACK, "fontSize": "0.82rem",
    "fontWeight": "600", "color": "rgba(255,255,255,0.6)",
    "backgroundColor": C_NAVY, "border": "none",
    "borderBottom": "3px solid transparent", "cursor": "pointer",
}
_TAB_SELECTED_STYLE = {
    **_TAB_STYLE, "color": C_PRIMARY,
    "borderBottom": f"3px solid {C_PRIMARY}", "backgroundColor": C_NAVY,
}
_FOOTER = html.Div(
    "Jefferson County EMS Study  |  UW-Madison ISyE 450  |  2026",
    style={"textAlign": "center", "padding": "24px", "color": C_MUTED,
           "fontSize": "0.78rem", "fontFamily": FONT_STACK,
           "borderTop": f"1px solid {C_BORDER}", "marginTop": "4px"})

app.layout = html.Div([

    # ── Sidebar ──────────────────────────────────────────────────────────────
    html.Div([
        # Sidebar header block
        html.Div([
            html.Div("JC EMS", style={
                "fontSize": "1.25rem", "fontWeight": "700", "color": "white",
                "letterSpacing": "0.02em",
            }),
            html.Div("Jefferson County", style={
                "fontSize": "0.75rem", "color": "rgba(255,255,255,0.5)",
                "marginTop": "2px",
            }),
        ], style={
            "padding": "22px 18px 18px",
            "borderBottom": "1px solid rgba(255,255,255,0.1)",
            "marginBottom": "16px",
        }),

        # ---- Department filter (Overview, Call Analysis, Response Times) ----
        html.Div([
            html.Div("DEPARTMENTS", style={
                "fontSize": "0.65rem", "fontWeight": "700", "color": "rgba(255,255,255,0.4)",
                "letterSpacing": "0.1em", "padding": "0 18px 8px",
            }),
            dcc.Checklist(
                id="dept-filter",
                options=[{"label": d, "value": d} for d in ALL_DEPTS],
                value=ALL_DEPTS,
                labelStyle={
                    "display": "block", "padding": "3px 0",
                    "fontSize": "0.81rem", "color": "rgba(255,255,255,0.85)",
                },
                inputStyle={"marginRight": "7px", "accentColor": C_PRIMARY},
                style={"padding": "0 18px"},
            ),
            html.Div(style={"borderTop": "1px solid rgba(255,255,255,0.1)", "margin": "16px 0"}),
        ], id="sidebar-dept-section"),

        # ---- Map metric selector (Overview only) ----
        html.Div([
            html.Div("MAP METRIC", style={
                "fontSize": "0.65rem", "fontWeight": "700", "color": "rgba(255,255,255,0.4)",
                "letterSpacing": "0.1em", "padding": "0 18px 8px",
            }),
            dcc.RadioItems(
                id="map-metric",
                options=[
                    {"label": "Total Calls",    "value": "total_calls"},
                    {"label": "EMS Calls",      "value": "ems_calls"},
                    {"label": "Median RT",      "value": "median_rt"},
                    {"label": "P90 RT",         "value": "p90_rt"},
                    {"label": "Ambulances",     "value": "ambulances"},
                    {"label": "EMS Personnel",  "value": "ems_personnel"},
                ],
                value="total_calls",
                labelStyle={
                    "display": "block", "padding": "4px 0",
                    "fontSize": "0.81rem", "color": "rgba(255,255,255,0.85)",
                },
                inputStyle={"marginRight": "7px", "accentColor": C_PRIMARY},
                style={"padding": "0 18px"},
            ),
            html.Div(style={"borderTop": "1px solid rgba(255,255,255,0.1)", "margin": "16px 0"}),
        ], id="sidebar-map-metric-section"),

        # ---- Map layers toggle (Overview only) ----
        html.Div([
            html.Div("MAP LAYERS", style={
                "fontSize": "0.65rem", "fontWeight": "700", "color": "rgba(255,255,255,0.4)",
                "letterSpacing": "0.1em", "padding": "0 18px 8px",
            }),
            dcc.Checklist(
                id="map-layers",
                options=[
                    {"label": "Municipal Boundaries",  "value": "muni"},
                    {"label": "Fire Districts (reference only)",  "value": "fire"},
                    {"label": "Stations (FD/PD/EMS)", "value": "stations"},
                    {"label": "Helenville 1st Resp.", "value": "helenville"},
                    {"label": "ZIP Code Boundaries", "value": "zcta"},
                ],
                value=[],
                labelStyle={
                    "display": "block", "padding": "3px 0",
                    "fontSize": "0.81rem", "color": "rgba(255,255,255,0.85)",
                },
                inputStyle={"marginRight": "7px", "accentColor": C_PRIMARY},
                style={"padding": "0 18px"},
            ),
            html.Div(style={"borderTop": "1px solid rgba(255,255,255,0.1)", "margin": "16px 0"}),
        ], id="sidebar-map-layers-section"),

        # ---- Dynamic filter applicability note ----
        html.Div(id="sidebar-filter-note", style={
            "fontSize": "0.7rem", "color": "rgba(255,255,255,0.35)",
            "padding": "0 18px", "lineHeight": "1.5",
        }),
    ], style=SIDEBAR_STYLE),

    # ── Main content ─────────────────────────────────────────────────────────
    html.Div([

        # ── Top header bar ────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Jefferson County EMS Dashboard", style={
                    "fontSize": "1.2rem", "fontWeight": "700", "color": "white",
                    "fontFamily": FONT_STACK,
                }),
                html.Div("EMS System Data Review  |  2024 NFIRS Data  |  FY2025 Budgets", style={
                    "fontSize": "0.75rem", "color": "rgba(255,255,255,0.55)",
                    "marginTop": "2px", "fontFamily": FONT_STACK,
                }),
            ]),
        ], style={
            "background": C_NAVY,
            "padding": "16px 28px",
            "borderBottom": f"3px solid {C_PRIMARY}",
        }),

        # ── Tab bar ──────────────────────────────────────────────────────────
        dcc.Tabs(
            id="main-tabs",
            value="tab-overview",
            children=[
                dcc.Tab(label="Overview",             value="tab-overview",   style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
                dcc.Tab(label="Call Analysis",         value="tab-calls",     style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
                dcc.Tab(label="Response Times",        value="tab-rt",        style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
                dcc.Tab(label="Financials & Staffing", value="tab-finance",   style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
                dcc.Tab(label="County Comparison",      value="tab-benchmark", style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
                dcc.Tab(label="Contracts & Legal",     value="tab-contracts", style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
                dcc.Tab(label="Secondary Network Sim", value="tab-simulation", style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE),
            ],
            style={"backgroundColor": C_NAVY, "borderBottom": "none"},
            colors={"border": "transparent", "primary": C_PRIMARY, "background": C_NAVY},
        ),

        # ── Tab content ──────────────────────────────────────────────────────
        dcc.Loading(
            html.Div(id="tab-content", style={"padding": "24px 28px", "overflowY": "auto"}),
            type="dot", color=C_PRIMARY,
        ),

        _FOOTER,

    ], style=CONTENT_STYLE),

], style={
    "display": "flex",
    "minHeight": "100vh",
    "fontFamily": FONT_STACK,
    "background": C_BG,
})


# ── 9. Callbacks ───────────────────────────────────────────────────────────────

def filter_raw(depts):
    return raw[raw["Department"].isin(depts)]

def filter_rt(depts):
    return rt_clean[rt_clean["Department"].isin(depts)]


# ── Sidebar visibility callback — show/hide sections based on active tab ────
# Tabs that use the dept filter: Overview, Call Analysis, Response Times
# Tabs that use map controls: Overview only
# Static tabs (Financials, Cross-County, Contracts, Recommendations): no sidebar filters
_DEPT_FILTER_TABS = {"tab-overview", "tab-calls", "tab-rt"}
_MAP_CONTROL_TABS = {"tab-overview"}

@app.callback(
    Output("sidebar-dept-section",        "style"),
    Output("sidebar-map-metric-section",  "style"),
    Output("sidebar-map-layers-section",  "style"),
    Output("sidebar-filter-note",         "children"),
    Input("main-tabs", "value"),
)
def update_sidebar_visibility(tab):
    _show = {"display": "block"}
    _hide = {"display": "none"}

    show_dept = _show if tab in _DEPT_FILTER_TABS else _hide
    show_map  = _show if tab in _MAP_CONTROL_TABS else _hide

    if tab in _MAP_CONTROL_TABS:
        note = [html.Span("Active: ", style={"fontWeight": "600"}),
                "Department filter + Map controls"]
    elif tab in _DEPT_FILTER_TABS:
        note = [html.Span("Active: ", style={"fontWeight": "600"}),
                "Department filter only"]
    else:
        note = [html.Span("No filters ", style={"fontWeight": "600"}),
                "for this tab"]

    return show_dept, show_map, show_map, note


# ── Tab render callback ─────────────────────────────────────────────────────
@app.callback(Output("tab-content", "children"), Input("main-tabs", "value"))
def render_tab(tab):
    if tab == "tab-overview":
        return html.Div([
            html.Div(id="kpi-row", style={
                "display": "flex", "gap": "14px", "flexWrap": "wrap", "marginBottom": "20px"}),
            # Map
            html.Div([
                _section_header("Jefferson County EMS District Map — 2024 NFIRS Data"),
                html.P(["Colored polygons = municipal boundaries (Census). ",
                         html.B("Cyan dashed outlines = EMS service districts"),
                         " (authoritative — differ from fire districts). "
                         "Toggle overlay layers in sidebar."],
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 12px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                html.Div([
                    dl.Map(id="leaflet-map", center=[43.02, -88.78], zoom=10,
                        trackViewport=True,
                        style={"width": "100%", "height": "580px", "borderRadius": "8px"},
                        children=[
                            dl.TileLayer(
                                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>'),
                            dl.GeoJSON(id="map-geojson", data=geojson_data,
                                options=dict(style=_geojson_style),
                                zoomToBoundsOnClick=True,
                                hideout={"showMuniBorders": False},
                                hoverStyle={"weight": 2, "color": C_PRIMARY, "fillOpacity": 0.1}),
                            dl.GeoJSON(id="map-ems-choropleth", data=geojson_ems_districts,
                                options=dict(style=_ems_district_style,
                                             onEachFeature=_ems_district_label),
                                hideout={"colorMap": _compute_color_map("total_calls")},
                                hoverStyle={"weight": 4, "fillOpacity": 0.6}),
                            dl.LayerGroup(id="map-layer-fire", children=[]),
                            dl.LayerGroup(id="map-layer-stations", children=[]),
                            dl.LayerGroup(id="map-layer-helenville", children=[]),
                            dl.LayerGroup(id="map-layer-zcta", children=[]),
                            dl.LayerGroup(id="map-markers"),
                        ]),
                    html.Div(id="zoom-badge", children="Department View", style={
                        "position": "absolute", "top": "10px", "right": "60px", "zIndex": "1000",
                        "background": "rgba(255,255,255,0.92)", "padding": "4px 12px",
                        "borderRadius": "4px", "fontSize": "11px", "fontWeight": "600",
                        "fontFamily": FONT_STACK, "boxShadow": "0 1px 4px rgba(0,0,0,.18)",
                        "color": C_PRIMARY, "border": "1px solid rgba(0,0,0,0.08)"}),
                    html.Div(id="map-legend", style={
                        "position": "absolute", "bottom": "16px", "left": "16px", "zIndex": "1000",
                        "background": C_CARD, "padding": "8px 14px", "borderRadius": "6px",
                        "boxShadow": "0 2px 8px rgba(0,0,0,.4)", "fontFamily": FONT_STACK,
                        "fontSize": "11px", "color": C_TEXT}),
                ], style={"position": "relative"}),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                    "jefferson_county.geojson (Census TIGER 2023 boundaries)",
                    "EMS district boundaries: Jefferson County GIS / ArcGIS Public Safety (authoritative — fire districts differ)",
                    "FY2025 municipal budget documents (station locations & staffing)",
                ),
            ], style=CARD),
            # Municipal KPI Table
            html.Div([
                _section_header("Full Municipal KPI Table — 2024 NFIRS Data"),
                dash_table.DataTable(
                    id="kpi-table",
                    columns=[{"name": c, "id": c} for c in muni_kpi.columns],
                    data=muni_kpi.to_dict("records"),
                    sort_action="native", filter_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER, style_cell=_DT_STYLE_CELL,
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE,
                    page_size=20),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                    "county_ems_comparison_data.xlsx — Jeff_Municipal_Breakdown sheet",
                ),
            ], style=CARD),
        ])

    elif tab == "tab-calls":
        return html.Div([
            html.Div([
                _section_header("Call Volume — 2024 NFIRS Data"),
                # Row 1: EMS call volume — full width so all depts are readable
                dcc.Graph(id="vol-bar"),
                # Row 2: population-normalized — full width; Western Lakes bar is capped for readability
                _sub_header("EMS Calls per 1,000 Population"),
                dcc.Graph(id="vol-norm-bar"),
                # Row 3: Cost per EMS call
                _sub_header("Cost per EMS Call"),
                dcc.Graph(id="ems-pct-bar"),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                    "Emergency Services Population - Jefferson County.xlsx (WI DOA 2025 — service area populations)",
                    "Call Volumes - Jefferson County EMS.xlsx (authoritative 2024 EMS call counts)",
                    ("WI statewide calls/1K benchmark — Northwestern EMS", "https://northwesternems.org/ems-in-wisconsin"),
                ),
            ], style=CARD),
            html.Div([
                _section_header("Temporal Call Patterns — 2024 NFIRS Data"),
                html.Div([
                    dcc.Graph(id="heat-hour", style={"flex": "1"}),
                    dcc.Graph(id="heat-dow", style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                dcc.Graph(id="monthly-trend"),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Mutual Aid Activity — 2024 NFIRS Data"),
                dcc.Graph(id="aid-bar"),
                _sub_header("Mutual Aid Dependency Ratio — Aid as % of Total Calls"),
                html.P(
                    "Departments above 20% received aid are structurally dependent on neighbors. "
                    "Ratios computed as aid events \u00f7 total calls per department.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 12px",
                           "fontFamily": FONT_STACK},
                ),
                dcc.Graph(id="aid-ratio-bar"),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Multi-Provider Coverage Areas — Jefferson County Towns"),
                html.P(
                    "Several rural towns are served by multiple EMS providers, with population "
                    "allocated proportionally by coverage area. Overlap areas represent mutual aid "
                    "corridors and coordination challenges.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 12px",
                           "fontFamily": FONT_STACK}),
                dcc.Graph(id="coverage-overlap-bar"),
                _source_citation(
                    "Emergency Services Population - Jefferson County.xlsx (new3.31.26/)",
                    "WI DOA Preliminary 2025 Estimates — Raw Data sheet",
                ),
            ], style=CARD),
        ])

    elif tab == "tab-rt":
        return html.Div([
            html.Div([
                _section_header("Response Times — 2024 NFIRS Data"),
                html.P(
                    "Top row: all incident types (fire, EMS, other). "
                    "Bottom row: EMS calls only with NFPA 1710/1720 benchmark lines. "
                    "RT capped 0–60 min.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 12px",
                           "fontFamily": FONT_STACK}),
                html.Div([
                    dcc.Graph(id="rt-percentile-bar", style={"flex": "1"}),
                    dcc.Graph(id="rt-box", style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                _sub_header("EMS-Only Response Times — NFPA Benchmarks"),
                html.Div([
                    dcc.Graph(id="rt-ems-percentile-bar", style={"flex": "1"}),
                    dcc.Graph(id="rt-ems-box",            style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                    "county_ems_comparison_data.xlsx — Jeff_Response_Percentiles sheet",
                    ("NFPA 1710 Standard (Career)", "https://www.emergent.tech/blog/nfpa-1710-response-times"),
                    ("NFPA 1720 Standard (Volunteer)", "https://www.firehouse.com/careers-education/article/21238058/nfpa-standards-nfpa-1720-an-update-on-the-volunteer-deployment-standard"),
                ),
            ], style=CARD),
            html.Div([
                _section_header("Individual Department Drill-Down"),
                html.P("Select a department to view its full operational profile.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 12px",
                           "fontFamily": FONT_STACK}),
                dcc.Dropdown(
                    id="dept-drilldown",
                    options=[{"label": d, "value": d} for d in sorted(raw["Department"].unique())],
                    value="Watertown", clearable=False,
                    style={"width": "320px", "marginBottom": "16px",
                           "fontFamily": FONT_STACK, "fontSize": "0.88rem"}),
                html.Div(id="drilldown-kpi-row",
                    style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"}),
                html.Div([
                    dcc.Graph(id="drilldown-als-bls", style={"flex": "0 0 300px", "maxWidth": "320px"}),
                    dcc.Graph(id="drilldown-rt-hist", style={"flex": "1"}),
                    dcc.Graph(id="drilldown-hour-bar", style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),
                dcc.Graph(id="drilldown-monthly"),
                html.Div(id="drilldown-high-freq"),
                html.Div(id="drilldown-data-quality"),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (ISyE Project/Data and Resources/Call Data/) + Megan 2026-04-19 geo corrections",
                    "FY2025 municipal budget documents (per-department staffing & financials)",
                    "Looker Studio PDF reports (2024) — ALS/BLS action-type breakdowns, high-frequency addresses",
                ),
            ], style=CARD),
        ])

    elif tab == "tab-finance":
        # Cache the result once so all 4 figures come from the same lru_cache call.
        _bf = _get_budget_figs()
        # Shared graph config: hide mode bar to reclaim top-right space; respond to
        # container resize so side-by-side charts fill their flex cells equally.
        _g_cfg = {"displayModeBar": False, "responsive": True}
        # flex: "1 1 0" + minWidth: 0 prevents flexbox overflow on narrow screens.
        _g_style = {"flex": "1 1 0", "minWidth": 0}
        return html.Div([
            html.Div([
                _section_header("Budget & Billing Rates — FY2025 Budget"),
                # Sankey diagram — full width
                dcc.Graph(id="budget-bar", figure=_bf[0], config=_g_cfg),
                # Funding gap breakdown — table only (bar removed per user request; table is sufficient)
                dash_table.DataTable(
                    id="funding-gap-table",
                    columns=[
                        {"name": "Department",       "id": "Department"},
                        {"name": "Gap Amount",       "id": "Gap Amount"},
                        {"name": "How They Cover It", "id": "How They Cover It"},
                    ],
                    data=_bf[5],
                    style_table={"overflowX": "auto", "marginTop": "-8px",
                                 "marginBottom": "24px"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "whiteSpace": "normal", "height": "auto"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE,
                    style_cell_conditional=[
                        {"if": {"column_id": "Gap Amount"},
                         "fontWeight": "bold", "textAlign": "right", "width": "120px"},
                        {"if": {"column_id": "Department"},
                         "width": "130px"},
                    ],
                ),
                # Billing rates chart
                dcc.Graph(id="billing-bar", figure=_bf[1], config=_g_cfg),
                # Row 2: Cost per call (10 depts, model-colored) + Expense per capita (10 depts).
                # Both figures are height=540.
                html.Div([
                    dcc.Graph(id="cost-per-call-bar",      figure=_bf[2],
                              config=_g_cfg, style=_g_style),
                    dcc.Graph(id="expense-per-capita-bar", figure=_bf[3],
                              config=_g_cfg, style=_g_style),
                ], style={"display": "flex", "gap": "16px", "alignItems": "flex-start"}),
                _source_citation(
                    "FY2025 municipal budget documents (11 municipalities)",
                    "2025 fee schedules — Jefferson, Fort Atkinson, Watertown (confirmed); "
                    "11 of 14 depts do not publish rates (web search Mar 2026 — see methodology note below)",
                    "WI peer benchmarks: Waukesha (waukesha-wi.gov), Fitch-Rona (fitchronaems.com), "
                    "Madison (cityofmadison.com), Richfield (richfieldwi.gov), Brookfield (ci.brookfield.wi.us)",
                    "2024 NFIRS call volumes for cost-per-call calculation",
                    "Emergency Services Population - Jefferson County.xlsx (WI DOA 2025 — service area populations)",
                    ("Northwestern EMS — WI avg EMS user fee $36/capita", "https://northwesternems.org/ems-in-wisconsin"),
                ),
                html.Div([
                    html.Span("Billing Rate Data Gap — ", style={
                        "fontWeight": "700", "color": C_YELLOW, "fontSize": "11px",
                        "fontFamily": FONT_STACK}),
                    html.Span(
                        "Systematic web search (Mar 2026) for all 11 missing Jefferson Co. dept billing rates "
                        "returned zero results — small WI fire departments do not publish fee schedules online. "
                        "Municipal fee schedules, board minutes, budget documents, and statewide surveys were "
                        "checked for each department individually. No WI statewide EMS billing rate database exists. "
                        "Data collection path: direct request from fire chiefs or batch Open Records requests. "
                        "EMS|MC (shared billing vendor for several depts) may also have consolidated rate data.",
                        style={"color": C_MUTED, "fontSize": "11px", "fontFamily": FONT_STACK}),
                ], style={"marginTop": "12px", "padding": "8px 12px",
                          "backgroundColor": "#2A2000", "borderRadius": "6px",
                          "border": f"1px solid {C_YELLOW}33"}),
            ], style=CARD),
            html.Div([
                _section_header("Inter-Municipal EMS Contract Payments"),
                html.P(
                    "How towns pay neighboring municipalities for fire/EMS coverage. "
                    "Contract structures vary widely: some use per-capita rates, others use "
                    "equalized improvement value formulas. Red bars indicate expired contracts.",
                    style={"fontSize": "0.82rem", "color": C_MUTED, "margin": "0 0 14px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                html.Div([
                    dcc.Graph(id="contract-rev-bar", figure=_get_contract_figs()[0], style={"flex": "1"}),
                    dcc.Graph(id="contract-percap-bar", figure=_get_contract_figs()[1], style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                _sub_header("All 17 Contract Details"),
                dash_table.DataTable(
                    id="contract-detail-table",
                    columns=_get_contract_figs()[2],
                    data=_get_contract_figs()[3],
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px",
                                "whiteSpace": "normal", "height": "auto",
                                "maxWidth": "280px"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE,
                ),
                html.Div([
                    html.Span("Data Gaps (research TODO): ", style={
                        "fontWeight": "700", "color": C_YELLOW, "fontSize": "11px",
                        "fontFamily": FONT_STACK}),
                    html.Span(
                        "Missing contracts: Cambridge, Palmyra, Whitewater, Western Lakes "
                        "(no IGAs in file base — Open Records requests needed). "
                        "Ixonia IGA found ($49,169/yr to Town of Watertown; extension to 2027 unconfirmed). "
                        "Fort Atkinson contracts EXPIRED Dec 2025 (no auto-renew; active renegotiation). "
                        "Waterloo likely auto-renewed 2026 at $26/capita. "
                        "Billing rates: 11 of 14 depts unpublished — not available via web search.",
                        style={"color": C_MUTED, "fontSize": "11px", "fontFamily": FONT_STACK}),
                ], style={"marginTop": "12px", "padding": "8px 12px",
                          "backgroundColor": "#2A2000", "borderRadius": "6px",
                          "border": f"1px solid {C_YELLOW}33"}),
                _source_citation(
                    "EMS Contract Details for all Towns in Jefferson County.xlsx "
                    "(ISyE Project/Data and Resources/)",
                    "Payment amounts extracted from free-text contract descriptions in source file",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Staffing & Service Level Overview — FY2025 Budget"),
                html.Div([
                    dcc.Graph(id="staffing-bar", figure=_get_staffing_figs()[0], style={"flex": "1"}),
                    dcc.Graph(id="model-pie", figure=_get_staffing_figs()[1], style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                _sub_header("ALS / BLS Service Level by Department"),
                html.P("Confidence: High = official source; Medium = inferred; Low = uncertain.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 8px",
                           "lineHeight": "1.5", "fontFamily": FONT_STACK}),
                dcc.Graph(id="als-level-chart", figure=_get_als_fig()),
                _source_citation(
                    "FY2025 municipal budget documents (staffing counts & service models)",
                    "Department websites & WI EMS Association (ALS/BLS levels)",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Utilization Analysis — Call Volume vs. Financials vs. Assets"),
                html.P("Derived metrics combining 2024 NFIRS data with FY2025 budgets. "
                       "Outlier flags highlight departments with significant inefficiency.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 16px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                html.Div([
                    dcc.Graph(id="util-cost-per-call", figure=_get_utilization_figs()[0], style={"flex": "1"}),
                    dcc.Graph(id="util-revenue-recovery", figure=_get_utilization_figs()[1], style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),
                html.Div([
                    dcc.Graph(id="util-tax-per-call", figure=_get_utilization_figs()[2], style={"flex": "1"}),
                    dcc.Graph(id="util-calls-per-ft", figure=_get_utilization_figs()[3], style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),
                _sub_header("Population-Normalized Metrics — Per-Capita & Per-1K Resident View"),
                html.P(
                    "Per-capita normalization adjusts for service area size, allowing apples-to-apples "
                    "comparison between small rural departments and larger city departments. "
                    "Population figures from WI DOA Preliminary 2025 Estimates (Emergency Services Population spreadsheet).",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 12px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK},
                ),
                html.Div([
                    dcc.Graph(id="util-tax-per-capita", figure=_get_utilization_figs()[7], style={"flex": "1"}),
                    dcc.Graph(id="util-calls-per-1k",   figure=_get_utilization_figs()[8], style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),
                dcc.Graph(id="util-model-bubble", figure=_get_utilization_figs()[4], style={"marginBottom": "16px"}),
                _source_citation(
                    "2024 NFIRS — 14 department Excel files (call volumes)",
                    "FY2025 municipal budget documents (financials & staffing)",
                    "utilization_analysis.md (derived metrics & outlier methodology)",
                    ("WI DOA 2025 Preliminary Municipal Estimates (service area populations)", "https://doa.wi.gov/DIR/Final_Ests_Muni_2025.xlsx"),
                    ("Northwestern EMS \u2014 WI avg EMS user fee $36/capita & 254 transports/1K", "https://northwesternems.org/ems-in-wisconsin"),
                ),
            ], style=CARD),
            html.Div([
                _section_header("Municipal Asset & Equipment Comparison — MABAS Division 118"),
                html.P("Apparatus inventories compiled from official MABAS Division 118 FD Resource Lists "
                       "filed by each Jefferson County fire/EMS department. Ambulance age analysis limited "
                       "to units with known model year.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 16px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                _sub_header("Ambulance Utilization Summary"),
                html.Div([
                    kpi_card("Total Ambulances",
                             _get_asset_figs()[8]["total_ambulances"],
                             f"{_get_asset_figs()[8]['n_depts_with_amb']} departments operate ambulances",
                             C_PRIMARY),
                    kpi_card("Avg Calls / Ambulance",
                             _get_asset_figs()[8]["avg_calls_per_amb"],
                             "County average — 2024 NFIRS EMS calls",
                             C_YELLOW),
                    kpi_card("County Amb / 10K Pop",
                             _get_asset_figs()[8]["county_amb_per_10k"],
                             f"Jefferson Co. ({_BENCH['jeff_county_pop']:,} residents)",
                             C_GREEN),
                ], style={"display": "flex", "gap": "14px", "flexWrap": "wrap", "marginBottom": "20px"}),
                html.Div([
                    dcc.Graph(id="asset-calls-per-amb", figure=_get_asset_figs()[6],
                              config={"displayModeBar": False, "responsive": True},
                              style={"flex": "1 1 0", "minWidth": 0}),
                    dcc.Graph(id="asset-amb-per-10k", figure=_get_asset_figs()[7],
                              config={"displayModeBar": False, "responsive": True},
                              style={"flex": "1 1 0", "minWidth": 0}),
                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),
                dcc.Graph(id="asset-ambulance-bar", figure=_get_asset_figs()[0], style={"marginBottom": "16px"}),
                dcc.Graph(id="asset-age-scatter", figure=_get_asset_figs()[2], style={"marginBottom": "16px"}),
                dcc.Graph(id="asset-personnel-bar", figure=_get_asset_figs()[3], style={"marginBottom": "16px"}),
                _sub_header("Full Apparatus Inventory Table"),
                dash_table.DataTable(
                    id="asset-summary-table",
                    data=_get_asset_figs()[4],
                    columns=_get_asset_figs()[5],
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px",
                                "whiteSpace": "normal", "height": "auto", "textAlign": "center"},
                    style_cell_conditional=[
                        {"if": {"column_id": "Municipality"}, "textAlign": "left", "fontWeight": "600"},
                    ],
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE,
                ),
                _sub_header("Ambulance Replacement Priority — Units Past End-of-Life"),
                dash_table.DataTable(
                    id="amb-replace-priority",
                    columns=[{"name": c, "id": c} for c in _AMBULANCE_REPLACE_PRIORITY.columns],
                    data=_AMBULANCE_REPLACE_PRIORITY.to_dict("records"),
                    style_table={"overflowX": "auto", "borderRadius": "8px",
                                 "overflow": "hidden", "marginBottom": "20px"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "whiteSpace": "normal", "height": "auto"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE),
                _source_citation(
                    "MABAS_Assets/*.xlsx — 14 MABAS Division 118 FD Resource Lists (apparatus inventories)",
                    "2024 NFIRS call data (EMS call volumes for utilization metrics)",
                    ("WI DOA 2025 Preliminary Estimates — service area populations", "Emergency Services Population - Jefferson County.xlsx"),
                    "Ambulance end-of-life standard: 15-year / 250,000 mi (ASCO/NHTSA industry guideline)",
                ),
            ], style=CARD),
            # ── NEW: Actual Billing Collections (Chief Association Data) ──────
            html.Div([
                _section_header("Actual Billing Collections — Chief Association Agency Data"),
                html.P(
                    "Net collections reported by 9 of 12 EMS agencies through the Jefferson County "
                    "Chief Association. These are actual amounts collected by billing vendors, not budget "
                    "estimates. Missing: Cambridge, Western Lakes, Whitewater.",
                    style={"fontSize": "0.82rem", "color": C_MUTED, "margin": "0 0 14px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                dcc.Graph(id="billing-collections-bar",
                    figure=_get_billing_collections_fig(), config={"displayModeBar": False}),
                _sub_header("Year-over-Year Change — All 9 Agencies Grew Revenue"),
                dcc.Graph(id="billing-change-bar",
                    figure=_get_billing_change_fig(), config={"displayModeBar": False}),
                _sub_header("Collections Detail Table"),
                dash_table.DataTable(
                    id="billing-collections-table",
                    columns=[
                        {"name": "Agency",           "id": "Agency"},
                        {"name": "2024 Collections", "id": "2024"},
                        {"name": "2025 Collections", "id": "2025"},
                        {"name": "Change",           "id": "Change"},
                        {"name": "% Change",         "id": "Pct"},
                    ],
                    data=[{
                        "Agency": r["Agency"],
                        "2024": f"${r['Collections_2024']:,.2f}",
                        "2025": f"${r['Collections_2025']:,.2f}",
                        "Change": f"+${r['Change']:,.2f}" if r["Change"] > 0 else f"${r['Change']:,.2f}",
                        "Pct": f"+{r['Pct_Change']:.1f}%" if r["Pct_Change"] > 0 else f"{r['Pct_Change']:.1f}%",
                    } for _, r in BILLING_COLLECTIONS.iterrows()] + [{
                        "Agency": "TOTAL",
                        "2024": f"${BILLING_COLLECTIONS['Collections_2024'].sum():,.2f}",
                        "2025": f"${BILLING_COLLECTIONS['Collections_2025'].sum():,.2f}",
                        "Change": f"+${BILLING_COLLECTIONS['Change'].sum():,.2f}",
                        "Pct": f"+{100*BILLING_COLLECTIONS['Change'].sum()/BILLING_COLLECTIONS['Collections_2024'].sum():.1f}%",
                    }],
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE + [
                        {"if": {"filter_query": '{Agency} = "TOTAL"'},
                         "fontWeight": "bold", "backgroundColor": "#2E3238"},
                    ],
                    style_cell_conditional=[
                        {"if": {"column_id": c}, "textAlign": "right"}
                        for c in ["2024", "2025", "Change", "Pct"]
                    ],
                ),
                _source_citation(
                    "Jefferson County Chief Association Agency Data 2025.xlsx (new3.31.26/)",
                    "Data reflects actual net collections from EMS billing vendors (EMS|MC and others)",
                ),
            ], style=CARD),
            # ── NEW: EMS Service Area Population (WI DOA 2025) ───────────────
            html.Div([
                _section_header("EMS Service Area Population — WI DOA 2025 Preliminary Estimates"),
                html.P(
                    "Population assigned by EMS responding unit coverage area. Each municipality's "
                    "population is allocated to its EMS provider based on coverage ratios from the "
                    "WI Department of Administration. County total: 86,855.",
                    style={"fontSize": "0.82rem", "color": C_MUTED, "margin": "0 0 14px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                dash_table.DataTable(
                    id="pop-by-provider-table",
                    columns=_get_population_table()[1],
                    data=_get_population_table()[0],
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE + [
                        {"if": {"filter_query": '{Department} = "COUNTY TOTAL"'},
                         "fontWeight": "bold", "backgroundColor": "#2E3238"},
                    ],
                ),
                _source_citation(
                    "Emergency Services Population - Jefferson County.xlsx (new3.31.26/)",
                    "WI DOA Preliminary 2025 Estimates — Sorted by Provider sheet",
                ),
            ], style=CARD),
            # ── NEW: Mill Rate Levy Projections ──────────────────────────────
            html.Div([
                _section_header("Hypothetical County EMS Levy Projections — By Mill Rate"),
                html.P(
                    "What a county-wide EMS levy would raise at different mill rates, distributed "
                    "proportionally by population across the 12 EMS service providers. These are "
                    "hypothetical projections — no levy is currently in place.",
                    style={"fontSize": "0.82rem", "color": C_MUTED, "margin": "0 0 14px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                dcc.Graph(id="levy-projection-chart",
                    figure=_get_levy_projection_figs()[0], config={"displayModeBar": False}),
                _sub_header("Full Mill Rate Projection Table"),
                dash_table.DataTable(
                    id="levy-projection-table",
                    columns=_get_levy_projection_figs()[2],
                    data=_get_levy_projection_figs()[1],
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px", "textAlign": "right"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE + [
                        {"if": {"filter_query": '{Provider} = "COUNTY TOTAL"'},
                         "fontWeight": "bold", "backgroundColor": "#2E3238"},
                    ],
                    style_cell_conditional=[
                        {"if": {"column_id": "Provider"}, "textAlign": "left", "fontWeight": "600"},
                    ],
                ),
                _source_citation(
                    "Emergency Services Population - Jefferson County.xlsx (new3.31.26/)",
                    "Payment by Service Provider sheet — WI DOA 2025 Preliminary Estimates",
                ),
            ], style=CARD),
            # ── NEW: Provider-Level Call Data Inventory ───────────────────────
            html.Div([
                _section_header("Provider-Level Call Data Inventory — CY2024"),
                html.P(
                    "6 departments provided incident-level EMS data directly (via Chief Association). "
                    "This supplements the NFIRS data with richer detail including exact dispatch/arrival "
                    "times, transport dispositions, and care levels.",
                    style={"fontSize": "0.82rem", "color": C_MUTED, "margin": "0 0 14px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                dash_table.DataTable(
                    id="provider-call-summary-table",
                    columns=[
                        {"name": "Department",  "id": "Department"},
                        {"name": "Records",     "id": "Records"},
                        {"name": "Care Level",  "id": "Care_Level"},
                        {"name": "Has RT Data", "id": "Has_RT"},
                        {"name": "Data Fields", "id": "Data_Fields"},
                        {"name": "Source File", "id": "Source_File"},
                    ],
                    data=PROVIDER_CALL_SUMMARY.to_dict("records"),
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px",
                                "whiteSpace": "normal", "height": "auto", "maxWidth": "250px"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE + [
                        {"if": {"filter_query": '{Has_RT} = "Yes"', "column_id": "Has_RT"},
                         "color": C_GREEN, "fontWeight": "bold"},
                        {"if": {"filter_query": '{Has_RT} = "No"', "column_id": "Has_RT"},
                         "color": C_RED},
                    ],
                ),
                html.Div([
                    html.Span("Coverage note: ", style={
                        "fontWeight": "700", "color": C_YELLOW, "fontSize": "11px",
                        "fontFamily": FONT_STACK}),
                    html.Span(
                        "6 of 12 EMS providers submitted data. Missing: Cambridge, Palmyra, "
                        "Watertown, Western Lakes, Ixonia, and full Whitewater (only Jeff Co contracts provided). "
                        "4 of 6 providers include response time data suitable for drill-down analysis.",
                        style={"color": C_MUTED, "fontSize": "11px", "fontFamily": FONT_STACK}),
                ], style={"marginTop": "12px", "padding": "8px 12px",
                          "backgroundColor": "#2A2000", "borderRadius": "6px",
                          "border": f"1px solid {C_YELLOW}33"}),
                _source_citation(
                    "Data from Providers-20260331T151417Z-1-001.zip (new3.31.26/)",
                    "6 individual department data files — CY2024 incident-level records",
                ),
            ], style=CARD),
        ])

    elif tab == "tab-benchmark":
        return html.Div([
            html.Div([
                _section_header("Portage County Benchmark — Consolidated County EMS Model"),
                html.P("Portage Co. operates a consolidated county EMS system — benchmark for Jefferson.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 14px",
                           "fontFamily": FONT_STACK}),
                html.Div([
                    dcc.Graph(id="portage-vol", figure=_get_portage_figs()[0], style={"flex": "1"}),
                    dcc.Graph(id="portage-rev", figure=_get_portage_figs()[1], style={"flex": "1"}),
                    dcc.Graph(id="portage-pay", figure=_get_portage_figs()[2], style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                _source_citation(
                    "county_ems_comparison_data.xlsx — Portage_Call_Volume_Trend sheet",
                    "county_ems_comparison_data.xlsx — Portage_Revenue_Trend sheet",
                    "county_ems_comparison_data.xlsx — Portage_Payor_Mix_2024 sheet",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Jefferson vs. Portage \u2014 Aspirational Model Comparison"),
                # Structural incomparability warning
                html.Div([
                    html.Strong("Important: Structural Difference",
                        style={"display": "block", "marginBottom": "6px",
                               "fontSize": "0.85rem", "color": "#92400E",
                               "fontFamily": FONT_STACK}),
                    html.P(
                        "Portage Co. operates a unified county EMS system; Jefferson Co. has 11 "
                        "independent municipal providers. These are structurally different systems. "
                        "This comparison shows what Jefferson County metrics could look like under a "
                        "Portage-style consolidated model \u2014 not a peer-to-peer equivalence.",
                        style={"margin": "0", "fontSize": "0.85rem", "lineHeight": "1.6",
                               "color": "#78350F", "fontFamily": FONT_STACK},
                    ),
                ], style={
                    "background": "#FEF3C7",
                    "border": "1px solid #F59E0B",
                    "borderLeft": "4px solid #F59E0B",
                    "borderRadius": "6px",
                    "padding": "12px 16px",
                    "marginBottom": "14px",
                }),
                # Population normalization note
                html.P(
                    "Population context: Jefferson Co. 84,700 residents; Portage Co. 70,700 residents. "
                    "Per-capita metrics are more meaningful than raw totals for cross-county comparison.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 14px",
                           "fontFamily": FONT_STACK},
                ),
                dash_table.DataTable(
                    id="comparison-table",
                    columns=[{"name": c, "id": c} for c in comparison.columns],
                    data=comparison.to_dict("records"),
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER, style_cell=_DT_STYLE_CELL,
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE),
                _source_citation(
                    "county_ems_comparison_data.xlsx — Comparison sheet",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Bayfield County — Countywide EMS Levy Model"),
                html.P("Bayfield County established a countywide EMS levy in 2025 — template for Jefferson.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 14px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                dcc.Graph(id="bayfield-levy-bar", figure=_get_fig_bayfield_levy(),
                    style={"marginBottom": "20px"}),
                _sub_header("Jefferson County vs Bayfield County — Structural Comparison"),
                dash_table.DataTable(
                    id="bayfield-compare-table",
                    columns=[{"name": c, "id": c} for c in _df_jeff_bayfield_compare.columns],
                    data=_df_jeff_bayfield_compare.to_dict("records"),
                    style_table={"overflowX": "auto", "borderRadius": "8px",
                                 "overflow": "hidden", "marginBottom": "14px"},
                    style_header=_DT_STYLE_HEADER, style_cell=_DT_STYLE_CELL,
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE,
                    style_cell_conditional=[
                        {"if": {"column_id": "Metric"}, "fontWeight": "600", "width": "28%", "minWidth": "180px"},
                        {"if": {"column_id": "Jefferson County"}, "width": "36%"},
                        {"if": {"column_id": "Bayfield County"}, "width": "36%"}]),
                html.P("Scaled estimate: $540K-$610K/yr county EMS overlay. Legal basis: "
                       "Wis. Stat. 66.0301 + 66.0602(3).",
                    style={"fontSize": "0.8rem", "color": C_TEXT, "lineHeight": "1.6",
                           "background": "#2E2A1E", "border": f"1px solid {C_PRIMARY}",
                           "borderLeft": f"4px solid {C_PRIMARY}", "borderRadius": "6px",
                           "padding": "10px 14px", "margin": "0", "fontFamily": FONT_STACK}),
                _source_citation(
                    ("Bayfield County 2025 Budget Introduction",
                     "https://www.bayfieldcounty.wi.gov/DocumentCenter/View/18161/2025-BUDGET-INTRODUCTION"),
                    "Wis. Stat. 66.0301 + 66.0602(3) (levy exception legal basis)",
                ),
            ], style=CARD),

            # ── Section 19: Cross-County Benchmarking ──────────────────────
            html.Div([
                html.Div("Benchmarking Data Disclaimer", style={
                    "fontWeight": "700", "fontSize": "0.85rem", "color": C_YELLOW,
                    "marginBottom": "6px", "fontFamily": FONT_STACK}),
                html.P(
                    "This section presents benchmarking data for informational purposes only. "
                    "County-level figures are drawn from public documents, news sources, and "
                    "secondary research as noted. All comparisons are descriptive and do not "
                    "constitute operational recommendations. Cells marked 'Missing' indicate "
                    "data not located in available sources as of March 2, 2026.",
                    style={"margin": "0", "lineHeight": "1.65", "fontFamily": FONT_STACK,
                           "fontSize": "0.8rem", "color": C_TEXT}),
            ], style={"background": "#2E2A1E", "border": f"1px solid {C_BORDER}",
                      "borderLeft": f"4px solid {C_YELLOW}", "borderRadius": "8px",
                      "padding": "12px 16px", "marginBottom": "4px",
                      "fontFamily": FONT_STACK}),
            html.Div([
                _section_header("Cross-County Benchmarking: 7-County System Structure Comparison"),
                html.P(
                    "Jefferson County compared to 6 Wisconsin peer counties. "
                    "Jefferson row highlighted in blue. Sort by any column. Hover cells for source notes.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 14px",
                           "fontFamily": FONT_STACK}),
                dash_table.DataTable(
                    id="cc-structure-table",
                    columns=[{"name": c, "id": c} for c in _df_cc_structure.columns],
                    data=_df_cc_structure.to_dict("records"),
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px",
                                 "overflow": "hidden", "marginBottom": "14px"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "whiteSpace": "normal", "height": "auto",
                                "maxWidth": "220px", "minWidth": "75px"},
                    style_cell_conditional=[
                        {"if": {"column_id": "County"}, "fontWeight": "600", "width": "75px"},
                        {"if": {"column_id": "System Model"}, "width": "230px"},
                        {"if": {"column_id": "ALS Coverage"}, "width": "155px"},
                        {"if": {"column_id": "Data Confidence"},
                         "textAlign": "center", "width": "85px"},
                    ],
                    style_data_conditional=_CC_STRUCTURE_COND,
                    tooltip_data=[
                        {col: {"value": (
                            "Source: 2024 NFIRS + FY2025 budget (Jefferson); "
                            "Bayfield 2025 Budget; WPF 2025 study (Walworth); "
                            "West Bend-Kewaskum MOU (Washington); "
                            "Perplexity secondary research Mar 2 2026 (Dodge, Rock, Portage)"
                        ), "type": "markdown"} for col in _df_cc_structure.columns}
                        for _ in range(len(_df_cc_structure))
                    ],
                    tooltip_delay=0, tooltip_duration=None,
                ),
                html.P(
                    "Confidence key -- Confirmed: primary source reviewed. "
                    "Estimated: derived from partial or proxy data. "
                    "Missing: not located as of March 2, 2026. "
                    "Mixed: some confirmed, some estimated.",
                    style={"fontSize": "0.75rem", "color": C_MUTED, "margin": "0",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                _source_citation(
                    "2024 NFIRS + FY2025 Budget Data (Jefferson County primary dataset)",
                    ("Bayfield County 2025 Budget Introduction",
                     "https://www.bayfieldcounty.wi.gov/DocumentCenter/View/18161/2025-BUDGET-INTRODUCTION"),
                    ("West Bend-Kewaskum Hybrid MOU (Washington Co.)",
                     "https://www.youtube.com/watch?v=zlf18eqnIYI"),
                    ("WPF Lafayette County EMS Report",
                     "https://wispolicyforum.org/research/the-next-level-collaborative-strategies-to-enhance-ems-in-lafayette-county/"),
                    "Secondary research: Perplexity Mar 2, 2026 (Dodge, Rock, Portage, Washington)",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Revenue Recovery Rate — Jefferson County + Portage Benchmark"),
                html.P(
                    "All 10 Jefferson County departments with known recovery rates plus "
                    "Portage County benchmarks (current ~35% and 10-year-ago ~49%). "
                    "Edgerton shown as N/A (partial budget only). "
                    "Dashed line = Jefferson County aggregate (26.8%). Data updated March 2, 2026.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 14px",
                           "fontFamily": FONT_STACK}),
                dcc.Graph(id="cc-recovery-bar", figure=_get_fig_cc_recovery()),
                html.P(_CC_RECOVERY_FOOTNOTE,
                    style={"fontSize": "0.75rem", "color": C_MUTED, "margin": "12px 0 0",
                           "lineHeight": "1.6", "fontFamily": FONT_STACK,
                           "background": "#2E3238", "border": f"1px solid {C_BORDER}",
                           "borderLeft": f"3px solid {C_MUTED}", "borderRadius": "4px",
                           "padding": "8px 12px"}),
                _source_citation(
                    "Jefferson County dept recovery rates: utilization_analysis.md (confirmed, FY2025 budget)",
                    "Portage County collection trend: county_ems_comparison_data.xlsx Portage_Revenue_Trend",
                    "26.8% aggregate: Edgerton expense in denominator; revenue unknown (partial budget only)",
                ),
            ], style=CARD),

            # ── Section 19b: Cross-County Asset Comparison ─────────────────
            html.Div([
                _section_header("Cross-County Asset & Fleet Comparison"),
                html.P(
                    "Jefferson County fleet data from MABAS Division 118 filings (confirmed). "
                    "Peer county fleet data not available from public sources — "
                    "Open Records requests or MABAS Division filings needed for comparison.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 16px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                html.Div([
                    kpi_card("Total Ambulances",  _get_fig_cc_assets()[2]["ambulances"],
                             f"{_get_fig_cc_assets()[2]['depts_with_ambulances']} depts transport / "
                             f"{_get_fig_cc_assets()[2]['depts_without']} fire-only",
                             C_PRIMARY),
                    kpi_card("Total Apparatus",    _get_fig_cc_assets()[2]["apparatus"],
                             "Engines, trucks, squads, tenders, brush, boats, ambulances",
                             C_YELLOW),
                    kpi_card("EMS Personnel",      _get_fig_cc_assets()[2]["ems_personnel"],
                             f"{_get_fig_cc_assets()[2]['pers_per_10k']} per 10K pop",
                             C_GREEN),
                    kpi_card("Amb. per 10K Pop",   _get_fig_cc_assets()[2]["amb_per_10k"],
                             "Jefferson County (84,700 pop)",
                             C_PRIMARY),
                ], style={"display": "flex", "gap": "14px", "marginBottom": "20px"}),
                dcc.Graph(id="cc-asset-ambulance-dist", figure=_get_fig_cc_assets()[0], style={"marginBottom": "16px"}),
                _sub_header("Peer County Fleet Data Availability"),
                dash_table.DataTable(
                    id="cc-asset-table",
                    columns=[
                        {"name": "County",         "id": "County"},
                        {"name": "Population",     "id": "Population"},
                        {"name": "Ambulances",     "id": "Ambulances"},
                        {"name": "Total Apparatus","id": "Total_Apparatus"},
                        {"name": "EMS Personnel",  "id": "EMS_Personnel"},
                        {"name": "Amb/10K Pop",    "id": "Amb_per_10K"},
                        {"name": "Data Status",    "id": "Status"},
                        {"name": "Notes",          "id": "Notes"},
                    ],
                    data=_df_cc_assets.to_dict("records"),
                    style_table={"overflowX": "auto", "borderRadius": "8px", "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px",
                                "whiteSpace": "normal", "height": "auto"},
                    style_cell_conditional=[
                        {"if": {"column_id": "County"}, "fontWeight": "600", "width": "80px"},
                        {"if": {"column_id": "Notes"}, "width": "250px"},
                        {"if": {"column_id": "Status"}, "textAlign": "center", "width": "80px"},
                    ],
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE + [
                        {"if": {"filter_query": '{County} = "Jefferson"'}, "fontWeight": "600", "color": C_PRIMARY},
                    ],
                ),
                html.P(
                    "Jefferson is the only county with confirmed fleet data from MABAS filings. "
                    "To enable peer comparison, fleet inventories should be requested from "
                    "neighboring MABAS Divisions or via WI DHS EMS licensing records.",
                    style={"fontSize": "0.75rem", "color": C_MUTED, "margin": "12px 0 0",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                _source_citation(
                    "MABAS_Assets/*.xlsx — 14 MABAS Division 118 FD Resource Lists (Jefferson County confirmed)",
                    "Peer county data: not available from public sources as of March 2, 2026",
                ),
            ], style=CARD),

        ])

    elif tab == "tab-contracts":
        _ck = _CONTRACT_KPIS
        _ct_figs = _get_fig_contract_timeline()
        return html.Div([
            # ── CARD 1: KPI Overview ──────────────────────────────────────
            html.Div([
                _section_header("EMS Contract & Service Area Overview"),
                html.Div([
                    kpi_card("EMS Providers", _ck["providers"],
                             "independent responding units", C_PRIMARY),
                    kpi_card("County Population", "86,855",
                             "WI DOA 2025 preliminary estimate", C_GREEN),
                    kpi_card("Active Contracts", _ck["active"],
                             "inter-governmental agreements", C_GREEN),
                    kpi_card("Per-Capita Range",
                             f"{_ck['rate_min']} – {_ck['rate_max']}",
                             "latest contract rates", C_PRIMARY),
                ], style={"display": "flex", "gap": "12px",
                          "flexWrap": "wrap", "marginBottom": "16px"}),
                _source_citation(
                    "contract_analysis.md — all 17 IGAs reviewed",
                    "Emergency Services Population - Jefferson County.xlsx (WI DOA 2025)",
                ),
            ], style=CARD),

            # ── CARD 2: Service Area Population ──────────────────────────
            html.Div([
                _section_header("EMS Service Area Population by Provider"),
                html.P("Each EMS provider covers a defined set of municipalities. "
                       "Several towns are split between 2-3 providers. Population "
                       "figures are WI DOA Preliminary 2025 Estimates, apportioned "
                       "to the responding unit serving each area.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 16px",
                           "lineHeight": "1.55", "fontFamily": FONT_STACK}),
                dcc.Graph(id="svc-area-pop-bar", figure=_get_fig_svc_area_pop()),
                dash_table.DataTable(
                    id="svc-area-pop-table",
                    columns=[
                        {"name": "EMS Provider",       "id": "Provider"},
                        {"name": "Municipalities Served", "id": "Municipalities"},
                        {"name": "Service Area Pop.",  "id": "Population"},
                        {"name": "% of County",        "id": "Pct_County"},
                    ],
                    data=_SVC_AREA_POP_TABLE,
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "8px",
                                 "overflow": "hidden"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "fontSize": "12px",
                                "whiteSpace": "normal", "height": "auto"},
                    style_cell_conditional=[
                        {"if": {"column_id": "Provider"}, "fontWeight": "600",
                         "textAlign": "left", "width": "130px"},
                        {"if": {"column_id": "Municipalities"}, "textAlign": "left",
                         "width": "350px"},
                        {"if": {"column_id": "Population"}, "textAlign": "center",
                         "width": "100px"},
                        {"if": {"column_id": "Pct_County"}, "textAlign": "center",
                         "width": "90px"},
                    ],
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE,
                ),
                _source_citation(
                    "Emergency Services Population - Jefferson County.xlsx (new3.31.26/)",
                    "WI DOA Preliminary 2025 Municipal Estimates — Sorted by Provider sheet",
                ),
            ], style=CARD),

            # ── CARD 3: Timeline & Rate Escalation ────────────────────────
            html.Div([
                _section_header("Contract Windows & Rate Escalation"),
                dcc.Graph(id="contract-gantt", figure=_ct_figs[0],
                    style={"marginBottom": "20px"}),
                dcc.Graph(id="contract-escalation", figure=_ct_figs[1]),
                _source_citation(
                    "Jefferson City EMS contract 2024-2027 (Aztalan template)",
                    "Waterloo fire and EMS contract (Town of Milford)",
                    "FA Ambulance contract 2023 (Koshkonong & Jefferson Twp)",
                    "Lake Mills / Ryan Brothers IGAs (Aztalan, Oakland, Lake Mills Town)",
                ),
            ], style=CARD),

        ])

    # ── SECONDARY NETWORK SIMULATION TAB ──────────────────────────────────
    elif tab == "tab-simulation":
        return _render_simulation_tab()

    # Recommendations tab — hidden from UI but code preserved for future use.
    # To re-enable: add dcc.Tab(label="Recommendations", value="tab-recommend", ...) to the tab bar above.
    elif tab == "tab-recommend":
        return html.Div([
            html.Div([
                _section_header("Cost Driver Diagnostics & Structural Findings"),
                html.P("Data-driven analysis of where costs concentrate and why. "
                    "Estimates quantify the magnitude of identified inefficiencies — "
                    "not prescriptive targets. Jefferson City figures subject to data audit.",
                    style={"fontSize": "0.8rem", "color": C_TEXT, "lineHeight": "1.6",
                           "background": "#2E1E1E", "border": f"1px solid {C_ORANGE}",
                           "borderLeft": f"4px solid {C_ORANGE}", "borderRadius": "6px",
                           "padding": "10px 14px", "marginBottom": "20px", "fontFamily": FONT_STACK}),
                _source_citation(
                    "savings_model.md — Section 3 (5% savings pathway)",
                    "utilization_analysis.md (cost-per-call & outlier analysis)",
                    "Wis. Stat. 66.0602(3) (levy exception eligibility)",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Reference Cost Model: 24/7 ALS Single Unit"),
                html.P("Chief Bruce Peterson's operating cost projection for a single 24/7 ALS "
                       "ambulance unit in Jefferson County. Capital costs excluded — assumes "
                       "existing ambulance(s) and station.",
                    style={"fontSize": "0.8rem", "color": C_TEXT, "lineHeight": "1.6",
                           "background": "#2E2A1E", "border": f"1px solid {C_PRIMARY}",
                           "borderLeft": f"4px solid {C_PRIMARY}", "borderRadius": "6px",
                           "padding": "10px 14px", "marginBottom": "20px", "fontFamily": FONT_STACK}),
                html.Div([
                    kpi_card("Total Operating", "$716,818", "Single 24/7 ALS unit", C_ORANGE),
                    kpi_card("EMS Revenue",     "$466,200", "700 calls x $666 avg collected", C_GREEN),
                    kpi_card("Net County Cost",  "$250,618", "Annual tax subsidy needed", C_PRIMARY),
                    kpi_card("Cost Per Call",    "$1,024",   "$716,818 / 700 calls", C_YELLOW),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px"}),
                dcc.Graph(id="peterson-waterfall", figure=_get_fig_peterson_waterfall(),
                    style={"marginBottom": "20px"}),
                _source_citation(
                    "25-1210 JC EMS Workgroup Cost Projection.pdf (Chief Bruce Peterson, Fort Atkinson FD)",
                    "Assumptions: 24/48 schedule, 6 FTEs, 45% benefits load, $666 avg transport fee collected",
                ),
            ], style=CARD),
            html.Div([
                _section_header("Contract Windows & Structural Transition Opportunities"),
                html.P("Contract expiration analysis identifying when and where structural changes become "
                    "feasible based on existing IGA terms.",
                    style={"fontSize": "0.8rem", "color": C_TEXT, "lineHeight": "1.6",
                           "background": "#2E2A1E", "border": f"1px solid {C_PRIMARY}",
                           "borderLeft": f"4px solid {C_PRIMARY}", "borderRadius": "6px",
                           "padding": "10px 14px", "marginBottom": "20px", "fontFamily": FONT_STACK}),
                _sub_header("Contract Expiration Windows & Feasibility Timeline (2026–2029)"),
                dash_table.DataTable(
                    id="sec17a-roadmap-table",
                    columns=[{"name": c, "id": c} for c in _df_transition_roadmap.columns],
                    data=_df_transition_roadmap.to_dict("records"),
                    style_table={"overflowX": "auto", "borderRadius": "8px",
                                 "overflow": "hidden", "marginBottom": "20px"},
                    style_header=_DT_STYLE_HEADER,
                    style_cell={**_DT_STYLE_CELL, "whiteSpace": "normal", "height": "auto"},
                    style_data_conditional=_DT_STYLE_DATA_CONDITIONAL_BASE),
                _source_citation(
                    "contract_analysis.md — Sections B-D (contract structure analysis)",
                    "savings_model.md (implementation phases & contract windows)",
                ),
            ], style=CARD),
        ])

    return html.Div("Select a tab.")


@app.callback(
    Output("map-markers", "children"),
    Output("map-ems-choropleth", "hideout"),
    Output("map-geojson", "hideout"),
    Output("map-legend", "children"),
    Output("zoom-badge", "children"),
    Output("map-layer-zcta", "children"),
    Input("map-metric", "value"),
    Input("dept-filter", "value"),
    Input("leaflet-map", "viewport"),
    Input("main-tabs", "value"),
    Input("map-layers", "value"),
)
def update_map(metric, selected_depts, viewport, tab, active_layers):
    if tab != "tab-overview":
        return no_update, no_update, no_update, no_update, no_update, no_update
    zoom = (viewport or {}).get("zoom", 10)
    active_layers = active_layers or []

    # Select tier based on zoom level — lower thresholds for earlier detail
    if zoom >= 12:
        tier = "zip"
        data_source = ZIP_DATA
        tier_max = _max_zip_calls
    elif zoom >= 10.5:
        tier = "city"
        data_source = CITY_DATA
        tier_max = _max_city_calls
    else:
        tier = "dept"
        data_source = MARKER_DATA
        tier_max = _max_calls

    is_rt = "rt" in metric
    is_asset = metric in ("ambulances", "ems_personnel")
    color_map = _compute_color_map(metric)
    show_muni = "muni" in active_layers
    ems_hideout = {"colorMap": color_map}
    muni_hideout = {"showMuniBorders": show_muni}

    def _tier_radius(total):
        if not total:
            return _MIN_MARKER_PX
        return _MIN_MARKER_PX + (_MAX_MARKER_PX - _MIN_MARKER_PX) * math.sqrt(float(total) / tier_max)

    def _tier_color_calls(val):
        if not val:
            return "rgb(198,219,239)"
        t = min(1.0, float(val) / tier_max)
        r = int(198 + (8 - 198) * t)
        g = int(219 + (48 - 219) * t)
        b = int(239 + (107 - 239) * t)
        return f"rgb({r},{g},{b})"

    markers = []
    min_calls = 3 if tier != "dept" else 0

    for md in sorted(data_source, key=lambda m: m["total_calls"], reverse=True):
        if md["dept"] not in selected_depts:
            continue
        total = md["total_calls"]
        if total < min_calls and not is_asset:
            continue
        radius = _tier_radius(total) if not is_asset else max(_MIN_MARKER_PX, _tier_radius(total))
        if is_asset:
            ast_d = asset_lookup.get(md["dept"], {})
            asset_val = ast_d.get("Ambulances", 0) if metric == "ambulances" else ast_d.get("EMS_Personnel", 0)
            asset_val = asset_val or 0
            asset_max = _max_amb if metric == "ambulances" else _max_pers
            color = _bubble_color_asset(asset_val, asset_max)
        elif is_rt:
            if tier == "dept" and metric == "p90_rt":
                val = md.get("p90", md.get("median_rt", 0))
            else:
                val = md.get("median_rt", 0)
            color = _bubble_color_rt(val)
        else:
            val = total if metric == "total_calls" else md.get("ems_calls", 0)
            color = _tier_color_calls(val)
        ems_c = md.get("ems_calls", 0)
        pct = f"{100*ems_c/total:.0f}%" if total > 0 else "N/A"

        if tier == "dept":
            _tt_items = [html.B(md["dept"], style={"fontSize": "13px"}), html.Br()]
            if is_asset:
                _ast_d = asset_lookup.get(md["dept"], {})
                _svc = ALS_LEVELS.get(md["dept"], {}).get("Level", "N/A")
                _tt_items += [
                    html.Span("Service Level: "), html.B(_svc), html.Br(),
                    html.Span("Ambulances: "), html.B(str(_ast_d.get("Ambulances", 0))), html.Br(),
                    html.Span("EMS Personnel: "), html.B(str(_ast_d.get("EMS_Personnel", 0))), html.Br(),
                    html.Span("Paramedics: "), html.B(str(_ast_d.get("Paramedics", 0))),
                ]
            else:
                _tt_items += [
                    html.Span("Total calls: "), html.B(f"{total:,}"), html.Br(),
                    html.Span("EMS calls: "), html.B(f"{ems_c:,}"), html.Span(f" ({pct})"), html.Br(),
                    html.Span("Median RT: "), html.B(f"{md.get('median_rt', 'N/A')} min"),
                ]
            tooltip_content = html.Div(_tt_items)
            popup_content = dl.Popup(_build_popup_content(md["dept"]), maxWidth=300)
        elif tier == "city":
            city_name = md.get("city", "")
            if is_asset:
                _ast_c = asset_lookup.get(md["dept"], {})
                _svc_c = ALS_LEVELS.get(md["dept"], {}).get("Level", "N/A")
                tooltip_content = html.Div([
                    html.B(city_name, style={"fontSize": "13px"}), html.Br(),
                    html.Span("Dept: "), html.B(md["dept"]), html.Br(),
                    html.Span("Service Level: "), html.B(_svc_c), html.Br(),
                    html.Span("Ambulances: "), html.B(str(_ast_c.get("Ambulances", 0))), html.Br(),
                    html.Span("EMS Personnel: "), html.B(str(_ast_c.get("EMS_Personnel", 0))),
                ])
            else:
                tooltip_content = html.Div([
                    html.B(city_name, style={"fontSize": "13px"}), html.Br(),
                    html.Span("Dept: "), html.B(md["dept"]), html.Br(),
                    html.Span("Total calls: "), html.B(f"{total:,}"), html.Br(),
                    html.Span("EMS calls: "), html.B(f"{ems_c:,}"), html.Span(f" ({pct})"), html.Br(),
                    html.Span("Median RT: "), html.B(f"{md.get('median_rt', 'N/A')} min"),
                ])
            popup_content = dl.Popup(html.Div([
                html.H4(city_name, style={"margin": "0 0 6px 0", "fontSize": "14px"}),
                html.P(f"Department: {md['dept']}", style={"margin": "2px 0"}),
                html.P(f"Total calls: {total:,}", style={"margin": "2px 0"}),
                html.P(f"EMS calls: {ems_c:,} ({pct})", style={"margin": "2px 0"}),
                html.P(f"Median RT: {md.get('median_rt', 'N/A')} min", style={"margin": "2px 0"}),
            ], style={"fontFamily": FONT_STACK, "fontSize": "12px"}), maxWidth=260)
        else:
            zip_code = md.get("zip", "")
            if is_asset:
                _ast_z = asset_lookup.get(md["dept"], {})
                _svc_z = ALS_LEVELS.get(md["dept"], {}).get("Level", "N/A")
                tooltip_content = html.Div([
                    html.B(f"ZIP {zip_code}", style={"fontSize": "13px"}), html.Br(),
                    html.Span("Dept: "), html.B(md["dept"]), html.Br(),
                    html.Span("Service Level: "), html.B(_svc_z), html.Br(),
                    html.Span("Ambulances: "), html.B(str(_ast_z.get("Ambulances", 0))), html.Br(),
                    html.Span("EMS Personnel: "), html.B(str(_ast_z.get("EMS_Personnel", 0))),
                ])
            else:
                tooltip_content = html.Div([
                    html.B(f"ZIP {zip_code}", style={"fontSize": "13px"}), html.Br(),
                    html.Span("Dept: "), html.B(md["dept"]), html.Br(),
                    html.Span("Total calls: "), html.B(f"{total:,}"), html.Br(),
                    html.Span("Median RT: "), html.B(f"{md.get('median_rt', 'N/A')} min"),
                ])
            popup_content = dl.Popup(html.Div([
                html.H4(f"ZIP {zip_code}", style={"margin": "0 0 6px 0", "fontSize": "14px"}),
                html.P(f"Department: {md['dept']}", style={"margin": "2px 0"}),
                html.P(f"Total calls: {total:,}", style={"margin": "2px 0"}),
                html.P(f"EMS calls: {ems_c:,} ({pct})", style={"margin": "2px 0"}),
                html.P(f"Median RT: {md.get('median_rt', 'N/A')} min", style={"margin": "2px 0"}),
            ], style={"fontFamily": FONT_STACK, "fontSize": "12px"}), maxWidth=260)

        markers.append(
            dl.CircleMarker(
                center=[md["lat"], md["lon"]],
                radius=radius,
                color=C_TEXT,
                weight=2,
                fillColor=color,
                fillOpacity=0.85,
                children=[dl.Tooltip(tooltip_content), popup_content],
            )
        )

    # ── Dynamic ZIP boundary layer ──
    # Auto-show when zoomed to city/zip tier, or when user checks the toggle.
    # Always uses the dynamic colored choropleth with data tooltips.
    show_zcta = tier in ("city", "zip") or "zcta" in active_layers
    zcta_children = []
    if show_zcta:
        zip_color_map = _compute_zip_color_map(metric, ZIP_DATA, selected_depts)
        enriched_zcta = _build_zcta_data_geojson(ZIP_DATA, selected_depts)
        zcta_children = [
            dl.GeoJSON(
                data=enriched_zcta,
                options=dict(style=_zcta_style_dynamic, onEachFeature=_zcta_label_dynamic),
                hideout={"zipColorMap": zip_color_map},
                hoverStyle={"weight": 2, "fillOpacity": 0.45},
            ),
        ]

    if is_asset:
        legend_label = "Ambulances" if metric == "ambulances" else "EMS Personnel"
        legend = [
            html.B(legend_label, style={"fontSize": "12px"}), html.Br(),
            html.Div([
                html.Span(style={"background": "rgb(209,196,233)", "display": "inline-block",
                                 "width": "12px", "height": "12px", "borderRadius": "50%",
                                 "border": "1px solid #888", "marginRight": "5px"}),
                html.Span("None / Low"),
            ], style={"marginTop": "5px"}),
            html.Div([
                html.Span(style={"background": "rgb(88,28,135)", "display": "inline-block",
                                 "width": "12px", "height": "12px", "borderRadius": "50%", "marginRight": "5px"}),
                html.Span("High"),
            ], style={"marginTop": "3px"}),
            html.Div("Fill = dept asset count", style={"marginTop": "5px", "color": C_MUTED}),
        ]
    elif is_rt:
        legend_type = "Response Time"
        legend = [
            html.B(legend_type, style={"fontSize": "12px"}), html.Br(),
            html.Div([
                html.Span(style={"background": "rgb(33,153,33)", "display": "inline-block",
                                 "width": "12px", "height": "12px", "borderRadius": "50%", "marginRight": "5px"}),
                html.Span("Fast (<5 min)"),
            ], style={"marginTop": "5px"}),
            html.Div([
                html.Span(style={"background": "rgb(215,48,39)", "display": "inline-block",
                                 "width": "12px", "height": "12px", "borderRadius": "50%", "marginRight": "5px"}),
                html.Span("Slow (>12 min)"),
            ], style={"marginTop": "3px"}),
            html.Div("Marker size = total calls", style={"marginTop": "5px", "color": C_MUTED}),
        ]
    else:
        legend = [
            html.B("Call Volume", style={"fontSize": "12px"}), html.Br(),
            html.Div([
                html.Span(style={"background": "rgb(198,219,239)", "display": "inline-block",
                                 "width": "12px", "height": "12px", "borderRadius": "50%",
                                 "border": "1px solid #888", "marginRight": "5px"}),
                html.Span("Low"),
            ], style={"marginTop": "5px"}),
            html.Div([
                html.Span(style={"background": "rgb(8,48,107)", "display": "inline-block",
                                 "width": "12px", "height": "12px", "borderRadius": "50%", "marginRight": "5px"}),
                html.Span("High"),
            ], style={"marginTop": "3px"}),
            html.Div("Marker size & fill = call volume", style={"marginTop": "5px", "color": C_MUTED}),
        ]
    # Add ZIP choropleth note to legend when showing dynamic boundaries
    if show_zcta:
        legend.append(html.Div(style={"borderTop": "1px solid rgba(0,0,0,0.12)",
                                       "margin": "6px 0 4px"}))
        legend.append(html.Div("ZIP fill = same metric", style={"color": C_MUTED, "fontSize": "10px"}))

    tier_labels = {"dept": "Department View", "city": "City/Town View", "zip": "ZIP Code View"}
    tier_hints = {
        "dept": "Zoom in or click a district for city-level detail",
        "city": "Zoom in for ZIP-code detail",
        "zip":  "Zoom out for broader view",
    }
    badge = html.Span([
        html.Span(tier_labels[tier], style={"fontWeight": "700"}),
        html.Span(f"  \u00b7  {tier_hints[tier]}",
                  style={"fontWeight": "400", "color": "rgba(0,0,0,0.45)", "fontSize": "10px"}),
    ])

    return markers, ems_hideout, muni_hideout, legend, badge, zcta_children


# ── Map overlay layers callback (ZCTA now handled by update_map) ─────────────
@app.callback(
    Output("map-layer-fire", "children"),
    Output("map-layer-stations", "children"),
    Output("map-layer-helenville", "children"),
    Input("map-layers", "value"),
    Input("main-tabs", "value"),
)
def toggle_map_layers(active_layers, tab):
    if tab != "tab-overview":
        return no_update, no_update, no_update
    active = active_layers or []

    # Fire Districts — reference only; boundaries differ from EMS districts
    fire_children = []
    if "fire" in active:
        fire_children = [
            dl.GeoJSON(data=geojson_fire_districts,
                       options=dict(style=_fire_district_style),
                       hoverStyle={"weight": 2, "fillOpacity": 0.25}),
        ]

    # Stations (point markers from ArcGIS)
    station_children = []
    if "stations" in active:
        _type_colors = {"FD": "#FF5722", "PD": "#2196F3", "EMS": "#00BCD4"}
        for feat in geojson_stations["features"]:
            coords = feat["geometry"]["coordinates"]
            props = feat["properties"]
            stype = props.get("TYPE", "FD")
            label = props.get("MAPLABEL", "")
            clr = _type_colors.get(stype, "#FFFFFF")
            station_children.append(
                dl.CircleMarker(
                    center=[coords[1], coords[0]],
                    radius=5, color=clr, fillColor=clr,
                    fillOpacity=0.9, weight=1,
                    children=[dl.Tooltip(f"{label} ({stype})")],
                )
            )

    # Helenville 1st Responders
    helen_children = []
    if "helenville" in active:
        helen_children = [
            dl.GeoJSON(data=geojson_helenville,
                       options=dict(style=_helenville_style),
                       hoverStyle={"weight": 3, "fillOpacity": 0.4}),
        ]

    return fire_children, station_children, helen_children


# ── Zoom-to-fit: auto-adjust map bounds when department filter changes ────────
@app.callback(
    Output("leaflet-map", "bounds"),
    Input("dept-filter", "value"),
    Input("main-tabs", "value"),
    prevent_initial_call=True,
)
def zoom_to_fit_depts(selected_depts, tab):
    if tab != "tab-overview" or not selected_depts:
        return no_update
    # If all depts selected, use full county bounds
    if len(selected_depts) >= len(ALL_DEPTS):
        return COUNTY_BOUNDS
    # Compute combined bounding box for selected departments
    sw_lat, sw_lon = 90.0, 180.0
    ne_lat, ne_lon = -90.0, -180.0
    found = False
    for d in selected_depts:
        if d in DEPT_BOUNDS:
            b = DEPT_BOUNDS[d]
            sw_lat = min(sw_lat, b[0][0])
            sw_lon = min(sw_lon, b[0][1])
            ne_lat = max(ne_lat, b[1][0])
            ne_lon = max(ne_lon, b[1][1])
            found = True
    if not found:
        return no_update
    # Add slight padding
    pad_lat = (ne_lat - sw_lat) * 0.08
    pad_lon = (ne_lon - sw_lon) * 0.08
    return [[sw_lat - pad_lat, sw_lon - pad_lon], [ne_lat + pad_lat, ne_lon + pad_lon]]


# FIX 1: Dynamic KPI header row callback
@app.callback(
    Output("kpi-row", "children"),
    Input("dept-filter", "value"),
    Input("main-tabs", "value"),
)
def update_kpi_row(depts, tab):
    if tab != "tab-overview":
        return no_update
    df       = filter_raw(depts)
    rt_f     = filter_rt(depts)

    # Authoritative EMS call total for selected departments
    if depts:
        auth_total = sum(AUTH_EMS_CALLS.get(d, 0) for d in depts)
    else:
        auth_total = _AUTH_COUNTY_TOTAL

    avg_rt   = f"{rt_f['RT'].mean():.1f} min" if len(rt_f) else "N/A"
    med_rt   = f"{rt_f['RT'].median():.1f} min" if len(rt_f) else "N/A"
    n_depts  = len(depts) if depts else len(AUTH_EMS_CALLS)
    pct_over8 = (
        f"{100*(rt_f['RT'] > 8).sum()/len(rt_f):.1f}%"
        if len(rt_f) else "N/A"
    )

    return [
        kpi_card("EMS Calls",       f"{auth_total:,}", f"2024 — {n_depts} depts selected"),
        kpi_card("Avg Resp. Time",  avg_rt,            "EMS incidents (0-60 min)"),
        kpi_card("Median RT",       med_rt,            "County-wide EMS"),
        kpi_card("Departments",     str(n_depts),      "EMS-providing communities"),
        kpi_card("% EMS > 8 min",   pct_over8,         "Calls exceeding NFPA benchmark", "#A78BFA"),
    ]


# FIX 2: Call Volume — EMS calls bar + population-normalized bar + EMS % bar
@app.callback(
    Output("vol-bar",      "figure"),
    Output("vol-norm-bar", "figure"),
    Output("ems-pct-bar",  "figure"),
    Input("dept-filter",   "value"),
    Input("main-tabs",     "value"),
)
def update_vol(depts, tab):
    if tab != "tab-calls":
        return no_update, no_update, no_update

    # Build call volume table from authoritative EMS counts
    selected = depts if depts else list(AUTH_EMS_CALLS.keys())
    cv = pd.DataFrame([
        {"Department": d, "EMS_Calls": AUTH_EMS_CALLS.get(d, 0)}
        for d in selected if d in AUTH_EMS_CALLS
    ])
    cv = cv.sort_values("EMS_Calls", ascending=True)

    # ── Chart 1: Horizontal bar — EMS Calls (authoritative) ─────────────────
    # Add asterisk for departments where Looker Studio data differs
    cv["Label"] = cv.apply(
        lambda r: f"{r['EMS_Calls']:,}*" if r["Department"] in CALL_VOLUME_NOTES else f"{r['EMS_Calls']:,}",
        axis=1)
    cv["HoverNote"] = cv["Department"].map(
        lambda d: f"<br><i>* {CALL_VOLUME_NOTES[d]}</i>" if d in CALL_VOLUME_NOTES else "")

    fig1 = go.Figure([
        go.Bar(
            y=cv["Department"], x=cv["EMS_Calls"],
            name="EMS Calls", orientation="h",
            marker_color=C_PRIMARY,
            text=cv["Label"], textposition="outside",
            textfont=dict(color=C_TEXT, size=11),
            customdata=cv["HoverNote"],
            hovertemplate="<b>%{y}</b><br>EMS calls: %{x:,}%{customdata}<extra></extra>",
        ),
    ])
    fig1.update_layout(
        title="2024 EMS Call Volume by Department",
        xaxis_title="Number of EMS Calls",
    )
    # Footnote for asterisks
    has_notes = cv["Department"].isin(CALL_VOLUME_NOTES).any()
    if has_notes:
        fig1.add_annotation(
            text="* Looker Studio data differs from authoritative count — hover for details",
            xref="paper", yref="paper", x=0, y=-0.08,
            showarrow=False, font=dict(size=10, color=C_MUTED),
            xanchor="left",
        )
    _apply_chart_style(fig1, height=500, legend_below=False)
    fig1.update_layout(
        margin=dict(l=140, r=80, t=55, b=45),
        yaxis=dict(tickfont=dict(size=12, color=C_TEXT)),
    )

    # ── Chart 2: Population-normalized — EMS Calls per 1,000 Population ──────
    # Join population data and service level from module-level dicts
    cv["Population"]    = cv["Department"].map(SERVICE_AREA_POP)
    cv["Service_Level"] = cv["Department"].map(
        lambda d: ALS_LEVELS.get(d, {}).get("Level", "Unknown")
    )
    # Compute calls/1K where population is available
    has_pop = cv["Population"].notna()
    cv["Calls_per_1K"] = None
    cv.loc[has_pop, "Calls_per_1K"] = (
        cv.loc[has_pop, "EMS_Calls"] / cv.loc[has_pop, "Population"] * 1000
    ).round(1)

    # Sort ascending by calls/1K (put N/A depts at top where value is None)
    cv_norm = cv.copy()
    cv_norm["_sort_key"] = cv_norm["Calls_per_1K"].fillna(-1)
    cv_norm = cv_norm.sort_values("_sort_key", ascending=True)

    # Bar colors by service level
    bar_colors = [_SVC_COLORS.get(lvl, C_MUTED) for lvl in cv_norm["Service_Level"]]

    # Build hover text — rich detail for depts with population; note for those without
    hover_texts = []
    for _, row in cv_norm.iterrows():
        dept  = row["Department"]
        ems_c = int(row["EMS_Calls"])
        lvl   = row["Service_Level"]
        pop   = row["Population"]
        if pd.notna(pop):
            pop_int  = int(pop)
            c1k      = row["Calls_per_1K"]
            hover_texts.append(
                f"<b>{dept}</b><br>"
                f"EMS Calls: {ems_c:,}<br>"
                f"Population: {pop_int:,}<br>"
                f"Calls/1K pop: <b>{c1k:.1f}</b><br>"
                f"Service level: {lvl}"
            )
        else:
            hover_texts.append(
                f"<b>{dept}</b><br>"
                f"EMS Calls: {ems_c:,}<br>"
                f"Population: N/A (no Census estimate)<br>"
                f"Service level: {lvl}"
            )

    # Bar x values — use 0 placeholder for N/A depts so bar renders (annotated separately)
    x_vals = cv_norm["Calls_per_1K"].fillna(0).tolist()

    # Text labels for bars — "Pop. N/A" for missing, value for known
    text_labels = [
        "Pop. N/A" if pd.isna(row["Calls_per_1K"]) else f"{row['Calls_per_1K']:.1f}"
        for _, row in cv_norm.iterrows()
    ]

    fig3 = go.Figure(go.Bar(
        y=cv_norm["Department"],
        x=x_vals,
        orientation="h",
        marker_color=bar_colors,
        marker_line_color=C_BORDER,
        marker_line_width=0.5,
        text=text_labels,
        textposition="outside",
        textfont=dict(size=10, color=C_TEXT),
        hovertext=hover_texts,
        hoverinfo="text",
        customdata=cv_norm["Calls_per_1K"].tolist(),
        showlegend=False,
    ))

    # WI statewide benchmark reference line
    wi_bench = _BENCH["wi_calls_per_1k"]
    fig3.add_vline(
        x=wi_bench, line_dash="dash", line_color=C_YELLOW, line_width=1.8,
        annotation_text=f"WI avg {wi_bench}/1K",
        annotation_position="top right",
        annotation_font=dict(size=10, color=C_YELLOW),
    )

    # County median reference line — computed only from depts that have population data
    cv_with_pop = cv_norm.dropna(subset=["Calls_per_1K"])
    if len(cv_with_pop) >= 2:
        county_med = cv_with_pop["Calls_per_1K"].median()
        fig3.add_vline(
            x=county_med, line_dash="dot", line_color=C_MUTED, line_width=1.5,
            annotation_text=f"County median {county_med:.0f}/1K",
            annotation_position="bottom right",
            annotation_font=dict(size=10, color=C_MUTED),
        )

    # Service-level legend: use invisible scatter markers (does not interfere with bar y-axis)
    for lvl, col in _SVC_COLORS.items():
        if lvl in cv_norm["Service_Level"].values:
            fig3.add_trace(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                name=lvl,
                marker=dict(color=col, size=10, symbol="square"),
                showlegend=True,
                hoverinfo="skip",
            ))

    # Western Lakes corrected 2026-04-19: 263 Jefferson-only calls (was 5,633 all-district).
    # Calls/1K now ~58 — no display cap needed. Cap logic removed.

    fig3.update_layout(
        title="EMS Calls per 1,000 Population — 2024<br>"
              "<sup>Linear scale  ·  Color = service level  ·  Dashed = WI avg (254/1K)  ·  "
              "Jefferson-County calls only (corrected 2026-04-19)</sup>",
        yaxis_title="",
    )
    _apply_chart_style(fig3, height=560, legend_below=True, title_has_subtitle=True)
    fig3.update_layout(
        margin=dict(l=145, r=200, t=88, b=60),
        xaxis=dict(
            title="Calls per 1,000 Population",
            gridcolor=C_BORDER, showline=False, zeroline=False,
            tickfont=dict(size=12, color=C_TEXT),
            title_font=dict(size=12, color=C_MUTED),
        ),
        yaxis=dict(tickfont=dict(size=13, color=C_TEXT)),
    )
    # Enforce correct y-axis order (ascending by calls/1K, departments only)
    fig3.update_yaxes(
        categoryorder="array",
        categoryarray=cv_norm["Department"].tolist(),
    )
    # Callout annotation: data correction note
    fig3.add_annotation(
        x=0.99, y=0.01, xref="paper", yref="paper",
        text=(
            "All figures reflect Jefferson-County calls only (corrected 2026-04-19). "
            "Western Lakes: 263 Jeff Co. calls (~58/1K); prior all-district figure was 5,633."
        ),
        showarrow=False,
        font=dict(size=10, color=C_YELLOW),
        xanchor="right", yanchor="bottom",
        bgcolor="rgba(40,34,20,0.85)",
        bordercolor=C_YELLOW, borderwidth=1,
        borderpad=5,
    )
    # Update the bar trace now that x_vals and text_labels may have changed
    fig3.data[0].x = x_vals
    fig3.data[0].text = text_labels

    # ── Chart 3: EMS Calls per Capita (absolute cost context) ───────────────
    # Since all calls are EMS-only, show cost/call by department as the 3rd panel
    cv_cost = cv.copy()
    cv_cost["Total_Expense"] = cv_cost["Department"].map(
        dict(zip(budget["Municipality"], budget["Total_Expense"]))
    )
    cv_cost = cv_cost.dropna(subset=["Total_Expense"])
    # Exclude Whitewater: $2.7M budget covers full multi-county dept but only 64 calls
    # are Jefferson Co. contracts — cost/call is misleading without full service area context.
    cv_cost = cv_cost[cv_cost["Department"] != "Whitewater"]
    cv_cost["Cost_Per_Call"] = (cv_cost["Total_Expense"] / cv_cost["EMS_Calls"].replace(0, float("nan"))).round(0)
    cv_cost = cv_cost.dropna(subset=["Cost_Per_Call"]).sort_values("Cost_Per_Call", ascending=True)
    fig2 = go.Figure(go.Bar(
        y=cv_cost["Department"], x=cv_cost["Cost_Per_Call"],
        orientation="h",
        marker_color=C_PRIMARY,
        text=cv_cost["Cost_Per_Call"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
        customdata=cv_cost["EMS_Calls"],
        hovertemplate="<b>%{y}</b><br>Cost/EMS Call: $%{x:,.0f}<br>EMS Calls: %{customdata:,}<extra></extra>",
    ))
    fig2.update_layout(
        title="Cost per EMS Call — 2024<br><sup>Total Expense ÷ Authoritative EMS Calls · Whitewater excluded (64 Jeff Co. calls vs $2.7M full-dept budget)</sup>",
        xaxis_title="$ per EMS Call",
        xaxis_tickprefix="$",
    )
    _apply_chart_style(fig2, height=500, title_has_subtitle=True)
    fig2.update_layout(
        margin=dict(l=145, r=80, t=70, b=30),
        yaxis=dict(tickfont=dict(size=13, color=C_TEXT)),
    )
    return fig1, fig3, fig2




# FIX 5: Response time box plot with N-count annotations
@app.callback(
    Output("rt-percentile-bar",     "figure"),
    Output("rt-box",                "figure"),
    Output("rt-ems-percentile-bar", "figure"),
    Output("rt-ems-box",            "figure"),
    Input("dept-filter",        "value"),
    Input("main-tabs",          "value"),
)
def update_rt(depts, tab):
    if tab != "tab-rt":
        return no_update, no_update, no_update, no_update
    df    = filter_rt(depts)
    stats = df.groupby("Department")["RT"].agg(
        P50="median",
        P75=lambda x: x.quantile(.75),
        P90=lambda x: x.quantile(.90),
    ).reset_index().sort_values("P50")

    # Dot plot (lollipop style): more appropriate than grouped bars for percentiles.
    # Each department shows P50 / P75 / P90 as stacked dots on a vertical stem.
    fig1 = go.Figure()
    # Vertical stems from 0 to P90 for each department (drawn as thin gray lines)
    for _, row in stats.iterrows():
        fig1.add_trace(go.Scatter(
            x=[row["Department"], row["Department"]],
            y=[0, row["P90"]],
            mode="lines",
            line=dict(color=C_BORDER, width=1.5),
            showlegend=False,
            hoverinfo="skip",
        ))
    # P90 dots
    fig1.add_trace(go.Scatter(
        x=stats["Department"], y=stats["P90"],
        mode="markers+text",
        name="P90",
        marker=dict(color=C_RED, size=11, symbol="circle"),
        text=stats["P90"].round(1).astype(str),
        textposition="top center",
        textfont=dict(size=9, color=C_RED),
        hovertemplate="<b>%{x}</b><br>P90: %{y:.1f} min<extra></extra>",
    ))
    # P75 dots
    fig1.add_trace(go.Scatter(
        x=stats["Department"], y=stats["P75"],
        mode="markers+text",
        name="P75",
        marker=dict(color=C_ORANGE, size=11, symbol="circle"),
        text=stats["P75"].round(1).astype(str),
        textposition="top center",
        textfont=dict(size=9, color=C_ORANGE),
        hovertemplate="<b>%{x}</b><br>P75: %{y:.1f} min<extra></extra>",
    ))
    # P50 (median) dots
    fig1.add_trace(go.Scatter(
        x=stats["Department"], y=stats["P50"],
        mode="markers+text",
        name="Median (P50)",
        marker=dict(color=C_GREEN, size=11, symbol="circle"),
        text=stats["P50"].round(1).astype(str),
        textposition="bottom center",
        textfont=dict(size=9, color=C_GREEN),
        hovertemplate="<b>%{x}</b><br>Median: %{y:.1f} min<extra></extra>",
    ))
    fig1.add_hline(y=8, line_dash="dash", line_color=C_YELLOW,
                   annotation_text="8-min clinical benchmark",
                   annotation_font_color=C_YELLOW)
    fig1.update_layout(
        title="Response Time Percentiles — All Incident Types (2024 NFIRS Data)<br>"
              "<sup>Dots = P50 (green), P75 (orange), P90 (red)  ·  Sorted by median RT</sup>",
        yaxis_title="Minutes",
    )
    _apply_chart_style(fig1, height=520, legend_below=True, title_has_subtitle=True)
    fig1.update_layout(
        margin=dict(l=40, r=80, t=80, b=140),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
        yaxis=dict(rangemode="tozero"),
    )

    fig2 = px.box(df, x="Department", y="RT", color="Department",
                  title="Response Time Distribution — All Incident Types (2024 NFIRS Data)",
                  labels={"RT": "Minutes"})
    fig2.update_traces(
        line_color=C_PRIMARY,
        marker_color=C_PRIMARY,
        fillcolor="rgba(242,140,56,0.18)",
        hovertemplate="<b>%{x}</b><br>RT: %{y:.1f} min<extra></extra>",
    )
    fig2.update_layout(showlegend=False)
    fig2.add_hline(y=8, line_dash="dash", line_color=C_YELLOW,
                   annotation_text="8-min benchmark",
                   annotation_font_color=C_YELLOW)
    _apply_chart_style(fig2, height=520)
    fig2.update_layout(
        margin=dict(l=40, r=40, t=60, b=120),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
    )

    # Add n-count annotations at the bottom of the plot area
    n_counts = df.groupby("Department").size()
    all_annot = [
        dict(
            x=dept, y=0,
            text=f"n={n_counts.get(dept, 0):,}",
            font=dict(size=9, color=C_MUTED),
            showarrow=False, xref="x", yref="paper",
            yanchor="top",
        )
        for dept in sorted(df["Department"].unique())
    ]
    fig2.update_layout(annotations=all_annot)

    # ── fig3: EMS-only percentile bar ─────────────────────────────────────────
    df_ems = df[df["IsEMS"]]
    if df_ems.empty:
        fig3 = go.Figure()
        fig3.update_layout(title="EMS-Only Response Times (no data for selected depts)")
        _apply_chart_style(fig3, height=440)
    else:
        stats_ems = df_ems.groupby("Department")["RT"].agg(
            P50="median",
            P75=lambda x: x.quantile(.75),
            P90=lambda x: x.quantile(.90),
        ).reset_index().sort_values("P50")

        # Dot plot (lollipop style) for EMS-only percentiles — same approach as all-incidents
        fig3 = go.Figure()
        for _, row in stats_ems.iterrows():
            fig3.add_trace(go.Scatter(
                x=[row["Department"], row["Department"]],
                y=[0, row["P90"]],
                mode="lines",
                line=dict(color=C_BORDER, width=1.5),
                showlegend=False,
                hoverinfo="skip",
            ))
        fig3.add_trace(go.Scatter(
            x=stats_ems["Department"], y=stats_ems["P90"],
            mode="markers+text",
            name="P90",
            marker=dict(color=C_RED, size=11, symbol="circle"),
            text=stats_ems["P90"].round(1).astype(str),
            textposition="top center",
            textfont=dict(size=9, color=C_RED),
            hovertemplate="<b>%{x}</b><br>P90: %{y:.1f} min<extra></extra>",
        ))
        fig3.add_trace(go.Scatter(
            x=stats_ems["Department"], y=stats_ems["P75"],
            mode="markers+text",
            name="P75",
            marker=dict(color=C_ORANGE, size=11, symbol="circle"),
            text=stats_ems["P75"].round(1).astype(str),
            textposition="top center",
            textfont=dict(size=9, color=C_ORANGE),
            hovertemplate="<b>%{x}</b><br>P75: %{y:.1f} min<extra></extra>",
        ))
        fig3.add_trace(go.Scatter(
            x=stats_ems["Department"], y=stats_ems["P50"],
            mode="markers+text",
            name="Median (P50)",
            marker=dict(color=C_GREEN, size=11, symbol="circle"),
            text=stats_ems["P50"].round(1).astype(str),
            textposition="bottom center",
            textfont=dict(size=9, color=C_GREEN),
            hovertemplate="<b>%{x}</b><br>Median: %{y:.1f} min<extra></extra>",
        ))
        # Three NFPA reference lines: BLS 4 min (green), ALS 8 min (yellow), Rural 14 min (red)
        fig3.add_hline(y=_BENCH["nfpa_1710_bls_min"], line_dash="dash",
                       line_color=C_GREEN, line_width=1.5,
                       annotation_text="NFPA 1710 BLS (4 min)",
                       annotation_font_color=C_GREEN,
                       annotation_position="top right")
        fig3.add_hline(y=_BENCH["nfpa_1710_als_min"], line_dash="dash",
                       line_color=C_YELLOW, line_width=1.5,
                       annotation_text="NFPA 1710 ALS (8 min)",
                       annotation_font_color=C_YELLOW,
                       annotation_position="top right")
        fig3.add_hline(y=_BENCH["nfpa_1720_rural_min"], line_dash="dash",
                       line_color=C_RED, line_width=1.5,
                       annotation_text="NFPA 1720 Rural (14 min)",
                       annotation_font_color=C_RED,
                       annotation_position="top right")
        fig3.update_layout(
            title=(
                "Response Time Percentiles \u2014 EMS Calls Only (2024 NFIRS Data)<br>"
                "<sup>Dots = P50 (green), P75 (orange), P90 (red)  ·  "
                "NFPA 1710 = career depts (90th pctl target); "
                "NFPA 1720 = volunteer depts (80th pctl target)</sup>"
            ),
            yaxis_title="Minutes",
        )
        _apply_chart_style(fig3, height=480, legend_below=True, title_has_subtitle=True)
        fig3.update_layout(
            margin=dict(l=40, r=150, t=88, b=130),
            xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=11, color=C_TEXT)),
            yaxis=dict(rangemode="tozero"),
        )

    # ── fig4: EMS-only box plot, colored by ALS/BLS service level ─────────────
    if df_ems.empty:
        fig4 = go.Figure()
        fig4.update_layout(title="EMS Response Time Distribution (no data)")
        _apply_chart_style(fig4, height=440)
    else:
        # Map each department to its service level color
        _SVC_BOX_COLORS = {
            "ALS":     C_ORANGE,
            "AEMT":    C_PRIMARY,
            "BLS":     C_GREEN,
            "N/A":     C_BORDER,
            "Unknown": "#D1D5DB",
        }
        fig4 = go.Figure()
        # Sort departments by median EMS RT ascending for readability
        dept_order = (
            df_ems.groupby("Department")["RT"]
            .median().sort_values().index.tolist()
        )
        for dept in dept_order:
            dept_df = df_ems[df_ems["Department"] == dept]
            if len(dept_df) < 5:
                continue  # skip depts with too few EMS calls for a meaningful box
            svc_level = ALS_LEVELS.get(dept, {}).get("Level", "Unknown")
            box_color = _SVC_BOX_COLORS.get(svc_level, "#D1D5DB")
            # Parse hex color for rgba fill
            r = int(box_color[1:3], 16)
            g = int(box_color[3:5], 16)
            b = int(box_color[5:7], 16)
            fig4.add_trace(go.Box(
                x=dept_df["Department"],
                y=dept_df["RT"],
                name=dept,
                marker_color=box_color,
                line_color=box_color,
                fillcolor=f"rgba({r},{g},{b},0.18)",
                hovertemplate=(
                    f"<b>{dept}</b> ({svc_level})<br>"
                    "RT: %{y:.1f} min<extra></extra>"
                ),
                showlegend=False,
            ))
        # Legend entries as invisible scatter markers (avoids y-axis pollution)
        for lvl, col in _SVC_BOX_COLORS.items():
            if lvl in ("N/A", "Unknown"):
                continue
            fig4.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(symbol="square", color=col, size=10),
                name=lvl, showlegend=True, hoverinfo="skip",
            ))
        # Three NFPA reference lines
        fig4.add_hline(y=_BENCH["nfpa_1710_bls_min"], line_dash="dash",
                       line_color=C_GREEN, line_width=1.5,
                       annotation_text="NFPA 1710 BLS (4 min)",
                       annotation_font_color=C_GREEN,
                       annotation_position="top right")
        fig4.add_hline(y=_BENCH["nfpa_1710_als_min"], line_dash="dash",
                       line_color=C_YELLOW, line_width=1.5,
                       annotation_text="NFPA 1710 ALS (8 min)",
                       annotation_font_color=C_YELLOW,
                       annotation_position="top right")
        fig4.add_hline(y=_BENCH["nfpa_1720_rural_min"], line_dash="dash",
                       line_color=C_RED, line_width=1.5,
                       annotation_text="NFPA 1720 Rural (14 min)",
                       annotation_font_color=C_RED,
                       annotation_position="top right")
        fig4.update_layout(
            title="EMS Response Time Distribution \u2014 Colored by Service Level (2024 NFIRS Data)",
            yaxis_title="Minutes",
            showlegend=True,
        )
        _apply_chart_style(fig4, height=440, legend_below=True)
        # n-count annotations at bottom of each box
        n_counts_ems = df_ems.groupby("Department").size()
        ems_annot = [
            dict(
                x=dept, y=0,
                text=f"n={n_counts_ems.get(dept, 0):,}",
                font=dict(size=9, color=C_MUTED),
                showarrow=False, xref="x", yref="paper",
                yanchor="top",
            )
            for dept in dept_order
            if len(df_ems[df_ems["Department"] == dept]) >= 5
        ]
        fig4.update_layout(
            annotations=ems_annot,
            margin=dict(l=40, r=120, t=60, b=130),
            xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=11, color=C_TEXT)),
        )

    return fig1, fig2, fig3, fig4


# FIX 3 & 4: Heatmaps with normalization + monthly trend with county aggregate
@app.callback(
    Output("heat-hour",    "figure"),
    Output("heat-dow",     "figure"),
    Output("monthly-trend","figure"),
    Input("dept-filter",   "value"),
    Input("main-tabs",     "value"),
)
def update_temporal(depts, tab):
    if tab != "tab-calls":
        return no_update, no_update, no_update
    df = filter_raw(depts)

    # FIX 3: Hour heatmap — row-normalized by dept average
    hp     = df.groupby(["Department","Hour"]).size().reset_index(name="Calls")
    hp_piv = hp.pivot_table(index="Department", columns="Hour", values="Calls", fill_value=0)
    # Normalize: divide each row by that dept's mean across hours
    row_means = hp_piv.mean(axis=1)
    hp_piv_norm = hp_piv.div(row_means, axis=0).round(2)

    fig_h = go.Figure(go.Heatmap(
        z=hp_piv_norm.values,
        customdata=hp_piv.values,
        y=hp_piv_norm.index.tolist(),
        x=[f"{int(c):02d}:00" for c in hp_piv_norm.columns],
        colorscale=[[0, "#2E2A1E"], [0.5, C_PRIMARY], [1, "#F7C143"]],
        hovertemplate=(
            "<b>%{y}</b><br>Hour: %{x}<br>"
            "Calls: %{customdata}<br>"
            "Relative intensity: %{z:.2f}x avg<extra></extra>"
        ),
    ))
    fig_h.update_layout(
        title="Call Intensity by Hour — Relative to Dept Average<br>"
              "<sup>1.0 = average hour for that department · 2024 NFIRS Data</sup>",
        xaxis_title="Hour of Day", yaxis_title="",
    )
    _apply_chart_style(fig_h, height=520, title_has_subtitle=True)
    fig_h.update_layout(
        margin=dict(l=145, r=20, t=82, b=50),
        yaxis=dict(tickfont=dict(size=12, color=C_TEXT)),
    )

    # DOW heatmap — row-normalized
    DOW    = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    dp     = df.groupby(["Department","Alarm Date - Day of Week"]).size().reset_index(name="Calls")
    dp_piv = dp.pivot_table(index="Department", columns="Alarm Date - Day of Week",
                            values="Calls", fill_value=0)
    dp_piv = dp_piv.reindex(columns=[d for d in DOW if d in dp_piv.columns], fill_value=0)
    dp_row_means = dp_piv.mean(axis=1)
    dp_piv_norm  = dp_piv.div(dp_row_means, axis=0).round(2)

    fig_d = go.Figure(go.Heatmap(
        z=dp_piv_norm.values,
        customdata=dp_piv.values,
        y=dp_piv_norm.index.tolist(),
        x=dp_piv_norm.columns.tolist(),
        colorscale=[[0, "#2E1E1E"], [0.5, C_ORANGE], [1, "#F28C38"]],
        hovertemplate=(
            "<b>%{y}</b><br>Day: %{x}<br>"
            "Calls: %{customdata}<br>"
            "Relative intensity: %{z:.2f}x avg<extra></extra>"
        ),
    ))
    fig_d.update_layout(
        title="Call Intensity by Day of Week — Relative to Dept Average<br>"
              "<sup>1.0 = average day for that department · 2024 NFIRS Data</sup>",
    )
    _apply_chart_style(fig_d, height=520, title_has_subtitle=True)
    fig_d.update_layout(
        margin=dict(l=145, r=20, t=82, b=50),
        yaxis=dict(tickfont=dict(size=12, color=C_TEXT)),
    )

    # Monthly trend — county total (bold accent) + individual dept lines (faded)
    mt     = df.groupby(["Department","Month"]).size().reset_index(name="Calls")
    mt_piv = mt.pivot_table(index="Month", columns="Department", values="Calls", fill_value=0)
    county_total = df.groupby("Month").size().reset_index(name="Total")

    fig_m = go.Figure()
    for dept in mt_piv.columns:
        fig_m.add_trace(go.Scatter(
            x=[MONTH_NAMES.get(m, m) for m in mt_piv.index],
            y=mt_piv[dept],
            name=dept,
            mode="lines+markers",
            line=dict(color=CMAP.get(dept), width=1),
            marker=dict(size=4),
            opacity=0.35,
            showlegend=True,
        ))
    # County total — thick accent line on top
    fig_m.add_trace(go.Scatter(
        x=[MONTH_NAMES.get(m, m) for m in county_total["Month"]],
        y=county_total["Total"],
        name="County Total",
        mode="lines+markers",
        line=dict(color=C_PRIMARY, width=3),
        marker=dict(size=7, color=C_PRIMARY),
        opacity=1.0,
    ))
    fig_m.update_layout(
        title="Monthly Call Volume Trends — County Total + Individual Depts (2024 NFIRS Data)",
        xaxis_title="Month", yaxis_title="Calls",
    )
    _apply_chart_style(fig_m, height=460, legend_below=False)
    # With 15+ department traces the legend is very long; hide individual dept lines in legend
    # and show only the County Total legend entry so the chart remains readable.
    for trace in fig_m.data:
        if trace.name != "County Total":
            trace.showlegend = False
    fig_m.update_layout(
        margin=dict(l=55, r=20, t=60, b=50),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        # Add subtitle note about faded lines
        annotations=[dict(
            x=0, y=1.0, xref="paper", yref="paper",
            text="Faded lines = individual departments; bold orange = county total",
            showarrow=False,
            font=dict(size=10, color=C_MUTED),
            xanchor="left", yanchor="bottom",
            bgcolor="rgba(0,0,0,0)",
        )],
    )
    return fig_h, fig_d, fig_m


@app.callback(
    Output("aid-bar",       "figure"),
    Output("aid-ratio-bar", "figure"),
    Input("dept-filter", "value"),
    Input("main-tabs",   "value"),
)
def update_aid(depts, tab):
    if tab != "tab-calls":
        return no_update, no_update
    df  = filter_raw(depts)

    # ── Raw count chart (unchanged) ───────────────────────────────────────────
    aid = df[df["Aid Given or Received Description"].notna()].groupby(
        ["Department","Aid Given or Received Description"]).size().reset_index(name="Count")
    fig = px.bar(aid, x="Department", y="Count", color="Aid Given or Received Description",
                 title="Mutual Aid Activity — 2024 NFIRS Data", barmode="group",
                 color_discrete_sequence=[C_PRIMARY, C_ORANGE, C_GREEN, C_RED, "#8B5CF6"],
                 labels={"Aid Given or Received Description": "Aid Type"})
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y:,}<extra></extra>",
    )
    _apply_chart_style(fig, height=480, legend_below=False)
    fig.update_layout(
        margin=dict(l=40, r=40, t=60, b=120),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
    )

    # ── Dependency ratio chart (NEW) ──────────────────────────────────────────
    # Total calls per department (from filtered data)
    total_calls = df.groupby("Department").size().rename("Total")

    # Aid received = any category containing "received"
    # Aid given    = any category containing "given"
    aid_col = "Aid Given or Received Description"
    df_aid = df[df[aid_col].notna()].copy()
    df_aid["AidReceived"] = df_aid[aid_col].str.contains("received", case=False, na=False)
    df_aid["AidGiven"]    = df_aid[aid_col].str.contains("given",    case=False, na=False)

    recv_counts  = df_aid[df_aid["AidReceived"]].groupby("Department").size().rename("RecvCount")
    given_counts = df_aid[df_aid["AidGiven"]].groupby("Department").size().rename("GivenCount")

    ratio_df = (
        total_calls
        .to_frame()
        .join(recv_counts,  how="left")
        .join(given_counts, how="left")
        .fillna(0)
        .reset_index()
    )
    ratio_df["RecvPct"]  = (ratio_df["RecvCount"]  / ratio_df["Total"] * 100).round(1)
    ratio_df["GivenPct"] = (ratio_df["GivenCount"] / ratio_df["Total"] * 100).round(1)
    ratio_df = ratio_df.sort_values("RecvPct", ascending=False)

    # Only show departments that have any aid activity (suppress zero-only rows)
    ratio_df = ratio_df[(ratio_df["RecvPct"] > 0) | (ratio_df["GivenPct"] > 0)]

    if ratio_df.empty:
        fig_r = go.Figure()
        fig_r.add_annotation(
            text="No mutual aid activity in selected departments",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color=C_MUTED),
        )
        _apply_chart_style(fig_r, height=380)
        return fig, fig_r

    # Color: received = red (dependency indicator); given = green (capacity indicator)
    recv_color  = C_RED    # "#EF4444"
    given_color = C_GREEN  # "#10B981"

    fig_r = go.Figure()
    fig_r.add_trace(go.Bar(
        name="Aid Received (% of Total Calls)",
        x=ratio_df["Department"],
        y=ratio_df["RecvPct"],
        marker_color=recv_color,
        text=ratio_df["RecvPct"].apply(lambda v: f"{v:.1f}%" if v > 0 else ""),
        textposition="outside",
        customdata=ratio_df[["RecvCount", "GivenCount", "Total"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Aid Received: %{customdata[0]:.0f} calls (%{y:.1f}% of total)<br>"
            "Aid Given: %{customdata[1]:.0f} calls<br>"
            "Total Calls: %{customdata[2]:.0f}<extra></extra>"
        ),
    ))
    fig_r.add_trace(go.Bar(
        name="Aid Given (% of Total Calls)",
        x=ratio_df["Department"],
        y=ratio_df["GivenPct"],
        marker_color=given_color,
        text=ratio_df["GivenPct"].apply(lambda v: f"{v:.1f}%" if v > 0 else ""),
        textposition="outside",
        customdata=ratio_df[["RecvCount", "GivenCount", "Total"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Aid Given: %{customdata[1]:.0f} calls (%{y:.1f}% of total)<br>"
            "Aid Received: %{customdata[0]:.0f} calls<br>"
            "Total Calls: %{customdata[2]:.0f}<extra></extra>"
        ),
    ))

    # 20% structural-dependency reference line
    fig_r.add_hline(
        y=20, line_dash="dash", line_color="#F59E0B", line_width=2,
        annotation_text="20% dependency threshold",
        annotation_position="top right",
        annotation_font=dict(size=11, color="#F59E0B"),
    )

    _apply_chart_style(
        fig_r, height=420, legend_below=False,
        title_has_subtitle=True,
    )
    fig_r.update_layout(
        title=dict(
            text=(
                "Mutual Aid Dependency Ratio \u2014 Aid as % of Total Calls<br>"
                "<sup>Departments above 20% received aid are structurally dependent on neighbors</sup>"
            ),
        ),
        barmode="group",
        yaxis=dict(
            ticksuffix="%",
            range=[0, max(ratio_df["RecvPct"].max(), ratio_df["GivenPct"].max()) * 1.25 + 5],
        ),
        margin=dict(l=40, r=40, t=80, b=110),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=11, color=C_TEXT)),
        legend=dict(
            orientation="h", y=1.06, x=0,
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
    )

    return fig, fig_r


# ── Multi-Provider Coverage callback ─────────────────────────────────────────
# Provider color palette (consistent across chart)
_PROVIDER_COLORS = {
    "Fort Atkinson": "#00838F", "Jefferson": "#F7C143", "Johnson Creek": "#10B981",
    "Lake Mills": "#60A5FA", "Watertown": "#EF4444", "Ixonia": "#A78BFA",
    "Western Lakes": "#F472B6", "Edgerton": "#34D399", "Cambridge": "#FB923C",
    "Whitewater": "#818CF8", "Palmyra": "#FBBF24", "Waterloo": "#2DD4BF",
}

@app.callback(
    Output("coverage-overlap-bar", "figure"),
    Input("dept-filter",           "value"),
    Input("main-tabs",             "value"),
)
def update_coverage(depts, tab):
    if tab != "tab-calls":
        return no_update

    selected = set(depts) if depts else set(AUTH_EMS_CALLS.keys())

    # Filter to towns where at least one selected dept is a provider
    filtered = {}
    for town, providers in MULTI_PROVIDER_COVERAGE.items():
        if any(p in selected for p, _ in providers):
            filtered[town] = providers

    if not filtered:
        fig = go.Figure()
        fig.add_annotation(text="No multi-provider towns for selected departments",
                          xref="paper", yref="paper", x=0.5, y=0.5,
                          showarrow=False, font=dict(size=13, color=C_MUTED))
        _apply_chart_style(fig, height=300)
        return fig

    # Sort by number of providers (desc), then total pop (desc)
    sorted_towns = sorted(filtered.items(),
                          key=lambda kv: (len(kv[1]), sum(p for _, p in kv[1])),
                          reverse=True)

    # Build stacked bar traces — one trace per provider
    all_providers = sorted({p for _, provs in sorted_towns for p, _ in provs})
    town_names = [t for t, _ in sorted_towns]

    fig = go.Figure()
    for provider in all_providers:
        pops = []
        for town, provs in sorted_towns:
            prov_dict = {p: pop for p, pop in provs}
            pops.append(prov_dict.get(provider, 0))
        fig.add_trace(go.Bar(
            y=town_names, x=pops,
            name=provider, orientation="h",
            marker_color=_PROVIDER_COLORS.get(provider, C_MUTED),
            hovertemplate=f"<b>{provider}</b><br>%{{y}}: %{{x:,}} pop served<extra></extra>",
        ))

    fig.update_layout(
        title="Multi-Provider Towns — Population Served by Each EMS Provider",
        xaxis_title="Population Served",
        barmode="stack",
    )
    _apply_chart_style(fig, height=max(350, len(town_names) * 35 + 120), legend_below=True)
    fig.update_layout(
        margin=dict(l=160, r=30, t=55, b=80),
        yaxis=dict(tickfont=dict(size=11, color=C_TEXT), autorange="reversed"),
    )
    return fig


# Portage charts — static, computed once on first access
@lru_cache(maxsize=1)
def _get_portage_figs():
    fig_v = px.bar(portage_vol, x="Year", y=["ALS","BLS"],
                   title="Portage Co. Call Volume — ALS vs BLS (Countywide EMS Benchmark)",
                   barmode="stack",
                   color_discrete_map={"ALS": C_PRIMARY, "BLS": C_GREEN},
                   labels={"value": "Calls", "variable": "Level"})
    fig_v.update_traces(hovertemplate="<b>%{fullData.name}</b> · %{x}: %{y:,} calls<extra></extra>")
    _apply_chart_style(fig_v, height=380, legend_below=False)
    fig_v.update_layout(margin=dict(l=50, r=40, t=60, b=60))

    # Revenue chart with secondary y-axis for collection rate
    fig_r = make_subplots(specs=[[{"secondary_y": True}]])
    fig_r.add_trace(
        go.Bar(x=portage_rev["Year"], y=portage_rev["Charges"],
               name="Gross Charges", marker_color="#8B6F47",
               hovertemplate="<b>%{x}</b><br>Gross Charges: $%{y:,.0f}<extra></extra>"),
        secondary_y=False,
    )
    fig_r.add_trace(
        go.Bar(x=portage_rev["Year"], y=portage_rev["Revenue"],
               name="Net Revenue", marker_color=C_PRIMARY,
               hovertemplate="<b>%{x}</b><br>Net Revenue: $%{y:,.0f}<extra></extra>"),
        secondary_y=False,
    )
    fig_r.add_trace(
        go.Scatter(
            x=portage_rev["Year"], y=portage_rev["Collection_Rate_Pct"],
            name="Collection Rate %", mode="lines+markers",
            line=dict(color=C_RED, dash="dash", width=2),
            marker=dict(size=7, color=C_RED),
            hovertemplate="<b>%{x}</b><br>Collection Rate: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig_r.update_yaxes(title_text="$ Amount", secondary_y=False,
                       gridcolor=C_BORDER, tickfont=dict(size=12))
    fig_r.update_yaxes(title_text="Collection Rate %", secondary_y=True, range=[0, 60],
                       tickfont=dict(size=12))
    fig_r.update_layout(
        title="Portage Co. Revenue vs. Charges — Collection Rate Declining",
        barmode="group",
    )
    _apply_chart_style(fig_r, height=360, legend_below=False)

    # Payor mix — grouped bar: % of calls vs % of revenue
    portage_pay_plot = portage_pay.copy()
    portage_pay_plot["Revenue_Pct"] = (
        portage_pay_plot["payments"] / portage_pay_plot["payments"].sum() * 100
    )
    fig_p = go.Figure([
        go.Bar(
            x=portage_pay_plot["Payor"], y=portage_pay_plot["pct"],
            name="% of Calls", marker_color=C_GREEN,
            text=portage_pay_plot["pct"].round(1),
            texttemplate="%{text:.1f}%", textposition="outside",
            hovertemplate="<b>%{x}</b><br>% of Calls: %{y:.1f}%<extra></extra>",
        ),
        go.Bar(
            x=portage_pay_plot["Payor"], y=portage_pay_plot["Revenue_Pct"],
            name="% of Revenue", marker_color=C_PRIMARY,
            text=portage_pay_plot["Revenue_Pct"].round(1),
            texttemplate="%{text:.1f}%", textposition="outside",
            hovertemplate="<b>%{x}</b><br>% of Revenue: %{y:.1f}%<extra></extra>",
        ),
    ])
    fig_p.update_layout(
        barmode="group",
        title="Portage 2024 Payor Mix: % of Calls vs % of Revenue<br>"
              "<sup>Private Pay = high % of calls but low % of revenue</sup>",
    )
    _apply_chart_style(fig_p, height=400, legend_below=True, title_has_subtitle=True)
    fig_p.update_layout(margin=dict(l=50, r=40, t=80, b=80))
    return fig_v, fig_r, fig_p


# Budget charts — static, computed once on first access
@lru_cache(maxsize=1)
def _get_budget_figs():
    b = budget.dropna(subset=["Total_Expense"])

    # Fill NaN EMS_Revenue / Net_Tax with 0 for plotting; Edgerton data not yet sourced.
    b_plot = b.copy()
    b_plot["EMS_Revenue"] = b_plot["EMS_Revenue"].fillna(0)
    b_plot["Net_Tax"]     = b_plot["Net_Tax"].fillna(0)

    # -- Sankey diagram: funding sources → each municipality's total expense --
    # Left side  = 3 funding source categories
    # Right side = each municipality (sized by total expense)
    # Flow width = dollar amount from that source into that department.
    b_plot["Other_Revenue"] = (
        b_plot["Total_Expense"] - b_plot["EMS_Revenue"] - b_plot["Net_Tax"]
    ).clip(lower=0)

    # ── 3-column Sankey: Known Funding → Municipalities → Total Expenses ────
    # IMPORTANT: We only show the two *confirmed* revenue streams — EMS billing
    # and tax levy. The gap between (Revenue + Tax) and Total Expense is real:
    # it's an unfunded shortfall covered by fund balance drawdowns, grants,
    # or other sources we can't confirm. By NOT plugging it with a fake "Other"
    # category, departments with deficits are visually obvious — the expense
    # node on the right will be fatter than the funding flowing in from the left.
    b_plot = b_plot.sort_values("Total_Expense", ascending=False).reset_index(drop=True)
    munis = b_plot["Municipality"].tolist()
    n_munis = len(munis)

    def _sk_fmt(v):
        if abs(v) >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if abs(v) >= 1_000:
            return f"${v / 1_000:.0f}K"
        return f"${v:,.0f}"

    # Compute known funding vs expense gap per municipality
    b_plot["Known_Funding"] = b_plot["EMS_Revenue"] + b_plot["Net_Tax"]
    b_plot["Funding_Gap"] = b_plot["Total_Expense"] - b_plot["Known_Funding"]

    # ── Node indices ──
    # 0 = EMS Revenue, 1 = Tax Levy
    # 2..2+n-1 = municipalities (middle column)
    # 2+n..2+2n-1 = expense nodes (right column)
    SRC_REV, SRC_TAX = 0, 1
    MUNI_START = 2
    EXP_START = 2 + n_munis

    muni_idx = {m: MUNI_START + i for i, m in enumerate(munis)}
    exp_idx  = {m: EXP_START + i for i, m in enumerate(munis)}

    tot_rev = b_plot["EMS_Revenue"].sum()
    tot_tax = b_plot["Net_Tax"].sum()
    tot_exp = b_plot["Total_Expense"].sum()
    tot_gap = b_plot["Funding_Gap"].clip(lower=0).sum()

    # -- Node labels --
    src_labels = [
        f"EMS Revenue  {_sk_fmt(tot_rev)}",
        f"Property Tax Levy  {_sk_fmt(tot_tax)}",
    ]
    muni_labels = list(munis)
    exp_labels = []
    for _, row in b_plot.iterrows():
        gap = row["Funding_Gap"]
        if gap > 100:
            tag = f"Gap: {_sk_fmt(gap)}"
        elif gap < -100:
            tag = f"Surplus: +{_sk_fmt(abs(gap))}"
        else:
            tag = "Fully Funded"
        exp_labels.append(f"Expenses {_sk_fmt(row['Total_Expense'])}  ({tag})")

    node_labels = src_labels + muni_labels + exp_labels

    # -- Node colors --
    src_colors = [
        "rgba(16,185,129,0.95)",   # green — EMS Revenue
        "rgba(96,165,250,0.95)",   # blue  — Tax Levy (neutral gov't funding, not "expense" red)
    ]
    muni_colors = ["rgba(140,150,165,0.80)"] * n_munis
    exp_colors = []
    for _, row in b_plot.iterrows():
        gap = row["Funding_Gap"]
        if gap > 100:
            exp_colors.append("rgba(217,65,51,0.75)")    # red — underfunded
        else:
            exp_colors.append("rgba(16,185,129,0.75)")   # green — fully covered
    node_colors = src_colors + muni_colors + exp_colors

    # -- Node positions --
    n_total = len(node_labels)
    node_x = [0.0] * n_total
    node_y = [0.0] * n_total
    # Left column: 2 source nodes
    node_x[SRC_REV] = 0.001; node_y[SRC_REV] = 0.15
    node_x[SRC_TAX] = 0.001; node_y[SRC_TAX] = 0.70
    # Middle + Right columns: spread municipalities evenly
    for i, m in enumerate(munis):
        y_pos = 0.01 + (i / max(n_munis - 1, 1)) * 0.98
        node_x[muni_idx[m]] = 0.42
        node_y[muni_idx[m]] = y_pos
        node_x[exp_idx[m]] = 0.999
        node_y[exp_idx[m]] = y_pos

    # -- Links --
    sources, targets, values, link_colors = [], [], [], []

    # Left → Middle: known funding into each municipality
    for _, row in b_plot.iterrows():
        m = row["Municipality"]
        if row["EMS_Revenue"] > 0:
            sources.append(SRC_REV)
            targets.append(muni_idx[m])
            values.append(row["EMS_Revenue"])
            link_colors.append("rgba(16,185,129,0.22)")
        if row["Net_Tax"] > 0:
            sources.append(SRC_TAX)
            targets.append(muni_idx[m])
            values.append(row["Net_Tax"])
            link_colors.append("rgba(96,165,250,0.22)")

    # Middle → Right: municipality → its expense node (full expense amount)
    # Sankey requires: flow out of muni = flow into muni. Since we're only
    # sending known funding in, we link min(known_funding, total_expense) as
    # the "funded" flow, then the expense node's size shows the full cost.
    # To make the expense node correctly sized, we send Total_Expense as the
    # link value — Plotly will size the muni node to the MAX of in/out.
    for _, row in b_plot.iterrows():
        m = row["Municipality"]
        sources.append(muni_idx[m])
        targets.append(exp_idx[m])
        # Use Total_Expense so the right node shows true cost
        values.append(row["Total_Expense"])
        gap = row["Funding_Gap"]
        if gap > 100:
            link_colors.append("rgba(217,65,51,0.15)")   # reddish — deficit flow
        else:
            link_colors.append("rgba(16,185,129,0.15)")  # greenish — funded flow

    fig_b = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=12,
            thickness=20,
            line=dict(color=C_BORDER, width=0.5),
            label=node_labels,
            color=node_colors,
            x=node_x,
            y=node_y,
            hovertemplate="<b>%{label}</b><extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
            hovertemplate=(
                "%{source.label} → %{target.label}<br>"
                "<b>$%{value:,.0f}</b><extra></extra>"
            ),
        ),
    ))
    fig_b.update_layout(
        title="EMS Funding Flow: Revenue → Departments → Expenses (FY2025)<br>"
              "<sup>Green = EMS billing revenue · Blue = property tax levy · "
              "Right: green = fully funded, red = funding gap · "
              "Edgerton revenue/tax N/A</sup>",
    )
    _apply_chart_style(fig_b, height=700, legend_below=True, title_has_subtitle=True)
    fig_b.update_layout(margin=dict(l=5, r=5, t=88, b=50))

    # ── Billing rates chart: Jefferson Co. confirmed (solid) + WI peer benchmarks (faded) ────────
    # Design decisions:
    #   - No blank-string spacer x-tick; instead, two separate x-category arrays + add_shape band
    #     render a clean visual separator without an empty tick mark.
    #   - None/NaN rates (e.g. Madison ALS2, Brookfield ALS1) are plotted as y=0 with invisible
    #     marker so the bar slot exists, then a scatter "N/A" text trace marks each absent rate.
    #   - Text labels: "$1,500" for real values, blank for None (suppressed via conditional list).
    #     A second pass of scatter text draws "N/A" above the zero-height bars.
    #   - Hover templates include Source + Note from wi_billing_benchmarks for WI peer bars.

    _jeff_munis   = list(billing["Municipality"])
    _bench_munis  = list(wi_billing_benchmarks["Municipality"])
    # No spacer in x-list; separation is achieved via shading + annotation below.
    _all_munis = _jeff_munis + _bench_munis

    nj = len(_jeff_munis)   # number of Jefferson Co. entries
    nb = len(_bench_munis)  # number of benchmark entries
    n  = nj + nb

    # ── Raw value arrays (None where rate doesn't exist) ──────────────────────────────────────────
    def _safe(series):
        return [v if pd.notna(v) else None for v in series]

    _bls_vals_j  = list(billing["BLS"])
    _als1_vals_j = list(billing["ALS1"])
    _als2_vals_j = list(billing["ALS2"])

    _bls_vals_b  = _safe(wi_billing_benchmarks["BLS"])
    _als1_vals_b = _safe(wi_billing_benchmarks["ALS1"])
    _als2_vals_b = _safe(wi_billing_benchmarks["ALS2"])

    _bls_vals  = _bls_vals_j  + _bls_vals_b
    _als1_vals = _als1_vals_j + _als1_vals_b
    _als2_vals = _als2_vals_j + _als2_vals_b

    # ── y-arrays for plotting: replace None with 0 so bar slot renders (invisible color) ─────────
    def _plot_y(vals):
        return [v if v is not None else 0 for v in vals]

    # ── Text label arrays: "$1,500" for real values, "" for None (label suppressed) ─────────────
    def _bar_text(vals):
        # Cast floats (e.g. 2200.0 from pandas float64 column) to int before formatting
        # so labels render as "$2,200" not "$2,200.0".
        return [f"${int(v):,}" if v is not None else "" for v in vals]

    # ── Bar color arrays: solid for Jefferson Co., faded for benchmarks, transparent for None ────
    # Jefferson Co. always has real values (all 3 rate levels confirmed), so no transparency needed.
    # For benchmark bars: faded if rate exists, fully transparent if None (invisible zero bar).
    _bls_colors_b  = ["rgba(139,111,71,0.45)" if v is not None else "rgba(0,0,0,0)" for v in _bls_vals_b]
    _als1_colors_b = ["rgba(37,99,235,0.35)"  if v is not None else "rgba(0,0,0,0)" for v in _als1_vals_b]
    _als2_colors_b = ["rgba(247,193,67,0.45)" if v is not None else "rgba(0,0,0,0)" for v in _als2_vals_b]

    _bls_colors  = ["#8B6F47"]  * nj + _bls_colors_b
    _als1_colors = [C_PRIMARY]  * nj + _als1_colors_b
    _als2_colors = [C_YELLOW]   * nj + _als2_colors_b

    # ── Hover text arrays ─────────────────────────────────────────────────────────────────────────
    # Jefferson Co.: simple rate display.
    # WI peers: include Source and Note from wi_billing_benchmarks.
    _bench_src   = list(wi_billing_benchmarks["Source"])
    _bench_note  = list(wi_billing_benchmarks["Note"])

    def _hover_jeff(level, vals):
        return [f"<b>{m}</b> (Jefferson Co.)<br>{level}: ${int(v):,}<br>"
                f"<i>Confirmed from 2025 fee schedule PDF</i><extra></extra>"
                for m, v in zip(_jeff_munis, vals)]

    def _hover_bench(level, vals):
        rows = []
        for m, v, src, note in zip(_bench_munis, vals, _bench_src, _bench_note):
            if v is not None:
                rows.append(f"<b>{m}</b> (WI Peer)<br>{level}: ${int(v):,}<br>"
                            f"Source: {src}<br>Note: {note}<extra></extra>")
            else:
                rows.append(f"<b>{m}</b> (WI Peer)<br>{level}: N/A"
                            f" — not offered or flat-rate structure<br>"
                            f"Source: {src}<br>Note: {note}<extra></extra>")
        return rows

    _bls_hover  = _hover_jeff("BLS",  _bls_vals_j)  + _hover_bench("BLS",  _bls_vals_b)
    _als1_hover = _hover_jeff("ALS1", _als1_vals_j) + _hover_bench("ALS1", _als1_vals_b)
    _als2_hover = _hover_jeff("ALS2", _als2_vals_j) + _hover_bench("ALS2", _als2_vals_b)

    # ── N/A scatter traces: text="N/A" above zero bars for missing benchmark rates ───────────────
    # y-axis max is ~$2,400 (Waukesha ALS2). Place "N/A" at $160 (~6.5% of range) so the label
    # sits clearly in the chart area just above the baseline, identifiable without obscuring data.
    _NA_Y = 160

    def _na_scatter(level, vals, color, offset_sign=1):
        """Return a go.Scatter trace drawing 'N/A' above bars where vals[i] is None.
        Only applies to benchmark positions (indices nj .. nj+nb-1) since Jefferson always has data."""
        na_x, na_y = [], []
        for i, (m, v) in enumerate(zip(_bench_munis, vals)):
            if v is None:
                na_x.append(m)
                na_y.append(_NA_Y)
        if not na_x:
            return None
        return go.Scatter(
            x=na_x, y=na_y,
            mode="text",
            text=["N/A"] * len(na_x),
            textfont=dict(size=10, color=color),
            textposition="middle center",
            showlegend=False,
            hoverinfo="skip",
            name=f"_na_{level}",
        )

    _na_bls  = _na_scatter("BLS",  _bls_vals_b,  "#8B6F47")
    _na_als1 = _na_scatter("ALS1", _als1_vals_b, C_PRIMARY)
    _na_als2 = _na_scatter("ALS2", _als2_vals_b, C_YELLOW)

    # ── Build figure ─────────────────────────────────────────────────────────────────────────────
    fig_bill = go.Figure([
        go.Bar(
            x=_all_munis, y=_plot_y(_bls_vals),
            name="BLS",
            marker_color=_bls_colors,
            text=_bar_text(_bls_vals),
            texttemplate="%{text}",
            textposition="outside",
            textfont=dict(size=10),
            customdata=list(range(n)),
            hovertemplate=[h.replace("<extra></extra>", "") + "<extra></extra>" for h in _bls_hover],
        ),
        go.Bar(
            x=_all_munis, y=_plot_y(_als1_vals),
            name="ALS1",
            marker_color=_als1_colors,
            text=_bar_text(_als1_vals),
            texttemplate="%{text}",
            textposition="outside",
            textfont=dict(size=10),
            hovertemplate=[h.replace("<extra></extra>", "") + "<extra></extra>" for h in _als1_hover],
        ),
        go.Bar(
            x=_all_munis, y=_plot_y(_als2_vals),
            name="ALS2",
            marker_color=_als2_colors,
            text=_bar_text(_als2_vals),
            texttemplate="%{text}",
            textposition="outside",
            textfont=dict(size=10),
            hovertemplate=[h.replace("<extra></extra>", "") + "<extra></extra>" for h in _als2_hover],
        ),
    ])
    # Append N/A scatter traces (only if there are any missing rates)
    for _na_tr in [_na_bls, _na_als1, _na_als2]:
        if _na_tr is not None:
            fig_bill.add_trace(_na_tr)

    fig_bill.update_layout(
        barmode="group",
        title="2025 EMS Billing Rates — Jefferson Co. vs. WI Peers<br>"
              "<sup>Jefferson Co.: 3 of 14 depts confirmed (solid) · WI peers for context (faded) · "
              "N/A = rate level not offered or flat-rate structure · 11 Jefferson Co. depts unpublished</sup>",
        yaxis_title="$ per transport",
    )

    # ── Visual separator: shaded band between Jefferson Co. and WI peers ─────────────────────────
    # x-axis is categorical; integer positions 0..nj-1 = Jefferson, nj..nj+nb-1 = WI peers.
    # The band x0=nj-0.5 / x1=nj+0.5 fills the half-bar gap on either side of the boundary.
    fig_bill.add_shape(
        type="rect",
        xref="x", yref="paper",
        x0=nj - 0.5, x1=nj + 0.5,
        y0=0, y1=1,
        fillcolor=C_BORDER,
        opacity=0.25,
        layer="below",
        line_width=0,
    )
    # Left group label above shaded band separator
    fig_bill.add_annotation(
        x=(nj - 1) / 2 / (n - 1), y=1.045,
        xref="paper", yref="paper",
        text="<b>Jefferson County</b> <i>(confirmed)</i>",
        showarrow=False,
        font=dict(size=10, color=C_PRIMARY),
        xanchor="center", yanchor="bottom",
    )
    # Right group label — center over positions nj .. nj+nb-1
    fig_bill.add_annotation(
        x=(nj + (nb - 1) / 2) / (n - 1), y=1.045,
        xref="paper", yref="paper",
        text="<b>WI Peer Benchmarks</b> <i>(context only)</i>",
        showarrow=False,
        font=dict(size=10, color=C_MUTED),
        xanchor="center", yanchor="bottom",
    )

    _apply_chart_style(fig_bill, height=560, legend_below=True, title_has_subtitle=True)
    fig_bill.update_layout(
        margin=dict(l=70, r=40, t=100, b=190),
        xaxis=dict(tickfont=dict(size=11, color=C_TEXT), tickangle=-30),
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.32,
            xanchor="left", x=0,
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
        ),
    )
    # Footnote annotation
    fig_bill.add_annotation(
        x=0.5, y=-0.52, xref="paper", yref="paper",
        text="Billed (list price) rates shown. Actual collected rates are significantly lower — "
             "e.g. Fort Atkinson avg collected = $666 vs $1,500 billed.<br>"
             "Hover each bar for source citation and notes. "
             "WI peers: Waukesha (soft billing — residents not billed after insurance), "
             "Fitch-Rona (combined BLS/ALS flat rate), Madison (flat rate, no BLS/ALS distinction), "
             "Richfield (volunteer dept), Brookfield (suburban benchmark). Sources: municipal websites, Mar 2026.",
        showarrow=False,
        font=dict(size=9, color=C_MUTED),
        xanchor="center", yanchor="top",
        align="center",
    )

    # Cost-per-call computation using muni_kpi call volumes
    kpi_df = pd.DataFrame(kpi_lookup).T.reset_index().rename(columns={"index": "Municipality"})
    budget_kpi = b.merge(kpi_df[["Municipality","Total Calls"]], on="Municipality", how="left")
    budget_kpi["Total Calls"] = pd.to_numeric(budget_kpi["Total Calls"], errors="coerce")
    # Use raw call data for departments that appear in call data
    raw_counts = raw.groupby("Department").size().reset_index(name="RawTotal")
    raw_counts.rename(columns={"Department":"Municipality"}, inplace=True)
    budget_kpi = budget_kpi.merge(raw_counts, on="Municipality", how="left")
    # Prefer raw count; fall back to kpi table.
    # Extrapolate partial-year departments to 12-month estimate before dividing.
    budget_kpi["Calls_Used"] = budget_kpi["RawTotal"].fillna(budget_kpi["Total Calls"])
    budget_kpi["Calls_Used"] = _extrapolate_annual(budget_kpi["Calls_Used"], budget_kpi["Municipality"])
    budget_kpi["Cost_Per_Call"] = (
        budget_kpi["Total_Expense"] / budget_kpi["Calls_Used"]
    ).round(0)
    budget_kpi_valid = budget_kpi.dropna(subset=["Cost_Per_Call"]).sort_values("Cost_Per_Call")

    fig_cpc = px.bar(
        budget_kpi_valid,
        x="Municipality", y="Cost_Per_Call",
        color="Model", color_discrete_map=MODEL_COLORS,
        title="Cost per Emergency Call by Municipality<br>"
              "<sup>FY2025 Budget ÷ 2024 NFIRS Call Volume · Partial-year depts extrapolated to 12 months</sup>",
        text="Cost_Per_Call",
        labels={"Cost_Per_Call": "$ per Call"},
    )
    fig_cpc.update_traces(
        texttemplate="$%{text:,.0f}", textposition="outside",
        hovertemplate="<b>%{x}</b><br>Cost/Call: $%{y:,.0f}<br>Model: %{fullData.name}<extra></extra>",
    )
    # legend_below=True: 5 model-color entries go below the plot.
    # height=540 matches fig_epc in the same flex row.
    # b=190: accommodates 2 possible legend rows (5 items may wrap) + rotated x-axis labels
    # + yshift=-30 below-axis annotations for Edgerton and Cambridge.
    # t=88: enough room for the 2-line title (main + <sup> subtitle) without crowding.
    # r=60: extra right margin for "outside" text labels on the tallest bars (Jefferson).
    # legend y=-0.30 with tracegroupgap=0: compact, non-wrapping layout preferred.
    _apply_chart_style(fig_cpc, height=540, legend_below=True, title_has_subtitle=True)
    fig_cpc.update_layout(
        margin=dict(l=70, r=60, t=88, b=190),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.28,
            xanchor="left", x=0,
            font=dict(size=11),
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            tracegroupgap=0,
        ),
    )
    # Annotate Edgerton — partial budget (west division only); true cost/call is higher
    if "Edgerton" in budget_kpi_valid["Municipality"].values:
        fig_cpc.add_annotation(
            x="Edgerton", y=0,
            text="Partial<br>budget",
            showarrow=False,
            yshift=-30,
            font=dict(size=9, color=C_MUTED),
            xanchor="center",
        )
    # Annotate Cambridge — 2024 data is pre-disruption; service collapsed in 2025
    if "Cambridge" in budget_kpi_valid["Municipality"].values:
        fig_cpc.add_annotation(
            x="Cambridge", y=0,
            text="Pre-disruption<br>2024; collapsed 2025",
            showarrow=False,
            yshift=-30,
            font=dict(size=9, color=C_MUTED),
            xanchor="center",
        )

    # ── Expense Per Capita chart ───────────────────────────────────────────────
    # Uses _util (pre-computed) which already has Expense_Per_Capita + Population columns.
    # Drop rows where Expense_Per_Capita is NaN (depts without budget or population).
    epc_df = _util.dropna(subset=["Expense_Per_Capita"]).copy()
    epc_df = epc_df.sort_values("Expense_Per_Capita")

    epc_colors = [MODEL_COLORS.get(m, C_MUTED) for m in epc_df["Model"]]
    epc_median = float(epc_df["Expense_Per_Capita"].median())

    fig_epc = go.Figure(go.Bar(
        x=epc_df["Municipality"],
        y=epc_df["Expense_Per_Capita"],
        marker_color=epc_colors,
        text=epc_df["Expense_Per_Capita"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
        customdata=epc_df[["Total_Expense", "Population", "Model"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Expense/Capita: $%{y:,.0f}<br>"
            "Total Expense: $%{customdata[0]:,.0f}<br>"
            "Service Area Pop.: %{customdata[1]:,}<br>"
            "Model: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig_epc.update_layout(
        title="Expense Per Capita by Department<br>"
              "<sup>FY2025 Budget / Service Area Population (WI DOA 2025 Preliminary Estimates) "
              "· WI avg EMS user fee = $36/capita shown for reference</sup>",
        yaxis_title="$ per capita",
    )
    # No named legend traces (colors are a list, not individual named traces), so
    # the legend widget is invisible.  legend_below=False keeps it above (harmless).
    # height=540 matches fig_cpc in the same flex row.
    # t=88: room for 2-line title + subtitle without crowding the topmost bar label.
    # r=180: critical — both hline annotations use annotation_position="top right" /
    #        "bottom right" and need space so their text isn't cut off at the right edge.
    # b=160: accommodates rotated x-axis tick labels + yshift=-30 below-axis annotations.
    _apply_chart_style(fig_epc, height=540, legend_below=False, title_has_subtitle=True)
    fig_epc.update_layout(
        margin=dict(l=70, r=180, t=88, b=160),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
    )
    # WI statewide average EMS user fee reference line ($36/capita, Northwestern EMS)
    fig_epc.add_hline(
        y=_BENCH["wi_ems_fee_per_capita"],
        line_dash="dash", line_color=C_GREEN,
        annotation_text=f"WI avg EMS user fee ${_BENCH['wi_ems_fee_per_capita']}/capita",
        annotation_font_color=C_GREEN,
        annotation_position="top right",
    )
    # County median expense/capita reference line
    fig_epc.add_hline(
        y=epc_median,
        line_dash="dot", line_color=C_MUTED,
        annotation_text=f"County median ${epc_median:,.0f}/capita",
        annotation_font_color=C_MUTED,
        annotation_position="bottom right",
    )
    # Annotate Edgerton — partial budget only (west division)
    if "Edgerton" in epc_df["Municipality"].values:
        fig_epc.add_annotation(
            x="Edgerton", y=0,
            text="Partial<br>budget",
            showarrow=False,
            yshift=-30,
            font=dict(size=9, color=C_MUTED),
            xanchor="center",
        )
    # Annotate Cambridge — service disrupted 2025
    if "Cambridge" in epc_df["Municipality"].values:
        fig_epc.add_annotation(
            x="Cambridge", y=0,
            text="Service<br>disrupted 2025",
            showarrow=False,
            yshift=-30,
            font=dict(size=9, color=C_MUTED),
            xanchor="center",
        )

    # ── Funding Gap Breakdown — explains how each dept covers the shortfall ──
    GAP_EXPLANATIONS = {
        "Ixonia":        "Town contracts ($180K from surrounding towns), state EMS dues, fund balance drawdown",
        "Jefferson":     "Referendum Fund 31 ($624K) — voters approved dedicated EMS tax in 2023",
        "Watertown":     "Small gap (~$69K) — likely state aid or miscellaneous revenue",
        "Fort Atkinson": "Minor gap (~$47K) — likely grants or fund balance; EMS fund nearly self-sustaining",
        "Whitewater":    "State shared revenue, grants, inter-fund transfers within Fund 249",
        "Cambridge":     "No gap — fully funded by tax levy",
        "Lake Mills":    "No gap — tax levy covers full contract payment to LMFD",
        "Waterloo":      "Contract payments from surrounding towns (City + Towns cost-sharing formula)",
        "Johnson Creek": "Township contract contributions, prior-year billing collections",
        "Palmyra":       "Town of Palmyra contribution ($250K) partially in levy; remainder is misc revenue",
        "Edgerton":      "Unknown — multi-county district (Rock/Dane/Jefferson), full budget not public",
    }
    gap_df = b_plot.copy()
    gap_df["Funding_Gap"] = (gap_df["Total_Expense"] - gap_df["EMS_Revenue"] - gap_df["Net_Tax"]).clip(lower=0)
    gap_df = gap_df[gap_df["Funding_Gap"] > 100].sort_values("Funding_Gap", ascending=True)
    gap_df["Explanation"] = gap_df["Municipality"].map(GAP_EXPLANATIONS).fillna("Not yet documented")

    fig_gap = go.Figure()
    fig_gap.add_trace(go.Bar(
        y=gap_df["Municipality"],
        x=gap_df["Funding_Gap"],
        orientation="h",
        marker_color=C_YELLOW,
        text=gap_df["Funding_Gap"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
        customdata=gap_df["Explanation"].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Funding Gap: <b>$%{x:,.0f}</b><br>"
            "%{customdata}<extra></extra>"
        ),
    ))
    # Explanation text moved to a companion table below the chart for readability

    fig_gap.update_layout(
        title="How Departments Fill the Funding Gap<br>"
              "<sup>Difference between (EMS Revenue + Tax Levy) and Total Expense — "
              "hover for details</sup>",
        xaxis_title="Unfunded Amount ($)",
    )
    _apply_chart_style(fig_gap, height=420, legend_below=True, title_has_subtitle=True)
    fig_gap.update_layout(
        margin=dict(l=120, r=80, t=88, b=60),
        xaxis=dict(tickprefix="$", tickformat=",.0f"),
    )

    # Build companion table data for the funding gap chart
    gap_table_df = gap_df[["Municipality", "Funding_Gap", "Explanation"]].copy()
    gap_table_df = gap_table_df.sort_values("Funding_Gap", ascending=False)
    gap_table_df["Funding_Gap"] = gap_table_df["Funding_Gap"].apply(lambda v: f"${v:,.0f}")
    gap_table_records = gap_table_df.rename(columns={
        "Municipality": "Department",
        "Funding_Gap": "Gap Amount",
        "Explanation": "How They Cover It",
    }).to_dict("records")

    return fig_b, fig_bill, fig_cpc, fig_epc, fig_gap, gap_table_records


# ── Inter-Municipal Contract Payments ────────────────────────────────────────
# Source: EMS Contract Details for all Towns in Jefferson County.xlsx
# (ISyE Project/Data and Resources/). Payment amounts hand-extracted from
# free-text contract descriptions in that file.
_CONTRACT_PAYMENTS = pd.DataFrame([
    # Johnson Creek → 4 towns (2024 amounts, Equalized Improvement Value basis)
    {"Provider": "Johnson Creek", "Client": "Town of Aztalan",    "Payment_2024": 32117,  "Basis": "Equalized Improvement Value",  "Per_Capita": None, "Expires": "Dec 2028"},
    {"Provider": "Johnson Creek", "Client": "Town of Farmington", "Payment_2024": 118249, "Basis": "Equalized Improvement Value",  "Per_Capita": None, "Expires": "Dec 2028"},
    {"Provider": "Johnson Creek", "Client": "Town of Milford",    "Payment_2024": 19788,  "Basis": "Equalized Improvement Value",  "Per_Capita": None, "Expires": "Dec 2028"},
    {"Provider": "Johnson Creek", "Client": "Town of Watertown",  "Payment_2024": 44949,  "Basis": "Equalized Improvement Value",  "Per_Capita": None, "Expires": "Dec 2028"},
    # Jefferson → 5 towns (2025 rate: $34/capita)
    {"Provider": "Jefferson",     "Client": "Town of Jefferson",  "Payment_2024": None,   "Basis": "Per capita ($34 in 2025)",     "Per_Capita": 34,   "Expires": "Dec 2027"},
    {"Provider": "Jefferson",     "Client": "Town of Farmington", "Payment_2024": None,   "Basis": "Per capita ($34 in 2025)",     "Per_Capita": 34,   "Expires": "Dec 2027"},
    {"Provider": "Jefferson",     "Client": "Town of Hebron",     "Payment_2024": None,   "Basis": "Per capita ($34 in 2025)",     "Per_Capita": 34,   "Expires": "Dec 2027"},
    {"Provider": "Jefferson",     "Client": "Town of Oakland",    "Payment_2024": None,   "Basis": "Per capita ($34 in 2025)",     "Per_Capita": 34,   "Expires": "Dec 2027"},
    {"Provider": "Jefferson",     "Client": "Town of Aztalan",    "Payment_2024": None,   "Basis": "Per capita ($34 in 2025)",     "Per_Capita": 34,   "Expires": "Dec 2027"},
    # Fort Atkinson → 2 towns ($7.22/resident base + CPI-W 2-6%) — EXPIRED
    {"Provider": "Fort Atkinson", "Client": "Town of Jefferson",  "Payment_2024": None,   "Basis": "$7.22/resident + CPI-W adj.",  "Per_Capita": 7.22, "Expires": "EXPIRED Dec 2025"},
    {"Provider": "Fort Atkinson", "Client": "Town of Koshkonong", "Payment_2024": None,   "Basis": "$7.22/resident + CPI-W adj.",  "Per_Capita": 7.22, "Expires": "EXPIRED Dec 2025"},
    # Edgerton FPD → Town of Koshkonong
    {"Provider": "Edgerton",      "Client": "Town of Koshkonong", "Payment_2024": 10974,  "Basis": "Fixed + CPI+2% annual adj.",   "Per_Capita": None, "Expires": "Auto-renew"},
    # Waterloo → 2 towns ($26/capita in 2025)
    {"Provider": "Waterloo",      "Client": "Town of Milford",    "Payment_2024": None,   "Basis": "Per capita ($26 in 2025)",     "Per_Capita": 26,   "Expires": "Dec 2025"},
    {"Provider": "Waterloo",      "Client": "Town of Waterloo",   "Payment_2024": None,   "Basis": "Per capita ($26 in 2025)",     "Per_Capita": 26,   "Expires": "Dec 2025"},
    # Watertown → Town of Milford (EXPIRED — only 6 months Jul-Dec 2023)
    {"Provider": "Watertown",     "Client": "Town of Milford",    "Payment_2024": None,   "Basis": "$40/capita (~133 pop)",         "Per_Capita": 40,   "Expires": "EXPIRED Dec 2023"},
    # Lake Mills → Town of Aztalan ($48/capita + 3-6% annual inflation)
    {"Provider": "Lake Mills",    "Client": "Town of Aztalan",    "Payment_2024": None,   "Basis": "$48/capita + 3-6% annual adj.","Per_Capita": 48,   "Expires": "Open-ended (2024+)"},
])


@lru_cache(maxsize=1)
def _get_contract_figs():
    """Build inter-municipal contract payment visualizations."""
    cp = _CONTRACT_PAYMENTS.copy()

    # ── Fig 1: Stacked bar — total contract revenue per provider ─────────
    # For per-capita contracts without a fixed dollar amount, note them but
    # only plot where we have actual dollar totals.
    provider_totals = (
        cp.dropna(subset=["Payment_2024"])
          .groupby("Provider")["Payment_2024"]
          .sum()
          .sort_values(ascending=False)
          .reset_index()
    )
    provider_totals.columns = ["Provider", "Total_Contract_Revenue"]

    fig_rev = go.Figure()
    # Get individual contracts for each provider with dollar amounts
    for prov in provider_totals["Provider"]:
        sub = cp[(cp["Provider"] == prov) & cp["Payment_2024"].notna()]
        fig_rev.add_trace(go.Bar(
            x=[prov] * len(sub),
            y=sub["Payment_2024"].values,
            name=sub["Client"].values[0] if len(sub) == 1 else prov,
            text=[f"${v:,.0f}" for v in sub["Payment_2024"].values],
            textposition="inside",
            customdata=list(zip(sub["Client"], sub["Basis"], sub["Expires"])),
            hovertemplate=(
                "<b>%{customdata[0]}</b> → %{x}<br>"
                "Payment: $%{y:,.0f}<br>"
                "Basis: %{customdata[1]}<br>"
                "Expires: %{customdata[2]}<extra></extra>"
            ),
        ))

    fig_rev.update_layout(
        barmode="stack",
        title="Inter-Municipal Contract Payments — Known Dollar Amounts<br>"
              "<sup>Source: EMS Contract Details for all Towns in Jefferson County.xlsx · "
              "Only contracts with fixed 2024 dollar amounts shown</sup>",
        yaxis_title="$ Annual Payment",
    )
    _apply_chart_style(fig_rev, height=460, legend_below=True, title_has_subtitle=True)
    fig_rev.update_layout(
        margin=dict(l=60, r=40, t=85, b=80),
        xaxis=dict(tickfont=dict(size=13, color=C_TEXT)),
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
    )

    # ── Fig 2: Per-capita rate comparison (where per-capita basis is used) ──
    pc = cp.dropna(subset=["Per_Capita"]).copy()
    # Aggregate to one row per provider (they use same per-capita rate for all clients)
    pc_agg = pc.groupby("Provider").agg(
        Per_Capita=("Per_Capita", "first"),
        Num_Clients=("Client", "count"),
        Expires=("Expires", "first"),
        Basis=("Basis", "first"),
    ).reset_index().sort_values("Per_Capita", ascending=False)

    expired_mask = pc_agg["Expires"].str.contains("EXPIRED", case=False, na=False)
    bar_colors = [C_RED if exp else C_PRIMARY for exp in expired_mask]

    fig_pc = go.Figure(go.Bar(
        x=pc_agg["Provider"],
        y=pc_agg["Per_Capita"],
        marker_color=bar_colors,
        text=pc_agg["Per_Capita"].apply(lambda v: f"${v:,.2f}"),
        textposition="outside",
        customdata=pc_agg[["Num_Clients", "Expires", "Basis"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Per Capita Rate: $%{y:,.2f}<br>"
            "Towns Served: %{customdata[0]}<br>"
            "Basis: %{customdata[2]}<br>"
            "Expires: %{customdata[1]}<extra></extra>"
        ),
    ))
    fig_pc.update_layout(
        title="EMS Contract Per-Capita Rates by Provider<br>"
              "<sup>Red = expired contract · Wide variation: $7.22 (Fort Atkinson) to $48.00 (Lake Mills)</sup>",
        yaxis_title="$ per capita per year",
    )
    _apply_chart_style(fig_pc, height=420, legend_below=False, title_has_subtitle=True)
    fig_pc.update_layout(
        margin=dict(l=60, r=40, t=85, b=80),
        xaxis=dict(tickfont=dict(size=13, color=C_TEXT)),
        yaxis=dict(tickprefix="$", tickformat=",.2f"),
    )

    # ── Contract status table (all 17 contracts) ────────────────────────
    tbl = cp.copy()
    tbl["Payment"] = tbl["Payment_2024"].apply(
        lambda v: f"${v:,.0f}" if pd.notna(v) else "Per-capita (see Basis)")
    tbl_display = tbl[["Provider", "Client", "Payment", "Basis", "Expires"]].copy()
    tbl_cols = [{"name": c, "id": c} for c in tbl_display.columns]
    tbl_data = tbl_display.to_dict("records")

    return fig_rev, fig_pc, tbl_cols, tbl_data


# Staffing charts — static, computed once on first access
@lru_cache(maxsize=1)
def _get_staffing_figs():
    b = budget.copy().sort_values("Staff_FT", ascending=True)

    fig_s = go.Figure([
        go.Bar(
            y=b["Municipality"], x=b["Staff_FT"],
            name="Full-Time", orientation="h",
            marker_color=C_PRIMARY,
            text=b["Staff_FT"], textposition="outside",
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>Full-Time staff: %{x}<extra></extra>",
        ),
        go.Bar(
            y=b["Municipality"], x=b["Staff_PT"],
            name="Part-Time / Volunteer", orientation="h",
            marker_color=C_GREEN,
            text=b["Staff_PT"], textposition="outside",
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>Part-Time/Volunteer: %{x}<extra></extra>",
        ),
    ])
    fig_s.update_layout(
        barmode="group",
        title="Staffing by Municipality — Full-Time vs Part-Time/Volunteer (FY2025 Budget)",
        xaxis_title="Number of Staff",
    )
    _apply_chart_style(fig_s, height=520, legend_below=False)
    fig_s.update_layout(
        margin=dict(l=140, r=80, t=60, b=30),
        yaxis=dict(tickfont=dict(size=13, color=C_TEXT)),
    )

    model_counts = budget["Model"].value_counts().reset_index()
    model_counts.columns = ["Model", "Count"]
    fig_m = px.pie(
        model_counts, values="Count", names="Model",
        title="Staffing Model Distribution (FY2025 Budget)",
        color="Model", color_discrete_map=MODEL_COLORS,
        hole=0.6,
    )
    fig_m.update_traces(
        textposition="outside",
        texttemplate="<b>%{label}</b><br>%{value} dept(s)",
        hovertemplate="<b>%{label}</b><br>%{value} department(s)<br>%{percent}<extra></extra>",
    )
    _apply_chart_style(fig_m, height=440, legend_below=True)
    fig_m.update_layout(margin=dict(l=20, r=20, t=60, b=100))

    return fig_s, fig_m


# ALS/BLS service level chart — static, computed once on first access
@lru_cache(maxsize=1)
def _get_als_fig():
    level_order  = ["ALS", "AEMT", "BLS", "N/A"]
    level_colors = {"ALS": C_PRIMARY, "AEMT": "#60A5FA", "BLS": C_GREEN, "N/A": C_BORDER}
    conf_marker  = {"High": "circle", "Medium": "diamond", "Low": "x"}

    rows = []
    for dept, info in ALS_LEVELS.items():
        n_calls = AUTH_EMS_CALLS.get(dept, 0)
        rows.append({
            "Department": dept,
            "Level":      info["Level"],
            "Notes":      info["Notes"],
            "Confidence": info["Confidence"],
            "EMS_Calls":  n_calls,
        })
    df_als = pd.DataFrame(rows).sort_values(
        ["Level", "EMS_Calls"], ascending=[True, False],
        key=lambda s: s.map(level_order.index) if s.name == "Level" else -s
    )

    fig = go.Figure()
    for lvl in level_order:
        sub = df_als[df_als["Level"] == lvl]
        if sub.empty:
            continue
        fig.add_trace(go.Bar(
            x=sub["Department"],
            y=[lvl] * len(sub),
            name=lvl,
            orientation="v",
            marker_color=level_colors[lvl],
            customdata=sub[["Notes", "Confidence", "EMS_Calls"]].values,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Level: " + lvl + "<br>"
                "Notes: %{customdata[0]}<br>"
                "Confidence: %{customdata[1]}<br>"
                "2024 EMS calls: %{customdata[2]:,}<extra></extra>"
            ),
            showlegend=True,
        ))

    # Overlay confidence markers
    for conf, sym in conf_marker.items():
        sub = df_als[df_als["Confidence"] == conf]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["Department"],
            y=sub["Level"],
            mode="markers",
            name=f"{conf} confidence",
            marker=dict(symbol=sym, size=14, color="white",
                        line=dict(color="#333", width=1.5)),
            hoverinfo="skip",
            showlegend=True,
        ))

    fig.update_layout(
        barmode="overlay",
        title="EMS Service Level (ALS / AEMT / BLS / No-Transport) — All Departments",
        xaxis_title="Department",
        yaxis=dict(
            categoryorder="array",
            categoryarray=level_order[::-1],   # ALS at top
            title="Service Level",
            gridcolor=C_BORDER,
            tickfont=dict(size=12, color=C_TEXT),
        ),
    )
    _apply_chart_style(fig, height=480, legend_below=True)
    fig.update_layout(
        margin=dict(l=40, r=40, t=60, b=140),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
    )
    return fig


# ── Section 14: Municipal Asset Comparison (MABAS data) ────────────────────
@lru_cache(maxsize=1)
def _get_asset_figs():
    """Build all asset comparison charts. Returns (fig_ambulance_bar, fig_fleet_stacked,
    fig_age_scatter, fig_personnel_bar, table_data, table_columns)."""
    ad = ASSET_DATA.copy()
    # Merge authoritative EMS call volumes for cross-referencing
    ad["EMS_Calls"] = ad["Municipality"].map(AUTH_EMS_CALLS).fillna(0)
    ad["Total_Apparatus"] = ad["Engines"] + ad["Trucks_Ladders"] + ad["Squads_Rescues"] + ad["Tenders"] + ad["Brush_ATV"] + ad["Boats"] + ad["Ambulances"]

    # Only departments with ambulances for ambulance-focused charts
    amb = ad[ad["Ambulances"] > 0].sort_values("Ambulances", ascending=True)

    # ── Chart 1: Ambulance count by municipality (horizontal bar) ────────
    fig_amb = go.Figure()
    fig_amb.add_trace(go.Bar(
        y=amb["Municipality"], x=amb["Ambulances"],
        orientation="h",
        marker_color=C_PRIMARY,
        text=amb["Ambulances"], textposition="outside",
        customdata=amb[["Ambulance_Detail", "EMS_Calls"]].values,
        hovertemplate="<b>%{y}</b><br>Ambulances: %{x}<br>EMS Calls: %{customdata[1]:,.0f}<br>%{customdata[0]}<extra></extra>",
    ))
    fig_amb.update_layout(
        title="Ambulance Units by Municipality<br><sup>EMS-transporting departments only — MABAS Division 118</sup>",
        xaxis_title="Number of Ambulances",
        yaxis_title="",
    )
    _apply_chart_style(fig_amb, height=400, title_has_subtitle=True)
    fig_amb.update_layout(margin=dict(l=120, r=40, t=70, b=30))

    # ── Chart 2: Full fleet stacked bar (all apparatus types) ────────────
    ad_sorted = ad.sort_values("Total_Apparatus", ascending=True)
    fleet_cats = [
        ("Engines",        C_RED,     "Engines"),
        ("Trucks_Ladders", C_YELLOW,  "Trucks/Ladders"),
        ("Squads_Rescues", "#60A5FA", "Squads/Rescues"),
        ("Tenders",        C_GREEN,   "Tenders"),
        ("Brush_ATV",      "#A78BFA", "Brush/ATV"),
        ("Boats",          "#06B6D4", "Boats"),
        ("Ambulances",     C_PRIMARY, "Ambulances"),
    ]
    fig_fleet = go.Figure()
    for col, color, label in fleet_cats:
        fig_fleet.add_trace(go.Bar(
            y=ad_sorted["Municipality"], x=ad_sorted[col],
            name=label, orientation="h",
            marker_color=color,
            hovertemplate=f"<b>%{{y}}</b><br>{label}: %{{x}}<extra></extra>",
        ))
    fig_fleet.update_layout(
        barmode="stack",
        title="Total Apparatus Fleet by Municipality<br><sup>All equipment categories — MABAS Division 118 filings</sup>",
        xaxis_title="Number of Units",
        yaxis_title="",
    )
    _apply_chart_style(fig_fleet, height=500, legend_below=True, title_has_subtitle=True)
    fig_fleet.update_layout(margin=dict(l=120, r=40, t=70, b=60))

    # ── Chart 3: Ambulance age scatter with unit labels ──────────────────
    det = AMBULANCE_DETAIL.copy()
    fig_age = go.Figure()
    # Color by age bracket
    def _age_color(age):
        if age <= 5: return C_GREEN
        if age <= 10: return C_YELLOW
        if age <= 15: return C_PRIMARY
        return C_RED
    det["Color"] = det["Age"].apply(_age_color)
    fig_age.add_trace(go.Scatter(
        x=det["Municipality"], y=det["Age"],
        mode="markers+text",
        text=det["Unit"],
        textposition="top center",
        textfont=dict(size=9, color=C_MUTED),
        marker=dict(size=14, color=det["Color"], line=dict(color="#FFF", width=1)),
        customdata=det[["Unit", "Year", "Chassis", "Body", "Level"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b> — %{x}<br>"
            "Year: %{customdata[1]} (age %{y} yrs)<br>"
            "Chassis: %{customdata[2]} | Body: %{customdata[3]}<br>"
            "Level: %{customdata[4]}<extra></extra>"
        ),
    ))
    # Reference lines
    fig_age.add_hline(y=10, line_dash="dash", line_color=C_YELLOW,
                      annotation_text="10-yr replacement target", annotation_font_color=C_YELLOW)
    fig_age.add_hline(y=15, line_dash="dash", line_color=C_RED,
                      annotation_text="15-yr end-of-life", annotation_font_color=C_RED)
    fig_age.update_layout(
        title="Ambulance Fleet Age Analysis (2025)<br><sup>Only units with known model year — green &le;5yr, yellow 6-10yr, orange 11-15yr, red &gt;15yr</sup>",
        xaxis_title="", yaxis_title="Vehicle Age (years)",
    )
    _apply_chart_style(fig_age, height=430, title_has_subtitle=True)
    fig_age.update_layout(
        margin=dict(l=50, r=40, t=80, b=100),
        xaxis=dict(tickangle=-40, automargin=True),
        yaxis=dict(dtick=5, range=[0, max(det["Age"]) + 5]),
    )

    # ── Chart 4: EMS personnel composition by municipality ───────────────
    pers = ad[ad["EMS_Personnel"] > 0].sort_values("EMS_Personnel", ascending=True)
    pers_cats = [
        ("Paramedics", C_PRIMARY, "Paramedics (EMT-P)"),
        ("AEMTs",      "#60A5FA", "AEMT"),
        ("EMTs",       C_GREEN,   "EMT"),
        ("EMRs",       C_YELLOW,  "EMR"),
    ]
    fig_pers = go.Figure()
    for col, color, label in pers_cats:
        fig_pers.add_trace(go.Bar(
            y=pers["Municipality"], x=pers[col],
            name=label, orientation="h",
            marker_color=color,
            hovertemplate=f"<b>%{{y}}</b><br>{label}: %{{x}}<extra></extra>",
        ))
    fig_pers.update_layout(
        barmode="stack",
        title="EMS Personnel by Certification Level<br><sup>MABAS Division 118 — departments with reported EMS staffing</sup>",
        xaxis_title="Number of EMS Personnel",
        yaxis_title="",
    )
    _apply_chart_style(fig_pers, height=450, legend_below=True, title_has_subtitle=True)
    fig_pers.update_layout(margin=dict(l=120, r=40, t=70, b=60))

    # ── Summary table data ───────────────────────────────────────────────
    tbl = ad[["Municipality", "Ambulances", "Engines", "Trucks_Ladders", "Squads_Rescues",
              "Tenders", "Brush_ATV", "Boats", "Total_Apparatus", "EMS_Personnel"]].copy()
    tbl = tbl.sort_values("Total_Apparatus", ascending=False)
    tbl.columns = ["Municipality", "Ambulances", "Engines", "Trucks/Ladders", "Squads/Rescues",
                    "Tenders", "Brush/ATV", "Boats", "Total Fleet", "EMS Personnel"]
    tbl_data = tbl.to_dict("records")
    tbl_cols = [{"name": c, "id": c} for c in tbl.columns]

    # ── Chart 5: EMS Calls per Ambulance (utilization efficiency) ─────
    util = ad[(ad["Ambulances"] > 0) & (ad["EMS_Calls"] > 0)].copy()
    util["Calls_Per_Amb"] = util["EMS_Calls"] / util["Ambulances"]
    util["Population"] = util["Municipality"].map(SERVICE_AREA_POP)
    util = util.sort_values("Calls_Per_Amb", ascending=True)

    # Green = high utilization (good), Yellow = moderate, Red = underutilized
    def _utilization_color(cpa):
        if cpa >= 400:  return C_GREEN
        if cpa >= 200:  return C_YELLOW
        return C_RED

    fig_cpa = go.Figure(go.Bar(
        y=util["Municipality"], x=util["Calls_Per_Amb"],
        orientation="h",
        marker_color=util["Calls_Per_Amb"].apply(_utilization_color).tolist(),
        text=util["Calls_Per_Amb"].apply(lambda v: f"{v:.0f}"),
        textposition="outside",
        customdata=util[["EMS_Calls", "Ambulances", "Population"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Calls/Ambulance: %{x:.0f}<br>"
            "EMS Calls: %{customdata[0]:,.0f}<br>"
            "Ambulances: %{customdata[1]}<br>"
            "Service Pop: %{customdata[2]:,.0f}<extra></extra>"
        ),
    ))
    med_cpa = util["Calls_Per_Amb"].median()
    fig_cpa.add_vline(
        x=med_cpa, line_dash="dash", line_color=C_MUTED,
        annotation_text=f"County median: {med_cpa:.0f}",
        annotation_font_color=C_MUTED,
        annotation_position="top right",
    )
    # CMS GADCS national benchmark: ~1,147 transports/unit (government EMS mean)
    fig_cpa.add_vline(
        x=1147, line_dash="dot", line_color=C_YELLOW,
        annotation_text="CMS national avg: 1,147",
        annotation_font_color=C_YELLOW,
        annotation_position="bottom right",
    )
    fig_cpa.update_layout(
        title="EMS Calls per Ambulance<br><sup>Higher = better utilization (green \u2265400 | yellow 200\u2013399 | red <200) \u2014 CMS GADCS 2024 national avg shown</sup>",
        xaxis_title="Annual EMS Calls per Ambulance",
        yaxis_title="",
    )
    _apply_chart_style(fig_cpa, height=400, title_has_subtitle=True)
    fig_cpa.update_layout(margin=dict(l=120, r=60, t=70, b=30))

    # ── Chart 6: Ambulances per 10K Population (resource density) ────
    # Exclude Lake Mills: 3 MABAS-listed ambulances but Ryan Brothers provides
    # transport since 2023 EMS nonprofit closure. LMFD units are BLS support only.
    pop_util = ad[(ad["Ambulances"] > 0) & (ad["Municipality"] != "Lake Mills")].copy()
    pop_util["Population"] = pop_util["Municipality"].map(SERVICE_AREA_POP)
    pop_util = pop_util.dropna(subset=["Population"])
    pop_util["Amb_Per_10K"] = pop_util["Ambulances"] / pop_util["Population"] * 10000
    pop_util = pop_util.sort_values("Amb_Per_10K", ascending=True)

    def _density_color(a10k):
        if a10k < 1.0:  return C_RED
        if a10k <= 2.0: return C_YELLOW
        return C_GREEN

    fig_a10k = go.Figure(go.Bar(
        y=pop_util["Municipality"], x=pop_util["Amb_Per_10K"],
        orientation="h",
        marker_color=pop_util["Amb_Per_10K"].apply(_density_color).tolist(),
        text=pop_util["Amb_Per_10K"].apply(lambda v: f"{v:.1f}"),
        textposition="outside",
        customdata=pop_util[["Ambulances", "Population"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Amb/10K Pop: %{x:.2f}<br>"
            "Ambulances: %{customdata[0]}<br>"
            "Service Pop: %{customdata[1]:,.0f}<extra></extra>"
        ),
    ))
    med_a10k = pop_util["Amb_Per_10K"].median()
    fig_a10k.add_vline(
        x=med_a10k, line_dash="dash", line_color=C_MUTED,
        annotation_text=f"County median: {med_a10k:.1f}",
        annotation_font_color=C_MUTED,
        annotation_position="top right",
    )
    # Annotate Whitewater — Jeff Co. portion only, full service area is ~15K
    if "Whitewater" in pop_util["Municipality"].values:
        ww_val = pop_util.loc[pop_util["Municipality"] == "Whitewater", "Amb_Per_10K"].iloc[0]
        fig_a10k.add_annotation(
            x=ww_val, y="Whitewater",
            text="Jeff Co. portion only (4,296 of ~15,000 served)",
            showarrow=True, ax=0, ay=-30,
            font=dict(size=9, color=C_MUTED),
            arrowcolor=C_MUTED, arrowwidth=1,
        )
    fig_a10k.update_layout(
        title="Ambulances per 10K Population<br><sup>Resource density by service area — excludes Lake Mills (Ryan Brothers transports)</sup>",
        xaxis_title="Ambulances per 10,000 Residents",
        yaxis_title="",
    )
    _apply_chart_style(fig_a10k, height=400, title_has_subtitle=True)
    fig_a10k.update_layout(margin=dict(l=120, r=60, t=70, b=30))

    # ── KPI summary dict ─────────────────────────────────────────────
    total_amb = int(_JEFF_TOTAL_AMBULANCES)
    # Avg uses only depts with NFIRS EMS data (excludes Lake Mills — Ryan Brothers)
    util_amb = int(util["Ambulances"].sum())
    total_ems_amb_depts = int(util["EMS_Calls"].sum())
    avg_cpa = total_ems_amb_depts / util_amb if util_amb else 0
    county_a10k_val = total_amb / _BENCH["jeff_county_pop"] * 10000
    n_amb_depts = len(ad[ad["Ambulances"] > 0])
    asset_kpis = {
        "total_ambulances": str(total_amb),
        "avg_calls_per_amb": f"{avg_cpa:.0f}",
        "county_amb_per_10k": f"{county_a10k_val:.1f}",
        "n_depts_with_amb": str(n_amb_depts),
    }

    return fig_amb, fig_fleet, fig_age, fig_pers, tbl_data, tbl_cols, fig_cpa, fig_a10k, asset_kpis


# FIX 12: Individual department drill-down callback
@app.callback(
    Output("drilldown-kpi-row",      "children"),
    Output("drilldown-als-bls",      "figure"),
    Output("drilldown-rt-hist",      "figure"),
    Output("drilldown-hour-bar",     "figure"),
    Output("drilldown-monthly",      "figure"),
    Output("drilldown-high-freq",    "children"),
    Output("drilldown-data-quality", "children"),
    Input("dept-drilldown",          "value"),
)
def update_drilldown(dept):
    df_d  = raw[raw["Department"] == dept]
    rt_d  = rt_clean[rt_clean["Department"] == dept]
    bud   = budget_lookup.get(dept, {})

    auth_c = AUTH_EMS_CALLS.get(dept, len(df_d))  # Authoritative EMS count
    med_rt = float(rt_d["RT"].median()) if len(rt_d) else None
    p90_rt = float(rt_d["RT"].quantile(0.90)) if len(rt_d) else None

    # Asterisk for call volume discrepancies
    call_note = CALL_VOLUME_NOTES.get(dept)
    ems_label = f"{auth_c:,}*" if call_note else f"{auth_c:,}"
    ems_sub = f"{dept} — 2024 | *{call_note}" if call_note else f"{dept} — 2024"

    cards = [
        kpi_card("EMS Calls",     ems_label,                             ems_sub),
        kpi_card("Median RT",      f"{med_rt:.1f} min" if med_rt is not None else "N/A",
                 "EMS response time"),
        kpi_card("P90 RT",         f"{p90_rt:.1f} min" if p90_rt is not None else "N/A",
                 "90th percentile",
                 C_RED if (p90_rt or 0) > 8 else C_GREEN),
        kpi_card("Staffing Model", bud.get("Model", "N/A"),
                 f"{bud.get('Staff_FT','?')} FT / {bud.get('Staff_PT','?')} PT"),
        kpi_card("Total Budget",
                 f"${bud['Total_Expense']:,.0f}" if bud.get("Total_Expense") else "N/A",
                 f"FY{bud.get('FY','?')}"),
    ]

    # ── ALS/BLS donut chart ────────────────────────────────────────────────────
    pct_data = ALS_BLS_PCTS.get(dept)
    _als_colors = {
        "ALS": C_PRIMARY, "BLS": "#10B981", "Critical Care": "#EF4444",
        "Transport": "#F59E0B", "First Aid": "#60A5FA", "Other": "#6B7280",
    }
    if pct_data:
        labels = list(pct_data.keys())
        values = list(pct_data.values())
        fig_als = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.55,
            marker_colors=[_als_colors.get(l, "#6B7280") for l in labels],
            textinfo="label+percent",
            textfont=dict(size=10, color=C_TEXT),
            hovertemplate="<b>%{label}</b>: %{percent}<extra></extra>",
            sort=False,
        ))
        svc_level = ALS_LEVELS.get(dept, {}).get("Level", "")
        fig_als.update_layout(
            title=dict(text=f"ALS / BLS Split", font=dict(size=13)),
            annotations=[dict(text=svc_level, x=0.5, y=0.5, font_size=15,
                             showarrow=False, font_color=C_TEXT)],
        )
        _apply_chart_style(fig_als, height=360, legend_below=True)
        fig_als.update_layout(margin=dict(l=10, r=10, t=45, b=80))
    else:
        fig_als = go.Figure()
        fig_als.add_annotation(
            text=f"No ALS/BLS breakdown<br>available for {dept}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=12, color="#6B7280"),
        )
        _apply_chart_style(fig_als, height=360)
        fig_als.update_layout(margin=dict(l=10, r=10, t=45, b=50))

    # Response time histogram
    fig_hist = px.histogram(
        rt_d, x="RT", nbins=20,
        title=f"{dept} — Response Time Distribution (2024 NFIRS Data)",
        labels={"RT": "Minutes", "count": "Incidents"},
        color_discrete_sequence=[C_PRIMARY],
    )
    fig_hist.update_traces(
        marker_line_color="white", marker_line_width=1,
        hovertemplate="RT: %{x:.1f} min<br>Incidents: %{y}<extra></extra>",
    )
    fig_hist.add_vline(x=8, line_dash="dash", line_color=C_YELLOW,
                       annotation_text="8-min benchmark",
                       annotation_font_color=C_YELLOW)
    if med_rt is not None:
        fig_hist.add_vline(x=med_rt, line_dash="dot", line_color=C_GREEN,
                           annotation_text=f"Median {med_rt:.1f} min",
                           annotation_font_color=C_GREEN)
    _apply_chart_style(fig_hist, height=360)
    fig_hist.update_layout(margin=dict(l=55, r=30, t=60, b=50))

    # Hour-of-day bar chart
    hr     = df_d.groupby("Hour").size().reset_index(name="Calls")
    fig_hr = px.bar(
        hr, x="Hour", y="Calls",
        title=f"{dept} — Calls by Hour of Day (2024 NFIRS Data)",
        color="Calls",
        color_continuous_scale=[[0, "#2E2A1E"], [0.5, C_PRIMARY], [1, "#F7C143"]],
    )
    fig_hr.update_traces(
        hovertemplate="Hour %{x}:00 — %{y} calls<extra></extra>",
    )
    fig_hr.add_vline(x=8,  line_dash="dash", line_color=C_MUTED,
                     annotation_text="8am", annotation_font_color=C_MUTED)
    fig_hr.add_vline(x=17, line_dash="dash", line_color=C_MUTED,
                     annotation_text="5pm", annotation_font_color=C_MUTED)
    fig_hr.update_layout(coloraxis_showscale=False)
    _apply_chart_style(fig_hr, height=360)
    fig_hr.update_layout(margin=dict(l=55, r=30, t=60, b=50))

    # Monthly — dept vs county average per dept
    mo_d       = df_d.groupby("Month").size().reset_index(name="Calls")
    mo_d["Month_Name"] = mo_d["Month"].map(MONTH_NAMES)
    county_mo  = raw.groupby("Month").size().reset_index(name="Total")
    county_mo["Avg"]        = county_mo["Total"] / raw["Department"].nunique()
    county_mo["Month_Name"] = county_mo["Month"].map(MONTH_NAMES)

    fig_mo = go.Figure([
        go.Scatter(
            x=mo_d["Month_Name"], y=mo_d["Calls"],
            name=dept, mode="lines+markers",
            line=dict(color=C_PRIMARY, width=2.5),
            marker=dict(size=7, color=C_PRIMARY),
            hovertemplate="<b>" + dept + "</b><br>%{x}: %{y} calls<extra></extra>",
        ),
        go.Scatter(
            x=county_mo["Month_Name"], y=county_mo["Avg"],
            name="County Avg (per dept)", mode="lines",
            line=dict(color=C_MUTED, dash="dash", width=1.5),
            hovertemplate="County avg: %{y:.0f} calls<extra></extra>",
        ),
    ])
    fig_mo.update_layout(
        title=f"{dept} — Monthly EMS Calls vs County Average (2024)",
        xaxis_title="Month", yaxis_title="EMS Calls",
    )
    _apply_chart_style(fig_mo, height=340, legend_below=False)
    fig_mo.update_layout(margin=dict(l=55, r=30, t=60, b=50))

    # ── High-frequency call locations (table + mini map) ─────────────────────
    hf = HIGH_FREQ_ADDRESSES.get(dept)
    if hf:
        # Build DataTable rows
        table_data = []
        for entry in hf:
            addr, calls, note = entry[0], entry[1], entry[2]
            pct = round(100 * calls / auth_c, 1) if auth_c else 0
            table_data.append({"Address": addr, "Calls": calls,
                               "% of Total": f"{pct}%", "Note": note})

        hf_table = dash_table.DataTable(
            data=table_data,
            columns=[
                {"name": "#", "id": "row_num"},
                {"name": "Address", "id": "Address"},
                {"name": "Calls", "id": "Calls", "type": "numeric"},
                {"name": "% of Total", "id": "% of Total"},
                {"name": "Note", "id": "Note"},
            ],
            # Add row numbers
            style_cell={"textAlign": "left", "padding": "6px 10px",
                        "fontFamily": FONT_STACK, "fontSize": "0.82rem",
                        "backgroundColor": C_CARD, "color": C_TEXT,
                        "border": f"1px solid {C_BORDER}"},
            style_header={"fontWeight": "bold", "backgroundColor": "#2A2E34",
                          "color": C_TEXT, "border": f"1px solid {C_BORDER}"},
            style_data_conditional=[
                {"if": {"column_id": "Calls"}, "textAlign": "right", "fontWeight": "bold"},
                {"if": {"column_id": "% of Total"}, "textAlign": "right"},
                {"if": {"column_id": "row_num"}, "textAlign": "center", "width": "35px"},
            ],
            sort_action="native",
            page_size=10,
        )
        # Add row numbers to data
        for i, row in enumerate(table_data, 1):
            row["row_num"] = i

        # Build mini map with markers
        markers = []
        max_calls = max(e[1] for e in hf)
        for entry in hf:
            addr, calls, note, lat, lon = entry[0], entry[1], entry[2], entry[3], entry[4]
            # Scale radius 6-20px by call volume
            radius = 6 + 14 * (calls / max_calls) if max_calls else 8
            color = "#EF4444" if calls >= 50 else "#F59E0B" if calls >= 20 else C_PRIMARY
            tooltip_text = f"{addr} — {calls:,} calls"
            if note:
                tooltip_text += f" ({note})"
            markers.append(dl.CircleMarker(
                center=[lat, lon], radius=radius,
                color="#1E293B", weight=1.5,
                fillColor=color, fillOpacity=0.85,
                children=[dl.Tooltip(tooltip_text)],
            ))

        # Compute map center and zoom from marker bounds
        lats = [e[3] for e in hf]
        lons = [e[4] for e in hf]
        center = [(min(lats)+max(lats))/2, (min(lons)+max(lons))/2]
        # Estimate zoom from lat/lon spread
        lat_spread = max(lats) - min(lats)
        lon_spread = max(lons) - min(lons)
        spread = max(lat_spread, lon_spread, 0.005)
        zoom = 14 if spread < 0.01 else 13 if spread < 0.03 else 12 if spread < 0.06 else 11

        mini_map = dl.Map(
            center=center, zoom=zoom,
            style={"width": "100%", "height": "360px", "borderRadius": "6px",
                   "border": f"1px solid {C_BORDER}"},
            children=[
                dl.TileLayer(
                    url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                    attribution='&copy; <a href="https://carto.com/">CARTO</a>',
                ),
                dl.LayerGroup(markers),
            ],
        )

        hf_content = html.Div([
            _sub_header(f"High-Frequency Call Locations — {dept} (2024 Looker Studio Data)"),
            html.P("Addresses with disproportionately high call volumes. Marker size = relative call volume.",
                    style={"fontSize": "0.8rem", "color": C_MUTED, "margin": "0 0 10px",
                           "fontFamily": FONT_STACK}),
            html.Div([
                html.Div(hf_table, style={"flex": "1", "minWidth": "320px"}),
                html.Div(mini_map, style={"flex": "1", "minWidth": "320px"}),
            ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),
            html.P(
                "Source: Looker Studio PDF reports (2024). "
                "Edgerton data excluded due to cross-department address error in source report.",
                style={"fontSize": "0.7rem", "color": C_MUTED, "marginTop": "8px",
                       "fontFamily": FONT_STACK}),
        ], style={"marginTop": "16px"})
    else:
        hf_content = html.Div()

    # ── Data quality warning ───────────────────────────────────────────────────
    dq_note = DATA_QUALITY_NOTES.get(dept)
    if dq_note:
        dq_content = html.Div([
            html.Div([
                html.Span("Data Quality Note: ", style={"fontWeight": "bold"}),
                html.Span(dq_note),
            ], style={
                "background": "#3D3520", "borderLeft": f"3px solid {C_YELLOW}",
                "padding": "10px 14px", "marginTop": "12px", "borderRadius": "4px",
                "fontSize": "0.82rem", "color": "#F7C143", "fontFamily": FONT_STACK,
            }),
        ])
    else:
        dq_content = html.Div()

    return cards, fig_als, fig_hist, fig_hr, fig_mo, hf_content, dq_content


# ── Section 13: Utilization Analysis Callbacks ──────────────────────────────────

def _build_util_df():
    """Merge budget + authoritative EMS call volumes into one utilization DataFrame."""
    merged = budget.copy()

    # Use authoritative EMS call counts (user-provided ground truth, Mar 2026)
    merged["EMS_Calls"] = merged["Municipality"].map(AUTH_EMS_CALLS).fillna(0)

    # Computed metrics — EMS-only scope (Total_Calls = EMS_Calls since we only consider EMS)
    merged["Total_Calls"]        = merged["EMS_Calls"]  # Alias for backward compat in charts
    merged["Cost_Per_Call"]      = (merged["Total_Expense"] / merged["EMS_Calls"].replace(0, float("nan"))).round(0)
    merged["Cost_Per_EMS_Call"]  = merged["Cost_Per_Call"]  # Same since EMS-only
    merged["Revenue_Recovery"]   = (merged["EMS_Revenue"] / merged["Total_Expense"] * 100).round(1)
    merged["Tax_Per_Call"]       = (merged["Net_Tax"] / merged["EMS_Calls"].replace(0, float("nan"))).round(0)
    merged["Staff_Total"]        = merged["Staff_FT"].fillna(0) + merged["Staff_PT"].fillna(0)
    merged["EMS_Per_FT"]         = (merged["EMS_Calls"] / merged["Staff_FT"].replace(0, float("nan"))).round(1)
    merged["EMS_Per_Staff"]      = (merged["EMS_Calls"] / merged["Staff_Total"].replace(0, float("nan"))).round(1)

    # ── Population-normalized metrics ──────────────────────────────────────
    merged["Population"]         = merged["Municipality"].map(SERVICE_AREA_POP)
    merged["Calls_Per_1K_Pop"]   = (merged["EMS_Calls"]   / merged["Population"] * 1000).round(1)
    merged["EMS_Per_1K_Pop"]     = merged["Calls_Per_1K_Pop"]  # Same since EMS-only
    merged["Expense_Per_Capita"] = (merged["Total_Expense"] / merged["Population"]).round(0)
    merged["Tax_Per_Capita"]     = (merged["Net_Tax"]       / merged["Population"]).round(0)
    merged["Revenue_Per_Capita"] = (merged["EMS_Revenue"]   / merged["Population"]).round(0)

    # Outlier flags — percentile-based thresholds (75th/25th) so they
    # adapt to the actual distribution rather than arbitrary cut-offs.
    _p75_cost = merged["Cost_Per_Call"].quantile(0.75)
    _p75_tax  = merged["Tax_Per_Call"].quantile(0.75)
    _p25_vol  = merged["EMS_Calls"].quantile(0.25)
    _p25_rec  = merged["Revenue_Recovery"].quantile(0.25)
    _p25_staff = merged["EMS_Per_Staff"].quantile(0.25)
    merged["Flag_Cost"]     = (merged["Cost_Per_Call"]    > _p75_cost).astype(int)
    merged["Flag_Tax"]      = (merged["Tax_Per_Call"]     > _p75_tax).astype(int)
    merged["Flag_Volume"]   = (merged["EMS_Calls"]        < _p25_vol).astype(int)
    merged["Flag_Recovery"] = (merged["Revenue_Recovery"] < _p25_rec).astype(int)
    merged["Flag_Staff"]    = (merged["EMS_Per_Staff"]    < _p25_staff).astype(int)
    merged["Flags"]         = (merged[["Flag_Cost","Flag_Tax","Flag_Volume",
                                        "Flag_Recovery","Flag_Staff"]].sum(axis=1))

    # Service level from ALS_LEVELS
    merged["Service_Level"] = merged["Municipality"].map(
        {k: v["Level"] for k, v in ALS_LEVELS.items()}
    ).fillna("Unknown")

    return merged


# Pre-compute once at startup
_util = _build_util_df()

# Colour helpers — updated to use the design system constants
_FLAG_COLORS = {0: C_GREEN, 1: C_YELLOW, 2: C_ORANGE, 3: C_RED}
_SVC_COLORS  = {"ALS": C_PRIMARY, "AEMT": "#60A5FA", "BLS": C_GREEN,
                "N/A": C_BORDER, "Unknown": "#5C5C5C"}


# Utilization analysis — static, computed once on first access
@lru_cache(maxsize=1)
def _get_utilization_figs():
    u = _util.copy()

    # ── Chart 1: Cost per call (horizontal bar, coloured by flag count) ────────
    u1 = u.dropna(subset=["Cost_Per_Call"]).sort_values("Cost_Per_Call")
    bar_colors = [_FLAG_COLORS.get(min(int(f), 3), C_MUTED) for f in u1["Flags"]]
    fig1 = go.Figure(go.Bar(
        y=u1["Municipality"], x=u1["Cost_Per_Call"],
        orientation="h",
        marker_color=bar_colors,
        text=u1["Cost_Per_Call"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
        customdata=u1[["Service_Level","Model","EMS_Calls","Flags"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Cost/Call: $%{x:,.0f}<br>"
            "Service: %{customdata[0]} · Model: %{customdata[1]}<br>"
            "EMS Calls: %{customdata[2]:,}<br>"
            "Outlier Flags: %{customdata[3]}<extra></extra>"
        ),
    ))
    fig1.update_layout(
        title="Cost Per EMS Call (Total Expense ÷ EMS Calls)",
        xaxis_title="$ per call",
        xaxis_tickprefix="$",
    )
    _apply_chart_style(fig1, height=500)
    fig1.update_layout(
        margin=dict(l=145, r=100, t=60, b=30),
        yaxis=dict(tickfont=dict(size=13, color=C_TEXT)),
    )
    fig1.add_vline(x=u1["Cost_Per_Call"].median(), line_dash="dash",
                   line_color=C_MUTED, annotation_text="County median",
                   annotation_font_color=C_MUTED,
                   annotation_position="top right")

    # ── Chart 2: Revenue recovery rate ─────────────────────────────────────────
    u2 = u.dropna(subset=["Revenue_Recovery"]).sort_values("Revenue_Recovery", ascending=False)
    _rr_q = u2["Revenue_Recovery"].quantile([0.25, 0.5, 0.75])
    rec_colors = [C_GREEN if v >= _rr_q[0.75] else C_ORANGE if v >= _rr_q[0.25] else C_RED
                  for v in u2["Revenue_Recovery"]]
    fig2 = go.Figure(go.Bar(
        x=u2["Municipality"], y=u2["Revenue_Recovery"],
        marker_color=rec_colors,
        text=u2["Revenue_Recovery"].apply(lambda v: f"{v:.1f}%"),
        textposition="outside",
        customdata=u2[["EMS_Revenue","Total_Expense","Net_Tax"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Recovery: %{y:.1f}%<br>"
            "EMS Revenue: $%{customdata[0]:,.0f}<br>"
            "Total Expense: $%{customdata[1]:,.0f}<br>"
            "Net Tax: $%{customdata[2]:,.0f}<extra></extra>"
        ),
    ))
    fig2.update_layout(
        title="Revenue Recovery Rate (EMS Revenue ÷ Total Expense)",
        yaxis_title="% of expenses recovered",
        yaxis_ticksuffix="%",
    )
    _apply_chart_style(fig2, height=500)
    fig2.update_layout(
        margin=dict(l=60, r=100, t=60, b=130),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
    )
    fig2.add_hline(y=100, line_dash="dot", line_color=C_GREEN,
                   annotation_text="Self-sustaining (100%)",
                   annotation_font_color=C_GREEN,
                   annotation_position="right")
    fig2.add_hline(y=u2["Revenue_Recovery"].mean(), line_dash="dash",
                   line_color=C_MUTED,
                   annotation_text=f"Avg {u2['Revenue_Recovery'].mean():.0f}%",
                   annotation_font_color=C_MUTED,
                   annotation_position="right")

    # ── Chart 3: Tax subsidy per call ──────────────────────────────────────────
    u3 = u.dropna(subset=["Tax_Per_Call"]).sort_values("Tax_Per_Call", ascending=False)
    _tpc_q = u3["Tax_Per_Call"].quantile([0.25, 0.5, 0.75])
    tax_colors = [C_RED if v > _tpc_q[0.75] else C_ORANGE if v > _tpc_q[0.5] else
                  C_YELLOW if v > _tpc_q[0.25] else C_GREEN for v in u3["Tax_Per_Call"]]
    fig3 = go.Figure(go.Bar(
        x=u3["Municipality"], y=u3["Tax_Per_Call"],
        marker_color=tax_colors,
        text=u3["Tax_Per_Call"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
        customdata=u3[["Net_Tax","EMS_Calls","Service_Level"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Tax/Call: $%{y:,.0f}<br>"
            "Net Tax: $%{customdata[0]:,.0f}<br>"
            "EMS Calls: %{customdata[1]:,}<br>"
            "Service Level: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig3.update_layout(
        title="Taxpayer Subsidy Per EMS Call (Net Tax ÷ EMS Calls)",
        yaxis_title="$ per call (tax levy only)",
        yaxis_tickprefix="$",
    )
    _apply_chart_style(fig3, height=500)
    fig3.update_layout(
        margin=dict(l=60, r=100, t=60, b=130),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
    )
    _p75_tax_chart = u3["Tax_Per_Call"].quantile(0.75)
    fig3.add_hline(y=_p75_tax_chart, line_dash="dash", line_color=C_ORANGE,
                   annotation_text=f"75th pctl ${_p75_tax_chart:,.0f}",
                   annotation_font_color=C_ORANGE,
                   annotation_position="right")

    # ── Chart 4: EMS calls per FT staff ────────────────────────────────────────
    u4 = u.dropna(subset=["EMS_Per_FT"]).sort_values("EMS_Per_FT", ascending=False)
    ft_colors = [_SVC_COLORS.get(s, C_MUTED) for s in u4["Service_Level"]]
    fig4 = go.Figure(go.Bar(
        x=u4["Municipality"], y=u4["EMS_Per_FT"],
        marker_color=ft_colors,
        text=u4["EMS_Per_FT"].apply(lambda v: f"{v:.0f}"),
        textposition="outside",
        customdata=u4[["EMS_Calls","Staff_FT","Service_Level","Model"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "EMS Calls/FT: %{y:.0f}<br>"
            "EMS Calls: %{customdata[0]:,.0f}<br>"
            "FT Staff: %{customdata[1]:.0f}<br>"
            "Level: %{customdata[2]} · Model: %{customdata[3]}<extra></extra>"
        ),
    ))
    fig4.add_hline(y=50, line_dash="dash", line_color=C_MUTED,
                   annotation_text="Minimum proficiency threshold (~50)",
                   annotation_font_color=C_MUTED,
                   annotation_position="right")
    fig4.update_layout(
        title="EMS Calls per Full-Time Staff (Staff Utilization — colored by service level)",
        yaxis_title="EMS calls / FT staff member",
    )
    _apply_chart_style(fig4, height=500)
    fig4.update_layout(
        margin=dict(l=60, r=100, t=60, b=130),
        xaxis=dict(tickangle=-40, automargin=True, tickfont=dict(size=12, color=C_TEXT)),
    )

    # ── Chart 5: Staffing model efficiency bubble ──────────────────────────────
    u5 = u.dropna(subset=["Cost_Per_EMS_Call","Revenue_Recovery","EMS_Calls"])
    svc_colors5 = [_SVC_COLORS.get(s, C_MUTED) for s in u5["Service_Level"]]
    fig5 = go.Figure(go.Scatter(
        x=u5["Revenue_Recovery"],
        y=u5["Cost_Per_EMS_Call"],
        mode="markers+text",
        marker=dict(
            size=(u5["EMS_Calls"] / u5["EMS_Calls"].max() * 60 + 12).clip(lower=12),
            color=svc_colors5,
            line=dict(width=1.5, color="white"),
            opacity=0.88,
        ),
        text=u5["Municipality"],
        textposition="top center",
        textfont=dict(size=11, color=C_TEXT, family=FONT_STACK),
        customdata=u5[["EMS_Calls","Model","Service_Level","Flags","Net_Tax"]].values,
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Cost/EMS Call: $%{y:,.0f}<br>"
            "Revenue Recovery: %{x:.1f}%<br>"
            "EMS Calls: %{customdata[0]:,}<br>"
            "Model: %{customdata[1]} · Level: %{customdata[2]}<br>"
            "Outlier Flags: %{customdata[3]}<br>"
            "Net Tax: $%{customdata[4]:,.0f}<extra></extra>"
        ),
        showlegend=False,
    ))
    # Quadrant reference lines
    med_rec = u5["Revenue_Recovery"].median()
    med_cst = u5["Cost_Per_EMS_Call"].median()
    fig5.add_vline(x=med_rec, line_dash="dash", line_color=C_BORDER)
    fig5.add_hline(y=med_cst, line_dash="dash", line_color=C_BORDER)
    # Quadrant labels
    for txt, xr, yr in [
        ("High recovery\nLow cost  \u2713", med_rec + 2, med_cst * 0.4),
        ("Low recovery\nLow cost",          med_rec * 0.3, med_cst * 0.4),
        ("Low recovery\nHigh cost  \u2717", med_rec * 0.3, med_cst * 2.5),
        ("High recovery\nHigh cost",        med_rec + 2,   med_cst * 2.5),
    ]:
        fig5.add_annotation(x=xr, y=yr, text=txt,
                            showarrow=False, font=dict(size=9, color=C_BORDER),
                            align="center")
    # Legend proxies for service level
    for lvl, col in _SVC_COLORS.items():
        if lvl in u5["Service_Level"].values:
            fig5.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=10, color=col, line=dict(color="white", width=1)),
                name=lvl, showlegend=True,
            ))
    fig5.update_layout(
        title="Efficiency Matrix: Revenue Recovery vs. Cost per EMS Call<br>"
              "<sup>Bubble size = EMS call volume  ·  Color = service level</sup>",
        xaxis_title="Revenue Recovery (%)",
        yaxis_title="Cost per EMS Call ($)",
        yaxis_tickprefix="$",
        xaxis_ticksuffix="%",
    )
    _apply_chart_style(fig5, height=540, legend_below=True, title_has_subtitle=True)
    fig5.update_layout(
        margin=dict(l=80, r=40, t=80, b=100),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.12,
            xanchor="left", x=0,
            title=dict(text="Service Level:", font=dict(size=11, color=C_MUTED)),
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
    )

    # ── Chart 6: Tax Per Capita (companion to Chart 3 Tax Per Call) ────────────
    # Drops depts where Tax_Per_Capita is NaN (Edgerton: multi-county budget; Lake Mills: Net_Tax=full)
    u6 = u.dropna(subset=["Tax_Per_Capita"]).sort_values("Tax_Per_Capita", ascending=False)
    _tc_q = u6["Tax_Per_Capita"].quantile([0.25, 0.5, 0.75])
    tpc_colors = [
        C_RED    if v > _tc_q[0.75] else
        C_ORANGE if v > _tc_q[0.5]  else
        C_YELLOW if v > _tc_q[0.25] else
        C_GREEN
        for v in u6["Tax_Per_Capita"]
    ]
    fig6 = go.Figure(go.Bar(
        y=u6["Municipality"], x=u6["Tax_Per_Capita"],
        orientation="h",
        marker_color=tpc_colors,
        text=u6["Tax_Per_Capita"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside",
        customdata=u6[["Net_Tax", "Population", "EMS_Calls", "Service_Level"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Tax/Resident: $%{x:,.0f}<br>"
            "Net Tax: $%{customdata[0]:,.0f}<br>"
            "Service Area Pop.: %{customdata[1]:,}<br>"
            "EMS Calls: %{customdata[2]:,}<br>"
            "Service Level: %{customdata[3]}<extra></extra>"
        ),
    ))
    # WI average EMS user fee reference line
    fig6.add_vline(
        x=_BENCH["wi_ems_fee_per_capita"],
        line_dash="dash", line_color=C_GREEN,
        annotation_text=f"WI avg EMS user fee ${_BENCH['wi_ems_fee_per_capita']}/capita",
        annotation_font_color=C_GREEN,
        annotation_position="top right",
    )
    fig6.update_layout(
        title=(
            "Taxpayer Burden Per Resident (Net Tax \u00f7 Service Area Population)"
            f"<br><sup>WI avg EMS user fee: $36/capita  \u00b7  "
            f"Color = quartile  \u00b7  Green <${_tc_q[0.25]:,.0f}  \u00b7  "
            f"Yellow ${_tc_q[0.25]:,.0f}\u2013${_tc_q[0.5]:,.0f}  \u00b7  "
            f"Orange ${_tc_q[0.5]:,.0f}\u2013${_tc_q[0.75]:,.0f}  \u00b7  "
            f"Red >${_tc_q[0.75]:,.0f}</sup>"
        ),
        xaxis_title="Net tax dollars per resident",
        xaxis_tickprefix="$",
    )
    _apply_chart_style(fig6, height=440, title_has_subtitle=True)
    fig6.update_layout(margin=dict(l=140, r=110, t=80, b=30))

    # ── Chart 7: Calls Per 1,000 Population (companion to call volume) ──────────
    # Western Lakes anomaly: 6,581 calls for only ~2,974 residents (full Waukesha Co. district)
    u7 = u.dropna(subset=["Calls_Per_1K_Pop"]).sort_values("Calls_Per_1K_Pop", ascending=False)
    svc_colors7 = [_SVC_COLORS.get(s, C_MUTED) for s in u7["Service_Level"]]
    fig7 = go.Figure(go.Bar(
        y=u7["Municipality"], x=u7["Calls_Per_1K_Pop"],
        orientation="h",
        marker_color=svc_colors7,
        text=u7["Calls_Per_1K_Pop"].apply(lambda v: f"{v:,.0f}"),
        textposition="outside",
        customdata=u7[["EMS_Calls", "Population", "Service_Level"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "EMS Calls/1K Residents: %{x:,.0f}<br>"
            "EMS Calls: %{customdata[0]:,}<br>"
            "Service Area Pop.: %{customdata[1]:,}<br>"
            "Service Level: %{customdata[2]}<extra></extra>"
        ),
    ))
    # WI statewide benchmark reference line
    fig7.add_vline(
        x=_BENCH["wi_calls_per_1k"],
        line_dash="dash", line_color=C_YELLOW,
        annotation_text=f"WI avg {_BENCH['wi_calls_per_1k']}/1K",
        annotation_font_color=C_YELLOW,
        annotation_position="top right",
    )
    # County median reference line
    med_c1k = float(u7["Calls_Per_1K_Pop"].median())
    fig7.add_vline(
        x=med_c1k, line_dash="dot", line_color=C_MUTED,
        annotation_text=f"County median {med_c1k:.0f}/1K",
        annotation_font_color=C_MUTED,
        annotation_position="bottom right",
    )
    # Western Lakes note (full Waukesha Co. district — inflated denominator)
    if "Western Lakes" in u7["Municipality"].values:
        wl_idx = u7[u7["Municipality"] == "Western Lakes"].index
        if len(wl_idx):
            fig7.add_annotation(
                x=float(u7.loc[wl_idx[0], "Calls_Per_1K_Pop"]) + 5,
                y="Western Lakes",
                text="Full Waukesha Co. district\n(~200\u2013250 Jeff. Co. calls only)",
                showarrow=True, arrowhead=2, arrowcolor=C_MUTED,
                font=dict(size=9, color=C_MUTED),
                xanchor="left", align="left",
                ax=40, ay=0,
            )
    # Legend proxies for service level
    for lvl, col in _SVC_COLORS.items():
        if lvl in u7["Service_Level"].values:
            fig7.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(symbol="square", size=10, color=col,
                            line=dict(color="white", width=1)),
                name=lvl, showlegend=True, hoverinfo="skip",
            ))
    fig7.update_layout(
        title=(
            "EMS Call Rate Per 1,000 Residents (EMS Calls \u00f7 Service Area Population \u00d7 1,000)"
            "<br><sup>Color = service level  \u00b7  Western Lakes: full Waukesha Co. district, not Jefferson Co. only</sup>"
        ),
        xaxis_title="EMS calls per 1,000 residents",
    )
    _apply_chart_style(fig7, height=460, legend_below=True, title_has_subtitle=True)
    fig7.update_layout(
        margin=dict(l=140, r=130, t=80, b=60),
        legend=dict(
            orientation="h",
            yanchor="top", y=-0.08,
            xanchor="left", x=0,
            title=dict(text="Service Level:", font=dict(size=11, color=C_MUTED)),
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
    )

    # ── Outlier table ──────────────────────────────────────────────────────────
    # Compute threshold labels from the actual data for transparency
    _p75c = u["Cost_Per_Call"].quantile(0.75)
    _p75t = u["Tax_Per_Call"].quantile(0.75)
    _p25v = u["EMS_Calls"].quantile(0.25)
    _p25r = u["Revenue_Recovery"].quantile(0.25)
    _p25s = u["EMS_Per_Staff"].quantile(0.25)
    flag_map = {
        "Flag_Cost":     f"Cost/call > ${_p75c:,.0f} (75th pctl)",
        "Flag_Tax":      f"Tax/call > ${_p75t:,.0f} (75th pctl)",
        "Flag_Volume":   f"Volume < {_p25v:,.0f} EMS calls (25th pctl)",
        "Flag_Recovery": f"Recovery < {_p25r:.0f}% (25th pctl)",
        "Flag_Staff":    f"Staff util < {_p25s:.0f} EMS/staff (25th pctl)",
    }
    rows = []
    for _, r in u.iterrows():
        if r["Flags"] < 2:          # only show departments with 2+ flags
            continue
        active_flags = [lbl for col, lbl in flag_map.items() if r.get(col, 0) == 1]
        rows.append({
            "Department":       r["Municipality"],
            "# Flags":          int(r["Flags"]),
            "Why Flagged":      " · ".join(active_flags),
            "Cost/Call":        f"${r['Cost_Per_Call']:,.0f}" if pd.notna(r.get("Cost_Per_Call")) else "—",
            "Recovery %":       f"{r['Revenue_Recovery']:.1f}%" if pd.notna(r.get("Revenue_Recovery")) else "—",
            "Tax/Call":         f"${r['Tax_Per_Call']:,.0f}" if pd.notna(r.get("Tax_Per_Call")) else "—",
            "EMS Calls":        f"{int(r['EMS_Calls']):,}" if pd.notna(r.get("EMS_Calls")) else "—",
            "Level":            r.get("Service_Level","—"),
        })
    rows.sort(key=lambda x: -x["# Flags"])
    cols = [{"name": c, "id": c} for c in
            ["Department","# Flags","Why Flagged","Cost/Call","Recovery %",
             "Tax/Call","EMS Calls","Level"]]
    return fig1, fig2, fig3, fig4, fig5, rows, cols, fig6, fig7


# ── NEW: Billing Collections Chart (Chief Association Data) ──────────────────
@lru_cache(maxsize=1)
def _get_billing_collections_fig():
    """Grouped bar chart: 2024 vs 2025 net collections by agency."""
    bc = BILLING_COLLECTIONS.sort_values("Collections_2025", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=bc["Agency"], x=bc["Collections_2024"], orientation="h",
        name="2024 Net Collections", marker_color=C_MUTED,
        text=bc["Collections_2024"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside", textfont=dict(size=10),
    ))
    fig.add_trace(go.Bar(
        y=bc["Agency"], x=bc["Collections_2025"], orientation="h",
        name="2025 Net Collections", marker_color=C_PRIMARY,
        text=bc["Collections_2025"].apply(lambda v: f"${v:,.0f}"),
        textposition="outside", textfont=dict(size=10),
    ))
    _total_24 = bc["Collections_2024"].sum()
    _total_25 = bc["Collections_2025"].sum()
    _total_chg = _total_25 - _total_24
    fig.update_layout(
        title=(
            "Actual Net Billing Collections by Agency — 2024 vs 2025"
            f"<br><sup style='color:{C_MUTED}'>Source: Jefferson County Chief Association Agency Data 2025.xlsx "
            f"| 9 of 12 EMS agencies reporting | County total: "
            f"${_total_24:,.0f} (2024) → ${_total_25:,.0f} (2025) = +${_total_chg:,.0f} (+{100*_total_chg/_total_24:.0f}%)</sup>"
        ),
        barmode="group",
    )
    _apply_chart_style(fig, height=480, legend_below=True, title_has_subtitle=True)
    fig.update_layout(margin=dict(l=20, r=120, t=70, b=20))
    return fig

@lru_cache(maxsize=1)
def _get_billing_change_fig():
    """Bar chart showing YoY change in collections."""
    bc = BILLING_COLLECTIONS.sort_values("Change", ascending=True)
    colors = [C_GREEN if v > 0 else C_RED for v in bc["Change"]]
    fig = go.Figure(go.Bar(
        y=bc["Agency"], x=bc["Change"], orientation="h",
        marker_color=colors,
        text=[f"+${v:,.0f} ({p:.0f}%)" if v > 0 else f"${v:,.0f} ({p:.0f}%)"
              for v, p in zip(bc["Change"], bc["Pct_Change"])],
        textposition="outside", textfont=dict(size=10),
        customdata=bc[["Collections_2024", "Collections_2025", "Pct_Change"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "2024: $%{customdata[0]:,.0f}<br>"
            "2025: $%{customdata[1]:,.0f}<br>"
            "Change: $%{x:,.0f} (%{customdata[2]:.1f}%)<extra></extra>"
        ),
    ))
    fig.update_layout(
        title=(
            "Year-over-Year Change in Net Collections (2024 → 2025)"
            f"<br><sup style='color:{C_MUTED}'>Source: Jefferson County Chief Association Agency Data 2025.xlsx</sup>"
        ),
    )
    _apply_chart_style(fig, height=420, title_has_subtitle=True)
    fig.update_layout(margin=dict(l=20, r=120, t=70, b=20))
    return fig


# ── NEW: Mill Rate Levy Projection Charts ────────────────────────────────────
@lru_cache(maxsize=1)
def _get_levy_projection_figs():
    """Stacked bar chart showing levy distribution at selected mill rates."""
    # Show 4 representative mill rates
    show_rates = [0.1, 0.25, 0.5, 1.0]
    lp = LEVY_BY_PROVIDER.copy()
    fig = go.Figure()
    _colors = px.colors.qualitative.Set3[:12]
    for i, (_, row) in enumerate(lp.iterrows()):
        fig.add_trace(go.Bar(
            x=[f"{r} mill" for r in show_rates],
            y=[row[r] for r in show_rates],
            name=row["Provider"],
            marker_color=_colors[i % len(_colors)],
            hovertemplate=f"<b>{row['Provider']}</b><br>" + "Mill rate: %{x}<br>Levy: $%{y:,.0f}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=(
            "Hypothetical County EMS Levy by Provider at Selected Mill Rates"
            f"<br><sup style='color:{C_MUTED}'>Source: Emergency Services Population - Jefferson County.xlsx "
            f"(Payment by Service Provider) | WI DOA 2025 Preliminary Estimates</sup>"
        ),
        yaxis_title="Levy Amount ($)",
    )
    _apply_chart_style(fig, height=500, legend_below=True, title_has_subtitle=True)

    # Second chart: table of all mill rates
    table_data = []
    for _, row in lp.iterrows():
        entry = {"Provider": row["Provider"]}
        for r in _MILL_RATES:
            entry[f"{r} mill"] = f"${int(row[r]):,}"
        table_data.append(entry)
    # Totals row
    totals = {"Provider": "COUNTY TOTAL"}
    for r in _MILL_RATES:
        totals[f"{r} mill"] = f"${_LEVY_COUNTY_TOTALS[r]:,}"
    table_data.append(totals)
    table_cols = [{"name": "Provider", "id": "Provider"}] + [
        {"name": f"{r} mill", "id": f"{r} mill"} for r in _MILL_RATES
    ]
    return fig, table_data, table_cols


# ── NEW: Population by EMS Provider Table ────────────────────────────────────
@lru_cache(maxsize=1)
def _get_population_table():
    """Build a table showing WI DOA populations per EMS provider."""
    ems_depts = [d for d in SERVICE_AREA_POP if d != "Helenville"]
    rows = []
    for dept in sorted(ems_depts, key=lambda d: SERVICE_AREA_POP[d], reverse=True):
        pop = SERVICE_AREA_POP[dept]
        calls = AUTH_EMS_CALLS.get(dept, 0)
        per_1k = round(calls / pop * 1000, 1) if pop > 0 else 0
        rows.append({
            "Department": dept,
            "Service Area Population": f"{pop:,}",
            "2024 EMS Calls": f"{calls:,}",
            "Calls per 1K Pop": per_1k,
        })
    rows.append({
        "Department": "COUNTY TOTAL",
        "Service Area Population": f"{sum(SERVICE_AREA_POP[d] for d in ems_depts):,}",
        "2024 EMS Calls": f"{_AUTH_COUNTY_TOTAL:,}",
        "Calls per 1K Pop": round(_AUTH_COUNTY_TOTAL / sum(SERVICE_AREA_POP[d] for d in ems_depts) * 1000, 1),
    })
    cols = [{"name": c, "id": c} for c in rows[0].keys()]
    return rows, cols


# ── NEW: Peterson 24/7 ALS Waterfall ──────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_fig_peterson_waterfall():
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=_PETERSON_COST_MODEL["measures"],
        x=_PETERSON_COST_MODEL["labels"],
        y=_PETERSON_COST_MODEL["values"],
        textposition="outside",
        text=[f"${abs(v):,.0f}" if v != 0 else "" for v in _PETERSON_COST_MODEL["values"]],
        hovertext=_PETERSON_COST_MODEL["notes"],
        connector={"line": {"color": C_BORDER}},
        increasing={"marker": {"color": C_PRIMARY}},
        decreasing={"marker": {"color": C_GREEN}},
        totals={"marker": {"color": C_YELLOW}},
    ))
    fig.update_layout(
        title="Chief Peterson's 24/7 ALS Single-Unit Cost Model"
              "<br><sup>Source: 25-1210 JC EMS Workgroup Cost Projection.pdf  |  "
              "6 FTEs (3 Paramedics + 3 EMT-A)  |  24/48 schedule  |  700 calls/yr</sup>",
        yaxis_title="$ Amount",
        yaxis_tickprefix="$",
        yaxis_separatethousands=True,
    )
    _apply_chart_style(fig, height=520, legend_below=True, title_has_subtitle=True)
    fig.update_layout(margin=dict(l=60, r=40, t=85, b=140),
                      xaxis=dict(tickangle=-35))
    return fig


# ── Secondary Network Simulation Tab ──────────────────────────────────────────

def _render_simulation_tab():
    """Build the full Secondary Network Simulation tab content."""
    if _SIM_KPI is None:
        return html.Div([
            html.Div([
                _section_header("Secondary Network Simulation"),
                html.P("Simulation data not found. Run secondary_simulation.py first "
                       "to generate results.",
                       style={"color": C_MUTED, "fontSize": "0.9rem"}),
            ], style=CARD),
        ])

    K = len(_SIM_HUBS) if _SIM_HUBS else 10

    # Extract key KPIs
    def _get_kpi(name):
        row = _SIM_KPI[_SIM_KPI["KPI"] == name]
        if row.empty:
            return {"Current": "N/A", "Proposed": "N/A", "Delta": "N/A"}
        r = row.iloc[0]
        return {"Current": r["Current"], "Proposed": r["Proposed"], "Delta": r["Delta"]}

    sec_count = _get_kpi("Secondary Calls")
    med_rt = _get_kpi("Median Secondary RT (min)")
    p90_rt = _get_kpi("P90 Secondary RT (min)")
    cov_14 = _get_kpi("Secondary within 14 min (%)")
    cov_10 = _get_kpi("Secondary within 10 min (%)")
    queue = _get_kpi("Calls with Wait (queue)")

    # Build interactive map markers
    map_children = [
        dl.TileLayer(
            url="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
            attribution='&copy; CARTO',
        ),
    ]

    # Existing primary stations (gray squares)
    for s in _SIM_PRIMARY_STATIONS:
        map_children.append(
            dl.Marker(
                position=[s["lat"], s["lon"]],
                children=[
                    dl.Tooltip(f"{s['name']} (Primary Station)"),
                    dl.Popup(html.Div([
                        html.B(s["name"]),
                        html.Br(),
                        html.Span("Existing primary station (retained)",
                                  style={"fontSize": "11px", "color": "#666"}),
                    ])),
                ],
                icon=dict(
                    iconUrl="https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-grey.png",
                    iconSize=[16, 26], iconAnchor=[8, 26], popupAnchor=[0, -26],
                ),
            )
        )

    # Proposed secondary hubs (red markers with info)
    hub_colors = ["red", "blue", "green", "orange", "violet",
                  "yellow", "black", "grey", "gold", "cadetblue"]
    for i, h in enumerate(_SIM_HUBS):
        color = hub_colors[i % len(hub_colors)]
        map_children.append(
            dl.Marker(
                position=[h["lat"], h["lon"]],
                children=[
                    dl.Tooltip(f"{h['unit']} - {h['calls']} calls/yr, {h['cpd']:.1f}/day"),
                    dl.Popup(html.Div([
                        html.B(f"{h['unit']}",
                               style={"fontSize": "14px", "color": "#c0392b"}),
                        html.Br(),
                        html.Span(f"Proposed county-wide secondary hub",
                                  style={"fontSize": "11px", "color": "#666"}),
                        html.Hr(style={"margin": "4px 0"}),
                        html.Div(f"Calls served: {h['calls']}/yr ({h['cpd']:.1f}/day)",
                                 style={"fontSize": "12px"}),
                        html.Div(f"Utilization: {h['util']:.1f}%",
                                 style={"fontSize": "12px"}),
                        html.Div(f"Location: ({h['lat']:.4f}, {h['lon']:.4f})",
                                 style={"fontSize": "11px", "color": "#999"}),
                    ], style={"lineHeight": "1.4"})),
                ],
                icon=dict(
                    iconUrl=f"https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-{color}.png",
                    iconSize=[20, 33], iconAnchor=[10, 33], popupAnchor=[0, -33],
                ),
            )
        )

    # Build sensitivity chart
    sens_fig = go.Figure()
    if _SIM_SENS is not None and len(_SIM_SENS) >= 2:
        sens_fig.add_trace(go.Scatter(
            x=_SIM_SENS["K"], y=_SIM_SENS["Median_Secondary_RT"],
            mode="lines+markers", name="Median RT",
            line=dict(color=C_PRIMARY, width=2.5), marker=dict(size=8),
        ))
        sens_fig.add_trace(go.Scatter(
            x=_SIM_SENS["K"], y=_SIM_SENS["P90_Secondary_RT"],
            mode="lines+markers", name="P90 RT",
            line=dict(color=C_RED, width=2, dash="dash"), marker=dict(size=7),
        ))
        sens_fig.update_layout(
            title="Secondary Response Time vs Fleet Size (K)"
                  "<br><sup>Discrete-event simulation of 13,754 CY2024 EMS calls (incl. Western Lakes)</sup>",
            xaxis=dict(title="County-Wide Secondary Units (K)", dtick=1),
            yaxis=dict(title="Response Time (min)"),
        )
        _apply_chart_style(sens_fig, height=380, title_has_subtitle=True, legend_below=True)

    # Build coverage chart
    cov_fig = go.Figure()
    if _SIM_SENS is not None and len(_SIM_SENS) >= 2:
        cov_fig.add_trace(go.Scatter(
            x=_SIM_SENS["K"], y=_SIM_SENS["Pct_Within_14min"],
            mode="lines+markers", name="Within 14 min",
            line=dict(color=C_GREEN, width=2.5), marker=dict(size=8),
        ))
        cov_fig.add_trace(go.Scatter(
            x=_SIM_SENS["K"], y=_SIM_SENS["Pct_Within_10min"],
            mode="lines+markers", name="Within 10 min",
            line=dict(color=C_YELLOW, width=2, dash="dash"), marker=dict(size=7),
        ))
        cov_fig.update_layout(
            title="Secondary Call Coverage vs Fleet Size"
                  "<br><sup>% of secondary calls arriving within threshold</sup>",
            xaxis=dict(title="County-Wide Secondary Units (K)", dtick=1),
            yaxis=dict(title="% of Secondary Calls Covered"),
        )
        _apply_chart_style(cov_fig, height=380, title_has_subtitle=True, legend_below=True)

    # Build utilization bar chart
    util_fig = go.Figure()
    if _SIM_UTIL is not None:
        util_fig.add_trace(go.Bar(
            y=_SIM_UTIL["Unit"], x=_SIM_UTIL["Calls_Served"],
            orientation="h", marker_color=C_PRIMARY,
            text=[f"{c} calls ({u:.1f}%)" for c, u in
                  zip(_SIM_UTIL["Calls_Served"], _SIM_UTIL["Utilization_Pct"])],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Calls: %{x}<br>Utilization: %{text}<extra></extra>",
        ))
        util_fig.update_layout(
            title=f"Per-Unit Call Volume & Utilization ({K} County-Wide Units)"
                  f"<br><sup>CY2024 simulation | Utilization = % of year unit is busy</sup>",
            xaxis=dict(title="Calls Served (CY2024)"),
            yaxis=dict(title="", autorange="reversed"),
        )
        _apply_chart_style(util_fig, height=max(280, 40 * K), title_has_subtitle=True)

    # Assemble the tab
    return html.Div([
        # CARD 1: Concept + KPIs
        html.Div([
            _section_header(f"Countywide Secondary Ambulance Network Simulation (K={K})"),
            html.P([
                "Discrete-event simulation replaying all 13,754 CY2024 EMS calls "
                "(includes Western Lakes). ",
                html.B("Current system: "), "each department uses its own fleet. ",
                html.B("Proposed system: "), "each department keeps 1 primary ambulance; ",
                f"secondary capacity replaced by {K} county-wide ALS units at optimized locations. ",
                "County-wide units respond anywhere when a primary is already on a call.",
            ], style={"fontSize": "0.85rem", "color": C_MUTED, "lineHeight": "1.6",
                      "marginBottom": "16px", "fontFamily": FONT_STACK}),

            html.Div([
                kpi_card("Secondary Calls",
                         f"{int(sec_count['Proposed'])}",
                         f"handled by county units (was {int(sec_count['Current'])} under current system)",
                         C_PRIMARY),
                kpi_card("Median Sec. RT",
                         f"{med_rt['Proposed']:.1f} min",
                         f"current: {med_rt['Current']:.1f} min",
                         C_PRIMARY,
                         delta=f"{med_rt['Delta']:+.1f} min",
                         delta_positive=med_rt['Delta'] <= 0),
                kpi_card("P90 Sec. RT",
                         f"{p90_rt['Proposed']:.1f} min",
                         f"current: {p90_rt['Current']:.1f} min",
                         C_ORANGE,
                         delta=f"{p90_rt['Delta']:+.1f} min",
                         delta_positive=p90_rt['Delta'] <= 0),
                kpi_card("14-min Coverage",
                         f"{cov_14['Proposed']:.1f}%",
                         f"of secondary calls (current: {cov_14['Current']:.1f}%)",
                         C_GREEN if cov_14['Delta'] >= 0 else C_ORANGE),
                kpi_card("Queue Events",
                         f"{int(queue['Proposed'])}",
                         f"all units busy (was {int(queue['Current'])})",
                         C_GREEN,
                         delta=f"{int(queue['Delta'])}",
                         delta_positive=queue['Delta'] <= 0),
            ], style={"display": "flex", "gap": "12px",
                      "flexWrap": "wrap", "marginBottom": "16px"}),

            html.Div([
                html.Span("Key insight: ", style={"fontWeight": "600", "color": C_PRIMARY}),
                html.Span(
                    f"Under the proposed system, {int(sec_count['Proposed'])} calls "
                    f"({100*sec_count['Proposed']/13754:.1f}%) are handled by county-wide "
                    f"secondary units. Hub locations were optimized using actual secondary call "
                    f"demand (P-Median). "
                    f"The proposed system reduces queue events from {int(queue['Current'])} to "
                    f"{int(queue['Proposed'])}. Median secondary RT "
                    f"{'improves' if med_rt['Delta'] <= 0 else 'increases'} by "
                    f"{abs(med_rt['Delta']):.1f} min.",
                    style={"fontSize": "0.8rem", "color": C_MUTED}),
            ], style={"background": "#2E3238", "borderRadius": "6px",
                      "padding": "10px 14px", "marginBottom": "10px",
                      "borderLeft": f"4px solid {C_PRIMARY}",
                      "fontFamily": FONT_STACK}),

            _source_citation(
                "secondary_simulation_v2.py -- discrete-event simulation (ems_db/)",
                "ems_calls.db (13,754 CY2024 EMS calls incl. Western Lakes)",
                "OpenRouteService drive-time matrices (13 stations x 65 BGs, 60 candidates x 65 BGs)",
                "P-Median optimization weighted by actual secondary call locations",
            ),
        ], style=CARD),

        # CARD 2: Interactive Map
        html.Div([
            _section_header("Proposed Secondary Hub Locations"),
            html.P([
                "Colored markers = proposed county-wide secondary hubs. ",
                "Gray markers = existing primary stations (retained by each department). ",
                "Click a marker for details.",
            ], style={"fontSize": "0.8rem", "color": C_MUTED, "marginBottom": "12px"}),
            dl.Map(
                id="sim-hub-map",
                center=[43.02, -88.78],
                zoom=10,
                children=map_children,
                style={"height": "550px", "borderRadius": "8px",
                       "border": f"1px solid {C_BORDER}"},
            ),
            _source_citation(
                "P-Median optimization (demand-weighted by actual secondary calls, ORS drive times)",
                "simulation_utilization.csv",
            ),
        ], style=CARD),

        # CARD 3: Sensitivity Analysis Charts
        html.Div([
            _section_header("Sensitivity Analysis: Fleet Size Impact"),
            html.P("How does the number of county-wide secondary units affect performance? "
                   "Simulation run for K = 2, 3, 4, 5, 6, 8 units.",
                   style={"fontSize": "0.8rem", "color": C_MUTED, "marginBottom": "12px"}),
            html.Div([
                html.Div([dcc.Graph(figure=sens_fig)],
                         style={"flex": "1", "minWidth": "400px"}),
                html.Div([dcc.Graph(figure=cov_fig)],
                         style={"flex": "1", "minWidth": "400px"}),
            ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),
            _source_citation("simulation_sensitivity.csv"),
        ], style=CARD),

        # CARD 4: Per-Unit Utilization
        html.Div([
            _section_header("Per-Unit Utilization & Call Distribution"),
            dcc.Graph(figure=util_fig),
            _source_citation("simulation_utilization.csv"),
        ], style=CARD),

        # CARD 5: KPI Comparison Table
        html.Div([
            _section_header("Full KPI Comparison: Current vs Proposed"),
            dash_table.DataTable(
                id="sim-kpi-table",
                columns=[
                    {"name": "KPI", "id": "KPI"},
                    {"name": "Current System", "id": "Current"},
                    {"name": f"Proposed (K={K})", "id": "Proposed"},
                    {"name": "Delta", "id": "Delta"},
                ],
                data=_SIM_KPI.to_dict("records"),
                sort_action="native",
                style_table={"overflowX": "auto", "borderRadius": "8px",
                             "overflow": "hidden"},
                style_header=_DT_STYLE_HEADER,
                style_cell={**_DT_STYLE_CELL, "fontSize": "12px"},
                style_cell_conditional=[
                    {"if": {"column_id": "KPI"}, "fontWeight": "600",
                     "textAlign": "left", "width": "300px"},
                    {"if": {"column_id": "Current"}, "textAlign": "center", "width": "120px"},
                    {"if": {"column_id": "Proposed"}, "textAlign": "center", "width": "120px"},
                    {"if": {"column_id": "Delta"}, "textAlign": "center", "width": "100px"},
                ],
                style_data_conditional=[
                    *_DT_STYLE_DATA_CONDITIONAL_BASE,
                    {"if": {"filter_query": "{Delta} < 0", "column_id": "Delta"},
                     "color": C_GREEN, "fontWeight": "600"},
                    {"if": {"filter_query": "{Delta} > 0", "column_id": "Delta"},
                     "color": C_ORANGE, "fontWeight": "600"},
                ],
            ),
            _source_citation("simulation_results_summary.csv"),
        ], style=CARD),
    ])


# ── NEW: Contract Timeline Gantt + Escalation Line ────────────────────────────
@lru_cache(maxsize=1)
def _get_fig_contract_timeline():
    status_colors = {
        "EXPIRED":               C_RED,
        "Auto-renewed":          C_YELLOW,
        "Active":                C_GREEN,
        "Active (rolling 3-yr)": C_GREEN,
        "Expired (1-yr)":        C_RED,
    }
    ct = _CONTRACT_TIMELINE.copy()
    # Sort: expired at bottom, active at top
    _so = {"Active": 0, "Active (rolling 3-yr)": 0,
           "Auto-renewed": 1, "EXPIRED": 2, "Expired (1-yr)": 2}
    ct["_order"] = ct["Status"].map(_so).fillna(1)
    ct = ct.sort_values(["_order", "End"], ascending=[False, True])

    fig_gantt = px.timeline(
        ct, x_start="Start", x_end="End", y="Contract", color="Status",
        color_discrete_map=status_colors,
    )
    fig_gantt.update_traces(marker_line_width=0, opacity=0.9)
    fig_gantt.update_yaxes(autorange="reversed", title="", showgrid=False)

    # "Today" marker
    today_dt = pd.Timestamp.now().normalize()
    fig_gantt.add_shape(
        type="line", x0=today_dt, x1=today_dt, y0=0, y1=1,
        yref="paper", line=dict(dash="dot", color=C_TEXT, width=1.5),
    )
    fig_gantt.add_annotation(
        x=today_dt, y=1.02, yref="paper",
        text="Today", showarrow=False,
        font=dict(size=10, color=C_TEXT), xanchor="left",
    )
    fig_gantt.update_layout(
        title="Contract Expiration Timeline"
              "<br><sup>Source: IGA contract text files</sup>",
        xaxis=dict(title="", tickformat="%b %Y"),
    )
    _apply_chart_style(fig_gantt, height=380, title_has_subtitle=True, legend_below=True)

    # --- Per-capita escalation line chart ---
    fig_esc = go.Figure()
    _esc_colors = {
        "Jefferson City -> 5 Towns": C_PRIMARY,
        "Waterloo -> Milford":       C_YELLOW,
        "Fort Atkinson -> Towns":    C_RED,
        "Lake Mills / Ryan Bros":    C_GREEN,
        "Ixonia -> Watertown Twp":   "#A78BFA",
    }
    for contract, grp in _CONTRACT_ESCALATION.groupby("Contract"):
        grp = grp.sort_values("Year")
        dash = "dash" if "EXPIRED" in grp["Status"].values[0] else "solid"
        fig_esc.add_trace(go.Scatter(
            x=grp["Year"], y=grp["Rate"],
            mode="lines+markers",
            name=contract,
            line=dict(color=_esc_colors.get(contract, C_MUTED), width=2.5, dash=dash),
            marker=dict(size=8),
            hovertemplate=f"<b>{contract}</b><br>%{{x}}: $%{{y:.2f}}/capita<extra></extra>",
        ))
    fig_esc.update_layout(
        title="Contract Per-Capita Rate Escalation (2023-2027)"
              "<br><sup>Source: Contract text files  |  Dashed = expired contracts</sup>",
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title="$/capita", tickprefix="$"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
    )
    _apply_chart_style(fig_esc, height=440, legend_below=True, title_has_subtitle=True)

    return fig_gantt, fig_esc


# ── 10. Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    print(f"\nDashboard ready -- open http://127.0.0.1:{port}\n")
    app.run(debug=True, host="0.0.0.0", port=port)
