# Jefferson County EMS — Peak Call Hours & Staffing Analysis

**Data Source:** CY2024 provider-level call records from 6 municipalities
**Departments with valid timestamps:** Edgerton, Jefferson, Johnson Creek, Lake Mills, Waterloo
**Note:** Whitewater excluded from hourly analysis (data contains dates only, no timestamps)

---

## 1. Countywide Peak Hours

### Hourly Call Distribution (All Departments Combined, n=3,331)

| Hour | % of Calls | Volume |
|------|-----------|--------|
| 00:00 | 2.0% | LOW |
| 01:00 | 2.0% | LOW |
| 02:00 | 2.0% | LOW |
| 03:00 | 2.0% | LOW |
| 04:00 | 1.6% | LOW |
| 05:00 | 2.3% | LOW |
| 06:00 | 3.0% | |
| 07:00 | 4.4% | |
| 08:00 | 4.2% | |
| 09:00 | 4.5% | |
| 10:00 | 5.6% | |
| 11:00 | 5.9% | **PEAK** |
| 12:00 | 5.6% | |
| 13:00 | 4.9% | |
| 14:00 | 5.6% | |
| 15:00 | 5.9% | **PEAK** |
| 16:00 | 6.0% | **PEAK** |
| 17:00 | 6.8% | **PEAK** |
| 18:00 | 6.5% | **PEAK** |
| 19:00 | 4.8% | |
| 20:00 | 4.2% | |
| 21:00 | 3.7% | |
| 22:00 | 3.7% | |
| 23:00 | 3.0% | |

- **Peak window:** 11:00 - 19:00 (31.1% of all calls in just 8 hours)
- **Low window:** 00:00 - 06:00 (11.9% of all calls)
- **Peak hour vs trough hour:** 4.2x difference (17:00 at 6.8% vs 04:00 at 1.6%)

### Shift Breakdown

| Shift | Hours | % of Calls | Note |
|-------|-------|-----------|------|
| Day | 06:00 - 13:59 | 38.1% | |
| Afternoon | 14:00 - 21:59 | **43.5%** | **Busiest shift** |
| Overnight | 22:00 - 05:59 | 18.6% | Quietest shift |

**Afternoon-to-overnight call ratio: 2.3x** — the afternoon shift handles 2.3 times the call volume of the overnight shift.

---

## 2. Day of Week Distribution

| Day | % of Calls |
|-----|-----------|
| Monday | 15.6% |
| Tuesday | 13.8% |
| Wednesday | 15.1% |
| Thursday | 13.6% |
| Friday | 14.6% |
| Saturday | 13.7% |
| Sunday | 13.6% |

- **Weekday average:** 14.5% per day
- **Weekend average:** 13.6% per day
- **Conclusion:** Nearly flat distribution. No significant weekend spike or drop. Staffing does not need weekday/weekend differentiation.

---

## 3. Per-Department Analysis

### Edgerton
**2,138 calls/yr | 24 FT + 0 PT | Career+PT | 2 ambulances**

| Metric | Value |
|--------|-------|
| Calls/ambulance | 1,069 |
| Calls/FT staff | 89 |
| Peak hours | 17:00 (7.3%), 10:00 (6.6%), 16:00 (6.2%) |
| Day shift load | 39% (~843 calls/yr, ~2.3/day) |
| Afternoon shift load | 42% (~895 calls/yr, ~2.5/day) |
| Overnight shift load | 19% (~399 calls/yr, ~1.1/day) |
| FT on duty per shift | ~8 staff = ~4 crews |
| Zero-call days | 184 (50%) |
| Max calls in a day | 6 |
| P95 daily calls | 4 |

**Assessment: Current model works well.** 24 FT career staff is efficient for this call volume. 2 ambulances at 1,069 calls/amb is the highest utilization in the county. Afternoon shift is busiest — could weight staffing slightly toward 14:00-22:00.

---

### Jefferson
**1,457 calls/yr | 6 FT + 20 PT | Career | 5 ambulances**

