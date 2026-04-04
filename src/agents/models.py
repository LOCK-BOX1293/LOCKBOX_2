from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    query: str
    repo_id: str
    branch: str = "main"
    top_k: int = 5
    trace_id: Optional[str] = None


class ContextChunk(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    confidence: float
    reason: str


class RoleAgentResponse(BaseModel):
    intent: str
    role: str
    simple_query: bool
    debug_query: bool
    confidence: float


class MemoryAgentResponse(BaseModel):
    chunks: List[ContextChunk] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class OrchestratorInput(BaseModel):
    request: AgentRequest
    role: RoleAgentResponse
    memory: Optional[MemoryAgentResponse] = None
    agents_used: List[str] = Field(default_factory=list)


class StandardResponse(BaseModel):
    answer: str
    agents_used: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    sources: List[str] = Field(default_factory=list)


class GuardAgentResponse(BaseModel):
    accepted: bool
    reasons: List[str] = Field(default_factory=list)
    response: StandardResponse


class SuperplaneExecuteRequest(BaseModel):
    query: str
    repo_id: str
    branch: str = "main"
    top_k: int = 5


class SuperplaneExecuteResponse(StandardResponse):
    trace_id: str
    chunks: List[ContextChunk] = Field(default_factory=list)
    routing: Dict[str, Any] = Field(default_factory=dict)
