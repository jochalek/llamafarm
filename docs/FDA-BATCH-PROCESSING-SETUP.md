# FDA Batch Processing - Complete Setup Guide

**Date:** 2025-10-08
**Use Case:** Process 500+ FDA correspondence documents to extract questions and validate answers

---

## Overview

This system processes large batches of FDA correspondence (PDFs, emails, meeting minutes) to:

1. **Extract Questions** - Identify real FDA questions vs. headers/references
2. **Classify Questions** - Critical regulatory vs. administrative
3. **Validate Answers** - Search response corpus with recursive verification
4. **Generate Reports** - Comprehensive CSV/JSON output with evidence

**Key Features:**
- ✅ Dual database strategy (full documents + chunked corpus)
- ✅ Recursive file upload from nested directories
- ✅ Progress tracking with resume capability
- ✅ Recursive answer verification (ensures answers are REAL, not just related)
- ✅ Question/answer evidence with document names, pages, excerpts

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ FDA Batch Processing Pipeline                                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Stage 1: Dual Database Setup                                │
│  ┌──────────────────────────────────────┐                   │
│  │ fda_letters_full:                    │                   │
│  │  - Full document preservation        │                   │
│  │  - 50K token chunks (no splitting)   │                   │
│  │  - Used for question extraction      │                   │
│  │                                      │                   │
│  │ fda_corpus_chunked:                  │                   │
│  │  - Semantic chunking (1500 tokens)   │                   │
│  │  - 200 token overlap                 │                   │
│  │  - Used for answer validation        │                   │
│  └──────────────────────────────────────┘                   │
│                          ↓                                   │
│  Stage 2: Recursive Document Upload                         │
│  ┌──────────────────────────────────────┐                   │
│  │ ./lf datasets ingest fda_letters \   │                   │
│  │   /path/to/fda/**/*                  │                   │
│  │                                      │                   │
│  │ Uploads from all subdirectories:     │                   │
│  │  /fda/2023/Q1/*.pdf                  │                   │
│  │  /fda/2023/Q2/*.pdf                  │                   │
│  │  /fda/2024/emails/*.msg              │                   │
│  │  /fda/meeting_minutes/*.pdf          │                   │
│  └──────────────────────────────────────┘                   │
│                          ↓                                   │
│  Stage 3: Question Extraction (File by File)                │
│  ┌──────────────────────────────────────┐                   │
│  │ For each document:                   │                   │
│  │  1. Retrieve full doc from RAG       │                   │
│  │  2. LLM analyzes entire document     │                   │
│  │  3. Classify questions:              │                   │
│  │     - critical: regulatory           │                   │
│  │     - administrative: procedural     │                   │
│  │     - not_question: headers/refs     │                   │
│  │  4. Extract context and page refs    │                   │
│  └──────────────────────────────────────┘                   │
│                          ↓                                   │
│  Stage 4: Answer Validation (Recursive Verification)        │
│  ┌──────────────────────────────────────┐                   │
│  │ For each critical question:          │                   │
│  │  1. RAG search in chunked corpus     │                   │
│  │  2. LLM verifies answer validity     │                   │
│  │  3. Check completeness:              │                   │
│  │     - complete: fully answered       │                   │
│  │     - partial: missing info          │                   │
│  │     - incomplete: not answered       │                   │
│  │  4. If partial: recursive search     │                   │
│  │     with refined query               │                   │
│  │  5. Extract evidence citations       │                   │
│  └──────────────────────────────────────┘                   │
│                          ↓                                   │
│  Stage 5: Report Generation                                 │
│  ┌──────────────────────────────────────┐                   │
│  │ Output Files:                        │                   │
│  │  - batch_XXXXX_report.json          │                   │
│  │  - batch_XXXXX_report.csv           │                   │
│  │  - batch_state.json (progress)       │                   │
│  │                                      │                   │
│  │ Report Contents:                     │                   │
│  │  - High-level statistics             │                   │
│  │  - All questions with classification │                   │
│  │  - Answered questions with evidence  │                   │
│  │  - Unanswered questions list         │                   │
│  │  - Per-document breakdown            │                   │
│  └──────────────────────────────────────┘                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. **Services Running:**
   ```bash
   # Terminal 1 - Server
   nx start server

   # Terminal 2 - RAG Worker
   nx start rag

   # Terminal 3 - Agents Service
   nx start agents

   # Terminal 4 - Model (optional, if using Lemonade)
   LEMONADE_MODEL=user.Qwen3-4B-GGUF LEMONADE_PORT=11536 nx start lemonade
   ```

2. **Verify Health:**
   ```bash
   curl http://localhost:8000/health  # Server
   curl http://localhost:8003/health/ # Agents (note trailing slash)
   ```

---

## Step 1: Configure llamafarm.yaml

Update your project's `llamafarm.yaml` with dual databases and agent configurations:

```yaml
version: v1
name: fda-batch-demo
namespace: default

# Prompts (can be minimal since agents have their own system prompts)
prompts:
  - role: system
    content: You are an FDA regulatory compliance assistant.

# RAG Configuration - DUAL DATABASE STRATEGY
rag:
  # Database 1: Full Documents (for question extraction)
  databases:
    - name: fda_letters_full
      type: ChromaStore
      config:
        distance_function: cosine
        collection_name: fda_letters_complete
        port: 8000
      embedding_strategies:
        - name: default_embeddings
          type: OllamaEmbedder
          config:
            base_url: http://localhost:11434
            model: nomic-embed-text
            dimension: 768
            batch_size: 16
            timeout: 60
            auto_pull: true
          priority: 0
      retrieval_strategies:
        - name: full_doc_retrieval
          type: BasicSimilarityStrategy
          config:
            distance_metric: cosine
            top_k: 1
          default: true
      default_embedding_strategy: default_embeddings
      default_retrieval_strategy: full_doc_retrieval

    # Database 2: Chunked Corpus (for answer validation)
    - name: fda_corpus_chunked
      type: ChromaStore
      config:
        distance_function: cosine
        collection_name: fda_answers
        port: 8000
      embedding_strategies:
        - name: default_embeddings
          type: OllamaEmbedder
          config:
            base_url: http://localhost:11434
            model: nomic-embed-text
            dimension: 768
            batch_size: 16
            timeout: 60
            auto_pull: true
          priority: 0
      retrieval_strategies:
        - name: semantic_search
          type: BasicSimilarityStrategy
          config:
            distance_metric: cosine
            top_k: 10
          default: true
      default_embedding_strategy: default_embeddings
      default_retrieval_strategy: semantic_search

  # Processing Strategies
  data_processing_strategies:
    # Strategy 1: Full Document Processor (no chunking)
    - name: fda_full_document_processor
      description: Preserves complete FDA letters for question extraction
      parsers:
        - type: PDFParser_PyPDF2
          config:
            chunk_size: 50000
            chunk_overlap: 0
            chunk_strategy: paragraphs
            extract_metadata: true
            preserve_layout: true
            combine_pages: false
            extract_page_info: true
            clean_text: true
          file_include_patterns:
            - '*.pdf'
            - '*.PDF'
          priority: 100
        - type: TextParser_Python
          config:
            encoding: utf-8
            chunk_size: 50000
            chunk_overlap: 0
            chunk_strategy: sentences
            extract_metadata: true
          file_include_patterns:
            - '*.txt'
            - '*.msg'
            - '*.eml'
          priority: 100
      extractors:
        - type: ContentStatisticsExtractor
          config:
            include_structure: true
          file_include_patterns:
            - '*'
          priority: 100

    # Strategy 2: Chunked Processor (semantic search)
    - name: fda_chunked_processor
      description: Chunk documents for semantic answer search
      parsers:
        - type: PDFParser_PyPDF2
          config:
            chunk_size: 1500
            chunk_overlap: 200
            chunk_strategy: paragraphs
            extract_metadata: true
            preserve_layout: true
            extract_page_info: true
          file_include_patterns:
            - '*.pdf'
            - '*.PDF'
          priority: 100
        - type: TextParser_Python
          config:
            chunk_size: 1500
            chunk_overlap: 200
            chunk_strategy: sentences
            extract_metadata: true
          file_include_patterns:
            - '*.txt'
            - '*.msg'
            - '*.eml'
          priority: 100
      extractors:
        - type: KeywordExtractor
          config:
            algorithm: rake
            max_keywords: 15
          file_include_patterns:
            - '*'
          priority: 100
        - type: ContentStatisticsExtractor
          config:
            include_readability: true
          file_include_patterns:
            - '*'
          priority: 90

# Runtime Configuration (multi-model)
runtime:
  default_model: balanced

  models:
    - name: fast
      description: Fast Ollama model for quick responses
      provider: ollama
      model: gemma3:1b
      base_url: http://localhost:11434/v1
      prompt_format: unstructured

    - name: balanced
      description: Balanced Lemonade model for FDA analysis (4B)
      provider: lemonade
      model: user.Qwen3-4B-GGUF
      provider_config:
        backend: llamacpp
        port: 11536
        context_size: 32768
        auto_download: false

# Agent Configurations
agents:
  - name: fda_question_extractor
    type: fda_question_extractor
    model: balanced
    description: Extracts and classifies FDA questions from correspondence
    system_prompt: ""  # Agent has built-in prompt
    config:
      database: fda_letters_full
      min_confidence: 0.7
      extract_informal: true

  - name: fda_answer_validator
    type: fda_answer_validator
    model: balanced
    description: Validates FDA question answers with recursive verification
    system_prompt: ""  # Agent has built-in prompt
    config:
      database: fda_corpus_chunked
      retrieval_strategy: semantic_search
      top_k: 10
      confidence_threshold: 0.75
      max_recursion_depth: 2

  - name: fda_batch_orchestrator
    type: fda_batch_orchestrator
    model: balanced
    description: Batch processes 500+ FDA documents
    system_prompt: ""  # Agent has built-in prompt
    config:
      batch_size: 10
      output_path: /tmp/fda_batch
      resume_on_failure: true
      extractor_config:
        database: fda_letters_full
        min_confidence: 0.7
      validator_config:
        database: fda_corpus_chunked
        top_k: 10
        confidence_threshold: 0.75

# Datasets (will be created by setup script)
datasets: []
```

---

## Step 2: Create Datasets

Create both datasets using the CLI:

```bash
# Dataset 1: Full Documents (for question extraction)
./lf datasets add fda_letters \
  --strategy fda_full_document_processor \
  --database fda_letters_full

# Dataset 2: Chunked Corpus (for answer validation)
./lf datasets add fda_corpus \
  --strategy fda_chunked_processor \
  --database fda_corpus_chunked

# Verify datasets created
./lf datasets list
```

---

## Step 3: Upload Documents Recursively

Upload all FDA documents from nested directories:

```bash
# Upload all files from nested directories to fda_letters
# This handles: /fda/2023/Q1/*.pdf, /fda/2024/emails/*.msg, etc.
./lf datasets ingest fda_letters /path/to/fda/**/*

