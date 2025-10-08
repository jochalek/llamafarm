"""Health check endpoints."""
from fastapi import APIRouter

from agents.api_models import HealthCheckResponse, ReadinessCheckResponse
from agents.core.registry import AgentRegistry
from agents.core.settings import settings

router = APIRouter()


@router.get("/", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint.

    Returns:
        Service health status with metadata
    """
    agent_types = AgentRegistry.list_types()

    return HealthCheckResponse(
        status="healthy",
        service="llamafarm-agents",
        version="0.1.0",
        agent_types_loaded=len(agent_types),
        agent_types=agent_types,
        server_url=settings.llamafarm_server_url,
    )


@router.get("/ready", response_model=ReadinessCheckResponse)
async def readiness_check():
    """Readiness check endpoint.

    Returns:
        Service readiness status
    """
    # Check if agents are registered
    agent_types = AgentRegistry.list_types()

    if len(agent_types) == 0:
        return ReadinessCheckResponse(
            status="not_ready",
            agent_types=0,
            reason="No agents registered",
        )

    return ReadinessCheckResponse(
        status="ready",
        agent_types=len(agent_types),
    )
