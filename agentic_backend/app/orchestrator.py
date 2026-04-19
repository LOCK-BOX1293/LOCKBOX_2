from __future__ import annotations

import json
import re

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
            branch=req.branch,
            query=req.query,
            top_k=self.settings.retrieval_top_k,
            path_prefix=req.path_prefix,
            include_tests=req.include_tests,
        )

        raw_answer: str
        if self.settings.ask_force_local:
            raw_answer = self._build_local_answer(req.query, retrieval_result.chunks)
        else:
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

    def _build_local_answer(self, query: str, chunks) -> str:
        if not chunks:
            return json.dumps(
                {
                    "summary": "No indexed evidence found for this question on the selected branch.",
                    "findings": [],
                    "next_steps": [
                        "Run indexing for the same repo_id and branch, then retry.",
                        "Ask a narrower question with file/module names.",
                    ],
                    "confidence": 0.0,
                }
            )

        top = chunks[:8]
        query_terms = self._query_terms(query)
        evidence_sentences = self._rank_evidence_sentences(query_terms, top)

        if evidence_sentences:
            direct_summary = " ".join(evidence_sentences[:3])
        else:
            lead = top[0]
            direct_summary = (
                f"The strongest evidence is in {lead.file_path}:{lead.start_line}-{lead.end_line}. "
                "This module is directly involved in the behavior requested by your question."
            )

        findings = [
            f"{c.file_path}:{c.start_line}-{c.end_line} (score {c.score:.3f})"
            for c in top[:5]
        ]
        max_score = max((float(c.score) for c in top), default=0.0)
        confidence = max(0.35, min(0.92, 0.45 + (max_score * 1.8)))

        summary = (
            f"{direct_summary}\n\n"
            f"Evidence used: {len(chunks)} chunks, strongest from {top[0].file_path}."
        )

        return json.dumps(
            {
                "summary": summary,
                "findings": findings,
                "next_steps": [
                    "Open cited files and lines to verify behavior.",
                    "Refine question to a specific function for deeper answers.",
                ],
                "confidence": round(confidence, 3),
            }
        )

    def _query_terms(self, query: str) -> set[str]:
        stop_words = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "by",
            "for",
            "from",
            "how",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "that",
            "the",
            "this",
            "to",
            "use",
            "what",
            "with",
        }
        terms = {t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query)}
        return {t for t in terms if t not in stop_words and len(t) > 2}

    def _rank_evidence_sentences(self, query_terms: set[str], chunks) -> list[str]:
        candidates: list[tuple[float, str]] = []
        seen: set[str] = set()

        for chunk in chunks:
            text = chunk.text or ""
            # Split into sentence-like segments; keep only informative snippets.
            segments = re.split(r"(?<=[.!?])\s+|\n+", text)
            for seg in segments:
                sentence = " ".join(seg.split()).strip()
                if len(sentence) < 45:
                    continue
                if sentence in seen:
                    continue
                lower = sentence.lower()
                overlap = sum(1 for term in query_terms if term in lower)
                score = float(chunk.score) + (0.08 * overlap)
                candidates.append((score, sentence))
                seen.add(sentence)

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [sent for _, sent in candidates[:6]]
