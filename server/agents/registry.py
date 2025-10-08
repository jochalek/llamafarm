"""Agent registry for managing agent types and instances.

This module provides a central registry for agent types, similar to the ToolRegistry.
Agents can be registered by type and instantiated from configuration.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from agents.base_agent import BaseAgent
from config.datamodel import LlamaFarmConfig
from core.logging import FastAPIStructLogger

logger = FastAPIStructLogger(__name__)


class AgentRegistry:
    """Registry for agent types and factory functions.

    This registry allows:
    - Registering agent types with their implementation classes
    - Registering factory functions for complex agent creation
    - Creating agent instances from configuration
    - Listing available agent types
    """

    # Class-level storage for agent types and factories
    _agent_types: dict[str, type[BaseAgent]] = {}
    _agent_factories: dict[str, Callable] = {}

    @classmethod
    def register_type(cls, agent_type: str, agent_class: type[BaseAgent]) -> None:
        """Register an agent type with its implementation class.

        Args:
            agent_type: Agent type identifier (e.g., "document_analyzer")
            agent_class: Agent implementation class (must inherit from BaseAgent)

        Raises:
            ValueError: If agent_type already registered or agent_class invalid
        """
        if agent_type in cls._agent_types:
            logger.warning(
                "Agent type already registered, overwriting",
                agent_type=agent_type,
                existing_class=cls._agent_types[agent_type].__name__,
                new_class=agent_class.__name__,
            )

        if not issubclass(agent_class, BaseAgent):
            raise ValueError(
                f"Agent class must inherit from BaseAgent, got {agent_class}"
            )

        cls._agent_types[agent_type] = agent_class
        logger.debug(
            "Registered agent type",
            agent_type=agent_type,
            agent_class=agent_class.__name__,
        )

    @classmethod
    def register_factory(
        cls, agent_type: str, factory: Callable[[dict, LlamaFarmConfig, str], BaseAgent]
    ) -> None:
        """Register a factory function for creating agents.

        Factory functions are useful when agent creation requires special logic
        beyond simple class instantiation.

        Args:
            agent_type: Agent type identifier
            factory: Factory function with signature:
                     (agent_config, project_config, project_dir) -> BaseAgent

        Raises:
            ValueError: If agent_type already has a factory
        """
        if agent_type in cls._agent_factories:
            logger.warning(
                "Agent factory already registered, overwriting",
                agent_type=agent_type,
            )

        cls._agent_factories[agent_type] = factory
        logger.debug("Registered agent factory", agent_type=agent_type)

    @classmethod
    def _ensure_agents_registered(cls):
        """Ensure agents are auto-discovered and registered.

        This triggers the lazy auto-discovery from agents.__init__.py
        """
        # Import and call the auto-discovery function directly
        import agents
        agents._auto_discover_and_register_agents()

    @classmethod
    def create_agent(
        cls,
        agent_config: dict[str, Any],
        project_config: LlamaFarmConfig,
        project_dir: str,
    ) -> BaseAgent:
        """Create an agent instance from configuration.

        Args:
            agent_config: Agent configuration from llamafarm.yaml
            project_config: Full project configuration
            project_dir: Path to project directory

        Returns:
            Instantiated agent

        Raises:
            ValueError: If agent type not registered or required fields missing
        """
        # Validate required fields
        if "name" not in agent_config:
            raise ValueError("Agent config missing required field 'name'")
        if "type" not in agent_config:
            raise ValueError(
                f"Agent '{agent_config['name']}' missing required field 'type'"
            )

        # Extract agent type (handle both string and enum)
        agent_type_raw = agent_config["type"]
        agent_type = agent_type_raw.value if hasattr(agent_type_raw, 'value') else str(agent_type_raw)
        agent_name = agent_config["name"]

        logger.debug(
            "Creating agent instance",
            agent_name=agent_name,
            agent_type=agent_type,
        )

        # Ensure agents are auto-discovered before checking
        cls._ensure_agents_registered()

        # Check if factory exists (takes precedence)
        if agent_type in cls._agent_factories:
            logger.debug(
                "Creating agent using factory",
                agent_name=agent_name,
                agent_type=agent_type,
            )
            factory = cls._agent_factories[agent_type]
            return factory(agent_config, project_config, project_dir)

        # Check if type is registered
        if agent_type not in cls._agent_types:
            available = ", ".join(cls.list_types())
            raise ValueError(
                f"Agent type '{agent_type}' not registered. "
                f"Available types: {available}"
            )

        # Create agent using registered class
        logger.debug(
            "Creating agent using registered class",
            agent_name=agent_name,
            agent_type=agent_type,
            agent_class=cls._agent_types[agent_type].__name__,
        )

        agent_class = cls._agent_types[agent_type]
        return agent_class(agent_config, project_config, project_dir)

    @classmethod
    def list_types(cls) -> list[str]:
        """List all registered agent types.

        Returns:
            List of agent type identifiers
        """
        # Combine types and factories
        all_types = set(cls._agent_types.keys()) | set(cls._agent_factories.keys())
        return sorted(all_types)

    @classmethod
    def get_type_info(cls, agent_type: str) -> dict[str, Any]:
        """Get information about a registered agent type.

        Args:
            agent_type: Agent type identifier

        Returns:
            Dictionary with type information

        Raises:
            ValueError: If agent type not registered
        """
        if agent_type not in cls._agent_types and agent_type not in cls._agent_factories:
            raise ValueError(f"Agent type '{agent_type}' not registered")

        info: dict[str, Any] = {"type": agent_type}

        if agent_type in cls._agent_types:
            agent_class = cls._agent_types[agent_type]
            info["class"] = agent_class.__name__
            info["module"] = agent_class.__module__
            info["has_factory"] = agent_type in cls._agent_factories

        if agent_type in cls._agent_factories:
            if "class" not in info:
                info["factory_only"] = True

        return info

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registered agents (mainly for testing).

        Warning: This will remove all agent registrations!
        """
        cls._agent_types.clear()
        cls._agent_factories.clear()
        logger.warning("Agent registry cleared")
