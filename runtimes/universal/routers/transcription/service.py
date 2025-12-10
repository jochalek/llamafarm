"""
Realtime transcription service for Universal Runtime.

Handles:
- Audio buffer management
- Voice Activity Detection (VAD)
- Whisper model loading and transcription
- Streaming transcription results
"""

import asyncio
import base64
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .types import SessionConfig

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSession:
    """Manages state for a single transcription WebSocket session."""

    session_id: str
    config: SessionConfig

    # Audio buffer (raw PCM samples as floats)
    audio_buffer: list[float] = field(default_factory=list)

    # Item tracking
    current_item_id: str | None = None
    previous_item_id: str | None = None

    # VAD state
    is_speaking: bool = False
    speech_start_sample: int = 0
    silence_samples: int = 0

    # Transcription task
    current_transcription_task: asyncio.Task | None = None

    def get_sample_rate(self) -> int:
        """Get the configured sample rate."""
        return self.config.audio.format.rate

    def get_buffer_duration_ms(self) -> int:
        """Get the current buffer duration in milliseconds."""
        sample_rate = self.get_sample_rate()
        return int(len(self.audio_buffer) * 1000 / sample_rate)

    def clear_buffer(self):
        """Clear the audio buffer."""
        self.audio_buffer = []
        self.is_speaking = False
        self.speech_start_sample = 0
        self.silence_samples = 0

    def generate_item_id(self) -> str:
        """Generate a new item ID and track previous."""
        self.previous_item_id = self.current_item_id
        self.current_item_id = f"item_{uuid.uuid4().hex[:12]}"
        return self.current_item_id


