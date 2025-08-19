#!/usr/bin/env bash
set -euo pipefail

cd /actions-runner

start_dind() {
  export DOCKER_HOST="unix:///var/run/docker.sock"
  export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"

  mkdir -p /var/run /var/lib/docker /var/log

  if ! command -v dockerd >/dev/null 2>&1; then
    echo "ERROR: dockerd not installed; install docker-ce & containerd.io." >&2
    exit 1
  fi

  # Ensure 'docker' group exists and 'actions' can access the socket
  getent group docker >/dev/null 2>&1 || groupadd -r docker
  usermod -aG docker actions || true

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
      return 0
    fi
    sleep 1
  done
  echo "✖ timed out waiting for dockerd; last 200 lines:" >&2
  tail -n 200 /var/log/dockerd.log || true
  exit 1
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
  if [[ -f .runner && -n "${RUNNER_TOKEN:-}" ]]; then
    gosu actions ./config.sh remove --token "${RUNNER_TOKEN}" || true
  else
    echo "Runner not configured; skipping unregister."
  fi
  stop_dind
}

trap cleanup EXIT
trap 'echo "⚙️  Signal received, shutting down…"; kill "$RUNNER_PID" 2>/dev/null || true' SIGINT SIGTERM

# Start Docker-in-Docker
start_dind

# Register the runner if not already registered
if [[ ! -f .runner ]]; then
  export HOME=/home/actions
  gosu actions ./config.sh --unattended \
    --url    "${REPO_URL}" \
    --token  "${RUNNER_TOKEN}" \
    --name   "${RUNNER_NAME:-$(hostname)}" \
    --work   "${RUNNER_WORKDIR:-_work}" \
    --labels "docker-dind,linux,x64,self-hosted,optimized"
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