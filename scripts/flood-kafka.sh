#!/usr/bin/env bash
# Volatix-AI — flood a Kafka topic for the Phase 3.2 KEDA test.
#
# Produces N records into `raw-ticks` so the volatix consumer group
# builds up enough lag for KEDA to scale the Deployment out. Runs inside
# an ephemeral Bitnami kafka client pod so we don't need a host-side
# librdkafka install.
#
# Usage:
#   ./scripts/flood-kafka.sh                # 50,000 records (default)
#   ./scripts/flood-kafka.sh 100000         # 100,000 records

set -euo pipefail

COUNT="${1:-50000}"
TOPIC="${TOPIC:-raw-ticks}"
KAFKA_RELEASE="${KAFKA_RELEASE:-chain-kafka}"
NAMESPACE="${NAMESPACE:-default}"
BROKER="${KAFKA_RELEASE}.${NAMESPACE}.svc.cluster.local:9092"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

command -v kubectl >/dev/null || die "missing kubectl"

log "Flooding ${COUNT} records into '${TOPIC}' via ${BROKER}"

# `seq` produces N lines, kafka-console-producer reads stdin as one record
# per line. --no-headers --restart=Never to ensure the pod exits cleanly.
kubectl run kafka-flood-$$ \
    --rm -i --tty=false \
    --image=bitnami/kafka:latest \
    --restart=Never \
    --namespace "${NAMESPACE}" \
    --command -- bash -c "
        seq 1 ${COUNT} \
            | awk '{print \"volatix-flood-\" \$1}' \
            | kafka-console-producer.sh \
                --bootstrap-server ${BROKER} \
                --topic ${TOPIC} \
                --batch-size 5000 \
                >/dev/null
    "

ok "Done. ${COUNT} records written to ${TOPIC}."
echo "Tip: watch KEDA react with:"
echo "  kubectl get pods -l app.kubernetes.io/name=volatix-engine --watch"
echo "  kubectl get hpa keda-hpa-volatix-engine --watch"
