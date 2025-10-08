"""Report Generator Agent.

This agent generates formatted reports from structured data.
Designed for creating final analysis reports from validation results.
"""

from __future__ import annotations

import json
from typing import Any

from agents.base_agent import BaseAgent
from agents.providers import get_provider
from config.datamodel import LlamaFarmConfig, Model, Runtime, PromptFormat
from core.logging import FastAPIStructLogger

logger = FastAPIStructLogger(__name__)


class ReportGeneratorAgent(BaseAgent):
    """Agent for generating formatted reports from data.

    This agent:
    - Takes structured data as input
    - Formats it according to specified template
    - Supports multiple output formats (JSON, Markdown, HTML)
    - Can aggregate statistics
    """

    AGENT_TYPE = "report_generator"

    def __init__(
        self,
        agent_config: dict[str, Any],
        project_config: LlamaFarmConfig,
        project_dir: str,
    ):
        """Initialize ReportGeneratorAgent.

        Agent config fields:
        - format: Output format (json, markdown, html)
        - template: Optional template file path
        - include_statistics: Whether to include summary statistics
        - group_by: Fields to group results by
        - system_prompt: Custom system prompt (optional)
        """
        super().__init__(agent_config, project_config, project_dir)

        # Agent-specific config
        config = agent_config.get("config", {})
        self.output_format = config.get("format", "json")
        self.template_path = config.get("template")
        self.include_statistics = config.get("include_statistics", True)
        self.group_by = config.get("group_by", [])
        self.custom_system_prompt = agent_config.get("system_prompt")

        # Initialize LLM client (for narrative generation if needed)
        self._init_client()

    def _init_client(self):
        """Initialize LLM client for narrative generation."""
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
            prompt_format=self.model_config.prompt_format or PromptFormat.unstructured,
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
        """Generate formatted report from input data.

        Args:
            input_data: Structured data to generate report from
            **kwargs: Additional parameters

        Returns:
            Generated report in specified format
        """
        logger.info(
            "ReportGeneratorAgent starting",
            agent_name=self.name,
            output_format=self.output_format,
        )

        # Generate report based on format
        if self.output_format == "json":
            report = await self._generate_json_report(input_data)
        elif self.output_format == "markdown":
            report = await self._generate_markdown_report(input_data)
        elif self.output_format == "html":
            report = await self._generate_html_report(input_data)
        else:
            raise ValueError(f"Unsupported output format: {self.output_format}")

        logger.info(
            "ReportGeneratorAgent completed",
            agent_name=self.name,
            output_format=self.output_format,
        )

        return report

    async def _generate_json_report(self, input_data: Any) -> dict[str, Any]:
        """Generate JSON report with statistics.

        Args:
            input_data: Input data

        Returns:
            JSON report dict
        """
        report = {"report_type": "analysis", "data": input_data}

        # Add statistics if requested
        if self.include_statistics:
            report["statistics"] = self._calculate_statistics(input_data)

        # Add metadata
        report["metadata"] = {
            "agent": self.name,
            "format": "json",
            "generated_by": "ReportGeneratorAgent",
        }

        return report

    async def _generate_markdown_report(self, input_data: Any) -> str:
        """Generate Markdown report.

        Args:
            input_data: Input data

        Returns:
            Markdown formatted report
        """
        lines = []

        # Title
        lines.append("# Analysis Report\n")

        # Statistics section
        if self.include_statistics:
            stats = self._calculate_statistics(input_data)
            lines.append("## Summary Statistics\n")

            for key, value in stats.items():
                lines.append(f"- **{key}**: {value}")

            lines.append("")

        # Data section
        lines.append("## Detailed Results\n")

        # Format data
        if isinstance(input_data, dict):
            # Check for common structures
            if "validations" in input_data:
                lines.append(self._format_validations_markdown(input_data["validations"]))
            elif "documents" in input_data:
                lines.append(self._format_documents_markdown(input_data["documents"]))
            else:
                # Generic dict formatting
                lines.append("```json")
                lines.append(json.dumps(input_data, indent=2))
                lines.append("```")

        lines.append("\n---\n")
        lines.append(f"*Generated by {self.name}*")

        return "\n".join(lines)

    async def _generate_html_report(self, input_data: Any) -> str:
        """Generate HTML report.

        Args:
            input_data: Input data

        Returns:
            HTML formatted report
        """
        # For now, wrap markdown in HTML
        markdown_report = await self._generate_markdown_report(input_data)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ccc; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 4px; }}
        .stats {{ background: #e8f4f8; padding: 15px; border-radius: 4px; }}
    </style>
</head>
<body>
    <pre>{markdown_report}</pre>
</body>
</html>"""

        return html

    def _calculate_statistics(self, input_data: Any) -> dict[str, Any]:
        """Calculate summary statistics from data.

        Args:
            input_data: Input data

        Returns:
            Statistics dict
        """
        stats: dict[str, Any] = {}

        # Handle validation results
        if isinstance(input_data, dict) and "validations" in input_data:
            validations = input_data["validations"]
            stats["total_validations"] = len(validations)
            stats["answered"] = sum(1 for v in validations if v.get("answered", False))
            stats["unanswered"] = stats["total_validations"] - stats["answered"]

            # Average confidence
            confidences = [v.get("confidence", 0.0) for v in validations]
            stats["average_confidence"] = (
                sum(confidences) / len(confidences) if confidences else 0.0
            )

        # Handle document results
        elif isinstance(input_data, dict) and "documents" in input_data:
            docs = input_data["documents"]
            stats["total_documents"] = len(docs)

        # Generic stats
        else:
            stats["data_type"] = type(input_data).__name__

        return stats

    def _format_validations_markdown(self, validations: list[dict[str, Any]]) -> str:
        """Format validation results as markdown.

        Args:
            validations: List of validation results

        Returns:
            Markdown formatted string
        """
        lines = []

        # Group by answered status if requested
        if "answered" in self.group_by or "status" in self.group_by:
            answered = [v for v in validations if v.get("answered", False)]
            unanswered = [v for v in validations if not v.get("answered", False)]

            lines.append("### Answered Questions\n")
            for v in answered:
                lines.append(f"- **Question**: {v.get('question', 'N/A')}")
                lines.append(f"  - Confidence: {v.get('confidence', 0.0):.2f}")
                lines.append(f"  - Summary: {v.get('summary', 'N/A')}\n")

            lines.append("### Unanswered Questions\n")
            for v in unanswered:
                lines.append(f"- **Question**: {v.get('question', 'N/A')}\n")

        else:
            # Flat list
            for v in validations:
                status = "✓ Answered" if v.get("answered", False) else "✗ Unanswered"
                lines.append(f"- {status}: {v.get('question', 'N/A')}")
                lines.append(f"  - Confidence: {v.get('confidence', 0.0):.2f}\n")

        return "\n".join(lines)

    def _format_documents_markdown(self, documents: list[dict[str, Any]]) -> str:
        """Format document results as markdown.

        Args:
            documents: List of document results

        Returns:
            Markdown formatted string
        """
        lines = []

        for doc in documents:
            source = doc.get("source", "Unknown")
            lines.append(f"### {source}\n")

            if "extracted_data" in doc:
                lines.append("```json")
                lines.append(json.dumps(doc["extracted_data"], indent=2))
                lines.append("```\n")

        return "\n".join(lines)

    def _default_system_prompt(self) -> str:
        """Get default system prompt for report generation."""
        return """You are a report generation expert. Create clear, well-structured reports from the provided data. Focus on readability and actionable insights."""
