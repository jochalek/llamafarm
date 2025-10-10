# FDA Document Analysis Agents

## Overview

The FDA agents system automatically analyzes FDA correspondence to extract questions/requests and validate if they've been answered in your response documents.

## Prerequisites

### macOS Setup

Before using the FDA agents system, ensure you have the required tools installed:

#### 1. Install Homebrew (if not already installed)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. Install Go
```bash
# Install Go via Homebrew
brew install go

# Verify installation
go version
```

#### 3. Install UV (Python package manager)
```bash
# Install UV via Homebrew
brew install uv

# Verify installation
uv --version
```

#### 4. Install Node.js and Nx
```bash
# Install Node.js via Homebrew
brew install node

# Install Nx globally
npm install -g nx

# Verify installations
node --version
npm --version
nx --version
```

#### 5. Install Ollama (for embeddings)
```bash
# Install Ollama via Homebrew
brew install ollama

# Start Ollama service
ollama serve &

# Pull required embedding model
ollama pull nomic-embed-text

# Verify installation
ollama list
```

#### 6. Install Docker Desktop (for services)
```bash
# Install Docker via Homebrew
brew install --cask docker

# Open Docker Desktop app to complete setup
open -a Docker

# Verify installation (after Docker Desktop starts)
docker --version
docker-compose --version
```

#### 7. Clone and Setup LlamaFarm
```bash
# Clone repository
git clone https://github.com/llama-farm/llamafarm.git
cd llamafarm

# Install Python dependencies
uv sync

# Build CLI
cd cli && go build -o lf . && cd ..

# Copy CLI to path (optional)
sudo cp cli/lf /usr/local/bin/

# Verify CLI installation
./cli/lf --version
```

#### 8. Start Required Services

**Option A: Using Nx (Recommended for Development)**

```bash
# Disable Docker auto-start (important!)
export LF_NO_DOCKER=1

# Terminal 1 - Server
nx start server

# Terminal 2 - RAG Worker
nx start rag

# Terminal 3 - Agents Service
nx start agents

# Verify services are running
curl http://localhost:8000/health   # Server
curl http://localhost:8003/health/  # Agents (note trailing slash)
```

**Option B: Using Docker (Alternative)**

```bash
# Don't set LF_NO_DOCKER
# CLI will auto-start Docker containers when needed
./lf start
```

**Important:** If running services via `nx start`, always set `export LF_NO_DOCKER=1` to prevent the CLI from trying to start Docker containers and conflicting with your running services.

### Quick Verification

Check that all prerequisites are installed:

```bash
# Check all tools
command -v brew && echo "✓ Homebrew installed"
command -v go && echo "✓ Go installed"
command -v uv && echo "✓ UV installed"
command -v node && echo "✓ Node.js installed"
command -v nx && echo "✓ Nx installed"
command -v ollama && echo "✓ Ollama installed"
command -v docker && echo "✓ Docker installed"

# Check services
curl -s http://localhost:8000/health && echo "✓ Server running"
curl -s http://localhost:8003/health/ && echo "✓ Agents running"
ollama list | grep nomic-embed-text && echo "✓ Embedding model ready"
```

If any checks fail, review the installation steps above.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    FDA DOCUMENT ANALYSIS                         │
└─────────────────────────────────────────────────────────────────┘

Step 1: INGESTION
┌──────────────────────────────────────────────────────────────┐
│  FDA Letters (PDFs)          Response Documents (PDFs)       │
│  ├─ Complete Response Letter ├─ Meeting Minutes              │
│  ├─ Information Requests     ├─ Email Threads                │
│  └─ Meeting Minutes          └─ Submissions                  │
└──────────────────────────────────────────────────────────────┘
                           ↓
                    Vector Database
         ┌──────────────────────────────────┐
         │  fda_letters_full (Questions)    │
         │  fda_corpus_chunked (Answers)    │
         └──────────────────────────────────┘


Step 2: QUESTION EXTRACTION
┌──────────────────────────────────────────────────────────────┐
│                   FDAQuestionExtractorAgent                   │
│                                                               │
│  For each FDA document:                                       │
│    1. Break into chunks (~500 chars each)                    │
│    2. Analyze each chunk with LLM:                           │
│       "Is there an FDA request/directive here?"              │
│    3. Extract:                                               │
│       • Question text                                        │
│       • Type (critical vs administrative)                    │
│       • Context (CMC, Safety, Clinical, etc.)                │
│       • Page number                                          │
│    4. Filter out:                                            │
│       ✗ Headers/footers                                      │
│       ✗ Greetings/signatures                                 │
│       ✗ Background info                                      │
│       ✓ ONLY actual FDA requests                            │
└──────────────────────────────────────────────────────────────┘
                           ↓
         ┌──────────────────────────────────┐
         │     Extracted Questions List      │
         │                                   │
         │  ✓ "Submit stability data..."    │
         │  ✓ "Provide virus testing..."    │
         │  ✗ Skipped administrative items  │
         └──────────────────────────────────┘


