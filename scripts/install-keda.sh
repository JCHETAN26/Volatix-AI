#!/usr/bin/env bash
# Volatix-AI — install KEDA into the local cluster (Phase 3.2).
#
# Idempotent. Registers the kedacore Helm repo, installs KEDA into the
# `keda` namespace, waits for the operator + metrics server to be Ready.
#
# Usage:
#   ./scripts/install-keda.sh

set -euo pipefail

KEDA_NAMESPACE="${KEDA_NAMESPACE:-keda}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300s}"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

command -v helm >/dev/null    || die "missing helm"
command -v kubectl >/dev/null || die "missing kubectl"

log "Ensuring kedacore Helm repo is registered"
if helm repo list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "kedacore"; then
    ok "kedacore repo already registered"
else
    helm repo add kedacore https://kedacore.github.io/charts
    ok "Added kedacore repo"
fi
helm repo update kedacore >/dev/null
ok "Helm repo cache refreshed"

log "Installing/Upgrading KEDA in namespace '${KEDA_NAMESPACE}'"
helm upgrade --install keda kedacore/keda \
    --namespace "${KEDA_NAMESPACE}" \
    --create-namespace \
    --wait \
    --timeout "${WAIT_TIMEOUT}"

log "Waiting for the operator + metrics server"
kubectl rollout status deployment/keda-operator -n "${KEDA_NAMESPACE}" --timeout="${WAIT_TIMEOUT}"
kubectl rollout status deployment/keda-operator-metrics-apiserver -n "${KEDA_NAMESPACE}" \
    --timeout="${WAIT_TIMEOUT}"

ok "KEDA Ready in ${KEDA_NAMESPACE}"
kubectl get pods -n "${KEDA_NAMESPACE}"
