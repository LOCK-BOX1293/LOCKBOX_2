from __future__ import annotations

from pathlib import Path

import mongomock

from app.indexer.pipeline import IndexingPipeline
from app.retrieval.hybrid import HybridRetriever
from app.settings import AppSettings
from app.storage.mongo_store import MongoStore


class MockStore(MongoStore):
    def __init__(self) -> None:
        self.client = mongomock.MongoClient()
        self.db = self.client["testdb"]

    def ensure_search_indexes(self, embedding_dim: int) -> None:
        return


def _settings() -> AppSettings:
    return AppSettings(
        mongodb_uri="mongodb://mock",
        mongodb_db="testdb",
        embedding_provider="local",
        embedding_model="hash-v1",
        embedding_dim=64,
        embedding_batch_size=8,
        chunk_target_tokens=120,
        chunk_overlap_tokens=20,
        index_top_k_default=5,
        rerank_enabled=True,
        debug_log_vectors=False,
        index_import_symbols=False,
    )


def test_full_index_and_retrieve(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")

    settings = _settings()
    store = MockStore()
    pipeline = IndexingPipeline(settings, store)
    retriever = HybridRetriever(settings, store)

    pipeline.ensure_indexes("r1")
    result = pipeline.index_full(str(repo), "r1", "main")
    assert result["status"] in {"success", "partial-success"}

    out = retriever.query("r1", "main", "add", top_k=3)
    assert out["chunks"]
    assert out["chunks"][0]["file_path"] == "mod.py"


def test_incremental_runs(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    repo.mkdir()
    f = repo / "mod.py"
    f.write_text("def a():\n    return 1\n", encoding="utf-8")

    settings = _settings()
    store = MockStore()
    pipeline = IndexingPipeline(settings, store)

    pipeline.ensure_indexes("r2")
    one = pipeline.index_full(str(repo), "r2", "main")
    assert one["status"] in {"success", "partial-success"}

    f.write_text("def a():\n    return 2\n", encoding="utf-8")
    two = pipeline.index_incremental(str(repo), "r2", "main")
    assert two["status"] in {"success", "partial-success"}
