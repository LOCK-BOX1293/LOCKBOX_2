from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from urllib import parse, request

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]
AGENTIC_BACKEND_DIR = ROOT_DIR / "agentic_backend"
if str(AGENTIC_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTIC_BACKEND_DIR))

load_dotenv(ROOT_DIR / ".env")

from app.llm.gemini import GeminiClient  # noqa: E402


class PlannerNodePayload(BaseModel):
    id: str
    title: str
    detail: str
    type: str
    x: float
    y: float
    width: float
    source: str
    sourceTurnId: str = ""
    tools: list[str] = Field(default_factory=list)
    linkedFrom: str | None = None
    imported: bool = False
    pinned: bool = False


class PlannerEdgePayload(BaseModel):
    id: str
    from_: str = Field(alias="from")
    to: str
    kind: str


class WorkspacePayload(BaseModel):
    id: str
    label: str
    topic: str
    drift: float = 0.0
    nodes: list[PlannerNodePayload] = Field(default_factory=list)
    edges: list[PlannerEdgePayload] = Field(default_factory=list)
    importedFrom: str | None = None


class ChatMessagePayload(BaseModel):
    id: str
    role: str
    text: str
    workspaceId: str
    tools: list[str] | None = None


class ChatStreamRequest(BaseModel):
    prompt: str
    workspace: WorkspacePayload
    messages: list[ChatMessagePayload] = Field(default_factory=list)
    allowNodes: bool = True
    allowLinks: bool = True


class PlanCardPayload(BaseModel):
    title: str
    detail: str
    type: str = "concept"
    role: str = "main"


class PlanEdgePayload(BaseModel):
    from_index: int
    to_index: int
    kind: str = "transforms"


class StructuredPlanPayload(BaseModel):
    title: str
    summary: str
    cards: list[PlanCardPayload] = Field(default_factory=list)
    edges: list[PlanEdgePayload] = Field(default_factory=list)
    imported: list[int] = Field(default_factory=list)


