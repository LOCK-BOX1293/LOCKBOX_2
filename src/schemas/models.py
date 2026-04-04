from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MongoBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # Using alias="_id" allows MongoDB natural IDs, but we might just ignore them or assign explicit string fields.
    # In MongoDB `_id` is auto-generated if missing.


class Repo(MongoBaseModel):
    repo_id: str
    name: str
    root_path: str
    default_branch: str
    last_indexed_commit: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RepoFile(MongoBaseModel):
    repo_id: str
    branch: str
    commit_sha: str
    file_path: str
    language: str
    size_bytes: int
    file_hash: str
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class Symbol(MongoBaseModel):
    repo_id: str
    branch: str
    commit_sha: str
    symbol_id: str
    file_path: str
    symbol_type: str  # class/function/module/import
    name: str
    signature: Optional[str] = None
    start_line: int
    end_line: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Chunk(MongoBaseModel):
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
    symbol_refs: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class Embedding(MongoBaseModel):
    repo_id: str
    branch: str
    commit_sha: str
    chunk_id: str
    embedding_model: str
    embedding_dim: int
    vector: List[float]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Edge(MongoBaseModel):
    repo_id: str
    branch: str
    from_symbol_id: str
    to_symbol_id: str
    edge_type: str  # calls/imports/references
    weight: float = 1.0


class IndexJob(MongoBaseModel):
    job_id: str
    repo_id: str
    mode: str  # full/incremental
    status: str  # running/completed/failed
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    stats: Dict[str, int] = Field(default_factory=lambda: {
        "files_scanned": 0,
        "files_parsed": 0,
        "symbols_extracted": 0,
        "chunks_created": 0,
        "embeddings_created": 0,
        "upserts": 0,
        "deletes": 0,
        "errors": 0
    })
    errors: List[str] = Field(default_factory=list)


class Session(MongoBaseModel):
    session_id: str
    user_id: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    recent_queries: List[str] = Field(default_factory=list)
    ttl_expires_at: datetime
