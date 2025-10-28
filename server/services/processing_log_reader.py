"""
Processing Log Reader Service

Reads and parses existing processing logs created by rag/core/processing_logger.py.
These logs are stored in lf_data/logs/processing_*.json
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessingLogReader:
    """
    Service for reading and querying existing RAG processing logs.

    Reads from: ~/.llamafarm/projects/{namespace}/{project}/lf_data/logs/
    Log format created by: rag/core/processing_logger.ProcessingLogger
    """

    @staticmethod
    def get_logs_directory(project_dir: str) -> Path:
        """Get the logs directory path"""
        return Path(project_dir) / "lf_data" / "logs"

    @staticmethod
    def read_log_file(log_path: Path) -> Optional[Dict[str, Any]]:
        """
        Read and parse a single log file.

        Args:
            log_path: Path to the log file

        Returns:
            Parsed log data or None if read fails
        """
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read log file {log_path}: {e}")
            return None

    @staticmethod
    def get_all_logs(
        project_dir: str,
        dataset: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all processing logs, optionally filtered by dataset.

        Args:
            project_dir: Path to project directory
            dataset: Optional dataset name to filter by
            limit: Maximum number of logs to return

        Returns:
            List of parsed log entries (most recent first)
        """
        logs_dir = ProcessingLogReader.get_logs_directory(project_dir)

        if not logs_dir.exists():
            return []

        # Get all JSON log files (exclude .log text files)
        log_files = list(logs_dir.glob("processing_*.json"))

        # Sort by modification time (newest first)
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        logs = []
        for log_file in log_files:
            if len(logs) >= limit:
                break

            log_data = ProcessingLogReader.read_log_file(log_file)
            if not log_data:
                continue

            # Filter by dataset if specified
            session = log_data.get('session', {})
            if dataset and session.get('dataset') != dataset:
                continue

            logs.append(log_data)

        return logs

    @staticmethod
    def parse_log_summary(log_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a log file and extract summary information.

        Args:
            log_data: Parsed log file data

        Returns:
            Summary dictionary with counts and metadata
        """
        session = log_data.get('session', {})
        events = log_data.get('events', [])

        # Find summary event if it exists
        summary_event = next(
            (e for e in events if e.get('type') == 'summary'),
            None
        )

        # Count file processing events
        file_events = [e for e in events if e.get('type') == 'file_processing']
        processed_count = sum(1 for e in file_events if e.get('status') == 'processed')
        skipped_count = sum(1 for e in file_events if e.get('status') == 'skipped')
        failed_count = sum(1 for e in file_events if e.get('status') == 'failed')

        # Get timestamps
        start_time = None
        end_time = None
        if events:
            start_time = events[0].get('timestamp')
            end_time = events[-1].get('timestamp')

        # Calculate duration
        duration = 0.0
        if start_time and end_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration = (end_dt - start_dt).total_seconds()
            except Exception:
                pass

        return {
            'dataset': session.get('dataset'),
            'session_timestamp': session.get('timestamp'),
            'started_at': start_time,
            'completed_at': end_time,
            'duration_seconds': duration,
            'total_files': len(file_events),
            'processed': processed_count,
            'skipped': skipped_count,
            'failed': failed_count,
            'summary_data': summary_event.get('data') if summary_event else None,
        }

    @staticmethod
    def get_file_processing_events(
        log_data: Dict[str, Any],
        file_hash: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract file processing events from a log.

        Args:
            log_data: Parsed log file data
            file_hash: Optional file hash to filter by

        Returns:
            List of file processing events
        """
        events = log_data.get('events', [])
        file_events = [e for e in events if e.get('type') == 'file_processing']

        if file_hash:
            # Filter by file hash in the file path or details
            file_events = [
                e for e in file_events
                if file_hash in e.get('file', '') or
                   file_hash in str(e.get('details', {}).get('file_hash', ''))
            ]

        return file_events

    @staticmethod
    def get_dataset_history(
        project_dir: str,
        dataset: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get processing history for a specific dataset.

        Args:
            project_dir: Path to project directory
            dataset: Dataset name
            limit: Maximum number of runs to return

        Returns:
            List of run summaries (most recent first)
        """
        logs = ProcessingLogReader.get_all_logs(
            project_dir=project_dir,
            dataset=dataset,
            limit=limit
        )

        history = []
        for log_data in logs:
            summary = ProcessingLogReader.parse_log_summary(log_data)

            # Extract file details
            events = log_data.get('events', [])
            file_events = [e for e in events if e.get('type') == 'file_processing']

            files = []
            for event in file_events:
                details = event.get('details', {})
                files.append({
                    'filename': Path(event.get('file', '')).name if event.get('file') else 'unknown',
                    'status': event.get('status'),
                    'parser': details.get('parser'),
                    'chunks': details.get('chunks', 0),
                    'error': details.get('error'),
                })

            history.append({
                'session_timestamp': summary['session_timestamp'],
                'started_at': summary['started_at'],
                'completed_at': summary['completed_at'],
                'duration_seconds': summary['duration_seconds'],
                'processed': summary['processed'],
                'skipped': summary['skipped'],
                'failed': summary['failed'],
                'total_files': summary['total_files'],
                'files': files,
            })

        return history

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
        logs = ProcessingLogReader.get_all_logs(
            project_dir=project_dir,
            dataset=dataset,
            limit=100  # Search through more logs for file history
        )

        file_history = []
        for log_data in logs:
            session = log_data.get('session', {})
            file_events = ProcessingLogReader.get_file_processing_events(
                log_data,
                file_hash=file_hash
            )

            for event in file_events:
                details = event.get('details', {})
                file_history.append({
                    'timestamp': event.get('timestamp'),
                    'dataset': session.get('dataset'),
                    'status': event.get('status'),
                    'parser': details.get('parser'),
                    'chunks': details.get('chunks', 0),
                    'chunk_size': details.get('chunk_size'),
                    'error': details.get('error'),
                })

        return file_history

    @staticmethod
    def get_latest_run(
        project_dir: str,
        dataset: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent processing run.

        Args:
            project_dir: Path to project directory
            dataset: Optional dataset name to filter by

        Returns:
            Most recent run summary or None
        """
        history = ProcessingLogReader.get_dataset_history(
            project_dir=project_dir,
            dataset=dataset,
            limit=1
        )
        return history[0] if history else None
