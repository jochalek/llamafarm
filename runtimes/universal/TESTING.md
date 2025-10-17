# Testing Guide - Universal Runtime

Quick reference for running tests in the Universal Runtime.

## Quick Start

```bash
# Run all fast tests (recommended for development)
./run_tests.sh

# Run all tests including slow model downloads
./run_tests.sh --slow

# Run with coverage report
./run_tests.sh --coverage

# Run verbose
./run_tests.sh -v

# Run specific test file
./run_tests.sh tests/test_encoder_model.py
```

## Test Organization

### Fast Tests (< 1 minute)
These use tiny test models and run quickly:
- `test_causal_lm_model.py` - Text generation
- `test_encoder_model.py` - Embeddings
- `test_diffusion_model.py` - Image generation (tiny model)

### Slow Tests (5-10 minutes)
These download larger models:
- `test_vision_model.py` - CLIP tests (marked `@pytest.mark.slow`)
- `test_audio_model.py` - Whisper tests (marked `@pytest.mark.slow`)
- `test_multimodal_model.py` - BLIP tests (marked `@pytest.mark.slow`)

## Common Commands

### Development Workflow
```bash
# During development, run fast tests only
./run_tests.sh

# Before committing, run all tests
./run_tests.sh --slow --coverage
```

### Using pytest directly
```bash
# Activate environment
cd runtimes/universal

# Run all fast tests (use python -m pytest to ensure uv environment)
uv run python -m pytest tests/ -m "not slow"

# Run all tests
uv run python -m pytest tests/

# Run specific test
uv run python -m pytest tests/test_encoder_model.py::test_encoder_embed_single -v

# Run with specific marker
uv run python -m pytest tests/ -m "slow"

# Run with pattern matching
uv run python -m pytest tests/ -k "embed"
```

## Test Markers

| Marker | Description | Usage |
|--------|-------------|-------|
| `slow` | Tests requiring large model downloads | `-m "not slow"` to skip |
| `asyncio` | Async tests (auto-handled) | N/A |

## Continuous Integration

### Fast CI (Pull Requests)
```bash
# Run only fast tests
uv run python -m pytest tests/ -m "not slow" --tb=short
```

### Full CI (Main Branch / Nightly)
```bash
# Run all tests with coverage
uv run python -m pytest tests/ --cov=models --cov-report=xml
```

## Test Coverage

Generate coverage report:
```bash
./run_tests.sh --coverage
open htmlcov/index.html  # View in browser
```

Or with pytest directly:
```bash
uv run pytest tests/ --cov=models --cov-report=html
```

## Test Output

### Successful Run
```
================================================
Universal Runtime Test Suite
================================================

Running fast tests only (use --slow to include all tests)

Command: uv run pytest tests/ -m 'not slow'

================================ test session starts =================================
tests/test_causal_lm_model.py::test_causal_lm_load PASSED                     [ 10%]
tests/test_causal_lm_model.py::test_causal_lm_generate PASSED                 [ 20%]
tests/test_encoder_model.py::test_encoder_load PASSED                         [ 30%]
tests/test_encoder_model.py::test_encoder_embed_single PASSED                 [ 40%]
...
================================ 20 passed in 45.23s =================================

✅ All tests passed!
```

### With Coverage
```
---------- coverage: platform darwin, python 3.11.8 -----------
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
models/__init__.py                   7      0   100%
models/base.py                      30      2    93%   45-46
models/causal_lm_model.py           55      3    95%   78-80
models/encoder_model.py             89      5    94%   120-124
models/diffusion_model.py          120      8    93%   180-187
models/vision_model.py             145     12    92%   ...
models/audio_model.py               95      8    92%   ...
models/multimodal_model.py         132     15    89%   ...
---------------------------------------------------------------
TOTAL                              673     53    92%

📊 Coverage report generated in htmlcov/index.html
```

## Debugging Failed Tests

### Run single test with full output
```bash
uv run python -m pytest tests/test_encoder_model.py::test_encoder_embed_single -vv -s
```

### Show captured logs
```bash
uv run python -m pytest tests/ --log-cli-level=DEBUG
```

### Drop into debugger on failure
```bash
uv run python -m pytest tests/ --pdb
```

## Writing New Tests

Example test structure:
```python
import pytest
from models.your_model import YourModel

@pytest.mark.asyncio
async def test_your_feature(device, test_model_ids):
    """Test description."""
    # Arrange
    model = YourModel(test_model_ids["your_type"], device)
    await model.load()

    # Act
    result = await model.your_method()

    # Assert
    assert result is not None
    assert isinstance(result, ExpectedType)
```

## Troubleshooting

### Import errors
```bash
# Ensure you're in the runtime directory
cd runtimes/universal

# Sync dependencies
uv sync
```

### Model download failures
```bash
# Check internet connection
ping huggingface.co

# Try downloading manually
uv run python -c "from transformers import AutoModel; AutoModel.from_pretrained('test-model-id')"
```

### Out of memory
```bash
# Run tests one at a time
uv run python -m pytest tests/ -m "not slow" -n 1

# Or skip specific tests
uv run python -m pytest tests/ -m "not slow and not vision"
```

### Slow test execution
```bash
# Skip slow tests during development
./run_tests.sh

# Or use pytest-xdist for parallel execution (if installed)
uv run python -m pytest tests/ -n auto
```

## Test Dependencies

Core dependencies (automatically installed with `uv sync`):
- `pytest` - Test framework
- `pytest-asyncio` - Async support
- `torch` - Deep learning framework
- `transformers` - HuggingFace models
- `diffusers` - Diffusion models
- `pillow` - Image processing
- `numpy` - Numerical computing

Optional (for enhanced testing):
- `pytest-cov` - Coverage reporting
- `pytest-timeout` - Test timeouts
- `pytest-xdist` - Parallel execution
- `pytest-benchmark` - Performance testing

## Performance Benchmarks

Expected test execution times (M2 Mac):

| Test Suite | Fast Mode | Full Mode |
|------------|-----------|-----------|
| CausalLM | ~10s | ~10s |
| Encoder | ~15s | ~15s |
| Diffusion | ~30s | ~30s |
| Vision | ~5s | ~60s (CLIP) |
| Audio | N/A | ~120s (Whisper) |
| Multimodal | N/A | ~180s (BLIP) |
| **Total** | **~60s** | **~450s** |

## CI/CD Integration Examples

### GitHub Actions
```yaml
- name: Run fast tests
  run: |
    cd runtimes/universal
    uv run python -m pytest tests/ -m "not slow"

- name: Run all tests (nightly)
  run: |
    cd runtimes/universal
    uv run python -m pytest tests/ --cov=models
```

### GitLab CI
```yaml
test:fast:
  script:
    - cd runtimes/universal
    - uv run python -m pytest tests/ -m "not slow"

test:full:
  script:
    - cd runtimes/universal
    - uv run python -m pytest tests/ --cov=models
  only:
    - main
```

## Support

For issues or questions:
1. Check test output for specific errors
2. Review test logs in `.pytest_cache/`
3. Consult test documentation in `tests/README.md`
4. Report bugs with full test output
