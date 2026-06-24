#!/usr/bin/env bash
# One-shot: read GOOGLE_API_KEY (prompt or env), merge into the
# volatix-agents-secrets K8s Secret, then roll the agents deployment.

set -euo pipefail
unset SDKROOT

if [ -z "${GOOGLE_API_KEY:-}" ]; then
    read -r -s -p "GOOGLE_API_KEY: " GOOGLE_API_KEY
    echo
fi

if [ -z "${GOOGLE_API_KEY}" ]; then
    echo "no key provided" >&2
    exit 1
fi

# Preserve any existing OPENAI_API_KEY rather than blowing it away on apply.
EXISTING_OPENAI=$(kubectl get secret volatix-agents-secrets \
    -o jsonpath='{.data.OPENAI_API_KEY}' 2>/dev/null | base64 -d 2>/dev/null || true)

kubectl create secret generic volatix-agents-secrets \
    --from-literal=OPENAI_API_KEY="${EXISTING_OPENAI}" \
    --from-literal=GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/volatix-agents
echo "done — agents deployment rolling with Gemini key"
