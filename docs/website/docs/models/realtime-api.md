---
title: Realtime WebSocket API
sidebar_position: 5
---

# Realtime WebSocket API

The Universal Runtime provides a WebSocket-based Realtime API for bidirectional LLM chat. Inspired by OpenAI's Realtime API, this enables:

- **Input buffering**: Build up input text incrementally before sending
- **Streaming output**: Receive generated tokens as they're produced
- **Mid-generation cancellation**: Cancel a response while it's being generated
- **Session management**: Maintain conversation history across turns

## Quick Start

### Connect

```javascript
const ws = new WebSocket('ws://localhost:11540/v1/realtime');

ws.onopen = () => {
  console.log('Connected!');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message.type);
};
```

### Configure Session

```javascript
// After receiving session.created
ws.send(JSON.stringify({
  type: 'session.update',
  session: {
    model: 'unsloth/Qwen3-0.6B-GGUF',
    temperature: 0.7,
    max_tokens: 512,
    system_prompt: 'You are a helpful assistant.'
  }
}));
```

### Send a Message

```javascript
// Append text to input buffer
ws.send(JSON.stringify({
  type: 'input_text.append',
  text: 'Hello, how are you?'
}));

// Commit to start generation
ws.send(JSON.stringify({
  type: 'input_text.commit'
}));

// Handle streaming response
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'response.text.delta') {
    process.stdout.write(msg.delta); // Print tokens as they arrive
  } else if (msg.type === 'response.done') {
    console.log('\n--- Response complete ---');
  }
};
```

### Cancel Generation

```javascript
// Cancel while response is being generated
ws.send(JSON.stringify({
  type: 'response.cancel'
}));

// Will receive response.cancelled with partial text
```

---

## Protocol Reference

### Connection Flow

```
Client                              Server
  |                                    |
  |-------- WebSocket Connect -------->|
  |                                    |
  |<------ session.created ------------|
  |                                    |
  |-------- session.update ----------->|
  |<------ session.updated ------------|
  |                                    |
  |-------- input_text.append -------->|
  |-------- input_text.commit -------->|
  |                                    |
  |<------ input_text.committed -------|
  |<------ response.text.delta --------|
  |<------ response.text.delta --------|
  |<------ response.text.delta --------|
  |<------ response.text.done ---------|
  |<------ response.done --------------|
  |                                    |
```

### Client → Server Messages

#### session.update

Update session configuration.

