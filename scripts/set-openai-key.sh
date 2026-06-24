#!/usr/bin/env bash
# One-shot: read OPENAI_API_KEY (prompt or env), inject into the
# volatix-agents-secrets K8s Secret, then roll the agents deployment.

set -euo pipefail
unset SDKROOT

if [ -z "${OPENAI_API_KEY:-}" ]; then
    read -r -s -p "OPENAI_API_KEY: " OPENAI_API_KEY
    echo
fi

if [ -z "${OPENAI_API_KEY}" ]; then
    echo "no key provided" >&2
    exit 1
fi

kubectl create secret generic volatix-agents-secrets \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/volatix-agents
echo "done — agents deployment rolling"
