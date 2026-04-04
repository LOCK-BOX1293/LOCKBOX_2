import { apiRequest } from "./client";

export function graphOverview(repoId: string, branch: string, mode: "full" | "focused", q?: string) {
  return apiRequest<{
    mode: string;
    repo_id: string;
    branch: string;
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
    meta: Record<string, unknown>;
  }>("/graph/overview", {
    query: {
      repo_id: repoId,
      branch,
      mode,
      q,
    },
  });
}

export function graphNode(repoId: string, branch: string, nodeType: "file" | "symbol", nodeId: string) {
  return apiRequest<Record<string, unknown>>(`/graph/node/${encodeURIComponent(nodeId)}`, {
    query: {
      repo_id: repoId,
      branch,
      node_type: nodeType,
    },
  });
}

export function edgeContext(repoId: string, branch: string, fromSymbolId: string, toSymbolId: string) {
  return apiRequest<Record<string, unknown>>("/graph/edge-context", {
    query: {
      repo_id: repoId,
      branch,
      from_symbol_id: fromSymbolId,
      to_symbol_id: toSymbolId,
    },
  });
}
