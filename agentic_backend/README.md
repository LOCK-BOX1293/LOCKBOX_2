# RoleReady MongoDB-First Index + Retrieval Backend

Production-oriented backend for repository indexing, vectorization, and hybrid retrieval using MongoDB Atlas as the primary operational and search platform.

## Architecture

```text
repo.scan -> code.parse -> chunk.build -> embed.generate -> mongo.write
                                            |
                                            v
                                     atlas.vectorSearch + atlas.textSearch
                                            |
                                      weighted fusion + rerank
                                            |
                           context pack (citations + confidence + graph links)
```

## Implemented modules

- scanner: repository scan, language detection, git commit and diff support
- parser: symbol extraction for Python and JS/TS
- chunker: symbol-aware semantic chunking and deterministic fallback window chunking
- embedder: provider abstraction (local, openai, vertex), batching and retry
- storage: Mongo repositories, idempotent upserts, schema indexes, Atlas search index creation
- indexer: full and incremental indexing orchestration with job tracking and metrics
- retrieval: vector search + lexical search + weighted fusion + graph expansion + rerank
- api: FastAPI endpoints for indexing, retrieval, jobs, node code, and edge context
- cli: operational command suite for indexing/retrieval/diagnostics

## MongoDB collections

- repos
- files
- symbols
- chunks
- embeddings
- edges
- index_jobs
- sessions
- retrieval_runs

## Required indexes

Standard indexes and unique constraints are created in app/storage/mongo_store.py and include:

- chunks: repo_id + branch + file_path
- chunks: repo_id + branch + content_hash
- symbols: repo_id + branch + file_path + name
- files: repo_id + branch + file_path + commit_sha
- index_jobs: repo_id + started_at
- files unique: repo_id + branch + commit_sha + file_path
- chunks unique: repo_id + branch + commit_sha + chunk_id
- symbols unique: repo_id + branch + commit_sha + symbol_id

Atlas indexes created/validated:

- embeddings_vector_v1 on embeddings.vector (cosine, configured dimensions)
- chunks_text_v1 on chunks.content + file_path + metadata fields

## API endpoints

- GET /health
- POST /index/full
- POST /index/incremental
- POST /index/ensure-indexes
- POST /retrieve/query
- POST /mindflow/turn
- GET /jobs/{repo_id}
- GET /graph/node/{node_id}
- GET /graph/edge-context

Node/edge support for web UI:

- graph node endpoint returns code payload for file or symbol node
- edge-context returns connection metadata and code snippets for both sides of the edge

Mindflow endpoint:

- `/mindflow/turn` executes one orchestrator loop (chat + node/edge updates + optional search enrichment + drift-based workspace switching)

## CLI

Run from agentic_backend:

- python -m app index full --repo-path <path> --repo-id <id> --branch <branch>
- python -m app index incremental --repo-path <path> --repo-id <id> --branch <branch>
- python -m app index ensure-indexes --repo-id <id>
- python -m app retrieve query --repo-id <id> --branch <branch> --q "..." --top-k 8 --lang python --path-prefix src/
- python -m app jobs status --repo-id <id>
- python -m app debug validate-dimensions --expected 1536

## Quickstart

1. Install dependencies

```bash
cd agentic_backend
pip install -r requirements.txt
```

2. Configure env

```bash
copy .env.example ..\.env
```

3. Run API

```bash
uvicorn app.main:app --reload --port 8081
```

4. Run tests

```bash
pytest -q
```

## Query output format

```json
{
  "chunks": [
    {
      "chunk_id": "...",
      "file_path": "src/module/file.py",
      "start_line": 10,
      "end_line": 33,
      "content": "...",
      "score": 0.094211,
      "reason": "hybrid-fusion+rerank"
    }
  ],
  "confidence": 0.71
}
```

## Incremental indexing rules

- full: scan and process all eligible files
- incremental: prefer git diff changed files, fallback to file hash comparison
- deleted files: remove stale files/symbols/chunks/embeddings/edges for repo+branch scope
- idempotent upsert keys ensure no duplication

## Migration notes

- edges schema is in place for graph expansion and future call/import/reference enrichment
- retrieval_runs collection is reserved for full trace persistence
- expert-answer agent integration can consume current context pack without schema changes
