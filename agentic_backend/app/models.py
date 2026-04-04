from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    file_path: str
    start_line: int = 1
    end_line: int = 1
    why_relevant: str = ""


class RetrievedChunk(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    text: str
    score: float = 0.0
    symbol_name: str | None = None


class AskRequest(BaseModel):
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    user_role: str = "backend"
    branch: str = Field(default="main", min_length=1)
    path_prefix: str | None = None
    include_tests: bool = False


class AskResponse(BaseModel):
    answer: str
    intent: str
    confidence: float
    citations: list[Citation]
    graph: dict


class RetrievalResult(BaseModel):
    chunks: list[RetrievedChunk] = Field(default_factory=list)


class SessionEvent(BaseModel):
    project_id: str
    session_id: str
    role: str
    content: str
