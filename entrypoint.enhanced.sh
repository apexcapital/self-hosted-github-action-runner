#!/usr/bin/env bash
set -euo pipefail

# Enhanced entrypoint for orchestrator-managed runners
cd /actions-runner

# Environment validation
if [[ -z "${REPO_URL:-}" ]]; then
    echo "ERROR: REPO_URL environment variable is required" >&2
    exit 1
fi

if [[ -z "${RUNNER_TOKEN:-}" ]]; then
    echo "ERROR: RUNNER_TOKEN environment variable is required" >&2
    exit 1
fi

# Default values
RUNNER_NAME="${RUNNER_NAME:-$(hostname)}"
RUNNER_WORKDIR="${RUNNER_WORKDIR:-_work}"
RUNNER_LABELS="${RUNNER_LABELS:-docker-dind,linux,x64,self-hosted,orchestrated}"

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
    # Try to remove with timeout
    timeout 30 gosu actions ./config.sh remove --token "${RUNNER_TOKEN}" || {
      echo "⚠️  Warning: Runner unregistration timed out or failed"
    }
  else
    echo "Runner not configured; skipping unregister."
  fi
  stop_dind
  
  # Signal to orchestrator that we're shutting down gracefully
  echo "🎯 Runner ${RUNNER_NAME} shutting down gracefully"
}

# Enhanced signal handling for orchestrator
trap cleanup EXIT
trap 'echo "⚙️  Signal received, shutting down gracefully…"; kill "$RUNNER_PID" 2>/dev/null || true' SIGINT SIGTERM

# Start Docker-in-Docker
start_dind

# Register the runner if not already registered
if [[ ! -f .runner ]]; then
  export HOME=/home/actions
  echo "🚀 Registering runner: ${RUNNER_NAME}"
  echo "📍 Repository: ${REPO_URL}"
  echo "🏷️  Labels: ${RUNNER_LABELS}"
  
  # Add retry logic for registration
  for attempt in {1..3}; do
    if gosu actions ./config.sh --unattended \
      --url    "${REPO_URL}" \
      --token  "${RUNNER_TOKEN}" \
      --name   "${RUNNER_NAME}" \
      --work   "${RUNNER_WORKDIR}" \
      --labels "${RUNNER_LABELS}"; then
      echo "✅ Runner registered successfully on attempt ${attempt}"
      break
    else
      echo "❌ Registration attempt ${attempt} failed"
      if [[ $attempt -eq 3 ]]; then
        echo "💥 All registration attempts failed"
        exit 1
      fi
      sleep 5
    fi
  done
else
  echo "♻️  Runner already configured, starting..."
fi

# Launch runner as 'actions' in background, then wait
export HOME=/home/actions
echo "🏃 Starting runner: ${RUNNER_NAME}"

gosu actions env \
  HOME=/home/actions \
  DOCKER_HOST="${DOCKER_HOST}" \
  DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}" \
  /actions-runner/run.sh &
RUNNER_PID=$!

echo "🎯 Runner ${RUNNER_NAME} is now active (PID: ${RUNNER_PID})"

# Wait for the runner process
wait "$RUNNER_PID"
echo "🏁 Runner ${RUNNER_NAME} finished"
