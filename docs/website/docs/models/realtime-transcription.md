---
title: Realtime Transcription API
sidebar_position: 6
---

# Realtime Transcription API

The Universal Runtime provides a WebSocket-based Realtime Transcription API for streaming audio-to-text conversion. Based on OpenAI's Realtime Transcription API, this enables:

- **Streaming audio input**: Send audio incrementally as it's captured
- **Voice Activity Detection (VAD)**: Automatic speech boundary detection
- **Multiple Whisper models**: Choose from tiny, base, small, medium, large
- **Multiple audio formats**: PCM, G.711 μ-law, G.711 A-law

## Quick Start

### Connect

```javascript
const ws = new WebSocket('ws://localhost:11540/v1/realtime/transcription');

ws.onopen = () => {
  console.log('Connected to transcription service');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'conversation.item.input_audio_transcription.completed') {
    console.log('Transcript:', message.transcript);
  }
};
```

### Configure Session

```javascript
// After receiving session.created
ws.send(JSON.stringify({
  type: 'session.update',
  session: {
    type: 'transcription',
    audio: {
      format: { type: 'audio/pcm', rate: 16000 },
      transcription: {
        model: 'openai/whisper-small',
        language: 'en'
      },
      turn_detection: {
        type: 'server_vad',
        threshold: 0.5,
        silence_duration_ms: 500
      }
    }
  }
}));
```

### Send Audio

```javascript
// Capture audio from microphone (example using Web Audio API)
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
    const audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      const audioData = e.inputBuffer.getChannelData(0);

      // Convert Float32Array to Int16 PCM
      const pcm16 = new Int16Array(audioData.length);
      for (let i = 0; i < audioData.length; i++) {
        pcm16[i] = Math.max(-32768, Math.min(32767, audioData[i] * 32768));
      }

      // Base64 encode and send
      const base64Audio = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));
      ws.send(JSON.stringify({
        type: 'input_audio_buffer.append',
        audio: base64Audio
      }));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
  });
```

### Trigger Transcription

```javascript
// Commit the audio buffer to trigger transcription
ws.send(JSON.stringify({
  type: 'input_audio_buffer.commit'
}));

// Handle transcription result
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'conversation.item.input_audio_transcription.delta') {
    // Streaming partial transcript
    console.log('Partial:', msg.delta);
  }

  if (msg.type === 'conversation.item.input_audio_transcription.completed') {
    // Final transcript
    console.log('Final:', msg.transcript);
  }
};
```

---

## Protocol Reference

### Connection Flow

```
Client                              Server
  |                                    |
  |-------- WebSocket Connect -------->|
  |                                    |
  |<------ session.created ------------|
  |                                    |
  |-------- session.update ----------->|
  |<------ session.updated ------------|
  |                                    |
  |-------- input_audio_buffer.append->|  (repeat for each chunk)
  |<------ speech_started -------------|  (if VAD enabled)
  |-------- input_audio_buffer.append->|
  |<------ speech_stopped -------------|  (if VAD enabled)
  |                                    |
  |-------- input_audio_buffer.commit->|
  |<------ committed ------------------|
  |<------ transcription.delta --------|
  |<------ transcription.completed ----|
  |                                    |
```

### Client → Server Messages

#### session.update

Update session configuration.

```json
{
  "type": "session.update",
  "session": {
    "type": "transcription",
    "audio": {
      "format": {
        "type": "audio/pcm",
        "rate": 16000
      },
      "noise_reduction": {
        "type": "near_field"
      },
      "transcription": {
        "model": "openai/whisper-base",
        "language": "en",
        "prompt": null
      },
      "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500
      }
    },
    "include": []
  }
}
```

#### input_audio_buffer.append

Append audio data to the buffer.

```json
{
  "type": "input_audio_buffer.append",
  "audio": "base64-encoded-audio-data..."
}
```

#### input_audio_buffer.commit

Commit the audio buffer and trigger transcription.

```json
{
  "type": "input_audio_buffer.commit"
}
```

#### input_audio_buffer.clear

Clear the audio buffer without transcribing.

```json
{
  "type": "input_audio_buffer.clear"
}
```

### Server → Client Messages

#### session.created

