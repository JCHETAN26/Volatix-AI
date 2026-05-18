#!/usr/bin/env bash
# ChainGuard-Core — apply scripts/sql/init.sql to the in-cluster Postgres.
# Idempotent; safe to rerun.

set -euo pipefail

DB_RELEASE="${DB_RELEASE:-chain-db}"
NAMESPACE="${NAMESPACE:-default}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-postgres}"

POD="${DB_RELEASE}-postgresql-0"
SECRET="${DB_RELEASE}-postgresql"
SQL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sql/init.sql"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

[ -f "${SQL_PATH}" ] || die "missing ${SQL_PATH}"

log "Looking up PostgreSQL password from Secret '${SECRET}'"
PGPASSWORD="$(kubectl get secret "${SECRET}" -n "${NAMESPACE}" \
    -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 --decode)"
[ -n "${PGPASSWORD}" ] || die "could not read postgres-password from ${SECRET}"

log "Applying ${SQL_PATH} to ${POD}/${DB_NAME}"
kubectl exec -i -n "${NAMESPACE}" "${POD}" -- \
    env PGPASSWORD="${PGPASSWORD}" \
    psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${DB_NAME}" \
    < "${SQL_PATH}"

ok "Schema applied."
