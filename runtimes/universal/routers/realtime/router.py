"""
Realtime WebSocket router for bidirectional LLM chat.

Provides an OpenAI Realtime API-inspired interface for:
- Text input buffering and commit
- Streaming text output
- Mid-generation cancellation
- Session-based configuration
"""

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .service import RealtimeService, RealtimeSession
from .types import (
    ErrorMessage,
    InputTextAppendMessage,
    InputTextClearedMessage,
    InputTextCommittedMessage,
    MessageType,
    ResponseCancelledMessage,
    ResponseDoneMessage,
    ResponseTextDeltaMessage,
    ResponseTextDoneMessage,
    SessionCreatedMessage,
    SessionUpdatedMessage,
    SessionUpdateMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RealtimeConnectionHandler:
    """Handles a single WebSocket connection for realtime chat."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
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

            updated_config = self.service.update_session(self.session, msg.session)
            await self.send_message(SessionUpdatedMessage(session=updated_config))

        except Exception as e:
            logger.error(f"Error updating session: {e}", exc_info=True)
            await self.send_error("session_update_failed", str(e))

    async def handle_input_text_append(self, data: dict) -> None:
        """Handle input_text.append message."""
        try:
            msg = InputTextAppendMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            self.service.append_input(self.session, msg.text)
            # No response needed for append - it's a fire-and-forget operation

        except Exception as e:
            logger.error(f"Error appending input: {e}", exc_info=True)
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
            logger.error(f"Error clearing input: {e}", exc_info=True)
            await self.send_error("input_clear_failed", str(e))

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

            # Start generation in background
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
                self.service.generate_response(self.session, on_token, on_done)
            )
            self.session.current_generation_task = generation_task

            # Wait for completion but don't block the message handler
            try:
                await generation_task
            except asyncio.CancelledError:
                # Cancelled - response was already sent
                pass
            except Exception as e:
                logger.error(f"Generation error: {e}", exc_info=True)
                await self.send_error("generation_failed", str(e))

        except Exception as e:
            logger.error(f"Error committing input: {e}", exc_info=True)
            await self.send_error("input_commit_failed", str(e))

    async def handle_response_cancel(self, data: dict) -> None:
        """Handle response.cancel message."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            item_id, partial_text = await self.service.cancel_generation(self.session)
            if item_id:
                await self.send_message(
                    ResponseCancelledMessage(item_id=item_id, partial_text=partial_text)
                )
            else:
                # Nothing to cancel
                await self.send_message(
                    ResponseCancelledMessage(item_id="", partial_text="")
                )

        except Exception as e:
            logger.error(f"Error cancelling response: {e}", exc_info=True)
            await self.send_error("cancel_failed", str(e))

    async def handle_message(self, data: dict) -> None:
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get("type")

        handlers = {
            MessageType.SESSION_UPDATE.value: self.handle_session_update,
            MessageType.INPUT_TEXT_APPEND.value: self.handle_input_text_append,
            MessageType.INPUT_TEXT_CLEAR.value: self.handle_input_text_clear,
            MessageType.INPUT_TEXT_COMMIT.value: self.handle_input_text_commit,
            MessageType.RESPONSE_CANCEL.value: self.handle_response_cancel,
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

        # Create initial session
        self.session = self.service.create_session()
        await self.send_message(
            SessionCreatedMessage(
                session_id=self.session.session_id, session=self.session.config
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
                # (e.g., receiving cancel while generation is running)
                asyncio.create_task(self.handle_message(data))

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {self.session.session_id}")
            # Clean up any running generation
            if self.session and self.session.current_generation_task:
                self.session.current_generation_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.session.current_generation_task


@router.websocket("/v1/realtime")
async def realtime_websocket(websocket: WebSocket):
    """
    Realtime WebSocket endpoint for bidirectional LLM chat.

    Protocol:
    ---------

    Client -> Server messages:
    - session.update: Update session configuration (model, temperature, etc.)
    - input_text.append: Append text to input buffer
    - input_text.clear: Clear input buffer
    - input_text.commit: Commit buffer and start generation
    - response.cancel: Cancel in-progress generation

    Server -> Client messages:
    - session.created: Initial session created
    - session.updated: Configuration updated
    - input_text.committed: Input was committed
    - input_text.cleared: Input buffer cleared
    - response.text.delta: Streaming text chunk
    - response.text.done: Text generation complete
    - response.done: Full response complete
    - response.cancelled: Response was cancelled
    - error: Error occurred

    Example flow:
    -------------
    1. Connect -> receive session.created
    2. Send session.update with model config
    3. Send input_text.append with "Hello"
    4. Send input_text.commit -> starts generation
    5. Receive response.text.delta (multiple times)
    6. Receive response.text.done
    7. Receive response.done
    8. Repeat from step 3 for next turn
    """
    handler = RealtimeConnectionHandler(websocket)
    await handler.run()
