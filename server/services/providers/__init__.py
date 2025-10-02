"""Model management provider implementations."""

from .ollama_model_provider import OllamaModelProvider
from .lemonade_model_provider import LemonadeModelProvider

__all__ = ["OllamaModelProvider", "LemonadeModelProvider", "get_provider"]


def get_provider(provider_type: str, base_url: str, **kwargs):
    """Factory function to get the appropriate provider instance.

    Args:
        provider_type: Provider name ("ollama", "lemonade", etc.)
        base_url: Base URL for the provider's API
        **kwargs: Provider-specific configuration

    Returns:
        ModelManagementProvider instance

    Raises:
        ValueError: If provider_type is not recognized
    """
    providers = {
        "ollama": OllamaModelProvider,
        "lemonade": LemonadeModelProvider,
    }

    provider_class = providers.get(provider_type.lower())
    if not provider_class:
        available = ", ".join(providers.keys())
        raise ValueError(
            f"Unknown provider: {provider_type}. Available: {available}"
        )

    return provider_class(base_url, **kwargs)
