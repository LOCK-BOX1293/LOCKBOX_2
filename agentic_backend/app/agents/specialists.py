from __future__ import annotations

import json
import hashlib
import re
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


def _clean_snippet(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned[:limit].rstrip(" ,;:.")


def _fallback_file_importance(query: str, file_path: str, chunks: list[RetrievedChunk]) -> str:
    ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
    symbol_names = [c.symbol_name for c in ranked if c.symbol_name]
    unique_symbols: list[str] = []
    for symbol in symbol_names:
        if symbol and symbol not in unique_symbols:
            unique_symbols.append(symbol)
        if len(unique_symbols) >= 3:
            break
    snippet = _clean_snippet(" ".join(c.text for c in ranked[:2]), 180)
    file_name = file_path.split("/")[-1] or file_path
    if unique_symbols:
        return f"Uses {', '.join(unique_symbols)} in {file_name} to answer the query. Evidence: {snippet or 'retrieved matching code.'}"
    return f"Uses the logic in {file_name} to answer the query. Evidence: {snippet or 'retrieved matching code.'}"


def _fallback_symbol_importance(file_path: str, symbol_name: str, chunk: RetrievedChunk) -> str:
    snippet = _clean_snippet(chunk.text, 150)
    file_name = file_path.split("/")[-1] or file_path
    return f"Shows how {symbol_name} works inside {file_name}. Evidence: {snippet or 'retrieved matching code.'}"


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
    def __init__(self, llm: GeminiClient | None = None) -> None:
        self.llm = llm

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

    def _annotate_trace_nodes(
        self,
        query: str,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
        file_annotations: dict[str, str] = {}
        symbol_annotations: dict[tuple[str, str], str] = {}
        if not self.llm or not chunks:
            return file_annotations, symbol_annotations

        by_file: dict[str, list[RetrievedChunk]] = defaultdict(list)
        for chunk in chunks:
            by_file[chunk.file_path].append(chunk)

        file_sections: list[str] = []
        top_files = sorted(
            by_file.items(),
            key=lambda item: max((c.score for c in item[1]), default=0.0),
            reverse=True,
        )[:6]
        for index, (file_path, file_chunks) in enumerate(top_files, start=1):
            ranked_chunks = sorted(file_chunks, key=lambda c: c.score, reverse=True)
            symbols = [c.symbol_name for c in ranked_chunks if c.symbol_name][:3]
            excerpt = " ".join(c.text.strip().replace("\n", " ")[:180] for c in ranked_chunks[:2]).strip()
            file_sections.append(
                "\n".join(
                    [
                        f"FILE {index}",
                        f"path={file_path}",
                        f"symbols={', '.join(symbols) if symbols else 'n/a'}",
                        f"evidence={excerpt or 'n/a'}",
                    ]
                )
            )

        prompt = (
            "You are annotating a query trace graph.\n"
            "For each file, write one compact sentence that states the real job of that file for this query.\n"
            "For each symbol, write one compact sentence only if the symbol clearly matters.\n"
            "Do not say generic phrases like 'explains', 'helps', 'is relevant', or 'matters'.\n"
            "Name the concrete role: fetches news, ranks candidates, checks coverage, builds fallback data, composes answer, routes request, etc.\n"
            "Do not repeat the file path in the sentence. Start with a concrete verb when possible.\n\n"
            f"Query:\n{query}\n\n"
            f"Final answer:\n{answer[:1200]}\n\n"
            f"Evidence groups:\n{chr(10).join(file_sections)}\n\n"
            "Return strict JSON with shape:\n"
            "{"
            "\"files\":[{\"path\":\"...\",\"importance\":\"...\"}],"
            "\"symbols\":[{\"path\":\"...\",\"symbol\":\"...\",\"importance\":\"...\"}]"
            "}"
        )

        try:
            raw = self.llm.generate("Trace annotation assistant", prompt)
            parsed = json.loads(raw)
        except Exception:
            return file_annotations, symbol_annotations

        for item in parsed.get("files", []) or []:
            path = str(item.get("path", "")).strip()
            importance = str(item.get("importance", "")).strip()
            if path and importance:
                file_annotations[path] = importance

        for item in parsed.get("symbols", []) or []:
            path = str(item.get("path", "")).strip()
            symbol = str(item.get("symbol", "")).strip()
            importance = str(item.get("importance", "")).strip()
            if path and symbol and importance:
                symbol_annotations[(path, symbol)] = importance

        return file_annotations, symbol_annotations

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

        file_annotations, symbol_annotations = self._annotate_trace_nodes(
            query=query,
            answer=answer,
            chunks=chunks,
        )

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
                    "label": file_path.split("/")[-1] or file_path,
                    "display_label": file_path.split("/")[-1] or file_path,
                    "type": "file",
                    "stage": "evidence",
                    "relevance_score": score,
                    "reason": file_annotations.get(file_path)
                    or _fallback_file_importance(query, file_path, file_symbols.get(file_path, [])),
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
                        "display_label": f"{symbol_name}()",
                        "type": "symbol",
                        "stage": "evidence",
                        "relevance_score": chunk.score,
                        "reason": symbol_annotations.get((file_path, symbol_name))
                        or _fallback_symbol_importance(file_path, symbol_name, chunk),
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
    def _markdown_to_plain_text(value: str) -> str:
        src = str(value or "").replace("\r", "")
        # Handle escaped newlines/tabs commonly returned by model JSON-in-text outputs.
        src = src.replace("\\n", "\n").replace("\\t", "\t")
        src = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).replace("```", "").strip(), src)
        src = re.sub(r"`([^`]+)`", r"\1", src)
        src = re.sub(r"!\[([^\]]+)\]\(([^)]+)\)", r"\1", src)
        src = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", src)
        src = re.sub(r"^#{1,6}\s*", "", src, flags=re.MULTILINE)
        src = re.sub(r"#{1,6}\s*", "", src)
        src = re.sub(r"^>\s?", "", src, flags=re.MULTILINE)
        src = re.sub(r"\*\*([^*]+)\*\*", r"\1", src)
        src = re.sub(r"__([^_]+)__", r"\1", src)
        src = re.sub(r"\*([^*]+)\*", r"\1", src)
        src = re.sub(r"_([^_]+)_", r"\1", src)
        src = re.sub(r"^\s*[-*+]\s+", "", src, flags=re.MULTILINE)
        src = re.sub(r"^\s*\d+\.\s+", "", src, flags=re.MULTILINE)
        src = re.sub(r"<[^>]+>", "", src)
        src = re.sub(r"[ \t]{2,}", " ", src)
        src = re.sub(r"\n{3,}", "\n\n", src)
        return src.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "summary": _markdown_to_plain_text(raw),
            "findings": [],
            "next_steps": [],
            "confidence": 0.25,
        }

    summary = _markdown_to_plain_text(str(parsed.get("summary", "")).strip()) or "No summary generated."
    findings = [
        _markdown_to_plain_text(str(item))
        for item in (parsed.get("findings") or [])
        if str(item).strip()
    ]
    next_steps = [
        _markdown_to_plain_text(str(item))
        for item in (parsed.get("next_steps") or [])
        if str(item).strip()
    ]
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
