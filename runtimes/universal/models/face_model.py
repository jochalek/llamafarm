"""
Face model wrapper for face detection, recognition, and analysis.

Uses DeepFace for face operations with multiple backend support.
"""

import asyncio
import base64
import contextlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .base import BaseModel

logger = logging.getLogger(__name__)

# Lazy imports to avoid loading heavy libraries until needed
DeepFace = None


def _get_deepface():
    """Lazy load DeepFace to avoid import overhead."""
    global DeepFace
    if DeepFace is None:
        from deepface import DeepFace as _DeepFace

        DeepFace = _DeepFace
    return DeepFace


# Supported backends and models
DETECTOR_BACKENDS = [
    "retinaface",  # Most accurate
    "mtcnn",  # Good balance
    "opencv",  # Fastest
    "ssd",
    "dlib",
    "mediapipe",
    "yolov8",
    "yunet",
    "fastmtcnn",
    "centerface",
]

RECOGNITION_MODELS = [
    "ArcFace",  # Best accuracy
    "Facenet512",  # Good accuracy
    "Facenet",
    "VGG-Face",
    "OpenFace",
    "DeepFace",
    "DeepID",
    "Dlib",
    "SFace",
    "GhostFaceNet",
]


class FaceModel(BaseModel):
    """DeepFace-based face recognition and analysis model."""

    def __init__(
        self,
        model_id: str = "ArcFace",
        device: str = "cpu",
        detector_backend: str = "retinaface",
        token: str | None = None,
    ):
        """
        Initialize face model.

        Args:
            model_id: Recognition model name (ArcFace, Facenet512, VGG-Face, etc.)
            device: Target device (not directly used by DeepFace, but kept for interface)
            detector_backend: Face detector (retinaface, mtcnn, opencv, etc.)
            token: Not used, kept for interface compatibility
        """
        super().__init__(model_id, device, token=token)
        self.detector_backend = detector_backend
        self.model_type = "face_recognition"
        self.supports_streaming = False
        self._initialized = False

    async def load(self) -> None:
        """
        Pre-load face detection and recognition models.

        DeepFace lazy-loads models on first use, but we can pre-warm them.
        """
        logger.info(
            f"Loading face model: {self.model_id} with detector: {self.detector_backend}"
        )

        df = _get_deepface()

        # Pre-build models by running a dummy detection
        # This ensures models are downloaded and cached
        try:
            # Create a small dummy image for warmup
            dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
            dummy_img[30:70, 30:70] = [200, 180, 160]  # Skin-tone rectangle

            # Warmup detection (will download detector if needed)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: df.extract_faces(
                    dummy_img,
                    detector_backend=self.detector_backend,
                    enforce_detection=False,
                ),
            )

            # Warmup recognition model (will download if needed)
            await loop.run_in_executor(
                None,
                lambda: df.represent(
                    dummy_img,
                    model_name=self.model_id,
                    detector_backend=self.detector_backend,
                    enforce_detection=False,
                ),
            )

            self._initialized = True
            logger.info(f"Face model loaded: {self.model_id}")

        except Exception as e:
            logger.warning(f"Face model warmup failed (will lazy-load): {e}")
            self._initialized = True

    async def unload(self) -> None:
        """Unload the model and free resources."""
        logger.info(f"Unloading face model: {self.model_id}")
        self._initialized = False

        # Clear GPU cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            with contextlib.suppress(Exception):
                torch.mps.empty_cache()

        logger.info(f"Face model unloaded: {self.model_id}")

    def _decode_image(self, image: str | bytes | np.ndarray | Path) -> np.ndarray:
        """
        Decode image from various formats to numpy array.

        Args:
            image: Base64 string, bytes, numpy array, or file path

        Returns:
            Numpy array (RGB format)
        """
        import cv2

        if isinstance(image, np.ndarray):
            # Already numpy, ensure RGB
            if len(image.shape) == 3 and image.shape[2] == 4:
                image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
            elif len(image.shape) == 3 and image.shape[2] == 3:
                # Assume BGR from OpenCV, convert to RGB
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            return image

        if isinstance(image, (str, Path)):
            image_str = str(image)

            # Check if it's base64
            if image_str.startswith("data:image"):
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

            # Try as file path
            if Path(image_str).exists():
                img = cv2.imread(image_str)
                return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            raise ValueError(f"Could not decode image string: {image_str[:50]}...")

        if isinstance(image, bytes):
            nparr = np.frombuffer(image, np.uint8)
            import cv2

            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        raise ValueError(f"Unsupported image type: {type(image)}")

    async def detect_faces(
        self,
        image: str | bytes | np.ndarray | Path,
        detector_backend: str | None = None,
        align: bool = True,
        expand_percentage: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Detect faces in an image.

        Args:
            image: Input image
            detector_backend: Override detector backend
            align: Align detected faces
            expand_percentage: Expand face region by percentage

        Returns:
            List of detected faces with bounding boxes and confidence
        """
        df = _get_deepface()
        img = self._decode_image(image)
        backend = detector_backend or self.detector_backend

        loop = asyncio.get_event_loop()
        faces = await loop.run_in_executor(
            None,
            lambda: df.extract_faces(
                img,
                detector_backend=backend,
                enforce_detection=False,
                align=align,
                expand_percentage=expand_percentage,
            ),
        )

        results = []
        for face in faces:
            facial_area = face.get("facial_area", {})
            results.append(
                {
                    "box": {
                        "x1": facial_area.get("x", 0),
                        "y1": facial_area.get("y", 0),
                        "x2": facial_area.get("x", 0) + facial_area.get("w", 0),
                        "y2": facial_area.get("y", 0) + facial_area.get("h", 0),
                        "width": facial_area.get("w", 0),
                        "height": facial_area.get("h", 0),
                    },
                    "confidence": face.get("confidence", 0.0),
                    "landmarks": facial_area.get("landmarks", {}),
                }
            )

        return results

    async def get_embedding(
        self,
        image: str | bytes | np.ndarray | Path,
        model_name: str | None = None,
        detector_backend: str | None = None,
        align: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get face embeddings from an image.

        Args:
            image: Input image
            model_name: Override recognition model
            detector_backend: Override detector backend
            align: Align faces before embedding

        Returns:
            List of face embeddings with metadata
        """
        df = _get_deepface()
        img = self._decode_image(image)
        model = model_name or self.model_id
        backend = detector_backend or self.detector_backend

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: df.represent(
                img,
                model_name=model,
                detector_backend=backend,
                enforce_detection=False,
                align=align,
            ),
        )

        results = []
        for emb in embeddings:
            facial_area = emb.get("facial_area", {})
            results.append(
                {
                    "embedding": emb.get("embedding", []),
                    "box": {
                        "x1": facial_area.get("x", 0),
                        "y1": facial_area.get("y", 0),
                        "x2": facial_area.get("x", 0) + facial_area.get("w", 0),
                        "y2": facial_area.get("y", 0) + facial_area.get("h", 0),
                    },
                    "model": model,
                }
            )

        return results

    async def verify(
        self,
        img1: str | bytes | np.ndarray | Path,
        img2: str | bytes | np.ndarray | Path,
        model_name: str | None = None,
        detector_backend: str | None = None,
        distance_metric: str = "cosine",
    ) -> dict[str, Any]:
        """
        Verify if two images contain the same person.

        Args:
            img1: First image
            img2: Second image
            model_name: Override recognition model
            detector_backend: Override detector backend
            distance_metric: Distance metric (cosine, euclidean, euclidean_l2)

        Returns:
            Verification result with verified flag and distance
        """
        df = _get_deepface()
        img1_arr = self._decode_image(img1)
        img2_arr = self._decode_image(img2)
        model = model_name or self.model_id
        backend = detector_backend or self.detector_backend

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: df.verify(
                img1_arr,
                img2_arr,
                model_name=model,
                detector_backend=backend,
                distance_metric=distance_metric,
                enforce_detection=False,
            ),
        )

        return {
            "verified": result.get("verified", False),
            "distance": result.get("distance", 1.0),
            "threshold": result.get("threshold", 0.0),
            "model": model,
            "detector_backend": backend,
            "distance_metric": distance_metric,
        }

    async def find(
        self,
        image: str | bytes | np.ndarray | Path,
        db_path: str | Path,
        model_name: str | None = None,
        detector_backend: str | None = None,
        distance_metric: str = "cosine",
    ) -> list[dict[str, Any]]:
        """
        Find matching faces in a database.

        Args:
            image: Query image
            db_path: Path to face database directory
            model_name: Override recognition model
            detector_backend: Override detector backend
            distance_metric: Distance metric

        Returns:
            List of matching faces sorted by distance
        """
        df = _get_deepface()
        img = self._decode_image(image)
        model = model_name or self.model_id
        backend = detector_backend or self.detector_backend

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: df.find(
                img,
                db_path=str(db_path),
                model_name=model,
                detector_backend=backend,
                distance_metric=distance_metric,
                enforce_detection=False,
            ),
        )

        # DeepFace returns a list of DataFrames, one per detected face
        matches = []
        for i, df_result in enumerate(results):
            if len(df_result) == 0:
                continue

            face_matches = []
            for _, row in df_result.iterrows():
                face_matches.append(
                    {
                        "identity": row.get("identity", ""),
                        "distance": row.get("distance", 1.0),
                        "threshold": row.get("threshold", 0.0),
                    }
                )

            matches.append(
                {
                    "face_index": i,
                    "matches": face_matches,
                }
            )

        return matches

    async def analyze(
        self,
        image: str | bytes | np.ndarray | Path,
        actions: list[str] | None = None,
        detector_backend: str | None = None,
        align: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Analyze facial attributes (age, gender, emotion, race).

        Args:
            image: Input image
            actions: Attributes to analyze (age, gender, emotion, race)
            detector_backend: Override detector backend
            align: Align faces before analysis

        Returns:
            List of analysis results per detected face
        """
        df = _get_deepface()
        img = self._decode_image(image)
        backend = detector_backend or self.detector_backend
        actions = actions or ["age", "gender", "emotion", "race"]

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: df.analyze(
                img,
                actions=actions,
                detector_backend=backend,
                enforce_detection=False,
                align=align,
            ),
        )

        analyses = []
        for result in results:
            region = result.get("region", {})
            analysis = {
                "box": {
                    "x1": region.get("x", 0),
                    "y1": region.get("y", 0),
                    "x2": region.get("x", 0) + region.get("w", 0),
                    "y2": region.get("y", 0) + region.get("h", 0),
                },
            }

            if "age" in actions:
                analysis["age"] = result.get("age")

            if "gender" in actions:
                analysis["gender"] = result.get("dominant_gender")
                analysis["gender_confidence"] = result.get("gender", {})

            if "emotion" in actions:
                analysis["dominant_emotion"] = result.get("dominant_emotion")
                analysis["emotions"] = result.get("emotion", {})

            if "race" in actions:
                analysis["dominant_race"] = result.get("dominant_race")
                analysis["race"] = result.get("race", {})

            analyses.append(analysis)

        return analyses

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model."""
        info = super().get_model_info()
        info.update(
            {
                "recognition_model": self.model_id,
                "detector_backend": self.detector_backend,
                "supported_detectors": DETECTOR_BACKENDS,
                "supported_models": RECOGNITION_MODELS,
            }
        )
        return info
