# Use Python 3.12 slim image with multi-arch support
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim

# Disable/limit bytecode compilation to avoid CI stalls
ENV UV_COMPILE_BYTECODE=0
ENV UV_COMPILE_BYTECODE_WORKERS=1
ENV UV_COMPILE_BYTECODE_TIMEOUT=15

# Set UV cache directory to a location that will be writable by any user
ENV UV_CACHE_DIR=/tmp/uv-cache

# Set UV to use a writable location for virtual environments
ENV UV_PROJECT_ENVIRONMENT=/tmp/uv-venv

ENV LF_DATA_DIR=/var/lib/llamafarm

RUN apt update && apt install -y curl && rm -rf /var/lib/apt/lists/*

# Create UV cache and virtual environment directories with proper permissions for any user
RUN mkdir -p /tmp/uv-cache && chmod 777 /tmp/uv-cache \
    && mkdir -p /tmp/uv-venv && chmod 777 /tmp/uv-venv \
    && mkdir -p /var/lib/llamafarm && chmod 777 /var/lib/llamafarm

# Set working directory
WORKDIR /app

# Copy the required packages from the monorepo
# Note: This Dockerfile should be run from the repo root: docker build -f agents/Dockerfile .
COPY config/ ./config/
COPY agents/ ./agents/

# Install dependencies
RUN ls -la config
RUN cd config && uv sync --locked --verbose
RUN cd agents && uv sync --locked --verbose

# Compile the config schema
RUN cd config && uv run python compile_schema.py

# Fix ownership and permissions of UV directories after they've been populated
RUN chmod -R 777 /tmp/uv-cache /tmp/uv-venv

# Expose port
EXPOSE 8003

# Change to /app so agents can access config
WORKDIR /app

# Run the agents service
CMD ["uv", "run", "--project", "/app/agents", "python", "/app/agents/main.py"]
