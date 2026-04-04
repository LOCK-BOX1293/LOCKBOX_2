from __future__ import annotations

import json
import hashlib
from collections import defaultdict

from app.llm.gemini import GeminiClient
from app.models import Citation, RetrievedChunk
from app.prompt_loader import build_system_prompt


def _format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "No retrieved evidence available."

    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(
            "\n".join(
                [
                    f"[{idx}] file={chunk.file_path}",
                    f"lines={chunk.start_line}-{chunk.end_line}",
                    f"symbol={chunk.symbol_name or 'n/a'}",
                    f"score={chunk.score:.4f}",
                    f"text={chunk.text}",
                ]
            )
        )
    return "\n\n".join(lines)


class ExplanationAgent:
    def __init__(self, llm: GeminiClient) -> None:
        self.llm = llm

    def explain(self, query: str, user_role: str, chunks: list[RetrievedChunk], history: str) -> str:
        system_prompt = build_system_prompt(user_role)
        prompt = (
            "Use only the evidence below. If insufficient, say what is missing.\n\n"
            f"User query:\n{query}\n\n"
            f"Recent session context:\n{history or 'No prior context.'}\n\n"
            f"Evidence:\n{_format_context(chunks)}\n\n"
            "Return JSON with keys: summary, findings (array of strings), next_steps (array), confidence (0..1)."
        )
        return self.llm.generate(system_prompt, prompt)


