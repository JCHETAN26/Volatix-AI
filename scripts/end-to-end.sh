#!/usr/bin/env bash
# Volatix-AI — end-to-end timing test (Phase 5.2 acceptance).
#
# Prereqs:
#   * `demo-up.sh` has the cluster stack running.
#   * `make port-forward-kafka` is live (Kafka @ localhost:9092).
#   * DATABASE_URL is set in this shell (Supabase or any Postgres).
#   * psql is installed locally.
#
# Flow:
#   1. Stamp the latest agent_report id.
#   2. Publish a flash-loan FeatureFrame burst onto financial-features
#      using scripts/inject-features.py.
#   3. Poll Postgres for a new agent_report row newer than the stamp.
#   4. Print the wall-clock delta between inject-time and DB-write-time.
#   5. Exit non-zero if it exceeds ACCEPTANCE_CEILING_S (default 5s).
#      The build plan's 1-second target only holds with LLM_PROVIDER=mock
#      and the local stack idle; this script reports the actual number
#      either way.
#
# Usage:
#   ./scripts/end-to-end.sh
#   COUNT=20 ACCEPTANCE_CEILING_S=8 ./scripts/end-to-end.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

BROKERS="${BROKERS:-localhost:9092}"
COUNT="${COUNT:-5}"
TIMEOUT_S="${TIMEOUT_S:-30}"
ACCEPTANCE_CEILING_S="${ACCEPTANCE_CEILING_S:-5}"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

command -v python3 >/dev/null || die "missing python3"
command -v psql    >/dev/null || die "missing psql (brew install libpq)"
[ -n "${DATABASE_URL:-}" ] || die "set DATABASE_URL first (your Supabase connection string)"

run_sql() {
    psql "${DATABASE_URL}" -tAc "$1"
}

# 1. Stamp
log "Stamping latest agent_report id"
START_MAX_ID="$(run_sql 'SELECT COALESCE(MAX(id), 0) FROM agent_report;' | tr -d ' ')"
[ -n "${START_MAX_ID}" ] || START_MAX_ID=0
log "  start_max_id=${START_MAX_ID}"

# 2. Inject
log "Injecting ${COUNT} flash-loan feature frame(s) onto financial-features"
INJECT_T0_NS=$(python3 -c 'import time; print(time.time_ns())')
python3 scripts/inject-features.py --brokers "${BROKERS}" --count "${COUNT}"
ok "frames injected"

# 3. Poll for the first new agent_report row
log "Polling for the first new agent_report row (timeout ${TIMEOUT_S}s)"
DEADLINE=$(( $(date +%s) + TIMEOUT_S ))
while :; do
    NEW_ROW="$(run_sql "SELECT id, ts_ns, anomaly_score, confidence, enforced, \
        EXTRACT(EPOCH FROM created_at) * 1000000000 \
        FROM agent_report WHERE id > ${START_MAX_ID} \
        ORDER BY id ASC LIMIT 1;")"
    if [ -n "${NEW_ROW}" ]; then break; fi
    if [ "$(date +%s)" -ge "${DEADLINE}" ]; then
        die "no new agent_report row within ${TIMEOUT_S}s — check classifier + agents pod logs"
    fi
    sleep 0.2
done

NEW_ID=$(echo "${NEW_ROW}" | cut -d'|' -f1)
TS_NS=$(echo "${NEW_ROW}" | cut -d'|' -f2)
SCORE=$(echo "${NEW_ROW}" | cut -d'|' -f3)
CONF=$(echo "${NEW_ROW}" | cut -d'|' -f4)
ENF=$(echo "${NEW_ROW}" | cut -d'|' -f5)
CREATED_NS=$(echo "${NEW_ROW}" | cut -d'|' -f6 | awk -F'.' '{print $1}')

# 4. Report timing
DELTA_NS=$(( CREATED_NS - INJECT_T0_NS ))
DELTA_MS=$(( DELTA_NS / 1000000 ))
DELTA_S=$(awk "BEGIN { printf \"%.3f\", ${DELTA_NS} / 1e9 }")

echo
ok "End-to-end pipeline drained:"
echo "  agent_report.id           = ${NEW_ID}"
echo "  anomaly_score             = ${SCORE}"
echo "  confidence                = ${CONF}"
echo "  enforced                  = ${ENF}"
echo "  injected → row written    = ${DELTA_S}s (${DELTA_MS}ms)"

# 5. Acceptance gate
CEILING_MS=$(( ACCEPTANCE_CEILING_S * 1000 ))
if [ "${DELTA_MS}" -ge "${CEILING_MS}" ]; then
    die "ABOVE acceptance ceiling of ${ACCEPTANCE_CEILING_S}s"
fi

echo
ok "  → meets acceptance (< ${ACCEPTANCE_CEILING_S}s)"
