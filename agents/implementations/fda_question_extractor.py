"""FDA Question Extractor Agent.

This agent analyzes FDA correspondence and extracts questions/requests with classification.
Distinguishes between critical regulatory questions and informal administrative questions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.core.base_agent import BaseAgent
from agents.services.server_client import ServerClient

logger = logging.getLogger(__name__)


class FDAQuestionExtractorAgent(BaseAgent):
    """Agent for extracting and classifying FDA questions from correspondence.

    This agent:
    - Reads FDA correspondence (PDFs, emails, meeting minutes)
    - Identifies FDA questions vs. non-questions (headers, references, etc.)
    - Classifies questions by type (critical regulatory vs. administrative)
    - Extracts context (page number, section, document type)
    """

    AGENT_TYPE = "fda_question_extractor"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: dict[str, Any],
        namespace: str,
        project: str,
        server_url: str = "http://localhost:8000",
    ):
        """Initialize FDAQuestionExtractorAgent.

        Agent config fields:
        - database: RAG database with full FDA documents
        - min_confidence: Minimum confidence threshold (default 0.7)
        - extract_informal: Whether to extract administrative questions (default True)
        """
        super().__init__(agent_config, project_config, namespace, project, server_url)

        # Agent-specific config
        self.database = self.config.get("database")
        self.min_confidence = self.config.get("min_confidence", 0.85)  # Stricter filtering for fewer false positives
        self.extract_informal = self.config.get("extract_informal", True)

        # Initialize server client
        self.server_client = ServerClient(server_url)

    async def run(self, input_data: Any, **kwargs) -> Any:
        """Extract FDA questions from document.

        Args:
            input_data: Dict with:
                - document_hash: File hash to analyze
                - document_name: Original filename
            **kwargs: Additional parameters

        Returns:
            Dict with extracted questions, stats, and metadata
        """
        logger.info(f"FDAQuestionExtractor starting: {self.name}")

        try:
            document_hash = input_data.get("document_hash")
            document_name = input_data.get("document_name", "unknown")

            # Get document chunks from RAG
            chunks = await self._get_document_chunks(document_hash)

            if not chunks:
                return {
                    "document_name": document_name,
                    "document_hash": document_hash,
                    "questions": [],
                    "stats": {"total": 0, "critical": 0, "administrative": 0},
                    "error": "Document not found in RAG database",
                }

            # Process each chunk individually to extract questions
            all_questions = []
            for i, chunk in enumerate(chunks):
                chunk_content = chunk.get("content", "")
                chunk_metadata = chunk.get("metadata", {})
                page = chunk_metadata.get("page", i + 1)

                logger.info(f"Processing chunk {i+1}/{len(chunks)} from document {document_hash[:12]}...")

                # Extract questions from this chunk
                chunk_questions = await self._extract_questions_from_chunk(
                    chunk_content, document_name, page
                )
                all_questions.extend(chunk_questions)

            # Deduplicate questions (same question found in multiple chunks)
            questions = self._deduplicate_questions(all_questions)

            # Filter by confidence
            filtered_questions = [
                q for q in questions if q.get("confidence", 0) >= self.min_confidence
            ]

            # Calculate stats
            stats = {
                "total": len(filtered_questions),
                "critical": len([q for q in filtered_questions if q.get("type") == "critical"]),
                "administrative": len(
                    [q for q in filtered_questions if q.get("type") == "administrative"]
                ),
                "filtered_out": len(questions) - len(filtered_questions),
            }

            logger.info(
                f"FDAQuestionExtractor completed: {self.name} "
                f"(extracted {stats['total']} questions from {document_name})"
            )

            return {
                "document_name": document_name,
                "document_hash": document_hash,
                "questions": filtered_questions,
                "stats": stats,
            }

        finally:
            await self.server_client.close()

    async def _get_document_chunks(self, document_hash: str) -> list[dict]:
        """Retrieve document chunks from RAG database.

        Args:
            document_hash: File hash

        Returns:
            List of chunk dicts with content and metadata
        """
        if not self.database:
            logger.error("No database configured")
            return []

        try:
            # Retrieve ALL chunks for this document by filtering on file_hash metadata
            # Use a generic query but retrieve many results to get all chunks
            results = await self.server_client.rag_search(
                namespace=self.namespace,
                project=self.project,
                database=self.database,
                query="document content",  # Generic query
                top_k=100,  # Get many chunks
            )

            if not results:
                logger.warning(f"No content found for document {document_hash[:12]}...")
                return []

            # Filter results to only those matching this document hash
            # Check both 'file_hash' and 'source' metadata fields
            matching_chunks = []
            for result in results:
                metadata = result.get("metadata", {})
                result_hash = metadata.get("file_hash") or metadata.get("source", "")

                # Check if this chunk belongs to our document
                if document_hash in result_hash or result_hash in document_hash:
                    matching_chunks.append(result)

            if not matching_chunks:
                # Fallback: if no metadata match, just use first result
                logger.warning(f"No metadata match for {document_hash[:12]}, using first result")
                matching_chunks = [results[0]] if results else []

            logger.info(f"Retrieved {len(matching_chunks)} chunks for document {document_hash[:12]}...")

            return matching_chunks

        except Exception as e:
            logger.error(f"Failed to retrieve document: {e}", exc_info=True)
            return []

    def _deduplicate_questions(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate questions using similarity matching.

        Args:
            questions: List of question dicts

        Returns:
            Deduplicated list
        """
        if not questions:
            return []

        unique_questions = []
        seen_texts = set()

        for q in questions:
            text = q.get("question_text", "").lower().strip()

            # Skip very long questions (likely extracted full paragraphs)
            if len(text) > 600:
                logger.warning(f"Skipping overly long question ({len(text)} chars): {text[:80]}...")
                continue

            # Improved deduplication: normalize whitespace and use longer key
            normalized = " ".join(text.split())  # Normalize whitespace
            text_key = normalized[:150]  # Longer key for better matching

            if text_key not in seen_texts:
                seen_texts.add(text_key)
                unique_questions.append(q)
            else:
                logger.debug(f"Skipping duplicate question: {text[:80]}")

        logger.info(f"Deduplicated {len(questions)} → {len(unique_questions)} questions")
        return unique_questions

    async def _extract_questions_from_chunk(
        self, chunk_content: str, document_name: str, page: int = None
    ) -> list[dict[str, Any]]:
        """Extract and classify questions from a single document chunk using LLM.

        Args:
            chunk_content: Single chunk of document text
            document_name: Document filename
            page: Page number if available

        Returns:
            List of question dicts
        """
        # Skip if chunk is too short or just boilerplate
        if len(chunk_content.strip()) < 100:
            return []

        system_prompt = """You are an FDA regulatory expert extracting ACTION ITEMS from FDA correspondence.

CRITICAL RULES:
1. ONLY extract items where the FDA is EXPLICITLY REQUESTING ACTION from the company
2. DO NOT extract:
   - Email greetings/signatures/footers
   - Meeting scheduling discussions
   - Clarification questions FROM the company TO the FDA
   - Background information or context
   - Document headers/footers like "This is a representation of an electronic record"
   - General statements without specific action required

FDA ACTION ITEMS typically use phrases like:
- "Please provide..."
- "Submit the following..."
- "The Office requests..."
- "Applicant should include..."
- "FDA recommends..."
- "You are requested to..."
- "Please address the following deficiencies..."

For each question/request:

1. Identify FDA asks (not just grammatical questions):
   - Direct requests ("Please provide X")
   - Directives ("Submit Y by Z date")
   - Recommendations requiring response ("FDA recommends...")
   - Deficiencies to address ("The following deficiencies were identified...")
   - Information requests ("OSI requests that the following items...")

2. Classify the type:
   - "critical": Regulatory requests requiring formal response:
     * Clinical data/studies/analyses
     * Safety or efficacy information
     * Chemistry/manufacturing/controls (CMC)
     * Protocol modifications
     * Deficiency corrections
     * Regulatory pathway requirements

   - "administrative": Procedural/timeline requests:
     * Meeting scheduling
     * Submission deadlines/extensions
     * Clarification requests
     * Timeline confirmations

   - "not_question": Skip these:
     * Headers, footers, letterhead
     * Greetings ("Dear Dr. Smith")
     * Closings ("Sincerely, Karen Boyd")
     * References ("Re: IND 113695")
     * Background information (no ask)

3. Extract details:
   - question_text: Full text of the request/question (include entire statement)
   - context: Topic area (e.g., "Clinical Investigator Information", "Nonclinical Safety", "CMC")
   - page_reference: Page number if identifiable (look for page markers)
   - confidence: 0.0-1.0 score for validity

EXTRACT (Critical regulatory requests):
✓ "OSI requests that you provide a list of all clinical investigators with their addresses"
✓ "Submit virus testing results for all UPB batches manufactured for the US market"
✓ "Please provide stability data at 25°C and 40°C for 12 months"
✓ "You must address the following deficiencies before approval can be granted"
✓ "Provide updated safety data from all ongoing clinical trials"

EXTRACT (Administrative requests):
✓ "Please confirm if you will need an additional 90 days for the submission"
✓ "Submit your request for a Type C meeting by November 15"

DO NOT EXTRACT (these are NOT action items):
✗ "Sure, you can have an extra 90 days to prepare the submission" (FDA's response, no action needed)
✗ "This is a representation of an electronic record that was signed" (document footer)
✗ "Dear Ms. Salyers," (greeting)
✗ "Can you tell me when the 6 month reporting should begin?" (company asking FDA)
✗ "We are requesting two aggregate summary reports per year" (context, not specific action)
✗ "Please provide a detailed description of..." (if this is generic instruction text, not from actual FDA letter)

Return ONLY a JSON array. Each question MUST have these fields:
- question_text: The ACTUAL full text extracted from the document (NOT a placeholder)
- type: MUST be either "critical" or "administrative"
- context: Topic area
- page_reference: Page number if found, or null
- confidence: 0.0 to 1.0

Example format (use REAL extracted text, not these examples):
[
  {
    "question_text": "OSI requests that the applicant provide a list of all clinical investigators...",
    "type": "critical",
    "context": "Clinical Investigator Information",
    "page_reference": "Page 2",
    "confidence": 0.95
  }
]

CRITICAL: Extract the ACTUAL text from the document above. Do NOT return placeholder text or instructions.

If this chunk contains NO FDA action items, return an empty array: []"""

        page_info = f" (Page {page})" if page else ""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Document: {document_name}{page_info}\n\nChunk Content:\n{chunk_content}",
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

            logger.info(f"LLM response content (first 500 chars): {content[:500]}")

            # Parse JSON response
            content_stripped = content.strip()

            # Try to extract JSON from markdown code blocks if present
            if "```json" in content_stripped:
                start = content_stripped.find("```json") + 7
                end = content_stripped.find("```", start)
                if end > start:
                    content_stripped = content_stripped[start:end].strip()
                    logger.info("Extracted JSON from markdown code block")
            elif "```" in content_stripped:
                start = content_stripped.find("```") + 3
                end = content_stripped.find("```", start)
                if end > start:
                    content_stripped = content_stripped[start:end].strip()
                    logger.info("Extracted content from code block")

            if content_stripped.startswith("[") or content_stripped.startswith("{"):
                try:
                    data = json.loads(content_stripped)
                    # Normalize to list
                    if isinstance(data, dict):
                        data = data.get("questions", [data])

                    # Validate and fix 'type' field for each question
                    validated_questions = []

                    # Patterns that indicate this is NOT a real FDA action item
                    skip_patterns = [
                        # Placeholder text from prompt
                        "full text of the fda request",
                        "please provide the complete text",
                        "actual full text extracted",
                        "not a placeholder",
                        "use real extracted text",
                        # Document boilerplate
                        "this is a representation of an electronic record",
                        "department of health and human services",
                        "center for drug evaluation",
                        "food and drug administration",
                        # Greetings/closings
                        "dear dr.",
                        "dear ms.",
                        "dear mr.",
                        "sincerely,",
                        "best regards,",
                        "kind regards,",
                        # Generic/vague requests (likely misidentified)
                        "please provide a detailed description",
                        "please provide an explanation",
                        "describe the changes",
                        "provide information about",
                    ]

                    for q in data:
                        question_text = q.get("question_text", "").lower()

                        # Skip if matches any skip pattern
                        if any(pattern in question_text for pattern in skip_patterns):
                            logger.warning(f"Skipping invalid/generic text: {q.get('question_text', '')[:80]}")
                            continue

                        # Skip very short questions (likely malformed)
                        if len(question_text.strip()) < 30:
                            logger.warning(f"Skipping too-short question: {question_text}")
                            continue

                        # Ensure 'type' field exists
                        if "type" not in q or q["type"] not in ["critical", "administrative"]:
                            # Default to 'critical' if missing or invalid
                            logger.warning(f"Question missing or has invalid 'type' field, defaulting to 'critical': {q.get('question_text', '')[:50]}")
                            q["type"] = "critical"

                        validated_questions.append(q)

                    logger.info(f"Successfully parsed {len(validated_questions)} questions from LLM response")
                    return validated_questions
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM JSON response: {e}")
                    logger.error(f"Content was: {content_stripped[:1000]}")
                    return []

            logger.warning(f"LLM response is not JSON format. Content: {content_stripped[:500]}")
            return []

        except Exception as e:
            logger.error(f"Question extraction failed: {e}", exc_info=True)
            return []
