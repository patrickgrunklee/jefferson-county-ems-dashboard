"""
Jefferson County geographic filter for EMS call data.

Authoritative 2024 EMS call counts per Megan 2026-04-19:
  Cambridge 197, Fort Atkinson 1,616, Ixonia 338, Jefferson 1,457,
  Johnson Creek 1,090, Lake Mills 518, Palmyra 32, Waterloo 520,
  Watertown 2,012, Whitewater 64, Edgerton 289, Western Lakes 263
  County total: 8,396 (fire+EMS combined, Jefferson-geography only).

Rule: "If a call is not in Jefferson County or not responded to by a
Jefferson-County-stationed ambulance, it is not counted."

Data sources vary per department (see DEPT_SOURCE below). Some depts'
NFIRS files include all-district calls spanning multiple counties — this
module filters them to Jefferson-only using a combination of Incident City
municipality matching + Waukesha/Rock/Dane ZIP exclusions.

Known limitation: Edgerton (Lakeside FPD) NFIRS only yields ~26 Jefferson
incidents vs Megan's authoritative 289. The remaining 263 calls are believed
to be transport/billing log records not present in the NFIRS export. Edgerton
therefore uses aggregate-only treatment (KPIs show 289; no incident-level
breakdowns available).
"""
from __future__ import annotations
import pandas as pd

# Megan's authoritative 2024 totals (fire+EMS combined, Jefferson-geography only)
AUTHORITATIVE_2024 = {
    "Cambridge":      197,
    "Fort Atkinson": 1616,
    "Ixonia":         338,
    "Jefferson":     1457,
    "Johnson Creek": 1090,
    "Lake Mills":     518,
    "Palmyra":         32,
    "Waterloo":       520,
    "Watertown":     2012,
    "Whitewater":      64,   # Koshkonong & Cold Springs contracts only
    "Edgerton":       289,   # Aggregate only; incident-level data unavailable
    "Western Lakes":  263,
}
COUNTY_TOTAL = sum(AUTHORITATIVE_2024.values())  # 7,486

# Jefferson County municipalities (cities, villages, towns)
JEFFERSON_MUNIS = frozenset({
    # Cities
    "watertown", "fort atkinson", "whitewater", "jefferson", "lake mills", "waterloo",
    # Villages
    "johnson creek", "cambridge", "palmyra", "sullivan",
    # Towns wholly or partially in Jefferson Co.
    "aztalan", "concord", "farmington", "hebron", "ixonia", "koshkonong",
    "milford", "oakland", "sumner", "cold spring",
    # Lac La Belle (village; partly in Jefferson)
    "lac la belle",
})

# ZIP codes primarily in Jefferson County
JEFFERSON_ZIPS = frozenset({
    "53036",  # Ixonia
    "53038",  # Johnson Creek
    "53094",  # Watertown (city, Jefferson Co. portion)
    "53137",  # Helenville
    "53156",  # Palmyra
    "53178",  # Sullivan (village + town)
    "53538",  # Fort Atkinson
    "53549",  # Jefferson
    "53551",  # Lake Mills
    "53557",  # Waterloo (Wisconsin)
    "53594",  # Waterloo alt
    "53523",  # Cambridge (Dane/Jefferson border; Cambridge village is in Jefferson)
})

# Non-Jefferson ZIPs that appear in Western Lakes / Edgerton / Whitewater NFIRS
# NOTE: 53523 Cambridge is intentionally NOT here — it's shared Jefferson/Dane.
NON_JEFFERSON_ZIPS = frozenset({
    # Waukesha County
    "53066", "53118", "53089", "53029", "53058", "53069",
    "53027", "53119", "53149", "53153", "53072", "53045",
    # Rock County (Edgerton jurisdiction)
    "53534", "53563", "53511", "53545", "53546", "53548", "53505",
    # Dane County (not Cambridge area)
    "53590", "53575",
    # Walworth County (Whitewater-city is Walworth)
    "53190", "53121", "53184", "53115", "53120", "53147",
    # Dodge County
    "53098", "53039", "53050",
})

# Non-Jefferson municipality substrings to exclude
NON_JEFFERSON_MUNI_SUBSTRINGS = frozenset({
    # Waukesha
    "oconomowoc", "summit", "dousman", "ottawa", "merton", "ashippun",
    "hartford", "delafield", "pewaukee", "colgate", "nashotah", "genesee",
    "eagle", "mukwonago",
    # Rock / Edgerton area
    "edgerton", "milton", "fulton", "albion", "janesville", "beloit",
    "indianford", "busseyville", "newville", "lima", "johnstown",
    "avalon", "delavan", "evansville",
    # Dane
    "stoughton", "madison", "verona",
    # Walworth
    "lake geneva", "whitewater",  # city of Whitewater straddles; filter per-dept
    # Dodge
    "lebanon",
})

