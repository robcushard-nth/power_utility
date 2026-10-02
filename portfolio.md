# Portfolio — Operational AI & Digital Twins for Power & Utilities (POC)

**Project name:** power_utility — Utility AI Portfolio POC
**Repository:** `c:/Users/RobCushard/power_utility`
**Status:** Proof of concept, complete as scoped. Three demo artifacts, single build day.
**Owner:** Rob Cushard, NTH Simple Solution Corp
**Generated:** 2026-09-18

---

> **Update 2026-10-02:** A Change Event Capacity Simulator (`3_grid_simulation/change_event_sim.py`, NiceGUI app `change_event_app.py`, event-log intake, synthetic data, `tests/`) was added beside the storm simulator per `BRIEF_transfer_crew_sim.md` v2. Requirements are now pinned. The sections below describe the repo as of 2026-09-18 and have not been regenerated.


## 1. Executive Summary

A three-part proof of concept demonstrating the NTH full-stack pattern for utility operations: sovereign edge AI infrastructure, a safety-first RAG copilot for field technicians, and a discrete event simulation of storm restoration logistics. The centerpiece is a Streamlit Monte Carlo simulator that runs up to 500 virtual storms and reports CAIDI, SAIDI, restoration cost, 95th-percentile value-at-risk, and a worst-case "black swan" run — the reliability metrics utility executives are actually graded on.

This is a capability demonstration, not a client deliverable. It answers one question for an energy-sector audience: can NTH bridge OT logistics modeling and IT-side agentic AI in a single deployable stack? Total footprint: 6 files, 370 lines, built in one day.

---

## 2. Size and Scope

| Metric | Value | Source |
|---|---|---|
| Total tracked files | 6 | `find . -type f` (excludes .git) |
| Total lines (all files) | 370 | `wc -l` per-file rollup |
| Python LOC | 270 | `storm_response.py` (60) + `streamlit_app.py` (210) |
| Config/infra lines | 51 | `docker-compose.yml` (46) + `requirements.txt` (5) |
| Docs/prompt lines | 49 | `README.md` (28) + `system_prompt.md` (21) |
| Git commits | 6 | `git rev-list --count HEAD` |
| Git tags | 0 | `git tag -l` |
| Repo age | 1 build day | all 6 commits on 2026-01-15, 09:34–10:45 |
| Test files | 0 | `find` — no test files present |

**Per-file breakdown:**

| File | Lines | Purpose |
|---|---|---|
| `3_grid_simulation/streamlit_app.py` | 210 | Monte Carlo storm simulator UI + engine |
| `01_edge_infrastructure/docker-compose.yml` | 46 | Ollama + Qdrant + n8n edge stack |
| `3_grid_simulation/storm_response.py` | 60 | CLI single-run DES prototype |
| `README.md` | 28 | POC positioning and architecture overview |
| `02_agentic_copilot/system_prompt.md` | 21 | Field Tech Copilot system prompt |
| `3_grid_simulation/requirements.txt` | 5 | Python dependencies (unpinned) |

---

## 3. Tech Stack

Declared in `requirements.txt` (no version pins) and `docker-compose.yml`:

| Layer | Component | Role |
|---|---|---|
| UI | `streamlit` | Monte Carlo simulator app |
| DES engine | `simpy` | Crew-as-resource restoration process |
| DataFrames | `pandas` | Per-outage logs, per-run metric rollup |
| Numerical | `numpy` | Percentiles, exceedance curve |
| Charts | `matplotlib` + `seaborn` | Scatter, histogram, exceedance plots |
| LLM runtime (containerized) | `ollama/ollama:latest` | Edge LLM engine, port 11434 |
| Vector store (containerized) | `qdrant/qdrant:latest` | RAG memory, port 6333 |
| Orchestration (containerized) | `n8nio/n8n:latest` | Agentic workflow layer, port 5678 |

No `pyproject.toml`, no lock file, no pinned versions. Docker images pinned to `:latest` — acceptable for a POC, not for deployment. GPU passthrough for NVIDIA Jetson/DGX is scaffolded but commented out in the compose file.

