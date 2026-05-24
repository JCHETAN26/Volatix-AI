"""ChainGuard-Core — nightly LLM eval DAG (Phase 6 / Task 6.4).

Runs the chainguard-agents image as an ephemeral KubernetesPodOperator
worker. The worker replays the curated 200-case fixture through the
LangGraph cluster, scores each case with Ragas faithfulness +
answer_relevancy + binary freeze_correctness, and writes one eval_run
row + 200 eval_case_result rows into Postgres.

Same architectural shape as the retraining DAG: scheduler stays light,
heavy work happens in a fat ephemeral pod that can be sized independently.

Triggered at 03:00 UTC daily — one hour after the retraining DAG so the
classifier the agents lean on has the freshest model. catchup off.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s


DEFAULT_ARGS = {
    "owner": "chainguard",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

AGENTS_IMAGE = os.getenv("AGENTS_IMAGE", "chainguard-agents:dev")
DB_SECRET_NAME = os.getenv("DB_SECRET_NAME", "chainguard-db")
AGENTS_SECRET_NAME = os.getenv("AGENTS_SECRET_NAME", "chainguard-agents-secrets")
AGENTS_CONFIG_MAP = os.getenv("AGENTS_CONFIG_MAP", "chainguard-agents-config")
EVAL_NAMESPACE = os.getenv("EVAL_NAMESPACE", "default")


# Pull the same env shape the agents Deployment uses, so the eval runner
# sees an identical (LLM provider, model, prompt version, Qdrant URL)
# environment to what the live consumer sees. Keeps the eval honest:
# what we score is what the live agents actually produce.
env_vars = [
    k8s.V1EnvVar(
        name="DATABASE_URL",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name=DB_SECRET_NAME, key="DATABASE_URL",
            ),
        ),
    ),
    k8s.V1EnvVar(
        name="GOOGLE_API_KEY",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name=AGENTS_SECRET_NAME, key="GOOGLE_API_KEY", optional=True,
            ),
        ),
    ),
    k8s.V1EnvVar(
        name="OPENAI_API_KEY",
        value_from=k8s.V1EnvVarSource(
            secret_key_ref=k8s.V1SecretKeySelector(
                name=AGENTS_SECRET_NAME, key="OPENAI_API_KEY", optional=True,
            ),
        ),
    ),
]

env_from = [
    k8s.V1EnvFromSource(
        config_map_ref=k8s.V1ConfigMapEnvSource(name=AGENTS_CONFIG_MAP),
    ),
]


with DAG(
    dag_id="chainguard_eval",
    description="Nightly Ragas + binary correctness eval of the LangGraph agent cluster",
    schedule="0 3 * * *",  # 1h after retraining DAG (02:00)
    start_date=datetime(2026, 5, 23),
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["chainguard", "phase-6", "llm-eval"],
) as dag:

    eval_run = KubernetesPodOperator(
        task_id="agent_eval_runner",
        name="chainguard-agent-eval",
        namespace=EVAL_NAMESPACE,
        image=AGENTS_IMAGE,
        image_pull_policy="IfNotPresent",
        cmds=["python", "-m", "agents.eval.runner"],
        arguments=[
            "--notes",
            "scheduled nightly run for {{ ds }}",
        ],
        env_vars=env_vars,
        env_from=env_from,
        # 3GB ceiling because Ragas + langchain + langgraph + lightgbm
        # all live in one process; the streaming agents pod (1Gi) OOMs
        # if you run the eval inline. See Phase 6 Day 2-3 commit notes.
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "1Gi"},
            limits={"cpu": "2000m", "memory": "3Gi"},
        ),
        is_delete_operator_pod=True,
        get_logs=True,
    )
