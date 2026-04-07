# Jefferson County EMS -- Quantitative Analysis Report (Phases A-G)

**Date:** April 7, 2026
**Data Period:** CY2024 (Calendar Year 2024)
**Data Sources:** 14 NFIRS Excel files (13,819 EMS calls), 6 provider-level datasets, concurrent call analysis, ORS drive time matrices
**Methodology:** All findings are diagnostic. Financial data quantifies the problem -- it does not prescribe solutions.

---

## Phase A: Primary vs Secondary Response Time Comparison

### Methodology
Each EMS call was classified as **primary** (first call in a concurrent overlap cluster) or **secondary** (arriving while another call is active in the same department). Classification was validated against Johnson Creek provider data, which includes explicit Vehicle ID and Mutual Aid columns.

### County-Wide Results

| Metric | Primary Calls | Secondary Calls | Delta |
|--------|:---:|:---:|:---:|
| Count | 6,967 | 1,268 | -- |
| Median RT | 5.0 min | 6.0 min | **+1.0 min** |
| P90 RT | 11.0 min | 12.0 min | **+1.0 min** |
| Mean RT | 6.1 min | 6.8 min | +0.7 min |

The difference is statistically significant (Mann-Whitney U, p < 0.0001).

### Per-Department Breakdown

| Department | Primary Median | Secondary Median | Delta | P90 Delta | Significant? |
|---|:---:|:---:|:---:|:---:|:---:|
| Watertown | 5.0 | 5.5 | +0.5 | +2.0 | Yes (p=0.004) |
| Fort Atkinson | 4.0 | 5.0 | +1.0 | +1.0 | Yes (p=0.008) |
| Whitewater | 5.0 | 5.0 | 0.0 | +1.8 | Yes (p=0.009) |
| Edgerton | 6.0 | 6.0 | 0.0 | +1.0 | No (p=0.187) |
| Johnson Creek | 7.0 | 6.5 | -0.5 | +2.6 | No (p=0.752) |
| Waterloo | 7.0 | 8.0 | +1.0 | -0.2 | No (p=0.558) |
| Ixonia | 10.0 | 13.0 | **+3.0** | +1.2 | Yes (p=0.035) |
| Palmyra | 5.0 | 8.0 | **+3.0** | -0.8 | No (p=0.066) |
| Cambridge | 6.5 | 9.0 | +2.5 | -2.5 | N/A (n=2) |
| Jefferson | 7.0 | 11.0 | +4.0 | +0.8 | N/A (n=2) |

**Key Finding:** Secondary calls experience a consistent 1-minute median delay county-wide, but the impact is much larger for rural/volunteer departments (Ixonia: +3 min, Palmyra: +3 min). The high-volume career departments (Watertown, Fort Atkinson, Whitewater) show smaller but statistically significant delays.

### Johnson Creek Ground-Truth Validation
Using Johnson Creek's provider data (728 ambulance records, 608 unique incidents, explicit Vehicle IDs):
- Primary: 584 records, Median RT = 6.9 min, P90 = 12.4 min
- Secondary: 144 records, Median RT = 8.0 min, P90 = 16.5 min
- **Ground-truth secondary RT is 1.1 min higher at median and 4.1 min higher at P90** -- consistent with NFIRS findings

### Output Files
- `phase_a_primary_secondary_rt.csv` -- per-dept RT comparison
- `phase_a_rt_comparison_boxplot.png` -- side-by-side box plots
- `phase_a_jc_validation.csv` -- Johnson Creek ground truth

---

## Phase B: Geographic Distribution of Secondary Ambulance Use

### Methodology
Each of the 8,341 classified calls was geocoded to one of 65 Census block groups using a city/ZIP-to-BG centroid mapping (115 unique city/ZIP pairs mapped).

### Top 10 Block Groups by Secondary Call Count

| Block Group | Population | Total Calls | Secondary Calls | Secondary per 1K Pop | Secondary % |
|---|:---:|:---:|:---:|:---:|:---:|
| 550551003022 (Watertown) | 1,478 | 2,035 | 377 | 255.1 | 18.5% |
| 550551016001 (Whitewater) | 3,283 | 1,449 | 236 | 71.9 | 16.3% |
| 550551012011 (Edgerton area) | 1,211 | 987 | 223 | 184.2 | 22.6% |
| 550551012012 (Edgerton area) | 1,066 | 1,021 | 209 | 196.1 | 20.5% |
| 550551013004 (Fort Atkinson) | 729 | 1,591 | 104 | 142.7 | 6.5% |
| 550551004002 (Waterloo area) | 1,917 | 354 | 56 | 29.2 | 15.8% |
| 550551007001 (Johnson Creek) | 2,840 | 357 | 34 | 12.0 | 9.5% |
| 550551017022 (Ixonia area) | 2,054 | 106 | 12 | 5.8 | 11.3% |
| 550551009002 (Jefferson area) | 826 | 34 | 9 | 10.9 | 26.5% |
| 550551017021 (Ixonia area) | 1,173 | 83 | 8 | 6.8 | 9.6% |