class VisualMapperAgent:
    def build_graph(self, chunks: list[RetrievedChunk]) -> dict:
        nodes = []
        edges = []
        seen = set()
        for chunk in chunks:
            if chunk.file_path not in seen:
                nodes.append({"id": chunk.file_path, "label": chunk.file_path, "type": "file"})
                seen.add(chunk.file_path)
            if chunk.symbol_name:
                symbol_id = f"{chunk.file_path}:{chunk.symbol_name}"
                nodes.append({"id": symbol_id, "label": chunk.symbol_name, "type": "symbol"})
                edges.append({"source": chunk.file_path, "target": symbol_id, "type": "contains"})
        return {"nodes": nodes, "edges": edges}

    def build_query_trace(
        self,
        query: str,
        user_role: str,
        chunks: list[RetrievedChunk],
        answer: str,
        confidence: float,
        citations: list[Citation],
        session_id: str,
        intent: str,
    ) -> dict:
        qhash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
        run_id = f"{session_id}:{qhash}"
        nodes: list[dict] = []
        edges: list[dict] = []

        def add_node(node: dict) -> None:
            nodes.append(node)

        def add_edge(source: str, target: str, relation: str) -> None:
            edges.append({"source": source, "target": target, "type": relation})

        query_id = f"trace:{run_id}:query"
        route_id = f"trace:{run_id}:route"
        retrieve_id = f"trace:{run_id}:retrieve"
        evidence_id = f"trace:{run_id}:evidence"
        explain_id = f"trace:{run_id}:explain"
        answer_id = f"trace:{run_id}:answer"

        add_node(
            {
                "id": query_id,
                "label": query,
                "display_label": query,
                "type": "query",
                "stage": "question",
                "reason": "user-query",
            }
        )
        add_node(
            {
                "id": route_id,
                "label": "POST /ask",
                "display_label": "POST /ask",
                "type": "stage",
                "stage": "route",
                "reason": "api-entry",
                "meta": {"session_id": session_id, "intent": intent, "role": user_role},
            }
        )
        add_node(
            {
                "id": retrieve_id,
                "label": "retrieve grounded evidence",
                "display_label": "retrieve grounded evidence",
                "type": "stage",
                "stage": "retrieve",
                "reason": "retrieval-pass",
                "relevance_score": confidence,
                "meta": {"chunk_count": len(chunks)},
            }
        )
        add_node(
            {
                "id": evidence_id,
                "label": "select answer path",
                "display_label": "select answer path",
                "type": "stage",
                "stage": "rank",
                "reason": "evidence-selection",
                "meta": {"citation_count": len(citations)},
            }
        )
        add_node(
            {
                "id": explain_id,
                "label": "compose grounded answer",
                "display_label": "compose grounded answer",
                "type": "stage",
                "stage": "explain",
                "reason": "llm-synthesis",
                "relevance_score": confidence,
            }
        )
        add_node(
            {
                "id": answer_id,
                "label": "final answer",
                "display_label": "final answer",
                "type": "answer",
                "stage": "answer",
                "reason": answer[:220],
                "relevance_score": confidence,
                "meta": {
                    "confidence": confidence,
                    "citation_count": len(citations),
                },
            }
        )

        add_edge(query_id, route_id, "enters")
        add_edge(route_id, retrieve_id, "runs")
        add_edge(retrieve_id, evidence_id, "collects")
        add_edge(evidence_id, explain_id, "grounds")
        add_edge(explain_id, answer_id, "produces")

        file_best_score: dict[str, float] = {}
        file_spans: dict[str, tuple[int, int]] = {}
        file_symbols: dict[str, list[RetrievedChunk]] = defaultdict(list)

        for chunk in chunks:
            current = file_best_score.get(chunk.file_path, -1.0)
            if chunk.score > current:
                file_best_score[chunk.file_path] = chunk.score
            span = file_spans.get(chunk.file_path)
            if span is None:
                file_spans[chunk.file_path] = (chunk.start_line, chunk.end_line)
            else:
                file_spans[chunk.file_path] = (
                    min(span[0], chunk.start_line),
                    max(span[1], chunk.end_line),
                )
            if chunk.symbol_name:
                file_symbols[chunk.file_path].append(chunk)

        sorted_files = sorted(
            file_best_score.items(),
            key=lambda item: (-item[1], item[0]),
        )[:6]

        terminal_ids: list[str] = []
        for index, (file_path, score) in enumerate(sorted_files, start=1):
            start_line, end_line = file_spans[file_path]
            file_id = f"trace:{run_id}:file:{index}"
            add_node(
                {
                    "id": file_id,
                    "label": file_path,
                    "display_label": file_path,
                    "type": "file",
                    "stage": "evidence",
                    "relevance_score": score,
                    "reason": f"retrieved lines {start_line}-{end_line}",
                    "meta": {
                        "file_path": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                    },
                }
            )
            add_edge(retrieve_id, file_id, "retrieves")
            add_edge(file_id, evidence_id, "supports")
            terminal_ids.append(file_id)

            symbol_chunks = sorted(
                file_symbols.get(file_path, []),
                key=lambda chunk: (-chunk.score, chunk.symbol_name or ""),
            )
            seen_symbols: set[str] = set()
            for sym_index, chunk in enumerate(symbol_chunks, start=1):
                symbol_name = (chunk.symbol_name or "").strip()
                if not symbol_name or symbol_name in seen_symbols:
                    continue
                seen_symbols.add(symbol_name)
                symbol_id = f"trace:{run_id}:symbol:{index}:{sym_index}"
                add_node(
                    {
                        "id": symbol_id,
                        "label": f"{symbol_name}()",
                        "display_label": f"{symbol_name} ({file_path.split('/')[-1]})",
                        "type": "symbol",
                        "stage": "evidence",
                        "relevance_score": chunk.score,
                        "reason": f"symbol evidence at {file_path}:{chunk.start_line}-{chunk.end_line}",
                        "meta": {
                            "file_path": file_path,
                            "symbol_name": symbol_name,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                        },
                    }
                )
                add_edge(file_id, symbol_id, "contains")
                add_edge(symbol_id, evidence_id, "highlights")
                terminal_ids.append(symbol_id)
                if len(seen_symbols) >= 3:
                    break

        citation_ids: list[str] = []
        for index, citation in enumerate(citations[:5], start=1):
            citation_id = f"trace:{run_id}:citation:{index}"
            add_node(
                {
                    "id": citation_id,
                    "label": f"{citation.file_path}:{citation.start_line}-{citation.end_line}",
                    "display_label": f"{citation.file_path}:{citation.start_line}-{citation.end_line}",
                    "type": "citation",
                    "stage": "citation",
                    "reason": citation.why_relevant,
                }
            )
            add_edge(evidence_id, citation_id, "cites")
            add_edge(citation_id, answer_id, "verifies")
            citation_ids.append(citation_id)

        return {
            "mode": "query-trace",
            "run_id": run_id,
            "query": query,
            "session_id": session_id,
            "intent": intent,
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "confidence": confidence,
                "role": user_role,
                "retrieved_files": len(sorted_files),
                "terminal_count": len(terminal_ids),
                "citation_count": len(citation_ids),
                "step_count": 6,
            },
        }


def parse_answer_payload(raw: str, chunks: list[RetrievedChunk]) -> tuple[str, float, list[Citation]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "summary": raw,
            "findings": [],
            "next_steps": [],
            "confidence": 0.25,
        }

    summary = str(parsed.get("summary", "")).strip() or "No summary generated."
    findings = parsed.get("findings") or []
    next_steps = parsed.get("next_steps") or []
    confidence = float(parsed.get("confidence", 0.35))

    body = [summary]
    if findings:
        body.append("\nFindings:")
        body.extend([f"- {item}" for item in findings])
    if next_steps:
        body.append("\nRecommended next steps:")
        body.extend([f"- {item}" for item in next_steps])

    citations = [
        Citation(
            file_path=c.file_path,
            start_line=c.start_line,
            end_line=c.end_line,
            why_relevant=f"Retrieved score {c.score:.3f}",
        )
        for c in chunks
    ]

    return "\n".join(body).strip(), max(0.0, min(confidence, 1.0)), citations
