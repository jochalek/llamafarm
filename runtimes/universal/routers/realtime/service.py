"""
Realtime WebSocket service for bidirectional LLM chat.

Provides:
- Text input buffering with commit
- Streaming text output
- Mid-generation cancellation
- Session-based conversation history
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field

from models import GGUFLanguageModel
from utils.thinking import inject_thinking_control

from .types import SessionConfig

logger = logging.getLogger(__name__)


@dataclass
class RealtimeSession:
    """Manages state for a single realtime WebSocket session."""

    session_id: str
    config: SessionConfig
    input_buffer: str = ""
    conversation_history: list[dict] = field(default_factory=list)
    current_generation_task: asyncio.Task | None = None
    cancel_requested: bool = False
    accumulated_response: str = ""

    def reset_generation_state(self):
        """Reset state for a new generation."""
        self.cancel_requested = False
        self.accumulated_response = ""
        self.current_generation_task = None


class RealtimeService:
    """Service for handling realtime WebSocket connections."""

    def __init__(self):
        # Import here to avoid circular import
        from server import load_language

        self.load_language = load_language

    def create_session(self, config: SessionConfig | None = None) -> RealtimeSession:
        """Create a new realtime session."""
        session_id = f"rt_{uuid.uuid4().hex[:16]}"
        session_config = config or SessionConfig()

        session = RealtimeSession(
            session_id=session_id,
            config=session_config,
        )

        # Add system prompt to conversation history if provided
        if session_config.system_prompt:
            session.conversation_history.append(
                {"role": "system", "content": session_config.system_prompt}
            )

        logger.info(f"Created realtime session: {session_id}")
        return session

    def update_session(
        self, session: RealtimeSession, config: SessionConfig
    ) -> SessionConfig:
        """Update session configuration."""
        # Update config
        session.config = config

        # Handle system prompt changes
        if config.system_prompt:
            # Replace or add system message
            if (
                session.conversation_history
                and session.conversation_history[0].get("role") == "system"
            ):
                session.conversation_history[0]["content"] = config.system_prompt
            else:
                session.conversation_history.insert(
                    0, {"role": "system", "content": config.system_prompt}
                )
        else:
            # Remove system message if exists
            if (
                session.conversation_history
                and session.conversation_history[0].get("role") == "system"
            ):
                session.conversation_history.pop(0)

        logger.info(f"Updated session {session.session_id} config")
        return session.config

    def append_input(self, session: RealtimeSession, text: str) -> str:
        """Append text to the input buffer."""
        session.input_buffer += text
        logger.debug(
            f"Session {session.session_id}: buffer now {len(session.input_buffer)} chars"
        )
        return session.input_buffer

    def clear_input(self, session: RealtimeSession) -> None:
        """Clear the input buffer."""
        session.input_buffer = ""
        logger.debug(f"Session {session.session_id}: buffer cleared")

    def commit_input(self, session: RealtimeSession) -> tuple[str, str]:
        """Commit input buffer and add to conversation history.

        Returns:
            Tuple of (committed_text, item_id)
        """
        if not session.input_buffer.strip():
            raise ValueError("Cannot commit empty input buffer")

        committed_text = session.input_buffer.strip()
        item_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Add user message to conversation history
        session.conversation_history.append({"role": "user", "content": committed_text})

        # Clear buffer
        session.input_buffer = ""

        logger.info(
            f"Session {session.session_id}: committed input ({len(committed_text)} chars)"
        )
        return committed_text, item_id

    async def cancel_generation(self, session: RealtimeSession) -> tuple[str, str]:
        """Cancel in-progress generation.

        Returns:
            Tuple of (item_id, partial_text) if there was an active generation,
            or (None, "") if nothing to cancel.
        """
        if session.current_generation_task is None:
            logger.debug(f"Session {session.session_id}: nothing to cancel")
            return "", ""

        # Signal cancellation
        session.cancel_requested = True
        logger.info(f"Session {session.session_id}: cancellation requested")

        # Wait for the task to complete (it should check cancel_requested)
        try:
            await asyncio.wait_for(session.current_generation_task, timeout=2.0)
        except TimeoutError:
            # Force cancel if it doesn't respond
            session.current_generation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.current_generation_task
        except asyncio.CancelledError:
            pass

        partial_text = session.accumulated_response
        item_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Add partial response to history if substantial
        if partial_text.strip():
            session.conversation_history.append(
                {"role": "assistant", "content": partial_text}
            )

        session.reset_generation_state()
        return item_id, partial_text

    async def generate_response(
        self, session: RealtimeSession, on_token: callable, on_done: callable
    ) -> None:
        """Generate a response for the current conversation.

        Args:
            session: The realtime session
            on_token: Async callback called with (item_id, delta) for each token
            on_done: Async callback called with (item_id, full_text) when complete
        """
        config = session.config
        item_id = f"msg_{uuid.uuid4().hex[:12]}"

        try:
            # Load the model
            model = await self.load_language(
                config.model,
                n_ctx=config.n_ctx,
            )

            # Prepare messages
            messages = list(session.conversation_history)

            # Inject thinking control for GGUF models
            is_gguf = isinstance(model, GGUFLanguageModel)
            if is_gguf:
                enable_thinking = config.think is True
                messages = inject_thinking_control(messages, enable_thinking)
                logger.debug(
                    f"Thinking mode {'enabled' if enable_thinking else 'disabled'}"
                )

            # Calculate token budget
            answer_tokens = config.max_tokens or 512
            thinking_tokens = 0
            if config.think and is_gguf:
                thinking_tokens = config.thinking_budget or 1024
            total_max_tokens = thinking_tokens + answer_tokens

            # Stream generation
            session.accumulated_response = ""

            async for token in model.generate_stream(
                messages=messages,
                max_tokens=total_max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                stop=config.stop,
                thinking_budget=thinking_tokens if is_gguf else None,
            ):
                # Check for cancellation
                if session.cancel_requested:
                    logger.info(f"Session {session.session_id}: generation cancelled")
                    return

                # Accumulate response
                session.accumulated_response += token

                # Send token to client
                await on_token(item_id, token)

                # Yield to event loop for responsiveness
                await asyncio.sleep(0)

            # Generation complete
            full_response = session.accumulated_response

            # Add assistant message to history
            session.conversation_history.append(
                {"role": "assistant", "content": full_response}
            )

            await on_done(item_id, full_response)
            logger.info(
                f"Session {session.session_id}: generation complete ({len(full_response)} chars)"
            )

        except asyncio.CancelledError:
            logger.info(f"Session {session.session_id}: generation task cancelled")
            raise
        except Exception as e:
            logger.error(
                f"Session {session.session_id}: generation error: {e}", exc_info=True
            )
            raise
        finally:
            session.reset_generation_state()
