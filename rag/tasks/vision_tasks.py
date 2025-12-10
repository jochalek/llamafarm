"""
Vision Training Tasks

Celery tasks for YOLO model training and fine-tuning.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from celery import Task

from celery_app import app

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logging import RAGStructLogger

logger = RAGStructLogger("rag.tasks.vision")


class VisionTrainingTask(Task):
    """Base task class for vision training operations with error handling."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure details."""
        logger.error(
            "Vision training task failed",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
            task_args=args,
            task_kwargs=kwargs,
            exc_info=True,
        )


@app.task(bind=True, base=VisionTrainingTask, name="vision.train_model")
def train_vision_model_task(
    self,
    project_dir: str,
    model_name: str,
    version: int,
    training_set: str,
    base_model: str = "yolo11m",
    epochs: int = 100,
    batch_size: int = 16,
    imgsz: int = 640,
    patience: int = 50,
    device: str = "auto",
    workers: int = 8,
    lr0: float = 0.01,
    export_formats: list[str] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    Train a YOLO model using Celery task.

    Args:
        project_dir: Project directory path
        model_name: Name for the trained model
        version: Version number
        training_set: Name of the training set to use
        base_model: Base YOLO model (e.g., yolo11n, yolo11m, yolo11l)
        epochs: Number of training epochs
        batch_size: Batch size for training
        imgsz: Image size for training
        patience: Early stopping patience
        device: Training device (auto, cpu, 0, 0,1 for multi-GPU)
        workers: Number of data loader workers
        lr0: Initial learning rate
        export_formats: Additional export formats (onnx, coreml, etc.)

    Returns:
        Tuple of (success: bool, details: dict)
    """
    logger.info(
        "Starting YOLO model training",
        extra={
            "task_id": self.request.id,
            "model_name": model_name,
            "version": version,
            "training_set": training_set,
            "base_model": base_model,
            "epochs": epochs,
        },
    )

    details = {
        "model_name": model_name,
        "version": version,
        "training_set": training_set,
        "base_model": base_model,
        "epochs_requested": epochs,
        "epochs_completed": 0,
        "metrics": {},
        "error": None,
        "weights_path": None,
    }

    try:
        from ultralytics import YOLO

        # Set up paths
        project_path = Path(project_dir)
        vision_dir = project_path / "lf_data" / "vision"
        training_set_dir = vision_dir / "training_sets" / training_set
        model_version_dir = vision_dir / "models" / model_name / f"v{version}"

        if not training_set_dir.exists():
            details["error"] = f"Training set '{training_set}' not found"
            return False, details

        # Create temp directory for YOLO format export
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / "dataset"

            # Export training set to YOLO format
            logger.info("Exporting training set to YOLO format")
            _export_training_set(training_set_dir, export_dir)

            # Check if data.yaml was created
            data_yaml = export_dir / "data.yaml"
            if not data_yaml.exists():
                details["error"] = "Failed to create data.yaml"
                return False, details

            # Initialize YOLO model
            logger.info(f"Loading base model: {base_model}")
            model = YOLO(base_model)

            # Train the model
            logger.info("Starting training")
            results = model.train(
                data=str(data_yaml),
                epochs=epochs,
                batch=batch_size,
                imgsz=imgsz,
                patience=patience,
                device=device if device != "auto" else None,
                workers=workers,
                lr0=lr0,
                project=str(model_version_dir),
                name="train",
                exist_ok=True,
                verbose=True,
            )

            # Extract metrics
            if hasattr(results, "box"):
                details["metrics"] = {
                    "mAP50": float(results.box.map50)
                    if hasattr(results.box, "map50")
                    else 0,
                    "mAP50-95": float(results.box.map)
                    if hasattr(results.box, "map")
                    else 0,
                    "precision": float(results.box.mp)
                    if hasattr(results.box, "mp")
                    else 0,
                    "recall": float(results.box.mr)
                    if hasattr(results.box, "mr")
                    else 0,
                }

            # Copy best weights
            train_dir = model_version_dir / "train"
            best_weights = train_dir / "weights" / "best.pt"

            if best_weights.exists():
                final_weights = model_version_dir / "weights.pt"
                shutil.copy2(best_weights, final_weights)
                details["weights_path"] = str(final_weights)
                details["epochs_completed"] = epochs

                # Export to additional formats if requested
                if export_formats:
                    for fmt in export_formats:
                        if fmt != "pt":
                            try:
                                model.export(format=fmt)
                                exported = train_dir / "weights" / f"best.{fmt}"
                                if exported.exists():
                                    shutil.copy2(
                                        exported, model_version_dir / f"weights.{fmt}"
                                    )
                            except Exception as e:
                                logger.warning(f"Failed to export to {fmt}: {e}")

                # Save metrics
                (model_version_dir / "metrics.json").write_text(
                    json.dumps(details["metrics"], indent=2)
                )

                # Update manifest
                manifest_path = model_version_dir / "manifest.json"
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                    manifest["metrics"] = details["metrics"]
                    manifest["files"]["weights"] = "weights.pt"
                    manifest_path.write_text(json.dumps(manifest, indent=2))

                # Update latest symlink
                model_dir = vision_dir / "models" / model_name
                latest_link = model_dir / "latest"
                if latest_link.exists() or latest_link.is_symlink():
                    latest_link.unlink()
                latest_link.symlink_to(f"v{version}")

                logger.info(
                    "Training completed successfully",
                    extra={
                        "task_id": self.request.id,
                        "metrics": details["metrics"],
                    },
                )
                return True, details
            else:
                details["error"] = "Training completed but weights not found"
                return False, details

    except ImportError as e:
        details["error"] = (
            f"Missing dependency: {e}. Install ultralytics: pip install ultralytics"
        )
        logger.error("Vision training failed - missing dependency", error=str(e))
        return False, details

    except Exception as e:
        details["error"] = str(e)
        logger.error(
            "Vision training failed",
            extra={
                "task_id": self.request.id,
                "error": str(e),
            },
            exc_info=True,
        )
        return False, details


def _export_training_set(training_set_dir: Path, output_dir: Path) -> None:
    """Export a training set to YOLO format."""
    import yaml

    # Read manifest
    manifest_path = training_set_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Training set manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())

    # Create YOLO directory structure
    for split in ["train", "val", "test"]:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    # Copy files
    meta_dir = training_set_dir / "meta"
    for meta_file in meta_dir.glob("*.json"):
        meta = json.loads(meta_file.read_text())
        img_hash = meta["hash"]
        ext = meta.get("extension", ".jpg")
        split = meta.get("split", "train")

        # Copy image
        src_image = training_set_dir / "raw" / f"{img_hash}{ext}"
        if src_image.exists():
            dst_image = output_dir / "images" / split / f"{img_hash}{ext}"
            shutil.copy2(src_image, dst_image)

        # Copy labels
        src_labels = training_set_dir / "labels" / f"{img_hash}.txt"
        if src_labels.exists():
            dst_labels = output_dir / "labels" / split / f"{img_hash}.txt"
            shutil.copy2(src_labels, dst_labels)

    # Generate data.yaml
    classes = manifest.get("classes", {})
    data_config = {
        "path": str(output_dir),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {int(k): v for k, v in classes.items()},
    }
    (output_dir / "data.yaml").write_text(
        yaml.dump(data_config, default_flow_style=False)
    )


@app.task(bind=True, base=VisionTrainingTask, name="vision.export_model")
def export_model_task(
    self,
    project_dir: str,
    model_name: str,
    version: int | str = "latest",
    format: str = "onnx",
) -> tuple[bool, dict[str, Any]]:
    """
    Export a trained model to different formats.

    Args:
        project_dir: Project directory path
        model_name: Model name
        version: Version number or "latest"
        format: Export format (onnx, coreml, tflite, etc.)

    Returns:
        Tuple of (success: bool, details: dict)
    """
    logger.info(
        "Exporting model",
        extra={
            "task_id": self.request.id,
            "model_name": model_name,
            "version": version,
            "format": format,
        },
    )

    details = {
        "model_name": model_name,
        "version": version,
        "format": format,
        "output_path": None,
        "error": None,
    }

    try:
        from ultralytics import YOLO

        project_path = Path(project_dir)
        vision_dir = project_path / "lf_data" / "vision"
        model_dir = vision_dir / "models" / model_name

        # Resolve version
        if version == "latest":
            latest_link = model_dir / "latest"
            if not latest_link.exists():
                details["error"] = f"No versions found for model '{model_name}'"
                return False, details
            version_dir = latest_link.resolve()
        else:
            version_dir = model_dir / f"v{version}"

        weights_path = version_dir / "weights.pt"
        if not weights_path.exists():
            details["error"] = f"Weights not found at {weights_path}"
            return False, details

        # Load and export
        model = YOLO(str(weights_path))
        export_path = model.export(format=format)

        if export_path:
            # Copy to version directory
            export_file = Path(export_path)
            dest_path = version_dir / f"weights.{format}"
            shutil.copy2(export_file, dest_path)
            details["output_path"] = str(dest_path)

            logger.info(
                "Model exported successfully",
                extra={
                    "task_id": self.request.id,
                    "output_path": str(dest_path),
                },
            )
            return True, details
        else:
            details["error"] = "Export failed"
            return False, details

    except ImportError as e:
        details["error"] = f"Missing dependency: {e}"
        return False, details

    except Exception as e:
        details["error"] = str(e)
        logger.error(
            "Model export failed",
            extra={
                "task_id": self.request.id,
                "error": str(e),
            },
            exc_info=True,
        )
        return False, details
