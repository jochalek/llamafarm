"""RAG Validator Agent.

This agent validates whether questions are answered in a RAG corpus.
Designed for checking if FDA questions have been addressed in response documents.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from agents.providers import get_provider
from config.datamodel import LlamaFarmConfig, Model, Runtime, PromptFormat
from core.logging import FastAPIStructLogger

logger = FastAPIStructLogger(__name__)


class ValidationResult(BaseModel):
    """Structured output for RAG validation."""

    answered: bool = Field(description="Whether the question is answered by the context")
    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0",
        ge=0.0,
        le=1.0,
    )
    evidence: list[str] = Field(
        description="List of relevant source document references",
        default_factory=list,
    )
    summary: str = Field(
        description="Brief explanation of the answer or why it wasn't found"
    )


class RAGValidatorAgent(BaseAgent):
    """Agent for validating if questions are answered using RAG.

    This agent:
    - Takes questions as input
    - Queries RAG database for relevant chunks
    - Uses LLM to determine if question is answered
    - Returns confidence scores and evidence
    """

    AGENT_TYPE = "rag_validator"

    def __init__(
        self,
            agent_config: dict[str, Any],
        project_config: LlamaFarmConfig,
        project_dir: str,
    ):
        """Initialize RAGValidatorAgent.

        Agent config fields:
        - database: RAG database name (should use chunked corpus)
        - retrieval_strategy: Strategy for retrieving chunks
        - top_k: Number of chunks to retrieve
        - confidence_threshold: Minimum confidence to consider "answered"
        - system_prompt: Custom system prompt (optional)
        """
        super().__init__(agent_config, project_config, project_dir)

        # Agent-specific config
        config = agent_config.get("config", {})
        self.database = config.get("database")
        self.retrieval_strategy = config.get("retrieval_strategy", "semantic_search")
        self.top_k = config.get("top_k", 10)
        self.confidence_threshold = config.get("confidence_threshold", 0.75)
        self.custom_system_prompt = agent_config.get("system_prompt")

        # Initialize LLM client
        self._init_client()

    def _init_client(self):
        """Initialize LLM client for validation."""
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
            prompt_format=self.model_config.prompt_format or PromptFormat.structured,
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
        """Validate if questions are answered in RAG corpus.

        Args:
            input_data: Can be:
                - dict with single question: {"question": "text"}
                - dict with multiple questions: {"questions": [...]}
                - list of question dicts
                - str: single question text
            **kwargs: Additional parameters

        Returns:
            Validation results with answered status, confidence, evidence
        """
        logger.info(
            "RAGValidatorAgent starting",
            agent_name=self.name,
            database=self.database,
        )

        # Parse input
        questions = self._parse_input(input_data)

        # Validate each question
        results = []
        for question in questions:
            logger.debug(
                "Validating question",
                agent_name=self.name,
                question=question.get("question_text", question.get("question", ""))[:100],
            )

            validation = await self._validate_question(question)
            results.append(validation)

        logger.info(
            "RAGValidatorAgent completed",
            agent_name=self.name,
            questions_validated=len(results),
            questions_answered=sum(1 for r in results if r["answered"]),
        )

        # Return single result or list based on input
        if len(results) == 1:
            return results[0]
        return {"validations": results}

    def _parse_input(self, input_data: Any) -> list[dict[str, Any]]:
        """Parse input data into list of questions.

        Args:
            input_data: Input in various formats

        Returns:
            List of question dicts
        """
        # String input
        if isinstance(input_data, str):
            return [{"question": input_data}]

        # List input
        if isinstance(input_data, list):
            return input_data

        # Dict input
        if isinstance(input_data, dict):
            # Single question
            if "question" in input_data:
                return [input_data]

            # Multiple questions
            if "questions" in input_data:
                return input_data["questions"]

        raise ValueError(f"Unsupported input format: {type(input_data)}")

    async def _validate_question(self, question: dict[str, Any]) -> dict[str, Any]:
        """Validate if a single question is answered using RAG.

        Args:
            question: Question dict with at least "question" or "question_text" field

        Returns:
            Validation result with answered status, confidence, evidence
        """
        question_text = question.get("question_text") or question.get("question")
        if not question_text:
            raise ValueError("Question missing 'question_text' or 'question' field")

        chunks = await self._query_rag(question_text)
        validation_result = await self._llm_validate(question_text, chunks)

        validation_result["question_id"] = question.get("id", question_text[:50])
        validation_result["question"] = question_text

        return validation_result

    async def _query_rag(self, question_text: str) -> list[dict[str, Any]]:
        """Query RAG database for relevant chunks.

        Args:
            question_text: Question to search for

        Returns:
            List of relevant chunks with metadata and scores
        """
        try:
            from services.rag_service import search_with_rag

            # Query RAG database using the RAG service
            results = search_with_rag(
                project_dir=self.project_dir,
                database=self.database,
                query=question_text,
                top_k=self.top_k,
                retrieval_strategy=self.retrieval_strategy,
            )

            # Convert results to expected format
            chunks = []
            for result in results:
                chunks.append({
                    "content": result["content"],
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0.0),
                })

            logger.info(
                "RAG query completed",
                agent_name=self.name,
                chunks_retrieved=len(chunks),
            )

            return chunks

        except Exception as e:
            logger.error(
                "Failed to query RAG database",
                agent_name=self.name,
                error=str(e),
            )
            return []

    async def _llm_validate(
        self, question: str, chunks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Use LLM to validate if question is answered by chunks.

        Args:
            question: Question text
            chunks: Retrieved RAG chunks

        Returns:
            Validation result dict
        """
        # Build system prompt
        system_prompt = self.custom_system_prompt or self._default_system_prompt()

        # Build context from chunks
        context = self._build_context(chunks)

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""Question: {question}

