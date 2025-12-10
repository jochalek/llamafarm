#!/bin/bash
# Test script for Realtime WebSocket API
# Tests bidirectional streaming chat with the Universal Runtime

set -e

BASE_URL="${UNIVERSAL_RUNTIME_URL:-http://localhost:11540}"
WS_URL="${BASE_URL/http/ws}"

echo "========================================"
echo "Testing Realtime WebSocket API"
echo "Base URL: $BASE_URL"
echo "WebSocket URL: $WS_URL"
echo "========================================"

# Check if server is running
echo ""
echo "1. Checking server health..."
if ! curl -sf "$BASE_URL/health" > /dev/null; then
    echo "   ERROR: Server not responding at $BASE_URL"
    echo "   Start with: nx start universal"
    exit 1
fi
echo "   Server is healthy"

# Check if websocat is available (for WebSocket testing)
if ! command -v websocat &> /dev/null; then
    echo ""
    echo "   NOTE: websocat not installed. Testing with Python instead."
    echo "   To install: brew install websocat (macOS) or cargo install websocat"
    USE_PYTHON=true
else
    USE_PYTHON=false
fi

echo ""
echo "2. Testing WebSocket connection and basic flow..."

if [ "$USE_PYTHON" = true ]; then
    # Use Python for WebSocket testing
    python3 << 'PYTHON_SCRIPT'
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("   Installing websockets package...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

async def test_realtime():
    uri = "ws://localhost:11540/v1/realtime"

    print(f"   Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            # Receive session.created
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            print(f"   Received: {data['type']}")
            assert data["type"] == "session.created", f"Expected session.created, got {data['type']}"
            session_id = data["session_id"]
            print(f"   Session ID: {session_id}")

            # Update session with model config
            print("   Updating session config...")
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "model": "unsloth/Qwen3-0.6B-GGUF",
                    "temperature": 0.7,
                    "max_tokens": 100,
                    "system_prompt": "You are a helpful assistant. Keep responses brief."
                }
            }))

            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            print(f"   Received: {data['type']}")
            assert data["type"] == "session.updated", f"Expected session.updated, got {data['type']}"

            # Append input text
            print("   Sending input text...")
            await ws.send(json.dumps({
                "type": "input_text.append",
                "text": "Say hello in exactly 5 words."
            }))

            # Commit input (triggers generation)
            print("   Committing input to start generation...")
            await ws.send(json.dumps({
                "type": "input_text.commit"
            }))

            # Receive messages until response.done
            committed = False
            deltas = []
            done = False

            while not done:
                msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                data = json.loads(msg)
                msg_type = data["type"]

                if msg_type == "input_text.committed":
                    committed = True
                    print(f"   Input committed: '{data['text']}'")
                elif msg_type == "response.text.delta":
                    delta = data["delta"]
                    deltas.append(delta)
                    print(f"   Token: '{delta}'", end="", flush=True)
                elif msg_type == "response.text.done":
                    print("")  # newline after tokens
                    print(f"   Full response: '{data['text']}'")
                elif msg_type == "response.done":
                    done = True
                    print(f"   Response complete!")
                elif msg_type == "error":
                    print(f"   ERROR: {data['message']}")
                    return False

            # Verify we got expected messages
            assert committed, "Never received input_text.committed"
            assert len(deltas) > 0, "No tokens received"

            print("")
            print("   SUCCESS: Basic flow test passed!")
            print(f"   - Received {len(deltas)} tokens")

            return True

    except asyncio.TimeoutError:
        print("   ERROR: Timeout waiting for response")
        return False
    except Exception as e:
        print(f"   ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if asyncio.run(test_realtime()):
    sys.exit(0)
else:
    sys.exit(1)
PYTHON_SCRIPT
else
    # Use websocat for WebSocket testing
    echo "   Using websocat for testing..."

    # Create a simple test that connects and receives session.created
    RESPONSE=$(echo '{"type": "input_text.append", "text": "Hi"}' | websocat -n1 "$WS_URL/v1/realtime" 2>&1 | head -1)

    if echo "$RESPONSE" | grep -q "session.created"; then
        echo "   SUCCESS: WebSocket connection established"
        echo "   Response: $RESPONSE"
    else
        echo "   ERROR: Unexpected response: $RESPONSE"
        exit 1
    fi
fi

echo ""
echo "3. Testing cancellation..."

python3 << 'PYTHON_SCRIPT'
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

async def test_cancellation():
    uri = "ws://localhost:11540/v1/realtime"

    print(f"   Testing cancellation at {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            # Receive session.created
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data["type"] == "session.created"

            # Update session with a slower config to ensure we can cancel
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "model": "unsloth/Qwen3-0.6B-GGUF",
                    "temperature": 0.7,
                    "max_tokens": 500,  # Request long response
                    "system_prompt": "You are a storyteller. Tell detailed stories."
                }
            }))

            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data["type"] == "session.updated"

            # Send input
            await ws.send(json.dumps({
                "type": "input_text.append",
                "text": "Tell me a very long story about a dragon."
            }))

            # Commit input
            await ws.send(json.dumps({
                "type": "input_text.commit"
            }))

            # Wait for a few tokens, then cancel
            token_count = 0
            while token_count < 10:
                msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                data = json.loads(msg)
                if data["type"] == "response.text.delta":
                    token_count += 1
                    print(f"   Token {token_count}: '{data['delta']}'", end="", flush=True)
                elif data["type"] == "input_text.committed":
                    print(f"   Input committed")
                elif data["type"] in ["response.text.done", "response.done"]:
                    # Response finished before we could cancel - that's ok
                    print("")
                    print("   Response finished before cancellation (model was fast)")
                    return True

            print("")
            print("   Sending cancel request...")
            await ws.send(json.dumps({
                "type": "response.cancel"
            }))

            # Wait for cancelled message
            cancelled = False
            timeout = asyncio.get_event_loop().time() + 5.0

            while asyncio.get_event_loop().time() < timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(msg)
                    print(f"   Received: {data['type']}")

                    if data["type"] == "response.cancelled":
                        cancelled = True
                        print(f"   Partial text length: {len(data.get('partial_text', ''))}")
                        break
                    elif data["type"] == "response.done":
                        # Response completed before cancel was processed
                        print("   Response completed before cancel")
                        return True
                except asyncio.TimeoutError:
                    break

            if cancelled:
                print("   SUCCESS: Cancellation test passed!")
            else:
                print("   WARNING: Cancel message not received (may have completed first)")

            return True

    except Exception as e:
        print(f"   ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if asyncio.run(test_cancellation()):
    sys.exit(0)
else:
    sys.exit(1)
PYTHON_SCRIPT

echo ""
echo "========================================"
echo "Realtime WebSocket tests complete!"
echo "========================================"
