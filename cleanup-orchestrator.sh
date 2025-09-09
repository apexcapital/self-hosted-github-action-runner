#!/bin/bash

# Safe cleanup script for GitHub Actions Runner Orchestrator
# This script only removes resources tagged with our orchestrator ID

set -e

ORCHESTRATOR_ID="${ORCHESTRATOR_ID:-apex-runner-orchestrator}"
DRY_RUN="${DRY_RUN:-false}"

echo "GitHub Actions Runner Orchestrator Cleanup"
echo "=========================================="
echo "Orchestrator ID: ${ORCHESTRATOR_ID}"
echo "Dry Run: ${DRY_RUN}"
echo ""

# Function to execute or show command based on dry run mode
execute_command() {
    local cmd="$1"
    local description="$2"
    
    if [ "$DRY_RUN" = "true" ]; then
        echo "[DRY RUN] Would execute: $cmd"
        echo "  Description: $description"
    else
        echo "Executing: $description"
        eval "$cmd"
    fi
}

echo "1. Stopping and removing orchestrator containers..."
ORCHESTRATOR_CONTAINERS=$(docker ps -a -q --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" --filter "label=type=orchestrator-container" 2>/dev/null || true)
if [ -n "$ORCHESTRATOR_CONTAINERS" ]; then
    execute_command "docker stop $ORCHESTRATOR_CONTAINERS" "Stop orchestrator containers"
    execute_command "docker rm $ORCHESTRATOR_CONTAINERS" "Remove orchestrator containers"
else
    echo "  No orchestrator containers found"
fi

echo ""
echo "2. Stopping and removing runner containers..."
RUNNER_CONTAINERS=$(docker ps -a -q --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" --filter "label=type=runner-container" 2>/dev/null || true)
if [ -n "$RUNNER_CONTAINERS" ]; then
    execute_command "docker stop $RUNNER_CONTAINERS" "Stop runner containers"
    execute_command "docker rm $RUNNER_CONTAINERS" "Remove runner containers"
else
    echo "  No runner containers found"
fi

echo ""
echo "3. Removing volumes..."
VOLUMES=$(docker volume ls -q --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" 2>/dev/null || true)
if [ -n "$VOLUMES" ]; then
    for volume in $VOLUMES; do
        execute_command "docker volume rm $volume" "Remove volume: $volume"
    done
else
    echo "  No volumes found"
fi

echo ""
echo "4. Removing networks..."
NETWORKS=$(docker network ls -q --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" 2>/dev/null || true)
if [ -n "$NETWORKS" ]; then
    for network in $NETWORKS; do
        execute_command "docker network rm $network" "Remove network: $network"
    done
else
    echo "  No networks found"
fi

echo ""
echo "5. Removing unused images..."
IMAGES=$(docker images -q --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" 2>/dev/null || true)
if [ -n "$IMAGES" ]; then
    for image in $IMAGES; do
        # Check if image is in use by any container
        IN_USE=$(docker ps -a --filter "ancestor=$image" -q 2>/dev/null || true)
        if [ -z "$IN_USE" ]; then
            execute_command "docker rmi $image" "Remove unused image: $image"
        else
            echo "  Skipping image $image (in use by containers)"
        fi
    done
else
    echo "  No images found"
fi

echo ""
if [ "$DRY_RUN" = "true" ]; then
    echo "Dry run complete. No resources were actually removed."
    echo "To perform the actual cleanup, run: DRY_RUN=false $0"
else
    echo "Cleanup complete!"
fi

echo ""
echo "Remaining resources with orchestrator-id=${ORCHESTRATOR_ID}:"
echo "Containers:"
docker ps -a --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" --format "table {{.Names}}\t{{.Status}}\t{{.Labels}}" 2>/dev/null || echo "  None"
echo "Volumes:"
docker volume ls --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" --format "table {{.Name}}\t{{.Labels}}" 2>/dev/null || echo "  None"
echo "Networks:"
docker network ls --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" --format "table {{.Name}}\t{{.Labels}}" 2>/dev/null || echo "  None"
echo "Images:"
docker images --filter "label=orchestrator-id=${ORCHESTRATOR_ID}" --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}" 2>/dev/null || echo "  None"
