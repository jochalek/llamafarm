# Testing Fixes Summary

This document summarizes the fixes applied to resolve test execution issues.

## Problems Encountered

### 1. ModuleNotFoundError: No module named 'diffusers'
**Symptom:** Tests failed to import models due to missing dependencies
```
E   ModuleNotFoundError: No module named 'diffusers'
```

**Root Cause:** `uv run pytest` was using system Python from Miniconda instead of the uv-managed environment

### 2. Asyncio marker not registered
**Symptom:**
```
ERROR: 'asyncio' not found in `markers` configuration option
```

**Root Cause:** Missing asyncio marker registration in pytest.ini

### 3. Unknown config option: asyncio_mode
**Symptom:**
```
PytestConfigWarning: Unknown config option: asyncio_mode
```

**Root Cause:** pytest-asyncio wasn't being picked up properly

## Solutions Applied

### 1. Fixed pytest command
**Changed from:** `uv run pytest`
**Changed to:** `uv run python -m pytest`

**Why:** Using `python -m pytest` ensures pytest runs within the uv-managed Python environment, not system Python.

### 2. Updated pytest.ini
Added asyncio marker registration:
```ini
markers =
    asyncio: marks tests as async (auto-applied by pytest-asyncio)
    slow: marks tests as slow (deselect with '-m "not slow"')
```

### 3. Added missing dev dependencies
Updated `pyproject.toml`:
```toml
[tool.uv]
dev-dependencies = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "pytest-timeout>=2.1.0",
    "httpx>=0.24.0",
    "numpy>=1.24.0",  # Added for audio tests
]
```

### 4. Fixed run_tests.sh script
**Changed from:** String-based command building
**Changed to:** Array-based command building

**Before:**
```bash
PYTEST_CMD="uv run pytest"
PYTEST_CMD="$PYTEST_CMD -m 'not slow'"
$PYTEST_CMD
```

**After:**
```bash
PYTEST_CMD=(uv run python -m pytest "$TEST_PATH")
PYTEST_CMD+=(-m "not slow")
"${PYTEST_CMD[@]}"
```

**Why:** Proper array handling prevents shell quoting issues

## Verification

After fixes, all 25 fast tests pass successfully:

```bash
./run_tests.sh

# Output:
# ✅ All tests passed!
# 25 passed, 21 deselected, 5 warnings in 16.28s
```

## Usage Examples

### Correct way to run tests

```bash
# Fast tests (recommended for development)
./run_tests.sh

# All tests including slow model downloads
./run_tests.sh --slow

# With coverage
./run_tests.sh --coverage

# Using pytest directly
uv run python -m pytest tests/ -m "not slow"

# Specific test
uv run python -m pytest tests/test_encoder_model.py::test_encoder_embed_single -v
```

### ❌ INCORRECT way (will use wrong Python)

```bash
# DON'T DO THIS - uses system Python
uv run pytest tests/

# DON'T DO THIS - uses system pytest
pytest tests/
```

## Key Takeaways

1. **Always use `uv run python -m pytest`** instead of `uv run pytest`
2. **Ensure pytest-asyncio is installed** for async test support
3. **Register custom markers** in pytest.ini
4. **Use bash arrays** for command building to handle arguments properly
5. **Deactivate conda/virtualenv** if uv commands pick wrong Python

## Files Modified

- ✅ `pytest.ini` - Added asyncio marker, fixed configuration
- ✅ `pyproject.toml` - Added numpy and other dev dependencies
- ✅ `run_tests.sh` - Fixed command building with arrays
- ✅ `TESTING.md` - Updated all examples to use correct commands
- ✅ `tests/README.md` - Updated all examples to use correct commands

## Test Results

### Fast Tests (25 tests, ~16 seconds)
- ✅ CausalLM: 5 tests
- ✅ Encoder: 7 tests
- ✅ Diffusion: 7 tests
- ✅ Vision: 6 tests

### Slow Tests (21 tests, marked as @pytest.mark.slow)
- Audio: 8 tests (Whisper)
- Vision CLIP: 3 tests
- Multimodal: 9 tests (BLIP)
- 1 additional vision test

## Environment Details

- **Python:** 3.12.2 (uv-managed)
- **pytest:** 8.4.2
- **pytest-asyncio:** 1.2.0
- **Platform:** macOS (darwin)
- **Virtual Environment:** `.venv/` (uv-managed)

## Troubleshooting

If tests still fail:

1. **Check Python being used:**
   ```bash
   uv run python --version
   uv run which python
   ```

2. **Verify dependencies:**
   ```bash
   uv pip list | grep -E "(pytest|transformers|diffusers)"
   ```

3. **Resync environment:**
   ```bash
   uv sync --reinstall
   ```

4. **Deactivate conda if active:**
   ```bash
   conda deactivate
   ```

5. **Clean pytest cache:**
   ```bash
   rm -rf .pytest_cache
   ```

## CI/CD Recommendations

For continuous integration, use:

```yaml
# GitHub Actions example
- name: Install dependencies
  run: |
    cd runtimes/universal
    uv sync

- name: Run tests
  run: |
    cd runtimes/universal
    uv run python -m pytest tests/ -m "not slow" --tb=short
```

This ensures tests run in the correct environment across all platforms.
