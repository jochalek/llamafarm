"""
Realtime Vision WebSocket router for Universal Runtime.

Provides bidirectional video processing with:
- Single image inference
- Video frame streaming
- RTSP/URL source streaming
- Real-time detection results
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .service import (
    VisionService,
    decode_base64_image,
    generate_session_id,
    get_vision_model,
)
from .types import (
    DetectionResultMessage,
    ErrorMessage,
    InputImageMessage,
    InputVideoFrameMessage,
    MessageType,
    SessionCreatedMessage,
    SessionUpdatedMessage,
    SessionUpdateMessage,
    StartStreamMessage,
    StreamStartedMessage,
    StreamStoppedMessage,
    VisionSessionConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vision-realtime"])


class VisionSession:
    """Manages state for a single vision WebSocket session."""

    def __init__(self, session_id: str, config: VisionSessionConfig):
        self.session_id = session_id
        self.config = config
        self.service = VisionService(config)
        self.stream_task: asyncio.Task | None = None
        self.stream_active = False
        self.frames_processed = 0
        self.stream_start_time: float | None = None


class VisionConnectionHandler:
    """Handles a single WebSocket connection for realtime vision processing."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.session: VisionSession | None = None

    async def send_message(self, message: dict | object) -> bool:
        """Send a message to the client.

        Returns:
            True if message was sent, False if connection is closed.
        """
        if self.websocket.client_state != WebSocketState.CONNECTED:
            return False

        data = message.model_dump() if hasattr(message, "model_dump") else message

        try:
            await self.websocket.send_json(data)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False

    async def send_error(
        self, code: str, message: str, details: dict | None = None
    ) -> bool:
        """Send an error message to the client."""
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

            # Update config
            self.session.config = msg.session
            self.session.service = VisionService(msg.session)

            await self.send_message(SessionUpdatedMessage(session=msg.session))

        except Exception as e:
            logger.error(f"Session update error: {e}")
            await self.send_error("session_update_failed", str(e))

    async def handle_input_image(self, data: dict) -> None:
        """Handle input.image message - process a single image."""
        try:
            msg = InputImageMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            # Decode image
            try:
                image_bytes = decode_base64_image(msg.image)
            except Exception as e:
                await self.send_error("invalid_image", f"Failed to decode image: {e}")
                return

            # Run inference based on task
            task = self.session.config.task.value
            service = self.session.service

            if task == "detect":
                result = await service.detect(
                    image=image_bytes,
                    return_annotated=self.session.config.return_image,
                )
            elif task == "segment":
                result = await service.segment(
                    image=image_bytes,
                    return_annotated=self.session.config.return_image,
                )
            elif task == "classify":
                result = await service.classify(image=image_bytes)
            elif task == "pose":
                result = await service.detect_pose(
                    image=image_bytes,
                    return_annotated=self.session.config.return_image,
                )
            else:
                await self.send_error("invalid_task", f"Unknown task: {task}")
                return

            # Send result
            await self.send_message(
                DetectionResultMessage(
                    result=result,
                    timestamp_ms=None,
                    annotated_image=None,  # Already in result if requested
                )
            )

        except Exception as e:
            logger.error(f"Image processing error: {e}")
            await self.send_error("processing_failed", str(e))

    async def handle_video_frame(self, data: dict) -> None:
        """Handle input.video_frame message - process a video frame."""
        try:
            msg = InputVideoFrameMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            # Decode frame
            try:
                frame_bytes = decode_base64_image(msg.frame)
            except Exception as e:
                await self.send_error("invalid_frame", f"Failed to decode frame: {e}")
                return

            # Run inference
            task = self.session.config.task.value
            service = self.session.service

            if task == "detect":
                result = await service.detect(
                    image=frame_bytes,
                    return_annotated=self.session.config.return_image,
                )
            elif task == "segment":
                result = await service.segment(
                    image=frame_bytes,
                    return_annotated=self.session.config.return_image,
                )
            elif task == "pose":
                result = await service.detect_pose(
                    image=frame_bytes,
                    return_annotated=self.session.config.return_image,
                )
            else:
                # Default to detection for video
                result = await service.detect(
                    image=frame_bytes,
                    return_annotated=self.session.config.return_image,
                )

            self.session.frames_processed += 1

            # Send result with timestamp
            await self.send_message(
                DetectionResultMessage(
                    result=result,
                    timestamp_ms=msg.timestamp_ms,
                    annotated_image=None,
                )
            )

        except Exception as e:
            logger.error(f"Frame processing error: {e}")
            await self.send_error("frame_processing_failed", str(e))

    async def handle_stream_start(self, data: dict) -> None:
        """Handle stream.start message - start processing from video source."""
        try:
            msg = StartStreamMessage(**data)
            if self.session is None:
                await self.send_error("session_not_found", "No active session")
                return

            if self.session.stream_active:
                await self.send_error(
                    "stream_already_active", "A stream is already active"
                )
                return

            # Get model for streaming
            model = await get_vision_model(
                model_id=self.session.config.model,
                task=self.session.config.task.value,
            )

            # Parse source
            source = msg.source
            if source.isdigit():
                source = int(source)  # Webcam index

            # Start stream task
            self.session.stream_active = True
            self.session.stream_start_time = time.time()
            self.session.frames_processed = 0

            self.session.stream_task = asyncio.create_task(
                self._process_stream(model, source, msg.fps)
            )

            # Get actual FPS from source (approximate)
            fps = msg.fps or 30.0  # Default if not specified

            await self.send_message(
                StreamStartedMessage(source=str(msg.source), fps=fps)
            )

        except Exception as e:
            logger.error(f"Stream start error: {e}")
            await self.send_error("stream_start_failed", str(e))

    async def _process_stream(
        self, model: Any, source: str | int, target_fps: int | None
    ) -> None:
        """Process video stream and send results."""
        try:
            frame_interval = 1.0 / target_fps if target_fps else 0

            async for result in model.predict_stream(
                source=source,
                confidence=self.session.config.confidence,
                iou_threshold=self.session.config.iou_threshold,
                classes=self.session.config.classes,
            ):
                if not self.session.stream_active:
                    break

                self.session.frames_processed += 1
                timestamp_ms = int(
                    (time.time() - self.session.stream_start_time) * 1000
                )

                # Convert raw result to VisionResult
                vision_result = self.session.service._convert_to_vision_result(result)

                # Send result
                sent = await self.send_message(
                    DetectionResultMessage(
                        result=vision_result,
                        timestamp_ms=timestamp_ms,
                        annotated_image=result.get("annotated_image"),
                    )
                )

                if not sent:
                    # Connection closed
                    break

                # Rate limiting
                if frame_interval > 0:
                    await asyncio.sleep(frame_interval)

        except Exception as e:
            logger.error(f"Stream processing error: {e}")
            await self.send_error("stream_processing_failed", str(e))
        finally:
            await self._stop_stream()

    async def handle_stream_stop(self, data: dict) -> None:
        """Handle stream.stop message."""
        await self._stop_stream()

    async def _stop_stream(self) -> None:
        """Stop the active stream."""
        if self.session is None:
            return

        if not self.session.stream_active:
            return

        self.session.stream_active = False

        if self.session.stream_task and not self.session.stream_task.done():
            self.session.stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.session.stream_task

        duration = 0.0
        if self.session.stream_start_time:
            duration = time.time() - self.session.stream_start_time

        await self.send_message(
            StreamStoppedMessage(
                frames_processed=self.session.frames_processed,
                duration_seconds=duration,
            )
        )

    async def handle_message(self, data: dict) -> None:
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get("type")

        handlers = {
            MessageType.SESSION_UPDATE.value: self.handle_session_update,
            MessageType.INPUT_IMAGE.value: self.handle_input_image,
            MessageType.INPUT_VIDEO_FRAME.value: self.handle_video_frame,
            MessageType.START_STREAM.value: self.handle_stream_start,
            MessageType.STOP_STREAM.value: self.handle_stream_stop,
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
        session_id = generate_session_id()
        config = VisionSessionConfig()
        self.session = VisionSession(session_id, config)

        # Send session.created
        await self.send_message(
            SessionCreatedMessage(
                session_id=session_id,
                session=config,
            )
        )

        try:
            while True:
                try:
                    raw_data = await self.websocket.receive_text()
                    data = json.loads(raw_data)
                except json.JSONDecodeError as e:
                    await self.send_error("invalid_json", f"Invalid JSON: {e}")
                    continue

                await self.handle_message(data)

        except WebSocketDisconnect:
            logger.info(
                f"Vision WebSocket disconnected: {self.session.session_id if self.session else 'unknown'}"
            )
        finally:
            # Cleanup - stop any active streams
            if self.session and self.session.stream_active:
                await self._stop_stream()


@router.websocket("/v1/realtime/vision")
async def vision_websocket(websocket: WebSocket):
    """
    Realtime WebSocket endpoint for video/image processing.

    This endpoint provides real-time vision inference with support for:
    - Single image processing
    - Video frame streaming (client sends frames)
    - Video source streaming (server reads from URL/RTSP/webcam)

    Protocol:
    ---------

    Client -> Server messages:
    - session.update: Update vision settings (model, task, confidence)
    - input.image: Process a single base64-encoded image
    - input.video_frame: Process a video frame with timestamp
    - stream.start: Start processing from video source (URL/RTSP/webcam)
    - stream.stop: Stop video stream processing

    Server -> Client messages:
    - session.created: Initial session with default config
    - session.updated: Configuration updated
    - detection.result: Detection/segmentation results
    - stream.started: Video stream started processing
    - stream.stopped: Video stream stopped
    - error: Error occurred

    Example session.update:
    ```json
    {
      "type": "session.update",
      "session": {
        "task": "detect",
        "model": "yolo11m",
        "confidence": 0.25,
        "iou_threshold": 0.45,
        "return_image": false
      }
    }
    ```

    Example input.image:
    ```json
    {
      "type": "input.image",
      "image": "base64_encoded_image_data...",
      "format": "jpeg"
    }
    ```

    Example stream.start (webcam):
    ```json
    {
      "type": "stream.start",
      "source": "0",
      "fps": 30
    }
    ```

    Example stream.start (RTSP):
    ```json
    {
      "type": "stream.start",
      "source": "rtsp://camera.example.com:554/stream",
      "fps": 15
    }
    ```
    """
    handler = VisionConnectionHandler(websocket)
    await handler.run()
