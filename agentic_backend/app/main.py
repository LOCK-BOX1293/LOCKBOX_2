from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from app.api_models import IndexRequest, QueryResponse, RetrieveRequest
from app.indexer.pipeline import IndexingPipeline
from app.retrieval.hybrid import HybridRetriever
from app.settings import get_settings
from app.storage.mongo_store import MongoStore


settings = get_settings()
store = MongoStore(uri=settings.mongodb_uri, db_name=settings.mongodb_db)
indexer = IndexingPipeline(settings=settings, store=store)
retriever = HybridRetriever(settings=settings, store=store)

app = FastAPI(title="RoleReady Index + Retrieval API", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mongodb_db": settings.mongodb_db,
        "embedding_provider": settings.embedding_provider,
        "embedding_dim": settings.embedding_dim,
        "rerank_enabled": settings.rerank_enabled,
    }


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
        return indexer.index_incremental(payload.repo_path, payload.repo_id, payload.branch)
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


@app.get("/jobs/{repo_id}")
def jobs_status(repo_id: str) -> dict:
    jobs = list(store.index_jobs.find({"repo_id": repo_id}, {"_id": 0}).sort("started_at", -1).limit(20))
    return {"repo_id": repo_id, "jobs": jobs}


@app.get("/graph/node/{node_id}")
def graph_node(repo_id: str, branch: str, node_type: str, node_id: str) -> dict:
    if node_type == "file":
        doc = store.files.find_one({"repo_id": repo_id, "branch": branch, "file_path": node_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="file node not found")
        return {
            "node": {"id": node_id, "type": "file"},
            "code": doc.get("content", ""),
            "metadata": {
                "language": doc.get("language"),
                "size_bytes": doc.get("size_bytes"),
                "commit_sha": doc.get("commit_sha"),
            },
        }

    symbol = store.symbols.find_one({"repo_id": repo_id, "branch": branch, "symbol_id": node_id}, {"_id": 0})
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
        "metadata": {
            "file_path": symbol["file_path"],
            "start_line": symbol["start_line"],
            "end_line": symbol["end_line"],
            "symbol_type": symbol["symbol_type"],
        },
    }


@app.get("/graph/edge-context")
def edge_context(repo_id: str, branch: str, from_symbol_id: str, to_symbol_id: str) -> dict:
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
        raise HTTPException(status_code=404, detail="edge not found")

    def _symbol_payload(symbol_id: str) -> dict:
        s = store.symbols.find_one({"repo_id": repo_id, "branch": branch, "symbol_id": symbol_id}, {"_id": 0})
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

    return {
        "edge": edge,
        "from": _symbol_payload(from_symbol_id),
        "to": _symbol_payload(to_symbol_id),
    }
