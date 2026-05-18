# ChainGuard-Core — Build Plan

> A concrete, sequenced plan for the builder LLM. Read alongside [`README.md`](./README.md) (product spec) and `system-prompt.md` (operating principles).
>
> **The README is the *what*. This document is the *how*. The system prompt is the *how to think*.**

---

## How to Use This Document

1. **Work tasks in strict order.** Do not skip ahead or merge phases.
2. **One Pull Request per task.** Every task requires its own isolated branch, PR, and green CI before being squashed into `main`.
3. **Every task has an Acceptance section.** Code is not "done" until each line passes.
4. **If blocked by an unanswered decision, stop and ask.** Do not invent system behavior.
5. **Out-of-scope items at the bottom are intentionally excluded** from the MVP to prevent scope creep.

---

## Source of Truth

| File | Role |
|------|------|
| `README.md` | Product spec, quantitative/fintech parameters, non-negotiables |
| `system-prompt.md` | Builder LLM operating principles |
| `build-plan.md` | This file — sequenced tasks and acceptance criteria |
| `src/core_engine.cpp` | Core low-latency streaming feature-engineering engine (C++20) |

> If these documents conflict, **the README wins**.

---

## Pre-flight Checklist

- [ ] Node.js **20+** and pnpm **9+**
- [ ] GCC/Clang with **C++20** support
- [ ] CMake **3.22+**
- [ ] Local **Minikube** or Docker Desktop with Kubernetes enabled
- [ ] **Helm v3+**
- [ ] `.env.local` populated with:
  ```env
  POLYGON_API_KEY=...
  OPENAI_API_KEY=sk-...    # or local Ollama setup
  ```

Verify before Phase 0:

```bash
node --version
g++ --version
cmake --version
kubectl version
helm version
```

---

## Phase 0 — Monorepo & Core CI/CD Infrastructure
**Window:** Day 1
**Goal:** Establish an enterprise-grade monorepo structure, strict git workflows, and automatic linting/validation across both C++ and TypeScript codebases.

### Task 0.1 — Monorepo Scaffolding & Git Rules
**Deliverable:** A remote private repository with branch protections enabled and project directories cleanly segregated.

**Steps**
- Initialize the target monorepo layout:
  ```
  ├── src/                # Ingestion & Feature Engineering Engine (C++20)
  ├── web/                # React / Next.js 15 Analytical Control Board
  ├── airflow/            # Airflow DAGs and MLOps automation scripts
  ├── k8s/                # Helm charts, KEDA manifests, K8s configs
  └── CMakeLists.txt      # Root C++ CMake configuration
  ```
- Establish a global `.gitignore` covering `node_modules/`, `.next/`, `build/`, `bin/`, `.env*`, `*.log`.
- Generate GitHub pull request templates at `.github/pull_request_template.md`.

**Acceptance**
- Project directories successfully established.
- Direct pushes to `main` are strictly blocked via GitHub Branch Protection rules.
- Pull Requests require at least 1 status check approval and linear history to merge.

---

### Task 0.2 — Multi-Language CI Pipeline
**Deliverable:** A functional GitHub Actions configuration (`.github/workflows/ci.yml`) that lints, builds, and verifies both frontend and backend directories on every PR.

**Steps**
- Configure formatting tools: **Prettier/ESLint** for React, **clang-format** for C++.
- Build `.github/workflows/ci.yml` with jobs for:
  - `frontend-ci`: runs `pnpm install`, `pnpm lint`, `pnpm typecheck`, `pnpm build`.
  - `cpp-ci`: sets up CMake, installs `librdkafka`, compiles the codebase with `-Wall -Wextra -Werror` for zero-warning enforcement.

**Acceptance**
- Creating a PR with unformatted C++ or broken TypeScript instantly fails the automated checks.
- Merges are locked out until all status checks turn green.

### ✅ Phase 0 Definition of Done
- Branch protection is active, the monorepo is scaffolded, and the dual-language CI pipeline correctly handles test failures.
- **Stop here.** Request human review and PR approval before Phase 1.

---

