"""API routes for the orchestrator."""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, List, Any
import structlog

logger = structlog.get_logger()

router = APIRouter()


@router.get("/status")
async def get_status(request: Request) -> Dict[str, Any]:
    """Get orchestrator status."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    return await orchestrator.get_status()


@router.get("/runners")
async def get_runners(request: Request) -> Dict[str, List[Dict[str, Any]]]:
    """Get list of all runners."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    docker_runners = await orchestrator.docker_client.get_runners()
    github_runners = await orchestrator.github_client.get_runners()

    return {
        "docker_runners": docker_runners,
        "github_runners": github_runners,
        "active_tracked": list(orchestrator.active_runners.values()),
    }


@router.post("/runners/scale-up")
async def scale_up_runners(request: Request) -> Dict[str, str]:
    """Manually trigger scale up."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    try:
        await orchestrator._scale_up()
        return {"message": "Scale up triggered successfully"}
    except Exception as e:
        logger.error("Manual scale up failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Scale up failed: {str(e)}")


@router.post("/runners/scale-down")
async def scale_down_runners(request: Request) -> Dict[str, str]:
    """Manually trigger scale down."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    try:
        await orchestrator._scale_down()
        return {"message": "Scale down triggered successfully"}
    except Exception as e:
        logger.error("Manual scale down failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Scale down failed: {str(e)}")


@router.delete("/runners/{runner_id}")
async def remove_runner(runner_id: str, request: Request) -> Dict[str, str]:
    """Remove a specific runner."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    try:
        success = await orchestrator.docker_client.remove_runner(runner_id)
        if success:
            return {"message": f"Runner {runner_id} removed successfully"}
        else:
            raise HTTPException(
                status_code=404, detail="Runner not found or could not be removed"
            )
    except Exception as e:
        logger.error("Failed to remove runner", runner_id=runner_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to remove runner: {str(e)}"
        )


@router.get("/runners/{runner_id}/logs")
async def get_runner_logs(
    runner_id: str, request: Request, tail: int = 100
) -> Dict[str, str]:
    """Get logs from a specific runner."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    try:
        logs = await orchestrator.docker_client.get_runner_logs(runner_id, tail)
        return {"logs": logs}
    except Exception as e:
        logger.error("Failed to get runner logs", runner_id=runner_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")


@router.post("/maintenance/cleanup")
async def cleanup_resources(request: Request) -> Dict[str, Any]:
    """Manually trigger cleanup of dead containers and orphaned resources."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    try:
        # Clean up dead containers
        dead_containers = await orchestrator.docker_client.cleanup_dead_containers()

        # Clean up orphaned resources
        orphaned_resources = (
            await orchestrator.docker_client.cleanup_orphaned_resources()
        )

        return {
            "message": "Cleanup completed successfully",
            "dead_containers_removed": dead_containers,
            "orphaned_volumes_removed": orphaned_resources["volumes"],
            "unused_images_removed": orphaned_resources["images"],
        }
    except Exception as e:
        logger.error("Manual cleanup failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/maintenance/status")
async def get_maintenance_status(request: Request) -> Dict[str, Any]:
    """Get maintenance and resource usage information."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    try:
        # Get Docker resource information for our orchestrator
        from ..config import settings

        # Count containers by type
        all_containers = orchestrator.docker_client.client.containers.list(all=True)
        our_containers = {"orchestrator": 0, "runner": 0, "other": 0}

        for container in all_containers:
            labels = container.labels or {}
            if labels.get("orchestrator-id") == settings.orchestrator_id:
                container_type = labels.get("type", "unknown")
                if "orchestrator" in container_type:
                    our_containers["orchestrator"] += 1
                elif "runner" in container_type:
                    our_containers["runner"] += 1
                else:
                    our_containers["other"] += 1

        # Count volumes
        all_volumes = orchestrator.docker_client.client.volumes.list()
        our_volumes = 0
        for volume in all_volumes:
            labels = volume.attrs.get("Labels") or {}
            if labels.get("orchestrator-id") == settings.orchestrator_id:
                our_volumes += 1

        # Count networks
        all_networks = orchestrator.docker_client.client.networks.list()
        our_networks = 0
        for network in all_networks:
            labels = network.attrs.get("Labels") or {}
            if labels.get("orchestrator-id") == settings.orchestrator_id:
                our_networks += 1

        # Count images
        all_images = orchestrator.docker_client.client.images.list()
        our_images = 0
        for image in all_images:
            labels = image.labels or {}
            if labels.get("orchestrator-id") == settings.orchestrator_id:
                our_images += 1

        return {
            "orchestrator_id": settings.orchestrator_id,
            "orchestrator_version": settings.orchestrator_version,
            "resources": {
                "containers": our_containers,
                "volumes": our_volumes,
                "networks": our_networks,
                "images": our_images,
            },
        }
    except Exception as e:
        logger.error("Failed to get maintenance status", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get maintenance status: {str(e)}"
        )


@router.get("/metrics")
async def get_metrics(request: Request) -> Dict[str, Any]:
    """Get Prometheus-style metrics."""
    orchestrator = request.app.state.orchestrator
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    status = await orchestrator.get_status()

    # Convert to Prometheus format
    metrics = {
        "github_actions_runners_active": status["runners"]["active"],
        "github_actions_runners_total_created": status["runners"]["total_created"],
        "github_actions_runners_total_destroyed": status["runners"]["total_destroyed"],
        "github_actions_queue_length": status["queue"]["current_length"],
        "github_actions_orchestrator_running": (
            1 if status["orchestrator"]["running"] else 0
        ),
    }

    return metrics
