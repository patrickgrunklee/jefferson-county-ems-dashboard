"""
Jefferson County EMS -- Multi-Objective Pareto Facility Location
================================================================
Three objectives (Pareto front):
  1. Minimize number of stations  (K = 7..10)
  2. Minimize pop-weighted avg response time  (P-Median)
  3. Maximize population covered within T minutes  (MCLP, T = 8/10/14)

Uses moveable candidate grid (60 sites) + Census block group centroids
(65 demand points, population-weighted).

Outputs:
  - pareto_frontier.png  -- 3-axis Pareto summary
  - pareto_K{k}_T{t}.png -- per-solution maps
  - pareto_results.csv   -- full results table

Author: ISyE 450 Senior Design Team
Date: March 2026
"""

import numpy as np
import pandas as pd
import json
import os
import time
import requests
import warnings
warnings.filterwarnings("ignore")

import pulp
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load .env ────────────────────────────────────────────────────────────
def _load_env():
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")


def _get_solver(time_limit=120):
    try:
        solver = pulp.GUROBI_CMD(msg=0, timeLimit=time_limit)
        if solver.available():
            return solver
    except Exception:
        pass
    return pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit)


# ── Load candidate grid from existing cache ──────────────────────────────
def load_candidates():
    cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                         "candidate_drive_time_matrix.json")
    with open(cache, "r") as f:
        data = json.load(f)
    return data["candidates"]


# ── Load block group demand ──────────────────────────────────────────────
def load_bg_demand():
    bg_path = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")
    with open(bg_path, "r") as f:
        gj = json.load(f)

    demand, pops = [], []
    for i, feat in enumerate(gj["features"]):
        p = feat["properties"]
        pop = p.get("P1_001N", 0)
        if pop <= 0:
            continue
        demand.append({
            "id": i,
            "lat": float(p["INTPTLAT"]),
            "lon": float(p["INTPTLON"]),
            "population": pop,
        })
        pops.append(pop)
    return demand, np.array(pops, dtype=float)


