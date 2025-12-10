"""
Realtime WebSocket service for LlamaFarm.

Provides bidirectional LLM chat with:
- Project-based configuration (system prompts, model settings)
- RAG integration with preview/caching
- Multi-model support
- Session management with conversation history
"""

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.datamodel import LlamaFarmConfig

from agents.chat_orchestrator import ChatOrchestratorAgent, ChatOrchestratorAgentFactory
from core.logging import FastAPIStructLogger
from services.project_chat_service import project_chat_service
from services.project_service import ProjectService
from services.rag_service import search_with_rag

from .types import RAGChunkPreview, RAGConfig, SessionConfig

logger = FastAPIStructLogger()


@dataclass
class CachedRAGResult:
    """Cached RAG search results for reuse on commit."""

    query: str
    chunks: list[Any]  # Raw chunk objects from RAG
    chunks_count: int
    database: str | None
    retrieval_strategy: str | None
    buffer_hash: str  # Hash of input buffer when search was done


@dataclass
class RealtimeSession:
    """Manages state for a single realtime WebSocket session."""

    session_id: str
    namespace: str
    project_id: str
    project_dir: Path
    project_config: LlamaFarmConfig
    config: SessionConfig
    agent: ChatOrchestratorAgent | None = None

    # Input and generation state
    input_buffer: str = ""
    current_generation_task: asyncio.Task | None = None
    cancel_requested: bool = False
    accumulated_response: str = ""

    # RAG preview cache
    cached_rag_result: CachedRAGResult | None = None
    rag_preview_task: asyncio.Task | None = None

    def reset_generation_state(self):
        """Reset state for a new generation."""
        self.cancel_requested = False
        self.accumulated_response = ""
        self.current_generation_task = None

    def invalidate_rag_cache(self):
        """Invalidate RAG cache when input changes significantly."""
        self.cached_rag_result = None

    def get_buffer_hash(self) -> str:
        """Get a hash of the current input buffer for cache validation."""
        # Use a simple hash - just the stripped buffer content
        return hash(self.input_buffer.strip())


