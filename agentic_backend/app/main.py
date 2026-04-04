from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api_models import IndexRequest, QueryResponse, RetrieveRequest
from app.indexer.pipeline import IndexingPipeline
from app.models import AskRequest, AskResponse
from app.orchestrator import Orchestrator
from app.retrieval.hybrid import HybridRetriever
from app.settings import get_settings
from app.storage.mongo_store import MongoStore


settings = get_settings()
store = MongoStore(uri=settings.mongodb_uri, db_name=settings.mongodb_db)
indexer = IndexingPipeline(settings=settings, store=store)
retriever = HybridRetriever(settings=settings, store=store)
orchestrator = Orchestrator()

app = FastAPI(title="RoleReady Index + Retrieval API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mongodb_db": settings.mongodb_db,
        "embedding_provider": settings.embedding_provider,
        "embedding_dim": settings.embedding_dim,
        "rerank_enabled": settings.rerank_enabled,
    }


@app.get("/repos")
def list_repos() -> dict:
    repos = list(store.repos.find({}, {"_id": 0}).sort("updated_at", -1).limit(200))
    return {"repos": repos}


@app.post("/index/full")
def index_full(payload: IndexRequest) -> dict:
    try:
        indexer.ensure_indexes(payload.repo_id)
        return indexer.index_full(payload.repo_path, payload.repo_id, payload.branch)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/index/incremental")
