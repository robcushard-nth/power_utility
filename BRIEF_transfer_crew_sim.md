# Session brief — power_utility: adapt the storm simulator into a Transfer Crew Capacity Simulator

**Target repo:** `C:\Users\RobCushard\power_utility` (branch `main`,
GitHub `robcushard-nth/power_utility`). Open a Claude session in that repo
and execute this brief. A copy of this file lives at the repo root as
`BRIEF_transfer_crew_sim.md`.

**Date:** 2026-10-01 · **Client:** prospect, an investor-owned electric
utility (name withheld; never put a utility name in this repo) ·
**Sensitivity:** client, no customer or circuit data; synthetic and
planning-assumption inputs only · **Priority:** internal/product capacity.
This feeds the Phase 1 assessment in the "Transfer Crew AI Concept"
(https://claude.ai/code/artifact/2684d893-80f3-4119-a4cb-f98ae44831d3) and
doubles as the discovery-call demo. It does not displace customer
commitments in `nth_program/commitments.json`.

## 0. Why

The utility runs one seven-person pole transfer / cutover crew against a
workload sized for several. The concept proposes an AI pilot that removes
non-tool time (packet defects, sequencing, waiting on clearances, locates
and attachers, close-out paperwork) rather than adding linemen. The ROI case
needs a model, not a hand range. `3_grid_simulation/` already has the right
skeleton: SimPy crews as a constrained resource, stochastic jobs, a Monte
Carlo wrapper, cost and tail-risk outputs. This brief turns it into a
transfer-crew capacity simulator with three scenarios: one crew as-is, one
crew with waiting reduced, two crews.

## 1. What exists (read first)

- `3_grid_simulation/storm_response.py` (60 lines): single-run DES, crews
  as `simpy.Resource`, gauss travel, exponential repair.
- `3_grid_simulation/streamlit_app.py` (210 lines): Monte Carlo UI, up to
  500 runs, sliders for crews, crew rate, outages, customers; reports
  CAIDI/SAIDI, restoration cost, 95th-percentile VaR, worst run; matplotlib
  and seaborn charts.
- `portfolio.md` (generated 2026-09-18) describes the whole POC.
- No tests. `requirements.txt` unpinned.

Leave the storm simulator working exactly as it is. Add beside it; do not
refactor it.

## 2. Build

### 2.1 Engine: `3_grid_simulation/transfer_crew_sim.py`

A SimPy model of a transfer crew's working weeks.

**Entities and parameters (all sliders in the UI, all with defaults that are
labeled "planning assumption" in code comments and in the UI):**

- Crews: count N (default 1), crew size (default 7, cost only), crew loaded
  cost per hour (default $700/hr for the whole crew; label as assumption).
- Calendar: working days per week (5), hours per day (10), horizon in weeks
  (12). Nothing happens outside shift hours.
- Arrivals: pole sets feeding the transfer queue, as a rate per week
  (default 12) with Poisson arrivals, plus an initial backlog (default 20).
  Each arrival is a transfer job carrying a `pole_set_time` so double-wood
  age can be measured.
- Job time components, each a distribution, in minutes:
  - travel to site (lognormal, median 35)
  - site setup and tailboard (triangular 20/30/45)
  - tool time on the pole (lognormal, median 150) — the crew's actual work
  - close-out and paperwork (triangular 15/25/40)
- Waiting and defect events, each with a probability and a delay:
  - packet defect found on site (p=0.20): delay (triangular 30/60/120) and
    with p=0.35 of those the job is re-dispatched (returns to queue, counts
    as a second trip)
  - clearance not ready at arrival (p=0.25): wait (lognormal, median 45)
  - locate not valid (p=0.10): job re-dispatched
  - attacher not ready (p=0.15): job re-dispatched
  - materials missing (p=0.10): delay (triangular 40/75/150)
- Scenario lever "AI-assisted packets and sequencing": multiplies the
  packet-defect, locate, attacher and materials probabilities and the
  clearance wait by `(1 - reduction)`, default reduction 0.25. Tool time is
  never reduced by the lever — AI does not climb.

**Scenarios run by default:** (a) 1 crew baseline, (b) 1 crew with the AI
lever on, (c) 2 crews baseline. The UI lets the user add a fourth custom
scenario.

**Outputs per run, then aggregated across Monte Carlo runs (median, p5,
p95):**

- transfers completed per crew-week
- wrench-time ratio = tool time / paid crew hours
- paid hours lost to waiting and defects, by cause
- re-dispatch rate (second trips / jobs)
- backlog at end of horizon and backlog over time (weekly series)
- double-wood age: time from pole set to transfer complete, median and p95
- cost per completed transfer = paid crew hours × crew cost / completed

Conservation check on every run: arrivals + initial backlog = completed +
in-progress + waiting.

Deterministic seeding: a `seed` parameter; same seed, same results.

### 2.2 Field-data intake

A CSV schema the Phase 1 time study produces, so the model can be
re-parameterized from real observations without code changes:

`data/time_study_template.csv` with columns
`date, job_id, block_start, block_end, category, note` where `category` is one
of: `tool_time, travel, setup_tailboard, wait_clearance, wait_locate,
packet_defect, materials_run, wait_attacher, traffic_control, closeout`.

`transfer_crew_sim.py` exposes `fit_from_time_study(path)` that returns the
parameter set (medians and probabilities) from such a file. Ship a synthetic
example file (clearly named `example_synthetic_time_study.csv`) so the path
is exercised.

### 2.3 UI: `3_grid_simulation/transfer_crew_app.py`

A second Streamlit app (do not merge into the storm app). Sidebar: Monte
Carlo runs, calendar, crews, cost, arrivals, the AI lever, seed, optional
time-study CSV upload. Main area, in this order:

1. One headline table: the three scenarios side by side with transfers per
   crew-week (median and p5–p95), wrench-time ratio, cost per transfer,
   double-wood age p95, backlog at end.
2. Backlog over time, one line per scenario.
3. Paid hours lost by cause, baseline versus AI lever.
4. Distribution of transfers per crew-week for each scenario.
5. A download button for the per-run CSV and for the headline table as CSV.

Every number on screen is labeled as a planning assumption until a
time-study file is loaded; when one is loaded, the caption says so.

### 2.4 Tests: `tests/test_transfer_crew_sim.py`

pytest, seeded:

- conservation holds on every run
- two crews complete at least as many transfers as one crew
- the AI lever never increases paid hours lost to waiting and defects
- the AI lever never changes tool-time draws (same seed, same tool time)
- `fit_from_time_study` on the synthetic example returns every parameter
  the engine needs
- the storm simulator still imports and runs one iteration unchanged

### 2.5 Housekeeping

- Pin `requirements.txt`; add `pytest`.
- README: add a "Transfer Crew Capacity Simulator" section mirroring the
  storm section, with how to run both apps.
- Regenerate `portfolio.md` with the nth-portfolio-builder skill if time
  allows; otherwise add a dated note at the top.

## 3. Constraints

- No utility name, no real circuit, customer or crew data, anywhere.
- Planning-assumption defaults are labeled as such in code and UI. Do not
  present them as benchmarks.
- Do not touch the storm simulator's behavior. Additive only.
- Session edits only `power_utility`. Report back to `nth_program` by
  telling the PM session what shipped; do not edit `nth_program` from here.
- Sized for one session. If 2.2 or 2.5 would push past that, ship 2.1, 2.3
  and 2.4 and leave a `TODO.md`.

## 4. Definition of done

- [ ] `transfer_crew_sim.py` runs the three default scenarios with a seed
      and prints the headline table from the command line.
- [ ] `streamlit run 3_grid_simulation/transfer_crew_app.py` shows the five
      panels and the downloads work.
- [ ] `pytest` passes; the six tests in 2.4 exist.
- [ ] Synthetic time-study CSV loads through `fit_from_time_study` and the
      UI caption changes.
- [ ] Storm app still runs.
- [ ] README updated; requirements pinned.
- [ ] Committed on `main` and pushed.

## 5. Report back

Give the PM session: commit hash, which items shipped, the headline table
for the three default scenarios, and anything learned that should change the
concept doc's ROI section. The PM session will flip `power_utility` to
active in `portfolio.json` and update the concept doc.
