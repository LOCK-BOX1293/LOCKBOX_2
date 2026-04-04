from __future__ import annotations

import hashlib

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api_models import IndexRequest, QueryResponse, RetrieveRequest
from app.indexer.pipeline import IndexingPipeline
from app.mindflow import MindflowOrchestrator, MindflowTurnRequest, MindflowTurnResponse
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
mindflow = MindflowOrchestrator(
    llm=orchestrator.llm,
    drift_threshold=orchestrator.settings.mindflow_drift_threshold,
)

app = FastAPI(title="RoleReady Index + Retrieval API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
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
            include_tests=payload.include_tests,
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


@app.post("/mindflow/turn", response_model=MindflowTurnResponse)
def mindflow_turn(payload: MindflowTurnRequest) -> MindflowTurnResponse:
    try:
        return mindflow.run_turn(payload)
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
    include_tests: bool = False,
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
            include_tests=include_tests,
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
    # Prevent visual overload: keep an important, bounded subset for "full" view.
    MAX_NODES = 140
    MAX_EDGES = 220

    file_docs = list(
        store.files.find(
            {"repo_id": repo_id, "branch": branch},
            {"_id": 0, "file_path": 1},
        ).limit(3000)
    )
    file_paths = [f.get("file_path") for f in file_docs if f.get("file_path")]

    all_symbols = list(
        store.symbols.find(
            {"repo_id": repo_id, "branch": branch},
            {
                "_id": 0,
                "symbol_id": 1,
                "name": 1,
                "symbol_type": 1,
                "file_path": 1,
                "start_line": 1,
            },
        ).limit(15000)
    )

    def _priority(sym: dict) -> int:
        t = (sym.get("symbol_type") or "").lower()
        if t == "class":
            return 4
        if t == "module":
            return 3
        if t == "function":
            return 2
        # imports and unknowns are least important for first render
        return 1

    # Filter out import nodes for initial overview (major source of noise)
    important = [s for s in all_symbols if (s.get("symbol_type") or "") != "import"]

    # Keep class/module symbols only for high-level overview.
    chosen: list[dict] = []
    important_sorted = sorted(
        important,
        key=lambda s: (
            -_priority(s),
            str(s.get("file_path") or ""),
            int(s.get("start_line") or 0),
            str(s.get("name") or ""),
        ),
    )

    for s in important_sorted:
        t = (s.get("symbol_type") or "").lower()
        if t not in {"class", "module"}:
            continue
        chosen.append(s)

    max_symbol_nodes = max(40, MAX_NODES - len(file_paths))
    chosen = chosen[:max_symbol_nodes]
    kept_symbol_ids = {s.get("symbol_id") for s in chosen if s.get("symbol_id")}

    nodes = [{"id": f, "label": f, "type": "file"} for f in file_paths]
    for s in chosen:
        sid = s.get("symbol_id")
        if not sid:
            continue
        nodes.append(
            {
                "id": sid,
                "label": s.get("name"),
                "type": "symbol",
                "symbol_type": s.get("symbol_type"),
                "file_path": s.get("file_path"),
                "importance": _priority(s),
            }
        )

    edges: list[dict] = []
    for s in chosen:
        fp = s.get("file_path")
        sid = s.get("symbol_id")
        if fp and sid:
            edges.append(
                {"source": fp, "target": sid, "type": "contains", "weight": 1.0}
            )

    edge_docs = list(
        store.edges.find(
            {
                "repo_id": repo_id,
                "branch": branch,
                "from_symbol_id": {"$in": list(kept_symbol_ids)},
                "to_symbol_id": {"$in": list(kept_symbol_ids)},
            },
            {
                "_id": 0,
                "from_symbol_id": 1,
                "to_symbol_id": 1,
                "edge_type": 1,
                "weight": 1,
            },
        ).limit(8000)
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
        key = (e.get("source"), e.get("target"), e.get("type"))
        uniq_edges[key] = e
    edge_list = list(uniq_edges.values())[:MAX_EDGES]

    # Final node trim safeguard (keeps files + top symbols)
    if len(nodes) > MAX_NODES:
        file_nodes = [n for n in nodes if n.get("type") == "file"]
        symbol_nodes = [n for n in nodes if n.get("type") == "symbol"]
        symbol_nodes = sorted(
            symbol_nodes,
            key=lambda n: (-int(n.get("importance") or 0), str(n.get("label") or "")),
        )
        nodes = file_nodes + symbol_nodes[: max(0, MAX_NODES - len(file_nodes))]
        kept_ids = {n.get("id") for n in nodes}
        edge_list = [
            e
            for e in edge_list
            if (e.get("source") in kept_ids and e.get("target") in kept_ids)
        ]

    return {
        "mode": "full",
        "repo_id": repo_id,
        "branch": branch,
        "nodes": nodes,
        "edges": edge_list,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edge_list),
            "raw_symbol_count": len(all_symbols),
            "filtered_symbol_count": len(chosen),
            "truncated": len(all_symbols) > len(chosen),
            "strategy": "files + class/module only (imports/functions hidden in overview)",
        },
    }


