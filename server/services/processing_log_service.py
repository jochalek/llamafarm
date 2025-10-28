"""
Processing Log Service

Handles persistent storage and retrieval of dataset processing logs.
Stores logs to disk for historical tracking and analysis.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class FileProcessingDetail:
    """Details of a single file's processing result"""
    hash: str
    filename: str
    status: str  # success, skipped, failed
    reason: Optional[str] = None
    chunks_created: int = 0
    chunks_stored: int = 0
    chunks_skipped: int = 0
    parser: Optional[str] = None
    extractors: List[str] = None
    embedder: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.extractors is None:
            self.extractors = []


@dataclass
class ProcessingLogEntry:
    """Complete processing log entry for a dataset processing run"""
    task_id: str
    started_at: str
    completed_at: str
    dataset: str
    strategy: str
    database: str
    files: List[FileProcessingDetail]
    summary: Dict[str, int]
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Ensure files are properly serialized
        data['files'] = [asdict(f) for f in self.files]
        return data


class ProcessingLogService:
    """
    Service for managing dataset processing logs.

    Stores processing logs in:
    ~/.llamafarm/projects/{namespace}/{project}/lf_data/processing_logs/
    """

    @staticmethod
    def get_logs_directory(project_dir: str) -> Path:
        """Get the processing logs directory path"""
        logs_dir = Path(project_dir) / "lf_data" / "processing_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    @staticmethod
    def store_processing_log(
        project_dir: str,
        task_id: str,
        dataset: str,
        strategy: str,
        database: str,
        started_at: datetime,
        completed_at: datetime,
        files: List[FileProcessingDetail],
        summary: Dict[str, int]
    ) -> Path:
        """
        Store a processing log to disk.

        Args:
            project_dir: Path to project directory
            task_id: Celery task ID
            dataset: Dataset name
            strategy: Processing strategy used
            database: Vector database name
            started_at: Processing start time
            completed_at: Processing completion time
            files: List of file processing details
            summary: Summary statistics (processed, skipped, failed)

        Returns:
            Path to the created log file
        """
        logs_dir = ProcessingLogService.get_logs_directory(project_dir)

        # Create log entry
        duration = (completed_at - started_at).total_seconds()
        log_entry = ProcessingLogEntry(
            task_id=task_id,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            dataset=dataset,
            strategy=strategy,
            database=database,
            files=files,
            summary=summary,
            duration_seconds=duration
        )

        # Generate filename: YYYYMMDD_HHMMSS_taskid.json
        timestamp = started_at.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{task_id[:8]}.json"
        log_path = logs_dir / filename

        # Write log file
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log_entry.to_dict(), f, indent=2)

            # Create/update latest.json symlink
            latest_link = logs_dir / "latest.json"
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(filename)

            logger.info(f"Stored processing log: {log_path}")
            return log_path

        except Exception as e:
            logger.error(f"Failed to store processing log: {e}")
            raise

    @staticmethod
    def get_processing_logs(
        project_dir: str,
        dataset: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve processing logs from disk.

        Args:
            project_dir: Path to project directory
            dataset: Optional dataset name to filter by
            limit: Maximum number of logs to return

        Returns:
            List of processing log entries (most recent first)
        """
        logs_dir = ProcessingLogService.get_logs_directory(project_dir)

        # Get all log files (exclude symlinks)
        log_files = [
            f for f in logs_dir.glob("*.json")
            if f.is_file() and not f.is_symlink()
        ]

        # Sort by modification time (newest first)
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        logs = []
        for log_file in log_files:
            if len(logs) >= limit:
                break

            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)

                # Filter by dataset if specified
                if dataset and log_data.get('dataset') != dataset:
                    continue

                logs.append(log_data)

            except Exception as e:
                logger.warning(f"Failed to read log file {log_file}: {e}")
                continue

        return logs

    @staticmethod
    def get_latest_log(
        project_dir: str,
        dataset: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent processing log.

        Args:
            project_dir: Path to project directory
            dataset: Optional dataset name to filter by

        Returns:
            Most recent log entry or None if no logs exist
        """
        logs = ProcessingLogService.get_processing_logs(
            project_dir,
            dataset=dataset,
            limit=1
        )
        return logs[0] if logs else None

    @staticmethod
    def get_log_by_task_id(
        project_dir: str,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific processing log by task ID.

        Args:
            project_dir: Path to project directory
            task_id: Celery task ID to search for

        Returns:
            Log entry or None if not found
        """
        logs_dir = ProcessingLogService.get_logs_directory(project_dir)

        # Search through all log files
        for log_file in logs_dir.glob("*.json"):
            if not log_file.is_file() or log_file.is_symlink():
                continue

            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)

                if log_data.get('task_id') == task_id:
                    return log_data

            except Exception as e:
                logger.warning(f"Failed to read log file {log_file}: {e}")
                continue

        return None

    @staticmethod
    def get_dataset_processing_history(
        project_dir: str,
        dataset: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get complete processing history for a dataset.

        Args:
            project_dir: Path to project directory
            dataset: Dataset name
            limit: Maximum number of runs to return

        Returns:
            List of processing runs (most recent first)
        """
        return ProcessingLogService.get_processing_logs(
            project_dir,
            dataset=dataset,
            limit=limit
        )

    @staticmethod
    def get_file_processing_history(
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
            List of processing runs where this file was processed
        """
        logs = ProcessingLogService.get_processing_logs(
            project_dir,
            dataset=dataset,
            limit=100  # Search through more logs
        )

        # Filter logs that include this file
        file_history = []
        for log in logs:
            # Check if file is in this processing run
            for file_detail in log.get('files', []):
                if file_detail.get('hash') == file_hash:
                    file_history.append({
                        'task_id': log['task_id'],
                        'timestamp': log['started_at'],
                        'dataset': log['dataset'],
                        'database': log['database'],
                        'strategy': log['strategy'],
                        'file_detail': file_detail
                    })
                    break

        return file_history

    @staticmethod
    def cleanup_old_logs(
        project_dir: str,
        keep_count: int = 100,
        dataset: Optional[str] = None
    ) -> int:
        """
        Clean up old processing logs, keeping only the most recent ones.

        Args:
            project_dir: Path to project directory
            keep_count: Number of logs to keep
            dataset: Optional dataset name to filter cleanup

        Returns:
            Number of logs deleted
        """
        logs_dir = ProcessingLogService.get_logs_directory(project_dir)

        # Get all log files
        log_files = [
            f for f in logs_dir.glob("*.json")
            if f.is_file() and not f.is_symlink()
        ]

        # If dataset specified, filter by dataset
        if dataset:
            filtered_files = []
            for log_file in log_files:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    if log_data.get('dataset') == dataset:
                        filtered_files.append(log_file)
                except Exception:
                    continue
            log_files = filtered_files

        # Sort by modification time (newest first)
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Delete old logs
        deleted_count = 0
        for log_file in log_files[keep_count:]:
            try:
                log_file.unlink()
                deleted_count += 1
                logger.info(f"Deleted old processing log: {log_file}")
            except Exception as e:
                logger.warning(f"Failed to delete log file {log_file}: {e}")

        return deleted_count