Retrieved Context:
{context}

Determine if the question is answered by the context. Provide:
1. answered: true/false
2. confidence: 0.0-1.0 score
3. evidence: list of relevant source references
4. summary: brief explanation of the answer if found, or why not found""",
            },
        ]

        # If no chunks retrieved, return negative result immediately
        if not chunks:
            return {
                "answered": False,
                "confidence": 0.0,
                "evidence": [],
                "summary": "No relevant information found in the corpus",
            }

        # Use LLM with structured output via instructor
        try:
            response = await self.client.chat.completions.create(
                model=self.model_config.model,
                messages=messages,
                response_model=ValidationResult,
                max_tokens=self.model_config.model_api_parameters.get("max_tokens", 1000)
                if self.model_config.model_api_parameters
                else 1000,
            )

            # Convert Pydantic model to dict
            result = response.model_dump() if hasattr(response, "model_dump") else response.dict()

            logger.info(
                "LLM validation completed",
                agent_name=self.name,
                answered=result["answered"],
                confidence=result["confidence"],
            )

            return result

        except Exception as e:
            logger.error(
                "LLM validation failed, falling back to heuristic",
                agent_name=self.name,
                error=str(e),
            )

            # Fallback to heuristic if LLM call fails
            answered = len(chunks) > 0 and chunks[0]["score"] > self.confidence_threshold
            confidence = chunks[0]["score"] if chunks else 0.0

            return {
                "answered": answered,
                "confidence": confidence,
                "evidence": [c["metadata"]["source"] for c in chunks[:3]] if chunks else [],
                "summary": f"Heuristic result (LLM failed): {'Answer likely present' if answered else 'No answer found'}",
            }

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        """Build context string from chunks.

        Args:
            chunks: Retrieved chunks

        Returns:
            Formatted context string
        """
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk["metadata"].get("source", "unknown")
            page = chunk["metadata"].get("page", "?")
            score = chunk.get("score", 0.0)

            context_parts.append(
                f"[{i}] Source: {source} (page {page}, relevance: {score:.2f})\n{chunk['content']}\n"
            )

        return "\n".join(context_parts)

    def _default_system_prompt(self) -> str:
        """Get default system prompt for validation."""
        return """You are a document analysis expert. Your task is to determine if a question is answered by the provided context from a document corpus.

Analyze the retrieved context carefully and provide:
- answered: true if the context contains information that answers the question, false otherwise
- confidence: a score from 0.0 to 1.0 indicating how confident you are in the answer
- evidence: list of document references that support the answer
- summary: a brief explanation of the answer, or why it wasn't found

Be precise and conservative - only mark as answered if the context truly addresses the question."""
