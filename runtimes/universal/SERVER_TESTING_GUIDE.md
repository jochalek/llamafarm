# Server Testing Guide

Complete guide for testing the Universal Runtime server endpoints.

## Quick Start

### 1. Start the Server
```bash
cd runtimes/universal
uv run uvicorn server:app --host 0.0.0.0 --port 11540 --reload
```

### 2. Run Quick Test
```bash
./quick_test.sh
```

This will test:
- ✅ Health check
- ✅ Text embeddings (single & batch)
- ✅ Text generation (normal & streaming)
- ✅ Image generation

**Expected time:** ~90 seconds

---

## Testing Resources

We've created three complementary resources for testing:

### 1. **`quick_test.sh`** - Automated Quick Tests
**Purpose:** Fast verification that core functionality works
**Time:** ~90 seconds
**Requirements:** None (no external files needed)

```bash
./quick_test.sh
```

**Tests:**
- Health check
- Single & batch embeddings
- Text generation
- Streaming
- Image generation

---

### 2. **`test_server.sh`** - Comprehensive Test Suite
**Purpose:** Full endpoint coverage with all model types
**Time:** ~5 minutes
**Requirements:** Optional test files for audio/vision

```bash
./test_server.sh
```

**Tests:**
- All quick tests
- Audio transcription (if test_audio.mp3 exists)
- Image classification (if test_image.jpg exists)
- Multimodal captioning
- All endpoints with realistic examples

**Setup test files:**
```bash
# Download test audio
curl -o test_audio.mp3 "https://www2.cs.uic.edu/~i101/SoundFiles/StarWars60.wav"

# Download test image
curl -o test_image.jpg "https://picsum.photos/512/512"

# Then run full suite
./test_server.sh
```

---

### 3. **`MANUAL_TEST_EXAMPLES.md`** - Copy-Paste Commands
**Purpose:** Manual testing with full control
**Format:** Ready-to-use curl commands

Open the file and copy/paste commands for:
- Text generation (various configs)
- Embeddings (RAG workflows)
- Image generation (with prompts, seeds, etc.)
- Audio transcription
- Image classification
- Multimodal (captioning, VQA)

---

### 4. **`CURL_TEST_COMMANDS.md`** - Complete Reference
**Purpose:** Comprehensive documentation of all endpoints
**Format:** Organized by endpoint type with examples

Includes:
- All endpoint specifications
- Request/response formats
- Complete workflow examples
- Performance testing commands
- Debugging tips

---

## Testing Workflows

### Workflow 1: Basic Functionality (30 seconds)
```bash
# Just verify server is working
./quick_test.sh
```

### Workflow 2: Development Testing (2 minutes)
```bash
# Test specific endpoint
curl -X POST http://localhost:11540/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "input": "Test text"
  }' | jq
```

### Workflow 3: Full Validation (5 minutes)
```bash
# Download test files
curl -o test_audio.mp3 "https://www2.cs.uic.edu/~i101/SoundFiles/StarWars60.wav"
curl -o test_image.jpg "https://picsum.photos/512/512"

# Run full suite
./test_server.sh
```

### Workflow 4: Manual Exploration
```bash
# Open docs and try different models
open http://localhost:11540/docs

# Or use manual examples
cat MANUAL_TEST_EXAMPLES.md
```

---

## Testing by Model Type

### CausalLM (Text Generation)
```bash
# Quick test
curl -X POST http://localhost:11540/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-0.5B-Instruct",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 10
  }' | jq -r '.choices[0].message.content'
```

### EncoderModel (Embeddings)
```bash
# Quick test
curl -X POST http://localhost:11540/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "input": "Test"
  }' | jq '.data[0].embedding | length'
```

### DiffusionModel (Image Generation)
```bash
# Quick test (~30s)
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1-base",
    "prompt": "A red circle",
    "size": "512x512",
    "num_inference_steps": 15
  }' | jq -r '.data[0].b64_json' | base64 -d > test.png
```

### AudioModel (Transcription)
```bash
# Requires audio file
curl -o test.mp3 "https://www2.cs.uic.edu/~i101/SoundFiles/StarWars60.wav"

curl -X POST http://localhost:11540/v1/audio/transcriptions \
  -F "file=@test.mp3" \
  -F "model=openai/whisper-tiny" | jq -r '.text'
```

### VisionModel (Classification)
```bash
# Requires image
curl -o cat.jpg "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=512"

IMAGE_BASE64=$(base64 -i cat.jpg)
curl -X POST http://localhost:11540/v1/vision/classify \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"google/vit-base-patch16-224\", \"image\": \"$IMAGE_BASE64\"}" \
  | jq '.predictions[0]'
```

### MultimodalModel (Captioning/VQA)
```bash
# Requires image
IMAGE_BASE64=$(base64 -i cat.jpg)

curl -X POST http://localhost:11540/v1/multimodal/caption \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"Salesforce/blip-image-captioning-base\", \"image\": \"$IMAGE_BASE64\"}" \
  | jq -r '.caption'
```

---

## Common Test Scenarios