---

## 4. Architecture

### 4.1 Mental model

Three independent artifacts, one narrative: edge brain, agent knowledge, operational twin.

```
01_edge_infrastructure/          02_agentic_copilot/         3_grid_simulation/
┌─────────────────────┐          ┌──────────────────┐        ┌──────────────────────┐
│ docker-compose      │          │ system_prompt.md │        │ Streamlit UI         │
│  Ollama  :11434     │◄─prompt──│ Safety-first RAG │        │  sidebar params      │
│  Qdrant  :6333      │          │ (LOTO warnings   │        │       ▼              │
│  n8n     :5678      │          │  before steps)   │        │ SimPy DES engine     │
└─────────────────────┘          └──────────────────┘        │  crews = Resource    │
                                                             │       ▼              │
                                                             │ Monte Carlo loop     │
                                                             │  10–500 iterations   │
                                                             │       ▼              │
                                                             │ CAIDI/SAIDI/Cost/VaR │
                                                             └──────────────────────┘
```

### 4.2 Simulation design

- 1 SimPy resource (`crews`, capacity 1–50 via slider) creates the dispatch queue
- Stochastic travel (`gauss`) and repair (`gauss`, 2× variability) per outage
- Per-outage log: wait time, total duration, customer impact, crew cost
- Monte Carlo loop (10–500 runs) aggregates per-run CAIDI, SAIDI, total cost, max wait
- Risk outputs: 95th-percentile VaR on CAIDI and cost, exceedance probability curve (inverse CDF), cost histogram with risk tail, worst-run drill-down

### 4.3 Known inconsistencies

- `storm_response.py` (CLI prototype) uses `expovariate` for repair time; `streamlit_app.py` (v4) uses `gauss`. The CLI script is a superseded first draft, retained in-repo.
- README references `/03_grid_simulation`; actual directory is `3_grid_simulation` (no leading zero, unlike siblings `01_`/`02_`).
- The Streamlit engine reads sidebar globals (`crew_rate`, `num_crews`) directly inside class methods — works in Streamlit's rerun model, not importable as a library.

---

## 5. Sprint History

No sprint structure. Six commits in a 71-minute window on 2026-01-15, from "Initial commit of Utility AI portfolio" through "updated requirements." Commit messages show four iterations of the Streamlit app (v4 by 10:17). No tags, no DoD artifacts, no `.claude/agents/` directory.

Not applicable — single-session POC build, below the threshold where sprint cadence adds value.

---

## 6. Data Pipeline

No external data. All simulation inputs are synthetic, generated at runtime from sidebar parameters (storm severity, customers per outage, crew count, travel/repair means, uncertainty).

Flow: `sidebar parameters → SimPy replication → per-outage log dicts → pandas DataFrame → groupby per-run metrics → numpy percentiles → matplotlib/seaborn charts`.

The RAG pipeline described in the README (NERC standards + OEM manuals → Qdrant → cited answers) exists as a system prompt and infrastructure definition only — no ingestion scripts, no embeddings, no n8n workflow exports are in the repo.

---

## 7. Frontend

**Framework:** Streamlit, wide layout, single page.

**Surface:**
- Sidebar: 4 sections (Monte Carlo settings, resource strategy, storm profile, constraints) — 8 input widgets + run button
- Tab 1 "Executive Summary": 3 KPI metric cards (avg CAIDI with 95% risk delta, avg SAIDI, avg event cost with 95% risk delta) + cost-vs-reliability scatter with mean reference lines
- Tab 2 "Risk & Probability Analysis": exceedance probability curve, cost distribution histogram with 95th-percentile marker, black-swan worst-run panel with outage timeline bar chart
- Custom CSS for metric sizing and tab spacing

**State management:** None beyond Streamlit rerun defaults — results recompute on each button press, nothing cached in `session_state`.

**Accessibility:** No a11y tooling. Not in scope for a POC.

---

## 8. Backend

