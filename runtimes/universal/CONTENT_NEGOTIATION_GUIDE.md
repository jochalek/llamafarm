# Content Negotiation Guide - Accept Header Support

The Universal Runtime now supports HTTP content negotiation via the `Accept` header for image endpoints. This allows clients to choose whether they want JSON (with base64) or raw binary responses.

## Overview

**Content negotiation** lets clients specify what format they want using the standard `Accept` HTTP header:

- `Accept: application/json` → JSON response with base64-encoded image
- `Accept: image/jpeg` → Raw JPEG bytes (binary, **default for images**)
- `Accept: image/png` → Raw PNG bytes (binary, lossless)
- `Accept: image/webp` → Raw WebP bytes (binary, modern format)
- `Accept: image/*` → Raw JPEG bytes (default binary format)
- `Accept: */*` → Raw JPEG bytes (default binary format)

## Supported Endpoints

All three image generation endpoints support content negotiation:

1. `/v1/images/generations` - Generate images from text
2. `/v1/images/edits` - Edit/inpaint images
3. `/v1/images/variations` - Create image variations

## Important Constraints

**Binary responses are only available for single images.**

- If `n=1` (single image) + `Accept: image/*` → Returns raw PNG bytes
- If `n>1` (multiple images) + `Accept: image/*` → Returns JSON (can't return multiple blobs)

---

## Format Selection

The server automatically determines the output format based on the `Accept` header:

| Accept Header | Format | Quality | Use Case |
|---------------|--------|---------|----------|
| `image/jpeg` | JPEG | 95% | **Default**, best compression for photos |
| `image/png` | PNG | Lossless | Transparency, text, sharp edges |
| `image/webp` | WebP | 90% | Modern browsers, good compression |
| `image/*` or `*/*` | JPEG | 95% | Default fallback |

### Format Characteristics

**JPEG (Default)**
- ✅ Smallest file size (~50-70% smaller than PNG)
- ✅ Best for photographic images
- ✅ Optimized compression
- ❌ No transparency support (RGBA → RGB conversion)
- Quality: 95% (high quality, good compression)

**PNG**
- ✅ Lossless compression
- ✅ Supports transparency (RGBA)
- ✅ Best for images with text or sharp edges
- ❌ Larger file size
- Use when: You need transparency or lossless quality

**WebP**
- ✅ Modern format with excellent compression
- ✅ Supports transparency
- ✅ Smaller than PNG, better quality than JPEG at same size
- ❌ Not supported in all tools
- Quality: 90%

---

## Usage Examples

### Example 1: Get JPEG (Default, Smallest Size)

```bash
# Request with Accept: image/jpeg (or image/* or */* - all default to JPEG)
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/jpeg" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A beautiful sunset",
    "n": 1
  }' > sunset.jpg

# Or just Accept: image/* (defaults to JPEG)
curl ... -H "Accept: image/*" ... > sunset.jpg

# Open directly
open sunset.jpg
```

**Response:**
- Content-Type: `image/jpeg`
- Body: Raw JPEG binary data (smallest size!)
- Headers: `X-Prompt`, `X-Model` with metadata

**Benefits:**
- ✅ Smallest response size (~50-70% smaller than PNG!)
- ✅ No base64 encoding (~33% overhead removed)
- ✅ No decoding needed
- ✅ Direct save to file
- ✅ Best for photographic images

### Example 2: Get PNG (Lossless Quality)

```bash
# Request PNG explicitly for lossless quality
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/png" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A diagram with text",
    "n": 1
  }' > diagram.png

# Open directly
open diagram.png
```

**Response:**
- Content-Type: `image/png`
- Body: Raw PNG binary data
- Lossless compression
- Supports transparency

**When to use PNG:**
- Images with text or sharp edges
- Need transparency (RGBA)
- Lossless quality required

### Example 3: Get WebP (Modern Format)

```bash
# Request WebP for modern browsers
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Accept: image/webp" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A modern web image"
  }' > modern.webp
```

**Response:**
- Content-Type: `image/webp`
- Body: Raw WebP binary data
- Excellent compression with transparency support
- Quality: 90%

---

### Example 4: Get JSON with Base64 (For Multiple Images or Metadata)

```bash
# Request with Accept: application/json (or no header)
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A beautiful sunset",
    "n": 1
  }' | jq -r '.data[0].b64_json' | base64 -d > sunset.png
```

**Response:**
```json
{
  "created": 1697563200,
  "data": [{
    "b64_json": "iVBORw0KGgoAAAANSUhEUgAAA...",
    "revised_prompt": "A beautiful sunset"
  }]
}
```

**Benefits:**
- ✅ Standard OpenAI API format
- ✅ Includes metadata in response
- ✅ Works with multiple images
- ✅ Can parse with JSON tools

---

### Example 3: Multiple Images (Always JSON)

```bash
# Even with Accept: image/png, returns JSON because n>1
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/png" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A beautiful sunset",
    "n": 3
  }' | jq -r '.data[].b64_json' | while read img; do
    echo "$img" | base64 -d > "sunset_${RANDOM}.png"
  done
```

**Why JSON?** HTTP can't return multiple binary files in one response without multipart encoding, so we return JSON.

---

### Example 4: Direct Image Display (Web)

```javascript
// Generate and display image directly
async function generateImage() {
  const response = await fetch('/v1/images/generations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'image/png'  // Request binary
    },
    body: JSON.stringify({
      model: 'stabilityai/stable-diffusion-2-1',
      prompt: 'A beautiful sunset',
      n: 1
    })
  });

  // Get raw PNG blob
  const imageBlob = await response.blob();

  // Display immediately
  const imageUrl = URL.createObjectURL(imageBlob);
  document.getElementById('myImage').src = imageUrl;

  // Download file
  const link = document.createElement('a');
  link.href = imageUrl;
  link.download = 'generated-image.png';
  link.click();
}
```

---

### Example 5: Stream to File

```bash
# Stream directly to file (no intermediate storage)
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/png" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A beautiful sunset"
  }' --output sunset.png

echo "Image saved to sunset.png"
```

---

### Example 6: Pipe to Image Viewer

```bash
# macOS: Generate and view immediately
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/png" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A cat"
  }' | open -f -a Preview

# Linux: Generate and view immediately
curl ... | display -  # ImageMagick
curl ... | feh -  # feh image viewer
```

---

### Example 7: Integration with ImageMagick

```bash
# Generate and resize in one pipeline
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/png" \
  -d '{
    "model": "stabilityai/stable-diffusion-2-1",
    "prompt": "A sunset"
  }' | convert - -resize 256x256 thumbnail.png

# Generate and add watermark
curl ... | convert - \
  -gravity southeast \
  -pointsize 20 \
  -fill white \
  -annotate +10+10 "Generated by AI" \
  watermarked.png
```

---

## Response Headers

When returning binary images, the server includes metadata in headers:

```http
HTTP/1.1 200 OK
Content-Type: image/png
Content-Length: 1234567
X-Prompt: A beautiful sunset
X-Model: stabilityai/stable-diffusion-2-1
```

**Available headers:**
- `X-Prompt` - The prompt used to generate the image
- `X-Model` - The model ID used
- (edits/variations endpoints include additional headers as appropriate)

---

## Comparison

### Binary Response (Accept: image/png)

**Pros:**
- ✅ Smaller size (~33% smaller than base64)
- ✅ No decoding needed
- ✅ Direct file save
- ✅ Can pipe to tools
- ✅ Faster transfer

**Cons:**
- ❌ Single image only
- ❌ Less metadata (headers only)
- ❌ Can't parse as JSON

**Best for:**
- CLI tools
- Image processing pipelines
- Direct file downloads
- Bandwidth-sensitive applications

---

### JSON Response (Accept: application/json)

**Pros:**
- ✅ Works with multiple images
- ✅ Rich metadata in response
- ✅ Standard OpenAI format
- ✅ Can parse with JSON tools
- ✅ Includes all fields (revised_prompt, etc.)

**Cons:**
- ❌ Larger size (+33% from base64)
- ❌ Requires base64 decoding
- ❌ Extra parsing step

**Best for:**
- Multiple image generation
- Web APIs
- When you need metadata
- OpenAI API compatibility

---

## Content Negotiation Logic

### Server Decision Tree

```
1. Check Accept header
   ├─ If image/png, image/*, or */* → wants_image = true
   └─ Otherwise → wants_image = false

2. Check number of images requested
   ├─ If n == 1 AND wants_image → Return PNG bytes
   └─ Otherwise → Return JSON
```

### Example Scenarios

| Accept Header | n | Response Type | Content-Type |
|---------------|---|---------------|--------------|
| `image/png` | 1 | Binary PNG | `image/png` |
| `image/png` | 3 | JSON | `application/json` |
| `application/json` | 1 | JSON | `application/json` |
| `*/*` | 1 | Binary PNG | `image/png` |
| (none/default) | 1 | JSON | `application/json` |

---

## Testing

### Test Binary Response
```bash
# Should return PNG binary
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Accept: image/png" \
  -d '{"model": "stabilityai/stable-diffusion-2-1", "prompt": "test", "n": 1}' \
  -o test.png

file test.png
# Output: test.png: PNG image data, 512 x 512, 8-bit/color RGB, non-interlaced
```

### Test JSON Response (Multiple Images)
```bash
# Should return JSON even with Accept: image/png
curl -X POST http://localhost:11540/v1/images/generations \
  -H "Accept: image/png" \
  -d '{"model": "stabilityai/stable-diffusion-2-1", "prompt": "test", "n": 2}' \
  | jq '.data | length'
# Output: 2
```

### Test Default (No Accept Header)
```bash
# Should return JSON by default
curl -X POST http://localhost:11540/v1/images/generations \
  -d '{"model": "stabilityai/stable-diffusion-2-1", "prompt": "test"}' \
  | jq '.data[0] | keys'
# Output: ["b64_json", "revised_prompt"]
```

---

## Best Practices

### When to Use Binary (Accept: image/png)

✅ **Use when:**
- Generating single images
- Building CLI tools
- Processing images with external tools
- Need smaller response sizes
- Want simplest possible integration

### When to Use JSON (Accept: application/json)

✅ **Use when:**
- Generating multiple images
- Need metadata in response
- Building web APIs
- Want OpenAI compatibility
- Need to parse responses programmatically

---

## Migration from Previous Version

**No breaking changes!**

The default behavior (without Accept header) is unchanged - returns JSON with base64.

**New capability:**
```bash
# Old way (still works)
curl ... | jq -r '.data[0].b64_json' | base64 -d > image.png

# New way (simpler)
curl ... -H "Accept: image/png" > image.png
```

---

## Error Handling

### Invalid Accept Header
```bash
curl -H "Accept: application/xml" ...
# Still returns JSON (falls back to default)
```

### Multiple Images with Image Accept
```bash
curl -H "Accept: image/png" -d '{"n": 3}' ...
# Returns JSON (can't return multiple images as binary)
```

---

## Performance Comparison

### Binary vs JSON

| Metric | Binary (image/png) | JSON (base64) | Difference |
|--------|-------------------|---------------|------------|
| Response size | ~500 KB | ~666 KB | **25% smaller** |
| Decoding needed | No | Yes | **Faster** |
| Processing time | 0ms | ~5ms | **Faster** |
| Network transfer | Faster | Slower | **Better** |

**Recommendation:** Use binary for single images when possible for best performance.

---

## Examples by Use Case

### Use Case 1: CLI Image Generator

```bash
#!/bin/bash
# generate-image.sh - Simple CLI tool

PROMPT="${1:-A beautiful landscape}"

curl -X POST http://localhost:11540/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Accept: image/png" \
  -d "{\"model\": \"stabilityai/stable-diffusion-2-1\", \"prompt\": \"$PROMPT\"}" \
  -o "$(echo $PROMPT | tr ' ' '_').png"

echo "Image generated: $(echo $PROMPT | tr ' ' '_').png"
```

### Use Case 2: Batch Processing

```bash
#!/bin/bash
# batch-generate.sh

while IFS= read -r prompt; do
  curl -X POST http://localhost:11540/v1/images/generations \
    -H "Accept: image/png" \
    -d "{\"model\": \"stabilityai/stable-diffusion-2-1\", \"prompt\": \"$prompt\"}" \
    | convert - -resize 256x256 "output_${RANDOM}.png"
done < prompts.txt
```

### Use Case 3: Web Application

```javascript
// Frontend: React component
async function GenerateImage({ prompt }) {
  const response = await fetch('/v1/images/generations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'image/png'  // Binary for single images
    },
    body: JSON.stringify({
      model: 'stabilityai/stable-diffusion-2-1',
      prompt: prompt,
      n: 1
    })
  });

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  return <img src={url} alt={prompt} />;
}
```

---

## Summary

**Key Takeaways:**

1. ✅ Use `Accept: image/png` for single images to get binary responses
2. ✅ Binary responses are ~25% smaller and faster
3. ✅ Multiple images always return JSON
4. ✅ Default (no header) returns JSON for backwards compatibility
5. ✅ Metadata available in response headers for binary format
6. ✅ No breaking changes - all existing code works as before

**Quick Reference:**

```bash
# Binary (smaller, faster)
curl -H "Accept: image/png" ... > image.png

# JSON (more metadata, multiple images)
curl ... | jq -r '.data[0].b64_json' | base64 -d > image.png
```

**Perfect for:** CLI tools, pipelines, bandwidth-sensitive apps, single image generation

---

## Related Documentation

- `CHANGES_IN_MEMORY_RESPONSES.md` - In-memory response changes
- `CURL_TEST_COMMANDS.md` - Complete curl examples
- `MANUAL_TEST_EXAMPLES.md` - Manual testing guide
- `server.py` - Implementation details

---

**Status:** ✅ Implemented and tested
**Version:** Universal Runtime v1.0+
**Backwards Compatible:** Yes
