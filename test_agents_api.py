#!/usr/bin/env python3
"""Test script for agents API endpoints.

Run this with the server running:
  nx start server
  python test_agents_api.py
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"
NAMESPACE = "default"
PROJECT = "test-project-1"

def test_list_agents():
    """Test GET /agents endpoint."""
    print("\n1. Testing: GET /agents")
    print("=" * 60)

    url = f"{BASE_URL}/v1/projects/{NAMESPACE}/{PROJECT}/agents/"
    response = requests.get(url)

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Found {data['total']} agents")
        for agent in data['agents']:
            print(f"   - {agent['name']} ({agent['type']})")
        return True
    else:
        print(f"\n❌ Failed: {response.json()}")
        return False


def test_get_agent():
    """Test GET /agents/{name} endpoint."""
    print("\n2. Testing: GET /agents/test_analyzer")
    print("=" * 60)

    url = f"{BASE_URL}/v1/projects/{NAMESPACE}/{PROJECT}/agents/test_analyzer"
    response = requests.get(url)

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        agent = response.json()
        print(f"\n✅ Agent: {agent['name']}")
        print(f"   Type: {agent['type']}")
        print(f"   Model: {agent.get('model', 'default')}")
        return True
    else:
        print(f"\n❌ Failed: {response.json()}")
        return False


def test_run_agent():
    """Test POST /agents/{name}/run endpoint."""
    print("\n3. Testing: POST /agents/test_analyzer/run")
    print("=" * 60)

    url = f"{BASE_URL}/v1/projects/{NAMESPACE}/{PROJECT}/agents/test_analyzer/run"

    payload = {
        "input": {"test": "data"},
        "parameters": {},
        "stream": False
    }

    print(f"Request payload: {json.dumps(payload, indent=2)}")

    response = requests.post(url, json=payload)

    print(f"Status: {response.status_code}")

    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        if response.status_code == 200:
            print(f"\n✅ Agent executed successfully")
            print(f"   Status: {data.get('status')}")
            return True
        else:
            print(f"\n⚠️  Agent execution had issues")
            return False
    except Exception as e:
        print(f"\n❌ Failed to parse response: {e}")
        print(f"Raw response: {response.text}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Agents API Endpoints")
    print("=" * 60)

    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/info", timeout=2)
        print(f"✅ Server is running (version: {response.json()['version']})")
    except Exception as e:
        print(f"❌ Server is not running: {e}")
        print("\nPlease start the server first:")
        print("  nx start server")
        sys.exit(1)

    # Run tests
    results = []
    results.append(("List Agents", test_list_agents()))
    results.append(("Get Agent", test_get_agent()))
    results.append(("Run Agent", test_run_agent()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
