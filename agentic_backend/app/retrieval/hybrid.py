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
            build_provider(
                settings.embedding_provider,
                settings.embedding_model,
                settings.embedding_dim,
            ),
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
        include_tests: bool = False,
    ) -> dict:
        vector_hits = self._vector_search(
            repo_id, branch, q, top_k, lang, path_prefix, include_tests
        )
        text_hits = self._text_search(
            repo_id, branch, q, top_k, lang, path_prefix, include_tests
        )
        fused = self._fuse(vector_hits, text_hits, top_k)

        # Apply deterministic query priors even when reranking is disabled.
        # This improves large-repo precision for architecture/code-flow queries.
        fused = self._apply_query_priors(q, fused)

        if include_graph:
            fused = self._expand_graph(repo_id, branch, fused, top_k)

        reranked = self._rerank(q, fused) if self.settings.rerank_enabled else fused
        ranked = reranked[:top_k]

        confidence = 0.0
        if ranked:
            confidence = max(
                0.05, min(0.99, sum(r["score"] for r in ranked) / len(ranked))
            )

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

    def _apply_query_priors(self, q: str, docs: list[dict]) -> list[dict]:
        q_lower = q.lower()
        q_terms = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", q_lower))

        technical_arch_query = any(
            t in q_terms
            for t in {
                "how",
                "where",
                "call",
                "calls",
                "called",
                "flow",
                "orchestrator",
                "agent",
                "search",
                "retrieve",
                "pipeline",
                "service",
                "function",
                "method",
                "class",
            }
        )
        mentions_tests = any(t in q_terms for t in {"test", "tests", "pytest"})
        mentions_docs = any(
            t in q_terms
            for t in {
                "readme",
                "docs",
                "documentation",
                "deploy",
                "docker",
                "yaml",
                "yml",
                "workflow",
                "ci",
                "cd",
            }
        )

        # Give strong boosts for literal query token overlap in path/content,
        # helps large repos surface exact call-chain chunks.
        boost_terms = [
            t
            for t in q_terms
            if len(t) >= 4
            and t
            not in {
                "how",
                "where",
                "calls",
                "called",
                "query",
                "search",
                "service",
                "method",
                "class",
                "function",
                "file",
                "code",
            }
        ]

        for d in docs:
            path = (d.get("file_path") or "").lower()
            content = (d.get("content") or "").lower()
            bonus = 0.0

            # Prefer core code paths for technical architecture questions.
            if technical_arch_query:
                if path.startswith("src/") or "/src/" in path:
                    bonus += 0.04
                if any(
                    path.startswith(p)
                    for p in ["docs/", "deployment/", ".github/", "config/"]
                ):
                    if not mentions_docs:
                        bonus -= 0.08
                if (
                    path.endswith((".md", ".rst", ".yaml", ".yml", ".json"))
                    and not mentions_docs
                ):
                    bonus -= 0.04

            if self._is_test_path(path) and not mentions_tests:
                bonus -= 0.07

            # token overlap boosts
            overlap_hits = 0
            for t in boost_terms:
                if t in path:
                    overlap_hits += 1
                    bonus += 0.03
                if t in content:
                    overlap_hits += 1
                    bonus += 0.015

            # Prefer operational chunks over metadata/manifest for technical flow queries.
            if technical_arch_query:
                if "agent_manifest" in content or "manifest" in path:
                    bonus -= 0.02
                if "answer_query" in content:
                    bonus += 0.05
                if "janapada_client.call" in content or 'method="search"' in content:
                    bonus += 0.07

            d["score"] = float(d.get("score", 0.0)) + bonus
            if bonus != 0:
                d["reason"] = f"{d.get('reason', 'match')}+prior"

        docs.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return docs

    def _vector_search(
        self,
        repo_id: str,
        branch: str,
        q: str,
        top_k: int,
        lang: str | None,
        path_prefix: str | None,
        include_tests: bool,
    ) -> list[dict]:
        q_vec = self.embedder.embed_with_retry([q])[0]
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "embeddings_vector_v1",
                    "path": "vector",
                    "queryVector": q_vec,
                    "numCandidates": max(30, top_k * 6),
                    "limit": top_k,
                    "filter": {
                        "$and": [
                            {"repo_id": repo_id},
                            {"branch": branch},
                            {"embedding_dim": len(q_vec)},
                        ]
                    },
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

        docs = self._apply_filters(docs, lang, path_prefix, include_tests)
        for d in docs:
            d["reason"] = "vector-match"
        return docs

    def _vector_fallback(
        self, repo_id: str, branch: str, q_vec: list[float]
    ) -> list[dict]:
        embs = list(
            self.store.embeddings.find(
                {"repo_id": repo_id, "branch": branch, "embedding_dim": len(q_vec)},
                {"_id": 0},
            )
        )
        if not embs:
            return []
        chunk_map = {
            c["chunk_id"]: c
            for c in self.store.chunks.find(
                {"repo_id": repo_id, "branch": branch}, {"_id": 0}
            )
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

    def _text_search(
        self,
        repo_id: str,
        branch: str,
        q: str,
        top_k: int,
        lang: str | None,
        path_prefix: str | None,
        include_tests: bool,
    ) -> list[dict]:
        def _fallback_text() -> list[dict]:
            rex = re.compile(re.escape(q), re.IGNORECASE)
            fallback_docs: list[dict] = []
            for c in self.store.chunks.find(
                {"repo_id": repo_id, "branch": branch}, {"_id": 0}
            ):
                m = rex.search(c.get("content", "")) or rex.search(
                    c.get("file_path", "")
                )
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
                        "must": [
                            {"text": {"query": q, "path": ["content", "file_path"]}}
                        ],
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

        docs = self._apply_filters(docs, lang, path_prefix, include_tests)
        for d in docs:
            d["reason"] = "text-match"
        return docs

    def _apply_filters(
        self,
        docs: list[dict],
        lang: str | None,
        path_prefix: str | None,
        include_tests: bool,
    ) -> list[dict]:
        out = docs
        if lang:
            out = [d for d in out if d.get("language") == lang]
        if path_prefix:
            out = [d for d in out if d.get("file_path", "").startswith(path_prefix)]
        if not include_tests:
            out = [
                d
                for d in out
                if not self._is_test_path((d.get("file_path") or "").lower())
            ]
        return out

    @staticmethod
    def _is_test_path(path: str) -> bool:
        return (
            path.startswith("tests/")
            or "/tests/" in path
            or path.startswith("test_")
            or "/test_" in path
            or path.endswith("_test.py")
            or path.endswith("test.py")
        )

    def _fuse(
        self, vector_hits: list[dict], text_hits: list[dict], top_k: int
    ) -> list[dict]:
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

    def _expand_graph(
        self, repo_id: str, branch: str, docs: list[dict], top_k: int
    ) -> list[dict]:
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
                "$or": [
                    {"from_symbol_id": {"$in": list(symbol_ids)}},
                    {"to_symbol_id": {"$in": list(symbol_ids)}},
                ],
            },
            {"_id": 0, "from_symbol_id": 1, "to_symbol_id": 1},
        ):
            related_symbols.add(edge["from_symbol_id"])
            related_symbols.add(edge["to_symbol_id"])

        extra = list(
            self.store.chunks.find(
                {
                    "repo_id": repo_id,
                    "branch": branch,
                    "symbol_refs": {"$in": list(related_symbols)},
                },
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
        query_mentions_test = any(t in q_terms for t in {"test", "tests", "pytest"})
        technical_query = any(
            t in q_terms
            for t in {
                "how",
                "where",
                "call",
                "calls",
                "called",
                "function",
                "method",
                "class",
                "service",
                "orchestrator",
            }
        )

        for d in docs:
            tokens = set(
                re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", d.get("content", "").lower())
            )
            overlap = len(q_terms.intersection(tokens))

            path = (d.get("file_path") or "").lower()
            bonus = 0.0
            if path.startswith("src/") or "/src/" in path:
                bonus += 0.02

            is_test_path = (
                path.startswith("tests/")
                or "/tests/" in path
                or path.startswith("test_")
                or "/test_" in path
                or path.endswith("_test.py")
                or path.endswith("test.py")
            )
            if is_test_path and not query_mentions_test:
                bonus -= 0.06

            is_docs_like = path.endswith((".md", ".rst", ".yml", ".yaml", ".json"))
            if is_docs_like and technical_query and not query_mentions_test:
                bonus -= 0.03

            if (
                "def test_" in (d.get("content", "").lower())
                and not query_mentions_test
            ):
                bonus -= 0.03

            d["score"] = float(d.get("score", 0.0)) + 0.01 * math.log1p(overlap) + bonus
            if overlap:
                d["reason"] = f"{d.get('reason', 'match')}+rerank"
        docs.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return docs
