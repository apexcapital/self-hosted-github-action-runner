#!/usr/bin/env python3
"""Test script to verify GitHub token validation and debug runner container issues."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import settings
from src.github_client import GitHubClient
from src.docker_client import DockerClient


async def test_github_token():
    """Test GitHub token validation."""
    print("🔍 Testing GitHub token validation...")
    print(
        f"GitHub Token: {'*' * len(settings.github_token[:-4]) + settings.github_token[-4:]}"
    )
    print(f"GitHub Org: {settings.github_org}")
    print(f"GitHub Repo: {settings.github_repo}")

    client = GitHubClient(
        token=settings.github_token, org=settings.github_org, repo=settings.github_repo
    )

    try:
        is_valid = await client.validate_token()
        print(f"✅ Token validation successful: {is_valid}")

        # Test getting a registration token
        print("\n🔍 Testing registration token generation...")
        reg_token = await client.get_registration_token()
        print(f"✅ Registration token obtained: {reg_token[:8]}...")

        return True
    except Exception as e:
        print(f"❌ Token validation failed: {e}")
        return False


async def inspect_runner_containers():
    """Inspect current runner containers."""
    print("\n🔍 Inspecting current runner containers...")

    docker_client = DockerClient()
    containers = docker_client.client.containers.list(
        filters={"label": "managed-by=runner-orchestrator"}
    )

    print(f"Found {len(containers)} runner containers:")

    for container in containers:
        print(f"\n📦 Container: {container.name}")
        print(f"   ID: {container.id[:12]}")
        print(
            f"   Image: {container.image.tags[0] if container.image.tags else 'unknown'}"
        )
        print(f"   Status: {container.status}")
        print(f"   Command: {container.attrs.get('Config', {}).get('Cmd', 'unknown')}")
        print(
            f"   Entrypoint: {container.attrs.get('Config', {}).get('Entrypoint', 'unknown')}"
        )

        # Check environment variables
        env_vars = container.attrs.get("Config", {}).get("Env", [])
        relevant_env = [
            env
            for env in env_vars
            if any(key in env for key in ["REPO_URL", "RUNNER_TOKEN", "RUNNER_NAME"])
        ]
        if relevant_env:
            print("   Key Environment Variables:")
            for env in relevant_env:
                if "TOKEN" in env:
                    # Mask the token
                    key, value = env.split("=", 1)
                    print(f"     {key}={value[:8]}...")
                else:
                    print(f"     {env}")


async def test_runner_creation():
    """Test creating a single runner to debug the issue."""
    print("\n🔍 Testing runner creation...")

    # First validate token
    client = GitHubClient(
        token=settings.github_token, org=settings.github_org, repo=settings.github_repo
    )

    try:
        # Get registration token
        reg_token = await client.get_registration_token()
        print(f"✅ Got registration token: {reg_token[:8]}...")

        # Determine repo URL
        if settings.github_org:
            repo_url = f"https://github.com/{settings.github_org}"
        else:
            repo_url = f"https://github.com/{settings.github_repo}"

        # Create test runner
        docker_client = DockerClient()
        runner_name = "test-debug-runner"

        print(f"🔧 Creating test runner: {runner_name}")
        print(f"   Image: {settings.runner_image}")
        print(f"   Repo URL: {repo_url}")

        container_id = await docker_client.create_runner(
            runner_name=runner_name, repo_url=repo_url, runner_token=reg_token
        )

        print(f"✅ Test runner created: {container_id[:12]}")

        # Wait a moment then check its status
        await asyncio.sleep(5)

        container = docker_client.client.containers.get(container_id)
        print(f"   Status after 5s: {container.status}")

        # Get logs
        logs = container.logs(tail=20).decode("utf-8", errors="ignore")
        print(f"   Recent logs:\n{logs}")

        # Clean up
        print(f"🧹 Cleaning up test runner...")
        await docker_client.remove_runner(container_id, force=True)

    except Exception as e:
        print(f"❌ Runner creation test failed: {e}")


async def main():
    """Main test function."""
    print("🚀 GitHub Runner Orchestrator - Token & Container Debug\n")
    print(f"Runner Image: {settings.runner_image}")
    print(f"Labels: {settings.runner_labels}")

    # Test 1: GitHub token validation
    token_valid = await test_github_token()

    if not token_valid:
        print("❌ Cannot proceed with container tests - token validation failed")
        return

    # Test 2: Inspect existing containers
    await inspect_runner_containers()

    # Test 3: Test creating a new runner
    await test_runner_creation()


if __name__ == "__main__":
    asyncio.run(main())
