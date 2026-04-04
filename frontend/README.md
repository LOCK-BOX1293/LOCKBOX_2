# Hackbite Frontend Wiring Guide

This frontend is the UI layer over the Hackbite agentic backend.

It is responsible for:

- sending user questions to backend agents (`/ask`)
- showing query-focused/full graph (`/graph/overview`)
- showing node code/details (`/graph/node/{node_id}`)
- showing edge context between nodes (`/graph/edge-context`)

---

## 1) Ports and services

### Backend API (FastAPI)

- Default URL: `http://localhost:8081`
- Start command (from `agentic_backend/`):

```bash
uvicorn app.main:app --reload --port 8081
```

### Frontend (Vite + React)

- Default dev URL: `http://localhost:5173`
- Start command (from `frontend/`):

```bash
pnpm dev
```

---

## 2) Frontend environment

Create `frontend/.env` from `frontend/.env.example`:

```bash
cp .env.example .env
```

Set backend base URL:

```env
VITE_API_BASE=http://localhost:8081
```

The frontend API client reads this in `src/api.ts`.

---

## 3) API contracts the frontend should call

## A. Ask (agent orchestration)

`POST /ask`

Request:

```json
{
  "project_id": "hackbyte-small",
  "session_id": "sess-1",
  "query": "where is PipelineService defined?",
  "user_role": "backend"
}
```

Response includes:

- `answer`
- `intent`
- `confidence`
- `citations[]`
- `graph { nodes, edges }`

Use this to render the assistant answer panel + focused graph from agent output.

## B. Graph overview

`GET /graph/overview?repo_id=<id>&branch=main&mode=full`

or query-focused:

`GET /graph/overview?repo_id=<id>&branch=main&mode=focused&q=<query>&top_k=8`

Use this for graph canvas data source.

## C. Node details

`GET /graph/node/{node_id}?repo_id=<id>&branch=main&node_type=file|symbol`

Returns:

- `code`
- `functions[]` (symbols in file / selected symbol)
- metadata (line range, language, size, etc.)

Use this for right-side inspector / code drawer.

## D. Edge context

`GET /graph/edge-context?repo_id=<id>&branch=main&from_symbol_id=<a>&to_symbol_id=<b>`

Returns both endpoint symbol payloads and relation context.

Use this when user clicks an edge.

---

## 4) Backend agent purpose (what frontend is visualizing)

- **Router/Orchestrator**: decides flow for each question
- **Retrieval Agent**: gets relevant chunks from Mongo (hybrid retrieval)
- **Node Selector/Visual Mapper**: produces graph nodes and edges
- **Explanation Agent**: turns context into answer text + citations

Frontend should treat backend as source of truth and only render the structured output.

---

## 5) Frontend wiring flow

1. User types query.
2. UI calls `POST /ask`.
3. Show answer + citations.
4. Load graph from `ask.graph` (or call `/graph/overview?mode=focused`).
5. On node click -> call `/graph/node/{node_id}` and render code.
6. On edge click -> call `/graph/edge-context` and render relation panel.

---

## 6) Quick local run (end-to-end)

Terminal A:

```bash
cd /home/rudra/Code/hackbite_2/agentic_backend
uvicorn app.main:app --reload --port 8081
```

Terminal B:

```bash
cd /home/rudra/Code/hackbite_2/frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173`.

---

## 7) Important note

If LLM generation is quota-limited, backend still returns retrieval-grounded fallback text + citations so frontend can continue functioning.
