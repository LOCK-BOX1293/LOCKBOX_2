from __future__ import annotations

from pydantic import BaseModel, Field


class IndexRequest(BaseModel):
    repo_path: str = Field(min_length=1)
    repo_id: str = Field(min_length=1)
    branch: str = Field(default="main", min_length=1)


class RetrieveRequest(BaseModel):
    repo_id: str = Field(min_length=1)
    branch: str = Field(default="main", min_length=1)
    q: str = Field(min_length=1)
    top_k: int = 8
    lang: str | None = None
    path_prefix: str | None = None
    include_tests: bool = False


class GraphNodeRequest(BaseModel):
    repo_id: str
    branch: str = "main"
    node_type: str = "symbol"


class QueryResponse(BaseModel):
    chunks: list[dict]
    confidence: float
