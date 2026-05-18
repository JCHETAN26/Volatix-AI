#!/usr/bin/env bash
# ChainGuard-Core — PostgreSQL validation (Phase 1 / Task 1.1 acceptance).
#
# Runs SELECT version() inside the chain-db pod using the password Bitnami
# wrote to the Secret. Proves the database is up and ACID-authenticated.
#
# Usage:
#   ./scripts/validate-postgres.sh

set -euo pipefail

DB_RELEASE="${DB_RELEASE:-chain-db}"
NAMESPACE="${NAMESPACE:-default}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-postgres}"

POD="${DB_RELEASE}-postgresql-0"
SECRET="${DB_RELEASE}-postgresql"

log() { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()  { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die() { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

log "Looking up PostgreSQL password from Secret '${SECRET}'"
PGPASSWORD="$(kubectl get secret "${SECRET}" -n "${NAMESPACE}" \
    -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 --decode)"
[ -n "${PGPASSWORD}" ] || die "could not read postgres-password from ${SECRET}"

log "Running SELECT version() inside ${POD}"
OUTPUT="$(kubectl exec -n "${NAMESPACE}" "${POD}" -- \
    env PGPASSWORD="${PGPASSWORD}" \
    psql -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT version();" 2>&1)" \
    || die "psql failed: ${OUTPUT}"

ok "PostgreSQL is reachable and authenticated."
echo "  ${OUTPUT}"
