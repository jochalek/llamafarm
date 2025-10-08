"""Document Analyzer Agent.

This agent analyzes documents and extracts structured information using LLM.
Designed for tasks like extracting FDA questions from regulatory documents.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from agents.providers import get_provider
from config.datamodel import LlamaFarmConfig, Model, Runtime, PromptFormat
from core.logging import FastAPIStructLogger

logger = FastAPIStructLogger(__name__)


class DocumentAnalyzerAgent(BaseAgent):
    """Agent for analyzing documents and extracting structured information.

    This agent:
    - Reads full documents from RAG database (uses full_document_processor)
    - Uses LLM to extract structured information
    - Supports custom extraction schemas
    - Can process multiple documents in batch
    """

    AGENT_TYPE = "document_analyzer"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: LlamaFarmConfig,
        project_dir: str,
    ):
        """Initialize DocumentAnalyzerAgent.

        Agent config fields:
        - database: RAG database name (should use full documents)
        - retrieval_strategy: Strategy for retrieving documents
        - max_context_length: Maximum context length for LLM
        - extraction_schema: Pydantic schema for structured extraction
        - system_prompt: Custom system prompt (optional)
        """
        super().__init__(agent_config, project_config, project_dir)

        # Agent-specific config
        config = agent_config.get("config", {})
        self.database = config.get("database")
        self.retrieval_strategy = config.get("retrieval_strategy", "full_doc_retrieval")
        self.max_context_length = config.get("max_context_length", 50000)
        self.extraction_schema = config.get("extraction_schema")
        self.custom_system_prompt = agent_config.get("system_prompt")

        # Initialize LLM client
        self._init_client()

    def _init_client(self):
        """Initialize LLM client for structured extraction."""
        # Get provider
        provider = get_provider(self.model_config.provider)

        # Create minimal config for client
        model_obj = Model(
            name=self.model_config.name,
            provider=self.model_config.provider,
            model=self.model_config.model,
            base_url=self.model_config.base_url,
            api_key=self.model_config.api_key,
            instructor_mode=self.model_config.instructor_mode,
            prompt_format=PromptFormat.structured,  # Force structured for extraction
            model_api_parameters=self.model_config.model_api_parameters,
            provider_config=self.model_config.provider_config,
        )

        temp_config = LlamaFarmConfig(
            version=self.project_config.version,
            name=self.project_config.name,
            namespace=self.project_config.namespace,
            runtime=Runtime(models=[model_obj]),
        )

        self.client = provider.get_client(temp_config)

    async def run(self, input_data: Any, **kwargs) -> Any:
        """Analyze documents and extract structured information.

        Args:
            input_data: Can be:
                - dict with {"files": ["path1", "path2"]} for batch processing
                - dict with {"document_content": "text"} for direct text
                - str: single document content
            **kwargs: Additional parameters

        Returns:
            Extracted structured data according to extraction_schema
        """
        logger.info(
            "DocumentAnalyzerAgent starting",
            agent_name=self.name,
            database=self.database,
        )

        # Parse input
        documents = self._parse_input(input_data)

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
            "DocumentAnalyzerAgent completed",
            agent_name=self.name,
            documents_processed=len(results),
        )

        # Return single result or list based on input
        if len(results) == 1:
            return results[0]["extracted_data"]
        return {"documents": results}

    def _parse_input(self, input_data: Any) -> list[dict[str, Any]]:
        """Parse input data into list of documents.

        Args:
            input_data: Input in various formats

        Returns:
            List of {"source": str, "content": str} dicts
        """
        # Direct text input
        if isinstance(input_data, str):
            return [{"source": "direct_input", "content": input_data}]

        # Dict input
        if isinstance(input_data, dict):
            # File list - query RAG database to get full document content
            if "files" in input_data:
                documents = []
                for file_path in input_data["files"]:
                    # Query RAG database using config from llamafarm.yaml
                    doc_content = self._fetch_document_from_rag(file_path)
                    documents.append({"source": file_path, "content": doc_content})
                return documents

            # Direct content
            if "document_content" in input_data:
                return [
                    {
                        "source": input_data.get("source", "direct_input"),
                        "content": input_data["document_content"],
                    }
                ]

            # Query string - search RAG database
            if "query" in input_data:
                results = self._search_rag_database(input_data["query"])
                return [
                    {"source": r.get("source", "rag_search"), "content": r["content"]}
                    for r in results
                ]

        raise ValueError(f"Unsupported input format: {type(input_data)}")

    def _fetch_document_from_rag(self, file_path: str) -> str:
        """Fetch full document content from RAG database via RAG service.

        Args:
            file_path: Path or identifier for the document

        Returns:
            Full document content
        """
        if not self.database:
            logger.warning(
                "No database configured, returning placeholder",
                agent_name=self.name,
                file_path=file_path,
            )
            return f"[No database configured for {file_path}]"

        try:
            from services.rag_service import search_with_rag

            # Use server's RAG service (calls Celery task directly)
            results = search_with_rag(
                project_dir=self.project_dir,
                database=self.database,
                query=file_path,  # Search by filename/path
                top_k=1,  # Get full document
                retrieval_strategy=self.retrieval_strategy,
            )

            if results:
                return results[0]["content"]
            else:
                logger.warning(
                    "Document not found in RAG database",
                    agent_name=self.name,
                    file_path=file_path,
                    database=self.database,
                )
                return f"[Document {file_path} not found in database {self.database}]"

        except Exception as e:
            logger.error(
                "Failed to fetch document from RAG",
                agent_name=self.name,
                error=str(e),
                file_path=file_path,
            )
            return f"[Error fetching {file_path}: {e}]"

    def _search_rag_database(self, query: str) -> list[dict[str, Any]]:
        """Search RAG database with query via RAG service.

        Args:
            query: Search query

        Returns:
            List of search results with content
        """
        if not self.database:
            return []

        try:
            from services.rag_service import search_with_rag

            # Use server's RAG service (calls Celery task directly)
            results = search_with_rag(
                project_dir=self.project_dir,
                database=self.database,
                query=query,
                top_k=10,  # Configurable via agent config
                retrieval_strategy=self.retrieval_strategy,
            )

            return [
                {
                    "content": r["content"],
                    "source": r.get("metadata", {}).get("source", "unknown"),
                    "score": r.get("score", 0.0),
                }
                for r in results
            ]

        except Exception as e:
            logger.error(
                "Failed to search RAG database",
                agent_name=self.name,
                error=str(e),
                query=query,
            )
            return []

    async def _extract_from_document(self, document_content: str) -> dict[str, Any]:
        """Extract structured information from document using LLM.

        Args:
            document_content: Full document text

        Returns:
            Extracted structured data
        """
        # Build system prompt
        system_prompt = self.custom_system_prompt or self._default_system_prompt()

        # Truncate if needed
        if len(document_content) > self.max_context_length:
            logger.warning(
                "Document content truncated",
                agent_name=self.name,
                original_length=len(document_content),
                max_length=self.max_context_length,
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

        # Use structured extraction if schema provided
        if self.extraction_schema:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_config.model,
                    messages=messages,
                    response_model=self.extraction_schema,
                    max_tokens=self.model_config.model_api_parameters.get("max_tokens", 4000)
                    if self.model_config.model_api_parameters
                    else 4000,
                )
                # Convert Pydantic model to dict
                return response.model_dump() if hasattr(response, "model_dump") else response.dict()
            except Exception as e:
                logger.error(
                    "Structured extraction failed",
                    agent_name=self.name,
                    error=str(e),
                )
                # Fallback to unstructured
                logger.warning("Falling back to unstructured extraction", agent_name=self.name)

        # Unstructured extraction (or fallback)
        try:
            # Get the original client (unwrapped from instructor if needed)
            client = self.client
            if hasattr(self.client, 'client'):
                # Instructor wraps the original client
                client = self.client.client

            response = await client.chat.completions.create(
                model=self.model_config.model,
                messages=messages,
                max_tokens=self.model_config.model_api_parameters.get("max_tokens", 4000)
                if self.model_config.model_api_parameters
                else 4000,
            )
            content = response.choices[0].message.content

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
            logger.error(
                "LLM extraction failed",
                agent_name=self.name,
                error=str(e),
            )
            return {"error": str(e), "content": ""}

    def _default_system_prompt(self) -> str:
        """Get default system prompt for document analysis."""
        return """You are a document analysis expert. Extract structured information from the provided documents according to the specified schema. Be precise and thorough in your analysis."""
