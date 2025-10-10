# Docker Distribution Guide

Guide for building and distributing LlamaFarm Docker containers to other users.

---

## Overview

LlamaFarm consists of 3 main services that can be distributed as Docker images:

1. **Server** (`llamafarm-server`) - FastAPI server on port 8000
2. **RAG Worker** (`llamafarm-rag`) - Celery worker for document processing
3. **Agents Service** (`llamafarm-agents`) - Agent orchestration service on port 8003

---

## Option 1: Build and Save as .tar Files (Offline Distribution)

### Step 1: Build All Images

From the project root directory:

```bash
cd /path/to/llamafarm-1

# Build server image
docker build -t llamafarm-server:latest -f server/Dockerfile .

# Build RAG worker image
docker build -t llamafarm-rag:latest -f rag/Dockerfile .

# Build agents service image
docker build -t llamafarm-agents:latest -f agents/Dockerfile .
```

### Step 2: Save Images to .tar Files

```bash
# Save server image
docker save llamafarm-server:latest -o llamafarm-server.tar

# Save RAG image
docker save llamafarm-rag:latest -o llamafarm-rag.tar

# Save agents image
docker save llamafarm-agents:latest -o llamafarm-agents.tar
```

### Step 3: Compress (Optional, Recommended)

```bash
# Compress to reduce file size (70-80% smaller)
gzip llamafarm-server.tar
gzip llamafarm-rag.tar
gzip llamafarm-agents.tar

# Result: llamafarm-server.tar.gz, llamafarm-rag.tar.gz, llamafarm-agents.tar.gz
```

### Step 4: Transfer to Recipient

Transfer the 3 files via:
- USB drive
- Cloud storage (Dropbox, Google Drive, etc.)
- File transfer service (WeTransfer, etc.)
- SCP/SFTP

**File sizes (approximate):**
- Server: ~500MB compressed
- RAG: ~600MB compressed
- Agents: ~400MB compressed

### Step 5: Recipient Loads Images

The recipient loads the images on their machine:

```bash
# If compressed, decompress first
gunzip llamafarm-server.tar.gz
gunzip llamafarm-rag.tar.gz
gunzip llamafarm-agents.tar.gz

# Load images into Docker
docker load -i llamafarm-server.tar
docker load -i llamafarm-rag.tar
docker load -i llamafarm-agents.tar

# Verify images loaded
docker images | grep llamafarm
```

---

## Option 2: Push to Docker Registry (Online Distribution)

### Using Docker Hub

#### Step 1: Create Docker Hub Account
Sign up at https://hub.docker.com

#### Step 2: Login
```bash
docker login
```

#### Step 3: Tag Images
```bash
# Replace 'yourusername' with your Docker Hub username
docker tag llamafarm-server:latest yourusername/llamafarm-server:latest
docker tag llamafarm-rag:latest yourusername/llamafarm-rag:latest
docker tag llamafarm-agents:latest yourusername/llamafarm-agents:latest
```

#### Step 4: Push Images
```bash
docker push yourusername/llamafarm-server:latest
docker push yourusername/llamafarm-rag:latest
docker push yourusername/llamafarm-agents:latest
```

#### Step 5: Recipient Pulls Images
```bash
docker pull yourusername/llamafarm-server:latest
docker pull yourusername/llamafarm-rag:latest
docker pull yourusername/llamafarm-agents:latest
```

### Using Private Registry (Alternative)

If you have a private registry:

```bash
# Tag for private registry
docker tag llamafarm-server:latest registry.example.com/llamafarm-server:latest
docker tag llamafarm-rag:latest registry.example.com/llamafarm-rag:latest
docker tag llamafarm-agents:latest registry.example.com/llamafarm-agents:latest

# Push
docker push registry.example.com/llamafarm-server:latest
docker push registry.example.com/llamafarm-rag:latest
docker push registry.example.com/llamafarm-agents:latest
```

---

## Option 3: Using Docker Compose for Easy Distribution

### Step 1: Create docker-compose.yml

