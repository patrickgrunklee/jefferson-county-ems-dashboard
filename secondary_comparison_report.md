# Secondary Ambulance Pipeline — Original vs Jefferson-Only Comparison

**Date**: 2026-04-19
**Context**: Megan (project sponsor) emailed corrected 2024 call volumes on 2026-04-19. The original NFIRS-based pipeline includes all cross-county calls (Western Lakes' 5,403 Waukesha-Co. EMS responses, Edgerton/Lakeside's 2,009 Rock-Co. responses, Whitewater's 1,447 Walworth-Co. responses). The `_jeffco` variant filters every call geographically to Jefferson County only.

Both pipelines remain on disk. Originals are **not overwritten** — they're preserved for reference/comparison.

---

## 1. Concurrent Call Analysis — `concurrent_call_results.csv` vs `concurrent_call_results_jeffco.csv`

### Before-after summary

| Dept | Orig EMS Calls | Jeffco EMS Calls | Change | Orig Secondary | Jeffco Secondary | Change |
|---|---:|---:|---:|---:|---:|---:|
| Edgerton | 2,035 | 25 | **-2,010** | 768 | 0 | **-768** |
| Watertown | 1,947 | 992 | -955 | 656 | 193 | -463 |
| Whitewater | 1,448 | 1 | **-1,447** | 421 | 0 | **-421** |
| Fort Atkinson | 1,621 | 1,605 | -16 | 209 | 201 | -8 |
| Waterloo | 403 | 399 | -4 | 93 | 91 | -2 |
| Johnson Creek | 454 | 454 | 0 | 59 | 59 | 0 |
| Ixonia | 260 | 172 | -88 | 32 | 21 | -11 |
| Cambridge | 64 | 64 | 0 | 4 | 4 | 0 |
| Jefferson | 91 | 91 | 0 | 2 | 2 | 0 |
| Palmyra | 32 | 32 | 0 | 0 | 0 | 0 |
| **Total** | **8,355** | **3,835** | **-4,520 (-54%)** | **2,244** | **571** | **-1,673 (-75%)** |

### Key takeaways

1. **Edgerton's secondary demand drops from 768 to 0.** The 768 figure was driven entirely by calls in Rock County (Edgerton/Milton); there are no Jefferson-area concurrent events in NFIRS. Edgerton's real Jefferson-area activity (289 per Megan) is in a billing/transport log we don't have — see `DATA_QUALITY_NOTES`.

2. **Whitewater's secondary demand drops from 421 to 0.** Same story — all concurrent events were in Walworth County. Whitewater's Jefferson contracts (Koshkonong/Cold Springs, 64 calls per Megan) don't generate multi-call overlaps.

3. **Watertown's concurrent rate falls from 33.7% to 19.5%.** Cross-county calls into Dodge (ZIP 53098) were inflating the concurrent count. Still the highest volume dept after Fort Atkinson.

4. **Fort Atkinson and Waterloo are nearly unchanged** — both are Jefferson-centric and only a handful of mutual-aid responses cross into Rock County.

5. **All-busy events** (calls arriving while every ambulance is already on scene) correctly reflect in both: Cambridge 64 (0 ambulances, so every call is "all busy"), Ixonia 21 (1 ambulance overwhelmed 12% of the time), Waterloo 12.

---

## 2. Secondary Network Solutions — K=3 MCLP, T=14 (recommended placement)

| | Original (all-district) | Jeffco (Jefferson-only) | Change |
|---|---|---|---|
| Avg Response Time | 10.64 min | 11.01 min | +0.37 min |
| Max Response Time | 30.8 min | 42.96 min | +12.2 min |
| Demand Coverage | 86.1% | 84.0% | -2.1 pp |

### Interpretation

- The **Jefferson-only demand distribution is more geographically scattered** (covers Fort Atkinson, Waterloo, Watertown, Ixonia pockets). When the model can't "cheat" by placing stations near the dense Oconomowoc / Edgerton clusters outside Jefferson, the max RT rises because outlying Jefferson BGs need coverage too.
- **K=3 is still the elbow point** — both pipelines show diminishing returns past K=3. The recommendation stands.
- **Station placements differ slightly**: Jefferson-only recommendation is entirely within county; original had one candidate near the Waukesha border that's now not useful.

See `secondary_network_map_K3_jeffco.png` vs `secondary_network_map_K3.png` for visual comparison.

---

## 3. Staffing & Cost Scenarios — Identical

Staffing scenarios (A: all 24/7, B: peak-only, C: hybrid) are driven by K (station count) and the Peterson cost model. Neither changes with the Jeffco filter, so `secondary_staffing_scenarios.csv` and `_jeffco.csv` are identical:

| Scenario | Total Operating | Net Cost | Total FTE |
|---|---:|---:|---:|
| A: All 3 stations 24/7 ALS | $2,150,454 | $751,854 | 21.6 |
| B: All 3 stations peak-only (08-20) | $1,547,636 | $638,546 | 14.4 |
| C: Hybrid (1 × 24/7 + 2 × peak) | $1,748,575 | $676,315 | 16.8 |

---

## 4. Erlang-C P(wait) — Materially Unchanged

P(wait) for most depts was <1% in both pipelines (low demand relative to ambulance count). The only depts with P(wait) ≥ 1% are:
- **Ixonia**: 2.3% all-day, 3.0% peak (both pipelines) — 1 ambulance, ~172 Jefferson-area calls/yr
- **Waterloo**: 0.2%/0.5% original → 0.2%/0.5% Jeffco — effectively unchanged
- **Palmyra**: 0.6%/0.8% original → same

---

## 5. Recommendations

1. **Use `_jeffco` outputs for dashboard/presentation going forward.** They reflect the correct Jefferson County scope per Megan's 2026-04-19 corrections.
2. **Keep originals on disk** — they document the pre-correction state and are useful to show the Working Group *why* the numbers changed.
3. **Edgerton note**: Zero secondary demand in Jeffco pipeline is an artifact of the NFIRS/billing-log gap, NOT a claim that Edgerton has no Jefferson-area concurrent events. Document this caveat wherever Edgerton secondary demand is shown.
4. **Whitewater note**: Effectively excluded from secondary-ambulance analysis. Its 64 Jefferson-contract calls are sparse and unlikely to drive placement decisions.

---

## 6. File Index

### Original (pre-correction, preserved)
- `concurrent_call_results.csv`, `concurrent_call_detail.csv`, `erlang_c_results.csv`
- `secondary_network_solutions.csv`, `secondary_allocation_table.csv`
- `secondary_staffing_scenarios.csv`, `fte_transition.csv`
- PNG outputs: `concurrent_hourly_heatmap.png`, `secondary_demand_by_dept.png`,
  `secondary_network_map_K{2,3,4,5}{_pmed}.png`,
  `secondary_network_diminishing_returns.png`, `staffing_waterfall.png`,
  `current_vs_consolidated.png`

### Jefferson-only (current, use for analysis)
- `concurrent_call_results_jeffco.csv`, `concurrent_call_detail_jeffco.csv`, `erlang_c_results_jeffco.csv`
- `secondary_network_solutions_jeffco.csv`, `secondary_allocation_table_jeffco.csv`
- `secondary_staffing_scenarios_jeffco.csv`, `fte_transition_jeffco.csv`
- PNG outputs: same names with `_jeffco` suffix

### Regenerate command
```bash
python concurrent_call_analysis.py --jeffco
python secondary_network_model.py --jeffco
python secondary_staffing_model.py --jeffco
```