# ── Fetch candidate-to-BG drive time matrix ──────────────────────────────
def fetch_cand_bg_matrix(candidates, bg_demand):
    cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                         "cand_bg_drive_time_matrix.json")
    os.makedirs(os.path.dirname(cache), exist_ok=True)

    if os.path.exists(cache):
        print("  Loading cached candidate-to-BG matrix...")
        with open(cache, "r") as f:
            data = json.load(f)
        return np.array(data["matrix"])

    if not ORS_API_KEY:
        print("  [SKIP] No ORS API key")
        return None

    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}

    n_cand = len(candidates)
    n_bg = len(bg_demand)

    # 60 candidates + 65 BG = 125 locations > 50 limit
    # Must batch: 10 sources x 40 destinations per request
    SRC_BATCH = 10
    DST_BATCH = 40

    full_matrix = np.full((n_cand, n_bg), np.inf)
    total_req = ((n_cand + SRC_BATCH - 1) // SRC_BATCH) * \
                ((n_bg + DST_BATCH - 1) // DST_BATCH)
    print(f"  Fetching: {n_cand} candidates x {n_bg} block groups (~{total_req} requests)")

    req = 0
    for src_s in range(0, n_cand, SRC_BATCH):
        src_e = min(src_s + SRC_BATCH, n_cand)
        src_batch = candidates[src_s:src_e]
        n_src = len(src_batch)

        for dst_s in range(0, n_bg, DST_BATCH):
            dst_e = min(dst_s + DST_BATCH, n_bg)
            dst_batch = bg_demand[dst_s:dst_e]
            n_dst = len(dst_batch)

            locations = [[c["lon"], c["lat"]] for c in src_batch]
            locations += [[d["lon"], d["lat"]] for d in dst_batch]

            payload = {
                "locations": locations,
                "sources": list(range(n_src)),
                "destinations": list(range(n_src, n_src + n_dst)),
                "metrics": ["duration"], "units": "m",
            }

            for attempt in range(3):
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=60)
                    if resp.status_code == 200:
                        durations = resp.json()["durations"]
                        for i in range(n_src):
                            for j in range(n_dst):
                                val = durations[i][j]
                                if val is not None:
                                    full_matrix[src_s + i, dst_s + j] = val / 60.0
                        break
                    elif resp.status_code == 429:
                        print(f"    Rate limited -- waiting 60s (attempt {attempt+1})")
                        time.sleep(60)
                    else:
                        print(f"    FAILED: {resp.status_code} {resp.text[:100]}")
                        break
                except Exception as e:
                    print(f"    Error: {e}")
                    break
            time.sleep(2)
            req += 1
            if req % 5 == 0:
                print(f"    Progress: {req}/{total_req}")

    with open(cache, "w") as f:
        json.dump({"matrix": full_matrix.tolist()}, f)
    print(f"  Cached to {cache}")
    return full_matrix


# ── Solvers ──────────────────────────────────────────────────────────────
def solve_mclp(time_matrix, candidates, bg_demand, p, max_time, pop_weights):
    n_cand = len(candidates)
    n_bg = len(bg_demand)
    total_pop = pop_weights.sum()

    prob = pulp.LpProblem("MCLP", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_cand)]
    z = [pulp.LpVariable(f"z_{j}", cat="Binary") for j in range(n_bg)]

    prob += pulp.lpSum([pop_weights[j] * z[j] for j in range(n_bg)])
    prob += pulp.lpSum(x) == p

    for j in range(n_bg):
        covering = [i for i in range(n_cand) if time_matrix[i, j] <= max_time]
        if covering:
            prob += z[j] <= pulp.lpSum([x[i] for i in covering])
        else:
            prob += z[j] == 0

    solver = _get_solver(time_limit=120)
    prob.solve(solver)

    if prob.status != 1:
        return None

    open_cands = [candidates[i] for i in range(n_cand) if x[i].varValue > 0.5]
    covered = [j for j in range(n_bg) if z[j].varValue > 0.5]
    pop_covered = sum(pop_weights[j] for j in covered)

    # Also compute avg response time for the covered population
    open_ids = [i for i in range(n_cand) if x[i].varValue > 0.5]
    total_wt = 0
    max_rt = 0
    for j in range(n_bg):
        best = min(time_matrix[i, j] for i in open_ids)
        total_wt += pop_weights[j] * best
        max_rt = max(max_rt, best)
    avg_rt = total_wt / total_pop

    return {
        "K": p,
        "T": max_time,
        "open_stations": open_cands,
        "pop_covered": int(pop_covered),
        "pop_total": int(total_pop),
        "pct_covered": round(100 * pop_covered / total_pop, 1),
        "avg_rt": round(avg_rt, 2),
        "max_rt": round(max_rt, 2),
    }


def solve_pmedian_pop(time_matrix, candidates, bg_demand, p, pop_weights):
    n_cand = len(candidates)
    n_bg = len(bg_demand)

    prob = pulp.LpProblem("PMed_Pop", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_cand)]
    y = [[pulp.LpVariable(f"y_{i}_{j}", lowBound=0, upBound=1)
          for j in range(n_bg)] for i in range(n_cand)]

    prob += pulp.lpSum([
        pop_weights[j] * time_matrix[i, j] * y[i][j]
        for i in range(n_cand) for j in range(n_bg)
        if time_matrix[i, j] < np.inf
    ])
    prob += pulp.lpSum(x) == p

    for j in range(n_bg):
        reachable = [i for i in range(n_cand) if time_matrix[i, j] < np.inf]
        if reachable:
            prob += pulp.lpSum([y[i][j] for i in reachable]) == 1

    for i in range(n_cand):
        for j in range(n_bg):
            if time_matrix[i, j] < np.inf:
                prob += y[i][j] <= x[i]

    solver = _get_solver(time_limit=300)
    prob.solve(solver)

    if prob.status != 1:
        return None

    open_cands = [candidates[i] for i in range(n_cand) if x[i].varValue > 0.5]
    open_ids = [i for i in range(n_cand) if x[i].varValue > 0.5]

    total_wt = 0
    max_rt = 0
    for j in range(n_bg):
        best = min(time_matrix[i, j] for i in open_ids)
        total_wt += pop_weights[j] * best
        max_rt = max(max_rt, best)
    avg_rt = total_wt / pop_weights.sum()

    # Coverage at multiple thresholds
    coverages = {}
    for t in [8, 10, 14]:
        cov = sum(pop_weights[j] for j in range(n_bg)
                  if min(time_matrix[i, j] for i in open_ids) <= t)
        coverages[t] = round(100 * cov / pop_weights.sum(), 1)

    return {
        "K": p,
        "T": "PMed",
        "open_stations": open_cands,
        "avg_rt": round(avg_rt, 2),
        "max_rt": round(max_rt, 2),
        "coverages": coverages,
        "pop_total": int(pop_weights.sum()),
    }


