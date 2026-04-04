from __future__ import annotations

from app.agents.specialists import (
    ExplanationAgent,
    VisualMapperAgent,
    parse_answer_payload,
)
from app.config import get_settings
from app.llm.gemini import GeminiClient
from app.memory.session_store import (
    InMemorySessionStore,
    MongoSessionStore,
    SessionStore,
)
from app.models import AskRequest, AskResponse, SessionEvent
from app.retrieval.providers import (
    HttpRetrievalProvider,
    LocalHybridRetrievalProvider,
    RetrievalProvider,
)


class Orchestrator:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.llm = GeminiClient(
            api_key=settings.gemini_api_key, model=settings.gemini_model
        )
        self.explainer = ExplanationAgent(self.llm)
        self.visual_mapper = VisualMapperAgent(self.llm)
        self.retrieval: RetrievalProvider = (
            HttpRetrievalProvider(settings.retrieval_service_url)
            if settings.retrieval_service_url
            else LocalHybridRetrievalProvider()
        )
        self.sessions: SessionStore = (
            MongoSessionStore(settings.mongodb_uri, settings.mongodb_db)
            if settings.mongodb_uri
            else InMemorySessionStore()
        )

    def _infer_intent(self, query: str) -> str:
        q = query.lower()
        if "where" in q or "find" in q:
            return "where-is"
        if "debug" in q or "error" in q or "fix" in q:
            return "debug"
        if "refactor" in q:
            return "refactor"
        if "explain" in q or "how" in q or "why" in q:
            return "explain"
        return "find"

    def ask(self, req: AskRequest) -> AskResponse:
        intent = self._infer_intent(req.query)
        history_events = self.sessions.recent_context(
            req.project_id, req.session_id, limit=6
        )
        history_text = "\n".join([f"{e.role}: {e.content}" for e in history_events])

        retrieval_result = self.retrieval.retrieve(
            project_id=req.project_id,
            query=req.query,
            top_k=self.settings.retrieval_top_k,
        )

        try:
            raw_answer = self.explainer.explain(
                query=req.query,
                user_role=req.user_role,
                chunks=retrieval_result.chunks,
                history=history_text,
            )
        except Exception as exc:
            # Graceful fallback: still provide retrieval-grounded response when LLM
            # generation is unavailable (quota/network/model issues).
            lines = [
                "LLM generation unavailable; returning retrieval-grounded context.",
                f"Reason: {str(exc)}",
                "",
                "Relevant evidence:",
            ]
            for i, c in enumerate(retrieval_result.chunks[:5], start=1):
                lines.append(
                    f"[{i}] {c.file_path}:{c.start_line}-{c.end_line} score={c.score:.4f}"
                )
                snippet = c.text.strip().replace("\n", " ")
                lines.append(f"    {snippet[:220]}")
            raw_answer = "\n".join(lines)
        answer, confidence, citations = parse_answer_payload(
            raw_answer, retrieval_result.chunks
        )
        graph = self.visual_mapper.build_query_trace(
            query=req.query,
            user_role=req.user_role,
            chunks=retrieval_result.chunks,
            answer=answer,
            confidence=confidence,
            citations=citations,
            session_id=req.session_id,
            intent=intent,
        )

        self.sessions.append_event(
            SessionEvent(
                project_id=req.project_id,
                session_id=req.session_id,
                role="user",
                content=req.query,
            )
        )
        self.sessions.append_event(
            SessionEvent(
                project_id=req.project_id,
                session_id=req.session_id,
                role="assistant",
                content=answer,
            )
        )

        return AskResponse(
            answer=answer,
            intent=intent,
            confidence=confidence,
            citations=citations,
            graph=graph,
        )
