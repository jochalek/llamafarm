---
title: RAG Guide
sidebar_position: 6
---

# RAG Guide

LlamaFarm treats retrieval-augmented generation as a first-class, configurable pipeline. This guide explains how strategies, databases, and datasets fit together—and how to operate and extend them.

## RAG at a Glance

| Piece | Where it lives | Purpose |
| ----- | -------------- | ------- |
| `rag.databases[]` | `llamafarm.yaml` | Define vector stores and retrieval strategies. |
| `rag.data_processing_strategies[]` | `llamafarm.yaml` | Describe parsers, extractors, and metadata processors for ingestion. |
| `lf datasets create/upload/process` | CLI | Ingest documents according to the chosen strategy/database. |
| `lf rag query` | CLI | Query the store with semantic, hybrid, or metadata-aware retrieval. |
| Celery workers | Server runtime | Perform heavy ingestion tasks. |

## Configure Databases

Each database entry declares a store type (default `ChromaStore` or `QdrantStore`) and the embedding/retrieval strategies available.

```yaml
rag:
  databases:
    - name: main_db
      type: ChromaStore
      default_embedding_strategy: default_embeddings
      default_retrieval_strategy: semantic_search
      embedding_strategies:
        - name: default_embeddings
          type: OllamaEmbedder
          config:
            model: nomic-embed-text:latest
      retrieval_strategies:
        - name: semantic_search
          type: BasicSimilarityStrategy
          config:
            top_k: 5
            distance_metric: cosine
        - name: hybrid_search
          type: HybridUniversalStrategy
          config:
            combination_method: weighted_average
            final_k: 10
```

**Available Retrieval Strategy Types:**

| Strategy | Description | Best For |
|----------|-------------|----------|
| `BasicSimilarityStrategy` | Fast vector similarity search | Simple queries, prototyping |
| `MetadataFilteredStrategy` | Vector search with metadata filtering | Multi-tenant, filtered search |
| `MultiQueryStrategy` | Expands query into variations | Ambiguous queries, better recall |
| `HybridUniversalStrategy` | Combines multiple strategies | Balanced precision/recall |
| `CrossEncoderRerankedStrategy` | Two-stage retrieval with reranking | High accuracy requirements |
| `MultiTurnRAGStrategy` | Query decomposition for complex questions | Complex multi-part queries |

