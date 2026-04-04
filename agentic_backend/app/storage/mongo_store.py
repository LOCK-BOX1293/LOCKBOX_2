from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection


class MongoStore:
    def __init__(self, uri: str, db_name: str) -> None:
        self.client = MongoClient(uri)
        self.db = self.client[db_name]

    @property
    def repos(self) -> Collection:
        return self.db.repos

    @property
    def files(self) -> Collection:
        return self.db.files

    @property
    def symbols(self) -> Collection:
        return self.db.symbols

    @property
    def chunks(self) -> Collection:
        return self.db.chunks

    @property
    def embeddings(self) -> Collection:
        return self.db.embeddings

    @property
    def edges(self) -> Collection:
        return self.db.edges

    @property
    def index_jobs(self) -> Collection:
        return self.db.index_jobs

    @property
    def sessions(self) -> Collection:
        return self.db.sessions

    @property
    def retrieval_runs(self) -> Collection:
        return self.db.retrieval_runs

    def ensure_standard_indexes(self) -> None:
        self.chunks.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("file_path", ASCENDING)], name="ix_chunks_repo_branch_path")
        self.chunks.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("content_hash", ASCENDING)], name="ix_chunks_repo_branch_hash")
        self.symbols.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("file_path", ASCENDING), ("name", ASCENDING)], name="ix_symbols_repo_branch_path_name")
        self.files.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("file_path", ASCENDING), ("commit_sha", ASCENDING)], name="ix_files_repo_branch_path_commit")
        self.index_jobs.create_index([("repo_id", ASCENDING), ("started_at", DESCENDING)], name="ix_jobs_repo_started")

        self.files.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("file_path", ASCENDING)], unique=True, name="ux_files_repo_branch_commit_path")
        self.chunks.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("chunk_id", ASCENDING)], unique=True, name="ux_chunks_repo_branch_commit_chunk")
        self.symbols.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("symbol_id", ASCENDING)], unique=True, name="ux_symbols_repo_branch_commit_symbol")

        self.sessions.create_index([("ttl_expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_sessions")
        self.index_jobs.create_index([("finished_at", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 14, name="ttl_jobs_14d")

    def ensure_search_indexes(self, embedding_dim: int) -> None:
        try:
            self.db.command(
                {
                    "createSearchIndexes": "embeddings",
                    "indexes": [
                        {
                            "name": "embeddings_vector_v1",
                            "type": "vectorSearch",
                            "definition": {
                                "fields": [
                                    {
                                        "type": "vector",
                                        "path": "vector",
                                        "numDimensions": embedding_dim,
                                        "similarity": "cosine",
                                    },
                                    {"type": "filter", "path": "repo_id"},
                                    {"type": "filter", "path": "branch"},
                                ]
                            },
                        }
                    ],
                }
            )
        except Exception:
            pass

        try:
            self.db.command(
                {
                    "createSearchIndexes": "chunks",
                    "indexes": [
                        {
                            "name": "chunks_text_v1",
                            "type": "search",
                            "definition": {
                                "mappings": {
                                    "dynamic": False,
                                    "fields": {
                                        "content": {"type": "string"},
                                        "file_path": {"type": "string"},
                                        "repo_id": {"type": "string"},
                                        "branch": {"type": "string"},
                                    },
                                }
                            },
                        }
                    ],
                }
            )
        except Exception:
            pass

    def validate_embedding_dimension(self, expected_dim: int) -> None:
        sample = self.embeddings.find_one({}, {"vector": 1})
        if not sample or "vector" not in sample:
            return
        dim = len(sample["vector"])
        if dim != expected_dim:
            raise RuntimeError(f"Embedding dimension mismatch in DB: expected {expected_dim}, found {dim}")

    def upsert_repo(self, repo_id: str, name: str, root_path: str, default_branch: str, last_indexed_commit: str | None) -> None:
        now = datetime.now(timezone.utc)
        self.repos.update_one(
            {"repo_id": repo_id},
            {
                "$set": {
                    "name": name,
                    "root_path": root_path,
                    "default_branch": default_branch,
                    "last_indexed_commit": last_indexed_commit,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def get_repo(self, repo_id: str) -> dict[str, Any] | None:
        return self.repos.find_one({"repo_id": repo_id}, {"_id": 0})

    def start_job(self, repo_id: str, mode: str) -> str:
        now = datetime.now(timezone.utc)
        job_id = f"{repo_id}:{int(now.timestamp() * 1000)}:{mode}"
        self.index_jobs.insert_one(
            {
                "job_id": job_id,
                "repo_id": repo_id,
                "mode": mode,
                "status": "running",
                "started_at": now,
                "finished_at": None,
                "stats": {},
                "errors": [],
            }
        )
        return job_id

    def finish_job(self, job_id: str, status: str, stats: dict[str, Any], errors: list[str]) -> None:
        self.index_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": status,
                    "finished_at": datetime.now(timezone.utc),
                    "stats": stats,
                    "errors": errors,
                }
            },
        )

    def upsert_many(self, collection: Collection, docs: list[dict], key_fields: list[str]) -> int:
        if not docs:
            return 0
        now = datetime.now(timezone.utc)
        for d in docs:
            if "indexed_at" in d and d.get("indexed_at") is None:
                d["indexed_at"] = now
        changed = 0
        for doc in docs:
            filt = {k: doc[k] for k in key_fields}
            result = collection.update_one(filt, {"$set": doc}, upsert=True)
            changed += int(result.modified_count) + int(result.upserted_id is not None)
        return changed

    def delete_by_paths(self, repo_id: str, branch: str, file_paths: list[str]) -> dict[str, int]:
        if not file_paths:
            return {"files": 0, "symbols": 0, "chunks": 0, "embeddings": 0, "edges": 0}
        files_deleted = self.files.delete_many({"repo_id": repo_id, "branch": branch, "file_path": {"$in": file_paths}}).deleted_count
        symbols = list(self.symbols.find({"repo_id": repo_id, "branch": branch, "file_path": {"$in": file_paths}}, {"symbol_id": 1, "_id": 0}))
        symbol_ids = [s["symbol_id"] for s in symbols]
        symbols_deleted = self.symbols.delete_many({"repo_id": repo_id, "branch": branch, "file_path": {"$in": file_paths}}).deleted_count
        chunks = list(self.chunks.find({"repo_id": repo_id, "branch": branch, "file_path": {"$in": file_paths}}, {"chunk_id": 1, "_id": 0}))
        chunk_ids = [c["chunk_id"] for c in chunks]
        chunks_deleted = self.chunks.delete_many({"repo_id": repo_id, "branch": branch, "file_path": {"$in": file_paths}}).deleted_count
        embeddings_deleted = self.embeddings.delete_many({"repo_id": repo_id, "branch": branch, "chunk_id": {"$in": chunk_ids}}).deleted_count
        edges_deleted = self.edges.delete_many({"repo_id": repo_id, "branch": branch, "$or": [{"from_symbol_id": {"$in": symbol_ids}}, {"to_symbol_id": {"$in": symbol_ids}}]}).deleted_count
        return {
            "files": files_deleted,
            "symbols": symbols_deleted,
            "chunks": chunks_deleted,
            "embeddings": embeddings_deleted,
            "edges": edges_deleted,
        }

    def write_session(self, session_id: str, user_id: str, recent_query: str) -> None:
        now = datetime.now(timezone.utc)
        self.sessions.update_one(
            {"session_id": session_id, "user_id": user_id},
            {
                "$set": {"ttl_expires_at": now + timedelta(days=7)},
                "$setOnInsert": {"preferences": {}},
                "$push": {"recent_queries": {"$each": [recent_query], "$slice": -20}},
            },
            upsert=True,
        )
