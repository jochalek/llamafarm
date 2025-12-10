"""
Vision API router for object detection, segmentation, classification, and pose estimation.

Provides REST endpoints for image inference.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .service import (
    VisionService,
    decode_base64_image,
    fetch_image_from_url,
)
from .types import (
    ClassifyRequest,
    DetectRequest,
    SegmentRequest,
    VisionResult,
    VisionSessionConfig,
    VisionTask,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vision"])


async def _get_image_data(
    file: UploadFile | None = None,
    image_base64: str | None = None,
    image_url: str | None = None,
) -> bytes:
    """
    Get image data from various sources.

    Args:
        file: Uploaded file
        image_base64: Base64-encoded image
        image_url: URL to fetch image from

    Returns:
        Image bytes

    Raises:
        HTTPException: If no valid image source provided
    """
    if file is not None:
        return await file.read()
    elif image_base64 is not None:
        try:
            return decode_base64_image(image_base64)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid base64 image: {e}"
            ) from None
    elif image_url is not None:
        try:
            return await fetch_image_from_url(image_url)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to fetch image: {e}"
            ) from None
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide file, image_base64, or image_url",
        )


@router.post("/v1/vision/detect", response_model=VisionResult)
async def detect_objects(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    model: Annotated[str, Form(description="Model name")] = "yolo11m",
    confidence: Annotated[
        float, Form(ge=0, le=1, description="Confidence threshold")
    ] = 0.25,
    iou_threshold: Annotated[
        float, Form(ge=0, le=1, description="IoU threshold")
    ] = 0.45,
    classes: Annotated[
        str | None, Form(description="Comma-separated class IDs to filter")
    ] = None,
    return_image: Annotated[bool, Form(description="Return annotated image")] = False,
) -> VisionResult:
    """
    Detect objects in an image.

    Returns bounding boxes with class names and confidence scores.
    Supports uploading a file, providing base64 data, or fetching from URL.
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        # Parse classes
        class_ids = None
        if classes:
            try:
                class_ids = [int(c.strip()) for c in classes.split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="classes must be comma-separated integers",
                ) from None

        config = VisionSessionConfig(
            task=VisionTask.DETECT,
            model=model,
            confidence=confidence,
            iou_threshold=iou_threshold,
            classes=class_ids,
            return_image=return_image,
        )

        service = VisionService(config)
        result = await service.detect(
            image=image_data,
            return_annotated=return_image,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/vision/detect/json", response_model=VisionResult)
async def detect_objects_json(request: DetectRequest) -> VisionResult:
    """
    Detect objects in an image (JSON request body).

    Alternative to form-based endpoint for easier API integration.
    """
    try:
        if request.image_base64:
            image_data = decode_base64_image(request.image_base64)
        elif request.image_url:
            image_data = await fetch_image_from_url(request.image_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide image_base64 or image_url",
            )

        config = VisionSessionConfig(
            task=VisionTask.DETECT,
            model=request.model,
            confidence=request.confidence,
            iou_threshold=request.iou_threshold,
            classes=request.classes,
            return_image=request.return_image,
        )

        service = VisionService(config)
        result = await service.detect(
            image=image_data,
            return_annotated=request.return_image,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/vision/segment", response_model=VisionResult)
async def segment_objects(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    model: Annotated[str, Form(description="Model name")] = "yolo11m-seg",
    confidence: Annotated[
        float, Form(ge=0, le=1, description="Confidence threshold")
    ] = 0.25,
    iou_threshold: Annotated[
        float, Form(ge=0, le=1, description="IoU threshold")
    ] = 0.45,
    classes: Annotated[
        str | None, Form(description="Comma-separated class IDs")
    ] = None,
    return_image: Annotated[bool, Form(description="Return annotated image")] = False,
) -> VisionResult:
    """
    Perform instance segmentation on an image.

    Returns bounding boxes with segmentation masks (polygon contours).
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        class_ids = None
        if classes:
            try:
                class_ids = [int(c.strip()) for c in classes.split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="classes must be comma-separated integers",
                ) from None

        config = VisionSessionConfig(
            task=VisionTask.SEGMENT,
            model=model,
            confidence=confidence,
            iou_threshold=iou_threshold,
            classes=class_ids,
            return_image=return_image,
        )

        service = VisionService(config)
        result = await service.segment(
            image=image_data,
            return_annotated=return_image,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Segmentation error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/vision/segment/json", response_model=VisionResult)
async def segment_objects_json(request: SegmentRequest) -> VisionResult:
    """
    Perform instance segmentation (JSON request body).
    """
    try:
        if request.image_base64:
            image_data = decode_base64_image(request.image_base64)
        elif request.image_url:
            image_data = await fetch_image_from_url(request.image_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide image_base64 or image_url",
            )

        config = VisionSessionConfig(
            task=VisionTask.SEGMENT,
            model=request.model,
            confidence=request.confidence,
            iou_threshold=request.iou_threshold,
            classes=request.classes,
            return_image=request.return_image,
            return_masks=request.return_masks,
        )

        service = VisionService(config)
        result = await service.segment(
            image=image_data,
            return_annotated=request.return_image,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Segmentation error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/vision/classify", response_model=VisionResult)
async def classify_image(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    model: Annotated[str, Form(description="Model name")] = "yolo11m-cls",
    top_k: Annotated[
        int, Form(ge=1, le=100, description="Number of top predictions")
    ] = 5,
) -> VisionResult:
    """
    Classify an image into categories.

    Returns top-k predictions with confidence scores.
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        config = VisionSessionConfig(
            task=VisionTask.CLASSIFY,
            model=model,
        )

        service = VisionService(config)
        result = await service.classify(
            image=image_data,
            top_k=top_k,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/vision/classify/json", response_model=VisionResult)
async def classify_image_json(request: ClassifyRequest) -> VisionResult:
    """
    Classify an image (JSON request body).
    """
    try:
        if request.image_base64:
            image_data = decode_base64_image(request.image_base64)
        elif request.image_url:
            image_data = await fetch_image_from_url(request.image_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide image_base64 or image_url",
            )

        config = VisionSessionConfig(
            task=VisionTask.CLASSIFY,
            model=request.model,
        )

        service = VisionService(config)
        result = await service.classify(
            image=image_data,
            top_k=request.top_k,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/vision/pose", response_model=VisionResult)
async def detect_pose(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    model: Annotated[str, Form(description="Model name")] = "yolo11m-pose",
    confidence: Annotated[
        float, Form(ge=0, le=1, description="Confidence threshold")
    ] = 0.25,
    return_image: Annotated[bool, Form(description="Return annotated image")] = False,
) -> VisionResult:
    """
    Detect human poses in an image.

    Returns keypoints for each detected person (17 COCO keypoints).
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        config = VisionSessionConfig(
            task=VisionTask.POSE,
            model=model,
            confidence=confidence,
            return_image=return_image,
        )

        service = VisionService(config)
        result = await service.detect_pose(
            image=image_data,
            return_annotated=return_image,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Pose detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/v1/vision/models")
async def list_vision_models() -> dict:
    """
    List available vision models.

    Returns information about supported models and their tasks.
    """
    return {
        "models": {
            "detection": [
                {"name": "yolo11n", "size": "6.5M", "speed": "fastest"},
                {"name": "yolo11s", "size": "9.4M", "speed": "fast"},
                {"name": "yolo11m", "size": "20M", "speed": "balanced"},
                {"name": "yolo11l", "size": "49M", "speed": "accurate"},
                {"name": "yolo11x", "size": "57M", "speed": "most accurate"},
            ],
            "segmentation": [
                {"name": "yolo11n-seg", "size": "10M", "speed": "fastest"},
                {"name": "yolo11s-seg", "size": "12M", "speed": "fast"},
                {"name": "yolo11m-seg", "size": "27M", "speed": "balanced"},
                {"name": "yolo11l-seg", "size": "52M", "speed": "accurate"},
                {"name": "yolo11x-seg", "size": "62M", "speed": "most accurate"},
            ],
            "classification": [
                {"name": "yolo11n-cls", "size": "5M", "speed": "fastest"},
                {"name": "yolo11s-cls", "size": "5.5M", "speed": "fast"},
                {"name": "yolo11m-cls", "size": "10M", "speed": "balanced"},
                {"name": "yolo11l-cls", "size": "23M", "speed": "accurate"},
                {"name": "yolo11x-cls", "size": "27M", "speed": "most accurate"},
            ],
            "pose": [
                {"name": "yolo11n-pose", "size": "7M", "speed": "fastest"},
                {"name": "yolo11s-pose", "size": "10M", "speed": "fast"},
                {"name": "yolo11m-pose", "size": "22M", "speed": "balanced"},
                {"name": "yolo11l-pose", "size": "50M", "speed": "accurate"},
                {"name": "yolo11x-pose", "size": "58M", "speed": "most accurate"},
            ],
        },
        "tasks": ["detect", "segment", "classify", "pose"],
        "default_model": "yolo11m",
    }


@router.get("/v1/vision/health")
async def vision_health() -> dict:
    """Check vision API health."""
    return {"status": "ok", "service": "vision"}
