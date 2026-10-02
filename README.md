# Operational AI & Digital Twins for Power & Utilities

### **Executive Summary**
This repository demonstrates a "Full-Stack" approach to modernizing Utility operations, bridging the gap between **Physical Logistics (OT)** and **Agentic AI (IT)**.

It serves as a Proof of Concept (POC) for three core capabilities required by modern Data Architects in the Energy sector:
1.  **Edge AI Infrastructure:** A containerized, air-gapped stack (Ollama/Qdrant) for secure on-premise deployment.
2.  **Agentic Knowledge Retrieval:** A RAG pipeline that turns static maintenance manuals into interactive "Field Tech Copilots."
3.  **Operational Simulation:** Discrete Event Simulation (DES) engines to stress-test logistics and resource adequacy, for storm events and for scheduled change-event work.

### **Architecture Overview**
* **Infrastructure:** Self-hosted `n8n` orchestration layer backed by `Qdrant` vector storage.
* **Simulation Engine:** Python `SimPy` for process modeling.
* **Deployment:** Dockerized for Edge/Gateway devices (e.g., NVIDIA DGX Spark, Jetson).

---

### **1. The "Walk-In" Edge Solution**
Located in `/01_edge_infrastructure`
A `docker-compose` configuration that deploys a secure, offline-capable AI brain. Designed to sit inside the substation control room firewall.

### **2. Field Tech Copilot (RAG)**
Located in `/02_agentic_copilot`
An Agentic workflow that ingests NERC reliability standards and OEM manuals to provide instant, cited technical support to field crews.
* **Key Feature:** "Safety-First" System Prompts that prioritize LOTO (Lock-Out/Tag-Out) warnings before technical steps.

### **3. Storm Response Simulator**
Located in `/3_grid_simulation`
A Python-based Digital Twin that models repair crew logistics during outage events. It calculates "Mean Time to Restoration" (MTTR) based on variable crew availability and staging locations.

**Run it:**
```
pip install -r 3_grid_simulation/requirements.txt
streamlit run 3_grid_simulation/streamlit_app.py
```

### **4. Change Event Capacity Simulator**
Located in `/3_grid_simulation`
A SimPy Monte Carlo model of network change-event teams (field engineer on site, bridge lead, implementation engineer) working evening change windows at utility sites. It compares three scenarios side by side: one team as-is, one team with an AI lever that removes non-tool time (packet validation, access confirmation, chat-to-report transcription, photo QA), and two teams.
* **Outputs:** changes and devices per team-week, wrench-time ratio, paid hours lost by cause (five runbook escalation paths, quality rework, administrative tail, idle), revisit rate, nights per change, backlog over time, end-of-life exposure in calendar days, cost per change and per device.
* **Site classes:** standard, renewables (per-device operations-center calls), large/complex, logical (no field engineer).
* **Field-data intake:** `fit_from_event_log()` re-parameterizes the model from an event-log CSV (`data/event_log_template.csv`); a synthetic example ships in `data/example_synthetic_event_log.csv`.
* **Every default is a planning assumption**, labeled as such in code and UI. None is a benchmark.

**Run it:**
```
pip install -r 3_grid_simulation/requirements.txt
python 3_grid_simulation/change_event_sim.py --runs 100 --seed 42        # headline table on the command line
python 3_grid_simulation/change_event_sim.py --event-log 3_grid_simulation/data/example_synthetic_event_log.csv
python 3_grid_simulation/change_event_app.py                              # NiceGUI app on http://localhost:8081
pytest                                                                    # test suite (tests/)
```
