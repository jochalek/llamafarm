"""
Vision Training API Router

REST endpoints for managing vision training sets, models, and face databases.
"""

import base64
import io
import os
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from core.celery import app as celery_app
from core.logging import FastAPIStructLogger
from services.project_service import ProjectService
from services.vision_training_service import (
    DataSplit,
    FaceDatabaseManifest,
    FaceIdentity,
    ImageMetadata,
    ModelManifest,
    TrainingSetManifest,
    VisionTask,
    VisionTrainingService,
)

from .models import (
    AddImageRequest,
    CreateFaceDatabaseRequest,
    CreateTrainingSetRequest,
    ExportModelRequest,
    FaceDatabaseResponse,
    FaceIdentityResponse,
    ImageMetadataResponse,
    ModelSummaryResponse,
    ModelVersionResponse,
    RegisterFaceRequest,
    RollbackRequest,
    StartTrainingRequest,
    TagVersionRequest,
    TrainingJobResponse,
    TrainingSetResponse,
    UpdateTrainingSetClassesRequest,
)

logger = FastAPIStructLogger()

router = APIRouter(
    prefix="/projects/{namespace}/{project}/vision", tags=["vision-training"]
)


def get_service(namespace: str, project: str) -> VisionTrainingService:
    """Get VisionTrainingService for a project."""
    # Just check project directory exists (don't validate full config)
    project_dir = ProjectService.get_project_dir(namespace, project)
    if not os.path.exists(project_dir):
        raise HTTPException(
            status_code=404, detail=f"Project not found: {namespace}/{project}"
        )
    return VisionTrainingService(namespace, project)


# === Training Set Endpoints ===


@router.post("/training-sets", response_model=TrainingSetResponse)
async def create_training_set(
    namespace: str,
    project: str,
    request: CreateTrainingSetRequest,
) -> TrainingSetResponse:
    """Create a new vision training set."""
    try:
        service = get_service(namespace, project)
        manifest = service.create_training_set(
            name=request.name,
            task=VisionTask(request.task.value),
            classes=request.classes,
        )
        return _training_set_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to create training set: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/training-sets", response_model=list[TrainingSetResponse])
async def list_training_sets(
    namespace: str,
    project: str,
) -> list[TrainingSetResponse]:
    """List all training sets in a project."""
    try:
        service = get_service(namespace, project)
        manifests = service.list_training_sets()
        return [_training_set_to_response(m) for m in manifests]
    except Exception as e:
        logger.exception(f"Failed to list training sets: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/training-sets/{name}", response_model=TrainingSetResponse)
async def get_training_set(
    namespace: str,
    project: str,
    name: str,
) -> TrainingSetResponse:
    """Get a training set by name."""
    try:
        service = get_service(namespace, project)
        manifest = service.get_training_set(name)
        return _training_set_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to get training set: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.delete("/training-sets/{name}", response_model=TrainingSetResponse)
async def delete_training_set(
    namespace: str,
    project: str,
    name: str,
) -> TrainingSetResponse:
    """Delete a training set."""
    try:
        service = get_service(namespace, project)
        manifest = service.delete_training_set(name)
        return _training_set_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to delete training set: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.patch("/training-sets/{name}/classes", response_model=TrainingSetResponse)
async def update_training_set_classes(
    namespace: str,
    project: str,
    name: str,
    request: UpdateTrainingSetClassesRequest,
) -> TrainingSetResponse:
    """Update the class definitions for a training set."""
    try:
        service = get_service(namespace, project)
        manifest = service.update_training_set_classes(name, request.classes)
        return _training_set_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to update classes: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/training-sets/{name}/images", response_model=ImageMetadataResponse)
