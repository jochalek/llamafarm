"""Image processing utilities for vision models."""

import base64
import io
from typing import Optional

from PIL import Image


def resize_base64_image(
    data_url: str,
    max_dimension: int = 768,
    max_size_kb: int = 500,
    quality: int = 85,
) -> tuple[str, bool]:
    """
    Resize a base64-encoded image if it's too large.

    Args:
        data_url: Base64 data URL (data:image/png;base64,...)
        max_dimension: Maximum width or height in pixels
        max_size_kb: Maximum size in KB before resizing
        quality: JPEG quality for re-encoding (1-95)

    Returns:
        Tuple of (new_data_url, was_resized)
    """
    # Parse data URL
    if not data_url.startswith("data:"):
        return data_url, False

    try:
        # Extract MIME type and base64 data
        header, b64_data = data_url.split(",", 1)
        mime_type = header.split(";")[0].replace("data:", "")

        # Decode base64
        image_bytes = base64.b64decode(b64_data)
        original_size_kb = len(image_bytes) / 1024

        # Check if resize is needed
        if original_size_kb <= max_size_kb:
            return data_url, False

        # Open image with PIL
        img = Image.open(io.BytesIO(image_bytes))

        # Get original dimensions
        width, height = img.size

        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            if width > max_dimension:
                new_width = max_dimension
                new_height = int((height * max_dimension) / width)
            else:
                return data_url, False  # No resize needed
        else:
            if height > max_dimension:
                new_height = max_dimension
                new_width = int((width * max_dimension) / height)
            else:
                return data_url, False  # No resize needed

        # Resize image with high-quality resampling
        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (for JPEG)
        if resized_img.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", resized_img.size, (255, 255, 255))
            if resized_img.mode == "P":
                resized_img = resized_img.convert("RGBA")
            background.paste(resized_img, mask=resized_img.split()[-1] if resized_img.mode in ("RGBA", "LA") else None)
            resized_img = background

        # Re-encode image
        output_buffer = io.BytesIO()

        # Determine format from MIME type
        if "jpeg" in mime_type or "jpg" in mime_type:
            resized_img.save(output_buffer, format="JPEG", quality=quality, optimize=True)
            output_mime = "image/jpeg"
        elif "png" in mime_type:
            resized_img.save(output_buffer, format="PNG", optimize=True)
            output_mime = "image/png"
        elif "gif" in mime_type:
            resized_img.save(output_buffer, format="GIF", optimize=True)
            output_mime = "image/gif"
        else:
            # Default to JPEG for unknown formats
            resized_img.save(output_buffer, format="JPEG", quality=quality, optimize=True)
            output_mime = "image/jpeg"

        # Encode to base64
        resized_bytes = output_buffer.getvalue()
        resized_b64 = base64.b64encode(resized_bytes).decode("utf-8")

        # Build new data URL
        new_data_url = f"data:{output_mime};base64,{resized_b64}"

        # Log resize stats
        new_size_kb = len(resized_bytes) / 1024
        reduction = ((original_size_kb - new_size_kb) / original_size_kb) * 100

        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"Resized image: {original_size_kb:.1f}KB -> {new_size_kb:.1f}KB "
            f"({width}x{height} -> {new_width}x{new_height}), {reduction:.0f}% reduction"
        )

        return new_data_url, True

    except Exception as e:
        # If resize fails, return original
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Image resize failed: {e}, using original")
        return data_url, False
