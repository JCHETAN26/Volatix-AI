#!/usr/bin/env bash
# ChainGuard-Core — full-stack demo teardown (Phase 5.2).
#
# Cleans everything `demo-up.sh` brought online without nuking the
# Minikube node itself. Pass --nuke to also `minikube delete`.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

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

log "Stopping background port-forwards"
pkill -f "kubectl port-forward.*chain-kafka.*9092" >/dev/null 2>&1 || true
pkill -f "kubectl port-forward.*chain-db.*5432"    >/dev/null 2>&1 || true
pkill -f "kubectl port-forward.*vector-db.*6333"   >/dev/null 2>&1 || true
ok "port-forwards stopped"

log "Removing k8s manifests"
make agents-undeploy        2>/dev/null || true
make classifier-undeploy    2>/dev/null || true
make k8s-undeploy           2>/dev/null || true

case "${MODE}" in
    full)
        log "Tearing down Helm releases + stopping Minikube"
        ./scripts/teardown-infra.sh --full
        ;;
    nuke)
        log "Tearing down Helm releases + deleting Minikube cluster (DESTRUCTIVE)"
        ./scripts/teardown-infra.sh --nuke
        ;;
    *)
        log "Tearing down Helm releases (cluster preserved)"
        ./scripts/teardown-infra.sh
        ;;
esac

ok "Demo torn down."
