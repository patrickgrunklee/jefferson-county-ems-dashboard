"""
Jefferson County EMS -- Baseline Analysis (Current 13 Stations)
===============================================================
Computes the same metrics as the Pareto analysis but for the EXISTING
13 station locations, giving a direct comparison baseline.

Metrics:
  - Pop-weighted avg response time
  - Max response time
  - Population coverage at 8, 10, and 14 minute thresholds

Uses ORS drive times from existing stations to Census block group centroids.

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


# ── Existing stations (from facility_location.py) ────────────────────────
STATIONS = [
    {"id": 0,  "name": "Watertown",     "lat": 43.1861, "lon": -88.7339},
    {"id": 1,  "name": "Fort Atkinson", "lat": 42.9271, "lon": -88.8397},
    {"id": 2,  "name": "Whitewater",    "lat": 42.8325, "lon": -88.7332},
    {"id": 3,  "name": "Edgerton",      "lat": 42.8403, "lon": -89.0629},
    {"id": 4,  "name": "Jefferson",     "lat": 43.0056, "lon": -88.8014},
    {"id": 5,  "name": "Johnson Creek", "lat": 43.0753, "lon": -88.7745},
    {"id": 6,  "name": "Waterloo",      "lat": 43.1886, "lon": -88.9797},
    {"id": 7,  "name": "Lake Mills",    "lat": 43.0781, "lon": -88.9144},
    {"id": 8,  "name": "Ixonia",        "lat": 43.1446, "lon": -88.5970},
    {"id": 9,  "name": "Palmyra",       "lat": 42.8794, "lon": -88.5855},
    {"id": 10, "name": "Cambridge",     "lat": 43.0049, "lon": -89.0224},
    {"id": 11, "name": "Helenville",    "lat": 43.0135, "lon": -88.6998},
    {"id": 12, "name": "Western Lakes", "lat": 43.0110, "lon": -88.5877},
]


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
            "geoid": p.get("GEOID_BG", f"BG_{i}"),
        })
        pops.append(pop)
    return demand, np.array(pops, dtype=float)


# ── Fetch existing station -> BG drive time matrix ───────────────────────
def fetch_existing_bg_matrix(stations, bg_demand):
    cache = os.path.join(SCRIPT_DIR, "isochrone_cache",
                         "existing_bg_drive_time_matrix.json")
    os.makedirs(os.path.dirname(cache), exist_ok=True)

    if os.path.exists(cache):
        print("  Loading cached existing-station-to-BG matrix...")
        with open(cache, "r") as f:
            data = json.load(f)
        return np.array(data["matrix"])

    if not ORS_API_KEY:
        print("  [ERROR] No ORS API key -- cannot fetch matrix")
        return None

    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}

    n_sta = len(stations)
    n_bg = len(bg_demand)
    full_matrix = np.full((n_sta, n_bg), np.inf)

    # 13 stations + up to 37 destinations per batch (50 total limit)
    DST_BATCH = 37

    total_batches = (n_bg + DST_BATCH - 1) // DST_BATCH
    print(f"  Fetching: {n_sta} existing stations x {n_bg} block groups "
          f"(~{total_batches} requests)")

    for dst_s in range(0, n_bg, DST_BATCH):
        dst_e = min(dst_s + DST_BATCH, n_bg)
        batch = bg_demand[dst_s:dst_e]
        n_dst = len(batch)

        locations = [[s["lon"], s["lat"]] for s in stations]
        locations += [[d["lon"], d["lat"]] for d in batch]

        payload = {
            "locations": locations,
            "sources": list(range(n_sta)),
            "destinations": list(range(n_sta, n_sta + n_dst)),
            "metrics": ["duration"], "units": "m",
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code == 200:
                    durations = resp.json()["durations"]
                    for i in range(n_sta):
                        for j in range(n_dst):
                            val = durations[i][j]
                            if val is not None:
                                full_matrix[i, dst_s + j] = val / 60.0
                    pct = dst_e / n_bg * 100
                    print(f"    Batch {dst_s}-{dst_e}: OK ({pct:.0f}%)")
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

    with open(cache, "w") as f:
        json.dump({"matrix": full_matrix.tolist()}, f)
    print(f"  Cached to {cache}")
    return full_matrix


# ── Analysis ─────────────────────────────────────────────────────────────
def compute_baseline(tm, stations, bg_demand, pop_weights):
    n_sta = len(stations)
    n_bg = len(bg_demand)
    total_pop = pop_weights.sum()

    # For each BG, find nearest station and its response time
    nearest_station = []
    nearest_time = []
    for j in range(n_bg):
        times = [tm[i, j] for i in range(n_sta)]
        best_i = int(np.argmin(times))
        best_t = times[best_i]
        nearest_station.append(best_i)
        nearest_time.append(best_t)

    nearest_time = np.array(nearest_time)

    # Pop-weighted avg response time
    avg_rt = np.sum(pop_weights * nearest_time) / total_pop

    # Max response time
    max_rt = np.max(nearest_time)

    # Coverage at thresholds
    coverages = {}
    for T in [8, 10, 14, 20]:
        covered_pop = sum(pop_weights[j] for j in range(n_bg)
                          if nearest_time[j] <= T)
        coverages[T] = round(100 * covered_pop / total_pop, 1)

    # Per-station assignment info
    station_assignments = {}
    for j in range(n_bg):
        sid = nearest_station[j]
        if sid not in station_assignments:
            station_assignments[sid] = {"pop": 0, "bgs": 0, "times": []}
        station_assignments[sid]["pop"] += int(pop_weights[j])
        station_assignments[sid]["bgs"] += 1
        station_assignments[sid]["times"].append(nearest_time[j])

    return {
        "K": n_sta,
        "avg_rt": round(avg_rt, 2),
        "max_rt": round(max_rt, 2),
        "coverages": coverages,
        "pop_total": int(total_pop),
        "nearest_station": nearest_station,
        "nearest_time": nearest_time,
        "station_assignments": station_assignments,
    }


# ── Plotting ─────────────────────────────────────────────────────────────
def plot_baseline(baseline, stations, bg_demand, pop_weights, nearest_time):
    fig, ax = plt.subplots(figsize=(14, 12))

    # Color BGs by response time
    for j, dp in enumerate(bg_demand):
        t = nearest_time[j]
        pop = pop_weights[j]
        size = max(8, min(50, pop / 80))
        if t <= 8:
            color = "#2ecc71"
        elif t <= 10:
            color = "#27ae60"
        elif t <= 14:
            color = "#f39c12"
        elif t <= 20:
            color = "#e74c3c"
        else:
            color = "#888888"
        ax.scatter(dp["lon"], dp["lat"], s=size, c=color, alpha=0.6,
                   zorder=2, edgecolors="none")

    # Plot existing stations
    for s in stations:
        ax.scatter(s["lon"], s["lat"], s=200, c="#3498db", marker="s",
                   edgecolors="#333", linewidths=1.5, zorder=10)
        ax.annotate(s["name"], (s["lon"], s["lat"] + 0.006),
                    fontsize=8, ha="center", fontweight="bold",
                    color="#2c3e50", zorder=11,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              alpha=0.8))

    # Title with metrics
    cov_str = " | ".join(f"{T}min: {baseline['coverages'][T]}%"
                         for T in [8, 10, 14])
    ax.set_title(
        f"BASELINE: Current {baseline['K']} Existing Stations\n"
        f"Pop-weighted avg RT: {baseline['avg_rt']:.1f} min | "
        f"Max: {baseline['max_rt']:.1f} min\n"
        f"Coverage: {cov_str}",
        fontsize=12, fontweight="bold",
    )

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)

    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#3498db",
               markersize=12, label="Existing station"),
        mpatches.Patch(color="#2ecc71", alpha=0.6, label="<= 8 min"),
        mpatches.Patch(color="#27ae60", alpha=0.6, label="8-10 min"),
        mpatches.Patch(color="#f39c12", alpha=0.6, label="10-14 min"),
        mpatches.Patch(color="#e74c3c", alpha=0.6, label="14-20 min"),
        mpatches.Patch(color="#888888", alpha=0.6, label="> 20 min"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
    ax.set_aspect("equal")
    plt.tight_layout()

    fpath = os.path.join(SCRIPT_DIR, "baseline_existing_stations.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: baseline_existing_stations.png")


def plot_comparison_table(baseline, pareto_csv):
    """Create a visual comparison table: baseline vs Pareto optima."""
    df = pd.read_csv(pareto_csv)

    # Build comparison rows
    rows = []

    # Baseline row
    rows.append({
        "Config": f"BASELINE ({baseline['K']} existing)",
        "K": baseline["K"],
        "Avg RT (min)": baseline["avg_rt"],
        "Max RT (min)": baseline["max_rt"],
        "8-min Cov (%)": baseline["coverages"][8],
        "10-min Cov (%)": baseline["coverages"][10],
        "14-min Cov (%)": baseline["coverages"][14],
    })

    # P-Median rows
    for _, r in df[df["T"] == "PMed"].iterrows():
        rows.append({
            "Config": f"Optimal K={int(r['K'])} (min RT)",
            "K": int(r["K"]),
            "Avg RT (min)": r["avg_rt"],
            "Max RT (min)": r["max_rt"],
            "8-min Cov (%)": r.get("cov_8min", ""),
            "10-min Cov (%)": r.get("cov_10min", ""),
            "14-min Cov (%)": r.get("cov_14min", ""),
        })

    # Best MCLP at T=14 for each K
    mclp14 = df[df["T"] == 14].copy()
    for _, r in mclp14.iterrows():
        rows.append({
            "Config": f"Optimal K={int(r['K'])} (max cov@14m)",
            "K": int(r["K"]),
            "Avg RT (min)": r["avg_rt"],
            "Max RT (min)": r["max_rt"],
            "8-min Cov (%)": "",
            "10-min Cov (%)": "",
            "14-min Cov (%)": r["pct_covered"],
        })

    comp_df = pd.DataFrame(rows)

    # Plot as a figure table
    fig, ax = plt.subplots(figsize=(16, max(4, len(rows) * 0.5 + 2)))
    ax.axis("off")

    table = ax.table(
        cellText=comp_df.values,
        colLabels=comp_df.columns,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.8)

    # Style header
    for j in range(len(comp_df.columns)):
        table[0, j].set_facecolor("#2c3e50")
        table[0, j].set_text_props(color="white", fontweight="bold")

    # Highlight baseline row
    for j in range(len(comp_df.columns)):
        table[1, j].set_facecolor("#e8f4f8")
        table[1, j].set_text_props(fontweight="bold")

    fig.suptitle("Jefferson County EMS: Baseline vs Optimized Station Placement",
                 fontsize=14, fontweight="bold", y=0.98)

    fpath = os.path.join(SCRIPT_DIR, "baseline_comparison.png")
    plt.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: baseline_comparison.png")


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("JEFFERSON COUNTY EMS -- BASELINE ANALYSIS (CURRENT STATIONS)")
    print("=" * 70)

    # Load BG data
    print("\n>> Loading block group demand data...")
    bg_demand, pop_weights = load_bg_demand()
    print(f"  {len(bg_demand)} block groups, {int(pop_weights.sum()):,} total pop")

    # Get drive times
    print("\n>> Drive time matrix (existing stations -> block groups)...")
    tm = fetch_existing_bg_matrix(STATIONS, bg_demand)
    if tm is None:
        print("  Cannot proceed without drive times.")
        return
    print(f"  Matrix shape: {tm.shape}")

    # Compute baseline metrics
    print("\n>> Computing baseline metrics...")
    baseline = compute_baseline(tm, STATIONS, bg_demand, pop_weights)

    print(f"\n{'='*60}")
    print(f"BASELINE RESULTS: {baseline['K']} Existing Stations")
    print(f"{'='*60}")
    print(f"  Pop-weighted avg response time: {baseline['avg_rt']:.1f} min")
    print(f"  Max response time:              {baseline['max_rt']:.1f} min")
    print(f"  Population covered:")
    for T in [8, 10, 14, 20]:
        cov = baseline["coverages"][T]
        pop_cov = int(pop_weights.sum() * cov / 100)
        print(f"    Within {T:2d} min: {cov:5.1f}% ({pop_cov:,} of {int(pop_weights.sum()):,})")

    # Per-station breakdown
    print(f"\n  Per-station served population:")
    for sid, info in sorted(baseline["station_assignments"].items(),
                             key=lambda x: -x[1]["pop"]):
        s = STATIONS[sid]
        avg_t = np.mean(info["times"])
        max_t = np.max(info["times"])
        print(f"    {s['name']:15s}: {info['pop']:6,} pop ({info['bgs']} BGs), "
              f"avg {avg_t:.1f} min, max {max_t:.1f} min")

    # Plot
    print("\n>> Generating baseline map...")
    plot_baseline(baseline, STATIONS, bg_demand, pop_weights,
                  baseline["nearest_time"])

    # Comparison with Pareto results
    pareto_csv = os.path.join(SCRIPT_DIR, "pareto_results.csv")
    if os.path.exists(pareto_csv):
        print("\n>> Generating comparison table (baseline vs Pareto)...")
        plot_comparison_table(baseline, pareto_csv)
    else:
        print("\n  [SKIP] pareto_results.csv not found -- no comparison table")

    print("\nDone!")


if __name__ == "__main__":
    main()
