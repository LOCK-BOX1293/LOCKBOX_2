# Backend Connection Logic for Frontend Team

This is the canonical reference for frontend developers integrating with the Hackbite backend.

## Purpose of backend layer

Backend is responsible for:

1. indexing codebase into MongoDB (`files`, `symbols`, `chunks`, `embeddings`, `edges`)
2. retrieval from indexed code (hybrid RAG)
3. question answering via orchestrated agents
4. graph payload creation for UI (full/focused)
5. node and edge context hydration (code + metadata)

Frontend should not infer repository logic on its own. It should render backend output.

---

## Ports / URLs

- Backend API: `http://localhost:8081`
- Frontend dev server (Vite): `http://localhost:5173`

Frontend env:

```env
VITE_API_BASE=http://localhost:8081
```

---

## API surface to wire

0) Repository list + onboarding

- `GET /repos` -> list existing indexed repos
- `POST /index/full` -> onboard bring-your-own repo

After onboarding, use selected `repo_id` for all following calls.

## 1) Ask endpoint (full agent pipeline)

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

Response:

```json
{
  "answer": "...",
  "intent": "where-is",
  "confidence": 0.71,
  "citations": [
    {
      "chunk_id": "...",
      "file_path": "pipeline/news_claim_pipeline/services/pipeline_service.py",
      "start_line": 1,
      "end_line": 218,
      "score": 0.023
    }
  ],
  "graph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

Use this as primary query flow.

---

## 2) Graph overview endpoint

`GET /graph/overview`

Modes:

- `mode=full` -> full graph for repo
- `mode=focused&q=<query>` -> query-focused subgraph

Example:

`/graph/overview?repo_id=hackbyte-small&branch=main&mode=focused&q=where%20is%20PipelineService&top_k=8`

---

## 3) Node details endpoint

`GET /graph/node/{node_id}` with query params:

- `repo_id`
- `branch`
- `node_type=file|symbol`

Returns code payload + functions list + metadata.

---

## 4) Edge context endpoint

`GET /graph/edge-context?repo_id=...&branch=...&from_symbol_id=...&to_symbol_id=...`

Returns relation payload + from/to symbol code context.

---

## 5) Retrieval endpoint (optional direct use)

`POST /retrieve/query`

Useful for explicit search panel or debugging, but normal UX should use `/ask` first.

---

## Frontend wiring sequence

1. On app load -> call `/graph/overview` with `mode=full`.
2. User enters query -> call `/ask`.
3. Render:
   - `answer`
   - `citations`
   - `graph` from response.
4. Node click -> call `/graph/node/{id}`.
5. Edge click -> call `/graph/edge-context`.

Current frontend implementation status:

- ✅ uses backend data for overview graph
- ✅ uses backend data for node inspector
- ✅ uses backend data for edge context
- ✅ asks backend via `/ask` with selected role and renders answer panel
- ✅ uses session id for continuity
- ✅ falls back to focused graph if ask graph payload missing
- ❌ no production-grade error toast system yet (console + placeholder text)

---

## Folder selection + node tree creation logic

Backend currently builds node trees from indexed records:

- file nodes from `symbols.file_path`
- symbol nodes from `symbols.symbol_id`
- contains edges from file -> symbol
- relation edges from `edges` collection (`calls/imports/references`)

For query-focused graph, backend selects nodes by retrieval relevance and nearby symbols in line range.

---

## Prompt + context injection logic

1. retrieval returns ranked chunks from MongoDB
2. explanation agent receives:
   - user query
   - user role
   - retrieved chunk context
   - session history
3. answer generated with citations
4. if LLM unavailable/quota issue, backend returns retrieval-grounded fallback text

So answer is always context-backed by retrieved data.

---

## Current frontend behavior caveat

If API call fails, frontend currently falls back to mock demo data in `App.tsx`.
For production behavior, remove or disable mock fallback paths.