Step 3: ANSWER VALIDATION
┌──────────────────────────────────────────────────────────────┐
│                  FDAAnswerValidatorAgent                      │
│                                                               │
│  For each critical question:                                 │
│    1. Search response corpus (RAG)                           │
│    2. Ask LLM: "Do these docs answer the question?"         │
│    3. Classify:                                              │
│       • Complete: ✅ Fully answered                          │
│       • Incomplete: ❌ Not answered                          │
│    4. Extract evidence:                                      │
│       • Document name                                        │
│       • Relevant excerpt                                     │
│       • Confidence score                                     │
└──────────────────────────────────────────────────────────────┘
                           ↓
         ┌──────────────────────────────────┐
         │       Validation Results          │
         │                                   │
         │  Question 1: ✅ Answered          │
         │    Source: response_2024.pdf      │
         │    Excerpt: "Stability data..."   │
         │                                   │
         │  Question 2: ❌ Unanswered        │
         │    Missing: Test results          │
         └──────────────────────────────────┘


Step 4: BATCH ORCHESTRATION & REPORTING
┌──────────────────────────────────────────────────────────────┐
│               FDABatchOrchestratorAgent                       │
│                                                               │
│  Coordinates processing of 500+ documents:                   │
│    • Progress tracking                                       │
│    • Error handling                                          │
│    • Resume on failure                                       │
│    • Generate final report                                   │
└──────────────────────────────────────────────────────────────┘
                           ↓
         ┌──────────────────────────────────┐
         │        Final Report               │
         │                                   │
         │  📊 Summary Statistics            │
         │    • 15 documents processed       │
         │    • 47 questions extracted       │
         │    • 35 answered (74%)            │
         │    • 12 unanswered (26%)          │
         │                                   │
         │  📋 Unanswered Questions          │
         │    1. "Submit CMC data..."        │
         │       Source: CR_letter_2024.pdf  │
         │       Page: 3                     │
         │                                   │
         │  ✅ Answered Questions            │
         │    1. "Provide stability..."      │
         │       Answer: response_Q3.pdf     │
         │       Confidence: 0.92            │
         └──────────────────────────────────┘
```

## What Gets Extracted

### ✅ **Critical Questions** (Validated for Answers)
- Regulatory data requests
- CMC/manufacturing requirements
- Clinical/safety study requests
- Deficiency corrections
- Protocol modifications

### ⚠️ **Administrative Questions** (Extracted, Not Validated)
- Meeting scheduling
- Timeline requests
- Submission deadlines

### ❌ **Not Extracted** (Filtered Out)
- Document headers/footers
- Email greetings/signatures
- Background information
- Generic statements without specific asks

## Example Flow

```
Input: Complete Response Letter (BLA 761225)
├─ Page 1: Header                           → ❌ Filtered out
├─ Page 2: "Submit stability data at 25°C"  → ✅ Extracted as critical
├─ Page 3: "Dear Dr. Smith,"                → ❌ Filtered out
├─ Page 4: "Provide virus testing results" → ✅ Extracted as critical
└─ Page 5: "Please confirm meeting date"   → ⚠️ Extracted as administrative

Validation:
├─ Question 1: "Submit stability data..."
│  └─ Search: fda_corpus_chunked
│     └─ Found: "Stability study results..." in response_2024.pdf
│        └─ Result: ✅ ANSWERED (confidence: 0.89)
│
└─ Question 2: "Provide virus testing..."
   └─ Search: fda_corpus_chunked
      └─ Not found or incomplete
         └─ Result: ❌ UNANSWERED

Final Output:
{
  "document": "BLA_761225_CR.pdf",
  "questions_extracted": 2,
  "answered": 1,
  "unanswered": 1,
  "unanswered_list": [
    {
      "question": "Provide virus testing results...",
      "source_page": 4,
      "type": "critical"
    }
  ]
}
```

## Performance

- **Question Extraction:** ~60 seconds per document (11 chunks × 5 sec)
- **Answer Validation:** ~15 seconds per question (single-pass, no recursion)
- **Total Processing:** ~90-120 seconds per document with 2-3 questions
- **Batch Processing:** ~7-10 minutes for 5 documents

## Key Features

### 🎯 **Precision Filtering**
- LLM analyzes each chunk independently
- Strict rules prevent false positives
- Only extracts explicit FDA requests

### 📝 **Context Preservation**
- Captures full question text
- Records page numbers
- Classifies by regulatory area

### ✅ **Answer Verification**
- RAG-based semantic search
- LLM validates actual answers (not just related content)
- Provides evidence with source documents

### 🔄 **Production Ready**
- Handles 500+ documents
- Progress tracking and resume capability
- Error handling with graceful degradation
- Comprehensive reporting

## Configuration

### Agents

```yaml
agents:
  - name: fda_question_extractor
    type: fda_question_extractor
    model: fast
    config:
      database: fda_letters_full      # Where FDA letters are stored
      min_confidence: 0.7              # Filter low-confidence extractions

  - name: fda_answer_validator
    type: fda_answer_validator
    model: fast
    config:
      database: fda_corpus_chunked     # Where answers are stored
      top_k: 3                         # RAG retrieval limit
      max_recursion_depth: 0           # Disabled for speed

  - name: fda_batch_orchestrator
    type: fda_batch_orchestrator
    model: fast
    config:
      batch_size: 10                   # Documents per batch
      output_path: /tmp/fda_batch      # Report output location
