"""
Face recognition service for Universal Runtime.

Handles model loading, caching, and inference for face operations.
"""

import asyncio
import base64
import logging
from datetime import datetime

import httpx

from models.face_model import FaceModel
from utils.device import get_optimal_device

from .types import (
    FaceAnalysis,
    FaceBox,
    FaceDetection,
    FaceEmbedding,
    FaceMatch,
    FaceSearchResult,
    FaceVerificationResult,
)

logger = logging.getLogger(__name__)

# Model cache
_face_models: dict[str, FaceModel] = {}
_model_last_access: dict[str, datetime] = {}
_model_load_lock = asyncio.Lock()


async def get_face_model(
    model_name: str = "ArcFace",
    detector_backend: str = "retinaface",
) -> FaceModel:
    """
    Get a cached face model or load a new one.

    Args:
        model_name: Recognition model name
        detector_backend: Face detector backend

    Returns:
        Loaded FaceModel instance
    """
    cache_key = f"face:{model_name}:{detector_backend}"

    async with _model_load_lock:
        if cache_key in _face_models:
            _model_last_access[cache_key] = datetime.now()
            return _face_models[cache_key]

        logger.info(
            f"Loading face model: {model_name} with detector: {detector_backend}"
        )

        model = FaceModel(
            model_id=model_name,
            device=get_optimal_device(),
            detector_backend=detector_backend,
        )
        await model.load()

        _face_models[cache_key] = model
        _model_last_access[cache_key] = datetime.now()

        return model


async def unload_face_model(
    model_name: str = "ArcFace",
    detector_backend: str = "retinaface",
) -> bool:
    """Unload a cached face model."""
    cache_key = f"face:{model_name}:{detector_backend}"

    async with _model_load_lock:
        if cache_key in _face_models:
            await _face_models[cache_key].unload()
            del _face_models[cache_key]
            del _model_last_access[cache_key]
            logger.info(f"Unloaded face model: {model_name}")
            return True
        return False


