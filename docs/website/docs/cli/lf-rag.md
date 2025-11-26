---
title: lf rag
sidebar_position: 5
---

# `lf rag`

Query your knowledge base and access RAG maintenance utilities.

## Querying Documents

```
lf rag query "question" [flags]
```

### Basic Flags

| Flag | Purpose |
| ---- | ------- |
| `--database` | Select a database (defaults to config default). |
| `--retrieval-strategy` | Override retrieval strategy (see below). |
| `--top-k` | Number of chunks to return (default: 5). |
| `--score-threshold` | Minimum similarity score (0.0-1.0). |
| `--filter` | Apply metadata filters (`key:value`). Repeatable. |
| `--include-metadata` | Show metadata columns in output. |
| `--include-score` | Show similarity scores in output. |

### Advanced Flags

| Flag | Purpose |
| ---- | ------- |
| `--distance-metric` | Distance metric: `cosine`, `euclidean`, `manhattan`, `dot`. |
| `--max-tokens` | Maximum tokens in combined results. |

### Available Retrieval Strategies

| Strategy Name | Description |
| ------------- | ----------- |
| `BasicSimilarityStrategy` | Fast vector similarity search |
| `MetadataFilteredStrategy` | Vector search with metadata filtering |
| `MultiQueryStrategy` | Query expansion with multiple variations |
| `HybridUniversalStrategy` | Combines multiple strategies |
| `CrossEncoderRerankedStrategy` | Two-stage retrieval with cross-encoder reranking |
| `MultiTurnRAGStrategy` | Query decomposition for complex queries |

### Examples

```bash
# Basic query
lf rag query --database main_db "What is machine learning?"

# With metadata filtering
lf rag query --database main_db --filter "doc_type:letter" --include-metadata \
  "Which letters mention additional clinical trials?"

# Use a specific retrieval strategy
lf rag query --database main_db --retrieval-strategy CrossEncoderRerankedStrategy \
  "What are the key findings?"

# Adjust results
lf rag query --database main_db --top-k 10 --score-threshold 0.7 \
  "Summarize the main conclusions"
```

## Maintenance Commands

Some subcommands are hidden from `--help` but available for operators:

| Command | Description |
| ------- | ----------- |
| `lf rag stats` | Vector/document counts, storage usage (JSON or table). |
| `lf rag health` | Embedder/store health summary. |
| `lf rag list` | List ingested documents and metadata. |
| `lf rag compact` | Compact/optimize the vector store. |
| `lf rag reindex` | Reindex all documents using a given strategy. |
| `lf rag clear` | Delete **all** documents from a database (dangerous). |
| `lf rag delete` | Remove documents by ID, filename, or metadata filter. |
| `lf rag export/import` | Move datasets between environments. |

> ⚠️ Destructive commands (`clear`, `delete`) prompt for confirmation unless you pass `--force`.

## Troubleshooting

- **Empty results** – confirm dataset processing succeeded and the retrieval strategy matches your query type.
- **Timeouts** – large datasets can take time to process; check Celery logs or increase `--server-start-timeout` before retrying.
- **Hybrid/Tool Errors** – some smaller models don’t support tool calls; switch to a basic agent handler via configuration.

## See Also

- [RAG Guide](../rag/index.md)
- [Extending RAG](../extending/index.md#extend-rag-components)
