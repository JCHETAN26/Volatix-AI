#!/usr/bin/env bash
# ChainGuard-Core — full-stack demo bring-up (Phase 5.2).
#
# Idempotent. Steps:
#   1. Local infra (Minikube + Kafka + Postgres + Qdrant)
#   2. Postgres schema
#   3. KEDA (event-driven autoscaler)
#   4. Build + load the three service images (engine / classifier / agents)
#   5. Apply k8s manifests for classifier + agents
#   6. Seed Qdrant attack_vectors collection
#   7. Start background port-forwards for the dashboard (Kafka, Postgres, Vector)
#
# After this returns, the user runs `make web-dev` (or relies on the
# Vercel deploy) to view the control board, then `make end-to-end` to
# drive the timing test.
#
# Usage:
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
for bin in minikube kubectl helm docker python3; do require "$bin"; done
ok "minikube / kubectl / helm / docker / python3 present"

# ---------------------------------------------------------------------------
# 1. Local infra (Phase 1)
# ---------------------------------------------------------------------------
log "Bringing up local infrastructure"
make infra-up

# ---------------------------------------------------------------------------
# 2. Postgres schema (Phase 4.1)
# ---------------------------------------------------------------------------
log "Applying Postgres schema"
make init-postgres

# ---------------------------------------------------------------------------
# 3. KEDA (Phase 3.2). The classifier + agents don't strictly need it for
#    the demo, but having it installed lets the user run `make flood-kafka`
#    against the engine deployment without redoing helm setup.
# ---------------------------------------------------------------------------
log "Installing KEDA"
make keda-install

# ---------------------------------------------------------------------------
# 4. Build + load images
# ---------------------------------------------------------------------------
log "Building chainguard-core (engine)"
make image-load            # builds chainguard-core:dev and minikube image load
log "Building chainguard-classifier"
make classifier-load
log "Building chainguard-agents"
make agents-load

# ---------------------------------------------------------------------------
# 5. Apply manifests
# ---------------------------------------------------------------------------
log "Deploying k8s manifests"
make k8s-deploy           # chainguard-engine + KEDA ScaledObject
make classifier-deploy
make agents-deploy

# ---------------------------------------------------------------------------
# 6. Seed Qdrant via a temporary port-forward
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
# 7. Long-running port-forwards (background; killed by demo-down.sh)
# ---------------------------------------------------------------------------
LOG_DIR="/tmp/chainguard-pf"
mkdir -p "${LOG_DIR}"
start_pf() {
    local label=$1 svc=$2 ports=$3
    pkill -f "kubectl port-forward.*${svc}.*${ports}" >/dev/null 2>&1 || true
    nohup kubectl port-forward -n default "svc/${svc}" "${ports}" \
        > "${LOG_DIR}/${label}.log" 2>&1 &
    echo "  ${label} (svc/${svc} ${ports}) pid=$!"
}

log "Starting background port-forwards"
start_pf kafka     chain-kafka              9092:9092
start_pf postgres  chain-db-postgresql      5432:5432
start_pf vector    vector-db                6333:6333
ok "port-forwards backgrounded (logs in ${LOG_DIR})"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
ok "Stack is up. Pod overview:"
kubectl get pods -n default

echo
PG_PASSWORD="$(kubectl get secret chain-db-postgresql \
    -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 --decode || echo "")"
cat <<EOF

Next steps:

  # Point the dashboard at the local Postgres and start it
  echo "DATABASE_URL=postgres://postgres:${PG_PASSWORD}@localhost:5432/postgres" > web/.env.local
  make web-install        # one-time
  make web-dev            # http://localhost:3000

  # Drive the end-to-end timing test
  make end-to-end

  # Tear it all down when you're done
  make demo-down
EOF
