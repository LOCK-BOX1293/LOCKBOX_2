from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTIC_BACKEND = ROOT / "agentic_backend"
if str(AGENTIC_BACKEND) not in sys.path:
    sys.path.insert(0, str(AGENTIC_BACKEND))

from app.config import get_settings
from app.llm.gemini import GeminiClient
from app.mindflow.orchestrator import MindflowOrchestrator
from app.mindflow.models import MindflowTurnRequest


def run_demo() -> None:
    settings = get_settings()
    llm = GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
    flow = MindflowOrchestrator(
        llm=llm, drift_threshold=settings.mindflow_drift_threshold
    )

    conversation = [
        "Let's build a backend API for task tracking with FastAPI and MongoDB.",
        "Add authentication and role-based access next.",
        "Actually, wait, let's talk about pricing strategy for our SaaS launch instead.",
        "Compare monthly vs usage-based pricing and what competitors do.",
    ]

    for i, msg in enumerate(conversation, start=1):
        res = flow.run_turn(
            MindflowTurnRequest(
                project_id="mindflow-demo",
                session_id="sim-1",
                message=msg,
                user_role="general",
            )
        )
        print("=" * 80)
        print(f"TURN {i}")
        print(f"USER: {msg}")
        print(f"ASSISTANT: {res.reply[:300]}{'...' if len(res.reply) > 300 else ''}")
        print(
            f"DRIFT: {res.drift_detected} (score={res.drift_score}) | active_ws={res.active_workspace_id} | workspaces={len(res.workspaces)}"
        )
        print(f"TOOLS: {[t['tool'] for t in res.tool_trace]}")


if __name__ == "__main__":
    run_demo()
