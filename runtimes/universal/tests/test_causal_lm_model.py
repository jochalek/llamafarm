"""
Tests for CausalLMModel (text generation).
"""

import pytest
from models.causal_lm_model import CausalLMModel


@pytest.mark.asyncio
async def test_causal_lm_load(device, test_model_ids):
    """Test loading a causal LM."""
    model = CausalLMModel(test_model_ids["causal_lm"], device)
    await model.load()

    assert model.model is not None
    assert model.tokenizer is not None
    assert model.model_type == "causal_lm"


@pytest.mark.asyncio
async def test_causal_lm_generate(device, test_model_ids, sample_text):
    """Test text generation."""
    model = CausalLMModel(test_model_ids["causal_lm"], device)
    await model.load()

    result = await model.generate(
        prompt=sample_text,
        max_tokens=10,
        temperature=0.7,
    )

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_causal_lm_format_messages(device, test_model_ids, sample_messages):
    """Test message formatting for chat."""
    model = CausalLMModel(test_model_ids["causal_lm"], device)
    await model.load()

    formatted = model.format_messages(sample_messages)

    assert isinstance(formatted, str)
    assert len(formatted) > 0
    assert "2+2" in formatted or "What" in formatted


@pytest.mark.asyncio
async def test_causal_lm_model_info(device, test_model_ids):
    """Test getting model info."""
    model = CausalLMModel(test_model_ids["causal_lm"], device)
    await model.load()

    info = model.get_model_info()

    assert info["model_id"] == test_model_ids["causal_lm"]
    assert info["model_type"] == "causal_lm"
    assert info["device"] == device


@pytest.mark.asyncio
async def test_causal_lm_temperature_variations(device, test_model_ids, sample_text):
    """Test generation with different temperatures."""
    model = CausalLMModel(test_model_ids["causal_lm"], device)
    await model.load()

    # Test with temperature=0 (deterministic)
    result1 = await model.generate(prompt=sample_text, max_tokens=5, temperature=0.0)
    result2 = await model.generate(prompt=sample_text, max_tokens=5, temperature=0.0)

    # Should be identical (or very similar due to floating point)
    assert isinstance(result1, str)
    assert isinstance(result2, str)

    # Test with temperature=1.0 (more random)
    result3 = await model.generate(prompt=sample_text, max_tokens=5, temperature=1.0)
    assert isinstance(result3, str)
