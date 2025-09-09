"""Docker client for managing runner containers."""

import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import uuid

import docker
import structlog

from .config import settings

logger = structlog.get_logger()


class DockerClient:
    """Docker client for managing runner containers."""

    def __init__(self):
        """Initialize Docker client."""
        self.client = docker.from_env()
        self.container_prefix = "github-runner"

        # Ensure network exists
        self._ensure_network()

    def _ensure_network(self):
        """Ensure the runner network exists."""
        try:
            self.client.networks.get(settings.runner_network)
        except docker.errors.NotFound:
            logger.info("Creating runner network", network=settings.runner_network)
            self.client.networks.create(
                settings.runner_network,
                driver="bridge",
                labels={"managed-by": "runner-orchestrator"},
            )

    async def create_runner(
        self,
        runner_name: str,
        repo_url: str,
        runner_token: str,
        labels: Optional[List[str]] = None,
    ) -> str:
        """Create a new runner container.

        Args:
            runner_name: Name for the runner
            repo_url: GitHub repository URL
            runner_token: Registration token
            labels: Additional labels for the runner

        Returns:
            Container ID
        """
        container_name = f"{self.container_prefix}-{runner_name}-{uuid.uuid4().hex[:8]}"

        # Merge default and custom labels
        all_labels = settings.runner_labels.copy()
        if labels:
            all_labels.extend(labels)

        environment = {
            "REPO_URL": repo_url,
            "RUNNER_TOKEN": runner_token,
            "RUNNER_NAME": runner_name,
            "RUNNER_WORKDIR": "_work",
            "RUNNER_LABELS": ",".join(all_labels),
        }

        # Create volume for runner work directory
        work_volume_name = f"{container_name}-work"
        try:
            self.client.volumes.create(
                name=work_volume_name,
                labels={"runner": runner_name, "managed-by": "runner-orchestrator"},
            )
        except Exception as e:
            logger.warning(
                "Volume might already exist", volume=work_volume_name, error=str(e)
            )

        # Container configuration
        container_config = {
            "image": settings.runner_image,
            "name": container_name,
            "environment": environment,
            "volumes": {
                work_volume_name: {"bind": "/actions-runner/_work", "mode": "rw"},
                "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
            },
            "network": settings.runner_network,
            "restart_policy": {"Name": "unless-stopped"},
            "labels": {
                "managed-by": "runner-orchestrator",
                "runner-name": runner_name,
                "created-at": datetime.now(timezone.utc).isoformat(),
                "repo-url": repo_url,
            },
            "privileged": True,  # Required for Docker-in-Docker
            "detach": True,
        }

        try:
            logger.info(
                "Creating runner container", name=container_name, runner=runner_name
            )
            container = self.client.containers.run(**container_config)

            logger.info(
                "Runner container created successfully",
                container_id=container.id,
                name=container_name,
                runner=runner_name,
            )

            return container.id

        except Exception as e:
            logger.error(
                "Failed to create runner container",
                name=container_name,
                runner=runner_name,
                error=str(e),
            )
            # Clean up volume if container creation failed
            try:
                volume = self.client.volumes.get(work_volume_name)
                volume.remove()
            except:
                pass
            raise

    async def remove_runner(self, container_id: str, force: bool = False) -> bool:
        """Remove a runner container.

        Args:
            container_id: Container ID or name
            force: Force removal even if container is running

        Returns:
            True if removed successfully
        """
        try:
            container = self.client.containers.get(container_id)

            # Get associated volume name before removing container
            work_volume_name = None
            for mount in container.attrs.get("Mounts", []):
                if mount.get("Destination") == "/actions-runner/_work":
                    work_volume_name = mount.get("Name")
                    break

            logger.info("Removing runner container", container_id=container_id)

            # Stop and remove container
            if container.status == "running":
                container.stop(timeout=30)
            container.remove(force=force)

            # Remove associated work volume
            if work_volume_name:
                try:
                    volume = self.client.volumes.get(work_volume_name)
                    volume.remove()
                    logger.info("Removed runner work volume", volume=work_volume_name)
                except Exception as e:
                    logger.warning(
                        "Failed to remove work volume",
                        volume=work_volume_name,
                        error=str(e),
                    )

            logger.info(
                "Runner container removed successfully", container_id=container_id
            )
            return True

        except docker.errors.NotFound:
            logger.warning("Container not found for removal", container_id=container_id)
            return True
        except Exception as e:
            logger.error(
                "Failed to remove runner container",
                container_id=container_id,
                error=str(e),
            )
            return False

    async def get_runners(self) -> List[Dict[str, Any]]:
        """Get list of all managed runner containers."""
        try:
            containers = self.client.containers.list(
                all=True, filters={"label": "managed-by=runner-orchestrator"}
            )

            runners = []
            for container in containers:
                runner_info = {
                    "id": container.id,
                    "name": container.name,
                    "status": container.status,
                    "runner_name": container.labels.get("runner-name"),
                    "created_at": container.labels.get("created-at"),
                    "repo_url": container.labels.get("repo-url"),
                    "image": (
                        container.image.tags[0] if container.image.tags else "unknown"
                    ),
                }
                runners.append(runner_info)

            return runners

        except Exception as e:
            logger.error("Failed to get runner containers", error=str(e))
            return []

    async def get_runner_logs(self, container_id: str, tail: int = 100) -> str:
        """Get logs from a runner container."""
        try:
            container = self.client.containers.get(container_id)
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8")
        except Exception as e:
            logger.error(
                "Failed to get runner logs", container_id=container_id, error=str(e)
            )
            return f"Error getting logs: {str(e)}"

    async def cleanup_dead_containers(self) -> int:
        """Clean up dead or exited runner containers."""
        try:
            containers = self.client.containers.list(
                all=True,
                filters={"label": "managed-by=runner-orchestrator", "status": "exited"},
            )

            cleaned = 0
            for container in containers:
                try:
                    await self.remove_runner(container.id)
                    cleaned += 1
                except Exception as e:
                    logger.error(
                        "Failed to cleanup container",
                        container_id=container.id,
                        error=str(e),
                    )

            if cleaned > 0:
                logger.info("Cleaned up dead containers", count=cleaned)

            return cleaned

        except Exception as e:
            logger.error("Failed to cleanup dead containers", error=str(e))
            return 0
