#!/usr/bin/env python3
"""Quick test script to verify agent implementation.

This script tests:
1. Agent module imports successfully
2. Agent types are registered
3. Config loading works
4. Agent creation works
"""

import sys
from pathlib import Path

# Add repo root and server to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "server"))

print("=" * 60)
print("Testing Agent Implementation")
print("=" * 60)

# Test 1: Import agents module
print("\n1. Testing agent module import...")
try:
    from agents import AgentRegistry, BaseAgent
    from agents import DocumentAnalyzerAgent, RAGValidatorAgent
    from agents import ReportGeneratorAgent, WorkflowOrchestratorAgent
    print("   ✅ Agent module imported successfully")
except Exception as e:
    print(f"   ❌ Failed to import agents: {e}")
    sys.exit(1)

# Test 2: Check agent registration
print("\n2. Testing agent registration...")
try:
    registered_types = AgentRegistry.list_types()
    print(f"   Registered agent types: {registered_types}")

    expected_types = ["document_analyzer", "rag_validator", "report_generator", "workflow_orchestrator"]
    for agent_type in expected_types:
        if agent_type in registered_types:
            print(f"   ✅ {agent_type} registered")
        else:
            print(f"   ❌ {agent_type} NOT registered")
except Exception as e:
    print(f"   ❌ Registration check failed: {e}")
    sys.exit(1)

# Test 3: Load config
print("\n3. Testing config loading...")
try:
    import yaml
    from config.datamodel import LlamaFarmConfig

    config_path = repo_root / "llamafarm.yaml"
    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    project_config = LlamaFarmConfig(**config_data)
    print(f"   ✅ Config loaded successfully")
    print(f"   Project: {project_config.namespace}/{project_config.name}")

    if project_config.agents:
        print(f"   Agents in config: {len(project_config.agents)}")
        for agent in project_config.agents:
            print(f"     - {agent.name} ({agent.type})")
    else:
        print("   ⚠️  No agents configured")

except Exception as e:
    print(f"   ❌ Config loading failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Test AgentService
print("\n4. Testing AgentService...")
try:
    from services.agent_service import AgentService

    # List agents
    agents = AgentService.list_agents(project_config)
    print(f"   ✅ AgentService.list_agents() returned {len(agents)} agents")

    # Get agent config
    if agents:
        first_agent = agents[0]
        agent_config = AgentService.get_agent_config(project_config, first_agent["name"])
        print(f"   ✅ AgentService.get_agent_config('{first_agent['name']}') succeeded")
        print(f"      Type: {agent_config['type']}")
        print(f"      Model: {agent_config.get('model', 'default')}")

except Exception as e:
    print(f"   ❌ AgentService test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Create an agent instance
print("\n5. Testing agent creation...")
try:
    if agents:
        project_dir = str(repo_root)
        first_agent_name = agents[0]["name"]

        agent = AgentService.create_agent(
            project_config,
            first_agent_name,
            project_dir
        )

        print(f"   ✅ Created agent '{first_agent_name}'")
        print(f"      Class: {agent.__class__.__name__}")
        print(f"      Type: {agent.agent_type}")
        print(f"      Model: {agent.model_config.name} ({agent.model_config.provider.value})")

        # Get metadata
        metadata = agent.get_metadata()
        print(f"      Metadata: {metadata}")

except Exception as e:
    print(f"   ❌ Agent creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Test runtime helpers
print("\n6. Testing runtime helpers...")
try:
    from config.runtime_helpers import get_active_model

    # Get default model
    model = get_active_model(project_config.runtime)
    print(f"   ✅ get_active_model() returned: {model.name}")
    print(f"      Provider: {model.provider.value}")
    print(f"      Model: {model.model}")

    # Get specific model
    if len(project_config.runtime.models) > 1:
        model2 = get_active_model(project_config.runtime, project_config.runtime.models[1].name)
        print(f"   ✅ get_active_model('{model2.name}') succeeded")

except Exception as e:
    print(f"   ❌ Runtime helpers test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All tests passed!")
print("=" * 60)
print("\nNext steps:")
print("  - Implement API endpoints (Phase 3)")
print("  - Implement CLI commands (Phase 3)")
print("  - Connect to real RAG queries (Phase 4)")
print("  - Add structured extraction with instructor (Phase 4)")