## Phase 1 — Local Infrastructure, Storage & Cluster Bootstrap
**Window:** Day 2
**Goal:** Launch a local, robust Kubernetes environment hosting transactional storage layers (PostgreSQL), the vector cache layer, and message brokers via Helm — demonstrating bare-metal infra mastery.

### Task 1.1 — Kubernetes, Kafka & PostgreSQL Deployment
**Deliverable:** A local cluster running containerized database instances and a message broker with ACID compliance.

**Steps**
- Spin up Minikube with higher resource thresholds:
  ```bash
  minikube start --cpus=4 --memory=8192
  ```
- Install Apache Kafka via the Bitnami Helm registry:
  ```bash
  helm install chain-kafka bitnami/kafka --set listeners.client.protocol=PLAINTEXT
  ```
- Install a local PostgreSQL cluster instance for ACID-compliant transaction logs, configuration records, and offline pipeline metadata:
  ```bash
  helm install chain-db bitnami/postgresql
  ```

**Acceptance**
- `kubectl get pods` displays Running states for both `chain-kafka` and `chain-db`.
- Database authentication tests from a local terminal client execute successfully.

---

### Task 1.2 — Vector Layer Initialization (Qdrant / pgvector)
**Deliverable:** A functioning vector database container layer initialized within the cluster network to host Agentic RAG structures.

**Steps**
- Deploy an isolated vector database pod (Qdrant or a standalone `pgvector`-enabled instance) via a Kubernetes manifest at `k8s/vector-db.yaml`.
- Expose internal endpoints securely across the local K8s domain (`vector-db.default.svc.cluster.local`).

**Acceptance**
- Health-check queries to the internal vector DB service return **200 OK**.
- Vector collections can be successfully initiated and torn down via sample Python validation scripts.

### ✅ Phase 1 Definition of Done
- Relational, vector, and streaming broker infrastructure layers run smoothly inside the local cluster.
- **Stop here.** Request human review and PR approval before Phase 2.

---

## Phase 2 — Low-Latency C++ Engine & Live Ingestion
**Window:** Days 3–6
**Goal:** Build the foundational high-frequency ingestion engine in C++20. It must hook into real-time financial WebSocket streams, parse them with hardware acceleration, compute sliding quantitative features, and push them to Kafka.

### Task 2.1 — CMake Project & Kafka Integration
**Deliverable:** A compiled C++ project structure linked with native `librdkafka` and asynchronous networking clients.

**Steps**
- Structure `CMakeLists.txt` to include threads and find system packages for `librdkafka` and `ssl`.
- Author `src/main.cpp` to spin up a native Kafka producer instance targeting a configurable broker address.

**Acceptance**
- `cmake -B build -S . && cmake --build build` generates a binary cleanly.
- Running the binary initializes a verified test link to a local Kafka node without packet drops.

---

### Task 2.2 — Asynchronous Ingestion & SIMD JSON Parsing
**Deliverable:** A highly efficient ingestion thread that processes live financial transactions via `simdjson`.

**Steps**
- Implement a WebSocket client loop using **Boost.Asio / Boost.Beast** targeting Polygon.io or a high-frequency mock transaction API.
- Use `simdjson::ondemand` to parse incoming JSON directly into native, tightly padded structs (`TickData`) utilizing hardware SIMD lanes.

**Acceptance**
- Engine handles a simulated burst of **20,000+ tick payloads/sec** with sub-millisecond thread execution overhead.
- Intentionally malformed payloads degrade gracefully through validation rather than crashing via segfault.

---

### Task 2.3 — Lock-Free Real-Time Feature Store
**Deliverable:** In-memory sliding metric calculation executed over lock-free circular ring buffers.

**Steps**
- Build a thread-safe, lock-free ring buffer structure using `std::atomic` pointers.
- Implement streaming feature calculations:
  - **Order Flow Imbalance (OFI):** microsecond shifts in buy/sell pressure over moving intervals.
  - **Realized Volatility:** sliding standard deviation windows tracking market volatility breaks.
- Serialize calculated feature matrices into binary arrays and broadcast them to a dedicated `financial-features` Kafka topic.

