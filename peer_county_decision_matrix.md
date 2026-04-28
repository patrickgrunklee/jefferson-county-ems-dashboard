# Peer County Decision Matrix — Jefferson County Hybrid Model

**Date:** April 27, 2026
**Purpose:** Slide-ready comparison of peer county EMS systems against the Jefferson County proposed regional secondary ambulance hybrid model. Jefferson County is the **benchmark row**.
**Companion document:** [peer_county_hybrid_models_research.md](peer_county_hybrid_models_research.md) (full source citations and narrative)

---

## Legend

- **Y** = Yes — feature is fully present
- **P** = Partial — feature partially present, recommended but not implemented, or analogous structure exists
- **N** = No — feature absent
- **?** = Unknown / not documented in available sources
- **Match Score** = count of features matching Jefferson's proposed design (Y = 1.0, P = 0.5, N/? = 0). Maximum = 8.0.

---

## Feature Definitions (Columns)

| # | Feature | What It Means |
|---|---|---|
| **F1** | Municipal Primaries Preserved | Each town/city retains its own primary ambulance, staffing, billing, and identity. No forced consolidation. |
| **F2** | County Overflow Transport Units | County (or regional authority) owns/operates transport-capable ambulances dedicated to overflow — not fly vehicles, not first-due replacements. |
| **F3** | Busy-Primary Dispatch Trigger | Secondary/overflow unit dispatches **only when** the home municipality's primary is already committed (concurrent-call trigger). |
| **F4** | Nearest-Unit Dispatch Algorithm | Real-time CAD/AVL closest-available logic routes overflow calls to the nearest secondary unit. |
| **F5** | County EMS Levy Funding | Dedicated countywide EMS property-tax levy funds the regional layer (Wisconsin: WI Stat. 66.0602(3) exemption or 2025 Act 212). |
| **F6** | Centralized County Dispatch / CAD | Single county-level PSAP and CAD coordinates all EMS units across municipalities. |
| **F7** | PT-to-FT Staffing Consolidation | Workforce moves from many underutilized PT crews scattered across municipal secondary units to fewer FT crews on the regional fleet. |
| **F8** | Optimization-Based Station Placement | Regional unit locations chosen by quantitative facility-location modeling (P-Median, MCLP, or equivalent). |

---

## Decision Matrix

| County | State | F1 Mun. Primaries | F2 County Overflow Units | F3 Busy-Primary Trigger | F4 Nearest-Unit Dispatch | F5 County Levy | F6 Central Dispatch | F7 PT→FT Consolidation | F8 Optimized Placement | **Match Score** | Tier |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **Jefferson (PROPOSED)** | **WI** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **Y** | **8.0** | **Benchmark** |
| Erie County | NY | Y | Y | Y | P | P | Y | P | P | 6.0 | **Strong Match** |
| King County | WA | Y | P | N | Y | Y | Y | Y | P | 5.5 | Cousin (acuity-tier) |
| Portage County | WI | Y | N | N | P | Y | Y | P | ? | 4.0 | Partial (gov./funding) |
| Dane County | WI | Y | P | N | Y | N | Y | P | ? | 4.0 | Partial (ALS overlay) |
| Pitt County | NC | Y | Y | N | Y | N | Y | N | N | 4.0 | Partial (geo-partition) |
| Walworth County | WI | Y | P | N | P | P | Y | N | ? | 3.5 | Partial (WPF-rec only) |
| La Crosse County | WI | Y | P | N | P | P | Y | N | ? | 3.5 | Partial (WPF-rec only) |
| Lafayette County | WI | P | P | N | P | Y | Y | P | ? | 3.5 | Partial (cautionary) |
| Milwaukee County | WI | Y | N | N | P | P | Y | N | N | 3.0 | Partial (subsidy only) |
| Washington County | WI | Y | ? | ? | ? | P | Y | ? | ? | 2.5 | Partial (active study) |
| Kalamazoo County | MI | P | Y | N | Y | N | Y | N | N | 3.5 | Cousin (multi-zone) |
| Sauk Prairie Amb. | WI | N/A | Y | N | Y | P | Y | Y | N | 5.0 | Cousin (joint comm.) |
| Western Lakes FD | WI | N/A | Y | N | Y | N | Y | Y | N | 4.5 | Cousin (multi-muni dist.) |
| Door County | WI | N | Y | N | Y | Y | Y | Y | N | 5.0 | Cousin (full county) |
| Waushara County | WI | N | Y | N | Y | Y | Y | Y | N | 5.0 | Cousin (full county) |
| Pinellas County | FL | N | Y | N | Y | Y | Y | Y | P | 5.5 | Cousin (utility model) |
| Multnomah County | OR | N | N | N | Y | N | Y | N | N | 2.0 | Cautionary tale |

---

## Tier Interpretation