def index_incremental(payload: IndexRequest) -> dict:
    try:
        indexer.ensure_indexes(payload.repo_id)
        return indexer.index_incremental(
            payload.repo_path, payload.repo_id, payload.branch
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/index/ensure-indexes")
def ensure_indexes(repo_id: str = Query(...)) -> dict:
    try:
        indexer.ensure_indexes(repo_id)
        return {"ok": True, "repo_id": repo_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/retrieve/query", response_model=QueryResponse)
def retrieve_query(payload: RetrieveRequest) -> QueryResponse:
    try:
        result = retriever.query(
            repo_id=payload.repo_id,
            branch=payload.branch,
            q=payload.q,
            top_k=payload.top_k,
            lang=payload.lang,
            path_prefix=payload.path_prefix,
            include_graph=True,
        )
        return QueryResponse.model_validate(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        return orchestrator.ask(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/graph/overview")
def graph_overview(
    repo_id: str,
    branch: str = "main",
    mode: str = "full",
    q: str | None = None,
    top_k: int = 8,
    lang: str | None = None,
    path_prefix: str | None = None,
) -> dict:
    """
    Return graph payload for UI.

    - mode=full: full graph for repo/branch
    - mode=focused: query-focused subgraph (important nodes only)
    """
    if mode not in {"full", "focused"}:
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'focused'")

    if mode == "focused":
        if not q:
            raise HTTPException(
                status_code=400,
                detail="q is required for focused mode",
            )
        return _build_focused_graph(
            repo_id=repo_id,
            branch=branch,
            q=q,
            top_k=top_k,
            lang=lang,
            path_prefix=path_prefix,
        )

    return _build_full_graph(repo_id=repo_id, branch=branch)


@app.get("/jobs/{repo_id}")
def jobs_status(repo_id: str) -> dict:
    jobs = list(
        store.index_jobs.find({"repo_id": repo_id}, {"_id": 0})
        .sort("started_at", -1)
        .limit(20)
    )
    return {"repo_id": repo_id, "jobs": jobs}


@app.get("/graph/node/{node_id:path}")
def graph_node(repo_id: str, branch: str, node_type: str, node_id: str) -> dict:
    if node_type == "file":
        doc = store.files.find_one(
            {"repo_id": repo_id, "branch": branch, "file_path": node_id}, {"_id": 0}
        )
        if not doc:
            raise HTTPException(status_code=404, detail="file node not found")
        code = doc.get("content", "")
        if not code:
            chunk_docs = list(
                store.chunks.find(
                    {"repo_id": repo_id, "branch": branch, "file_path": node_id},
                    {"_id": 0, "start_line": 1, "content": 1},
                ).sort("start_line", 1)
            )
            code = "\n\n".join(
                c.get("content", "") for c in chunk_docs if c.get("content")
            )
        symbol_docs = list(
            store.symbols.find(
                {"repo_id": repo_id, "branch": branch, "file_path": node_id},
                {
                    "_id": 0,
                    "symbol_id": 1,
                    "name": 1,
                    "symbol_type": 1,
                    "signature": 1,
                    "start_line": 1,
                    "end_line": 1,
                    "metadata": 1,
                },
            ).sort("start_line", 1)
        )
        functions = [
            {
                "id": s.get("symbol_id"),
                "name": s.get("name"),
                "symbol_type": s.get("symbol_type"),
                "signature": s.get("signature"),
                "start_line": s.get("start_line"),
                "end_line": s.get("end_line"),
                "tags": (s.get("metadata") or {}).get("tags", []),
            }
            for s in symbol_docs
        ]
        return {
            "node": {"id": node_id, "type": "file"},
            "code": code,
            "functions": functions,
            "metadata": {
                "language": doc.get("language"),
                "size_bytes": doc.get("size_bytes"),
                "commit_sha": doc.get("commit_sha"),
                "symbol_count": len(functions),
            },
        }

    symbol = store.symbols.find_one(
        {"repo_id": repo_id, "branch": branch, "symbol_id": node_id}, {"_id": 0}
    )
    if not symbol:
        raise HTTPException(status_code=404, detail="symbol node not found")
    chunk = store.chunks.find_one(
        {
            "repo_id": repo_id,
            "branch": branch,
            "file_path": symbol["file_path"],
            "start_line": {"$lte": symbol["start_line"]},
            "end_line": {"$gte": symbol["end_line"]},
        },
        {"_id": 0},
    )
    return {
        "node": {"id": node_id, "type": "symbol", "name": symbol["name"]},
        "code": (chunk or {}).get("content", ""),
        "functions": [
            {
                "id": symbol.get("symbol_id"),
                "name": symbol.get("name"),
                "symbol_type": symbol.get("symbol_type"),
                "signature": symbol.get("signature"),
                "start_line": symbol.get("start_line"),
                "end_line": symbol.get("end_line"),
                "tags": (symbol.get("metadata") or {}).get("tags", []),
            }
        ],
        "metadata": {
            "file_path": symbol["file_path"],
            "start_line": symbol["start_line"],
            "end_line": symbol["end_line"],
            "symbol_type": symbol["symbol_type"],
        },
    }


@app.get("/graph/edge-context")
def edge_context(
    repo_id: str, branch: str, from_symbol_id: str, to_symbol_id: str
) -> dict:
    edge = store.edges.find_one(
        {
            "repo_id": repo_id,
            "branch": branch,
            "from_symbol_id": from_symbol_id,
            "to_symbol_id": to_symbol_id,
        },
        {"_id": 0},
    )
    if not edge:
        # Support synthetic 'contains' edges returned by graph overview (file -> symbol)
        from_is_file = bool(
            store.files.find_one(
                {"repo_id": repo_id, "branch": branch, "file_path": from_symbol_id},
                {"_id": 1},
            )
        )
        to_is_file = bool(
            store.files.find_one(
                {"repo_id": repo_id, "branch": branch, "file_path": to_symbol_id},
                {"_id": 1},
            )
        )
        if from_is_file and not to_is_file:
            sym = store.symbols.find_one(
                {
                    "repo_id": repo_id,
                    "branch": branch,
                    "symbol_id": to_symbol_id,
                    "file_path": from_symbol_id,
                },
                {"_id": 0, "symbol_id": 1, "file_path": 1},
            )
            if sym:
                edge = {
                    "repo_id": repo_id,
                    "branch": branch,
                    "from_symbol_id": from_symbol_id,
                    "to_symbol_id": to_symbol_id,
                    "edge_type": "contains",
                    "weight": 1.0,
                }
        if not edge:
            raise HTTPException(status_code=404, detail="edge not found")

    def _file_payload(file_path: str) -> dict:
        f = store.files.find_one(
            {"repo_id": repo_id, "branch": branch, "file_path": file_path},
            {"_id": 0},
        )
        if not f:
            return {"file_path": file_path, "code": "", "metadata": {}}
        chunks = list(
            store.chunks.find(
                {"repo_id": repo_id, "branch": branch, "file_path": file_path},
                {"_id": 0, "start_line": 1, "content": 1},
            ).sort("start_line", 1)
        )
        code = "\n\n".join(c.get("content", "") for c in chunks if c.get("content"))
        return {
            "file_path": file_path,
            "code": code,
            "metadata": {
                "language": f.get("language"),
                "size_bytes": f.get("size_bytes"),
                "commit_sha": f.get("commit_sha"),
            },
        }

    def _symbol_payload(symbol_id: str) -> dict:
        s = store.symbols.find_one(
            {"repo_id": repo_id, "branch": branch, "symbol_id": symbol_id}, {"_id": 0}
        )
        if not s:
            return {"symbol_id": symbol_id, "code": "", "metadata": {}}
        c = store.chunks.find_one(
            {
                "repo_id": repo_id,
                "branch": branch,
                "file_path": s["file_path"],
                "start_line": {"$lte": s["start_line"]},
                "end_line": {"$gte": s["end_line"]},
            },
            {"_id": 0},
        )
        return {
            "symbol_id": symbol_id,
            "name": s["name"],
            "file_path": s["file_path"],
            "start_line": s["start_line"],
            "end_line": s["end_line"],
            "code": (c or {}).get("content", ""),
        }

    # Support both symbol-symbol and file-symbol contains edges.
    from_is_file = bool(
        store.files.find_one(
            {"repo_id": repo_id, "branch": branch, "file_path": from_symbol_id},
            {"_id": 1},
        )
    )
    to_is_file = bool(
        store.files.find_one(
            {"repo_id": repo_id, "branch": branch, "file_path": to_symbol_id},
            {"_id": 1},
        )
    )

    return {
        "edge": edge,
        "from": _file_payload(from_symbol_id)
        if from_is_file
        else _symbol_payload(from_symbol_id),
        "to": _file_payload(to_symbol_id)
        if to_is_file
        else _symbol_payload(to_symbol_id),
    }


def _build_full_graph(repo_id: str, branch: str) -> dict:
    symbol_docs = list(
        store.symbols.find(
            {"repo_id": repo_id, "branch": branch},
            {
                "_id": 0,
                "symbol_id": 1,
                "name": 1,
                "symbol_type": 1,
                "file_path": 1,
            },
        ).limit(5000)
    )
    edge_docs = list(
        store.edges.find(
            {"repo_id": repo_id, "branch": branch},
            {
                "_id": 0,
                "from_symbol_id": 1,
                "to_symbol_id": 1,
                "edge_type": 1,
                "weight": 1,
            },
        ).limit(10000)
    )

    nodes = []
    edges = []
    file_seen: set[str] = set()
    for s in symbol_docs:
        f = s.get("file_path") or ""
        if f and f not in file_seen:
            file_seen.add(f)
            nodes.append({"id": f, "label": f, "type": "file"})
        sid = s.get("symbol_id")
        nodes.append(
            {
                "id": sid,
                "label": s.get("name"),
                "type": "symbol",
                "symbol_type": s.get("symbol_type"),
                "file_path": f,
            }
        )
        if f and sid:
            edges.append(
                {"source": f, "target": sid, "type": "contains", "weight": 1.0}
            )

    for e in edge_docs:
        edges.append(
            {
                "source": e.get("from_symbol_id"),
                "target": e.get("to_symbol_id"),
                "type": e.get("edge_type", "related"),
                "weight": float(e.get("weight", 1.0)),
            }
        )

    uniq_edges = {}
    for e in edges:
        uniq_edges[(e.get("source"), e.get("target"), e.get("type"))] = e

    return {
        "mode": "full",
        "repo_id": repo_id,
        "branch": branch,
        "nodes": nodes,
        "edges": list(uniq_edges.values()),
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(uniq_edges),
        },
    }


def _build_focused_graph(
    repo_id: str,
    branch: str,
    q: str,
    top_k: int,
    lang: str | None,
    path_prefix: str | None,
) -> dict:
    result = retriever.query(
        repo_id=repo_id,
        branch=branch,
        q=q,
        top_k=top_k,
        lang=lang,
        path_prefix=path_prefix,
        include_graph=True,
    )
    chunks = result.get("chunks", [])

    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()
    symbol_ids: set[str] = set()

    for c in chunks:
        file_path = c.get("file_path")
        if file_path and file_path not in node_ids:
            node_ids.add(file_path)
            nodes.append(
                {
                    "id": file_path,
                    "label": file_path,
                    "type": "file",
                    "relevance_score": float(c.get("score", 0.0)),
                    "reason": c.get("reason", "retrieval"),
                }
            )

        # Resolve nearby symbols in the same range
        if file_path:
            syms = list(
                store.symbols.find(
                    {
                        "repo_id": repo_id,
                        "branch": branch,
                        "file_path": file_path,
                        "start_line": {"$lte": int(c.get("end_line", 1))},
                        "end_line": {"$gte": int(c.get("start_line", 1))},
                    },
                    {
                        "_id": 0,
                        "symbol_id": 1,
                        "name": 1,
                        "symbol_type": 1,
                        "file_path": 1,
                    },
                ).limit(20)
            )
            for s in syms:
                sid = s.get("symbol_id")
                if not sid:
                    continue
                symbol_ids.add(sid)
                if sid not in node_ids:
                    node_ids.add(sid)
                    nodes.append(
                        {
                            "id": sid,
                            "label": s.get("name"),
                            "type": "symbol",
                            "symbol_type": s.get("symbol_type"),
                            "file_path": s.get("file_path"),
                            "relevance_score": float(c.get("score", 0.0)),
                            "reason": c.get("reason", "retrieval"),
                        }
                    )
                edges.append({"source": file_path, "target": sid, "type": "contains"})

    if symbol_ids:
        for e in store.edges.find(
            {
                "repo_id": repo_id,
                "branch": branch,
                "$or": [
                    {"from_symbol_id": {"$in": list(symbol_ids)}},
                    {"to_symbol_id": {"$in": list(symbol_ids)}},
                ],
            },
            {
                "_id": 0,
                "from_symbol_id": 1,
                "to_symbol_id": 1,
                "edge_type": 1,
                "weight": 1,
            },
        ).limit(500):
            s = e.get("from_symbol_id")
            t = e.get("to_symbol_id")
            if s in node_ids and t in node_ids:
                edges.append(
                    {
                        "source": s,
                        "target": t,
                        "type": e.get("edge_type", "related"),
                        "weight": float(e.get("weight", 1.0)),
                    }
                )

    # De-dup edges
    uniq = {}
    for e in edges:
        key = (e.get("source"), e.get("target"), e.get("type"))
        uniq[key] = e

    return {
        "mode": "focused",
        "repo_id": repo_id,
        "branch": branch,
        "query": q,
        "nodes": nodes,
        "edges": list(uniq.values()),
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(uniq),
            "retrieval_confidence": float(result.get("confidence", 0.0)),
        },
    }
