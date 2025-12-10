#!/usr/bin/env python3
"""
Test Vision Training API

This script tests the vision training REST endpoints on the LlamaFarm server.
It covers:
1. Training set CRUD operations
2. Image upload and management
3. Face database CRUD operations
4. Face registration and identity management

Prerequisites:
- LlamaFarm server running on http://localhost:8000
- A project created with `lf init test-project` or via API

Usage:
    python test_vision_training_api.py [--base-url http://localhost:8000] [--namespace default] [--project test-project-1]
"""

import argparse
import base64
import os
import sys
import time
from pathlib import Path

import httpx

# Configuration
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_NAMESPACE = "default"
DEFAULT_PROJECT = "test-project-1"

# Test image (1x1 red pixel JPEG, base64 encoded)
TINY_IMAGE_B64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMCwsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQCEAPwCwAB//9k="


class VisionTrainingAPITester:
    """Test vision training API endpoints."""

    def __init__(self, base_url: str, namespace: str, project: str):
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.project = project
        self.api_base = f"{self.base_url}/v1/projects/{namespace}/{project}/vision"
        self.client = httpx.Client(timeout=60.0)
        self.results = {"passed": 0, "failed": 0, "tests": []}

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

    def test_health(self) -> bool:
        """Test health endpoint."""
        print("\n=== Testing Health Endpoint ===")
        try:
            response = self.client.get(f"{self.api_base}/health")
            if response.status_code == 200 and response.json().get("status") == "ok":
                self.log_result("Health endpoint", True)
                return True
            else:
                self.log_result("Health endpoint", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health endpoint", False, str(e))
            return False

    def test_training_sets(self):
        """Test training set CRUD operations."""
        print("\n=== Testing Training Set Endpoints ===")

        training_set_name = f"test_set_{int(time.time())}"

        # Create training set
        try:
            response = self.client.post(
                f"{self.api_base}/training-sets",
                json={
                    "name": training_set_name,
                    "task": "detect",
                    "classes": ["person", "car", "dog"],
                },
            )
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Create training set",
                    data.get("name") == training_set_name,
                    f"Created: {training_set_name}",
                )
            else:
                self.log_result("Create training set", False, response.text[:100])
                return
        except Exception as e:
            self.log_result("Create training set", False, str(e))
            return

        # List training sets
        try:
            response = self.client.get(f"{self.api_base}/training-sets")
            if response.status_code == 200:
                data = response.json()
                found = any(ts.get("name") == training_set_name for ts in data)
                self.log_result("List training sets", found, f"Found {len(data)} sets")
            else:
                self.log_result("List training sets", False, response.text[:100])
        except Exception as e:
            self.log_result("List training sets", False, str(e))

        # Get training set
        try:
            response = self.client.get(f"{self.api_base}/training-sets/{training_set_name}")
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Get training set",
                    data.get("name") == training_set_name,
                )
            else:
                self.log_result("Get training set", False, response.text[:100])
        except Exception as e:
            self.log_result("Get training set", False, str(e))

        # Add image to training set
        try:
            response = self.client.post(
                f"{self.api_base}/training-sets/{training_set_name}/images/json",
                json={
                    "image_base64": TINY_IMAGE_B64,
                    "filename": "test_image.jpg",
                    "split": "train",
                    "labels": "0 0.5 0.5 0.2 0.2",  # YOLO format: class x_center y_center w h
                },
            )
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Add image to training set",
                    "hash" in data,
                    f"Hash: {data.get('hash', 'N/A')[:16]}...",
                )
            else:
                self.log_result("Add image to training set", False, response.text[:100])
        except Exception as e:
            self.log_result("Add image to training set", False, str(e))

        # List images
        try:
            response = self.client.get(
                f"{self.api_base}/training-sets/{training_set_name}/images"
            )
            if response.status_code == 200:
                data = response.json()
                self.log_result("List training set images", len(data) > 0, f"Found {len(data)} images")
            else:
                self.log_result("List training set images", False, response.text[:100])
        except Exception as e:
            self.log_result("List training set images", False, str(e))

        # Update classes
        try:
            response = self.client.patch(
                f"{self.api_base}/training-sets/{training_set_name}/classes",
                json={"classes": ["person", "car", "dog", "cat"]},
            )
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Update training set classes",
                    len(data.get("classes", {})) == 4,
                )
            else:
                self.log_result("Update training set classes", False, response.text[:100])
        except Exception as e:
            self.log_result("Update training set classes", False, str(e))

        # Delete training set
        try:
            response = self.client.delete(f"{self.api_base}/training-sets/{training_set_name}")
            if response.status_code == 200:
                self.log_result("Delete training set", True)
            else:
                self.log_result("Delete training set", False, response.text[:100])
        except Exception as e:
            self.log_result("Delete training set", False, str(e))

    def test_face_databases(self):
        """Test face database CRUD operations."""
        print("\n=== Testing Face Database Endpoints ===")

        db_name = f"test_faces_{int(time.time())}"

        # Create face database
        try:
            response = self.client.post(
                f"{self.api_base}/faces",
                json={
                    "name": db_name,
                    "detector_backend": "opencv",  # Fastest for testing
                    "recognition_model": "ArcFace",
                },
            )
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Create face database",
                    data.get("name") == db_name,
                    f"Created: {db_name}",
                )
            else:
                self.log_result("Create face database", False, response.text[:100])
                return
        except Exception as e:
            self.log_result("Create face database", False, str(e))
            return

        # List face databases
        try:
            response = self.client.get(f"{self.api_base}/faces")
            if response.status_code == 200:
                data = response.json()
                found = any(db.get("name") == db_name for db in data)
                self.log_result("List face databases", found, f"Found {len(data)} databases")
            else:
                self.log_result("List face databases", False, response.text[:100])
        except Exception as e:
            self.log_result("List face databases", False, str(e))

        # Get face database
        try:
            response = self.client.get(f"{self.api_base}/faces/{db_name}")
            if response.status_code == 200:
                data = response.json()
                self.log_result("Get face database", data.get("name") == db_name)
            else:
                self.log_result("Get face database", False, response.text[:100])
        except Exception as e:
            self.log_result("Get face database", False, str(e))

        # Register a face (using tiny test image - won't work for actual recognition)
        try:
            response = self.client.post(
                f"{self.api_base}/faces/{db_name}/register/json",
                json={
                    "person_id": "test_person",
                    "display_name": "Test Person",
                    "image_base64": TINY_IMAGE_B64,
                    "filename": "test_face.jpg",
                },
            )
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Register face",
                    data.get("person_id") == "test_person",
                    f"Registered: test_person",
                )
            else:
                self.log_result("Register face", False, response.text[:100])
        except Exception as e:
            self.log_result("Register face", False, str(e))

        # List identities
        try:
            response = self.client.get(f"{self.api_base}/faces/{db_name}/identities")
            if response.status_code == 200:
                data = response.json()
                self.log_result("List face identities", len(data) > 0, f"Found {len(data)} identities")
            else:
                self.log_result("List face identities", False, response.text[:100])
        except Exception as e:
            self.log_result("List face identities", False, str(e))

        # Get identity
        try:
            response = self.client.get(f"{self.api_base}/faces/{db_name}/identities/test_person")
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Get face identity",
                    data.get("person_id") == "test_person",
                )
            else:
                self.log_result("Get face identity", False, response.text[:100])
        except Exception as e:
            self.log_result("Get face identity", False, str(e))

        # Get DB path (for use with Universal Runtime)
        try:
            response = self.client.get(f"{self.api_base}/faces/{db_name}/db-path")
            if response.status_code == 200:
                data = response.json()
                self.log_result(
                    "Get face DB path",
                    "db_path" in data,
                    f"Path: {data.get('db_path', 'N/A')}",
                )
            else:
                self.log_result("Get face DB path", False, response.text[:100])
        except Exception as e:
            self.log_result("Get face DB path", False, str(e))

        # Delete identity
        try:
            response = self.client.delete(f"{self.api_base}/faces/{db_name}/identities/test_person")
            if response.status_code == 200:
                self.log_result("Delete face identity", True)
            else:
                self.log_result("Delete face identity", False, response.text[:100])
        except Exception as e:
            self.log_result("Delete face identity", False, str(e))

        # Delete face database
        try:
            response = self.client.delete(f"{self.api_base}/faces/{db_name}")
            if response.status_code == 200:
                self.log_result("Delete face database", True)
            else:
                self.log_result("Delete face database", False, response.text[:100])
        except Exception as e:
            self.log_result("Delete face database", False, str(e))

    def test_models_endpoint(self):
        """Test model management endpoints."""
        print("\n=== Testing Model Endpoints ===")

        # List models (should be empty initially)
        try:
            response = self.client.get(f"{self.api_base}/models")
            if response.status_code == 200:
                data = response.json()
                self.log_result("List models", True, f"Found {len(data)} models")
            else:
                self.log_result("List models", False, response.text[:100])
        except Exception as e:
            self.log_result("List models", False, str(e))

    def print_summary(self):
        """Print test summary."""
        total = self.results["passed"] + self.results["failed"]
        print("\n" + "=" * 60)
        print("VISION TRAINING API TEST SUMMARY")
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
        print("VISION TRAINING API TEST SUITE")
        print(f"Base URL: {self.base_url}")
        print(f"Project: {self.namespace}/{self.project}")
        print("=" * 60)

        # Check health first
        if not self.test_health():
            print("\n❌ API not available. Is the LlamaFarm server running?")
            return False

        # Run all test categories
        self.test_training_sets()
        self.test_face_databases()
        self.test_models_endpoint()

        # Print summary
        return self.print_summary()


def main():
    parser = argparse.ArgumentParser(description="Test Vision Training API")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the LlamaFarm API (default: {DEFAULT_BASE_URL})",
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
    args = parser.parse_args()

    tester = VisionTrainingAPITester(args.base_url, args.namespace, args.project)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
