import * as vscode from "vscode";
import { graphOverview } from "../api/graphApi";

export async function openGraphPanel(repoId: string, branch: string): Promise<void> {
  const panel = vscode.window.createWebviewPanel(
    "hackbite.graph",
    "Hackbite Code Map",
    vscode.ViewColumn.Beside,
    { enableScripts: false }
  );

  try {
    const graph = await graphOverview(repoId, branch, "full");
    panel.webview.html = `<!doctype html><html><body style="font-family:Segoe UI,sans-serif;padding:16px;">
      <h2>Hackbite Graph Overview</h2>
      <p>Mode: ${graph.mode} | Nodes: ${graph.meta.node_count ?? "?"} | Edges: ${graph.meta.edge_count ?? "?"}</p>
      <pre style="white-space:pre-wrap; font-size:12px;">${escapeHtml(JSON.stringify(graph, null, 2))}</pre>
    </body></html>`;
  } catch (error) {
    panel.webview.html = `<!doctype html><html><body style="font-family:Segoe UI,sans-serif;padding:16px;">
      <h2>Hackbite Code Map</h2>
      <p>Failed to load graph: ${escapeHtml(error instanceof Error ? error.message : "Unknown error")}</p>
    </body></html>`;
  }
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
