import builtins
import contextlib
import shutil
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import celery.result  # type: ignore
import httpx
from atomic_agents import AtomicAgent  # type: ignore
from fastapi import APIRouter, Header, HTTPException, Response
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from agents.project_chat_orchestrator import ProjectChatOrchestratorAgentFactory
from api.errors import ErrorResponse
from api.routers.inference.models import ChatRequest

# RAG imports moved to function level to avoid circular imports
from api.routers.shared.response_utils import (
    create_streaming_response_from_iterator,
    set_session_header,
)
from core.celery import app
from core.settings import settings
from services.project_chat_service import (
    FALLBACK_ECHO_RESPONSE,
    project_chat_service,
)
from services.project_service import ProjectService
from services.docs_context_service import get_docs_service

repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))
from config.datamodel import LlamaFarmConfig  # noqa: E402


class Project(BaseModel):
    namespace: str
    name: str
    config: LlamaFarmConfig


class ListProjectsResponse(BaseModel):
    total: int
    projects: list[Project]


class CreateProjectRequest(BaseModel):
    name: str
    config_template: str | None = None


class CreateProjectResponse(BaseModel):
    project: Project


class GetProjectResponse(BaseModel):
    project: Project


class DeleteProjectResponse(BaseModel):
    project: Project


class UpdateProjectRequest(BaseModel):
    # Full replacement update of the project's configuration
    config: LlamaFarmConfig


class UpdateProjectResponse(BaseModel):
    project: Project


router = APIRouter(
    prefix="/projects",
    tags=["projects"],
)


