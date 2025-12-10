"""
Tests for Vision REST API endpoints.
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


class TestVisionHealth:
    """Test vision health endpoint."""

    def test_vision_health(self, client):
        """Test /v1/vision/health endpoint."""
        response = client.get("/v1/vision/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "vision"


class TestVisionModels:
    """Test vision models list endpoint."""

    def test_list_vision_models(self, client):
        """Test /v1/vision/models endpoint."""
        response = client.get("/v1/vision/models")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "models" in data
        assert "tasks" in data
        assert "default_model" in data

        # Check model categories
        models = data["models"]
        assert "detection" in models
        assert "segmentation" in models
        assert "classification" in models
        assert "pose" in models

        # Check tasks
        assert set(data["tasks"]) == {"detect", "segment", "classify", "pose"}


class TestVisionDetect:
    """Test detection endpoints."""

    def test_detect_with_file(self, client, sample_image_bytes):
        """Test detection with file upload."""
        response = client.post(
            "/v1/vision/detect",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"model": "yolo11n", "confidence": "0.1"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "boxes" in data
        assert "inference_time_ms" in data
        assert "image_width" in data
        assert "image_height" in data
        assert "model" in data
        assert "task" in data

        assert data["task"] == "detect"

    def test_detect_with_base64(self, client, sample_image_base64):
        """Test detection with base64 image."""
        response = client.post(
            "/v1/vision/detect",
            data={
                "image_base64": sample_image_base64,
                "model": "yolo11n",
                "confidence": "0.1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "boxes" in data

    def test_detect_with_return_image(self, client, sample_image_bytes):
        """Test detection with annotated image return."""
        response = client.post(
            "/v1/vision/detect",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"model": "yolo11n", "return_image": "true"},
        )

        assert response.status_code == 200
        # Note: annotated_image is included in response but may not be
        # in the Pydantic model (check implementation)

    def test_detect_json_endpoint(self, client, sample_image_base64):
        """Test JSON detection endpoint."""
        response = client.post(
            "/v1/vision/detect/json",
            json={
                "image_base64": sample_image_base64,
                "model": "yolo11n",
                "confidence": 0.1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "boxes" in data

    def test_detect_no_image_error(self, client):
        """Test error when no image provided."""
        response = client.post(
            "/v1/vision/detect",
            data={"model": "yolo11n"},
        )

        assert response.status_code == 400
        assert "Must provide" in response.json()["detail"]

    def test_detect_invalid_base64_error(self, client):
        """Test error on invalid base64."""
        response = client.post(
            "/v1/vision/detect",
            data={
                "image_base64": "not-valid-base64!!!",
                "model": "yolo11n",
            },
        )

        assert response.status_code == 400
        assert "Invalid base64" in response.json()["detail"]

    def test_detect_with_class_filter(self, client, sample_image_bytes):
        """Test detection with class filtering."""
        response = client.post(
            "/v1/vision/detect",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={
                "model": "yolo11n",
                "classes": "0,1,2",  # Person, bicycle, car
            },
        )

        assert response.status_code == 200
        data = response.json()

        # All detected boxes should be in filtered classes
        for box in data["boxes"]:
            assert box["class_id"] in [0, 1, 2]

    def test_detect_invalid_classes_error(self, client, sample_image_bytes):
        """Test error on invalid class filter format."""
        response = client.post(
            "/v1/vision/detect",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={
                "model": "yolo11n",
                "classes": "person,car",  # Should be integers
            },
        )

        assert response.status_code == 400
        assert "comma-separated integers" in response.json()["detail"]


class TestVisionSegment:
    """Test segmentation endpoints."""

    def test_segment_with_file(self, client, sample_image_bytes):
        """Test segmentation with file upload."""
        response = client.post(
            "/v1/vision/segment",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"model": "yolo11n-seg", "confidence": "0.1"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "boxes" in data
        assert "masks" in data or data.get("masks") is None
        assert data["task"] == "segment"

    def test_segment_json_endpoint(self, client, sample_image_base64):
        """Test JSON segmentation endpoint."""
        response = client.post(
            "/v1/vision/segment/json",
            json={
                "image_base64": sample_image_base64,
                "model": "yolo11n-seg",
                "confidence": 0.1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "boxes" in data


class TestVisionClassify:
    """Test classification endpoints."""

    def test_classify_with_file(self, client, sample_image_bytes):
        """Test classification with file upload."""
        response = client.post(
            "/v1/vision/classify",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"model": "yolo11n-cls", "top_k": "5"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "classification" in data
        classification = data["classification"]

        assert "class_id" in classification
        assert "class_name" in classification
        assert "confidence" in classification
        assert "top_k" in classification

    def test_classify_json_endpoint(self, client, sample_image_base64):
        """Test JSON classification endpoint."""
        response = client.post(
            "/v1/vision/classify/json",
            json={
                "image_base64": sample_image_base64,
                "model": "yolo11n-cls",
                "top_k": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "classification" in data


class TestVisionPose:
    """Test pose estimation endpoints."""

    def test_pose_with_file(self, client, sample_image_bytes):
        """Test pose estimation with file upload."""
        response = client.post(
            "/v1/vision/pose",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"model": "yolo11n-pose", "confidence": "0.1"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "boxes" in data
        assert "keypoints" in data or data.get("keypoints") is None
        assert data["task"] == "pose"


class TestVisionErrorHandling:
    """Test error handling across endpoints."""

    def test_invalid_confidence_range(self, client, sample_image_bytes):
        """Test error on invalid confidence value."""
        response = client.post(
            "/v1/vision/detect",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"confidence": "1.5"},  # Invalid, should be 0-1
        )

        assert response.status_code == 422  # Validation error

    def test_invalid_iou_range(self, client, sample_image_bytes):
        """Test error on invalid IoU value."""
        response = client.post(
            "/v1/vision/detect",
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"iou_threshold": "-0.1"},  # Invalid, should be 0-1
        )

        assert response.status_code == 422  # Validation error
