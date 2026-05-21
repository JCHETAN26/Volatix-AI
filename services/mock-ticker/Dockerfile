# ChainGuard-Core — mock-ticker (in-cluster synthetic Polygon-flavored feed)
#
# Image wraps scripts/mock-ticker.py so the K8s engine deployment can
# consume a stable WebSocket URL instead of relying on a laptop-side
# producer. Same uid/group as the rest of the chainguard services.

FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="chainguard-mock-ticker" \
      org.opencontainers.image.description="Synthetic Polygon-flavored tick generator for the in-cluster live pipeline"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir websockets==13.1 \
    && groupadd --system --gid 1000 chainguard \
    && useradd  --system --gid 1000 --uid 1000 --shell /usr/sbin/nologin chainguard

# The script ships at the repo root so local `make mock-ticker` keeps
# working unmodified; we just bundle a copy into the image.
COPY scripts/mock-ticker.py /app/mock-ticker.py

USER chainguard
EXPOSE 8765

ENTRYPOINT ["python", "/app/mock-ticker.py"]
CMD ["--host", "0.0.0.0", "--port", "8765", "--rate", "25000"]
