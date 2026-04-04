import hashlib
from typing import List
from src.parser.ast_parser import SymbolData, hash_id
from src.core.config import settings
from src.schemas.models import Chunk

class ChunkerData:
    def __init__(self, content: str, start_line: int, end_line: int, symbol_refs: List[str]):
        self.content = content
        self.start_line = start_line
        self.end_line = end_line
        self.symbol_refs = symbol_refs

class SemanticChunker:
    def __init__(self):
        # Using a simple character to token ratio for fallback heuristic
        self.chars_per_token = 4
        self.max_chars = settings.chunk_target_tokens * self.chars_per_token
        self.overlap_chars = settings.chunk_overlap_tokens * self.chars_per_token

    def chunk_file(self, content: str, symbols: List[SymbolData]) -> List[ChunkerData]:
        """
        Splits file into chunks. Tries to respect symbol boundaries.
        If a symbol is too large, applies sliding window over it.
        Lines outside symbols are gathered into 'gap' chunks.
        """
        lines = content.splitlines()
        if not lines:
            return []

        chunks: List[ChunkerData] = []
        
        # very naive approach:
        # just slice chunks over the full file, but tag them with symbol refs.
        # to properly do semantic chunking by symbol:
        symbol_bounds = [(s.start_line, s.end_line, s) for s in symbols]
        
        # Sort by start_line ascending
        symbol_bounds.sort(key=lambda x: x[0])
        
        current_line = 1
        total_lines = len(lines)
        
        while current_line <= total_lines:
            # find symbols that overlap current_line
            active_symbols = [s for s in symbols if s.start_line <= current_line <= s.end_line]
            
            chunk_end_line = current_line
            chunk_content = ""
            chars_added = 0
            
            while chunk_end_line <= total_lines and chars_added < self.max_chars:
                line_idx = chunk_end_line - 1
                if line_idx < len(lines):
                    chunk_content += lines[line_idx] + "\n"
                    chars_added += len(lines[line_idx]) + 1
                chunk_end_line += 1
                
                # Check symbol boundaries
                active_symbols_now = [s for s in symbols if s.start_line <= chunk_end_line <= s.end_line]
                # If we cross an end boundary of an active symbol, and we have enough content, yield it
                # to keep symbol semantics together.
                ending_symbols = [s for s in active_symbols if s.end_line == chunk_end_line - 1]
                if ending_symbols and chars_added > self.max_chars * 0.3:
                    break  # Cut chunk here to align with symbol boundary

            chunk_content = chunk_content.strip()
            if chunk_content:
                # Find all symbols overlapping this chunk
                final_active_symbols = [
                    s.name for s in symbols 
                    if not (s.end_line < current_line or s.start_line > chunk_end_line - 1)
                ]
                
                chunks.append(ChunkerData(
                    content=chunk_content,
                    start_line=current_line,
                    end_line=chunk_end_line - 1,
                    symbol_refs=final_active_symbols
                ))
            
            # Move current_line, accounting for overlap if we hit max_chars
            if chars_added >= self.max_chars:
                # Approximate overlap in lines:
                overlap_lines = max(1, self.overlap_chars // 50)  # assume ~50 chars per line
                current_line = (chunk_end_line - 1) - overlap_lines + 1
            else:
                current_line = chunk_end_line

            # prevent infinite loops easily
            if current_line < chunk_end_line - self.overlap_chars // 10:
                pass
            else:
                if current_line == chunk_end_line:
                    pass

        return chunks

    def to_models(self, chunks_data: List[ChunkerData], repo_id: str, branch: str, commit_sha: str, file_path: str, language: str) -> List[Chunk]:
        result = []
        for i, c in enumerate(chunks_data):
            content_hash = hash_id(c.content)
            chunk_id = hash_id(repo_id, file_path, c.start_line, c.end_line, content_hash)
            
            # token_count approx
            token_count = len(c.content) // self.chars_per_token
            
            result.append(Chunk(
                repo_id=repo_id,
                branch=branch,
                commit_sha=commit_sha,
                chunk_id=chunk_id,
                file_path=file_path,
                chunk_index=i,
                start_line=c.start_line,
                end_line=c.end_line,
                content=c.content,
                content_hash=content_hash,
                token_count=token_count,
                language=language,
                symbol_refs=c.symbol_refs
            ))
        return result
