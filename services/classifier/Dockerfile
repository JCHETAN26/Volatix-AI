# Volatix-AI — Python classifier service (Phase 4.1).
#
# Two-stage so we can train the baseline model inside the build pipeline
# (stage 1) and keep the runtime layer slim (stage 2). The same image is
# used by the Airflow KubernetesPodOperator that runs nightly retraining —
# entrypoint is selected via the K8s args field.

# ---------------------------------------------------------------------------
# Stage 1 — install deps + bake a baseline model
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY services/classifier/requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

COPY services/classifier ./classifier
RUN PYTHONPATH=/install/lib/python3.12/site-packages:/build \
    python classifier/scripts/train_baseline.py \
        --out /build/classifier/models/baseline.txt

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="volatix-classifier" \
      org.opencontainers.image.description="LightGBM anomaly classifier + Airflow trainer" \
      org.opencontainers.image.source="https://github.com/JCHETAN26/Volatix-AI" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KAFKA_BROKERS="" \
    MODEL_PATH="/models/baseline.txt"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 volatix \
    && useradd  --system --gid 1000 --uid 1000 --shell /usr/sbin/nologin volatix \
    && mkdir -p /models /app \
    && chown -R volatix:volatix /models /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/classifier /app/classifier
COPY --from=builder /build/classifier/models/baseline.txt /models/baseline.txt

WORKDIR /app
USER volatix

# Default entrypoint runs the streaming consumer. Airflow's
# KubernetesPodOperator overrides args=[...] to invoke the trainer:
#   command: ["python", "-m", "classifier.trainer"]
ENTRYPOINT ["python", "-m", "classifier.main"]