class RealtimeService:
    """Service for handling realtime WebSocket connections with LlamaFarm."""

    async def create_session(
        self,
        namespace: str,
        project_id: str,
        config: SessionConfig | None = None,
    ) -> RealtimeSession:
        """Create a new realtime session for a project."""
        session_id = f"rt_{uuid.uuid4().hex[:16]}"
        session_config = config or SessionConfig()

        # Load project configuration
        project_dir = ProjectService.get_project_dir(namespace, project_id)
        project_config = ProjectService.load_config(namespace, project_id)

        # Create the chat agent
        agent = await ChatOrchestratorAgentFactory.create_agent(
            project_config=project_config,
            project_dir=str(project_dir),
            model_name=session_config.model,
            session_id=session_id,
        )

        session = RealtimeSession(
            session_id=session_id,
            namespace=namespace,
            project_id=project_id,
            project_dir=project_dir,
            project_config=project_config,
            config=session_config,
            agent=agent,
        )

        logger.info(
            "realtime_session_created",
            session_id=session_id,
            namespace=namespace,
            project_id=project_id,
        )
        return session

    def get_available_models(self, project_config: LlamaFarmConfig) -> list[str]:
        """Get list of available model names from project config."""
        if project_config.runtime and project_config.runtime.models:
            return list(project_config.runtime.models.keys())
        return []

    async def update_session(
        self, session: RealtimeSession, config: SessionConfig
    ) -> SessionConfig:
        """Update session configuration."""
        old_model = session.config.model
        session.config = config

        # If model changed, recreate the agent
        if config.model != old_model:
            session.agent = await ChatOrchestratorAgentFactory.create_agent(
                project_config=session.project_config,
                project_dir=str(session.project_dir),
                model_name=config.model,
                session_id=session.session_id,
            )
            logger.info(
                "realtime_session_model_changed",
                session_id=session.session_id,
                old_model=old_model,
                new_model=config.model,
            )

        logger.info(
            "realtime_session_updated",
            session_id=session.session_id,
        )
        return session.config

    def append_input(self, session: RealtimeSession, text: str) -> str:
        """Append text to the input buffer."""
        session.input_buffer += text
        return session.input_buffer

    def clear_input(self, session: RealtimeSession) -> None:
        """Clear the input buffer and invalidate RAG cache."""
        session.input_buffer = ""
        session.invalidate_rag_cache()

    def commit_input(self, session: RealtimeSession) -> tuple[str, str]:
        """Commit input buffer.

        Returns:
            Tuple of (committed_text, item_id)
        """
        if not session.input_buffer.strip():
            raise ValueError("Cannot commit empty input buffer")

        committed_text = session.input_buffer.strip()
        item_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Clear buffer
        session.input_buffer = ""

        logger.info(
            "realtime_input_committed",
            session_id=session.session_id,
            text_length=len(committed_text),
            item_id=item_id,
        )
        return committed_text, item_id

    def clear_conversation(self, session: RealtimeSession) -> None:
        """Clear conversation history."""
        if session.agent:
            session.agent.history.clear()
        session.invalidate_rag_cache()
        logger.info(
            "realtime_conversation_cleared",
            session_id=session.session_id,
        )

    async def preview_rag(
        self, session: RealtimeSession
    ) -> tuple[list[RAGChunkPreview], int, str | None, str | None, bool]:
        """Search RAG with current input buffer and cache results.

        Returns:
            Tuple of (chunk_previews, total_count, database, strategy, is_cached)
        """
        rag_config = session.config.rag or RAGConfig()

        if not rag_config.enabled:
            return [], 0, None, None, False

        if not session.input_buffer.strip():
            return [], 0, rag_config.database, rag_config.retrieval_strategy, False

        query = session.input_buffer.strip()
        buffer_hash = str(session.get_buffer_hash())

        # Check if we have a valid cached result
        if (
            session.cached_rag_result is not None
            and session.cached_rag_result.buffer_hash == buffer_hash
        ):
            # Return cached result
            previews = self._chunks_to_previews(session.cached_rag_result.chunks)
            return (
                previews,
                session.cached_rag_result.chunks_count,
                session.cached_rag_result.database,
                session.cached_rag_result.retrieval_strategy,
                True,  # is_cached
            )

        # Perform RAG search
        try:
            database = rag_config.database
            strategy = rag_config.retrieval_strategy
            top_k = rag_config.top_k or 5
            score_threshold = rag_config.score_threshold

            # Use custom queries if provided, otherwise use buffer content
            queries = rag_config.queries or [query]

            chunks = await search_with_rag(
                project_dir=str(session.project_dir),
                project_config=session.project_config,
                queries=queries,
                database_name=database,
                retrieval_strategy=strategy,
                top_k=top_k,
                score_threshold=score_threshold,
            )

            # Cache the result
            session.cached_rag_result = CachedRAGResult(
                query=query,
                chunks=chunks,
                chunks_count=len(chunks),
                database=database,
                retrieval_strategy=strategy,
                buffer_hash=buffer_hash,
            )

            logger.info(
                "realtime_rag_preview_complete",
                session_id=session.session_id,
                chunks_count=len(chunks),
                query_length=len(query),
            )

            previews = self._chunks_to_previews(chunks)
            return previews, len(chunks), database, strategy, False

        except Exception as e:
            logger.error(
                "realtime_rag_preview_error",
                session_id=session.session_id,
                error=str(e),
            )
            # Return empty on error, don't cache
            return [], 0, rag_config.database, rag_config.retrieval_strategy, False

    def _chunks_to_previews(
        self, chunks: list[Any], max_content_length: int = 200
    ) -> list[RAGChunkPreview]:
        """Convert RAG chunks to preview format."""
        previews = []
        for chunk in chunks[:10]:  # Limit to 10 previews
            content = ""
            score = None
            source = None

            # Extract content based on chunk structure
            if hasattr(chunk, "content"):
                content = chunk.content
            elif hasattr(chunk, "text"):
                content = chunk.text
            elif isinstance(chunk, dict):
                content = chunk.get("content", chunk.get("text", str(chunk)))
            else:
                content = str(chunk)

            # Extract score
            if hasattr(chunk, "score"):
                score = chunk.score
            elif isinstance(chunk, dict):
                score = chunk.get("score")

            # Extract source
            if hasattr(chunk, "metadata"):
                metadata = chunk.metadata
                if isinstance(metadata, dict):
                    source = metadata.get("source", metadata.get("filename"))
            elif isinstance(chunk, dict):
                metadata = chunk.get("metadata", {})
                if isinstance(metadata, dict):
                    source = metadata.get("source", metadata.get("filename"))

            # Truncate content for preview
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."

            previews.append(
                RAGChunkPreview(content=content, score=score, source=source)
            )

        return previews

    def has_valid_rag_cache(self, session: RealtimeSession) -> bool:
        """Check if session has valid RAG cache for current buffer."""
        if session.cached_rag_result is None:
            return False
        buffer_hash = str(session.get_buffer_hash())
        return session.cached_rag_result.buffer_hash == buffer_hash

    async def cancel_generation(self, session: RealtimeSession) -> tuple[str, str]:
        """Cancel in-progress generation.

        Returns:
            Tuple of (item_id, partial_text)
        """
        if session.current_generation_task is None:
            return "", ""

        # Signal cancellation
        session.cancel_requested = True
        logger.info(
            "realtime_cancel_requested",
            session_id=session.session_id,
        )

        # Wait for the task to complete
        try:
            await asyncio.wait_for(session.current_generation_task, timeout=2.0)
        except TimeoutError:
            session.current_generation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.current_generation_task
        except asyncio.CancelledError:
            pass

        partial_text = session.accumulated_response
        item_id = f"msg_{uuid.uuid4().hex[:12]}"

        session.reset_generation_state()
        return item_id, partial_text

    async def generate_response(
        self,
        session: RealtimeSession,
        user_message: str,
        on_rag_context: callable,
        on_token: callable,
        on_done: callable,
    ) -> None:
        """Generate a response using the chat orchestrator.

        Args:
            session: The realtime session
            user_message: The user's message text
            on_rag_context: Async callback when RAG context is added
            on_token: Async callback called with (item_id, delta) for each token
            on_done: Async callback called with (item_id, full_text) when complete
        """
        config = session.config
        item_id = f"msg_{uuid.uuid4().hex[:12]}"

        try:
            if session.agent is None:
                raise ValueError("No agent available for session")

            # Build messages list with the new user message
            messages = [{"role": "user", "content": user_message}]

            # Determine RAG settings
            rag_config = config.rag or RAGConfig()

            # Stream the response using project_chat_service
            session.accumulated_response = ""

            # Use streaming chat
            async for chunk in project_chat_service.stream_chat(
                project_dir=str(session.project_dir),
                project_config=session.project_config,
                chat_agent=session.agent,
                messages=messages,
                tools=[],  # No tools in realtime for now
                rag_enabled=rag_config.enabled,
                database=rag_config.database,
                retrieval_strategy=rag_config.retrieval_strategy,
                rag_top_k=rag_config.top_k,
                rag_score_threshold=rag_config.score_threshold,
                rag_queries=rag_config.queries,
                n_ctx=config.n_ctx,
                think=config.think,
                thinking_budget=config.thinking_budget,
            ):
                # Check for cancellation
                if session.cancel_requested:
                    logger.info(
                        "realtime_generation_cancelled",
                        session_id=session.session_id,
                    )
                    return

                # Extract content from chunk
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        content = delta.content
                        session.accumulated_response += content
                        await on_token(item_id, content)

                await asyncio.sleep(0)

            # Generation complete
            full_response = session.accumulated_response
            await on_done(item_id, full_response)

            logger.info(
                "realtime_generation_complete",
                session_id=session.session_id,
                response_length=len(full_response),
            )

        except asyncio.CancelledError:
            logger.info(
                "realtime_generation_task_cancelled",
                session_id=session.session_id,
            )
            raise
        except Exception as e:
            logger.error(
                "realtime_generation_error",
                session_id=session.session_id,
                error=str(e),
            )
            raise
        finally:
            session.reset_generation_state()
