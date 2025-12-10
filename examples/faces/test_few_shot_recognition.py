#!/usr/bin/env python3
"""
Test Few-Shot Face Recognition.

This script demonstrates few-shot face recognition by:
1. Creating a face database from training images (few-shot learning)
2. Testing if the model correctly identifies people from held-out test images

The "training" in DeepFace is simply organizing images into a database structure.
DeepFace builds embeddings on first search and caches them as .pkl files.

Usage:
    python test_few_shot_recognition.py [--base-url http://localhost:11540]
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import httpx

# Configuration
DEFAULT_BASE_URL = "http://localhost:11540"
FACES_DIR = Path(__file__).parent

# Expected people in our database
PEOPLE = {
    "george_w_bush": {
        "source_dir": FACES_DIR / "person1_george_w_bush",
        "display_name": "George W. Bush",
    },
    "colin_powell": {
        "source_dir": FACES_DIR / "person2_colin_powell",
        "display_name": "Colin Powell",
    },
    "tony_blair": {
        "source_dir": FACES_DIR / "person3_tony_blair",
        "display_name": "Tony Blair",
    },
}


class FewShotRecognitionTester:
    """Test few-shot face recognition."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=120.0)  # Long timeout for model loading
        self.results = {"passed": 0, "failed": 0, "tests": []}
        self.temp_dir = None
        self.db_path = None

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log a test result."""
        status = "PASS" if passed else "FAIL"
        print(f"  {'✓' if passed else '✗'} {status}: {test_name}")
        if details:
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

    def setup_face_database(self):
        """
        Set up the face database for few-shot learning.

        Structure:
            temp_db/
                george_w_bush/
                    george_w_bush_1.jpg  (training)
                    george_w_bush_2.jpg  (training)
                    george_w_bush_3.jpg  (training)
                    george_w_bush_4.jpg  (training)
                colin_powell/
                    ...
                tony_blair/
                    ...

        We use images 1-4 for "training" and image 5 for testing.
        """
        print("\n=== Setting Up Face Database (Few-Shot Training) ===")

        # Create temp directory for face database
        self.temp_dir = tempfile.mkdtemp(prefix="face_db_")
        self.db_path = self.temp_dir
        print(f"  Database path: {self.db_path}")

        for person_id, info in PEOPLE.items():
            source_dir = info["source_dir"]
            target_dir = Path(self.db_path) / person_id
            target_dir.mkdir(parents=True, exist_ok=True)

            # Copy first 4 images for training, keep 5th for testing
            images = sorted(source_dir.glob("*.jpg"))
            training_images = images[:4]

            print(f"  {info['display_name']}: {len(training_images)} training images")

            for img in training_images:
                shutil.copy(img, target_dir / img.name)

        print(f"\n  Total: {len(PEOPLE)} people in database")
        print("  Few-shot training complete (images copied to database)")
        return True

    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"\n  Cleaned up: {self.temp_dir}")

    def test_health(self) -> bool:
        """Test face API health."""
        print("\n=== Testing Face API Health ===")
        try:
            response = self.client.get(f"{self.base_url}/v1/face/health")
            if response.status_code == 200:
                self.log_result("Health endpoint", True)
                return True
            else:
                self.log_result("Health endpoint", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health endpoint", False, str(e))
            return False

    def test_recognition(self):
        """Test few-shot face recognition."""
        print("\n=== Testing Few-Shot Face Recognition ===")
        print("  Using held-out test images (image 5 of each person)")

        for person_id, info in PEOPLE.items():
            source_dir = info["source_dir"]
            display_name = info["display_name"]

            # Use the 5th image as test (held out from training)
            images = sorted(source_dir.glob("*.jpg"))
            if len(images) < 5:
                test_image = images[-1]  # Use last available
            else:
                test_image = images[4]  # Use 5th image

            print(f"\n  Testing: {display_name}")
            print(f"    Query image: {test_image.name}")

            try:
                with open(test_image, "rb") as f:
                    response = self.client.post(
                        f"{self.base_url}/v1/face/search",
                        files={"file": (test_image.name, f, "image/jpeg")},
                        data={
                            "db_path": self.db_path,
                            "model": "ArcFace",
                            "detector_backend": "opencv",  # Faster for testing
                            "distance_metric": "cosine",
                        },
                    )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])

                    if results and results[0].get("matches"):
                        matches = results[0]["matches"]
                        best_match = matches[0]  # First match is best

                        # Extract person name from identity path
                        identity = best_match.get("identity", "")
                        distance = best_match.get("distance", 1.0)

                        # Check if the correct person was identified
                        identified_person = None
                        for pid in PEOPLE.keys():
                            if pid in identity:
                                identified_person = pid
                                break

                        correct = identified_person == person_id

                        self.log_result(
                            f"Recognize {display_name}",
                            correct,
                            f"Identified as: {identified_person or 'unknown'}, "
                            f"Distance: {distance:.4f}",
                        )

                        if correct:
                            print(f"    ✓ Correctly identified with distance {distance:.4f}")
                        else:
                            print(f"    ✗ Misidentified as {identified_person}")

                        # Show all matches for debugging
                        if len(matches) > 1:
                            print(f"    All matches ({len(matches)}):")
                            for m in matches[:3]:
                                mid = m.get("identity", "").split("/")[-2]  # Get person folder
                                print(f"      - {mid}: {m.get('distance', 0):.4f}")
                    else:
                        self.log_result(
                            f"Recognize {display_name}",
                            False,
                            "No matches found",
                        )
                else:
                    self.log_result(
                        f"Recognize {display_name}",
                        False,
                        f"Status: {response.status_code}, {response.text[:100]}",
                    )
            except Exception as e:
                self.log_result(f"Recognize {display_name}", False, str(e))

    def test_cross_person_rejection(self):
        """Test that the model correctly rejects wrong identities."""
        print("\n=== Testing Cross-Person Rejection ===")
        print("  Verifying that different people are NOT matched as the same")

        # Test: Query Colin Powell against only George Bush's folder
        george_only_db = tempfile.mkdtemp(prefix="george_only_")

        try:
            # Create a database with only George W Bush
            source = PEOPLE["george_w_bush"]["source_dir"]
            target = Path(george_only_db) / "george_w_bush"
            target.mkdir(parents=True)

            for img in list(source.glob("*.jpg"))[:3]:
                shutil.copy(img, target)

            # Query with Colin Powell's image
            colin_image = list(PEOPLE["colin_powell"]["source_dir"].glob("*.jpg"))[0]

            with open(colin_image, "rb") as f:
                response = self.client.post(
                    f"{self.base_url}/v1/face/search",
                    files={"file": (colin_image.name, f, "image/jpeg")},
                    data={
                        "db_path": george_only_db,
                        "model": "ArcFace",
                        "detector_backend": "opencv",
                        "distance_metric": "cosine",
                    },
                )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                if results and results[0].get("matches"):
                    matches = results[0]["matches"]
                    best_match = matches[0]
                    distance = best_match.get("distance", 0)
                    threshold = best_match.get("threshold", 0.4)

                    # Should have high distance (different person)
                    is_rejected = distance > threshold

                    self.log_result(
                        "Reject Colin Powell as George Bush",
                        is_rejected or distance > 0.5,  # High distance means rejection
                        f"Distance: {distance:.4f}, Threshold: {threshold:.4f}",
                    )

                    if distance > 0.5:
                        print(f"    ✓ Correctly rejected (high distance: {distance:.4f})")
                    else:
                        print(f"    ⚠ Distance lower than expected: {distance:.4f}")
                else:
                    # No matches is also acceptable for different person
                    self.log_result(
                        "Reject Colin Powell as George Bush",
                        True,
                        "No matches found (correct rejection)",
                    )
            else:
                self.log_result(
                    "Reject Colin Powell as George Bush",
                    False,
                    f"Status: {response.status_code}",
                )
        finally:
            shutil.rmtree(george_only_db)

    def print_summary(self):
        """Print test summary."""
        total = self.results["passed"] + self.results["failed"]
        print("\n" + "=" * 60)
        print("FEW-SHOT FACE RECOGNITION TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total}")
        print(f"Passed: {self.results['passed']} ✓")
        print(f"Failed: {self.results['failed']} ✗")
        if total > 0:
            print(f"Success Rate: {100 * self.results['passed'] / total:.1f}%")
        print("=" * 60)

        return self.results["failed"] == 0

    def run_all_tests(self):
        """Run all few-shot recognition tests."""
        print("=" * 60)
        print("FEW-SHOT FACE RECOGNITION TEST SUITE")
        print(f"Base URL: {self.base_url}")
        print("=" * 60)

        try:
            # Check health first
            if not self.test_health():
                print("\n❌ Face API not available. Is the server running?")
                return False

            # Set up the face database
            self.setup_face_database()

            # Run recognition tests
            self.test_recognition()
            self.test_cross_person_rejection()

            # Print summary
            return self.print_summary()

        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Test Few-Shot Face Recognition")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the API (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()

    # Verify test images exist
    for person_id, info in PEOPLE.items():
        if not info["source_dir"].exists():
            print(f"❌ Test images not found: {info['source_dir']}")
            print("   Run download_faces.py first")
            sys.exit(1)

    tester = FewShotRecognitionTester(args.base_url)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
