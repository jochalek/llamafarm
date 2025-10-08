"""Agent execution API endpoints."""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agents.api_models import (
    AgentRunRequest,
    AgentRunResponse,
    AgentTypeInfo,
    ListAgentTypesResponse,
    Status,
)
from agents.core.registry import AgentRegistry
from agents.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest):
    """Execute an agent with provided configuration and input.

    This endpoint receives:
    - Agent configuration from llamafarm.yaml
    - Project configuration
    - Input data

    And returns the agent execution result.

    Args:
        request: Agent run request with config and input

    Returns:
        Agent execution result or error
    """
    agent_name = request.agent_config.get("name", "unknown")

    logger.info(
        f"Agent run request: {agent_name} "
        f"(namespace={request.namespace}, project={request.project})"
    )

    try:
        # Create agent instance
        agent = AgentRegistry.create_agent(
            agent_config=request.agent_config,
            project_config=request.project_config,
            namespace=request.namespace,
            project=request.project,
            server_url=settings.llamafarm_server_url,
        )

        # Execute agent
        if request.stream:
            # Return streaming response
            async def stream_result():
                try:
                    async for chunk in agent.run_stream(request.input_data):
                        yield f"data: {chunk}\n\n"
                except Exception as e:
                    logger.error(f"Agent streaming failed: {e}", exc_info=True)
                    yield f"data: ERROR: {str(e)}\n\n"

            return StreamingResponse(
                stream_result(),
                media_type="text/event-stream",
            )
        else:
            # Run synchronously
            result = await agent.run(request.input_data)

            logger.info(f"Agent execution completed: {agent_name}")

            return AgentRunResponse(
                agent_name=agent_name,
                status=Status.completed,
                result=result,
            )

    except ValueError as e:
        # Configuration or validation errors
        logger.error(f"Agent execution failed (validation): {e}")
        return AgentRunResponse(
            agent_name=agent_name,
            status=Status.failed,
            error=str(e),
        )

    except Exception as e:
        # Runtime errors
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        return AgentRunResponse(
            agent_name=agent_name,
            status=Status.failed,
            error=str(e),
        )


@router.get("/types", response_model=ListAgentTypesResponse)
async def list_agent_types():
    """List available agent types.

    Returns:
        List of registered agent types with metadata
    """
    types = AgentRegistry.list_types()

    logger.debug(f"Listing agent types: {len(types)} types")

    type_infos = []
    for agent_type in types:
        try:
            info = AgentRegistry.get_type_info(agent_type)
            type_infos.append(
                AgentTypeInfo(
                    type=info["type"],
                    class_=info.get("class"),
                    module=info.get("module"),
                    has_factory=info.get("has_factory", False),
                )
            )
        except Exception as e:
            logger.warning(f"Failed to get info for agent type '{agent_type}': {e}")
            # Add minimal info
            type_infos.append(AgentTypeInfo(type=agent_type))

    return ListAgentTypesResponse(
        total=len(type_infos),
        types=type_infos,
    )


@router.get("/types/{agent_type}", response_model=AgentTypeInfo)
async def get_agent_type_info(agent_type: str):
    """Get information about a specific agent type.

    Args:
        agent_type: Agent type identifier

    Returns:
        Agent type information

    Raises:
        HTTPException: If agent type not found
    """
    try:
        info = AgentRegistry.get_type_info(agent_type)

        return AgentTypeInfo(
            type=info["type"],
            class_=info.get("class"),
            module=info.get("module"),
            has_factory=info.get("has_factory", False),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
