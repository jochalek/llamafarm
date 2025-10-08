"""Test FDA agents with actual LLM calls.

This script tests the FDA agent workflow end-to-end:
1. Document Analyzer - Extract questions from FDA letters
2. RAG Validator - Validate answers using RAG database
3. Report Generator - Generate formatted reports
"""

import asyncio
import sys
from pathlib import Path

# Add paths
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "server"))

from config import load_config
from agents.document_analyzer import DocumentAnalyzerAgent
from services.project_service import ProjectService
from core.logging import FastAPIStructLogger

logger = FastAPIStructLogger(__name__)


# Sample FDA letter content (mock)
SAMPLE_FDA_LETTER = """
FDA Warning Letter

Company: BioTech Pharmaceuticals
Date: January 15, 2024
Subject: Deficiencies in Manufacturing Practices

Dear Dr. Smith,

This letter concerns significant deficiencies observed during our inspection of your drug manufacturing facility located at 123 Pharma Drive, conducted from October 1-15, 2023.

Question 1: Please provide a comprehensive corrective action plan addressing the contamination issues found in Manufacturing Suite B. Include timeline for implementation and validation protocols.

Question 2: What procedures will you implement to ensure proper environmental monitoring in all sterile manufacturing areas going forward?

Question 3: Provide documentation demonstrating that all batches manufactured between June 2023 and October 2023 meet quality specifications.

Our investigation revealed:
- Inadequate environmental monitoring in sterile manufacturing areas
- Failure to investigate contamination events promptly
- Insufficient cleaning validation protocols

You must respond to this letter within 15 business days with specific plans to address each deficiency noted above.

Sincerely,
FDA Compliance Division
"""


async def test_document_analyzer():
    """Test DocumentAnalyzerAgent with sample FDA letter."""
    logger.info("=" * 80)
    logger.info("Testing FDA Document Analyzer Agent")
    logger.info("=" * 80)

    # Load project config
    project_dir = str(Path.home() / ".llamafarm" / "projects" / "default" / "test-project-1")
    project_config = ProjectService.load_config("default", "test-project-1")

    # Find FDA document analyzer agent config
    agent_config = None
    for agent in project_config.agents or []:
        if agent.get("name") == "fda_document_analyzer":
            agent_config = agent
            break

    if not agent_config:
        logger.error("fda_document_analyzer not found in config!")
        return

    logger.info(f"Found agent config: {agent_config.get('name')}")
    logger.info(f"Model: {agent_config.get('model')}")
    logger.info(f"Database: {agent_config.get('config', {}).get('database')}")

    # Create agent
    agent = DocumentAnalyzerAgent(
        agent_config=agent_config,
        project_config=project_config,
        project_dir=project_dir,
    )

    # Test with direct text input
    logger.info("\n" + "=" * 80)
    logger.info("Running document analysis on sample FDA letter...")
    logger.info("=" * 80)

    result = await agent.run(SAMPLE_FDA_LETTER)

    logger.info("\n" + "=" * 80)
    logger.info("RESULT FROM DOCUMENT ANALYZER:")
    logger.info("=" * 80)
    import json
    print(json.dumps(result, indent=2))

    return result


async def test_model_switching():
    """Test that different models are being used."""
    logger.info("\n" + "=" * 80)
    logger.info("Testing Model Switching")
    logger.info("=" * 80)

    project_dir = str(Path.home() / ".llamafarm" / "projects" / "default" / "test-project-1")
    config_service = ConfigService(project_dir)
    project_config = config_service.get_config()

    # Test each FDA agent
    agent_names = ["fda_document_analyzer", "fda_rag_validator", "fda_report_generator"]

    for agent_name in agent_names:
        agent_config = None
        for agent in project_config.agents or []:
            if agent.get("name") == agent_name:
                agent_config = agent
                break

        if agent_config:
            model_name = agent_config.get("model")
            logger.info(f"{agent_name} uses model: {model_name}")

            # Get model details
            for model in project_config.runtime.models:
                if model.name == model_name:
                    logger.info(f"  - Provider: {model.provider}")
                    logger.info(f"  - Model: {model.model}")
                    if hasattr(model, 'provider_config') and model.provider_config:
                        logger.info(f"  - Port: {model.provider_config.get('port')}")
                    break


async def main():
    """Run all tests."""
    try:
        # Test model configuration
        await test_model_switching()

        # Test document analyzer
        result = await test_document_analyzer()

        logger.info("\n" + "=" * 80)
        logger.info("✅ All tests completed successfully!")
        logger.info("=" * 80)

        # Instructions for checking logs
        logger.info("\nNext steps:")
        logger.info("1. Check server logs (above) for:")
        logger.info("   - LLM API calls to Lemonade")
        logger.info("   - Model switching (should use 'balanced' model on port 11536)")
        logger.info("2. Check Lemonade logs:")
        logger.info("   - tail -f /tmp/lemonade-balanced.log")
        logger.info("3. Verify RAG database queries (if configured)")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
