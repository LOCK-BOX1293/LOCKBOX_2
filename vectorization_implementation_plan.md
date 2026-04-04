# Codebase Vectorization and Retrieval System

This plan outlines the architecture and implementation strategy for the MongoDB Atlas-backed codebase vectorization and retrieval system.

## User Review Required

> [!IMPORTANT]
> - Do you want to explicitly pin specific `tree-sitter` language bindings versions (e.g., `tree-sitter==0.21.3`, `tree-sitter-python==0.21.0`), as `tree-sitter` APIs have changed significantly recently?
> - Should we use Poetry or `requirements.txt` / `pip` + `venv` for dependency management? I will default to `requirements.txt` for simplicity unless specified.
> - The prompt mentions "tree-sitter or robust AST parsers". We will use `tree-sitter` with `tree-sitter-python` and `tree-sitter-typescript` bindings. Let me know if you prefer Python's built-in `ast` for Python files instead.

## Proposed Changes

### Project Setup and Configuration
We will use Python 3.11+ and set up the following package structure. We'll use `pydantic` heavily for data modeling, config management, and validation. `pymongo` will be used for MongoDB interactions.

#### [NEW] `requirements.txt`
Dependencies:
- `fastapi`, `uvicorn` (API)
- `typer` (CLI)
- `pymongo` (Storage)
- `pydantic`, `pydantic-settings` (Config/Validation)
- `tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript` (Parsing/Chunking)
- `sentence-transformers` (Local Embeddings)
- `openai`, `google-cloud-aiplatform` (Cloud Embeddings - optional imports)
- `structlog` or `rich` (Logging)
- `pathspec` (Gitignore evaluation)
- `pytest`, `mongomock` (Testing)

#### [NEW] `src/core/config.py`
`pydantic-settings` based configuration handling `.env` defaults securely.

### Data Storage & Schemas
We will implement data models corresponding to the requested collections.

#### [NEW] `src/schemas/*`
Pydantic schemas for `Repo`, `File`, `Symbol`, `Chunk`, `Embedding`, `Edge`, `IndexJob`, `Session`. These will handle serialization to and from MongoDB documents.

#### [NEW] `src/storage/mongo.py`
MongoDB client manager wrapper.

#### [NEW] `src/storage/repositories.py`
Repository pattern implementations for each schema:
- `RepoRepository`
- `FileRepository`
- `ChunkRepository`
- `SymbolRepository`, etc.
Methods will include `upsert`, `bulk_write` with idempotency guarantees (using `UpdateOne` with `upsert=True` based on unique keys).
Also includes an `ensure_indexes` administrative function that creates standard indices and configures the Atlas Vector Search schema logic (creates search index definitions to be manually or programmatically applied to Atlas).

### Code Processing Pipeline

#### [NEW] `src/scanner/repo_scanner.py`
Walks a local repository. Respects `.gitignore` using standard library `pathspec`. Yields files, computes `hashlib.sha256` for contents to determine if a file changed (for incremental indexing).

#### [NEW] `src/parser/ast_parser.py`
Language-specific parsers using `tree-sitter`. Extracts symbols (classes, functions, methods, imports) utilizing tailored queries for Python and JS/TS.

#### [NEW] `src/chunker/semantic_chunker.py`
Uses extracted symbols to form semantic chunks. Large functions are split using overlapping windows or recursive character splitting. Hashes chunk contents and assigns deterministic `chunk_id`.

### Embeddings and Retrieval

#### [NEW] `src/embedder/base.py` & Implementations
`BaseEmbedder` abstract class. Implementations:
- `LocalEmbedder` (using `sentence-transformers`)
- `OpenAIEmbedder`
Batch embedding support with exponential backoff retries.

#### [NEW] `src/retrieval/search.py`
Implements the hybrid search flow:
1. `vector_search` using `$vectorSearch`.
2. `lexical_search` using `$search` (text search on content/names).
3. `fuse_results` using Reciprocal Rank Fusion (RRF).

### Orchestration and External Interfaces

#### [NEW] `src/indexer/pipeline.py`
Coordinates the full and incremental indexing flows:
1. Initialize `IndexJob`.
2. Scan repo (diffing for incremental).
3. Delete stale records in DB.
4. Parse & Chunk new/modified files.
5. Embed chunks in batches.
6. Upsert records.
7. Finalize `IndexJob`.

#### [NEW] `src/api/routes.py`
FastAPI generic setup and `/retrieve` endpoints that return a robust context pack with citations to the chunk sources.

#### [NEW] `src/cli/main.py`
`typer` app exposing requested commands:
- `index full`
- `index incremental`
- `index ensure-indexes`
- `retrieve query`
- `jobs status`
- `debug validate-dimensions`

## Open Questions

- Atlas Search and Vector Search endpoints usually require deploying the indexes explicitly in the Atlas UI or via the Atlas Admin API since `pymongo` driver standard `create_index` only handles traditional b-tree indexes. The Search indices use the `createSearchIndexes` command in MongoDB 7.0+. Is it acceptable if the `ensure-indexes` CLI command explicitly runs the `createSearchIndexes` database command, assuming the target cluster is MongoDB 7.0+?
- Is there a preferred default embedding model for local? `all-MiniLM-L6-v2` is fast and standard.

## Verification Plan

### Automated Tests
1. **Unit Tests**:
   - `test_scanner.py`: Ignoring correctly, finding files, computing hashes.
   - `test_parser.py`: Verify tree-sitter symbols for Python sample.
   - `test_chunker.py`: Verify chunk bounds and reproducibility of chunk IDs.
2. **Integration Tests**:
   - Setup a `pytest` fixture with a temporary git repo.
   - Run indexing through CLI pipeline against a live test db if available/mock.

### Manual Verification
1. I will write the source code into the `LOCKBOX_2` directory as a python package.
2. I will prepare test scripts executing `typer` CLI.
3. Once completed, I will output the final summary of setup and testing instructions.
