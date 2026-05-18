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

WebSocket ingest + SIMD JSON parsing (Phase 2.2):
```bash
pip install websockets                # one-time
make mock-ticker                      # terminal 1: ws://localhost:8765/ @ 25k tps
make cpp-ingest                       # terminal 2: streams and prints rate
make cpp-throughput                   # in-process benchmark; fails below 20k tps
```
`make mock-ticker` accepts `MOCK_RATE=50000` and the underlying script supports `--inject-malformed N` (per 1000) to exercise the parser's degrade-gracefully path.

Container image (Phase 3.1):
```bash
make docker-build     # multi-stage build → chainguard-core:dev
make docker-size      # enforces the <150MB acceptance ceiling
make docker-run       # docker run --rm chainguard-core:dev --version
```
The Dockerfile uses `debian:bookworm-slim` for the build stage and `gcr.io/distroless/cc-debian12:nonroot` for the runtime stage. Shared library deps are auto-resolved via `ldd` and copied into the final image; no shell, no package manager, runs as uid 65532 by default.

Kubernetes + KEDA (Phase 3.2):
```bash
make image-load       # docker-build + minikube image load chainguard-core:dev
make keda-install     # helm install kedacore/keda into the keda namespace
make k8s-deploy       # apply k8s/deployment.yaml + k8s/keda-scaledobject.yaml
make watch-pods       # tail replicas + the KEDA-managed HPA

# Acceptance: flood raw-ticks with 50k records, watch the Deployment scale 1 → 5
make flood-kafka      # ephemeral kafka-console-producer pod, 50,000 messages
                      # KEDA sees lag ≥ 50k, lagThreshold=10k → desired = 5 replicas
                      # once chainguard-engine drains the backlog, replicas → 1
```
The Deployment runs `chainguard --consume raw-ticks --group chainguard-engine` so KEDA has a real consumer-group lag to scale on. The ScaledObject's kafka trigger polls every 10s and uses a 60s scale-down cooldown.

Full feature pipeline (Phase 2.3):
```bash
# end-to-end live: mock-ticker → engine → financial-features Kafka topic
make port-forward-kafka &             # terminal 1
make mock-ticker &                    # terminal 2
make cpp-engine                       # terminal 3: pushes FeatureFrame to Kafka

# microbench: frame-gen latency
make cpp-feature-bench                # fails if median ≥ 50µs
```
Architecture: WebSocket producer thread parses JSON ticks with simdjson and pushes them into an SPSC lock-free ring (64k slots, cache-line-padded indices, zero mutexes in the hot path). A consumer thread pops, updates the OFI (16-bucket time-windowed) and Realized Volatility (rolling stddev of log returns) kernels, and every N ticks publishes a 64-byte trivially-copyable `FeatureFrame` to the `financial-features` Kafka topic for downstream LightGBM consumption (Phase 4).

System dependencies (Ubuntu):
```bash
sudo apt-get install -y build-essential cmake ninja-build pkg-config \
    librdkafka-dev libssl-dev libboost-system-dev libsimdjson-dev
```
macOS (Homebrew):
```bash
brew install cmake librdkafka openssl pkg-config boost simdjson
export PKG_CONFIG_PATH="$(brew --prefix openssl)/lib/pkgconfig:$(brew --prefix librdkafka)/lib/pkgconfig:$(brew --prefix simdjson)/lib/pkgconfig"
```

### 3. Run the analytics & agent stack (Phase 4)
```bash
# One-time schema setup
make init-postgres

# Build + load the Python classifier image (bakes a baseline LightGBM
# model from synthetic data so the service can boot cold)
make classifier-load
make classifier-deploy

# Install Airflow with the chainguard retraining DAG mounted in
make airflow-install
make airflow-ui                       # → http://localhost:8080 (admin/admin)

# Run unit tests for the FeatureFrame layout / kernels
make classifier-test
```
The classifier subscribes to `financial-features` (produced by the C++ engine), decodes each 64-byte FeatureFrame, runs LightGBM, and publishes the score on `anomaly-scores`. Frames + scores are mirrored into PostgreSQL (`feature_log`, `anomaly_score_log`) so the nightly Airflow DAG can retrain on real traffic via Purged K-Fold cross-validation.

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
