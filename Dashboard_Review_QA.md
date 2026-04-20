# Jefferson County EMS Dashboard — Review Q&A

**Date:** March 9, 2026
**Source:** Dashboard review notes (fixes.txt)
**Data sources:** ems_dashboard_app.py, NFIRS call data (CY2024), FY2025 budgets, IGA contracts

---

## Q1. Western Lakes Call Volume — Real or Data Artifact?

**It's a data scope issue, not just time.**

Western Lakes Fire District is based in Waukesha County and primarily serves the Oconomowoc area. Their NFIRS file contains **all 6,581 district calls from 2024** — but only approximately **200–250 of those are Jefferson County incidents** (Towns of Oakland and Concord). The rest are Waukesha County responses.

**Secondary issue — time horizons vary:**
- Palmyra: only 3 months of NFIRS data (Jan–Mar)
- Helenville: only 7 months (Mar–Sep)
- Western Lakes: full 12 months (but wrong geography)
- All other departments: full 12 months

**Impact:** Western Lakes' call volume KPIs are essentially unusable for per-capita or cost-efficiency comparisons with Jefferson County departments. The dashboard excludes them from cost-per-call calculations for this reason.

---

## Q2. Peak Hour Scheduling — 6am to 8pm Pattern

**The pattern is real (~2–2.5x more calls during 6am–8pm vs overnight), but we have no scheduling data.**

What we know:
- The hour-of-day heatmap (Tab 2) confirms the county-wide pattern
- Peterson's cost model assumes 24/48 shift schedule (24 on, 48 off) — most common for career WI departments
- 130 overtime hours/employee/year in the Peterson model suggests some callback demand for coverage gaps

**Data gap:** To answer whether scheduling is optimized for peak hours, we would need shift rosters or scheduling data from each department. That data is not in the current dataset. This is a good question for the Working Group — ask fire chiefs whether any department adjusts staffing levels for peak vs. off-peak hours.

---

## Q3. Cambridge Staffing — Part-Time vs. Volunteer

**The 31 "PT" are almost certainly volunteers, not paid part-time employees.**

Cambridge's total FY2025 budget is $92,000. If 31 people were truly paid part time, that would cost about $500K — more than 5x the entire budget. The $92K is consistent with a volunteer model where members receive stipends or per-call payments of $10–15.

In Wisconsin fire/EMS reporting, many volunteer/combination departments list their volunteer roster under "Part-Time" in budget documents because volunteers technically have an employment-like relationship (background checks, physicals, required training) even though they are not salaried.

**Dashboard accuracy:** The Model field correctly shows "Volunteer" for Cambridge. A footnote clarifying "PT = volunteer roster" would improve clarity.

---

## Q4. Western Lakes Budget

**We do not have it, and obtaining it is structurally complicated.**

- Western Lakes is a Waukesha County entity — their budget is filed in Waukesha County, not Jefferson County
- No Western Lakes IGA contract with any Jefferson County municipality was found in our contract document set
- Their MABAS filing was a blank template — no apparatus data filed

**To obtain:** Would need a Waukesha County public records request, plus a formal call count to isolate just the Jefferson County portion. Their operational costs may partially subsidize services that Towns of Oakland/Concord/Rome/Sullivan would otherwise need to fund — making Western Lakes an invisible budget item in Jefferson County's EMS financial picture.

---

## Q5. Funding Gap — Are Some Entries Actually Revenue?

**Yes — several entries are inter-municipal contract payments that function as EMS revenue.**

| Department | Payment Type | Amount | Notes |
|---|---|---|---|
| Jefferson City | Per-capita fees from 5 townships | ~$102K/yr | Included in $732K EMS Revenue |
| Fort Atkinson | Per-capita fees from Koshkonong & Jefferson Twp | ~$28–31K/yr | Included in $713K EMS Revenue |
| Johnson Creek | Equalized value payments from 4 townships | Included in $288K | — |
| Ixonia | Town of Watertown payment | $49,169 | Captured in total fund, not EMS_Revenue line |

**Exception — Lake Mills:** Pays $347K OUT to Ryan Brothers, who keeps 100% of transport billing. The $8K Lake Mills shows as EMS revenue is prior-year billing adjustments. Their funding gap is real.

**Key point:** The "Net Tax" column already accounts for these inter-municipal revenues being netted out. Fort Atkinson's ~$0 net tax means their EMS Fund is fully covered by billing + township payments.

