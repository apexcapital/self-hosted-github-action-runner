# syntax=docker/dockerfile:1

ARG RUNNER_VERSION=2.328.0
ARG BASE_IMAGE=debian:bookworm-slim
ARG NODE_VERSION=22
ARG TARGETARCH

##############################
# Builder: fetch runner files
##############################
FROM ${BASE_IMAGE} AS builder
ARG RUNNER_VERSION
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tar gzip \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /runner
ARG TARGETARCH
RUN set -eux; \
  case "${TARGETARCH:-x86_64}" in \
    arm64|aarch64) ARCH=arm64 ;; \
    amd64|x86_64)  ARCH=x64 ;; \
    *)             ARCH=x64 ;; \
  esac; \
  curl -fsSL "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${ARCH}-${RUNNER_VERSION}.tar.gz" \
    -o runner.tar.gz; \
  echo "Verifying download..."; \
  tar -tzf runner.tar.gz > /dev/null; \
  tar -xzf runner.tar.gz --strip-components=1; \
  rm runner.tar.gz; \
  chmod +x bin/*

############################################
# Runtime: runner + Docker + Playwright
############################################
FROM ${BASE_IMAGE} AS runtime
ARG RUNNER_VERSION
ARG NODE_VERSION
ENV DEBIAN_FRONTEND=noninteractive

# Core utilities + Docker Engine (dockerd/cli/buildx/compose)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg wget gosu jq xz-utils pigz iptables iproute2 unzip zip \
    python3 python3-venv python3-pip \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
 && chmod a+r /etc/apt/keyrings/docker.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
    > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
 && rm -rf /var/lib/apt/lists/*

# --- Playwright system dependencies (GTK3/4, X11, GStreamer, codecs, fonts) ---
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    # Basics \
    git \
    # Core X and graphics \
    libglib2.0-0 libnspr4 libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 libdrm2 libxshmfence1 libxcursor1 libx11-xcb1 \
    # GTK stacks \
    libgtk-3-0 libgdk-pixbuf-2.0-0 libpangocairo-1.0-0 libcairo-gobject2 \
    libgtk-4-1 libgraphene-1.0-0 \
    # gstreamer \
    libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 libgstreamer-plugins-bad1.0-0 libgstreamer-gl1.0-0 \
    # media/codec libs \
    libxslt1.1 libwoff1 libvpx7 libevent-2.1-7 libopus0 libflite1 libwebpdemux2 libavif15 \
    libharfbuzz-icu0 libwebpmux3 libenchant-2-2 libsecret-1-0 libhyphen0 libmanette-0.2-0 \
    libgles2 libx264-164 \
    # runtime helpers \
    xdg-utils fonts-liberation fonts-noto-core fonts-noto-color-emoji ffmpeg libu2f-udev \
 && rm -rf /var/lib/apt/lists/*

# Non-root user for runner + Playwright cache ownership
RUN groupadd -r actions \
 && useradd -r -g actions -d /home/actions -m -s /bin/bash actions

# GitHub runner bits
COPY --from=builder --chown=actions:actions /runner /actions-runner
RUN /actions-runner/bin/installdependencies.sh || true

# Workspace dirs with proper permissions
RUN mkdir -p /actions-runner/_work /actions-runner/_tool \
 && chown -R actions:actions /actions-runner/_work /actions-runner/_tool \
 && chmod 755 /actions-runner/_work /actions-runner/_tool

# --- Node.js LTS and Playwright (install as actions user) ---
# Use NodeSource for Node.js LTS (bookworm repo node can lag)
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash - \
 && apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && npm config set fund false \
 && npm config set audit false

# Ensure ldconfig available in PATH for Playwright validation in non-root shells
ENV PATH="/sbin:/usr/sbin:${PATH}"
# Note: CI, PLAYWRIGHT_BROWSERS_PATH, and NODE_ENV are now set at runtime via orchestrator
# These ENV declarations serve as defaults if not overridden
ENV CI=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_ENV=production

# Prepare Playwright dirs with proper permissions
RUN mkdir -p /ms-playwright \
 && chown -R actions:actions /ms-playwright \
 && chmod 755 /ms-playwright

# DinD state (optional)
VOLUME ["/var/lib/docker"]

# Copy Docker daemon config with validation
COPY daemon.json /etc/docker/daemon.json
RUN test -s /etc/docker/daemon.json && chmod 644 /etc/docker/daemon.json

# Entrypoint with proper permissions
COPY runner-image/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh \
 && test -x /usr/local/bin/entrypoint.sh

# Security: Remove setuid/setgid bits from unnecessary binaries (hardening)
RUN find /usr/bin /usr/sbin /bin /sbin -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Metadata labels
LABEL org.opencontainers.image.title="GitHub Actions Self-Hosted Runner" \
      org.opencontainers.image.description="Custom runner with Docker-in-Docker and Playwright support" \
      org.opencontainers.image.version="${RUNNER_VERSION}" \
      org.opencontainers.image.vendor="Custom" \
      maintainer="nate.brandeburg"

WORKDIR /actions-runner
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]