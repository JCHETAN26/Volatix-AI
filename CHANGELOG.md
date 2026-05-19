# ChainGuard-Core — Changelog

## v1.0.0 — Phase 5 complete

End-to-end financial threat-detection pipeline:

- **Phase 0 — Monorepo & CI/CD.** Branch protection on `main`, dual-language
  CI (frontend + cpp + docker + python) with an aggregate gate. PR template
  keyed to build-plan tasks.
- **Phase 1 — Local infrastructure.** Idempotent `make infra-up` brings
  Minikube + Kafka (Bitnami) + PostgreSQL (Bitnami) + Qdrant online.
- **Phase 2.1 — Native Kafka producer.** C++20 binary with `--probe` /
  `--smoke` modes; CMake + librdkafka + OpenSSL via pkg-config; zero-warning
  build under `-Wall -Wextra -Wpedantic -Werror`.
- **Phase 2.2 — WebSocket ingest + simdjson parsing.** Boost.Beast (TCP +
  TLS+SNI) WS client; simdjson::ondemand `TickData` parser with graceful
  reject path. `--throughput-test` benchmark enforces ≥20,000 tps.
- **Phase 2.3 — Lock-free feature store.** SPSC ring buffer with cache-
  line-padded atomics, OFI (16-bucket sliding window) + Realized Volatility
  (rolling stddev of log returns) kernels, 64-byte packed `FeatureFrame`
  published to `financial-features`. `--feature-bench` enforces median
  frame-gen latency < 50µs.
- **Phase 3.1 — Multi-stage container.** `debian:bookworm-slim` builder →
  `gcr.io/distroless/cc-debian12:nonroot` runtime. `ldd`-resolved deps;
  hard size gate (< 150MB) in `docker-ci`.
- **Phase 3.2 — KEDA autoscaling.** ScaledObject scales the
  `chainguard-engine` Deployment from 1 → 5 replicas on `raw-ticks`
  consumer lag; cooldown back to 1 after drain.
- **Phase 4.1 — LightGBM classifier + Airflow.** Python `kafka-python`
  consumer → LightGBM → `anomaly-scores`. Postgres mirror tables
  (`feature_log`, `anomaly_score_log`, `model_registry`). Daily
  KubernetesPodOperator DAG retrains with **Purged K-Fold** CV against
  yesterday's `feature_log` slice.
- **Phase 4.2 — LangGraph 3-tier agent cluster.**
  Forensic Investigator (RAG on Qdrant `attack_vectors`) → Risk &
  Compliance Auditor (fraud confidence in `[0,1]`) → Settlement & Enforcer
  (gated at confidence ≥ 0.95, writes structured action + markdown
  rationale to `agent_report`). LLM provider auto-falls back to a
  deterministic `MockChatLLM` so the pod never crash-loops on missing
  credentials. `httpx`-only Qdrant client to keep the runtime image small.
- **Phase 5.1 — Next.js 15 control board.** App Router + RSC + Tailwind +
  Server-Sent Events live feed. `pg`-backed API for reports / scores /
  health. KPI cards, ledger status indicator, anomaly score feed, agent
  reasoning log inspector (markdown). Connected to Vercel.
- **Phase 5.2 — End-to-end demo orchestration.** `make demo-up` / `make
  demo-down` bring the whole stack online and tear it down. `scripts/
  exploit-ws.py` ships a pre-recorded flash-loan burst the C++ engine can
  consume; `scripts/inject-features.py` bypasses the engine for timing
  tests. `make end-to-end` prints the inject → `agent_report` row latency
  and asserts the configured ceiling.

### Local acceptance

```bash
make demo-up
echo "DATABASE_URL=postgres://postgres:$(kubectl get secret chain-db-postgresql \
    -o jsonpath='{.data.postgres-password}' | base64 -d)@localhost:5432/postgres" \
    > web/.env.local
make web-install && make web-dev          # http://localhost:3000
make end-to-end                            # → prints inject→DB latency
```

### Tagging

Tag v1.0.0 from main once the Phase 5.2 PR has merged and the local
acceptance run is green:

```bash
git checkout main && git pull
git tag -a v1.0.0 -m "ChainGuard-Core v1.0.0 — end-to-end pipeline"
git push origin v1.0.0
```