```

### Databases

```yaml
rag:
  databases:
    - name: fda_letters_full
      # Stores complete FDA letters for question extraction
      # Strategy: Full document chunks (no splitting)

    - name: fda_corpus_chunked
      # Stores response documents for answer validation
      # Strategy: Chunked for semantic search
```

## Getting Started

### Step 1: Setup (One-Time)

Before running batch processing, set up your databases and upload documents:

```bash
# Full setup with document processing
./scripts/fda_batch_setup.sh

# Or skip processing if datasets already exist
./scripts/fda_batch_setup.sh --skip-processing
```

**What this does:**
- ✅ Verifies services are running
- ✅ Creates `fda_letters_test` dataset (full documents)
- ✅ Creates `fda_corpus_test` dataset (chunked for answers)
- ✅ Uploads all documents from sample directory
- ✅ Processes documents into vector databases
- ✅ Tests individual agents (extractor + validator)
- ✅ Validates system health

### Step 2: Process Documents

Run batch processing on all documents:

```bash
# Process all documents with default settings
./scripts/fda_batch_process.sh

# Custom batch size and model
./scripts/fda_batch_process.sh --batch-size 10 --model balanced

# Custom output directory
./scripts/fda_batch_process.sh --output-dir /data/fda_results
```

**Available options:**
- `--namespace NS` - Project namespace (default: default)
- `--project PROJ` - Project name (default: fda-demo-1)
- `--batch-size N` - Documents per batch (default: 5)
- `--output-dir DIR` - Output directory (default: /tmp/fda_batch)
- `--model MODEL` - Model to use (default: fast, options: fast, balanced)

### Step 3: Control & Monitor

Control running batch jobs:

```bash
# Check current batch status
./scripts/fda_batch_control.sh status

# Stop batch gracefully (completes current document)
./scripts/fda_batch_control.sh stop

# Resume stopped batch from last checkpoint
./scripts/fda_batch_control.sh resume

# List all batch results
./scripts/fda_batch_control.sh results

# Clean up batch state (WARNING: cannot resume after this)
./scripts/fda_batch_control.sh clean
```

## Usage

### Via CLI Scripts (Recommended)
```bash
# Setup (one-time)
./scripts/fda_batch_setup.sh

# Process all documents
./scripts/fda_batch_process.sh

# Monitor progress
./scripts/fda_batch_control.sh status
```

### Via Agents API (Advanced)
```bash
# Or via agents API directly
./lf agents run fda_batch_orchestrator --input-file batch_request.json
```

### Input Format
```json
{
  "documents": [
    {
      "hash": "81abd139a975...",
      "name": "BLA_761225_CR.pdf"
    },
    {
      "hash": "ad1def8bec11...",
      "name": "IND_113695_IR.pdf"
    }
  ]
}
```

### Output Report
```json
{
  "batch_id": "batch_1728505730",
  "summary": {
    "total_documents": 15,
    "total_questions": 47,
    "answered_questions": 35,
    "unanswered_questions": 12,
    "answer_rate": 74.5
  },
  "unanswered_questions": [
    {
      "question": "Submit virus testing results for all UPB batches",
      "source_document": "BLA_761225_CR.pdf",
      "page_reference": "Page 4",
      "type": "critical",
      "context": "CMC - Viral Safety"
    }
  ],
  "document_details": [ /* per-document breakdown */ ]
}
```

## Tips for Best Results

1. **Organize Documents by Type**
   - FDA letters → `fda_letters_full` database
   - Your responses → `fda_corpus_chunked` database

2. **Use Consistent Naming**
   - Include document type and date in filenames
   - Example: `BLA_761225_CR_2024-03-15.pdf`

3. **Quality Over Quantity**
   - 15-20 high-quality documents > 500 random files
   - Focus on official correspondence

4. **Review Unanswered Questions**
   - The system is conservative (minimizes false positives)
   - Manual review recommended for borderline cases

## Troubleshooting

**Too many false positives?**
→ Increase `min_confidence` threshold (0.7 → 0.8)

**Missing real questions?**
→ Decrease `min_confidence` threshold (0.7 → 0.6)

**Too slow?**
→ Already optimized! Consider:
- Reducing document count
- Using faster hardware
- Skipping answer validation for speed

**Questions not being validated?**
→ Check that response documents are in `fda_corpus_chunked` database
