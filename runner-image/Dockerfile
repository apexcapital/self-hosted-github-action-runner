# syntax=docker/dockerfile:1

ARG RUNNER_VERSION=2.328.0
ARG BASE_IMAGE=debian:bookworm-slim
ARG TARGETARCH

############################################
# Builder: download & extract GitHub runner
############################################
FROM ${BASE_IMAGE} AS builder
ARG RUNNER_VERSION
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tar gzip \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /runner
# Choose correct runner architecture build artifact
ARG TARGETARCH
RUN set -eux; \
        case "${TARGETARCH:-x86_64}" in \
            arm64|aarch64) ARCH=arm64 ;; \
            amd64|x86_64) ARCH=x64 ;; \
            *) ARCH=x64 ;; \
        esac; \
        echo "Downloading runner for arch=${ARCH}"; \
        curl -fsSL "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${ARCH}-${RUNNER_VERSION}.tar.gz" \
            | tar zx --strip-components=1; \
        chmod +x bin/*

############################################
# Runtime: Debian Bookworm-Slim + Docker & .NET deps
############################################
FROM ${BASE_IMAGE} AS runtime
ARG RUNNER_VERSION
ENV DEBIAN_FRONTEND=noninteractive

# Core deps + Docker Engine (dockerd + CLI + buildx + compose)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
     ca-certificates curl gnupg wget gosu jq xz-utils pigz iptables iproute2 unzip zip \
    python3 python3-venv python3-pip \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
     | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
 && chmod a+r /etc/apt/keyrings/docker.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
     https://download.docker.com/linux/debian bookworm stable" \
     > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
     docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r actions \
 && useradd -r -g actions -d /home/actions -m -s /bin/bash actions

# GitHub runner files
COPY --from=builder --chown=actions:actions /runner /actions-runner
RUN /actions-runner/bin/installdependencies.sh || true

# Workspace dirs
RUN mkdir -p /actions-runner/_work /actions-runner/_tool \
 && chown -R actions:actions /actions-runner/_work /actions-runner/_tool

# DinD state (optional but recommended)
VOLUME ["/var/lib/docker"]

# Apex network configuration
COPY daemon.json /etc/docker/daemon.json

# Entrypoint (when building from the runner-image directory the entrypoint is local)
COPY runner-image/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /actions-runner
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