Sent immediately after WebSocket connection.

```json
{
  "type": "session.created",
  "session_id": "trans_abc123def456",
  "session": { ... }
}
```

#### input_audio_buffer.speech_started

Sent when VAD detects speech start.

```json
{
  "type": "input_audio_buffer.speech_started",
  "audio_start_ms": 1250,
  "item_id": "item_abc123"
}
```

#### input_audio_buffer.speech_stopped

Sent when VAD detects speech end.

```json
{
  "type": "input_audio_buffer.speech_stopped",
  "audio_end_ms": 3500,
  "item_id": "item_abc123"
}
```

#### conversation.item.input_audio_transcription.delta

Streaming transcription delta. For Whisper models, this contains the full transcript (same as completed).

```json
{
  "type": "conversation.item.input_audio_transcription.delta",
  "event_id": "evt_xyz789",
  "item_id": "item_abc123",
  "content_index": 0,
  "delta": "Hello, how are you today?"
}
```

#### conversation.item.input_audio_transcription.completed

Final transcription result.

```json
{
  "type": "conversation.item.input_audio_transcription.completed",
  "event_id": "evt_xyz789",
  "item_id": "item_abc123",
  "content_index": 0,
  "transcript": "Hello, how are you today?"
}
```

---

## Configuration Options

### LlamaFarm Config

Configure transcription models in your `llamafarm.yaml`:

```yaml
runtime:
  default_transcription_model: whisper

  models:
    # Transcription model (Whisper)
    - name: whisper
      type: transcription
      description: "Local Whisper for speech-to-text"
      provider: universal
      model: openai/whisper-base
      base_url: http://localhost:11540
      language: en
      commit_interval_ms: 1500
      hallucination_filter: true
      vad:
        enabled: true
        threshold: 0.5
        silence_duration_ms: 800
      chain_to_model: fast  # Optional: forward transcriptions to chat model
```

### Audio Formats

| Format | Description | Sample Rate | Notes |
|--------|-------------|-------------|-------|
| `audio/pcmf32` | 32-bit float PCM | 16000 Hz | **Easiest** - no conversion needed |
| `audio/pcm` | 16-bit PCM, little-endian | 16000 Hz | Standard PCM |
| `audio/pcmu` | G.711 μ-law (telephony) | 8000 Hz | For telephony |
| `audio/pcma` | G.711 A-law (telephony) | 8000 Hz | For telephony |

**Recommended**: Use `audio/pcmf32` for simplest client code - just send raw float32 samples directly.

### Whisper Models

| Model | Size | Speed | Accuracy | HuggingFace ID |
|-------|------|-------|----------|----------------|
| Tiny | 39M | Fastest | Good | `openai/whisper-tiny` |
| Base | 74M | Fast | Better | `openai/whisper-base` |
| Small | 244M | Moderate | Great | `openai/whisper-small` |
| Medium | 769M | Slow | Excellent | `openai/whisper-medium` |
| Large | 1.5B | Slowest | Best | `openai/whisper-large-v3` |

### Voice Activity Detection

VAD automatically detects when speech starts and stops:

```json
{
  "turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 500
  }
}
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `threshold` | Speech detection sensitivity (0-1, higher = less sensitive) | 0.5 |
| `prefix_padding_ms` | Audio to include before detected speech | 300 |
| `silence_duration_ms` | Silence duration to end speech segment | 500 |

Set `turn_detection` to `null` to disable VAD and manually control turn boundaries.

### Additional Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `hallucination_filter` | Filter repetitive Whisper hallucinations (e.g., music transcribed as "no, no, no...") | `true` |
| `commit_interval_ms` | Suggested interval for committing audio (500-10000ms). Lower = faster but less context | `1500` |
| `chain_to_model` | Model name to forward transcriptions to (for voice chat pipelines) | `null` |

**Example with all options:**

```json
{
  "type": "session.update",
  "session": {
    "audio": {
      "format": { "type": "audio/pcmf32", "rate": 16000 },
      "transcription": {
        "model": "openai/whisper-base",
        "language": "en",
        "hallucination_filter": true,
        "commit_interval_ms": 1500,
        "chain_to_model": null
      },
      "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "silence_duration_ms": 800
      }
    }
  }
}
```

---

## Python Client Example

Using `audio/pcmf32` format (simplest - no conversion needed):

```python
import asyncio
import base64
import json
import sounddevice as sd
import websockets

