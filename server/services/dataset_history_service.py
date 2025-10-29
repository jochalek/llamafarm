"""
Dataset History Service

Provides a unified interface for querying file processing status and history.
Combines metadata lookups (fast O(1) for current status) with log parsing (for historical runs).
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from services.processing_log_reader import ProcessingLogReader
from services.file_processing_metadata import FileProcessingMetadata

logger = logging.getLogger(__name__)


class DatasetHistoryService:
    """
    Unified service for dataset processing history and file status.

    Strategy:
    1. For file status: Read from metadata (fast O(1) lookup)
    2. For processing history: Read from logs (on-demand)
    3. For detailed file info: Combine both sources
    """

    @staticmethod
    def get_file_status(project_dir: str, file_hash: str, dataset: str) -> Dict[str, Any]:
        """
        Get current processing status for a file.

        Reads from metadata for fast O(1) lookup.

        Args:
            project_dir: Path to project directory
            file_hash: File content hash
            dataset: Dataset name (for filtering)

        Returns:
            File status dict with last_processed info, or empty if never processed
        """
        last_processed = FileProcessingMetadata.get_last_processed(project_dir, file_hash)

        if not last_processed:
            return {
                "file_hash": file_hash,
                "status": "pending",
                "last_processed": None,
                "dataset": None,
                "database": None,
            }

        # Filter by dataset if specified
        if dataset and last_processed.get("dataset") != dataset:
            return {
                "file_hash": file_hash,
                "status": "pending",
                "last_processed": None,
                "dataset": None,
                "database": None,
            }

        return {
            "file_hash": file_hash,
            "status": last_processed.get("status", "unknown"),
            "last_processed": last_processed.get("timestamp"),
            "dataset": last_processed.get("dataset"),
            "database": last_processed.get("database"),
            "strategy": last_processed.get("strategy"),
            "chunks_created": last_processed.get("chunks_created", 0),
            "chunks_stored": last_processed.get("chunks_stored", 0),
            "chunks_skipped": last_processed.get("chunks_skipped", 0),
            "parser": last_processed.get("parser"),
            "embedder": last_processed.get("embedder"),
            "reason": last_processed.get("reason"),
        }

    @staticmethod
    def get_dataset_file_statuses(
        project_dir: str,
        dataset: str,
        file_hashes: List[str]
    ) -> Dict[str, str]:
        """
        Get status for all files in a dataset (for dashboard display).

        Args:
            project_dir: Path to project directory
            dataset: Dataset name
            file_hashes: List of file hashes in the dataset

        Returns:
            Dict mapping file_hash -> status string
        """
        return FileProcessingMetadata.get_dataset_file_statuses(
            project_dir, dataset, file_hashes
        )

    @staticmethod
    def get_dataset_processing_history(
        project_dir: str,
        dataset: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get processing history for a dataset (list of runs).

        Reads from log files on-demand.

        Args:
            project_dir: Path to project directory
            dataset: Dataset name
            limit: Maximum number of runs to return

        Returns:
            List of run summaries (most recent first)
        """
        return ProcessingLogReader.get_dataset_history(project_dir, dataset, limit)

    @staticmethod
    def get_dataset_info(
        project_dir: str,
        dataset: str,
        file_hashes: List[str],
        history_limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get comprehensive dataset information combining file status and history.

        Args:
            project_dir: Path to project directory
            dataset: Dataset name
            file_hashes: List of file hashes in the dataset
            history_limit: Max processing runs to include

        Returns:
            Comprehensive dataset info dict
        """
        # Get file statuses from metadata (fast)
        file_statuses = DatasetHistoryService.get_dataset_file_statuses(
            project_dir, dataset, file_hashes
        )

        # Count by status
        processed = sum(1 for s in file_statuses.values() if s == "processed")
        failed = sum(1 for s in file_statuses.values() if s == "failed")
        skipped = sum(1 for s in file_statuses.values() if s == "skipped")
        pending = sum(1 for s in file_statuses.values() if s == "pending")

        # Get processing history from logs (on-demand)
        processing_history = DatasetHistoryService.get_dataset_processing_history(
            project_dir, dataset, history_limit
        )

        return {
            "files": {
                "total": len(file_hashes),
                "processed": processed,
                "failed": failed,
                "skipped": skipped,
                "pending": pending,
            },
            "processing_history": processing_history,
            "file_statuses": file_statuses if len(file_hashes) < 100 else {},  # Omit for large datasets
        }

    @staticmethod
    def get_file_history(
        project_dir: str,
        file_hash: str,
        dataset: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get processing history for a specific file across all runs.

        Args:
            project_dir: Path to project directory
            file_hash: File hash to search for
            dataset: Optional dataset name to filter by

        Returns:
            List of processing events for this file
        """
        return ProcessingLogReader.get_file_history(project_dir, file_hash, dataset)

    @staticmethod
    def update_file_processing_status(
        project_dir: str,
        file_hash: str,
        dataset: str,
        database: str,
        strategy: str,
        status: str,
        chunks_created: int = 0,
        chunks_stored: int = 0,
        chunks_skipped: int = 0,
        parser: Optional[str] = None,
        embedder: Optional[str] = None,
        reason: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Update file metadata with processing result.

        This should be called after each file processing completes.

        Args:
            project_dir: Path to project directory
            file_hash: File content hash
            dataset: Dataset name
            database: Vector database name
            strategy: Processing strategy name
            status: Processing status (processed, skipped, failed)
            chunks_created: Number of chunks created
            chunks_stored: Number of chunks stored
            chunks_skipped: Number of chunks skipped
            parser: Parser used
            embedder: Embedder used
            reason: Reason if skipped/failed
            timestamp: ISO timestamp (defaults to now)

        Returns:
            True if update succeeded, False otherwise
        """
        return FileProcessingMetadata.update_file_metadata(
            project_dir=project_dir,
            file_hash=file_hash,
            dataset=dataset,
            database=database,
            strategy=strategy,
            status=status,
            chunks_created=chunks_created,
            chunks_stored=chunks_stored,
            chunks_skipped=chunks_skipped,
            parser=parser,
            embedder=embedder,
            reason=reason,
            timestamp=timestamp,
        )

    @staticmethod
    def get_logs_directory(project_dir: str) -> Path:
        """Get the logs directory path."""
        return ProcessingLogReader.get_logs_directory(project_dir)

    @staticmethod
    def list_log_files(project_dir: str, dataset: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all processing log files.

        Args:
            project_dir: Path to project directory
            dataset: Optional dataset name to filter by

        Returns:
            List of log file info dicts with name, path, size, modified time
        """
        logs_dir = ProcessingLogReader.get_logs_directory(project_dir)

        if not logs_dir.exists():
            return []

        log_files = list(logs_dir.glob("processing_*.json"))
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        results = []
        for log_file in log_files:
            # Check if this log is for the requested dataset
            if dataset:
                log_data = ProcessingLogReader.read_log_file(log_file)
                if not log_data or log_data.get("session", {}).get("dataset") != dataset:
                    continue

            stat = log_file.stat()
            results.append({
                "filename": log_file.name,
                "path": str(log_file.relative_to(project_dir)),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return results

    @staticmethod
    def get_log_file_content(project_dir: str, log_filename: str) -> Optional[Dict[str, Any]]:
        """
        Read a specific log file by filename.

        Args:
            project_dir: Path to project directory
            log_filename: Name of the log file (e.g., "processing_20250115_143000_my_dataset.json")

        Returns:
            Parsed log data or None if not found
        """
        log_path = Path(project_dir) / "lf_data" / "logs" / log_filename

        if not log_path.exists():
            logger.warning(f"Log file not found: {log_path}")
            return None

        return ProcessingLogReader.read_log_file(log_path)
