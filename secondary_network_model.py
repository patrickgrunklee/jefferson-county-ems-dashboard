"""
Jefferson County EMS — Secondary Ambulance Network Design
=========================================================
Uses concurrent call (secondary demand) data from Phase 1 as weights
for MCLP / P-Median facility location models. Determines optimal
placement of K=2..5 regional secondary ambulances.

Inputs:
  - concurrent_call_results.csv (Phase 1)
  - isochrone_cache/cand_bg_drive_time_matrix.json (60 candidates × 65 BGs)
  - jefferson_bg_density.geojson (65 Census block groups)
  - Existing station coordinates from facility_location.py

Outputs:
  - secondary_network_solutions.csv
  - secondary_network_map_K{N}.png (for each K)
  - secondary_network_diminishing_returns.png
  - secondary_allocation_table.csv

Author: ISyE 450 Senior Design Team
Date:   March 2026
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Reuse solvers from pareto_facility.py
from pareto_facility import (
    solve_mclp, solve_pmedian_pop, load_candidates, load_bg_demand,
    fetch_cand_bg_matrix, _get_solver
)
from facility_location import STATIONS as EXISTING_STATIONS

# Service area population (from ems_dashboard_app.py)
SERVICE_AREA_POP = {
    "Watertown": 23000, "Fort Atkinson": 16300, "Whitewater": 4296,
    "Jefferson": 7800, "Lake Mills": 8700, "Johnson Creek": 3367,
    "Cambridge": 1650, "Palmyra": 3341, "Ixonia": 5078,
    "Edgerton": 3763, "Waterloo": 4415, "Western Lakes": 2974,
    "Helenville": 1500,
}


# ── Load Phase 1 results ───────────────────────────────────────────────
def load_secondary_demand():
    """Load concurrent call results and compute secondary demand per department."""
    csv = os.path.join(SCRIPT_DIR, "concurrent_call_results.csv")
    df = pd.read_csv(csv)
    return df


# ── Allocate secondary demand to block groups ──────────────────────────
def allocate_demand_to_bgs(secondary_df, bg_demand, pop_weights):
    """
    Distribute each department's secondary call count across block groups
    proportional to BG population within that department's coverage area.

    Approach: for each BG, find the nearest existing station. That BG's share
    of secondary demand = dept's secondary events × (BG pop / dept total pop).
    """
    n_bg = len(bg_demand)
    demand_weights = np.zeros(n_bg, dtype=float)

    # Find nearest existing station for each BG (by haversine)
    from math import radians, sin, cos, sqrt, atan2

    def haversine(lat1, lon1, lat2, lon2):
        R = 3958.8
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1-a))

    # Map station names to their secondary demand
    sec_by_dept = dict(zip(secondary_df["Dept"], secondary_df["Secondary_Events"]))

    # For each BG, find nearest station, assign proportional secondary demand
    for j, bg in enumerate(bg_demand):
        bg_lat, bg_lon = bg["lat"], bg["lon"]
        bg_pop = pop_weights[j]

        # Find nearest existing station
        best_dist = float("inf")
        best_dept = None
        for sta in EXISTING_STATIONS:
            d = haversine(bg_lat, bg_lon, sta["lat"], sta["lon"])
            if d < best_dist:
                best_dist = d
                best_dept = sta["name"]

        if best_dept and best_dept in sec_by_dept:
            dept_pop = SERVICE_AREA_POP.get(best_dept, 1)
            dept_secondary = sec_by_dept[best_dept]
            # Proportional allocation
            demand_weights[j] = dept_secondary * (bg_pop / dept_pop) if dept_pop > 0 else 0

    # Ensure non-negative
    demand_weights = np.maximum(demand_weights, 0)

    print(f"  Total secondary demand allocated to BGs: {demand_weights.sum():.0f} events")
    print(f"  BGs with demand > 0: {(demand_weights > 0).sum()} / {n_bg}")

    return demand_weights


# ── Solve for K secondary stations ─────────────────────────────────────
def solve_secondary_network(time_matrix, candidates, bg_demand, demand_weights,
                            pop_weights, k_range=(2, 3, 4, 5)):
    """Solve MCLP and P-Median with secondary-demand weights for each K."""
    results = []

    for K in k_range:
        print(f"\n  K={K} secondary stations:")

        # MCLP at 10 and 14 min thresholds
        for T in [10, 14]:
            sol = solve_mclp(time_matrix, candidates, bg_demand, K, T, demand_weights)
            if sol:
                sol["objective"] = "MCLP"
                sol["weight_type"] = "secondary_demand"
                # Recompute coverage in terms of demand captured
                open_ids = [i for i, c in enumerate(candidates)
                            if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                                   for s in sol["open_stations"])]
                demand_covered = sum(
                    demand_weights[j] for j in range(len(bg_demand))
                    if min(time_matrix[i, j] for i in open_ids) <= T
                )
                sol["demand_covered"] = round(demand_covered, 1)
                sol["demand_total"] = round(demand_weights.sum(), 1)
                sol["pct_demand_covered"] = round(
                    100 * demand_covered / demand_weights.sum(), 1
                ) if demand_weights.sum() > 0 else 0
                results.append(sol)
                print(f"    MCLP T={T}: {sol['pct_demand_covered']:.1f}% demand covered, "
                      f"avg RT={sol['avg_rt']:.1f} min")

        # P-Median (minimize demand-weighted avg RT)
        sol = solve_pmedian_pop(time_matrix, candidates, bg_demand, K, demand_weights)
        if sol:
            sol["objective"] = "PMed"
            sol["weight_type"] = "secondary_demand"
            # Compute demand covered at various thresholds
            open_ids = [i for i, c in enumerate(candidates)
                        if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                               for s in sol["open_stations"])]
            for T in [10, 14]:
                dcov = sum(
                    demand_weights[j] for j in range(len(bg_demand))
                    if min(time_matrix[i, j] for i in open_ids) <= T
                )
                sol[f"demand_cov_{T}min"] = round(100 * dcov / demand_weights.sum(), 1)
            results.append(sol)
            print(f"    P-Median: avg RT={sol['avg_rt']:.1f} min, "
                  f"14-min cov={sol.get('demand_cov_14min', '?')}%")

    return results


# ── Plotting ───────────────────────────────────────────────────────────
def plot_solution_map(sol, candidates, bg_demand, demand_weights,
                      time_matrix, k, label=""):
    """Map showing secondary station placement with demand-weighted BGs."""
    fig, ax = plt.subplots(figsize=(14, 12))

    open_ids = [i for i, c in enumerate(candidates)
                if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                       for s in sol["open_stations"])]

    # Color BGs by response time from secondary stations
    for j, dp in enumerate(bg_demand):
        best = min(time_matrix[i, j] for i in open_ids) if open_ids else 999
        w = demand_weights[j]
        size = max(6, min(60, w / 3))  # scale by secondary demand
        if w == 0:
            color = "#dddddd"
            alpha = 0.3
        elif best <= 8:
            color = "#2ecc71"
            alpha = 0.7
        elif best <= 10:
            color = "#27ae60"
            alpha = 0.7
        elif best <= 14:
            color = "#f39c12"
            alpha = 0.7
        elif best <= 20:
            color = "#e74c3c"
            alpha = 0.7
        else:
            color = "#888888"
            alpha = 0.5
        ax.scatter(dp["lon"], dp["lat"], s=size, c=color, alpha=alpha,
                   zorder=2, edgecolors="none")

    # Existing stations (gray reference)
    for s in EXISTING_STATIONS:
        ax.scatter(s["lon"], s["lat"], s=60, c="#bbbbbb", marker="s",
                   edgecolors="#666", linewidths=1, zorder=5, alpha=0.6)
        ax.annotate(s["name"], (s["lon"], s["lat"] + 0.005),
                    fontsize=6.5, ha="center", color="#999", zorder=6)

    # Secondary station locations
    zone_labels = _assign_zone_labels(sol["open_stations"])
    for idx, s in enumerate(sol["open_stations"]):
        ax.scatter(s["lon"], s["lat"], s=400, c="#e74c3c", marker="*",
                   edgecolors="#333", linewidths=1.5, zorder=10)
        zone = zone_labels[idx]
        ax.annotate(f"SEC-{idx+1}\n{zone}",
                    (s["lon"], s["lat"] - 0.01),
                    fontsize=8, ha="center", va="top", fontweight="bold",
                    color="#c0392b",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.9),
                    zorder=11)

    # Title
    if sol.get("T") == "PMed" or sol.get("objective") == "PMed":
        pct_14 = sol.get("demand_cov_14min", "?")
        title = (f"Secondary Ambulance Network: {k} Stations (P-Median)\n"
                 f"Demand-weighted avg RT: {sol['avg_rt']:.1f} min | "
                 f"14-min demand coverage: {pct_14}%")
    else:
        T = sol["T"]
        pct = sol.get("pct_demand_covered", sol.get("pct_covered", "?"))
        title = (f"Secondary Ambulance Network: {k} Stations (MCLP T={T}min)\n"
                 f"{pct}% secondary demand within {T} min | "
                 f"Avg RT: {sol['avg_rt']:.1f} min")

    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)

    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#e74c3c",
               markersize=15, label="SECONDARY station (new)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#bbb",
               markersize=10, label="Existing primary station"),
        mpatches.Patch(color="#2ecc71", alpha=0.7, label="≤ 8 min"),
        mpatches.Patch(color="#27ae60", alpha=0.7, label="8-10 min"),
        mpatches.Patch(color="#f39c12", alpha=0.7, label="10-14 min"),
        mpatches.Patch(color="#e74c3c", alpha=0.7, label="14-20 min"),
        mpatches.Patch(color="#dddddd", alpha=0.3, label="No secondary demand"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
    ax.set_aspect("equal")
    plt.tight_layout()

    fname = f"secondary_network_map_K{k}{label}.png"
    fpath = os.path.join(SCRIPT_DIR, fname)
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")
    return fname


def _assign_zone_labels(stations):
    """Assign geographic zone labels (North/Central/South) based on latitude."""
    lats = [s["lat"] for s in stations]
    sorted_lats = sorted(enumerate(lats), key=lambda x: x[1], reverse=True)

    labels = [""] * len(stations)
    n = len(stations)
    if n == 1:
        labels[0] = "County-wide"
    elif n == 2:
        labels[sorted_lats[0][0]] = "North"
        labels[sorted_lats[1][0]] = "South"
    elif n == 3:
        labels[sorted_lats[0][0]] = "North"
        labels[sorted_lats[1][0]] = "Central"
        labels[sorted_lats[2][0]] = "South"
    else:
        for rank, (idx, _) in enumerate(sorted_lats):
            if rank == 0:
                labels[idx] = "North"
            elif rank == n - 1:
                labels[idx] = "South"
            else:
                labels[idx] = f"Central-{rank}"
    return labels


def plot_diminishing_returns(results_summary):
    """Elbow chart: coverage gain per additional secondary station."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Filter to MCLP T=14 results
    mclp14 = results_summary[
        (results_summary["Objective"] == "MCLP") &
        (results_summary["T"] == 14)
    ].sort_values("K")

    pmed = results_summary[
        results_summary["Objective"] == "PMed"
    ].sort_values("K")

    # Panel 1: Coverage vs K
    if not mclp14.empty:
        ax1.plot(mclp14["K"], mclp14["Demand_Pct_Covered"], "o-",
                 color="#e74c3c", linewidth=2, markersize=10, label="MCLP T=14min")
        for _, row in mclp14.iterrows():
            ax1.annotate(f"{row['Demand_Pct_Covered']:.0f}%",
                         (row["K"], row["Demand_Pct_Covered"]),
                         textcoords="offset points", xytext=(8, 8),
                         fontsize=10, fontweight="bold", color="#e74c3c")

    # Also plot T=10
    mclp10 = results_summary[
        (results_summary["Objective"] == "MCLP") &
        (results_summary["T"] == 10)
    ].sort_values("K")
    if not mclp10.empty:
        ax1.plot(mclp10["K"], mclp10["Demand_Pct_Covered"], "s--",
                 color="#f39c12", linewidth=2, markersize=9, label="MCLP T=10min")
        for _, row in mclp10.iterrows():
            ax1.annotate(f"{row['Demand_Pct_Covered']:.0f}%",
                         (row["K"], row["Demand_Pct_Covered"]),
                         textcoords="offset points", xytext=(8, -12),
                         fontsize=9, color="#f39c12")

    ax1.set_xlabel("Number of Secondary Stations (K)", fontsize=12)
    ax1.set_ylabel("Secondary Demand Covered (%)", fontsize=12)
    ax1.set_title("Coverage of Secondary Demand\nvs Number of Stations",
                  fontsize=13, fontweight="bold")
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(range(2, 6))

    # Panel 2: Avg RT vs K
    if not pmed.empty:
        ax2.plot(pmed["K"], pmed["Avg_RT"], "^-",
                 color="#3498db", linewidth=2, markersize=10, label="P-Median")
        for _, row in pmed.iterrows():
            ax2.annotate(f"{row['Avg_RT']:.1f} min",
                         (row["K"], row["Avg_RT"]),
                         textcoords="offset points", xytext=(10, 5),
                         fontsize=10, fontweight="bold", color="#3498db")

    ax2.set_xlabel("Number of Secondary Stations (K)", fontsize=12)
    ax2.set_ylabel("Demand-Weighted Avg Response Time (min)", fontsize=12)
    ax2.set_title("Response Time to Secondary Calls\nvs Number of Stations",
                  fontsize=13, fontweight="bold")
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(range(2, 6))

    fig.suptitle(
        "Jefferson County EMS — Secondary Ambulance Network: Diminishing Returns\n"
        "Demand weights from CY2024 concurrent call analysis",
        fontsize=14, fontweight="bold", y=1.03
    )
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "secondary_network_diminishing_returns.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: secondary_network_diminishing_returns.png")


