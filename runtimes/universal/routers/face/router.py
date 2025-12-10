"""
Face Recognition API router for Universal Runtime.

Provides REST endpoints for face detection, verification, recognition, and analysis.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .service import (
    FaceService,
    decode_base64_image,
    fetch_image_from_url,
)
from .types import (
    AnalyzeFacesRequest,
    AnalyzeFacesResponse,
    DetectFacesRequest,
    DetectFacesResponse,
    FaceVerificationResult,
    GetEmbeddingRequest,
    GetEmbeddingsResponse,
    SearchFacesRequest,
    SearchFacesResponse,
    VerifyFacesRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["face"])


async def _get_image_data(
    file: UploadFile | None = None,
    image_base64: str | None = None,
    image_url: str | None = None,
) -> bytes:
    """Get image data from various sources."""
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


@router.post("/v1/face/detect", response_model=DetectFacesResponse)
async def detect_faces(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    detector_backend: Annotated[
        str, Form(description="Detector backend")
    ] = "retinaface",
    align: Annotated[bool, Form(description="Align detected faces")] = True,
) -> DetectFacesResponse:
    """
    Detect faces in an image.

    Returns bounding boxes and confidence scores for each detected face.
    Supports various detector backends for different speed/accuracy tradeoffs.
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        service = FaceService(detector_backend=detector_backend)
        faces = await service.detect_faces(
            image=image_data,
            align=align,
        )

        return DetectFacesResponse(
            faces=faces,
            count=len(faces),
            detector_backend=detector_backend,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/detect/json", response_model=DetectFacesResponse)
async def detect_faces_json(request: DetectFacesRequest) -> DetectFacesResponse:
    """Detect faces in an image (JSON request body)."""
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

        service = FaceService(detector_backend=request.detector_backend.value)
        faces = await service.detect_faces(
            image=image_data,
            align=request.align,
        )

        return DetectFacesResponse(
            faces=faces,
            count=len(faces),
            detector_backend=request.detector_backend.value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/embeddings", response_model=GetEmbeddingsResponse)
async def get_embeddings(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    model: Annotated[str, Form(description="Recognition model")] = "ArcFace",
    detector_backend: Annotated[
        str, Form(description="Detector backend")
    ] = "retinaface",
) -> GetEmbeddingsResponse:
    """
    Get face embeddings from an image.

    Returns embedding vectors that can be used for face comparison/matching.
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        service = FaceService(model_name=model, detector_backend=detector_backend)
        embeddings = await service.get_embeddings(image=image_data)

        return GetEmbeddingsResponse(
            embeddings=embeddings,
            count=len(embeddings),
            model=model,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/embeddings/json", response_model=GetEmbeddingsResponse)
async def get_embeddings_json(request: GetEmbeddingRequest) -> GetEmbeddingsResponse:
    """Get face embeddings (JSON request body)."""
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

        service = FaceService(
            model_name=request.model.value,
            detector_backend=request.detector_backend.value,
        )
        embeddings = await service.get_embeddings(image=image_data)

        return GetEmbeddingsResponse(
            embeddings=embeddings,
            count=len(embeddings),
            model=request.model.value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/verify", response_model=FaceVerificationResult)
async def verify_faces(
    file1: Annotated[UploadFile | None, File(description="First image file")] = None,
    file2: Annotated[UploadFile | None, File(description="Second image file")] = None,
    image1_base64: Annotated[
        str | None, Form(description="First image (base64)")
    ] = None,
    image2_base64: Annotated[
        str | None, Form(description="Second image (base64)")
    ] = None,
    model: Annotated[str, Form(description="Recognition model")] = "ArcFace",
    detector_backend: Annotated[
        str, Form(description="Detector backend")
    ] = "retinaface",
    distance_metric: Annotated[str, Form(description="Distance metric")] = "cosine",
) -> FaceVerificationResult:
    """
    Verify if two images contain the same person.

    Compares faces in two images and returns whether they match.
    """
    try:
        # Get first image
        if file1 is not None:
            image1_data = await file1.read()
        elif image1_base64 is not None:
            image1_data = decode_base64_image(image1_base64)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide file1 or image1_base64",
            )

        # Get second image
        if file2 is not None:
            image2_data = await file2.read()
        elif image2_base64 is not None:
            image2_data = decode_base64_image(image2_base64)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide file2 or image2_base64",
            )

        service = FaceService(model_name=model, detector_backend=detector_backend)
        result = await service.verify_faces(
            image1=image1_data,
            image2=image2_data,
            distance_metric=distance_metric,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/verify/json", response_model=FaceVerificationResult)
async def verify_faces_json(request: VerifyFacesRequest) -> FaceVerificationResult:
    """Verify if two images contain the same person (JSON request body)."""
    try:
        # Get first image
        if request.image1_base64:
            image1_data = decode_base64_image(request.image1_base64)
        elif request.image1_url:
            image1_data = await fetch_image_from_url(request.image1_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide image1_base64 or image1_url",
            )

        # Get second image
        if request.image2_base64:
            image2_data = decode_base64_image(request.image2_base64)
        elif request.image2_url:
            image2_data = await fetch_image_from_url(request.image2_url)
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide image2_base64 or image2_url",
            )

        service = FaceService(
            model_name=request.model.value,
            detector_backend=request.detector_backend.value,
        )
        result = await service.verify_faces(
            image1=image1_data,
            image2=image2_data,
            distance_metric=request.distance_metric.value,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/analyze", response_model=AnalyzeFacesResponse)
async def analyze_faces(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    actions: Annotated[
        str, Form(description="Comma-separated actions: age,gender,emotion,race")
    ] = "age,gender,emotion",
    detector_backend: Annotated[
        str, Form(description="Detector backend")
    ] = "retinaface",
) -> AnalyzeFacesResponse:
    """
    Analyze facial attributes.

    Returns age, gender, emotion, and race predictions for each face.
    """
    try:
        image_data = await _get_image_data(file, image_base64, image_url)

        # Parse actions
        action_list = [a.strip() for a in actions.split(",")]

        service = FaceService(detector_backend=detector_backend)
        analyses = await service.analyze_faces(
            image=image_data,
            actions=action_list,
        )

        return AnalyzeFacesResponse(
            faces=analyses,
            count=len(analyses),
            actions=action_list,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/analyze/json", response_model=AnalyzeFacesResponse)
async def analyze_faces_json(request: AnalyzeFacesRequest) -> AnalyzeFacesResponse:
    """Analyze facial attributes (JSON request body)."""
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

        service = FaceService(detector_backend=request.detector_backend.value)
        analyses = await service.analyze_faces(
            image=image_data,
            actions=request.actions,
        )

        return AnalyzeFacesResponse(
            faces=analyses,
            count=len(analyses),
            actions=request.actions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/search", response_model=SearchFacesResponse)
async def search_faces(
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    image_url: Annotated[
        str | None, Form(description="URL to fetch image from")
    ] = None,
    db_path: Annotated[str, Form(description="Path to face database directory")] = "",
    model: Annotated[str, Form(description="Recognition model")] = "ArcFace",
    detector_backend: Annotated[
        str, Form(description="Detector backend")
    ] = "retinaface",
    distance_metric: Annotated[str, Form(description="Distance metric")] = "cosine",
) -> SearchFacesResponse:
    """
    Search for matching faces in a database (few-shot face recognition).

    The database is a directory containing subdirectories for each person,
    with face images inside. For example:
        db_path/
            person1/
                img1.jpg
                img2.jpg
            person2/
                img1.jpg

    Returns the best matching identities for each detected face.
    """
    try:
        if not db_path:
            raise HTTPException(
                status_code=400,
                detail="db_path is required",
            )

        image_data = await _get_image_data(file, image_base64, image_url)

        service = FaceService(model_name=model, detector_backend=detector_backend)
        results = await service.search_faces(
            image=image_data,
            db_path=db_path,
            distance_metric=distance_metric,
        )

        return SearchFacesResponse(
            results=results,
            count=len(results),
            model=model,
            db_path=db_path,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face search error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/v1/face/search/json", response_model=SearchFacesResponse)
async def search_faces_json(request: SearchFacesRequest) -> SearchFacesResponse:
    """Search for matching faces in a database (JSON request body)."""
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

        service = FaceService(
            model_name=request.model.value,
            detector_backend=request.detector_backend.value,
        )
        results = await service.search_faces(
            image=image_data,
            db_path=request.db_path,
            distance_metric=request.distance_metric.value,
        )

        return SearchFacesResponse(
            results=results,
            count=len(results),
            model=request.model.value,
            db_path=request.db_path,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face search error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/v1/face/models")
async def list_face_models() -> dict:
    """List available face recognition models, detectors, and capabilities."""
    return {
        "recognition_models": [
            {
                "name": "ArcFace",
                "accuracy": "best",
                "speed": "fast",
                "embedding_dim": 512,
                "description": "State-of-the-art face recognition with additive angular margin loss",
            },
            {
                "name": "Facenet512",
                "accuracy": "very good",
                "speed": "fast",
                "embedding_dim": 512,
                "description": "Google's FaceNet with 512-dim embeddings",
            },
            {
                "name": "Facenet",
                "accuracy": "good",
                "speed": "fast",
                "embedding_dim": 128,
                "description": "Google's FaceNet with 128-dim embeddings",
            },
            {
                "name": "VGG-Face",
                "accuracy": "good",
                "speed": "slow",
                "embedding_dim": 4096,
                "description": "Oxford's VGG-based face recognition",
            },
            {
                "name": "OpenFace",
                "accuracy": "fair",
                "speed": "fast",
                "embedding_dim": 128,
                "description": "CMU's OpenFace implementation",
            },
            {
                "name": "DeepFace",
                "accuracy": "fair",
                "speed": "medium",
                "embedding_dim": 4096,
                "description": "Facebook's DeepFace model",
            },
            {
                "name": "DeepID",
                "accuracy": "fair",
                "speed": "fast",
                "embedding_dim": 160,
                "description": "Chinese University of Hong Kong's DeepID",
            },
            {
                "name": "Dlib",
                "accuracy": "good",
                "speed": "medium",
                "embedding_dim": 128,
                "description": "dlib's face recognition model",
            },
            {
                "name": "SFace",
                "accuracy": "good",
                "speed": "fast",
                "embedding_dim": 128,
                "description": "Sigmoid-constrained face recognition",
            },
            {
                "name": "GhostFaceNet",
                "accuracy": "good",
                "speed": "fast",
                "embedding_dim": 512,
                "description": "Lightweight face recognition using ghost modules",
            },
        ],
        "detector_backends": [
            {
                "name": "retinaface",
                "accuracy": "best",
                "speed": "medium",
                "description": "Multi-scale face detection with landmark regression",
            },
            {
                "name": "mtcnn",
                "accuracy": "good",
                "speed": "medium",
                "description": "Multi-task Cascaded CNN for face detection",
            },
            {
                "name": "opencv",
                "accuracy": "fair",
                "speed": "fastest",
                "description": "OpenCV's Haar cascade detector (fastest, least accurate)",
            },
            {
                "name": "ssd",
                "accuracy": "fair",
                "speed": "fast",
                "description": "Single Shot MultiBox Detector",
            },
            {
                "name": "dlib",
                "accuracy": "good",
                "speed": "slow",
                "description": "dlib's HOG + SVM face detector",
            },
            {
                "name": "mediapipe",
                "accuracy": "good",
                "speed": "fast",
                "description": "Google's MediaPipe face detection",
            },
            {
                "name": "yolov8",
                "accuracy": "good",
                "speed": "fast",
                "description": "YOLOv8 face detection",
            },
            {
                "name": "yunet",
                "accuracy": "good",
                "speed": "fast",
                "description": "YuNet lightweight face detector",
            },
            {
                "name": "fastmtcnn",
                "accuracy": "fair",
                "speed": "fast",
                "description": "Faster MTCNN implementation",
            },
            {
                "name": "centerface",
                "accuracy": "good",
                "speed": "fast",
                "description": "CenterFace anchor-free detector",
            },
        ],
        "distance_metrics": [
            {"name": "cosine", "description": "Cosine similarity (recommended)"},
            {"name": "euclidean", "description": "Euclidean distance"},
            {"name": "euclidean_l2", "description": "L2-normalized Euclidean distance"},
        ],
        "analysis_actions": [
            {"name": "age", "description": "Estimate age (returns integer)"},
            {
                "name": "gender",
                "description": "Predict gender (Man/Woman with confidence)",
            },
            {
                "name": "emotion",
                "description": "Detect emotion (angry, disgust, fear, happy, sad, surprise, neutral)",
            },
            {
                "name": "race",
                "description": "Predict race/ethnicity (asian, indian, black, white, middle eastern, latino hispanic)",
            },
        ],
        "capabilities": {
            "face_detection": "Detect faces with bounding boxes and landmarks",
            "face_verification": "Compare two faces to check if they're the same person",
            "face_recognition": "Identify a face from a database of known faces (few-shot learning)",
            "face_analysis": "Analyze age, gender, emotion, and race attributes",
            "face_embedding": "Generate 512-dim embedding vectors for face comparison",
        },
        "default_model": "ArcFace",
        "default_detector": "retinaface",
    }


@router.get("/v1/face/health")
async def face_health() -> dict:
    """Check face API health."""
    return {"status": "ok", "service": "face"}