**Acceptance**
- Codebase contains **zero mutex locks** or thread-blocking calls in the critical calculation pathway.
- Profiling confirms feature frame generation benchmarks drop **below 50 microseconds**.

### ✅ Phase 2 Definition of Done
- The C++ background process runs continuously, ingesting real-world API data, executing microsecond feature calculations, and piping outcomes directly to Kafka.
- **Stop here.** Request human review and PR approval before Phase 3.

---

## Phase 3 — Containerization & Event-Driven Autoscaling
**Window:** Days 7–9
**Goal:** Package the C++ engine into a highly optimized container, deploy it to Kubernetes, and establish automated infrastructure scaling using KEDA.

### Task 3.1 — Multi-Stage Lean Containerization
**Deliverable:** A hardened, ultra-lightweight Docker image for the C++ streaming engine.

**Steps**
- Write a multi-stage `Dockerfile`:
  - **Stage 1:** comprehensive developer toolchain image to compile static binaries.
  - **Stage 2:** strip symbols and copy the final binary into a minimal `distroless/cc` runtime.

**Acceptance**
- Final target image footprint **< 150 MB**.
- Initializing the container outputs operational telemetry logs to stdout.

---

### Task 3.2 — Kubernetes Deployment & KEDA Scaling
**Deliverable:** Helm deployment templates and scaling configurations that auto-scale processing replicas during high-volatility events.

**Steps**
- Draft `k8s/deployment.yaml` to inject env vars for Kafka broker and PostgreSQL connectivity.
- Deploy **KEDA** (Kubernetes Event-driven Autoscaling) via Helm.
- Build a `ScaledObject` manifest targeting the C++ deployment that monitors Kafka topic partition consumer lag.

**Acceptance**
- Flooding the Kafka broker with 50,000 entries triggers KEDA to scale the C++ deployment out to handle the lag.
- Once the backlog clears, pod counts scale back down to base configuration.

### ✅ Phase 3 Definition of Done
- Core ingestion infrastructure executes inside isolated Kubernetes pods, reacting dynamically to stream saturation.
- **Stop here.** Request human review and PR approval before Phase 4.

---

## Phase 4 — Python Analytics, MLOps Pipelines & Agentic Workflows
**Window:** Days 10–12
**Goal:** Consume calculated features from Kafka, execute high-speed ML anomaly classification, orchestrate nightly MLOps maintenance routines via Apache Airflow, and configure the 3-tier Agentic evaluation layer.

### Task 4.1 — Fast Inference Classifier & MLOps Airflow DAG
**Deliverable:** A streaming Python classification consumer paired with an Airflow DAG that performs data validation and leakage-free retraining.

**Steps**
- Write a Python service that reads features from Kafka and passes them to a pre-trained **LightGBM** binary classifier to generate an anomaly score in `[0.0, 1.0]`.
- Configure Apache Airflow to run on Kubernetes via the `KubernetesPodOperator`.
- Build a daily MLOps DAG at `airflow/dags/retraining_pipeline.py` that:
  1. Aggregates daily historical feature logs from PostgreSQL.
  2. Performs validation checks.
  3. Applies **Purged K-Fold Cross-Validation** to retrain LightGBM without time-series data leakage.

**Acceptance**
- Injected market shocks correctly trigger the LightGBM classifier to produce an immediate high-risk anomaly payload.
- Triggering the Airflow DAG processes retraining loops cleanly inside isolated, ephemeral K8s workers, writing optimized models back to the registry.

---

### Task 4.2 — 3-Tier Multi-Agent Intelligent Reasoning Layer (LangGraph)
**Deliverable:** An autonomous, stateful multi-agent system executing high-level threat assessment, vector lookups, and network state updates.

**Steps**
- Construct an asynchronous multi-agent engine using **LangGraph** running inside its own Kubernetes container.
- Establish the 3 specialized agent nodes with clear routing:

| # | Agent | Trigger | Responsibility |
|---|-------|---------|----------------|
| 1 | **Forensic Investigator** | anomaly score `> 0.85` | RAG-queries the Vector DB for known attack vectors / historic exploit matches |
| 2 | **Risk & Compliance Auditor** | after Agent 1 | Fuses Agent 1 evidence with raw C++ features from Kafka → fraud confidence percentage |
| 3 | **Settlement & Enforcer** | confidence `> 95%` | Compiles a structured freeze instruction (account / smart-contract), outputs a Markdown audit report to PostgreSQL |