class FaceService:
    """Service for face recognition operations."""

    def __init__(
        self,
        model_name: str = "ArcFace",
        detector_backend: str = "retinaface",
    ):
        """
        Initialize face service.

        Args:
            model_name: Recognition model to use
            detector_backend: Face detector backend
        """
        self.model_name = model_name
        self.detector_backend = detector_backend
        self._model: FaceModel | None = None

    async def ensure_model_loaded(self) -> FaceModel:
        """Ensure the face model is loaded."""
        if self._model is None:
            self._model = await get_face_model(
                model_name=self.model_name,
                detector_backend=self.detector_backend,
            )
        return self._model

    async def detect_faces(
        self,
        image: str | bytes,
        detector_backend: str | None = None,
        align: bool = True,
    ) -> list[FaceDetection]:
        """
        Detect faces in an image.

        Args:
            image: Image data (base64 or bytes)
            detector_backend: Override detector backend
            align: Align detected faces

        Returns:
            List of detected faces
        """
        model = await self.ensure_model_loaded()

        results = await model.detect_faces(
            image=image,
            detector_backend=detector_backend or self.detector_backend,
            align=align,
        )

        faces = []
        for r in results:
            box = r.get("box", {})
            faces.append(
                FaceDetection(
                    box=FaceBox(
                        x1=box.get("x1", 0),
                        y1=box.get("y1", 0),
                        x2=box.get("x2", 0),
                        y2=box.get("y2", 0),
                        width=box.get("width"),
                        height=box.get("height"),
                    ),
                    confidence=r.get("confidence", 0.0),
                    landmarks=r.get("landmarks"),
                )
            )

        return faces

    async def get_embeddings(
        self,
        image: str | bytes,
        model_name: str | None = None,
        detector_backend: str | None = None,
    ) -> list[FaceEmbedding]:
        """
        Get face embeddings from an image.

        Args:
            image: Image data
            model_name: Override recognition model
            detector_backend: Override detector backend

        Returns:
            List of face embeddings
        """
        model = await self.ensure_model_loaded()

        results = await model.get_embedding(
            image=image,
            model_name=model_name or self.model_name,
            detector_backend=detector_backend or self.detector_backend,
        )

        embeddings = []
        for r in results:
            box = r.get("box", {})
            embeddings.append(
                FaceEmbedding(
                    embedding=r.get("embedding", []),
                    box=FaceBox(
                        x1=box.get("x1", 0),
                        y1=box.get("y1", 0),
                        x2=box.get("x2", 0),
                        y2=box.get("y2", 0),
                    ),
                    model=r.get("model", self.model_name),
                )
            )

        return embeddings

    async def verify_faces(
        self,
        image1: str | bytes,
        image2: str | bytes,
        model_name: str | None = None,
        detector_backend: str | None = None,
        distance_metric: str = "cosine",
    ) -> FaceVerificationResult:
        """
        Verify if two images contain the same person.

        Args:
            image1: First image
            image2: Second image
            model_name: Override recognition model
            detector_backend: Override detector backend
            distance_metric: Distance metric

        Returns:
            Verification result
        """
        model = await self.ensure_model_loaded()

        result = await model.verify(
            img1=image1,
            img2=image2,
            model_name=model_name or self.model_name,
            detector_backend=detector_backend or self.detector_backend,
            distance_metric=distance_metric,
        )

        return FaceVerificationResult(
            verified=result.get("verified", False),
            distance=result.get("distance", 1.0),
            threshold=result.get("threshold", 0.0),
            model=result.get("model", self.model_name),
            detector_backend=result.get("detector_backend", self.detector_backend),
            distance_metric=result.get("distance_metric", distance_metric),
        )

    async def search_faces(
        self,
        image: str | bytes,
        db_path: str,
        model_name: str | None = None,
        detector_backend: str | None = None,
        distance_metric: str = "cosine",
    ) -> list[FaceSearchResult]:
        """
        Search for matching faces in a database.

        Args:
            image: Query image
            db_path: Path to face database
            model_name: Override recognition model
            detector_backend: Override detector backend
            distance_metric: Distance metric

        Returns:
            List of search results per detected face
        """
        model = await self.ensure_model_loaded()

        results = await model.find(
            image=image,
            db_path=db_path,
            model_name=model_name or self.model_name,
            detector_backend=detector_backend or self.detector_backend,
            distance_metric=distance_metric,
        )

        search_results = []
        for r in results:
            matches = [
                FaceMatch(
                    identity=m.get("identity", ""),
                    distance=m.get("distance", 1.0),
                    threshold=m.get("threshold", 0.0),
                )
                for m in r.get("matches", [])
            ]
            search_results.append(
                FaceSearchResult(
                    face_index=r.get("face_index", 0),
                    matches=matches,
                )
            )

        return search_results

    async def analyze_faces(
        self,
        image: str | bytes,
        actions: list[str] | None = None,
        detector_backend: str | None = None,
    ) -> list[FaceAnalysis]:
        """
        Analyze facial attributes.

        Args:
            image: Image data
            actions: Attributes to analyze
            detector_backend: Override detector backend

        Returns:
            List of analysis results per face
        """
        model = await self.ensure_model_loaded()

        results = await model.analyze(
            image=image,
            actions=actions or ["age", "gender", "emotion"],
            detector_backend=detector_backend or self.detector_backend,
        )

        analyses = []
        for r in results:
            box = r.get("box", {})
            analyses.append(
                FaceAnalysis(
                    box=FaceBox(
                        x1=box.get("x1", 0),
                        y1=box.get("y1", 0),
                        x2=box.get("x2", 0),
                        y2=box.get("y2", 0),
                    ),
                    age=r.get("age"),
                    gender=r.get("gender"),
                    gender_confidence=r.get("gender_confidence"),
                    dominant_emotion=r.get("dominant_emotion"),
                    emotions=r.get("emotions"),
                    dominant_race=r.get("dominant_race"),
                    race=r.get("race"),
                )
            )

        return analyses


async def fetch_image_from_url(url: str) -> bytes:
    """Fetch image from URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.content


def decode_base64_image(base64_str: str) -> bytes:
    """Decode base64 image string."""
    if base64_str.startswith("data:image"):
        base64_str = base64_str.split(",", 1)[1]
    return base64.b64decode(base64_str)
