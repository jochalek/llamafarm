"""HTTP client for LlamaFarm server APIs.

This client provides access to RAG, model, and project APIs through the server.
All agents should use this client to interact with server resources.
"""

import httpx
from typing import Any, Optional, AsyncGenerator
import logging

logger = logging.getLogger(__name__)


class ServerClient:
    """Client for calling LlamaFarm server APIs.

    This unified client provides access to:
    - RAG search and query endpoints
    - Chat completions (model) endpoints
    - Project configuration endpoints
    """

    def __init__(self, server_url: str, timeout: int = 120):
        """Initialize server client.

        Args:
            server_url: Base URL of LlamaFarm server (e.g., http://localhost:8000)
            timeout: Request timeout in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout)
        self._closed = False

    # =============================================================================
    # RAG APIs
    # =============================================================================

    async def rag_search(
        self,
        namespace: str,
        project: str,
        database: str,
        query: str,
        top_k: int = 10,
        retrieval_strategy: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """Search RAG database.

        Args:
            namespace: Project namespace
            project: Project name
            database: Database name
            query: Search query
            top_k: Number of results to return
            retrieval_strategy: Optional retrieval strategy
            score_threshold: Optional minimum score threshold

        Returns:
            List of search results with content, metadata, and scores
        """
        url = f"{self.server_url}/v1/projects/{namespace}/{project}/rag/query"
        payload = {
            "database": database,
            "query": query,
            "top_k": top_k,
        }
        if retrieval_strategy:
            payload["retrieval_strategy"] = retrieval_strategy
        if score_threshold is not None:
            payload["score_threshold"] = score_threshold

        logger.debug(f"RAG search: {database} query='{query}' top_k={top_k}")

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPError as e:
            logger.error(f"RAG search failed: {e}")
            raise

    async def rag_health(self) -> dict[str, Any]:
        """Check RAG service health.

        Returns:
            Health status dictionary
        """
        url = f"{self.server_url}/v1/rag/health"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"RAG health check failed: {e}")
            raise

    # =============================================================================
    # Model/Chat APIs
    # =============================================================================

    async def chat_completion(
        self,
        namespace: str,
        project: str,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> dict[str, Any] | AsyncGenerator[str, None]:
        """Call chat completions endpoint.

        Args:
            namespace: Project namespace
            project: Project name
            messages: List of chat messages
            model: Optional model name (uses project default if not specified)
            stream: Whether to stream the response
            **kwargs: Additional parameters for the model

        Returns:
            Chat completion response or async generator for streaming
        """
        url = f"{self.server_url}/v1/projects/{namespace}/{project}/chat/completions"
        payload = {
            "messages": messages,
            "stream": stream,
            **kwargs,
        }
        if model:
            payload["model"] = model

        logger.debug(
            f"Chat completion: model={model or 'default'} stream={stream} "
            f"messages={len(messages)}"
        )

        if stream:
            return self._stream_chat(url, payload)
        else:
            try:
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Chat completion failed: {e}")
                raise

    async def _stream_chat(
        self, url: str, payload: dict
    ) -> AsyncGenerator[str, None]:
        """Stream chat completions.

        Args:
            url: API endpoint URL
            payload: Request payload

        Yields:
            Server-sent event chunks
        """
        try:
            async with self.client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]  # Strip "data: " prefix
        except httpx.HTTPError as e:
            logger.error(f"Chat streaming failed: {e}")
            raise

    # =============================================================================
    # Project APIs
    # =============================================================================

    async def get_project_config(
        self, namespace: str, project: str
    ) -> dict[str, Any]:
        """Get project configuration.

        Args:
            namespace: Project namespace
            project: Project name

        Returns:
            Project configuration dictionary
        """
        url = f"{self.server_url}/v1/projects/{namespace}/{project}"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Get project config failed: {e}")
            raise

    async def list_models(self, namespace: str, project: str) -> list[dict[str, Any]]:
        """List available models for a project.

        Args:
            namespace: Project namespace
            project: Project name

        Returns:
            List of model configurations
        """
        url = f"{self.server_url}/v1/projects/{namespace}/{project}/models"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except httpx.HTTPError as e:
            logger.error(f"List models failed: {e}")
            raise

    # =============================================================================
    # Lifecycle
    # =============================================================================

    async def close(self) -> None:
        """Close the HTTP client."""
        if not self._closed:
            await self.client.aclose()
            self._closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
