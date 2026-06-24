#!/usr/bin/env bash
# Volatix-AI — full-stack demo bring-up (Phase 5.2, Supabase-backed).
#
# Idempotent. Steps:
#   1. Verify $DATABASE_URL is set (Supabase connection string).
#   2. Apply the schema (init-postgres → Supabase).
#   3. Local infra (Minikube + Kafka + Qdrant) — NO in-cluster Postgres.
#   4. Sync DATABASE_URL into the in-cluster `volatix-db` Secret.
#   5. KEDA (event-driven autoscaler).
#   6. Build + load the three service images (engine / classifier / agents).
#   7. Apply k8s manifests for classifier + agents.
#   8. Seed Qdrant attack_vectors collection.
#   9. Start background port-forwards for Kafka + Vector.
#
# After this returns, the user runs `make web-dev` (or relies on the
# Vercel deploy) to view the control board, then `make end-to-end` to
# drive the timing test.
#
# Usage:
#   export DATABASE_URL='postgres://postgres:PASSWORD@PROJ.supabase.co:5432/postgres'
#   ./scripts/demo-up.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

require() {
    command -v "$1" >/dev/null 2>&1 || die "missing prerequisite: $1"
}

# ---------------------------------------------------------------------------
# 0. Prerequisites
# ---------------------------------------------------------------------------
log "Checking prerequisites"
for bin in minikube kubectl helm docker python3 psql; do require "$bin"; done
[ -n "${DATABASE_URL:-}" ] \
    || die "set DATABASE_URL first — paste your Supabase project's session-pooler URL"
ok "minikube / kubectl / helm / docker / python3 / psql present"
ok "DATABASE_URL is set"

# ---------------------------------------------------------------------------
# 1. Supabase schema
# ---------------------------------------------------------------------------
log "Applying Postgres schema to Supabase"
make init-postgres

# ---------------------------------------------------------------------------
# 2. Local infra (Phase 1 — Kafka + Qdrant only; Postgres lives in Supabase)
# ---------------------------------------------------------------------------
log "Bringing up local infrastructure (Kafka + Qdrant)"
make infra-up

# ---------------------------------------------------------------------------
# 3. Mirror DATABASE_URL into the in-cluster Secret
# ---------------------------------------------------------------------------
log "Syncing volatix-db Secret"
make set-db-url

# ---------------------------------------------------------------------------
# 4. KEDA
# ---------------------------------------------------------------------------
log "Installing KEDA"
make keda-install

# ---------------------------------------------------------------------------
# 5. Build + load images
# ---------------------------------------------------------------------------
log "Building volatix-core (engine)"
make image-load
log "Building volatix-classifier"
make classifier-load
log "Building volatix-agents"
make agents-load
log "Building volatix-mock-ticker (in-cluster synthetic feed)"
make mock-ticker-load
log "Building volatix-realfeed (Coinbase WS adapter)"
make realfeed-load

# ---------------------------------------------------------------------------
# 6. Apply manifests
# ---------------------------------------------------------------------------
log "Deploying k8s manifests"
make k8s-deploy           # volatix-engine (KEDA --consume fixture) + ScaledObject
make classifier-deploy
make agents-deploy
make tickers-deploy       # mock-ticker + realfeed Services
make engine-live-deploy   # volatix-engine-live (--engine mode, drives the dashboard)

# ---------------------------------------------------------------------------
# 7. Seed Qdrant via a temporary port-forward
# ---------------------------------------------------------------------------
log "Seeding Qdrant attack_vectors collection"
kubectl port-forward -n default svc/vector-db 6333:6333 >/dev/null 2>&1 &
PF_VECTOR_PID=$!
trap 'kill ${PF_VECTOR_PID} 2>/dev/null || true' EXIT
sleep 2
if ! make agents-seed; then
    warn "vector seed failed; you can re-run \`make agents-seed\` once port-forward-vector is up"
fi
kill "${PF_VECTOR_PID}" 2>/dev/null || true
trap - EXIT

# ---------------------------------------------------------------------------
# 8. Long-running port-forwards (background; killed by demo-down.sh)
# ---------------------------------------------------------------------------
LOG_DIR="/tmp/volatix-pf"
mkdir -p "${LOG_DIR}"
start_pf() {
    local label=$1 svc=$2 ports=$3
    pkill -f "kubectl port-forward.*${svc}.*${ports}" >/dev/null 2>&1 || true
    nohup kubectl port-forward -n default "svc/${svc}" "${ports}" \
        > "${LOG_DIR}/${label}.log" 2>&1 &
    echo "  ${label} (svc/${svc} ${ports}) pid=$!"
}

log "Starting background port-forwards"
start_pf kafka   chain-kafka  9092:9092
start_pf vector  vector-db    6333:6333
ok "port-forwards backgrounded (logs in ${LOG_DIR})"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
ok "Stack is up. Pod overview:"
kubectl get pods -n default

echo
cat <<EOF

Next steps:

  # Start the dashboard (DATABASE_URL is already in your shell)
  echo "DATABASE_URL=\${DATABASE_URL}" > web/.env.local
  make web-install        # one-time
  make web-dev            # http://localhost:3000

  # Drive the end-to-end timing test
  make end-to-end

  # Tear it all down when you're done
  make demo-down
EOF