---

## Q6. Staffing Data Sources

**Mixed sources — no single authoritative database.**

| Department | Source | Confidence |
|---|---|---|
| Watertown | 2024 Annual Report | High |
| Fort Atkinson | 2024 Annual Report | High |
| Whitewater | McMahon staffing analysis (Jan 2025 consultant report) | High |
| Jefferson | 2025 Budget Document for Council | Medium |
| Waterloo | Wage line items in fire_dept_2025.pdf | Medium |
| Johnson Creek | johnsoncreekfiredept.com website (web research Mar 2026) | Low — corrected mid-project |
| Ixonia | Ixonia 2024 Fire-EMS-Budget.pdf | Medium |
| Cambridge, Lake Mills, Palmyra | Annual reports / budget documents | Medium-Low |

No department has provided direct payroll data. MABAS filings include personnel counts but those are from 2016–2020 — too stale for current analysis.

---

## Q7. Cost Per Emergency Call — Is It Normalized?

**Partially. Two departments have confirmed partial-year data, one has zero NFIRS data.**

| Department | Issue | Handling |
|---|---|---|
| Palmyra | 3 months only (Jan–Mar), 35 actual calls | Extrapolated to ~140 annual (×4.0) |
| Helenville | 7 months only (Mar–Sep), 16 actual calls | Extrapolated to ~27 annual (×1.714) |
| Lake Mills | Zero NFIRS records (Ryan Brothers files separately) | Excluded from cost-per-call |
| Western Lakes | 6,581 calls includes wrong geography | Excluded from cost-per-call |

**Net effect:** Cost-per-call figures are directionally correct but should be treated as **±15–25% estimates** for departments with data quality issues. Fort Atkinson and Watertown (high volume, full year, complete budgets) have the most reliable figures.

---

## Q8. Revenue Recovery Rates — Why So Different?

**Calculation:** EMS_Revenue ÷ Total_Expense × 100

**Six root causes explain the variation:**

1. **Billing rates differ dramatically:**
   - Watertown: $1,100 (BLS)
   - Fort Atkinson: $1,500
   - Jefferson: $1,900
   - At identical call volumes, Watertown generates 42% less revenue per transport than Jefferson

2. **Collection rates:** Fort Atkinson nets ~$666 on a $1,500 bill = 44% collection rate. Medicare/Medicaid reimburse at pre-set rates regardless of billed amount.

3. **Dedicated EMS Fund:** Fort Atkinson segregates EMS revenue/expense into Fund 7, operated at near-breakeven. No other department does this.

4. **Contract structure:** Lake Mills pays Ryan Brothers, who retains all billing → near-zero recovery for the city.

5. **Whether billing is attempted:** Cambridge had $0 EMS revenue in FY2025 (medical director vacancy shut down collections).

6. **Call volume:** Palmyra's ~140 calls can generate at most ~$93K gross on an $818K budget — structurally incapable of meaningful recovery regardless of billing efficiency.

---

## Q9. Palmyra Taxpayer Subsidy — Why So High?

**Fixed costs don't scale down with call volume.**

Palmyra's $817,740 budget covers a full ambulance infrastructure on **~140 calls/year**. Fixed costs that don't shrink:
- Insurance: $50K+ annually (liability + workers comp)
- Vehicle maintenance on the ambulance
- Medical supplies (medications expire regardless of use)
- Training and certification for 20 volunteer members
- Dispatch/paging infrastructure

**Cost per call:** $5,841 (at 140 extrapolated) to $23,364 (at 35 raw calls) — dramatically above any other department.

**Hidden subsidy:** Palmyra is BLS-only. ALS calls (cardiac, trauma, overdose) require Western Lakes intercept — Western Lakes provides the expensive paramedic care without Palmyra's budget covering that cost.

---

## Q10. Whitewater vs. Fort Atkinson Taxpayer Burden

### Whitewater — High burden (~$319/resident)
- Net Tax: $1,370,114 on $2,710,609 total expense (50.5% tax-supported)
- Converted BLS → ALS via **November 2022 referendum** — added paramedic staffing costs that haven't been offset by increased billing yet
- **Denominator problem:** Jefferson County service population is only 4,296 (city straddles Jefferson + Walworth counties). Full service area is ~15,000. The per-capita figure is inflated because we only count the Jefferson County portion.
- Revenue recovery: 23.1%

