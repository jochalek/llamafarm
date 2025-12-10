# Vision API Implementation Plan

## Overview

This plan introduces comprehensive image recognition capabilities to LlamaFarm, starting with the Universal Runtime and then expanding to the LlamaFarm server. The implementation follows existing patterns from the transcription and encoder model implementations, **and critically, follows the established dataset/file storage patterns for reproducible, versioned training pipelines**.

## Goals

1. **Classification** - Identify what's in an image
2. **Classification + Localization** - Identify and locate the main object
3. **Object Detection** - Detect multiple objects with bounding boxes
4. **Instance Segmentation** - Per-pixel masks for each detected object
5. **Face Recognition** - Detect, identify, and analyze faces
6. **Streaming** - Real-time video processing (WebSocket in/out)
7. **Training/Fine-tuning** - One-shot/few-shot learning endpoints
8. **Reproducible Pipelines** - Versioned training with rollback capability
9. **Persistent Storage** - All training data stored in LlamaFarm data directory

---

## Critical: Training Pipeline & Reproducibility

### Design Principles

Following LlamaFarm's existing patterns for RAG datasets:

1. **Content-Addressed Storage** - Training images stored by SHA-256 hash (deduplication)
2. **Metadata Tracking** - Every image/annotation has JSON metadata
3. **Version Control** - Training runs are versioned, models can be rolled back
4. **Config-Driven Pipelines** - Training defined in `llamafarm.yaml`
5. **Event Logging** - All training jobs logged for audit/reproducibility
6. **Async Processing** - Training runs via Celery tasks (like RAG ingestion)

### Storage Structure

```
~/.llamafarm/projects/{namespace}/{project}/
└── lf_data/
    ├── datasets/                          # Existing RAG datasets
    │   └── {dataset_name}/...
    │
    ├── vision/                            # NEW: Vision data
    │   ├── training_sets/                 # Training image collections
    │   │   └── {training_set_name}/
    │   │       ├── raw/                   # Hash-based image storage
    │   │       │   └── {SHA256_hash}.{ext}
    │   │       ├── meta/                  # Image metadata
    │   │       │   └── {SHA256_hash}.json
    │   │       ├── labels/                # YOLO-format annotations
    │   │       │   └── {SHA256_hash}.txt
    │   │       ├── index/
    │   │       │   └── by_name/           # Symlinks to raw
    │   │       └── manifest.json          # Training set manifest
    │   │
    │   ├── models/                        # Trained model storage
    │   │   └── {model_name}/
    │   │       └── v{version}/
    │   │           ├── weights.pt         # PyTorch weights
    │   │           ├── weights.onnx       # ONNX export (optional)
    │   │           ├── config.yaml        # Training config snapshot
    │   │           ├── metrics.json       # Training metrics
    │   │           └── manifest.json      # Model manifest
    │   │
    │   └── faces/                         # Face recognition databases
    │       └── {face_db_name}/
    │           ├── identities/            # Per-person directories
    │           │   └── {person_id}/
    │           │       ├── raw/           # Face images by hash
    │           │       ├── embeddings/    # Cached face embeddings
    │           │       └── meta.json      # Person metadata
    │           ├── manifest.json          # Face DB manifest
    │           └── index.json             # Identity index
    │
    └── stores/                            # Existing vector stores
```

### Training Set Manifest Format

```json
{
  "version": "1.0",
  "name": "custom_detector_v1",
  "created_at": "2025-12-10T12:00:00Z",
  "updated_at": "2025-12-10T14:30:00Z",
  "task": "detect",
  "classes": {
    "0": "person",
    "1": "car",
    "2": "bicycle"
  },
  "splits": {
    "train": 800,
    "val": 150,
    "test": 50
  },
  "files": [
    {
      "hash": "2b3e321d...",
      "original_name": "image001.jpg",
      "split": "train",
      "labels_hash": "a1b2c3d4..."
    }
  ],
  "stats": {
    "total_images": 1000,
    "total_annotations": 5420,
    "class_distribution": {"person": 2100, "car": 1800, "bicycle": 1520}
  }
}
```

### Model Manifest Format

```json
{
  "version": 3,
  "name": "custom_detector",
  "task": "detect",
  "base_model": "yolo11m",
  "created_at": "2025-12-10T15:00:00Z",
  "training_set": "custom_detector_v1",
  "training_set_hash": "abc123...",
  "config": {
    "epochs": 100,
    "batch_size": 16,
    "imgsz": 640,
    "lr0": 0.01,
    "augmentation": true
  },
  "config_hash": "def456...",
  "metrics": {
    "mAP50": 0.89,
    "mAP50-95": 0.72,
    "precision": 0.91,
    "recall": 0.87
  },
  "files": {
    "weights": "weights.pt",
    "onnx": "weights.onnx"
  },
  "parent_version": 2,
  "tags": ["production", "v3-release"]
}
```

