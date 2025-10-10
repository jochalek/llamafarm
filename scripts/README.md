# FDA Batch Processing Scripts

Two-step process for analyzing 500+ FDA correspondence documents.

## Quick Start

```bash
# Step 1: Setup (creates datasets, uploads documents, validates system)
./scripts/fda_batch_setup.sh

# Step 2: Process all documents
./scripts/fda_batch_process.sh
```

---

## Script 1: `fda_batch_setup.sh`

**Purpose:** Sets up RAG databases, uploads documents, and validates the system is ready.

**What it does:**
1. Verifies services are running
2. Creates `fda_letters_test` dataset (full documents)
3. Creates `fda_corpus_test` dataset (chunked for answers)
4. Uploads all documents from sample directory
5. Processes documents into vector databases
6. Tests individual agents (extractor + validator)
7. Validates system health

**Usage:**
```bash
# Full setup with document processing
./scripts/fda_batch_setup.sh

# Skip processing if datasets already exist
./scripts/fda_batch_setup.sh --skip-processing

# Help
./scripts/fda_batch_setup.sh --help
```

**Output:**
- Uploads and processes documents
- Creates vector databases
- Validates agents work
- Logs saved to `/tmp/fda_batch_test/`

**Run this first!** Before using `fda_batch_process.sh`.

---

## Script 2: `fda_batch_process.sh`

**Purpose:** Processes ALL documents through the batch orchestrator agent.

**What it does:**
1. Retrieves all document hashes from `fda_letters_test` dataset
2. Calls the `fda_batch_orchestrator` agent
3. Agent loops through ALL documents:
   - Extracts questions from each document
   - Classifies questions (critical vs. administrative)
   - Validates answers in corpus database
   - Uses recursive verification
4. Generates comprehensive report (JSON + CSV)

**Usage:**
```bash
# Process all documents with default settings
./scripts/fda_batch_process.sh

# Custom batch size and model
./scripts/fda_batch_process.sh --batch-size 10 --model balanced

# Custom output directory
./scripts/fda_batch_process.sh --output-dir /data/fda_results

# Help
./scripts/fda_batch_process.sh --help
```

**Options:**
- `--namespace NS` - Project namespace (default: default)
- `--project PROJ` - Project name (default: fda-demo-1)
- `--batch-size N` - Documents per batch (default: 5)
- `--output-dir DIR` - Output directory (default: /tmp/fda_batch)
- `--model MODEL` - Model to use (default: fast, options: fast, balanced)

**Output:**
- `/tmp/fda_batch/batch_XXXXX_report.json` - Detailed report
- `/tmp/fda_batch/batch_XXXXX_report.csv` - CSV export
- `/tmp/fda_batch/batch_state.json` - Progress tracking
- `/tmp/fda_batch/batch_response.json` - Full API response

**Performance:**
- ~20-30 seconds per document
- 5 documents: ~2-3 minutes
- 500 documents: ~4-6 hours (with batch_size=10)

---

## Complete Workflow

### Initial Setup (one time)

```bash
# 1. Start services
nx start server    # Terminal 1
nx start rag       # Terminal 2
nx start agents    # Terminal 3

# 2. Run setup script
./scripts/fda_batch_setup.sh
```

### Process Documents (repeatable)

```bash
# Process all documents in the dataset
./scripts/fda_batch_process.sh

# Or with custom settings
./scripts/fda_batch_process.sh --batch-size 10 --model balanced --output-dir /results
```

### Review Results

```bash
# View summary statistics
cat /tmp/fda_batch/batch_*_report.json | python3 -m json.tool | head -50

# Open CSV in Excel/Numbers
open /tmp/fda_batch/batch_*_report.csv

# Check unanswered questions
cat /tmp/fda_batch/batch_*_report.json | python3 -c '
import json, sys
report = json.load(sys.stdin)
print(f"Unanswered: {len(report[\"unanswered_questions\"])}")
for q in report["unanswered_questions"][:5]:
    print(f"  - {q[\"question\"][:80]}...")
'
```

---

## Report Structure

### JSON Report

```json
{
  "batch_id": "batch_1696800000",
  "summary": {
    "total_documents": 5,
    "total_questions": 48,
    "critical_questions": 32,
    "administrative_questions": 16,
    "answered_questions": 24,
    "unanswered_questions": 8,
    "answer_rate": 75.0,
    "processing_time_minutes": 2.5
  },
  "all_questions": [ ... ],
  "answered_questions": [ ... ],
  "unanswered_questions": [ ... ],
  "document_details": [ ... ]
}
```

### CSV Export

| Source Document | Question | Question Type | Answered | Confidence | Evidence | Summary |
|----------------|----------|---------------|----------|------------|----------|---------|
| 761240_2023.pdf | Provide virus testing results | critical | Yes | 0.92 | 761248_2024.pdf p.12 | Testing protocol described... |
| 761225_2024.pdf | Submit clinical trial data | critical | No | 0.0 | | No matching response found |

---

## Troubleshooting

### Setup script fails at processing

**Issue:** Documents fail to process into vector database

**Solution:**
```bash
# Check RAG worker is running
nx start rag

# Check for errors in RAG logs
# Ensure Ollama is running with nomic-embed-text model
```

### Batch process finds 0 documents

**Issue:** `No documents found in fda_letters_test dataset`

**Solution:**
```bash
# Run setup first
./scripts/fda_batch_setup.sh

# Or check dataset exists
./lf datasets list
```

### Agent timeout

**Issue:** Request takes too long and times out

**Solution:**
```bash
# Use smaller batch size
./scripts/fda_batch_process.sh --batch-size 3

# Or use faster model
./scripts/fda_batch_process.sh --model fast
```

### Out of memory

**Issue:** System runs out of memory with large batches

**Solution:**
```bash
# Reduce batch size
./scripts/fda_batch_process.sh --batch-size 2

# Or process in chunks (stop and restart)
# Resume capability built-in via batch_state.json
```

---

## Architecture

```
Setup Script                  Batch Process Script
     ↓                              ↓
Creates Datasets              Batch Orchestrator Agent
     ↓                              ↓
Uploads Files                 For each document:
     ↓                              ├→ Question Extractor Agent
Processes to Vector DB             │   ├─ Retrieves full doc from RAG
     ↓                              │   ├─ LLM extracts questions
Validates Agents                   │   └─ Classifies (critical/admin)
     ↓                              │
System Ready                       └→ Answer Validator Agent
                                       ├─ RAG searches response corpus
                                       ├─ LLM validates answer validity
                                       ├─ Recursive verification if partial
                                       └─ Extracts evidence citations
                                        ↓
                                   Final Report (JSON + CSV)
```

---

## See Also

- **Complete Setup Guide:** `docs/FDA-BATCH-PROCESSING-SETUP.md`
- **Agent Documentation:** `agents/README.md`
- **Batch Processing Strategy:** `thoughts/BATCH-PROCESSING-STRATEGY.md`
