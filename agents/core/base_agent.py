"""Base agent interface for LlamaFarm agents service.

This module defines the base interface that all agents must implement.
Agents are autonomous entities that use tools and models to complete tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Optional

from agents.datamodel import AgentType


class BaseAgent(ABC):
    """Base class for all LlamaFarm agents.

    Agents are autonomous entities that:
    - Use LLM models to process information
    - Can call server APIs (RAG, models) via HTTP
    - Can be chained together for complex workflows
    - Have their own configuration and prompts
    """

    # Each agent implementation must define its type
    AGENT_TYPE: str = "base"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: dict[str, Any],
        namespace: str,
        project: str,
        server_url: str = "http://localhost:8000",
    ):
        """Initialize the base agent.

        Args:
            agent_config: Agent-specific configuration from llamafarm.yaml
            project_config: Full project configuration
            namespace: Project namespace
            project: Project name
            server_url: LlamaFarm server URL for API calls
        """
        self.agent_config = agent_config
        self.project_config = project_config
        self.namespace = namespace
        self.project = project
        self.server_url = server_url

        # Agent metadata
        self.name: str = agent_config["name"]
        self.agent_type: AgentType = agent_config["type"]
        self.description: Optional[str] = agent_config.get("description")
        self.model_name: Optional[str] = agent_config.get("model")
        self.system_prompt: Optional[str] = agent_config.get("system_prompt")
        self.config: dict[str, Any] = agent_config.get("config", {})

    @abstractmethod
    async def run(self, input_data: Any, **kwargs) -> Any:
        """Execute agent logic.

        Args:
            input_data: Input for the agent (format depends on agent type)
            **kwargs: Additional parameters

        Returns:
            Agent output (format depends on agent type)
        """
        pass

    async def run_stream(self, input_data: Any, **kwargs) -> AsyncGenerator[Any, None]:
        """Execute agent logic with streaming output.

        Override this method if the agent supports streaming.

        Args:
            input_data: Input for the agent
            **kwargs: Additional parameters

        Yields:
            Chunks of output as they become available

        Raises:
            NotImplementedError: If streaming not supported
        """
        raise NotImplementedError(
            f"Streaming not supported for agent type '{self.agent_type}'"
        )
        yield  # Make it a generator

    def get_metadata(self) -> dict[str, Any]:
        """Get agent metadata for introspection.

        Returns:
            Dictionary with agent metadata
        """
        return {
            "name": self.name,
            "type": str(self.agent_type.value) if hasattr(self.agent_type, "value") else str(self.agent_type),
            "description": self.description,
            "model": self.model_name,
        }
