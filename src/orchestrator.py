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
            "failed_scale_attempts": 0,  # Track consecutive failures
            "circuit_breaker_active": False,  # Emergency brake
        }

    async def start(self) -> None:
        """Start the orchestrator."""
        logger.info("Starting Runner Orchestrator")

        # Validate GitHub token before starting
        try:
            await self.github_client.validate_token()
        except Exception as e:
            logger.error("GitHub token validation failed", error=str(e))
            raise Exception(f"Invalid GitHub token or permissions: {e}")

        self.is_running = True

        # Start background tasks
        self.running_tasks = [
            asyncio.create_task(self._monitor_queue()),
            asyncio.create_task(self._manage_runners()),
            asyncio.create_task(self._cleanup_dead_containers()),
            asyncio.create_task(self._sync_runners()),
            asyncio.create_task(self._monitor_runner_utilization()),
            asyncio.create_task(self._maintain_minimum_runners()),
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
        """Monitor GitHub Actions queue and trigger scaling decisions."""
        while self.is_running:
            try:
                # EMERGENCY SAFETY CHECK: Count all containers before any scaling decision
                try:
                    docker_runners = await self.docker_client.get_runners()
                    total_containers = len(
                        [
                            r
                            for r in docker_runners
                            if r["status"] in ["running", "created", "restarting"]
                        ]
                    )

                    # CIRCUIT BREAKER: If we have too many containers, activate emergency brake
                    if total_containers >= settings.max_runners:
                        if not self.metrics["circuit_breaker_active"]:
                            logger.error(
                                "EMERGENCY: Container limit reached, activating circuit breaker",
                                total_containers=total_containers,
                                max_allowed=settings.max_runners,
                            )
                            self.metrics["circuit_breaker_active"] = True

                        # Skip all scaling operations
                        await asyncio.sleep(settings.poll_interval)
                        continue
                    elif self.metrics["circuit_breaker_active"]:
                        logger.info(
                            "Circuit breaker deactivated, container count within limits",
                            total_containers=total_containers,
                            max_allowed=settings.max_runners,
                        )
                        self.metrics["circuit_breaker_active"] = False

                except Exception as container_check_error:
                    logger.error(
                        "Failed container safety check",
                        error=str(container_check_error),
                    )
                    # If we can't count containers, don't scale
                    await asyncio.sleep(settings.poll_interval)
                    continue

                queue_length = await self.github_client.get_queue_length()
                self.metrics["current_queue_length"] = queue_length
                self.metrics["last_poll_time"] = datetime.now(timezone.utc).isoformat()

                logger.debug(
                    "Queue monitoring",
                    queue_length=queue_length,
                    total_containers=total_containers,
                    circuit_breaker=self.metrics["circuit_breaker_active"],
                )
                await self.debug_scaling_state()  # Debug call

                # Only scale if circuit breaker is not active
                if not self.metrics["circuit_breaker_active"]:
                    # Scale up if queue is too long
                    if queue_length >= settings.scale_up_threshold:
                        await self._scale_up()
                    # Scale down if queue is minimal
                    elif queue_length <= settings.scale_down_threshold:
                        await self._scale_down()

            except Exception as e:
                logger.error("Error monitoring queue", error=str(e))
                self.metrics["failed_scale_attempts"] += 1

                # If too many failures, activate circuit breaker
                if self.metrics["failed_scale_attempts"] >= 5:
                    logger.error(
                        "Too many monitoring failures, activating circuit breaker"
                    )
                    self.metrics["circuit_breaker_active"] = True

            await asyncio.sleep(settings.poll_interval)

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
        """Periodically clean up dead containers."""
        while self.is_running:
            try:
                cleaned = await self.docker_client.cleanup_dead_containers()
                if cleaned > 0:
                    self.metrics["total_runners_destroyed"] += cleaned
            except Exception as e:
                logger.error("Error cleaning up containers", error=str(e))

            await asyncio.sleep(300)  # Clean up every 5 minutes

    async def _sync_runners(self) -> None:
        """Sync with GitHub to remove orphaned runners and unregistered containers."""
        while self.is_running:
            try:
                # Get runners from GitHub (only managed ones, not actions-runner-*)
                github_runners = await self.github_client.get_runners()
                github_names = {runner["name"] for runner in github_runners}

                # Also get all runners for logging/monitoring purposes
                all_github_runners = await self.github_client.get_all_runners()
                # Determine which existing GitHub runners we should ignore when
                # syncing. Historically we ignored names like "actions-runner-*"
                # and "Mac-Build-*". Use the configured prefix so the
                # orchestrator only manages runners it created.
                configured_prefix = settings.runner_name_prefix
                ignored_runners = [
                    r["name"]
                    for r in all_github_runners
                    if not r["name"].startswith(configured_prefix)
                ]

                if ignored_runners:
                    logger.debug(
                        "Found existing non-orchestrated runners (ignoring)",
                        count=len(ignored_runners),
                        names=ignored_runners[:5],  # Log first 5 names to avoid spam
                    )

                # Get local container runners
                docker_runners = await self.docker_client.get_runners()
                docker_names = {
                    runner["runner_name"]
                    for runner in docker_runners
                    if runner["runner_name"]
                }

                # Find containers that exist locally but aren't registered with GitHub
                # These are likely failed registrations that should be removed
                unregistered_containers = docker_names - github_names
                if unregistered_containers:
                    logger.info(
                        "Found unregistered containers (removing)",
                        count=len(unregistered_containers),
                        names=list(unregistered_containers)[:5],
                    )
                    for runner in docker_runners:
                        if (
                            runner["runner_name"] in unregistered_containers
                            and runner["status"] == "running"
                        ):
                            try:
                                # Check if container has been running for more than 2 minutes
                                # Give it time to register before removing
                                container_age = self._get_container_age_minutes(runner)
                                if container_age > 2:
                                    await self.docker_client.remove_runner(runner["id"])
                                    logger.info(
                                        "Removed unregistered container",
                                        runner_name=runner["runner_name"],
                                        container_id=runner["id"],
                                        age_minutes=container_age,
                                    )
                                    self.metrics["total_runners_destroyed"] += 1
                            except Exception as e:
                                logger.error(
                                    "Failed to remove unregistered container",
                                    runner_name=runner["runner_name"],
                                    error=str(e),
                                )

                # Find runners that exist in GitHub but not locally (might be from previous instances)
                orphaned_github = github_names - docker_names
                if orphaned_github:
                    logger.info(
                        "Found orphaned runners in GitHub", count=len(orphaned_github)
                    )
                    prefix = settings.runner_name_prefix
                    for runner in github_runners:
                        if runner["name"] in orphaned_github:
                            # Only remove runners that match our naming prefix to avoid
                            # deleting unrelated runners (e.g., Mac build agents).
                            if not runner["name"].startswith(prefix):
                                logger.info(
                                    "Skipping orphaned runner - not managed by this orchestrator",
                                    name=runner["name"],
                                )
                                continue

                            try:
                                await self.github_client.delete_runner(runner["id"])
                                logger.info(
                                    "Removed orphaned runner from GitHub",
                                    name=runner["name"],
                                )
                            except Exception as e:
                                logger.error(
                                    "Failed to remove orphaned runner",
                                    name=runner["name"],
                                    error=str(e),
                                )

            except Exception as e:
                logger.error("Error syncing runners", error=str(e))

            await asyncio.sleep(120)  # Sync more frequently - every 2 minutes

    async def _scale_up(self) -> None:
        """Scale up runners based on both registered and docker container counts."""
        # CRITICAL: Count ALL containers first to prevent runaway scaling
        try:
            docker_runners = await self.docker_client.get_runners()
            total_containers = len(
                [
                    r
                    for r in docker_runners
                    if r["status"] in ["running", "created", "restarting"]
                ]
            )
        except Exception as e:
            logger.error(
                "Could not get Docker containers for scale up safety check",
                error=str(e),
            )
            return

        # HARD LIMIT: Never exceed max_runners containers regardless of registration status
        if total_containers >= settings.max_runners:
            logger.warning(
                "Cannot scale up, at maximum container limit",
                total_containers=total_containers,
                max=settings.max_runners,
            )
            return

        # Count registered runners for scaling logic
        try:
            github_runners = await self.github_client.get_runners()
            registered_count = len(github_runners)
        except Exception as e:
            logger.warning(
                "Could not get GitHub runners for scale up, using container count",
                error=str(e),
            )
            registered_count = total_containers

        if registered_count >= settings.max_runners:
            logger.warning(
                "Cannot scale up, at maximum registered runners",
                registered_count=registered_count,
                max=settings.max_runners,
            )
            return

        # Check if we recently scaled up to prevent runaway scaling
        if self.metrics["last_scale_action"]:
            last_action = self.metrics["last_scale_action"]
            if (
                isinstance(last_action, dict)
                and last_action.get("action") == "scale_up"
            ):
                timestamp = last_action.get("timestamp")
                if timestamp:
                    last_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                else:
                    last_time = datetime.min
                time_diff = datetime.now(timezone.utc) - last_time
                if time_diff.total_seconds() < 60:
                    logger.debug("Scale up cooldown active, skipping")
                    return

        # Be more aggressive in scaling - create up to 2 runners at once if needed
        docker_runners = await self.docker_client.get_runners()
        total_containers = len(
            [
                r for r in docker_runners if r["status"] in ["running", "created", "restarting"]
            ]
        )
        github_runners = await self.github_client.get_runners()
        registered_count = len(github_runners)
        max_new_containers = min(2, settings.max_runners - total_containers)
        max_new_registered = min(2, settings.max_runners - registered_count)
        runners_needed = min(max_new_containers, max_new_registered)

        if runners_needed <= 0:
            logger.debug(
                "No runners needed",
                total_containers=total_containers,
                registered_count=registered_count,
            )
            return

        logger.info(
            "Scaling up runners",
            registered_count=registered_count,
            total_containers=total_containers,
            adding=runners_needed,
        )

        successful_creates = 0
        for _ in range(runners_needed):
            try:
                container_id = await self._create_runner()
                if container_id:
                    successful_creates += 1
                    # Add a delay between creating runners
                    await asyncio.sleep(10)  # Increased delay
                else:
                    logger.warning("Failed to create runner (returned None)")
                    break  # Stop trying if creation fails
            except Exception as e:
                logger.error("Failed to create runner during scale up", error=str(e))
                break  # Stop trying if creation fails

        self.metrics["last_scale_action"] = {
            "action": "scale_up",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runners_added": successful_creates,
        }

    async def _scale_down(self) -> None:
        """Scale down runners based on registered runner count."""
        # Count registered runners, not just containers
        try:
            github_runners = await self.github_client.get_runners()
            current_count = len(github_runners)
            registered_names = {runner["name"] for runner in github_runners}
        except Exception as e:
            logger.warning(
                "Could not get GitHub runners for scale down, using active runners",
                error=str(e),
            )
            current_count = len(self.active_runners)
            registered_names = set()

        if current_count <= settings.min_runners:
            logger.debug(
                "Cannot scale down, at minimum runners",
                current_registered=current_count,
                min=settings.min_runners,
            )
            return

        # Only scale down if we have more than minimum + threshold
        if current_count <= settings.min_runners + 1:
            return

        runners_to_remove = min(1, current_count - settings.min_runners)

        logger.info(
            "Scaling down runners",
            current_registered=current_count,
            removing=runners_to_remove,
        )

        # Remove oldest idle runners first, but only if they're registered
        docker_runners = await self.docker_client.get_runners()
        registered_containers = [
            r
            for r in docker_runners
            if r["runner_name"] in registered_names and r["status"] == "running"
        ]

        # Sort by creation time (oldest first)
        runners_by_age = sorted(
            registered_containers, key=lambda x: x.get("created_at", "")
        )

        removed = 0
        for runner_info in runners_by_age:
            if removed >= runners_to_remove:
                break

            try:
                await self.docker_client.remove_runner(runner_info["id"])
                logger.info(
                    "Removed runner during scale down", runner_id=runner_info["id"]
                )
                removed += 1
                self.metrics["total_runners_destroyed"] += 1
            except Exception as e:
                logger.error(
                    "Failed to remove runner during scale down",
                    runner_id=runner_info["id"],
                    error=str(e),
                )

        self.metrics["last_scale_action"] = {
            "action": "scale_down",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "runners_removed": removed,
        }

    async def _scale_to_minimum(self) -> None:
        """Ensure minimum number of runners are running and registered with HARD SAFETY LIMITS."""
        # CRITICAL: Get all Docker containers first for safety checks
        try:
            docker_runners = await self.docker_client.get_runners()
            all_containers = [
                r
                for r in docker_runners
                if r["status"] in ["running", "created", "restarting"]
            ]
            running_containers = [r for r in docker_runners if r["status"] == "running"]
        except Exception as e:
            logger.error(
                "Could not get Docker containers for scaling safety", error=str(e)
            )
            return

        # HARD SAFETY LIMIT: Never exceed max_runners containers
        if len(all_containers) >= settings.max_runners:
            logger.warning(
                "Cannot scale to minimum, already at container limit",
                total_containers=len(all_containers),
                max=settings.max_runners,
            )
            return

        # Get registered runners from GitHub (only our managed ones)
        try:
            github_runners = await self.github_client.get_runners()
            registered_names = {runner["name"] for runner in github_runners}

            # CRITICAL FIX: Count only ONLINE runners, not offline ones
            online_runners = [
                r for r in github_runners
                if r.get("status") == "online"
            ]
            online_names = {runner["name"] for runner in online_runners}

            # Count only containers that are both running AND registered AND online
            online_registered_running_count = len(
                [r for r in running_containers if r["runner_name"] in online_names]
            )

            logger.debug(
                "Runner count analysis",
                docker_running=len(running_containers),
                docker_total=len(all_containers),
                github_registered=len(github_runners),
                github_online=len(online_runners),
                online_and_running=online_registered_running_count,
                min_required=settings.min_runners,
            )

            # Use ONLINE count for scaling decisions
            current_count = online_registered_running_count

        except Exception as e:
            logger.warning(
                "Could not get GitHub runners for scaling, using Docker count",
                error=str(e),
            )
            current_count = len(running_containers)

        needed = settings.min_runners - current_count

        if needed > 0:
            # SAFETY: Respect hard container limits
            max_containers_allowed = settings.max_runners - len(all_containers)
            safe_needed = min(
                needed, max_containers_allowed, 2
            )  # Never create more than 2 at once

            if safe_needed <= 0:
                logger.warning(
                    "Cannot scale to minimum due to container limits",
                    needed=needed,
                    total_containers=len(all_containers),
                    max_allowed=settings.max_runners,
                )
                return

            logger.info(
                "Scaling to minimum runners",
                current_online=current_count,
                needed=needed,
                safe_needed=safe_needed,
                docker_running=len(running_containers),
                docker_total=len(all_containers),
            )

            failed_attempts = 0
            successful_creates = 0

            for i in range(safe_needed):
                try:
                    runner_id = await self._create_runner()
                    if runner_id is None:
                        failed_attempts += 1
                        logger.warning("Failed to create runner (returned None)")
                        if failed_attempts >= 2:  # Strict failure threshold
                            logger.error(
                                "Too many failed attempts to create runners, stopping"
                            )
                            break
                    else:
                        successful_creates += 1
                        failed_attempts = 0  # Reset on success
                        # Add delay between creates to avoid overwhelming systems
                        await asyncio.sleep(10)  # Increased delay
                except Exception as e:
                    failed_attempts += 1
                    logger.error("Failed to create minimum runner", error=str(e))
                    if failed_attempts >= 2:  # More strict failure threshold
                        logger.error("Too many failures, stopping scale to minimum")
                        break

            logger.info(
                "Scale to minimum completed",
                successful_creates=successful_creates,
                failed_attempts=failed_attempts,
            )

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
                runner_name=runner_name, repo_url=repo_url, runner_token=token
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

    async def _monitor_runner_utilization(self) -> None:
        """Monitor runner utilization and scale based on usage."""
        while self.is_running:
            try:
                github_runners = await self.github_client.get_runners()
                total_runners = len(github_runners)
                busy_runners = len([r for r in github_runners if r.get("status") == "online" and r.get("busy", False)])
                idle_runners = total_runners - busy_runners
                utilization = (busy_runners / total_runners * 100) if total_runners > 0 else 0
                logger.debug(
                    "Runner utilization check",
                    total_runners=total_runners,
                    busy_runners=busy_runners,
                    idle_runners=idle_runners,
                    utilization_percent=utilization,
                )
                if utilization >= 80 and total_runners < settings.max_runners:
                    queue_length = await self.github_client.get_queue_length()
                    if queue_length > 0:
                        logger.info(
                            "High utilization detected, scaling up",
                            utilization=utilization,
                            queue_length=queue_length,
                        )
                        await self._scale_up()
                elif utilization <= 20 and idle_runners > 1 and total_runners > settings.min_runners:
                    logger.info(
                        "Low utilization detected, considering scale down",
                        utilization=utilization,
                        idle_runners=idle_runners,
                    )
                    await self._scale_down()
            except Exception as e:
                logger.error("Error monitoring runner utilization", error=str(e))
            await asyncio.sleep(60)

    async def _maintain_minimum_runners(self) -> None:
        """Periodically ensure minimum number of ONLINE runners are maintained."""
        while self.is_running:
            try:
                # Wait before first check to let initial runners come online
                await asyncio.sleep(60)

                # Only maintain minimum if circuit breaker is not active
                if not self.metrics.get("circuit_breaker_active", False):
                    await self._scale_to_minimum()
                else:
                    logger.debug("Skipping minimum maintenance due to circuit breaker")

            except Exception as e:
                logger.error("Error maintaining minimum runners", error=str(e))

            # Check every 60 seconds to ensure we always have minimum runners
            await asyncio.sleep(60)

    async def debug_scaling_state(self) -> None:
        """Debug method to log current scaling state."""
        try:
            github_runners = await self.github_client.get_runners()
            docker_runners = await self.docker_client.get_runners()
            queue_length = await self.github_client.get_queue_length()
            logger.info(
                "SCALING DEBUG",
                github_runners_count=len(github_runners),
                github_runners=[{
                    "name": r["name"],
                    "status": r.get("status"),
                    "busy": r.get("busy", False)
                } for r in github_runners],
                docker_runners_count=len([r for r in docker_runners if r["status"] == "running"]),
                queue_length=queue_length,
                min_runners=settings.min_runners,
                max_runners=settings.max_runners,
                circuit_breaker=self.metrics["circuit_breaker_active"],
            )
        except Exception as e:
            logger.error("Debug scaling state failed", error=str(e))

    def _get_container_age_minutes(self, runner_info: Dict) -> float:
        """Calculate how long a container has been running in minutes."""
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
                    age_seconds = (
                        datetime.now(timezone.utc) - created_at
                    ).total_seconds()
                    return age_seconds / 60.0
        except Exception as e:
            logger.warning("Could not calculate container age", error=str(e))

        # Fallback: assume container is old enough if we can't determine age
        return 5.0

    async def get_status(self) -> Dict:
        """Get orchestrator status."""
        docker_runners = await self.docker_client.get_runners()

        # Get info about ignored runners for monitoring
        try:
            all_github_runners = await self.github_client.get_all_runners()
            github_runners = await self.github_client.get_runners()  # Only managed ones
            # Report runners that are not managed by this orchestrator for monitoring
            configured_prefix = settings.runner_name_prefix
            ignored_runners = [
                r["name"]
                for r in all_github_runners
                if not r["name"].startswith(configured_prefix)
            ]

            # Calculate registered vs unregistered containers
            github_names = {runner["name"] for runner in github_runners}
            docker_names = {
                r["runner_name"] for r in docker_runners if r["status"] == "running"
            }
            registered_running = len(docker_names & github_names)
            unregistered_running = len(docker_names - github_names)

        except Exception:
            ignored_runners = []
            registered_running = 0
            unregistered_running = len(
                [r for r in docker_runners if r["status"] == "running"]
            )

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
                "registered_running": registered_running,
                "unregistered_running": unregistered_running,
                "total_created": self.metrics["total_runners_created"],
                "total_destroyed": self.metrics["total_runners_destroyed"],
                "ignored_existing": len(ignored_runners),
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
