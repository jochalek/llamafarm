"""Agent registry for managing agent types and instances.

This module provides a central registry for agent types.
Agents can be registered by type and instantiated from configuration.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Callable

from agents.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


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
    _registered: bool = False

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
                f"Agent type '{agent_type}' already registered, overwriting "
                f"(existing: {cls._agent_types[agent_type].__name__}, "
                f"new: {agent_class.__name__})"
            )

        if not issubclass(agent_class, BaseAgent):
            raise ValueError(
                f"Agent class must inherit from BaseAgent, got {agent_class}"
            )

        cls._agent_types[agent_type] = agent_class
        logger.debug(f"Registered agent type '{agent_type}' -> {agent_class.__name__}")

    @classmethod
    def register_factory(
        cls, agent_type: str, factory: Callable
    ) -> None:
        """Register a factory function for creating agents.

        Factory functions are useful when agent creation requires special logic
        beyond simple class instantiation.

        Args:
            agent_type: Agent type identifier
            factory: Factory function with signature:
                     (agent_config, project_config, namespace, project, server_url) -> BaseAgent
        """
        if agent_type in cls._agent_factories:
            logger.warning(f"Agent factory for '{agent_type}' already registered, overwriting")

        cls._agent_factories[agent_type] = factory
        logger.debug(f"Registered agent factory for '{agent_type}'")

    @classmethod
    def auto_discover_agents(cls) -> None:
        """Auto-discover and register all agent classes in implementations/ directory.

        This function:
        1. Scans all Python files in agents/implementations/
        2. Imports each module
        3. Finds classes with an AGENT_TYPE attribute
        4. Registers them with the AgentRegistry

        Agents must have:
        - AGENT_TYPE: str class attribute (e.g., "document_analyzer")
        - Must inherit from BaseAgent
        """
        if cls._registered:
            return

        # Get the implementations directory path
        agents_dir = Path(__file__).parent.parent / "implementations"
        if not agents_dir.exists():
            logger.warning(f"Implementations directory not found: {agents_dir}")
            cls._registered = True
            return

        # Files to skip during auto-discovery
        skip_files = {"__init__.py", "__pycache__"}

        # Discover all Python files
        agent_files = [
            f
            for f in agents_dir.glob("*.py")
            if f.name not in skip_files and not f.name.startswith("_")
        ]

        # Import and register each agent
        registered_count = 0
        for agent_file in agent_files:
            module_name = f"agents.implementations.{agent_file.stem}"
            try:
                # Import the module
                module = importlib.import_module(module_name)

                # Find all classes in the module with AGENT_TYPE
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if this class has AGENT_TYPE and is defined in this module
                    if (
                        hasattr(obj, "AGENT_TYPE")
                        and obj.__module__ == module_name
                        and not inspect.isabstract(obj)
                    ):
                        agent_type = obj.AGENT_TYPE
                        cls.register_type(agent_type, obj)
                        registered_count += 1

            except Exception as e:
                # Log but don't fail - allows partial registration
                logger.warning(f"Failed to import agent from {module_name}: {e}")

        cls._registered = True

        # Log registration summary
        if registered_count > 0:
            logger.info(
                f"Auto-registered {registered_count} agent types from {len(agent_files)} files"
            )

    @classmethod
    def create_agent(
        cls,
        agent_config: dict[str, Any],
        project_config: dict[str, Any],
        namespace: str,
        project: str,
        server_url: str = "http://localhost:8000",
    ) -> BaseAgent:
        """Create an agent instance from configuration.

        Args:
            agent_config: Agent configuration from llamafarm.yaml
            project_config: Full project configuration
            namespace: Project namespace
            project: Project name
            server_url: LlamaFarm server URL

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
        agent_type = (
            agent_type_raw.value
            if hasattr(agent_type_raw, "value")
            else str(agent_type_raw)
        )
        agent_name = agent_config["name"]

        logger.debug(f"Creating agent instance: {agent_name} (type: {agent_type})")

        # Ensure agents are auto-discovered before checking
        cls.auto_discover_agents()

        # Check if factory exists (takes precedence)
        if agent_type in cls._agent_factories:
            logger.debug(f"Creating agent '{agent_name}' using factory")
            factory = cls._agent_factories[agent_type]
            return factory(agent_config, project_config, namespace, project, server_url)

        # Check if type is registered
        if agent_type not in cls._agent_types:
            available = ", ".join(cls.list_types())
            raise ValueError(
                f"Agent type '{agent_type}' not registered. "
                f"Available types: {available or 'none'}"
            )

        # Create agent using registered class
        logger.debug(
            f"Creating agent '{agent_name}' using class {cls._agent_types[agent_type].__name__}"
        )

        agent_class = cls._agent_types[agent_type]
        return agent_class(agent_config, project_config, namespace, project, server_url)

    @classmethod
    def list_types(cls) -> list[str]:
        """List all registered agent types.

        Returns:
            List of agent type identifiers
        """
        # Ensure agents are discovered
        cls.auto_discover_agents()

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
        cls.auto_discover_agents()

        if (
            agent_type not in cls._agent_types
            and agent_type not in cls._agent_factories
        ):
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
        cls._registered = False
        logger.warning("Agent registry cleared")
