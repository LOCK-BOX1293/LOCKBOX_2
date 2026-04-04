from __future__ import annotations

from app.llm.gemini import GeminiClient
from app.mindflow.drift import score_drift, update_centroid_terms
from app.mindflow.extractors import extract_candidates, should_search
from app.mindflow.models import (
    ChatTurn,
    MindflowSessionState,
    MindflowTurnRequest,
    MindflowTurnResponse,
)
from app.mindflow.tools import MindflowToolbox


class MindflowOrchestrator:
    def __init__(self, llm: GeminiClient, drift_threshold: float = 0.62) -> None:
        self.llm = llm
        self.drift_threshold = drift_threshold
        self.tools = MindflowToolbox()
        self._sessions: dict[tuple[str, str], MindflowSessionState] = {}

    def _session(self, project_id: str, session_id: str) -> MindflowSessionState:
        key = (project_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = MindflowSessionState(
                project_id=project_id,
                session_id=session_id,
            )
        return self._sessions[key]

    def _build_reply(
        self, req: MindflowTurnRequest, state: MindflowSessionState
    ) -> str:
        recent = state.messages[-6:]
        history = "\n".join([f"{m.role}: {m.text}" for m in recent])
        prompt = (
            "You are Mindflow assistant. Give a concise, helpful reply.\n"
            "User message:\n"
            f"{req.message}\n\n"
            f"Recent chat:\n{history or 'none'}"
        )
        try:
            return self.llm.generate("Mindflow assistant", prompt)
        except Exception:
            return "Got it. I captured your direction and mapped it on the canvas."

    def run_turn(self, req: MindflowTurnRequest) -> MindflowTurnResponse:
        state = self._session(req.project_id, req.session_id)
        workspace = self.tools.ensure_workspace(state)
        tool_trace: list[dict] = []

        user_msg = ChatTurn(
            id=self.tools._next_id("msg"),
            role="user",
            text=req.message,
            workspace_id=workspace.id,
        )
        state.messages.append(user_msg)

        # 1) streamable chat reply (single-call here)
        reply = self._build_reply(req, state)
        assistant_msg = ChatTurn(
            id=self.tools._next_id("msg"),
            role="assistant",
            text=reply,
            workspace_id=workspace.id,
        )
        state.messages.append(assistant_msg)

        # 2) candidate extraction
        candidates = extract_candidates(req.message, reply)
        created_nodes = []
        for c in candidates:
            node = self.tools.make_node(
                workspace=workspace,
                node_type=c["type"],
                title=c["title"],
                content=c["content"],
                source_message_id=user_msg.id,
            )
            created_nodes.append(node)
            tool_trace.append(
                {
                    "tool": "make_node",
                    "args": {
                        "type": c["type"],
                        "title": c["title"],
                    },
                    "result": {"node_id": node.id},
                }
            )

        # 3) connect sequential nodes
        for left, right in zip(created_nodes, created_nodes[1:]):
            edge = self.tools.make_connection(
                workspace,
                from_node_id=left.id,
                to_node_id=right.id,
                relation="related",
            )
            tool_trace.append(
                {
                    "tool": "make_connection",
                    "args": {
                        "fromNodeId": left.id,
                        "toNodeId": right.id,
                        "relation": "related",
                    },
                    "result": {"edge_id": edge.id},
                }
            )

        # 4) optional search + fetch + search-result nodes
        if should_search(req.message):
            hits = self.tools.search(req.message)
            tool_trace.append(
                {
                    "tool": "search",
                    "args": {"query": req.message},
                    "result": {"hits": len(hits)},
                }
            )
            parent = created_nodes[0] if created_nodes else None
            for hit in hits[:2]:
                detail = (
                    self.tools.fetch_doc(hit.get("url", "")) if hit.get("url") else ""
                )
                tool_trace.append(
                    {
                        "tool": "fetch_doc",
                        "args": {"url": hit.get("url", "")},
                        "result": {"chars": len(detail)},
                    }
                )
                s_node = self.tools.make_node(
                    workspace=workspace,
                    node_type="search-result",
                    title=hit.get("title") or "Search result",
                    content=(hit.get("snippet") or "")
                    + (f"\n\n{detail}" if detail else ""),
                    source_message_id=assistant_msg.id,
                    metadata={"url": hit.get("url", ""), "externally_sourced": True},
                )
                tool_trace.append(
                    {
                        "tool": "make_node",
                        "args": {"type": "search-result", "title": s_node.title},
                        "result": {"node_id": s_node.id},
                    }
                )
                if parent:
                    edge = self.tools.make_connection(
                        workspace,
                        from_node_id=parent.id,
                        to_node_id=s_node.id,
                        relation="enriched-by",
                    )
                    tool_trace.append(
                        {
                            "tool": "make_connection",
                            "args": {
                                "fromNodeId": parent.id,
                                "toNodeId": s_node.id,
                                "relation": "enriched-by",
                            },
                            "result": {"edge_id": edge.id},
                        }
                    )

        # 5) simple grouping for same-type clusters
        concepts = [n.id for n in created_nodes if n.type == "concept"]
        if len(concepts) >= 2:
            grp = self.tools.group_nodes(workspace, concepts, "Concept cluster")
            if grp:
                tool_trace.append(
                    {
                        "tool": "group_nodes",
                        "args": {"nodeIds": concepts, "groupTitle": "Concept cluster"},
                        "result": {"group_id": grp.id},
                    }
                )

        # 6) drift detection + workspace switch
        recent_text = "\n".join(m.text for m in state.messages[-8:-1])
        drift_score, diagnostics = score_drift(
            current_message=req.message,
            recent_text=recent_text,
            centroid_terms=state.topic_centroid_terms,
        )
        strong_phrase = bool(diagnostics.get("transition_hit"))
        drift_hit = drift_score >= self.drift_threshold
        state.pending_drift_hits = state.pending_drift_hits + 1 if drift_hit else 0

        drift_detected = strong_phrase or state.pending_drift_hits >= 2
        if drift_detected:
            carry = [
                n
                for n in workspace.nodes[-6:]
                if n.type in {"concept", "decision", "step"}
            ]
            new_ws = self.tools.change_canvas(
                state,
                mode="new_workspace",
                payload={
                    "title": "Shifted Topic",
                    "carry_over_nodes": carry,
                },
            )
            tool_trace.append(
                {
                    "tool": "change_canvas",
                    "args": {
                        "mode": "new_workspace",
                        "payload": {"carry_over_count": len(carry)},
                    },
                    "result": {"active_workspace_id": new_ws.id},
                }
            )
            state.pending_drift_hits = 0
            reply = (
                f"Looks like we're moving into a new topic. "
                f"Opening a new workspace and preserving {len(carry)} key nodes.\n\n{reply}"
            )
        else:
            self.tools.change_canvas(state, mode="reuse_workspace", payload={})
            tool_trace.append(
                {
                    "tool": "change_canvas",
                    "args": {"mode": "reuse_workspace", "payload": {}},
                    "result": {"active_workspace_id": state.active_workspace_id},
                }
            )

        state.topic_centroid_terms = update_centroid_terms(
            state.topic_centroid_terms,
            req.message,
        )

        return MindflowTurnResponse(
            reply=reply,
            drift_detected=drift_detected,
            drift_score=drift_score,
            active_workspace_id=state.active_workspace_id or "",
            workspaces=state.workspaces,
            tool_trace=tool_trace,
        )
