from __future__ import annotations

from app.hashing import deterministic_chunk_id, estimate_token_count, stable_hash


class SemanticChunker:
    def __init__(self, target_tokens: int, overlap_tokens: int) -> None:
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens

    def build_chunks(self, repo_id: str, branch: str, commit_sha: str, file_path: str, language: str, content: str, symbols: list[dict]) -> list[dict]:
        lines = content.splitlines()
        if not lines:
            return []

        chunks: list[dict] = []
        symbol_windows = [s for s in symbols if s["symbol_type"] in {"class", "function", "module"}]
        if symbol_windows:
            symbol_windows = sorted(symbol_windows, key=lambda s: (s["start_line"], s["end_line"]))
            for i, symbol in enumerate(symbol_windows):
                start = max(1, symbol["start_line"])
                end = min(len(lines), max(start, symbol["end_line"]))
                text = "\n".join(lines[start - 1 : end]).strip()
                if not text:
                    continue
                c_hash = stable_hash(text)
                chunks.append(
                    {
                        "repo_id": repo_id,
                        "project_id": repo_id,
                        "branch": branch,
                        "commit_sha": commit_sha,
                        "chunk_id": deterministic_chunk_id(repo_id, file_path, start, end, c_hash),
                        "chunk_key": f"{commit_sha}:{file_path}:{start}-{end}:{c_hash[:10]}",
                        "file_path": file_path,
                        "chunk_index": i,
                        "start_line": start,
                        "end_line": end,
                        "content": text,
                        "content_hash": c_hash,
                        "token_count": estimate_token_count(text),
                        "language": language,
                        "symbol_refs": [symbol["symbol_id"]],
                        "metadata": {"strategy": "symbol"},
                        "indexed_at": None,
                    }
                )

        if chunks:
            return chunks

        words = content.split()
        idx = 0
        chunk_index = 0
        while idx < len(words):
            window = words[idx : idx + self.target_tokens]
            text = " ".join(window)
            c_hash = stable_hash(text)
            start_line = 1
            end_line = len(lines)
            chunks.append(
                {
                    "repo_id": repo_id,
                    "project_id": repo_id,
                    "branch": branch,
                    "commit_sha": commit_sha,
                    "chunk_id": deterministic_chunk_id(repo_id, file_path, start_line, end_line, c_hash),
                    "chunk_key": f"{commit_sha}:{file_path}:{start_line}-{end_line}:{c_hash[:10]}",
                    "file_path": file_path,
                    "chunk_index": chunk_index,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": text,
                    "content_hash": c_hash,
                    "token_count": estimate_token_count(text),
                    "language": language,
                    "symbol_refs": [],
                    "metadata": {"strategy": "window"},
                    "indexed_at": None,
                }
            )
            chunk_index += 1
            idx += max(1, self.target_tokens - self.overlap_tokens)
        return chunks
