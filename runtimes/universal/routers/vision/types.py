"""
Type definitions for the Vision API.

Supports object detection, instance segmentation, classification, and pose estimation.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class VisionTask(str, Enum):
    """Vision task types."""

    DETECT = "detect"
    SEGMENT = "segment"
    CLASSIFY = "classify"
    POSE = "pose"


class BoundingBox(BaseModel):
    """Bounding box for detected objects."""

    x1: float = Field(..., description="Left edge (pixels)")
    y1: float = Field(..., description="Top edge (pixels)")
    x2: float = Field(..., description="Right edge (pixels)")
    y2: float = Field(..., description="Bottom edge (pixels)")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence")
    class_id: int = Field(..., description="Class ID from model")
    class_name: str = Field(..., description="Human-readable class name")


class SegmentationMask(BaseModel):
    """Segmentation mask for an instance."""

    contour: list[list[float]] = Field(
        ..., description="Polygon points as [[x1,y1], [x2,y2], ...]"
    )
    class_id: int = Field(..., description="Class ID")
    class_name: str = Field(..., description="Class name")
    area: float = Field(..., description="Mask area in pixels")


class Keypoint(BaseModel):
    """Single keypoint for pose estimation."""

    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")
    confidence: float = Field(..., ge=0, le=1, description="Keypoint confidence")
    name: str | None = Field(
        None, description="Keypoint name (e.g., 'nose', 'left_eye')"
    )


class PoseResult(BaseModel):
    """Pose estimation result for a single person."""

    box: BoundingBox = Field(..., description="Person bounding box")
    keypoints: list[Keypoint] = Field(..., description="Detected keypoints")


class ClassificationResult(BaseModel):
    """Image classification result."""

    class_id: int = Field(..., description="Predicted class ID")
    class_name: str = Field(..., description="Predicted class name")
    confidence: float = Field(..., ge=0, le=1, description="Classification confidence")
    top_k: list[dict[str, float]] | None = Field(
        None, description="Top-k predictions as [{class_name: confidence}, ...]"
    )


class VisionResult(BaseModel):
    """Vision inference result for detection/segmentation."""

    boxes: list[BoundingBox] = Field(
        default_factory=list, description="Detected objects"
    )
    masks: list[SegmentationMask] | None = Field(
        None, description="Segmentation masks (for segment task)"
    )
    keypoints: list[PoseResult] | None = Field(
        None, description="Pose keypoints (for pose task)"
    )
    classification: ClassificationResult | None = Field(
        None, description="Classification result (for classify task)"
    )
    inference_time_ms: float = Field(..., description="Inference time in milliseconds")
    image_width: int = Field(..., description="Input image width")
    image_height: int = Field(..., description="Input image height")
    model: str = Field(..., description="Model used for inference")
    task: VisionTask = Field(..., description="Vision task performed")


# WebSocket Message Types


class MessageType(str, Enum):
    """WebSocket message types for realtime vision."""

    # Client -> Server
    SESSION_UPDATE = "session.update"
    INPUT_IMAGE = "input.image"
    INPUT_VIDEO_FRAME = "input.video_frame"
    START_STREAM = "stream.start"
    STOP_STREAM = "stream.stop"

    # Server -> Client
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    DETECTION_RESULT = "detection.result"
    STREAM_STARTED = "stream.started"
    STREAM_STOPPED = "stream.stopped"
    ERROR = "error"


class VisionSessionConfig(BaseModel):
    """Configuration for a vision session."""

    task: VisionTask = Field(default=VisionTask.DETECT, description="Vision task")
    model: str = Field(default="yolo11m", description="Model name or path")
    confidence: float = Field(
        default=0.25, ge=0, le=1, description="Minimum confidence threshold"
    )
    iou_threshold: float = Field(
        default=0.45, ge=0, le=1, description="IoU threshold for NMS"
    )
    classes: list[int] | None = Field(None, description="Filter to specific class IDs")
    max_detections: int = Field(
        default=300, ge=1, description="Maximum detections per image"
    )
    return_image: bool = Field(
        default=False, description="Include annotated image in response"
    )
    return_masks: bool = Field(default=True, description="Include segmentation masks")


# Client -> Server messages


class SessionUpdateMessage(BaseModel):
    """Client message to update session configuration."""

    type: Literal["session.update"] = "session.update"
    session: VisionSessionConfig


class InputImageMessage(BaseModel):
    """Client message to process a single image."""

    type: Literal["input.image"] = "input.image"
    image: str = Field(..., description="Base64-encoded image data")
    format: str = Field(default="jpeg", description="Image format (jpeg, png, webp)")


class InputVideoFrameMessage(BaseModel):
    """Client message to process a video frame."""

    type: Literal["input.video_frame"] = "input.video_frame"
    frame: str = Field(..., description="Base64-encoded frame data")
    timestamp_ms: int = Field(..., description="Frame timestamp in milliseconds")
    format: str = Field(default="jpeg", description="Frame format")


class StartStreamMessage(BaseModel):
    """Client message to start processing from a video source."""

    type: Literal["stream.start"] = "stream.start"
    source: str = Field(
        ..., description="Video source: URL, RTSP stream, or webcam index"
    )
    fps: int | None = Field(None, description="Target FPS (None for source rate)")


class StopStreamMessage(BaseModel):
    """Client message to stop video stream processing."""

    type: Literal["stream.stop"] = "stream.stop"


# Server -> Client messages


class SessionCreatedMessage(BaseModel):
    """Server message when vision session is created."""

    type: Literal["session.created"] = "session.created"
    session_id: str
    session: VisionSessionConfig


class SessionUpdatedMessage(BaseModel):
    """Server message when session is updated."""

    type: Literal["session.updated"] = "session.updated"
    session: VisionSessionConfig


class DetectionResultMessage(BaseModel):
    """Server message with detection results."""

    type: Literal["detection.result"] = "detection.result"
    result: VisionResult
    timestamp_ms: int | None = Field(None, description="Frame timestamp if from stream")
    annotated_image: str | None = Field(
        None, description="Base64-encoded annotated image"
    )


class StreamStartedMessage(BaseModel):
    """Server message when video stream starts."""

    type: Literal["stream.started"] = "stream.started"
    source: str
    fps: float


class StreamStoppedMessage(BaseModel):
    """Server message when video stream stops."""

    type: Literal["stream.stopped"] = "stream.stopped"
    frames_processed: int
    duration_seconds: float


class ErrorMessage(BaseModel):
    """Server error message."""

    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict | None = None


# Request/Response models for REST API


class DetectRequest(BaseModel):
    """Request for object detection endpoint."""

    image_base64: str | None = Field(None, description="Base64-encoded image")
    image_url: str | None = Field(None, description="URL to fetch image from")
    model: str = Field(default="yolo11m", description="Model to use")
    confidence: float = Field(default=0.25, ge=0, le=1)
    iou_threshold: float = Field(default=0.45, ge=0, le=1)
    classes: list[int] | None = Field(None, description="Filter to specific classes")
    return_image: bool = Field(default=False, description="Return annotated image")


class SegmentRequest(DetectRequest):
    """Request for instance segmentation endpoint."""

    return_masks: bool = Field(default=True, description="Include polygon masks")


class ClassifyRequest(BaseModel):
    """Request for image classification endpoint."""

    image_base64: str | None = Field(None, description="Base64-encoded image")
    image_url: str | None = Field(None, description="URL to fetch image from")
    model: str = Field(default="yolo11m-cls", description="Classification model")
    top_k: int = Field(default=5, ge=1, le=100, description="Number of top predictions")