- Add multiple strategies for different workloads (semantic, filtered, reranked).
- Set `default_*` fields to control CLI defaults.
- Extend store/types by editing `rag/schema.yaml` and following the [Extending guide](../extending/index.md#extend-rag-components).

## Define Processing Strategies

Processing strategies control how files become chunks in the vector store.

```yaml
rag:
  data_processing_strategies:
    - name: pdf_ingest
      description: Ingest FDA letters with headings & stats.
      parsers:
        - type: PDFParser_LlamaIndex
          config:
            chunk_size: 1500
            chunk_overlap: 200
            preserve_layout: true
      extractors:
        - type: HeadingExtractor
        - type: ContentStatisticsExtractor
        - type: EntityExtractor
          config:
            entity_types: [PERSON, ORG, GPE, DATE]
```

**Available Parser Types:**

| Parser | File Types | Description |
|--------|------------|-------------|
| `PDFParser_PyPDF2` | `.pdf` | Enhanced PDF parsing with PyPDF2 |
| `PDFParser_LlamaIndex` | `.pdf` | Advanced PDF with multiple fallback strategies |
| `CSVParser_Pandas` | `.csv` | CSV with Pandas data analysis |
| `CSVParser_Python` | `.csv` | Simple native Python CSV parsing |
| `ExcelParser_OpenPyXL` | `.xlsx`, `.xls` | Excel with formula support |
| `ExcelParser_Pandas` | `.xlsx`, `.xls` | Excel with data analysis |
| `DocxParser_PythonDocx` | `.docx` | Word document parsing |
| `DocxParser_LlamaIndex` | `.docx` | Advanced DOCX with semantic chunking |
| `MarkdownParser_Python` | `.md` | Markdown with regex parsing |
| `MarkdownParser_LlamaIndex` | `.md` | Advanced markdown with semantic chunking |
| `TextParser_Python` | `.txt` | Text with encoding detection |
| `TextParser_LlamaIndex` | `.txt` | Advanced text with semantic splitting |
| `MsgParser_ExtractMsg` | `.msg` | Outlook email message parsing |

**Available Extractor Types:**

| Extractor | Description |
|-----------|-------------|
| `HeadingExtractor` | Extract document headings and hierarchy |
| `ContentStatisticsExtractor` | Calculate readability, vocabulary, structure metrics |
| `EntityExtractor` | Extract named entities (people, organizations, dates) |
| `KeywordExtractor` | Extract keywords using RAKE, YAKE, or TF-IDF |
| `DateTimeExtractor` | Extract and normalize dates and times |
| `LinkExtractor` | Extract URLs, emails, and domains |
| `PathExtractor` | Extract file paths and S3 paths |
| `PatternExtractor` | Extract patterns (emails, phones, IPs, credit cards) |
| `SummaryExtractor` | Generate extractive summaries |
| `TableExtractor` | Extract and parse tables |
| `YAKEExtractor` | YAKE keyword extraction |
| `RAKEExtractor` | RAKE keyword extraction |
| `TFIDFExtractor` | TF-IDF keyword extraction |

- Parsers handle format-aware chunking (PDF, CSV, DOCX, Markdown, text).
- Extractors add metadata (entities, headings, statistics) to each chunk.
- Customize chunk size/overlap per parser type.

## Dataset Lifecycle

1. **Create** a dataset referencing a strategy and database.
   ```bash
   lf datasets create -s pdf_ingest -b main_db research-notes
   ```
2. **Upload** files via `lf datasets upload` (supports globs and directories). The CLI stores file hashes for dedupe.
3. **Process** documents with `lf datasets process research-notes`. The server schedules a Celery job; monitor progress in the CLI output and server logs.
4. **Query** with `lf rag query` to validate retrieval quality.

## Querying & Retrieval Strategies

`lf rag query` exposes several toggles:

- `--retrieval-strategy` to select among those defined in the database.
- `--filter "key:value"` for metadata filtering (e.g., `doc_type:letter`, `year:2024`).
- `--top-k`, `--score-threshold`, `--include-metadata`, `--include-score` for result tuning.
- `--distance-metric`, `--hybrid-alpha`, `--rerank-model`, `--query-expansion` for advanced workflows.

Pair queries with `lf chat` to confirm the runtime consumes retrieved context correctly.

### Advanced Retrieval Strategies

For improved accuracy and handling of complex queries, LlamaFarm supports:

- **Cross-Encoder Reranking** - Rerank initial candidates using specialized models (10-100x faster than LLM reranking)
- **Multi-Turn RAG** - Decompose complex queries into sub-queries, retrieve in parallel, and merge results

See [Advanced Retrieval Strategies](./advanced-retrieval.md) for detailed configuration and usage.

## Monitoring & Maintenance

- `lf rag stats` – view vector counts and storage usage.
- `lf rag health` – check embedder/store health status.
- `lf rag list` – inspect documents and metadata.
- `lf rag compact` / `lf rag reindex` – maintain store performance.
- `lf rag clear` / `lf rag delete` – remove data (dangerous; confirm before use).

## Troubleshooting

| Symptom | Possible Cause | Fix |
| ------- | -------------- | ---- |
| `No response received` after `lf chat` | Runtime returned empty stream (model mismatch, tool support) | Try `--no-rag`, switch models, or adjust agent handler. |
| `Task timed out or failed: PENDING` during processing | Celery worker still ingesting large files | Wait and re-run, check worker logs, ensure enough resources. |
| Query returns 0 results | Incorrect strategy/database, unprocessed dataset, high score threshold | Verify dataset processed successfully, adjust `--score-threshold`. |

## Next Steps

- [CLI Reference](../cli/index.md) – command usage.
- [Extending RAG](../extending/index.md#extend-rag-components) – add stores/parsers.
- [Examples](../examples/index.md) – see FDA and Raleigh workflows.