### Fort Atkinson — Near-zero burden
Three structural advantages combine:
1. **Dedicated EMS Fund** (Fund 7) operated at breakeven
2. **High call volume + right-sized staffing:** 2,076 calls on 16 FT + 28 PT (career + PT model keeps fixed costs lower)
3. **Contract revenue** from Towns of Koshkonong and Jefferson (~$28–31K/yr)
4. **$666/transport net collection × 1,621 EMS calls ≈ $1.08M gross** → nets to $713,850 after adjustments

Fort Atkinson is the closest thing Jefferson County has to a financially self-sustaining municipal EMS operation.

---

## Q11. Low Ambulance Utilization

**The low utilization is real — not just a data artifact.**

| Benchmark | Value | Source |
|---|---|---|
| **National avg (CMS GADCS 2024)** | 1,147 transports/ambulance/year | CMS Ground Ambulance Data Collection |
| **UHU target (911 systems)** | 0.30 – 0.50 | Fitch & Associates |
| **High-performance UHU** | 0.23 – 0.48 | AIMHI member agencies |

**Jefferson County comparison:**

| Department | Ambulances | EMS Calls | Calls/Ambulance | vs. National |
|---|---|---|---|---|
| Watertown | 3 | 1,947 | 649 | 57% of benchmark |
| Fort Atkinson | 3 | 1,621 | 540 | 47% of benchmark |
| Jefferson City | 5 | 91* | 18 | 2% of benchmark |
| Palmyra | 1 | ~140 | 140 | 12% of benchmark |

*Jefferson City's 91 NFIRS calls may be undercounted — CAD cross-validation needed.

**Structural cause:** 11 separate departments each maintaining their own fleet creates inherent overcapacity. Each department reserves standby capacity for concurrent calls. Consolidation into 3–4 larger departments could maintain coverage with fewer total ambulances at higher utilization.

---

## Q12. Ambulances Per Capita — National Benchmarks

| System Type | Benchmark | Source |
|---|---|---|
| **US average** | 1 ambulance per 51,000 population | HMP Global / EMS World |
| **One-tier systems** | 1 per 53,291 | Same |
| **Two-tier systems** | 1 per 47,546 | Same |
| **Urban career systems** | 1.0–1.5 per 10,000 | NFPA deployment guidelines |
| **Rural/mixed systems** | 2.0–4.0 per 10,000 | Same |

**Whitewater anomaly explained:** 4 ambulances ÷ 4,296 Jefferson County residents = 9.3 per 10K (appears extreme). But their full service area is ~15,000 → 4 ÷ 15,000 = **2.7 per 10K** (normal for mixed urban/rural). The inflated appearance is entirely a denominator problem — we use only the Jefferson County resident count.

**Jefferson City:** 5 ambulances for 7,800 residents = 6.4 per 10K — genuinely high, though 2 of those are older intercept/backup vehicles.

---

## Q13. Fort Atkinson Revenue Recovery — Why So High, and Why Are Others Low?

**Fort Atkinson has five structural advantages no other department combines:**

1. Career + PT staffing model (lower fixed labor cost than pure career)
2. Dedicated EMS Fund with ring-fenced accounting
3. High call volume (1,621 EMS calls) generating meaningful billing
4. ALS-level service enabling higher billing categories
5. Contract revenue from two surrounding townships

**Why others are low — systematic patterns:**

| Department | Key Issue |
|---|---|
| Cambridge | $0 revenue — medical director vacancy shut down billing |
| Lake Mills | Ryan Brothers retains all transport billing |
| Watertown | BLS rate ($1,100) is 42% below Jefferson's ($1,900) |
| Palmyra | Call volume too low for meaningful billing on any rate |
| Waterloo, Ixonia | Lower billing aggressiveness, organizational structures that make revenue retention difficult |

The revenue gap follows predictable structural patterns (billing rate, fund structure, volume) that are addressable with specific interventions. *(Specific recommendations reserved for Act phase, Apr 22+.)*

---

## Q14. Mutual Aid Activity

**Yes — mutual aid measures how much departments help one another.**

The NFIRS "Aid Given or Received" field tracks:
- **Aid Given:** Department sent resources to help another department
- **Aid Received:** Department received help from another department on a call in their jurisdiction

