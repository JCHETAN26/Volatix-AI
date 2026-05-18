# ChainGuard-Core

A real-time, low-latency financial threat detection platform combining a C++20 streaming feature-engineering engine, event-driven Kubernetes infrastructure, ML anomaly classification, and a 3-tier agentic reasoning layer.

ChainGuard-Core ingests live market transactions over WebSockets, computes microsecond-scale quantitative features (Order Flow Imbalance, Realized Volatility) directly on hardware SIMD lanes, classifies anomalies with LightGBM, and triggers an autonomous LangGraph agent cluster that investigates, audits, and enforces freezes on high-confidence fraud — all visualized through a Next.js 15 analytical control board.

---

## Architecture Overview

```
Polygon.io / Mock API
        │ (WebSocket)
        ▼
┌─────────────────────────┐
│  C++20 Ingestion Engine │   simdjson · Boost.Asio · Lock-free ring buffers
│  (Order Flow Imbalance, │
│   Realized Volatility)  │
└──────────┬──────────────┘
           │ financial-features topic
           ▼
       ┌───────┐
       │ Kafka │ ◄──── KEDA autoscaling (consumer lag)
       └───┬───┘
           │
   ┌───────┴────────────────────────────┐
   ▼                                    ▼
┌─────────────────────┐         ┌──────────────────────┐
│ LightGBM Classifier │         │ LangGraph 3-Agent    │
│  (anomaly score)    │────────▶│ Forensic / Auditor / │
└──────────┬──────────┘         │ Enforcer             │
           │                    └──────────┬───────────┘
           ▼                               ▼
     ┌───────────┐               ┌──────────────────┐
     │  Airflow  │               │   PostgreSQL     │
     │ Retraining│◄──────────────│  + pgvector/Qdrant│
     │   DAG     │               └──────────────────┘
     └───────────┘                         │
                                           ▼
                              ┌────────────────────────┐
                              │ Next.js 15 Control Board│
                              │  (SSE / WebSockets)     │
                              └────────────────────────┘
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Ingestion & Feature Engineering | C++20, Boost.Asio/Beast, simdjson, librdkafka |
| Message Broker | Apache Kafka (Bitnami Helm) |
| Storage | PostgreSQL (ACID logs/metadata), Qdrant / pgvector (RAG) |
| Orchestration | Kubernetes (Minikube), Helm, KEDA |
| ML Pipeline | Python, LightGBM, Apache Airflow (KubernetesPodOperator) |
| Agentic Layer | LangGraph, OpenAI / Local Ollama |
| Frontend | Next.js 15 (App Router), React, shadcn/ui, SSE/WebSockets |
| CI/CD | GitHub Actions, clang-format, Prettier/ESLint |

---

## Monorepo Layout

```
.
├── src/                # C++20 Ingestion & Feature Engineering Engine
├── web/                # Next.js 15 Analytical Control Board
├── airflow/            # Airflow DAGs & MLOps automation
├── k8s/                # Helm charts, KEDA manifests, K8s configs
└── CMakeLists.txt      # Root C++ CMake configuration
```

---

## Pre-flight Requirements

- Node.js 20+ and pnpm 9+
- GCC/Clang with C++20 support
- CMake 3.22+
- Minikube or Docker Desktop with Kubernetes enabled
- Helm v3+
- `.env.local` containing:
  ```
  POLYGON_API_KEY=...
  OPENAI_API_KEY=sk-...   # or local Ollama setup
  ```

Verify with:
```bash
node --version
g++ --version
cmake --version
kubectl version
helm version
```

---

## Build & Run

### 1. Bootstrap local infrastructure
```bash
make infra-up        # minikube + chain-kafka + chain-db + vector-db (Qdrant)
make pods            # sanity-check Running state
make validate        # PostgreSQL SELECT + Qdrant create/get/delete a test collection
```
Under the hood: `scripts/bootstrap-infra.sh` runs `minikube start --cpus=4 --memory=8192`, installs the Bitnami Helm charts for Kafka and PostgreSQL, and applies `k8s/vector-db.yaml`.

For validating the vector DB you need a port-forward in another terminal:
```bash
make port-forward-vector   # exposes localhost:6333 (HTTP) + 6334 (gRPC)
```

### 2. Build the C++ engine
```bash
make cpp-build       # cmake configure + build
make cpp-run         # build + execute (no broker contact)
```

Verify the Kafka producer link (requires `make port-forward-kafka` in another terminal, or pass `KAFKA_BROKERS=host:port`):
```bash
make cpp-probe       # metadata request only — confirms reachability
make cpp-smoke       # produces 10 records to chainguard.smoke; fails if any drop
```

System dependencies (Ubuntu):
```bash
sudo apt-get install -y build-essential cmake ninja-build \
    pkg-config librdkafka-dev libssl-dev
