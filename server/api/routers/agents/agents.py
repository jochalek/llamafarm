"""Agent API endpoints.

This module provides REST API endpoints for managing and executing agents.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.logging import FastAPIStructLogger
from services.agent_service import AgentService
from services.project_service import ProjectService

logger = FastAPIStructLogger(__name__)

router = APIRouter(
    prefix="/projects/{namespace}/{project}/agents",
    tags=["agents"],
)


# Request/Response Models
class AgentRunRequest(BaseModel):
    """Request body for running an agent."""

    input: Any = Field(..., description="Input data for the agent")
    parameters: Optional[dict[str, Any]] = Field(
        None, description="Additional parameters for agent execution"
    )
    stream: bool = Field(False, description="Enable streaming response")


class AgentRunResponse(BaseModel):
    """Response for agent execution."""

    agent_name: str
    status: str  # "completed", "failed"
    result: Optional[Any] = None
    error: Optional[str] = None


class AgentInfo(BaseModel):
    """Agent information."""

    name: str
    type: str
    description: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None


class ListAgentsResponse(BaseModel):
    """Response for listing agents."""

    total: int
    agents: list[AgentInfo]


# Endpoints
@router.get("/", response_model=ListAgentsResponse)
async def list_agents(namespace: str, project: str):
    """List all configured agents for a project.

    Args:
        namespace: Project namespace
        project: Project name

    Returns:
        List of agent configurations
    """
    logger.bind(namespace=namespace, project=project)

    try:
        # Load project config
        project_config = ProjectService.load_config(namespace, project)

        # List agents
        agents = AgentService.list_agents(project_config)

        return ListAgentsResponse(
            total=len(agents),
            agents=[
                AgentInfo(
                    name=agent["name"],
                    type=str(agent["type"]),
                    description=agent.get("description"),
                    model=agent.get("model"),
                    tools=agent.get("tools"),
                )
                for agent in agents
            ],
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except Exception as e:
        logger.error("Failed to list agents", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {e}")


@router.get("/{agent_name}", response_model=AgentInfo)
async def get_agent(namespace: str, project: str, agent_name: str):
    """Get information about a specific agent.

    Args:
        namespace: Project namespace
        project: Project name
        agent_name: Agent name

    Returns:
        Agent configuration details
    """
    logger.bind(namespace=namespace, project=project, agent_name=agent_name)

    try:
        # Load project config
        project_config = ProjectService.load_config(namespace, project)

        # Get agent config
        agent_config = AgentService.get_agent_config(project_config, agent_name)

        return AgentInfo(
            name=agent_config["name"],
            type=str(agent_config["type"]),
            description=agent_config.get("description"),
            model=agent_config.get("model"),
            tools=agent_config.get("tools"),
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get agent", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {e}")


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(
    namespace: str, project: str, agent_name: str, request: AgentRunRequest
):
    """Execute an agent with the provided input.

    Args:
        namespace: Project namespace
        project: Project name
        agent_name: Agent name
        request: Agent execution request

    Returns:
        Agent execution result
    """
    logger.bind(namespace=namespace, project=project, agent_name=agent_name)

    try:
        # Load project config and get directory
        project_config = ProjectService.load_config(namespace, project)
        project_dir = ProjectService.get_project_dir(namespace, project)

        # Check if streaming is requested
        if request.stream:
            # Return streaming response
            async def stream_agent():
                try:
                    async for chunk in AgentService.run_agent_stream(
                        project_config, agent_name, request.input, str(project_dir)
                    ):
                        yield chunk
                except Exception as e:
                    logger.error("Agent streaming failed", error=str(e))
                    yield f"ERROR: {str(e)}\n"

            return StreamingResponse(
                stream_agent(),
                media_type="text/event-stream",
            )

        # Run agent synchronously
        result = await AgentService.run_agent(
            project_config,
            agent_name,
            request.input,
            str(project_dir),
            **(request.parameters or {}),
        )

        return AgentRunResponse(
            agent_name=agent_name, status="completed", result=result
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        logger.error("Agent execution failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Agent execution failed", error=str(e))
        return AgentRunResponse(agent_name=agent_name, status="failed", error=str(e))


@router.post("/{agent_name}/run/async")
async def run_agent_async(
    namespace: str,
    project: str,
    agent_name: str,
    request: AgentRunRequest,
    background_tasks: BackgroundTasks,
):
    """Execute an agent asynchronously in the background.

    Args:
        namespace: Project namespace
        project: Project name
        agent_name: Agent name
        request: Agent execution request
        background_tasks: FastAPI background tasks

    Returns:
        Task ID for tracking execution
    """
    logger.bind(namespace=namespace, project=project, agent_name=agent_name)

    try:
        # Load project config and get directory
        project_config = ProjectService.load_config(namespace, project)
        project_dir = ProjectService.get_project_dir(namespace, project)

        # Create a task ID
        import uuid

        task_id = f"agent-{agent_name}-{uuid.uuid4().hex[:8]}"

        # Define background task
        async def execute_agent():
            try:
                result = await AgentService.run_agent(
                    project_config,
                    agent_name,
                    request.input,
                    str(project_dir),
                    **(request.parameters or {}),
                )
                logger.info(
                    "Agent execution completed",
                    task_id=task_id,
                    agent_name=agent_name,
                )
                # TODO: Store result somewhere (redis, db, file)
            except Exception as e:
                logger.error(
                    "Agent execution failed", task_id=task_id, error=str(e)
                )
                # TODO: Store error somewhere

        # Add to background tasks
        background_tasks.add_task(execute_agent)

        return {
            "task_id": task_id,
            "status": "queued",
            "agent_name": agent_name,
            "message": "Agent execution queued in background",
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to queue agent execution", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to queue agent execution: {e}"
        )
