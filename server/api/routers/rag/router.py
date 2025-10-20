"""RAG router for query endpoints."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from core.logging import FastAPIStructLogger
from services.project_service import ProjectService
from services.database_service import DatabaseService, DatabaseMetrics
from api.errors import NotFoundError
from config.datamodel import DatabaseDefinition
from .rag_query import QueryRequest, QueryResponse, handle_rag_query
from .rag_health import RAGHealthResponse, handle_rag_health

logger = FastAPIStructLogger()

router = APIRouter(
    prefix="/projects/{namespace}/{project}/rag",
    tags=["rag"],
)


# Response models for databases endpoint
class RetrievalStrategyInfo(BaseModel):
    name: str
    type: str
    is_default: bool


class DatabaseInfo(BaseModel):
    name: str
    type: str
    is_default: bool
    retrieval_strategies: List[RetrievalStrategyInfo]


class DatabasesResponse(BaseModel):
    databases: List[DatabaseInfo]
    default_database: Optional[str]


@router.post("/query", response_model=QueryResponse)
async def query_rag(namespace: str, project: str, request: QueryRequest):
    """Query the RAG system for semantic search."""
    logger.bind(namespace=namespace, project=project)

    # Get project configuration
    project_obj = ProjectService.get_project(namespace, project)
    project_dir = ProjectService.get_project_dir(namespace, project)

    if not project_obj.config.rag:
        raise HTTPException(
            status_code=400, detail="RAG not configured for this project"
        )

    # Use the handler function from rag_query.py
    return await handle_rag_query(request, project_obj.config, str(project_dir))


@router.get("/health", response_model=RAGHealthResponse)
async def get_rag_health(
    namespace: str,
    project: str,
    database: Optional[str] = Query(
        None, description="Specific database to check health for"
    ),
):
    """Get health status of the RAG system and database."""
    logger.bind(namespace=namespace, project=project, database=database)

    # Get project configuration
    project_obj = ProjectService.get_project(namespace, project)
    project_dir = ProjectService.get_project_dir(namespace, project)

    if not project_obj.config.rag:
        raise HTTPException(
            status_code=400, detail="RAG not configured for this project"
        )

    # Use the handler function from rag_health.py
    return await handle_rag_health(project_obj.config, str(project_dir), database)


@router.get("/databases", response_model=DatabasesResponse)
async def get_rag_databases(namespace: str, project: str):
    """Get list of RAG databases and their retrieval strategies."""
    logger.bind(namespace=namespace, project=project)

    # Get project configuration
    project_obj = ProjectService.get_project(namespace, project)

    if not project_obj.config.rag:
        raise HTTPException(
            status_code=400, detail="RAG not configured for this project"
        )

    rag_config = project_obj.config.rag

    # Build database list with retrieval strategies
    databases = []
    for db in rag_config.databases or []:
        # Get retrieval strategies for this database
        strategies = []
        default_strategy_name = None
        found_default = False

        # Determine default strategy (priority: default_retrieval_strategy > strategy.default > first)
        if hasattr(db, 'default_retrieval_strategy') and db.default_retrieval_strategy:
            default_strategy_name = str(db.default_retrieval_strategy)

        # First pass: check if any strategy is explicitly marked as default
        if not default_strategy_name:
            for strategy in db.retrieval_strategies or []:
                if hasattr(strategy, 'default') and strategy.default:
                    default_strategy_name = str(strategy.name)
                    break

        # Second pass: build strategy list with exactly one default
        for strategy in db.retrieval_strategies or []:
            is_default = False

            # Mark as default based on priority order, ensuring only one default
            if not found_default:
                if default_strategy_name and strategy.name == default_strategy_name:
                    is_default = True
                    found_default = True
                elif not default_strategy_name and not strategies:
                    # First strategy is default if no explicit default found
                    is_default = True
                    found_default = True

            strategies.append(RetrievalStrategyInfo(
                name=str(strategy.name),
                type=strategy.type.value if hasattr(strategy.type, 'value') else str(strategy.type),
                is_default=is_default
            ))

        # Check if this database is the default
        is_default_db = False
        if rag_config.default_database and str(db.name) == str(rag_config.default_database):
            is_default_db = True
        elif not rag_config.default_database and not databases:
            # First database is default if no explicit default
            is_default_db = True

        databases.append(DatabaseInfo(
            name=str(db.name),
            type=db.type.value if hasattr(db.type, 'value') else str(db.type),
            is_default=is_default_db,
            retrieval_strategies=strategies
        ))

    return DatabasesResponse(
        databases=databases,
        default_database=str(rag_config.default_database) if rag_config.default_database else None
    )


# Database management endpoints

class CreateDatabaseRequest(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]
    embedding_strategies: Optional[List[Dict[str, Any]]] = None
    retrieval_strategies: Optional[List[Dict[str, Any]]] = None
    default_embedding_strategy: Optional[str] = None
    default_retrieval_strategy: Optional[str] = None


class CreateDatabaseResponse(BaseModel):
    database: DatabaseDefinition


@router.post("/databases", response_model=CreateDatabaseResponse)
async def create_database(
    namespace: str, project: str, request: CreateDatabaseRequest
):
    """Create a new database in the project"""
    logger.bind(namespace=namespace, project=project)
    try:
        database = DatabaseService.create_database(
            namespace=namespace,
            project=project,
            name=request.name,
            db_type=request.type,
            config=request.config,
            embedding_strategies=request.embedding_strategies,
            retrieval_strategies=request.retrieval_strategies,
            default_embedding_strategy=request.default_embedding_strategy,
            default_retrieval_strategy=request.default_retrieval_strategy,
        )
        return CreateDatabaseResponse(database=database)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class DeleteDatabaseResponse(BaseModel):
    database: DatabaseDefinition
    message: str


@router.delete("/databases/{database}", response_model=DeleteDatabaseResponse)
async def delete_database(
    namespace: str,
    project: str,
    database: str,
    delete_data: bool = Query(
        False,
        description="If true, delete database data (hard delete). If false, only remove from config (soft delete).",
    ),
):
    """
    Delete a database from the project.

    - **Soft delete (delete_data=false)**: Removes database from llamafarm.yaml but keeps data on disk.
      This allows you to re-add the database later and repopulate it.

    - **Hard delete (delete_data=true)**: Removes database from llamafarm.yaml AND deletes all data from disk.
      This is permanent and cannot be undone.
    """
    logger.bind(namespace=namespace, project=project, database=database)
    try:
        deleted_database = DatabaseService.delete_database(
            namespace=namespace,
            project=project,
            name=database,
            delete_data=delete_data,
        )
        message = (
            f"Database '{database}' deleted from config and data removed from disk"
            if delete_data
            else f"Database '{database}' removed from config (data preserved on disk)"
        )
        return DeleteDatabaseResponse(database=deleted_database, message=message)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class ClearDatabaseResponse(BaseModel):
    database: DatabaseDefinition
    message: str


@router.post("/databases/{database}/clear", response_model=ClearDatabaseResponse)
async def clear_database(namespace: str, project: str, database: str):
    """
    Clear all data from a database but keep it in the configuration.

    This is useful when you want to repopulate a database from scratch without
    reconfiguring it.
    """
    logger.bind(namespace=namespace, project=project, database=database)
    try:
        cleared_database = DatabaseService.clear_database_data(
            namespace=namespace, project=project, name=database
        )
        return ClearDatabaseResponse(
            database=cleared_database,
            message=f"Database '{database}' data cleared (configuration preserved)",
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/databases/{database}/metrics", response_model=DatabaseMetrics)
async def get_database_metrics(namespace: str, project: str, database: str):
    """
    Get metrics for a database including document count and embedding status.

    This helps verify that embeddings are working correctly by showing:
    - Total document count
    - Documents with embeddings vs without
    - Embedding dimensions
    - Collection size on disk
    """
    logger.bind(namespace=namespace, project=project, database=database)
    try:
        metrics = DatabaseService.get_database_metrics(
            namespace=namespace, project=project, name=database
        )
        return metrics
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error getting database metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
