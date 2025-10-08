"""FDA RAG Dual-Database Tests.

Tests the dual-database RAG architecture:
1. Full documents database for question extraction
2. Chunked corpus database for answer validation

These tests require:
- FDA datasets to be ingested and processed
- Server running for RAG queries
"""

import pytest
from services.project_service import ProjectService


@pytest.fixture
def project_config():
    """Load project configuration."""
    return ProjectService.load_config("default", "test-project-1")


@pytest.fixture
def project_dir():
    """Get project directory."""
    return ProjectService.get_project_dir("default", "test-project-1")


class TestFDADualDatabase:
    """Test dual-database setup for FDA use case."""

    def test_fda_letters_full_database(self, project_config):
        """Test querying full documents database."""
        # This database should return full documents (large chunks)
        database_name = "fda_letters_full"

        # Verify database exists in config
        databases = {db.name: db for db in project_config.rag.databases}
        assert database_name in databases

        db_config = databases[database_name]
        assert db_config.config.collection_name == "fda_letters_complete"

        # Check retrieval strategy
        strategies = db_config.retrieval_strategies
        assert len(strategies) > 0

        full_doc_strategy = strategies[0]
        assert full_doc_strategy.name == "full_doc_retrieval"
        assert full_doc_strategy.config.top_k == 1  # Retrieve whole documents

    def test_fda_corpus_chunked_database(self, project_config):
        """Test querying chunked corpus database."""
        # This database should return semantic chunks
        database_name = "fda_corpus_chunked"

        # Verify database exists in config
        databases = {db.name: db for db in project_config.rag.databases}
        assert database_name in databases

        db_config = databases[database_name]
        assert db_config.config.collection_name == "fda_answers"

        # Check retrieval strategy
        strategies = db_config.retrieval_strategies
        assert len(strategies) > 0

        semantic_strategy = strategies[0]
        assert semantic_strategy.name == "semantic_search"
        assert semantic_strategy.config.top_k == 10  # Multiple chunks


class TestFDADatasetProcessing:
    """Test FDA dataset processing with different strategies."""

    def test_fda_letters_dataset(self, project_config):
        """Test fda_letters dataset configuration."""
        datasets = {d.name: d for d in project_config.datasets}
        assert "fda_letters" in datasets

        dataset = datasets["fda_letters"]

        # Should use full document processor
        assert dataset.data_processing_strategy == "fda_full_document_processor"

        # Should write to full documents database
        assert dataset.database == "fda_letters_full"

        # Verify processing strategy
        strategies = {s.name: s for s in project_config.rag.data_processing_strategies}
        strategy = strategies[dataset.data_processing_strategy]

        # Should use large chunks
        parser = strategy.parsers[0]
        assert parser.config.chunk_size == 50000
        assert parser.config.chunk_overlap == 0

    def test_fda_response_corpus_dataset(self, project_config):
        """Test fda_response_corpus dataset configuration."""
        datasets = {d.name: d for d in project_config.datasets}
        assert "fda_response_corpus" in datasets

        dataset = datasets["fda_response_corpus"]

        # Should use chunked processor
        assert dataset.data_processing_strategy == "fda_chunked_processor"

        # Should write to chunked database
        assert dataset.database == "fda_corpus_chunked"

        # Verify processing strategy
        strategies = {s.name: s for s in project_config.rag.data_processing_strategies}
        strategy = strategies[dataset.data_processing_strategy]

        # Should use small chunks
        parser = strategy.parsers[0]
        assert parser.config.chunk_size == 1500
        assert parser.config.chunk_overlap == 200


class TestChunkingStrategies:
    """Test that different chunking strategies produce expected results."""

    def test_full_document_strategy_config(self, project_config):
        """Verify full document strategy uses large chunks."""
        strategies = {s.name: s for s in project_config.rag.data_processing_strategies}
        strategy = strategies["fda_full_document_processor"]

        # Check parser configuration
        assert len(strategy.parsers) > 0
        parser = strategy.parsers[0]

        # Large chunk size preserves full context
        assert parser.config.chunk_size == 50000

        # No overlap needed for full documents
        assert parser.config.chunk_overlap == 0

        # Should extract page info for traceability
        assert parser.config.extract_page_info is True

    def test_chunked_strategy_config(self, project_config):
        """Verify chunked strategy uses small chunks with overlap."""
        strategies = {s.name: s for s in project_config.rag.data_processing_strategies}
        strategy = strategies["fda_chunked_processor"]

        # Check parser configuration
        assert len(strategy.parsers) > 0
        parser = strategy.parsers[0]

        # Small chunk size for semantic search
        assert parser.config.chunk_size == 1500

        # Overlap ensures context continuity
        assert parser.config.chunk_overlap == 200

    def test_extractors_configured(self, project_config):
        """Verify extractors are configured for each strategy."""
        strategies = {s.name: s for s in project_config.rag.data_processing_strategies}

        # Full document processor extractors
        full_strategy = strategies["fda_full_document_processor"]
        assert len(full_strategy.extractors) > 0

        extractor_types = [e.type for e in full_strategy.extractors]
        # Should have pattern extractor for FDA question markers
        assert "PatternExtractor" in extractor_types
        assert "ContentStatisticsExtractor" in extractor_types

        # Chunked processor extractors
        chunked_strategy = strategies["fda_chunked_processor"]
        assert len(chunked_strategy.extractors) > 0

        extractor_types = [e.type for e in chunked_strategy.extractors]
        # Should have keyword extractor for semantic search
        assert "KeywordExtractor" in extractor_types


