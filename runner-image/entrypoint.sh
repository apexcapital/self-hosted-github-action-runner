#!/usr/bin/env bash
set -euo pipefail

cd /actions-runner
 
# Read orchestration environment flags
# RUNNER_LABELS: comma-separated labels provided by orchestrator
# NO_DEFAULT_LABELS: if true, do not append default labels
# UNSET_CONFIG_VARS: if true and deregistration disabled, unset sensitive vars before running
# START_DOCKER_SERVICE: if false, skip starting dockerd (use host socket)
# DISABLE_AUTOMATIC_DEREGISTRATION: if true, skip unregister on shutdown
# DEBUG_OUTPUT: if true, enable extra shell tracing

DEFAULT_LABELS="docker-dind,linux,self-hosted,optimized"

if [[ "${DEBUG_OUTPUT:-false}" == "true" ]]; then
  set -x
fi

# Build final labels list
if [[ "${NO_DEFAULT_LABELS:-false}" == "true" ]]; then
  LABELS="${RUNNER_LABELS:-}"
else
  if [[ -n "${RUNNER_LABELS:-}" ]]; then
    LABELS="${RUNNER_LABELS},${DEFAULT_LABELS}"
  else
    LABELS="${DEFAULT_LABELS}"
  fi
fi

# Normalize empty LABELS to empty string
LABELS="$(echo "$LABELS" | sed 's/^,//;s/,$//')"

start_dind() {
  export DOCKER_HOST="unix:///var/run/docker.sock"
  export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"

  mkdir -p /var/run /var/lib/docker /var/log

  if ! command -v dockerd >/dev/null 2>&1; then
    echo "ERROR: dockerd not installed; install docker-ce & containerd.io." >&2
    exit 1
  fi

  # After dockerd starts, ensure the 'actions' user is in the group that owns
  # the Docker socket so it can connect to the daemon. We handle variable
  # GIDs from the host by creating a group with the socket GID when needed.

  echo "▶ Starting dockerd (DinD)…"
  dockerd \
    --host=unix:///var/run/docker.sock \
    --data-root="${DOCKER_DATA_ROOT:-/var/lib/docker}" \
    --storage-driver="${DOCKER_DRIVER:-overlay2}" \
    --exec-opt "native.cgroupdriver=${DOCKER_CGROUP_DRIVER:-cgroupfs}" \
    --iptables=true \
    --log-level="${DOCKERD_LOG_LEVEL:-info}" \
    > /var/log/dockerd.log 2>&1 &
  DIND_PID=$!

  # Wait for daemon to be ready
  for i in {1..60}; do
    if docker version >/dev/null 2>&1; then
      echo "✔ dockerd is ready"
      ensure_docker_socket_access || true
      return 0
    fi
    sleep 1
  done
  echo "✖ timed out waiting for dockerd; last 200 lines:" >&2
  tail -n 200 /var/log/dockerd.log || true
  exit 1
}

# Ensure the actions user can talk to Docker via the mounted socket. If the
# socket exists, find its group id (GID) and create/add a group with that GID
# so the 'actions' user may be added to it. This handles the common pattern of
# bind-mounting /var/run/docker.sock from the host (where the socket GID may
# not be the same as the 'docker' group inside the image).
ensure_docker_socket_access() {
  if [[ -S "/var/run/docker.sock" ]]; then
    # Get gid of socket
    socket_gid=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || true)
    if [[ -n "$socket_gid" ]]; then
      # If a group already exists with that gid, use it. Otherwise create one.
      existing_grp=$(getent group "${socket_gid}" | cut -d: -f1 || true)
      if [[ -n "$existing_grp" ]]; then
        docker_grp="$existing_grp"
      else
        # create a group named docker-host-GID to avoid collisions
        docker_grp="docker-host-${socket_gid}"
        groupadd -g "$socket_gid" "$docker_grp" || true
      fi

      # Add actions user to the group
      usermod -aG "$docker_grp" actions || true
      echo "Added user 'actions' to group $docker_grp (gid=$socket_gid)"
    fi
  fi
}

stop_dind() {
  if [[ -n "${DIND_PID:-}" ]] && kill -0 "$DIND_PID" 2>/dev/null; then
    echo "⏹ stopping dockerd…"
    kill "$DIND_PID" || true
    wait "$DIND_PID" || true
  fi
}

cleanup() {
  echo "⏏️  Unregistering runner…"
  if [[ "${DISABLE_AUTOMATIC_DEREGISTRATION:-false}" == "true" ]]; then
    echo "Automatic deregistration disabled; skipping unregister."
  else
    if [[ -f .runner && -n "${RUNNER_TOKEN:-}" ]]; then
      gosu actions ./config.sh remove --token "${RUNNER_TOKEN}" || true
    else
      echo "Runner not configured or no token available; skipping unregister."
    fi
  fi
  stop_dind
}

trap cleanup EXIT
trap 'echo "⚙️  Signal received, shutting down…"; kill "$RUNNER_PID" 2>/dev/null || true' SIGINT SIGTERM

# Start Docker-in-Docker if requested (otherwise assume host socket will be provided)
if [[ "${START_DOCKER_SERVICE:-true}" == "true" ]]; then
  start_dind
else
  echo "▶ Skipping dockerd startup (START_DOCKER_SERVICE=false)"
fi

# Register the runner if not already registered
if [[ ! -f .runner ]]; then
  export HOME=/home/actions
  # Pass labels set via orchestrator
  if [[ -n "${LABELS}" ]]; then
    LABEL_ARG=(--labels "${LABELS}")
  else
    LABEL_ARG=()
  fi

  gosu actions ./config.sh --unattended \
    --url    "${REPO_URL}" \
    --token  "${RUNNER_TOKEN}" \
    --name   "${RUNNER_NAME:-$(hostname)}" \
    --work   "${RUNNER_WORKDIR:-_work}" "${LABEL_ARG[@]}"

  # Optionally unset sensitive config vars to avoid leaking into workflow env
  if [[ "${UNSET_CONFIG_VARS:-false}" == "true" && "${DISABLE_AUTOMATIC_DEREGISTRATION:-false}" == "true" ]]; then
    echo "▶ Unsetting sensitive config variables (UNSET_CONFIG_VARS=true and deregistration disabled)"
    unset RUNNER_TOKEN
    unset REPO_URL
  fi
fi

# Launch runner as 'actions' in background, then wait (no exec)
export HOME=/home/actions
gosu actions env \
  HOME=/home/actions \
  DOCKER_HOST="${DOCKER_HOST}" \
  DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}" \
  /actions-runner/run.sh &
RUNNER_PID=$!

wait "$RUNNER_PID"