Create a `docker-compose.yml` file for the recipient:

```yaml
version: '3.8'

services:
  server:
    image: llamafarm-server:latest
    container_name: llamafarm-server
    ports:
      - "8000:8000"
    environment:
      - LF_DATA_DIR=/var/lib/llamafarm
    volumes:
      - llamafarm-data:/var/lib/llamafarm
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  rag:
    image: llamafarm-rag:latest
    container_name: llamafarm-rag
    depends_on:
      server:
        condition: service_healthy
    environment:
      - LF_DATA_DIR=/var/lib/llamafarm
      - SERVER_URL=http://server:8000
    volumes:
      - llamafarm-data:/var/lib/llamafarm

  agents:
    image: llamafarm-agents:latest
    container_name: llamafarm-agents
    ports:
      - "8003:8003"
    depends_on:
      server:
        condition: service_healthy
    environment:
      - LF_DATA_DIR=/var/lib/llamafarm
      - SERVER_URL=http://server:8000
    volumes:
      - llamafarm-data:/var/lib/llamafarm

volumes:
  llamafarm-data:
```

### Step 2: Start All Services

Recipient runs:

```bash
docker-compose up -d
```

### Step 3: Verify Services

```bash
# Check status
docker-compose ps

# Check logs
docker-compose logs -f

# Test health
curl http://localhost:8000/health
curl http://localhost:8003/health/
```

---

## Complete Distribution Package

Create a complete package for the recipient:

### Package Contents

```
llamafarm-distribution/
├── docker-compose.yml          # Service orchestration
├── README.md                   # Setup instructions
├── images/
│   ├── llamafarm-server.tar.gz
│   ├── llamafarm-rag.tar.gz
│   └── llamafarm-agents.tar.gz
└── scripts/
    ├── load-images.sh          # Script to load images
    └── start-services.sh       # Script to start services
```

### load-images.sh

```bash
#!/bin/bash
set -e

echo "Loading LlamaFarm Docker images..."

cd images

# Decompress
echo "Decompressing images..."
gunzip -k llamafarm-server.tar.gz
gunzip -k llamafarm-rag.tar.gz
gunzip -k llamafarm-agents.tar.gz

# Load
echo "Loading server image..."
docker load -i llamafarm-server.tar

echo "Loading RAG image..."
docker load -i llamafarm-rag.tar

echo "Loading agents image..."
docker load -i llamafarm-agents.tar

# Cleanup
rm *.tar

echo "✓ All images loaded successfully!"
docker images | grep llamafarm
```

### start-services.sh

```bash
#!/bin/bash
set -e

echo "Starting LlamaFarm services..."

# Check if images exist
if ! docker images | grep -q llamafarm-server; then
    echo "Error: Images not loaded. Run ./load-images.sh first"
    exit 1
fi

# Start with docker-compose
docker-compose up -d

echo "Waiting for services to start..."
sleep 5

# Check health
echo "Checking service health..."
curl -s http://localhost:8000/health && echo "✓ Server is healthy"
curl -s http://localhost:8003/health/ && echo "✓ Agents service is healthy"

echo ""
echo "✓ LlamaFarm is running!"
echo ""
echo "Server:  http://localhost:8000"
echo "Agents:  http://localhost:8003"
echo ""
echo "View logs: docker-compose logs -f"
echo "Stop services: docker-compose down"
```

### README.md for Recipient

````markdown
# LlamaFarm Docker Distribution

## Prerequisites

