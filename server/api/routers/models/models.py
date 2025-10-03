"""Model management endpoints for LlamaFarm.

This module provides unified model management across all providers
(Ollama, Lemonade, etc.) configured in a project.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.project_service import ProjectService
from services.providers import get_provider
from services.model_management_provider import ModelInfo

router = APIRouter(
    prefix="/models",
    tags=["models"],
)


class PullModelRequest(BaseModel):
    """Request to pull/download a model."""

    model_name: str
    provider: str  # Which provider to pull from
    # Optional provider-specific parameters
    checkpoint: str | None = None  # For Lemonade custom models (e.g., "google/gemma-3-4b-it-qat-q4_0-gguf")
    variant: str | None = None  # For Lemonade GGUF models (e.g., "Q4_0", "Q8_0") - appended to checkpoint
    recipe: str | None = None  # For Lemonade (llamacpp, transformers, etc.)
    vision: bool = False  # For Lemonade vision models
    reasoning: bool = False  # For Lemonade reasoning models
    mmproj: str | None = None  # For Lemonade vision models
    insecure: bool = False  # For Ollama insecure connections


class DeleteModelRequest(BaseModel):
    """Request to delete a model."""

    model_name: str
    provider: str


class CopyModelRequest(BaseModel):
    """Request to copy a model."""

    source: str
    destination: str
    provider: str


class ShowModelRequest(BaseModel):
    """Request to show model details."""

    model_name: str
    provider: str


@router.get("/{namespace}/{project_id}/models")
async def list_all_models(namespace: str, project_id: str):
    """List all models from all providers configured in the project.

    Returns models from:
    - Ollama (if configured)
    - Lemonade (if configured)
    - Other providers as they're added

    Response includes provider information for each model.
    """
    project_config = ProjectService.load_config(namespace, project_id)

    if not project_config or not project_config.runtime.models:
        return {"models": []}

    all_models = []
    seen_providers = set()

    # Iterate through configured models to find unique providers
    for model_config in project_config.runtime.models:
        provider_name = model_config.provider.value
        if provider_name in seen_providers:
            continue

        seen_providers.add(provider_name)

        # Get provider-specific base URL
        if provider_name == "ollama":
            base_url = model_config.base_url or "http://localhost:11434"
        elif provider_name == "lemonade":
            port = model_config.lemonade.port if model_config.lemonade else 11534
            base_url = f"http://localhost:{port}"
        else:
            continue  # Skip unsupported providers

        try:
            provider = get_provider(provider_name, base_url.rstrip("/v1"))
            models = await provider.list_models()
            all_models.extend([m.dict() for m in models])
        except Exception as e:
            # Log error but continue with other providers
            print(f"Error listing models from {provider_name}: {e}")
            continue

    return {"models": all_models}


@router.post("/{namespace}/{project_id}/models/pull")
async def pull_model(
    namespace: str,
    project_id: str,
    request: PullModelRequest
):
    """Pull/download a model from the specified provider.

    This endpoint supports streaming progress updates.

    For Ollama:
    - model_name: "llama3:70b"
    - insecure: optional

    For Lemonade:
    - model_name: "Qwen2.5-VL-7B-Instruct-GGUF" (registered)
    - OR model_name: "user.CustomModel" with:
      - checkpoint: "google/gemma-3-4b-it-qat-q4_0-gguf" (HuggingFace repo)
      - variant: "Q4_0" (quantization variant for GGUF models)
      - recipe: "llamacpp" (optional, defaults to llamacpp for GGUF)
    """
    project_config = ProjectService.load_config(namespace, project_id)

    # Find provider config
    provider_config = None
    for model_config in project_config.runtime.models:
        if model_config.provider.value == request.provider:
            provider_config = model_config
            break

    if not provider_config:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{request.provider}' not configured in project"
        )

    # Get base URL
    if request.provider == "ollama":
        base_url = provider_config.base_url or "http://localhost:11434"
    elif request.provider == "lemonade":
        port = provider_config.lemonade.port if provider_config.lemonade else 11534
        base_url = f"http://localhost:{port}"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {request.provider}"
        )

    # Create provider instance
    provider = get_provider(request.provider, base_url.rstrip("/v1"))

    # Build provider-specific options
    options = {}
    if request.provider == "ollama":
        if request.insecure:
            options["insecure"] = True
    elif request.provider == "lemonade":
        if request.checkpoint:
            options["checkpoint"] = request.checkpoint
        if request.variant:
            options["variant"] = request.variant
        if request.recipe:
            options["recipe"] = request.recipe
        if request.vision:
            options["vision"] = True
        if request.reasoning:
            options["reasoning"] = True
        if request.mmproj:
            options["mmproj"] = request.mmproj

    # Stream progress
    async def progress_stream():
        """Stream pull progress as JSON lines."""
        async for progress in provider.pull_model(request.model_name, **options):
            import json
            yield json.dumps(progress.dict()) + "\n"

    return StreamingResponse(
        progress_stream(),
        media_type="application/x-ndjson"
    )


@router.delete("/{namespace}/{project_id}/models/delete")
async def delete_model(
    namespace: str,
    project_id: str,
    request: DeleteModelRequest
):
    """Delete a model from the specified provider."""
    project_config = ProjectService.load_config(namespace, project_id)

    # Find provider config
    provider_config = None
    for model_config in project_config.runtime.models:
        if model_config.provider.value == request.provider:
            provider_config = model_config
            break

    if not provider_config:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{request.provider}' not configured in project"
        )

    # Get base URL
    if request.provider == "ollama":
        base_url = provider_config.base_url or "http://localhost:11434"
    elif request.provider == "lemonade":
        port = provider_config.lemonade.port if provider_config.lemonade else 11534
        base_url = f"http://localhost:{port}"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {request.provider}"
        )

    provider = get_provider(request.provider, base_url.rstrip("/v1"))
    success = await provider.delete_model(request.model_name)

    if success:
        return {"message": f"Model '{request.model_name}' deleted successfully"}
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete model '{request.model_name}'"
        )


@router.post("/{namespace}/{project_id}/models/show")
async def show_model(
    namespace: str,
    project_id: str,
    request: ShowModelRequest
):
    """Get detailed information about a specific model."""
    project_config = ProjectService.load_config(namespace, project_id)

    # Find provider config
    provider_config = None
    for model_config in project_config.runtime.models:
        if model_config.provider.value == request.provider:
            provider_config = model_config
            break

    if not provider_config:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{request.provider}' not configured in project"
        )

    # Get base URL
    if request.provider == "ollama":
        base_url = provider_config.base_url or "http://localhost:11434"
    elif request.provider == "lemonade":
        port = provider_config.lemonade.port if provider_config.lemonade else 11534
        base_url = f"http://localhost:{port}"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {request.provider}"
        )

    provider = get_provider(request.provider, base_url.rstrip("/v1"))
    model_info = await provider.show_model(request.model_name)

    return model_info


@router.post("/{namespace}/{project_id}/models/copy")
async def copy_model(
    namespace: str,
    project_id: str,
    request: CopyModelRequest
):
    """Copy a model to a new name (Ollama only)."""
    if request.provider != "ollama":
        raise HTTPException(
            status_code=400,
            detail="Model copying is only supported for Ollama provider"
        )

    project_config = ProjectService.load_config(namespace, project_id)

    # Find Ollama config
    provider_config = None
    for model_config in project_config.runtime.models:
        if model_config.provider.value == "ollama":
            provider_config = model_config
            break

    if not provider_config:
        raise HTTPException(
            status_code=404,
            detail="Ollama not configured in project"
        )

    base_url = provider_config.base_url or "http://localhost:11434"
    provider = get_provider("ollama", base_url.rstrip("/v1"))

    success = await provider.copy_model(request.source, request.destination)

    if success:
        return {
            "message": f"Model copied from '{request.source}' to '{request.destination}'"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to copy model"
        )
