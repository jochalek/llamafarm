"""Agents service configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Agents service settings."""

    # Service configuration
    service_port: int = 8003
    service_host: str = "0.0.0.0"
    log_level: str = "INFO"

    # LlamaFarm server connection
    llamafarm_server_url: str = "http://localhost:8000"

    # Agent execution
    max_concurrent_agents: int = 4
    agent_timeout: int = 300  # 5 minutes

    # Environment
    environment: str = "development"

    class Config:
        env_file = ".env"
        env_prefix = "AGENTS_"


settings = Settings()
