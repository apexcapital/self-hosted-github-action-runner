"""GitHub API client for managing runners."""

import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class GitHubClient:
    """GitHub API client for runner management."""

    def __init__(
        self, token: str, org: Optional[str] = None, repo: Optional[str] = None
    ):
        """Initialize GitHub client.

        Args:
            token: GitHub Personal Access Token
            org: GitHub organization (optional)
            repo: GitHub repository in format "owner/repo" (optional)
        """
        self.token = token
        self.org = org
        self.repo = repo
        self.base_url = "https://api.github.com"

        # Determine the API endpoint based on org vs repo
        if org:
            self.runners_url = f"{self.base_url}/orgs/{org}/actions/runners"
            self.registration_url = (
                f"{self.base_url}/orgs/{org}/actions/runners/registration-token"
            )
        elif repo:
            self.runners_url = f"{self.base_url}/repos/{repo}/actions/runners"
            self.registration_url = (
                f"{self.base_url}/repos/{repo}/actions/runners/registration-token"
            )
        else:
            raise ValueError("Either org or repo must be specified")

        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Actions-Runner-Orchestrator/2.0.0",
        }

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_registration_token(self) -> str:
        """Get a registration token for new runners."""
        async with httpx.AsyncClient() as client:
            response = await client.post(self.registration_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data["token"]

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_runners(self) -> List[Dict[str, Any]]:
        """Get list of all runners."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.runners_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get("runners", [])

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_workflow_runs(self, status: str = "queued") -> List[Dict[str, Any]]:
        """Get workflow runs by status."""
        if self.org:
            # For organization-level runners, we can't get workflow runs directly
            # The GitHub API doesn't support /orgs/{org}/actions/runs
            # Instead, we'll return an empty list and rely on runner count-based scaling
            logger.warning(
                "Organization-level workflow run monitoring not supported by GitHub API",
                org=self.org,
                status=status,
            )
            return []
        else:
            url = f"{self.base_url}/repos/{self.repo}/actions/runs"

        params = {"status": status, "per_page": 100}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("workflow_runs", [])

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def delete_runner(self, runner_id: int) -> bool:
        """Delete a runner."""
        url = f"{self.runners_url}/{runner_id}"
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=self.headers)
            if response.status_code == 204:
                return True
            elif response.status_code == 404:
                logger.warning("Runner not found for deletion", runner_id=runner_id)
                return True
            else:
                response.raise_for_status()
                return False

    async def get_queue_length(self) -> int:
        """Get the current queue length of pending workflow runs."""
        try:
            if self.org:
                # For organization-level runners, queue-based scaling is not supported
                # We'll return 0 to disable queue-based scaling
                logger.debug(
                    "Queue-based scaling disabled for organization-level runners",
                    org=self.org,
                )
                return 0

            queued_runs = await self.get_workflow_runs("queued")
            in_progress_runs = await self.get_workflow_runs("in_progress")

            # Count runs that need self-hosted runners
            queue_length = 0
            for run in queued_runs + in_progress_runs:
                # This is a simplified check - in reality you might want to check
                # if the workflow specifically requires self-hosted runners
                if run.get("status") == "queued":
                    queue_length += 1

            return queue_length
        except Exception as e:
            logger.error("Failed to get queue length", error=str(e))
            return 0

    async def get_runner_url(self) -> str:
        """Get the repository/organization URL for runner registration."""
        if self.org:
            return f"https://github.com/{self.org}"
        else:
            return f"https://github.com/{self.repo}"

    async def get_managed_runner_states(
        self, managed_runner_names: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Get the busy/idle state of our managed runners.

        Args:
            managed_runner_names: List of runner names we're managing

        Returns:
            Dict mapping runner name to its state info
        """
        try:
            all_runners = await self.get_runners()
            managed_states = {}

            for runner in all_runners:
                runner_name = runner.get("name", "")
                if runner_name in managed_runner_names:
                    managed_states[runner_name] = {
                        "id": runner.get("id"),
                        "name": runner_name,
                        "status": runner.get("status", "unknown"),
                        "busy": runner.get("busy", False),
                        "os": runner.get("os", "unknown"),
                        "labels": [
                            label.get("name", "") for label in runner.get("labels", [])
                        ],
                    }

            return managed_states
        except Exception as e:
            logger.error("Failed to get managed runner states", error=str(e))
            return {}
