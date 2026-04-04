# Superplane Migration Guide

This backend now supports a modular multi-agent architecture where each agent can run as an independent API and orchestration is delegated to a Superplane-compatible layer.

## Agent Endpoints

- POST /role-agent
- POST /memory-agent
- POST /orchestrator
- POST /guard
- POST /superplane/execute

The public compatibility endpoint remains:

- GET /retrieve

`/retrieve` now forwards query execution to the Superplane client and returns additional metadata (`agents_used`, `sources`, `confidence`, `trace_id`) while preserving `results`.

## Pipeline Routing Rules

Configured in `config/superplane_pipeline.json`:

1. role
2. memory
3. orchestrator
4. guard

Dynamic routing:

- simple queries skip memory when `skip_memory_if_simple=true`
- debug-like queries force memory when `force_memory_if_debug=true`

## Memory Agent Behavior

Memory agent performs:

1. Hybrid retrieval (vector + lexical/fallback)
2. Reranking by blended retrieval score and query-term overlap
3. High-relevance filtering to top-k chunks

## Guardrails

Guard agent rejects responses when:

- unsafe response terms are detected
- confidence is below `GUARD_MIN_CONFIDENCE`

Guard output is always standardized to:

{
  "answer": "...",
  "agents_used": ["role", "memory", "orchestrator", "guard"],
  "confidence": 0.0,
  "sources": []
}

## Observability

Each agent logs structured telemetry:

- agent name
- trace_id
- latency_ms
- failures with error reason

Input/output tracing is metadata-only and excludes sensitive chunk payloads.

## Example Request/Response Flow

Request:

POST /superplane/execute
{
  "query": "how does indexing pipeline work",
  "repo_id": "lockbox2",
  "branch": "dev",
  "top_k": 5
}

Response:

{
  "answer": "Found relevant flow in src/indexer/pipeline.py lines 10-90. Top reasoning source: reranked_high_relevance.",
  "agents_used": ["role", "memory", "orchestrator", "guard"],
  "confidence": 0.82,
  "sources": ["src/indexer/pipeline.py", "src/cli/main.py"],
  "trace_id": "c36f47f9-...",
  "chunks": [...],
  "routing": {
    "simple_query": false,
    "debug_query": false,
    "memory_called": true,
    "guard_accepted": true,
    "guard_reasons": []
  }
}
