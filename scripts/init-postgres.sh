#!/usr/bin/env bash
# ChainGuard-Core — apply scripts/sql/init.sql to Supabase (or any Postgres
# reachable via DATABASE_URL). Idempotent; safe to rerun.

set -euo pipefail

SQL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sql/init.sql"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

[ -f "${SQL_PATH}" ] || die "missing ${SQL_PATH}"
[ -n "${DATABASE_URL:-}" ] || die "set DATABASE_URL first (Supabase project's connection string)"
command -v psql >/dev/null || die "missing psql — install postgresql client (brew install libpq, apt install postgresql-client)"

log "Applying ${SQL_PATH} to DATABASE_URL"
psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -f "${SQL_PATH}"
ok "Schema applied."
