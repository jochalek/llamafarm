# Model Pull/Download Implementation

**Status:** ✅ Complete
**Date:** 2025-10-02
**Branch:** `feat/multi-model`

---

## 🎯 Overview

Added comprehensive model pull/download functionality to LlamaFarm that supports:
- Lemonade models with GGUF checkpoints and variants
- Ollama model pulls
- Configuration-based model metadata via `model_info`
- CLI command: `lf models pull`
- API endpoint: `POST /v1/models/{namespace}/{project}/models/pull`

---

## 📝 What Was Implemented

### 1. **API Enhancements**

#### Server-Side Provider Update
**File:** `server/services/providers/lemonade_model_provider.py`

Added support for `variant` parameter in Lemonade model pulls:
```python
async def pull_model(self, model_name: str, **options) -> AsyncIterator[PullProgress]:
    """
    Args:
        checkpoint: HuggingFace checkpoint (e.g., "google/gemma-3-4b-it-qat-q4_0-gguf")
        variant: Variant/quantization (e.g., "Q4_0", "Q8_0") - appended to checkpoint
        recipe: Recipe name (llamacpp, transformers, onnx)
        vision: bool - Vision model support
        reasoning: bool - Reasoning capabilities
        mmproj: str - Multimodal projector file
    """
    # Automatically appends variant to checkpoint if provided separately
    if "variant" in options and ":" not in checkpoint:
        checkpoint = f"{checkpoint}:{options['variant']}"
```

**Key Feature:** Handles both formats:
- `checkpoint="google/gemma-3-4b-it-qat-q4_0-gguf:Q4_0"` (explicit)
- `checkpoint="google/gemma-3-4b-it-qat-q4_0-gguf"` + `variant="Q4_0"` (separate)

#### API Endpoint Update
**File:** `server/api/routers/models/models.py`

Updated `PullModelRequest` with new `variant` field:
```python
class PullModelRequest(BaseModel):
    model_name: str
    provider: str
    checkpoint: str | None = None
    variant: str | None = None  # NEW
    recipe: str | None = None
    vision: bool = False
    reasoning: bool = False
    mmproj: str | None = None
    insecure: bool = False
```

---

### 2. **CLI Command**

**File:** `cli/cmd/models.go`

Added `lf models pull` command with full flag support:

```bash
lf models pull MODEL_NAME --provider PROVIDER [flags]
```

**Flags:**
- `--provider` (required): ollama, lemonade, etc.
- `--checkpoint`: HuggingFace checkpoint path
- `--variant`: Quantization variant (Q4_0, Q8_0, etc.)
- `--recipe`: Lemonade recipe (llamacpp, transformers, onnx)
- `--vision`: Mark as vision model
- `--reasoning`: Mark as reasoning model
- `--mmproj`: Multimodal projector file
- `--insecure`: Allow insecure connections (Ollama)
- `--project`: Override project (namespace/project)

**Features:**
- Streams progress updates in real-time (NDJSON format)
- Shows success/error messages
- Works with current project context or explicit project flag

---

### 3. **Configuration Schema**

**File:** `config/schema.yaml`

Added `model_info` section to model configurations:

```yaml
runtime:
  models:
    - name: my-model
      provider: lemonade
      model: user.my-model

      # NEW: Model pull metadata
      model_info:
        checkpoint: google/gemma-3-4b-it-qat-q4_0-gguf
        variant: Q4_0
        recipe: llamacpp
        reasoning: false
        mmproj_file: null

      lemonade:
        backend: llamacpp
        port: 11534
        context_size: 32768
```

**Purpose:**
- Documents how to download/pull each model
- Makes it easy to share reproducible configurations
- Future: Could be used to auto-pull models on startup

---

## 🚀 Usage Examples

### Example 1: Pull Gemma 3 4B Model (Lemonade)

```bash
# Using CLI with all parameters
lf models pull user.gemma-3-4b-it \
  --provider lemonade \
  --checkpoint google/gemma-3-4b-it-qat-q4_0-gguf \
  --variant Q4_0 \
  --recipe llamacpp

# Using API
curl -X POST 'http://localhost:8000/v1/models/default/test-project-1/models/pull' \
  -H 'Content-Type: application/json' \
  -d '{
    "model_name": "user.gemma-3-4b-it",
    "provider": "lemonade",
    "checkpoint": "google/gemma-3-4b-it-qat-q4_0-gguf",
    "variant": "Q4_0",
    "recipe": "llamacpp"
  }'
```

### Example 2: Pull Ollama Model

```bash
lf models pull llama3:70b --provider ollama

# With insecure flag
lf models pull llama3:70b --provider ollama --insecure
```

### Example 3: Pull Registered Lemonade Model

```bash
# For models already in Lemonade's registry
lf models pull Qwen2.5-VL-7B-Instruct-GGUF --provider lemonade
```

---

## 📋 Configuration Example

**File:** `examples/model-pull-example.yaml`

