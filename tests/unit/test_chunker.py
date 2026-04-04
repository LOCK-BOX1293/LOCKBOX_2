from src.chunker.semantic_chunker import SemanticChunker
from src.parser.ast_parser import SymbolData

def test_chunking_with_symbols():
    chunker = SemanticChunker()
    # Mocking target to be very small to force multiple chunks
    chunker.max_chars = 40
    chunker.overlap_chars = 10
    
    code = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    symbols = [
        SymbolData("sym1", "function", start_line=1, end_line=2),
        SymbolData("sym2", "function", start_line=4, end_line=5)
    ]
    
    chunks = chunker.chunk_file(code, symbols)
    assert len(chunks) > 0
    # chunk 1 should probably have sym1
    assert "sym1" in chunks[0].symbol_refs
    
    models = chunker.to_models(chunks, "repo-1", "main", "sha", "file.py", "python")
    assert len(models) == len(chunks)
    assert models[0].chunk_id != ""