async def add_image_to_training_set(
    namespace: str,
    project: str,
    name: str,
    file: Annotated[UploadFile | None, File(description="Image file")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    split: Annotated[str, Form(description="Data split")] = "train",
    labels: Annotated[str | None, Form(description="YOLO format labels")] = None,
) -> ImageMetadataResponse:
    """Add an image to a training set (multipart form)."""
    try:
        service = get_service(namespace, project)

        # Handle file upload vs base64
        if file:
            metadata = await service.add_image_to_training_set(
                name=name,
                file=file,
                split=DataSplit(split),
                labels=labels,
            )
        elif image_base64:
            # Convert base64 to UploadFile
            image_data = base64.b64decode(image_base64)
            temp_file = io.BytesIO(image_data)
            upload = UploadFile(file=temp_file, filename="image.jpg")
            metadata = await service.add_image_to_training_set(
                name=name,
                file=upload,
                split=DataSplit(split),
                labels=labels,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Must provide file or image_base64"
            )

        return _image_metadata_to_response(metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to add image: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/training-sets/{name}/images/json", response_model=ImageMetadataResponse)
async def add_image_json(
    namespace: str,
    project: str,
    name: str,
    request: AddImageRequest,
) -> ImageMetadataResponse:
    """Add an image to a training set (JSON body with base64)."""
    try:
        service = get_service(namespace, project)

        # Convert base64 to UploadFile
        image_data = base64.b64decode(request.image_base64)
        temp_file = io.BytesIO(image_data)
        upload = UploadFile(file=temp_file, filename=request.filename)

        metadata = await service.add_image_to_training_set(
            name=name,
            file=upload,
            split=DataSplit(request.split.value),
            labels=request.labels,
        )
        return _image_metadata_to_response(metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to add image: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/training-sets/{name}/images", response_model=list[ImageMetadataResponse])
async def list_training_set_images(
    namespace: str,
    project: str,
    name: str,
) -> list[ImageMetadataResponse]:
    """List all images in a training set."""
    try:
        service = get_service(namespace, project)
        images = service.list_training_set_images(name)
        return [_image_metadata_to_response(img) for img in images]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to list images: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


# === Model Training Endpoints ===


@router.post("/train", response_model=TrainingJobResponse)
async def start_training(
    namespace: str,
    project: str,
    request: StartTrainingRequest,
) -> TrainingJobResponse:
    """Start a model training job."""
    try:
        service = get_service(namespace, project)

        # Validate training set exists
        try:
            service.get_training_set(request.training_set)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Training set '{request.training_set}' not found",
            ) from None

        # Create model version directory
        config = {
            "base_model": request.base_model,
            "epochs": request.epochs,
            "batch_size": request.batch_size,
            "imgsz": request.imgsz,
            "patience": request.patience,
            "device": request.device,
            "lr0": request.lr0,
        }

        version, version_dir = service.create_model_version(
            name=request.model_name,
            task=VisionTask.DETECT,
            base_model=request.base_model,
            config=config,
            training_set=request.training_set,
        )

        # Start Celery task
        from rag.tasks.vision_tasks import train_vision_model_task

        project_dir = ProjectService.get_project_dir(namespace, project)
        task = train_vision_model_task.delay(
            project_dir=project_dir,
            model_name=request.model_name,
            version=version,
            training_set=request.training_set,
            base_model=request.base_model,
            epochs=request.epochs,
            batch_size=request.batch_size,
            imgsz=request.imgsz,
            patience=request.patience,
            device=request.device,
            lr0=request.lr0,
            export_formats=request.export_formats,
        )

        logger.info(
            "Started training job",
            model_name=request.model_name,
            version=version,
            task_id=task.id,
        )

        return TrainingJobResponse(
            job_id=task.id,
            model_name=request.model_name,
            version=version,
            status="started",
            message=f"Training job started for {request.model_name} v{version}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to start training: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/train/{job_id}")
async def get_training_status(
    namespace: str,
    project: str,
    job_id: str,
) -> dict[str, Any]:
    """Get the status of a training job."""
    try:
        result = celery_app.AsyncResult(job_id)

        response = {
            "job_id": job_id,
            "status": result.status,
            "ready": result.ready(),
        }

        if result.ready():
            if result.successful():
                success, details = result.result
                response["success"] = success
                response["details"] = details
            else:
                response["success"] = False
                response["error"] = str(result.result)

        return response
    except Exception as e:
        logger.exception(f"Failed to get training status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.delete("/train/{job_id}")
async def cancel_training(
    namespace: str,
    project: str,
    job_id: str,
) -> dict[str, str]:
    """Cancel a training job."""
    try:
        celery_app.control.revoke(job_id, terminate=True)
        return {"message": f"Cancelled training job {job_id}"}
    except Exception as e:
        logger.exception(f"Failed to cancel training: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


# === Model Management Endpoints ===


@router.get("/models", response_model=list[ModelSummaryResponse])
async def list_models(
    namespace: str,
    project: str,
) -> list[ModelSummaryResponse]:
    """List all trained models."""
    try:
        service = get_service(namespace, project)
        models = service.list_models()
        return [ModelSummaryResponse(**m) for m in models]
    except Exception as e:
        logger.exception(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/models/{name}/versions", response_model=list[ModelVersionResponse])
async def list_model_versions(
    namespace: str,
    project: str,
    name: str,
) -> list[ModelVersionResponse]:
    """List all versions of a model."""
    try:
        service = get_service(namespace, project)
        versions = service.list_model_versions(name)
        return [_model_version_to_response(v) for v in versions]
    except Exception as e:
        logger.exception(f"Failed to list model versions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/models/{name}/versions/{version}", response_model=ModelVersionResponse)
async def get_model_version(
    namespace: str,
    project: str,
    name: str,
    version: str,
) -> ModelVersionResponse:
    """Get a specific model version."""
    try:
        service = get_service(namespace, project)
        v = version if version == "latest" else int(version)
        manifest = service.get_model_version(name, v)
        return _model_version_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to get model version: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/models/{name}/rollback", response_model=ModelVersionResponse)
async def rollback_model(
    namespace: str,
    project: str,
    name: str,
    request: RollbackRequest,
) -> ModelVersionResponse:
    """Rollback a model to a previous version."""
    try:
        service = get_service(namespace, project)
        manifest = service.rollback_model(name, request.version)
        return _model_version_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to rollback model: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/models/{name}/tag", response_model=ModelVersionResponse)
async def tag_model_version(
    namespace: str,
    project: str,
    name: str,
    request: TagVersionRequest,
) -> ModelVersionResponse:
    """Add tags to a model version."""
    try:
        service = get_service(namespace, project)
        manifest = service.tag_model_version(name, request.version, request.tags)
        return _model_version_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to tag model: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/models/{name}/export")
async def export_model(
    namespace: str,
    project: str,
    name: str,
    request: ExportModelRequest,
) -> dict[str, Any]:
    """Export a model to a different format (starts async task)."""
    try:
        from rag.tasks.vision_tasks import export_model_task

        project_dir = ProjectService.get_project_dir(namespace, project)

        task = export_model_task.delay(
            project_dir=project_dir,
            model_name=name,
            version=request.version,
            format=request.format,
        )

        return {
            "job_id": task.id,
            "model_name": name,
            "version": request.version,
            "format": request.format,
            "status": "started",
        }
    except Exception as e:
        logger.exception(f"Failed to start export: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


# === Face Database Endpoints ===


@router.post("/faces", response_model=FaceDatabaseResponse)
async def create_face_database(
    namespace: str,
    project: str,
    request: CreateFaceDatabaseRequest,
) -> FaceDatabaseResponse:
    """Create a new face recognition database."""
    try:
        service = get_service(namespace, project)
        manifest = service.create_face_database(
            name=request.name,
            detector_backend=request.detector_backend,
            recognition_model=request.recognition_model,
        )
        return _face_db_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to create face database: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/faces", response_model=list[FaceDatabaseResponse])
async def list_face_databases(
    namespace: str,
    project: str,
) -> list[FaceDatabaseResponse]:
    """List all face databases."""
    try:
        service = get_service(namespace, project)
        databases = service.list_face_databases()
        return [_face_db_to_response(db) for db in databases]
    except Exception as e:
        logger.exception(f"Failed to list face databases: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/faces/{name}", response_model=FaceDatabaseResponse)
async def get_face_database(
    namespace: str,
    project: str,
    name: str,
) -> FaceDatabaseResponse:
    """Get a face database by name."""
    try:
        service = get_service(namespace, project)
        manifest = service.get_face_database(name)
        return _face_db_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to get face database: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.delete("/faces/{name}", response_model=FaceDatabaseResponse)
async def delete_face_database(
    namespace: str,
    project: str,
    name: str,
) -> FaceDatabaseResponse:
    """Delete a face database."""
    try:
        service = get_service(namespace, project)
        manifest = service.delete_face_database(name)
        return _face_db_to_response(manifest)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to delete face database: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/faces/{name}/register", response_model=FaceIdentityResponse)
async def register_face(
    namespace: str,
    project: str,
    name: str,
    person_id: Annotated[str, Form(description="Person identifier")],
    file: Annotated[UploadFile | None, File(description="Face image")] = None,
    image_base64: Annotated[
        str | None, Form(description="Base64-encoded image")
    ] = None,
    display_name: Annotated[str | None, Form(description="Display name")] = None,
) -> FaceIdentityResponse:
    """Register a face image for a person (multipart form)."""
    try:
        service = get_service(namespace, project)

        if file:
            identity = await service.register_face(
                database=name,
                person_id=person_id,
                file=file,
                display_name=display_name,
            )
        elif image_base64:
            image_data = base64.b64decode(image_base64)
            temp_file = io.BytesIO(image_data)
            upload = UploadFile(file=temp_file, filename="face.jpg")
            identity = await service.register_face(
                database=name,
                person_id=person_id,
                file=upload,
                display_name=display_name,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Must provide file or image_base64"
            )

        return _face_identity_to_response(identity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to register face: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.post("/faces/{name}/register/json", response_model=FaceIdentityResponse)
async def register_face_json(
    namespace: str,
    project: str,
    name: str,
    request: RegisterFaceRequest,
) -> FaceIdentityResponse:
    """Register a face image for a person (JSON body)."""
    try:
        service = get_service(namespace, project)

        image_data = base64.b64decode(request.image_base64)
        temp_file = io.BytesIO(image_data)
        upload = UploadFile(file=temp_file, filename=request.filename)

        identity = await service.register_face(
            database=name,
            person_id=request.person_id,
            file=upload,
            display_name=request.display_name,
        )
        return _face_identity_to_response(identity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to register face: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/faces/{name}/identities", response_model=list[FaceIdentityResponse])
async def list_face_identities(
    namespace: str,
    project: str,
    name: str,
) -> list[FaceIdentityResponse]:
    """List all registered identities in a face database."""
    try:
        service = get_service(namespace, project)
        identities = service.list_face_identities(name)
        return [_face_identity_to_response(i) for i in identities]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to list identities: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/faces/{name}/identities/{person_id}", response_model=FaceIdentityResponse)
async def get_face_identity(
    namespace: str,
    project: str,
    name: str,
    person_id: str,
) -> FaceIdentityResponse:
    """Get a specific face identity."""
    try:
        service = get_service(namespace, project)
        identity = service.get_face_identity(name, person_id)
        return _face_identity_to_response(identity)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to get identity: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.delete(
    "/faces/{name}/identities/{person_id}", response_model=FaceIdentityResponse
)
async def delete_face_identity(
    namespace: str,
    project: str,
    name: str,
    person_id: str,
) -> FaceIdentityResponse:
    """Delete a face identity."""
    try:
        service = get_service(namespace, project)
        identity = service.delete_face_identity(name, person_id)
        return _face_identity_to_response(identity)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to delete identity: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/faces/{name}/db-path")
async def get_face_db_path(
    namespace: str,
    project: str,
    name: str,
) -> dict[str, str]:
    """
    Get the file system path to use for face recognition.

    This path can be passed to the Universal Runtime's /v1/face/search endpoint.
    """
    try:
        service = get_service(namespace, project)
        db_path = service.get_face_db_path(name)
        return {"db_path": str(db_path)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.exception(f"Failed to get db path: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from None


# === Health Check ===


@router.get("/health")
async def vision_training_health() -> dict[str, str]:
    """Check vision training service health."""
    return {"status": "ok", "service": "vision-training"}


# === Response Converters ===


def _training_set_to_response(manifest: TrainingSetManifest) -> TrainingSetResponse:
    """Convert TrainingSetManifest to response."""
    return TrainingSetResponse(
        name=manifest.name,
        task=manifest.task.value,
        classes=manifest.classes,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
        file_count=manifest.file_count,
        splits=manifest.splits,
    )


def _image_metadata_to_response(metadata: ImageMetadata) -> ImageMetadataResponse:
    """Convert ImageMetadata to response."""
    return ImageMetadataResponse(
        hash=metadata.hash,
        original_name=metadata.original_name,
        extension=metadata.extension,
        split=metadata.split.value,
        timestamp=metadata.timestamp,
        size=metadata.size,
        mime_type=metadata.mime_type,
        width=metadata.width,
        height=metadata.height,
        labels_hash=metadata.labels_hash,
    )


def _model_version_to_response(manifest: ModelManifest) -> ModelVersionResponse:
    """Convert ModelManifest to response."""
    return ModelVersionResponse(
        version=manifest.version,
        name=manifest.name,
        task=manifest.task.value,
        base_model=manifest.base_model,
        created_at=manifest.created_at,
        training_set=manifest.training_set,
        metrics=manifest.metrics,
        tags=manifest.tags,
    )


def _face_db_to_response(manifest: FaceDatabaseManifest) -> FaceDatabaseResponse:
    """Convert FaceDatabaseManifest to response."""
    return FaceDatabaseResponse(
        name=manifest.name,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
        detector_backend=manifest.detector_backend,
        recognition_model=manifest.recognition_model,
        total_identities=manifest.total_identities,
        total_images=manifest.total_images,
    )


def _face_identity_to_response(identity: FaceIdentity) -> FaceIdentityResponse:
    """Convert FaceIdentity to response."""
    return FaceIdentityResponse(
        person_id=identity.person_id,
        display_name=identity.display_name,
        created_at=identity.created_at,
        updated_at=identity.updated_at,
        image_count=identity.image_count,
        image_hashes=identity.image_hashes,
    )