# Upload response documents to corpus
./lf datasets ingest fda_corpus /path/to/responses/**/*

# Check upload status
./lf datasets list
```

**Supported patterns:**
- `/**/*` - All files in all subdirectories
- `/**/*.pdf` - All PDFs in all subdirectories
- `/2023/**/*.pdf` - All PDFs under 2023 folder
- Mixed: `./emails/*.msg ./pdfs/**/*.pdf`

---

## Step 4: Process Documents into Vector Databases

Process uploaded files into embeddings:

```bash
# Process full documents
./lf datasets process fda_letters

# Process chunked corpus
./lf datasets process fda_corpus

# Monitor progress in Terminal 2 (RAG worker logs)
```

**Expected time:** ~2-3 minutes per 10 documents

---

## Step 5: Verify Databases

Test RAG queries to ensure databases are working:

```bash
# Query full documents database
./lf rag query --database fda_letters_full \
  "virus testing requirements" --top-k 2

# Query chunked corpus
./lf rag query --database fda_corpus_chunked \
  "virus testing requirements" --top-k 10
```

---

## Step 6: Run Batch Processing

Use the batch processing script (see next section) or manual API calls:

```bash
# Run batch processing script
./scripts/fda_batch_process.sh

# Or manually via API (see API section below)
```

---

## API Usage

### Extract Questions from Single Document

```bash
curl -X POST http://localhost:8003/v1/agents/run \
  -H "Content-Type: application/json" \
  -d '{
    "namespace": "default",
    "project": "fda-batch-demo",
    "agent_config": {
      "name": "fda_question_extractor",
      "type": "fda_question_extractor",
      "model": "balanced",
      "config": {
        "database": "fda_letters_full",
        "min_confidence": 0.7
      }
    },
    "project_config": {},
    "input_data": {
      "document_hash": "81abd139a97521c1e673d2b0c2bc9f701dd72d67",
      "document_name": "761240_2023_Letter.pdf"
    }
  }'
