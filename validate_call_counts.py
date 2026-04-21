"""
Validate per-department EMS call counts against Megan's authoritative 2026-04-19 figures.

For each department, loads the appropriate source file per DEPT_SOURCE, applies
the Jefferson geo filter where relevant, and reports:
  - exact match
  - within ±10% tolerance
  - out of tolerance (needs investigation)

Run: python validate_call_counts.py
Exit code 0 if all depts pass (exact or within tolerance), 1 otherwise.
"""
from __future__ import annotations
import os
import sys
import pandas as pd
from jefferson_geo_filter import (
    AUTHORITATIVE_2024,
    DEPT_SOURCE,
    COUNTY_TOTAL,
    filter_to_jefferson,
    validate_dept_count,
)

NFIRS_DIR    = "ISyE Project/Data and Resources/Call Data"
PROVIDER_DIR = "Data from Providers/Data from Providers"

# Provider file names (all in PROVIDER_DIR)
PROVIDER_FILES = {
    "Jefferson":     "Jefferson Fire Dept 2024 EMS Call Data.xlsx",
    "Johnson Creek": "Johnson Creek EMS Data 2024.csv",
    "Lake Mills":    "Lake Mills Ryan Bros EMS Data 2024.csv",
    "Waterloo":      "Waterloo Call Data.xlsx",
    "Whitewater":    "Whitewater Fire Dept Call Data for Koshkonong and Cold Springs ONLY.xlsx",
}

# NFIRS file names (all in NFIRS_DIR) — map to canonical dept name
NFIRS_FILES = {
    "Cambridge":      "Copy of 2024 EMS Workgroup - Cambridge.xlsx",
    "Fort Atkinson":  "Copy of 2024 EMS Workgroup - Fort Atkinson.xlsx",
    "Ixonia":         "Copy of 2024 EMS Workgroup - Ixonia.xlsx",
    "Palmyra":        "Copy of 2024 EMS Workgroup - Palmyra.xlsx",
    "Watertown":      "Copy of 2024 EMS Workgroup - Watertown.xlsx",
    "Western Lakes":  "Copy of 2024 EMS Workgroup - Western Lakes.xlsx",
    "Edgerton":       "Copy of 2024 EMS Workgroup - Edgerton (Lakeside).xlsx",
}


def _count_provider(dept: str) -> int:
    """Load provider CSV/xlsx and return row count (already Jefferson-filtered)."""
    fname = PROVIDER_FILES[dept]
    path = os.path.join(PROVIDER_DIR, fname)
    if not os.path.exists(path):
        print(f"  [!] Missing provider file: {path}")
        return -1
    if path.endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)
    return len(df)


def _count_nfirs(dept: str, apply_filter: bool, ems_only: bool = False) -> int:
    """Load NFIRS xlsx, optionally filter to EMS-only or apply Jefferson geo filter.

    Megan's 2026-04-19 authoritative totals are fire+EMS combined, so by default
    we count ALL incidents, not just EMS. Use ems_only=True for EMS-only analyses
    (incident-level hourly/address breakdowns).
    """
    fname = NFIRS_FILES[dept]
    path = os.path.join(NFIRS_DIR, fname)
    if not os.path.exists(path):
        print(f"  [!] Missing NFIRS file: {path}")
        return -1
    df = pd.read_excel(path)
    type_col = "Incident Type Code Category Description"
    if ems_only and type_col in df.columns:
        df = df[df[type_col].astype(str).str.contains("Rescue and EMS", case=False, na=False)]
    if apply_filter:
        df, stats = filter_to_jefferson(df)
        print(f"  [i] {dept} geo-filter: {stats['input_rows']} -> {stats['kept_rows']}")
    return len(df)


def main() -> int:
    print(f"{'='*60}")
    print(f"Validate call counts vs Megan 2026-04-19 authoritative totals")
    print(f"County target: {COUNTY_TOTAL:,}")
    print(f"{'='*60}")

    results = []
    for dept, source_type in DEPT_SOURCE.items():
        target = AUTHORITATIVE_2024[dept]
        if source_type == "aggregate_only":
            print(f"\n{dept} ({source_type}):")
            print(f"  Target: {target} (aggregate only — no incident-level validation)")
            results.append({"dept": dept, "status": "skipped_aggregate_only",
                            "target": target, "actual": None})
            continue

        print(f"\n{dept} ({source_type}):")
        if source_type in ("provider", "provider_ems_only"):
            n = _count_provider(dept)
        elif source_type == "nfirs":
            n = _count_nfirs(dept, apply_filter=False)  # whole file = Jefferson territory
        elif source_type in ("nfirs_filtered", "nfirs_investigate"):
            n = _count_nfirs(dept, apply_filter=True)
        else:
            print(f"  [!] Unknown source type: {source_type}")
            results.append({"dept": dept, "status": "unknown_source"})
            continue

        if n < 0:
            results.append({"dept": dept, "status": "missing_file", "target": target})
            continue

        r = validate_dept_count(dept, n)
        status_icon = {"exact": "[OK]", "within_tolerance": "[~]", "out_of_tolerance": "[!]"}.get(r["status"], "[?]")
        print(f"  {status_icon} target={r['target']}, actual={r['actual']}, delta={r['delta']:+d} ({r['pct_delta']:+.1f}%)")
        results.append(r)

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")
    exact       = [r for r in results if r.get("status") == "exact"]
    tolerant    = [r for r in results if r.get("status") == "within_tolerance"]
    failing     = [r for r in results if r.get("status") == "out_of_tolerance"]
    missing     = [r for r in results if r.get("status") in ("missing_file", "unknown_source")]
    skipped     = [r for r in results if r.get("status") == "skipped_aggregate_only"]
    print(f"  Exact match:        {len(exact)}")
    print(f"  Within ±10%:        {len(tolerant)}")
    print(f"  OUT OF TOLERANCE:   {len(failing)}")
    print(f"  Skipped (agg only): {len(skipped)}")
    print(f"  Missing / error:    {len(missing)}")

    if failing:
        print(f"\nFAIL — {len(failing)} dept(s) out of tolerance:")
        for r in failing:
            print(f"  - {r['dept']}: target {r['target']}, actual {r['actual']} ({r['pct_delta']:+.1f}%)")
        return 1
    if missing:
        print(f"\nPARTIAL — {len(missing)} dept(s) could not be validated (file missing).")
        return 1
    print(f"\nPASS — all validatable depts match authoritative (exact or within tolerance).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