**Key Finding:** Secondary demand is concentrated in three geographic corridors:
1. **Watertown** (northwest) -- 377 secondary calls, highest absolute count
2. **Edgerton/Lakeside** (southwest) -- 432 combined secondary calls across two BGs, highest secondary percentage (20-23%)
3. **Whitewater** (south-central) -- 236 secondary calls

These three areas account for **83%** of all secondary demand county-wide.

### Output Files
- `phase_b_secondary_by_bg.csv` -- all 65 BGs with secondary counts
- `phase_b_secondary_heatmap.png` -- graduated circle map
- `phase_b_geocoded_calls.csv` -- all 8,341 calls with BG assignments

---

## Phase C: Ambulance Utilization by Unit and Time of Day

### Methodology
For each department, hourly utilization was calculated as: (total call-minutes overlapping that hour) / (ambulances x days x 60 minutes). This measures the fraction of total ambulance capacity consumed.

### Department Utilization Summary

| Department | Ambulances | Calls | Daily Avg Util | Peak Util (09-19) | Peak Hour | Exceeds 25%? |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Edgerton | 2 | 2,033 | 11.3% | **15.2%** | 12:00 | No |
| Whitewater | 2 | 1,448 | 6.9% | 8.7% | 10:00 | No |
| Watertown | 3 | 1,945 | 5.5% | 6.9% | 10:00 | No |
| Palmyra | 1 | 32 | 3.6% | 4.5% | 12:00 | No |
| Ixonia | 1 | 258 | 3.2% | 4.2% | 18:00 | No |
| Waterloo | 2 | 398 | 3.1% | 4.3% | 16:00 | No |
| Johnson Creek | 2 | 454 | 2.6% | 3.2% | 18:00 | No |
| Fort Atkinson | 3 | 1,618 | 2.1% | 2.8% | 13:00 | No |
| Jefferson | 3 | 91 | 0.2% | 0.2% | 15:00 | No |

**Key Findings:**
- **No department exceeds the 25% peak utilization threshold** -- the industry benchmark where service reliability begins to degrade.
- **Edgerton is the most utilized** at 15.2% peak, despite having only 2 ambulances for 2,033 calls. This is high for a 2-ambulance department.
- **Jefferson is severely underutilized**: 5 ambulances handling 91 calls = 0.1% utilization. This represents significant excess capacity.
- **Peak hours are 09:00-19:00** across all departments, with the highest demand between 10:00-14:00.
- **Off-peak utilization drops to 1.7-8.5%** across all departments.

### Output Files
- `phase_c_utilization_by_dept_hour.csv` -- dept x hour utilization matrix (216 rows)
- `phase_c_utilization_profiles.png` -- faceted 24-hour profiles per dept
- `phase_c_utilization_summary.csv` -- per-dept summary statistics

---

## Phase D: Current Staffing Operations Investigation

### Methodology
Staffing data was compiled from department budgets, chief interviews, and the EMS Chief Association. FTE equivalents use 1 FT = 1.0, 1 PT = 0.5 FTE. Cost per call = total annual expense / EMS calls.

### Staffing Efficiency Comparison

| Department | Model | FT | PT | FTE | Ambulances | Calls | Calls/FTE | Cost/Call | Cost/Capita |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Edgerton | Career | 24 | 0 | 24.0 | 2 | 2,033 | **84.7** | **$347** | $187 |
| Whitewater | Career + PT | 15 | 17 | 23.5 | 2 | 1,448 | 61.6 | $1,872 | $631 |
| Watertown | Career 24/7 | 31 | 3 | 32.5 | 3 | 1,945 | 59.8 | $1,971 | $167 |
| Fort Atkinson | Career + PT | 16 | 28 | 30.0 | 3 | 1,618 | 53.9 | $470 | $47 |
| Waterloo | Career + Vol | 4 | 22 | 15.0 | 2 | 398 | 26.5 | $2,770 | $250 |
| Johnson Creek | Combination | 3 | 40 | 23.0 | 2 | 454 | 19.7 | $2,498 | $337 |
| Ixonia | Vol + FT chiefs | 2 | 45 | 24.5 | 1 | 258 | 10.5 | $2,446 | $124 |
| Jefferson | Career + PT | 6 | 20 | 16.0 | 3 | 91 | **5.7** | **$16,487** | $192 |
| Palmyra | Volunteer | 0 | 20 | 10.0 | 1 | 32 | **3.2** | **$25,554** | $245 |

