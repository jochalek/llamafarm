"""
Vision Training Service

Manages vision training sets, model versioning, and face databases
with content-addressed storage for reproducibility.

Storage structure:
    lf_data/
      vision/
        training_sets/{name}/
          raw/              # Images by SHA-256 hash
          meta/             # Image metadata JSON
          labels/           # YOLO format label files
          index/by_name/    # Symlinks to raw
          manifest.json     # Training set manifest
        models/{name}/
          v{version}/
            weights.pt
            config.yaml
            metrics.json
            manifest.json
          latest -> v{version}  # Symlink
        faces/{name}/
          identities/{person_id}/
            raw/            # Face images by hash
            meta/           # Image metadata
          manifest.json
          index.json
"""

import contextlib
import hashlib
import json
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, Field

from core.logging import FastAPIStructLogger
from services.project_service import ProjectService

logger = FastAPIStructLogger()

DATA_DIR_NAME = "lf_data"
VISION_DIR_NAME = "vision"


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


# === Manifest Types ===


class ImageMetadata(BaseModel):
    """Metadata for a stored image."""

    hash: str = Field(..., description="SHA-256 hash of image content")
    original_name: str = Field(..., description="Original filename")
    extension: str = Field(..., description="File extension")
    split: DataSplit = Field(default=DataSplit.TRAIN, description="Data split")
    timestamp: float = Field(..., description="Unix timestamp when added")
    size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    width: int | None = Field(None, description="Image width if detected")
    height: int | None = Field(None, description="Image height if detected")
    labels_hash: str | None = Field(None, description="Hash of associated label file")


class TrainingSetManifest(BaseModel):
    """Manifest for a vision training set."""

    version: str = Field(default="1.0", description="Manifest format version")
    name: str = Field(..., description="Training set name")
    task: VisionTask = Field(..., description="Vision task type")
    classes: dict[int, str] = Field(
        default_factory=dict, description="Class ID to name mapping"
    )
    created_at: str = Field(..., description="ISO timestamp when created")
    updated_at: str = Field(..., description="ISO timestamp when last updated")
    file_count: int = Field(default=0, description="Total number of images")
    splits: dict[str, int] = Field(
        default_factory=lambda: {"train": 0, "val": 0, "test": 0},
        description="Count per split",
    )
    stats: dict[str, Any] = Field(
        default_factory=dict, description="Additional statistics"
    )


class ModelManifest(BaseModel):
    """Manifest for a trained model version."""

    version: int = Field(..., description="Version number")
    name: str = Field(..., description="Model name")
    task: VisionTask = Field(..., description="Vision task")
    base_model: str = Field(..., description="Base model used for training")
    created_at: str = Field(..., description="ISO timestamp when created")
    training_set: str | None = Field(None, description="Training set used")
    training_set_hash: str | None = Field(
        None, description="Hash of training set manifest"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Training configuration"
    )
    config_hash: str | None = Field(
        None, description="Hash of config for reproducibility"
    )
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Training metrics"
    )
    files: dict[str, str] = Field(
        default_factory=lambda: {"weights": "weights.pt"},
        description="Output files",
    )
    parent_version: int | None = Field(None, description="Parent version if fine-tuned")
    tags: list[str] = Field(default_factory=list, description="Version tags")


class FaceIdentity(BaseModel):
    """Metadata for a registered face identity."""

    person_id: str = Field(..., description="Unique person identifier")
    display_name: str = Field(..., description="Human-readable name")
    created_at: str = Field(..., description="ISO timestamp when created")
    updated_at: str = Field(..., description="ISO timestamp when last updated")
    image_count: int = Field(default=0, description="Number of registered face images")
    image_hashes: list[str] = Field(
        default_factory=list, description="Hashes of face images"
    )


