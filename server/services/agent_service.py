"""Agent service for managing and executing agents.

This service provides high-level operations for working with agents:
- Loading agent configurations from project config
- Creating agent instances
- Running agents and getting results
"""

from __future__ import annotations

from typing import Any, Optional

from agents.base_agent import BaseAgent
from agents.registry import AgentRegistry
from config.datamodel import LlamaFarmConfig
from core.logging import FastAPIStructLogger

logger = FastAPIStructLogger(__name__)


class AgentService:
    """Service for managing and executing agents."""

    @staticmethod
    def get_agent_config(
        project_config: LlamaFarmConfig, agent_name: str
    ) -> dict[str, Any]:
        """Get agent configuration from project config.

        Args:
            project_config: Project configuration
            agent_name: Name of the agent to retrieve

        Returns:
            Agent configuration dictionary

        Raises:
            ValueError: If agent not found in config
        """
        if not project_config.agents:
            raise ValueError("No agents configured in project")

        # Find agent by name
        for agent_config in project_config.agents:
            if agent_config.name == agent_name:
                # Convert Pydantic model to dict for compatibility
                return agent_config.model_dump()

        # Agent not found
        available = ", ".join([a.name for a in project_config.agents])
        raise ValueError(
            f"Agent '{agent_name}' not found. Available agents: {available}"
        )

    @staticmethod
    def list_agents(project_config: LlamaFarmConfig) -> list[dict[str, Any]]:
        """List all configured agents in project.

        Args:
            project_config: Project configuration

        Returns:
            List of agent metadata dictionaries
        """
        if not project_config.agents:
            return []

        agents = []
        for agent_config in project_config.agents:
            agents.append(
                {
                    "name": agent_config.name,
                    "type": agent_config.type,
                    "description": agent_config.description,
                    "model": agent_config.model,
                }
            )

        return agents

    @staticmethod
    def create_agent(
        project_config: LlamaFarmConfig, agent_name: str, project_dir: str
    ) -> BaseAgent:
        """Create an agent instance from project configuration.

        Args:
            project_config: Project configuration
            agent_name: Name of the agent to create
            project_dir: Path to project directory

        Returns:
            Instantiated agent

        Raises:
            ValueError: If agent not found or cannot be created
        """
        # Get agent config
        agent_config = AgentService.get_agent_config(project_config, agent_name)

        # Create agent using registry
        logger.debug(
            "Creating agent instance",
            agent_name=agent_name,
            agent_type=agent_config["type"],
        )

        agent = AgentRegistry.create_agent(agent_config, project_config, project_dir)

        logger.debug(
            "Agent instance created",
            agent_name=agent_name,
            agent_type=agent_config["type"],
        )

        return agent

    @staticmethod
    async def run_agent(
        project_config: LlamaFarmConfig,
        agent_name: str,
        input_data: Any,
        project_dir: str,
        **kwargs,
    ) -> Any:
        """Run an agent and return its results.

        This is a convenience method that creates and runs an agent in one call.

        Args:
            project_config: Project configuration
            agent_name: Name of the agent to run
            input_data: Input data for the agent
            project_dir: Path to project directory
            **kwargs: Additional parameters for agent.run()

        Returns:
            Agent output

        Raises:
            ValueError: If agent not found or execution fails
        """
        # Create agent
        agent = AgentService.create_agent(project_config, agent_name, project_dir)

        # Run agent
        logger.info(
            "Running agent",
            agent_name=agent_name,
            agent_type=agent.agent_type,
        )

        try:
            result = await agent.run(input_data, **kwargs)

            logger.info(
                "Agent completed successfully",
                agent_name=agent_name,
                agent_type=agent.agent_type,
            )

            return result

        except Exception as e:
            logger.error(
                "Agent execution failed",
                agent_name=agent_name,
                agent_type=agent.agent_type,
                error=str(e),
            )
            raise

    @staticmethod
    async def run_agent_stream(
        project_config: LlamaFarmConfig,
        agent_name: str,
        input_data: Any,
        project_dir: str,
        **kwargs,
    ):
        """Run an agent with streaming output.

        Args:
            project_config: Project configuration
            agent_name: Name of the agent to run
            input_data: Input data for the agent
            project_dir: Path to project directory
            **kwargs: Additional parameters for agent.run_stream()

        Yields:
            Agent output chunks

        Raises:
            ValueError: If agent not found or doesn't support streaming
        """
        # Create agent
        agent = AgentService.create_agent(project_config, agent_name, project_dir)

        # Check if agent supports streaming
        if not hasattr(agent, "run_stream"):
            raise ValueError(f"Agent '{agent_name}' does not support streaming")

        # Run agent with streaming
        logger.info(
            "Running agent with streaming",
            agent_name=agent_name,
            agent_type=agent.agent_type,
        )

        try:
            async for chunk in agent.run_stream(input_data, **kwargs):
                yield chunk

            logger.info(
                "Agent streaming completed",
                agent_name=agent_name,
                agent_type=agent.agent_type,
            )

        except Exception as e:
            logger.error(
                "Agent streaming failed",
                agent_name=agent_name,
                agent_type=agent.agent_type,
                error=str(e),
            )
            raise

    @staticmethod
    def validate_agent_config(
        project_config: LlamaFarmConfig, agent_name: str
    ) -> tuple[bool, Optional[str]]:
        """Validate an agent's configuration.

        Args:
            project_config: Project configuration
            agent_name: Name of the agent to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if agent exists
            agent_config = AgentService.get_agent_config(project_config, agent_name)

            # Check if type is registered
            agent_type = agent_config["type"]
            if agent_type not in AgentRegistry.list_types():
                return (
                    False,
                    f"Agent type '{agent_type}' not registered. "
                    f"Available: {', '.join(AgentRegistry.list_types())}",
                )

            # Check if model exists (if specified)
            model_name = agent_config.get("model")
            if model_name:
                from services.model_service import ModelService

                try:
                    ModelService.get_model_config(project_config, model_name)
                except ValueError as e:
                    return (False, f"Invalid model configuration: {e}")

            return (True, None)

        except ValueError as e:
            return (False, str(e))
