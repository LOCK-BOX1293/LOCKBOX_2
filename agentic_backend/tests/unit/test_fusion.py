from __future__ import annotations

from app.retrieval.hybrid import HybridRetriever


class _DummyStore:
    pass


class _DummySettings:
    embedding_provider = "local"
    embedding_model = "hash"
    embedding_dim = 16
    embedding_batch_size = 4
    rerank_enabled = False



def test_weighted_fusion_prefers_joint_hits() -> None:
    retriever = HybridRetriever(_DummySettings(), _DummyStore())
    vector = [
        {"chunk_id": "c1", "file_path": "a", "start_line": 1, "end_line": 2, "content": "x", "score": 1.0},
        {"chunk_id": "c2", "file_path": "b", "start_line": 1, "end_line": 2, "content": "x", "score": 0.8},
    ]
    text = [
        {"chunk_id": "c2", "file_path": "b", "start_line": 1, "end_line": 2, "content": "x", "score": 1.0},
    ]
    fused = retriever._fuse(vector, text, top_k=3)
    assert fused[0]["chunk_id"] == "c2"