### Scenario 1: RAG System Testing
```bash
# 1. Embed documents
curl -X POST http://localhost:11540/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "input": ["Doc 1", "Doc 2", "Doc 3"]
  }' > docs.json

# 2. Embed query
curl -X POST http://localhost:11540/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "input": "My question"
  }' > query.json

# 3. Generate answer with context
curl -X POST http://localhost:11540/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-0.5B-Instruct",
    "messages": [
      {"role": "system", "content": "Context: [retrieved docs]"},
      {"role": "user", "content": "Answer based on context"}
    ]
  }' | jq
```

### Scenario 2: Image Analysis Pipeline
```bash
# Generate image → Caption it → Generate story

# 1. Generate
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"model": "stabilityai/stable-diffusion-2-1-base", "prompt": "A cat"}' \
  | jq -r '.data[0].b64_json' | base64 -d > cat.png

# 2. Caption
IMAGE=$(base64 -i cat.png)
CAPTION=$(curl -s -X POST http://localhost:11540/v1/multimodal/caption \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"Salesforce/blip-image-captioning-base\", \"image\": \"$IMAGE\"}" \
  | jq -r '.caption')

# 3. Story
curl -X POST http://localhost:11540/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"Qwen/Qwen2.5-0.5B-Instruct\", \"messages\": [{\"role\": \"user\", \"content\": \"Story about: $CAPTION\"}]}" \
  | jq -r '.choices[0].message.content'
```

---

## Performance Testing

### Latency Test
```bash
# Single request
time curl -s -X POST http://localhost:11540/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "sentence-transformers/all-MiniLM-L6-v2", "input": "Test"}' \
  > /dev/null
```

### Throughput Test
```bash
# 100 requests
time for i in {1..100}; do
  curl -s -X POST http://localhost:11540/v1/embeddings \
    -H "Content-Type: application/json" \
    -d '{"model": "sentence-transformers/all-MiniLM-L6-v2", "input": "Test"}' \
    > /dev/null
done
```

### Concurrent Requests
```bash
# 10 parallel requests
for i in {1..10}; do
  curl -s -X POST http://localhost:11540/v1/embeddings \
    -H "Content-Type: application/json" \
    -d '{"model": "sentence-transformers/all-MiniLM-L6-v2", "input": "Test"}' &
done
wait
```

---

## Debugging

### Check Server Health
```bash
curl http://localhost:11540/health | jq
```

### View Loaded Models
```bash
curl http://localhost:11540/models | jq
```

### Test with Verbose Output
```bash
curl -v -X POST http://localhost:11540/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "sentence-transformers/all-MiniLM-L6-v2", "input": "Test"}'
```

### Check Server Logs
```bash
# In the terminal where server is running
# Watch for errors or warnings
```

---

## Test File Overview

| File | Purpose | Time | Requirements |
|------|---------|------|--------------|
| `quick_test.sh` | Fast verification | 90s | None |
| `test_server.sh` | Full coverage | 5min | Optional files |
| `MANUAL_TEST_EXAMPLES.md` | Copy-paste commands | N/A | None |
| `CURL_TEST_COMMANDS.md` | Complete reference | N/A | None |

---

## Recommended Testing Flow

### First Time Setup
1. Start server: `uv run uvicorn server:app --reload`
2. Quick test: `./quick_test.sh`
3. Download test files
4. Full test: `./test_server.sh`
5. Explore manual examples

### Daily Development
1. Start server
2. Quick test to verify
3. Manual testing of specific endpoints
4. Check docs: http://localhost:11540/docs

### Before Deployment
1. Run full test suite
2. Performance testing
3. Test all model types
4. Verify error handling

---

## Success Criteria

✅ **Quick Test Passes**
- Health check OK
- Embeddings work
- Text generation works
- Image generation works

✅ **Full Test Passes**
- All model types load
- All endpoints respond
- No errors or crashes
- Performance acceptable

✅ **Manual Tests Pass**
- Can test specific scenarios
- API responses correct format
- Models load on demand
- Caching works

---

## Troubleshooting

### Server won't start
```bash
# Check port
lsof -i :11540

# Kill existing process
pkill -f uvicorn

# Restart
uv run uvicorn server:app --reload
```

### Tests fail
```bash
# Check server is running
curl http://localhost:11540/health

# Check logs for errors
# Review server terminal output
```

### Slow performance
```bash
# Check device
curl http://localhost:11540/health | jq '.device'

# Should show: "cuda", "mps", or "cpu"
```

---

## Next Steps

After testing:
1. ✅ Review `PRODUCTION_READY_CHECKLIST.md` for deployment
2. ✅ See `ONNX_IMPLEMENTATION_GUIDE.md` for optimization
3. ✅ Check `TEST_FIXES_SUMMARY.md` for implementation details
4. ✅ Explore API docs at http://localhost:11540/docs

---

## Summary

**You have 4 ways to test:**

1. **Automated Quick** → `./quick_test.sh` (90s)
2. **Automated Full** → `./test_server.sh` (5min)
3. **Manual Commands** → `MANUAL_TEST_EXAMPLES.md`
4. **Complete Reference** → `CURL_TEST_COMMANDS.md`

**Start here:** `./quick_test.sh`

Happy testing! 🚀