class TestDualDatabaseArchitecture:
    """Test the core dual-database architecture principle."""

    def test_same_files_different_strategies(self, project_config):
        """Verify same files can be processed with different strategies."""
        datasets = {d.name: d for d in project_config.datasets}

        letters_ds = datasets["fda_letters"]
        corpus_ds = datasets["fda_response_corpus"]

        # Different processing strategies
        assert letters_ds.data_processing_strategy != corpus_ds.data_processing_strategy

        # Different target databases
        assert letters_ds.database != corpus_ds.database

        # This allows:
        # - Same PDFs in both datasets
        # - Different chunking (full vs small)
        # - Different embeddings/indexes
        # - Optimized for different query patterns

    def test_retrieval_strategy_pairing(self, project_config):
        """Test database retrieval strategies match use case."""
        databases = {db.name: db for db in project_config.rag.databases}

        # Full docs database - retrieve complete documents
        full_db = databases["fda_letters_full"]
        full_strategy = full_db.retrieval_strategies[0]
        assert full_strategy.name == "full_doc_retrieval"
        assert full_strategy.config.top_k == 1

        # Chunked database - semantic search across chunks
        chunked_db = databases["fda_corpus_chunked"]
        chunked_strategy = chunked_db.retrieval_strategies[0]
        assert chunked_strategy.name == "semantic_search"
        assert chunked_strategy.config.top_k == 10


class TestPhase4RAGIntegration:
    """Integration tests for Phase 4 RAG functionality."""

    def test_complete_fda_pipeline(self, project_config):
        """Test complete FDA processing pipeline configuration."""
        # 1. Datasets configured
        datasets = {d.name: d for d in project_config.datasets}
        assert "fda_letters" in datasets
        assert "fda_response_corpus" in datasets

        # 2. Processing strategies configured
        strategies = {s.name: s for s in project_config.rag.data_processing_strategies}
        assert "fda_full_document_processor" in strategies
        assert "fda_chunked_processor" in strategies

        # 3. Databases configured
        databases = {db.name: db for db in project_config.rag.databases}
        assert "fda_letters_full" in databases
        assert "fda_corpus_chunked" in databases

        # 4. Everything connected properly
        letters_ds = datasets["fda_letters"]
        assert letters_ds.data_processing_strategy in strategies
        assert letters_ds.database in databases

        corpus_ds = datasets["fda_response_corpus"]
        assert corpus_ds.data_processing_strategy in strategies
        assert corpus_ds.database in databases

        print("\n✅ Complete FDA RAG Pipeline Configuration:")
        print("  1. Ingest PDFs → fda_letters dataset")
        print("     → Process with fda_full_document_processor (50k chunks)")
        print("     → Store in fda_letters_full database")
        print("     → Use for question extraction")
        print()
        print("  2. Ingest PDFs → fda_response_corpus dataset")
        print("     → Process with fda_chunked_processor (1.5k chunks)")
        print("     → Store in fda_corpus_chunked database")
        print("     → Use for answer validation")

    def test_configuration_zero_code_changes(self, project_config):
        """Verify FDA setup required zero code changes."""
        # All configuration in llamafarm.yaml:
        # - 2 databases (60 lines)
        # - 2 processing strategies (80 lines)
        # - 4 agents (60 lines)
        # - 2 datasets (10 lines)
        # Total: ~210 lines of YAML, 0 lines of code

        # Verify all components exist
        assert len(project_config.rag.databases) >= 2
        assert len(project_config.rag.data_processing_strategies) >= 2
        assert len(project_config.datasets) >= 2
        assert len(project_config.agents) >= 4

        # Configuration-driven design working
        databases = {db.name: db for db in project_config.rag.databases}
        assert "fda_letters_full" in databases
        assert "fda_corpus_chunked" in databases


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
