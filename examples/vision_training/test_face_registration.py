#!/usr/bin/env python3
"""
Test Face Registration with Real Images

This script tests the face registration and recognition workflow using
real face images stored in the LlamaFarm project directory.

It demonstrates:
1. Creating a face database via the LlamaFarm API
2. Registering faces for multiple people
3. Using the Universal Runtime to perform face search/recognition
4. Cleaning up

Prerequisites:
- LlamaFarm server running on http://localhost:8000
- Universal Runtime running on http://localhost:11540
- Face images available (download with download_faces.py in examples/faces)
- A project created via `lf init`

Usage:
    python test_face_registration.py [--namespace default] [--project test-project-1]
"""

import argparse
import os
import sys
from pathlib import Path

import httpx

# Configuration
DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_RUNTIME_URL = "http://localhost:11540"
DEFAULT_NAMESPACE = "default"
DEFAULT_PROJECT = "test-project-1"

# Path to face images (relative to this script's directory)
SCRIPT_DIR = Path(__file__).parent.parent
FACES_DIR = SCRIPT_DIR / "faces"

# People to register
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


class FaceRegistrationTester:
    """Test face registration workflow."""

    def __init__(
        self,
        server_url: str,
        runtime_url: str,
        namespace: str,
        project: str,
    ):
        self.server_url = server_url.rstrip("/")
        self.runtime_url = runtime_url.rstrip("/")
        self.namespace = namespace
        self.project = project
        self.vision_api = f"{self.server_url}/v1/projects/{namespace}/{project}/vision"
        self.client = httpx.Client(timeout=120.0)
        self.results = {"passed": 0, "failed": 0, "tests": []}
        self.db_name = "test_employees"

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

    def check_prerequisites(self) -> bool:
        """Check that prerequisites are met."""
        print("\n=== Checking Prerequisites ===")

        # Check LlamaFarm server
        try:
            response = self.client.get(f"{self.vision_api}/health")
            if response.status_code != 200:
                print(f"  ✗ LlamaFarm server not responding at {self.server_url}")
                return False
            print(f"  ✓ LlamaFarm server: {self.server_url}")
        except Exception as e:
            print(f"  ✗ LlamaFarm server error: {e}")
            return False

        # Check Universal Runtime
        try:
            response = self.client.get(f"{self.runtime_url}/v1/face/health")
            if response.status_code != 200:
                print(f"  ✗ Universal Runtime not responding at {self.runtime_url}")
                return False
            print(f"  ✓ Universal Runtime: {self.runtime_url}")
        except Exception as e:
            print(f"  ✗ Universal Runtime error: {e}")
            return False

        # Check face images
        for person_id, info in PEOPLE.items():
            if not info["source_dir"].exists():
                print(f"  ✗ Face images not found: {info['source_dir']}")
                print("    Run download_faces.py in examples/faces first")
                return False
            images = list(info["source_dir"].glob("*.jpg"))
            print(f"  ✓ {info['display_name']}: {len(images)} images")

        return True

    def create_face_database(self) -> bool:
        """Create a face database."""
        print("\n=== Creating Face Database ===")
        try:
            # First try to delete if exists
            self.client.delete(f"{self.vision_api}/faces/{self.db_name}")

            response = self.client.post(
                f"{self.vision_api}/faces",
                json={
                    "name": self.db_name,
                    "detector_backend": "retinaface",
                    "recognition_model": "ArcFace",
                },
            )
            if response.status_code == 200:
                self.log_result("Create face database", True, f"Name: {self.db_name}")
                return True
            else:
                self.log_result("Create face database", False, response.text[:100])
                return False
        except Exception as e:
            self.log_result("Create face database", False, str(e))
            return False

    def register_faces(self):
        """Register faces for all people."""
        print("\n=== Registering Faces ===")

        for person_id, info in PEOPLE.items():
            source_dir = info["source_dir"]
            display_name = info["display_name"]

            # Use first 4 images for registration
            images = sorted(source_dir.glob("*.jpg"))[:4]

            for i, image_path in enumerate(images):
                try:
                    with open(image_path, "rb") as f:
                        files = {"file": (image_path.name, f, "image/jpeg")}
                        data = {
                            "person_id": person_id,
                            "display_name": display_name,
                        }
                        response = self.client.post(
                            f"{self.vision_api}/faces/{self.db_name}/register",
                            files=files,
                            data=data,
                        )

                    if response.status_code == 200:
                        if i == 0:  # Only log first image per person
                            self.log_result(
                                f"Register {display_name}",
                                True,
                                f"Registered {len(images)} images",
                            )
                    else:
                        self.log_result(
                            f"Register {display_name} ({image_path.name})",
                            False,
                            response.text[:100],
                        )
                except Exception as e:
                    self.log_result(
                        f"Register {display_name} ({image_path.name})",
                        False,
                        str(e),
                    )

    def verify_registration(self):
        """Verify face registration."""
        print("\n=== Verifying Registration ===")

        try:
            response = self.client.get(f"{self.vision_api}/faces/{self.db_name}/identities")
            if response.status_code == 200:
                identities = response.json()
                self.log_result(
                    "List registered identities",
                    len(identities) == len(PEOPLE),
                    f"Found {len(identities)} identities",
                )

                for identity in identities:
                    person_id = identity.get("person_id")
                    image_count = identity.get("image_count", 0)
                    print(f"    - {person_id}: {image_count} images")
            else:
                self.log_result("List registered identities", False, response.text[:100])
        except Exception as e:
            self.log_result("List registered identities", False, str(e))

    def test_recognition(self):
        """Test face recognition using Universal Runtime."""
        print("\n=== Testing Face Recognition ===")

        # Get DB path
        try:
            response = self.client.get(f"{self.vision_api}/faces/{self.db_name}/db-path")
            if response.status_code != 200:
                self.log_result("Get DB path", False, response.text[:100])
                return

            db_path = response.json().get("db_path")
            self.log_result("Get DB path", True, db_path)
        except Exception as e:
            self.log_result("Get DB path", False, str(e))
            return

        # Test recognition with held-out images (5th image of each person)
        for person_id, info in PEOPLE.items():
            display_name = info["display_name"]
            source_dir = info["source_dir"]

            # Use 5th image as test (held out from registration)
            images = sorted(source_dir.glob("*.jpg"))
            if len(images) < 5:
                test_image = images[-1]
            else:
                test_image = images[4]

            try:
                with open(test_image, "rb") as f:
                    response = self.client.post(
                        f"{self.runtime_url}/v1/face/search",
                        files={"file": (test_image.name, f, "image/jpeg")},
                        data={
                            "db_path": db_path,
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
                        identity = best_match.get("identity", "")
                        distance = best_match.get("distance", 1.0)

                        # Check if correct person was identified
                        identified_person = None
                        for pid in PEOPLE.keys():
                            if pid in identity:
                                identified_person = pid
                                break

                        correct = identified_person == person_id
                        self.log_result(
                            f"Recognize {display_name}",
                            correct,
                            f"Identified: {identified_person or 'unknown'}, Distance: {distance:.4f}",
                        )
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
                        f"Status: {response.status_code}",
                    )
            except Exception as e:
                self.log_result(f"Recognize {display_name}", False, str(e))

    def cleanup(self):
        """Clean up test data."""
        print("\n=== Cleaning Up ===")
        try:
            response = self.client.delete(f"{self.vision_api}/faces/{self.db_name}")
            if response.status_code == 200:
                print(f"  ✓ Deleted face database: {self.db_name}")
            else:
                print(f"  ⚠ Failed to delete database: {response.status_code}")
        except Exception as e:
            print(f"  ⚠ Cleanup error: {e}")

    def print_summary(self):
        """Print test summary."""
        total = self.results["passed"] + self.results["failed"]
        print("\n" + "=" * 60)
        print("FACE REGISTRATION TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total}")
        print(f"Passed: {self.results['passed']} ✓")
        print(f"Failed: {self.results['failed']} ✗")
        if total > 0:
            print(f"Success Rate: {100 * self.results['passed'] / total:.1f}%")
        print("=" * 60)

        return self.results["failed"] == 0

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 60)
        print("FACE REGISTRATION INTEGRATION TEST")
        print(f"LlamaFarm Server: {self.server_url}")
        print(f"Universal Runtime: {self.runtime_url}")
        print(f"Project: {self.namespace}/{self.project}")
        print("=" * 60)

        try:
            if not self.check_prerequisites():
                print("\n❌ Prerequisites not met. Exiting.")
                return False

            if not self.create_face_database():
                print("\n❌ Failed to create face database. Exiting.")
                return False

            self.register_faces()
            self.verify_registration()
            self.test_recognition()

            return self.print_summary()
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Test Face Registration Workflow")
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SERVER_URL,
        help=f"LlamaFarm server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--runtime-url",
        default=DEFAULT_RUNTIME_URL,
        help=f"Universal Runtime URL (default: {DEFAULT_RUNTIME_URL})",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Project namespace (default: {DEFAULT_NAMESPACE})",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"Project name (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't delete the face database after testing",
    )
    args = parser.parse_args()

    tester = FaceRegistrationTester(
        args.server_url,
        args.runtime_url,
        args.namespace,
        args.project,
    )

    if args.no_cleanup:
        tester.cleanup = lambda: print("\n  (Skipping cleanup)")

    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
