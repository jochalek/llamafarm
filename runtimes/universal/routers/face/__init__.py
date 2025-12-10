"""Face recognition router for face detection, verification, and analysis."""

from .router import router
from .service import (
    FaceService,
    decode_base64_image,
    fetch_image_from_url,
    get_face_model,
    unload_face_model,
)
from .types import (
    AnalyzeFacesRequest,
    AnalyzeFacesResponse,
    DetectFacesRequest,
    DetectFacesResponse,
    DetectorBackend,
    DistanceMetric,
    FaceAnalysis,
    FaceBox,
    FaceDetection,
    FaceEmbedding,
    FaceMatch,
    FaceSearchResult,
    FaceVerificationResult,
    GetEmbeddingRequest,
    GetEmbeddingsResponse,
    RecognitionModel,
    SearchFacesRequest,
    SearchFacesResponse,
    VerifyFacesRequest,
)

__all__ = [
    # Router
    "router",
    # Service
    "FaceService",
    "decode_base64_image",
    "fetch_image_from_url",
    "get_face_model",
    "unload_face_model",
    # Types
    "AnalyzeFacesRequest",
    "AnalyzeFacesResponse",
    "DetectFacesRequest",
    "DetectFacesResponse",
    "DetectorBackend",
    "DistanceMetric",
    "FaceAnalysis",
    "FaceBox",
    "FaceDetection",
    "FaceEmbedding",
    "FaceMatch",
    "FaceSearchResult",
    "FaceVerificationResult",
    "GetEmbeddingRequest",
    "GetEmbeddingsResponse",
    "RecognitionModel",
    "SearchFacesRequest",
    "SearchFacesResponse",
    "VerifyFacesRequest",
]
