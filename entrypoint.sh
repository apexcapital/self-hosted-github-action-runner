#!/usr/bin/env bash
set -euo pipefail
cd /actions-runner

#─────────────────────────────────────────────────
# Cleanup function: will unregister the runner
#─────────────────────────────────────────────────
cleanup() {
  echo "⏏️  Unregistering runner…"
  gosu actions ./config.sh remove \
    --token "$RUNNER_TOKEN"
}

#─────────────────────────────────────────────────
# Trap EXIT so cleanup() always runs when this script exits,
# and forward SIGINT/SIGTERM to the runner child process
#─────────────────────────────────────────────────
trap cleanup EXIT
trap 'echo "⚙️  Signal received, shutting down runner…"; kill "$RUNNER_PID"' SIGINT SIGTERM

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
# Start the runner in the background, save its PID,
# then wait so this script stays alive as PID 1
#─────────────────────────────────────────────────
gosu actions ./run.sh &
RUNNER_PID=$!
wait "$RUNNER_PID"