@router.get(
    "/{namespace}",
    response_model=ListProjectsResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_projects(namespace: str):
    projects = ProjectService.list_projects(namespace)
    return ListProjectsResponse(
        total=len(projects),
        projects=[
            Project(
                namespace=namespace,
                name=project.name,
                config=project.config,
            )
            for project in projects
        ],
    )


@router.post(
    "/{namespace}",
    response_model=CreateProjectResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_project(namespace: str, request: CreateProjectRequest):
    cfg = ProjectService.create_project(
        namespace, request.name, request.config_template
    )
    return CreateProjectResponse(
        project=Project(
            namespace=namespace,
            name=request.name,
            config=cfg,
        ),
    )


@router.get(
    "/{namespace}/{project_id}",
    response_model=GetProjectResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_project(namespace: str, project_id: str):
    project = ProjectService.get_project(namespace, project_id)
    return GetProjectResponse(
        project=Project(
            namespace=project.namespace,
            name=project.name,
            config=project.config,
        ),
    )


@router.put(
    "/{namespace}/{project_id}",
    response_model=UpdateProjectResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_project(
    namespace: str,
    project_id: str,
    request: UpdateProjectRequest,
):
    updated_config = ProjectService.update_project(
        namespace,
        project_id,
        request.config,
    )
    return UpdateProjectResponse(
        project=Project(
            namespace=namespace,
            name=project_id,
            config=updated_config,
        )
    )


@router.delete(
    "/{namespace}/{project_id}",
    response_model=DeleteProjectResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_project(namespace: str, project_id: str):
    # TODO: Implement actual delete in ProjectService; placeholder response for now
    project = Project(
        namespace=namespace,
        name=project_id,
        config=ProjectService.load_config(namespace, project_id),
    )
    return DeleteProjectResponse(
        project=project,
    )


SESSION_TTL_SECONDS = 30 * 60


@dataclass
class SessionRecord:
    namespace: str
    project_id: str
    agent: AtomicAgent
    created_at: float
    last_used: float
    request_count: int


agent_sessions: builtins.dict[str, SessionRecord] = {}
_agent_sessions_lock = threading.RLock()


def _session_key(namespace: str, project_id: str, session_id: str) -> str:
    return f"{namespace}:{project_id}:{session_id}"


def _cleanup_expired_sessions(now: float | None = None) -> None:
    timestamp = now or time.time()
    to_delete: list[str] = []
    for key, record in agent_sessions.items():
        if timestamp - record.last_used > SESSION_TTL_SECONDS:
            to_delete.append(key)
    for key in to_delete:
        agent_sessions.pop(key, None)


def _delete_session(namespace: str, project_id: str, session_id: str) -> bool:
    key = _session_key(namespace, project_id, session_id)
    record = agent_sessions.pop(key, None)
    if record is None:
        return False
    if hasattr(record.agent, "reset_history"):
        with contextlib.suppress(Exception):
            record.agent.reset_history()
    return True


def _delete_all_sessions(namespace: str, project_id: str) -> int:
    to_delete = [
        key
        for key, record in agent_sessions.items()
        if record.namespace == namespace and record.project_id == project_id
    ]
    for key in to_delete:
        record = agent_sessions.pop(key, None)
        if record and hasattr(record.agent, "reset_history"):
            with contextlib.suppress(Exception):
                record.agent.reset_history()
    return len(to_delete)


def has_vision_content(messages: list) -> bool:
    """Check if any message contains image content."""
    for msg in messages:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for part in msg.content:
                if (hasattr(part, 'type') and part.type == "image_url") or \
                   (isinstance(part, dict) and part.get('type') == 'image_url'):
                    return True
    return False


async def handle_vision_request(
    request: ChatRequest,
    model_config,
    project_config,
    project_dir: str,
) -> ChatCompletion:
    """Handle vision requests by calling the provider directly."""
    from services.model_service import ModelService
    from openai.types.chat import ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice

    # Build provider URL based on config
    if model_config.provider.value == "lemonade":
        port = model_config.lemonade.port if model_config.lemonade else 8000
        provider_url = f"http://localhost:{port}/api/v1/chat/completions"
    elif model_config.provider.value == "ollama":
        base_url = model_config.base_url or "http://localhost:11434"
        provider_url = f"{base_url}/api/chat"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Vision not supported for provider: {model_config.provider.value}"
        )

    # Get vision config for image optimization
    vision_cfg = getattr(model_config, 'vision_config', None)

    # Image resize settings (server-side optimization)
    resize_enabled = True  # Default enabled
    max_dimension = 768    # Default
    max_size_kb = 500      # Default

    if vision_cfg:
        resize_enabled = getattr(vision_cfg, 'resize_images', True)
        if resize_enabled is None:
            resize_enabled = True
        max_dimension = getattr(vision_cfg, 'max_dimension', 768) or 768
        max_size_kb = getattr(vision_cfg, 'max_image_size_kb', 500) or 500

    # Import resize utility
    from utils.image_utils import resize_base64_image

    # Prepare messages for provider
    provider_messages = []
    for msg in request.messages:
        provider_msg = {"role": msg.role}

        if isinstance(msg.content, str):
            provider_msg["content"] = msg.content
        elif isinstance(msg.content, list):
            # Convert to provider format
            provider_content = []
            for part in msg.content:
                if hasattr(part, 'type'):
                    if part.type == "text":
                        provider_content.append({"type": "text", "text": part.text})
                    elif part.type == "image_url":
                        # Resize image if enabled in config
                        image_url = part.image_url.url
                        if resize_enabled and image_url.startswith("data:"):
                            image_url, was_resized = resize_base64_image(
                                image_url,
                                max_dimension=max_dimension,
                                max_size_kb=max_size_kb
                            )

                        provider_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        })
                elif isinstance(part, dict):
                    provider_content.append(part)
            provider_msg["content"] = provider_content

        provider_messages.append(provider_msg)

    # Call provider directly
    # Use vision_config parameters if available, otherwise use defaults
    max_tokens = 512
    temperature = 0.1

    if vision_cfg:
        max_tokens = getattr(vision_cfg, 'max_tokens', 512) or 512
        temperature = getattr(vision_cfg, 'temperature', 0.1) or 0.1

    request_params = {
        "model": model_config.model,
        "messages": provider_messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    # Lemonade-specific optimizations
    if model_config.provider.value == "lemonade":
        request_params.update({
            "top_p": 0.9,
        })

    # Use longer timeout for vision models (can take 2-5 minutes for detailed analysis)
    # Get timeout from vision_config or use default
    timeout_seconds = 300.0  # 5 minutes default
    if vision_cfg and hasattr(vision_cfg, 'timeout'):
        timeout_seconds = getattr(vision_cfg, 'timeout', 300.0) or 300.0

    # Log start of vision processing for user visibility
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Vision request starting: model={model_config.model}, max_tokens={max_tokens}, timeout={timeout_seconds}s, resize={resize_enabled}")

    # Log the actual image details being sent
    for i, msg in enumerate(provider_messages):
        if isinstance(msg.get('content'), list):
            for j, part in enumerate(msg['content']):
                if isinstance(part, dict) and part.get('type') == 'image_url':
                    img_url = part.get('image_url', {})
                    # Log first 100 chars of base64 to verify image is present
                    url_preview = img_url.get('url', '')[:100]
                    logger.info(f"Image {j+1} in message {i+1}: url_prefix={url_preview}")

    # Create timeout config for httpx (needs all timeout types set)
    timeout_config = httpx.Timeout(
        connect=30.0,              # 30s to connect
        read=timeout_seconds,      # Main timeout for reading response
        write=30.0,                # 30s to write request
        pool=30.0                  # 30s for pool operations
    )

    async with httpx.AsyncClient(timeout=timeout_config) as client:
        response = await client.post(
            provider_url,
            json=request_params
        )

        logger.info(f"Vision request completed: status={response.status_code}, response_time={response.elapsed.total_seconds():.2f}s")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Provider error: {response.text}"
            )

        result = response.json()

        # Debug logging
        logger.info(f"Vision response received: status={response.status_code}, result_keys={list(result.keys())}")
        logger.info(f"Vision response content: {result.get('choices', [{}])[0].get('message', {}).get('content', 'NO CONTENT')[:200]}")

        # Convert provider response to OpenAI format
        if model_config.provider.value == "lemonade":
            # Lemonade returns OpenAI-compatible format
            completion = ChatCompletion(**result)
            logger.info(f"Vision completion created: choices={len(completion.choices)}, first_content={completion.choices[0].message.content[:100] if completion.choices else 'NO CHOICES'}")
            return completion
        else:
            # Handle other providers
            content = result.get("message", {}).get("content", "")
            return ChatCompletion(
                id=f"chat-{uuid.uuid4()}",
                object="chat.completion",
                created=int(time.time()),
                model=model_config.model,
                choices=[
                    Choice(
                        index=0,
                        message=ChatCompletionMessage(
                            role="assistant",
                            content=content,
                        ),
                        finish_reason="stop",
                    )
                ],
            )


@router.post(
    "/{namespace}/{project_id}/chat/completions", response_model=ChatCompletion
)
async def chat(
    request: ChatRequest,
    namespace: str,
    project_id: str,
    response: Response,
    session_id: str | None = Header(None, alias="X-Session-ID"),
    x_no_session: str | None = Header(None, alias="X-No-Session"),
):
    """Send a message to the chat agent"""
    project_dir = ProjectService.get_project_dir(namespace, project_id)
    project_config = ProjectService.load_config(namespace, project_id)

    # Get model config to check for vision support
    from services.model_service import ModelService
    model_config = ModelService.get_model_config(project_config, request.model)

    # Check if this is a vision request (has images) AND model supports vision
    if has_vision_content(request.messages):
        # Vision request detected - use direct provider call
        prompt_format = getattr(model_config, 'prompt_format', None)
        # Handle both string and enum values
        prompt_format_str = prompt_format.value if hasattr(prompt_format, 'value') else prompt_format
        vision_enabled = getattr(model_config, 'vision', False)

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Vision request detected. Model: {request.model}, prompt_format: {prompt_format_str}, vision: {vision_enabled}")

        if prompt_format_str == 'image' or vision_enabled:
            completion = await handle_vision_request(
                request=request,
                model_config=model_config,
                project_config=project_config,
                project_dir=project_dir,
            )
            # Set session header if needed
            if not x_no_session and session_id:
                set_session_header(response, session_id)
            elif not x_no_session:
                new_session_id = str(uuid.uuid4())
                set_session_header(response, new_session_id)

            # If streaming requested, convert to SSE format
            if request.stream:
                from fastapi.responses import StreamingResponse
                import json

                async def vision_stream():
                    # Send the complete message as a single chunk
                    if completion.choices:
                        content = completion.choices[0].message.content
                        chunk_data = {
                            "id": completion.id,
                            "object": "chat.completion.chunk",
                            "created": completion.created,
                            "model": completion.model,
                            "choices": [{
                                "index": 0,
                                "delta": {"role": "assistant", "content": content},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"

                        # Send final chunk with finish_reason
                        final_chunk = {
                            "id": completion.id,
                            "object": "chat.completion.chunk",
                            "created": completion.created,
                            "model": completion.model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop"
                            }]
                        }
                        yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    vision_stream(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    }
                )
            else:
                return completion
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{request.model or 'default'}' does not support vision. Set prompt_format='image' or vision=true in config."
            )

    now = time.time()
    stateless = x_no_session is not None

    if stateless:
        # Stateless mode: create throwaway agent without session or persistence
        agent = ProjectChatOrchestratorAgentFactory.create_agent(
            project_config, project_dir=project_dir, model_name=request.model
        )
    else:
        # Stateful mode: use or create cached agent with disk-persisted history
        if not session_id:
            session_id = str(uuid.uuid4())

        key = _session_key(namespace, project_id, session_id)
        with _agent_sessions_lock:
            # Clean up expired sessions before checking cache
            _cleanup_expired_sessions(now)

            record = agent_sessions.get(key)
            if record is not None and (now - record.last_used > SESSION_TTL_SECONDS):
                # Session expired, remove it and create fresh
                agent_sessions.pop(key, None)
                record = None

            if record is None:
                # Create new agent and enable persistence
                agent = ProjectChatOrchestratorAgentFactory.create_agent(
                    project_config, project_dir=project_dir, model_name=request.model
                )
                agent.enable_persistence(session_id=session_id)
                # Cache the agent in memory
                agent_sessions[key] = SessionRecord(
                    namespace=namespace,
                    project_id=project_id,
                    agent=agent,
                    created_at=now,
                    last_used=now,
                    request_count=1,
                )
            else:
                # Reuse cached agent and update stats
                record.last_used = now
                record.request_count += 1
                agent = record.agent

        set_session_header(response, session_id)

    # Extract the latest user message
    latest_user_message = None
    for msg in reversed(request.messages):
        if msg.role == "user" and msg.content:
            # Handle both string and multimodal (list) content
            if isinstance(msg.content, str):
                latest_user_message = msg.content
            elif isinstance(msg.content, list):
                # For multimodal content, extract text parts
                text_parts = []
                for part in msg.content:
                    if hasattr(part, 'type') and part.type == "text":
                        text_parts.append(part.text)
                    elif isinstance(part, dict) and part.get('type') == 'text':
                        text_parts.append(part.get('text', ''))
                latest_user_message = ' '.join(text_parts) if text_parts else None
            break

    # If no user message, check if this is a greeting request (new session)
    if latest_user_message is None:
        # For new sessions on project_seed, return the greeting from history
        if project_id == "project_seed" and hasattr(agent, 'history'):
            history_messages = list(agent.history.get_history())
            # Look for the greeting message (last assistant message if it exists)
            for msg in reversed(history_messages):
                role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
                if role == "assistant":
                    content_obj = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
                    content = None
                    if isinstance(content_obj, dict):
                        content = content_obj.get("chat_message")
                    elif hasattr(content_obj, "chat_message"):
                        content = getattr(content_obj, "chat_message", None)
                    elif isinstance(content_obj, str):
                        content = content_obj

                    if content and "Welcome" in content:
                        # Return the greeting as a chat completion
                        from openai.types.chat import ChatCompletionMessage
                        from openai.types.chat.chat_completion import Choice
                        from services.model_service import ModelService

                        # Get the actual model name being used
                        model_config = ModelService.get_model_config(project_config, request.model)

                        return ChatCompletion(
                            id=f"chat-{uuid.uuid4()}",
                            object="chat.completion",
                            created=int(time.time()),
                            model=model_config.model,
                            choices=[
                                Choice(
                                    index=0,
                                    message=ChatCompletionMessage(
                                        role="assistant",
                                        content=content,
                                    ),
                                    finish_reason="stop",
                                )
                            ],
                        )

        raise HTTPException(status_code=400, detail="No user message provided")  # noqa: F821

    # Inject relevant documentation based on user query (dev mode only)
    if settings.lf_dev_mode_docs_enabled and project_id == "project_seed" and hasattr(agent, "docs_context_provider"):
        docs_service = get_docs_service()
        matched_docs = docs_service.match_docs_for_query(latest_user_message)
        agent.docs_context_provider.set_docs(matched_docs)

    if request.stream:
        return create_streaming_response_from_iterator(
            request,
            project_chat_service.stream_chat(
                project_dir=project_dir,
                project_config=project_config,
                chat_agent=agent,
                message=latest_user_message,
                rag_enabled=request.rag_enabled,
                database=request.database,
                rag_top_k=request.rag_top_k,
                rag_score_threshold=request.rag_score_threshold,
            ),
            session_id if not stateless else "",
            default_message=FALLBACK_ECHO_RESPONSE,
        )

    try:
        # For vision messages, we need to pass the full multimodal content
        # Currently the agent only supports text, so we extract text for now
        # TODO: Refactor agent to support multimodal messages natively
        completion = await project_chat_service.chat(
            project_dir=project_dir,
            project_config=project_config,
            chat_agent=agent,
            message=latest_user_message or "",  # Ensure we have a string
            rag_enabled=request.rag_enabled,
            database=request.database,
            rag_top_k=request.rag_top_k,
            rag_score_threshold=request.rag_score_threshold,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Chat service failed to generate a response: {e}",
        ) from e

    if not stateless:
        set_session_header(response, session_id)
    return completion


@router.post(
    "/{namespace}/{project_id}/rag/query",
    responses={
        404: {"model": ErrorResponse, "description": "Database or strategy not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def rag_query(
    namespace: str,
    project_id: str,
    request: dict,  # Using dict to avoid circular import, will validate inside function
):
    """Perform a RAG query on the project's configured databases."""
    # Import here to avoid circular import
    from api.routers.rag.rag_query import QueryRequest, handle_rag_query

    # Validate request
    request = QueryRequest(**request)
    # Get project configuration
    project_service = ProjectService()
    project_dir = project_service.get_project_dir(namespace, project_id)

    if not Path(project_dir).exists():
        raise HTTPException(
            status_code=404, detail=f"Project {namespace}/{project_id} not found"
        )

    project_config = ProjectService.load_config(namespace, project_id)

    if not project_config:
        raise HTTPException(
            status_code=500, detail="Failed to load project configuration"
        )

    # Handle the RAG query
    response = await handle_rag_query(request, project_config, str(project_dir))

    return response


@router.get("/{namespace}/{project_id}/tasks/{task_id}")
async def get_task(namespace: str, project_id: str, task_id: str):
    """Return state, progress meta, and result/error if available."""
    res: celery.result.AsyncResult = app.AsyncResult(task_id)

    payload = {
        "task_id": task_id,
        "state": res.state,
        "meta": None,
        "result": None,
        "error": None,
        "traceback": None,
    }

    if res.info:
        payload["meta"] = res.info

    if res.state == "SUCCESS":
        payload["result"] = res.result
    elif res.state == "FAILURE":
        payload["error"] = str(res.result)
        payload["traceback"] = res.traceback

    return payload


@router.get(
    "/{namespace}/{project_id}/chat/sessions/{session_id}/history",
    responses={
        200: {"model": dict},
        404: {"model": ErrorResponse},
    },
)
async def get_chat_session_history(namespace: str, project_id: str, session_id: str):
    """Retrieve the chat history for a specific session."""
    try:
        project_dir = ProjectService.get_project_dir(namespace, project_id)
        history_file = Path(project_dir) / "sessions" / session_id / "history.json"

        if not history_file.exists():
            return {"messages": []}

        import json

        with open(history_file, encoding="utf-8") as f:
            data = json.load(f)

        return {"messages": data if isinstance(data, list) else []}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load session history: {e}"
        ) from e


@router.delete(
    "/{namespace}/{project_id}/chat/sessions/{session_id}",
    responses={
        200: {"model": dict},
        404: {"model": ErrorResponse},
    },
)
async def delete_chat_session(namespace: str, project_id: str, session_id: str):
    # Delete in-memory record if present
    with _agent_sessions_lock:
        _delete_session(namespace, project_id, session_id)
    # Delete on-disk history directory
    with contextlib.suppress(Exception):
        project_dir = ProjectService.get_project_dir(namespace, project_id)
        sessions_dir = Path(project_dir) / "sessions" / session_id
        if sessions_dir.exists():
            shutil.rmtree(sessions_dir, ignore_errors=True)
    return {"message": f"Session {session_id} deleted"}


@router.delete(
    "/{namespace}/{project_id}/chat/sessions",
    responses={200: {"model": dict}},
)
async def delete_all_chat_sessions(namespace: str, project_id: str):
    with _agent_sessions_lock:
        count = _delete_all_sessions(namespace, project_id)
    return {"message": f"Deleted {count} session(s)", "count": count}


@router.get(
    "/{namespace}/{project_id}/models",
    responses={
        200: {"model": dict},
        404: {"model": ErrorResponse},
    },
)
async def list_models(namespace: str, project_id: str):
    """List all available models for this project."""
    from services.model_service import ModelService

    project_config = ProjectService.load_config(namespace, project_id)
    models = ModelService.list_models(project_config)
    return {"models": models}