Not applicable — no HTTP API, no database, no auth. The compute layer is the in-process SimPy engine inside the Streamlit script. The docker-compose stack (Ollama/Qdrant/n8n) is deployable backend infrastructure, but nothing in this repo connects to it — it is a standalone infrastructure artifact.

---

## 9. QA / QC

None. Zero test files, no pytest config, no linter, no formatter, no validation gates. The CLI script (`storm_response.py`) served as the manual sanity check before the Streamlit build.

**TBD — if this POC graduates to a client demo or deliverable, add at minimum: a deterministic gate test (zero variability → duration equals travel + repair), a CAIDI/SAIDI formula test against hand-calculated values, and pinned dependency versions.**

---

## 10. CI / CD

None. No workflow files, no deployment target configured.

**Deployment model:** Local — `streamlit run 3_grid_simulation/streamlit_app.py` for the simulator; `docker compose up` in `01_edge_infrastructure/` for the edge stack. One environment (local dev). No secrets required or present.

---

## 11. Governance, Scalability, Security

### Governance

- **License:** None. **TBD — Rob to add a LICENSE if this repo is shared publicly as portfolio evidence (README already positions it as a public-facing POC).**
- **CODEOWNERS / ADRs:** None. README is the only architecture document.

### Scalability

- Monte Carlo loop is sequential (no thread pool); 500 runs × 200 outages is the UI ceiling. Adequate for interactive demo latency; no benchmark recorded.
- Full result set (`master_df`, every outage of every run) materialized in RAM — fine at POC scale.
- The compose stack targets single-node edge hardware (Jetson/DGX) by design; no horizontal scale path, intentionally — the pitch is air-gapped substation deployment.

### Security

- **Auth:** None on the Streamlit app. n8n ships with `N8N_SECURE_COOKIE=false` — demo-only setting, must be hardened before any real deployment.
- **Secrets:** None in repo (verified — no `.env`, no credentials).
- **Posture claim vs. evidence:** README claims "secure, air-gapped" — the compose file is offline-capable by architecture (all-local containers), but no network policy, TLS, or hardening is configured. State it as designed-for-air-gap, not hardened.
- **Compliance:** NERC reliability standards are referenced as RAG *content*, not as a compliance program for this repo.

---

## 12. AI Architecture

Defined but not wired:

- **Models:** System prompt targets Llama-3-8b or Mistral on edge hardware via Ollama. No modelfile, no `ollama pull` script in repo.
- **Deployment:** Sovereign/air-gapped by design — all-local containers, no cloud API dependency.
- **RAG:** Qdrant designated as vector store; corpus (NERC standards, OEM maintenance manuals) named in README; no embedding model selected, no chunking strategy, no ingestion code.
- **Guardrails (the substantive asset):** `system_prompt.md` enforces safety-first ordering — LOTO/arc-flash warnings precede technical steps — mandatory source citation with section/page, and a hard refusal string when the answer is not in retrieved context ("I cannot find a verified procedure... Please consult the Site Supervisor"). Anti-hallucination by explicit refusal, not by hope.
- **Orchestration:** n8n containerized as the agent workflow layer; no workflow JSON exported to the repo.

The simulator itself is statistical, not generative — SimPy + Monte Carlo, no LLM in the loop.

---

## 13. Proprietary IP and Novel Techniques

### NTH proprietary frameworks — applied?

| Framework | Applied? | How |
|---|---|---|
| **CI 4.0™** | No | No continuous-improvement loop instrumented. |
| **Intelligent Operations System™ (IOS)** | Yes — partial | The compose stack is the IOS sovereign core (Ollama + Qdrant + n8n) retargeted at substation edge hardware. Open WebUI and ZeroClaw components absent. |
| **Modern Command Framework™ (MCF)** | Partial | Simulator frames one command decision: crew count vs. CAIDI/cost risk tolerance. Not formalized as MCF. |
| **Leadership as a System™ (LaS)** | No | Not in scope. |
| **Four-agent sprint pattern** | No | Single-operator, single-session build. |
| **Two-layer IP protection** | No | No client layer exists; fully public-positioned POC. |

