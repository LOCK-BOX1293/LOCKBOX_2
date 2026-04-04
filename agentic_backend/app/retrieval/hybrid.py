from __future__ import annotations

import math
import re
from collections import defaultdict

from app.embedder.providers import EmbeddingClient, build_provider
from app.settings import AppSettings
from app.storage.mongo_store import MongoStore


class HybridRetriever:
    def __init__(self, settings: AppSettings, store: MongoStore) -> None:
        self.settings = settings
        self.store = store
        self.embedder = EmbeddingClient(
            build_provider(settings.embedding_provider, settings.embedding_model, settings.embedding_dim),
            batch_size=settings.embedding_batch_size,
        )

    def query(
        self,
        repo_id: str,
        branch: str,
        q: str,
        top_k: int,
        lang: str | None = None,
        path_prefix: str | None = None,
        include_graph: bool = True,
    ) -> dict:
        vector_hits = self._vector_search(repo_id, branch, q, top_k, lang, path_prefix)
        text_hits = self._text_search(repo_id, branch, q, top_k, lang, path_prefix)
        fused = self._fuse(vector_hits, text_hits, top_k)

        if include_graph:
            fused = self._expand_graph(repo_id, branch, fused, top_k)

        reranked = self._rerank(q, fused) if self.settings.rerank_enabled else fused
        ranked = reranked[:top_k]

        confidence = 0.0
        if ranked:
            confidence = max(0.05, min(0.99, sum(r["score"] for r in ranked) / len(ranked)))

        return {
            "chunks": [
                {
                    "chunk_id": r["chunk_id"],
                    "file_path": r["file_path"],
                    "start_line": r["start_line"],
                    "end_line": r["end_line"],
                    "content": r["content"],
                    "score": round(float(r["score"]), 6),
                    "reason": r["reason"],
                }
                for r in ranked
            ],
            "confidence": confidence,
        }

    def _vector_search(self, repo_id: str, branch: str, q: str, top_k: int, lang: str | None, path_prefix: str | None) -> list[dict]:
        q_vec = self.embedder.embed_with_retry([q])[0]
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "embeddings_vector_v1",
                    "path": "vector",
                    "queryVector": q_vec,
                    "numCandidates": max(30, top_k * 6),
                    "limit": top_k,
                    "filter": {"repo_id": repo_id, "branch": branch},
                }
            },
            {
                "$lookup": {
                    "from": "chunks",
                    "let": {"cid": "$chunk_id", "repo": "$repo_id", "br": "$branch"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$chunk_id", "$$cid"]},
                                        {"$eq": ["$repo_id", "$$repo"]},
                                        {"$eq": ["$branch", "$$br"]},
                                    ]
                                }
                            }
                        }
                    ],
                    "as": "chunk",
                }
            },
            {"$unwind": "$chunk"},
            {
                "$project": {
                    "chunk_id": "$chunk.chunk_id",
                    "file_path": "$chunk.file_path",
                    "start_line": "$chunk.start_line",
                    "end_line": "$chunk.end_line",
                    "content": "$chunk.content",
                    "language": "$chunk.language",
                    "score": {"$meta": "vectorSearchScore"},
                    "symbol_refs": "$chunk.symbol_refs",
                }
            },
        ]
        try:
            docs = list(self.store.embeddings.aggregate(pipeline))
        except Exception:
            docs = self._vector_fallback(repo_id, branch, q_vec)

        docs = self._apply_filters(docs, lang, path_prefix)
        for d in docs:
            d["reason"] = "vector-match"
        return docs

    def _vector_fallback(self, repo_id: str, branch: str, q_vec: list[float]) -> list[dict]:
        embs = list(self.store.embeddings.find({"repo_id": repo_id, "branch": branch}, {"_id": 0}))
        if not embs:
            return []
        chunk_map = {
            c["chunk_id"]: c
            for c in self.store.chunks.find({"repo_id": repo_id, "branch": branch}, {"_id": 0})
        }

        docs: list[dict] = []
        for e in embs:
            vec = e.get("vector") or []
            if len(vec) != len(q_vec):
                continue
            dot = sum(a * b for a, b in zip(vec, q_vec))
            chunk = chunk_map.get(e["chunk_id"])
            if not chunk:
                continue
            docs.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "file_path": chunk["file_path"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "content": chunk["content"],
                    "language": chunk.get("language"),
                    "score": dot,
                    "symbol_refs": chunk.get("symbol_refs", []),
                }
            )
        docs.sort(key=lambda x: x["score"], reverse=True)
        return docs

    def _text_search(self, repo_id: str, branch: str, q: str, top_k: int, lang: str | None, path_prefix: str | None) -> list[dict]:
        def _fallback_text() -> list[dict]:
            rex = re.compile(re.escape(q), re.IGNORECASE)
            fallback_docs: list[dict] = []
            for c in self.store.chunks.find({"repo_id": repo_id, "branch": branch}, {"_id": 0}):
                m = rex.search(c.get("content", "")) or rex.search(c.get("file_path", ""))
                if not m:
                    continue
                score = 1.0 / (1.0 + max(0, m.start()))
                fallback_docs.append({**c, "score": score})
            fallback_docs.sort(key=lambda x: x["score"], reverse=True)
            return fallback_docs[:top_k]

        pipeline = [
            {
                "$search": {
                    "index": "chunks_text_v1",
                    "compound": {
                        "must": [{"text": {"query": q, "path": ["content", "file_path"]}}],
                        "filter": [
                            {"equals": {"path": "repo_id", "value": repo_id}},
                            {"equals": {"path": "branch", "value": branch}},
                        ],
                    },
                }
            },
            {"$limit": top_k},
            {
                "$project": {
                    "chunk_id": 1,
                    "file_path": 1,
                    "start_line": 1,
                    "end_line": 1,
                    "content": 1,
                    "language": 1,
                    "symbol_refs": 1,
                    "score": {"$meta": "searchScore"},
                }
            },
        ]
        try:
            docs = list(self.store.chunks.aggregate(pipeline))
            if not docs:
                docs = _fallback_text()
        except Exception:
            docs = _fallback_text()

        docs = self._apply_filters(docs, lang, path_prefix)
        for d in docs:
            d["reason"] = "text-match"
        return docs

    def _apply_filters(self, docs: list[dict], lang: str | None, path_prefix: str | None) -> list[dict]:
        out = docs
        if lang:
            out = [d for d in out if d.get("language") == lang]
        if path_prefix:
            out = [d for d in out if d.get("file_path", "").startswith(path_prefix)]
        return out

    def _fuse(self, vector_hits: list[dict], text_hits: list[dict], top_k: int) -> list[dict]:
        bucket: dict[str, dict] = {}
        rank_map: defaultdict[str, float] = defaultdict(float)

        for i, hit in enumerate(vector_hits):
            cid = hit["chunk_id"]
            bucket[cid] = hit
            rank_map[cid] += 0.7 * (1.0 / (50 + i + 1))

        for i, hit in enumerate(text_hits):
            cid = hit["chunk_id"]
            bucket[cid] = {**bucket.get(cid, {}), **hit}
            rank_map[cid] += 0.3 * (1.0 / (50 + i + 1))

        fused = []
        for cid, doc in bucket.items():
            doc["score"] = rank_map[cid]
            if doc.get("reason") != "vector-match":
                doc["reason"] = "hybrid-fusion"
            fused.append(doc)

        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused[: max(top_k * 2, top_k)]

    def _expand_graph(self, repo_id: str, branch: str, docs: list[dict], top_k: int) -> list[dict]:
        symbol_ids = set()
        for d in docs:
            symbol_ids.update(d.get("symbol_refs", []))
        if not symbol_ids:
            return docs

        related_symbols = set(symbol_ids)
        for edge in self.store.edges.find(
            {
                "repo_id": repo_id,
                "branch": branch,
                "$or": [{"from_symbol_id": {"$in": list(symbol_ids)}}, {"to_symbol_id": {"$in": list(symbol_ids)}}],
            },
            {"_id": 0, "from_symbol_id": 1, "to_symbol_id": 1},
        ):
            related_symbols.add(edge["from_symbol_id"])
            related_symbols.add(edge["to_symbol_id"])

        extra = list(
            self.store.chunks.find(
                {"repo_id": repo_id, "branch": branch, "symbol_refs": {"$in": list(related_symbols)}},
                {"_id": 0},
            ).limit(top_k)
        )
        for e in extra:
            e["score"] = 0.05
            e["reason"] = "graph-expansion"

        merged = {d["chunk_id"]: d for d in docs}
        for e in extra:
            merged.setdefault(e["chunk_id"], e)
        out = list(merged.values())
        out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return out

    def _rerank(self, q: str, docs: list[dict]) -> list[dict]:
        q_terms = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", q.lower()))
        if not q_terms:
            return docs
        for d in docs:
            tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", d.get("content", "").lower()))
            overlap = len(q_terms.intersection(tokens))
            d["score"] = float(d.get("score", 0.0)) + 0.01 * math.log1p(overlap)
            if overlap:
                d["reason"] = f"{d.get('reason', 'match')}+rerank"
        docs.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return docs