**What high "Aid Received" means:**
- Department frequently can't staff or respond with own resources
- Neighbors are filling coverage gaps
- Cambridge post-collapse is the extreme case — virtually all EMS calls went to Fort Atkinson as mutual aid

**What high "Aid Given" means:**
- Department has excess capacity or is geographically positioned to respond into neighbors' territories
- Fort Atkinson and Whitewater tend to be net aid givers (career staff available during business hours when volunteer departments are understaffed)

**Caveat:** NFIRS coding of mutual aid vs. automatic aid (pre-planned multi-department dispatch) is not standardized across departments.

---

## New Intel: Waterloo Fire Chief Interview (March 11, 2026)

Key findings from a direct conversation with the Waterloo Fire Department Chief:

### Staffing (corrects/supplements Q6)
- **4 full-time members** (responsibility is to cover EMS) — chief says they could use 6 FT for 24/7 coverage with no days off/vacation running crews of two
- **10 individuals who are EMS-only**, 12 cross-trained fire+EMS, 20 fire-only
- On any given day, cannot guarantee 1 fully-staffed engine
- Volunteers paid on-call, mainly 2nd and 3rd shift; required to be within city limits with 3–4 min response to station
- **Pay rates:** $20/call/person at fire level; EMS part-time get $10/hr (AEMT) and $7.50/hr (EMR driver)

### Service Model
- Originally all-volunteer through the fire department; ~15 years ago started allowing EMS-only members
- Started with 2 FT EMTs, now at 4 FT and requesting more
- State requires at least 1 Advanced EMT + 1 EMT to provide service
- EMS calls require 2 people on the rig; cardiac arrest needs higher-quality crew; can be up to 6 responders
- **Covers 4 townships + City of Waterloo**, governed by the city
- Transports to **10 different hospitals in 4 different counties**

### Territory & Contracting
- Territories set many years ago — chief acknowledges they may need review
- Some boundaries set by county lines, which the chief views as "unrealistic historical distribution"
- More calls = more revenue, which incentivizes departments to bid for larger territories
- Towns sometimes go for cheaper contracts instead of shortest response time
- Contract rates: uses per-capita rate, looks at median of what other municipalities charge
- Gets advice from their billing agency to help set rates
- Waterloo is **low to medium** in billing rates

### Fleet & Equipment
- Ambulance life expectancy: **10 years first-line, then 10 years as second-out unit (~20 years total)**
- Timeline getting stretched — departments deferring replacements
- Re-boxing ambulances instead of buying new (cost savings strategy)
- Ambulance prices increased significantly through and after COVID
- Cardiac monitors: ~$60,000 each, not on a regular replacement schedule
- Cots: ~20-year service life, require ongoing service plan

### County-Wide Levy (Q on feasibility)
- Chief's view: biggest derailment risk is **"Who's gonna get the money and who's not, and do they get it for the right reasons"**
- Suggested looking at the **Library Model** for fund distribution
- 3 levels of EMS service with different cost structures — fund distribution would need to account for this
- **80–85% of calls are basic-level (nationwide)** — departments staffing paramedics 24/7 send them to all calls including basic ones
- Takeaway: *"People will be hawks for their funds and fight for their territory"*

### Dashboard Data Corrections
- Our data showed Waterloo as 3 FT / 15 PT. Chief confirms **4 FT** (corrected up from 3). The ~42 total personnel (10 EMS-only + 12 cross-trained + 20 fire-only) is higher than our 15 PT count — suggests the 15 was EMS-eligible members only, not the full roster.
- Ambulance lifecycle benchmark: **10-year first-line + 10-year second-out = 20 years** (vs. the 15-year end-of-life standard we used for the replacement priority table). This means our "CRITICAL" flags may be slightly aggressive — though the chief also said timelines are being stretched.

---

## New Intel: Johnson Creek Fire Chief Interview (March 13, 2026)

Key findings from a direct conversation with the Johnson Creek Fire Department Chief:

### Staffing (corrects/supplements Q6)
- **3 FT employees** (chief is both Fire Chief and Paramedic) — confirmed, matches our data
- **18-20 part-time EMS employees**, 12-15 paid-on-call (fire-cert only)
- Dashboard updated: Model changed from "Volunteer" → **"Combination"** (3 FT makes it combination by definition)
- Dashboard updated: Staff_PT changed from 40 → **33** (midpoint of 30-35 actual roster: 18-20 PT + 12-15 paid-on-call)
- 3-person FT shift provides ALS coverage; 5-6 paid-on-call always available at any given time

