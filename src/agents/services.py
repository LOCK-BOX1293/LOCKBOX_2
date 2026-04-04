import time
import uuid
from typing import Callable, List, Optional

from src.agents.models import (
    AgentRequest,
    ContextChunk,
    GuardAgentResponse,
    MemoryAgentResponse,
    OrchestratorInput,
    RoleAgentResponse,
    StandardResponse,
)
from src.core.config import logger, settings
from src.retrieval.search import Retriever


def _observe(agent_name: str, trace_id: str, fn: Callable[[], object]):
    start = time.perf_counter()
    try:
        result = fn()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info("agent_success", agent=agent_name, trace_id=trace_id, latency_ms=latency_ms)
        return result
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error("agent_failure", agent=agent_name, trace_id=trace_id, latency_ms=latency_ms, error=str(exc))
        raise


def classify_query(query: str) -> RoleAgentResponse:
    q = query.lower()
    debug_terms = ["debug", "trace", "stack", "error", "exception", "failing", "bug"]
    intent = "debug" if any(t in q for t in debug_terms) else "qa"
    simple_query = len(q.split()) <= 5 and intent != "debug"
    debug_query = intent == "debug"

    role = "expert_debugger" if debug_query else "expert_architect"
    confidence = 0.85 if debug_query else (0.8 if simple_query else 0.78)

    return RoleAgentResponse(
        intent=intent,
        role=role,
        simple_query=simple_query,
        debug_query=debug_query,
        confidence=confidence,
    )


def role_agent(request: AgentRequest) -> RoleAgentResponse:
    trace_id = request.trace_id or str(uuid.uuid4())
    logger.info(
        "agent_input",
        agent="role",
        trace_id=trace_id,
        query_len=len(request.query),
        repo_id=request.repo_id,
        branch=request.branch,
    )
    return _observe("role", trace_id, lambda: classify_query(request.query))


def _rerank(chunks: List[ContextChunk], query: str) -> List[ContextChunk]:
    query_terms = {t for t in query.lower().split() if len(t) > 2}
    rescored = []

    for c in chunks:
        hay = f"{c.file_path} {c.content}".lower()
        overlap = sum(1 for t in query_terms if t in hay)
        blended = (c.score * 0.7) + (overlap * 0.3)
        rescored.append((blended, c))

    rescored.sort(key=lambda x: x[0], reverse=True)

    filtered: List[ContextChunk] = []
    for score, chunk in rescored:
        if score <= 0:
            continue
        filtered.append(
            ContextChunk(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                score=round(float(score), 4),
                confidence=chunk.confidence,
                reason="reranked_high_relevance",
            )
        )

    return filtered


def memory_agent(request: AgentRequest) -> MemoryAgentResponse:
    trace_id = request.trace_id or str(uuid.uuid4())
    logger.info(
        "agent_input",
        agent="memory",
        trace_id=trace_id,
        query_len=len(request.query),
        top_k=request.top_k,
        repo_id=request.repo_id,
        branch=request.branch,
    )

    def _run() -> MemoryAgentResponse:
        retriever = Retriever()
        raw = retriever.retrieve_hybrid(request.repo_id, request.branch, request.query, top_k=request.top_k)

        chunks = [
            ContextChunk(
                chunk_id=r["chunk"]["chunk_id"],
                file_path=r["chunk"]["file_path"],
                start_line=r["chunk"]["start_line"],
                end_line=r["chunk"]["end_line"],
                content=r["chunk"]["content"],
                score=float(r["score"]),
                confidence=float(r["confidence"]),
                reason=r.get("reason", "hybrid_match"),
            )
            for r in raw
        ]

        reranked = _rerank(chunks, request.query)
        high_relevance = reranked[: request.top_k]
        sources = sorted({c.file_path for c in high_relevance})

        confidence = 0.0
        if high_relevance:
            confidence = round(sum(c.confidence for c in high_relevance) / (100.0 * len(high_relevance)), 4)

        output = MemoryAgentResponse(chunks=high_relevance, sources=sources, confidence=confidence)
        logger.info(
            "agent_output",
            agent="memory",
            trace_id=trace_id,
            chunks=len(output.chunks),
            source_count=len(output.sources),
            confidence=output.confidence,
        )
        return output

    return _observe("memory", trace_id, _run)


def orchestrator_agent(payload: OrchestratorInput) -> StandardResponse:
    trace_id = payload.request.trace_id or str(uuid.uuid4())
    logger.info(
        "agent_input",
        agent="orchestrator",
        trace_id=trace_id,
        agents_used=payload.agents_used,
        has_memory=bool(payload.memory and payload.memory.chunks),
    )

    def _run() -> StandardResponse:
        if payload.memory and payload.memory.chunks:
            top = payload.memory.chunks[0]
            answer = (
                f"Found relevant flow in {top.file_path} lines {top.start_line}-{top.end_line}. "
                f"Top reasoning source: {top.reason}."
            )
            confidence = max(payload.role.confidence * 0.6 + payload.memory.confidence * 0.4, 0.1)
            sources = payload.memory.sources
        else:
            answer = (
                "This looks like a straightforward request. "
                "No deep repository retrieval was required for this response path."
            )
            confidence = payload.role.confidence * 0.75
            sources = []

        response = StandardResponse(
            answer=answer,
            agents_used=payload.agents_used,
            confidence=round(min(confidence, 0.99), 4),
            sources=sources,
        )
        logger.info(
            "agent_output",
            agent="orchestrator",
            trace_id=trace_id,
            answer_len=len(response.answer),
            confidence=response.confidence,
            source_count=len(response.sources),
        )
        return response

    return _observe("orchestrator", trace_id, _run)


def guard_agent(response: StandardResponse, trace_id: Optional[str] = None) -> GuardAgentResponse:
    effective_trace = trace_id or str(uuid.uuid4())
    logger.info(
        "agent_input",
        agent="guard",
        trace_id=effective_trace,
        confidence=response.confidence,
        source_count=len(response.sources),
    )

    def _run() -> GuardAgentResponse:
        reasons: List[str] = []
        unsafe_terms = ["drop database", "steal", "exploit", "bypass auth"]
        lower_answer = response.answer.lower()

        if any(t in lower_answer for t in unsafe_terms):
            reasons.append("unsafe_content_detected")

        if response.confidence < settings.guard_min_confidence:
            reasons.append("low_confidence")

        accepted = len(reasons) == 0
        final = response

        if not accepted:
            final = StandardResponse(
                answer="I cannot provide a safe high-confidence answer for this request.",
                agents_used=response.agents_used + ["guard"],
                confidence=0.0,
                sources=[],
            )
        else:
            if "guard" not in final.agents_used:
                final.agents_used = final.agents_used + ["guard"]

        guarded = GuardAgentResponse(accepted=accepted, reasons=reasons, response=final)
        logger.info(
            "agent_output",
            agent="guard",
            trace_id=effective_trace,
            accepted=guarded.accepted,
            reasons=guarded.reasons,
            confidence=guarded.response.confidence,
        )
        return guarded

    return _observe("guard", effective_trace, _run)
