from __future__ import annotations

from pydantic import BaseModel, Field


NodeType = str


class WorkspaceNode(BaseModel):
    id: str
    type: NodeType
    title: str
    content: str = ""
    source_message_id: str
    workspace_id: str
    imported: bool = False
    metadata: dict = Field(default_factory=dict)


class WorkspaceEdge(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    relation: str = "related"
    workspace_id: str


class WorkspaceGroup(BaseModel):
    id: str
    workspace_id: str
    title: str
    node_ids: list[str] = Field(default_factory=list)


class PipelineWorkspace(BaseModel):
    id: str
    title: str
    parent_workspace_id: str | None = None
    inherited_nodes: list[str] = Field(default_factory=list)
    nodes: list[WorkspaceNode] = Field(default_factory=list)
    edges: list[WorkspaceEdge] = Field(default_factory=list)
    groups: list[WorkspaceGroup] = Field(default_factory=list)
    created_at: str


class ChatTurn(BaseModel):
    id: str
    role: str
    text: str
    workspace_id: str


class MindflowSessionState(BaseModel):
    project_id: str
    session_id: str
    workspaces: list[PipelineWorkspace] = Field(default_factory=list)
    active_workspace_id: str | None = None
    messages: list[ChatTurn] = Field(default_factory=list)
    topic_centroid_terms: list[str] = Field(default_factory=list)
    pending_drift_hits: int = 0


class MindflowTurnRequest(BaseModel):
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    user_role: str = "general"


class MindflowTurnResponse(BaseModel):
    reply: str
    drift_detected: bool
    drift_score: float
    active_workspace_id: str
    workspaces: list[PipelineWorkspace]
    tool_trace: list[dict]
