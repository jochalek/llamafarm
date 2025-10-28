"""
Processing Callbacks

Celery tasks that run after dataset processing completes to handle:
- Storing processing logs
- Aggregating statistics
- Cleanup operations
"""

import time
from datetime import datetime
from typing import List, Dict, Any
from celery import Task

from core.celery import app
from core.logging import FastAPIStructLogger
from services.processing_log_service import (
    ProcessingLogService,
    FileProcessingDetail as LogFileDetail,
)
from services.project_service import ProjectService

logger = FastAPIStructLogger(__name__)


@app.task(bind=True)
def store_processing_log_task(
    self: Task,
    namespace: str,
    project: str,
    dataset: str,
    strategy: str,
    database: str,
    started_at_iso: str,
    file_results: List[Dict[str, Any]],
    parent_task_id: str,
) -> Dict[str, Any]:
    """
    Store processing log after dataset processing completes.

    This task is called after all file processing tasks complete.
    It aggregates the results and stores a persistent log to disk.

    Args:
        namespace: Project namespace
        project: Project name
        dataset: Dataset name
        strategy: Data processing strategy used
        database: Vector database name
        started_at_iso: ISO 8601 timestamp when processing started
        file_results: List of file processing results
        parent_task_id: Parent task ID (group task ID)

    Returns:
        Summary of log storage operation
    """
    logger.info(
        "Storing processing log",
        namespace=namespace,
        project=project,
        dataset=dataset,
        file_count=len(file_results),
    )

    try:
        # Get project directory
        project_dir = ProjectService.get_project_directory(namespace, project)

        # Parse timestamps
        started_at = datetime.fromisoformat(started_at_iso.replace('Z', '+00:00'))
        completed_at = datetime.now()

        # Convert file results to log format
        log_files = []
        processed_count = 0
        skipped_count = 0
        failed_count = 0

        for file_result in file_results:
            file_hash = file_result.get("file_hash", "")
            success = file_result.get("success", False)
            details = file_result.get("details", {})

            # Extract processing details
            result_data = details.get("result", {})
            status = result_data.get("status", "unknown")

            # Determine overall status
            if success:
                if status == "skipped":
                    actual_status = "skipped"
                    skipped_count += 1
                else:
                    actual_status = "success"
                    processed_count += 1
            else:
                actual_status = "failed"
                failed_count += 1

            # Create log entry for this file
            log_file = LogFileDetail(
                hash=file_hash,
                filename=result_data.get("filename", details.get("filename", file_hash[:16])),
                status=actual_status,
                reason=details.get("reason") or result_data.get("reason"),
                chunks_created=details.get("chunks", 0) or result_data.get("document_count", 0),
                chunks_stored=details.get("stored_count", 0) or result_data.get("stored_count", 0),
                chunks_skipped=details.get("skipped_count", 0) or result_data.get("skipped_count", 0),
                parser=details.get("parser") or (result_data.get("parsers_used", [None])[0] if result_data.get("parsers_used") else None),
                extractors=details.get("extractors", []) or result_data.get("extractors_applied", []),
                embedder=details.get("embedder") or result_data.get("embedder"),
                duration_seconds=0.0,  # TODO: Track per-file duration
                error=details.get("error") if not success else None,
            )

            log_files.append(log_file)

        # Create summary
        summary = {
            "processed": processed_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }

        # Store log to disk
        log_path = ProcessingLogService.store_processing_log(
            project_dir=project_dir,
            task_id=parent_task_id,
            dataset=dataset,
            strategy=strategy,
            database=database,
            started_at=started_at,
            completed_at=completed_at,
            files=log_files,
            summary=summary,
        )

        logger.info(
            "Processing log stored successfully",
            log_path=str(log_path),
            processed=processed_count,
            skipped=skipped_count,
            failed=failed_count,
        )

        return {
            "success": True,
            "log_path": str(log_path),
            "summary": summary,
        }

    except Exception as e:
        logger.error(f"Failed to store processing log: {e}", exc_info=True)
        # Don't raise - we don't want log storage failure to fail the entire processing
        return {
            "success": False,
            "error": str(e),
        }


@app.task(bind=True)
def cleanup_processing_task(
    self: Task,
    namespace: str,
    project: str,
    dataset: str,
    keep_logs: int = 100,
) -> Dict[str, Any]:
    """
    Clean up old processing logs for a dataset.

    Args:
        namespace: Project namespace
        project: Project name
        dataset: Dataset name
        keep_logs: Number of logs to keep (default: 100)

    Returns:
        Summary of cleanup operation
    """
    logger.info(
        "Cleaning up processing logs",
        namespace=namespace,
        project=project,
        dataset=dataset,
        keep_logs=keep_logs,
    )

    try:
        project_dir = ProjectService.get_project_directory(namespace, project)

        deleted_count = ProcessingLogService.cleanup_old_logs(
            project_dir=project_dir,
            keep_count=keep_logs,
            dataset=dataset,
        )

        logger.info(
            "Processing logs cleaned up",
            deleted_count=deleted_count,
        )

        return {
            "success": True,
            "deleted_count": deleted_count,
        }

    except Exception as e:
        logger.error(f"Failed to cleanup processing logs: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }
