# Hackbite 2 Vectorization and Retrieval System

A production-ready end-to-end Python system that scans a source repository, extracts code symbols, generates semantic chunks with embeddings, and stores them in MongoDB Atlas for hybrid semantic search.

## Architecture

![Architecture](https://via.placeholder.com/800x400.png?text=RepoScanner+->+ASTParser+->+SemanticChunker+->+BatchEmbedder+->+MongoDB)

The pipeline incorporates:
1. **Scanner**: Scans standard directories respecting `.gitignore`.
2. **Parser**: Uses tree-sitter to break down files into functions/classes.
3. **Chunker**: Splits large files while keeping symbols logically intact.
4. **Embedder**: Pluggable embedder (Sentence Transformers or OpenAI).
5. **Storage**: Interacts with MongoDB. Upsert capabilities ensure idempotency.
6. **Search**: Hybrid search using Reciprocal Rank Fusion on Vector Search and Lexical Search results.

## Quickstart

### Setup Requirements
1. Python 3.11+
2. MongoDB Atlas Cluster (version 7.0+ for Vector/Search index integration)
3. SentenceTransformers (default) or OpenAI credentials.

### Installation
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### Configuration
Create a `.env` in the root:
```env
MONGODB_URI=mongodb+srv://<USER>:<PASS>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=hackbite2
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
```

## CLI Usage

### 1. Ensure Database Indexes
This command sets up the necessary MongoDB uniqueness constraints and Atlas Search indexes. 
*(Note: Attempting to create Atlas Search indexes via pymongo CLI requires MongoDB 7.0+)*
```bash
python -m src.cli.main index ensure-indexes
```

### 2. Full Indexing
Perform a clean indexing of the target repository.
```bash
python -m src.cli.main index full \
    --repo-path ./ \
    --repo-id myconfig-repo \
    --branch main
```

### 3. Incremental Indexing
Updates the index efficiently by relying on file content hashing.
```bash
python -m src.cli.main index incremental \
    --repo-path ./ \
    --repo-id myconfig-repo \
    --branch main
```

### 4. Search and Retrieve
Uses hybrid search combining Atlas Vector Search and regular Atlas Search.
```bash
python -m src.cli.main retrieve query \
    --repo-id myconfig-repo \
    --q "How does the indexing pipeline work?" \
    --top-k 3
```

## Future Expansions (Migration Notes)
- **Graph Expansion**: The data models already include `edges` and `symbols`. In the future, building an AST traversal module that detects references and function call traces will permit a graph agent to traverse from one symbol identifier to another.
- **Expert-Answer Agents**: The retrieval layer currently outputs standard ContextPacks. Wrapping a language model (e.g., GPT-4 or Gemini 1.5 Pro) tightly around the `RetrieveResponse` to provide a summarized markdown output will readily complete the Generation part of RAG.
