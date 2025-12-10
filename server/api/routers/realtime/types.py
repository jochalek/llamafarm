"""
Type definitions for the Realtime WebSocket API.

Extends the Universal Runtime realtime protocol with LlamaFarm-specific
features: RAG integration, project-based configuration, multi-model support.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """WebSocket message types."""

    # Client -> Server
    SESSION_UPDATE = "session.update"
    INPUT_TEXT_APPEND = "input_text.append"
    INPUT_TEXT_COMMIT = "input_text.commit"
    INPUT_TEXT_CLEAR = "input_text.clear"
    RESPONSE_CANCEL = "response.cancel"
    CONVERSATION_CLEAR = "conversation.clear"
    RAG_PREVIEW = "rag.preview"  # Request RAG preview for current buffer

    # Server -> Client
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    INPUT_TEXT_COMMITTED = "input_text.committed"
    INPUT_TEXT_CLEARED = "input_text.cleared"
    CONVERSATION_CLEARED = "conversation.cleared"
    RAG_CONTEXT_ADDED = "rag.context_added"
    RAG_PREVIEW_RESULT = "rag.preview_result"  # RAG preview results
    RAG_PREVIEW_SEARCHING = "rag.preview_searching"  # RAG search in progress
    RESPONSE_TEXT_DELTA = "response.text.delta"
    RESPONSE_TEXT_DONE = "response.text.done"
    RESPONSE_DONE = "response.done"
    RESPONSE_CANCELLED = "response.cancelled"
    ERROR = "error"


class RAGConfig(BaseModel):
    """RAG configuration for the session."""

    enabled: bool = Field(default=False, description="Enable RAG retrieval")
    database: str | None = Field(default=None, description="Database name for RAG")
    retrieval_strategy: str | None = Field(
        default=None, description="Retrieval strategy (hybrid, semantic, keyword)"
    )
    top_k: int | None = Field(default=None, description="Number of chunks to retrieve")
    score_threshold: float | None = Field(
        default=None, description="Minimum score threshold for chunks"
    )
    queries: list[str] | None = Field(
        default=None,
        description="Custom queries for RAG (overrides using user message)",
    )


class SessionConfig(BaseModel):
    """Session configuration for LlamaFarm realtime chat."""

    # Model selection (uses project's configured models)
    model: str | None = Field(
        default=None, description="Model name from project config (null = default)"
    )

    # Generation parameters
    temperature: float | None = Field(default=None, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, description="Max tokens to generate")
    top_p: float | None = Field(default=None, description="Nucleus sampling threshold")
    stop: list[str] | None = Field(default=None, description="Stop sequences")

    # GGUF-specific
    n_ctx: int | None = Field(default=None, description="Context window size for GGUF")

    # Thinking mode (Qwen models)
    think: bool | None = Field(default=None, description="Enable thinking mode")
    thinking_budget: int | None = Field(
        default=None, description="Max tokens for thinking"
    )

    # RAG configuration
    rag: RAGConfig = Field(default_factory=RAGConfig, description="RAG configuration")


class SessionUpdateMessage(BaseModel):
    """Client message to update session configuration."""

    type: Literal["session.update"] = "session.update"
    session: SessionConfig


class InputTextAppendMessage(BaseModel):
    """Client message to append text to input buffer."""

    type: Literal["input_text.append"] = "input_text.append"
    text: str


class InputTextCommitMessage(BaseModel):
    """Client message to commit input buffer and start generation."""

    type: Literal["input_text.commit"] = "input_text.commit"


class InputTextClearMessage(BaseModel):
    """Client message to clear input buffer."""

    type: Literal["input_text.clear"] = "input_text.clear"


class ResponseCancelMessage(BaseModel):
    """Client message to cancel in-progress generation."""

    type: Literal["response.cancel"] = "response.cancel"


class ConversationClearMessage(BaseModel):
    """Client message to clear conversation history."""

    type: Literal["conversation.clear"] = "conversation.clear"


class RAGPreviewMessage(BaseModel):
    """Client message to request RAG preview for current input buffer.

    Triggers a RAG search using the current input buffer text.
    Results are cached and reused when input is committed.
    """

    type: Literal["rag.preview"] = "rag.preview"


# Server -> Client messages


class SessionCreatedMessage(BaseModel):
    """Server message when session is created."""

    type: Literal["session.created"] = "session.created"
    session_id: str
    session: SessionConfig
    project: dict = Field(
        default_factory=dict, description="Project info (namespace, name)"
    )
    available_models: list[str] = Field(
        default_factory=list, description="Available model names from project config"
    )


class SessionUpdatedMessage(BaseModel):
    """Server message when session is updated."""

    type: Literal["session.updated"] = "session.updated"
    session: SessionConfig


class InputTextCommittedMessage(BaseModel):
    """Server message when input is committed."""

    type: Literal["input_text.committed"] = "input_text.committed"
    text: str
    item_id: str


class InputTextClearedMessage(BaseModel):
    """Server message when input buffer is cleared."""

    type: Literal["input_text.cleared"] = "input_text.cleared"


class ConversationClearedMessage(BaseModel):
    """Server message when conversation is cleared."""

    type: Literal["conversation.cleared"] = "conversation.cleared"


class RAGContextAddedMessage(BaseModel):
    """Server message when RAG context is retrieved."""

    type: Literal["rag.context_added"] = "rag.context_added"
    item_id: str
    chunks_count: int
    database: str | None
    retrieval_strategy: str | None


class RAGChunkPreview(BaseModel):
    """Preview of a single RAG chunk."""

    content: str = Field(description="Truncated chunk content (first ~200 chars)")
    score: float | None = Field(default=None, description="Relevance score")
    source: str | None = Field(default=None, description="Source document name")


class RAGPreviewSearchingMessage(BaseModel):
    """Server message indicating RAG search is in progress."""

    type: Literal["rag.preview_searching"] = "rag.preview_searching"
    query: str = Field(description="The query being searched")


class RAGPreviewResultMessage(BaseModel):
    """Server message with RAG preview results.

    Sent in response to rag.preview request. Contains chunk previews
    that show what context will be used when the user commits.
    """

    type: Literal["rag.preview_result"] = "rag.preview_result"
    query: str = Field(description="The query that was searched")
    chunks_count: int = Field(description="Total chunks found")
    chunks: list[RAGChunkPreview] = Field(
        default_factory=list, description="Preview of top chunks"
    )
    database: str | None = Field(default=None, description="Database searched")
    retrieval_strategy: str | None = Field(default=None, description="Strategy used")
    cached: bool = Field(
        default=False,
        description="Whether these results will be reused on commit",
    )


class ResponseTextDeltaMessage(BaseModel):
    """Server message with streaming text delta."""

    type: Literal["response.text.delta"] = "response.text.delta"
    item_id: str
    delta: str


class ResponseTextDoneMessage(BaseModel):
    """Server message when text generation for an item is complete."""

    type: Literal["response.text.done"] = "response.text.done"
    item_id: str
    text: str


class ResponseDoneMessage(BaseModel):
    """Server message when full response is complete."""

    type: Literal["response.done"] = "response.done"
    item_id: str


class ResponseCancelledMessage(BaseModel):
    """Server message when response was cancelled."""

    type: Literal["response.cancelled"] = "response.cancelled"
    item_id: str
    partial_text: str


class ErrorMessage(BaseModel):
    """Server error message."""

    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict | None = None
