"""
Tests for VisionService (service layer for vision operations).
"""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from routers.vision.service import (
    VisionService,
    decode_base64_image,
    generate_session_id,
    get_vision_model,
    unload_vision_model,
)
from routers.vision.types import VisionSessionConfig, VisionTask


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


class TestHelperFunctions:
    """Test helper functions."""

    def test_generate_session_id(self):
        """Test session ID generation."""
        session_id = generate_session_id()

        assert session_id.startswith("vis_")
        assert len(session_id) == 16  # "vis_" + 12 hex chars

        # Each call should generate unique ID
        session_id2 = generate_session_id()
        assert session_id != session_id2

    def test_decode_base64_image(self, sample_image_base64):
        """Test base64 image decoding."""
        result = decode_base64_image(sample_image_base64)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_decode_base64_with_data_url(self, sample_image_base64):
        """Test base64 decoding with data URL prefix."""
        data_url = f"data:image/jpeg;base64,{sample_image_base64}"
        result = decode_base64_image(data_url)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_decode_invalid_base64(self):
        """Test error on invalid base64."""
        with pytest.raises(ValueError):
            decode_base64_image("not-valid-base64!!!")


class TestVisionModelCaching:
    """Test vision model caching."""

    @pytest.mark.asyncio
    async def test_get_vision_model_caching(self):
        """Test that models are cached."""
        model1 = await get_vision_model("yolo11n", "detect")
        model2 = await get_vision_model("yolo11n", "detect")

        # Should be the same cached instance
        assert model1 is model2

        # Cleanup
        await unload_vision_model("yolo11n", "detect")

    @pytest.mark.asyncio
    async def test_different_tasks_different_models(self):
        """Test that different tasks use different models."""
        model_detect = await get_vision_model("yolo11n", "detect")
        model_segment = await get_vision_model("yolo11n-seg", "segment")

        # Should be different instances
        assert model_detect is not model_segment

        # Cleanup
        await unload_vision_model("yolo11n", "detect")
        await unload_vision_model("yolo11n-seg", "segment")

    @pytest.mark.asyncio
    async def test_unload_vision_model(self):
        """Test model unloading."""
        model = await get_vision_model("yolo11n", "detect")
        assert model is not None

        result = await unload_vision_model("yolo11n", "detect")
        assert result is True

        # Unloading again should return False
        result = await unload_vision_model("yolo11n", "detect")
        assert result is False


class TestVisionService:
    """Test VisionService class."""

    @pytest.mark.asyncio
    async def test_service_default_config(self, sample_image_bytes):
        """Test service with default configuration."""
        service = VisionService()

        # Default task is detect
        assert service.config.task == VisionTask.DETECT
        assert service.config.model == "yolo11m"
        assert service.config.confidence == 0.25

    @pytest.mark.asyncio
    async def test_service_custom_config(self):
        """Test service with custom configuration."""
        config = VisionSessionConfig(
            task=VisionTask.DETECT,
            model="yolo11n",
            confidence=0.5,
            iou_threshold=0.6,
            classes=[0, 1, 2],
        )
        service = VisionService(config)

        assert service.config.model == "yolo11n"
        assert service.config.confidence == 0.5
        assert service.config.iou_threshold == 0.6
        assert service.config.classes == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_service_detect(self, sample_image_bytes):
        """Test detection via service."""
        config = VisionSessionConfig(
            task=VisionTask.DETECT,
            model="yolo11n",
            confidence=0.1,
        )
        service = VisionService(config)

        result = await service.detect(
            image=sample_image_bytes,
            return_annotated=False,
        )

        # Check result type
        assert hasattr(result, "boxes")
        assert hasattr(result, "inference_time_ms")
        assert hasattr(result, "image_width")
        assert hasattr(result, "image_height")

    @pytest.mark.asyncio
    async def test_service_segment(self, sample_image_bytes):
        """Test segmentation via service."""
        config = VisionSessionConfig(
            task=VisionTask.SEGMENT,
            model="yolo11n-seg",
            confidence=0.1,
        )
        service = VisionService(config)

        result = await service.segment(
            image=sample_image_bytes,
            return_annotated=False,
        )

        assert hasattr(result, "boxes")
        assert hasattr(result, "masks")

    @pytest.mark.asyncio
    async def test_service_classify(self, sample_image_bytes):
        """Test classification via service."""
        config = VisionSessionConfig(
            task=VisionTask.CLASSIFY,
            model="yolo11n-cls",
        )
        service = VisionService(config)

        result = await service.classify(
            image=sample_image_bytes,
            top_k=5,
        )

        assert hasattr(result, "classification")
        assert result.classification is not None

    @pytest.mark.asyncio
    async def test_service_detect_pose(self, sample_image_bytes):
        """Test pose detection via service."""
        config = VisionSessionConfig(
            task=VisionTask.POSE,
            model="yolo11n-pose",
            confidence=0.1,
        )
        service = VisionService(config)

        result = await service.detect_pose(
            image=sample_image_bytes,
            return_annotated=False,
        )

        assert hasattr(result, "boxes")
        assert hasattr(result, "keypoints")

    @pytest.mark.asyncio
    async def test_service_auto_model_switch_segment(self, sample_image_bytes):
        """Test automatic model switching for segmentation."""
        # Start with detect model
        config = VisionSessionConfig(
            task=VisionTask.SEGMENT,
            model="yolo11n",  # Not a seg model
        )
        service = VisionService(config)

        # Service should switch to seg variant
        await service.segment(image=sample_image_bytes)

        # Model should have been switched
        assert service.config.model == "yolo11n-seg"

    @pytest.mark.asyncio
    async def test_service_auto_model_switch_classify(self, sample_image_bytes):
        """Test automatic model switching for classification."""
        config = VisionSessionConfig(
            task=VisionTask.CLASSIFY,
            model="yolo11n",  # Not a cls model
        )
        service = VisionService(config)

        await service.classify(image=sample_image_bytes)

        # Model should have been switched
        assert service.config.model == "yolo11n-cls"

    @pytest.mark.asyncio
    async def test_service_auto_model_switch_pose(self, sample_image_bytes):
        """Test automatic model switching for pose."""
        config = VisionSessionConfig(
            task=VisionTask.POSE,
            model="yolo11n",  # Not a pose model
        )
        service = VisionService(config)

        await service.detect_pose(image=sample_image_bytes)

        # Model should have been switched
        assert service.config.model == "yolo11n-pose"


class TestVisionResult:
    """Test VisionResult conversion."""

    @pytest.mark.asyncio
    async def test_detection_result_structure(self, sample_image_bytes):
        """Test detection result has correct structure."""
        config = VisionSessionConfig(
            task=VisionTask.DETECT,
            model="yolo11n",
            confidence=0.1,
        )
        service = VisionService(config)

        result = await service.detect(image=sample_image_bytes)

        # Check it's a VisionResult
        from routers.vision.types import VisionResult

        assert isinstance(result, VisionResult)

        # Check box structure (if any detections)
        for box in result.boxes:
            assert hasattr(box, "x1")
            assert hasattr(box, "y1")
            assert hasattr(box, "x2")
            assert hasattr(box, "y2")
            assert hasattr(box, "confidence")
            assert hasattr(box, "class_id")
            assert hasattr(box, "class_name")

            # Values should be valid
            assert box.x1 >= 0
            assert box.y1 >= 0
            assert 0 <= box.confidence <= 1
            assert box.class_id >= 0
