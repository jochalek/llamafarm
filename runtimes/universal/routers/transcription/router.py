"""
Realtime Transcription WebSocket router for Universal Runtime.

Provides bidirectional audio transcription with:
- Audio buffer management
- Voice Activity Detection (VAD)
- Streaming transcription results
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .service import TranscriptionService, TranscriptionSession
from .types import (
    ErrorMessage,
    InputAudioBufferAppendMessage,
    InputAudioBufferClearedMessage,
    InputAudioBufferCommittedMessage,
    InputAudioBufferSpeechStartedMessage,
    MessageType,
    SessionCreatedMessage,
    SessionUpdatedMessage,
    SessionUpdateMessage,
    TranscriptionCompletedMessage,
    TranscriptionDeltaMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class TranscriptionConnectionHandler:
    """Handles a single WebSocket connection for realtime transcription."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.service = TranscriptionService()
        self.session: TranscriptionSession | None = None

    async def send_message(self, message: dict | object) -> bool:
        """Send a message to the client.

        Returns:
            True if message was sent, False if connection is closed.
        """
        # Check if websocket is still connected
        if self.websocket.client_state != WebSocketState.CONNECTED:
            return False

        data = message.model_dump() if hasattr(message, "model_dump") else message

        try:
            await self.websocket.send_json(data)
            return True
        except (WebSocketDisconnect, RuntimeError):
            # Client disconnected
            return False

    async def send_error(
        self, code: str, message: str, details: dict | None = None
    ) -> bool:
        """Send an error message to the client.

        Returns:
            True if message was sent, False if connection is closed.
        """
        return await self.send_message(
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
            logger.error(f"Session update error: {e}")
            await self.send_error("session_update_failed", str(e))

    async def handle_audio_append(self, data: dict) -> None:
        """Handle input_audio_buffer.append message."""
        try:
            msg = InputAudioBufferAppendMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            # Append audio and check for speech
            speech_detected, speech_start_ms = self.service.append_audio(
                self.session, msg.audio
            )

            # Send speech started event if newly detected
            if speech_start_ms is not None:
                item_id = self.session.generate_item_id()
                await self.send_message(
                    InputAudioBufferSpeechStartedMessage(
                        audio_start_ms=speech_start_ms,
                        item_id=item_id,
                    )
                )

        except Exception as e:
            logger.error(f"Audio append error: {e}")
            await self.send_error("audio_append_failed", str(e))

    async def handle_audio_commit(self, data: dict) -> None:
        """Handle input_audio_buffer.commit message."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            if not self.session.audio_buffer:
                await self.send_error("buffer_empty", "No audio in buffer")
                return

            # Generate item ID
            item_id = self.session.generate_item_id()

            # Send committed message
            await self.send_message(
                InputAudioBufferCommittedMessage(
                    item_id=item_id,
                    previous_item_id=self.session.previous_item_id,
                )
            )

            # Define callbacks for streaming transcription
            async def on_delta(event_id: str, item_id: str, delta: str):
                await self.send_message(
                    TranscriptionDeltaMessage(
                        event_id=event_id,
                        item_id=item_id,
                        delta=delta,
                    )
                )

            async def on_completed(event_id: str, item_id: str, transcript: str):
                await self.send_message(
                    TranscriptionCompletedMessage(
                        event_id=event_id,
                        item_id=item_id,
                        transcript=transcript,
                    )
                )

            # Run transcription
            await self.service.transcribe(
                self.session,
                on_delta=on_delta,
                on_completed=on_completed,
            )

            # Clear buffer after transcription
            self.service.clear_buffer(self.session)

        except Exception as e:
            logger.error(f"Audio commit error: {e}")
            await self.send_error("transcription_failed", str(e))

    async def handle_audio_clear(self, data: dict) -> None:
        """Handle input_audio_buffer.clear message."""
        try:
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            self.service.clear_buffer(self.session)
            await self.send_message(InputAudioBufferClearedMessage())

        except Exception as e:
            logger.error(f"Audio clear error: {e}")
            await self.send_error("clear_failed", str(e))

    async def handle_message(self, data: dict) -> None:
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get("type")

        handlers = {
            MessageType.SESSION_UPDATE.value: self.handle_session_update,
            MessageType.INPUT_AUDIO_BUFFER_APPEND.value: self.handle_audio_append,
            MessageType.INPUT_AUDIO_BUFFER_COMMIT.value: self.handle_audio_commit,
            MessageType.INPUT_AUDIO_BUFFER_CLEAR.value: self.handle_audio_clear,
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

        # Send session.created
        await self.send_message(
            SessionCreatedMessage(
                session_id=self.session.session_id,
                session=self.session.config,
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

                # Handle message
                await self.handle_message(data)

        except WebSocketDisconnect:
            logger.info(
                f"Transcription WebSocket disconnected: {self.session.session_id if self.session else 'unknown'}"
            )


@router.websocket("/v1/realtime/transcription")
async def transcription_websocket(websocket: WebSocket):
    """
    Realtime WebSocket endpoint for audio transcription.

    This endpoint provides streaming audio-to-text transcription with:
    - Audio buffer management (append audio incrementally)
    - Voice Activity Detection (VAD) for automatic speech boundary detection
    - Support for various audio formats (PCM, G.711 μ-law, G.711 A-law)
    - Multiple Whisper model options

    Protocol:
    ---------

    Client -> Server messages:
    - session.update: Update transcription settings (model, language, VAD)
    - input_audio_buffer.append: Append base64-encoded audio
    - input_audio_buffer.commit: Trigger transcription of buffered audio
    - input_audio_buffer.clear: Clear the audio buffer

    Server -> Client messages:
    - session.created: Initial session with default config
    - session.updated: Configuration updated
    - input_audio_buffer.committed: Audio buffer was committed
    - input_audio_buffer.cleared: Audio buffer was cleared
    - input_audio_buffer.speech_started: VAD detected speech start
    - input_audio_buffer.speech_stopped: VAD detected speech end
    - conversation.item.input_audio_transcription.delta: Streaming transcript
    - conversation.item.input_audio_transcription.completed: Final transcript
    - error: Error occurred

    Example session.update:
    ```json
    {
      "type": "session.update",
      "session": {
        "type": "transcription",
        "audio": {
          "input": {
            "format": {"type": "audio/pcm", "rate": 16000},
            "transcription": {
              "model": "openai/whisper-small",
              "language": "en"
            },
            "turn_detection": {
              "type": "server_vad",
              "threshold": 0.5,
              "silence_duration_ms": 500
            }
          }
        }
      }
    }
    ```
    """
    handler = TranscriptionConnectionHandler(websocket)
    await handler.run()
