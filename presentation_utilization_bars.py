"""Presentation chart — per-muni stacked bar: primary vs secondary call share.

Each muni's bar sums to 100% of its EMS calls, split into:
  - Primary (blue):   calls handled without overflow
  - Secondary (orange): calls that required a second ambulance

Source:
  AUTH_EMS_CALLS (Megan 2026-04-19, authoritative CY2024 totals)
  Pct_Concurrent from concurrent_call_results_jeffco.csv
  For depts with missing Jefferson-area incident data (Edgerton, Western Lakes,
  Whitewater, Palmyra), Pct_Concurrent is imputed from the county median of
  depts with credible data and flagged with a hatch pattern.

Outputs:
  presentation_utilization_stacked.png   (single chart, primary use)
  presentation_utilization_bars.png      (alias — same content, replaces prior)
"""
from pathlib import Path
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
df = pd.DataFrame(rows).sort_values("Secondary_Pct", ascending=True) \
                       .reset_index(drop=True)

cty_total = df["Total"].sum()
cty_primary = df["Primary_Calls"].sum()
cty_secondary = df["Secondary_Calls"].sum()
cty_pri_pct = cty_primary / cty_total * 100
cty_sec_pct = cty_secondary / cty_total * 100

# ============================ Plot ============================
plt.rcParams.update({"font.size": 11, "axes.titleweight": "bold"})

fig, ax = plt.subplots(figsize=(13, 7))

y = range(len(df))
prim_bars = ax.barh(y, df["Primary_Pct"], color=PRIMARY_COLOR,
                    edgecolor="white", label="Primary (first-out)")
sec_bars = ax.barh(y, df["Secondary_Pct"], left=df["Primary_Pct"],
                   color=SECONDARY_COLOR, edgecolor="white",
                   label="Secondary (overflow)")
for b, imp in zip(sec_bars, df["Imputed"]):
    if imp:
        b.set_hatch("//")

# Inside-bar labels: primary %
for i, row in df.iterrows():
    ax.text(row["Primary_Pct"] / 2, i,
            f"{row['Primary_Pct']:.1f}%\n({row['Primary_Calls']:,})",
            ha="center", va="center", color="white",
            fontsize=9.5, fontweight="bold")
    # Secondary % label (inside if bar wide enough, else outside)
    if row["Secondary_Pct"] >= 6:
        ax.text(row["Primary_Pct"] + row["Secondary_Pct"] / 2, i,
                f"{row['Secondary_Pct']:.1f}%\n({row['Secondary_Calls']:,})",
                ha="center", va="center", color="white",
                fontsize=9.5, fontweight="bold")
    else:
        tag = " †" if row["Imputed"] else ""
        ax.text(100.5, i,
                f"{row['Secondary_Pct']:.1f}%  ({row['Secondary_Calls']:,} sec){tag}",
                va="center", fontsize=9.5, color="#333")

ax.set_yticks(list(y))
ax.set_yticklabels([f"{r['Dept']}  —  {r['Total']:,} calls, {r['Amb']} amb"
                    for _, r in df.iterrows()])
ax.set_xlim(0, 118)
ax.set_xlabel("Share of EMS calls (%)")
ax.set_title(
    "Jefferson County EMS — Primary vs Secondary Ambulance Utilization by Municipality\n"
    f"CY2024 — County: {cty_primary:,} primary ({cty_pri_pct:.1f}%), "
    f"{cty_secondary:,} secondary ({cty_sec_pct:.1f}%)  of {cty_total:,} calls",
    loc="left")
ax.legend(loc="lower right", frameon=False)
ax.grid(axis="x", alpha=0.3)
ax.spines[["top", "right"]].set_visible(False)
ax.axvline(100, color="#888", linewidth=0.8, linestyle="--", alpha=0.6)

fig.text(0.01, -0.015,
         "† Hatched: Jefferson-area incident-level data unavailable; "
         "secondary rate imputed from county median of depts with data "
         f"({median_pct:.1f}%).",
         fontsize=8, color="#444")

fig.tight_layout()
fig.savefig(ROOT / "presentation_utilization_stacked.png", dpi=200,
            bbox_inches="tight")
fig.savefig(ROOT / "presentation_utilization_bars.png", dpi=200,
            bbox_inches="tight")
print("Saved:")
print("  presentation_utilization_stacked.png")
print("  presentation_utilization_bars.png  (same content)")

print(f"\nCounty: {cty_total:,} calls -> "
      f"{cty_primary:,} primary ({cty_pri_pct:.1f}%), "
      f"{cty_secondary:,} secondary ({cty_sec_pct:.1f}%)")
print("\n--- Per-muni breakdown ---")
print(df[["Dept", "Amb", "Total", "Primary_Pct", "Secondary_Pct",
          "Primary_Calls", "Secondary_Calls", "Imputed"]].to_string(index=False))
