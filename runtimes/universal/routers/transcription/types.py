"""
Type definitions for the Realtime Transcription WebSocket API.

Based on OpenAI's Realtime Transcription API, adapted for local Whisper models.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """WebSocket message types for transcription."""

    # Client -> Server
    SESSION_UPDATE = "session.update"
    INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
    INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
    INPUT_AUDIO_BUFFER_CLEAR = "input_audio_buffer.clear"

    # Server -> Client
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
    INPUT_AUDIO_BUFFER_CLEARED = "input_audio_buffer.cleared"
    INPUT_AUDIO_BUFFER_SPEECH_STARTED = "input_audio_buffer.speech_started"
    INPUT_AUDIO_BUFFER_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_DELTA = (
        "conversation.item.input_audio_transcription.delta"
    )
    CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED = (
        "conversation.item.input_audio_transcription.completed"
    )
    ERROR = "error"


class AudioFormat(BaseModel):
    """Audio input format configuration."""

    type: Literal["audio/pcm", "audio/pcmf32", "audio/pcmu", "audio/pcma"] = Field(
        default="audio/pcmf32",
        description="Audio format: pcmf32 (float32, easiest), pcm (int16), pcmu/pcma (G.711)",
    )
    rate: int = Field(
        default=16000,
        description="Sample rate in Hz (Whisper requires 16000)",
    )


class NoiseReduction(BaseModel):
    """Noise reduction configuration."""

    type: Literal["near_field", "far_field"] | None = Field(
        default="near_field",
        description="Noise reduction type. near_field for close mics, far_field for distant.",
    )


class TurnDetection(BaseModel):
    """Voice Activity Detection (VAD) configuration."""

    type: Literal["server_vad"] | None = Field(
        default="server_vad",
        description="VAD type. Set to null to manage turn boundaries manually.",
    )
    threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="VAD threshold (0-1). Higher = less sensitive.",
    )
    prefix_padding_ms: int = Field(
        default=300,
        ge=0,
        description="Audio to include before speech detection (ms).",
    )
    silence_duration_ms: int = Field(
        default=500,
        ge=0,
        description="Silence duration to end a speech segment (ms).",
    )


class TranscriptionConfig(BaseModel):
    """Transcription model configuration."""

    model: str = Field(
        default="openai/whisper-base",
        description="Whisper model to use (whisper-tiny, whisper-base, whisper-small, etc.)",
    )
    language: str | None = Field(
        default=None,
        description="ISO-639-1 language code (e.g., 'en'). None for auto-detect.",
    )
    prompt: str | None = Field(
        default=None,
        description="Optional prompt to guide transcription output.",
    )
    hallucination_filter: bool = Field(
        default=True,
        description="Filter repetitive Whisper hallucinations (e.g., music transcribed as 'no, no, no...')",
    )
    commit_interval_ms: int = Field(
        default=1500,
        ge=500,
        le=10000,
        description="Suggested commit interval for clients (ms). Lower = faster but less context.",
    )
    chain_to_model: str | None = Field(
        default=None,
        description="Model name to forward transcriptions to (for voice chat pipelines).",
    )


class AudioInputConfig(BaseModel):
    """Audio input configuration."""

    format: AudioFormat = Field(default_factory=AudioFormat)
    noise_reduction: NoiseReduction | None = Field(default_factory=NoiseReduction)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    turn_detection: TurnDetection | None = Field(default_factory=TurnDetection)


class SessionConfig(BaseModel):
    """Session configuration for realtime transcription."""

    type: Literal["transcription"] = "transcription"
    audio: AudioInputConfig = Field(
        default_factory=lambda: AudioInputConfig(),
        description="Audio input configuration",
    )
    include: list[str] = Field(
        default_factory=list,
        description="Additional fields to include in events (e.g., 'item.input_audio_transcription.logprobs')",
    )


# Client -> Server messages


class SessionUpdateMessage(BaseModel):
    """Client message to update session configuration."""

    type: Literal["session.update"] = "session.update"
    session: SessionConfig


class InputAudioBufferAppendMessage(BaseModel):
    """Client message to append audio to the buffer.

    Audio should be base64-encoded PCM audio data.
    """

    type: Literal["input_audio_buffer.append"] = "input_audio_buffer.append"
    audio: str = Field(description="Base64-encoded audio data")


class InputAudioBufferCommitMessage(BaseModel):
    """Client message to commit audio buffer and trigger transcription."""

    type: Literal["input_audio_buffer.commit"] = "input_audio_buffer.commit"


class InputAudioBufferClearMessage(BaseModel):
    """Client message to clear the audio buffer."""

    type: Literal["input_audio_buffer.clear"] = "input_audio_buffer.clear"


# Server -> Client messages


class SessionCreatedMessage(BaseModel):
    """Server message when transcription session is created."""

    type: Literal["session.created"] = "session.created"
    session_id: str
    session: SessionConfig


class SessionUpdatedMessage(BaseModel):
    """Server message when session is updated."""

    type: Literal["session.updated"] = "session.updated"
    session: SessionConfig


class InputAudioBufferCommittedMessage(BaseModel):
    """Server message when audio buffer is committed."""

    type: Literal["input_audio_buffer.committed"] = "input_audio_buffer.committed"
    item_id: str
    previous_item_id: str | None = None


class InputAudioBufferClearedMessage(BaseModel):
    """Server message when audio buffer is cleared."""

    type: Literal["input_audio_buffer.cleared"] = "input_audio_buffer.cleared"


class InputAudioBufferSpeechStartedMessage(BaseModel):
    """Server message when VAD detects speech start."""

    type: Literal["input_audio_buffer.speech_started"] = (
        "input_audio_buffer.speech_started"
    )
    audio_start_ms: int = Field(description="Audio offset where speech started (ms)")
    item_id: str


class InputAudioBufferSpeechStoppedMessage(BaseModel):
    """Server message when VAD detects speech end."""

    type: Literal["input_audio_buffer.speech_stopped"] = (
        "input_audio_buffer.speech_stopped"
    )
    audio_end_ms: int = Field(description="Audio offset where speech ended (ms)")
    item_id: str


class TranscriptionDeltaMessage(BaseModel):
    """Server message with incremental transcription.

    For streaming models, contains partial transcript.
    For batch models (whisper-1), contains full transcript same as completed.
    """

    type: Literal["conversation.item.input_audio_transcription.delta"] = (
        "conversation.item.input_audio_transcription.delta"
    )
    event_id: str
    item_id: str
    content_index: int = 0
    delta: str


class TranscriptionCompletedMessage(BaseModel):
    """Server message when transcription for a segment is complete."""

    type: Literal["conversation.item.input_audio_transcription.completed"] = (
        "conversation.item.input_audio_transcription.completed"
    )
    event_id: str
    item_id: str
    content_index: int = 0
    transcript: str


class ErrorMessage(BaseModel):
    """Server error message."""

    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict | None = None
