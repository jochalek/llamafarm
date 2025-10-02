"""Ollama model management provider implementation."""

import aiohttp
from typing import Any, AsyncIterator

from ..model_management_provider import (
    ModelManagementProvider,
    ModelInfo,
    PullProgress,
)


class OllamaModelProvider(ModelManagementProvider):
    """Ollama-specific model management implementation."""

    async def list_models(self) -> list[ModelInfo]:
        """List all locally available Ollama models.

        Calls GET /api/tags

        Returns:
            List of ModelInfo objects with Ollama model details
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/api/tags") as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Failed to list Ollama models: {response.status}"
                    )

                data = await response.json()
                models = []

                for model_data in data.get("models", []):
                    models.append(
                        ModelInfo(
                            id=model_data["name"],
                            name=model_data["name"],
                            size=model_data.get("size"),
                            modified_at=model_data.get("modified_at"),
                            digest=model_data.get("digest"),
                            details=model_data.get("details"),
                            provider="ollama",
                            # Ollama doesn't expose vision/reasoning flags in list
                            # Would need to call show_model for details
                        )
                    )

                return models

    async def pull_model(
        self,
        model_name: str,
        **options
    ) -> AsyncIterator[PullProgress]:
        """Pull a model from Ollama library.

        Calls POST /api/pull with streaming response

        Args:
            model_name: Model name (e.g., "llama3:70b")
            **options:
                insecure: bool - Allow insecure connections
                stream: bool - Stream progress (default: True)

        Yields:
            PullProgress updates during download
        """
        payload = {
            "model": model_name,
            "stream": options.get("stream", True),
        }

        if "insecure" in options:
            payload["insecure"] = options["insecure"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/pull",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield PullProgress(
                        status="error",
                        message=f"Pull failed: {error_text}"
                    )
                    return

                # Stream progress updates
                async for line in response.content:
                    if not line:
                        continue

                    try:
                        import json
                        progress_data = json.loads(line)

                        status = progress_data.get("status", "unknown")
                        completed = progress_data.get("completed", 0)
                        total = progress_data.get("total", 0)

                        yield PullProgress(
                            status=status,
                            completed=completed,
                            total=total,
                            message=progress_data.get("message"),
                        )

                        # Check if done
                        if status in ["success", "error"]:
                            break

                    except json.JSONDecodeError:
                        continue

    async def delete_model(self, model_name: str) -> bool:
        """Delete a model from Ollama.

        Calls DELETE /api/delete

        Args:
            model_name: Model name to delete

        Returns:
            True if successful
        """
        payload = {"model": model_name}

        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}/api/delete",
                json=payload
            ) as response:
                return response.status == 200

    async def show_model(self, model_name: str) -> dict[str, Any]:
        """Get detailed information about an Ollama model.

        Calls POST /api/show

        Args:
            model_name: Model name

        Returns:
            Dictionary with model details including:
            - modelfile
            - parameters
            - template
            - details (architecture, family, etc.)
        """
        payload = {"model": model_name}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/show",
                json=payload
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Failed to get model info: {response.status}"
                    )

                return await response.json()

    async def copy_model(self, source: str, destination: str) -> bool:
        """Copy an Ollama model to a new name.

        Calls POST /api/copy

        Args:
            source: Source model name
            destination: Destination model name

        Returns:
            True if successful
        """
        payload = {
            "source": source,
            "destination": destination,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/copy",
                json=payload
            ) as response:
                return response.status == 200

    async def push_model(
        self,
        model_name: str,
        **options
    ) -> AsyncIterator[dict]:
        """Push a model to Ollama registry.

        Calls POST /api/push with streaming response

        Args:
            model_name: Model name in namespace/model:tag format
            **options:
                insecure: bool - Allow insecure connections
                stream: bool - Stream progress (default: True)

        Yields:
            Progress dictionaries during upload
        """
        payload = {
            "model": model_name,
            "stream": options.get("stream", True),
        }

        if "insecure" in options:
            payload["insecure"] = options["insecure"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/push",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield {"status": "error", "message": error_text}
                    return

                # Stream progress updates
                async for line in response.content:
                    if not line:
                        continue

                    try:
                        import json
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
