from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileRecord:
    repo_id: str
    branch: str
    commit_sha: str
    file_path: str
    language: str
    size_bytes: int
    file_hash: str
    content: str


@dataclass(frozen=True)
class SymbolRecord:
    repo_id: str
    branch: str
    commit_sha: str
    symbol_id: str
    file_path: str
    symbol_type: str
    name: str
    signature: str
    start_line: int
    end_line: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkRecord:
    repo_id: str
    branch: str
    commit_sha: str
    chunk_id: str
    file_path: str
    chunk_index: int
    start_line: int
    end_line: int
    content: str
    content_hash: str
    token_count: int
    language: str
    symbol_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalChunk:
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    reason: str
