"""FDA Answer Validator Agent.

This agent validates whether FDA questions have been answered in the response corpus.
Performs recursive verification to ensure answers are REAL (not just related content).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.core.base_agent import BaseAgent
from agents.services.server_client import ServerClient

logger = logging.getLogger(__name__)


class FDAAnswerValidatorAgent(BaseAgent):
    """Agent for validating FDA question answers in response corpus.

    This agent:
    - Takes extracted FDA questions
    - Searches RAG corpus for potential answers
    - Uses LLM to verify answer validity (not just related content)
    - Ensures the answer references the question context
    - Provides evidence (document name, page, excerpt)
    """

    AGENT_TYPE = "fda_answer_validator"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: dict[str, Any],
        namespace: str,
        project: str,
        server_url: str = "http://localhost:8000",
    ):
        """Initialize FDAAnswerValidatorAgent.

        Agent config fields:
        - database: RAG database with response documents
        - retrieval_strategy: Strategy for RAG search
        - top_k: Number of chunks to retrieve (default 10)
        - confidence_threshold: Min confidence for answered (default 0.75)
        - max_recursion_depth: Max recursive verification attempts (default 2)
        """
        super().__init__(agent_config, project_config, namespace, project, server_url)

        # Agent-specific config
        self.database = self.config.get("database")
        self.retrieval_strategy = self.config.get("retrieval_strategy", "semantic_search")
        self.top_k = self.config.get("top_k", 3)  # Reduced from 10 for speed
        self.confidence_threshold = self.config.get("confidence_threshold", 0.75)
        self.max_recursion_depth = 0  # Disabled recursion for speed - single-pass only

        # Initialize server client
        self.server_client = ServerClient(server_url)

    async def run(self, input_data: Any, **kwargs) -> Any:
        """Validate FDA question answers.

        Args:
            input_data: Dict with:
                - questions: List of extracted questions from extractor agent
                - document_name: Source document name
            **kwargs: Additional parameters

        Returns:
            Dict with validation results and statistics
        """
        logger.info(f"FDAAnswerValidator starting: {self.name}")

        try:
            questions = input_data.get("questions", [])
            document_name = input_data.get("document_name", "unknown")

            if not questions:
                return {
                    "document_name": document_name,
                    "validations": [],
                    "stats": {"total": 0, "answered": 0, "unanswered": 0},
                }

            # Validate each question
            validations = []
            for question_data in questions:
                validation = await self._validate_question(question_data, document_name)
                validations.append(validation)

            # Calculate stats
            stats = {
                "total": len(validations),
                "answered": len([v for v in validations if v.get("answered")]),
                "unanswered": len([v for v in validations if not v.get("answered")]),
                "high_confidence": len(
                    [
                        v
                        for v in validations
                        if v.get("confidence", 0) >= self.confidence_threshold
                    ]
                ),
            }

            logger.info(
                f"FDAAnswerValidator completed: {self.name} "
                f"({stats['answered']}/{stats['total']} questions answered)"
            )

            return {
                "document_name": document_name,
                "validations": validations,
                "stats": stats,
            }

        finally:
            await self.server_client.close()

    async def _validate_question(
        self, question_data: dict[str, Any], source_document: str, depth: int = 0
    ) -> dict[str, Any]:
        """Validate if question has been answered with recursive verification.

        Args:
            question_data: Question dict from extractor
            source_document: Original question document name
            depth: Current recursion depth

        Returns:
            Validation result dict
        """
        question_text = question_data.get("question_text", "")
        question_type = question_data.get("type", "unknown")
        context = question_data.get("context", "")

        # Skip administrative questions if they're low priority
        if question_type == "administrative":
            logger.debug(f"Skipping administrative question: {question_text[:50]}...")
            return {
                "question": question_text,
                "question_type": question_type,
                "source_document": source_document,
                "answered": False,
                "confidence": 0.0,
                "validation_status": "skipped_administrative",
                "evidence": [],
            }

        # Search RAG for potential answers
        rag_results = await self._search_for_answers(question_text, context)

        if not rag_results:
            return {
                "question": question_text,
                "question_type": question_type,
                "source_document": source_document,
                "answered": False,
                "confidence": 0.0,
                "validation_status": "no_rag_results",
                "evidence": [],
            }

        # Verify answer validity with LLM
        verification = await self._verify_answer_validity(
            question_text, question_type, context, rag_results
        )

        # Recursive verification if answer is partial
        if (
            verification.get("completeness") == "partial"
            and depth < self.max_recursion_depth
        ):
            logger.info(f"Partial answer detected, recursing (depth={depth+1})")
            missing_info = verification.get("missing_info", [])
            refined_query = f"{question_text} - specifically: {', '.join(missing_info)}"

            # Recursive call with refined query
            refined_question = {**question_data, "question_text": refined_query}
            refined_validation = await self._validate_question(
                refined_question, source_document, depth + 1
            )

            # Merge evidence
            verification["evidence"].extend(refined_validation.get("evidence", []))
            if refined_validation.get("answered"):
                verification["completeness"] = "complete"
                verification["confidence"] = max(
                    verification["confidence"], refined_validation["confidence"]
                )

        return {
            "question": question_text,
            "question_type": question_type,
            "source_document": source_document,
            "context": context,
            "answered": verification.get("completeness") == "complete",
            "confidence": verification.get("confidence", 0.0),
            "completeness": verification.get("completeness", "incomplete"),
            "validation_status": "validated",
            "evidence": verification.get("evidence", []),
            "summary": verification.get("summary", ""),
            "missing_info": verification.get("missing_info", []),
        }

    async def _search_for_answers(
        self, question_text: str, context: str
    ) -> list[dict[str, Any]]:
        """Search RAG corpus for potential answers.

        Args:
            question_text: FDA question
            context: Question context/section

        Returns:
            List of RAG result chunks
        """
        if not self.database:
            logger.error("No database configured")
            return []

        try:
            # Enhance query with context
            query = f"{context}: {question_text}" if context else question_text

            results = await self.server_client.rag_search(
                namespace=self.namespace,
                project=self.project,
                database=self.database,
                query=query,
                top_k=self.top_k,
                retrieval_strategy=self.retrieval_strategy,
            )

            return results

        except Exception as e:
            logger.error(f"RAG search failed: {e}", exc_info=True)
            return []

    async def _verify_answer_validity(
        self,
        question_text: str,
        question_type: str,
        context: str,
        rag_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Verify if RAG results actually answer the question.

        Args:
            question_text: FDA question
            question_type: Question classification
            context: Question context
            rag_results: Retrieved chunks

        Returns:
            Verification result dict
        """
        system_prompt = """Validate if retrieved documents ACTUALLY answer the FDA question.

Rules:
1. Must DIRECTLY address the question (not just related content)
2. Must be EXPLICIT (not vague)
3. Completeness: "complete", "partial", or "incomplete"

Return JSON:
{
  "completeness": "complete|partial|incomplete",
  "confidence": 0.0-1.0,
  "evidence": [{document, excerpt}],
  "missing_info": ["what's missing"],
  "summary": "brief explanation"
}"""

        # Build context from RAG results (limit to 3 chunks, 400 chars each for speed)
        rag_context = "\n\n".join(
            [
                f"[Document: {r.get('metadata', {}).get('source', 'unknown')}]\n{r.get('content', '')[:400]}"
                for r in rag_results[:3]
            ]
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""Question Type: {question_type}
Question Context: {context}
Question: {question_text}

Retrieved Documents:
{rag_context}

Validate if these documents answer the question.""",
            },
        ]

        try:
            response = await self.server_client.chat_completion(
                namespace=self.namespace,
                project=self.project,
                messages=messages,
                model=self.model_name,
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse JSON
            content_stripped = content.strip()
            if content_stripped.startswith("{") or content_stripped.startswith("["):
                try:
                    return json.loads(content_stripped)
                except json.JSONDecodeError:
                    pass

            # Fallback
            return {
                "completeness": "incomplete",
                "confidence": 0.0,
                "evidence": [],
                "summary": "Failed to parse LLM response",
            }

        except Exception as e:
            logger.error(f"Answer verification failed: {e}", exc_info=True)
            return {
                "completeness": "incomplete",
                "confidence": 0.0,
                "evidence": [],
                "summary": f"Error: {str(e)}",
            }
