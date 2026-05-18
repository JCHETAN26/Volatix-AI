# ChainGuard-Core — multi-stage container build (Phase 3 / Task 3.1).
#
# Stage 1 ("builder"): full Debian toolchain — apt installs the same packages
#   cpp-ci uses (librdkafka-dev, libsimdjson-dev, libboost-system-dev, libssl-dev)
#   then compiles a Release binary under -Wall -Wextra -Werror.
#
# Stage 2 ("runtime"): Google distroless/cc-debian12:nonroot. We ship the
#   stripped binary plus the exact set of shared libraries that `ldd`
#   reports, copied via cp -L into the same /usr/lib/x86_64-linux-gnu
#   layout the linker already knows about. No package manager, no shell,
#   non-root by default. Target footprint: < 150 MB.
#
# Build:    docker build -t chainguard-core:dev .
# Run:      docker run --rm chainguard-core:dev --version
# Size:     docker image inspect chainguard-core:dev --format '{{.Size}}'

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        pkg-config \
        librdkafka-dev \
        libssl-dev \
        libboost-system-dev \
        libsimdjson-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Copy only what the C++ build needs — keeps the cache friendly and the
# image clean if the build context expands later.
COPY CMakeLists.txt ./
COPY src/ ./src/

RUN cmake -B build -S . -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --parallel \
    && strip build/bin/chainguard

# Resolve the binary's shared-library dependencies into a staging tree so
# stage 2 can copy them in a single layer. `cp -L --parents` preserves the
# /usr/lib/x86_64-linux-gnu/... path under /chainguard-deps/.
RUN mkdir -p /chainguard-deps \
    && ldd build/bin/chainguard \
       | awk '/=>/ && $3 ~ /^\// {print $3}' \
       | sort -u \
       | xargs -I {} cp -L --parents {} /chainguard-deps/ \
    && cp -L --parents /lib64/ld-linux-x86-64.so.2 /chainguard-deps/ 2>/dev/null || true

# ---------------------------------------------------------------------------
# Stage 2: distroless runtime
# ---------------------------------------------------------------------------
FROM gcr.io/distroless/cc-debian12:nonroot AS runtime

# OCI labels for image inventory / supply-chain tooling.
LABEL org.opencontainers.image.title="chainguard-core" \
      org.opencontainers.image.description="Low-latency streaming feature engine (C++20)" \
      org.opencontainers.image.source="https://github.com/JCHETAN26/Volatix-AI" \
      org.opencontainers.image.licenses="Proprietary"

# Default operational telemetry goes straight to stdout (Phase 3.1 acceptance).
ENV KAFKA_BROKERS="" \
    WS_URL=""

COPY --from=builder /chainguard-deps/ /
COPY --from=builder /src/build/bin/chainguard /usr/local/bin/chainguard

# `nonroot` (uid=65532) is the default user in distroless/cc-debian12:nonroot.
USER nonroot
ENTRYPOINT ["/usr/local/bin/chainguard"]
CMD ["--version"]
