"""
Vision model wrapper for object detection, segmentation, classification, and pose estimation.

Uses Ultralytics YOLO for inference.
"""

import base64
import contextlib
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .base import BaseModel

logger = logging.getLogger(__name__)

# Lazy import to avoid loading ultralytics until needed
YOLO = None


def _get_yolo():
    """Lazy load YOLO to avoid import overhead."""
    global YOLO
    if YOLO is None:
        from ultralytics import YOLO as _YOLO

        YOLO = _YOLO
    return YOLO


class VisionModel(BaseModel):
    """Ultralytics YOLO-based vision model for detection, segmentation, classification, and pose."""

    def __init__(
        self,
        model_id: str,
        device: str,
        task: str = "detect",
        token: str | None = None,
    ):
        """
        Initialize vision model.

        Args:
            model_id: Model name (e.g., "yolo11n", "yolo11m-seg") or path to weights
            device: Target device (cuda/mps/cpu)
            task: Vision task - "detect", "segment", "classify", "pose"
            token: HuggingFace token (not used for YOLO, but kept for interface compatibility)
        """
        super().__init__(model_id, device, token=token)
        self.task = task
        self.model_type = f"vision_{task}"
        self.supports_streaming = True
        self._class_names: dict[int, str] = {}

    async def load(self) -> None:
        """Load the YOLO model."""
        logger.info(f"Loading vision model ({self.task}): {self.model_id}")

        YOLOClass = _get_yolo()

        # Load model - YOLO handles downloading automatically
        self.model = YOLOClass(self.model_id)

        # Move to device
        if self.device != "cpu":
            self.model.to(self.device)

        # Cache class names
        if hasattr(self.model, "names"):
            self._class_names = self.model.names

        logger.info(
            f"Vision model loaded on {self.device} with {len(self._class_names)} classes"
        )

    async def unload(self) -> None:
        """Unload the model and free resources."""
        logger.info(f"Unloading vision model: {self.model_id}")

        self.model = None
        self._class_names = {}

        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            with contextlib.suppress(Exception):
                torch.mps.empty_cache()

        logger.info(f"Vision model unloaded: {self.model_id}")

    def _decode_image(self, image: str | bytes | np.ndarray | Path) -> np.ndarray:
        """
        Decode image from various formats to numpy array.

        Args:
            image: Base64 string, bytes, numpy array, file path, or URL

        Returns:
            Numpy array (RGB format)
        """
        import cv2

        if isinstance(image, np.ndarray):
            # Already numpy, ensure RGB
            if len(image.shape) == 3 and image.shape[2] == 4:
                # RGBA -> RGB
                image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
            elif len(image.shape) == 3 and image.shape[2] == 3:
                # Check if BGR (OpenCV default) - YOLO expects RGB
                pass  # YOLO handles this internally
            return image

        if isinstance(image, (str, Path)):
            image_str = str(image)

            # Check if it's base64
            if image_str.startswith("data:image"):
                # Remove data URL prefix
                image_str = image_str.split(",", 1)[1]

            # Try to decode as base64
            try:
                image_bytes = base64.b64decode(image_str)
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            except Exception:
                pass

            # Try as file path or URL
            if Path(image_str).exists():
                img = cv2.imread(image_str)
                return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Assume it's a URL - YOLO will handle it
            return image_str

        if isinstance(image, bytes):
            nparr = np.frombuffer(image, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        raise ValueError(f"Unsupported image type: {type(image)}")

    async def predict(
        self,
        image: str | bytes | np.ndarray | Path,
        confidence: float = 0.25,
        iou_threshold: float = 0.45,
        classes: list[int] | None = None,
        max_detections: int = 300,
        return_annotated: bool = False,
    ) -> dict[str, Any]:
        """
        Run inference on a single image.

        Args:
            image: Input image (base64, bytes, numpy, path, or URL)
            confidence: Minimum confidence threshold
            iou_threshold: IoU threshold for NMS
            classes: Filter to specific class IDs
            max_detections: Maximum detections per image
            return_annotated: Include annotated image in response

        Returns:
            Detection results with boxes, masks, keypoints, etc.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        # Decode image if needed
        decoded_image = self._decode_image(image)

        # Run inference
        results = self.model(
            decoded_image,
            conf=confidence,
            iou=iou_threshold,
            classes=classes,
            max_det=max_detections,
            verbose=False,
        )

        # Format results
        result = results[0]
        return self._format_result(result, return_annotated)

    async def predict_batch(
        self,
        images: list[str | bytes | np.ndarray | Path],
        confidence: float = 0.25,
        iou_threshold: float = 0.45,
        classes: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Run inference on multiple images.

        Args:
            images: List of input images
            confidence: Minimum confidence threshold
            iou_threshold: IoU threshold for NMS
            classes: Filter to specific class IDs

        Returns:
            List of detection results
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        # Decode all images
        decoded_images = [self._decode_image(img) for img in images]

        # Run batch inference
        results = self.model(
            decoded_images,
            conf=confidence,
            iou=iou_threshold,
            classes=classes,
            verbose=False,
        )

        # Format all results
        return [self._format_result(r) for r in results]

    async def predict_stream(
        self,
        source: str | int,
        confidence: float = 0.25,
        iou_threshold: float = 0.45,
        classes: list[int] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream predictions from video source.

        Args:
            source: Video path, RTSP URL, or webcam index (0, 1, etc.)
            confidence: Minimum confidence threshold
            iou_threshold: IoU threshold for NMS
            classes: Filter to specific class IDs

        Yields:
            Detection results for each frame
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        # Stream inference
        for result in self.model(
            source,
            stream=True,
            conf=confidence,
            iou=iou_threshold,
            classes=classes,
            verbose=False,
        ):
            yield self._format_result(result)

    def _format_result(
        self,
        result,
        return_annotated: bool = False,
    ) -> dict[str, Any]:
        """
        Format YOLO result to our schema.

        Args:
            result: Ultralytics Results object
            return_annotated: Include annotated image

        Returns:
            Formatted detection result
        """
        import cv2

        output = {
            "boxes": [],
            "masks": None,
            "keypoints": None,
            "classification": None,
            "inference_time_ms": result.speed.get("inference", 0),
            "image_width": result.orig_shape[1] if result.orig_shape else 0,
            "image_height": result.orig_shape[0] if result.orig_shape else 0,
            "model": self.model_id,
            "task": self.task,
        }

        # Process boxes (detection)
        if result.boxes is not None and len(result.boxes) > 0:
            boxes_xyxy = result.boxes.xyxy.cpu().numpy()
            boxes_conf = result.boxes.conf.cpu().numpy()
            boxes_cls = result.boxes.cls.cpu().numpy().astype(int)

            for box, conf, cls in zip(boxes_xyxy, boxes_conf, boxes_cls, strict=False):
                output["boxes"].append(
                    {
                        "x1": float(box[0]),
                        "y1": float(box[1]),
                        "x2": float(box[2]),
                        "y2": float(box[3]),
                        "confidence": float(conf),
                        "class_id": int(cls),
                        "class_name": self._class_names.get(int(cls), str(cls)),
                    }
                )

        # Process masks (segmentation)
        if hasattr(result, "masks") and result.masks is not None:
            output["masks"] = []
            masks_xy = result.masks.xy  # Polygon format

            for i, contour in enumerate(masks_xy):
                if len(output["boxes"]) > i:
                    box_info = output["boxes"][i]
                    # Calculate area from contour
                    area = cv2.contourArea(contour.astype(np.float32))
                    output["masks"].append(
                        {
                            "contour": contour.tolist(),
                            "class_id": box_info["class_id"],
                            "class_name": box_info["class_name"],
                            "area": float(area),
                        }
                    )

        # Process keypoints (pose)
        if hasattr(result, "keypoints") and result.keypoints is not None:
            output["keypoints"] = []
            kpts = result.keypoints

            if kpts.xy is not None:
                kpts_xy = kpts.xy.cpu().numpy()
                kpts_conf = kpts.conf.cpu().numpy() if kpts.conf is not None else None

                # COCO keypoint names
                keypoint_names = [
                    "nose",
                    "left_eye",
                    "right_eye",
                    "left_ear",
                    "right_ear",
                    "left_shoulder",
                    "right_shoulder",
                    "left_elbow",
                    "right_elbow",
                    "left_wrist",
                    "right_wrist",
                    "left_hip",
                    "right_hip",
                    "left_knee",
                    "right_knee",
                    "left_ankle",
                    "right_ankle",
                ]

                for person_idx, person_kpts in enumerate(kpts_xy):
                    person_keypoints = []
                    for kpt_idx, (x, y) in enumerate(person_kpts):
                        conf = (
                            float(kpts_conf[person_idx][kpt_idx])
                            if kpts_conf is not None
                            else 1.0
                        )
                        name = (
                            keypoint_names[kpt_idx]
                            if kpt_idx < len(keypoint_names)
                            else f"kpt_{kpt_idx}"
                        )
                        person_keypoints.append(
                            {
                                "x": float(x),
                                "y": float(y),
                                "confidence": conf,
                                "name": name,
                            }
                        )

                    # Include the bounding box for this person if available
                    box = (
                        output["boxes"][person_idx]
                        if person_idx < len(output["boxes"])
                        else None
                    )
                    output["keypoints"].append(
                        {
                            "box": box,
                            "keypoints": person_keypoints,
                        }
                    )

        # Process classification
        if hasattr(result, "probs") and result.probs is not None:
            probs = result.probs
            top1_idx = int(probs.top1)
            top1_conf = float(probs.top1conf)

            # Get top-k predictions
            top5_indices = probs.top5
            top5_confs = probs.top5conf.cpu().numpy()

            top_k = []
            for idx, conf in zip(top5_indices, top5_confs, strict=False):
                class_name = self._class_names.get(idx, str(idx))
                top_k.append({class_name: float(conf)})

            output["classification"] = {
                "class_id": top1_idx,
                "class_name": self._class_names.get(top1_idx, str(top1_idx)),
                "confidence": top1_conf,
                "top_k": top_k,
            }

        # Include annotated image if requested
        if return_annotated:
            annotated = result.plot()  # Returns BGR numpy array
            # Encode as base64 JPEG
            _, buffer = cv2.imencode(".jpg", annotated)
            output["annotated_image"] = base64.b64encode(buffer).decode("utf-8")

        return output

    @property
    def class_names(self) -> dict[int, str]:
        """Get the class names for this model."""
        return self._class_names

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model."""
        info = super().get_model_info()
        info.update(
            {
                "task": self.task,
                "num_classes": len(self._class_names),
                "class_names": self._class_names,
            }
        )
        return info
