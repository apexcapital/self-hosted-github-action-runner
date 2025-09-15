"""GitHub API client for managing runners."""

from typing import List, Dict, Optional, Any

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
            token: GitHub Personal Access Token (fine-grained supported)
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
            # Pin API version for consistent behavior across fine-grained PATs
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHub-Actions-Runner-Orchestrator/2.0.0",
        }

    async def validate_token(self) -> bool:
        """
        Validate the GitHub token and required permissions.

        Org flow (unchanged order, strict -> lenient):
          1) GET /user
          2) GET /orgs/{org}
          3) GET /orgs/{org}/actions/runners
          4) POST /orgs/{org}/actions/runners/registration-token

        Repo flow (re-ordered to avoid false 403s on runner listing):
          1) GET /user
          2) GET /repos/{owner}/{repo}
          3) POST /repos/{owner}/{repo}/actions/runners/registration-token  <-- strict
          4) (Optional) GET /repos/{owner}/{repo}/actions/runners           <-- informative only
        """

        def _raise_perm(method: str, url: str, e: httpx.HTTPStatusError) -> None:
            code = e.response.status_code
            try:
                detail = e.response.json().get("message", "")
            except Exception:
                detail = e.response.text or ""
            logger.error(
                "GitHub API error during validation",
                method=method,
                url=url,
                status_code=code,
                detail=detail,
            )
            if code == 401:
                raise Exception("Invalid or expired GitHub token")
            if code == 403:
                raise Exception(
                    "Insufficient GitHub token permissions for runner management"
                )
            if code == 404:
                raise Exception(
                    "Organization or repository not found or not visible to the token"
                )
            if code == 422:
                raise Exception(
                    "GitHub request could not be processed during validation"
                )
            raise Exception(f"GitHub API error during validation: {code}")

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # 1) Token validity
                url = f"{self.base_url}/user"
                try:
                    resp = await client.get(url, headers=self.headers)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    _raise_perm("GET", url, e)

                # Branch by target type
                if self.org:
                    # 2) Org visibility
                    url = f"{self.base_url}/orgs/{self.org}"
                    try:
                        resp = await client.get(url, headers=self.headers)
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        _raise_perm("GET", url, e)

                    # 3) Read access to runners list (org)
                    url = self.runners_url  # /orgs/{org}/actions/runners
                    try:
                        resp = await client.get(url, headers=self.headers)
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        _raise_perm("GET", url, e)

                    # 4) Write/admin permission: create registration token (org)
                    url = (
                        self.registration_url
                    )  # /orgs/{org}/actions/runners/registration-token
                    try:
                        resp = await client.post(url, headers=self.headers)
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        _raise_perm("POST", url, e)

                    data = resp.json()
                    if not isinstance(data, dict) or "token" not in data:
                        logger.error(
                            "Unexpected registration-token response payload (org)"
                        )
                        raise Exception(
                            "Unexpected GitHub response while validating token permissions"
                        )

                    logger.info("GitHub token validation successful (org)")
                    return True

                # Repo flow
                owner_repo = (self.repo or "").strip()
                if "/" not in owner_repo:
                    raise ValueError("repo must be in 'owner/repo' format")
                owner, repo = owner_repo.split("/", 1)

                # 2) Repo visibility
                url = f"{self.base_url}/repos/{owner}/{repo}"
                try:
                    resp = await client.get(url, headers=self.headers)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    _raise_perm("GET", url, e)

                # 3) STRICT: can we mint a registration token at repo scope?
                # (This is the most authoritative check for runner admin on the repo
                #  and avoids misleading 403s that sometimes occur when listing runners.)
                url = (
                    self.registration_url
                )  # /repos/{owner}/{repo}/actions/runners/registration-token
                try:
                    reg_resp = await client.post(url, headers=self.headers)
                    reg_resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    _raise_perm("POST", url, e)

                data = reg_resp.json()
                if not isinstance(data, dict) or "token" not in data:
                    logger.error(
                        "Unexpected registration-token response payload (repo)"
                    )
                    raise Exception(
                        "Unexpected GitHub response while validating token permissions"
                    )

                # 4) Optional: read runners list for diagnostics; ignore failures here
                # Some fine-grained PATs can create registration tokens but still 403 on list
                # if "Self-hosted runners: Read" wasn't granted. That shouldn't fail validation.
                url = self.runners_url  # /repos/{owner}/{repo}/actions/runners
                try:
                    runners_read = await client.get(url, headers=self.headers)
                    runners_read.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        "Repo runners list not readable with this token (continuing)",
                        method="GET",
                        url=url,
                        status_code=e.response.status_code,
                    )

                logger.info("GitHub token validation successful (repo)")
                return True

        except Exception as e:
            logger.error("GitHub token validation failed", error=str(e))
            raise Exception(f"Token validation failed: {e}")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_registration_token(self) -> str:
        """Get a registration token for new runners."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.post(self.registration_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data["token"]

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_all_runners(self) -> List[Dict[str, Any]]:
        """Get list of ALL runners including actions-runner-* ones we don't manage."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(self.runners_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get("runners", [])

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_runners(self) -> List[Dict[str, Any]]:
        """Get list of all runners, excluding actions-runner-* runners from management."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(self.runners_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            all_runners = data.get("runners", [])

            # Filter out existing actions-runner-* runners that we should not manage
            managed_runners = []
            for runner in all_runners:
                runner_name = runner.get("name", "")
                if runner_name.startswith("actions-runner-"):
                    logger.debug(
                        "Ignoring existing actions-runner from GitHub API",
                        name=runner_name,
                    )
                    continue
                managed_runners.append(runner)

            return managed_runners

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_workflow_runs(self, status: str = "queued") -> List[Dict[str, Any]]:
        """Get workflow runs by status."""
        if self.org:
            # For organization-level runners, we can't get workflow runs directly
            # The GitHub API doesn't support /orgs/{org}/actions/runs
            # Instead, we'll return an empty list and rely on runner count-based scaling
            logger.debug(
                "Organization-level workflow run monitoring not supported by GitHub API",
                org=self.org,
                status=status,
            )
            return []
        else:
            url = f"{self.base_url}/repos/{self.repo}/actions/runs"
            params = {"status": status, "per_page": 100}

            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
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
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
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
