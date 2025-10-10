# FDA Document Analysis Agents

## Overview

The FDA agents system automatically analyzes FDA correspondence to extract questions/requests and validate if they've been answered in your response documents.

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

## Usage

### Via CLI
```bash
# Run batch processing
./scripts/fda_batch_process.sh

# Or via agents API
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
