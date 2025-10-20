"""Service for managing RAG databases within projects"""
import shutil
from pathlib import Path
from typing import Any

from config.datamodel import DatabaseDefinition
from pydantic import BaseModel

from api.errors import NotFoundError
from core.logging import FastAPIStructLogger
from services.project_service import ProjectService

logger = FastAPIStructLogger()


class DatabaseMetrics(BaseModel):
    """Metrics for a database"""

    database_name: str
    database_type: str
    total_documents: int
    documents_with_embeddings: int
    documents_without_embeddings: int
    embedding_dimension: int | None = None
    collection_size_bytes: int | None = None
    collection_name: str | None = None


class DatabaseInfo(BaseModel):
    """Information about a database"""

    name: str
    type: str
    collection_name: str | None = None
    port: int | None = None
    persist_directory: str | None = None


class DatabaseService:
    """Service for managing RAG databases within projects"""

    @classmethod
    def list_databases(
        cls, namespace: str, project: str
    ) -> list[DatabaseDefinition]:
        """
        List all databases for a given project
        """
        project_config = ProjectService.load_config(namespace, project)
        if not project_config.rag or not project_config.rag.databases:
            return []
        return project_config.rag.databases

    @classmethod
    def get_database(
        cls, namespace: str, project: str, name: str
    ) -> DatabaseDefinition:
        """
        Get a specific database by name

        Raises:
            NotFoundError: If database with given name is not found
        """
        databases = cls.list_databases(namespace, project)
        database = next((db for db in databases if db.name == name), None)
        if database is None:
            raise NotFoundError(f"Database '{name}' not found")
        return database

    @classmethod
    def create_database(
        cls,
        namespace: str,
        project: str,
        name: str,
        db_type: str,
        config: dict[str, Any],
        embedding_strategies: list[dict[str, Any]] | None = None,
        retrieval_strategies: list[dict[str, Any]] | None = None,
        default_embedding_strategy: str | None = None,
        default_retrieval_strategy: str | None = None,
    ) -> DatabaseDefinition:
        """
        Create a new database in the project

        Args:
            namespace: Project namespace
            project: Project ID
            name: Database name
            db_type: Database type (e.g., 'ChromaStore')
            config: Database configuration dict
            embedding_strategies: List of embedding strategy configurations
            retrieval_strategies: List of retrieval strategy configurations
            default_embedding_strategy: Name of default embedding strategy
            default_retrieval_strategy: Name of default retrieval strategy

        Returns:
            DatabaseDefinition: The created database

        Raises:
            ValueError: If database with same name already exists
        """
        project_config = ProjectService.load_config(namespace, project)

        # Ensure RAG config exists
        if not project_config.rag:
            raise ValueError("Project does not have RAG configuration")

        existing_databases = project_config.rag.databases or []

        # Check if database already exists
        for database in existing_databases:
            if database.name == name:
                raise ValueError(f"Database '{name}' already exists")

        # Create new database definition
        # Note: We're passing dicts which will be validated and converted to proper types by Pydantic
        new_database_dict = {
            "name": name,
            "type": db_type,
            "config": config,
        }

        if embedding_strategies:
            new_database_dict["embedding_strategies"] = embedding_strategies
        if retrieval_strategies:
            new_database_dict["retrieval_strategies"] = retrieval_strategies
        if default_embedding_strategy:
            new_database_dict["default_embedding_strategy"] = (
                default_embedding_strategy
            )
        if default_retrieval_strategy:
            new_database_dict["default_retrieval_strategy"] = (
                default_retrieval_strategy
            )

        # Let Pydantic validate and create the proper object
        from config.datamodel import DatabaseDefinition

        new_database = DatabaseDefinition(**new_database_dict)

        existing_databases.append(new_database)
        project_config.rag.databases = existing_databases
        ProjectService.save_config(namespace, project, project_config)

        logger.info(f"Created database '{name}' in project {namespace}/{project}")
        return new_database

    @classmethod
    def delete_database(
        cls,
        namespace: str,
        project: str,
        name: str,
        delete_data: bool = False,
    ) -> DatabaseDefinition:
        """
        Delete a database from the project

        Args:
            namespace: Project namespace
            project: Project ID
            name: Database name
            delete_data: If True, delete database data from disk (hard delete).
                        If False, only remove from config but keep data (soft delete).

        Returns:
            DatabaseDefinition: The deleted database object

        Raises:
            NotFoundError: If database with given name is not found
        """
        project_config = ProjectService.load_config(namespace, project)

        if not project_config.rag or not project_config.rag.databases:
            raise NotFoundError(f"Database '{name}' not found")

        existing_databases = project_config.rag.databases

        # Find the database to delete
        database_to_delete = next(
            (database for database in existing_databases if database.name == name),
            None,
        )
        if database_to_delete is None:
            raise NotFoundError(f"Database '{name}' not found")

        # If hard delete, remove data from disk
        if delete_data:
            cls._delete_database_data(namespace, project, database_to_delete)

        # Remove from config
        project_config.rag.databases = [
            database for database in existing_databases if database.name != name
        ]
        ProjectService.save_config(namespace, project, project_config)

        logger.info(
            f"Deleted database '{name}' from project {namespace}/{project}",
            delete_data=delete_data,
        )
        return database_to_delete

    @classmethod
    def _delete_database_data(
        cls, namespace: str, project: str, database: DatabaseDefinition
    ):
        """
        Delete database data from disk

        For ChromaStore, this removes the persist directory.
        For other database types, this may be a no-op.
        """
        project_dir = ProjectService.get_project_dir(namespace, project)

        # Handle different database types
        if database.type.value == "ChromaStore" or str(database.type) == "ChromaStore":
            # For ChromaStore, delete the persist directory
            # Default location: {project_dir}/lf_data/stores/ChromaStore/{collection_name}
            if hasattr(database.config, "collection_name"):
                collection_name = database.config.collection_name
            elif isinstance(database.config, dict) and "collection_name" in database.config:
                collection_name = database.config["collection_name"]
            else:
                collection_name = None

            if collection_name:
                # Try both ChromaStore and ChromaDB directory names
                for store_dir_name in ["ChromaStore", "ChromaDB"]:
                    persist_dir = Path(project_dir) / "lf_data" / "stores" / store_dir_name / collection_name

                    if not persist_dir.exists():
                        continue

                    # Safety check: ensure path is within project directory
                    try:
                        persist_dir_resolved = persist_dir.resolve()
                        project_dir_resolved = Path(project_dir).resolve()
                        if not persist_dir_resolved.is_relative_to(project_dir_resolved):
                            logger.error(f"Security: Attempted to delete outside project dir: {persist_dir_resolved}")
                            continue
                    except (ValueError, OSError) as e:
                        logger.error(f"Failed to resolve path: {e}")
                        continue

                    # Additional safety: check if it's actually a directory
                    if not persist_dir.is_dir():
                        logger.warning(f"Skipping non-directory: {persist_dir}")
                        continue

                    # Log what we're about to delete
                    try:
                        file_count = len(list(persist_dir.rglob('*')))
                        dir_size = sum(f.stat().st_size for f in persist_dir.rglob('*') if f.is_file())
                        logger.info(
                            f"Deleting ChromaStore data",
                            path=str(persist_dir),
                            files=file_count,
                            size_bytes=dir_size
                        )
                    except Exception as e:
                        logger.warning(f"Could not calculate directory stats: {e}")

                    # Perform the deletion
                    try:
                        shutil.rmtree(persist_dir)
                        logger.info(f"Successfully deleted ChromaStore collection '{collection_name}' at {persist_dir}")
                    except Exception as e:
                        logger.error(f"Failed to delete directory {persist_dir}: {e}")
                        raise

            # Also check for custom persist_directory in config
            if hasattr(database.config, "persist_directory"):
                custom_dir = database.config.persist_directory
            elif isinstance(database.config, dict) and "persist_directory" in database.config:
                custom_dir = database.config["persist_directory"]
            else:
                custom_dir = None

            if custom_dir:
                custom_path = Path(custom_dir)
                # Only delete if it's under the project directory (security check)
                try:
                    custom_path_resolved = custom_path.resolve()
                    project_dir_resolved = Path(project_dir).resolve()
                    if custom_path_resolved.is_relative_to(project_dir_resolved):
                        if custom_path_resolved.exists():
                            logger.info(f"Deleting custom persist directory at {custom_path_resolved}")
                            shutil.rmtree(custom_path_resolved)
                except (ValueError, OSError) as e:
                    logger.warning(f"Could not delete custom persist directory: {e}")

    @classmethod
    def clear_database_data(
        cls, namespace: str, project: str, name: str
    ) -> DatabaseDefinition:
        """
        Clear all data from a database but keep it in the configuration (soft delete)

        This is useful for repopulating a database from scratch.

        Args:
            namespace: Project namespace
            project: Project ID
            name: Database name

        Returns:
            DatabaseDefinition: The database object (still in config)

        Raises:
            NotFoundError: If database with given name is not found
        """
        database = cls.get_database(namespace, project, name)

        # Delete the data
        cls._delete_database_data(namespace, project, database)

        logger.info(
            f"Cleared data for database '{name}' in project {namespace}/{project}"
        )
        return database

    @classmethod
    def get_database_metrics(
        cls, namespace: str, project: str, name: str
    ) -> DatabaseMetrics:
        """
        Get metrics for a database (document count, embeddings, etc.)

        This method uses the RAG store infrastructure to get metrics,
        so it works with any database type defined in the config.

        Args:
            namespace: Project namespace
            project: Project ID
            name: Database name

        Returns:
            DatabaseMetrics: Metrics for the database

        Raises:
            NotFoundError: If database with given name is not found
        """
        database = cls.get_database(namespace, project, name)
        project_config = ProjectService.load_config(namespace, project)
        project_dir = ProjectService.get_project_dir(namespace, project)

        # Initialize default metrics
        metrics = DatabaseMetrics(
            database_name=name,
            database_type=str(database.type.value if hasattr(database.type, 'value') else database.type),
            total_documents=0,
            documents_with_embeddings=0,
            documents_without_embeddings=0,
        )

        # Use the RAG store infrastructure to get metrics
        try:
            import sys
            from pathlib import Path as PathLib

            # Add RAG module to path
            rag_path = PathLib(project_dir).parent.parent.parent / "rag"
            if str(rag_path) not in sys.path:
                sys.path.insert(0, str(rag_path))

            from core.rag_pipeline import RAGPipeline

            # Initialize RAG pipeline to get the store
            rag_pipeline = RAGPipeline(
                config=project_config,
                project_dir=str(project_dir),
                database_name=name
            )

            # Get the vector store
            vector_store = rag_pipeline.vector_store

            # Get metrics from the store
            if hasattr(vector_store, 'get_metrics'):
                # If store implements get_metrics, use it
                store_metrics = vector_store.get_metrics()
                metrics.total_documents = store_metrics.get('total_documents', 0)
                metrics.documents_with_embeddings = store_metrics.get('documents_with_embeddings', 0)
                metrics.documents_without_embeddings = store_metrics.get('documents_without_embeddings', 0)
                metrics.embedding_dimension = store_metrics.get('embedding_dimension')
                metrics.collection_size_bytes = store_metrics.get('collection_size_bytes')
                metrics.collection_name = store_metrics.get('collection_name')
            else:
                # Fallback: try to get basic count
                try:
                    # Most stores should support some form of count/search
                    results = vector_store.search(query_embedding=[0.0] * 768, top_k=10000)
                    if results:
                        metrics.total_documents = len(results)
                        # Try to check if embeddings exist
                        if hasattr(results[0], 'embedding') or (isinstance(results[0], dict) and 'embedding' in results[0]):
                            metrics.documents_with_embeddings = len(results)
                except Exception as e:
                    logger.warning(f"Could not get basic metrics from store: {e}")

        except Exception as e:
            logger.error(f"Error getting database metrics: {e}")

        return metrics