- **Strong Match (≥6 features)**: real-world examples that validate the core mechanism. **Erie County, NY is the only one.**
- **Cousin / Partial (3–5 features)**: validated components Jefferson can borrow — funding (Portage), tiered dispatch (King), governance (Sauk Prairie, Western Lakes), full-county operations (Door, Waushara), public-utility scale (Pinellas).
- **Cautionary (≤2 features)**: structural failures that justify Jefferson's choice not to replicate them (Multnomah's "Level Zero" crisis under single-vendor franchise).

---

## Why Jefferson Is Unique

Looking down each column, Jefferson is the **only system that scores Y on all eight features simultaneously**. The unique synthesis points are:

- **F2 + F3 together**: Erie County is the only peer with both county-owned transport units **and** a busy-primary trigger. No Wisconsin county does this today.
- **F3 + F4 + F8 together**: a busy-primary trigger paired with closest-unit dispatch and optimization-driven placement is undocumented in any peer reviewed in this research. Jefferson's P-Median/MCLP work is the methodological differentiator.
- **F1 + F5 + F7 together**: preserving municipal identity while running a county levy AND consolidating PT into FT is rare. Portage has F1+F5 but not F7. Waushara/Door have F5+F7 but not F1.

---

## Current Operations — One-Line Summary per County

### Wisconsin

- **Portage County** — County sheriff's EMS Division coordinates and contracts with Stevens Point FD, Amherst FD, Plover FD; $3.03M county EMS levy at $0.35/$1,000; municipal departments deliver service, county owns no ambulances.
- **Dane County** — Tiered system: municipal fire departments (Madison, Sun Prairie, etc.) provide BLS first response; county-coordinated ALS resources overlay via 66.0301 IGAs; closest-unit dispatch via county PSAP.
- **Walworth County** — 15 municipal departments / 18 stations; WPF October 2025 study recommends adding a single county-funded paramedic fly vehicle as a mid-tier option; no county levy or county-owned transport unit yet.
- **La Crosse County** — Mostly municipal; WPF 2020 report recommended a "jointly funded county-wide paramedic intercept system"; not implemented as of 2026.
- **Lafayette County** — County created LCEMS in 2021 (replaced Argyle Fire ambulance service); experienced political backlash over levy; WPF 2025 report now recommends a paramedic fly vehicle at a county base as the next consolidation step.
- **Milwaukee County** — 15 municipal agencies retain primary transport; county contributes ~$2.5M ALS subsidy; central dispatch with closest-unit logic; no county-owned overflow units.
- **Washington County** — November 2025 county board resolution authorized study of a county-run EMS system; structure TBD; West Bend FD currently operates as the regional ALS anchor under bilateral MOUs.
- **Door County** — County is the sole transport provider with 4 staffed stations; municipal first-response only; sole-provider model with hospital overflow protocol when all units are committed.
- **Waushara County** — County operates four staffed ambulance stations as the sole provider; municipal services replaced; not preserved.
- **Western Lakes FD** — Multi-municipality fire/EMS district covering 11 municipalities including parts of Jefferson County (Ixonia/Sullivan); commission governance with one rep per member.
- **Sauk Prairie Ambulance** — Joint Powers Board across 3+ counties; one rep per municipality; FT-staffed countywide transport.

### National

- **Erie County, NY** — In 2023, county purchased five backup ambulances stationed at volunteer fire halls explicitly framed as a "safety net" when local volunteer units and mutual aid are committed. ~$4.67M startup, ~$2M annual operating. Local volunteer units remain primary.
- **King County, WA** — Medic One: 27 county-staffed paramedic units overlay municipal BLS fire departments since 1970s; county EMS property-tax levy funds the ALS layer; trigger is **call acuity** (ALS criteria), not concurrent-call status.
- **Pitt County, NC** — County EMS (10 stations) coexists with city EMS (Greenville, 6 stations); unified county dispatch; geographic partition rather than overflow-triggered.
- **Pinellas County, FL** — County public-utility model where Sunstar Paramedics (single private contractor) replaced all municipal transport; EMS authority levy funds; political cautionary tale because municipal transport had to be eliminated.
- **Kalamazoo County, MI** — County Medical Authority + 5 private ALS zones + 16 BLS first-responder municipalities; multi-zone with medical oversight.
- **Multnomah County, OR** — Single private franchise (AMR) with no backup layer; experienced "Level Zero" no-units-available crises in 2023; cautionary case validating Jefferson's need for a secondary capacity buffer.

---

## Source Notes

All scores are derived from documented sources cited in [peer_county_hybrid_models_research.md](peer_county_hybrid_models_research.md). Where a feature is marked **?**, the source material did not document the feature one way or the other — it should not be read as evidence the feature is absent. The matrix is a presentation tool, not a research instrument; for nuance, refer back to the full research file.

---

*End of decision matrix — designed for direct use as a presentation slide.*
