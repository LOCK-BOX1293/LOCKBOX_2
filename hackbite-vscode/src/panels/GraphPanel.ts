import * as vscode from "vscode";
import { graphNode, graphOverview } from "../api/graphApi";

export async function openGraphPanel(repoId: string, branch: string): Promise<void> {
  const panel = vscode.window.createWebviewPanel(
    "hackbite.graph",
    "Hackbite Code Map",
    vscode.ViewColumn.Beside,
    { enableScripts: true }
  );

  try {
    const graph = await graphOverview(repoId, branch, "full");
    panel.webview.html = getGraphHtml(graph);

    panel.webview.onDidReceiveMessage(async (message: { type: string; nodeId?: string; nodeType?: string; q?: string }) => {
      if (message.type === "selectNode" && message.nodeId && message.nodeType) {
        try {
          const detail = await graphNode(repoId, branch, message.nodeType === "file" ? "file" : "symbol", message.nodeId);
          panel.webview.postMessage({ type: "nodeDetail", payload: detail });
        } catch (error) {
          panel.webview.postMessage({ type: "nodeError", error: error instanceof Error ? error.message : "Unknown error" });
        }
      }

      if (message.type === "focusedQuery" && message.q?.trim()) {
        try {
          const focused = await graphOverview(repoId, branch, "focused", message.q.trim());
          panel.webview.postMessage({ type: "graphData", payload: focused });
        } catch (error) {
          panel.webview.postMessage({ type: "nodeError", error: error instanceof Error ? error.message : "Unknown error" });
        }
      }
    });
  } catch (error) {
    panel.webview.html = `<!doctype html><html><body style="font-family:Segoe UI,sans-serif;padding:16px;">
      <h2>Hackbite Code Map</h2>
      <p>Failed to load graph: ${escapeHtml(error instanceof Error ? error.message : "Unknown error")}</p>
    </body></html>`;
  }
}

function getGraphHtml(graph: { nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>>; mode: string; meta: Record<string, unknown> }): string {
  const nonce = String(Date.now());
  const serialized = escapeHtml(JSON.stringify(graph));
  return `<!doctype html>
  <html>
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';" />
    <style>
      body { font-family: Segoe UI, sans-serif; margin: 0; color: var(--vscode-foreground); }
      .top { padding: 12px; border-bottom: 1px solid var(--vscode-panel-border); }
      .row { display:flex; gap:8px; margin-top:8px; }
      input { flex:1; padding:6px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border:1px solid var(--vscode-input-border); }
      button { padding:6px 10px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border:none; }
      .wrap { display:grid; grid-template-columns: 1.2fr 1fr; height: calc(100vh - 98px); }
      .map { position: relative; overflow:auto; border-right: 1px solid var(--vscode-panel-border); background: linear-gradient(120deg, #09121f, #10253a); }
      .node { position:absolute; transform: translate(-50%, -50%); border-radius: 999px; padding: 4px 8px; font-size: 11px; cursor:pointer; white-space:nowrap; }
      .node.file { background:#198754; color:#fff; }
      .node.symbol { background:#0d6efd; color:#fff; }
      .side { padding:10px; overflow:auto; }
      .meta { color: var(--vscode-descriptionForeground); font-size:12px; margin-bottom:10px; }
      pre { white-space: pre-wrap; font-size: 12px; background: var(--vscode-editor-background); padding: 8px; border-radius: 6px; }
    </style>
  </head>
  <body>
    <div class="top">
      <div><strong>Hackbite Graph</strong></div>
      <div class="meta">Mode: ${escapeHtml(String(graph.mode))} | Nodes: ${escapeHtml(String(graph.meta.node_count ?? "?"))} | Edges: ${escapeHtml(String(graph.meta.edge_count ?? "?"))}</div>
      <div class="row">
        <input id="q" placeholder="Focused graph query (e.g. map markers)" />
        <button id="focusBtn">Focus</button>
      </div>
    </div>
    <div class="wrap">
      <div class="map" id="map"></div>
      <div class="side">
        <div class="meta" id="status">Click a node to load details.</div>
        <div id="detail"></div>
      </div>
    </div>
    <script nonce="${nonce}">
      const vscode = acquireVsCodeApi();
      let graph = JSON.parse('${serialized}');
      const mapEl = document.getElementById('map');
      const statusEl = document.getElementById('status');
      const detailEl = document.getElementById('detail');
      const qEl = document.getElementById('q');

      function esc(v) { return String(v || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

      function renderGraph() {
        mapEl.innerHTML = '';
        const nodes = (graph.nodes || []).slice(0, 160);
        const cols = Math.max(8, Math.ceil(Math.sqrt(nodes.length)));
        const rowHeight = 72;
        const colWidth = 140;
        mapEl.style.minHeight = (Math.ceil(nodes.length / cols) * rowHeight + 40) + 'px';
        mapEl.style.minWidth = (cols * colWidth + 60) + 'px';

        nodes.forEach((n, i) => {
          const r = Math.floor(i / cols);
          const c = i % cols;
          const x = 40 + c * colWidth + (r % 2 ? 22 : 0);
          const y = 40 + r * rowHeight;
          const node = document.createElement('div');
          const t = (n.type || 'symbol') === 'file' ? 'file' : 'symbol';
          node.className = 'node ' + t;
          node.style.left = x + 'px';
          node.style.top = y + 'px';
          node.title = esc(n.id || '');
          node.textContent = esc((n.label || n.name || n.id || '').toString().slice(0, 28));
          node.onclick = () => {
            statusEl.textContent = 'Loading node details...';
            vscode.postMessage({ type: 'selectNode', nodeId: n.id, nodeType: t });
          };
          mapEl.appendChild(node);
        });
      }

      document.getElementById('focusBtn').addEventListener('click', () => {
        const q = qEl.value.trim();
        if (!q) return;
        statusEl.textContent = 'Loading focused graph...';
        vscode.postMessage({ type: 'focusedQuery', q });
      });

      window.addEventListener('message', (event) => {
        const msg = event.data;
        if (msg.type === 'graphData') {
          graph = msg.payload;
          renderGraph();
          statusEl.textContent = 'Focused graph loaded.';
        }
        if (msg.type === 'nodeError') {
          statusEl.textContent = 'Error: ' + msg.error;
        }
        if (msg.type === 'nodeDetail') {
          const p = msg.payload || {};
          const meta = p.metadata || {};
          const funcs = p.functions || [];
          const code = (p.code || '').toString().slice(0, 2500);
          detailEl.innerHTML = ''
            + '<div class="meta">Node: ' + esc((p.node || {}).id) + '</div>'
            + '<div class="meta">Type: ' + esc((p.node || {}).type) + '</div>'
            + '<div class="meta">File: ' + esc(meta.file_path || '') + '</div>'
            + (funcs.length ? '<div class="meta">Functions: ' + esc(funcs.map(f => f.name).slice(0,10).join(', ')) + '</div>' : '')
            + '<pre>' + esc(code) + '</pre>';
          statusEl.textContent = 'Node details loaded.';
        }
      });

      renderGraph();
    </script>
  </body>
  </html>`;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