### Call Volume (supplements Q7)
- Chief reports **~750 calls in 2024** — NFIRS data shows 636. Discrepancy (~15%) likely due to NFIRS excluding non-transport responses, cancelled calls, or lift assists that the chief counts operationally.
- **~70 calls on 2nd ambulance** (second-call situations) — mitigated with mutual aid + staff responding from home
- 2nd ambulance not always staffed 24/7; relies on nearby personnel

### County-Wide BLS/ALS Split (NEW — Q15)
- **60-70% of Jefferson County call volume is BLS** — paramedic response not always necessary
- Corroborates Waterloo Chief's statement that 80-85% of calls are basic-level (nationwide)
- Implication: Departments staffing paramedics 24/7 are sending ALS crews to majority-BLS calls

### WI ALS Dispatch Mandate (NEW — Q16)
- If an agency is an ALS service in WI, the **paramedic must be sent** to answer every call (possibly SPS law)
- Chief flagged this as worth investigating — what exactly is required from the paramedic, what unit must transport
- This is a structural constraint on any staffing optimization: ALS agencies cannot selectively dispatch BLS-only crews even when the call is BLS

### Medical Direction (NEW — Q17)
- **Singular medical direction is the #1 takeaway** for any consolidation/coordination effort
- Currently multiple medical directors across the county (Dr. George covers several munis)
- Different doctors = different protocols (NEP protocol) — usually based on geography/proximity
- No major clinical issues, but differences in training levels and what procedures are allowed
- Unifying medical direction is the lowest-friction, highest-impact first step — doesn't require full consolidation

### Views on Consolidation
- **Benefits:** One unified unit → same guidelines, apparatus, training. Single medical director. Boundaries become less rigid → focus on closest vehicle. Facilities more movable.
- **Drawbacks:** 13 agencies run by 13 different people. Employment, political, financial differences. Agencies have "versions of ownership." Many rely on EMS revenue to support fire side financially.
- **Feasibility:** Thinks it *can* work. Doubts all 13 agencies would agree. Realistic first step = **unified front on EMS** (not full consolidation). Timeline estimate: within a year for first step.
- Taking away EMS autonomy tends to hurt fire department finances — but it's better for citizens.

### Response Model Insights
- Current distributed model keeps response times low because agencies are geographically spread
- 2nd vehicle dispatch takes 10-12 minutes; if still no coverage, neighboring counties help (sequential decision-making)
- Large geographic area + small population = response time driven by population distribution
- Higher call volume → higher quality response and care (practice effect)
- Recommends **repositioning ambulances/facilities closer to where call volume actually is**

### Boundary Observations
- Boundaries set by municipalities, working well from his perspective
- **Waterloo is BLS, Ixonia is BLS** — both contracted with a paramedic service for ALS coverage
- Jurisdictional boundaries are the current model; county-based would shift to closest-vehicle dispatching

