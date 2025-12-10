"""
Vision service for object detection, segmentation, classification, and pose estimation.

Handles model loading, caching, and inference.
"""

import asyncio
import base64
import logging
import uuid
from datetime import datetime
from typing import Any

import httpx
import numpy as np

from models.vision_model import VisionModel
from utils.device import get_optimal_device

from .types import (
    BoundingBox,
    ClassificationResult,
    Keypoint,
    PoseResult,
    SegmentationMask,
    VisionResult,
    VisionSessionConfig,
    VisionTask,
)

logger = logging.getLogger(__name__)

# Model cache
_models: dict[str, VisionModel] = {}
_model_last_access: dict[str, datetime] = {}
_model_load_lock = asyncio.Lock()


async def get_vision_model(
    model_id: str = "yolo11m",
    task: str = "detect",
) -> VisionModel:
    """
    Get a cached vision model or load a new one.

    Args:
        model_id: Model name or path (e.g., "yolo11n", "yolo11m-seg")
        task: Vision task (detect, segment, classify, pose)

    Returns:
        Loaded VisionModel instance
    """
    cache_key = f"vision:{task}:{model_id}"

    async with _model_load_lock:
        if cache_key in _models:
            _model_last_access[cache_key] = datetime.now()
            return _models[cache_key]

        logger.info(f"Loading vision model: {model_id} for task: {task}")

        model = VisionModel(
            model_id=model_id,
            device=get_optimal_device(),
            task=task,
        )
        await model.load()

        _models[cache_key] = model
        _model_last_access[cache_key] = datetime.now()

        return model


async def unload_vision_model(model_id: str, task: str = "detect") -> bool:
    """
    Unload a cached vision model.

    Args:
        model_id: Model name or path
        task: Vision task

    Returns:
        True if model was unloaded, False if not found
    """
    cache_key = f"vision:{task}:{model_id}"

    async with _model_load_lock:
        if cache_key in _models:
            await _models[cache_key].unload()
            del _models[cache_key]
            del _model_last_access[cache_key]
            logger.info(f"Unloaded vision model: {model_id}")
            return True
        return False