**Key Findings:**
- **15x efficiency spread**: Edgerton handles 84.7 calls per FTE vs Palmyra at 3.2 calls per FTE.
- **74x cost-per-call spread**: Edgerton at $347/call vs Palmyra at $25,554/call.
- **Jefferson has 3 ambulances for 91 calls** -- 30 calls per ambulance per year, or roughly 1 call every 12 days per unit. This is the most significant capacity mismatch.
- **Volunteer/combination departments** (Ixonia, Johnson Creek, Waterloo) have high PT staff counts (22-45) but low call-per-FTE ratios, reflecting on-call standby overhead.
- **Career departments** (Edgerton, Watertown, Fort Atkinson) achieve significantly better staffing efficiency due to higher call volumes and dedicated crews.

### Output Files
- `phase_d_staffing_profile.csv` -- full staffing and efficiency metrics
- `phase_d_staffing_efficiency.png` -- scatter plot (FTE per 1K calls vs cost per call)

---

## Phase E: Secondary Ambulance Response Destinations & Mutual Aid Flows

### Mutual Aid Exchange

| Department | Aid Given | Aid Received | Net | Direction |
|---|:---:|:---:|:---:|---|
| Watertown | 34 | 14 | **+20** | Net Provider |
| Fort Atkinson | 8 | 2 | +6 | Net Provider |
| Edgerton | 12 | 8 | +4 | Net Provider |
| Ixonia | 12 | 14 | -2 | Net Receiver |
| Johnson Creek | 20 | 25 | -5 | Net Receiver |
| Palmyra | 0 | 5 | -5 | Net Receiver |
| Whitewater | 7 | 14 | **-7** | Net Receiver |
| Waterloo | 4 | 28 | **-24** | Net Receiver |

**Key Findings:**
- **Waterloo is the county's largest net mutual aid receiver** (-24), relying heavily on neighboring departments. This aligns with its AEMT-level service (not full ALS) and volunteer staffing model.
- **Watertown is the county's largest net mutual aid provider** (+20), consistent with its career 24/7 staffing and 3-ambulance fleet.
- **Three departments carry the mutual aid burden**: Watertown, Fort Atkinson, and Edgerton collectively provide 54 mutual aid responses while receiving only 24 -- a net export of 30 responses to other jurisdictions.
- **Mutual aid is asymmetric**: Provider departments tend to be career-staffed ALS, while receiver departments tend to be volunteer/combination with lower service levels.

### Output Files
- `phase_e_secondary_destinations.csv` -- top 5 destination BGs per department
- `phase_e_cross_boundary_flows.csv` -- mutual aid exchange table
- `phase_e_secondary_flow_map.png` -- flow visualization with inset bar chart

---

## Phase F: Response Area Hot Spots

### Methodology
Block groups were ranked by both absolute call count and calls per 1,000 population. A combined rank (average of both) identifies areas that are significant on both dimensions.

### Top 10 Demand Hot Spots

| Rank | Block Group | Population | Total Calls | Calls/1K Pop | Secondary Calls |
|:---:|---|:---:|:---:|:---:|:---:|
| 1.5 | 550551013004 (Fort Atkinson core) | 729 | 1,591 | **2,182** | 104 |
| 1.5 | 550551003022 (Watertown core) | 1,478 | 2,035 | 1,377 | 377 |
| 3.5 | 550551012012 (Edgerton area) | 1,066 | 1,021 | 958 | 209 |
| 4.0 | 550551016001 (Whitewater area) | 3,283 | 1,449 | 441 | 236 |
| 4.5 | 550551012011 (Edgerton area) | 1,211 | 987 | 815 | 223 |
| 6.5 | 550551007001 (Johnson Creek area) | 2,840 | 357 | 126 | 34 |
| 6.5 | 550551004002 (Waterloo area) | 1,917 | 354 | 185 | 56 |
| 8.0 | 550551011001 (Jefferson area) | 1,655 | 127 | 77 | 5 |
| 9.5 | 550551017021 (Ixonia area) | 1,173 | 83 | 71 | 8 |
| 9.5 | 550551017022 (Ixonia area) | 2,054 | 106 | 52 | 12 |