class PlannerRuntime:
    def __init__(self) -> None:
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        self.drift_threshold = float(os.getenv("MINDFLOW_DRIFT_THRESHOLD", "0.62"))
        self.chat_gemini = GeminiClient(self.gemini_api_key, self.gemini_model)
        self._counter = 1

    def next_id(self, prefix: str) -> str:
        value = f"{prefix}_{self._counter}"
        self._counter += 1
        return value

    def normalize(self, text: str) -> list[str]:
        raw = re.sub(r"[^a-z0-9\s-]", " ", text.lower())
        tokens = [token for token in raw.split() if len(token) > 2]
        stop_words = {
            "the", "and", "for", "that", "with", "this", "from", "then", "will", "have",
            "there", "their", "about", "into", "they", "them", "what", "when", "where",
            "your", "you", "are", "was", "were", "can", "could", "should", "would",
            "like", "need", "just", "also", "only", "more", "less", "some", "any",
            "been", "being", "how", "why", "who", "use", "used", "using", "make",
            "create", "created", "idea", "ideas", "thing", "things", "point", "points",
        }
        return [token for token in tokens if token not in stop_words]

    def topic_label(self, text: str) -> str:
        tokens = self.normalize(text)
        if not tokens:
            return "Untitled idea"
        return " ".join(token.capitalize() for token in tokens[:3])

    def truncate(self, text: str, limit: int = 84) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned if len(cleaned) <= limit else f"{cleaned[:limit - 1].rstrip()}…"

    def workspace_centroid(self, workspace: WorkspacePayload) -> str:
        titles = [node.title for node in workspace.nodes if node.type != "search-result"][-6:]
        return " ".join(titles) or workspace.topic or workspace.label

    def score_drift(self, workspace: WorkspacePayload, prompt: str) -> tuple[float, str]:
        active = set(self.normalize(self.workspace_centroid(workspace)))
        current = self.normalize(prompt)
        if not current:
            return 0.0, "No drift detected."
        overlap = sum(1 for token in current if token in active)
        base = 1 - overlap / max(1, min(len(active) or 1, len(current)))
        phrase = bool(re.search(r"\b(actually|instead|forget|switch|wait|different|let's talk about)\b", prompt, re.I))
        if phrase:
            return min(1.0, base + 0.3), "The prompt contains an explicit topic switch phrase."
        return min(1.0, base), "Topic overlap against the current workspace centroid fell below the threshold."

    def classify_edit_intent(self, prompt: str) -> str:
        lower = prompt.lower()
        if re.search(r"\b(replace|rewrite|rework|revise|rearrange|restructure|edit|modify|refine|update|change)\b", lower):
            return "replace"
        if re.search(r"\b(add|append|include|insert|more|also|plus|another|extra)\b", lower):
            return "add"
        if re.search(r"\b(delete|remove|drop|erase|discard|skip|without|trim|cut)\b", lower):
            return "delete"
        return "neutral"

    def detect_node_type(self, text: str) -> str:
        lower = text.lower()
        if "?" in text or re.search(r"\b(why|how|what|when|where|who)\b", lower):
            return "question"
        if re.search(r"\b(decide|choose|prefer|settle|confirm|adopt)\b", lower):
            return "decision"
        if re.search(
            r"\b(do|build|ship|add|create|move|wire|write|review|make|implement|extract|group|verify|fact|retrieve|summarize|cluster|ground)\b",
            lower,
        ):
            return "step"
        if re.search(r"\b(search|source|evidence|paper|article|api|docs|reference|research)\b", lower):
            return "search-result"
        return "concept"

    def clean_title(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", cleaned)
        cleaned = re.sub(r"^\*\*(.+?)\*\*$", r"\1", cleaned)
        cleaned = re.sub(r"^\*(.+?)\*$", r"\1", cleaned)
        cleaned = cleaned.replace("`", "").replace('"', "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:72]

    def detail_for_node(self, title: str, node_type: str) -> str:
        lower = title.lower()
        if node_type == "decision":
            return "Constraint or choice carried into the active workflow."
        if node_type == "question":
            return "Open question that still needs resolution in this workspace."
        if node_type == "search-result":
            return "Evidence or referenced source attached by the agent."
        if any(token in lower for token in ["rss", "newsapi", "gnews", "feed", "api", "search"]):
            return "Input source or retrieval stage in the workflow."
        if any(token in lower for token in ["gemini", "groq", "llama", "model", "claude"]):
            return "Model stage selected by the agent for this pipeline."
        return "Structured workflow stage captured from the turn."

    def infer_edge_kind(self, from_title: str, to_title: str) -> str:
        source = from_title.lower()
        target = to_title.lower()
        if any(token in source for token in ["rss", "newsapi", "gnews", "feed", "api"]):
            return "feeds"
        if any(token in target for token in ["gemini", "groq", "llama", "model", "claude"]):
            return "calls"
        if any(token in target for token in ["fact check", "verify", "ground", "validation"]):
            return "checks"
        if any(token in target for token in ["group", "cluster", "context", "summary", "summarize"]):
            return "groups"
        return "transforms"

    def choose_tools(self, text: str, node_type: str) -> list[str]:
        lower = text.lower()
        tools = {"extract", "promote"}
        if re.search(r"\b(search|api|docs|reference|research|evidence|article|source)\b", lower):
            tools.add("search")
        if re.search(r"\b(related|link|connect|same|similar|because|therefore|instead)\b", lower):
            tools.add("link")
        if re.search(r"\b(cluster|group|workspace|topic|theme)\b", lower):
            tools.add("cluster")
        if node_type == "decision":
            tools.add("link")
        return list(tools)

    def extract_plan_seed(self, prompt: str, assistant_text: str) -> list[dict[str, str]]:
        combined = f"{assistant_text}\n{prompt}"
        chain = self.extract_workflow_chain(combined)
        if chain:
            return chain

        candidate_titles: list[str] = []
        generic_titles = {"workflow", "modules", "constraints", "output", "summary", "role", "goal", "plan"}
        allowed_prefixes = ("card", "node", "step", "stage", "module")
        for raw_line in assistant_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if not lower.startswith(allowed_prefixes):
                continue
            line = re.sub(r"^\s*(card|node|step|stage|module)\s*\d*[:\-]?\s*", "", line, flags=re.I)
            line = re.sub(r"^\s*[-*]\s+", "", line)
            line = re.sub(r"^\s*\d+\.\s+", "", line)
            title = self.clean_title(line)
            if title and title.lower() not in generic_titles and len(self.normalize(title)) <= 4:
                candidate_titles.append(title)
        if not candidate_titles:
            for raw_line in prompt.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if not re.search(r"\b(news|claim|fact|group|extract|retrieve|source|model|api|workspace)\b", line, re.I):
                    continue
                line = re.sub(r"^\s*[-*]\s+", "", line)
                title = self.clean_title(line)
                if title and title.lower() not in generic_titles:
                    candidate_titles.append(title)
        if not candidate_titles:
            candidate_titles = [self.topic_label(prompt)]
        return [
            {"title": title, "detail": self.detail_for_node(title, self.detect_node_type(title)), "type": self.detect_node_type(title), "role": "main"}
            for title in candidate_titles[:4]
        ]

    def extract_workflow_chain(self, text: str) -> list[dict[str, str]]:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if "->" not in line and "→" not in line:
                continue
            payload = re.sub(r"^[\-\*\d\.\)\s]*(workflow|suggested workflow)\s*:\s*", "", line, flags=re.I)
            parts = [self.clean_title(part) for part in re.split(r"\s*(?:->|→)\s*", payload) if self.clean_title(part)]
            if len(parts) < 2:
                continue
            cards: list[dict[str, str]] = []
            for title in parts[:5]:
                node_type = self.detect_node_type(title)
                if node_type == "search-result":
                    node_type = "concept"
                cards.append(
                    {
                        "title": title,
                        "detail": self.detail_for_node(title, node_type),
                        "type": node_type,
                        "role": "main",
                    }
                )
            return cards
        return []

    def build_structured_flow(
        self,
        payload: ChatStreamRequest,
        assistant_text: str,
        search_text: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        nodes: list[dict[str, Any]] = []
        search_nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        tools = self.choose_tools(payload.prompt + "\n" + assistant_text, self.detect_node_type(payload.prompt))
        cards = self.extract_plan_seed(payload.prompt, assistant_text)
        if not cards:
            cards = [
                {
                    "title": self.topic_label(payload.prompt),
                    "detail": "The main idea captured from the conversation.",
                    "type": self.detect_node_type(payload.prompt),
                    "role": "main",
                }
            ]

        max_cards = 4 if payload.allowNodes else 0
        cards = cards[:max_cards]
        card_width = 240.0
        card_gap = 54.0
        base_x = 96.0
        base_y = 86.0

        for index, card in enumerate(cards):
            x = base_x + index * (card_width + card_gap)
            y = base_y + (index % 2) * 18
            node_id = self.next_id("node")
            nodes.append(
                {
                    "id": node_id,
                    "title": self.clean_title(card["title"]),
                    "detail": self.truncate(card.get("detail", ""), 96),
                    "type": card.get("type", "concept"),
                    "x": x,
                    "y": y,
                    "width": card_width,
                    "source": assistant_text or payload.prompt,
                    "sourceTurnId": "",
                    "tools": tools,
                    "linkedFrom": nodes[index - 1]["id"] if index > 0 and payload.allowLinks else None,
                    "imported": False,
                    "pinned": False,
                }
            )
            if index > 0 and payload.allowLinks:
                edges.append(
                    {
                        "id": self.next_id("edge"),
                        "from": nodes[index - 1]["id"],
                        "to": node_id,
                        "kind": "transforms",
                    }
                )

        if "search" in tools and search_text and payload.allowNodes:
            node_id = self.next_id("search")
            search_nodes.append(
                {
                    "id": node_id,
                    "title": self.truncate(search_text.splitlines()[0], 72),
                    "detail": "Grounded evidence attached to the rough plan.",
                    "type": "search-result",
                    "x": base_x + len(nodes) * (card_width + card_gap),
                    "y": base_y + 160,
                    "width": 300.0,
                    "source": search_text[:300],
                    "sourceTurnId": "",
                    "tools": tools,
                    "linkedFrom": nodes[-1]["id"] if nodes else None,
                    "imported": False,
                    "pinned": True,
                }
            )
            if payload.allowLinks and nodes:
                edges.append(
                    {
                        "id": self.next_id("edge"),
                        "from": nodes[-1]["id"],
                        "to": node_id,
                        "kind": "supports",
                    }
                )

        return nodes, search_nodes, edges, tools

    def workspace_context(self, workspace: WorkspacePayload) -> str:
        recent_nodes = workspace.nodes[-6:]
        node_lines = [
            f"- {node.type}: {node.title} [{round(node.x)}, {round(node.y)}]"
            for node in recent_nodes
        ]
        edge_lines = [
            f"- {edge.kind}: {edge.from_} -> {edge.to}"
            for edge in workspace.edges[-6:]
        ]
        context = [
            f"Workspace label: {workspace.label}",
            f"Workspace topic: {workspace.topic}",
            "Approximate node footprint: 240x92 with at least 84px horizontal and 86px vertical spacing.",
            "If a layout needs a fallback, place the next card farther right and slightly lower than the previous one.",
            "Current arrangement:",
            *(node_lines or ["- none"]),
            "Recent connections:",
            *(edge_lines or ["- none"]),
        ]
        return "\n".join(context)

    def create_position(self, index: int, source_node: PlannerNodePayload | None, isolated: bool) -> tuple[float, float]:
        if source_node is not None and not isolated:
            offset = index % 3
            return source_node.x + 318 + offset * 28, source_node.y + (offset - 1) * 122
        row = index // 3
        column = index % 3
        return 180 + column * 320 + row * 60, 124 + row * 186 + (column % 2) * 28

    def run_search(self, prompt: str) -> str:
        query = parse.quote(prompt)
        endpoint = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
        req = request.Request(endpoint, headers={"User-Agent": "planner-prototype/0.1"}, method="GET")
        try:
            with request.urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return ""

        snippets: list[str] = []
        abstract = (payload.get("AbstractText") or "").strip()
        abstract_url = (payload.get("AbstractURL") or "").strip()
        heading = (payload.get("Heading") or prompt).strip() or prompt
        if abstract:
            snippets.append(f"{heading}: {abstract}")
            if abstract_url:
                snippets.append(f"Source: {abstract_url}")

        for item in (payload.get("RelatedTopics") or [])[:4]:
            if "Topics" in item:
                for sub in (item.get("Topics") or [])[:2]:
                    text = (sub.get("Text") or "").strip()
                    url = (sub.get("FirstURL") or "").strip()
                    if text:
                        snippets.append(f"{text}" + (f" ({url})" if url else ""))
                continue
            text = (item.get("Text") or "").strip()
            url = (item.get("FirstURL") or "").strip()
            if text:
                snippets.append(f"{text}" + (f" ({url})" if url else ""))

        return "\n".join(snippets[:5])

    def generate_reply(
        self,
        prompt: str,
        messages: list[ChatMessagePayload],
        search_text: str,
        workspace: WorkspacePayload,
    ) -> tuple[str, str]:
        history = "\n".join(f"{message.role}: {message.text}" for message in messages[-8:])
        system_prompt = (
            "You are a planning copilot for a rough-plan canvas. "
            "Translate the user's request into only the essential cards and keep them compact. "
            "Prefer 2 to 4 important nodes. "
            "Output only lines in the form `Card N: <title>` or `Node N: <title>`. "
            "Do not create generic section cards like Workflow, Modules, Constraints, or Output. "
            "If the user already has a layout, use the current arrangement as context and refine or compact it. "
            "Do not invent filler nodes. "
            "Do not mention hidden reasoning. "
            "If search context is present, use it naturally."
        )
        user_prompt = (
            f"Recent conversation:\n{history or 'none'}\n\n"
            f"Current workspace context:\n{self.workspace_context(workspace)}\n\n"
            f"Search context:\n{search_text or 'none'}\n\n"
            f"User prompt:\n{prompt}\n\n"
            "Reply with compact card lines only."
        )
        try:
            if self.gemini_api_key:
                return "gemini", self.chat_gemini.generate(system_prompt, user_prompt).strip()
        except Exception:
            pass
        return (
            "fallback",
            "Card 1: News Retrieval\nCard 2: Claim Extraction\nCard 3: Fact Verification\nCard 4: Context Grouping\n",
        )

    def build_plan(self, payload: ChatStreamRequest, assistant_text: str, search_text: str) -> dict[str, Any]:
        workspace = payload.workspace
        drift, drift_reason = self.score_drift(workspace, payload.prompt)
        edit_intent = self.classify_edit_intent(payload.prompt)
        if len(workspace.nodes) <= 1 and all(node.source == "seed" for node in workspace.nodes):
            drift = 0.0
            drift_reason = "The workspace is still at its seed state, so the first structured plan stays here."
        elif edit_intent in {"add", "delete"}:
            drift = 0.0
            drift_reason = "The prompt extends or trims the current workspace, so it should stay in place."
        elif edit_intent == "replace" and drift >= self.drift_threshold * 0.7:
            drift = min(1.0, max(drift, self.drift_threshold))
            drift_reason = "The prompt is a replacement or rearrangement request, so a new workspace is warranted."
        action = "split" if edit_intent == "replace" and drift >= self.drift_threshold else "stay"
        nodes, search_nodes, edges, tools = self.build_structured_flow(payload, assistant_text, search_text)
        imported_ids: list[str] = []

        if action == "split":
            important_nodes = [
                node
                for node in workspace.nodes
                if node.source != "seed" and not node.imported and node.type != "search-result"
            ][-3:]
            for index, node in enumerate(important_nodes):
                imported_id = self.next_id("imported")
                nodes.insert(
                    0,
                    {
                        "id": imported_id,
                        "title": node.title,
                        "detail": node.detail,
                        "type": node.type,
                        "x": 96 + index * 214,
                        "y": 90 + index * 18,
                        "width": node.width,
                        "source": node.source,
                        "sourceTurnId": node.sourceTurnId,
                        "tools": node.tools,
                        "linkedFrom": node.linkedFrom,
                        "imported": True,
                        "pinned": True,
                    },
                )
                imported_ids.append(imported_id)
                target_id = next((entry["id"] for entry in nodes if not entry.get("imported")), None)
                if payload.allowLinks and target_id:
                    edges.append(
                        {
                            "id": self.next_id("edge"),
                            "from": imported_id,
                            "to": target_id,
                            "kind": "imported",
                        }
                    )

        return {
            "action": action,
            "workspaceLabel": self.topic_label(payload.prompt) if action == "split" else workspace.label,
            "drift": drift,
            "driftReason": drift_reason,
            "tools": tools,
            "nodes": nodes,
            "searchNodes": search_nodes,
            "edges": edges,
            "importedNodeIds": imported_ids,
            "summary": (
                f'The agent detected drift and opened a fresh workspace around "{self.topic_label(payload.prompt)}".'
                if action == "split"
                else "The agent kept the turn inside the current workspace and attached the key point to the existing rough plan."
            ),
        }


runtime = PlannerRuntime()
app = FastAPI(title="Planner Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse_event(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "groq_configured": bool(runtime.groq_api_key),
        "gemini_configured": bool(runtime.gemini_api_key),
        "drift_threshold": runtime.drift_threshold,
    }


@app.post("/api/planner/chat/stream")
def planner_chat_stream(payload: ChatStreamRequest) -> StreamingResponse:
    def generate() -> Iterable[bytes]:
        started = time.perf_counter()
        yield sse_event({"type": "status", "message": "Evaluating the current workspace centroid."})
        search_text = ""
        tools = runtime.choose_tools(payload.prompt, runtime.detect_node_type(payload.prompt))
        if "search" in tools:
            yield sse_event({"type": "tool", "tool": "search", "message": "Calling grounded search to enrich the strongest node."})
            search_text = runtime.run_search(payload.prompt)
        else:
            yield sse_event({"type": "tool", "tool": "extract", "message": "Extracting durable points and assigning them on the canvas."})

        provider, reply = runtime.generate_reply(payload.prompt, payload.messages, search_text, payload.workspace)
        for chunk in reply.split():
            yield sse_event({"type": "assistant_delta", "delta": f"{chunk} "})
            time.sleep(0.01)

        plan = runtime.build_plan(payload, reply, search_text)
        yield sse_event(
            {
                "type": "result",
                "assistantText": reply,
                "provider": provider,
                "latencyMs": int((time.perf_counter() - started) * 1000),
                "plan": plan,
            }
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8788)
