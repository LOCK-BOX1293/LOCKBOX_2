from __future__ import annotations

import json
import re

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
