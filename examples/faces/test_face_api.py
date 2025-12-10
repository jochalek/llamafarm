#!/usr/bin/env python3
"""
Test Face Recognition API with real face images.

This script tests the Universal Runtime's face recognition endpoints using
real face images from the LFW (Labeled Faces in the Wild) dataset.

Tests:
1. Face Detection - Detect faces in each image
2. Face Verification (Same Person) - Verify two images of the same person match
3. Face Verification (Different People) - Verify different people don't match
4. Face Analysis - Analyze age, gender, emotion for each face
5. Face Embeddings - Get embedding vectors for faces

Usage:
    python test_face_api.py [--base-url http://localhost:11540]
"""

import argparse
import base64
import os
import sys
from pathlib import Path

import httpx

# Configuration
DEFAULT_BASE_URL = "http://localhost:11540"
FACES_DIR = Path(__file__).parent

# Test data structure
PEOPLE = {
    "george_w_bush": FACES_DIR / "person1_george_w_bush",
    "colin_powell": FACES_DIR / "person2_colin_powell",
    "tony_blair": FACES_DIR / "person3_tony_blair",
}


def load_image_base64(path: Path) -> str:
    """Load an image file as base64 string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_person_images(person_name: str) -> list[Path]:
    """Get all image paths for a person."""
    person_dir = PEOPLE[person_name]
    return sorted(person_dir.glob("*.jpg"))


class FaceAPITester:
    """Test face recognition API endpoints."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60.0)
        self.results = {"passed": 0, "failed": 0, "tests": []}

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log a test result."""
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
        if details and not passed:
            print(f"         {details}")

        self.results["tests"].append({
            "name": test_name,
            "passed": passed,
            "details": details,
        })
        if passed:
            self.results["passed"] += 1
        else:
            self.results["failed"] += 1

    def test_health(self) -> bool:
        """Test face API health endpoint."""
        print("\n=== Testing Face API Health ===")
        try:
            response = self.client.get(f"{self.base_url}/v1/face/health")
            if response.status_code == 200:
                data = response.json()
                self.log_result("Health endpoint", data.get("status") == "ok")
                return True
            else:
                self.log_result("Health endpoint", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health endpoint", False, str(e))
            return False

    def test_models_list(self):
        """Test listing available models."""
        print("\n=== Testing Models List ===")
        try:
            response = self.client.get(f"{self.base_url}/v1/face/models")
            data = response.json()

            self.log_result(
                "List recognition models",
                "recognition_models" in data and len(data["recognition_models"]) > 0,
            )
            self.log_result(
                "List detector backends",
                "detector_backends" in data and len(data["detector_backends"]) > 0,
            )

            if "recognition_models" in data:
                print(f"    Available models: {[m['name'] for m in data['recognition_models'][:3]]}...")
            if "detector_backends" in data:
                print(f"    Available detectors: {[d['name'] for d in data['detector_backends'][:3]]}...")

        except Exception as e:
            self.log_result("List models", False, str(e))

    def test_face_detection(self):
        """Test face detection on all images."""
        print("\n=== Testing Face Detection ===")

        for person_name, person_dir in PEOPLE.items():
            images = list(person_dir.glob("*.jpg"))[:2]  # Test first 2 images per person

            for image_path in images:
                try:
                    # Use file upload
                    with open(image_path, "rb") as f:
                        response = self.client.post(
                            f"{self.base_url}/v1/face/detect",
                            files={"file": (image_path.name, f, "image/jpeg")},
                            data={"detector_backend": "opencv"},
                        )

                    if response.status_code == 200:
                        data = response.json()
                        face_count = data.get("count", 0)
                        self.log_result(
                            f"Detect face in {image_path.name}",
                            face_count >= 1,
                            f"Found {face_count} faces" if face_count > 0 else "No faces detected",
                        )
                    else:
                        self.log_result(
                            f"Detect face in {image_path.name}",
                            False,
                            f"Status: {response.status_code}",
                        )
                except Exception as e:
                    self.log_result(f"Detect face in {image_path.name}", False, str(e))

    def test_face_verification_same_person(self):
        """Test verification of same person (should match)."""
        print("\n=== Testing Face Verification (Same Person - Should Match) ===")

        for person_name in PEOPLE.keys():
            images = get_person_images(person_name)
            if len(images) < 2:
                continue

            img1_path = images[0]
            img2_path = images[1]

            try:
                with open(img1_path, "rb") as f1, open(img2_path, "rb") as f2:
                    response = self.client.post(
                        f"{self.base_url}/v1/face/verify",
                        files={
                            "file1": (img1_path.name, f1, "image/jpeg"),
                            "file2": (img2_path.name, f2, "image/jpeg"),
                        },
                        data={
                            "model": "ArcFace",
                            "detector_backend": "opencv",
                            "distance_metric": "cosine",
                        },
                    )

                if response.status_code == 200:
                    data = response.json()
                    verified = data.get("verified", False)
                    distance = data.get("distance", 1.0)
                    threshold = data.get("threshold", 0.0)

                    # For same person, we expect verified=True or at least low distance
                    test_passed = verified or distance < 0.6

                    self.log_result(
                        f"Verify {person_name} (same person)",
                        test_passed,
                        f"verified={verified}, distance={distance:.4f}, threshold={threshold:.4f}",
                    )

                    if test_passed:
                        print(f"         Distance: {distance:.4f} (lower = more similar)")
                else:
                    self.log_result(
                        f"Verify {person_name}",
                        False,
                        f"Status: {response.status_code}",
                    )
            except Exception as e:
                self.log_result(f"Verify {person_name}", False, str(e))

    def test_face_verification_different_people(self):
        """Test verification of different people (should NOT match)."""
        print("\n=== Testing Face Verification (Different People - Should NOT Match) ===")

        people_list = list(PEOPLE.keys())

        for i in range(len(people_list)):
            for j in range(i + 1, len(people_list)):
                person1 = people_list[i]
                person2 = people_list[j]

                img1_path = get_person_images(person1)[0]
                img2_path = get_person_images(person2)[0]

                try:
                    with open(img1_path, "rb") as f1, open(img2_path, "rb") as f2:
                        response = self.client.post(
                            f"{self.base_url}/v1/face/verify",
                            files={
                                "file1": (img1_path.name, f1, "image/jpeg"),
                                "file2": (img2_path.name, f2, "image/jpeg"),
                            },
                            data={
                                "model": "ArcFace",
                                "detector_backend": "opencv",
                                "distance_metric": "cosine",
                            },
                        )

                    if response.status_code == 200:
                        data = response.json()
                        verified = data.get("verified", True)
                        distance = data.get("distance", 0.0)

                        # For different people, we expect verified=False or high distance
                        test_passed = not verified or distance > 0.4

                        self.log_result(
                            f"Verify {person1} vs {person2} (different people)",
                            test_passed,
                            f"verified={verified}, distance={distance:.4f}",
                        )

                        if test_passed:
                            print(f"         Distance: {distance:.4f} (higher = less similar)")
                    else:
                        self.log_result(
                            f"Verify {person1} vs {person2}",
                            False,
                            f"Status: {response.status_code}",
                        )
                except Exception as e:
                    self.log_result(f"Verify {person1} vs {person2}", False, str(e))

    def test_face_analysis(self):
        """Test face analysis (age, gender, emotion)."""
        print("\n=== Testing Face Analysis ===")

        # Test one image per person
        for person_name in PEOPLE.keys():
            images = get_person_images(person_name)
            if not images:
                continue

            image_path = images[0]

            try:
                with open(image_path, "rb") as f:
                    response = self.client.post(
                        f"{self.base_url}/v1/face/analyze",
                        files={"file": (image_path.name, f, "image/jpeg")},
                        data={
                            "actions": "age,gender,emotion",
                            "detector_backend": "opencv",
                        },
                    )

                if response.status_code == 200:
                    data = response.json()
                    face_count = data.get("count", 0)

                    if face_count > 0 and data.get("faces"):
                        face = data["faces"][0]
                        age = face.get("age")
                        gender = face.get("gender")
                        emotion = face.get("dominant_emotion")

                        self.log_result(
                            f"Analyze {person_name}",
                            age is not None or gender is not None,
                            f"age={age}, gender={gender}, emotion={emotion}",
                        )
                        print(f"         Results: age={age}, gender={gender}, emotion={emotion}")
                    else:
                        self.log_result(
                            f"Analyze {person_name}",
                            False,
                            "No faces detected for analysis",
                        )
                else:
                    self.log_result(
                        f"Analyze {person_name}",
                        False,
                        f"Status: {response.status_code}",
                    )
            except Exception as e:
                self.log_result(f"Analyze {person_name}", False, str(e))

    def test_face_embeddings(self):
        """Test face embedding generation."""
        print("\n=== Testing Face Embeddings ===")

        # Test one image per person
        embeddings_by_person = {}

        for person_name in PEOPLE.keys():
            images = get_person_images(person_name)
            if not images:
                continue

            image_path = images[0]

            try:
                with open(image_path, "rb") as f:
                    response = self.client.post(
                        f"{self.base_url}/v1/face/embeddings",
                        files={"file": (image_path.name, f, "image/jpeg")},
                        data={
                            "model": "ArcFace",
                            "detector_backend": "opencv",
                        },
                    )

                if response.status_code == 200:
                    data = response.json()
                    emb_count = data.get("count", 0)

                    if emb_count > 0 and data.get("embeddings"):
                        embedding = data["embeddings"][0].get("embedding", [])
                        emb_dim = len(embedding)

                        self.log_result(
                            f"Get embedding for {person_name}",
                            emb_dim > 100,  # ArcFace produces 512-dim embeddings
                            f"Embedding dimension: {emb_dim}",
                        )
                        print(f"         Embedding dimension: {emb_dim}")

                        embeddings_by_person[person_name] = embedding
                    else:
                        self.log_result(
                            f"Get embedding for {person_name}",
                            False,
                            "No faces detected",
                        )
                else:
                    self.log_result(
                        f"Get embedding for {person_name}",
                        False,
                        f"Status: {response.status_code}",
                    )
            except Exception as e:
                self.log_result(f"Get embedding for {person_name}", False, str(e))

        return embeddings_by_person

    def test_base64_input(self):
        """Test face detection with base64 input."""
        print("\n=== Testing Base64 Input ===")

        image_path = get_person_images("george_w_bush")[0]
        image_b64 = load_image_base64(image_path)

        try:
            response = self.client.post(
                f"{self.base_url}/v1/face/detect",
                data={
                    "image_base64": image_b64,
                    "detector_backend": "opencv",
                },
            )

            if response.status_code == 200:
                data = response.json()
                face_count = data.get("count", 0)
                self.log_result(
                    "Detect face from base64",
                    face_count >= 1,
                    f"Found {face_count} faces",
                )
            else:
                self.log_result(
                    "Detect face from base64",
                    False,
                    f"Status: {response.status_code}",
                )
        except Exception as e:
            self.log_result("Detect face from base64", False, str(e))

    def test_json_endpoints(self):
        """Test JSON request body endpoints."""
        print("\n=== Testing JSON Endpoints ===")

        image_path = get_person_images("colin_powell")[0]
        image_b64 = load_image_base64(image_path)

        # Test detect/json
        try:
            response = self.client.post(
                f"{self.base_url}/v1/face/detect/json",
                json={
                    "image_base64": image_b64,
                    "detector_backend": "opencv",
                },
            )

            self.log_result(
                "JSON detect endpoint",
                response.status_code == 200 and response.json().get("count", 0) >= 0,
                f"Status: {response.status_code}",
            )
        except Exception as e:
            self.log_result("JSON detect endpoint", False, str(e))

        # Test analyze/json
        try:
            response = self.client.post(
                f"{self.base_url}/v1/face/analyze/json",
                json={
                    "image_base64": image_b64,
                    "actions": ["age", "gender"],
                    "detector_backend": "opencv",
                },
            )

            self.log_result(
                "JSON analyze endpoint",
                response.status_code == 200,
                f"Status: {response.status_code}",
            )
        except Exception as e:
            self.log_result("JSON analyze endpoint", False, str(e))

    def print_summary(self):
        """Print test summary."""
        total = self.results["passed"] + self.results["failed"]
        print("\n" + "=" * 60)
        print("FACE RECOGNITION TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total}")
        print(f"Passed: {self.results['passed']} ✓")
        print(f"Failed: {self.results['failed']} ✗")
        print(f"Success Rate: {100 * self.results['passed'] / total:.1f}%")
        print("=" * 60)

        return self.results["failed"] == 0

    def run_all_tests(self):
        """Run all face recognition tests."""
        print("=" * 60)
        print("FACE RECOGNITION API TEST SUITE")
        print(f"Base URL: {self.base_url}")
        print(f"Test Images: {FACES_DIR}")
        print("=" * 60)

        # Check health first
        if not self.test_health():
            print("\n❌ Face API not available. Is the server running?")
            print(f"   Try: curl {self.base_url}/v1/face/health")
            return False

        # Run all tests
        self.test_models_list()
        self.test_face_detection()
        self.test_face_verification_same_person()
        self.test_face_verification_different_people()
        self.test_face_analysis()
        self.test_face_embeddings()
        self.test_base64_input()
        self.test_json_endpoints()

        # Print summary
        return self.print_summary()


def main():
    parser = argparse.ArgumentParser(description="Test Face Recognition API")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the API (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()

    # Verify test images exist
    for person_name, person_dir in PEOPLE.items():
        if not person_dir.exists():
            print(f"❌ Test images not found: {person_dir}")
            print("   Run download_faces.py first to download LFW samples")
            sys.exit(1)

    tester = FaceAPITester(args.base_url)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
