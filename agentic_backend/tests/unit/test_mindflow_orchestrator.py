from __future__ import annotations

from app.mindflow.models import MindflowTurnRequest
from app.mindflow.orchestrator import MindflowOrchestrator


class StubLLM:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "Here is a concise plan with next steps."


def test_mindflow_creates_nodes_and_edges() -> None:
    flow = MindflowOrchestrator(llm=StubLLM(), drift_threshold=0.9)
    res = flow.run_turn(
        MindflowTurnRequest(
            project_id="p1",
            session_id="s1",
            message="Let's build a parser. Next step is write tests.",
        )
    )
    assert len(res.workspaces) == 1
    ws = res.workspaces[0]
    assert len(ws.nodes) >= 1
    assert any(t["tool"] == "make_node" for t in res.tool_trace)
    assert any(t["tool"] == "change_canvas" for t in res.tool_trace)


def test_mindflow_drift_switches_workspace_on_strong_phrase() -> None:
    flow = MindflowOrchestrator(llm=StubLLM(), drift_threshold=0.95)
    flow.run_turn(
        MindflowTurnRequest(
            project_id="p2",
            session_id="s2",
            message="Let's discuss backend architecture and indexing.",
        )
    )
    res = flow.run_turn(
        MindflowTurnRequest(
            project_id="p2",
            session_id="s2",
            message="Actually, wait, let's talk about pricing tiers instead.",
        )
    )
    assert res.drift_detected is True
    assert len(res.workspaces) >= 2
    assert any(t["tool"] == "change_canvas" for t in res.tool_trace)