async def realtime_transcription():
    uri = "ws://localhost:11540/v1/realtime/transcription"

    async with websockets.connect(uri) as ws:
        # Wait for session.created
        msg = await ws.recv()
        session = json.loads(msg)
        print(f"Connected: {session['session_id']}")

        # Configure for English transcription with float32 audio
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {
                    "format": {"type": "audio/pcmf32", "rate": 16000},
                    "transcription": {
                        "model": "openai/whisper-base",
                        "language": "en",
                        "hallucination_filter": True
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "silence_duration_ms": 800
                    }
                }
            }
        }))
        await ws.recv()  # session.updated

        print("Recording... Press Ctrl+C to stop")

        # Audio callback to stream to WebSocket
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"Audio status: {status}")
            # Send float32 directly - no conversion needed!
            audio_b64 = base64.b64encode(indata.tobytes()).decode()

            # Send audio (non-blocking)
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.create_task(ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64
                })))
            )

        # Start recording (float32 is the default)
        stream = sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype='float32',
            blocksize=4096,
            callback=audio_callback
        )

        async def listen_for_transcriptions():
            while True:
                msg = json.loads(await ws.recv())

                if msg["type"] == "input_audio_buffer.speech_started":
                    print("🎤 Speech started")
                elif msg["type"] == "input_audio_buffer.speech_stopped":
                    print("🔇 Speech stopped - transcribing...")
                    # Commit the buffer
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.commit"
                    }))
                elif msg["type"] == "conversation.item.input_audio_transcription.completed":
                    print(f"📝 {msg['transcript']}")

        with stream:
            await listen_for_transcriptions()

asyncio.run(realtime_transcription())
```

**Requirements**: `pip install sounddevice websockets numpy`

---

## Use Cases

### Live Subtitles

Generate real-time captions for video calls or presentations:

```javascript
let subtitleDiv = document.getElementById('subtitles');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'conversation.item.input_audio_transcription.completed') {
    subtitleDiv.textContent = msg.transcript;

    // Fade out after 3 seconds
    setTimeout(() => {
      subtitleDiv.textContent = '';
    }, 3000);
  }
};
```

### Voice Commands

Process voice commands with immediate feedback:

```javascript
const commands = {
  'play': () => player.play(),
  'pause': () => player.pause(),
  'next': () => player.next(),
  'stop': () => player.stop()
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'conversation.item.input_audio_transcription.completed') {
    const text = msg.transcript.toLowerCase().trim();

    for (const [command, action] of Object.entries(commands)) {
      if (text.includes(command)) {
        action();
        break;
      }
    }
  }
};
```

### Meeting Transcription

Continuously transcribe a meeting with speaker turns:

```javascript
let transcript = [];
let currentSegment = '';

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'input_audio_buffer.speech_started') {
    currentSegment = '';
  }

  if (msg.type === 'conversation.item.input_audio_transcription.completed') {
    transcript.push({
      timestamp: new Date().toISOString(),
      text: msg.transcript
    });
    updateTranscriptDisplay();
  }
};
```

---

## Comparison with Batch Transcription

| Feature | Realtime WebSocket | Batch API |
|---------|-------------------|-----------|
| **Latency** | Low (streaming) | Higher (full file) |
| **Use case** | Live audio | Recorded files |
| **VAD** | Built-in | Manual splitting |
| **Connection** | Persistent WebSocket | HTTP request |
| **Audio format** | PCM, G.711 | Many (wav, mp3, etc.) |

Choose **Realtime Transcription** when you need:
- Live transcription from microphone
- Real-time subtitles or captions
- Voice command processing
- Interactive voice applications

Choose **Batch Transcription** when you have:
- Pre-recorded audio files
- Large audio files to process
- No need for streaming output

---

## Next Steps

- [Realtime Chat API](./realtime-api.md) - Bidirectional LLM chat
- [Models Overview](./index.md) - Available models and configurations
- [Specialized ML Models](./specialized-ml.md) - OCR, classification, anomaly detection
