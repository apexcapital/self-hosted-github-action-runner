#!/bin/bash

# Build script for the GitHub Actions Runner Orchestrator
# This script builds the orchestrator image with proper tagging for safe resource management

set -e

# Configuration
ORCHESTRATOR_ID="${ORCHESTRATOR_ID:-apex-runner-orchestrator}"
ORCHESTRATOR_VERSION="${ORCHESTRATOR_VERSION:-1.0.0}"
IMAGE_NAME="${IMAGE_NAME:-github-actions-orchestrator}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Building orchestrator image with custom tags..."
echo "Orchestrator ID: ${ORCHESTRATOR_ID}"
echo "Version: ${ORCHESTRATOR_VERSION}"
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"

# Build the image with proper labels
docker build \
    --label "managed-by=runner-orchestrator" \
    --label "orchestrator-id=${ORCHESTRATOR_ID}" \
    --label "orchestrator-version=${ORCHESTRATOR_VERSION}" \
    --label "component=orchestrator" \
    --label "built-at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    -f Dockerfile \
    .

echo "Image built successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "Labels applied:"
echo "  - managed-by=runner-orchestrator"
echo "  - orchestrator-id=${ORCHESTRATOR_ID}"
echo "  - orchestrator-version=${ORCHESTRATOR_VERSION}"
echo "  - component=orchestrator"
echo "  - built-at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