def _build_focused_graph(
    repo_id: str,
    branch: str,
    q: str,
    top_k: int,
    lang: str | None,
    path_prefix: str | None,
    include_tests: bool,
) -> dict:
    MAX_FOCUSED_NODES = 180
    MAX_FOCUSED_EDGES = 260

    result = retriever.query(
        repo_id=repo_id,
        branch=branch,
        q=q,
        top_k=top_k,
        lang=lang,
        path_prefix=path_prefix,
        include_tests=include_tests,
        include_graph=True,
    )
    chunks = result.get("chunks", [])

    if not path_prefix:
        path_prefix = "src/"

    def _is_low_signal_symbol(sym: dict) -> bool:
        name = str(sym.get("name") or "").strip().lower()
        symbol_type = str(sym.get("symbol_type") or "").strip().lower()
        file_path = str(sym.get("file_path") or "").strip().lower()

        if symbol_type == "import":
            return True
        if name in {"__init__", "main", "index"} and file_path.endswith(
            ("/__init__.py", "/index.ts", "/index.tsx", "/index.js")
        ):
            return True
        return False

    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()
    symbol_ids: set[str] = set()

    # Synthetic query node (AI-selected anchor) for focused graph readability.
    qid = f"query::{hashlib.sha1(q.encode('utf-8')).hexdigest()[:12]}"
    nodes.append(
        {
            "id": qid,
            "label": q[:64] + ("..." if len(q) > 64 else ""),
            "type": "query",
            "relevance_score": float(result.get("confidence", 0.0)),
            "reason": "query-anchor",
        }
    )
    node_ids.add(qid)

    for c in chunks:
        file_path = c.get("file_path")
        if path_prefix and file_path and not str(file_path).startswith(path_prefix):
            continue
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
        if file_path:
            edges.append({"source": qid, "target": file_path, "type": "focuses_on"})

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
                if _is_low_signal_symbol(s):
                    continue
                if path_prefix and not str(s.get("file_path") or "").startswith(
                    path_prefix
                ):
                    continue
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

                # Synthetic function-focus node for highly relevant chunks
                if str(s.get("symbol_type") or "").lower() in {"function", "class"}:
                    focus_id = f"focus::{sid}"
                    if focus_id not in node_ids:
                        node_ids.add(focus_id)
                        nodes.append(
                            {
                                "id": focus_id,
                                "label": f"{s.get('name')}()"
                                if str(s.get("symbol_type") or "").lower() == "function"
                                else str(s.get("name") or "symbol"),
                                "type": "focus",
                                "relevance_score": float(c.get("score", 0.0)) + 0.01,
                                "reason": "ai-focus-node",
                                "file_path": s.get("file_path"),
                            }
                        )
                    edges.append({"source": qid, "target": focus_id, "type": "selects"})
                    edges.append({"source": focus_id, "target": sid, "type": "maps_to"})

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

    # Focused graph caps: preserve highest relevance nodes first.
    if len(nodes) > MAX_FOCUSED_NODES:
        file_nodes = [n for n in nodes if n.get("type") == "file"]
        sym_nodes = [n for n in nodes if n.get("type") == "symbol"]
        sym_nodes.sort(
            key=lambda n: (
                -float(n.get("relevance_score", 0.0)),
                str(n.get("label") or ""),
            )
        )
        nodes = file_nodes + sym_nodes[: max(0, MAX_FOCUSED_NODES - len(file_nodes))]

    edge_list = list(uniq.values())
    if len(edge_list) > MAX_FOCUSED_EDGES:
        edge_list = edge_list[:MAX_FOCUSED_EDGES]

    kept_ids = {n.get("id") for n in nodes}
    edge_list = [
        e
        for e in edge_list
        if e.get("source") in kept_ids and e.get("target") in kept_ids
    ]

    return {
        "mode": "focused",
        "repo_id": repo_id,
        "branch": branch,
        "query": q,
        "nodes": nodes,
        "edges": edge_list,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edge_list),
            "retrieval_confidence": float(result.get("confidence", 0.0)),
        },
    }
