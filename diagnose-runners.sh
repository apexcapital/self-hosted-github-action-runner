#!/bin/bash

# Diagnostic script to check runner container health
# This script will help debug why containers are failing

echo "🔍 GitHub Runner Container Diagnostics"
echo "====================================="

# Check if we have any runner containers
echo "1. Current github-runner containers:"
docker ps -a --filter "name=github-runner" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.CreatedAt}}"

echo ""
echo "2. Recent container logs (if any exist):"

# Get the most recent container
LATEST_CONTAINER=$(docker ps -a --filter "name=github-runner" --format "{{.Names}}" | head -1)

if [ -n "$LATEST_CONTAINER" ]; then
    echo "Latest container: $LATEST_CONTAINER"
    echo "Logs:"
    docker logs "$LATEST_CONTAINER" 2>&1 | tail -50
    
    echo ""
    echo "3. Container inspection:"
    docker inspect "$LATEST_CONTAINER" | jq '.[] | {
        State: .State,
        Config: {
            Env: .Config.Env,
            Image: .Config.Image
        },
        Mounts: .Mounts
    }'
else
    echo "No github-runner containers found"
fi

echo ""
echo "4. Docker images available:"
docker images | grep -E "(github-runner|myoung34)"

echo ""
echo "5. Network status:"
docker network ls | grep runner

echo ""
echo "6. Orchestrator container logs (last 20 lines):"
if docker ps --filter "name=orchestrator" --quiet | head -1 > /dev/null; then
    docker logs orchestrator 2>&1 | tail -20
else
    echo "Orchestrator container not running"
fi
