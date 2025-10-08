"""LlamaFarm Agents module.

This module provides the agent system for LlamaFarm, including:
- Base agent interface (BaseAgent)
- Agent registry (AgentRegistry)
- Built-in agent implementations
- Auto-discovery and registration

Agents are automatically discovered and registered when the registry is first accessed.
To add a new agent, simply create a file in this directory with a class that:
1. Inherits from BaseAgent
2. Has an AGENT_TYPE class attribute
"""

import importlib
import inspect
from pathlib import Path

# Lazy registration state
_agents_registered = False


def _auto_discover_and_register_agents():
    """Auto-discover and register all agent classes in this directory.

    This function:
    1. Scans all Python files in the agents directory
    2. Imports each module
    3. Finds classes with an AGENT_TYPE attribute
    4. Registers them with the AgentRegistry

    Agents must have:
    - AGENT_TYPE: str class attribute (e.g., "document_analyzer")
    - Must inherit from BaseAgent
    """
    global _agents_registered
    if _agents_registered:
        return

    # Import registry first (it doesn't depend on BaseAgent at import time)
    from agents.registry import AgentRegistry

    # Get the agents directory path
    agents_dir = Path(__file__).parent

    # Files to skip during auto-discovery
    skip_files = {
        "__init__.py",
        "base_agent.py",  # Base class, not an agent implementation
        "registry.py",    # Registry, not an agent
        "agent.py",       # Legacy LFAgent
        "project_chat_orchestrator.py",  # Legacy, will be refactored later
    }

    # Discover all Python files
    agent_files = [
        f for f in agents_dir.glob("*.py")
        if f.name not in skip_files and not f.name.startswith("_")
    ]

    # Import and register each agent
    registered_count = 0
    for agent_file in agent_files:
        module_name = f"agents.{agent_file.stem}"
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
                    AgentRegistry.register_type(agent_type, obj)
                    registered_count += 1

        except Exception as e:
            # Log but don't fail - allows partial registration
            import logging
            logging.warning(
                f"Failed to import agent from {module_name}: {e}"
            )

    _agents_registered = True

    # Log registration summary
    if registered_count > 0:
        import logging
        logging.info(
            f"Auto-registered {registered_count} agent types from {len(agent_files)} files"
        )


def __getattr__(name):
    """Lazy import and registration of agent classes.

    This enables:
    - from agents import BaseAgent
    - from agents import AgentRegistry
    - from agents import DocumentAnalyzerAgent

    Without triggering imports at module load time.
    """
    # Always ensure agents are registered when accessing registry
    if name == "AgentRegistry":
        from agents.registry import AgentRegistry
        _auto_discover_and_register_agents()
        return AgentRegistry

    # BaseAgent doesn't need registration
    if name == "BaseAgent":
        from agents.base_agent import BaseAgent
        return BaseAgent

    # For specific agent classes, ensure registration then import
    # Try to import from the module with the same name (snake_case)
    module_name = _camel_to_snake(name.replace("Agent", ""))

    try:
        _auto_discover_and_register_agents()
        module = importlib.import_module(f"agents.{module_name}")
        return getattr(module, name)
    except (ImportError, AttributeError):
        raise AttributeError(f"module 'agents' has no attribute '{name}'")


def _camel_to_snake(name):
    """Convert CamelCase to snake_case.

    Examples:
        DocumentAnalyzer -> document_analyzer
        RAGValidator -> rag_validator
    """
    import re
    # Insert underscore before capitals (except first char)
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Insert underscore before capitals preceded by lowercase
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# Define __all__ for type checkers and documentation
# Actual imports are handled by __getattr__
__all__ = [
    "BaseAgent",
    "AgentRegistry",
    # Agent implementations are auto-discovered
]
