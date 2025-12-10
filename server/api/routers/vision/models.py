"""
Pydantic models for Vision Training API.
"""

from enum import Enum

from pydantic import BaseModel, Field


class VisionTask(str, Enum):
    """Vision task types."""

    DETECT = "detect"
    SEGMENT = "segment"
    CLASSIFY = "classify"
    POSE = "pose"


class DataSplit(str, Enum):
    """Data split types."""

    TRAIN = "train"
    VAL = "val"
    TEST = "test"


# === Training Set Models ===


class CreateTrainingSetRequest(BaseModel):
    """Request to create a training set."""

    name: str = Field(..., description="Training set name")
    task: VisionTask = Field(default=VisionTask.DETECT, description="Vision task type")
    classes: list[str] | None = Field(None, description="Class names")


class UpdateTrainingSetClassesRequest(BaseModel):
    """Request to update training set classes."""

    classes: list[str] = Field(..., description="New class names")


class AddImageRequest(BaseModel):
    """Request to add an image to a training set (JSON body)."""

    image_base64: str = Field(..., description="Base64-encoded image")
    filename: str = Field(default="image.jpg", description="Original filename")
    split: DataSplit = Field(default=DataSplit.TRAIN, description="Data split")
    labels: str | None = Field(
        None, description="YOLO format labels (one line per object)"
    )


class TrainingSetResponse(BaseModel):
    """Response for training set operations."""

    name: str
    task: str
    classes: dict[int, str]
    created_at: str
    updated_at: str
    file_count: int
    splits: dict[str, int]


class ImageMetadataResponse(BaseModel):
    """Response for image metadata."""

    hash: str
    original_name: str
    extension: str
    split: str
    timestamp: float
    size: int
    mime_type: str
    width: int | None = None
    height: int | None = None
    labels_hash: str | None = None


# === Model Training Models ===


class StartTrainingRequest(BaseModel):
    """Request to start model training."""

    model_name: str = Field(..., description="Name for the trained model")
    training_set: str = Field(..., description="Training set to use")
    base_model: str = Field(default="yolo11m", description="Base YOLO model")
    epochs: int = Field(default=100, ge=1, le=1000, description="Training epochs")
    batch_size: int = Field(default=16, ge=1, le=128, description="Batch size")
    imgsz: int = Field(default=640, description="Image size")
    patience: int = Field(default=50, ge=1, description="Early stopping patience")
    device: str = Field(default="auto", description="Device (auto, cpu, 0, 0,1)")
    lr0: float = Field(default=0.01, gt=0, description="Initial learning rate")
    export_formats: list[str] | None = Field(
        None, description="Additional export formats"
    )


class TrainingJobResponse(BaseModel):
    """Response for training job."""

    job_id: str
    model_name: str
    version: int
    status: str
    message: str


class ModelVersionResponse(BaseModel):
    """Response for model version info."""

    version: int
    name: str
    task: str
    base_model: str
    created_at: str
    training_set: str | None = None
    metrics: dict[str, float]
    tags: list[str]


class ModelSummaryResponse(BaseModel):
    """Summary of a model."""

    name: str
    latest_version: int
    total_versions: int
    task: str
    base_model: str
    metrics: dict[str, float]
    tags: list[str]


class RollbackRequest(BaseModel):
    """Request to rollback a model."""

    version: int = Field(..., description="Target version to rollback to")


class TagVersionRequest(BaseModel):
    """Request to tag a model version."""

    version: int = Field(..., description="Version to tag")
    tags: list[str] = Field(..., description="Tags to add")


class ExportModelRequest(BaseModel):
    """Request to export a model."""

    version: int | str = Field(default="latest", description="Version to export")
    format: str = Field(default="onnx", description="Export format")


# === Face Database Models ===


class CreateFaceDatabaseRequest(BaseModel):
    """Request to create a face database."""

    name: str = Field(..., description="Database name")
    detector_backend: str = Field(default="retinaface", description="Face detector")
    recognition_model: str = Field(default="ArcFace", description="Recognition model")


class RegisterFaceRequest(BaseModel):
    """Request to register a face (JSON body)."""

    person_id: str = Field(..., description="Unique person identifier")
    display_name: str | None = Field(None, description="Human-readable name")
    image_base64: str = Field(..., description="Base64-encoded face image")
    filename: str = Field(default="face.jpg", description="Original filename")


class FaceDatabaseResponse(BaseModel):
    """Response for face database operations."""

    name: str
    created_at: str
    updated_at: str
    detector_backend: str
    recognition_model: str
    total_identities: int
    total_images: int


class FaceIdentityResponse(BaseModel):
    """Response for face identity."""

    person_id: str
    display_name: str
    created_at: str
    updated_at: str
    image_count: int
    image_hashes: list[str]
