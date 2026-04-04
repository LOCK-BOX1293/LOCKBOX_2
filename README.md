# RoleReady 🎯

Don't watch training. Live it.

Hackbite 2 is a **web-first, index-first, multi-agent system** for understanding large codebases.

It starts by indexing your repository into structured knowledge (symbols, chunks, embeddings, relationships), then gives a **clickable visual interface** where each node/file/function opens related code and explanations.

> TUI is supported for basic usage, but the **primary product experience is the web app**.

---

## Core Product Principles

1. **Web First**: main UX is visual and clickable.
2. **Index First**: first request triggers full indexing and knowledge graph creation.
3. **Simple but Powerful**: fast answers + traceable, interactive evidence.
4. **Agentic by Design**: multiple specialized agents cooperate on each request.

---

## What It Does

- Connect a repo (GitHub/local)
- Auto-ingest and index codebase
- Build symbol graph + hybrid retrieval indexes
- Answer developer questions with citations
- Show clickable code map and dependency graph
- Let users drill into exact files, functions, call paths, and related snippets

---

## Multi-Agent Architecture

Hackbite 2 uses specialized agents coordinated by an orchestrator.

### 1) Orchestrator Agent (Svami)
**Role**: traffic controller and planner

- Detects intent (`find`, `explain`, `debug`, `where-is`, `refactor`)
- Decides which specialist agents to invoke
- Combines outputs into final response
- Handles retries, fallbacks, and confidence scoring

### 2) Ingestion Agent
**Role**: repository processing pipeline

- Scans files and applies filters
- Parses AST/tree-sitter for symbols
- Chunks content on semantic boundaries
- Emits metadata: file path, symbol name/type, lines, language

### 3) Indexing Agent
**Role**: searchable knowledge creation

- Generates embeddings (code + docs)
- Writes to vector index
- Writes to lexical/BM25 index
- Updates graph relations (imports, calls, references)

### 4) Retrieval Agent (RAG Core)
**Role**: high-quality context fetch

- Runs **hybrid retrieval** (vector + lexical + graph expansion)
- Fuses candidates (RRF/weighted fusion)
- Reranks top results
- Returns compact, high-signal context blocks

### 5) Explanation Agent
**Role**: answer generation and teaching

- Produces concise technical explanations
- Includes source citations and line-level references
- Adapts style by role (backend/frontend/security/devops)

### 6) Visual Mapping Agent
**Role**: UI-ready structure

- Converts retrieval/graph output into clickable nodes/edges
- Highlights “why this was retrieved”
- Provides related symbols, usages, and test links

### 7) Session Memory Agent
**Role**: continuity and personalization

- Stores conversation context and user focus areas
- Tracks recent files/symbols/questions
- Improves follow-up query understanding

---

## Request Lifecycle

1. User asks question in web UI
2. Orchestrator classifies intent
3. Retrieval Agent fetches relevant context (hybrid)
4. Explanation Agent generates answer + citations
5. Visual Mapping Agent prepares clickable graph
6. UI renders answer + highlighted code + interactive nodes

If no index exists, system runs:
`Ingestion Agent -> Indexing Agent -> Graph build -> Query execution`

---

## RAG Strategy (Better-Than-Basic)

- **Hybrid retrieval**: vector + BM25 + graph neighbors
- **Symbol-first chunking**: function/class/module aware
- **Metadata filters**: language, path, service, ownership
- **Reranking**: improve precision on final context window
- **Grounded generation**: answer only from retrieved evidence

---

## Web UX (Primary)

### Main Screens

1. **Repository Dashboard**
   - indexing status, repo stats, health

2. **Interactive Code Map**
   - nodes: modules/classes/functions
   - edges: import/call/reference dependencies

3. **Code Viewer**
   - syntax-highlighted file/symbol panel
   - line-level highlights from retrieval

4. **Q&A Workspace**
   - answers with cited snippets
   - “why shown” relevance panel

### Click-to-Explore Behavior

Click any node (file/function/class) to open:
- definition
- usages/references
- related snippets
- nearby dependency graph
- recent discussions related to that symbol

---

## TUI (Secondary)

TUI is for quick terminal workflows:
- start indexing
- ask question
- view top sources
- inspect service/agent health

---

## Suggested Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Next.js + React + Monaco + Cytoscape/D3
- **Queue/Workers**: Redis + Celery/Arq
- **Vector DB**: Qdrant/Weaviate/Pinecone
- **Lexical Search**: OpenSearch/Elasticsearch
- **Graph Store**: Neo4j (or lightweight graph layer)
- **LLM Layer**: pluggable (Gemini/Claude/OpenAI)
- **Observability**: OpenTelemetry + Prometheus + Grafana

---

## Monorepo Skeleton (Recommended)

```text
hackbite_2/
├── apps/
│   ├── web/                  # Next.js web app (main product)
│   ├── tui/                  # Terminal UI (secondary)
│   └── api/                  # FastAPI gateway
├── agents/
│   ├── orchestrator/
│   ├── ingestion/
│   ├── indexing/
│   ├── retrieval/
│   ├── explanation/
│   ├── visual-mapper/
│   └── memory/
├── libs/
│   ├── parsers/
│   ├── embeddings/
│   ├── ranking/
│   ├── graph/
│   └── shared-models/
├── infra/
│   ├── docker/
│   └── k8s/
├── scripts/
│   ├── ingest_repo.py
│   └── reindex_changed_files.py
└── README.md
```

---

## V1 Scope (Keep It Tight)

1. Repo connect + automatic indexing
2. Hybrid search API
3. Q&A API with citations
4. Web code viewer + basic graph
5. Click node -> show related code

---

## Long-Term Roadmap

- Incremental indexing from git diff
- PR-aware reasoning and review suggestions
- Team knowledge memory and ownership maps
- Agent-to-agent planning with cost-aware routing
- Multi-repo dependency intelligence

---

## Project Status

🚧 Early architecture stage — designed for a strong V1 that is usable fast, then hardens into production.

---

## License

Add your preferred license (`MIT`, `Apache-2.0`, etc.)