**Acceptance**
- High-risk anomaly flags from the classifier trigger the agent cluster to execute sequential chain-of-thought analysis.
- Agents correctly output structured markdown rationale logs and write verified entries to PostgreSQL.

### ✅ Phase 4 Definition of Done
- Streaming features are classified in real-time, the automated Airflow retraining pipeline executes flawlessly, and the 3-agent system intercepts anomalies with verifiable reasoning logs.
- **Stop here.** Request human review and PR approval before Phase 5.

---

## Phase 5 — React / Next.js Interface & Comprehensive Validation
**Window:** Days 13–14
**Goal:** Build a high-performance frontend control dashboard to monitor live operations, and run an end-to-end simulation of a financial exploit for the demo.

### Task 5.1 — Real-Time React Monitoring Control Board
**Deliverable:** A modern React interface built with Next.js 15 App Router and `shadcn/ui` detailing system performance.

**Steps**
- Establish the web client app directory under `web/`.
- Integrate WebSockets or **Server-Sent Events (SSE)** to map real-time indicators from PostgreSQL and Kafka:
  - Transaction throughput
  - Kafka consumer lag
  - Rolling analytics lines
- Add an interactive log inspector to display multi-agent reasoning logs and cryptographic state-update hashes stored in PostgreSQL.

**Acceptance**
- The React app interfaces with the Kubernetes backend smoothly, updating dashboard components at **60 fps** without browser lockups.
- System metrics update dynamically as transaction simulation files are loaded into the streaming components.

---

### Task 5.2 — Exploit Simulation & Final Validation
**Deliverable:** A full-scale integration validation simulating an exploit being intercepted by the system, optimized for a 3-minute demo recording.

**Steps**
- Draft an end-to-end orchestration shell script that starts the C++ stream nodes, initializes Kafka pipelines, sets the LightGBM models live, and opens the React monitoring dashboard.
- Inject a pre-recorded exploit script simulating a multi-million-dollar high-frequency flash-loan attack vector.

**Acceptance**
- The entire application lifecycle runs end-to-end:
  1. **C++** captures the burst.
  2. **Kafka** queues the records.
  3. **LightGBM** signals the alert.
  4. The **3-Agent framework** isolates the source.
  5. The ledger status locks to `SECURED` on the React interface — **within 1 second** of execution.

### ✅ Phase 5 Definition of Done
- The integration simulation passes cleanly across all metrics.
- The React frontend documents the millisecond interception performance.
- Tag repository release at **v1.0.0** and capture the 3-minute demo recording.

---

## Out of Scope for MVP

The following are intentionally excluded to prevent scope creep:

- Multi-region geo-replicated Kafka cluster setup.
- Production deployment onto public cloud providers (AWS EKS, MSK, managed cloud setups).
- Multi-factor authentication mechanisms and fine-grained user access role controls (RBAC layers).
- Heavy managed-cloud abstraction layers such as Supabase — all infrastructure must run natively inside Kubernetes.

---

## Quick Reference — Phase Summary

| Phase | Window | Focus | Gate |
|:-----:|--------|-------|------|
| 0 | Day 1 | Monorepo, branch protections, dual-language CI | CI fails on bad PRs |
| 1 | Day 2 | Minikube + Kafka + PostgreSQL + Vector DB | Pods Running, 200 OK |
| 2 | Days 3–6 | C++20 engine: WebSocket → simdjson → lock-free ring → Kafka | 20k tps, <50µs frames |
| 3 | Days 7–9 | Multi-stage Docker, KEDA autoscaling | Image <150 MB, scales on lag |
| 4 | Days 10–12 | LightGBM streaming, Airflow Purged K-Fold, 3-tier LangGraph | Agents log to Postgres |
| 5 | Days 13–14 | Next.js 15 dashboard, flash-loan exploit sim | End-to-end <1 s, v1.0.0 |
