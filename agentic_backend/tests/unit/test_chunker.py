from __future__ import annotations

from app.chunker.semantic_chunker import SemanticChunker
from app.hashing import deterministic_chunk_id



def test_chunker_is_deterministic() -> None:
    chunker = SemanticChunker(target_tokens=120, overlap_tokens=20)
    content = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    symbols = [
        {"symbol_id": "s1", "symbol_type": "function", "start_line": 1, "end_line": 2},
        {"symbol_id": "s2", "symbol_type": "function", "start_line": 4, "end_line": 5},
    ]
    c1 = chunker.build_chunks("r", "main", "c1", "m.py", "python", content, symbols)
    c2 = chunker.build_chunks("r", "main", "c1", "m.py", "python", content, symbols)
    assert [c["chunk_id"] for c in c1] == [c["chunk_id"] for c in c2]



def test_chunk_id_determinism() -> None:
    one = deterministic_chunk_id("r", "f.py", 1, 10, "abc")
    two = deterministic_chunk_id("r", "f.py", 1, 10, "abc")
    assert one == two