class VisionService:
    """Service for vision inference operations."""

    def __init__(self, config: VisionSessionConfig | None = None):
        """
        Initialize vision service.

        Args:
            config: Session configuration (optional)
        """
        self.config = config or VisionSessionConfig()
        self._model: VisionModel | None = None

    async def ensure_model_loaded(self) -> VisionModel:
        """Ensure the configured model is loaded."""
        if self._model is None:
            self._model = await get_vision_model(
                model_id=self.config.model,
                task=self.config.task.value,
            )
        return self._model

    async def detect(
        self,
        image: str | bytes | np.ndarray,
        confidence: float | None = None,
        iou_threshold: float | None = None,
        classes: list[int] | None = None,
        return_annotated: bool = False,
    ) -> VisionResult:
        """
        Detect objects in an image.

        Args:
            image: Input image (base64, bytes, numpy, path, or URL)
            confidence: Override confidence threshold
            iou_threshold: Override IoU threshold
            classes: Filter to specific class IDs
            return_annotated: Include annotated image

        Returns:
            VisionResult with detected objects
        """
        model = await self.ensure_model_loaded()

        result = await model.predict(
            image=image,
            confidence=confidence or self.config.confidence,
            iou_threshold=iou_threshold or self.config.iou_threshold,
            classes=classes or self.config.classes,
            max_detections=self.config.max_detections,
            return_annotated=return_annotated,
        )

        return self._convert_to_vision_result(result)

    async def segment(
        self,
        image: str | bytes | np.ndarray,
        confidence: float | None = None,
        iou_threshold: float | None = None,
        classes: list[int] | None = None,
        return_annotated: bool = False,
    ) -> VisionResult:
        """
        Perform instance segmentation on an image.

        Args:
            image: Input image
            confidence: Override confidence threshold
            iou_threshold: Override IoU threshold
            classes: Filter to specific class IDs
            return_annotated: Include annotated image

        Returns:
            VisionResult with segmentation masks
        """
        # Ensure we're using a segmentation model
        if not self.config.model.endswith("-seg"):
            # Try to use the seg variant
            self.config.model = f"{self.config.model}-seg"
            self._model = None  # Force reload
            logger.info(f"Switching to segmentation model: {self.config.model}")

        model = await self.ensure_model_loaded()

        result = await model.predict(
            image=image,
            confidence=confidence or self.config.confidence,
            iou_threshold=iou_threshold or self.config.iou_threshold,
            classes=classes or self.config.classes,
            max_detections=self.config.max_detections,
            return_annotated=return_annotated,
        )

        return self._convert_to_vision_result(result)

    async def classify(
        self,
        image: str | bytes | np.ndarray,
        top_k: int = 5,
    ) -> VisionResult:
        """
        Classify an image.

        Args:
            image: Input image
            top_k: Number of top predictions to return

        Returns:
            VisionResult with classification result
        """
        # Ensure we're using a classification model
        if not self.config.model.endswith("-cls"):
            self.config.model = f"{self.config.model}-cls"
            self._model = None  # Force reload
            logger.info(f"Switching to classification model: {self.config.model}")

        model = await self.ensure_model_loaded()

        result = await model.predict(
            image=image,
            confidence=0.0,  # No filtering for classification
        )

        return self._convert_to_vision_result(result)

    async def detect_pose(
        self,
        image: str | bytes | np.ndarray,
        confidence: float | None = None,
        return_annotated: bool = False,
    ) -> VisionResult:
        """
        Detect poses in an image.

        Args:
            image: Input image
            confidence: Override confidence threshold
            return_annotated: Include annotated image

        Returns:
            VisionResult with pose keypoints
        """
        # Ensure we're using a pose model
        if not self.config.model.endswith("-pose"):
            self.config.model = f"{self.config.model}-pose"
            self._model = None  # Force reload
            logger.info(f"Switching to pose model: {self.config.model}")

        model = await self.ensure_model_loaded()

        result = await model.predict(
            image=image,
            confidence=confidence or self.config.confidence,
            return_annotated=return_annotated,
        )

        return self._convert_to_vision_result(result)

    def _convert_to_vision_result(self, raw_result: dict[str, Any]) -> VisionResult:
        """Convert raw model output to VisionResult."""
        # Convert boxes
        boxes = [
            BoundingBox(
                x1=b["x1"],
                y1=b["y1"],
                x2=b["x2"],
                y2=b["y2"],
                confidence=b["confidence"],
                class_id=b["class_id"],
                class_name=b["class_name"],
            )
            for b in raw_result.get("boxes", [])
        ]

        # Convert masks
        masks = None
        if raw_result.get("masks"):
            masks = [
                SegmentationMask(
                    contour=m["contour"],
                    class_id=m["class_id"],
                    class_name=m["class_name"],
                    area=m["area"],
                )
                for m in raw_result["masks"]
            ]

        # Convert keypoints
        keypoints = None
        if raw_result.get("keypoints"):
            keypoints = [
                PoseResult(
                    box=BoundingBox(**p["box"]) if p.get("box") else None,
                    keypoints=[
                        Keypoint(
                            x=k["x"],
                            y=k["y"],
                            confidence=k["confidence"],
                            name=k.get("name"),
                        )
                        for k in p["keypoints"]
                    ],
                )
                for p in raw_result["keypoints"]
            ]

        # Convert classification
        classification = None
        if raw_result.get("classification"):
            c = raw_result["classification"]
            classification = ClassificationResult(
                class_id=c["class_id"],
                class_name=c["class_name"],
                confidence=c["confidence"],
                top_k=c.get("top_k"),
            )

        return VisionResult(
            boxes=boxes,
            masks=masks,
            keypoints=keypoints,
            classification=classification,
            inference_time_ms=raw_result.get("inference_time_ms", 0),
            image_width=raw_result.get("image_width", 0),
            image_height=raw_result.get("image_height", 0),
            model=raw_result.get("model", self.config.model),
            task=VisionTask(raw_result.get("task", self.config.task.value)),
        )


async def fetch_image_from_url(url: str) -> bytes:
    """
    Fetch image from URL.

    Args:
        url: Image URL

    Returns:
        Image bytes
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.content


def decode_base64_image(base64_str: str) -> bytes:
    """
    Decode base64 image string.

    Args:
        base64_str: Base64 encoded image (with or without data URL prefix)

    Returns:
        Image bytes
    """
    # Remove data URL prefix if present
    if base64_str.startswith("data:image"):
        base64_str = base64_str.split(",", 1)[1]

    return base64.b64decode(base64_str)


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"vis_{uuid.uuid4().hex[:12]}"
