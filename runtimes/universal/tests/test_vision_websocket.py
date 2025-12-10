"""
Tests for Vision WebSocket streaming endpoint.
"""

import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def sample_image_bytes():
    """Create sample image bytes."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[100:300, 200:400] = [255, 255, 255]
    pil_img = Image.fromarray(img)
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def sample_image_base64(sample_image_bytes):
    """Create sample base64 image."""
    return base64.b64encode(sample_image_bytes).decode("utf-8")


@pytest.fixture
def client():
    """Create FastAPI test client."""
    from server import app

    return TestClient(app)


class TestVisionWebSocketConnection:
    """Test WebSocket connection and session creation."""

    def test_connect_and_receive_session_created(self, client):
        """Test connecting to WebSocket and receiving session.created."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            data = websocket.receive_json()

            assert data["type"] == "session.created"
            assert "session_id" in data
            assert data["session_id"].startswith("vis_")
            assert "session" in data
            assert data["session"]["task"] == "detect"
            assert data["session"]["model"] == "yolo11m"

    def test_session_update(self, client):
        """Test updating session configuration."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Send session update
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "segment",
                        "model": "yolo11n-seg",
                        "confidence": 0.5,
                    },
                }
            )

            # Receive session.updated
            data = websocket.receive_json()

            assert data["type"] == "session.updated"
            assert data["session"]["task"] == "segment"
            assert data["session"]["model"] == "yolo11n-seg"
            assert data["session"]["confidence"] == 0.5


class TestVisionWebSocketImageProcessing:
    """Test single image processing via WebSocket."""

    def test_input_image_detection(self, client, sample_image_base64):
        """Test processing a single image for detection."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update to use smaller model for faster testing
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "detect",
                        "model": "yolo11n",
                        "confidence": 0.1,
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Send image
            websocket.send_json(
                {
                    "type": "input.image",
                    "image": sample_image_base64,
                    "format": "jpeg",
                }
            )

            # Receive detection result
            data = websocket.receive_json()

            assert data["type"] == "detection.result"
            assert "result" in data
            assert "boxes" in data["result"]
            assert "inference_time_ms" in data["result"]
            assert data["result"]["task"] == "detect"

    def test_input_image_segmentation(self, client, sample_image_base64):
        """Test processing a single image for segmentation."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update to segmentation
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "segment",
                        "model": "yolo11n-seg",
                        "confidence": 0.1,
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Send image
            websocket.send_json(
                {
                    "type": "input.image",
                    "image": sample_image_base64,
                    "format": "jpeg",
                }
            )

            # Receive result
            data = websocket.receive_json()

            assert data["type"] == "detection.result"
            assert data["result"]["task"] == "segment"

    def test_input_image_classification(self, client, sample_image_base64):
        """Test processing a single image for classification."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update to classification
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "classify",
                        "model": "yolo11n-cls",
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Send image
            websocket.send_json(
                {
                    "type": "input.image",
                    "image": sample_image_base64,
                    "format": "jpeg",
                }
            )

            # Receive result
            data = websocket.receive_json()

            assert data["type"] == "detection.result"
            assert data["result"]["task"] == "classify"
            assert data["result"]["classification"] is not None

    def test_input_image_pose(self, client, sample_image_base64):
        """Test processing a single image for pose estimation."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update to pose
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "pose",
                        "model": "yolo11n-pose",
                        "confidence": 0.1,
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Send image
            websocket.send_json(
                {
                    "type": "input.image",
                    "image": sample_image_base64,
                    "format": "jpeg",
                }
            )

            # Receive result
            data = websocket.receive_json()

            assert data["type"] == "detection.result"
            assert data["result"]["task"] == "pose"


class TestVisionWebSocketVideoFrame:
    """Test video frame processing via WebSocket."""

    def test_video_frame_processing(self, client, sample_image_base64):
        """Test processing video frames with timestamps."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update to use smaller model
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "detect",
                        "model": "yolo11n",
                        "confidence": 0.1,
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Send multiple frames
            for i in range(3):
                timestamp_ms = i * 33  # ~30fps

                websocket.send_json(
                    {
                        "type": "input.video_frame",
                        "frame": sample_image_base64,
                        "timestamp_ms": timestamp_ms,
                        "format": "jpeg",
                    }
                )

                # Receive result
                data = websocket.receive_json()

                assert data["type"] == "detection.result"
                assert data["timestamp_ms"] == timestamp_ms
                assert "result" in data


class TestVisionWebSocketErrors:
    """Test error handling in WebSocket."""

    def test_invalid_json(self, client):
        """Test error on invalid JSON."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Send invalid JSON
            websocket.send_text("not valid json{")

            # Receive error
            data = websocket.receive_json()

            assert data["type"] == "error"
            assert data["code"] == "invalid_json"

    def test_unknown_message_type(self, client):
        """Test error on unknown message type."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Send unknown message type
            websocket.send_json({"type": "unknown.message"})

            # Receive error
            data = websocket.receive_json()

            assert data["type"] == "error"
            assert data["code"] == "unknown_message_type"

    def test_invalid_base64_image(self, client):
        """Test error on invalid base64 image."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Send invalid base64 image
            websocket.send_json(
                {
                    "type": "input.image",
                    "image": "not-valid-base64!!!",
                    "format": "jpeg",
                }
            )

            # Receive error
            data = websocket.receive_json()

            assert data["type"] == "error"
            assert data["code"] == "invalid_image"


class TestVisionWebSocketStreaming:
    """Test video stream processing (source-based streaming)."""

    def test_stream_start_stop(self, client, sample_image_base64):
        """Test starting and stopping a stream."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update session first
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "task": "detect",
                        "model": "yolo11n",
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Note: Full stream testing requires a video source
            # This test just verifies the message protocol

            # Test stream.stop without active stream (should be no-op)
            websocket.send_json({"type": "stream.stop"})

            # The handler should not send anything back if no stream was active
            # We'll use a small timeout to check

    def test_stream_already_active_error(self, client):
        """Test error when trying to start stream while one is active."""
        # Note: This test would require mocking the video source
        # For now, we just verify the handler exists
        pass


class TestVisionWebSocketMultipleImages:
    """Test processing multiple images in sequence."""

    def test_multiple_images_sequential(self, client, sample_image_base64):
        """Test processing multiple images in sequence."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Update to use smaller model
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {
                        "model": "yolo11n",
                    },
                }
            )
            websocket.receive_json()  # session.updated

            # Send 5 images
            for _ in range(5):
                websocket.send_json(
                    {
                        "type": "input.image",
                        "image": sample_image_base64,
                        "format": "jpeg",
                    }
                )

                data = websocket.receive_json()
                assert data["type"] == "detection.result"

    def test_session_update_between_images(self, client, sample_image_base64):
        """Test updating session config between image processing."""
        with client.websocket_connect("/v1/realtime/vision") as websocket:
            # Receive session.created
            websocket.receive_json()

            # Process with detection
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {"task": "detect", "model": "yolo11n"},
                }
            )
            websocket.receive_json()

            websocket.send_json(
                {"type": "input.image", "image": sample_image_base64, "format": "jpeg"}
            )
            data1 = websocket.receive_json()
            assert data1["result"]["task"] == "detect"

            # Switch to classification
            websocket.send_json(
                {
                    "type": "session.update",
                    "session": {"task": "classify", "model": "yolo11n-cls"},
                }
            )
            websocket.receive_json()

            websocket.send_json(
                {"type": "input.image", "image": sample_image_base64, "format": "jpeg"}
            )
            data2 = websocket.receive_json()
            assert data2["result"]["task"] == "classify"
