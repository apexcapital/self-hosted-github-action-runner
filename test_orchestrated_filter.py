#!/usr/bin/env python3
"""
Test script to verify that the orchestrated runner filtering works correctly.
This script simulates the filtering logic without making actual API calls.
"""

import asyncio
from typing import List, Dict, Any


class MockGitHubClient:
    """Mock GitHub client for testing the orchestrated runner filtering."""

    def __init__(self):
        # Simulate a mix of orchestrated and non-orchestrated runners
        self.mock_runners = [
            {
                "id": 1,
                "name": "runner-1-orchestrated",
                "status": "online",
                "labels": [
                    {"name": "self-hosted"},
                    {"name": "linux"},
                    {"name": "x64"},
                    {"name": "orchestrated"},
                ],
            },
            {
                "id": 2,
                "name": "runner-2-manual",
                "status": "online",
                "labels": [{"name": "self-hosted"}, {"name": "linux"}, {"name": "x64"}],
            },
            {
                "id": 3,
                "name": "runner-3-orchestrated",
                "status": "offline",
                "labels": [
                    {"name": "self-hosted"},
                    {"name": "linux"},
                    {"name": "x64"},
                    {"name": "orchestrated"},
                    {"name": "docker-dind"},
                ],
            },
            {
                "id": 4,
                "name": "runner-4-other-system",
                "status": "online",
                "labels": [
                    {"name": "self-hosted"},
                    {"name": "windows"},
                    {"name": "x64"},
                    {"name": "other-label"},
                ],
            },
        ]

    async def get_runners(self) -> List[Dict[str, Any]]:
        """Mock implementation of get_runners."""
        return self.mock_runners

    async def get_orchestrated_runners(self) -> List[Dict[str, Any]]:
        """Get all runners that have the 'orchestrated' label."""
        try:
            all_runners = await self.get_runners()
            orchestrated_runners = []

            for runner in all_runners:
                runner_labels = [
                    label.get("name", "") for label in runner.get("labels", [])
                ]
                if "orchestrated" in runner_labels:
                    orchestrated_runners.append(runner)

            return orchestrated_runners
        except Exception as e:
            print(f"Failed to get orchestrated runners: {e}")
            return []


async def test_orchestrated_filtering():
    """Test the orchestrated runner filtering logic."""
    print("🧪 Testing Orchestrated Runner Filtering")
    print("=" * 50)

    client = MockGitHubClient()

    # Get all runners
    all_runners = await client.get_runners()
    print(f"📊 Total runners found: {len(all_runners)}")
    for runner in all_runners:
        labels = [label.get("name", "") for label in runner.get("labels", [])]
        print(f"  - {runner['name']}: {labels}")

    print()

    # Get only orchestrated runners
    orchestrated_runners = await client.get_orchestrated_runners()
    print(f"🎯 Orchestrated runners found: {len(orchestrated_runners)}")
    for runner in orchestrated_runners:
        labels = [label.get("name", "") for label in runner.get("labels", [])]
        print(f"  - {runner['name']}: {labels}")

    print()

    # Verify filtering
    expected_orchestrated = ["runner-1-orchestrated", "runner-3-orchestrated"]
    actual_orchestrated = [r["name"] for r in orchestrated_runners]

    print("✅ Verification:")
    print(f"  Expected orchestrated runners: {expected_orchestrated}")
    print(f"  Actual orchestrated runners: {actual_orchestrated}")

    if set(expected_orchestrated) == set(actual_orchestrated):
        print("  🎉 Test PASSED: Filtering works correctly!")
        print("  ✅ Only runners with 'orchestrated' label are included")
        print("  ✅ Manual and other system runners are safely excluded")
    else:
        print("  ❌ Test FAILED: Filtering not working as expected")
        return False

    # Simulate cleanup scenario
    print()
    print("🧹 Simulating Cleanup Scenario:")
    print("  Local Docker runners: ['runner-1-orchestrated']")
    print(
        "  GitHub orchestrated runners: ['runner-1-orchestrated', 'runner-3-orchestrated']"
    )

    local_runners = {"runner-1-orchestrated"}
    github_orchestrated = {r["name"] for r in orchestrated_runners}
    orphaned = github_orchestrated - local_runners

    print(f"  Orphaned orchestrated runners to cleanup: {list(orphaned)}")
    print("  ✅ runner-2-manual and runner-4-other-system will be left alone!")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_orchestrated_filtering())
    exit(0 if success else 1)
