#!/usr/bin/env python3
"""
Live Microphone Transcription

Captures audio from your microphone and streams it to the
Universal Runtime for real-time transcription.

Usage:
    python mic_transcription.py

Requirements:
    pip install sounddevice websockets numpy

Press Ctrl+C to stop.
"""

import asyncio
import base64
import json
import signal
import sys
from datetime import datetime

import sounddevice as sd
import websockets


class MicTranscriber:
    """Real-time microphone transcription using WebSocket."""

    def __init__(
        self,
        server_url: str = "ws://localhost:11540/v1/realtime/transcription",
        sample_rate: int = 16000,
        chunk_duration_ms: int = 250,  # Send audio every 250ms
        commit_interval_ms: int = 1500,  # Commit for transcription every 1.5s
        model: str = "openai/whisper-base",
        language: str = "en",
    ):
        self.server_url = server_url
        self.sample_rate = sample_rate
        self.chunk_size = int(sample_rate * chunk_duration_ms / 1000)
        self.commit_interval_ms = commit_interval_ms
        self.model = model
        self.language = language

        self.ws = None
        self.running = False
        self.audio_queue = asyncio.Queue()

    def audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio chunk."""
        if status:
            print(f"⚠️  Audio status: {status}", file=sys.stderr)

        # Convert to mono if needed
        if indata.ndim > 1:
            audio = indata[:, 0]
        else:
            audio = indata.flatten()

        # Put audio chunk in queue
        try:
            self.audio_queue.put_nowait(audio.copy())
        except asyncio.QueueFull:
            pass  # Drop if queue is full

    async def send_audio(self):
        """Send audio chunks to WebSocket."""
        buffer = []
        buffer_duration_ms = 0
        commit_threshold_ms = self.commit_interval_ms

        while self.running:
            try:
                # Get audio chunk (with timeout)
                chunk = await asyncio.wait_for(
                    self.audio_queue.get(), timeout=0.1
                )

                # Send float32 directly (server handles it)
                audio_b64 = base64.b64encode(chunk.tobytes()).decode()

                # Send to WebSocket
                await self.ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64
                }))

                # Track buffer duration
                buffer_duration_ms += len(chunk) * 1000 / self.sample_rate

                # Auto-commit after threshold
                if buffer_duration_ms >= commit_threshold_ms:
                    await self.ws.send(json.dumps({
                        "type": "input_audio_buffer.commit"
                    }))
                    buffer_duration_ms = 0

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.running:
                    print(f"❌ Send error: {e}", file=sys.stderr)
                break

    async def receive_messages(self):
        """Receive and display transcription results."""
        while self.running:
            try:
                msg = json.loads(await self.ws.recv())
                msg_type = msg.get("type")

                if msg_type == "input_audio_buffer.speech_started":
                    print("\n🎤 [Listening...]", end="", flush=True)

                elif msg_type == "input_audio_buffer.speech_stopped":
                    print(" [Processing...]", end="", flush=True)

                elif msg_type == "input_audio_buffer.committed":
                    pass  # Silently handle

                elif msg_type == "conversation.item.input_audio_transcription.delta":
                    # Clear line and show partial transcript
                    print(f"\r📝 {msg['delta']}", end="", flush=True)

                elif msg_type == "conversation.item.input_audio_transcription.completed":
                    # Show final transcript with timestamp
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"\r[{timestamp}] 📝 {msg['transcript']}")

                elif msg_type == "error":
                    print(f"\n❌ Error: {msg['code']}: {msg['message']}")

            except websockets.exceptions.ConnectionClosed:
                if self.running:
                    print("\n⚠️  Connection closed")
                break
            except Exception as e:
                if self.running:
                    print(f"\n❌ Receive error: {e}", file=sys.stderr)
                break

    async def run(self):
        """Main run loop."""
        print(f"🔌 Connecting to {self.server_url}...")

        try:
            async with websockets.connect(
                self.server_url,
                ping_interval=30,
                ping_timeout=60,
            ) as ws:
                self.ws = ws
                self.running = True

                # Wait for session.created
                msg = json.loads(await ws.recv())
                print(f"✅ Connected: {msg['session_id']}")

                # Configure session
                print(f"⚙️  Model: {self.model}, Language: {self.language}")
                await ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "type": "transcription",
                        "audio": {
                            "format": {"type": "audio/pcmf32", "rate": self.sample_rate},
                            "transcription": {
                                "model": self.model,
                                "language": self.language
                            },
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "silence_duration_ms": 800
                            }
                        }
                    }
                }))

                msg = json.loads(await ws.recv())
                if msg["type"] == "session.updated":
                    print("✅ Session configured")
                else:
                    print(f"⚠️  Unexpected: {msg}")

                print("\n" + "="*50)
                print("🎙️  LIVE TRANSCRIPTION")
                print("="*50)
                print("Speak into your microphone. Press Ctrl+C to stop.\n")

                # Start audio capture (float32 is the default)
                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=self.chunk_size,
                    callback=self.audio_callback,
                )

                with stream:
                    # Run send and receive tasks concurrently
                    await asyncio.gather(
                        self.send_audio(),
                        self.receive_messages(),
                    )

        except (OSError, ConnectionRefusedError):
            print("❌ Could not connect to server")
            print("   Make sure Universal Runtime is running:")
            print("   nx start universal")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            self.running = False

    def stop(self):
        """Stop the transcriber."""
        self.running = False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Live Microphone Transcription")
    parser.add_argument(
        "--model", default="openai/whisper-base",
        help="Whisper model (whisper-tiny, whisper-base, whisper-small, etc.)"
    )
    parser.add_argument(
        "--language", default="en",
        help="Language code (en, es, fr, de, etc.)"
    )
    parser.add_argument(
        "--server", default="ws://localhost:11540/v1/realtime/transcription",
        help="WebSocket server URL"
    )
    parser.add_argument(
        "--interval", type=int, default=1500,
        help="Commit interval in ms (default: 1500). Lower = faster but less context."
    )
    args = parser.parse_args()

    transcriber = MicTranscriber(
        server_url=args.server,
        model=args.model,
        language=args.language,
        commit_interval_ms=args.interval,
    )

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n👋 Stopping...")
        transcriber.stop()

    signal.signal(signal.SIGINT, signal_handler)

    await transcriber.run()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())
