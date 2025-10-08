"""Integration tests for agents API endpoints.

These tests require:
1. Server running (nx start server)
2. Test project configured in llamafarm.yaml with agents
"""

import pytest
from fastapi.testclient import TestClient

# Import will trigger auto-discovery
from agents import AgentRegistry
from api.main import llama_farm_api


@pytest.fixture
def client():
    """Create test client."""
    app = llama_farm_api()
    return TestClient(app)


@pytest.fixture
def test_project():
    """Test project details."""
    return {
        "namespace": "default",
        "project": "test-project-1",
    }


class TestAgentsAPI:
    """Test suite for agents API endpoints."""

    def test_list_agents(self, client, test_project):
        """Test GET /agents - list all agents."""
        response = client.get(
            f"/v1/projects/{test_project['namespace']}/{test_project['project']}/agents/"
        )

        assert response.status_code == 200
        data = response.json()

        assert "total" in data
        assert "agents" in data
        assert isinstance(data["agents"], list)

        # Should have at least the test agents from llamafarm.yaml
        assert data["total"] >= 4

        # Check agent structure
        for agent in data["agents"]:
            assert "name" in agent
            assert "type" in agent
            # Optional fields
            assert "description" in agent or agent.get("description") is None
            assert "model" in agent or agent.get("model") is None

    def test_get_agent(self, client, test_project):
        """Test GET /agents/{name} - get specific agent."""
        agent_name = "test_analyzer"

        response = client.get(
            f"/v1/projects/{test_project['namespace']}/{test_project['project']}/agents/{agent_name}"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == agent_name
        assert data["type"] == "document_analyzer"
        assert data.get("model") == "fast"

    def test_get_nonexistent_agent(self, client, test_project):
        """Test GET /agents/{name} with non-existent agent."""
        response = client.get(
            f"/v1/projects/{test_project['namespace']}/{test_project['project']}/agents/nonexistent"
        )

        assert response.status_code == 404

    def test_run_agent_sync(self, client, test_project):
        """Test POST /agents/{name}/run - synchronous execution."""
        agent_name = "test_reporter"  # Simpler agent for testing

        payload = {
            "input": {
                "data": [{"id": 1, "value": "test"}],
                "statistics": {"total": 1}
            },
            "parameters": {},
            "stream": False
        }

        response = client.post(
            f"/v1/projects/{test_project['namespace']}/{test_project['project']}/agents/{agent_name}/run",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()

        assert data["agent_name"] == agent_name
        assert "status" in data
        # May be "completed" or "failed" depending on dependencies

    def test_run_agent_async(self, client, test_project):
        """Test POST /agents/{name}/run/async - asynchronous execution."""
        agent_name = "test_reporter"

        payload = {
            "input": {"data": []},
            "parameters": {}
        }

        response = client.post(
            f"/v1/projects/{test_project['namespace']}/{test_project['project']}/agents/{agent_name}/run/async",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()

        assert "task_id" in data
        assert data["status"] == "queued"
        assert data["agent_name"] == agent_name
        assert "message" in data


class TestAgentRegistry:
    """Test the agent registry auto-discovery system."""

    def test_agent_types_registered(self):
        """Test that built-in agent types are auto-discovered and registered."""
        # Accessing AgentRegistry triggers auto-discovery
        registered_types = AgentRegistry.list_types()

        # Should have all our built-in agents
        expected_types = [
            "document_analyzer",
            "rag_validator",
            "report_generator",
            "workflow_orchestrator"
        ]

        for agent_type in expected_types:
            assert agent_type in registered_types, \
                f"Agent type '{agent_type}' not registered"

    def test_agent_type_info(self):
        """Test getting agent type information."""
        info = AgentRegistry.get_type_info("document_analyzer")

        assert info["type"] == "document_analyzer"
        assert "class" in info
        assert info["class"] == "DocumentAnalyzerAgent"

    def test_agent_type_not_found(self):
        """Test getting info for non-existent agent type."""
        with pytest.raises(ValueError, match="not registered"):
            AgentRegistry.get_type_info("nonexistent")


class TestAgentService:
    """Test the agent service."""

    def test_list_agents_from_config(self):
        """Test listing agents from project configuration."""
        from services.project_service import ProjectService
        from services.agent_service import AgentService

        # Load test project config
        project_config = ProjectService.load_config("default", "test-project-1")

        # List agents
        agents = AgentService.list_agents(project_config)

        assert isinstance(agents, list)
        assert len(agents) >= 4

        # Check agent structure
        for agent in agents:
            assert "name" in agent
            assert "type" in agent

    def test_get_agent_config(self):
        """Test getting specific agent configuration."""
        from services.project_service import ProjectService
        from services.agent_service import AgentService

        project_config = ProjectService.load_config("default", "test-project-1")

        # Get specific agent
        agent_config = AgentService.get_agent_config(project_config, "test_analyzer")

        assert agent_config["name"] == "test_analyzer"
        assert agent_config["type"].value == "document_analyzer"
        assert agent_config.get("model") == "fast"

    def test_validate_agent_config(self):
        """Test agent configuration validation."""
        from services.project_service import ProjectService
        from services.agent_service import AgentService

        project_config = ProjectService.load_config("default", "test-project-1")

        # Validate existing agent
        is_valid, error = AgentService.validate_agent_config(
            project_config, "test_analyzer"
        )

        assert is_valid is True
        assert error is None

        # Validate non-existent agent
        is_valid, error = AgentService.validate_agent_config(
            project_config, "nonexistent"
        )

        assert is_valid is False
        assert "not found" in error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
