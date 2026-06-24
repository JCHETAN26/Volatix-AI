"""Volatix-AI — daily LightGBM retraining DAG (Phase 4 / Task 4.1).

Runs the volatix-classifier image as an ephemeral KubernetesPodOperator
worker. The worker pulls yesterday's feature_log rows out of PostgreSQL,
runs Purged K-Fold cross-validation, retrains LightGBM, and writes the
new artifact + CV metrics into the `model_registry` table.

The DAG itself does no data work — that lets retraining scale by spawning
fatter K8s pods (more CPU/memory) without touching the Airflow scheduler.

Triggered at 02:00 UTC daily; catchup off so restarts don't backfill.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s


DEFAULT_ARGS = {
    "owner": "volatix",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

TRAINER_IMAGE = os.getenv("TRAINER_IMAGE", "volatix-classifier:dev")
DB_SECRET_NAME = os.getenv("DB_SECRET_NAME", "volatix-db")
MODELS_PVC = os.getenv("MODELS_PVC", "volatix-models")
NAMESPACE = os.getenv("RETRAIN_NAMESPACE", "default")


db_env = [
    k8s.V1EnvVar(
        name="DATABASE_URL",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name=DB_SECRET_NAME, key="DATABASE_URL"
            )
        ),
    ),
    k8s.V1EnvVar(name="MODEL_OUT", value="/models/latest.txt"),
]

models_volume = k8s.V1Volume(
    name="models",
    persistent_volume_claim=k8s.V1PersistentVolumeClaimVolumeSource(claim_name=MODELS_PVC),
)
models_mount = k8s.V1VolumeMount(name="models", mount_path="/models")


with DAG(
    dag_id="volatix_retraining",
    description="Nightly Purged K-Fold retraining of the LightGBM anomaly classifier",
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["volatix", "phase-4", "ml"],
) as dag:

    retrain = KubernetesPodOperator(
        task_id="retrain_lightgbm",
        name="volatix-retrain",
        namespace=NAMESPACE,
        image=TRAINER_IMAGE,
        image_pull_policy="IfNotPresent",
        cmds=["python", "-m", "classifier.trainer"],
        arguments=[
            "--day", "{{ ds }}",  # YYYY-MM-DD of the DAG run's logical date
            "--n-splits", "5",
            "--rounds", "500",
        ],
        env_vars=db_env,
        volumes=[models_volume],
        volume_mounts=[models_mount],
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "1Gi"},
            limits={"cpu": "2000m", "memory": "2Gi"},
        ),
        # Ensure the pod actually exits on failure rather than hanging.
        is_delete_operator_pod=True,
        get_logs=True,
    )
