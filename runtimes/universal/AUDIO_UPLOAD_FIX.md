# Audio Upload Fix

## Problem

The audio transcription and translation endpoints were originally designed to accept JSON with base64-encoded audio data, but curl was sending files via `multipart/form-data` (using the `-F` flag). This caused:

1. Binary audio data being printed to the console/logs
2. Stack traces from FastAPI trying to parse multipart form data as JSON
3. Failed transcription attempts

## Solution

Updated both audio endpoints to properly handle file uploads via `multipart/form-data`, which is the standard OpenAI-compatible approach:

### Changes Made

1. **Added imports** in `server.py`:
   ```python
   from fastapi import File, Form, UploadFile
   ```

2. **Updated `/v1/audio/transcriptions` endpoint**:
   - Changed from Pydantic model to individual parameters
   - Accept `file: UploadFile` via `File(...)`
   - Accept form fields via `Form(...)`
   - Pass raw bytes directly to `AudioModel` (no wasteful base64 conversion)
   - Return plain text for `response_format=text`

3. **Updated `/v1/audio/translations` endpoint**:
   - Same approach as transcriptions
   - Properly handles file uploads via multipart/form-data
   - Passes raw bytes directly to the model

### Before vs After

**Before (JSON with base64):**
```bash
# Required manual base64 encoding
AUDIO_BASE64=$(base64 -i audio.mp3)
curl -X POST http://localhost:11540/v1/audio/transcriptions \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"openai/whisper-tiny\", \"file\": \"$AUDIO_BASE64\"}"
```

**After (Direct file upload):**
```bash
# Just upload the file directly
curl -X POST http://localhost:11540/v1/audio/transcriptions \
  -F "file=@audio.mp3" \
  -F "model=openai/whisper-tiny"
```

## Testing

### Quick Test

1. **Get a test audio file:**
   ```bash
   curl -o test_audio.mp3 "https://www2.cs.uic.edu/~i101/SoundFiles/StarWars60.wav"
   ```

2. **Start the server:**
   ```bash
   ./start.sh
   ```

3. **Test transcription:**
   ```bash
   curl -X POST http://localhost:11540/v1/audio/transcriptions \
     -F "file=@test_audio.mp3" \
     -F "model=openai/whisper-tiny" \
     -F "language=en"
   ```

   **Expected response:**
   ```json
   {
     "text": "transcribed text here..."
   }
   ```

4. **Test with plain text response:**
   ```bash
   curl -X POST http://localhost:11540/v1/audio/transcriptions \
     -F "file=@test_audio.mp3" \
     -F "model=openai/whisper-tiny" \
     -F "response_format=text"
   ```

   **Expected response:**
   ```
   transcribed text here...
   ```

5. **Test verbose JSON:**
   ```bash
   curl -X POST http://localhost:11540/v1/audio/transcriptions \
     -F "file=@test_audio.mp3" \
     -F "model=openai/whisper-tiny" \
     -F "response_format=verbose_json"
   ```

   **Expected response:**
   ```json
   {
     "task": "transcribe",
     "language": "en",
     "duration": 0.0,
     "text": "transcribed text here...",
     "words": []
   }
   ```

### Full Test Suite

See `CURL_TEST_COMMANDS.md` section 4 (Audio Transcription) for more examples.

## API Parameters

### Transcription Endpoint

**POST** `/v1/audio/transcriptions`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | File | Yes | - | Audio file to transcribe |
| `model` | string | Yes | - | Model ID (e.g., `openai/whisper-tiny`) |
| `language` | string | No | auto | ISO-639-1 language code |
| `prompt` | string | No | - | Optional text to guide transcription |
| `response_format` | string | No | `json` | `json`, `text`, or `verbose_json` |
| `temperature` | float | No | 0.0 | Sampling temperature (0.0 - 1.0) |

### Translation Endpoint

**POST** `/v1/audio/translations`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | File | Yes | - | Audio file to translate |
| `model` | string | Yes | - | Model ID (e.g., `openai/whisper-tiny`) |
| `prompt` | string | No | - | Optional text to guide translation |
| `response_format` | string | No | `json` | `json` or `text` |
| `temperature` | float | No | 0.0 | Sampling temperature (0.0 - 1.0) |

## Supported Audio Formats

The server accepts any audio format supported by the underlying model (typically Whisper):

- ✅ MP3
- ✅ WAV
- ✅ M4A
- ✅ FLAC
- ✅ OGG
- ✅ WEBM

## Future Enhancements

- [ ] Add support for `timestamp_granularities` parameter
- [ ] Calculate and return actual audio duration
- [ ] Add support for speaker diarization
- [ ] Batch transcription support
- [ ] Streaming transcription for long audio files

## Related Files

- `server.py` - Audio endpoint implementations
- `models/audio_model.py` - AudioModel class
- `CURL_TEST_COMMANDS.md` - Complete test examples
- `SERVER_TESTING_GUIDE.md` - Server testing documentation
