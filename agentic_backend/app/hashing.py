from __future__ import annotations

import hashlib



def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()



def deterministic_chunk_id(repo_id: str, file_path: str, start_line: int, end_line: int, content_hash: str) -> str:
    payload = f"{repo_id}:{file_path}:{start_line}:{end_line}:{content_hash}"
    return stable_hash(payload)



def estimate_token_count(text: str) -> int:
    return max(1, len(text.split()))
