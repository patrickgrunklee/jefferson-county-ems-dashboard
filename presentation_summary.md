# Jefferson County EMS — Final Presentation Summary

**ISyE 450 Senior Design Team | March 2026**
**Prepared for: EMS Working Group (fire chiefs + county officials)**

---

## Framing: This Is About Better Care for Citizens

Every finding below answers one question: *How can Jefferson County improve EMS response quality for its residents?* Financial data diagnoses the structural problem; the solution is measured in faster response times, better coverage, and improved patient outcomes.

---

## Goal 1: Regional Secondary Ambulance Network

### The Problem: Secondary Demand

When a department's primary ambulance is already on a call, the next patient waits. This is **secondary demand** — and it happens more often than expected.

| Department | EMS Calls (2024) | Secondary Events | % Concurrent | Max Simultaneous | All-Busy Events |
|-----------|-----------------|-----------------|-------------|-----------------|----------------|
| **Edgerton** | 2,035 | **768** | **37.7%** | 8 | 161 (7.9%) |
| **Watertown** | 1,947 | **656** | **33.7%** | 8 | 16 (0.8%) |
| **Whitewater** | 1,448 | **421** | **29.1%** | 6 | 63 (4.4%) |
| Fort Atkinson | 1,621 | 209 | 12.9% | 3 | 1 (0.1%) |
| Waterloo | 403 | 93 | 23.1% | 3 | 12 (3.0%) |
| Johnson Creek | 454 | 59 | 13.0% | 4 | 7 (1.5%) |
| Ixonia | 260 | 32 | 12.3% | 3 | **32 (12.3%)** |

**Key finding**: Edgerton has 161 instances/year where ALL ambulances were busy. Ixonia (single ambulance) has 12.3% all-busy rate. These are moments when patients wait or rely on mutual aid from farther away.

*Source: CY2024 NFIRS call data, 14 departments. "Concurrent" = another call active in same dept during [alarm, cleared] window.*
*Charts: `concurrent_hourly_heatmap.png`, `secondary_demand_by_dept.png`*

### When Secondary Demand Peaks

- **Peak hours: 09:00–19:00** — concurrent call rate is ~2.9× the overnight rate
- **Peak days**: Wednesday and Thursday slightly higher, but day-of-week effect is modest
- County-wide: **2,244 secondary demand events/year** (county total across all depts with data)

### Erlang-C Queueing Model

| Department | Ambulances | P(wait) All-Day | P(wait) Peak Hrs | Interpretation |
|-----------|-----------|----------------|-----------------|---------------|
| Edgerton | 2 | 2.5% | **4.5%** | Significant peak-hour congestion |
| Whitewater | 2 | 0.9% | 1.4% | Moderate congestion |
| Ixonia | 1 | **3.5%** | **4.7%** | Single-unit vulnerability |
| Waterloo | 2 | 0.2% | 0.5% | Manageable with longer call durations |
| Watertown | 3 | 0.07% | 0.15% | Well-served by 3 units |

*Source: `erlang_c_results.csv`. P(wait) = probability all ambulances busy when a new call arrives.*

### Recommended Network: 3 Regional Secondary Stations

The MCLP optimization (60 candidate sites, 65 Census block groups, ORS road-network drive times) finds that **3 secondary stations** cover **86.1% of secondary demand within 14 minutes**. This is the "elbow" — going from 2→3 stations gains +19 percentage points, while 3→4 gains only +5.

| Secondary Stations | 10-min Coverage | 14-min Coverage | Avg RT | Max RT |
|-------------------|----------------|----------------|--------|--------|
| K=2 | 57.0% | 66.8% | 11.7 min | 33.1 min |
| **K=3** | **72.1%** | **86.1%** | **10.6 min** | 30.8 min |
| K=4 | 80.0% | 91.2% | 9.7 min | 30.8 min |
| K=5 | 85.1% | 96.0% | 7.9 min | 30.8 min |

**Three zones**: North (Watertown area), Central (Jefferson/Fort Atkinson corridor), South (Whitewater/Edgerton area).

*Source: `secondary_network_solutions.csv`. Weights = secondary demand (not population). Solver: PuLP MCLP + P-Median.*
*Charts: `secondary_network_map_K3.png`, `secondary_network_diminishing_returns.png`*

---

## Goal 1 Continued: Staffing & Cost

### Peterson Cost Model Baseline

Chief Peterson's 24/7 ALS crew cost projection:
- **Operating cost per station**: $716,818/year (3 paramedics + 3 EMT-A, OT, benefits, insurance, supplies)
- **Revenue per station**: $466,200/year (700 calls × $666 avg collected)
- **Net cost per station**: $250,618/year

### Three Scenarios for K=3 Stations

| Scenario | Coverage | Operating | Revenue | **Net Cost** | FTE |
|---------|---------|----------|---------|-------------|-----|
| A: All 3 × 24/7 ALS | 24/7 | $2,150,454 | $1,398,600 | **$751,854** | 21.6 |
| B: All 3 × peak-only (08-20) | 12hr/day | $1,547,636 | $909,090 | **$638,546** | 14.4 |
| **C: Hybrid** (1 × 24/7 + 2 × peak) | Mixed | $1,748,575 | $1,072,260 | **$676,315** | 16.8 |

### Current Distributed Overhead (Diagnostic)

Departments currently spend an estimated **$2.36M/year** on secondary ambulance capacity (backup unit maintenance, PT on-call coverage, extra insurance for 2nd+ ambulances). This is distributed across 7 departments, each maintaining their own surplus capacity independently.