# ── Plotting ─────────────────────────────────────────────────────────────
# Load existing stations for reference overlay
from facility_location import STATIONS as EXISTING_STATIONS


def plot_solution(sol, candidates, bg_demand, pop_weights, time_matrix,
                  label_suffix=""):
    """Plot a single Pareto solution map, same style as facility_moveable_K*.png."""
    fig, ax = plt.subplots(figsize=(14, 12))

    open_ids = [i for i, c in enumerate(candidates)
                if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                       for s in sol["open_stations"])]

    # Color block groups by response time from open stations
    for j, dp in enumerate(bg_demand):
        best = min(time_matrix[i, j] for i in open_ids) if open_ids else 999
        pop = pop_weights[j]
        size = max(8, min(50, pop / 80))  # scale by population
        if best <= 8:
            color = "#2ecc71"
        elif best <= 10:
            color = "#27ae60"
        elif best <= 14:
            color = "#f39c12"
        elif best <= 20:
            color = "#e74c3c"
        else:
            color = "#888888"
        ax.scatter(dp["lon"], dp["lat"], s=size, c=color, alpha=0.6, zorder=2,
                   edgecolors="none")

    # Existing stations (gray reference)
    for s in EXISTING_STATIONS:
        ax.scatter(s["lon"], s["lat"], s=80, c="#bbbbbb", marker="s",
                   edgecolors="#666", linewidths=1.5, zorder=5, alpha=0.7)
        ax.annotate(s["name"], (s["lon"], s["lat"] + 0.006),
                    fontsize=7, ha="center", color="#999", zorder=6)

    # Optimal NEW locations
    for s in sol["open_stations"]:
        ax.scatter(s["lon"], s["lat"], s=300, c="#e74c3c", marker="*",
                   edgecolors="#333", linewidths=1.5, zorder=10)
        ax.annotate(f"NEW ({s['lat']:.3f}, {s['lon']:.3f})",
                    (s["lon"], s["lat"] - 0.008),
                    fontsize=7, ha="center", va="top", fontweight="bold",
                    color="#c0392b",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              alpha=0.9),
                    zorder=11)

    # Title
    K = sol["K"]
    if sol["T"] == "PMed":
        title_line2 = (f"Pop-weighted avg RT: {sol['avg_rt']:.1f} min | "
                       f"Max: {sol['max_rt']:.1f} min")
        cov_str = " | ".join(f"{t}min: {sol['coverages'][t]}%"
                             for t in [8, 10, 14])
        title_line3 = f"Coverage: {cov_str}"
    else:
        T = sol["T"]
        title_line2 = (f"{sol['pct_covered']}% pop within {T} min "
                       f"({sol['pop_covered']:,} / {sol['pop_total']:,})")
        title_line3 = (f"Avg RT: {sol['avg_rt']:.1f} min | "
                       f"Max: {sol['max_rt']:.1f} min")

    ax.set_title(
        f"Moveable Facility: {K} Optimal Stations{label_suffix}\n"
        f"{title_line2}\n{title_line3}",
        fontsize=12, fontweight="bold",
    )

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)

    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#e74c3c",
               markersize=15, label="OPTIMAL new location"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#bbb",
               markersize=10, label="Existing station (reference)"),
        mpatches.Patch(color="#2ecc71", alpha=0.6, label="<= 8 min"),
        mpatches.Patch(color="#27ae60", alpha=0.6, label="8-10 min"),
        mpatches.Patch(color="#f39c12", alpha=0.6, label="10-14 min"),
        mpatches.Patch(color="#e74c3c", alpha=0.6, label="14-20 min"),
        mpatches.Patch(color="#888888", alpha=0.6, label="> 20 min"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
    ax.set_aspect("equal")
    plt.tight_layout()

    if sol["T"] == "PMed":
        fname = f"pareto_K{K}_PMed.png"
    else:
        fname = f"pareto_K{K}_T{sol['T']}.png"
    fpath = os.path.join(SCRIPT_DIR, fname)
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")
    return fname


def _load_baseline():
    """Load baseline metrics from cached existing-station-to-BG matrix."""
    cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                         "existing_bg_drive_time_matrix.json")
    if not os.path.exists(cache):
        return None

    bg_path = os.path.join(SCRIPT_DIR, "jefferson_bg_density.geojson")
    with open(bg_path, "r") as f:
        gj = json.load(f)

    pops = []
    for feat in gj["features"]:
        p = feat["properties"].get("P1_001N", 0)
        if p > 0:
            pops.append(p)
    pop_weights = np.array(pops, dtype=float)
    total_pop = pop_weights.sum()

    with open(cache, "r") as f:
        tm = np.array(json.load(f)["matrix"])

    n_sta, n_bg = tm.shape
    nearest_time = np.array([min(tm[i, j] for i in range(n_sta)) for j in range(n_bg)])
    avg_rt = float(np.sum(pop_weights * nearest_time) / total_pop)
    max_rt = float(np.max(nearest_time))

    coverages = {}
    for T in [8, 10, 14, 20]:
        cov_pop = sum(pop_weights[j] for j in range(n_bg) if nearest_time[j] <= T)
        coverages[T] = round(100 * cov_pop / total_pop, 1)

    return {
        "K": n_sta, "avg_rt": round(avg_rt, 2), "max_rt": round(max_rt, 2),
        "coverages": coverages, "pop_total": int(total_pop),
    }


