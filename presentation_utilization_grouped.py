"""Presentation chart — per-muni GROUPED bar: primary vs secondary side-by-side.

Unlike presentation_utilization_bars.py (stacked to 100%), this version puts
the primary and secondary bars next to each other for each muni so absolute
call volume is directly comparable across departments.

Bars are plotted as call counts (not %), with % labels above each bar.

Source:
  AUTH_EMS_CALLS (Megan 2026-04-19, authoritative CY2024 totals)
  Pct_Concurrent from concurrent_call_results_jeffco.csv
  Imputed (county-median) flag hatched for depts without Jeff-area incident data.

Output:
  presentation_utilization_grouped.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent

AUTH_EMS_CALLS = {
    "Cambridge":      197,
    "Fort Atkinson":  1616,
    "Ixonia":         338,
    "Jefferson":      1457,
    "Johnson Creek":  1090,
    "Lake Mills":     518,
    "Palmyra":        32,
    "Waterloo":       520,
    "Watertown":      2012,
    "Whitewater":     64,
    "Edgerton":       289,
    "Western Lakes":  263,
}
FLEET = {
    "Cambridge":      0, "Edgerton":       1, "Fort Atkinson":  3,
    "Ixonia":         1, "Jefferson":      3, "Johnson Creek":  2,
    "Lake Mills":     0, "Palmyra":        1, "Waterloo":       2,
    "Watertown":      3, "Western Lakes":  2, "Whitewater":     1,
}

PRIMARY_COLOR = "#2C7FB8"
SECONDARY_COLOR = "#D95F0E"

jeffco = pd.read_csv(ROOT / "concurrent_call_results_jeffco.csv")
pct_conc = dict(zip(jeffco["Dept"], jeffco["Pct_Concurrent"]))
CREDIBLE = {"Fort Atkinson", "Watertown", "Waterloo", "Johnson Creek",
            "Ixonia", "Jefferson"}
median_pct = pd.Series([pct_conc[d] for d in CREDIBLE
                        if d in pct_conc]).median()

rows = []
for dept, calls in AUTH_EMS_CALLS.items():
    amb = FLEET[dept]
    if amb == 0:
        continue
    raw = pct_conc.get(dept)
    imputed = dept not in CREDIBLE or raw is None or pd.isna(raw)
    pct_sec = median_pct if imputed else raw
    pct_pri = 100 - pct_sec
    rows.append({
        "Dept": dept, "Total": calls, "Amb": amb,
        "Primary_Pct": pct_pri, "Secondary_Pct": pct_sec,
        "Primary_Calls": round(calls * pct_pri / 100),
        "Secondary_Calls": round(calls * pct_sec / 100),
        "Imputed": imputed,
    })
df = pd.DataFrame(rows).sort_values("Total", ascending=False).reset_index(drop=True)

cty_total = df["Total"].sum()
cty_primary = df["Primary_Calls"].sum()
cty_secondary = df["Secondary_Calls"].sum()
cty_pri_pct = cty_primary / cty_total * 100
cty_sec_pct = cty_secondary / cty_total * 100

# ============================ Plot ============================
plt.rcParams.update({"font.size": 11, "axes.titleweight": "bold"})

fig, ax = plt.subplots(figsize=(14, 7.5))

x = np.arange(len(df))
width = 0.4

prim_bars = ax.bar(x - width/2, df["Primary_Calls"], width,
                   color=PRIMARY_COLOR, edgecolor="white",
                   label="Primary (first-out)")
sec_bars = ax.bar(x + width/2, df["Secondary_Calls"], width,
                  color=SECONDARY_COLOR, edgecolor="white",
                  label="Secondary (overflow)")
for b, imp in zip(sec_bars, df["Imputed"]):
    if imp:
        b.set_hatch("//")

# Labels above each bar: count + %
ymax = df["Primary_Calls"].max()
label_pad = ymax * 0.015
for i, row in df.iterrows():
    ax.text(i - width/2, row["Primary_Calls"] + label_pad,
            f"{row['Primary_Calls']:,}\n({row['Primary_Pct']:.1f}%)",
            ha="center", va="bottom", fontsize=8.5, color="#222")
    tag = "†" if row["Imputed"] else ""
    ax.text(i + width/2, row["Secondary_Calls"] + label_pad,
            f"{row['Secondary_Calls']:,}{tag}\n({row['Secondary_Pct']:.1f}%)",
            ha="center", va="bottom", fontsize=8.5, color="#222")

ax.set_xticks(x)
ax.set_xticklabels([f"{r['Dept']}\n{r['Total']:,} calls · {r['Amb']} amb"
                    for _, r in df.iterrows()], fontsize=9.5)
ax.set_ylabel("EMS call count (CY2024)")
ax.set_ylim(0, ymax * 1.18)
ax.set_title(
    "Jefferson County EMS — Primary vs Secondary Call Volume by Municipality (Grouped)\n"
    f"CY2024 — County: {cty_primary:,} primary ({cty_pri_pct:.1f}%), "
    f"{cty_secondary:,} secondary ({cty_sec_pct:.1f}%)  of {cty_total:,} calls",
    loc="left")
ax.legend(loc="upper right", frameon=False)
ax.grid(axis="y", alpha=0.3)
ax.spines[["top", "right"]].set_visible(False)

fig.text(0.01, -0.02,
         "† Hatched: Jefferson-area incident-level data unavailable; "
         "secondary rate imputed from county median of depts with data "
         f"({median_pct:.1f}%).    "
         "Source: AUTH_EMS_CALLS (Megan 2026-04-19) + concurrent_call_results_jeffco.csv.",
         fontsize=8, color="#444")

fig.tight_layout()
fig.savefig(ROOT / "presentation_utilization_grouped.png", dpi=200,
            bbox_inches="tight")
print("Saved: presentation_utilization_grouped.png")

print(f"\nCounty: {cty_total:,} calls -> "
      f"{cty_primary:,} primary ({cty_pri_pct:.1f}%), "
      f"{cty_secondary:,} secondary ({cty_sec_pct:.1f}%)")
print("\n--- Per-muni breakdown ---")
print(df[["Dept", "Amb", "Total", "Primary_Pct", "Secondary_Pct",
          "Primary_Calls", "Secondary_Calls", "Imputed"]].to_string(index=False))
