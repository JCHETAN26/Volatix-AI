#!/usr/bin/env bash
# ChainGuard-Core — Local infrastructure bootstrap
# Phase 1 / Task 1.1 + 1.2.
#
# Idempotent. Brings up:
#   1. Minikube cluster (4 CPU / 8 GiB)
#   2. Apache Kafka via Bitnami Helm  (release: chain-kafka)
#   3. PostgreSQL via Bitnami Helm    (release: chain-db)
#   4. Qdrant vector store            (k8s/vector-db.yaml)
#
# Usage:
#   ./scripts/bootstrap-infra.sh
#
# Re-runnable — existing resources are detected and left in place.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (override with env vars)
# ---------------------------------------------------------------------------
MINIKUBE_CPUS="${MINIKUBE_CPUS:-4}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-8192}"
KAFKA_RELEASE="${KAFKA_RELEASE:-chain-kafka}"
NAMESPACE="${NAMESPACE:-default}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300s}"

# Note: PostgreSQL is now managed (Supabase) rather than in-cluster.
# See scripts/init-postgres.sh for schema bootstrapping.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VECTOR_MANIFEST="${REPO_ROOT}/k8s/vector-db.yaml"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
log()   { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m!\033[0m %s\n" "$*"; }
die()   { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
require_bin() {
    command -v "$1" >/dev/null 2>&1 || die "missing required binary: $1"
}

log "Checking prerequisites"
require_bin minikube
require_bin kubectl
require_bin helm
ok "minikube, kubectl, helm present"

# ---------------------------------------------------------------------------
# 1. Minikube
# ---------------------------------------------------------------------------
log "Ensuring Minikube cluster is running (cpus=${MINIKUBE_CPUS}, memory=${MINIKUBE_MEMORY})"
if minikube status >/dev/null 2>&1; then
    ok "Minikube already running"
else
    minikube start --cpus="${MINIKUBE_CPUS}" --memory="${MINIKUBE_MEMORY}"
    ok "Minikube started"
fi

kubectl config use-context minikube >/dev/null

# ---------------------------------------------------------------------------
# 2. Helm repo
# ---------------------------------------------------------------------------
log "Ensuring bitnami Helm repo is registered"
if helm repo list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "bitnami"; then
    ok "bitnami repo already registered"
else
    helm repo add bitnami https://charts.bitnami.com/bitnami
    ok "Added bitnami repo"
fi
helm repo update bitnami >/dev/null
ok "Helm repo cache refreshed"

# ---------------------------------------------------------------------------
# 3. Kafka
# ---------------------------------------------------------------------------
log "Installing/Upgrading Kafka release '${KAFKA_RELEASE}'"
# Bitnami moved their free Docker Hub images to bitnamilegacy/ in Aug 2025.
# Pin the registry override here so the chart pulls images that actually exist.
helm upgrade --install "${KAFKA_RELEASE}" bitnami/kafka \
    --namespace "${NAMESPACE}" \
    --set global.security.allowInsecureImages=true \
    --set image.registry=docker.io \
    --set image.repository=bitnamilegacy/kafka \
    --set listeners.client.protocol=PLAINTEXT \
    --set listeners.controller.protocol=PLAINTEXT \
    --set listeners.interbroker.protocol=PLAINTEXT \
    --wait \
    --timeout "${WAIT_TIMEOUT}"
ok "Kafka deployed"

# ---------------------------------------------------------------------------
# 4. Vector DB (Qdrant)
# ---------------------------------------------------------------------------
log "Applying vector DB manifest (${VECTOR_MANIFEST})"
kubectl apply -f "${VECTOR_MANIFEST}" -n "${NAMESPACE}"

log "Waiting for vector-db deployment to be Ready"
kubectl rollout status deployment/vector-db -n "${NAMESPACE}" --timeout="${WAIT_TIMEOUT}"
ok "vector-db Ready"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
ok "Infrastructure up. Pod overview:"
kubectl get pods -n "${NAMESPACE}"

echo
cat <<EOF
Connection hints (cluster-internal DNS):
  Kafka      : ${KAFKA_RELEASE}.${NAMESPACE}.svc.cluster.local:9092
  Vector DB  : vector-db.${NAMESPACE}.svc.cluster.local:6333  (HTTP)
               vector-db.${NAMESPACE}.svc.cluster.local:6334  (gRPC)

PostgreSQL is managed (Supabase). Export DATABASE_URL=postgres://... and run:
  make init-postgres      # applies scripts/sql/init.sql to Supabase
  make set-db-url         # syncs the URL into the chainguard-db k8s Secret

To validate from your laptop:
  make validate           # runs the vector-db validator
  make port-forward-vector
EOF
