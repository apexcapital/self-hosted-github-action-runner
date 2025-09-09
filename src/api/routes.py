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
