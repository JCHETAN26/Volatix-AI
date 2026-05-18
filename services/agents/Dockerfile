# ChainGuard-Core — agents service container (Phase 4.2).
#
# python:3.12-slim base, nonroot uid 1000. langgraph + langchain stacks are
# heavy enough that we keep a single-stage build for readability — the
# image is still well under the size budget for an inference service.

FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="chainguard-agents" \
      org.opencontainers.image.description="LangGraph 3-tier multi-agent risk pipeline" \
      org.opencontainers.image.source="https://github.com/JCHETAN26/Volatix-AI" \
      org.opencontainers.image.licenses="Proprietary"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KAFKA_BROKERS="" \
    LLM_PROVIDER=""

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 chainguard \
    && useradd  --system --gid 1000 --uid 1000 --shell /usr/sbin/nologin chainguard

COPY services/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Service code last so it doesn't bust the deps cache.
COPY services/agents /app/agents

USER chainguard

ENTRYPOINT ["python", "-m", "agents.main"]
