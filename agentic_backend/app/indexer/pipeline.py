from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.chunker.semantic_chunker import SemanticChunker
from app.embedder.providers import EmbeddingClient, build_provider
from app.logging_utils import get_logger
from app.parser.symbol_parser import SymbolParser
from app.scanner.repo_scanner import RepoScanner
from app.settings import AppSettings
from app.storage.mongo_store import MongoStore


class IndexingPipeline:
    def __init__(self, settings: AppSettings, store: MongoStore) -> None:
        self.settings = settings
        self.store = store
        self.logger = get_logger("indexer")
        self.scanner = RepoScanner()
        self.parser = SymbolParser()
        self.chunker = SemanticChunker(
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        provider = build_provider(
            name=settings.embedding_provider,
            model=settings.embedding_model,
            dimension=settings.embedding_dim,
        )
        self.embedder = EmbeddingClient(provider, batch_size=settings.embedding_batch_size)

    def ensure_indexes(self, repo_id: str) -> None:
        self.store.ensure_standard_indexes()
        self.store.ensure_search_indexes(self.settings.embedding_dim)
        self.store.validate_embedding_dimension(self.settings.embedding_dim)
        repo = self.store.get_repo(repo_id)
        if not repo:
            self.store.upsert_repo(repo_id, repo_id, "", "main", None)

    def index_full(self, repo_path: str, repo_id: str, branch: str) -> dict:
        return self._index(repo_path=repo_path, repo_id=repo_id, branch=branch, mode="full")

    def index_incremental(self, repo_path: str, repo_id: str, branch: str) -> dict:
        return self._index(repo_path=repo_path, repo_id=repo_id, branch=branch, mode="incremental")

    def _index(self, repo_path: str, repo_id: str, branch: str, mode: str) -> dict:
        repo_root = Path(repo_path)
        job_id = self.store.start_job(repo_id=repo_id, mode=mode)
        errors: list[str] = []
        stats = defaultdict(int)
        started = datetime.now(timezone.utc)

        try:
            commit_sha = self.scanner.current_commit(repo_root)
            prev = self.store.get_repo(repo_id)
            previous_commit = (prev or {}).get("last_indexed_commit") if prev else None
            self.store.upsert_repo(repo_id, repo_root.name, str(repo_root), branch, commit_sha)

            all_files = self.scanner.scan(repo_root)
            files_to_process = all_files
            deleted: list[str] = []

            if mode == "incremental" and previous_commit and previous_commit != "no-git" and commit_sha != "no-git":
                changes = self.scanner.changed_files(repo_root, previous_commit, commit_sha)
                touched = set(changes["added"] + changes["modified"])
                deleted = changes["deleted"]
                if touched:
                    files_to_process = [f for f in all_files if f["file_path"] in touched]
                else:
                    hash_by_path = {
                        d["file_path"]: d["file_hash"]
                        for d in self.store.files.find(
                            {"repo_id": repo_id, "branch": branch}, {"_id": 0, "file_path": 1, "file_hash": 1}
                        )
                    }
                    files_to_process = [f for f in all_files if hash_by_path.get(f["file_path"]) != f["file_hash"]]

            stats["files_scanned"] = len(all_files)
            stats["files_selected"] = len(files_to_process)

            if deleted:
                deleted_counts = self.store.delete_by_paths(repo_id, branch, deleted)
                for k, v in deleted_counts.items():
                    stats[f"deleted_{k}"] += v

            file_docs: list[dict] = []
            symbol_docs: list[dict] = []
            chunk_docs: list[dict] = []

            for f in files_to_process:
                try:
                    file_docs.append(
                        {
                            "repo_id": repo_id,
                            "branch": branch,
                            "commit_sha": commit_sha,
                            "file_path": f["file_path"],
                            "language": f["language"],
                            "size_bytes": f["size_bytes"],
                            "file_hash": f["file_hash"],
                            "content": f["content"],
                            "indexed_at": datetime.now(timezone.utc),
                        }
                    )
                    symbols = self.parser.parse(
                        repo_id=repo_id,
                        branch=branch,
                        commit_sha=commit_sha,
                        file_path=f["file_path"],
                        language=f["language"],
                        content=f["content"],
                    )
                    symbol_docs.extend(symbols)
                    chunks = self.chunker.build_chunks(
                        repo_id=repo_id,
                        branch=branch,
                        commit_sha=commit_sha,
                        file_path=f["file_path"],
                        language=f["language"],
                        content=f["content"],
                        symbols=symbols,
                    )
                    chunk_docs.extend(chunks)
                except Exception as exc:
                    errors.append(f"{f['file_path']}: {exc}")

            stats["symbols_extracted"] = len(symbol_docs)
            stats["chunks_created"] = len(chunk_docs)

            self.store.upsert_many(
                self.store.files,
                file_docs,
                key_fields=["repo_id", "branch", "commit_sha", "file_path"],
            )
            self.store.upsert_many(
                self.store.symbols,
                symbol_docs,
                key_fields=["repo_id", "branch", "commit_sha", "symbol_id"],
            )
            self.store.upsert_many(
                self.store.chunks,
                chunk_docs,
                key_fields=["repo_id", "branch", "commit_sha", "chunk_id"],
            )

            vectors = self.embedder.embed_with_retry([c["content"] for c in chunk_docs])
            if vectors and len(vectors[0]) != self.settings.embedding_dim:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected {self.settings.embedding_dim}, got {len(vectors[0])}"
                )

            emb_docs = []
            for chunk, vector in zip(chunk_docs, vectors):
                emb_docs.append(
                    {
                        "repo_id": repo_id,
                        "branch": branch,
                        "commit_sha": commit_sha,
                        "chunk_id": chunk["chunk_id"],
                        "embedding_model": self.settings.embedding_model,
                        "embedding_dim": self.settings.embedding_dim,
                        "vector": vector,
                        "created_at": datetime.now(timezone.utc),
                    }
                )

            self.store.upsert_many(
                self.store.embeddings,
                emb_docs,
                key_fields=["repo_id", "branch", "commit_sha", "chunk_id"],
            )

            stats["embeddings_created"] = len(emb_docs)
            stats["duration_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            status = "success" if not errors else "partial-success"
            self.store.finish_job(job_id, status=status, stats=dict(stats), errors=errors)
            return {"job_id": job_id, "status": status, "stats": dict(stats), "errors": errors}
        except Exception as exc:
            errors.append(str(exc))
            stats["duration_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            self.store.finish_job(job_id, status="failed", stats=dict(stats), errors=errors)
            raise
