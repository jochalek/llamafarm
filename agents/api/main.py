"""Agents service FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.api.routers import health, agents as agents_router
from agents.core.settings import settings
from agents.core.logging import setup_logging
from agents.core.registry import AgentRegistry

# Setup logging
setup_logging(settings.log_level)

# Create FastAPI app
app = FastAPI(
    title="LlamaFarm Agents Service",
    description="Agent execution and management service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(agents_router.router, prefix="/v1/agents", tags=["agents"])


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    import logging

    logger = logging.getLogger(__name__)

    # Trigger agent auto-discovery
    AgentRegistry.auto_discover_agents()

    # Log startup
    agent_types = AgentRegistry.list_types()
    logger.info(
        f"Agents service started on {settings.service_host}:{settings.service_port}"
    )
    logger.info(f"Registered agent types: {', '.join(agent_types) if agent_types else 'none'}")
    logger.info(f"Server URL: {settings.llamafarm_server_url}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info("Agents service shutting down")


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "llamafarm-agents",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }
