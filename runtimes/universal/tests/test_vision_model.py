"""
Tests for VisionModel (object detection, segmentation, classification, pose estimation).

Uses YOLO11 nano (smallest) models for fast testing.
"""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from models.vision_model import VisionModel

# Test model IDs - using smallest models for speed
VISION_TEST_MODELS = {
    "detect": "yolo11n",  # Smallest detection model
    "segment": "yolo11n-seg",  # Smallest segmentation model
    "classify": "yolo11n-cls",  # Smallest classification model
    "pose": "yolo11n-pose",  # Smallest pose model
}


@pytest.fixture
def sample_image_array():
    """Create a sample RGB image as numpy array."""
    # Create a 640x480 image with some basic patterns
    # This should trigger some detections in COCO-trained models
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    # Add a bright rectangle (might be detected as something)
    img[100:300, 200:400] = [255, 255, 255]

    # Add some color variation
    img[150:250, 250:350] = [255, 0, 0]  # Red square

    return img


@pytest.fixture
def sample_image_bytes(sample_image_array):
    """Convert sample image to bytes (JPEG format)."""
    img = Image.fromarray(sample_image_array)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def sample_image_base64(sample_image_bytes):
    """Convert sample image to base64 string."""
    return base64.b64encode(sample_image_bytes).decode("utf-8")


@pytest.fixture
def sample_person_image():
    """Create a larger image that might trigger person detection."""
    # Create a simple humanoid shape
    img = np.zeros((640, 640, 3), dtype=np.uint8)

    # Background
    img[:, :] = [200, 200, 200]  # Gray background

    # Head (circle approximation with rectangle)
    img[100:180, 280:360] = [255, 220, 180]  # Skin tone

    # Body
    img[180:400, 260:380] = [50, 50, 200]  # Blue shirt

    # Legs
    img[400:600, 260:310] = [50, 50, 50]  # Dark pants
    img[400:600, 330:380] = [50, 50, 50]

    return img


class TestVisionModelLoading:
    """Test vision model loading."""

    @pytest.mark.asyncio
    async def test_load_detection_model(self, device):
        """Test loading a detection model."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        assert model.model is not None
        assert model.model_type == "vision_detect"
        assert len(model.class_names) > 0  # COCO has 80 classes

        await model.unload()
        assert model.model is None

    @pytest.mark.asyncio
    async def test_load_segmentation_model(self, device):
        """Test loading a segmentation model."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["segment"],
            device=device,
            task="segment",
        )
        await model.load()

        assert model.model is not None
        assert model.model_type == "vision_segment"

        await model.unload()

    @pytest.mark.asyncio
    async def test_load_classification_model(self, device):
        """Test loading a classification model."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["classify"],
            device=device,
            task="classify",
        )
        await model.load()

        assert model.model is not None
        assert model.model_type == "vision_classify"
        # ImageNet has 1000 classes
        assert len(model.class_names) > 0

        await model.unload()

    @pytest.mark.asyncio
    async def test_load_pose_model(self, device):
        """Test loading a pose estimation model."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["pose"],
            device=device,
            task="pose",
        )
        await model.load()

        assert model.model is not None
        assert model.model_type == "vision_pose"

        await model.unload()

    @pytest.mark.asyncio
    async def test_model_info(self, device):
        """Test getting model info."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        info = model.get_model_info()

        assert info["model_id"] == VISION_TEST_MODELS["detect"]
        assert info["model_type"] == "vision_detect"
        assert info["device"] == device
        assert info["task"] == "detect"
        assert "num_classes" in info
        assert "class_names" in info

        await model.unload()


class TestVisionModelPrediction:
    """Test vision model prediction."""

    @pytest.mark.asyncio
    async def test_predict_from_numpy(self, device, sample_image_array):
        """Test prediction from numpy array."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        result = await model.predict(
            image=sample_image_array,
            confidence=0.1,  # Low threshold for test image
        )

        # Check result structure
        assert "boxes" in result
        assert "inference_time_ms" in result
        assert "image_width" in result
        assert "image_height" in result
        assert "model" in result
        assert "task" in result

        assert result["image_width"] == 640
        assert result["image_height"] == 480
        assert result["task"] == "detect"

        await model.unload()

    @pytest.mark.asyncio
    async def test_predict_from_bytes(self, device, sample_image_bytes):
        """Test prediction from image bytes."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        result = await model.predict(
            image=sample_image_bytes,
            confidence=0.1,
        )

        assert "boxes" in result
        assert result["image_width"] == 640
        assert result["image_height"] == 480

        await model.unload()

    @pytest.mark.asyncio
    async def test_predict_from_base64(self, device, sample_image_base64):
        """Test prediction from base64 string."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        result = await model.predict(
            image=sample_image_base64,
            confidence=0.1,
        )

        assert "boxes" in result

        await model.unload()

    @pytest.mark.asyncio
    async def test_predict_with_data_url(self, device, sample_image_base64):
        """Test prediction from data URL format."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        data_url = f"data:image/jpeg;base64,{sample_image_base64}"
        result = await model.predict(
            image=data_url,
            confidence=0.1,
        )

        assert "boxes" in result

        await model.unload()

    @pytest.mark.asyncio
    async def test_predict_with_annotated_output(self, device, sample_image_array):
        """Test prediction with annotated image output."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        result = await model.predict(
            image=sample_image_array,
            confidence=0.1,
            return_annotated=True,
        )

        # Should include annotated image as base64
        assert "annotated_image" in result
        assert isinstance(result["annotated_image"], str)

        # Verify it's valid base64
        try:
            decoded = base64.b64decode(result["annotated_image"])
            assert len(decoded) > 0
        except Exception as e:
            pytest.fail(f"Invalid base64 annotated image: {e}")

        await model.unload()

    @pytest.mark.asyncio
    async def test_predict_with_class_filter(self, device, sample_image_array):
        """Test prediction with class filtering."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        # Filter to only detect persons (class 0 in COCO)
        result = await model.predict(
            image=sample_image_array,
            confidence=0.1,
            classes=[0],  # Person only
        )

        assert "boxes" in result
        # All detected boxes should be class 0 (if any detected)
        for box in result["boxes"]:
            assert box["class_id"] == 0

        await model.unload()


class TestVisionModelSegmentation:
    """Test segmentation model."""

    @pytest.mark.asyncio
    async def test_segmentation_output(self, device, sample_image_array):
        """Test segmentation model output includes masks."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["segment"],
            device=device,
            task="segment",
        )
        await model.load()

        result = await model.predict(
            image=sample_image_array,
            confidence=0.1,
        )

        # Check structure
        assert "boxes" in result
        assert "masks" in result or result["masks"] is None
        assert result["task"] == "segment"

        # If there are detections, masks should exist
        if len(result["boxes"]) > 0 and result["masks"] is not None:
            assert len(result["masks"]) > 0
            for mask in result["masks"]:
                assert "contour" in mask
                assert "class_id" in mask
                assert "class_name" in mask
                assert "area" in mask

        await model.unload()


class TestVisionModelClassification:
    """Test classification model."""

    @pytest.mark.asyncio
    async def test_classification_output(self, device, sample_image_array):
        """Test classification model output."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["classify"],
            device=device,
            task="classify",
        )
        await model.load()

        result = await model.predict(
            image=sample_image_array,
            confidence=0.0,  # No filtering for classification
        )

        # Check structure
        assert "classification" in result
        assert result["classification"] is not None

        classification = result["classification"]
        assert "class_id" in classification
        assert "class_name" in classification
        assert "confidence" in classification
        assert "top_k" in classification

        # Top-k should have multiple predictions
        assert isinstance(classification["top_k"], list)
        assert len(classification["top_k"]) > 0

        await model.unload()


class TestVisionModelPose:
    """Test pose estimation model."""

    @pytest.mark.asyncio
    async def test_pose_output_structure(self, device, sample_person_image):
        """Test pose model output structure."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["pose"],
            device=device,
            task="pose",
        )
        await model.load()

        result = await model.predict(
            image=sample_person_image,
            confidence=0.1,
        )

        # Check structure
        assert "boxes" in result
        assert "keypoints" in result or result["keypoints"] is None
        assert result["task"] == "pose"

        # If there are detections, keypoints should exist
        if result["keypoints"] is not None and len(result["keypoints"]) > 0:
            for person in result["keypoints"]:
                assert "keypoints" in person
                # COCO has 17 keypoints
                assert len(person["keypoints"]) == 17

                for kpt in person["keypoints"]:
                    assert "x" in kpt
                    assert "y" in kpt
                    assert "confidence" in kpt
                    assert "name" in kpt

        await model.unload()


class TestVisionModelBatch:
    """Test batch prediction."""

    @pytest.mark.asyncio
    async def test_batch_prediction(self, device, sample_image_array):
        """Test batch prediction on multiple images."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        # Create variations of the sample image
        images = [
            sample_image_array,
            np.fliplr(sample_image_array).copy(),  # Flipped horizontally
            np.flipud(sample_image_array).copy(),  # Flipped vertically
        ]

        results = await model.predict_batch(
            images=images,
            confidence=0.1,
        )

        assert isinstance(results, list)
        assert len(results) == 3

        for result in results:
            assert "boxes" in result
            assert "inference_time_ms" in result

        await model.unload()


class TestVisionModelErrors:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_predict_without_load(self, device, sample_image_array):
        """Test that prediction fails without loading model."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )

        # Don't call load()

        with pytest.raises(RuntimeError, match="Model not loaded"):
            await model.predict(sample_image_array)

    @pytest.mark.asyncio
    async def test_invalid_image_type(self, device):
        """Test error on invalid image type."""
        model = VisionModel(
            model_id=VISION_TEST_MODELS["detect"],
            device=device,
            task="detect",
        )
        await model.load()

        with pytest.raises(ValueError, match="Unsupported image type"):
            await model.predict(12345)  # Invalid type

        await model.unload()
