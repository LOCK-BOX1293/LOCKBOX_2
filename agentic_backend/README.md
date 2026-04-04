# Agentic Backend (Your Module)

This folder contains the first working implementation of the Hackbite 2 agentic layer:

- Orchestrator agent flow
- Specialist explanation + visual mapping agents
- Gemini integration using `GEMINI_API_KEY`
- Pluggable retrieval adapter (for your vector teammate)
- Session memory adapter with Mongo/in-memory fallback (for your DB teammate)

## Structure

- `app/main.py` - FastAPI app and endpoints
- `app/orchestrator.py` - routing and flow logic
- `app/agents/specialists.py` - explanation + visual mapper behaviors
- `app/retrieval/providers.py` - retrieval interface and HTTP adapter
- `app/memory/session_store.py` - session event persistence
- `app/llm/gemini.py` - Gemini API wrapper

## Required env

Uses `.env` from project root (`LOCKBOX_2/.env`).

- `GEMINI_API_KEY` (already set by you)

Optional:

- `GEMINI_MODEL` (default `gemini-1.5-flash`)
- `RETRIEVAL_SERVICE_URL` (example: `http://localhost:9000`)
- `MONGODB_URI`
- `MONGODB_DB` (default `hackbite2`)
- `RETRIEVAL_TOP_K` (default `8`)

## Run

```bash
cd agentic_backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
```

## Quick test

```bash
curl -X POST "http://127.0.0.1:8081/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":"hackbite2",
    "session_id":"s1",
    "query":"Explain orchestrator responsibilities",
    "user_role":"backend"
  }'
```

## Contract expected from retrieval service

`POST /retrieve`

Request:

```json
{
  "project_id": "hackbite2",
  "query": "where auth middleware is defined",
  "top_k": 8
}
```

Response:

```json
{
  "chunks": [
    {
      "chunk_id": "chunk_1",
      "file_path": "src/auth/middleware.ts",
      "start_line": 12,
      "end_line": 44,
      "text": "export function authMiddleware(...) { ... }",
      "score": 0.91,
      "symbol_name": "authMiddleware"
    }
  ]
}
```