def plot_pareto_frontier(results_df):
    """Plot the Pareto frontier: 3-panel layout showing all 4 optimization
    scenarios (MCLP T=8/10/14 + P-Median) with baseline overlay."""
    # Normalize T column -- CSV reads mixed int/str as all strings
    results_df = results_df.copy()
    results_df["T"] = results_df["T"].apply(
        lambda x: int(x) if str(x).isdigit() else x)

    baseline = _load_baseline()

    colors = {8: "#e74c3c", 10: "#f39c12", 14: "#2ecc71", "PMed": "#3498db"}
    markers = {8: "o", 10: "s", 14: "D", "PMed": "^"}
    BL_COLOR = "#8e44ad"

    fig, axes = plt.subplots(1, 3, figsize=(22, 7))

    # ── Panel 1: K vs Avg RT (all 4 scenarios) ──────────────────────────
    ax = axes[0]
    for t in [8, 10, 14, "PMed"]:
        subset = results_df[results_df["T"] == t].sort_values("K")
        if not subset.empty:
            lbl = f"MCLP T={t} min" if t != "PMed" else "P-Median (min avg RT)"
            ax.plot(subset["K"], subset["avg_rt"], marker=markers[t],
                    color=colors[t], linewidth=2, markersize=9, zorder=5,
                    label=lbl, alpha=0.85)
    if baseline:
        ax.scatter([baseline["K"]], [baseline["avg_rt"]], c=BL_COLOR,
                   marker="*", s=350, zorder=10, edgecolors="#333", linewidths=1,
                   label=f"BASELINE ({baseline['K']} stations)")
        ax.annotate(f"{baseline['avg_rt']:.1f} min",
                    (baseline["K"], baseline["avg_rt"]),
                    textcoords="offset points", xytext=(-50, 12),
                    fontsize=9, fontweight="bold", color=BL_COLOR,
                    arrowprops=dict(arrowstyle="->", color=BL_COLOR, lw=1.5))
        ax.axhline(y=baseline["avg_rt"], color=BL_COLOR, linewidth=1.5,
                    linestyle="--", alpha=0.4)
    ax.set_xlabel("Number of Stations (K)", fontsize=12)
    ax.set_ylabel("Pop-Weighted Avg Response Time (min)", fontsize=12)
    ax.set_title("Stations vs Response Time", fontsize=13, fontweight="bold")
    ax.legend(fontsize=8.5, loc="upper right")
    ax.grid(True, alpha=0.3)

    # ── Panel 2: K vs Pop Coverage (MCLP at each threshold + baseline) ──
    ax = axes[1]
    for t in [8, 10, 14]:
        subset = results_df[results_df["T"] == t].sort_values("K")
        if not subset.empty:
            ax.plot(subset["K"], subset["pct_covered"], marker=markers[t],
                    color=colors[t], linewidth=2, markersize=9, zorder=5,
                    label=f"MCLP T={t} min", alpha=0.85)
            for _, row in subset.iterrows():
                ax.annotate(f"{row['pct_covered']:.0f}%",
                            (row["K"], row["pct_covered"]),
                            textcoords="offset points", xytext=(7, 4),
                            fontsize=7.5, color=colors[t], fontweight="bold")
    if baseline:
        for T in [8, 10, 14]:
            cov = baseline["coverages"][T]
            ax.scatter([baseline["K"]], [cov], c=BL_COLOR, marker="*",
                       s=250, zorder=10, edgecolors="#333", linewidths=1)
            ax.axhline(y=cov, color=colors[T], linewidth=1,
                        linestyle=":", alpha=0.35)
            ax.annotate(f"BL {cov:.0f}%",
                        (baseline["K"], cov),
                        textcoords="offset points", xytext=(-50, -2),
                        fontsize=8, fontweight="bold", color=BL_COLOR)
        ax.scatter([], [], c=BL_COLOR, marker="*", s=150,
                   edgecolors="#333", linewidths=1,
                   label=f"BASELINE ({baseline['K']} stations)")
    ax.set_xlabel("Number of Stations (K)", fontsize=12)
    ax.set_ylabel("Population Covered (%)", fontsize=12)
    ax.set_title("Stations vs Population Coverage", fontsize=13, fontweight="bold")
    ax.legend(fontsize=8.5, loc="lower right")
    ax.set_ylim(45, 100)
    ax.grid(True, alpha=0.3)

    # ── Panel 3: Avg RT vs 14-min Coverage (the actual Pareto front) ────
    ax = axes[2]
    # Plot each K as a point, connected by lines for each scenario
    for t in [8, 10, 14]:
        subset = results_df[results_df["T"] == t].sort_values("K")
        if not subset.empty:
            ax.plot(subset["avg_rt"], subset["pct_covered"], marker=markers[t],
                    color=colors[t], linewidth=1.5, markersize=9, zorder=5,
                    label=f"MCLP T={t} min", alpha=0.85)
            for _, row in subset.iterrows():
                ax.annotate(f"K={int(row['K'])}",
                            (row["avg_rt"], row["pct_covered"]),
                            textcoords="offset points", xytext=(8, 4),
                            fontsize=7.5, color=colors[t])
    if baseline:
        for T in [8, 10, 14]:
            cov = baseline["coverages"][T]
            ax.scatter([baseline["avg_rt"]], [cov], c=BL_COLOR, marker="*",
                       s=300, zorder=10, edgecolors="#333", linewidths=1)
            ax.annotate(f"BL @{T}m",
                        (baseline["avg_rt"], cov),
                        textcoords="offset points", xytext=(-45, -5),
                        fontsize=8, fontweight="bold", color=BL_COLOR)
        ax.axvline(x=baseline["avg_rt"], color=BL_COLOR, linewidth=1.5,
                    linestyle="--", alpha=0.4)
        ax.scatter([], [], c=BL_COLOR, marker="*", s=150,
                   edgecolors="#333", linewidths=1,
                   label=f"BASELINE ({baseline['avg_rt']} min)")
    ax.set_xlabel("Pop-Weighted Avg Response Time (min)", fontsize=12)
    ax.set_ylabel("Population Covered (%)", fontsize=12)
    ax.set_title("Tradeoff: Response Time vs Coverage", fontsize=13,
                 fontweight="bold")
    ax.legend(fontsize=8.5, loc="lower left")
    ax.set_ylim(45, 100)
    ax.grid(True, alpha=0.3)

    fig.suptitle("Jefferson County EMS -- Multi-Objective Pareto Analysis\n"
                 "Moveable Facilities | Census Block Group Population | ORS Drive Times",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "pareto_frontier.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: pareto_frontier.png")


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS -- MULTI-OBJECTIVE PARETO ANALYSIS")
    print("=" * 70)

    # Load data
    print("\n>> Loading data...")
    candidates = load_candidates()
    bg_demand, pop_weights = load_bg_demand()
    print(f"  {len(candidates)} candidate sites, {len(bg_demand)} block groups "
          f"({int(pop_weights.sum()):,} pop)")

    # Get drive time matrix
    print("\n>> Drive time matrix (candidates -> block groups)...")
    tm = fetch_cand_bg_matrix(candidates, bg_demand)
    if tm is None:
        print("  Cannot proceed without drive times.")
        return
    print(f"  Matrix shape: {tm.shape}")

    # Solve
    K_RANGE = [7, 8, 9, 10, 11, 12, 13]
    T_RANGE = [8, 10, 14]

    all_results = []

    # MCLP at each threshold
    print("\n>> Solving MCLP (maximize population covered)...")
    print("-" * 50)
    for K in K_RANGE:
        for T in T_RANGE:
            sol = solve_mclp(tm, candidates, bg_demand, K, T, pop_weights)
            if sol:
                stations_str = ", ".join(
                    f"({s['lat']:.3f},{s['lon']:.3f})"
                    for s in sol["open_stations"])
                print(f"  K={K}, T={T:2d}: {sol['pct_covered']:5.1f}% covered, "
                      f"avg RT={sol['avg_rt']:.1f} min")
                all_results.append(sol)

                # Plot individual map
                plot_solution(sol, candidates, bg_demand, pop_weights, tm)

    # P-Median (min avg RT)
    print("\n>> Solving P-Median (minimize pop-weighted avg RT)...")
    print("-" * 50)
    for K in K_RANGE:
        sol = solve_pmedian_pop(tm, candidates, bg_demand, K, pop_weights)
        if sol:
            print(f"  K={K}: avg RT={sol['avg_rt']:.1f} min, "
                  f"max={sol['max_rt']:.1f} min")
            cov_str = " | ".join(f"{t}min={sol['coverages'][t]}%"
                                 for t in [8, 10, 14])
            print(f"    Coverage: {cov_str}")
            all_results.append(sol)
            plot_solution(sol, candidates, bg_demand, pop_weights, tm)

    # Build results dataframe
    rows = []
    for r in all_results:
        row = {
            "K": r["K"],
            "T": r["T"],
            "avg_rt": r["avg_rt"],
            "max_rt": r["max_rt"],
            "pop_total": r["pop_total"],
        }
        if r["T"] != "PMed":
            row["pct_covered"] = r["pct_covered"]
            row["pop_covered"] = r["pop_covered"]
        else:
            row["pct_covered"] = None
            row["pop_covered"] = None
            for t in [8, 10, 14]:
                row[f"cov_{t}min"] = r["coverages"][t]

        row["stations"] = " | ".join(
            f"({s['lat']:.4f},{s['lon']:.4f})"
            for s in r["open_stations"])
        rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = os.path.join(SCRIPT_DIR, "pareto_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n  Saved: pareto_results.csv")

    # Plot Pareto frontier
    print("\n>> Plotting Pareto frontier...")
    plot_pareto_frontier(df)

    print("\nDone!")


if __name__ == "__main__":
    main()
