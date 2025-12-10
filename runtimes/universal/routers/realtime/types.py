"""
Type definitions for the Realtime WebSocket API.

Inspired by OpenAI's Realtime API, adapted for text-only LLM chat.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class MessageType(str, Enum):
    """WebSocket message types."""

    # Client -> Server
    SESSION_UPDATE = "session.update"
    INPUT_TEXT_APPEND = "input_text.append"
    INPUT_TEXT_COMMIT = "input_text.commit"
    INPUT_TEXT_CLEAR = "input_text.clear"
    RESPONSE_CANCEL = "response.cancel"

    # Server -> Client
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    INPUT_TEXT_COMMITTED = "input_text.committed"
    INPUT_TEXT_CLEARED = "input_text.cleared"
    RESPONSE_TEXT_DELTA = "response.text.delta"
    RESPONSE_TEXT_DONE = "response.text.done"
    RESPONSE_DONE = "response.done"
    RESPONSE_CANCELLED = "response.cancelled"
    ERROR = "error"


class SessionConfig(BaseModel):
    """Session configuration."""

    model: str = "unsloth/Qwen3-0.6B-GGUF"
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 1.0
    n_ctx: int | None = None
    system_prompt: str | None = None
    stop: list[str] | None = None
    think: bool = False
    thinking_budget: int | None = None


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


# Server -> Client messages


class SessionCreatedMessage(BaseModel):
    """Server message when session is created."""

    type: Literal["session.created"] = "session.created"
    session_id: str
    session: SessionConfig


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