```

**Response:**
```json
{
  "agent_name": "fda_question_extractor",
  "status": "completed",
  "result": {
    "document_name": "761240_2023_Letter.pdf",
    "document_hash": "81abd139...",
    "questions": [
      {
        "question_text": "Provide virus testing results for UPB for every batch manufactured",
        "type": "critical",
        "context": "Manufacturing and viral contamination control",
        "page_reference": "3",
        "confidence": 0.95
      },
      {
        "question_text": "When is the submission due?",
        "type": "administrative",
        "context": "Timeline clarification",
        "page_reference": "1",
        "confidence": 0.85
      }
    ],
    "stats": {
      "total": 2,
      "critical": 1,
      "administrative": 1,
      "filtered_out": 0
    }
  }
}
```

### Validate Answers

```bash
curl -X POST http://localhost:8003/v1/agents/run \
  -H "Content-Type: application/json" \
  -d '{
    "namespace": "default",
    "project": "fda-batch-demo",
    "agent_config": {
      "name": "fda_answer_validator",
      "type": "fda_answer_validator",
      "model": "balanced",
      "config": {
        "database": "fda_corpus_chunked",
        "top_k": 10,
        "confidence_threshold": 0.75
      }
    },
    "project_config": {},
    "input_data": {
      "questions": [
        {
          "question_text": "Provide virus testing results for UPB",
          "type": "critical",
          "context": "Manufacturing"
        }
      ],
      "document_name": "761240_2023_Letter.pdf"
    }
  }'
