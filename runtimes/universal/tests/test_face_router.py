"""
Tests for Face Recognition REST API endpoints.
"""

import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def sample_face_image():
    """Create a sample image with a face-like pattern."""
    img = np.ones((300, 300, 3), dtype=np.uint8) * 200

    # Face oval
    for y in range(50, 250):
        for x in range(75, 225):
            if ((x - 150) ** 2) / (75**2) + ((y - 150) ** 2) / (100**2) < 1:
                img[y, x] = [220, 180, 160]

    # Eyes
    for y in range(110, 130):
        for x in range(110, 130):
            img[y, x] = [50, 50, 50]
        for x in range(170, 190):
            img[y, x] = [50, 50, 50]

    # Mouth
    for x in range(120, 180):
        img[200, x] = [150, 50, 50]

    return img


@pytest.fixture
def sample_face_bytes(sample_face_image):
    """Convert sample face image to bytes."""
    pil_img = Image.fromarray(sample_face_image)
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def sample_face_base64(sample_face_bytes):
    """Convert sample face image to base64."""
    return base64.b64encode(sample_face_bytes).decode("utf-8")


@pytest.fixture
def client():
    """Create FastAPI test client."""
    from server import app

    return TestClient(app)


class TestFaceHealth:
    """Test face health endpoint."""

    def test_face_health(self, client):
        """Test /v1/face/health endpoint."""
        response = client.get("/v1/face/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "face"


class TestFaceModels:
    """Test face models list endpoint."""

    def test_list_face_models(self, client):
        """Test /v1/face/models endpoint."""
        response = client.get("/v1/face/models")

        assert response.status_code == 200
        data = response.json()

        assert "recognition_models" in data
        assert "detector_backends" in data
        assert "distance_metrics" in data
        assert "analysis_actions" in data
        assert "default_model" in data
        assert "default_detector" in data

        # Check some expected models exist
        model_names = [m["name"] for m in data["recognition_models"]]
        assert "ArcFace" in model_names
        assert "Facenet512" in model_names

        # Check some expected detectors exist
        detector_names = [d["name"] for d in data["detector_backends"]]
        assert "retinaface" in detector_names
        assert "opencv" in detector_names


class TestFaceDetection:
    """Test face detection endpoints."""

    def test_detect_with_file(self, client, sample_face_bytes):
        """Test face detection with file upload."""
        response = client.post(
            "/v1/face/detect",
            files={"file": ("face.jpg", sample_face_bytes, "image/jpeg")},
            data={"detector_backend": "opencv"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "faces" in data
        assert "count" in data
        assert "detector_backend" in data
        assert data["detector_backend"] == "opencv"

    def test_detect_with_base64(self, client, sample_face_base64):
        """Test face detection with base64 image."""
        response = client.post(
            "/v1/face/detect",
            data={
                "image_base64": sample_face_base64,
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "faces" in data

    def test_detect_json_endpoint(self, client, sample_face_base64):
        """Test JSON face detection endpoint."""
        response = client.post(
            "/v1/face/detect/json",
            json={
                "image_base64": sample_face_base64,
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "faces" in data

    def test_detect_no_image_error(self, client):
        """Test error when no image provided."""
        response = client.post(
            "/v1/face/detect",
            data={"detector_backend": "opencv"},
        )

        assert response.status_code == 400
        assert "Must provide" in response.json()["detail"]


class TestFaceEmbeddings:
    """Test face embedding endpoints."""

    def test_embeddings_with_file(self, client, sample_face_bytes):
        """Test getting embeddings with file upload."""
        response = client.post(
            "/v1/face/embeddings",
            files={"file": ("face.jpg", sample_face_bytes, "image/jpeg")},
            data={
                "model": "ArcFace",
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "embeddings" in data
        assert "count" in data
        assert "model" in data

    def test_embeddings_json_endpoint(self, client, sample_face_base64):
        """Test JSON embeddings endpoint."""
        response = client.post(
            "/v1/face/embeddings/json",
            json={
                "image_base64": sample_face_base64,
                "model": "ArcFace",
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "embeddings" in data


class TestFaceVerification:
    """Test face verification endpoints."""

    def test_verify_with_files(self, client, sample_face_bytes):
        """Test verification with file uploads."""
        response = client.post(
            "/v1/face/verify",
            files={
                "file1": ("face1.jpg", sample_face_bytes, "image/jpeg"),
                "file2": ("face2.jpg", sample_face_bytes, "image/jpeg"),
            },
            data={
                "model": "ArcFace",
                "detector_backend": "opencv",
                "distance_metric": "cosine",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "verified" in data
        assert "distance" in data
        assert "threshold" in data
        assert "model" in data
        assert "detector_backend" in data
        assert "distance_metric" in data

    def test_verify_with_base64(self, client, sample_face_base64):
        """Test verification with base64 images."""
        response = client.post(
            "/v1/face/verify",
            data={
                "image1_base64": sample_face_base64,
                "image2_base64": sample_face_base64,
                "model": "ArcFace",
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "verified" in data

    def test_verify_json_endpoint(self, client, sample_face_base64):
        """Test JSON verification endpoint."""
        response = client.post(
            "/v1/face/verify/json",
            json={
                "image1_base64": sample_face_base64,
                "image2_base64": sample_face_base64,
                "model": "ArcFace",
                "detector_backend": "opencv",
                "distance_metric": "cosine",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "verified" in data

    def test_verify_missing_image_error(self, client, sample_face_base64):
        """Test error when missing second image."""
        response = client.post(
            "/v1/face/verify",
            data={
                "image1_base64": sample_face_base64,
                "model": "ArcFace",
            },
        )

        assert response.status_code == 400
        assert "Must provide" in response.json()["detail"]


class TestFaceAnalysis:
    """Test face analysis endpoints."""

    def test_analyze_with_file(self, client, sample_face_bytes):
        """Test face analysis with file upload."""
        response = client.post(
            "/v1/face/analyze",
            files={"file": ("face.jpg", sample_face_bytes, "image/jpeg")},
            data={
                "actions": "age,gender,emotion",
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "faces" in data
        assert "count" in data
        assert "actions" in data
        assert set(data["actions"]) == {"age", "gender", "emotion"}

    def test_analyze_with_all_actions(self, client, sample_face_bytes):
        """Test analysis with all actions."""
        response = client.post(
            "/v1/face/analyze",
            files={"file": ("face.jpg", sample_face_bytes, "image/jpeg")},
            data={
                "actions": "age,gender,emotion,race",
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "race" in data["actions"]

    def test_analyze_json_endpoint(self, client, sample_face_base64):
        """Test JSON analysis endpoint."""
        response = client.post(
            "/v1/face/analyze/json",
            json={
                "image_base64": sample_face_base64,
                "actions": ["age", "gender"],
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "faces" in data


class TestFaceErrorHandling:
    """Test error handling across endpoints."""

    def test_invalid_base64_image(self, client):
        """Test error on invalid base64."""
        response = client.post(
            "/v1/face/detect",
            data={
                "image_base64": "not-valid-base64!!!",
                "detector_backend": "opencv",
            },
        )

        assert response.status_code == 400
        assert "Invalid base64" in response.json()["detail"]
