"""
Type definitions for the Face Recognition API.

Supports face detection, verification, recognition, and analysis.
"""

from enum import Enum

from pydantic import BaseModel, Field


class DetectorBackend(str, Enum):
    """Supported face detector backends."""

    RETINAFACE = "retinaface"
    MTCNN = "mtcnn"
    OPENCV = "opencv"
    SSD = "ssd"
    DLIB = "dlib"
    MEDIAPIPE = "mediapipe"
    YOLOV8 = "yolov8"
    YUNET = "yunet"
    FASTMTCNN = "fastmtcnn"
    CENTERFACE = "centerface"


class RecognitionModel(str, Enum):
    """Supported face recognition models."""

    ARCFACE = "ArcFace"
    FACENET512 = "Facenet512"
    FACENET = "Facenet"
    VGGFACE = "VGG-Face"
    OPENFACE = "OpenFace"
    DEEPFACE = "DeepFace"
    DEEPID = "DeepID"
    DLIB = "Dlib"
    SFACE = "SFace"
    GHOSTFACENET = "GhostFaceNet"


class DistanceMetric(str, Enum):
    """Distance metrics for face comparison."""

    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    EUCLIDEAN_L2 = "euclidean_l2"


class FacialLandmarks(BaseModel):
    """Facial landmark points."""

    left_eye: tuple[float, float] | None = None
    right_eye: tuple[float, float] | None = None
    nose: tuple[float, float] | None = None
    mouth_left: tuple[float, float] | None = None
    mouth_right: tuple[float, float] | None = None


class FaceBox(BaseModel):
    """Bounding box for a detected face."""

    x1: float = Field(..., description="Left edge")
    y1: float = Field(..., description="Top edge")
    x2: float = Field(..., description="Right edge")
    y2: float = Field(..., description="Bottom edge")
    width: float | None = Field(None, description="Box width")
    height: float | None = Field(None, description="Box height")


class FaceDetection(BaseModel):
    """Single face detection result."""

    box: FaceBox
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence")
    landmarks: dict[str, list[float]] | None = Field(
        None, description="Facial landmarks"
    )


class FaceEmbedding(BaseModel):
    """Face embedding result."""

    embedding: list[float] = Field(..., description="Face embedding vector")
    box: FaceBox
    model: str = Field(..., description="Model used for embedding")


class FaceVerificationResult(BaseModel):
    """Face verification result."""

    verified: bool = Field(..., description="Whether faces match")
    distance: float = Field(..., description="Distance between faces")
    threshold: float = Field(..., description="Threshold for verification")
    model: str = Field(..., description="Recognition model used")
    detector_backend: str = Field(..., description="Detector used")
    distance_metric: str = Field(..., description="Distance metric used")


class FaceMatch(BaseModel):
    """Single face match result."""

    identity: str = Field(..., description="Path/identifier of matched face")
    distance: float = Field(..., description="Distance to query face")
    threshold: float = Field(..., description="Match threshold")


class FaceSearchResult(BaseModel):
    """Face search result for one detected face."""

    face_index: int = Field(..., description="Index of detected face")
    matches: list[FaceMatch] = Field(..., description="Matching faces")


class EmotionScores(BaseModel):
    """Emotion analysis scores."""

    angry: float = 0.0
    disgust: float = 0.0
    fear: float = 0.0
    happy: float = 0.0
    sad: float = 0.0
    surprise: float = 0.0
    neutral: float = 0.0


class GenderScores(BaseModel):
    """Gender analysis scores."""

    Woman: float = 0.0
    Man: float = 0.0


class RaceScores(BaseModel):
    """Race/ethnicity analysis scores."""

    asian: float = 0.0
    indian: float = 0.0
    black: float = 0.0
    white: float = 0.0
    middle_eastern: float = Field(0.0, alias="middle eastern")
    latino_hispanic: float = Field(0.0, alias="latino hispanic")


