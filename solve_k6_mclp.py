"""Solve MCLP at K=6 for the total-demand variant — fills the gap in
secondary_network_solutions_totaldemand.csv (which only has K=2..5 MCLP and K=6 PMed)."""
import sys
sys.argv.append("--total-demand")

import os
import numpy as np
import pandas as pd

from secondary_network_model import (
    load_candidates, load_bg_demand, fetch_cand_bg_matrix,
    allocate_total_demand_to_bgs,
)
from pareto_facility import solve_mclp, solve_pmedian_pop

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

print("Loading candidates / BGs / drive-time matrix...")
candidates = load_candidates()
bg_demand, pop_weights = load_bg_demand()
tm = fetch_cand_bg_matrix(candidates, bg_demand)
print(f"  candidates={len(candidates)}  BGs={len(bg_demand)}  matrix={tm.shape}")

print("Allocating total-demand weights to BGs...")
demand_weights = allocate_total_demand_to_bgs(bg_demand, pop_weights)

K = 6
print(f"\nSolving MCLP at K={K}, T=14 (total-demand)...")
sol14 = solve_mclp(tm, candidates, bg_demand, K, 14, demand_weights)
print(f"\nSolving MCLP at K={K}, T=10 (total-demand)...")
sol10 = solve_mclp(tm, candidates, bg_demand, K, 10, demand_weights)

def summarize(sol, T):
    if not sol:
        return None
    open_ids = [i for i, c in enumerate(candidates)
                if any(c["lat"] == s["lat"] and c["lon"] == s["lon"]
                       for s in sol["open_stations"])]
    demand_covered = sum(
        demand_weights[j] for j in range(len(bg_demand))
        if min(tm[i, j] for i in open_ids) <= T
    )
    pct = 100 * demand_covered / demand_weights.sum() if demand_weights.sum() > 0 else 0
    stations = " | ".join(f"({s['lat']:.4f},{s['lon']:.4f})" for s in sol["open_stations"])
    return {
        "K": K,
        "Objective": "MCLP",
        "T": T,
        "Avg_RT": round(sol["avg_rt"], 2),
        "Max_RT": round(sol["max_rt"], 2),
        "Demand_Pct_Covered": round(pct, 1),
        "Demand_Covered": round(demand_covered, 1),
        "Stations": stations,
    }

results = []
for sol, T in [(sol10, 10), (sol14, 14)]:
    s = summarize(sol, T)
    if s:
        results.append(s)
        print(f"\nMCLP K=6 T={T}: avg RT={s['Avg_RT']} | max RT={s['Max_RT']} | "
              f"coverage={s['Demand_Pct_Covered']}%")
        print(f"  Stations: {s['Stations']}")

# Append to existing CSV
csv_path = os.path.join(SCRIPT_DIR, "secondary_network_solutions_totaldemand.csv")
existing = pd.read_csv(csv_path)
existing = existing[~((existing["K"] == 6) & (existing["Objective"] == "MCLP"))]
new_df = pd.concat([existing, pd.DataFrame(results)], ignore_index=True)
new_df = new_df.sort_values(by=["K", "Objective", "T"], kind="stable")
new_df.to_csv(csv_path, index=False)
print(f"\nUpdated {csv_path}")
print(new_df.to_string(index=False))