```

**Response:**
```json
{
  "agent_name": "fda_answer_validator",
  "status": "completed",
  "result": {
    "document_name": "761240_2023_Letter.pdf",
    "validations": [
      {
        "question": "Provide virus testing results for UPB",
        "question_type": "critical",
        "source_document": "761240_2023_Letter.pdf",
        "context": "Manufacturing",
        "answered": true,
        "confidence": 0.92,
        "completeness": "complete",
        "validation_status": "validated",
        "evidence": [
          {
            "document": "761248_2024_Response.pdf",
            "page": "12",
            "excerpt": "UPB virus testing implemented for all batches per ICH Q5A..."
          }
        ],
        "summary": "Answer found in response document 761248_2024. Testing protocol described with batch-specific results.",
        "missing_info": []
      }
    ],
    "stats": {
      "total": 1,
      "answered": 1,
      "unanswered": 0,
      "high_confidence": 1
    }
  }
}
```

---

## Output Files

Batch processing generates:

### 1. Progress State (`/tmp/fda_batch/batch_state.json`)
```json
{
  "batch_id": "batch_1696800000",
  "total_documents": 500,
  "processed_documents": 234,
  "status": "running",
  "started_at": 1696800000,
  "updated_at": 1696850000
}
```

### 2. Final Report (`/tmp/fda_batch/batch_XXXXX_report.json`)
```json
{
  "batch_id": "batch_1696800000",
  "summary": {
    "total_documents": 500,
    "total_questions": 4850,
    "critical_questions": 3200,
    "administrative_questions": 1650,
    "answered_questions": 2400,
    "unanswered_questions": 800,
    "answer_rate": 75.0,
    "processing_time_minutes": 180.5
  },
  "all_questions": [ ... ],
  "answered_questions": [ ... ],
  "unanswered_questions": [ ... ],
  "document_details": [ ... ]
}
```

### 3. CSV Export (`/tmp/fda_batch/batch_XXXXX_report.csv`)
```csv
document_name,question_text,question_type,answered,confidence,completeness,evidence,summary
761240_2023.pdf,"Provide virus testing results",critical,true,0.92,complete,"761248_2024_Response.pdf p.12","Testing protocol described..."
761225_2024.pdf,"When is submission due?",administrative,false,0.0,skipped_administrative,"",""
```

---

## Performance Estimates (500 Documents)

| Stage | Time per Document | Total Time (500 docs) | With 3 Workers |
|-------|------------------|----------------------|----------------|
| Upload | 0.5 sec | 4 min | 4 min |
| Processing | 2 min | 1,000 min | 334 min (5.5 hrs) |
| Question Extraction | 15 sec | 125 min | 42 min |
| Answer Validation | 2 sec/question | 340 min (10 q/doc) | 115 min |
| **TOTAL** | | **1,469 min (24.5 hrs)** | **~8-10 hours** |

**Optimizations:**
- Batch processing reduces overhead
- Caching avoids duplicate RAG queries
- Administrative questions skipped in validation
- Parallel workers (3x speedup)

---

## Troubleshooting

### Issue: Documents not found in RAG

**Solution:** Verify dataset processed successfully
```bash
./lf datasets list
./lf rag query --database fda_letters_full "test" --top-k 1
```

### Issue: Agent timeout

**Solution:** Increase timeout in agents service settings
```bash
# In agents/.env
AGENTS_AGENT_TIMEOUT=600
```

### Issue: Out of memory

**Solution:** Reduce batch size in agent config
```yaml
agents:
  - name: fda_batch_orchestrator
    config:
      batch_size: 5  # Reduce from 10