class FaceAnalysis(BaseModel):
    """Face analysis result."""

    box: FaceBox
    age: int | None = Field(None, description="Estimated age")
    gender: str | None = Field(None, description="Predicted gender")
    gender_confidence: dict[str, float] | None = Field(
        None, description="Gender scores"
    )
    dominant_emotion: str | None = Field(None, description="Dominant emotion")
    emotions: dict[str, float] | None = Field(None, description="Emotion scores")
    dominant_race: str | None = Field(None, description="Dominant race/ethnicity")
    race: dict[str, float] | None = Field(None, description="Race scores")


# Request Models


class DetectFacesRequest(BaseModel):
    """Request for face detection."""

    image_base64: str | None = Field(None, description="Base64-encoded image")
    image_url: str | None = Field(None, description="URL to fetch image from")
    detector_backend: DetectorBackend = Field(
        default=DetectorBackend.RETINAFACE, description="Detector to use"
    )
    align: bool = Field(default=True, description="Align detected faces")


class GetEmbeddingRequest(BaseModel):
    """Request for face embedding."""

    image_base64: str | None = Field(None, description="Base64-encoded image")
    image_url: str | None = Field(None, description="URL to fetch image from")
    model: RecognitionModel = Field(
        default=RecognitionModel.ARCFACE, description="Recognition model"
    )
    detector_backend: DetectorBackend = Field(
        default=DetectorBackend.RETINAFACE, description="Detector to use"
    )


class VerifyFacesRequest(BaseModel):
    """Request for face verification."""

    image1_base64: str | None = Field(None, description="First image (base64)")
    image1_url: str | None = Field(None, description="First image URL")
    image2_base64: str | None = Field(None, description="Second image (base64)")
    image2_url: str | None = Field(None, description="Second image URL")
    model: RecognitionModel = Field(
        default=RecognitionModel.ARCFACE, description="Recognition model"
    )
    detector_backend: DetectorBackend = Field(
        default=DetectorBackend.RETINAFACE, description="Detector to use"
    )
    distance_metric: DistanceMetric = Field(
        default=DistanceMetric.COSINE, description="Distance metric"
    )


class AnalyzeFacesRequest(BaseModel):
    """Request for face analysis."""

    image_base64: str | None = Field(None, description="Base64-encoded image")
    image_url: str | None = Field(None, description="URL to fetch image from")
    actions: list[str] = Field(
        default=["age", "gender", "emotion"],
        description="Attributes to analyze (age, gender, emotion, race)",
    )
    detector_backend: DetectorBackend = Field(
        default=DetectorBackend.RETINAFACE, description="Detector to use"
    )


# Response Models


class DetectFacesResponse(BaseModel):
    """Response for face detection."""

    faces: list[FaceDetection]
    count: int
    detector_backend: str


class GetEmbeddingsResponse(BaseModel):
    """Response for face embeddings."""

    embeddings: list[FaceEmbedding]
    count: int
    model: str


class AnalyzeFacesResponse(BaseModel):
    """Response for face analysis."""

    faces: list[FaceAnalysis]
    count: int
    actions: list[str]


class SearchFacesRequest(BaseModel):
    """Request for face search/recognition in a database."""

    image_base64: str | None = Field(None, description="Base64-encoded image")
    image_url: str | None = Field(None, description="URL to fetch image from")
    db_path: str = Field(..., description="Path to face database directory")
    model: RecognitionModel = Field(
        default=RecognitionModel.ARCFACE, description="Recognition model"
    )
    detector_backend: DetectorBackend = Field(
        default=DetectorBackend.RETINAFACE, description="Detector to use"
    )
    distance_metric: DistanceMetric = Field(
        default=DistanceMetric.COSINE, description="Distance metric"
    )


class SearchFacesResponse(BaseModel):
    """Response for face search."""

    results: list[FaceSearchResult]
    count: int
    model: str
    db_path: str
