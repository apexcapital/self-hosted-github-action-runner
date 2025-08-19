# syntax=docker/dockerfile:1

############################################
# Build-time default for runner version
############################################
ARG RUNNER_VERSION=2.325.0

############################################
# Builder: download & extract GitHub runner
############################################
FROM debian:bookworm-slim AS builder
ARG RUNNER_VERSION
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      tar \
      gzip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /runner
RUN curl -fsSL \
      https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz \
    | tar zx --strip-components=1 \
 && chmod +x bin/*

############################################
# Runtime: Debian Bookworm-Slim + Docker & .NET deps
############################################
FROM debian:bookworm-slim AS runtime
ARG RUNNER_VERSION
ENV DEBIAN_FRONTEND=noninteractive

# 1) Install OS packages, Docker CLI, qemu, gosu, wget
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      docker.io \
      qemu-user-static \
      gosu \
      wget \
      docker-compose-plugin \
      iptables \
      iproute2 \
      jq \
      xz-utils \
      pigz \
 && rm -rf /var/lib/apt/lists/*

# 2) Install Docker Compose v2 plugin
RUN mkdir -p /usr/local/lib/docker/cli-plugins \
 && curl -fsSL \
      https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
      -o /usr/local/lib/docker/cli-plugins/docker-compose \
 && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# 3) Create non-root 'actions' user & group
RUN groupadd -r actions \
 && useradd -r -g actions -d /home/actions -m -s /bin/bash actions

# 4) Copy runner bits from builder as 'actions'
COPY --from=builder --chown=actions:actions /runner /actions-runner

# 5) Run the runner’s dependency installer (installdependencies.sh)
RUN /actions-runner/bin/installdependencies.sh

# 6) Prepare workspace dirs with correct ownership
RUN mkdir -p /actions-runner/_work /actions-runner/_tool \
 && chown -R actions:actions /actions-runner/_work /actions-runner/_tool

# 7) Copy and set up entrypoint
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /actions-runner

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
