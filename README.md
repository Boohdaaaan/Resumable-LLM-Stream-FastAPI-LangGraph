## Streaming Chat Template (FastAPI · Redis Streams · LangGraph)

High-level template for resumable LLM token streaming using FastAPI, Redis Streams, and LangGraph with a Postgres checkpointer. Includes a minimal frontend and clean SSE streaming endpoints.

<img width="1512" height="838" alt="image" src="https://github.com/user-attachments/assets/fd259a7c-ce9e-4082-a20d-2b13b77dc903" />

### Features
- **Resumable streaming**: Tokens are streamed into Redis; clients consume via SSE and can resume after network hiccups.
- **LangGraph Persistence**: Conversation state persisted via LangGraph Postgres checkpointer.
- **ReAct agent**: Simple Agent with a simple web-search tool and summarization hook for long context.
- **Minimal UI**: Static frontend served from `src/frontend/`.

### Requirements
- Python 3.11+
- Redis 6+ (or compatible managed Redis)
- PostgreSQL (for LangGraph checkpoints)
- LLM provider API key (OpenAI/Anthropic/Google, selectable in config)

### Run the project
1. Clone and enter the repository:
```bash
git clone https://github.com/Boohdaaaan/Resumable-LLM-Stream-FastAPI-LangGraph
cd Resumable-LLM-Stream-FastAPI-LangGraph
```

2. Install dependencies:
- Option A (pip):
```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e .
```
- Option B (uv):
```bash
uv sync
```

3. Configure the app:
- Create a `.env` file in the project root.
- Select the LLM provider/model in `src/ai/config.py` under the `config` mapping (supported: `openai`, `anthropic`, `google`).

4. Start the API:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

5. Verify:
- Open docs at `http://localhost:8000/docs`.
- UI is served at `http://localhost:8000`.

### How streaming works (at a glance)
- `POST /v1/chat/message` accepts a user message and starts background generation that streams tokens to a Redis Stream.
- `GET /v1/chat/stream?thread_id=...` reads from Redis and relays tokens to the client via Server‑Sent Events (SSE). If the connection drops, the client can resume.

### API
- `POST /v1/chat/message`
  - Body: `{ "message": string, "thread_id"?: uuid }`
  - Returns 200 immediately; generation continues in background and tokens are streamed to Redis.

- `GET /v1/chat/stream?thread_id=<uuid>` (SSE)
  - Emits events: `chunk` (token text), `tool_call` (tool name), `system` (markers like `message_ended`, `end`).
  - Returns 204 when there is no active or already-completed stream.

- `GET /v1/thread?thread_id=<uuid>`
  - Returns the normalized message history for a thread.

- `DELETE /v1/thread?thread_id=<uuid>`
  - Deletes a thread from the DB.

- `PATCH /v1/thread?thread_id=<uuid>`
  - Body: `{ "chat_name": string }` – updates chat title.

### Minimal SSE client example (browser)
```html
<script>
  const threadId = crypto.randomUUID();

  // 1) Send a message (start background generation)
  fetch('/v1/chat/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: 'Hello!', thread_id: threadId })
  });

  // 2) Stream tokens
  const es = new EventSource(`/v1/chat/stream?thread_id=${threadId}`);
  es.onmessage = (e) => console.log('data:', e.data);
  es.addEventListener('chunk', (e) => console.log('chunk:', e.data));
  es.addEventListener('tool_call', (e) => console.log('tool:', e.data));
  es.addEventListener('system', (e) => {
    console.log('system:', e.data);
    if (e.data === 'end') es.close();
  });
</script>
```