### Dashboard Data Corrections Applied
- Model: "Volunteer" → "Combination" (3 FT career staff = combination by definition)
- Staff_PT: 40 → 33 (midpoint of chief's 18-20 PT + 12-15 paid-on-call = 30-35)
- Source comment updated to cite chief interview (Mar 13, 2026)

---

## Q15. BLS vs. ALS Call Split — How Much Is Basic?

**60-70% of Jefferson County calls are BLS, per Johnson Creek Chief. Waterloo Chief cited 80-85% nationally.**

This is a critical finding for cost analysis:
- Departments staffing paramedics 24/7/365 are sending ALS crews to majority-BLS calls
- The ALS overhead (higher pay, more training, more expensive equipment) is applied to calls that don't require it
- This is not inefficiency per se — WI may require ALS agencies to dispatch paramedics to all calls (see Q16)

**Data gap:** The NFIRS data includes incident type codes that could validate this split. A systematic analysis of Type of Situation Found codes (e.g., 300-series = EMS, with sub-codes for severity) would give a department-by-department BLS/ALS breakdown. This has not yet been done.

---

## Q16. WI ALS Dispatch Requirement — Must Paramedics Respond to Every Call?

**Johnson Creek Chief reports this is a state requirement, possibly under SPS (Safety and Professional Services) law.**

Key questions to investigate:
1. Is the mandate statutory (WI Statutes Chapter 256) or administrative code (SPS/DHS)?
2. Does it require the paramedic to *respond on the truck*, or just be *available*?
3. Can an ALS agency dispatch a BLS-only crew to a confirmed BLS call?
4. What are the liability implications if an ALS agency sends BLS to an ALS call?

**Why this matters:** If ALS agencies truly cannot selectively dispatch, then any cost savings from "right-sizing" responses (sending BLS to BLS calls) requires either (a) changing the dispatch protocol with state approval, or (b) restructuring agencies so some operate at BLS level with ALS intercept from a centralized paramedic unit.

**Action needed:** Research WI Admin Code Chapter DHS 110 and SPS rules on ambulance service levels and dispatch requirements.

---

## Q17. Medical Direction — Multiple Doctors, Multiple Protocols

**Johnson Creek Chief identifies unified medical direction as the single most important first step.**

Current state:
- Multiple medical directors serve Jefferson County departments
- Dr. George covers several municipalities
- Other doctors cover other areas — assignment based on geography/proximity
- Each medical director sets their own protocols (NEP protocol framework common)
- Result: Differences in training levels and allowed procedures across department boundaries

**Why it matters:**
- A patient having a cardiac event in one jurisdiction may receive different interventions than the same patient 2 miles away in another jurisdiction
- Cross-training and mutual aid are complicated when protocols differ
- Unified medical direction is achievable without any structural consolidation — it's a contractual/administrative change

**Precedent:** County-based EMS systems (Portage County, Bayfield County) typically operate under a single medical director, which is cited as a key advantage for protocol consistency and training standardization.

---

## Q18. EMS District Boundaries vs. Fire District Boundaries

**Added March 25, 2026 — per project team clarification.**

**EMS service area boundaries and fire district boundaries are NOT the same in Jefferson County.** The dashboard now treats EMS district lines as the authoritative geographic boundaries for all analysis.

**Key differences:**
- Fire districts include entities like **Helenville, Rome, Sullivan, and Lake Mills** as separate fire districts — but EMS coverage for those areas is provided by neighboring EMS departments (e.g., Western Lakes covers Rome & Sullivan for EMS)
- The **12 EMS districts** are: Cambridge, Edgerton, Fort Atkinson, Ixonia, Jefferson, Johnson Creek, Palmyra, Ryan Brothers, Waterloo, Watertown, Western Lakes, Whitewater
- The **14 fire districts** include additional entities (Helenville, Rome, Sullivan, Lake Mills) that do not operate independent EMS services

**Dashboard implementation:**
- EMS district overlay (cyan dashed lines) is now **ON by default** and labeled "authoritative"
- Fire district overlay (orange dashed lines) is available for reference but labeled "reference only"
- EMS district polygons show district names on hover
- The data quality notes at the top of the Overview tab explicitly state "EMS ≠ Fire Districts"
- Source: `Copy of Map of Jefferson County EMS Districts .jpg` (Jefferson County GIS)

**Why this matters for the project:** All geographic analysis — coverage modeling, response time territories, facility location optimization, and boundary consolidation scenarios — must use EMS district boundaries, not fire district lines. Using fire districts would incorrectly represent service areas and produce misleading coverage assessments.

---

## Items Still Requiring External Data

| Item | What's Needed | Suggested Path |
|---|---|---|
| Western Lakes budget | Waukesha County public records | County website or records request |
| Shift scheduling data | Rosters from each department | Ask fire chiefs at Working Group meeting |
| Lake Mills call volumes | Ryan Brothers NFIRS data | Contact Ryan Brothers or Lake Mills FD |
| Jefferson City call validation | CAD dispatch records | Cross-reference with dispatch center |
| Missing billing rates (11 depts) | Rate schedules | Ask fire chiefs or EMS|MC (shared billing vendor) |
| Chief Peterson report details | Full cost projection document | Already in project: `25-1210 JC EMS Workgroup Cost Projection.pdf` |
| WI ALS dispatch mandate | Statutory/admin code text (DHS 110 / SPS) | Research WI Admin Code; contact DHS EMS Section |
| BLS/ALS call split by dept | NFIRS Type of Situation Found analysis | Analyze existing NFIRS data (codes 300-series) |
| Medical director inventory | Which MD covers which dept, protocol differences | Ask at Working Group meeting |
