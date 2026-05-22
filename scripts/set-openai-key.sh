#!/usr/bin/env bash
# One-shot: read OPENAI_API_KEY (prompt or env), inject into the
# chainguard-agents-secrets K8s Secret, then roll the agents deployment.

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

kubectl create secret generic chainguard-agents-secrets \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/chainguard-agents
echo "done — agents deployment rolling"
