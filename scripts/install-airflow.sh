#!/usr/bin/env bash
# Volatix-AI — install Apache Airflow into the local cluster (Phase 4.1).
#
# Idempotent. Adds the apache-airflow Helm repo, installs Airflow into the
# `airflow` namespace, and ConfigMap-mounts the project's DAG folder so
# `airflow/dags/retraining_pipeline.py` is picked up automatically.

set -euo pipefail

AIRFLOW_NAMESPACE="${AIRFLOW_NAMESPACE:-airflow}"
AIRFLOW_RELEASE="${AIRFLOW_RELEASE:-airflow}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600s}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAG_DIR="${REPO_ROOT}/airflow/dags"

log()  { printf "\033[1;34m▶\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

command -v helm >/dev/null    || die "missing helm"
command -v kubectl >/dev/null || die "missing kubectl"

[ -d "${DAG_DIR}" ] || die "missing DAG dir ${DAG_DIR}"

log "Ensuring apache-airflow Helm repo is registered"
if helm repo list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "apache-airflow"; then
    ok "apache-airflow repo already registered"
else
    helm repo add apache-airflow https://airflow.apache.org
    ok "Added apache-airflow repo"
fi
helm repo update apache-airflow >/dev/null
ok "Helm repo cache refreshed"

log "Creating namespace ${AIRFLOW_NAMESPACE}"
kubectl create namespace "${AIRFLOW_NAMESPACE}" 2>/dev/null || true

log "Packaging DAGs into ConfigMap volatix-dags"
kubectl create configmap volatix-dags \
    --from-file="${DAG_DIR}" \
    -n "${AIRFLOW_NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -

log "Installing/Upgrading Airflow release '${AIRFLOW_RELEASE}'"
helm upgrade --install "${AIRFLOW_RELEASE}" apache-airflow/airflow \
    --namespace "${AIRFLOW_NAMESPACE}" \
    --set "dags.persistence.enabled=false" \
    --set "dags.gitSync.enabled=false" \
    --set "config.core.load_examples=False" \
    --set "executor=KubernetesExecutor" \
    --set "extraVolumes[0].name=volatix-dags" \
    --set "extraVolumes[0].configMap.name=volatix-dags" \
    --set "extraVolumeMounts[0].name=volatix-dags" \
    --set "extraVolumeMounts[0].mountPath=/opt/airflow/dags/volatix" \
    --wait \
    --timeout "${WAIT_TIMEOUT}"

ok "Airflow Ready in ${AIRFLOW_NAMESPACE}"
kubectl get pods -n "${AIRFLOW_NAMESPACE}"

echo
echo "Open the Airflow UI with:"
echo "  kubectl port-forward -n ${AIRFLOW_NAMESPACE} svc/${AIRFLOW_RELEASE}-webserver 8080:8080"
echo "Default credentials: admin / admin"
