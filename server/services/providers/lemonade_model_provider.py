"""Lemonade model management provider implementation."""

import aiohttp
from typing import Any, AsyncIterator, Optional

from ..model_management_provider import (
    ModelManagementProvider,
    ModelInfo,
    PullProgress,
)


class LemonadeModelProvider(ModelManagementProvider):
    """Lemonade-specific model management implementation."""

    async def list_models(self) -> list[ModelInfo]:
        """List all available Lemonade models.

        Calls GET /api/v1/models

        Returns:
            List of ModelInfo objects with Lemonade model details
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/api/v1/models") as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Failed to list Lemonade models: {response.status}"
                    )

                data = await response.json()
                models = []

                for model_data in data.get("data", []):
                    # Extract vision/reasoning from labels if available
                    labels = model_data.get("labels", [])
                    has_vision = "vision" in labels if isinstance(labels, list) else False
                    has_reasoning = "reasoning" in labels if isinstance(labels, list) else False

                    models.append(
                        ModelInfo(
                            id=model_data["id"],
                            name=model_data["id"],
                            size=None,  # Lemonade doesn't provide size in list
                            modified_at=None,
                            digest=None,
                            details={
                                "checkpoint": model_data.get("checkpoint"),
                                "recipe": model_data.get("recipe"),
                                "labels": labels,
                            },
                            provider="lemonade",
                            vision=has_vision,
                            reasoning=has_reasoning,
                        )
                    )

                return models

    async def pull_model(
        self,
        model_name: str,
        **options
    ) -> AsyncIterator[PullProgress]:
        """Pull a model from Lemonade registry.

        Calls POST /api/v1/pull

        Args:
            model_name: Model name (registered or user.ModelName)
            **options:
                checkpoint: str - HuggingFace checkpoint (for new models)
                recipe: str - Recipe name (llamacpp, transformers, etc.)
                vision: bool - Whether model supports vision
                reasoning: bool - Whether model has reasoning
                mmproj: str - Path to multimodal projector for vision models

        Yields:
            PullProgress updates during download
        """
        payload = {"model_name": model_name}

        # Add optional parameters for custom models
        if "checkpoint" in options:
            payload["checkpoint"] = options["checkpoint"]
        if "recipe" in options:
            payload["recipe"] = options["recipe"]
        if "vision" in options:
            payload["vision"] = options["vision"]
        if "reasoning" in options:
            payload["reasoning"] = options["reasoning"]
        if "mmproj" in options:
            payload["mmproj"] = options["mmproj"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/pull",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield PullProgress(
                        status="error",
                        message=f"Pull failed: {error_text}"
                    )
                    return

                # Lemonade returns simple JSON response, not streaming
                result = await response.json()

                if result.get("status") == "success":
                    yield PullProgress(
                        status="success",
                        message=result.get("message", "Model pulled successfully")
                    )
                else:
                    yield PullProgress(
                        status="error",
                        message=result.get("message", "Unknown error")
                    )

    async def delete_model(self, model_name: str) -> bool:
        """Delete a model from Lemonade.

        Calls DELETE /api/v1/models/{model_name}

        Args:
            model_name: Model name to delete

        Returns:
            True if successful
        """
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}/api/v1/models/{model_name}"
            ) as response:
                return response.status == 200

    async def show_model(self, model_name: str) -> dict[str, Any]:
        """Get detailed information about a Lemonade model.

        Calls GET /api/v1/models (filtered by model_name)

        Args:
            model_name: Model name

        Returns:
            Dictionary with model details
        """
        models = await self.list_models()

        for model in models:
            if model.id == model_name or model.name == model_name:
                return {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "vision": model.vision,
                    "reasoning": model.reasoning,
                    "details": model.details,
                }

        raise RuntimeError(f"Model '{model_name}' not found")
