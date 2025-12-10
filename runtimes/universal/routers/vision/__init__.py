"""Vision router for object detection, segmentation, and classification."""

from .router import router
from .service import (
    VisionService,
    decode_base64_image,
    fetch_image_from_url,
    generate_session_id,
    get_vision_model,
    unload_vision_model,
)
from .types import (
    BoundingBox,
    ClassificationResult,
    DetectRequest,
    Keypoint,
    MessageType,
    PoseResult,
    SegmentationMask,
    SegmentRequest,
    VisionResult,
    VisionSessionConfig,
    VisionTask,
)
from .websocket_router import router as websocket_router

__all__ = [
    # Routers
    "router",
    "websocket_router",
    # Service
    "VisionService",
    "decode_base64_image",
    "fetch_image_from_url",
    "generate_session_id",
    "get_vision_model",
    "unload_vision_model",
    # Types
    "BoundingBox",
    "ClassificationResult",
    "DetectRequest",
    "Keypoint",
    "MessageType",
    "PoseResult",
    "SegmentationMask",
    "SegmentRequest",
    "VisionResult",
    "VisionSessionConfig",
    "VisionTask",
]