A consolidated 3-station regional network achieves **86% secondary demand coverage at $676K–$752K net** — a fraction of the distributed overhead. This is not a "savings" recommendation; it is a **diagnostic finding** about structural inefficiency in how secondary capacity is currently provided.

*Source: `secondary_staffing_scenarios.csv`, `current_vs_consolidated.png`*

### FTE Transition

- Current: ~51 PT positions partially dedicated to secondary ambulance coverage across 7 depts
- Proposed (Hybrid): 16.8 FTE (professional, dedicated, trained secondary crews)
- This converts inconsistent part-time on-call coverage into reliable full-time response capacity

*Source: `fte_transition.csv`*

---

## Goal 2: Peak Staffing Investigation

### Where County-Funded EMTs Provide the Most Care Improvement

Using Erlang-C queueing theory, we computed the **marginal value of adding one ambulance crew** at each department during each shift. The metric: reduction in P(wait) — the probability a patient has to wait because all units are busy.

### Optimal EMT Assignment (Greedy Allocation)

| # County EMTs | Best Assignments | Total Marginal Value |
|--------------|-----------------|---------------------|
| 1 | **Edgerton Day (08-20)** | 0.1508 |
| 2 | + Whitewater Day (08-20) | 0.1820 |
| 3 | + Edgerton Night (20-08) | 0.2075 |
| 4 | + Ixonia Day (08-20) | 0.2293 |
| 5 | + Whitewater Night (20-08) | 0.2397 |

**Key insight**: The first county EMT at **Edgerton daytime** provides **6× more care improvement** than the second-best option. Edgerton's 2 ambulances handle 5.6 calls/day with 61-minute average duration — the highest utilization in the county.

**Ixonia appears at #4** despite low call volume because its single ambulance means ANY concurrent call creates a coverage gap. Adding one crew eliminates that vulnerability entirely.

*Source: `peak_staffing_optimal.csv`, `peak_staffing_shift_values.csv`*

### Hourly Demand Pattern

- **Peak hours: 09:00–19:00** across all departments
- **Peak-to-valley ratio**: ~3.5× county-wide
- **Busiest departments by peak-hour volume**: Edgerton (0.36 calls/hr peak), Watertown (0.35), Fort Atkinson (0.28)
- Best single 8-hour shift window: **08:00–16:00** (captures 43% of all EMS calls)
- Best 12-hour window: **07:00–19:00** (captures 65% of all EMS calls)

*Source: `peak_staffing_profiles.png`, `peak_staffing_marginal_heatmap.png`*

### SPC Control Limits

Departments flagged with demand exceeding μ+2σ control limits:
- **Edgerton** 09:00–15:00: consistently above upper control limit
- **Watertown** 09:00–12:00: near-UCL demand
- **Whitewater** 10:00–14:00: regular UCL exceedances

These are the hours where current staffing is most strained and additional resources provide the most patient-care benefit.

---

## ISyE Tools Applied

| Tool | Application |
|------|------------|
| **Queueing Theory (Erlang-C)** | P(wait) computation for each dept × hour; marginal value of +1 staff |
| **Integer Programming (MCLP/P-Median)** | Optimal secondary station placement from 60 candidate sites |
| **Pareto Analysis** | Multi-objective tradeoff: coverage vs cost vs number of stations |
| **SPC Control Charts** | Flag department-hours exceeding 2σ above mean call volume |
| **Sweep-Line Algorithm** | O(n log n) concurrent call detection across 13,800+ EMS records |
| **PDCA Framework** | Plan phase complete; results inform Act phase (Apr 22+) |

---

## Output Files Reference

### Phase 1: Concurrent Call Analysis
- `concurrent_call_results.csv` — per-department summary
- `concurrent_hourly_heatmap.png` — 24×7 heatmap
- `secondary_demand_by_dept.png` — bar chart
- `erlang_c_results.csv` — P(wait) per department

### Phase 2: Secondary Network Design
- `secondary_network_solutions.csv` — K=2-5 results
- `secondary_network_map_K2.png` through `K5.png` — maps
- `secondary_network_diminishing_returns.png` — elbow chart
- `secondary_allocation_table.csv` — BG-level assignments

### Phase 3: Staffing & Cost
- `secondary_staffing_scenarios.csv` — 3 scenario comparison
- `staffing_waterfall.png` — cost waterfall
- `current_vs_consolidated.png` — before/after comparison
- `fte_transition.csv` — PT→FT transition detail

### Phase 4: Peak Staffing
- `peak_staffing_profiles.png` — hourly profiles with SPC limits
- `peak_staffing_optimal.csv` — optimal EMT assignments (1-5)
- `peak_staffing_marginal_heatmap.png` — dept × hour marginal value
- `peak_staffing_shift_values.csv` — all shift-level values

### Existing Analysis (prior work)
- `peak_staffing_report.md` — comprehensive temporal demand report
- `peak_staffing_heatmap_county.png` — county-wide hour × DOW
- `peak_staffing_optimal_shift.png` — optimal shift window
- `peak_staffing_response_time_by_hour.png` — RT degradation signals
- `peak_staffing_overstaffing.png` — day/night staffing mismatch

---

## Data Sources

| Source | Period | Use |
|--------|--------|-----|
| 14 NFIRS Excel files | CY2024 | Call volumes, temporal patterns, response times |
| FY2025 department budgets | FY2025 | Expense, revenue, staffing levels |
| Chief Peterson cost projection | Dec 2025 | 24/7 ALS station cost model |
| Census ACS / WI DOA estimates | 2024-25 | Service area population |
| ORS road-network drive times | Cached | Station-to-block-group travel times |
| Fire chief interviews | Mar 2026 | Staffing corrections, operational context |
