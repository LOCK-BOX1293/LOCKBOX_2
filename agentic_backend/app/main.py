from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.models import AskRequest, AskResponse
from app.orchestrator import Orchestrator


app = FastAPI(title="Hackbite 2 Agentic API", version="0.1.0")
orchestrator = Orchestrator()


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "gemini_configured": bool(settings.gemini_api_key),
        "retrieval_service_configured": bool(settings.retrieval_service_url),
        "mongo_configured": bool(settings.mongodb_uri),
    }


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        return orchestrator.ask(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
