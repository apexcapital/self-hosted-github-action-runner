#!/usr/bin/env bash
set -euo pipefail
cd /actions-runner

#─────────────────────────────────────────────────
# Docker socket setup for non-root 'actions' user
#─────────────────────────────────────────────────
setup_docker() {
  # Prefer DOCKER_HOST if set to a unix socket; else default path
  local sock_path="/var/run/docker.sock"
  if [[ "${DOCKER_HOST:-}" =~ ^unix:// ]]; then
    sock_path="${DOCKER_HOST#unix://}"
  fi

  if [[ -S "${sock_path}" ]]; then
    # Ensure DOCKER_HOST is set for child processes
    export DOCKER_HOST="unix://${sock_path}"
    export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
    export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"

    # Map socket GID to a group visible in the container, then add 'actions'
    local sock_gid group_name
    sock_gid="$(stat -c '%g' "${sock_path}")"
    # If a group with this GID already exists, reuse it; else create 'dockersock'
    group_name="$(getent group "${sock_gid}" | cut -d: -f1 || true)"
    if [[ -z "${group_name}" ]]; then
      group_name="dockersock"
      # groupadd may race across restarts; ignore if it already exists
      groupadd -g "${sock_gid}" "${group_name}" 2>/dev/null || true
    fi
    usermod -aG "${group_name}" actions || true

    # Optional sanity (non-fatal). Avoid -e exit on failure.
    if command -v docker >/dev/null 2>&1; then
      if ! gosu actions docker info >/dev/null 2>&1; then
        echo "NOTE: Docker CLI present but cannot access ${sock_path} yet." >&2
      fi
    else
      echo "WARNING: Docker CLI not installed inside the container." >&2
    fi
  else
    echo "WARNING: Docker socket not found at ${sock_path}. Mount /var/run/docker.sock." >&2
  fi
}

#─────────────────────────────────────────────────
# Cleanup: unregister the runner
#─────────────────────────────────────────────────
cleanup() {
  echo "⏏️  Unregistering runner…"
  gosu actions ./config.sh remove \
    --token "$RUNNER_TOKEN"
}

#─────────────────────────────────────────────────
# Traps
#─────────────────────────────────────────────────
trap cleanup EXIT
trap 'echo "⚙️  Signal received, shutting down runner…"; kill "$RUNNER_PID"' SIGINT SIGTERM

#─────────────────────────────────────────────────
# Ensure Docker access before runner starts
#─────────────────────────────────────────────────
setup_docker

#─────────────────────────────────────────────────
# Register the runner if not already registered
#─────────────────────────────────────────────────
if [ ! -f .runner ]; then
  gosu actions ./config.sh --unattended \
    --url    "$REPO_URL" \
    --token  "$RUNNER_TOKEN" \
    --name   "${RUNNER_NAME:-$(hostname)}" \
    --work   "${RUNNER_WORKDIR:-_work}"
fi

#─────────────────────────────────────────────────
# Start the runner
#─────────────────────────────────────────────────
gosu actions ./run.sh &
RUNNER_PID=$!
wait "$RUNNER_PID"