```
macOS (Homebrew): `brew install cmake librdkafka openssl pkg-config` and export `PKG_CONFIG_PATH=$(brew --prefix openssl)/lib/pkgconfig:$(brew --prefix librdkafka)/lib/pkgconfig`.

### 3. Run the analytics & agent stack
```bash
# Python classifier consumer
python services/classifier/main.py

# LangGraph agent cluster
python services/agents/graph.py

# Airflow retraining DAG (KubernetesPodOperator)
airflow dags trigger retraining_pipeline
```

### 4. Launch the dashboard
```bash
cd web
pnpm install
pnpm dev
```

### Teardown
```bash
make infra-down      # remove helm releases + vector-db (cluster keeps running)
make infra-stop      # the above + `minikube stop`
make infra-nuke      # DESTRUCTIVE: `minikube delete`
```

---

## Phased Build Plan

Implementation follows the strict sequence defined in `build-plan.md`. Each phase ships behind its own PR with CI gates.

| Phase | Window | Focus |
|-------|--------|-------|
| 0 | Day 1 | Monorepo scaffolding, branch protections, dual-language CI |
| 1 | Day 2 | Minikube + Kafka + PostgreSQL + vector DB |
| 2 | Days 3–6 | C++20 engine: WebSocket ingest, simdjson, lock-free ring buffers, OFI / Realized Volatility, Kafka producer |
| 3 | Days 7–9 | Multi-stage Docker (<150MB), Helm deploy, KEDA autoscaling on consumer lag |
| 4 | Days 10–12 | LightGBM streaming classifier, Airflow Purged K-Fold retraining, 3-tier LangGraph agents |
| 5 | Days 13–14 | Next.js 15 control board, end-to-end flash-loan exploit simulation, v1.0.0 tag |

---

## Performance Targets

- Ingestion throughput: **20,000+ ticks/sec** sustained burst
- Feature frame generation: **< 50 microseconds**
- Zero mutex locks in the critical calculation pathway
- Container image footprint: **< 150 MB**
- End-to-end exploit interception (capture → classify → agent decision → ledger lock): **< 1 second**
- Dashboard render: **60 fps**

---

## The 3-Tier Agentic Layer

| Agent | Trigger | Role |
|-------|---------|------|
| **Forensic Investigator** | anomaly score > 0.85 | RAG lookup against Vector DB for known attack vectors / historic exploits |
| **Risk & Compliance Auditor** | after Agent 1 | Fuses Agent 1 evidence with raw C++ features → fraud confidence % |
| **Settlement & Enforcer** | confidence > 95% | Compiles structured freeze instruction, writes Markdown audit report to PostgreSQL |

---

## CI/CD Gates

- Direct pushes to `main` are blocked via GitHub Branch Protection
- PRs require ≥1 approval and linear history
- `frontend-ci`: `pnpm lint`, `pnpm typecheck`, `pnpm build`
- `cpp-ci`: CMake + `-Wall -Wextra -Werror` zero-warning enforcement
- Unformatted C++ or broken TypeScript fails status checks instantly

---

## Source of Truth

| File | Role |
|------|------|
| `README.md` | Product spec, quantitative parameters, non-negotiables |
| `system-prompt.md` | Builder LLM operating principles |
| `build-plan.md` | Sequenced tasks and acceptance criteria |
| `src/core_engine.cpp` | Core low-latency streaming feature engine (C++20) |

If these conflict, **the README wins**.

---

## Out of Scope (MVP)

- Multi-region geo-replicated Kafka clusters
- Public-cloud deployment (AWS EKS, MSK, managed services)
- MFA and fine-grained RBAC
- Heavy managed abstractions (e.g. Supabase) — all infra runs natively in Kubernetes

---

## License

Private — all rights reserved.