def build_allocation_table(best_sol, bg_demand, demand_weights, time_matrix, candidates):
    """For the recommended solution, show which secondary station serves which areas."""
    open_ids = [i for i, c in enumerate(candidates)
                if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                       for s in best_sol["open_stations"])]

    zone_labels = _assign_zone_labels(best_sol["open_stations"])
    rows = []
    for j, bg in enumerate(bg_demand):
        if demand_weights[j] == 0:
            continue
        # Find nearest secondary station
        best_time = float("inf")
        best_sec_idx = -1
        for rank, oid in enumerate(open_ids):
            t = time_matrix[oid, j]
            if t < best_time:
                best_time = t
                best_sec_idx = rank

        # Find nearest existing (primary) station
        from math import radians, sin, cos, sqrt, atan2
        def haversine(lat1, lon1, lat2, lon2):
            R = 3958.8
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
            return 2 * R * atan2(sqrt(a), sqrt(1-a))

        nearest_pri = min(EXISTING_STATIONS,
                          key=lambda s: haversine(bg["lat"], bg["lon"], s["lat"], s["lon"]))

        rows.append({
            "BG_Lat": round(bg["lat"], 4),
            "BG_Lon": round(bg["lon"], 4),
            "BG_Pop": bg["population"],
            "Secondary_Demand": round(demand_weights[j], 1),
            "Nearest_Primary": nearest_pri["name"],
            "Assigned_Secondary": f"SEC-{best_sec_idx+1} ({zone_labels[best_sec_idx]})",
            "Secondary_RT_Min": round(best_time, 1),
        })

    alloc = pd.DataFrame(rows).sort_values("Secondary_Demand", ascending=False)
    fpath = os.path.join(SCRIPT_DIR, "secondary_allocation_table.csv")
    alloc.to_csv(fpath, index=False)
    print(f"  Saved: secondary_allocation_table.csv ({len(alloc)} BGs)")
    return alloc


