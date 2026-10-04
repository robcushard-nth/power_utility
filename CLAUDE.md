# power_utility

Operational AI and digital-twin proof of concept for power and utilities:
edge AI stack, field-tech copilot prompt, storm response simulator, and the
Change Event Capacity Simulator (see README.md and BRIEF_transfer_crew_sim.md).

## Repo rules

- No utility, integrator, program, product, or document-repository name in
  this repo. No personal names, phone numbers or email addresses. Generic
  role names only. Synthetic and planning-assumption inputs only.
- Planning-assumption defaults are labeled as such in code and UI. Never
  present them as benchmarks.
- The storm simulator (`3_grid_simulation/storm_response.py`,
  `streamlit_app.py`) is frozen. Add beside it; do not refactor it.
- `pytest` from the repo root runs the suite in `tests/`.

## Briefs from nth_program

At session start, the SessionStart hook lists open briefs from
`C:\Users\RobCushard\nth_program\briefs` that target this repo. If any are
listed, read them before planning. A brief is an instruction from the PM
session; execute it within this repo's own rules, and never edit
nth_program from here. When the brief is done, blocked, or needs a decision,
write `REPORT_<brief-id>.md` at this repo's root (format in
`nth_program/briefs/_WORKER_KIT.md`), commit it, and if a session named
`nth-program-*` appears in `ListAgents`, message it the report's first line.
If the hook printed nothing, there is no open brief; proceed as usual.