### Face Database Manifest

```json
{
  "version": "1.0",
  "name": "office_employees",
  "created_at": "2025-12-10T10:00:00Z",
  "detector_backend": "retinaface",
  "recognition_model": "ArcFace",
  "identities": [
    {
      "person_id": "john_doe",
      "display_name": "John Doe",
      "created_at": "2025-12-10T10:05:00Z",
      "image_count": 5,
      "embedding_hash": "xyz789..."
    }
  ],
  "total_identities": 50,
  "total_images": 250
}
```

---

## Technology Stack

### Primary Libraries

| Task | Library | Rationale |
|------|---------|-----------|
| Object Detection | [Ultralytics YOLO11](https://docs.ultralytics.com/) | State-of-the-art, unified API, streaming support, ONNX export |
| Instance Segmentation | Ultralytics YOLO11-seg | Same library, different model variant |
| Face Recognition | [DeepFace](https://github.com/serengil/deepface) | Lightweight wrapper, multiple backends (ArcFace, RetinaFace) |
| Face Detection | RetinaFace (via DeepFace) | Best accuracy for face detection |
| ONNX Inference | [ONNX Runtime](https://onnxruntime.ai/) | Cross-platform optimization, 2-4ms per frame |
| Image Processing | OpenCV + Pillow | Standard image I/O and preprocessing |

### Model Recommendations

| Task | Model | Size | FPS (GPU) | Notes |
|------|-------|------|-----------|-------|
| Detection (fast) | YOLO11n | 6.5M | 400+ | Edge deployment |
| Detection (balanced) | YOLO11m | 20M | 180 | Best tradeoff |
| Detection (accurate) | YOLO11x | 57M | 90 | Maximum accuracy |
| Segmentation | YOLO11m-seg | 27M | 120 | Instance masks |
| Face Detection | RetinaFace | 30M | 100+ | Best face detector |
| Face Recognition | ArcFace | 112M | 50+ | 99.4% LFW accuracy |

---

## Architecture

### Phase 1: Universal Runtime (Core)

```
runtimes/universal/
├── models/
│   ├── vision_model.py          # YOLO-based detection/segmentation
│   ├── face_model.py            # DeepFace-based recognition
│   └── vision_model_onnx.py     # ONNX-optimized version
├── routers/
│   └── vision/
│       ├── router.py            # REST + WebSocket endpoints
│       ├── service.py           # Business logic
│       ├── types.py             # Pydantic message types
│       └── training.py          # Fine-tuning service
└── server.py                    # Add load_vision() function
```

### Phase 2: LlamaFarm Server Integration

```
server/
├── api/routers/
│   └── vision/
│       └── router.py            # Proxy to Universal Runtime
└── services/
    └── vision_service.py        # Model management, caching
```

---

## Implementation Steps

### Step 1: Vision Model Classes (2 files)

#### 1.1 `runtimes/universal/models/vision_model.py`

```python
class VisionModel(BaseModel):
    """Ultralytics YOLO-based vision model for detection and segmentation."""

    def __init__(
        self,
        model_id: str,  # e.g., "yolo11n", "yolo11m-seg"
        device: str,
        task: str = "detect",  # detect, segment, classify, pose
        token: str | None = None,
    ):
        ...

    async def load(self) -> None:
        """Load YOLO model from Ultralytics hub or local path."""
        from ultralytics import YOLO
        self.model = YOLO(self.model_id)
        self.model.to(self.device)

    async def predict(
        self,
        image: np.ndarray | bytes | str,  # numpy, bytes, URL, or path
        confidence: float = 0.25,
        iou_threshold: float = 0.45,
        classes: list[int] | None = None,
    ) -> VisionResult:
        """Run inference on a single image."""
        results = self.model(
            image,
            conf=confidence,
            iou=iou_threshold,
            classes=classes,
            stream=False,
        )
        return self._format_results(results[0])

    async def predict_stream(
        self,
        source: str | int,  # video path, RTSP URL, or webcam index
        confidence: float = 0.25,
    ) -> AsyncGenerator[VisionResult, None]:
        """Stream predictions from video source."""
        for result in self.model(source, stream=True, conf=confidence):
            yield self._format_results(result)

    def _format_results(self, result) -> VisionResult:
        """Convert YOLO results to our schema."""
        return VisionResult(
            boxes=[
                BoundingBox(
                    x1=box[0], y1=box[1], x2=box[2], y2=box[3],
                    confidence=conf,
                    class_id=cls,
                    class_name=self.model.names[cls],
                )
                for box, conf, cls in zip(
                    result.boxes.xyxy.cpu().numpy(),
                    result.boxes.conf.cpu().numpy(),
                    result.boxes.cls.cpu().numpy().astype(int),
                )
            ],
            masks=result.masks.xy if hasattr(result, 'masks') and result.masks else None,
            keypoints=result.keypoints if hasattr(result, 'keypoints') else None,
            inference_time_ms=result.speed['inference'],
        )
```

#### 1.2 `runtimes/universal/models/face_model.py`

```python
class FaceModel(BaseModel):
    """DeepFace-based face recognition and analysis."""

    async def load(self) -> None:
        """Pre-load face detection and recognition models."""
        from deepface import DeepFace
        # Pre-load models for faster inference
        DeepFace.build_model(self.detector_backend)
        DeepFace.build_model(self.model_name)

    async def detect_faces(
        self,
        image: np.ndarray | bytes | str,
        detector_backend: str = "retinaface",
    ) -> list[FaceDetection]:
        """Detect faces with bounding boxes."""
        ...

    async def recognize(
        self,
        image: np.ndarray | bytes | str,
        db_path: str,  # Path to face database
        model_name: str = "ArcFace",
    ) -> list[FaceMatch]:
        """Recognize faces against a database."""
        ...

    async def analyze(
        self,
        image: np.ndarray | bytes | str,
        actions: list[str] = ["age", "gender", "emotion"],
    ) -> list[FaceAnalysis]:
        """Analyze facial attributes."""
        ...

    async def register_face(
        self,
        image: np.ndarray | bytes | str,
        person_id: str,
        db_path: str,
    ) -> None:
        """Add a face to the recognition database."""
        ...
```

---

### Step 2: Type Definitions

#### `runtimes/universal/routers/vision/types.py`

```python
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

class VisionTask(str, Enum):
    DETECT = "detect"
    SEGMENT = "segment"
    CLASSIFY = "classify"
    POSE = "pose"
    FACE_DETECT = "face_detect"
    FACE_RECOGNIZE = "face_recognize"
    FACE_ANALYZE = "face_analyze"

class BoundingBox(BaseModel):
    x1: float = Field(..., description="Left edge")
    y1: float = Field(..., description="Top edge")
    x2: float = Field(..., description="Right edge")
    y2: float = Field(..., description="Bottom edge")
    confidence: float = Field(..., ge=0, le=1)
    class_id: int
    class_name: str

class SegmentationMask(BaseModel):
    contour: list[list[float]]  # Polygon points [[x,y], ...]
    class_id: int
    class_name: str
    area: float

class VisionResult(BaseModel):
    boxes: list[BoundingBox] = []
    masks: list[SegmentationMask] | None = None
    keypoints: list[list[float]] | None = None
    inference_time_ms: float
    image_width: int
    image_height: int

class FaceDetection(BaseModel):
    box: BoundingBox
    landmarks: dict[str, tuple[float, float]] | None = None
    confidence: float

class FaceMatch(BaseModel):
    person_id: str
    confidence: float
    box: BoundingBox

class FaceAnalysis(BaseModel):
    box: BoundingBox
    age: int | None = None
    gender: str | None = None
    emotion: dict[str, float] | None = None
    race: dict[str, float] | None = None

# WebSocket Message Types
class MessageType(str, Enum):
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
    task: VisionTask = VisionTask.DETECT
    model: str = "yolo11m"
    confidence: float = 0.25
    iou_threshold: float = 0.45
    classes: list[int] | None = None
    return_image: bool = False  # Include annotated image in response
    return_masks: bool = True   # Include segmentation masks
```

---

### Step 3: Router Implementation

#### `runtimes/universal/routers/vision/router.py`

**REST Endpoints:**

```python
router = APIRouter()

@router.post("/v1/vision/detect")
async def detect_objects(
    file: UploadFile | None = None,
    image_url: str | None = None,
    image_base64: str | None = None,
    model: str = "yolo11m",
    confidence: float = 0.25,
    classes: list[int] | None = None,
) -> VisionResult:
    """Detect objects in a single image."""
    ...

@router.post("/v1/vision/segment")
async def segment_objects(...) -> VisionResult:
    """Instance segmentation on a single image."""
    ...

@router.post("/v1/vision/classify")
async def classify_image(...) -> ClassificationResult:
    """Classify image into categories."""
    ...

@router.post("/v1/vision/faces/detect")
async def detect_faces(...) -> list[FaceDetection]:
    """Detect faces in an image."""
    ...

@router.post("/v1/vision/faces/recognize")
async def recognize_faces(
    file: UploadFile,
    db_path: str,  # Face database path
    model: str = "ArcFace",
) -> list[FaceMatch]:
    """Recognize faces against a database."""
    ...

@router.post("/v1/vision/faces/analyze")
async def analyze_faces(
    file: UploadFile,
    actions: list[str] = ["age", "gender", "emotion"],
) -> list[FaceAnalysis]:
    """Analyze facial attributes."""
    ...

@router.post("/v1/vision/faces/register")
async def register_face(
    file: UploadFile,
    person_id: str,
    db_path: str,
) -> dict:
    """Add a face to the recognition database."""
    ...
```

**WebSocket Streaming:**

```python
@router.websocket("/v1/realtime/vision")
async def vision_websocket(websocket: WebSocket):
    """
    Realtime WebSocket endpoint for video processing.

    Protocol:
    ---------
    Client -> Server:
    - session.update: Configure model, task, confidence
    - input.image: Send base64-encoded image for processing
    - input.video_frame: Send video frame with timestamp
    - stream.start: Start processing from video source (URL/RTSP)
    - stream.stop: Stop video stream processing

    Server -> Client:
    - session.created: Initial session config
    - detection.result: Detection/segmentation results
    - stream.started: Video stream started
    - stream.stopped: Video stream stopped
    - error: Error message
    """
    handler = VisionConnectionHandler(websocket)
    await handler.run()
```

---

### Step 4: Training Pipeline Architecture

This is the **critical section** for reproducible, versioned training.

#### 4.1 Configuration in `llamafarm.yaml`

```yaml
vision:
  # Training sets (like RAG datasets, but for images)
  training_sets:
    - name: custom_objects
      task: detect
      classes:
        - person
        - forklift
        - safety_vest
      augmentation:
        enabled: true
        hsv_h: 0.015
        hsv_s: 0.7
        hsv_v: 0.4
        degrees: 0.0
        translate: 0.1
        scale: 0.5
        fliplr: 0.5
        mosaic: 1.0

  # Training pipelines (like RAG processing strategies)
  training_pipelines:
    - name: production_detector
      base_model: yolo11m
      training_set: custom_objects
      epochs: 100
      batch_size: 16
      imgsz: 640
      patience: 50
      save_period: 10
      device: auto  # auto, cpu, 0, 0,1 (multi-GPU)
      workers: 8
      optimizer: auto
      lr0: 0.01
      lrf: 0.01
      momentum: 0.937
      weight_decay: 0.0005
      warmup_epochs: 3.0
      export_formats:
        - pt
        - onnx

  # Face databases
  face_databases:
    - name: employees
      detector_backend: retinaface
      recognition_model: ArcFace
      distance_metric: cosine
      threshold: 0.6

  # Model registry (trained models)
  models:
    - name: forklift_detector
      type: vision
      task: detect
      source: trained  # trained | pretrained | huggingface
      version: latest  # or specific version number
      path: vision/models/forklift_detector/v3/weights.pt
```

#### 4.2 Training Set Service

**File: `server/services/vision_training_service.py`**

```python
class VisionTrainingService:
    """Manages vision training sets with versioning and reproducibility."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.vision_dir = project_dir / "lf_data" / "vision"
        self.training_sets_dir = self.vision_dir / "training_sets"
        self.models_dir = self.vision_dir / "models"

    # === Training Set Management ===

    async def create_training_set(
        self,
        name: str,
        task: VisionTask,
        classes: list[str],
    ) -> TrainingSetManifest:
        """Create a new training set."""
        set_dir = self.training_sets_dir / name
        set_dir.mkdir(parents=True, exist_ok=True)

        (set_dir / "raw").mkdir(exist_ok=True)
        (set_dir / "meta").mkdir(exist_ok=True)
        (set_dir / "labels").mkdir(exist_ok=True)
        (set_dir / "index" / "by_name").mkdir(parents=True, exist_ok=True)

        manifest = TrainingSetManifest(
            name=name,
            task=task,
            classes={i: c for i, c in enumerate(classes)},
            created_at=datetime.now().isoformat(),
        )
        self._save_manifest(set_dir / "manifest.json", manifest)
        return manifest

    async def add_image(
        self,
        training_set: str,
        image_data: bytes,
        original_name: str,
        labels: list[BoundingBox] | None = None,
        split: str = "train",
    ) -> ImageMetadata:
        """Add image to training set with content-addressed storage."""
        set_dir = self.training_sets_dir / training_set

        # Hash-based storage (deduplication)
        image_hash = hashlib.sha256(image_data).hexdigest()
        ext = Path(original_name).suffix.lower()

        # Store raw image
        raw_path = set_dir / "raw" / f"{image_hash}{ext}"
        if not raw_path.exists():
            raw_path.write_bytes(image_data)

        # Store metadata
        meta = ImageMetadata(
            hash=image_hash,
            original_name=original_name,
            split=split,
            timestamp=time.time(),
            size=len(image_data),
            mime_type=mimetypes.guess_type(original_name)[0],
        )
        meta_path = set_dir / "meta" / f"{image_hash}.json"
        meta_path.write_text(meta.model_dump_json(indent=2))

        # Store labels in YOLO format
        if labels:
            labels_path = set_dir / "labels" / f"{image_hash}.txt"
            yolo_labels = self._convert_to_yolo_format(labels)
            labels_path.write_text(yolo_labels)

        # Create symlink for name-based access
        symlink_path = set_dir / "index" / "by_name" / original_name
        if not symlink_path.exists():
            symlink_path.symlink_to(f"../../raw/{image_hash}{ext}")

        # Update manifest
        await self._update_manifest_stats(training_set)

        return meta

    async def export_for_training(
        self,
        training_set: str,
        output_dir: Path,
    ) -> Path:
        """Export training set to YOLO format for training."""
        set_dir = self.training_sets_dir / training_set
        manifest = self._load_manifest(set_dir / "manifest.json")

        # Create YOLO directory structure
        for split in ["train", "val", "test"]:
            (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        # Copy files to appropriate splits
        for meta_file in (set_dir / "meta").glob("*.json"):
            meta = ImageMetadata.model_validate_json(meta_file.read_text())
            image_hash = meta.hash
            ext = Path(meta.original_name).suffix

            # Copy image
            src_image = set_dir / "raw" / f"{image_hash}{ext}"
            dst_image = output_dir / "images" / meta.split / f"{image_hash}{ext}"
            shutil.copy2(src_image, dst_image)

            # Copy labels
            src_labels = set_dir / "labels" / f"{image_hash}.txt"
            if src_labels.exists():
                dst_labels = output_dir / "labels" / meta.split / f"{image_hash}.txt"
                shutil.copy2(src_labels, dst_labels)

        # Generate data.yaml
        data_yaml = {
            "path": str(output_dir),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": manifest.classes,
        }
        (output_dir / "data.yaml").write_text(yaml.dump(data_yaml))

        return output_dir

    # === Model Training ===

    async def start_training(
        self,
        pipeline_name: str,
        model_name: str,
    ) -> TrainingJob:
        """Start a training job with full versioning."""
        config = self._load_pipeline_config(pipeline_name)

        # Determine next version number
        model_dir = self.models_dir / model_name
        version = self._get_next_version(model_dir)

        version_dir = model_dir / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Snapshot configuration for reproducibility
        config_snapshot = {
            "pipeline": pipeline_name,
            "config": config.model_dump(),
            "training_set_hash": self._get_training_set_hash(config.training_set),
            "timestamp": datetime.now().isoformat(),
        }
        (version_dir / "config.yaml").write_text(yaml.dump(config_snapshot))

        # Start Celery task
        job_id = f"train_{model_name}_v{version}_{uuid.uuid4().hex[:8]}"
        train_vision_model_task.delay(
            job_id=job_id,
            project_dir=str(self.project_dir),
            pipeline_name=pipeline_name,
            model_name=model_name,
            version=version,
        )

        return TrainingJob(
            job_id=job_id,
            model_name=model_name,
            version=version,
            status="started",
        )

    # === Model Versioning ===

    async def list_model_versions(self, model_name: str) -> list[ModelVersion]:
        """List all versions of a model."""
        model_dir = self.models_dir / model_name
        versions = []

        for version_dir in sorted(model_dir.glob("v*"), reverse=True):
            manifest_path = version_dir / "manifest.json"
            if manifest_path.exists():
                manifest = ModelManifest.model_validate_json(manifest_path.read_text())
                versions.append(ModelVersion(
                    version=manifest.version,
                    created_at=manifest.created_at,
                    metrics=manifest.metrics,
                    tags=manifest.tags,
                ))

        return versions

    async def rollback_model(
        self,
        model_name: str,
        target_version: int,
    ) -> dict:
        """Rollback model to a previous version."""
        model_dir = self.models_dir / model_name
        version_dir = model_dir / f"v{target_version}"

        if not version_dir.exists():
            raise ValueError(f"Version {target_version} not found")

        # Update "latest" symlink
        latest_link = model_dir / "latest"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(f"v{target_version}")

        return {"model": model_name, "active_version": target_version}

    async def tag_model_version(
        self,
        model_name: str,
        version: int,
        tags: list[str],
    ) -> ModelManifest:
        """Add tags to a model version (e.g., 'production', 'staging')."""
        manifest_path = self.models_dir / model_name / f"v{version}" / "manifest.json"
        manifest = ModelManifest.model_validate_json(manifest_path.read_text())
        manifest.tags = list(set(manifest.tags + tags))
        manifest_path.write_text(manifest.model_dump_json(indent=2))
        return manifest

    # === Few-Shot Learning ===

    async def few_shot_adapt(
        self,
        base_model: str,
        examples: list[FewShotExample],
        output_name: str,
    ) -> ModelManifest:
        """
        Adapt model to new classes using few-shot learning.

        Uses embedding-based matching for inference rather than full retraining.
        """
        # Store examples in training set
        training_set = f"{output_name}_few_shot"
        await self.create_training_set(
            name=training_set,
            task=VisionTask.DETECT,
            classes=[ex.class_name for ex in examples],
        )

        for ex in examples:
            await self.add_image(
                training_set=training_set,
                image_data=ex.image_data,
                original_name=ex.filename,
                labels=ex.labels,
                split="train",
            )

        # Generate embedding prototypes for each class
        prototypes = await self._generate_class_prototypes(training_set, base_model)

        # Save as a new model version
        model_dir = self.models_dir / output_name
        version = self._get_next_version(model_dir)
        version_dir = model_dir / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Store prototypes and config
        (version_dir / "prototypes.pt").write_bytes(
            torch.save(prototypes, version_dir / "prototypes.pt")
        )

        manifest = ModelManifest(
            version=version,
            name=output_name,
            task="detect",
            base_model=base_model,
            training_type="few_shot",
            training_set=training_set,
            example_count=len(examples),
            created_at=datetime.now().isoformat(),
        )
        (version_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))

        return manifest
```

#### 4.3 Celery Training Tasks

**File: `rag/tasks/vision_tasks.py`** (alongside existing RAG tasks)

```python
@celery_app.task(bind=True, name="train_vision_model")
def train_vision_model_task(
    self,
    job_id: str,
    project_dir: str,
    pipeline_name: str,
    model_name: str,
    version: int,
):
    """
    Celery task for training vision models.

    Runs in background worker, logs progress, saves checkpoints.
    """
    from ultralytics import YOLO

    project_path = Path(project_dir)
    service = VisionTrainingService(project_path)

    try:
        # Load pipeline config
        config = service._load_pipeline_config(pipeline_name)

        # Export training set to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / "dataset"
            await service.export_for_training(config.training_set, export_dir)

            # Initialize model
            model = YOLO(config.base_model)

            # Output directory
            version_dir = service.models_dir / model_name / f"v{version}"

            # Train with progress callbacks
            results = model.train(
                data=export_dir / "data.yaml",
                epochs=config.epochs,
                batch=config.batch_size,
                imgsz=config.imgsz,
                patience=config.patience,
                save_period=config.save_period,
                device=config.device,
                workers=config.workers,
                optimizer=config.optimizer,
                lr0=config.lr0,
                lrf=config.lrf,
                momentum=config.momentum,
                weight_decay=config.weight_decay,
                warmup_epochs=config.warmup_epochs,
                project=str(version_dir),
                name="train",
                exist_ok=True,
            )

            # Copy best weights
            best_weights = version_dir / "train" / "weights" / "best.pt"
            shutil.copy2(best_weights, version_dir / "weights.pt")

            # Export to additional formats
            for fmt in config.export_formats:
                if fmt != "pt":
                    model.export(format=fmt)
                    exported = version_dir / "train" / "weights" / f"best.{fmt}"
                    if exported.exists():
                        shutil.copy2(exported, version_dir / f"weights.{fmt}")

            # Save metrics
            metrics = {
                "mAP50": float(results.box.map50),
                "mAP50-95": float(results.box.map),
                "precision": float(results.box.mp),
                "recall": float(results.box.mr),
            }
            (version_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

            # Save manifest
            manifest = ModelManifest(
                version=version,
                name=model_name,
                task="detect",
                base_model=config.base_model,
                training_set=config.training_set,
                training_set_hash=service._get_training_set_hash(config.training_set),
                config=config.model_dump(),
                config_hash=hashlib.sha256(
                    json.dumps(config.model_dump(), sort_keys=True).encode()
                ).hexdigest(),
                metrics=metrics,
                created_at=datetime.now().isoformat(),
                files={"weights": "weights.pt"},
            )
            (version_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))

            # Update "latest" symlink
            latest_link = service.models_dir / model_name / "latest"
            if latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(f"v{version}")

            # Log event
            EventLogService(project_path).log_event(
                event_type="vision_training",
                status="SUCCESS",
                details={
                    "model_name": model_name,
                    "version": version,
                    "metrics": metrics,
                },
            )

    except Exception as e:
        EventLogService(project_path).log_event(
            event_type="vision_training",
            status="FAILED",
            details={"error": str(e), "job_id": job_id},
        )
        raise
```

#### 4.4 CLI Commands

**File: `cli/cmd/vision.go`**

```bash
# Training set management (like datasets)
lf vision training-sets list
lf vision training-sets create my_detector --task detect --classes person,car,truck
lf vision training-sets upload my_detector ./images/*.jpg --labels ./labels/
lf vision training-sets stats my_detector
lf vision training-sets delete my_detector

# Training pipelines
lf vision train my_detector --pipeline production_detector
lf vision train my_detector --base-model yolo11m --epochs 100 --batch-size 16
lf vision train status <job_id>
lf vision train logs <job_id>
lf vision train cancel <job_id>

# Model versioning
lf vision models list
lf vision models versions my_detector
lf vision models rollback my_detector --version 2
lf vision models tag my_detector --version 3 --tags production,v3-release
lf vision models export my_detector --format onnx --version latest
lf vision models delete my_detector --version 2

# Few-shot learning
lf vision few-shot my_new_class \
  --base-model yolo11m \
  --examples ./examples/class1/*.jpg \
  --class-name "safety_helmet"

# Face database management
lf vision faces create employees --model ArcFace
lf vision faces register employees john_doe ./john_photos/*.jpg
lf vision faces list employees
lf vision faces search employees --image ./unknown.jpg
lf vision faces delete employees john_doe
```

#### 4.5 REST API Endpoints for Training

```python
# Training Sets
POST   /v1/projects/{ns}/{proj}/vision/training-sets/
GET    /v1/projects/{ns}/{proj}/vision/training-sets/
DELETE /v1/projects/{ns}/{proj}/vision/training-sets/{name}
POST   /v1/projects/{ns}/{proj}/vision/training-sets/{name}/images
GET    /v1/projects/{ns}/{proj}/vision/training-sets/{name}/stats

# Training Jobs
POST   /v1/projects/{ns}/{proj}/vision/train
GET    /v1/projects/{ns}/{proj}/vision/train/{job_id}
DELETE /v1/projects/{ns}/{proj}/vision/train/{job_id}  # Cancel

# Model Management
GET    /v1/projects/{ns}/{proj}/vision/models
GET    /v1/projects/{ns}/{proj}/vision/models/{name}/versions
POST   /v1/projects/{ns}/{proj}/vision/models/{name}/rollback
POST   /v1/projects/{ns}/{proj}/vision/models/{name}/tag
POST   /v1/projects/{ns}/{proj}/vision/models/{name}/export

# Few-Shot Learning
POST   /v1/projects/{ns}/{proj}/vision/few-shot

# Face Databases
POST   /v1/projects/{ns}/{proj}/vision/faces/
GET    /v1/projects/{ns}/{proj}/vision/faces/
POST   /v1/projects/{ns}/{proj}/vision/faces/{db}/register
DELETE /v1/projects/{ns}/{proj}/vision/faces/{db}/identities/{person_id}
```

---

### Step 5: Configuration Schema Updates

#### Update `config/schema.yaml`

```yaml
runtime:
  models:
    items:
      properties:
        type:
          enum: [chat, transcription, tts, embedding, vision, face]

        # Vision-specific settings
        vision:
          type: object
          properties:
            task:
              type: string
              enum: [detect, segment, classify, pose]
              default: detect
            confidence:
              type: number
              default: 0.25
              minimum: 0
              maximum: 1
            iou_threshold:
              type: number
              default: 0.45
            classes:
              type: array
              items:
                type: integer
              description: "Filter to specific class IDs"
            return_masks:
              type: boolean
              default: true

        # Face recognition settings
        face:
          type: object
          properties:
            detector_backend:
              type: string
              enum: [retinaface, mtcnn, opencv, ssd, dlib]
              default: retinaface
            recognition_model:
              type: string
              enum: [ArcFace, Facenet512, VGG-Face, DeepFace]
              default: ArcFace
            db_path:
              type: string
              description: "Path to face database directory"
```

---

### Step 6: Server.py Updates

```python
# Add to runtimes/universal/server.py

async def load_vision(
    model_id: str,
    task: str = "detect",
) -> VisionModel:
    """Load a vision model with caching."""
    cache_key = f"vision:{task}:{model_id}"

    async with _model_load_lock:
        if cache_key in _models:
            _model_last_access[cache_key] = datetime.now()
            return _models[cache_key]

        model = VisionModel(
            model_id=model_id,
            device=get_device(),
            task=task,
        )
        await model.load()

        _models[cache_key] = model
        _model_last_access[cache_key] = datetime.now()

        return model

async def load_face_model(
    model_name: str = "ArcFace",
    detector_backend: str = "retinaface",
) -> FaceModel:
    """Load face recognition model with caching."""
    ...
```

---

## API Response Examples

### Object Detection

**Request:**
```bash
curl -X POST http://localhost:11540/v1/vision/detect \
  -F "file=@image.jpg" \
  -F "confidence=0.5"
```

**Response:**
```json
{
  "boxes": [
    {
      "x1": 100.5,
      "y1": 200.3,
      "x2": 400.2,
      "y2": 500.1,
      "confidence": 0.92,
      "class_id": 0,
      "class_name": "person"
    },
    {
      "x1": 450.0,
      "y1": 180.0,
      "x2": 600.0,
      "y2": 320.0,
      "confidence": 0.85,
      "class_id": 2,
      "class_name": "car"
    }
  ],
  "masks": null,
  "inference_time_ms": 12.5,
  "image_width": 1920,
  "image_height": 1080
}
```

### Instance Segmentation

**Response includes polygon masks:**
```json
{
  "boxes": [...],
  "masks": [
    {
      "contour": [[100, 200], [150, 180], [200, 220], ...],
      "class_id": 0,
      "class_name": "person",
      "area": 45230.5
    }
  ],
  "inference_time_ms": 18.2
}
```

### Face Recognition

**Response:**
```json
{
  "matches": [
    {
      "person_id": "john_doe",
      "confidence": 0.94,
      "box": {
        "x1": 120, "y1": 80, "x2": 280, "y2": 320,
        "confidence": 0.99
      }
    }
  ]
}
```

### WebSocket Streaming

**Client sends frame:**
```json
{
  "type": "input.video_frame",
  "frame": "base64_encoded_jpeg...",
  "timestamp_ms": 1234567890
}
```

**Server responds:**
```json
{
  "type": "detection.result",
  "timestamp_ms": 1234567890,
  "boxes": [...],
  "inference_time_ms": 8.5,
  "fps": 117.6
}
```

---

## Directory Structure (Final)

```
runtimes/universal/
├── models/
│   ├── base.py                      # Existing
│   ├── vision_model.py              # NEW: YOLO-based detection
│   ├── face_model.py                # NEW: Face recognition
│   └── ...
├── routers/
│   ├── vision/                      # NEW
│   │   ├── __init__.py
│   │   ├── router.py                # REST + WebSocket
│   │   ├── service.py               # Business logic
│   │   ├── types.py                 # Pydantic types
│   │   └── training.py              # Training endpoints
│   ├── transcription/               # Existing
│   └── ...
└── server.py                        # Add load_vision()

docs/website/docs/models/
├── vision-api.md                    # NEW: API documentation
├── face-recognition.md              # NEW: Face recognition guide
└── ...

examples/
└── vision/                          # NEW
    ├── object_detection.py
    ├── video_stream.py
    ├── face_recognition.py
    └── few_shot_training.py
```

---

## Dependencies to Add

```toml
# runtimes/universal/pyproject.toml

[project.dependencies]
ultralytics = ">=8.3.0"      # YOLO11 support
deepface = ">=0.0.93"        # Face recognition
opencv-python-headless = ">=4.9.0"  # Image processing
onnxruntime = ">=1.18.0"     # ONNX inference (optional)
onnxruntime-gpu = ">=1.18.0" # GPU acceleration (optional)
```

---

## Implementation Phases

### Phase 1: Core Detection (Week 1)
1. VisionModel class with YOLO
2. REST endpoints for detect/segment/classify
3. Type definitions
4. Basic tests

### Phase 2: Streaming (Week 2)
1. WebSocket router (following transcription pattern)
2. Video frame handling
3. RTSP/webcam source support
4. Connection management

### Phase 3: Face Recognition (Week 3)
1. FaceModel class with DeepFace
2. Face detection/recognition/analysis endpoints
3. Face database management
4. Registration endpoint

### Phase 4: Training (Week 4)
1. Training endpoint with job management
2. Few-shot learning
3. Model export (ONNX, CoreML, TFLite)
4. Custom model loading

### Phase 5: LlamaFarm Integration (Week 5)
1. Config schema updates
2. LlamaFarm server proxy routes
3. CLI commands (`lf vision detect`, etc.)
4. Documentation

---

## Testing Plan

1. **Unit tests**: Each model class method
2. **Integration tests**: Full API endpoint testing
3. **Performance tests**: FPS benchmarks for streaming
4. **Examples**: Working Python examples for each use case

---

## Sources

- [Ultralytics YOLO11 Docs](https://docs.ultralytics.com/)
- [Ultralytics Predict Mode](https://docs.ultralytics.com/modes/predict/)
- [DeepFace GitHub](https://github.com/serengil/deepface)
- [InsightFace GitHub](https://github.com/deepinsight/insightface)
- [ONNX Runtime](https://onnxruntime.ai/)
- [YOLO AI WebSocket Framework](https://github.com/ChaosAIVision/yolo-ai)
- [YOLO-SAM Paper](https://www.nature.com/articles/s41598-025-24576-6)
- [SAM2 Docs](https://docs.ultralytics.com/models/sam-2/)
- [Train YOLO11 Segmentation](https://blog.roboflow.com/train-yolov11-instance-segmentation/)
