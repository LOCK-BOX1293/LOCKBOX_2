from __future__ import annotations

from app.embedder.providers import LocalHashEmbeddingProvider



def test_embedding_contract_dimension() -> None:
    provider = LocalHashEmbeddingProvider(model="hash", dimension=64)
    vectors = provider.embed(["a", "b"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 64