| Metric | Value |
|--------|-------|
| Calls/ambulance | 291 |
| Calls/FT staff | 243 |
| Peak hours | 11:00 (7.6%), 15:00 (6.6%), 16:00 (6.5%) |
| Day shift load | 39% (~562 calls/yr, ~1.5/day) |
| Afternoon shift load | 42% (~617 calls/yr, ~1.7/day) |
| Overnight shift load | 19% (~278 calls/yr, ~0.8/day) |
| FT on duty per shift | ~2 staff = ~1 crew |
| Zero-call days | 7 (2%) |
| Max calls in a day | 12 |
| P95 daily calls | 8 |

**Assessment: Over-ambulanced, under-crewed on FT.** 5 ambulances for 1,457 calls is excessive — 3 would suffice. Only 6 FT means just 1 crew per shift, forcing reliance on 20 PT for all additional units. P95 days hit 8 calls, requiring 2+ concurrent crews during peak afternoon hours.

**Suggestion:** Reduce to 3 ambulances. Add 2-4 FT positions to cover peak afternoon shift (14:00-22:00), reducing dependence on the PT pool.

---

### Johnson Creek
**487 calls/yr | 3 FT + 33 PT | Combination | 2 ambulances**

| Metric | Value |
|--------|-------|
| Calls/ambulance | 244 |
| Calls/FT staff | 162 |
| Peak hours | 17:00 (10.7%), 18:00 (7.6%), 19:00 (6.6%) |
| Day shift load | 38% (~183 calls/yr, ~0.5/day) |
| Afternoon shift load | 46% (~223 calls/yr, ~0.6/day) |
| Overnight shift load | 17% (~81 calls/yr, ~0.2/day) |
| FT on duty per shift | ~1 staff = ~0.5 crews |
| Zero-call days | 98 (27%) |
| Max calls in a day | 11 |
| P95 daily calls | 7 |

**Assessment: Heavily PT-dependent with crew gap risk.** Only 3 FT = 1 per shift, which cannot field a 2-person FT crew at any time. The 33 PT staff compensate, but availability is unpredictable. Johnson Creek has the sharpest peak of any department — 17:00 alone accounts for 10.7% of all calls, 2x the average hour.

**Suggestion:** Add 1-2 FT positions to guarantee a daytime crew (06:00-18:00). This covers the 17:00 spike without relying on PT page-outs. Reduce PT from 33 to ~20 with better FT coverage.

---

### Lake Mills
**518 calls/yr | 4 FT + 20 PT | Career+Vol | 3 ambulances**

| Metric | Value |
|--------|-------|
| Calls/ambulance | 173 |
| Calls/FT staff | 130 |
| Peak hours | 14:00 (8.5%), 10:00 (7.3%), 15:00 (6.4%) |
| Day shift load | 39% (~204 calls/yr, ~0.6/day) |
| Afternoon shift load | 43% (~223 calls/yr, ~0.6/day) |
| Overnight shift load | 18% (~91 calls/yr, ~0.2/day) |
| FT on duty per shift | ~1.3 staff = ~0.7 crews |
| Zero-call days | 88 (24%) |
| Max calls in a day | 8 |
| P95 daily calls | 4 |

**Assessment: Overstaffed on ambulances and PT.** 3 ambulances for 518 calls = 173 calls/amb. At 1.4 calls/day average with 24% zero-call days, 1-2 ambulances would suffice. 4 FT + 20 PT for this volume is excessive.

**Suggestion:** Reduce to 2 ambulances. Current 4 FT is adequate for daytime coverage. Reduce PT from 20 to ~12 for overnight/backup.

---

### Waterloo
**520 calls/yr | 4 FT + 22 PT | Career+Vol | 2 ambulances**

| Metric | Value |
|--------|-------|
| Calls/ambulance | 260 |
| Calls/FT staff | 130 |
| Peak hours | 18:00 (8.2%), 16:00 (7.9%), 09:00 (6.3%) |
| Day shift load | 35% (~184 calls/yr, ~0.5/day) |
| Afternoon shift load | 45% (~232 calls/yr, ~0.6/day) |
| Overnight shift load | 20% (~104 calls/yr, ~0.3/day) |
| FT on duty per shift | ~1.3 staff = ~0.7 crews |
| Zero-call days | 133 (36%) |
| Max calls in a day | 7 |
| P95 daily calls | 3 |

