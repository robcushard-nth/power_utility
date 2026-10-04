---
brief: 2026-10-01-power-utility-transfer-crew-sim
status: done
commit: b23781f
date: 2026-10-04
---

# Report — Change Event Capacity Simulator (brief v2 MVP)

**Brief revised locally before build (v2, 2026-10-01).** Version 1 modeled a
seven-person pole transfer crew. The client's runbook showed the work is
network change events: a field engineer on site, an implementation engineer
remote, a bridge lead coordinating through a change ticket and chat room.
v2 relabeled every wait cause to a runbook escalation path, added a quality
rework loop, an administrative tail and four site classes, replaced ten-hour
days with evening change windows, replaced the hand time study with an
event-log schema, and switched the UI from Streamlit to NiceGUI (2026-10-02).
Module names changed to `change_event_*`; the brief file name was kept.

## What shipped (by brief item)

- **2.1 Engine** `3_grid_simulation/change_event_sim.py`: SimPy, window-minute
  clock with calendar mapping, Poisson arrivals plus backlog, site classes,
  five wait causes with abort shares and immunity, rework loop, admin tail,
  AI lever, common random numbers per site, Monte Carlo wrapper, conservation
  check, CLI headline table.
- **2.2 Intake** `data/event_log_template.csv`, `fit_from_event_log()`,
  synthetic `data/example_synthetic_event_log.csv` (80 sites, 93 visits).
  Fit recovers parameters near the assumptions; only documented
  non-observable parameters stay at default.
- **2.3 UI** `3_grid_simulation/change_event_app.py` (NiceGUI, port 8081):
  six panels, custom fourth scenario, event-log upload, CSV downloads,
  planning-assumption caption that changes when a log is loaded.
- **2.4 Tests** `tests/test_change_event_sim.py` + `conftest.py`: 8 tests
  including a NiceGUI user-simulation test; all pass (about 2 s).
- **2.5 Housekeeping** requirements pinned (+nicegui, pytest), README section
  4 and path fix, `portfolio.md` committed with a dated note, `.gitignore`.
- Committed and pushed on `main`: 297d8a7 (work), b23781f (cache cleanup).

## What did not ship

- `portfolio.md` was not regenerated with the portfolio-builder skill; a
  dated note at the top stands in, per the brief's fallback.
- The brief's fit test was reworded: `missing` may contain only parameters a
  per-visit log cannot observe (arrival rate, backlog, rates, sigmas).

## Headline (100 runs, seed 42, planning assumptions, median)

| Metric | 1 team baseline | 1 team + AI lever | 2 teams baseline |
|---|---|---|---|
| Changes / team-week | 3.12 | 3.31 | 2.81 |
| Wrench-time ratio | 0.20 | 0.26 | 0.19 |
| Cost / change ($) | 3,893 | 3,374 | 4,193 |
| EOL exposure p95 (days) | 95 | 90 | 60 |
| Revisit rate | 0.27 | 0.18 | 0.25 |
| Backlog at end (16 wk) | 40 | 37 | 0 |

## For the concept doc's ROI section

- The administrative tail dominates non-tool cost: about 400 paid hours per
  team over 16 weeks versus about 70 hours across the five on-site wait
  causes. The AI case rests on prep, reporting and uploads, not on the night.
- The AI lever cuts cost per change about 13% and lifts wrench time from
  0.20 to 0.26, but one team still falls behind 4 change-ready sites a week.
  Headcount decides end-of-life exposure; AI decides cost per change.
- Two teams clear the backlog by week 8 and then idle about a third of the
  time, which is why their cost per change is highest.
- The arrival rate (4/week) and the rates ($95/$85/$125) are guesses and
  drive everything above.

## Open questions for Rob

1. Who pays: the integrator's program (benefit = bridge-lead hours, revisit
   nights) or the utility (benefit = escort hours, ops-center load, days on
   end-of-life hardware)?
2. Real arrival rate of change-ready sites and the current revisit rate.
3. Can chat-room exports be obtained so `fit_from_event_log` runs on real
   data instead of the synthetic file?
