# Session brief — power_utility: adapt the storm simulator into a Change Event Capacity Simulator

**Version:** 2 (2026-10-01). Supersedes version 1 of this file. The file name is
kept so existing pointers still resolve; the module names below are new.

**Target repo:** `C:\Users\RobCushard\power_utility` (branch `main`,
GitHub `robcushard-nth/power_utility`). Open a Claude session in that repo
and execute this brief.

**Date:** 2026-10-01 · **Client:** prospect; a network transformation program
run by a systems integrator inside an investor-owned electric utility (neither
is named; never put a utility, integrator, program, or product-repository name
in this repo) · **Sensitivity:** client. The source runbook contains personal
names, direct phone numbers and email addresses. It never enters this repo,
and nothing derived from it may carry those identifiers. Synthetic and
planning-assumption inputs only · **Priority:** internal/product capacity.
This feeds the Phase 1 assessment in the "Transfer Crew AI Concept"
(https://claude.ai/code/artifact/2684d893-80f3-4119-a4cb-f98ae44831d3) and
doubles as the discovery-call demo. It does not displace customer
commitments in `nth_program/commitments.json`.

## 0. Why

The program replaces end-of-life network hardware at utility sites (operations
buildings, substations, hydro and solar plants, large campuses). Each site is
one or more scheduled change events. A change event is run by a field
engineer on site, an implementation engineer working remotely, and a bridge
lead who coordinates both through a change ticket, a chat room, and a set of
operations-center calls. Around them sit a design engineer, a remediation
lead, a workstream lead and a PM: roughly seven roles per change.

The program's runbook shows that most of a change night is not device work.
It is a gated pre-implementation checklist, access and hardware verification,
per-building check-in calls, a post-photo quality loop, a closure checklist,
and an administrative tail of prep and reporting that happens outside the
window. The concept proposes an AI pilot that removes that non-tool time
(packet validation, access and escort confirmation, chat-to-report
transcription, photo naming and first-pass QA, call logging) rather than
adding field engineers. The ROI case needs a model, not a hand range.

`3_grid_simulation/` already has the right skeleton: SimPy crews as a
constrained resource, stochastic jobs, a Monte Carlo wrapper, cost and
tail-risk outputs. This brief turns it into a change-event capacity simulator
with three scenarios: one team as-is, one team with the AI lever, two teams.

### Changes from version 1

Version 1 modeled a pole transfer crew. The client's runbook shows the work
is network change events. Version 2 relabels every wait cause to its runbook
escalation path, adds three things version 1 lacked (a quality rework loop,
the administrative tail, and site classes), replaces ten-hour days with
evening change windows, and replaces the hand time study with an event log
that can be produced from chat-room exports and ticket data. It also bakes in
the modeling decisions from the 2026-10-01 review: separate random streams
per component, aggregate-level test assertions, explicit lognormal sigmas,
a working-minutes clock with a calendar mapping, and a conftest for the
digit-leading directory name.

## 1. What exists (read first)

- `3_grid_simulation/storm_response.py` (60 lines): single-run DES, crews
  as `simpy.Resource`, gauss travel, exponential repair. Importable.
- `3_grid_simulation/streamlit_app.py` (210 lines): Monte Carlo UI, up to
  500 runs; reports CAIDI/SAIDI, restoration cost, 95th-percentile VaR,
  worst run. Reads sidebar globals inside class methods; not importable.
  Imports seaborn, which is not installed in the local environment today.
- `portfolio.md` (generated 2026-09-18, currently untracked) describes the
  whole POC. Commit it before regenerating.
- No tests. `requirements.txt` unpinned. README points at
  `/03_grid_simulation`; the directory is `3_grid_simulation`.
- `3_grid_simulation` is not an importable package name. Tests need a
  `conftest.py` that inserts the directory on `sys.path`.

Leave the storm simulator working exactly as it is. Add beside it; do not
refactor it.

## 2. Build

### 2.1 Engine: `3_grid_simulation/change_event_sim.py`

A SimPy model of change-event teams working evening change windows.

**Clock.** The simulation clock counts window minutes only. Window k falls
on calendar day `(k // windows_per_week) * 7 + (k % windows_per_week)`.
Nothing happens between windows except the administrative tail, which is
booked as daytime paid hours and does not consume window capacity. A change
that does not finish inside its window continues in the team's next window
(a second night, counted separately from a revisit caused by a defect).

**Entities and parameters (all sliders in the UI, all with defaults labeled
"planning assumption" in code comments and in the UI):**

- Teams: count N (default 1). A team is one field engineer on site, one
  bridge lead and one implementation engineer. Loaded hourly rates per role,
  defaults $95 / $85 / $125 (planning assumptions; the team costs about
  $305/hr during a window). Admin-tail hours are paid at the bridge lead and
  implementation engineer rates.
- Calendar: change windows per week (default 4), window length in hours
  (default 8), horizon in weeks (default 16).
- Arrivals: change-ready sites per week (Poisson, default 4) plus an initial
  backlog of change-ready sites (default 25). Backlog sites carry a
  `ready_time` spread uniformly over the 8 weeks before the horizon starts
  (assumption; exposed as a slider). Each site carries `ready_time` so
  end-of-life exposure can be measured.
- Site classes, drawn per site with a mix that sums to 1:

  | Class | Mix | Devices per change (triangular) | Notes |
  |---|---|---|---|
  | standard | 0.70 | 8 / 15 / 25 | |
  | renewables | 0.15 | 4 / 8 / 15 | per-device call to the renewables operations center, triangular 3/5/10 min |
  | large/complex | 0.10 | 20 / 35 / 60 | pre-gate and closure times ×1.5 |
  | logical | 0.05 | 5 / 10 / 20 | no field engineer, no travel, no access or hardware events |

- Time components, each a distribution, in minutes:
  - travel to site: lognormal, median 60, sigma 0.5 (logical: 0)
  - pre-implementation gate: triangular 45/70/120 (check-in, handwritten job
    briefing, per-building operations-center calls, room access walk,
    hardware and serial verification, tool check, pre-photos)
  - tool time: per device, lognormal median 12, sigma 0.4; summed per change.
    This is the team's actual work.
  - rooms per change: `1 + devices // 8`
  - quality rework: per room, probability 0.30 of a corrective action with
    delay triangular 10/20/45 (post-photo review, fix, re-photo)
  - closure on site: triangular 45/75/120 (decom logs, freight prep, trash
    sweep, per-building checkout)
  - administrative tail, outside the window: bridge lead prep triangular
    90/150/240; implementation engineer prep triangular 60/90/150; reporting
    and uploads triangular 60/90/180
- Wait and defect events, evaluated in this order at the gate. The first
  event that resolves to a no-go aborts the night; the site returns to the
  back of the queue, the aborted night's travel, gate and delay minutes are
  charged to that cause, and the site is immune to that same cause on its
  next visit.

  | Cause (runbook escalation path) | p | Delay if not aborted | Share that abort |
  |---|---|---|---|
  | packet defect: walkdown workbook, access tab, engineering package or shipment manifest disagree | 0.20 | triangular 30/60/120 | 0.30 |
  | go/no-go not ready: operations center, renewables center, or firewall impact with no incident ticket | 0.15 | lognormal median 45, sigma 0.5 | 0.20 |
  | showstopping remediation not complete or unverified | 0.10 | triangular 30/60/120 | 0.60 |
  | access failure: escort absent or leaves, badge, key, gate code | 0.20 | triangular 20/45/90 | 0.25 |
  | hardware or tools missing or damaged | 0.12 | triangular 30/60/120 | 0.35 |

- Scenario lever "AI-assisted packets, access and reporting": multiplies the
  five event probabilities and the quality-rework probability by
  `(1 - reduction)`, default reduction 0.25, and multiplies the administrative
  tail by `(1 - admin_reduction)`, default 0.40. Tool time, travel and the
  per-device renewables calls are never reduced by the lever.

**Random streams.** The arrival stream has its own generator. Each site
owns one `numpy.random.Generator` seeded from `(seed, site_id)`; per-site
draws (class, devices, tool time) happen once, and per-visit draws happen in
a fixed order with fixed counts, so the same site gets the same draws in
every scenario (common random numbers). Event outcomes are drawn as a
uniform compared against the threshold, so a reduced probability can only
turn an event off, never on.

**Scenarios run by default:** (a) 1 team baseline, (b) 1 team with the AI
lever on, (c) 2 teams baseline. The UI lets the user add a fourth custom
scenario.

**Outputs per run, then aggregated across Monte Carlo runs (median, p5,
p95):**

- changes closed per team-week, and devices installed per team-week
- wrench-time ratio = tool time / paid hours, where paid hours = window
  hours × team rate-hours + administrative-tail hours
- paid hours lost to waiting and defects, by cause, with quality rework and
  the administrative tail shown as their own rows
- revisit rate (aborted nights / changes) and nights per closed change
- backlog of change-ready sites at end of horizon and over time (weekly)
- end-of-life exposure: calendar days from `ready_time` to successful
  closure, median and p95
- cost per closed change and per device = paid hours × rates / closed

Conservation check on every run: arrivals + initial backlog = closed +
in-progress + waiting.

Deterministic seeding: same seed, same results.

### 2.2 Field-data intake

The program already records the time study. The chat room carries
timestamped check-in, milestones, delays and completion; the change ticket
carries start and stop; the external summary carries device counts, status
and a revisit flag. Define one event-log schema those sources can be exported
into, so the model is re-parameterized without code changes:

`3_grid_simulation/data/event_log_template.csv` with columns
`site_id, site_class, visit_n, event_time, event, note` where `event` is one
of: `depart, check_in, gate_start, gate_end, packet_issue, gonogo_wait_start,
gonogo_wait_end, remediation_block, access_issue, hardware_issue, resumed,
no_go, device_done, renewables_call, qa_rework, closure_start, checkout,
revisit_scheduled, prep_start, prep_end, report_start, report_sent`.
Probabilities are derived as the share of visits that contain an event;
durations as medians of the matching intervals (an issue's delay ends at the
next event, normally `resumed`); abort shares as the share of occurrences
followed by `no_go` on the same visit.

`change_event_sim.py` exposes `fit_from_event_log(path)` returning the full
parameter set the engine needs, with any parameter the log cannot support
left at its planning-assumption default and listed in a `missing` field.
Ship a synthetic example (clearly named `example_synthetic_event_log.csv`) so
the path is exercised.

### 2.3 UI: `3_grid_simulation/change_event_app.py`

A NiceGUI app (decision 2026-10-02; the storm app stays Streamlit and is not
merged). Charts via NiceGUI's ECharts element; no seaborn. Left drawer:
Monte Carlo runs, calendar, teams and rates, arrivals and backlog, site-class
mix, the AI lever, seed, optional event-log CSV upload, and an "advanced"
expander for the lognormal sigmas. Main area, in this order:

1. One headline table: the three scenarios side by side with changes per
   team-week (median and p5–p95), devices per team-week, wrench-time ratio,
   cost per change, end-of-life exposure p95, revisit rate, backlog at end.
2. Backlog over time, one line per scenario.
3. Paid hours lost by cause, baseline versus AI lever, including quality
   rework and the administrative tail.
4. Distribution of changes per team-week for each scenario.
5. Nights per change and revisit rate, baseline versus AI lever.
6. A download button for the per-run CSV and for the headline table as CSV.

Every number on screen is labeled as a planning assumption until an event
log is loaded; when one is loaded, the caption says so and lists any
parameters still at default. A NiceGUI user-simulation test opens the page,
presses Run and checks the headline renders.

### 2.4 Tests: `tests/test_change_event_sim.py` (with `tests/conftest.py`)

pytest, seeded:

- conservation holds on every run
- two teams close at least as many changes as one team, on the Monte Carlo
  median
- the AI lever does not increase paid hours lost per closed change, on the
  Monte Carlo median
- the AI lever never changes tool-time draws for a given site (same seed,
  same per-site tool time)
- `fit_from_event_log` on the synthetic example returns a valid parameter
  set, and `missing` contains only the documented non-observable parameters
  (arrival rate, backlog, rates, sigmas, implementation-engineer prep)
- the site-class mix is validated to sum to 1 and a logical site never
  draws travel, access or hardware events
- the storm simulator still imports and runs one iteration unchanged

### 2.5 Housekeeping

- Pin `requirements.txt` to the versions in the local environment (simpy
  4.1.1, streamlit 1.55.0, pandas 2.2.3, numpy 2.2.6, matplotlib 3.10.8,
  seaborn 0.13.2, nicegui 3.9.0); add `pytest`.
- README: add a "Change Event Capacity Simulator" section mirroring the
  storm section, with how to run both apps, and fix the directory path.
- Commit `portfolio.md`. Regenerate it with the nth-portfolio-builder skill
  if time allows; otherwise add a dated note at the top.

## 3. Constraints

- No utility, integrator, program, product, or document-repository name
  anywhere in the repo. No personal names, phone numbers or email addresses.
  Generic role names only (field engineer, bridge lead, implementation
  engineer, operations center, renewables operations center).
- Planning-assumption defaults are labeled as such in code and UI. Do not
  present them as benchmarks. The rates in 2.1 are placeholders.
- Do not touch the storm simulator's behavior. Additive only.
- Session edits only `power_utility`. Report back to `nth_program` by
  telling the PM session what shipped; do not edit `nth_program` from here.
- Sized for one session. If 2.2 or 2.5 would push past that, ship 2.1, 2.3
  and 2.4 and leave a `TODO.md`.

## 4. Definition of done

- [ ] `change_event_sim.py` runs the three default scenarios with a seed
      and prints the headline table from the command line.
- [ ] `python 3_grid_simulation/change_event_app.py` shows the six panels
      and the downloads work.
- [ ] `pytest` passes; the seven tests in 2.4 exist.
- [ ] Synthetic event log loads through `fit_from_event_log` and the UI
      caption changes.
- [ ] Storm app still runs (after `pip install -r requirements.txt`).
- [ ] README updated; requirements pinned; `portfolio.md` committed.
- [ ] Committed on `main` and pushed.

## 5. Report back

Give the PM session: commit hash, which items shipped, the headline table
for the three default scenarios, and anything learned that should change the
concept doc's ROI section. Two things the PM session must settle before the
ROI section is final: who the paying client is (the integrator's program or
the utility), because that decides whether the benefit is bridge-lead hours
and revisit nights or escort hours and days on end-of-life hardware; and the
real arrival rate of change-ready sites, because the default of 4 per week
against one team is a guess. The PM session will flip `power_utility` to
active in `portfolio.json` and update the concept doc.
