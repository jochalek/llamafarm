# LlamaFarm Agents Service

Standalone microservice for executing LlamaFarm agents.

## Overview

The agents service is an independent FastAPI application that:
- Executes autonomous agents for document analysis, validation, and reporting
- Communicates with LlamaFarm server via HTTP APIs
- Supports streaming responses for long-running operations
- Auto-discovers agent implementations
- Provides OpenAPI documentation

## Architecture

```
agents/
├── api/                    # FastAPI application
│   ├── main.py            # App initialization
│   └── routers/           # API endpoints
│       ├── agents.py      # Agent execution
│       └── health.py      # Health checks
├── core/                  # Core infrastructure
│   ├── base_agent.py      # Agent interface
│   ├── registry.py        # Auto-discovery
│   ├── settings.py        # Configuration
│   └── logging.py         # Logging setup
├── implementations/       # Agent implementations
│   └── document_analyzer.py
├── services/              # HTTP clients
│   └── server_client.py   # Server API client
├── api_models.py          # Generated API types
├── datamodel.py           # Generated config types
└── main.py                # Entry point
```

## Agent Types

### Document Analyzer
Extracts structured information from documents using LLM and RAG.

**Config:**
```yaml
agents:
  - name: my_analyzer
    type: document_analyzer
    model: fast  # Optional: uses project default if not specified
    description: Analyze documents
    system_prompt: You are a document analysis expert.
    config:
      database: my_database
      retrieval_strategy: basic_search
      max_context_length: 50000
```

## Development

### Start Service
```bash
# From project root
nx start agents

# Or directly
cd agents
uv run python main.py
```

Service runs on **http://localhost:8003**

### Run Tests
```bash
nx test agents

# Or directly
cd agents
uv run pytest -v
```

### Lint Code
```bash
nx lint agents
```

### Generate Types
```bash
# From config/ directory
./generate-types.sh
```

Generates:
- `agents/datamodel.py` - Agent config types from `schema.yaml`
- `agents/api_models.py` - API request/response types from `api_schema.yaml`

## Configuration

### Environment Variables

See `.env.example` for all options:

```bash
AGENTS_SERVICE_PORT=8003
AGENTS_SERVICE_HOST=0.0.0.0
AGENTS_LOG_LEVEL=INFO
AGENTS_LLAMAFARM_SERVER_URL=http://localhost:8000
AGENTS_MAX_CONCURRENT_AGENTS=4
AGENTS_AGENT_TIMEOUT=300
AGENTS_ENVIRONMENT=development
```

### Agent Configuration

Agents are configured in `llamafarm.yaml`:

```yaml
agents:
  - name: agent_name
    type: document_analyzer  # One of: document_analyzer, rag_validator, report_generator, workflow_orchestrator
    model: model_name        # Optional: references runtime.models.name
    description: Human-readable description
    system_prompt: Custom system prompt for LLM
    config:
      # Agent-specific configuration
      database: database_name
      # ... other config fields
```

## API Endpoints

### Agent Execution

**POST** `/v1/agents/run`

Execute an agent with provided configuration and input.

Request:
```json
{
  "namespace": "default",
  "project": "my-project",
  "agent_config": {
    "name": "my_analyzer",
    "type": "document_analyzer",
    "config": {"database": "my_db"}
  },
  "project_config": {...},
  "input_data": {"query": "search term"},
  "stream": false
}
```

Response:
```json
{
  "agent_name": "my_analyzer",
  "status": "completed",
  "result": {...}
}
```

### List Agent Types

**GET** `/v1/agents/types`

Returns all registered agent types.

**GET** `/v1/agents/types/{agent_type}`

Get info about a specific agent type.

### Health Checks

**GET** `/health`

Service health with metadata:
```json
{
  "status": "healthy",
  "service": "llamafarm-agents",
  "version": "0.1.0",
  "agent_types_loaded": 1,
  "agent_types": ["document_analyzer"],
  "server_url": "http://localhost:8000"
}
```

**GET** `/health/ready`

Readiness check for orchestration:
```json
{
  "status": "ready",
  "agent_types": 1
}
```

### OpenAPI Documentation

**GET** `/docs` - Swagger UI
**GET** `/redoc` - ReDoc UI

## Adding New Agents

1. Create file in `agents/implementations/my_agent.py`
2. Inherit from `BaseAgent`
3. Set `AGENT_TYPE` class attribute
4. Implement `async def run(self, input_data, **kwargs)`
5. Add agent type to `agents/schema.yaml`
6. Regenerate types: `cd config && ./generate-types.sh`

Example:

```python
from agents.core.base_agent import BaseAgent

class MyAgent(BaseAgent):
    AGENT_TYPE = "my_agent"

    async def run(self, input_data, **kwargs):
        # Use self.server_client for server API calls
        results = await self.server_client.rag_search(
            namespace=self.namespace,
            project=self.project,
            database=self.config["database"],
            query=input_data["query"],
        )
        return {"results": results}
```

## Communication with Server

Agents communicate with LlamaFarm server via `ServerClient`:

```python
# In agent implementation
results = await self.server_client.rag_search(...)
response = await self.server_client.chat_completion(...)
config = await self.server_client.get_project_config(...)
```

**No direct imports of server code!** This maintains clean separation.

## Docker

Build image:
```bash
nx build agents
# or
docker build -t llamafarm-agents:latest ./agents
```

Run container:
```bash
docker run -p 8003:8003 \
  -e AGENTS_LLAMAFARM_SERVER_URL=http://server:8000 \
  llamafarm-agents:latest
```

## Troubleshooting

### Port Already in Use
```bash
lsof -ti:8003 | xargs kill -9
```

### Agent Not Discovered
- Check that agent file is in `implementations/`
- Verify `AGENT_TYPE` class attribute is set
- Check service logs for import errors
- Ensure agent inherits from `BaseAgent`

### Cannot Connect to Server
- Verify server is running: `curl http://localhost:8000/health`
- Check `AGENTS_LLAMAFARM_SERVER_URL` setting
- Ensure network connectivity between services

### Type Generation Fails
```bash
cd agents
uv sync --group dev  # Install datamodel-code-generator
cd ../config
./generate-types.sh
```

## Production Deployment

1. Build Docker image
2. Deploy to Kubernetes/ECS/etc
3. Configure environment variables
4. Ensure network access to server
5. Set up health check monitoring on `/health/ready`
6. Scale horizontally as needed (stateless service)

## Architecture Notes

- **Stateless**: No persistent state, scales horizontally
- **HTTP-based**: All communication via HTTP APIs
- **Independent**: Can be developed, tested, deployed separately
- **Generated Types**: All models generated from schemas
- **Auto-discovery**: Agents automatically registered on startup

## License

Part of LlamaFarm project.