Complete example showing `model_info` usage:

```yaml
version: v1
name: model-pull-example
namespace: default

runtime:
  default_model: gemma-4b

  models:
    - name: gemma-4b
      description: "Google Gemma 3 4B model with Q4_0 quantization"
      provider: lemonade
      model: user.gemma-3-4b-it
      prompt_format: unstructured

      # Model pull configuration
      model_info:
        checkpoint: google/gemma-3-4b-it-qat-q4_0-gguf
        variant: Q4_0
        recipe: llamacpp

      lemonade:
        backend: llamacpp
        port: 11534
        context_size: 32768

    - name: qwen-vision
      description: "Qwen 2.5 VL 7B vision model"
      provider: lemonade
      model: Qwen2.5-VL-7B-Instruct-GGUF
      prompt_format: image
      vision: true

      model_info:
        recipe: llamacpp

      lemonade:
        backend: llamacpp
        port: 11535
        context_size: 65536

      vision_config:
        max_tokens: 1024
        resize_images: true

prompts:
  - role: system
    content: "You are a helpful AI assistant."
```

---

## 🔧 Technical Details

### Lemonade Model Naming Convention

Lemonade requires specific naming for custom models:

```bash
# CORRECT: User namespace required
user.gemma-3-4b-it

# WRONG: No namespace
gemma-3-4b-it
```

### Checkpoint Variant Format

For GGUF models, Lemonade requires the variant in the checkpoint:

```bash
# Format: CHECKPOINT:VARIANT
google/gemma-3-4b-it-qat-q4_0-gguf:Q4_0
```

Our implementation handles both:
1. **Explicit:** `checkpoint="repo:variant"`
2. **Separate:** `checkpoint="repo"` + `variant="Q4_0"`

### Progress Streaming

API returns NDJSON (newline-delimited JSON) for streaming:

```json
{"status": "downloading", "message": "Downloading model...", "completed": 1024, "total": 4096}
{"status": "success", "message": "Model pulled successfully"}
```

CLI decodes this and shows progress in real-time.

---

## 📂 Files Modified

### Configuration
- ✏️ `config/schema.yaml` - Added `model_info` section
- 🔄 `config/datamodel.py` - Auto-generated with new fields
- 🔄 `cli/cmd/config/schema.yaml` - Auto-copied schema

### Backend (Python)
- ✏️ `server/services/providers/lemonade_model_provider.py` - Added `variant` support
- ✏️ `server/api/routers/models/models.py` - Added `variant` to request model

### CLI (Go)
- ✏️ `cli/cmd/models.go` - Added `models pull` command with all flags

### Examples & Documentation
- ✨ `examples/model-pull-example.yaml` - Complete configuration example
- ✨ `.claude/MODEL_PULL_IMPLEMENTATION.md` - This document

**Legend:** ✏️ = Modified, ✨ = New file, 🔄 = Auto-generated

---

## ✅ Testing

### CLI Testing

```bash
# Check help
./lf models pull --help

# Pull Gemma model
./lf models pull user.gemma-3-4b-it \
  --provider lemonade \
  --checkpoint google/gemma-3-4b-it-qat-q4_0-gguf \
  --variant Q4_0 \
  --recipe llamacpp
```

### API Testing

```bash
# Test endpoint
curl -X POST 'http://localhost:8000/v1/models/default/test-project-1/models/pull' \
  -H 'Content-Type: application/json' \
  -d '{
    "model_name": "user.gemma-3-4b-it",
    "provider": "lemonade",
    "checkpoint": "google/gemma-3-4b-it-qat-q4_0-gguf",
    "variant": "Q4_0",
    "recipe": "llamacpp"
  }'
```

---

## 🎯 Benefits

1. **Unified Interface:** Same API/CLI for Ollama, Lemonade, and future providers
2. **Configuration as Code:** `model_info` documents how to pull each model
3. **User-Friendly:** Simple CLI command with clear flags
4. **Streaming Progress:** Real-time feedback on download progress
5. **Flexible:** Supports both registered and custom models
6. **Extensible:** Easy to add new providers (vLLM, TGI, etc.)

---

## 🔮 Future Enhancements

1. **Auto-Pull on Startup:** Read `model_info` and auto-pull missing models
2. **Model Registry:** Cache of available models with metadata
3. **Batch Pull:** Pull multiple models in parallel
4. **Pull from Config:** `lf models pull --from-config` to pull all models listed
5. **Progress Bars:** Better visual progress in CLI
6. **Model Validation:** Verify model works after pull

---

## 📚 Related Documentation

- Model Management API: `server/api/routers/models/models.py`
- Provider Pattern: `.claude/LEMONADE_INTEGRATION_STATUS.md`
- Multi-Model Config: `.claude/MULTI_MODEL_IMPLEMENTATION_PLAN.md`
- Lemonade Docs: https://lemonade-server.ai/

---

**Implementation Complete** ✅

All changes tested and working. CLI command available via `./lf models pull`.
