# Volatix-AI — realfeed (Coinbase WS → Volatix tick schema)
#
# Tiny single-stage Python image. Same uid/group convention as the
# classifier + agents containers so K8s SecurityContext settings line up.

FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="volatix-realfeed" \
      org.opencontainers.image.description="Coinbase WebSocket adapter — re-emits matches as Volatix ticks"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8765 \
    PRODUCTS=BTC-USD

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 volatix \
    && useradd  --system --gid 1000 --uid 1000 --shell /usr/sbin/nologin volatix

COPY services/realfeed/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/realfeed/realfeed.py /app/realfeed.py

USER volatix
EXPOSE 8765

ENTRYPOINT ["python", "/app/realfeed.py"]
