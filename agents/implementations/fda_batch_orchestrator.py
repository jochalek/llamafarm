"""FDA Batch Orchestrator Agent.

This agent orchestrates batch processing of 500+ FDA documents.
Manages progress tracking, error handling, and report generation.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from agents.core.base_agent import BaseAgent
from agents.core.registry import AgentRegistry

logger = logging.getLogger(__name__)


class FDABatchOrchestratorAgent(BaseAgent):
    """Agent for batch processing FDA correspondence at scale.

    This agent:
    - Processes 500+ documents in batches
    - Tracks progress and handles failures
    - Coordinates question extraction and answer validation
    - Generates comprehensive reports with statistics
    """

    AGENT_TYPE = "fda_batch_orchestrator"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: dict[str, Any],
        namespace: str,
        project: str,
        server_url: str = "http://localhost:8000",
    ):
        """Initialize FDABatchOrchestratorAgent.

        Agent config fields:
        - batch_size: Documents per batch (default 10)
        - output_path: Where to save progress and reports
        - resume_on_failure: Continue from last checkpoint (default True)
        - extractor_config: Config for question extractor agent
        - validator_config: Config for answer validator agent
        """
        super().__init__(agent_config, project_config, namespace, project, server_url)

        # Agent-specific config
        self.batch_size = self.config.get("batch_size", 10)
        self.output_path = Path(self.config.get("output_path", "/tmp/fda_batch"))
        self.resume_on_failure = self.config.get("resume_on_failure", True)
        self.extractor_config = self.config.get("extractor_config", {})
        self.validator_config = self.config.get("validator_config", {})

        # Ensure output directory exists
        self.output_path.mkdir(parents=True, exist_ok=True)

        # Progress tracking
        self.state_file = self.output_path / "batch_state.json"
        self.stop_signal_file = self.output_path / "STOP_BATCH"

    async def run(self, input_data: Any, **kwargs) -> Any:
        """Process batch of FDA documents.

        Args:
            input_data: Dict with:
                - dataset_name: Dataset containing FDA documents
                - documents: List of {hash, name} dicts
                OR
                - batch_id: Resume existing batch
            **kwargs: Additional parameters

        Returns:
            Dict with batch results and final report
        """
        logger.info(f"FDABatchOrchestrator starting: {self.name}")

        batch_id = input_data.get("batch_id")
        documents = input_data.get("documents", [])
        resume = input_data.get("resume", False)

        # Clear stop signal if resuming
        if resume and self.stop_signal_file.exists():
            self.stop_signal_file.unlink()
            logger.info("Cleared stop signal, resuming batch processing")

        # Resume or start new batch
        if resume or (batch_id and self.resume_on_failure):
            # Try to load existing state
            if self.state_file.exists():
                state = self._load_state_from_file()
                logger.info(f"Resuming batch {state['batch_id']}: {state['processed_documents']}/{state['total_documents']} completed")
            else:
                logger.warning("No state file found, starting new batch")
                batch_id = f"batch_{int(time.time())}"
                state = self._init_state(batch_id, documents)
        else:
            batch_id = batch_id or f"batch_{int(time.time())}"
            state = self._init_state(batch_id, documents)

        try:
            # Process documents in batches
            results = await self._process_batches(state)

            # Generate final report
            report = self._generate_report(results, state)

            # Save report
            report_file = self.output_path / f"{batch_id}_report.json"
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)

            logger.info(f"FDABatchOrchestrator completed: {batch_id}")

            return {
                "batch_id": batch_id,
                "status": "completed",
                "report": report,
                "report_file": str(report_file),
            }

        except Exception as e:
            logger.error(f"Batch processing failed: {e}", exc_info=True)
            self._save_state(state)
            raise

    def _init_state(
        self, batch_id: str, documents: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Initialize batch processing state.

        Args:
            batch_id: Unique batch identifier
            documents: List of documents to process

        Returns:
            State dict
        """
        return {
            "batch_id": batch_id,
            "total_documents": len(documents),
            "processed_documents": 0,
            "documents": documents,
            "results": [],
            "started_at": time.time(),
            "updated_at": time.time(),
            "status": "running",
        }

    def _load_state_from_file(self) -> dict[str, Any]:
        """Load batch state from checkpoint file.

        Returns:
            State dict
        """
        if not self.state_file.exists():
            raise ValueError("No state file found")

        with open(self.state_file) as f:
            state = json.load(f)

        return state

    def _load_state(self, batch_id: str) -> dict[str, Any]:
        """Load batch state from checkpoint.

        Args:
            batch_id: Batch identifier

        Returns:
            State dict
        """
        state = self._load_state_from_file()

        if state["batch_id"] != batch_id:
            raise ValueError(f"State file batch ID mismatch: {state['batch_id']} != {batch_id}")

        logger.info(
            f"Resuming batch {batch_id}: "
            f"{state['processed_documents']}/{state['total_documents']} completed"
        )

        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        """Save batch state checkpoint.

        Args:
            state: Current state
        """
        state["updated_at"] = time.time()

        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _save_interim_report(self, result: dict[str, Any], state: dict[str, Any]) -> None:
        """Save interim report after each document.

        Args:
            result: Document processing result
            state: Current batch state
        """
        doc_name = result.get("document_name", "unknown")
        doc_id = state["processed_documents"]

        # Create interim report with running totals
        interim_report = {
            "document_number": doc_id,
            "total_documents": state["total_documents"],
            "document_name": doc_name,
            "questions_extracted": len(result.get("questions", [])),
            "questions_answered": result.get("stats", {}).get("answered", 0),
            "questions_unanswered": result.get("stats", {}).get("unanswered", 0),
            "questions": result.get("questions", []),
            "validations": result.get("validations", []),
            "running_totals": {
                "documents_processed": doc_id,
                "total_questions": sum(len(r.get("questions", [])) for r in state["results"]),
                "total_answered": sum(r.get("stats", {}).get("answered", 0) for r in state["results"]),
                "total_unanswered": sum(r.get("stats", {}).get("unanswered", 0) for r in state["results"]),
            }
        }

        # Save interim report
        interim_file = self.output_path / f"{state['batch_id']}_doc_{doc_id:03d}_{doc_name.replace('/', '_')}.json"
        with open(interim_file, "w") as f:
            json.dump(interim_report, f, indent=2)

        logger.info(f"Saved interim report: {interim_file}")

    async def _process_batches(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Process all documents in batches.

        Args:
            state: Batch state

        Returns:
            List of document results
        """
        documents = state["documents"]
        start_idx = state["processed_documents"]

        for i in range(start_idx, len(documents), self.batch_size):
            batch = documents[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1

            logger.info(
                f"Processing batch {batch_num}: "
                f"documents {i+1}-{min(i+self.batch_size, len(documents))}"
            )

            # Process each document in batch
            for doc in batch:
                # Check for stop signal
                if self.stop_signal_file.exists():
                    logger.warning("Stop signal detected! Saving state and exiting...")
                    state["status"] = "stopped"
                    self._save_state(state)
                    return state["results"]

                try:
                    result = await self._process_document(doc)
                    state["results"].append(result)
                    state["processed_documents"] += 1

                except Exception as e:
                    logger.error(f"Document processing failed: {doc.get('name')}: {e}")
                    state["results"].append(
                        {
                            "document_name": doc.get("name"),
                            "document_hash": doc.get("hash"),
                            "error": str(e),
                            "questions": [],
                            "validations": [],
                        }
                    )
                    state["processed_documents"] += 1

                # Save progress after each document
                self._save_state(state)

                # Save interim document report
                self._save_interim_report(result, state)

        return state["results"]

    async def _process_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Process single document through extraction and validation pipeline.

        Args:
            doc: Document dict with hash and name

        Returns:
            Document result dict
        """
        doc_name = doc.get("name", "unknown")
        doc_hash = doc.get("hash")

        logger.info(f"Processing document: {doc_name}")

        # Step 1: Extract questions
        extractor_result = await self._run_extractor(doc_hash, doc_name)

        questions = extractor_result.get("questions", [])

        # Step 2: Validate answers (only for critical questions)
        critical_questions = [q for q in questions if q.get("type") == "critical"]

        if critical_questions:
            validator_result = await self._run_validator(critical_questions, doc_name)
            validations = validator_result.get("validations", [])
        else:
            validations = []

        return {
            "document_name": doc_name,
            "document_hash": doc_hash,
            "questions": questions,
            "validations": validations,
            "stats": {
                "total_questions": len(questions),
                "critical_questions": len(critical_questions),
                "administrative_questions": len(
                    [q for q in questions if q.get("type") == "administrative"]
                ),
                "answered": len([v for v in validations if v.get("answered")]),
                "unanswered": len([v for v in validations if not v.get("answered")]),
            },
        }

    async def _run_extractor(self, doc_hash: str, doc_name: str) -> dict[str, Any]:
        """Run question extractor agent.

        Args:
            doc_hash: Document hash
            doc_name: Document name

        Returns:
            Extractor result
        """
        # Create extractor agent instance
        extractor = AgentRegistry.create_agent(
            agent_config={
                "name": "temp_extractor",
                "type": "fda_question_extractor",
                "config": self.extractor_config,
                "system_prompt": "",
                "model": self.model_name,
            },
            project_config=self.project_config,
            namespace=self.namespace,
            project=self.project,
            server_url=self.server_url,
        )

        return await extractor.run({"document_hash": doc_hash, "document_name": doc_name})

    async def _run_validator(
        self, questions: list[dict[str, Any]], doc_name: str
    ) -> dict[str, Any]:
        """Run answer validator agent.

        Args:
            questions: Extracted questions
            doc_name: Source document name

        Returns:
            Validator result
        """
        # Create validator agent instance
        validator = AgentRegistry.create_agent(
            agent_config={
                "name": "temp_validator",
                "type": "fda_answer_validator",
                "config": self.validator_config,
                "system_prompt": "",
                "model": self.model_name,
            },
            project_config=self.project_config,
            namespace=self.namespace,
            project=self.project,
            server_url=self.server_url,
        )

        return await validator.run({"questions": questions, "document_name": doc_name})

    def _generate_report(
        self, results: list[dict[str, Any]], state: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate comprehensive batch processing report.

        Args:
            results: All document results
            state: Batch state

        Returns:
            Report dict
        """
        # Aggregate statistics
        total_docs = len(results)
        total_questions = sum(r.get("stats", {}).get("total_questions", 0) for r in results)
        total_critical = sum(r.get("stats", {}).get("critical_questions", 0) for r in results)
        total_administrative = sum(
            r.get("stats", {}).get("administrative_questions", 0) for r in results
        )
        total_answered = sum(r.get("stats", {}).get("answered", 0) for r in results)
        total_unanswered = sum(r.get("stats", {}).get("unanswered", 0) for r in results)

        # Collect all questions and validations
        all_questions = []
        all_validations = []

        for result in results:
            doc_name = result.get("document_name")

            for q in result.get("questions", []):
                all_questions.append({**q, "source_document": doc_name})

            for v in result.get("validations", []):
                all_validations.append(v)

        # Group unanswered questions
        unanswered = [v for v in all_validations if not v.get("answered")]

        # Calculate processing time
        duration_seconds = time.time() - state["started_at"]
        duration_minutes = duration_seconds / 60

        return {
            "batch_id": state["batch_id"],
            "summary": {
                "total_documents": total_docs,
                "total_questions": total_questions,
                "critical_questions": total_critical,
                "administrative_questions": total_administrative,
                "answered_questions": total_answered,
                "unanswered_questions": total_unanswered,
                "answer_rate": (
                    round(total_answered / total_critical * 100, 1) if total_critical > 0 else 0
                ),
                "processing_time_minutes": round(duration_minutes, 1),
            },
            "all_questions": all_questions,
            "answered_questions": [v for v in all_validations if v.get("answered")],
            "unanswered_questions": unanswered,
            "document_details": results,
        }