- Docker installed (https://docs.docker.com/get-docker/)
- Docker Compose installed (comes with Docker Desktop)

## Quick Start

1. **Load Docker images:**
   ```bash
   chmod +x scripts/load-images.sh
   ./scripts/load-images.sh
   ```

2. **Start services:**
   ```bash
   chmod +x scripts/start-services.sh
   ./scripts/start-services.sh
   ```

3. **Verify services are running:**
   ```bash
   docker-compose ps
   curl http://localhost:8000/health
   curl http://localhost:8003/health/
   ```

## Usage

- **View logs:** `docker-compose logs -f`
- **Stop services:** `docker-compose down`
- **Restart services:** `docker-compose restart`
- **Remove everything:** `docker-compose down -v`

## Services

- **Server:** http://localhost:8000 - Main API server
- **Agents:** http://localhost:8003 - Agent orchestration service
- **RAG Worker:** Background service (no exposed port)

## Support

For issues, contact [your contact info]
````

---

## Build Script for Distribution

Create a `build-distribution.sh` script to automate everything:

```bash
#!/bin/bash
set -e

DIST_DIR="llamafarm-distribution"
VERSION="latest"

echo "Building LlamaFarm distribution package..."

# Clean previous build
rm -rf $DIST_DIR
mkdir -p $DIST_DIR/{images,scripts}

# Build images
echo "Building Docker images..."
docker build -t llamafarm-server:$VERSION -f server/Dockerfile .
docker build -t llamafarm-rag:$VERSION -f rag/Dockerfile .
docker build -t llamafarm-agents:$VERSION -f agents/Dockerfile .

# Save and compress images
echo "Saving images..."
docker save llamafarm-server:$VERSION | gzip > $DIST_DIR/images/llamafarm-server.tar.gz
docker save llamafarm-rag:$VERSION | gzip > $DIST_DIR/images/llamafarm-rag.tar.gz
docker save llamafarm-agents:$VERSION | gzip > $DIST_DIR/images/llamafarm-agents.tar.gz

# Copy docker-compose and scripts
cp docker-compose.yml $DIST_DIR/
cp scripts/load-images.sh $DIST_DIR/scripts/
cp scripts/start-services.sh $DIST_DIR/scripts/
cp docs/DISTRIBUTION-README.md $DIST_DIR/README.md

# Make scripts executable
chmod +x $DIST_DIR/scripts/*.sh

# Create archive
echo "Creating distribution archive..."
tar -czf llamafarm-distribution-$VERSION.tar.gz $DIST_DIR

echo "✓ Distribution package created: llamafarm-distribution-$VERSION.tar.gz"
echo "Size: $(du -h llamafarm-distribution-$VERSION.tar.gz | cut -f1)"
```

---

## Versioning Best Practices

When distributing, use version tags:

```bash
# Build with version tag
docker build -t llamafarm-server:1.0.0 -f server/Dockerfile .
docker build -t llamafarm-rag:1.0.0 -f rag/Dockerfile .
docker build -t llamafarm-agents:1.0.0 -f agents/Dockerfile .

# Also tag as latest
docker tag llamafarm-server:1.0.0 llamafarm-server:latest
docker tag llamafarm-rag:1.0.0 llamafarm-rag:latest
docker tag llamafarm-agents:1.0.0 llamafarm-agents:latest
```

---

## Troubleshooting

### Image size too large

```bash
# Use multi-stage builds
# Optimize layer caching
# Remove unnecessary files before COPY
```

### Transfer interrupted

```bash
# Use rsync for resumable transfers
rsync -avz --progress llamafarm-*.tar.gz user@host:/destination/
```

### Recipient has different architecture

```bash
# Build for multiple platforms
docker buildx build --platform linux/amd64,linux/arm64 \
  -t llamafarm-server:latest -f server/Dockerfile .
```

---

## Security Considerations

1. **Don't include secrets** - Ensure no API keys or credentials in images
2. **Scan images** - Run security scans before distribution
   ```bash
   docker scan llamafarm-server:latest
   ```
3. **Use specific versions** - Don't distribute `latest` tag in production
4. **Provide checksums** - Generate SHA256 checksums for verification
   ```bash
   sha256sum llamafarm-*.tar.gz > checksums.txt
   ```

---

## Next Steps

After recipient loads and starts containers:

1. Configure project with `llamafarm.yaml`
2. Upload documents via CLI or API
3. Run FDA batch processing scripts
4. Access chat interface

See main documentation for usage instructions.
