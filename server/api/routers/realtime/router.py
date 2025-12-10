"""
Realtime WebSocket router for LlamaFarm.

Provides bidirectional streaming chat with:
- Project-based configuration
- RAG integration
- Multi-model support
- Session management
"""

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.logging import FastAPIStructLogger
from services.project_service import ProjectService

from .service import RealtimeService, RealtimeSession
from .types import (
    ConversationClearedMessage,
    ErrorMessage,
    InputTextAppendMessage,
    InputTextClearedMessage,
    InputTextCommittedMessage,
    MessageType,
    RAGContextAddedMessage,
    RAGPreviewResultMessage,
    RAGPreviewSearchingMessage,
    ResponseCancelledMessage,
    ResponseDoneMessage,
    ResponseTextDeltaMessage,
    ResponseTextDoneMessage,
    SessionCreatedMessage,
    SessionUpdatedMessage,
    SessionUpdateMessage,
)

logger = FastAPIStructLogger()

router = APIRouter()


class RealtimeConnectionHandler:
    """Handles a single WebSocket connection for realtime chat."""

    def __init__(self, websocket: WebSocket, namespace: str, project_id: str):
        self.websocket = websocket
        self.namespace = namespace
        self.project_id = project_id
        self.service = RealtimeService()
        self.session: RealtimeSession | None = None

    async def send_message(self, message: dict | object) -> None:
        """Send a message to the client."""
        data = message.model_dump() if hasattr(message, "model_dump") else message
        await self.websocket.send_json(data)

    async def send_error(self, code: str, message: str, details: dict | None = None):
        """Send an error message to the client."""
        await self.send_message(
            ErrorMessage(code=code, message=message, details=details)
        )

    async def handle_session_update(self, data: dict) -> None:
        """Handle session.update message."""
        try:
            msg = SessionUpdateMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            updated_config = await self.service.update_session(
                self.session, msg.session
            )
            await self.send_message(SessionUpdatedMessage(session=updated_config))

        except Exception as e:
            logger.error(
                "realtime_session_update_error",
                error=str(e),
            )
            await self.send_error("session_update_failed", str(e))

    async def handle_input_text_append(self, data: dict) -> None:
        """Handle input_text.append message."""
        try:
            msg = InputTextAppendMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            self.service.append_input(self.session, msg.text)

        except Exception as e:
            logger.error(
                "realtime_input_append_error",
                error=str(e),
            )
            await self.send_error("input_append_failed", str(e))

    async def handle_input_text_clear(self, data: dict) -> None:
        """Handle input_text.clear message."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            self.service.clear_input(self.session)
            await self.send_message(InputTextClearedMessage())

        except Exception as e:
            logger.error(
                "realtime_input_clear_error",
                error=str(e),
            )
            await self.send_error("input_clear_failed", str(e))

    async def handle_conversation_clear(self, data: dict) -> None:
        """Handle conversation.clear message."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            self.service.clear_conversation(self.session)
            await self.send_message(ConversationClearedMessage())

        except Exception as e:
            logger.error(
                "realtime_conversation_clear_error",
                error=str(e),
            )
            await self.send_error("conversation_clear_failed", str(e))

    async def handle_input_text_commit(self, data: dict) -> None:
        """Handle input_text.commit message - starts generation."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            # Cancel any existing generation first
            if self.session.current_generation_task is not None:
                item_id, partial_text = await self.service.cancel_generation(
                    self.session
                )
                if item_id:
                    await self.send_message(
                        ResponseCancelledMessage(
                            item_id=item_id, partial_text=partial_text
                        )
                    )

            # Commit the input
            try:
                committed_text, item_id = self.service.commit_input(self.session)
            except ValueError as e:
                await self.send_error("input_empty", str(e))
                return

            await self.send_message(
                InputTextCommittedMessage(text=committed_text, item_id=item_id)
            )

            # Callbacks for generation events
            async def on_rag_context(
                chunks_count: int, database: str | None, strategy: str | None
            ):
                await self.send_message(
                    RAGContextAddedMessage(
                        item_id=item_id,
                        chunks_count=chunks_count,
                        database=database,
                        retrieval_strategy=strategy,
                    )
                )

            async def on_token(item_id: str, delta: str):
                await self.send_message(
                    ResponseTextDeltaMessage(item_id=item_id, delta=delta)
                )

            async def on_done(item_id: str, full_text: str):
                await self.send_message(
                    ResponseTextDoneMessage(item_id=item_id, text=full_text)
                )
                await self.send_message(ResponseDoneMessage(item_id=item_id))

            # Create generation task
            generation_task = asyncio.create_task(
                self.service.generate_response(
                    self.session,
                    committed_text,
                    on_rag_context,
                    on_token,
                    on_done,
                )
            )
            self.session.current_generation_task = generation_task

            # Wait for completion
            try:
                await generation_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(
                    "realtime_generation_error",
                    error=str(e),
                )
                await self.send_error("generation_failed", str(e))

        except Exception as e:
            logger.error(
                "realtime_input_commit_error",
                error=str(e),
            )
            await self.send_error("input_commit_failed", str(e))

    async def handle_response_cancel(self, data: dict) -> None:
        """Handle response.cancel message."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            item_id, partial_text = await self.service.cancel_generation(self.session)
            await self.send_message(
                ResponseCancelledMessage(item_id=item_id, partial_text=partial_text)
            )

        except Exception as e:
            logger.error(
                "realtime_cancel_error",
                error=str(e),
            )
            await self.send_error("cancel_failed", str(e))

    async def handle_rag_preview(self, data: dict) -> None:
        """Handle rag.preview message - search RAG and cache results."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            # Check if RAG is enabled
            rag_config = self.session.config.rag
            if not rag_config or not rag_config.enabled:
                await self.send_error(
                    "rag_not_enabled",
                    "RAG is not enabled. Update session with rag.enabled=true",
                )
                return

            # Check if there's input to search
            if not self.session.input_buffer.strip():
                await self.send_message(
                    RAGPreviewResultMessage(
                        query="",
                        chunks_count=0,
                        chunks=[],
                        database=rag_config.database,
                        retrieval_strategy=rag_config.retrieval_strategy,
                        cached=False,
                    )
                )
                return

            # Send searching indicator
            await self.send_message(
                RAGPreviewSearchingMessage(query=self.session.input_buffer.strip())
            )

            # Perform RAG preview
            (
                previews,
                count,
                database,
                strategy,
                is_cached,
            ) = await self.service.preview_rag(self.session)

            # Send results
            await self.send_message(
                RAGPreviewResultMessage(
                    query=self.session.input_buffer.strip(),
                    chunks_count=count,
                    chunks=previews,
                    database=database,
                    retrieval_strategy=strategy,
                    cached=is_cached,
                )
            )

        except Exception as e:
            logger.error(
                "realtime_rag_preview_error",
                error=str(e),
            )
            await self.send_error("rag_preview_failed", str(e))

    async def handle_message(self, data: dict) -> None:
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get("type")

        handlers = {
            MessageType.SESSION_UPDATE.value: self.handle_session_update,
            MessageType.INPUT_TEXT_APPEND.value: self.handle_input_text_append,
            MessageType.INPUT_TEXT_CLEAR.value: self.handle_input_text_clear,
            MessageType.INPUT_TEXT_COMMIT.value: self.handle_input_text_commit,
            MessageType.RESPONSE_CANCEL.value: self.handle_response_cancel,
            MessageType.CONVERSATION_CLEAR.value: self.handle_conversation_clear,
            MessageType.RAG_PREVIEW.value: self.handle_rag_preview,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(data)
        else:
            await self.send_error(
                "unknown_message_type", f"Unknown message type: {msg_type}"
            )

    async def run(self) -> None:
        """Main loop for handling the WebSocket connection."""
        await self.websocket.accept()

        # Verify project exists
        try:
            project_dir = ProjectService.get_project_dir(
                self.namespace, self.project_id
            )
            if not project_dir.exists():
                await self.send_error(
                    "project_not_found",
                    f"Project not found: {self.namespace}/{self.project_id}",
                )
                await self.websocket.close()
                return
        except Exception as e:
            await self.send_error("project_error", str(e))
            await self.websocket.close()
            return

        # Create initial session
        try:
            self.session = await self.service.create_session(
                self.namespace, self.project_id
            )
        except Exception as e:
            await self.send_error("session_create_failed", str(e))
            await self.websocket.close()
            return

        # Get available models
        available_models = self.service.get_available_models(
            self.session.project_config
        )

        # Send session.created
        await self.send_message(
            SessionCreatedMessage(
                session_id=self.session.session_id,
                session=self.session.config,
                project={
                    "namespace": self.namespace,
                    "name": self.project_id,
                },
                available_models=available_models,
            )
        )

        try:
            while True:
                # Receive message
                try:
                    raw_data = await self.websocket.receive_text()
                    data = json.loads(raw_data)
                except json.JSONDecodeError as e:
                    await self.send_error("invalid_json", f"Invalid JSON: {e}")
                    continue

                # Handle message in background to allow concurrent operations
                asyncio.create_task(self.handle_message(data))

        except WebSocketDisconnect:
            logger.info(
                "realtime_websocket_disconnected",
                session_id=self.session.session_id if self.session else None,
            )
            # Clean up any running generation
            if self.session and self.session.current_generation_task:
                self.session.current_generation_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.session.current_generation_task


@router.websocket("/v1/projects/{namespace}/{project_id}/realtime")
async def realtime_websocket(websocket: WebSocket, namespace: str, project_id: str):
    """
    Realtime WebSocket endpoint for bidirectional LLM chat.

    This endpoint provides the same capabilities as the REST chat API but with:
    - Bidirectional WebSocket communication
    - Input buffering (build up text before sending)
    - Mid-generation cancellation
    - Persistent session state

    The session automatically uses the project's configuration including:
    - System prompts from llamafarm.yaml
    - Available models from runtime config
    - RAG settings

    Protocol:
    ---------

    Client -> Server messages:
    - session.update: Update model, RAG settings, generation params
    - input_text.append: Append text to input buffer
    - input_text.clear: Clear input buffer
    - input_text.commit: Commit buffer and start generation
    - response.cancel: Cancel in-progress generation
    - conversation.clear: Clear conversation history
    - rag.preview: Preview RAG results for current buffer (cached for commit)

    Server -> Client messages:
    - session.created: Initial session with project info and available models
    - session.updated: Configuration updated
    - input_text.committed: Input was committed
    - rag.preview_searching: RAG search in progress
    - rag.preview_result: RAG preview results with chunk summaries
    - rag.context_added: RAG chunks were retrieved (if RAG enabled)
    - response.text.delta: Streaming text chunk
    - response.text.done: Text generation complete
    - response.done: Full response complete
    - response.cancelled: Response was cancelled
    - error: Error occurred

    Example session.update with RAG:
    ```json
    {
      "type": "session.update",
      "session": {
        "model": "powerful",
        "temperature": 0.7,
        "rag": {
          "enabled": true,
          "database": "main_db",
          "top_k": 5
        }
      }
    }
    ```
    """
    handler = RealtimeConnectionHandler(websocket, namespace, project_id)
    await handler.run()
