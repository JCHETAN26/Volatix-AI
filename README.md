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

### 0. Provision Supabase (one-time)

1. Create a Supabase project at https://supabase.com (free tier is plenty).
2. Copy the **session pooler** connection string from Project Settings → Database. It looks like:
   ```
   postgres://postgres.<project>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
3. Export it in your shell (and in Vercel project settings):
   ```bash
   export DATABASE_URL='postgres://postgres.<project>:<password>@...pooler.supabase.com:5432/postgres'
   make init-postgres        # applies scripts/sql/init.sql to your project
   ```

### 1. Bootstrap local infrastructure
```bash
make infra-up        # minikube + chain-kafka + vector-db (Qdrant)
make pods            # sanity-check Running state
make validate        # Qdrant create/get/delete a test collection
```
Under the hood: `scripts/bootstrap-infra.sh` runs `minikube start --cpus=4 --memory=8192`, installs the Bitnami Helm chart for Kafka, and applies `k8s/vector-db.yaml`. PostgreSQL is intentionally absent — it lives in your Supabase project (see step 0).

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
# Schema goes into Supabase (from step 0 above)
make init-postgres

# Make sure the cluster can talk to Supabase
make set-db-url                       # syncs $DATABASE_URL into the chainguard-db Secret

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

3-tier LangGraph agent cluster (Phase 4.2):
```bash
make port-forward-vector &
make agents-seed                       # populate Qdrant attack_vectors collection
# Optional — if you have an OpenAI API key, otherwise the service falls back
# to a deterministic mock LLM so it doesn't crash-loop:
OPENAI_API_KEY=sk-... make agents-set-openai-key
make agents-load && make agents-deploy
make agents-test                       # graph routing tests under MockChatLLM
```
The agents service consumes `anomaly-scores`, filters on `high_risk=true`, and routes each case through three nodes:
1. **Forensic Investigator** — searches Qdrant `attack_vectors` for the closest historical exploit signatures.
2. **Risk & Compliance Auditor** — fuses RAG evidence with the live features, emits a fraud confidence in `[0, 1]`.
3. **Settlement & Enforcer** *(only when confidence ≥ 0.95)* — compiles a structured freeze instruction and a final markdown audit report.

Every case (enforced or not) is persisted to PostgreSQL `agent_report` for the Phase 5 dashboard.

### 4. Launch the dashboard (Phase 5.1)
```bash
make web-install                      # one-time
echo "DATABASE_URL=${DATABASE_URL}" > web/.env.local
make web-dev                          # http://localhost:3000
```

The board renders four KPI cards (scores/min, high-risk/min, enforced/24h, mean score), a ledger status indicator (SECURED / MONITORING / OFFLINE), a live anomaly-score feed and an agent-report inspector with full markdown rationale. Server Components hydrate the initial state; `app/api/stream` then streams new rows via SSE. The same code is what Vercel builds — set `DATABASE_URL` in the project settings and the deploy renders the same dashboard.

### 5. End-to-end demo (Phase 5.2)
```bash
export DATABASE_URL='postgres://postgres.<project>:<password>@...pooler.supabase.com:5432/postgres'
make demo-up                          # init-postgres → infra → set-db-url → images → manifests → seeds
# In another terminal: bring the dashboard up
echo "DATABASE_URL=${DATABASE_URL}" > web/.env.local
make web-install && make web-dev      # http://localhost:3000

# Drive the timing test (inject feature frames straight onto Kafka):
make end-to-end                       # prints "injected → row written = N ms"

# For the full WS → C++ → … recording, point the engine at the exploit WS:
make exploit-ws                       # starts ws://localhost:8766/ in this terminal
# Then in a docker shell (or wherever you can run the C++ binary):
docker run --rm --network=host -e WS_URL=ws://localhost:8766/ \
    -e KAFKA_BROKERS=localhost:9092 chainguard-core:dev --engine

make demo-down                        # tear everything down (cluster preserved)
make demo-down-full                   # also `minikube stop`
```

After the local acceptance run is green, tag the release per `CHANGELOG.md`.

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