```json
{
  "type": "session.update",
  "session": {
    "model": "unsloth/Qwen3-0.6B-GGUF",
    "temperature": 0.7,
    "max_tokens": 512,
    "top_p": 1.0,
    "n_ctx": null,
    "system_prompt": "You are a helpful assistant.",
    "stop": null,
    "think": false,
    "thinking_budget": null
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | `unsloth/Qwen3-0.6B-GGUF` | Model identifier (GGUF or Transformers) |
| `temperature` | float | `0.7` | Sampling temperature |
| `max_tokens` | int | `512` | Maximum tokens to generate |
| `top_p` | float | `1.0` | Nucleus sampling threshold |
| `n_ctx` | int | `null` | Context window size (null = auto) |
| `system_prompt` | string | `null` | System prompt for the conversation |
| `stop` | string[] | `null` | Stop sequences |
| `think` | bool | `false` | Enable thinking mode (Qwen models) |
| `thinking_budget` | int | `null` | Max tokens for thinking |

#### input_text.append

Append text to the input buffer. Can be called multiple times to build up the message.

```json
{
  "type": "input_text.append",
  "text": "Hello, "
}
```

#### input_text.clear

Clear the input buffer without sending.

```json
{
  "type": "input_text.clear"
}
```

#### input_text.commit

**Commit** finalizes your input and triggers LLM generation. Think of it like pressing "Send" in a chat app:

1. Takes all text accumulated in the input buffer (via `input_text.append`)
2. Adds it to conversation history as a user message
3. Clears the input buffer
4. Starts streaming the LLM response
5. Uses any cached RAG results (if `rag.preview` was called)

```json
{
  "type": "input_text.commit"
}
```

**Why use input buffering?** The append/commit pattern enables:
- **Incremental input**: Build text from voice-to-text, collaborative editing, or keystroke streaming
- **Preview before sending**: Show RAG documents or validate input before committing
- **Cancel before commit**: Clear buffer without sending (`input_text.clear`)

#### response.cancel

Cancel the current generation. Any partial response is returned.

```json
{
  "type": "response.cancel"
}
```

### Server → Client Messages

#### session.created

Sent immediately after WebSocket connection.

```json
{
  "type": "session.created",
  "session_id": "rt_abc123def456",
  "session": {
    "model": "unsloth/Qwen3-0.6B-GGUF",
    "temperature": 0.7,
    ...
  }
}
```

#### session.updated

Sent after session.update is processed.

```json
{
  "type": "session.updated",
  "session": { ... }
}
```

#### input_text.committed

Sent when input is committed and generation is starting.

```json
{
  "type": "input_text.committed",
  "text": "Hello, how are you?",
  "item_id": "msg_abc123"
}
```

#### input_text.cleared

Sent when input buffer is cleared.

```json
{
  "type": "input_text.cleared"
}
```

#### response.text.delta

Sent for each generated token during streaming.

```json
{
  "type": "response.text.delta",
  "item_id": "msg_xyz789",
  "delta": "Hello"
}
```

#### response.text.done

Sent when text generation is complete (before response.done).

```json
{
  "type": "response.text.done",
  "item_id": "msg_xyz789",
  "text": "Hello! I'm doing well, thank you for asking."
}
```

#### response.done

Sent when the full response is complete.

```json
{
  "type": "response.done",
  "item_id": "msg_xyz789"
}
```

#### response.cancelled

Sent when generation was cancelled.

```json
{
  "type": "response.cancelled",
  "item_id": "msg_xyz789",
  "partial_text": "Hello! I'm do"
}
```

#### error

Sent when an error occurs.

```json
{
  "type": "error",
  "code": "generation_failed",
  "message": "Model not found: invalid-model",
  "details": null
}
```

---

## Use Cases

### Real-time Chat Interface

Build responsive chat UIs where users see tokens appear as they're generated:

```javascript
let responseDiv = document.getElementById('response');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'response.text.delta') {
    responseDiv.textContent += msg.delta;
  }
};
```

### Interruptible AI Assistant

Allow users to cancel long responses:

```javascript
document.getElementById('stopBtn').onclick = () => {
  ws.send(JSON.stringify({ type: 'response.cancel' }));
};
```

### Text Input with Preview

Build up text before sending (useful for voice-to-text or collaborative editing):

```javascript
// As user types or speaks
function onTextChunk(chunk) {
  ws.send(JSON.stringify({
    type: 'input_text.append',
    text: chunk
  }));
}

// When user is done
function onSubmit() {
  ws.send(JSON.stringify({ type: 'input_text.commit' }));
}
```

### Multi-turn Conversations

The session maintains conversation history automatically:

```javascript
// Turn 1
ws.send(JSON.stringify({ type: 'input_text.append', text: 'What is Python?' }));
ws.send(JSON.stringify({ type: 'input_text.commit' }));
// ... receive response ...

// Turn 2 - context is preserved
ws.send(JSON.stringify({ type: 'input_text.append', text: 'Give me an example.' }));
ws.send(JSON.stringify({ type: 'input_text.commit' }));
// Response will know we're talking about Python
```

---

## Python Client Example

```python
import asyncio
import json
import websockets