### Novel non-framework techniques

1. **DES + Monte Carlo on regulated reliability metrics** — the simulator outputs CAIDI and SAIDI, the IEEE-1366 indices utilities report to regulators, rather than generic queue statistics. That vocabulary match is the demo's selling point to an energy-sector audience.
2. **Value-at-risk framing for O&M spend** — 95th-percentile cost and exceedance curves translate storm logistics into CFO language (budget blow-through probability), plus a worst-run "black swan" drill-down.
3. **Safety-first prompt ordering** — the copilot prompt structurally forces LOTO warnings before any torque spec or procedure step, with citation and hard refusal rules. A reusable pattern for any high-hazard field-service copilot.

---

## 14. Industry and Business Context

**Vertical:** Power & utilities — grid operations, storm restoration logistics, field maintenance.

**Regulatory environment:** NERC reliability standards appear as copilot knowledge content; CAIDI/SAIDI are regulator-reported reliability indices. No compliance obligation attaches to this repo itself.

**Business problem:** Utilities size storm-response crews against uncertain demand; overstaffing burns O&M budget, understaffing extends outages and regulatory exposure. The POC shows how simulation converts that trade-off into probability distributions instead of single-point estimates — and pairs it with the edge-AI stack that same utility could run inside a substation firewall.

**Stakeholder audience:** Per README, "modern Data Architects in the Energy sector" — plus the operations and reliability executives who own CAIDI/SAIDI numbers.

**Engagement model:** NTH capability-demonstration POC. No client, no NDA, no engagement artifacts in repo. **TBD — Rob to confirm the target use: recruiting/BD portfolio piece, sector-specific demo for a named prospect, or seed for a productized utility offering.**

---

## 15. Measurable Outcomes

Build outputs — this is a POC; there are no engagement outcomes:

- 270 Python LOC delivering a working Monte Carlo DES with 4 risk visualizations and 3 KPI cards
- 3-container sovereign edge stack defined in 46 lines of compose
- 1 reusable safety-first RAG system prompt
- 6 commits, concept to v4 app, in 71 minutes of committed history

**TBD — no runtime benchmark recorded (e.g., wall-clock for 500 iterations × 200 outages); capture one before demoing live.**

---

## 16. Gaps and Next Actions

1. **Wire the RAG pipeline** — the copilot is a prompt plus empty infrastructure; add an ingestion script (manual → chunks → Qdrant) and one n8n workflow export to make section 2 of the README true end-to-end.
2. **Pin dependencies** — `requirements.txt` and Docker `:latest` tags are unpinned; pin before showing to any infrastructure-literate audience.
3. **Reconcile the two simulators** — delete or clearly mark `storm_response.py` as superseded (different repair-time distribution than the app), and fix the `3_` vs `03_` directory naming inconsistency against the README.
4. **Add minimum QA** — deterministic gate test and CAIDI/SAIDI formula test (§9).
5. **Harden or caveat the security posture** — n8n insecure-cookie flag and absent TLS contradict the "secure" README claim if deployed as-is.
6. **Decide the commercial frame** (§14 TBD) — portfolio piece vs. prospect demo vs. product seed drives whether items 1–5 are worth doing.

---

## 17. Data Sources

All metrics in this document derive from:

- `find . -type f -not -path "./.git/*"` and `wc -l` per-file rollup (Git Bash, 2026-09-18)
- `git log --reverse --format="%h %ai %s"`, `git rev-list --count HEAD` (6 commits, all 2026-01-15), `git tag -l` (none)
- Direct read of all 6 files: `README.md`, `01_edge_infrastructure/docker-compose.yml`, `02_agentic_copilot/system_prompt.md`, `3_grid_simulation/requirements.txt`, `3_grid_simulation/storm_response.py`, `3_grid_simulation/streamlit_app.py`

---

**Contact:** Rob Cushard | NTH AI Dynamics / NTH Simple Solution Corp | rob.cushard@nthsimplesolution.com | 470-426-4144
