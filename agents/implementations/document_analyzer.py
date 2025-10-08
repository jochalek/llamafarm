"""Document Analyzer Agent.

This agent analyzes documents and extracts structured information using LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.core.base_agent import BaseAgent
from agents.services.server_client import ServerClient

logger = logging.getLogger(__name__)


class DocumentAnalyzerAgent(BaseAgent):
    """Agent for analyzing documents and extracting structured information.

    This agent:
    - Reads documents from RAG database via server API
    - Uses LLM to extract structured information via server API
    - Supports custom extraction schemas
    """

    AGENT_TYPE = "document_analyzer"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: dict[str, Any],
        namespace: str,
        project: str,
        server_url: str = "http://localhost:8000",
    ):
        """Initialize DocumentAnalyzerAgent.

        Agent config fields:
        - database: RAG database name (should use full documents)
        - retrieval_strategy: Strategy for retrieving documents
        - max_context_length: Maximum context length for LLM
        - extraction_schema: Schema for structured extraction (optional)
        """
        super().__init__(agent_config, project_config, namespace, project, server_url)

        # Agent-specific config
        self.database = self.config.get("database")
        self.retrieval_strategy = self.config.get("retrieval_strategy", "basic_search")
        self.max_context_length = self.config.get("max_context_length", 50000)
        self.extraction_schema = self.config.get("extraction_schema")

        # Initialize server client
        self.server_client = ServerClient(server_url)

    async def run(self, input_data: Any, **kwargs) -> Any:
        """Analyze documents and extract structured information.

        Args:
            input_data: Can be:
                - dict with {"query": "search term"} to search RAG
                - dict with {"document_content": "text"} for direct text
                - str: query string
            **kwargs: Additional parameters

        Returns:
            Extracted structured data
        """
        logger.info(
            f"DocumentAnalyzerAgent starting: {self.name} (database: {self.database})"
        )

        try:
            # Parse input
            documents = await self._parse_input(input_data)

            # Process documents
            results = []
            for doc in documents:
                extracted = await self._extract_from_document(doc["content"])
                results.append(
                    {
                        "source": doc.get("source", "unknown"),
                        "extracted_data": extracted,
                    }
                )

            logger.info(
                f"DocumentAnalyzerAgent completed: {self.name} "
                f"(processed {len(results)} documents)"
            )

            # Return single result or list based on input
            if len(results) == 1:
                return results[0]["extracted_data"]
            return {"documents": results}

        finally:
            await self.server_client.close()

    async def _parse_input(self, input_data: Any) -> list[dict[str, Any]]:
        """Parse input data into list of documents.

        Args:
            input_data: Input in various formats

        Returns:
            List of {"source": str, "content": str} dicts
        """
        # Direct text input
        if isinstance(input_data, str):
            # Treat as query string
            return await self._search_rag_database(input_data)

        # Dict input
        if isinstance(input_data, dict):
            # Query string - search RAG database
            if "query" in input_data:
                results = await self._search_rag_database(input_data["query"])
                return results

            # Direct content
            if "document_content" in input_data:
                return [
                    {
                        "source": input_data.get("source", "direct_input"),
                        "content": input_data["document_content"],
                    }
                ]

        raise ValueError(f"Unsupported input format: {type(input_data)}")

    async def _search_rag_database(self, query: str) -> list[dict[str, Any]]:
        """Search RAG database with query via server API.

        Args:
            query: Search query

        Returns:
            List of documents with content
        """
        if not self.database:
            logger.warning(f"No database configured for agent {self.name}")
            return []

        try:
            # Call server RAG API
            results = await self.server_client.rag_search(
                namespace=self.namespace,
                project=self.project,
                database=self.database,
                query=query,
                top_k=5,  # Get top 5 documents
                retrieval_strategy=self.retrieval_strategy,
            )

            return [
                {
                    "content": r.get("content", ""),
                    "source": r.get("metadata", {}).get("source", "unknown"),
                    "score": r.get("score", 0.0),
                }
                for r in results
            ]

        except Exception as e:
            logger.error(
                f"Failed to search RAG database: {e}",
                exc_info=True,
            )
            return []

    async def _extract_from_document(self, document_content: str) -> dict[str, Any]:
        """Extract structured information from document using LLM via server API.

        Args:
            document_content: Full document text

        Returns:
            Extracted structured data
        """
        # Build system prompt
        system_prompt = self.system_prompt or self._default_system_prompt()

        # Truncate if needed
        if len(document_content) > self.max_context_length:
            logger.warning(
                f"Document content truncated: {len(document_content)} -> {self.max_context_length}"
            )
            document_content = document_content[: self.max_context_length]

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Analyze this document and extract the requested information:\n\n{document_content}",
            },
        ]

        try:
            # Call server chat completions API
            response = await self.server_client.chat_completion(
                namespace=self.namespace,
                project=self.project,
                messages=messages,
                model=self.model_name,  # Uses project default if None
            )

            # Extract content from response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Try to parse as JSON if it looks like JSON
            import json

            content_stripped = content.strip()
            if content_stripped.startswith("{") or content_stripped.startswith("["):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass

            return {"content": content}

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}", exc_info=True)
            return {"error": str(e), "content": ""}

    def _default_system_prompt(self) -> str:
        """Get default system prompt for document analysis."""
        return """You are a document analysis expert. Extract structured information from the provided documents according to the specified schema. Be precise and thorough in your analysis."""
