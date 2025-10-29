"""
File Processing Metadata Service

Updates file metadata with last processing information.
Stores processing status directly in lf_data/meta/{hash}.json for fast lookups.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class FileProcessingMetadata:
    """
    Service for updating file metadata with last processing information.

    Extends the existing metadata format with a 'last_processed' field:
    {
        "original_file_name": "document.pdf",
        "hash": "abc123...",
        ...existing fields...,
        "last_processed": {
            "timestamp": "2025-10-28T17:47:31.232936",
            "dataset": "my_dataset",
            "database": "main_database",
            "strategy": "universal_processor",
            "status": "processed",  // or "skipped", "failed"
            "reason": "duplicate",  // optional, if skipped/failed
            "chunks_created": 16,
            "chunks_stored": 16,
            "chunks_skipped": 0,
            "parser": "PDFParser_LlamaIndex",
            "embedder": "OllamaEmbedder"
        }
    }
    """

    @staticmethod
    def update_file_metadata(
        project_dir: str,
        file_hash: str,
        dataset: str,
        database: str,
        strategy: str,
        status: str,  # "processed", "skipped", "failed"
        chunks_created: int = 0,
        chunks_stored: int = 0,
        chunks_skipped: int = 0,
        parser: Optional[str] = None,
        embedder: Optional[str] = None,
        reason: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Update file metadata with last processing information.

        Args:
            project_dir: Path to project directory
            file_hash: File content hash
            dataset: Dataset name
            database: Vector database name
            strategy: Processing strategy name
            status: Processing status (processed, skipped, failed)
            chunks_created: Number of chunks created
            chunks_stored: Number of chunks stored in vector DB
            chunks_skipped: Number of chunks skipped
            parser: Parser used
            embedder: Embedder used
            reason: Reason if skipped/failed
            timestamp: ISO timestamp (defaults to now)

        Returns:
            True if update succeeded, False otherwise
        """
        meta_path = Path(project_dir) / "lf_data" / "meta" / f"{file_hash}.json"

        if not meta_path.exists():
            logger.warning(f"Metadata file not found: {meta_path}")
            return False

        try:
            # Read existing metadata
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # Add/update last_processed field
            metadata['last_processed'] = {
                'timestamp': timestamp or datetime.now().isoformat(),
                'dataset': dataset,
                'database': database,
                'strategy': strategy,
                'status': status,
                'chunks_created': chunks_created,
                'chunks_stored': chunks_stored,
                'chunks_skipped': chunks_skipped,
            }

            # Add optional fields
            if parser:
                metadata['last_processed']['parser'] = parser
            if embedder:
                metadata['last_processed']['embedder'] = embedder
            if reason:
                metadata['last_processed']['reason'] = reason

            # Write back atomically
            temp_path = meta_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            temp_path.replace(meta_path)

            logger.info(
                f"Updated file metadata with last_processed",
                extra={
                    'file_hash': file_hash[:16],
                    'status': status,
                    'dataset': dataset,
                }
            )
            return True

        except Exception as e:
            logger.error(f"Failed to update file metadata: {e}", exc_info=True)
            return False

    @staticmethod
    def get_last_processed(
        project_dir: str,
        file_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get last processing information from file metadata.

        Args:
            project_dir: Path to project directory
            file_hash: File content hash

        Returns:
            Last processed info dict or None if not found
        """
        meta_path = Path(project_dir) / "lf_data" / "meta" / f"{file_hash}.json"

        if not meta_path.exists():
            return None

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return metadata.get('last_processed')
        except Exception as e:
            logger.warning(f"Failed to read file metadata: {e}")
            return None

    @staticmethod
    def get_files_by_status(
        project_dir: str,
        file_hashes: list[str],
        status: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get processing status for multiple files.

        Args:
            project_dir: Path to project directory
            file_hashes: List of file hashes to check
            status: Optional status filter ("processed", "skipped", "failed")

        Returns:
            Dict mapping file_hash to last_processed info
        """
        results = {}

        for file_hash in file_hashes:
            last_processed = FileProcessingMetadata.get_last_processed(
                project_dir, file_hash
            )

            if last_processed:
                # Filter by status if specified
                if status is None or last_processed.get('status') == status:
                    results[file_hash] = last_processed

        return results

    @staticmethod
    def get_dataset_file_statuses(
        project_dir: str,
        dataset: str,
        file_hashes: list[str]
    ) -> Dict[str, str]:
        """
        Get status of all files in a dataset (for quick dashboard display).

        Args:
            project_dir: Path to project directory
            dataset: Dataset name to filter by
            file_hashes: List of file hashes in the dataset

        Returns:
            Dict mapping file_hash to status string
        """
        statuses = {}

        for file_hash in file_hashes:
            last_processed = FileProcessingMetadata.get_last_processed(
                project_dir, file_hash
            )

            if last_processed and last_processed.get('dataset') == dataset:
                statuses[file_hash] = last_processed.get('status', 'unknown')
            else:
                statuses[file_hash] = 'pending'

        return statuses