async def realtime_chat():
    uri = "ws://localhost:11540/v1/realtime"

    async with websockets.connect(uri) as ws:
        # Wait for session.created
        msg = await ws.recv()
        print(f"Connected: {json.loads(msg)['session_id']}")

        # Configure session
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "model": "unsloth/Qwen3-0.6B-GGUF",
                "system_prompt": "You are a helpful assistant."
            }
        }))
        await ws.recv()  # session.updated

        # Chat loop
        while True:
            user_input = input("You: ")
            if user_input.lower() == 'quit':
                break

            # Send message
            await ws.send(json.dumps({
                "type": "input_text.append",
                "text": user_input
            }))
            await ws.send(json.dumps({
                "type": "input_text.commit"
            }))

            # Print streaming response
            print("Assistant: ", end="", flush=True)
            while True:
                msg = json.loads(await ws.recv())

                if msg["type"] == "response.text.delta":
                    print(msg["delta"], end="", flush=True)
                elif msg["type"] == "response.done":
                    print()  # newline
                    break

asyncio.run(realtime_chat())
```

---

## RAG Preview (LlamaFarm Server)

When using the LlamaFarm server's realtime endpoint (`/v1/projects/{ns}/{proj}/realtime`), you can preview RAG results before committing your message. This is useful for:

- Showing users what documents will be used
- Validating that RAG is finding relevant content
- Caching results to speed up generation

### Enable RAG

```javascript
ws.send(JSON.stringify({
  type: 'session.update',
  session: {
    rag: {
      enabled: true,
      database: 'my_docs',
      top_k: 5
    }
  }
}));
```

### Preview RAG Results

```javascript
// Build up your query
ws.send(JSON.stringify({
  type: 'input_text.append',
  text: 'What are the FDA requirements?'
}));

// Request RAG preview (searches and caches results)
ws.send(JSON.stringify({
  type: 'rag.preview'
}));

// Handle preview response
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'rag.preview_searching') {
    console.log('Searching:', msg.query);
  }

  if (msg.type === 'rag.preview_result') {
    console.log(`Found ${msg.chunks_count} relevant documents`);
    msg.chunks.forEach(chunk => {
      console.log(`- ${chunk.source}: ${chunk.content}`);
    });
  }
};

// When ready, commit - uses cached RAG results
ws.send(JSON.stringify({ type: 'input_text.commit' }));
```

### RAG Preview Response

```json
{
  "type": "rag.preview_result",
  "query": "What are the FDA requirements?",
  "chunks_count": 5,
  "chunks": [
    {
      "content": "FDA requirements for clinical trials include...",
      "score": 0.92,
      "source": "fda_guidelines.pdf"
    },
    {
      "content": "Section 21 CFR Part 11 outlines...",
      "score": 0.87,
      "source": "regulations.pdf"
    }
  ],
  "database": "my_docs",
  "retrieval_strategy": "hybrid",
  "cached": false
}
```

### Debounced Preview Pattern

For real-time preview as users type, use debouncing:

```javascript
let previewTimeout = null;

function onUserTyping(text) {
  // Append text
  ws.send(JSON.stringify({
    type: 'input_text.append',
    text: text
  }));

  // Debounce RAG preview (500ms after typing stops)
  clearTimeout(previewTimeout);
  previewTimeout = setTimeout(() => {
    ws.send(JSON.stringify({ type: 'rag.preview' }));
  }, 500);
}
```

---

## Comparison with SSE Streaming

| Feature | Realtime WebSocket | SSE Chat Completions |
|---------|-------------------|---------------------|
| **Protocol** | WebSocket (bidirectional) | HTTP + SSE (unidirectional) |
| **Input buffering** | Yes | No |
| **Cancellation** | Yes (mid-stream) | Close connection |
| **Session state** | Server-side | Client manages |
| **Conversation history** | Automatic | Send full history each request |
| **Use case** | Interactive chat UIs | Simple integrations |

Choose **Realtime WebSocket** when you need:
- True bidirectional communication
- Mid-generation cancellation
- Input buffering (voice-to-text, etc.)
- Persistent sessions

Choose **SSE Chat Completions** when you need:
- Simple request/response pattern
- Stateless interactions
- Maximum compatibility

---

## Next Steps

- [Chat Completions API](./index.md#universal-runtime) - SSE-based streaming
- [Specialized ML Models](./specialized-ml.md) - OCR, classification, anomaly detection
- [API Reference](../api/index.md) - Full API documentation
