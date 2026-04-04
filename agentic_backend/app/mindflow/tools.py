from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from itertools import count
from urllib import parse, request

from app.mindflow.models import (
    MindflowSessionState,
    PipelineWorkspace,
    WorkspaceEdge,
    WorkspaceGroup,
    WorkspaceNode,
)


class MindflowToolbox:
    def __init__(self) -> None:
        self._id_counter = count(1)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}_{next(self._id_counter)}"

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def ensure_workspace(self, state: MindflowSessionState) -> PipelineWorkspace:
        if state.active_workspace_id:
            for w in state.workspaces:
                if w.id == state.active_workspace_id:
                    return w
        workspace = PipelineWorkspace(
            id=self._next_id("ws"),
            title="Workspace 1",
            created_at=self.now_iso(),
        )
        state.workspaces.append(workspace)
        state.active_workspace_id = workspace.id
        return workspace

    def search(self, query: str) -> list[dict]:
        endpoint = "https://api.duckduckgo.com/?" + parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
        )
        req = request.Request(
            endpoint,
            headers={"User-Agent": "mindflow-hackathon/0.1"},
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return []

        results: list[dict] = []
        abstract = (payload.get("AbstractText") or "").strip()
        abs_url = (payload.get("AbstractURL") or "").strip()
        heading = (payload.get("Heading") or query).strip() or query
        if abstract:
            results.append(
                {
                    "title": heading,
                    "snippet": abstract,
                    "url": abs_url,
                }
            )

        related = payload.get("RelatedTopics") or []
        for item in related[:5]:
            if "Topics" in item:
                for sub in (item.get("Topics") or [])[:2]:
                    text = (sub.get("Text") or "").strip()
                    if text:
                        results.append(
                            {
                                "title": text.split(" - ")[0],
                                "snippet": text,
                                "url": (sub.get("FirstURL") or "").strip(),
                            }
                        )
                continue
            text = (item.get("Text") or "").strip()
            if text:
                results.append(
                    {
                        "title": text.split(" - ")[0],
                        "snippet": text,
                        "url": (item.get("FirstURL") or "").strip(),
                    }
                )

        uniq = []
        seen = set()
        for row in results:
            key = (row.get("title"), row.get("url"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(row)
        return uniq[:5]

    def fetch_doc(self, url: str) -> str:
        if not url:
            return ""
        req = request.Request(
            url,
            headers={"User-Agent": "mindflow-hackathon/0.1"},
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return ""
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\\s+", " ", text).strip()
        return text[:1200]

    def make_node(
        self,
        workspace: PipelineWorkspace,
        node_type: str,
        title: str,
        content: str,
        source_message_id: str,
        imported: bool = False,
        metadata: dict | None = None,
    ) -> WorkspaceNode:
        node = WorkspaceNode(
            id=self._next_id("node"),
            type=node_type,
            title=title.strip()[:120] or "Untitled",
            content=(content or "").strip(),
            source_message_id=source_message_id,
            workspace_id=workspace.id,
            imported=imported,
            metadata=metadata or {},
        )
        workspace.nodes.append(node)
        return node

    def make_connection(
        self,
        workspace: PipelineWorkspace,
        from_node_id: str,
        to_node_id: str,
        relation: str,
    ) -> WorkspaceEdge:
        edge = WorkspaceEdge(
            id=self._next_id("edge"),
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            relation=relation or "related",
            workspace_id=workspace.id,
        )
        workspace.edges.append(edge)
        return edge

    def group_nodes(
        self,
        workspace: PipelineWorkspace,
        node_ids: list[str],
        group_title: str,
    ) -> WorkspaceGroup | None:
        uniq_ids = [nid for nid in dict.fromkeys(node_ids) if nid]
        if len(uniq_ids) < 2:
            return None
        group = WorkspaceGroup(
            id=self._next_id("group"),
            workspace_id=workspace.id,
            title=group_title.strip()[:120] or "Group",
            node_ids=uniq_ids,
        )
        workspace.groups.append(group)
        return group

    def change_canvas(
        self,
        state: MindflowSessionState,
        mode: str,
        payload: dict,
    ) -> PipelineWorkspace:
        if mode == "reuse_workspace":
            return self.ensure_workspace(state)

        if mode != "new_workspace":
            return self.ensure_workspace(state)

        parent = self.ensure_workspace(state)
        carry_nodes = payload.get("carry_over_nodes") or []
        title = payload.get("title") or f"Workspace {len(state.workspaces) + 1}"
        next_ws = PipelineWorkspace(
            id=self._next_id("ws"),
            title=title,
            parent_workspace_id=parent.id,
            inherited_nodes=[],
            created_at=self.now_iso(),
        )

        for node in carry_nodes:
            imported = self.make_node(
                next_ws,
                node_type=node.type,
                title=node.title,
                content=node.content,
                source_message_id=node.source_message_id,
                imported=True,
                metadata={**node.metadata, "imported_from_workspace": parent.id},
            )
            next_ws.inherited_nodes.append(imported.id)

        state.workspaces.append(next_ws)
        state.active_workspace_id = next_ws.id
        return next_ws