class TranscriptionService:
    """Service for handling realtime transcription sessions."""

    def __init__(self):
        self._model = None
        self._model_id: str | None = None
        self._model_lock = asyncio.Lock()
        self._vad = None
        self._vad_initialized = False

    async def _ensure_model(self, model_id: str) -> None:
        """Ensure the transcription model is loaded."""
        if self._model is not None and self._model_id == model_id:
            return

        async with self._model_lock:
            # Double-check after acquiring lock
            if self._model is not None and self._model_id == model_id:
                return

            # Import here to avoid circular imports
            from models import TranscriptionModel
            from utils.device import get_optimal_device

            logger.info(f"Loading transcription model: {model_id}")

            device = get_optimal_device()
            self._model = TranscriptionModel(model_id, device)
            await self._model.load()
            self._model_id = model_id

    def _init_vad(self, sample_rate: int) -> None:
        """Initialize Voice Activity Detection."""
        if self._vad_initialized:
            return

        try:
            # Try to use silero-vad (best quality)
            import torch

            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
            )
            self._vad = model
            self._vad_utils = utils
            self._vad_type = "silero"
            logger.info("Initialized Silero VAD")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD: {e}")
            # Fall back to simple energy-based VAD
            self._vad = None
            self._vad_type = "energy"
            logger.info("Using energy-based VAD fallback")

        self._vad_initialized = True

    def create_session(
        self, config: SessionConfig | None = None
    ) -> TranscriptionSession:
        """Create a new transcription session."""
        session_id = f"trans_{uuid.uuid4().hex[:16]}"
        session_config = config or SessionConfig()

        session = TranscriptionSession(
            session_id=session_id,
            config=session_config,
        )

        logger.info(
            f"Created transcription session: {session_id}",
            extra={"model": session_config.audio.transcription.model},
        )
        return session

    def update_session(
        self, session: TranscriptionSession, config: SessionConfig
    ) -> SessionConfig:
        """Update session configuration."""
        session.config = config
        logger.info(f"Updated session config: {session.session_id}")
        return session.config

    def decode_audio(self, base64_audio: str, audio_format: str) -> list[float]:
        """Decode base64 audio to float samples.

        Args:
            base64_audio: Base64-encoded audio data
            audio_format: Audio format (pcmf32, pcm, pcmu, pcma)

        Returns:
            List of float samples normalized to [-1, 1]
        """
        raw_bytes = base64.b64decode(base64_audio)

        if audio_format == "audio/pcmf32":
            # 32-bit float PCM - already in [-1, 1] range
            # This is the easiest format for clients (no conversion needed)
            samples = np.frombuffer(raw_bytes, dtype=np.float32)
            return samples.tolist()

        elif audio_format == "audio/pcm":
            # 16-bit PCM, little-endian
            samples = np.frombuffer(raw_bytes, dtype=np.int16)
            # Normalize to [-1, 1]
            return (samples.astype(np.float32) / 32768.0).tolist()

        elif audio_format == "audio/pcmu":
            # G.711 μ-law
            import audioop

            pcm_bytes = audioop.ulaw2lin(raw_bytes, 2)
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            return (samples.astype(np.float32) / 32768.0).tolist()

        elif audio_format == "audio/pcma":
            # G.711 A-law
            import audioop

            pcm_bytes = audioop.alaw2lin(raw_bytes, 2)
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            return (samples.astype(np.float32) / 32768.0).tolist()

        else:
            raise ValueError(f"Unsupported audio format: {audio_format}")

    def append_audio(
        self, session: TranscriptionSession, base64_audio: str
    ) -> tuple[bool, int | None]:
        """Append audio to the session buffer.

        Args:
            session: The transcription session
            base64_audio: Base64-encoded audio data

        Returns:
            Tuple of (speech_detected, speech_start_ms)
            - speech_detected: True if this chunk contains speech
            - speech_start_ms: Offset in ms where speech started (if newly detected)
        """
        audio_format = session.config.audio.format.type
        samples = self.decode_audio(base64_audio, audio_format)
        session.audio_buffer.extend(samples)

        # Run VAD if enabled
        vad_config = session.config.audio.turn_detection
        if vad_config is None or vad_config.type is None:
            return False, None

        # Initialize VAD if needed
        self._init_vad(session.get_sample_rate())

        # Detect speech
        speech_detected, speech_start_ms = self._detect_speech(session, samples)
        return speech_detected, speech_start_ms

    def _detect_speech(
        self, session: TranscriptionSession, new_samples: list[float]
    ) -> tuple[bool, int | None]:
        """Detect speech in audio using VAD.

        Returns:
            Tuple of (speech_detected, speech_start_ms)
        """
        vad_config = session.config.audio.turn_detection
        if vad_config is None:
            return False, None

        sample_rate = session.get_sample_rate()
        threshold = vad_config.threshold

        if self._vad_type == "silero":
            # Use Silero VAD
            import torch

            audio_tensor = torch.FloatTensor(new_samples)
            speech_prob = self._vad(audio_tensor, sample_rate).item()

            is_speech = speech_prob > threshold
        else:
            # Energy-based fallback
            energy = np.sqrt(np.mean(np.array(new_samples) ** 2))
            is_speech = energy > threshold * 0.1  # Scale threshold for energy

        speech_start_ms = None

        if is_speech and not session.is_speaking:
            # Speech just started
            session.is_speaking = True
            # Account for prefix padding
            padding_samples = int(vad_config.prefix_padding_ms * sample_rate / 1000)
            session.speech_start_sample = max(
                0, len(session.audio_buffer) - len(new_samples) - padding_samples
            )
            speech_start_ms = int(session.speech_start_sample * 1000 / sample_rate)
            session.silence_samples = 0

        elif not is_speech and session.is_speaking:
            # Accumulate silence
            session.silence_samples += len(new_samples)
            silence_ms = int(session.silence_samples * 1000 / sample_rate)

            if silence_ms >= vad_config.silence_duration_ms:
                # Speech ended
                session.is_speaking = False
                session.silence_samples = 0

        elif is_speech:
            # Reset silence counter while speaking
            session.silence_samples = 0

        return is_speech, speech_start_ms

    def clear_buffer(self, session: TranscriptionSession) -> None:
        """Clear the audio buffer."""
        session.clear_buffer()
        logger.info(f"Cleared audio buffer: {session.session_id}")

    def _check_audio_quality(self, audio: np.ndarray) -> tuple[bool, str]:
        """Check if audio is suitable for transcription.

        Args:
            audio: Audio samples as numpy array

        Returns:
            Tuple of (is_valid, reason)
        """
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio**2))

        # Check if audio is too quiet (likely silence/noise)
        # Typical speech has RMS > 0.01, silence/noise is < 0.005
        MIN_RMS = 0.01
        if rms < MIN_RMS:
            return False, f"Audio too quiet (RMS={rms:.4f} < {MIN_RMS})"

        # Check for clipping (all samples near max)
        max_val = np.max(np.abs(audio))
        if max_val < 0.001:
            return False, "Audio is essentially silent"

        # Check for reasonable dynamic range (not just DC offset or constant tone)
        std = np.std(audio)
        if std < 0.005:
            return False, f"Audio has no variation (std={std:.4f})"

        return True, "OK"

    def _is_hallucination(self, text: str) -> bool:
        """Detect if transcription is likely a Whisper hallucination.

        Whisper hallucinates repetitive patterns on music/noise.
        """
        if not text or len(text) < 20:
            return False

        # Normalize text
        text_lower = text.lower().strip()

        # Check for repetitive word patterns (e.g., "no, no, no, no")
        words = text_lower.replace(",", "").replace(".", "").split()
        if len(words) >= 5:
            # Check if same word repeated many times
            word_counts = {}
            for w in words:
                word_counts[w] = word_counts.get(w, 0) + 1

            # If any single word is >60% of the text, likely hallucination
            max_count = max(word_counts.values())
            if max_count / len(words) > 0.6:
                return True

        # Check for measurement patterns (e.g., "2 cm x 2 cm x 2 cm")
        if " x " in text_lower and text_lower.count(" x ") > 3:
            return True

        # Check for excessive repetition of short phrases
        if len(text) > 50:
            # Look for 2-3 word phrases repeated
            for phrase_len in [2, 3]:
                if len(words) >= phrase_len * 4:
                    phrases = [
                        " ".join(words[i : i + phrase_len])
                        for i in range(len(words) - phrase_len + 1)
                    ]
                    phrase_counts = {}
                    for p in phrases:
                        phrase_counts[p] = phrase_counts.get(p, 0) + 1
                    max_phrase_count = max(phrase_counts.values())
                    if max_phrase_count >= 4:
                        return True

        return False

    async def transcribe(
        self,
        session: TranscriptionSession,
        on_delta: Callable | None = None,
        on_completed: Callable | None = None,
    ) -> str:
        """Transcribe the audio buffer.

        Args:
            session: The transcription session
            on_delta: Callback for streaming deltas (item_id, delta_text)
            on_completed: Callback when complete (item_id, full_transcript)

        Returns:
            Full transcript text
        """
        if not session.audio_buffer:
            return ""

        # Ensure model is loaded
        model_id = session.config.audio.transcription.model
        await self._ensure_model(model_id)

        # Generate item ID for this transcription
        item_id = session.generate_item_id()
        event_id = f"evt_{uuid.uuid4().hex[:12]}"

        # Get audio as numpy array
        audio = np.array(session.audio_buffer, dtype=np.float32)

        # Check audio quality to avoid Whisper hallucinations
        is_valid, reason = self._check_audio_quality(audio)
        if not is_valid:
            logger.info(
                f"Skipping transcription: {reason}",
                extra={"session_id": session.session_id, "item_id": item_id},
            )
            # Return empty but still call callbacks so client knows we processed it
            if on_completed:
                await on_completed(event_id, item_id, "")
            return ""

        # Get transcription config
        trans_config = session.config.audio.transcription
        language = trans_config.language

        logger.info(
            f"Transcribing {len(audio) / session.get_sample_rate():.2f}s of audio",
            extra={"session_id": session.session_id, "item_id": item_id},
        )

        # Transcribe
        result = await self._model.transcribe(
            audio=audio,
            language=language,
            task="transcribe",
        )

        transcript = result["text"]

        # Check for hallucination patterns (if enabled)
        if trans_config.hallucination_filter and self._is_hallucination(transcript):
            logger.info(
                f"Filtered hallucination: '{transcript[:50]}...'",
                extra={"session_id": session.session_id, "item_id": item_id},
            )
            if on_completed:
                await on_completed(event_id, item_id, "")
            return ""

        # For Whisper, we get the full result at once
        # Send delta with full text (matching OpenAI whisper-1 behavior)
        if on_delta:
            await on_delta(event_id, item_id, transcript)

        if on_completed:
            await on_completed(event_id, item_id, transcript)

        return transcript