**Key Findings:**
- **Fort Atkinson core BG has the highest per-capita demand** at 2,182 calls per 1,000 population -- likely driven by nursing home/assisted living facilities.
- **The top 5 hot spots generate 73% of all secondary demand** (1,149 of 1,568 secondary calls across all BGs with data).
- **Edgerton has two hot-spot BGs** that together produce 432 secondary calls -- the highest secondary demand concentration in the county.
- **Urban cores drive absolute volume; small-population BGs drive per-capita rates** -- both perspectives are important for ambulance placement.

### Output Files
- `phase_f_hotspot_ranking.csv` -- all 65 BGs ranked
- `phase_f_hotspot_map.png` -- dual-panel map (absolute vs per-capita)
- `phase_f_temporal_hotspots.csv` -- hour-by-hour patterns for top 10 BGs

---

## Phase G: Baseline System Performance & Optimization Inputs

### Current System Baseline (13 stations, 20 ambulances)

| Metric | Value |
|---|:---:|
| Pop-weighted average RT | **7.47 min** |
| Weighted median RT | **7.05 min** |
| Weighted P90 RT | **12.72 min** |
| Maximum RT (any BG) | **18.66 min** |
| Coverage within 8 min | 64.9% |
| Coverage within 10 min | 78.1% |
| Coverage within 14 min | **94.1%** |
| Coverage within 20 min | 100.0% |
| Total FTE equivalents | 198.5 |
| Total annual cost | $13,196,149 |

### Optimization Targets
- **Primary target:** >=90% population within 14 minutes (currently met at 94.1%)
- **Stretch target:** >=90% population within 10 minutes (currently at 78.1% -- **gap of 11.9 percentage points**)
- **Constraint:** Every block group reachable within 20 minutes (currently met)

### Demand Weights for Optimization
Composite demand weights were built for each of the 65 block groups, blending:
- Population (40% weight)
- Total EMS call volume (40% weight)
- Secondary demand frequency (20% weight)

These weights feed into the P-Median and MCLP facility location solvers for Phases H-L.

### Output Files
- `phase_g_demand_weights.csv` -- composite weights per BG
- `phase_g_baseline_metrics.csv` -- current system performance

---

## Consolidated Diagnostic Summary

### Coverage & Response Time
- The current 13-station system provides adequate 14-minute coverage (94.1%) but falls short of 10-minute coverage (78.1%). The stretch target of 90% within 10 minutes requires optimized placement.
- Secondary calls experience a statistically significant +1.0 minute delay at both median and P90.

### Demand Concentration
- Three geographic corridors (Watertown, Edgerton, Whitewater) generate 83% of secondary demand.
- The top 5 hot-spot block groups produce 73% of all secondary calls.

### Capacity Mismatch
- No department exceeds the 25% peak utilization threshold -- there is system-wide excess capacity.
- Jefferson operates 5 ambulances at 0.1% utilization (91 calls/year). Palmyra operates 1 ambulance for 32 calls/year at $25,554/call.
- Edgerton is the most efficient at 84.7 calls/FTE and $347/call.

### Mutual Aid Asymmetry
- Three career departments (Watertown, Fort Atkinson, Edgerton) are net mutual aid providers (+30 net responses).
- Six departments are net receivers, with Waterloo being the largest (-24).
- This pattern reflects the structural dependence of volunteer/combination departments on career departments for secondary coverage.

### Staffing Efficiency
- A 15x efficiency spread exists across departments (3.2 to 84.7 calls per FTE).
- A 74x cost-per-call spread exists ($347 to $25,554 per call).
- The county spends $13.2 million annually across 198.5 FTE for 8,341 EMS calls in the NFIRS transport-department dataset (14,853 county-wide including Western Lakes and others).

---

## Output File Index

| Phase | File | Description |
|---|---|---|
| A | `phase_a_primary_secondary_rt.csv` | Per-dept RT comparison table |
| A | `phase_a_rt_comparison_boxplot.png` | Side-by-side box plots |
| A | `phase_a_jc_validation.csv` | Johnson Creek ground truth |
| B | `phase_b_secondary_by_bg.csv` | Secondary counts per block group |
| B | `phase_b_secondary_heatmap.png` | Graduated circle density map |
| B | `phase_b_geocoded_calls.csv` | All calls with BG assignments |
| C | `phase_c_utilization_by_dept_hour.csv` | Hourly utilization matrix |
| C | `phase_c_utilization_profiles.png` | Faceted utilization profiles |
| C | `phase_c_utilization_summary.csv` | Per-dept utilization summary |
| D | `phase_d_staffing_profile.csv` | Staffing and efficiency metrics |
| D | `phase_d_staffing_efficiency.png` | FTE vs cost scatter plot |
| E | `phase_e_secondary_destinations.csv` | Top destinations per dept |
| E | `phase_e_cross_boundary_flows.csv` | Mutual aid exchange table |
| E | `phase_e_secondary_flow_map.png` | Flow visualization |
| F | `phase_f_hotspot_ranking.csv` | All 65 BGs ranked |
| F | `phase_f_hotspot_map.png` | Dual-panel hot spot map |
| F | `phase_f_temporal_hotspots.csv` | Hourly patterns for top BGs |
| G | `phase_g_demand_weights.csv` | Composite optimization weights |
| G | `phase_g_baseline_metrics.csv` | Current system baseline |

