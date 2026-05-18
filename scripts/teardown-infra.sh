#!/usr/bin/env bash
# ChainGuard-Core — Local infrastructure teardown
# Phase 1 helper. Removes everything bootstrap-infra.sh installs.
#
# Usage:
#   ./scripts/teardown-infra.sh            # uninstall Helm releases + vector-db
#   ./scripts/teardown-infra.sh --full     # also `minikube stop`
#   ./scripts/teardown-infra.sh --nuke     # also `minikube delete` (DESTRUCTIVE)

set -euo pipefail

KAFKA_RELEASE="${KAFKA_RELEASE:-chain-kafka}"
DB_RELEASE="${DB_RELEASE:-chain-db}"
NAMESPACE="${NAMESPACE:-default}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VECTOR_MANIFEST="${REPO_ROOT}/k8s/vector-db.yaml"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }

MODE="soft"
case "${1:-}" in
    --full) MODE="full" ;;
    --nuke) MODE="nuke" ;;
    "")     MODE="soft" ;;
    *)      echo "Unknown flag: $1" >&2; exit 2 ;;
esac

log "Uninstalling vector-db manifest"
kubectl delete -f "${VECTOR_MANIFEST}" -n "${NAMESPACE}" --ignore-not-found

log "Uninstalling Helm releases"
helm uninstall "${KAFKA_RELEASE}" -n "${NAMESPACE}" 2>/dev/null || warn "${KAFKA_RELEASE} not installed"
helm uninstall "${DB_RELEASE}"    -n "${NAMESPACE}" 2>/dev/null || warn "${DB_RELEASE} not installed"

# Clean up Bitnami-managed PVCs (Helm leaves these behind on purpose).
log "Removing leftover PersistentVolumeClaims"
kubectl get pvc -n "${NAMESPACE}" -o name 2>/dev/null \
    | grep -E "(${KAFKA_RELEASE}|${DB_RELEASE})" \
    | xargs -r kubectl delete -n "${NAMESPACE}" --ignore-not-found

case "${MODE}" in
    full)
        log "Stopping Minikube"
        minikube stop
        ok "Minikube stopped (data preserved)"
        ;;
    nuke)
        log "Deleting Minikube cluster (DESTRUCTIVE)"
        minikube delete
        ok "Minikube cluster removed"
        ;;
    *)
        ok "Soft teardown complete (cluster still running)"
        ;;
esac
