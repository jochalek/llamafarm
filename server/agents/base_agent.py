"""Base agent interface for all LlamaFarm agents.

This module defines the base interface that all agents must implement.
Agents are autonomous entities that use tools and models to complete tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Optional

from config.datamodel import LlamaFarmConfig
from services.model_service import ModelConfig


class BaseAgent(ABC):
    """Base class for all LlamaFarm agents.

    Agents are autonomous entities that:
    - Use LLM models to process information
    - Can call tools to perform actions
    - Can be chained together for complex workflows
    - Have their own configuration and prompts
    """

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: LlamaFarmConfig,
        project_dir: str,
    ):
        """Initialize the base agent.

        Args:
            agent_config: Agent-specific configuration from llamafarm.yaml
            project_config: Full project configuration
            project_dir: Path to project directory
        """
        self.agent_config = agent_config
        self.project_config = project_config
        self.project_dir = project_dir

        # Agent metadata
        self.name: str = agent_config["name"]
        self.agent_type: str = agent_config["type"]
        self.description: Optional[str] = agent_config.get("description")

        # Model configuration
        from services.model_service import ModelService

        model_name = agent_config.get("model")  # Can be None (use default)
        self.model_config: ModelConfig = ModelService.get_model_config(
            project_config, model_name
        )

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
        raise NotImplementedError(f"Streaming not supported for agent type '{self.agent_type}'")

    def register_context_provider(self, name: str, provider: Any) -> None:
        """Register a context provider (for RAG, docs, etc).

        Override this method if the agent needs context providers.

        Args:
            name: Provider name
            provider: Provider instance
        """
        pass

    def get_metadata(self) -> dict[str, Any]:
        """Get agent metadata for introspection.

        Returns:
            Dictionary with agent metadata
        """
        return {
            "name": self.name,
            "type": self.agent_type,
            "description": self.description,
            "model": self.model_config.name,
            "model_provider": self.model_config.provider.value,
        }