# ── Main ───────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS — SECONDARY AMBULANCE NETWORK DESIGN")
    print("=" * 70)

    # Load data
    print("\n>> Loading Phase 1 secondary demand...")
    sec_df = load_secondary_demand()
    print(sec_df[["Dept", "Secondary_Events", "Pct_Concurrent"]].to_string(index=False))

    print("\n>> Loading facility location data...")
    candidates = load_candidates()
    bg_demand, pop_weights = load_bg_demand()
    print(f"  {len(candidates)} candidates, {len(bg_demand)} block groups")

    print("\n>> Loading drive time matrix...")
    tm = fetch_cand_bg_matrix(candidates, bg_demand)
    if tm is None:
        print("  FATAL: No drive time matrix available")
        return
    print(f"  Matrix: {tm.shape}")

    # Allocate demand to BGs
    print("\n>> Allocating secondary demand to block groups...")
    demand_weights = allocate_demand_to_bgs(sec_df, bg_demand, pop_weights)

    # Solve for K=2..5
    print("\n>> Solving secondary network placement...")
    print("-" * 50)
    all_results = solve_secondary_network(
        tm, candidates, bg_demand, demand_weights, pop_weights,
        k_range=[2, 3, 4, 5]
    )

    # Build summary table
    summary_rows = []
    for r in all_results:
        row = {
            "K": r["K"],
            "Objective": r.get("objective", ""),
            "T": r.get("T", "PMed"),
            "Avg_RT": r.get("avg_rt", np.nan),
            "Max_RT": r.get("max_rt", np.nan),
        }
        if r.get("objective") == "MCLP":
            row["Demand_Pct_Covered"] = r.get("pct_demand_covered", np.nan)
            row["Demand_Covered"] = r.get("demand_covered", np.nan)
        elif r.get("objective") == "PMed":
            row["Demand_Pct_Covered"] = r.get("demand_cov_14min", np.nan)
            row["Demand_Covered"] = np.nan

        row["Stations"] = " | ".join(
            f"({s['lat']:.4f},{s['lon']:.4f})" for s in r["open_stations"]
        )
        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    csv_path = os.path.join(SCRIPT_DIR, "secondary_network_solutions.csv")
    summary_df.to_csv(csv_path, index=False)
    print(f"\n  Saved: secondary_network_solutions.csv")
    print()
    print(summary_df[["K", "Objective", "T", "Avg_RT", "Max_RT",
                       "Demand_Pct_Covered"]].to_string(index=False))

    # Plot maps — pick best per K (MCLP T=14)
    print("\n>> Generating solution maps...")
    for r in all_results:
        if r.get("objective") == "MCLP" and r.get("T") == 14:
            plot_solution_map(r, candidates, bg_demand, demand_weights,
                              tm, r["K"])
        elif r.get("objective") == "PMed":
            plot_solution_map(r, candidates, bg_demand, demand_weights,
                              tm, r["K"], label="_pmed")

    # Diminishing returns
    print("\n>> Plotting diminishing returns...")
    plot_diminishing_returns(summary_df)

    # Allocation table for recommended K (pick K=3 MCLP T=14 if available)
    best = None
    for r in all_results:
        if r.get("K") == 3 and r.get("objective") == "MCLP" and r.get("T") == 14:
            best = r
            break
    if best is None and all_results:
        best = all_results[0]

    if best:
        print("\n>> Building allocation table for recommended solution...")
        build_allocation_table(best, bg_demand, demand_weights, tm, candidates)

    print("\n" + "=" * 70)
    print("PHASE 2 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
