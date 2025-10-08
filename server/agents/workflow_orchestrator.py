"""Workflow Orchestrator Agent.

This agent orchestrates multi-step workflows by chaining other agents together.
Designed for complex tasks like the FDA analysis workflow.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from config.datamodel import LlamaFarmConfig
from core.logging import FastAPIStructLogger
from services.agent_service import AgentService

logger = FastAPIStructLogger(__name__)


class WorkflowOrchestratorAgent(BaseAgent):
    """Agent for orchestrating multi-agent workflows.

    This agent:
    - Chains multiple agents together
    - Manages data flow between agents
    - Supports batch processing
    - Handles parallel execution where possible
    """

    AGENT_TYPE = "workflow_orchestrator"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: LlamaFarmConfig,
        project_dir: str,
    ):
        """Initialize WorkflowOrchestratorAgent.

        Agent config fields:
        - workflow: List of workflow steps
          Each step: {agent: str, input_field: str, output_field: str}
        - batch_size: Number of items to process per batch
        - parallel_workers: Number of parallel workers for batch processing
        """
        super().__init__(agent_config, project_config, project_dir)

        # Agent-specific config
        config = agent_config.get("config", {})
        self.workflow_steps = config.get("workflow", [])
        self.batch_size = config.get("batch_size", 10)
        self.parallel_workers = config.get("parallel_workers", 3)

        # Validate workflow
        if not self.workflow_steps:
            raise ValueError(f"Workflow orchestrator '{self.name}' has no workflow steps defined")

        logger.debug(
            "Initialized workflow orchestrator",
            agent_name=self.name,
            num_steps=len(self.workflow_steps),
            batch_size=self.batch_size,
            parallel_workers=self.parallel_workers,
        )

    async def run(self, input_data: Any, **kwargs) -> Any:
        """Execute the workflow.

        Args:
            input_data: Initial input for the workflow
            **kwargs: Additional parameters

        Returns:
            Final workflow output
        """
        logger.info(
            "WorkflowOrchestratorAgent starting",
            agent_name=self.name,
            num_steps=len(self.workflow_steps),
        )

        # Initialize workflow context
        context = {"input": input_data}

        # Execute each step in sequence
        for step_idx, step in enumerate(self.workflow_steps, 1):
            agent_name = step.get("agent")
            input_field = step.get("input_field", "input")
            output_field = step.get("output_field", f"step_{step_idx}_output")

            logger.info(
                "Executing workflow step",
                agent_name=self.name,
                step=step_idx,
                step_agent=agent_name,
                input_field=input_field,
                output_field=output_field,
            )

            # Get input data for this step
            step_input = context.get(input_field)
            if step_input is None:
                raise ValueError(
                    f"Step {step_idx}: input field '{input_field}' not found in context. "
                    f"Available fields: {list(context.keys())}"
                )

            # Execute the agent
            step_output = await self._execute_step(agent_name, step_input, step)

            # Store output in context
            context[output_field] = step_output

            logger.info(
                "Workflow step completed",
                agent_name=self.name,
                step=step_idx,
                step_agent=agent_name,
                output_field=output_field,
            )

        # Get final output
        final_step = self.workflow_steps[-1]
        final_output_field = final_step.get("output_field", f"step_{len(self.workflow_steps)}_output")
        final_output = context.get(final_output_field)

        logger.info(
            "WorkflowOrchestratorAgent completed",
            agent_name=self.name,
            num_steps=len(self.workflow_steps),
        )

        return final_output

    async def _execute_step(
        self, agent_name: str, step_input: Any, step_config: dict[str, Any]
    ) -> Any:
        """Execute a single workflow step.

        Args:
            agent_name: Name of the agent to execute
            step_input: Input data for this step
            step_config: Step configuration

        Returns:
            Step output
        """
        # Check if this is a batch processing step
        if isinstance(step_input, dict) and "document_directory" in step_input:
            return await self._execute_batch_step(agent_name, step_input, step_config)

        # Regular single execution
        result = await AgentService.run_agent(
            self.project_config,
            agent_name,
            self.project_dir,
            step_input,
        )

        return result

    async def _execute_batch_step(
        self, agent_name: str, batch_input: dict[str, Any], step_config: dict[str, Any]
    ) -> Any:
        """Execute a step with batch processing.

        Args:
            agent_name: Name of the agent to execute
            batch_input: Batch input with document_directory, file_pattern, etc.
            step_config: Step configuration

        Returns:
            Aggregated batch results
        """
        # Discover files
        doc_dir = Path(batch_input["document_directory"])
        pattern = batch_input.get("file_pattern", "*.pdf")
        all_files = list(doc_dir.glob(pattern))

        logger.info(
            "Batch processing",
            agent_name=self.name,
            step_agent=agent_name,
            total_files=len(all_files),
            batch_size=self.batch_size,
        )

        # Create batches
        batches = [
            all_files[i : i + self.batch_size]
            for i in range(0, len(all_files), self.batch_size)
        ]

        # Process batches in parallel (with semaphore to limit concurrency)
        semaphore = asyncio.Semaphore(self.parallel_workers)
        all_results = []

        async def process_batch_with_limit(batch_files):
            async with semaphore:
                return await self._process_batch(agent_name, batch_files)

        # Execute all batches
        batch_results = await asyncio.gather(*[
            process_batch_with_limit(batch) for batch in batches
        ])

        # Aggregate results
        for batch_result in batch_results:
            if isinstance(batch_result, dict) and "documents" in batch_result:
                all_results.extend(batch_result["documents"])
            else:
                all_results.append(batch_result)

        logger.info(
            "Batch processing completed",
            agent_name=self.name,
            step_agent=agent_name,
            total_files=len(all_files),
            results_count=len(all_results),
        )

        return {"documents": all_results}

    async def _process_batch(
        self, agent_name: str, batch_files: list[Path]
    ) -> Any:
        """Process a single batch of files.

        Args:
            agent_name: Name of the agent to execute
            batch_files: List of file paths to process

        Returns:
            Batch results
        """
        logger.debug(
            "Processing batch",
            agent_name=self.name,
            step_agent=agent_name,
            batch_size=len(batch_files),
        )

        # Prepare batch input
        batch_input = {"files": [str(f) for f in batch_files]}

        # Execute agent on batch
        result = await AgentService.run_agent(
            self.project_config,
            agent_name,
            self.project_dir,
            batch_input,
        )

        return result

    def get_workflow_info(self) -> dict[str, Any]:
        """Get information about the workflow.

        Returns:
            Workflow information dict
        """
        return {
            "agent_name": self.name,
            "num_steps": len(self.workflow_steps),
            "steps": [
                {
                    "step": i + 1,
                    "agent": step.get("agent"),
                    "input_field": step.get("input_field", "input"),
                    "output_field": step.get("output_field", f"step_{i+1}_output"),
                }
                for i, step in enumerate(self.workflow_steps)
            ],
            "batch_size": self.batch_size,
            "parallel_workers": self.parallel_workers,
        }
