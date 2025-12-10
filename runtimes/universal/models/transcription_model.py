"""
Whisper-based transcription model for audio-to-text.

Supports:
- OpenAI Whisper models (whisper-tiny, whisper-base, whisper-small, etc.)
- Streaming transcription with chunked audio
- Language detection
- Timestamped output
"""

import logging
from typing import Any

import numpy as np
import torch

from .base import BaseModel

logger = logging.getLogger(__name__)


class TranscriptionModel(BaseModel):
    """Whisper-based transcription model using HuggingFace transformers."""

    def __init__(
        self,
        model_id: str = "openai/whisper-base",
        device: str = "cpu",
        token: str | None = None,
    ):
        super().__init__(model_id, device, token)
        self.model_type = "transcription"
        self.supports_streaming = True
        self.sample_rate = 16000  # Whisper expects 16kHz audio

    async def load(self) -> None:
        """Load Whisper model and processor."""
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        logger.info(f"Loading Whisper model: {self.model_id}")

        # Load processor (handles audio preprocessing and tokenization)
        self.processor = WhisperProcessor.from_pretrained(
            self.model_id,
            token=self.token,
            trust_remote_code=True,
        )

        # IMPORTANT: Whisper on MPS with float16 produces garbage output.
        # Use float32 on MPS, or float16 on CUDA only.
        if self.device == "mps":
            dtype = torch.float32
            logger.info("Using float32 for Whisper on MPS (float16 is buggy)")
        elif self.device == "cuda":
            dtype = torch.float16
        else:
            dtype = torch.float32

        self.model = WhisperForConditionalGeneration.from_pretrained(
            self.model_id,
            torch_dtype=dtype,
            token=self.token,
            trust_remote_code=True,
        ).to(self.device)

        # Put model in eval mode
        self.model.eval()

        logger.info(f"Whisper model loaded on {self.device} with dtype {dtype}")

    async def transcribe(
        self,
        audio: np.ndarray | list[float] | bytes,
        language: str | None = None,
        task: str = "transcribe",
        return_timestamps: bool = False,
    ) -> dict[str, Any]:
        """Transcribe audio to text.

        Args:
            audio: Audio data as numpy array, list of floats, or raw bytes.
                   Expected sample rate: 16kHz mono.
            language: ISO-639-1 language code (e.g., "en", "es"). None for auto-detect.
            task: "transcribe" or "translate" (translate to English)
            return_timestamps: Whether to return word/segment timestamps

        Returns:
            Dict with:
                - text: Transcribed text
                - language: Detected/specified language
                - segments: List of segments with timestamps (if return_timestamps=True)
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Convert audio to numpy array if needed
        if isinstance(audio, bytes):
            audio = np.frombuffer(audio, dtype=np.float32)
        elif isinstance(audio, list):
            audio = np.array(audio, dtype=np.float32)

        # Ensure audio is 1D
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # Process audio through Whisper processor
        inputs = self.processor(
            audio,
            sampling_rate=self.sample_rate,
            return_tensors="pt",
            return_attention_mask=True,
        )
        # Use the model's dtype (float32 on MPS, float16 on CUDA)
        model_dtype = next(self.model.parameters()).dtype
        input_features = inputs.input_features.to(self.device, dtype=model_dtype)
        attention_mask = (
            inputs.attention_mask.to(self.device)
            if hasattr(inputs, "attention_mask")
            else None
        )

        # Build generation kwargs
        generate_kwargs = {
            "task": task,
        }
        if language:
            generate_kwargs["language"] = language

        if return_timestamps:
            generate_kwargs["return_timestamps"] = True

        if attention_mask is not None:
            generate_kwargs["attention_mask"] = attention_mask

        # Generate transcription
        with torch.no_grad():
            predicted_ids = self.model.generate(
                input_features,
                **generate_kwargs,
            )

        # Decode
        transcription = self.processor.batch_decode(
            predicted_ids,
            skip_special_tokens=True,
        )[0]

        result = {
            "text": transcription.strip(),
            "language": language or "auto",
        }

        return result

    async def transcribe_streaming(
        self,
        audio_chunk: np.ndarray | list[float] | bytes,
        language: str | None = None,
    ) -> str:
        """Transcribe a single audio chunk for streaming use.

        This is a simplified method for streaming transcription that:
        - Takes smaller audio chunks
        - Returns just the text
        - Optimized for low latency

        Args:
            audio_chunk: Audio chunk (recommended: 1-5 seconds at 16kHz)
            language: ISO-639-1 language code

        Returns:
            Transcribed text for this chunk
        """
        result = await self.transcribe(
            audio=audio_chunk,
            language=language,
            task="transcribe",
            return_timestamps=False,
        )
        return result["text"]
