"""Provider interface for model management operations.

This module defines an abstract base class for managing models across different
LLM runtime providers (Ollama, Lemonade, etc.).

Each provider implements:
- list_models(): Get available models
- pull_model(): Download/install a model
- delete_model(): Remove a model
- show_model(): Get detailed model information
- copy_model(): Duplicate a model (if supported)
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional
from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Standard model information across providers."""

    id: str  # Unique model identifier
    name: str  # Display name
    size: Optional[int] = None  # Size in bytes
    modified_at: Optional[str] = None  # Last modified timestamp
    digest: Optional[str] = None  # Model digest/hash
    details: Optional[dict[str, Any]] = None  # Provider-specific details

    # LlamaFarm-specific fields
    provider: str  # Provider name (ollama, lemonade, etc.)
    vision: bool = False  # Whether model supports vision
    reasoning: bool = False  # Whether model has reasoning capabilities


class PullProgress(BaseModel):
    """Progress information for model pulling."""

    status: str  # downloading, extracting, success, error
    completed: int = 0  # Bytes completed
    total: int = 0  # Total bytes
    message: Optional[str] = None  # Status message


class ModelManagementProvider(ABC):
    """Abstract base class for model management providers."""

    def __init__(self, base_url: str, **kwargs):
        """Initialize provider with base URL and optional config.

        Args:
            base_url: Base URL of the provider's API
            **kwargs: Provider-specific configuration
        """
        self.base_url = base_url
        self.config = kwargs

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List all available models from this provider.

        Returns:
            List of ModelInfo objects
        """
        pass

    @abstractmethod
    async def pull_model(
        self,
        model_name: str,
        **options
    ) -> AsyncIterator[PullProgress]:
        """Pull/download a model from the provider.

        Args:
            model_name: Name of the model to pull
            **options: Provider-specific pull options

        Yields:
            PullProgress updates during download
        """
        pass

    @abstractmethod
    async def delete_model(self, model_name: str) -> bool:
        """Delete a model from local storage.

        Args:
            model_name: Name of the model to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def show_model(self, model_name: str) -> dict[str, Any]:
        """Get detailed information about a specific model.

        Args:
            model_name: Name of the model

        Returns:
            Dictionary with detailed model information
        """
        pass

    async def copy_model(
        self,
        source: str,
        destination: str
    ) -> bool:
        """Copy a model to a new name (optional operation).

        Args:
            source: Source model name
            destination: Destination model name

        Returns:
            True if successful, False if not supported

        Raises:
            NotImplementedError: If provider doesn't support copying
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support model copying"
        )

    async def push_model(
        self,
        model_name: str,
        **options
    ) -> AsyncIterator[dict]:
        """Push a model to a registry (optional operation).

        Args:
            model_name: Name of the model to push
            **options: Provider-specific push options

        Yields:
            Progress updates during upload

        Raises:
            NotImplementedError: If provider doesn't support pushing
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support model pushing"
        )