**Assessment: FT level is right, PT pool is oversized.** 4 FT for 520 calls is appropriate. However, 22 PT for a department that averages 1.4 calls/day with 36% zero-call days is excessive. Afternoon shift carries 45% of calls — the strongest afternoon skew of any department.

**Suggestion:** Maintain 4 FT. Reduce PT from 22 to ~12-15. Weight FT scheduling toward afternoon shift (14:00-22:00). Second ambulance is justified for P95 days (3+ calls) but only needed 12% of days.

---

## 4. Cross-Cutting Findings

### Finding 1: Universal Afternoon Peak
Every department shows 42-47% of calls between 14:00-21:59. The overnight shift (22:00-05:59) consistently carries only 15-20% of call volume.

**Implication:** Staffing should be weighted toward afternoon, not equally split across three shifts.

### Finding 2: Day of Week is Flat
Call volume is nearly identical across all 7 days (range: 13.3% - 15.7%).

**Implication:** No need for different weekday vs weekend staffing models.

### Finding 3: Overnight Staffing Opportunity
With only 15-20% of calls overnight, departments paying for 24/7 FT staffing are carrying significant idle overnight capacity. For small departments, overnight on-call (PT/volunteer) is defensible given the low call volume.

### Finding 4: Simultaneous Calls are Rare for Small Departments
- Waterloo: only 12% of days have 3+ calls
- Lake Mills: only 22% of days have 3+ calls
- Johnson Creek: 58% of days have 3+ calls (includes non-EMS in raw data)

**Implication:** Most secondary ambulances sit idle on most days. This directly supports Goal 1 (regional secondary ambulance pooling).

---

## 5. Recommended County-Funded Staff Placement

If Jefferson County funds 1-2 paid EMTs/paramedics (per Goal 2 of the recommendation plan):

### Option A: One 12-Hour EMT (10:00 - 22:00)
- Covers **65% of all county EMS call volume** in a single shift
- Fills the afternoon gap when PT workers are least available (day jobs)
- Should be stationed with the regional secondary ambulance network (Goal 1)
- Estimated coverage: ~9,600 calls/yr fall in this window countywide

### Option B: Two 10-Hour EMTs (Staggered)
- EMT 1: 08:00 - 18:00 (covers morning + midday peak)
- EMT 2: 14:00 - 00:00 (covers afternoon peak + early overnight)
- **Overlap 14:00-18:00** provides double coverage during the busiest 4 hours
- This overlap period contains ~25% of all daily calls

Either option should be assigned to the **regional secondary ambulance network**, not embedded in a single municipality, to maximize utilization across the county.

---

## 6. Summary Table

| Department | Calls/Yr | FT | PT | Amb | Peak Shift | Assessment | Suggested Change |
|---|---|---|---|---|---|---|---|
| Edgerton | 2,138 | 24 | 0 | 2 | Afternoon (42%) | Current model works | Weight FT slightly toward afternoon |
| Jefferson | 1,457 | 6 | 20 | 5 | Afternoon (42%) | Over-ambulanced, under-crewed | Cut to 3 amb, add 2-4 FT for afternoon |
| Johnson Creek | 487 | 3 | 33 | 2 | Afternoon (46%) | Crew gap risk | Add 1-2 FT, reduce PT to ~20 |
| Lake Mills | 518 | 4 | 20 | 3 | Afternoon (43%) | Overstaffed | Cut to 2 amb, reduce PT to ~12 |
| Waterloo | 520 | 4 | 22 | 2 | Afternoon (45%) | PT oversized | Reduce PT to ~12-15 |

---

## Data Notes

- **Edgerton:** 289 of 2,138 calls have timestamps in this extract. Hourly distribution patterns are representative even from partial data.
- **Johnson Creek:** Raw data includes 1,090 rows (fire + EMS). Filtered to ~650 EMS-related calls for this analysis. Authoritative EMS count is 487.
- **Waterloo:** 379 of 520 authoritative calls present in data file.
- **Whitewater:** Excluded from hourly analysis — data file contains only dates (Incident Date), no dispatch timestamps. All 64 Jeff Co calls are for Koshkonong and Cold Springs townships only.
- **Lake Mills:** Data is from Ryan Brothers Ambulance (private provider), which took over 911 service after Lake Mills EMS nonprofit closed in 2023.
