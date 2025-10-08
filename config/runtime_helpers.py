"""Runtime helper methods for LlamaFarmConfig.

This module provides helper methods for working with Runtime configurations.
These helpers are kept separate from datamodel.py since that file is auto-generated.
"""

from typing import Optional
from config.datamodel import Runtime, Model


def get_active_model(runtime: Runtime, model_name: Optional[str] = None) -> Model:
    """Get the active model config (specified, default, or first).

    Args:
        runtime: Runtime configuration object
        model_name: Optional model name to select

    Returns:
        Model configuration

    Raises:
        ValueError: If model_name doesn't exist or no models configured
    """
    if not runtime.models:
        raise ValueError("No models configured in runtime")

    # If specific model requested, find it
    if model_name:
        for model in runtime.models:
            if model.name == model_name:
                return model
        available = ", ".join([m.name for m in runtime.models])
        raise ValueError(f"Model '{model_name}' not found. Available: {available}")

    # Use default_model if set
    if runtime.default_model:
        for model in runtime.models:
            if model.name == runtime.default_model:
                return model

    # Fall back to first model
    return runtime.models[0]
