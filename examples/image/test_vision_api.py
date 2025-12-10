#!/usr/bin/env python3
"""
Test script to run sample images through the Vision API.

Usage:
    python test_vision_api.py
"""

import base64
import json
import sys
from pathlib import Path

import httpx

# API endpoint
BASE_URL = "http://localhost:11540"

# Image files to test
IMAGE_DIR = Path(__file__).parent
IMAGES = [
    ("1.jpeg", "Unknown"),
    ("cat.png", "Cat"),
    ("cat1.jpg", "Cat"),
    ("cat2.jpg", "Cat"),
    ("horse.jpg", "Horse"),
    ("ts_to_test.jpg", "Test image"),
]


def load_image_base64(filepath: Path) -> str:
    """Load image and encode as base64."""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def test_detection(client: httpx.Client, image_path: Path, description: str) -> dict:
    """Test object detection on an image."""
    print(f"\n{'='*60}")
    print(f"Testing DETECTION: {image_path.name} ({description})")
    print("=" * 60)

    with open(image_path, "rb") as f:
        response = client.post(
            f"{BASE_URL}/v1/vision/detect",
            files={"file": (image_path.name, f, "image/jpeg")},
            data={"model": "yolo11n", "confidence": "0.25"},
        )

    if response.status_code != 200:
        print(f"  ERROR: {response.status_code} - {response.text}")
        return {"error": response.text}

    result = response.json()
    print(f"  Inference time: {result['inference_time_ms']:.1f}ms")
    print(f"  Image size: {result['image_width']}x{result['image_height']}")
    print(f"  Objects detected: {len(result['boxes'])}")

    for i, box in enumerate(result["boxes"][:5]):  # Show top 5
        print(
            f"    [{i+1}] {box['class_name']}: {box['confidence']:.2%} "
            f"at ({box['x1']:.0f},{box['y1']:.0f})-({box['x2']:.0f},{box['y2']:.0f})"
        )

    if len(result["boxes"]) > 5:
        print(f"    ... and {len(result['boxes']) - 5} more")

    return result


def test_classification(
    client: httpx.Client, image_path: Path, description: str
) -> dict:
    """Test image classification on an image."""
    print(f"\n{'='*60}")
    print(f"Testing CLASSIFICATION: {image_path.name} ({description})")
    print("=" * 60)

    with open(image_path, "rb") as f:
        response = client.post(
            f"{BASE_URL}/v1/vision/classify",
            files={"file": (image_path.name, f, "image/jpeg")},
            data={"model": "yolo11n-cls", "top_k": "5"},
        )

    if response.status_code != 200:
        print(f"  ERROR: {response.status_code} - {response.text}")
        return {"error": response.text}

    result = response.json()
    print(f"  Inference time: {result['inference_time_ms']:.1f}ms")

    if result.get("classification"):
        cls = result["classification"]
        print(f"  Top prediction: {cls['class_name']} ({cls['confidence']:.2%})")
        print(f"  Top-5 predictions:")
        for pred in cls.get("top_k", [])[:5]:
            for class_name, conf in pred.items():
                print(f"    - {class_name}: {conf:.2%}")

    return result


def test_segmentation(
    client: httpx.Client, image_path: Path, description: str
) -> dict:
    """Test instance segmentation on an image."""
    print(f"\n{'='*60}")
    print(f"Testing SEGMENTATION: {image_path.name} ({description})")
    print("=" * 60)

    with open(image_path, "rb") as f:
        response = client.post(
            f"{BASE_URL}/v1/vision/segment",
            files={"file": (image_path.name, f, "image/jpeg")},
            data={"model": "yolo11n-seg", "confidence": "0.25"},
        )

    if response.status_code != 200:
        print(f"  ERROR: {response.status_code} - {response.text}")
        return {"error": response.text}

    result = response.json()
    print(f"  Inference time: {result['inference_time_ms']:.1f}ms")
    print(f"  Objects segmented: {len(result['boxes'])}")

    if result.get("masks"):
        print(f"  Masks generated: {len(result['masks'])}")
        for i, mask in enumerate(result["masks"][:3]):
            print(
                f"    [{i+1}] {mask['class_name']}: area={mask['area']:.0f}px, "
                f"contour points={len(mask['contour'])}"
            )

    return result


def test_pose(client: httpx.Client, image_path: Path, description: str) -> dict:
    """Test pose estimation on an image."""
    print(f"\n{'='*60}")
    print(f"Testing POSE ESTIMATION: {image_path.name} ({description})")
    print("=" * 60)

    with open(image_path, "rb") as f:
        response = client.post(
            f"{BASE_URL}/v1/vision/pose",
            files={"file": (image_path.name, f, "image/jpeg")},
            data={"model": "yolo11n-pose", "confidence": "0.25"},
        )

    if response.status_code != 200:
        print(f"  ERROR: {response.status_code} - {response.text}")
        return {"error": response.text}

    result = response.json()
    print(f"  Inference time: {result['inference_time_ms']:.1f}ms")
    print(f"  Persons detected: {len(result.get('keypoints', []))}")

    if result.get("keypoints"):
        for i, person in enumerate(result["keypoints"][:2]):
            print(f"    Person {i+1}: {len(person['keypoints'])} keypoints")
            # Show a few keypoints
            for kpt in person["keypoints"][:3]:
                if kpt["confidence"] > 0.5:
                    print(
                        f"      - {kpt['name']}: ({kpt['x']:.0f},{kpt['y']:.0f}) "
                        f"conf={kpt['confidence']:.2%}"
                    )

    return result


def test_health(client: httpx.Client) -> bool:
    """Check API health."""
    print("\nChecking API health...")
    try:
        response = client.get(f"{BASE_URL}/v1/vision/health")
        if response.status_code == 200:
            print(f"  API is healthy: {response.json()}")
            return True
        else:
            print(f"  API returned: {response.status_code}")
            return False
    except Exception as e:
        print(f"  API not reachable: {e}")
        return False


def main():
    print("=" * 60)
    print("Vision API Test Suite")
    print("=" * 60)

    with httpx.Client(timeout=60.0) as client:
        # Check health first
        if not test_health(client):
            print("\nERROR: API is not available. Make sure universal runtime is running.")
            print("Start it with: nx start universal")
            sys.exit(1)

        # Test each image
        results = {}
        for filename, description in IMAGES:
            image_path = IMAGE_DIR / filename
            if not image_path.exists():
                print(f"\nSkipping {filename} - file not found")
                continue

            # Run detection
            results[f"{filename}_detect"] = test_detection(
                client, image_path, description
            )

            # Run classification
            results[f"{filename}_classify"] = test_classification(
                client, image_path, description
            )

        # Run segmentation on a couple images
        print("\n" + "=" * 60)
        print("SEGMENTATION TESTS")
        print("=" * 60)
        for filename in ["cat1.jpg", "horse.jpg"]:
            image_path = IMAGE_DIR / filename
            if image_path.exists():
                test_segmentation(client, image_path, filename)

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        success = sum(1 for r in results.values() if "error" not in r)
        total = len(results)
        print(f"  Passed: {success}/{total}")

        if success == total:
            print("\n  All tests PASSED!")
            return 0
        else:
            print("\n  Some tests FAILED")
            return 1


if __name__ == "__main__":
    sys.exit(main())
