#!/usr/bin/env python3
"""
Test script for Realtime Transcription API.

Converts an MP3 file to PCM and sends it through the WebSocket for transcription.
"""

import asyncio
import base64
import json
import sys
from pathlib import Path

import websockets
import numpy as np
import librosa


def convert_mp3_to_pcm(mp3_path: str, sample_rate: int = 16000) -> bytes:
    """Convert MP3 to 16-bit PCM using librosa."""
    # Load audio file with librosa (handles MP3, WAV, etc.)
    audio, sr = librosa.load(mp3_path, sr=sample_rate, mono=True)

    # Convert float32 [-1, 1] to int16
    pcm16 = (audio * 32767).astype(np.int16)

    return pcm16.tobytes()


async def test_transcription(audio_file: str, server_url: str = "ws://localhost:11540/v1/realtime/transcription"):
    """Test transcription API with an audio file."""

    print(f"🎵 Converting {audio_file} to PCM...")
    import warnings
    warnings.filterwarnings("ignore", message=".*PySoundFile failed.*")
    pcm_data = convert_mp3_to_pcm(audio_file)
    print(f"   Audio size: {len(pcm_data)} bytes ({len(pcm_data) / 32000:.2f} seconds)")

    print(f"\n🔌 Connecting to {server_url}...")

    async with websockets.connect(server_url, ping_interval=30, ping_timeout=120) as ws:
        # Wait for session.created
        msg = json.loads(await ws.recv())
        print(f"✅ Connected: {msg['session_id']}")

        # Configure session for Whisper
        print("\n⚙️  Configuring session...")
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {
                    "format": {"type": "audio/pcm", "rate": 16000},
                    "transcription": {
                        "model": "openai/whisper-base",
                        "language": "en"
                    },
                    "turn_detection": None  # Manual commit
                }
            }
        }))

        msg = json.loads(await ws.recv())
        if msg["type"] == "session.updated":
            print("✅ Session configured")
        else:
            print(f"⚠️  Unexpected response: {msg}")

        # Send audio in chunks (simulating streaming)
        print("\n📤 Sending audio...")
        chunk_size = 32000  # 1 second of audio at 16kHz, 16-bit
        total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size

        for i in range(0, len(pcm_data), chunk_size):
            chunk = pcm_data[i:i + chunk_size]
            chunk_b64 = base64.b64encode(chunk).decode()
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": chunk_b64
            }))
            chunk_num = i // chunk_size + 1
            print(f"   Sent chunk {chunk_num}/{total_chunks}")

        # Commit to trigger transcription
        print("\n🎯 Committing audio buffer...")
        await ws.send(json.dumps({
            "type": "input_audio_buffer.commit"
        }))

        # Wait for transcription results
        print("\n📝 Waiting for transcription...")
        while True:
            msg = json.loads(await ws.recv())

            if msg["type"] == "input_audio_buffer.committed":
                print(f"   Buffer committed: {msg['item_id']}")

            elif msg["type"] == "conversation.item.input_audio_transcription.delta":
                print(f"   Delta: {msg['delta']}")

            elif msg["type"] == "conversation.item.input_audio_transcription.completed":
                print(f"\n✅ Transcription complete!")
                print(f"\n{'='*60}")
                print(f"📜 TRANSCRIPT:")
                print(f"{'='*60}")
                print(msg["transcript"])
                print(f"{'='*60}\n")
                break

            elif msg["type"] == "error":
                print(f"\n❌ Error: {msg['code']}: {msg['message']}")
                break

            else:
                print(f"   {msg['type']}")


async def main():
    # Find audio file
    script_dir = Path(__file__).parent
    audio_file = script_dir / "speaker_0.mp3"

    if not audio_file.exists():
        print(f"❌ Audio file not found: {audio_file}")
        sys.exit(1)

    # Check if server is running
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 11540))
    sock.close()

    if result != 0:
        print("❌ Universal Runtime not running on port 11540")
        print("   Start it with: nx start universal")
        sys.exit(1)

    await test_transcription(str(audio_file))


if __name__ == "__main__":
    asyncio.run(main())
