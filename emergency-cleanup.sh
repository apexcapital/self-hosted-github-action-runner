#!/bin/bash

# Emergency cleanup script for runaway GitHub Actions runners
# This script will stop and remove all github-runner containers

set -e

echo "🚨 Emergency cleanup of runaway GitHub runners"
echo "=============================================="

# Count containers before cleanup
RUNNER_CONTAINERS=$(docker ps -a -q --filter "name=github-runner" 2>/dev/null || true)
TOTAL_COUNT=$(echo "$RUNNER_CONTAINERS" | wc -w)

echo "Found $TOTAL_COUNT github-runner containers"

if [ "$TOTAL_COUNT" -eq 0 ]; then
    echo "✅ No github-runner containers found"
    exit 0
fi

# Ask for confirmation
read -p "⚠️  Are you sure you want to stop and remove ALL github-runner containers? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 1
fi

echo "🛑 Stopping all github-runner containers..."
if [ -n "$RUNNER_CONTAINERS" ]; then
    echo "$RUNNER_CONTAINERS" | xargs docker stop 2>/dev/null || true
    echo "✅ Stopped containers"
fi

echo "🗑️  Removing all github-runner containers..."
if [ -n "$RUNNER_CONTAINERS" ]; then
    echo "$RUNNER_CONTAINERS" | xargs docker rm -f 2>/dev/null || true
    echo "✅ Removed containers"
fi

# Clean up associated volumes
echo "🧹 Cleaning up associated volumes..."
RUNNER_VOLUMES=$(docker volume ls -q --filter "label=managed-by=runner-orchestrator" 2>/dev/null || true)
if [ -n "$RUNNER_VOLUMES" ]; then
    echo "$RUNNER_VOLUMES" | xargs docker volume rm 2>/dev/null || true
    echo "✅ Cleaned up volumes"
fi

# Final count
REMAINING=$(docker ps -a -q --filter "name=github-runner" 2>/dev/null | wc -l)
echo ""
echo "🎉 Emergency cleanup completed!"
echo "   - Removed: $TOTAL_COUNT containers"
echo "   - Remaining: $REMAINING containers"

if [ "$REMAINING" -gt 0 ]; then
    echo "⚠️  Some containers may still exist. Check with: docker ps -a --filter 'name=github-runner'"
fi
