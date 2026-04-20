"""
Jefferson County EMS — Peak Staffing Erlang-C Analysis (Goal 2 Supplement)
==========================================================================
Adds Erlang-C queueing model layer on top of the existing peak_staffing_analysis.py.
Computes marginal value of +1 staff per department-hour and optimal placement
of 1-5 county-funded EMTs.

Inputs:
  - concurrent_call_detail.csv (Phase 1)
  - concurrent_call_results.csv (Phase 1)

Outputs:
  - peak_staffing_profiles.png           hourly call profiles with SPC control limits
  - peak_staffing_optimal.csv            optimal assignment of 1-5 county EMTs
  - peak_staffing_shift_values.csv       all dept × shift marginal values
  - peak_staffing_marginal_heatmap.png   dept × hour marginal value matrix

Author: ISyE 450 Senior Design Team
Date:   March 2026
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from math import factorial
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Departments that transport (from Phase 1)
EMS_TRANSPORT_DEPTS = [
    "Watertown", "Fort Atkinson", "Whitewater", "Edgerton",
    "Jefferson", "Johnson Creek", "Waterloo", "Ixonia", "Palmyra",
]

AMBULANCE_COUNT = {
    "Watertown": 3, "Fort Atkinson": 3, "Whitewater": 2, "Edgerton": 2,
    "Jefferson": 5, "Johnson Creek": 2, "Waterloo": 2,
    "Ixonia": 1, "Palmyra": 1,
}

# Shifts for optimization: Day (08-20) and Night (20-08)
SHIFTS = {
    "Day (08-20)": list(range(8, 20)),
    "Night (20-08)": list(range(20, 24)) + list(range(0, 8)),
}


# ── Erlang-C ───────────────────────────────────────────────────────────
def erlang_c(lam, mu, c):
    """P(wait) -- probability all c servers busy."""
    if c == 0 or lam <= 0 or mu <= 0:
        return 1.0 if c == 0 and lam > 0 else 0.0
    rho = lam / (c * mu)
    if rho >= 1.0:
        return 1.0
    a = lam / mu
    sum_terms = sum(a**k / factorial(k) for k in range(c))
    last_term = (a**c / factorial(c)) * (1 / (1 - rho))
    p0 = 1.0 / (sum_terms + last_term)
    return ((a**c / factorial(c)) * (1 / (1 - rho))) * p0


# ── Load data ──────────────────────────────────────────────────────────
def load_detail():
    """Load Phase 1 concurrent call detail."""
    path = os.path.join(SCRIPT_DIR, "concurrent_call_detail.csv")
    df = pd.read_csv(path, parse_dates=["Alarm_DT", "Cleared_DT"])
    return df[df["Dept"].isin(EMS_TRANSPORT_DEPTS)]


# ── Hourly demand profiles ─────────────────────────────────────────────
def compute_hourly_profiles(detail):
    """Compute hourly call rate and CV per department."""
    profiles = {}
    for dept in EMS_TRANSPORT_DEPTS:
        dg = detail[detail["Dept"] == dept]
        if dg.empty:
            continue

        # Calls per hour-of-day, total across year
        hourly = dg.groupby("Hour").size()
        hourly = hourly.reindex(range(24), fill_value=0)

        # Compute daily counts per hour for CV
        dg_copy = dg.copy()
        dg_copy["Date"] = dg_copy["Alarm_DT"].dt.date
        daily_hourly = dg_copy.groupby(["Date", "Hour"]).size().unstack(fill_value=0)
        daily_hourly = daily_hourly.reindex(columns=range(24), fill_value=0)

        mean_per_hour = daily_hourly.mean()
        std_per_hour = daily_hourly.std()

        profiles[dept] = {
            "total_per_hour": hourly,
            "mean_daily": mean_per_hour,
            "std_daily": std_per_hour,
            "ucl_2sigma": mean_per_hour + 2 * std_per_hour,
        }

    return profiles


# ── Marginal value of +1 staff ─────────────────────────────────────────
def compute_marginal_value(detail, profiles):
    """
    For each department x hour, compute the reduction in P(wait)
    from adding one more on-duty EMT crew (= +1 ambulance equivalent).
    """
    rows = []

    for dept in EMS_TRANSPORT_DEPTS:
        dg = detail[detail["Dept"] == dept]
        if dg.empty:
            continue

        amb = AMBULANCE_COUNT.get(dept, 1)
        mean_dur_hrs = dg["Duration_Min"].dropna().mean() / 60.0
        if mean_dur_hrs <= 0 or np.isnan(mean_dur_hrs):
            mean_dur_hrs = 0.75
        mu = 1.0 / mean_dur_hrs

        prof = profiles.get(dept)
        if prof is None:
            continue

        for hour in range(24):
            annual_count = prof["total_per_hour"].get(hour, 0)
            lam = annual_count / 365.0  # average calls/hour for this time slot

            if lam <= 0:
                rows.append({
                    "Dept": dept, "Hour": hour, "Ambulances": amb,
                    "Lambda": 0, "P_Wait_Current": 0,
                    "P_Wait_Plus1": 0, "Delta_P_Wait": 0,
                })
                continue

            p_current = erlang_c(lam, mu, amb)
            p_plus1 = erlang_c(lam, mu, amb + 1)
            delta = p_current - p_plus1

            rows.append({
                "Dept": dept, "Hour": hour, "Ambulances": amb,
                "Lambda": round(lam, 4),
                "P_Wait_Current": round(p_current, 6),
                "P_Wait_Plus1": round(p_plus1, 6),
                "Delta_P_Wait": round(delta, 6),
            })

    return pd.DataFrame(rows)


# ── Optimal placement of N county EMTs ─────────────────────────────────
def optimize_emt_placement(marginal_df, max_emts=5):
    """
    Greedy allocation: given N county-funded EMTs (each covers 1 dept x 1 shift),
    assign to maximize total P(wait) reduction weighted by call volume.
    """
    shift_values = []
    for dept in EMS_TRANSPORT_DEPTS:
        dept_data = marginal_df[marginal_df["Dept"] == dept]
        if dept_data.empty:
            continue
        for shift_name, hours in SHIFTS.items():
            subset = dept_data[dept_data["Hour"].isin(hours)]
            # Expected events where P(wait) improvement matters:
            # sum(lambda_h * delta_p_wait_h) across hours in shift
            weighted_val = (subset["Lambda"] * subset["Delta_P_Wait"]).sum()
            avg_delta = subset["Delta_P_Wait"].mean()
            total_calls = subset["Lambda"].sum() * 365  # annual calls in this shift
            shift_values.append({
                "Dept": dept,
                "Shift": shift_name,
                "Marginal_Value": round(weighted_val, 6),
                "Avg_Delta_P": round(avg_delta, 6),
                "Annual_Calls_Shift": round(total_calls, 0),
            })

    sv_df = pd.DataFrame(shift_values).sort_values("Marginal_Value", ascending=False)

    # Greedy: pick top N (one assignment per dept per shift)
    results = []
    for n_emts in range(1, max_emts + 1):
        top = sv_df.head(n_emts)
        total_value = top["Marginal_Value"].sum()
        assignments = []
        for _, row in top.iterrows():
            assignments.append(
                f"{row['Dept']} {row['Shift']} "
                f"(value={row['Marginal_Value']:.4f}, "
                f"~{int(row['Annual_Calls_Shift'])} calls/yr in shift)"
            )
        results.append({
            "N_EMTs": n_emts,
            "Total_Marginal_Value": round(total_value, 4),
            "Assignments": "; ".join(assignments),
        })

    return pd.DataFrame(results), sv_df


# ── Plotting ───────────────────────────────────────────────────────────
def plot_profiles(profiles, detail):
    """Faceted hourly call profiles with 2-sigma control limits."""
    depts = [d for d in EMS_TRANSPORT_DEPTS if d in profiles]
    n = len(depts)
    cols = 3
    nrows = (n + cols - 1) // cols

    fig, axes = plt.subplots(nrows, cols, figsize=(16, 4 * nrows), sharex=True)
    axes_flat = axes.flatten() if n > 1 else [axes]

    for idx, dept in enumerate(depts):
        ax = axes_flat[idx]
        prof = profiles[dept]
        hours = range(24)
        mean = prof["mean_daily"]
        ucl = prof["ucl_2sigma"]

        ax.bar(hours, mean, color="#3498db", alpha=0.7, edgecolor="#2c3e50",
               linewidth=0.5, label="Mean calls/day/hr")
        ax.plot(hours, ucl, "r--", linewidth=1.5, label="UCL (mu+2sigma)")

        # Shade peak hours
        ax.axvspan(8, 20, alpha=0.08, color="orange", label="Peak 08-20")

        ax.set_title(f"{dept} ({AMBULANCE_COUNT.get(dept, '?')} amb)", fontsize=11,
                     fontweight="bold")
        ax.set_xlim(-0.5, 23.5)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xticklabels(["00", "06", "12", "18", "23"])
        if idx == 0:
            ax.legend(fontsize=7, loc="upper right")

    # Hide empty subplots
    for idx in range(n, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle(
        "EMS Hourly Call Volume Profiles with SPC Control Limits\n"
        "Mean daily calls per hour +/- 2sigma | CY2024 NFIRS | Shaded = peak hours",
        fontsize=14, fontweight="bold"
    )
    fig.supxlabel("Hour of Day", fontsize=12)
    fig.supylabel("Calls per Hour (daily avg)", fontsize=12)
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "peak_staffing_profiles.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: peak_staffing_profiles.png")


def plot_marginal_heatmap(marginal_df):
    """Department x hour heatmap of marginal P(wait) reduction."""
    pivot = marginal_df.pivot_table(
        index="Dept", columns="Hour", values="Delta_P_Wait", aggfunc="sum"
    )
    pivot["Total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Total", ascending=True).drop(columns="Total")
    pivot = pivot.reindex(columns=range(24), fill_value=0)

    fig, ax = plt.subplots(figsize=(16, 7))

    vmax = pivot.values.max()
    if vmax > 0:
        im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto",
                       vmin=0, vmax=vmax)
    else:
        im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=9)
    ax.set_yticks(range(len(pivot)))
    ax.set_yticklabels(pivot.index, fontsize=10)

    for i in range(len(pivot)):
        for j in range(24):
            val = pivot.values[i, j]
            if val > 0.0001:
                color = "white" if val > vmax * 0.6 else "black"
                ax.text(j, i, f"{val:.4f}", ha="center", va="center",
                        fontsize=6, color=color)

    ax.set_xlabel("Hour of Day", fontsize=12)
    ax.set_ylabel("Department", fontsize=12)
    ax.set_title(
        "Marginal Value of +1 Ambulance Crew by Department x Hour\n"
        "Delta_P(wait) = P(wait|current) - P(wait|+1 crew) | Higher = more care improvement",
        fontsize=13, fontweight="bold"
    )

    plt.colorbar(im, ax=ax, label="Delta P(wait)", shrink=0.8)

    # Mark peak hours
    ax.axvline(x=7.5, color="orange", linewidth=1, linestyle="--", alpha=0.5)
    ax.axvline(x=19.5, color="orange", linewidth=1, linestyle="--", alpha=0.5)

    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "peak_staffing_marginal_heatmap.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: peak_staffing_marginal_heatmap.png")


# ── Main ───────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS -- PEAK STAFFING ERLANG-C ANALYSIS (GOAL 2)")
    print("=" * 70)

    # Load data
    print("\n>> Loading Phase 1 detail data...")
    detail = load_detail()
    print(f"  {len(detail):,} records across {detail['Dept'].nunique()} departments")

    # Hourly profiles
    print("\n>> Computing hourly demand profiles...")
    profiles = compute_hourly_profiles(detail)
    for dept, prof in profiles.items():
        peak_hr = prof["mean_daily"].idxmax()
        peak_val = prof["mean_daily"].max()
        print(f"  {dept:15s}: peak hour={peak_hr:02d}:00 ({peak_val:.2f} calls/day/hr)")

    # Marginal value
    print("\n>> Computing marginal value of +1 staff (Erlang-C)...")
    marginal = compute_marginal_value(detail, profiles)

    # Top 10
    top10 = marginal.nlargest(10, "Delta_P_Wait")
    print("\n  Top 10 department-hour marginal values:")
    print(top10[["Dept", "Hour", "Lambda", "P_Wait_Current",
                  "P_Wait_Plus1", "Delta_P_Wait"]].to_string(index=False))

    # Optimal EMT placement
    print("\n>> Optimizing county EMT placement (1-5 EMTs)...")
    optimal_df, shift_values = optimize_emt_placement(marginal)
    print()
    print(optimal_df.to_string(index=False))

    # Save
    opt_path = os.path.join(SCRIPT_DIR, "peak_staffing_optimal.csv")
    optimal_df.to_csv(opt_path, index=False)
    print(f"\n  Saved: peak_staffing_optimal.csv")

    shift_path = os.path.join(SCRIPT_DIR, "peak_staffing_shift_values.csv")
    shift_values.to_csv(shift_path, index=False)
    print(f"  Saved: peak_staffing_shift_values.csv")

    # Plots
    print("\n>> Generating plots...")
    plot_profiles(profiles, detail)
    plot_marginal_heatmap(marginal)

    print("\n" + "=" * 70)
    print("PHASE 4 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