class FaceDatabaseManifest(BaseModel):
    """Manifest for a face recognition database."""

    version: str = Field(default="1.0", description="Manifest format version")
    name: str = Field(..., description="Face database name")
    created_at: str = Field(..., description="ISO timestamp when created")
    updated_at: str = Field(..., description="ISO timestamp when last updated")
    detector_backend: str = Field(default="retinaface", description="Face detector")
    recognition_model: str = Field(default="ArcFace", description="Recognition model")
    total_identities: int = Field(default=0, description="Total registered people")
    total_images: int = Field(default=0, description="Total face images")


# === Result Types ===


@dataclass
class TrainingJobResult:
    """Result from starting a training job."""

    job_id: str
    model_name: str
    version: int
    status: str
    message: str


class VisionTrainingService:
    """
    Service for managing vision training sets, models, and face databases.

    Follows the same patterns as DatasetService and DataService for
    content-addressed storage with SHA-256 hashes.
    """

    def __init__(self, namespace: str, project: str):
        """
        Initialize the vision training service.

        Args:
            namespace: Project namespace
            project: Project name
        """
        self.namespace = namespace
        self.project = project
        self.project_dir = ProjectService.get_project_dir(namespace, project)
        self.vision_dir = Path(self.project_dir) / DATA_DIR_NAME / VISION_DIR_NAME

    # === Directory Management ===

    def _ensure_vision_dir(self) -> Path:
        """Ensure the vision data directory exists."""
        self.vision_dir.mkdir(parents=True, exist_ok=True)
        return self.vision_dir

    def _ensure_training_set_dir(self, name: str) -> Path:
        """Ensure a training set directory exists with proper structure."""
        self._ensure_vision_dir()
        set_dir = self.vision_dir / "training_sets" / name

        # Validate name to prevent path traversal
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError(f"Invalid training set name: {name!r}")

        # Create directory structure
        set_dir.mkdir(parents=True, exist_ok=True)
        (set_dir / "raw").mkdir(exist_ok=True)
        (set_dir / "meta").mkdir(exist_ok=True)
        (set_dir / "labels").mkdir(exist_ok=True)
        (set_dir / "index" / "by_name").mkdir(parents=True, exist_ok=True)

        return set_dir

    def _ensure_model_dir(self, name: str) -> Path:
        """Ensure a model directory exists."""
        self._ensure_vision_dir()
        model_dir = self.vision_dir / "models" / name

        if ".." in name or "/" in name or "\\" in name:
            raise ValueError(f"Invalid model name: {name!r}")

        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir

    def _ensure_face_db_dir(self, name: str) -> Path:
        """Ensure a face database directory exists."""
        self._ensure_vision_dir()
        db_dir = self.vision_dir / "faces" / name

        if ".." in name or "/" in name or "\\" in name:
            raise ValueError(f"Invalid face database name: {name!r}")

        db_dir.mkdir(parents=True, exist_ok=True)
        (db_dir / "identities").mkdir(exist_ok=True)

        return db_dir

    # === Hash Utilities ===

    @staticmethod
    def hash_data(data: bytes) -> str:
        """Compute SHA-256 hash of data."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_file(path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    # === Training Set Management ===

    def create_training_set(
        self,
        name: str,
        task: VisionTask,
        classes: list[str] | None = None,
    ) -> TrainingSetManifest:
        """
        Create a new training set.

        Args:
            name: Training set name
            task: Vision task type
            classes: List of class names (optional)

        Returns:
            TrainingSetManifest for the created set
        """
        set_dir = self._ensure_training_set_dir(name)
        manifest_path = set_dir / "manifest.json"

        if manifest_path.exists():
            raise ValueError(f"Training set '{name}' already exists")

        now = datetime.now().isoformat()
        class_map = {i: c for i, c in enumerate(classes)} if classes else {}

        manifest = TrainingSetManifest(
            name=name,
            task=task,
            classes=class_map,
            created_at=now,
            updated_at=now,
        )

        manifest_path.write_text(manifest.model_dump_json(indent=2))

        logger.info(
            "Created training set",
            name=name,
            task=task.value,
            classes=len(class_map),
        )

        return manifest

    def get_training_set(self, name: str) -> TrainingSetManifest:
        """Get a training set by name."""
        set_dir = self.vision_dir / "training_sets" / name
        manifest_path = set_dir / "manifest.json"

        if not manifest_path.exists():
            raise ValueError(f"Training set '{name}' not found")

        return TrainingSetManifest.model_validate_json(manifest_path.read_text())

    def list_training_sets(self) -> list[TrainingSetManifest]:
        """List all training sets."""
        sets_dir = self.vision_dir / "training_sets"
        if not sets_dir.exists():
            return []

        manifests = []
        for set_dir in sets_dir.iterdir():
            if set_dir.is_dir():
                manifest_path = set_dir / "manifest.json"
                if manifest_path.exists():
                    manifests.append(
                        TrainingSetManifest.model_validate_json(
                            manifest_path.read_text()
                        )
                    )

        return manifests

    def delete_training_set(self, name: str) -> TrainingSetManifest:
        """Delete a training set and all its contents."""
        manifest = self.get_training_set(name)
        set_dir = self.vision_dir / "training_sets" / name

        shutil.rmtree(set_dir)

        logger.info("Deleted training set", name=name)
        return manifest

    async def add_image_to_training_set(
        self,
        name: str,
        file: UploadFile,
        split: DataSplit = DataSplit.TRAIN,
        labels: str | None = None,
    ) -> ImageMetadata:
        """
        Add an image to a training set.

        Args:
            name: Training set name
            file: Uploaded image file
            split: Data split (train/val/test)
            labels: Optional YOLO format labels (one line per object)

        Returns:
            ImageMetadata for the added image
        """
        set_dir = self._ensure_training_set_dir(name)

        # Read and hash image
        image_data = await file.read()
        image_hash = self.hash_data(image_data)

        # Get extension and mime type
        original_name = os.path.basename(file.filename or "unknown.jpg")
        extension = Path(original_name).suffix.lower()
        mime_type = (
            file.content_type or mimetypes.guess_type(original_name)[0] or "image/jpeg"
        )

        # Check for duplicate
        meta_path = set_dir / "meta" / f"{image_hash}.json"
        if meta_path.exists():
            existing = ImageMetadata.model_validate_json(meta_path.read_text())
            logger.info("Image already exists in training set", hash=image_hash[:16])
            return existing

        # Write raw image
        raw_path = set_dir / "raw" / f"{image_hash}{extension}"
        raw_path.write_bytes(image_data)

        # Write labels if provided
        labels_hash = None
        if labels:
            labels_path = set_dir / "labels" / f"{image_hash}.txt"
            labels_path.write_text(labels)
            labels_hash = self.hash_data(labels.encode())

        # Try to get image dimensions
        width, height = None, None
        try:
            from PIL import Image

            with Image.open(raw_path) as img:
                width, height = img.size
        except Exception:
            pass

        # Create metadata
        metadata = ImageMetadata(
            hash=image_hash,
            original_name=original_name,
            extension=extension,
            split=split,
            timestamp=datetime.now().timestamp(),
            size=len(image_data),
            mime_type=mime_type,
            width=width,
            height=height,
            labels_hash=labels_hash,
        )
        meta_path.write_text(metadata.model_dump_json(indent=2))

        # Create symlink for name-based access
        symlink_path = set_dir / "index" / "by_name" / original_name
        if not symlink_path.exists():
            with contextlib.suppress(FileExistsError):
                symlink_path.symlink_to(f"../../raw/{image_hash}{extension}")

        # Update manifest
        manifest = self.get_training_set(name)
        manifest.file_count += 1
        manifest.splits[split.value] = manifest.splits.get(split.value, 0) + 1
        manifest.updated_at = datetime.now().isoformat()
        (set_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))

        logger.info(
            "Added image to training set",
            training_set=name,
            hash=image_hash[:16],
            split=split.value,
        )

        return metadata

    def list_training_set_images(self, name: str) -> list[ImageMetadata]:
        """List all images in a training set."""
        set_dir = self.vision_dir / "training_sets" / name
        meta_dir = set_dir / "meta"

        if not meta_dir.exists():
            return []

        images = []
        for meta_file in meta_dir.glob("*.json"):
            images.append(ImageMetadata.model_validate_json(meta_file.read_text()))

        return images

    def update_training_set_classes(
        self,
        name: str,
        classes: list[str],
    ) -> TrainingSetManifest:
        """Update the class definitions for a training set."""
        set_dir = self.vision_dir / "training_sets" / name
        manifest = self.get_training_set(name)

        manifest.classes = {i: c for i, c in enumerate(classes)}
        manifest.updated_at = datetime.now().isoformat()

        (set_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        return manifest

    def export_training_set(self, name: str, output_dir: Path) -> Path:
        """
        Export training set to YOLO format for training.

        Args:
            name: Training set name
            output_dir: Output directory

        Returns:
            Path to the output directory with data.yaml
        """
        set_dir = self.vision_dir / "training_sets" / name
        manifest = self.get_training_set(name)

        # Create YOLO directory structure
        for split in ["train", "val", "test"]:
            (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        # Copy files to appropriate splits
        for meta_file in (set_dir / "meta").glob("*.json"):
            meta = ImageMetadata.model_validate_json(meta_file.read_text())
            split = meta.split.value

            # Copy image
            src_image = set_dir / "raw" / f"{meta.hash}{meta.extension}"
            dst_image = output_dir / "images" / split / f"{meta.hash}{meta.extension}"
            if src_image.exists():
                shutil.copy2(src_image, dst_image)

            # Copy labels
            src_labels = set_dir / "labels" / f"{meta.hash}.txt"
            if src_labels.exists():
                dst_labels = output_dir / "labels" / split / f"{meta.hash}.txt"
                shutil.copy2(src_labels, dst_labels)

        # Generate data.yaml
        import yaml

        data_yaml = {
            "path": str(output_dir),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": manifest.classes,
        }
        (output_dir / "data.yaml").write_text(
            yaml.dump(data_yaml, default_flow_style=False)
        )

        logger.info("Exported training set", name=name, output_dir=str(output_dir))
        return output_dir

    # === Model Versioning ===

    def get_next_model_version(self, name: str) -> int:
        """Get the next version number for a model."""
        model_dir = self.vision_dir / "models" / name
        if not model_dir.exists():
            return 1

        versions = []
        for version_dir in model_dir.iterdir():
            if version_dir.is_dir() and version_dir.name.startswith("v"):
                with contextlib.suppress(ValueError):
                    versions.append(int(version_dir.name[1:]))

        return max(versions, default=0) + 1

    def create_model_version(
        self,
        name: str,
        task: VisionTask,
        base_model: str,
        config: dict[str, Any],
        training_set: str | None = None,
    ) -> tuple[int, Path]:
        """
        Create a new model version directory.

        Args:
            name: Model name
            task: Vision task
            base_model: Base model identifier
            config: Training configuration
            training_set: Name of training set used

        Returns:
            Tuple of (version number, version directory path)
        """
        model_dir = self._ensure_model_dir(name)
        version = self.get_next_model_version(name)
        version_dir = model_dir / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Compute config hash for reproducibility
        config_hash = self.hash_data(json.dumps(config, sort_keys=True).encode())

        # Get training set hash if provided
        training_set_hash = None
        if training_set:
            try:
                ts_manifest = self.get_training_set(training_set)
                training_set_hash = self.hash_data(
                    ts_manifest.model_dump_json().encode()
                )
            except Exception:
                pass

        # Create manifest
        manifest = ModelManifest(
            version=version,
            name=name,
            task=task,
            base_model=base_model,
            created_at=datetime.now().isoformat(),
            training_set=training_set,
            training_set_hash=training_set_hash,
            config=config,
            config_hash=config_hash,
        )

        # Save config snapshot
        import yaml

        (version_dir / "config.yaml").write_text(
            yaml.dump(config, default_flow_style=False)
        )
        (version_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))

        logger.info("Created model version", name=name, version=version)
        return version, version_dir

    def save_model_weights(
        self,
        name: str,
        version: int,
        weights_path: Path,
        metrics: dict[str, float] | None = None,
    ) -> ModelManifest:
        """
        Save trained model weights and update manifest with metrics.

        Args:
            name: Model name
            version: Version number
            weights_path: Path to weights file
            metrics: Training metrics

        Returns:
            Updated ModelManifest
        """
        version_dir = self.vision_dir / "models" / name / f"v{version}"
        if not version_dir.exists():
            raise ValueError(f"Model version v{version} not found for '{name}'")

        # Copy weights
        dest_weights = version_dir / "weights.pt"
        shutil.copy2(weights_path, dest_weights)

        # Load and update manifest
        manifest_path = version_dir / "manifest.json"
        manifest = ModelManifest.model_validate_json(manifest_path.read_text())

        if metrics:
            manifest.metrics = metrics
            (version_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

        manifest_path.write_text(manifest.model_dump_json(indent=2))

        # Update latest symlink
        model_dir = self.vision_dir / "models" / name
        latest_link = model_dir / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(f"v{version}")

        logger.info("Saved model weights", name=name, version=version, metrics=metrics)
        return manifest

    def list_model_versions(self, name: str) -> list[ModelManifest]:
        """List all versions of a model."""
        model_dir = self.vision_dir / "models" / name
        if not model_dir.exists():
            return []

        versions = []
        for version_dir in sorted(model_dir.iterdir(), reverse=True):
            if version_dir.is_dir() and version_dir.name.startswith("v"):
                manifest_path = version_dir / "manifest.json"
                if manifest_path.exists():
                    versions.append(
                        ModelManifest.model_validate_json(manifest_path.read_text())
                    )

        return versions

    def get_model_version(
        self, name: str, version: int | str = "latest"
    ) -> ModelManifest:
        """Get a specific model version."""
        model_dir = self.vision_dir / "models" / name

        if version == "latest":
            latest_link = model_dir / "latest"
            if not latest_link.exists():
                raise ValueError(f"No versions found for model '{name}'")
            version_dir = latest_link.resolve()
        else:
            version_dir = model_dir / f"v{version}"

        if not version_dir.exists():
            raise ValueError(f"Model version v{version} not found for '{name}'")

        manifest_path = version_dir / "manifest.json"
        return ModelManifest.model_validate_json(manifest_path.read_text())

    def rollback_model(self, name: str, target_version: int) -> ModelManifest:
        """Rollback model to a previous version by updating the latest symlink."""
        model_dir = self.vision_dir / "models" / name
        version_dir = model_dir / f"v{target_version}"

        if not version_dir.exists():
            raise ValueError(f"Model version v{target_version} not found for '{name}'")

        # Update latest symlink
        latest_link = model_dir / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(f"v{target_version}")

        manifest = self.get_model_version(name, target_version)
        logger.info("Rolled back model", name=name, version=target_version)
        return manifest

    def tag_model_version(
        self,
        name: str,
        version: int,
        tags: list[str],
    ) -> ModelManifest:
        """Add tags to a model version."""
        version_dir = self.vision_dir / "models" / name / f"v{version}"
        manifest_path = version_dir / "manifest.json"

        if not manifest_path.exists():
            raise ValueError(f"Model version v{version} not found for '{name}'")

        manifest = ModelManifest.model_validate_json(manifest_path.read_text())
        manifest.tags = list(set(manifest.tags + tags))
        manifest_path.write_text(manifest.model_dump_json(indent=2))

        logger.info("Tagged model version", name=name, version=version, tags=tags)
        return manifest

    def list_models(self) -> list[dict[str, Any]]:
        """List all models with their latest version info."""
        models_dir = self.vision_dir / "models"
        if not models_dir.exists():
            return []

        models = []
        for model_dir in models_dir.iterdir():
            if model_dir.is_dir():
                try:
                    manifest = self.get_model_version(model_dir.name, "latest")
                    versions = self.list_model_versions(model_dir.name)
                    models.append(
                        {
                            "name": model_dir.name,
                            "latest_version": manifest.version,
                            "total_versions": len(versions),
                            "task": manifest.task.value,
                            "base_model": manifest.base_model,
                            "metrics": manifest.metrics,
                            "tags": manifest.tags,
                        }
                    )
                except Exception:
                    pass

        return models

    # === Face Database Management ===

    def create_face_database(
        self,
        name: str,
        detector_backend: str = "retinaface",
        recognition_model: str = "ArcFace",
    ) -> FaceDatabaseManifest:
        """Create a new face recognition database."""
        db_dir = self._ensure_face_db_dir(name)
        manifest_path = db_dir / "manifest.json"

        if manifest_path.exists():
            raise ValueError(f"Face database '{name}' already exists")

        now = datetime.now().isoformat()
        manifest = FaceDatabaseManifest(
            name=name,
            created_at=now,
            updated_at=now,
            detector_backend=detector_backend,
            recognition_model=recognition_model,
        )

        manifest_path.write_text(manifest.model_dump_json(indent=2))
        (db_dir / "index.json").write_text(json.dumps({"identities": {}}, indent=2))

        logger.info(
            "Created face database",
            name=name,
            detector=detector_backend,
            model=recognition_model,
        )
        return manifest

    def get_face_database(self, name: str) -> FaceDatabaseManifest:
        """Get a face database by name."""
        db_dir = self.vision_dir / "faces" / name
        manifest_path = db_dir / "manifest.json"

        if not manifest_path.exists():
            raise ValueError(f"Face database '{name}' not found")

        return FaceDatabaseManifest.model_validate_json(manifest_path.read_text())

    def list_face_databases(self) -> list[FaceDatabaseManifest]:
        """List all face databases."""
        faces_dir = self.vision_dir / "faces"
        if not faces_dir.exists():
            return []

        databases = []
        for db_dir in faces_dir.iterdir():
            if db_dir.is_dir():
                manifest_path = db_dir / "manifest.json"
                if manifest_path.exists():
                    databases.append(
                        FaceDatabaseManifest.model_validate_json(
                            manifest_path.read_text()
                        )
                    )

        return databases

    def delete_face_database(self, name: str) -> FaceDatabaseManifest:
        """Delete a face database and all its contents."""
        manifest = self.get_face_database(name)
        db_dir = self.vision_dir / "faces" / name

        shutil.rmtree(db_dir)

        logger.info("Deleted face database", name=name)
        return manifest

    async def register_face(
        self,
        database: str,
        person_id: str,
        file: UploadFile,
        display_name: str | None = None,
    ) -> FaceIdentity:
        """
        Register a face image for a person.

        Args:
            database: Face database name
            person_id: Unique person identifier
            file: Uploaded face image
            display_name: Optional human-readable name

        Returns:
            FaceIdentity for the person
        """
        db_dir = self.vision_dir / "faces" / database

        if not (db_dir / "manifest.json").exists():
            raise ValueError(f"Face database '{database}' not found")

        # Ensure person directory exists
        person_dir = db_dir / "identities" / person_id
        person_dir.mkdir(parents=True, exist_ok=True)
        (person_dir / "raw").mkdir(exist_ok=True)
        (person_dir / "meta").mkdir(exist_ok=True)

        # Read and hash image
        image_data = await file.read()
        image_hash = self.hash_data(image_data)

        # Get extension
        original_name = os.path.basename(file.filename or "unknown.jpg")
        extension = Path(original_name).suffix.lower() or ".jpg"

        # Write raw image
        raw_path = person_dir / "raw" / f"{image_hash}{extension}"
        raw_path.write_bytes(image_data)

        # Write metadata
        meta_path = person_dir / "meta" / f"{image_hash}.json"
        meta = {
            "hash": image_hash,
            "original_name": original_name,
            "extension": extension,
            "timestamp": datetime.now().timestamp(),
            "size": len(image_data),
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        # Load or create person metadata
        person_meta_path = person_dir / "meta.json"
        now = datetime.now().isoformat()

        if person_meta_path.exists():
            identity = FaceIdentity.model_validate_json(person_meta_path.read_text())
            if image_hash not in identity.image_hashes:
                identity.image_hashes.append(image_hash)
                identity.image_count = len(identity.image_hashes)
            identity.updated_at = now
        else:
            identity = FaceIdentity(
                person_id=person_id,
                display_name=display_name or person_id,
                created_at=now,
                updated_at=now,
                image_count=1,
                image_hashes=[image_hash],
            )

        person_meta_path.write_text(identity.model_dump_json(indent=2))

        # Update database manifest
        manifest = self.get_face_database(database)
        manifest.updated_at = now

        # Count totals
        total_identities = 0
        total_images = 0
        for id_dir in (db_dir / "identities").iterdir():
            if id_dir.is_dir():
                total_identities += 1
                id_meta = id_dir / "meta.json"
                if id_meta.exists():
                    id_data = FaceIdentity.model_validate_json(id_meta.read_text())
                    total_images += id_data.image_count

        manifest.total_identities = total_identities
        manifest.total_images = total_images
        (db_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))

        # Update index
        index_path = db_dir / "index.json"
        index = json.loads(index_path.read_text())
        index["identities"][person_id] = {
            "display_name": identity.display_name,
            "image_count": identity.image_count,
        }
        index_path.write_text(json.dumps(index, indent=2))

        logger.info(
            "Registered face",
            database=database,
            person_id=person_id,
            hash=image_hash[:16],
        )

        return identity

    def list_face_identities(self, database: str) -> list[FaceIdentity]:
        """List all registered identities in a face database."""
        db_dir = self.vision_dir / "faces" / database
        identities_dir = db_dir / "identities"

        if not identities_dir.exists():
            return []

        identities = []
        for person_dir in identities_dir.iterdir():
            if person_dir.is_dir():
                meta_path = person_dir / "meta.json"
                if meta_path.exists():
                    identities.append(
                        FaceIdentity.model_validate_json(meta_path.read_text())
                    )

        return identities

    def get_face_identity(self, database: str, person_id: str) -> FaceIdentity:
        """Get a specific face identity."""
        meta_path = (
            self.vision_dir
            / "faces"
            / database
            / "identities"
            / person_id
            / "meta.json"
        )

        if not meta_path.exists():
            raise ValueError(
                f"Identity '{person_id}' not found in database '{database}'"
            )

        return FaceIdentity.model_validate_json(meta_path.read_text())

    def delete_face_identity(self, database: str, person_id: str) -> FaceIdentity:
        """Delete a face identity from a database."""
        identity = self.get_face_identity(database, person_id)
        person_dir = self.vision_dir / "faces" / database / "identities" / person_id

        shutil.rmtree(person_dir)

        # Update manifest
        db_dir = self.vision_dir / "faces" / database
        manifest = self.get_face_database(database)
        manifest.total_identities = max(0, manifest.total_identities - 1)
        manifest.total_images = max(0, manifest.total_images - identity.image_count)
        manifest.updated_at = datetime.now().isoformat()
        (db_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))

        # Update index
        index_path = db_dir / "index.json"
        index = json.loads(index_path.read_text())
        index["identities"].pop(person_id, None)
        index_path.write_text(json.dumps(index, indent=2))

        logger.info("Deleted face identity", database=database, person_id=person_id)
        return identity

    def get_face_db_path(self, database: str) -> Path:
        """
        Get the path to use for face search/recognition.

        This returns the path to the identities directory, which is the format
        expected by DeepFace's find() function.
        """
        db_dir = self.vision_dir / "faces" / database

        if not (db_dir / "manifest.json").exists():
            raise ValueError(f"Face database '{database}' not found")

        return db_dir / "identities"