All files are located in the `analysis_output/` directory.

---

## Next Steps: Optimization Phases (H-L)

Based on the diagnostic findings above, here is the recommended path forward:

### Phase H: Determine How Many County-Wide Ambulances Are Needed

**What we know now:** The current system has 20 ambulances across 13 stations but utilization is extremely uneven -- Edgerton runs at 15.2% peak while Jefferson runs at 0.2%. The three demand corridors (Watertown, Edgerton, Whitewater) account for 83% of secondary demand. No department exceeds 25% utilization, meaning there is significant excess fleet capacity county-wide.

**What to do:** Sweep K=3 through K=13 county-wide ambulances using the P-Median and MCLP solvers (already built in `pareto_facility.py`) with the Phase G composite demand weights. Identify the "elbow" -- the K value where adding another ambulance yields diminishing coverage improvement. Prior secondary network analysis found K=3 as the elbow for secondary-only demand; the county-wide analysis using blended weights may yield K=7-9.

**Key question to answer:** Can we cover >=90% of the population within 14 minutes with fewer than 20 ambulances?

### Phase I: Determine County-Wide Staffing Requirements

**What we know now:** The county currently employs 198.5 FTE equivalents (105 FT + ~187 PT at 0.5 FTE each). Calls per FTE ranges from 3.2 (Palmyra) to 84.7 (Edgerton). Peak demand is 09:00-19:00 at ~2.9x overnight rates.

**What to do:** For the recommended K ambulances, compute staffing needs using three scenarios:
- **Scenario A:** All K stations staffed 24/7 (K x 7.2 FTE each = Peterson model)
- **Scenario B:** All K stations peak-only 08:00-20:00 (K x 4.8 FTE each)
- **Scenario C:** Hybrid -- high-demand stations 24/7, others peak-only

Validate each scenario with pooled Erlang-C queueing model to ensure P(wait) is acceptable.

### Phase J: Determine Optimal Ambulance Locations

**What we know now:** The 60-candidate site grid and 65-block-group demand points with ORS road-network drive times are cached and ready. Baseline coverage: 94.1% at 14 min, 78.1% at 10 min.

**What to do:** Run `solve_pmedian_pop()` with the recommended K from Phase H to find optimal placement. Generate territory maps showing which block groups each ambulance serves. Compare against current station locations to identify which existing stations align with optimal placement (likely Watertown, Fort Atkinson, Edgerton, Whitewater) and which are redundant.

### Phase K: Feasibility Check & Iteration

**What to do:** Calculate median, P90, and coverage metrics for the Phase J solution. If targets aren't met (90% within 14 min, P90 under 20 min), increment K and re-solve. Sensitivity analysis: show what happens at K-1 and K+1 to quantify the marginal value of each additional ambulance.

### Phase L: Validation -- Before vs After Comparison

**What to do:** Side-by-side comparison of:
- Coverage improvement (especially the 10-min stretch target gap)
- Response time reduction for underserved areas
- Reduced P(wait) during peak hours
- Fleet size reduction and staffing efficiency gains
- Financial context (diagnostic, not prescriptive)

Frame findings around care quality: "X% more citizens reached within 14 minutes" and "reduced secondary call delays from +3 min to +X min in rural areas."

### Decision Points Before Proceeding

1. **Optimization objective priority:** Should the solver minimize average response time (P-Median) or maximize population coverage within a threshold (MCLP)? Or run both and compare? The current plan runs both.

2. **Candidate sites:** Should we constrain placement to existing station locations only, or allow the moveable 60-point candidate grid? Using existing stations is more realistic for near-term implementation; the grid shows the theoretical optimum.

3. **Service level constraint:** Should all county-wide ambulances be ALS, or is a mix of ALS/BLS acceptable? This affects staffing costs significantly (ALS paramedic crews vs BLS EMT crews).

4. **Scope of "county-wide":** Are we optimizing a secondary/backup network that supplements existing primary departments, or a fully consolidated system that replaces them? The analysis infrastructure supports both.
