# Operational AI & Digital Twins for Power & Utilities

### **Executive Summary**
This repository demonstrates a "Full-Stack" approach to modernizing Utility operations, bridging the gap between **Physical Logistics (OT)** and **Agentic AI (IT)**.

It serves as a Proof of Concept (POC) for three core capabilities required by modern Data Architects in the Energy sector:
1.  **Edge AI Infrastructure:** A containerized, air-gapped stack (Ollama/Qdrant) for secure on-premise deployment.
2.  **Agentic Knowledge Retrieval:** A RAG pipeline that turns static maintenance manuals into interactive "Field Tech Copilots."
3.  **Operational Simulation:** A Discrete Event Simulation (DES) engine to stress-test logistics and resource adequacy during storm events.

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
Located in `/03_grid_simulation`
A Python-based Digital Twin that models repair crew logistics during outage events. It calculates "Mean Time to Restoration" (MTTR) based on variable crew availability and staging locations.