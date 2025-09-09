"""Main orchestrator that manages GitHub Actions runners."""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
import uuid

import structlog

from .config import settings
from .github_client import GitHubClient
from .docker_client import DockerClient

logger = structlog.get_logger()


class RunnerOrchestrator:
    """Orchestrates GitHub Actions runners based on workload."""

    def __init__(self):
        """Initialize the orchestrator."""
        self.github_client = GitHubClient(
            token=settings.github_token,
            org=settings.github_org,
            repo=settings.github_repo,
        )
        self.docker_client = DockerClient()
        self.is_running = False
        self.running_tasks: List[asyncio.Task] = []
        self.active_runners: Dict[str, Dict] = {}
        self.metrics = {
            "total_runners_created": 0,
            "total_runners_destroyed": 0,
            "current_queue_length": 0,
            "last_scale_action": None,
            "last_poll_time": None,
        }

    async def start(self) -> None:
        """Start the orchestrator."""
        logger.info("Starting Runner Orchestrator")
        self.is_running = True

        # Log configuration info
        if settings.github_org:
            logger.info(
                "Running in organization mode - queue-based scaling disabled",
                org=settings.github_org,
                scaling_mode="runner_count_based",
            )
        else:
            logger.info(
                "Running in repository mode - queue-based scaling enabled",
                repo=settings.github_repo,
                scaling_mode="queue_based",
            )

        # Start background tasks
        self.running_tasks = [
            asyncio.create_task(self._monitor_queue()),
            asyncio.create_task(self._manage_runners()),
            asyncio.create_task(self._cleanup_dead_containers()),
            asyncio.create_task(self._sync_runners()),
        ]

        # Initialize minimum runners
        await self._scale_to_minimum()

        logger.info("Orchestrator started successfully")

    async def stop(self) -> None:
        """Stop the orchestrator."""
        logger.info("Stopping Runner Orchestrator")
        self.is_running = False

        # Cancel all running tasks
        for task in self.running_tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.running_tasks, return_exceptions=True)

        logger.info("Orchestrator stopped")

    async def _monitor_queue(self) -> None:
        """Monitor GitHub Actions queue/runner states and trigger scaling decisions."""
        while self.is_running:
            try:
                if settings.github_org:
                    # Organization mode: Scale based on runner busy states
                    await self._monitor_runner_states()
                else:
                    # Repository mode: Scale based on queue length
                    await self._monitor_queue_length()

            except Exception as e:
                logger.error("Error monitoring queue", error=str(e))
                # Set safe default to prevent future comparison errors
                self.metrics["current_queue_length"] = 0
                self.metrics["last_poll_time"] = datetime.now(timezone.utc).isoformat()

            await asyncio.sleep(settings.poll_interval)

    async def _monitor_queue_length(self) -> None:
        """Monitor queue length for repository-level scaling."""
        try:
            queue_length = await self.github_client.get_queue_length()
            # Ensure queue_length is always an integer
            if queue_length is None:
                queue_length = 0

            self.metrics["current_queue_length"] = queue_length
            self.metrics["last_poll_time"] = datetime.now(timezone.utc).isoformat()

            logger.debug("Queue monitoring", queue_length=queue_length)

            # Scale up if queue is too long
            if queue_length >= settings.scale_up_threshold:
                await self._scale_up()
            # Scale down if queue is minimal
            elif queue_length <= settings.scale_down_threshold:
                await self._scale_down()
        except Exception as e:
            logger.error("Error in queue monitoring", error=str(e))
            # Set safe default values
            self.metrics["current_queue_length"] = 0
            self.metrics["last_poll_time"] = datetime.now(timezone.utc).isoformat()

    async def _monitor_runner_states(self) -> None:
        """Monitor runner busy states for organization-level scaling."""
        try:
            # Get names of our managed runners
            managed_runner_names = list(self.active_runners.keys())

            if not managed_runner_names:
                logger.debug("No managed runners to monitor")
                return

            # Get current states from GitHub
            runner_states = await self.github_client.get_managed_runner_states(
                managed_runner_names
            )

            online_runners = [
                r for r in runner_states.values() if r.get("status") == "online"
            ]
            busy_runners = [r for r in online_runners if r.get("busy", False)]
            idle_runners = [r for r in online_runners if not r.get("busy", False)]

            total_managed = len(managed_runner_names)
            total_online = len(online_runners)
            total_busy = len(busy_runners)
            total_idle = len(idle_runners)

            logger.debug(
                "Runner state monitoring",
                total_managed=total_managed,
                total_online=total_online,
                busy=total_busy,
                idle=total_idle,
            )

            # Update metrics
            self.metrics["current_queue_length"] = 0  # Not applicable for org mode
            self.metrics["last_poll_time"] = datetime.now(timezone.utc).isoformat()

            # Scaling logic: Ensure at least 1 idle runner, max 15 total
            max_runners = 15

            if total_idle == 0 and total_managed < max_runners:
                # No idle runners and we're under the cap - scale up
                logger.info(
                    "All runners busy, scaling up",
                    busy_runners=total_busy,
                    idle_runners=total_idle,
                    total_managed=total_managed,
                )
                await self._scale_up()
            elif total_idle > 2 and total_managed > settings.min_runners:
                # Too many idle runners - scale down (but keep at least min_runners)
                logger.info(
                    "Too many idle runners, scaling down",
                    busy_runners=total_busy,
                    idle_runners=total_idle,
                    total_managed=total_managed,
                )
                await self._scale_down()
            else:
                logger.debug(
                    "Runner levels optimal",
                    busy_runners=total_busy,
                    idle_runners=total_idle,
                    total_managed=total_managed,
                )

        except Exception as e:
            logger.error("Error monitoring runner states", error=str(e))

    async def _manage_runners(self) -> None:
        """Manage runner lifecycle and health."""
        while self.is_running:
            try:
                # Get current runners from Docker
                docker_runners = await self.docker_client.get_runners()

                # Update active runners tracking
                active_ids = set()
                for runner in docker_runners:
                    if runner["status"] == "running":
                        active_ids.add(runner["id"])
                        if runner["id"] not in self.active_runners:
                            self.active_runners[runner["id"]] = {
                                "name": runner["runner_name"],
                                "created_at": runner["created_at"],
                                "container_id": runner["id"],
                                "last_seen": datetime.now(timezone.utc),
                            }

                # Remove inactive runners from tracking
                inactive_ids = set(self.active_runners.keys()) - active_ids
                for inactive_id in inactive_ids:
                    logger.info(
                        "Removing inactive runner from tracking", runner_id=inactive_id
                    )
                    del self.active_runners[inactive_id]

                logger.debug(
                    "Runner health check",
                    active_count=len(self.active_runners),
                    docker_count=len(
                        [r for r in docker_runners if r["status"] == "running"]
                    ),
                )

            except Exception as e:
                logger.error("Error managing runners", error=str(e))

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _cleanup_dead_containers(self) -> None:
        """Periodically clean up dead containers and orphaned resources."""
        cleanup_counter = 0
        while self.is_running:
            try:
                # Clean up dead containers every cycle
                cleaned = await self.docker_client.cleanup_dead_containers()
                if cleaned > 0:
                    self.metrics["total_runners_destroyed"] += cleaned

                # Clean up orphaned resources every 5 cycles (25 minutes)
                cleanup_counter += 1
                if cleanup_counter >= 5:
                    cleanup_counter = 0
                    cleaned_resources = (
                        await self.docker_client.cleanup_orphaned_resources()
                    )
                    logger.info(
                        "Resource cleanup completed",
                        volumes_cleaned=cleaned_resources["volumes"],
                        images_cleaned=cleaned_resources["images"],
                    )

            except Exception as e:
                logger.error("Error cleaning up containers", error=str(e))

            await asyncio.sleep(300)  # Clean up every 5 minutes

    async def _sync_runners(self) -> None:
        """Sync runners between GitHub and local Docker containers.

        This method safely cleans up orphaned runners by only targeting runners
        with the 'orchestrated' label. This ensures that manually registered
        runners or runners from other systems are left untouched.
        """
        while self.is_running:
            try:
                # Get orchestrated runners from GitHub (only those with 'orchestrated' label)
                github_runners = await self.github_client.get_orchestrated_runners()
                github_names = {runner["name"] for runner in github_runners}

                # Get local container runners
                docker_runners = await self.docker_client.get_runners()
                docker_names = {
                    runner["runner_name"]
                    for runner in docker_runners
                    if runner["runner_name"]
                }

                # Find runners that exist in GitHub but not locally (might be from previous instances)
                # Only consider orchestrated runners for cleanup
                orphaned_github = github_names - docker_names
                if orphaned_github:
                    logger.info(
                        "Found orphaned orchestrated runners in GitHub",
                        count=len(orphaned_github),
                    )
                    for runner in github_runners:
                        if runner["name"] in orphaned_github:
                            try:
                                await self.github_client.delete_runner(runner["id"])
                                logger.info(
                                    "Removed orphaned orchestrated runner from GitHub",
                                    name=runner["name"],
                                )
                            except Exception as e:
                                logger.error(
                                    "Failed to remove orphaned orchestrated runner",
                                    name=runner["name"],
                                    error=str(e),
                                )

            except Exception as e:
                logger.error("Error syncing runners", error=str(e))

            await asyncio.sleep(600)  # Sync every 10 minutes

    async def _scale_up(self) -> None:
        """Scale up runners."""
        current_count = len(self.active_runners)

        # For organization mode, enforce max of 15 runners
        max_allowed = 15 if settings.github_org else settings.max_runners

        if current_count >= max_allowed:
            logger.warning(
                "Cannot scale up, at maximum runners",
                current=current_count,
                max=max_allowed,
                mode="organization" if settings.github_org else "repository",
            )
            return

        # For organization mode, add just 1 runner at a time
        # For repository mode, use the threshold-based approach
        if settings.github_org:
            runners_needed = 1
        else:
            runners_needed = min(
                settings.scale_up_threshold, max_allowed - current_count
            )

        logger.info(
            "Scaling up runners",
            current=current_count,
            adding=runners_needed,
            max_allowed=max_allowed,
            mode="organization" if settings.github_org else "repository",
        )

        for i in range(runners_needed):
            try:
                await self._create_runner()
            except Exception as e:
                logger.error("Failed to create runner during scale up", error=str(e))

        self.metrics["last_scale_action"] = {
            "action": "scale_up",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runners_added": runners_needed,
        }

    async def _scale_down(self) -> None:
        """Scale down runners."""
        current_count = len(self.active_runners)
        if current_count <= settings.min_runners:
            logger.debug(
                "Cannot scale down, at minimum runners",
                current=current_count,
                min=settings.min_runners,
            )
            return

        # Only scale down if we have more than minimum + threshold
        if current_count <= settings.min_runners + 1:
            return

        runners_to_remove = min(1, current_count - settings.min_runners)

        logger.info(
            "Scaling down runners", current=current_count, removing=runners_to_remove
        )

        # Remove oldest idle runners first
        runners_by_age = sorted(
            self.active_runners.items(), key=lambda x: x[1]["created_at"]
        )

        removed = 0
        for runner_id, runner_info in runners_by_age:
            if removed >= runners_to_remove:
                break

            try:
                await self.docker_client.remove_runner(runner_id)
                logger.info("Removed runner during scale down", runner_id=runner_id)
                removed += 1
                self.metrics["total_runners_destroyed"] += 1
            except Exception as e:
                logger.error(
                    "Failed to remove runner during scale down",
                    runner_id=runner_id,
                    error=str(e),
                )

        self.metrics["last_scale_action"] = {
            "action": "scale_down",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runners_removed": removed,
        }

    async def _scale_to_minimum(self) -> None:
        """Ensure minimum number of runners are running."""
        current_count = len(self.active_runners)
        needed = settings.min_runners - current_count

        if needed > 0:
            logger.info(
                "Scaling to minimum runners", current=current_count, needed=needed
            )
            for i in range(needed):
                try:
                    await self._create_runner()
                except Exception as e:
                    logger.error("Failed to create minimum runner", error=str(e))

    async def _create_runner(self) -> Optional[str]:
        """Create a new runner."""
        try:
            # Get registration token
            token = await self.github_client.get_registration_token()
            repo_url = await self.github_client.get_runner_url()

            # Generate unique runner name
            runner_name = f"orchestrated-{uuid.uuid4().hex[:8]}"

            # Create container
            container_id = await self.docker_client.create_runner(
                runner_name=runner_name,
                repo_url=repo_url,
                runner_token=token,
                labels=settings.runner_labels,
            )

            # Track the new runner
            self.active_runners[container_id] = {
                "name": runner_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "container_id": container_id,
                "last_seen": datetime.now(timezone.utc),
            }

            self.metrics["total_runners_created"] += 1

            logger.info(
                "Created new runner", runner_name=runner_name, container_id=container_id
            )
            return container_id

        except Exception as e:
            logger.error("Failed to create runner", error=str(e))
            return None

    async def get_status(self) -> Dict:
        """Get orchestrator status."""
        docker_runners = await self.docker_client.get_runners()

        return {
            "orchestrator": {
                "running": self.is_running,
                "uptime": "N/A",  # Could track start time
            },
            "runners": {
                "active": len(self.active_runners),
                "docker_containers": len(
                    [r for r in docker_runners if r["status"] == "running"]
                ),
                "total_created": self.metrics["total_runners_created"],
                "total_destroyed": self.metrics["total_runners_destroyed"],
            },
            "queue": {
                "current_length": self.metrics["current_queue_length"],
                "last_poll": self.metrics["last_poll_time"],
            },
            "scaling": {
                "min_runners": settings.min_runners,
                "max_runners": settings.max_runners,
                "scale_up_threshold": settings.scale_up_threshold,
                "scale_down_threshold": settings.scale_down_threshold,
                "last_action": self.metrics["last_scale_action"],
            },
            "settings": {
                "poll_interval": settings.poll_interval,
                "idle_timeout": settings.idle_timeout,
                "runner_image": settings.runner_image,
            },
        }
