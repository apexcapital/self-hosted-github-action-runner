#!/usr/bin/env python3
"""Test script to debug container age calculation issues."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.docker_client import DockerClient


async def debug_container_ages():
    """Debug the container age calculation for existing containers."""
    print("🔍 Debugging container age calculations...\n")

    docker_client = DockerClient()

    # Get current runners
    runners = await docker_client.get_runners()

    if not runners:
        print("No runner containers found.")
        return

    print(f"Found {len(runners)} runner containers:\n")

    for i, runner in enumerate(runners, 1):
        print(f"📦 Container {i}: {runner['name']}")
        print(f"   ID: {runner['id'][:12]}")
        print(f"   Status: {runner['status']}")
        print(f"   Runner Name: {runner['runner_name']}")
        print(f"   Created At (label): {runner['created_at']}")

        # Calculate age using the orchestrator's logic
        container_age = calculate_container_age_minutes(runner)
        print(f"   Calculated Age: {container_age:.2f} minutes")

        # Get actual Docker container details
        try:
            container = docker_client.client.containers.get(runner["id"])
            docker_created = container.attrs["Created"]
            print(f"   Docker Created: {docker_created}")

            # Parse Docker's created timestamp
            docker_created_dt = datetime.fromisoformat(
                docker_created.replace("Z", "+00:00")
            )
            docker_age_minutes = (
                datetime.now(timezone.utc) - docker_created_dt
            ).total_seconds() / 60.0
            print(f"   Docker Age: {docker_age_minutes:.2f} minutes")

        except Exception as e:
            print(f"   Error getting Docker details: {e}")

        print(f"   Would be removed: {'YES' if container_age > 2 else 'NO'}")
        print()


def calculate_container_age_minutes(runner_info: dict) -> float:
    """Calculate how long a container has been running in minutes (copy of orchestrator logic)."""
    try:
        if "created_at" in runner_info and runner_info["created_at"]:
            # Try to parse the created_at timestamp
            created_at_str = runner_info["created_at"]
            if isinstance(created_at_str, str):
                # Handle different timestamp formats
                if created_at_str.endswith("Z"):
                    created_at_str = created_at_str.replace("Z", "+00:00")
                elif "+" not in created_at_str and not created_at_str.endswith(
                    "+00:00"
                ):
                    created_at_str += "+00:00"

                created_at = datetime.fromisoformat(created_at_str)
                age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
                return age_seconds / 60.0
    except Exception as e:
        print(f"   Age calculation error: {e}")

    # Fallback: assume container is old enough if we can't determine age
    return 5.0


async def test_new_container_timing():
    """Test the timing of a new container creation and age calculation."""
    print("🔧 Testing new container creation timing...\n")

    from src.config import settings
    from src.github_client import GitHubClient

    # Get a registration token
    client = GitHubClient(
        token=settings.github_token, org=settings.github_org, repo=settings.github_repo
    )

    reg_token = await client.get_registration_token()

    # Determine repo URL
    if settings.github_org:
        repo_url = f"https://github.com/{settings.github_org}"
    else:
        repo_url = f"https://github.com/{settings.github_repo}"

    docker_client = DockerClient()
    runner_name = "timing-test-runner"

    print(f"Creating container at: {datetime.now(timezone.utc).isoformat()}")

    # Create the container
    container_id = await docker_client.create_runner(
        runner_name=runner_name, repo_url=repo_url, runner_token=reg_token
    )

    print(f"Container created: {container_id[:12]}")

    # Check age immediately after creation
    runners = await docker_client.get_runners()
    test_runner = next((r for r in runners if r["id"] == container_id), None)

    if test_runner:
        age = calculate_container_age_minutes(test_runner)
        print(f"Age immediately after creation: {age:.2f} minutes")

        # Wait 30 seconds and check again
        print("Waiting 30 seconds...")
        await asyncio.sleep(30)

        runners = await docker_client.get_runners()
        test_runner = next((r for r in runners if r["id"] == container_id), None)

        if test_runner:
            age = calculate_container_age_minutes(test_runner)
            print(f"Age after 30 seconds: {age:.2f} minutes")

        # Clean up
        await docker_client.remove_runner(container_id, force=True)
        print(f"Cleaned up test container")


async def main():
    """Main debug function."""
    print("🚀 Container Age Calculation Debug\n")

    # Test 1: Check existing containers
    await debug_container_ages()

    # Test 2: Test timing with new container
    await test_new_container_timing()


if __name__ == "__main__":
    asyncio.run(main())