```

### Issue: Resume after failure

**Solution:** Use batch ID to resume
```bash
# Find batch ID in /tmp/fda_batch/batch_state.json
# Then resume via API or script
```

---

## Key Differences from Standard RAG

1. **Dual Database Strategy:**
   - Full docs DB: Complete documents for context-aware question extraction
   - Chunked DB: Semantic search optimized for answer finding

2. **Recursive Verification:**
   - Not just "related content"
   - LLM validates answer actually addresses question
   - Refines search if answer is partial

3. **Question Classification:**
   - Critical: Regulatory questions requiring formal responses
   - Administrative: Procedural/timeline questions
   - Not questions: Headers, references, greetings

4. **Evidence Requirements:**
   - Must reference specific documents
   - Must include page numbers
   - Must have excerpt showing actual answer

---

## Next Steps

1. Review and update `llamafarm.yaml` configuration
2. Run setup script to create datasets
3. Upload documents from all nested directories
4. Process documents into vector databases
5. Run batch processing on small test set (10 docs)
6. Review output quality
7. Run full batch (500+ docs)
8. Export results to CSV for analysis

---

## Related Documentation

- [Batch Processing Strategy](/Users/robthelen/rgthelen-thoughts/BATCH-PROCESSING-STRATEGY.md)
- [Agent Demo Guide](/Users/robthelen/rgthelen-thoughts/AGENT-DEMO-GUIDE.md)
- [RAG Configuration](docs/website/docs/rag/index.md)
- [Multi-Model Configuration](docs/website/docs/configuration/index.md)