# Per-department data source assignments.
# "provider" = Data from Providers/ CSV (pre-filtered by dept)
# "nfirs"    = ISyE Project/Data and Resources/Call Data/*.xlsx (needs geo filter)
# "aggregate_only" = incident-level data unavailable; use AUTHORITATIVE_2024 count only
DEPT_SOURCE = {
    "Cambridge":     "nfirs",            # NFIRS 197 = Megan (fire+EMS combined)
    "Fort Atkinson": "nfirs_investigate",# NFIRS 2,076 vs Megan 1,616 — over by 460; reason TBD
    "Ixonia":        "nfirs",            # NFIRS 338 = Megan exact
    "Jefferson":     "provider",         # 1,457 = Megan exact
    "Johnson Creek": "provider",         # 1,090 = Megan exact
    "Lake Mills":    "provider",         # 518 = Megan exact
    "Palmyra":       "nfirs",            # NFIRS 35 vs Megan 32 (+3, within tolerance)
    "Waterloo":      "provider_ems_only",# Provider 379 = EMS-only subset of Megan's fire+EMS 520
    "Watertown":     "nfirs_filtered",   # NFIRS 2,719 → filter drops Dodge-Co. calls to ~1,446;
                                         #   Megan 2,012 suggests some Dodge-Co. retained; investigate
    "Whitewater":    "provider",         # 64 = Megan exact (Koshkonong/Cold Springs only)
    "Edgerton":      "aggregate_only",   # NFIRS 26 Jefferson vs Megan 289; billing log missing
    "Western Lakes": "nfirs_filtered",   # NFIRS 6,581 → filter to 281 (within 10% of Megan 263)
}


def is_jefferson_city(city) -> bool:
    """Check if an Incident City value belongs to Jefferson County.

    Handles common NFIRS variants: 'City of X', 'Village of X', 'Town of X',
    'X - Town', 'X - Village'. Returns False for known non-Jefferson cities
    even when the name partially matches a Jefferson muni.
    """
    if pd.isna(city):
        return False
    s = str(city).lower().strip()
    # Normalize
    for prefix in ("city of ", "village of ", "town of "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    for suffix in (" - town", " - village", " - city"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = s.replace(",", " ").strip()

    # Exclude any non-Jefferson substring match first
    for bad in NON_JEFFERSON_MUNI_SUBSTRINGS:
        if bad in s:
            return False
    # Then check Jefferson munis
    for muni in JEFFERSON_MUNIS:
        if muni == s:
            return True
        if muni in s.split():
            return True
        if s in muni:  # e.g. 'ix' for 'ixonia' shouldn't happen but safe
            continue
    return False


def normalize_zip(z) -> str | None:
    """Coerce a ZIP value to 5-digit string, or None."""
    if pd.isna(z):
        return None
    s = str(z).replace(".0", "").strip()
    if len(s) >= 5 and s[:5].isdigit():
        return s[:5]
    return None


def is_jefferson_zip(z) -> bool | None:
    """Tri-state: True if Jefferson ZIP, False if known non-Jefferson, None if unknown.

    Use with is_jefferson_city for composite filter:
      keep if city-match=True AND zip-match != False
    """
    z = normalize_zip(z)
    if z is None:
        return None
    if z in NON_JEFFERSON_ZIPS:
        return False
    if z in JEFFERSON_ZIPS:
        return True
    return None


def filter_to_jefferson(
    df: pd.DataFrame,
    city_col: str = "Incident City",
    zip_col: str = "Incident Zip Code",
) -> tuple[pd.DataFrame, dict]:
    """Apply Jefferson-geography filter to an NFIRS-style dataframe.

    Keeps a row if ANY positive signal AND no negative signal:
      * positive signal: city is a Jefferson muni, OR ZIP is a Jefferson ZIP
      * negative signal: ZIP is a known non-Jefferson ZIP (overrides positive)

    Returns (filtered_df, stats_dict).
    """
    if city_col not in df.columns:
        raise KeyError(f"{city_col} not in dataframe columns")
    has_zip = zip_col in df.columns

    city_match = df[city_col].apply(is_jefferson_city)
    if has_zip:
        zip_match = df[zip_col].apply(is_jefferson_zip)  # True / False / None
        positive = city_match | (zip_match == True)
        not_negative = zip_match != False
        keep = positive & not_negative
    else:
        keep = city_match

    kept = df[keep].copy()
    stats = {
        "input_rows":     len(df),
        "city_matches":   int(city_match.sum()),
        "kept_rows":      len(kept),
        "dropped_rows":   len(df) - len(kept),
    }
    return kept, stats


def validate_dept_count(
    dept: str,
    filtered_count: int,
    tolerance: float = 0.10,
) -> dict:
    """Compare a dept's filtered incident count to Megan's authoritative total.

    Returns dict with status: "exact", "within_tolerance", or "out_of_tolerance".
    """
    target = AUTHORITATIVE_2024.get(dept)
    if target is None:
        return {"dept": dept, "status": "no_authoritative", "target": None, "actual": filtered_count}
    delta = filtered_count - target
    pct = abs(delta) / target if target else 1.0
    if delta == 0:
        status = "exact"
    elif pct <= tolerance:
        status = "within_tolerance"
    else:
        status = "out_of_tolerance"
    return {
        "dept": dept,
        "target": target,
        "actual": filtered_count,
        "delta": delta,
        "pct_delta": round(pct * 100, 1),
        "status": status,
    }


if __name__ == "__main__":
    print("jefferson_geo_filter — Jefferson County authoritative 2024 totals")
    print(f"County total: {COUNTY_TOTAL:,}")
    for d, n in sorted(AUTHORITATIVE_2024.items(), key=lambda kv: -kv[1]):
        print(f"  {d:<16s} {n:>5,}  ({DEPT_SOURCE[d]})")
