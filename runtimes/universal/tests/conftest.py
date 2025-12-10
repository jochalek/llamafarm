"""
Shared pytest fixtures for Universal Runtime tests.
"""

import pytest
import torch


@pytest.fixture(scope="session")
def device():
    """Get optimal device for testing."""
    if torch.cuda.is_available():
        return "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"


@pytest.fixture
def sample_text():
    """Sample text for testing."""
    return "Hello, this is a test sentence."


@pytest.fixture
def sample_texts():
    """Multiple sample texts for batch testing."""
    return [
        "Hello, this is a test sentence.",
        "Machine learning is fascinating.",
        "The quick brown fox jumps over the lazy dog.",
    ]


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        {"role": "user", "content": "What is 2+2?"},
    ]


# Model IDs for testing (using smallest/fastest models)
TEST_MODELS = {
    "language": "hf-internal-testing/tiny-random-gpt2",
    "encoder": "sentence-transformers/all-MiniLM-L6-v2",
    "vision_detect": "yolo11n",
    "vision_segment": "yolo11n-seg",
    "vision_classify": "yolo11n-cls",
    "vision_pose": "yolo11n-pose",
}


@pytest.fixture
def test_model_ids():
    """Return test model IDs."""
    return TEST_MODELS


# Vision-specific fixtures
@pytest.fixture
def sample_image_array():
    """Create a sample RGB image as numpy array for vision tests."""
    import numpy as np

    # Create a 640x480 image with some basic patterns
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[100:300, 200:400] = [255, 255, 255]  # White rectangle
    img[150:250, 250:350] = [255, 0, 0]  # Red square
    return img


@pytest.fixture
def sample_image_bytes(sample_image_array):
    """Convert sample image to bytes (JPEG format)."""
    import io

    from PIL import Image

    img = Image.fromarray(sample_image_array)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def sample_image_base64(sample_image_bytes):
    """Convert sample image to base64 string."""
    import base64

    return base64.b64encode(sample_image_bytes).decode("utf-8")
