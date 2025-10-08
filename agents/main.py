"""Agents service entry point."""
import sys
from pathlib import Path

# Add parent directory to path so agents module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from agents.core.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "agents.api.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
