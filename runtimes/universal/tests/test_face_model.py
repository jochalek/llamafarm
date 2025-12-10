"""
Tests for FaceModel (face detection, verification, and analysis).

Uses DeepFace with various backends.
"""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from models.face_model import DETECTOR_BACKENDS, RECOGNITION_MODELS, FaceModel


@pytest.fixture
def sample_face_image():
    """Create a sample image with a face-like pattern."""
    # Create a simple face-like pattern (oval shape with features)
    img = np.ones((300, 300, 3), dtype=np.uint8) * 200  # Gray background

    # Face oval (skin tone)
    for y in range(50, 250):
        for x in range(75, 225):
            # Ellipse check
            if ((x - 150) ** 2) / (75**2) + ((y - 150) ** 2) / (100**2) < 1:
                img[y, x] = [220, 180, 160]  # Skin tone

    # Eyes (dark circles)
    for y in range(110, 130):
        for x in range(110, 130):
            img[y, x] = [50, 50, 50]
        for x in range(170, 190):
            img[y, x] = [50, 50, 50]

    # Mouth (red line)
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


class TestFaceModelLoading:
    """Test face model loading."""

    @pytest.mark.asyncio
    async def test_load_arcface_model(self, device):
        """Test loading ArcFace model."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",  # Fastest for testing
        )
        await model.load()

        assert model._initialized is True
        assert model.model_type == "face_recognition"

        await model.unload()
        assert model._initialized is False

    @pytest.mark.asyncio
    async def test_model_info(self, device):
        """Test getting model info."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        info = model.get_model_info()

        assert info["model_id"] == "ArcFace"
        assert info["recognition_model"] == "ArcFace"
        assert info["detector_backend"] == "opencv"
        assert "supported_detectors" in info
        assert "supported_models" in info

        await model.unload()


class TestFaceDetection:
    """Test face detection."""

    @pytest.mark.asyncio
    async def test_detect_faces_from_bytes(self, device, sample_face_bytes):
        """Test face detection from image bytes."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        faces = await model.detect_faces(
            image=sample_face_bytes,
            align=False,
        )

        # Result should be a list (may or may not detect faces in synthetic image)
        assert isinstance(faces, list)

        await model.unload()

    @pytest.mark.asyncio
    async def test_detect_faces_from_numpy(self, device, sample_face_image):
        """Test face detection from numpy array."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        faces = await model.detect_faces(
            image=sample_face_image,
            align=False,
        )

        assert isinstance(faces, list)

        await model.unload()

    @pytest.mark.asyncio
    async def test_detect_faces_from_base64(self, device, sample_face_base64):
        """Test face detection from base64 string."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        faces = await model.detect_faces(
            image=sample_face_base64,
            align=False,
        )

        assert isinstance(faces, list)

        await model.unload()


class TestFaceEmbedding:
    """Test face embedding generation."""

    @pytest.mark.asyncio
    async def test_get_embedding(self, device, sample_face_bytes):
        """Test getting face embeddings."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        embeddings = await model.get_embedding(
            image=sample_face_bytes,
        )

        assert isinstance(embeddings, list)
        # If faces detected, embeddings should have the right structure
        for emb in embeddings:
            assert "embedding" in emb
            assert "box" in emb
            assert "model" in emb
            assert isinstance(emb["embedding"], list)

        await model.unload()


class TestFaceVerification:
    """Test face verification."""

    @pytest.mark.asyncio
    async def test_verify_same_image(self, device, sample_face_bytes):
        """Test verification with the same image."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        result = await model.verify(
            img1=sample_face_bytes,
            img2=sample_face_bytes,
        )

        assert "verified" in result
        assert "distance" in result
        assert "threshold" in result
        assert "model" in result
        assert "distance_metric" in result

        await model.unload()

    @pytest.mark.asyncio
    async def test_verify_different_metrics(self, device, sample_face_bytes):
        """Test verification with different distance metrics."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        for metric in ["cosine", "euclidean", "euclidean_l2"]:
            result = await model.verify(
                img1=sample_face_bytes,
                img2=sample_face_bytes,
                distance_metric=metric,
            )

            assert result["distance_metric"] == metric

        await model.unload()


class TestFaceAnalysis:
    """Test face analysis."""

    @pytest.mark.asyncio
    async def test_analyze_faces(self, device, sample_face_bytes):
        """Test face analysis."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        analyses = await model.analyze(
            image=sample_face_bytes,
            actions=["age", "gender", "emotion"],
        )

        assert isinstance(analyses, list)
        # If faces detected, analyses should have the right structure
        for analysis in analyses:
            assert "box" in analysis
            # Age, gender, emotion should be present (if face detected)

        await model.unload()

    @pytest.mark.asyncio
    async def test_analyze_with_all_actions(self, device, sample_face_bytes):
        """Test analysis with all actions."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        analyses = await model.analyze(
            image=sample_face_bytes,
            actions=["age", "gender", "emotion", "race"],
        )

        assert isinstance(analyses, list)

        await model.unload()


class TestFaceModelErrors:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_invalid_image_type(self, device):
        """Test error on invalid image type."""
        model = FaceModel(
            model_id="ArcFace",
            device=device,
            detector_backend="opencv",
        )
        await model.load()

        with pytest.raises(ValueError, match="Unsupported image type"):
            await model.detect_faces(12345)

        await model.unload()


class TestSupportedBackends:
    """Test supported backends and models."""

    def test_detector_backends_list(self):
        """Test that detector backends are defined."""
        assert len(DETECTOR_BACKENDS) > 0
        assert "retinaface" in DETECTOR_BACKENDS
        assert "opencv" in DETECTOR_BACKENDS
        assert "mtcnn" in DETECTOR_BACKENDS

    def test_recognition_models_list(self):
        """Test that recognition models are defined."""
        assert len(RECOGNITION_MODELS) > 0
        assert "ArcFace" in RECOGNITION_MODELS
        assert "Facenet512" in RECOGNITION_MODELS
        assert "VGG-Face" in RECOGNITION_MODELS
