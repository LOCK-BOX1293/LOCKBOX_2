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
  const serialized = JSON.stringify(graph).replace(/</g, "\\u003c");
  return `<!doctype html>
  <html>
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';" />
    <style>
      :root {
        --panel-border: var(--vscode-panel-border);
        --muted: var(--vscode-descriptionForeground);
      }
      body { font-family: Segoe UI, sans-serif; margin: 0; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
      .top { padding: 12px; border-bottom: 1px solid var(--panel-border); }
      .row { display:flex; gap:8px; margin-top:8px; }
      input { flex:1; padding:7px 8px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border:1px solid var(--vscode-input-border); border-radius: 6px; }
      button { padding:7px 11px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border:none; border-radius: 6px; cursor: pointer; }
      .meta { color: var(--muted); font-size:12px; margin-top: 6px; }
      .layout { display:grid; grid-template-columns: 280px 1fr 420px; height: calc(100vh - 124px); }
      .left { border-right: 1px solid var(--panel-border); overflow:auto; }
      .center { position: relative; overflow:auto; border-right: 1px solid var(--panel-border); background: radial-gradient(circle at 10% 20%, #103554 0%, #0b1a2a 60%, #08121d 100%); }
      .right { overflow:auto; padding: 10px; }
      .leftHead { padding: 10px; position: sticky; top: 0; background: var(--vscode-sideBar-background); border-bottom: 1px solid var(--panel-border); }
      .nodeList { padding: 8px; }
      .nodeItem { font-size: 12px; padding: 6px 8px; border: 1px solid transparent; border-radius: 6px; cursor: pointer; margin-bottom: 6px; }
      .nodeItem:hover { border-color: var(--panel-border); }
      .nodeItem.active { border-color: var(--vscode-focusBorder); background: color-mix(in srgb, var(--vscode-focusBorder) 18%, transparent); }
      .nodeType { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
      #mapCanvas { position: relative; min-width: 1200px; min-height: 900px; }
      #edgeSvg { position: absolute; inset: 0; pointer-events: none; }
      .node { position:absolute; transform: translate(-50%, -50%); border-radius: 10px; padding: 5px 9px; font-size: 11px; cursor:pointer; white-space:nowrap; border: 1px solid transparent; }
      .node.file { background:#198754; color:#fff; }
      .node.symbol { background:#0d6efd; color:#fff; }
      .node.query { background:#dc3545; color:#fff; }
      .node.focus { background:#fd7e14; color:#111; }
      .node.active { border-color: #f8f9fa; box-shadow: 0 0 0 2px rgba(255,255,255,0.35); }
      .status { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
      .card { border: 1px solid var(--panel-border); border-radius: 8px; padding: 10px; margin-bottom: 10px; background: color-mix(in srgb, var(--vscode-editorWidget-background) 75%, transparent); }
      .code { white-space: pre-wrap; font-size: 12px; line-height: 1.45; background: var(--vscode-editor-background); border-radius: 6px; padding: 8px; max-height: 420px; overflow:auto; }
      .pill { display:inline-block; margin: 3px 4px 0 0; padding: 3px 6px; border-radius: 999px; font-size: 11px; border: 1px solid var(--panel-border); }
    </style>
  </head>
  <body>
    <div class="top">
      <div><strong>Hackbite Graph</strong></div>
      <div class="meta">Mode: ${escapeHtml(String(graph.mode))} | Nodes: ${escapeHtml(String(graph.meta.node_count ?? "?"))} | Edges: ${escapeHtml(String(graph.meta.edge_count ?? "?"))}</div>
      <div class="row">
        <input id="q" placeholder="Focused graph query (e.g. orchestrator with specialist agents)" />
        <button id="focusBtn">Focus</button>
        <input id="nodeQuery" placeholder="Type file path or symbol name/id" />
        <button id="openNodeBtn">Open Node</button>
      </div>
    </div>
    <div class="layout">
      <div class="left">
        <div class="leftHead">
          <input id="filter" placeholder="Filter files/symbols" />
          <div class="meta" id="leftMeta">All nodes</div>
        </div>
        <div class="nodeList" id="nodeList"></div>
      </div>
      <div class="center">
        <div id="mapCanvas">
          <svg id="edgeSvg"></svg>
        </div>
      </div>
      <div class="right">
        <div class="status" id="status">Select a node from graph/list or type a file path above.</div>
        <div id="detail"></div>
      </div>
    </div>
    <script nonce="${nonce}">
      const vscode = acquireVsCodeApi();
      let graph = ${serialized};
      let selectedNodeId = null;
      const mapEl = document.getElementById('mapCanvas');
      const edgeSvg = document.getElementById('edgeSvg');
      const nodeListEl = document.getElementById('nodeList');
      const filterEl = document.getElementById('filter');
      const leftMetaEl = document.getElementById('leftMeta');
      const statusEl = document.getElementById('status');
      const detailEl = document.getElementById('detail');
      const qEl = document.getElementById('q');
      const nodeQueryEl = document.getElementById('nodeQuery');
      let positions = new Map();

      function esc(v) { return String(v || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

      function norm(v) { return String(v || '').toLowerCase(); }

      function getDisplayLabel(n) {
        return String(n.label || n.name || n.id || '').trim();
      }

      function nodeType(n) {
        return String(n.type || 'symbol');
      }

      function selectNodeByData(n) {
        if (!n || !n.id) return;
        selectedNodeId = n.id;
        statusEl.textContent = 'Loading node details...';
        renderNodeList();
        updateActiveNodeStyles();
        vscode.postMessage({ type: 'selectNode', nodeId: n.id, nodeType: nodeType(n) === 'file' ? 'file' : 'symbol' });
      }

      function findNodeByQuery(q) {
        const query = norm(q).trim();
        if (!query) return null;
        const nodes = graph.nodes || [];
        const exact = nodes.find((n) => norm(n.id) === query || norm(getDisplayLabel(n)) === query);
        if (exact) return exact;
        return nodes.find((n) => norm(n.id).includes(query) || norm(getDisplayLabel(n)).includes(query));
      }

      function renderGraph() {
        mapEl.querySelectorAll('.node').forEach((n) => n.remove());
        edgeSvg.innerHTML = '';

        const nodes = (graph.nodes || []).slice(0, 220);
        const files = nodes.filter((n) => nodeType(n) === 'file');
        const others = nodes.filter((n) => nodeType(n) !== 'file');
        const ringCenterX = 620;
        const ringCenterY = 460;
        const fileRadius = 330;
        const symbolRadius = 210;

        positions = new Map();

        files.forEach((n, i) => {
          const angle = (Math.PI * 2 * i) / Math.max(files.length, 1);
          const x = ringCenterX + Math.cos(angle) * fileRadius;
          const y = ringCenterY + Math.sin(angle) * fileRadius;
          positions.set(n.id, { x, y });
        });

        others.forEach((n, i) => {
          const angle = (Math.PI * 2 * i) / Math.max(others.length, 1);
          const x = ringCenterX + Math.cos(angle) * symbolRadius;
          const y = ringCenterY + Math.sin(angle) * symbolRadius;
          positions.set(n.id, { x, y });
        });

        edgeSvg.setAttribute('viewBox', '0 0 1240 920');
        edgeSvg.setAttribute('width', '1240');
        edgeSvg.setAttribute('height', '920');

        (graph.edges || []).slice(0, 500).forEach((e) => {
          const p1 = positions.get(e.source);
          const p2 = positions.get(e.target);
          if (!p1 || !p2) return;
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', String(p1.x));
          line.setAttribute('y1', String(p1.y));
          line.setAttribute('x2', String(p2.x));
          line.setAttribute('y2', String(p2.y));
          line.setAttribute('stroke', 'rgba(255,255,255,0.24)');
          line.setAttribute('stroke-width', e.type === 'contains' ? '1.2' : '1');
          edgeSvg.appendChild(line);
        });

        nodes.forEach((n) => {
          const pos = positions.get(n.id);
          if (!pos) return;
          const node = document.createElement('div');
          const t = nodeType(n);
          node.className = 'node ' + t;
          node.dataset.nodeId = String(n.id);
          node.style.left = pos.x + 'px';
          node.style.top = pos.y + 'px';
          node.title = esc(n.id || '');
          node.textContent = esc(getDisplayLabel(n).slice(0, 36));
          node.onclick = () => selectNodeByData(n);
          mapEl.appendChild(node);
        });

        updateActiveNodeStyles();
      }

      function updateActiveNodeStyles() {
        mapEl.querySelectorAll('.node').forEach((el) => {
          if (el.dataset.nodeId === String(selectedNodeId || '')) {
            el.classList.add('active');
          } else {
            el.classList.remove('active');
          }
        });
      }

      function renderNodeList() {
        const q = norm(filterEl.value || '').trim();
        const nodes = (graph.nodes || [])
          .filter((n) => {
            if (!q) return true;
            return norm(n.id).includes(q) || norm(getDisplayLabel(n)).includes(q);
          })
          .sort((a, b) => {
            const at = nodeType(a) === 'file' ? 0 : 1;
            const bt = nodeType(b) === 'file' ? 0 : 1;
            if (at !== bt) return at - bt;
            return getDisplayLabel(a).localeCompare(getDisplayLabel(b));
          })
          .slice(0, 350);

        leftMetaEl.textContent = nodes.length + ' visible nodes';
        nodeListEl.innerHTML = nodes.map((n) => {
          const active = String(n.id) === String(selectedNodeId || '');
          return '<div class="nodeItem ' + (active ? 'active' : '') + '" data-id="' + esc(n.id) + '">'
            + '<div>' + esc(getDisplayLabel(n)) + '</div>'
            + '<div class="nodeType">' + esc(nodeType(n)) + '</div>'
            + '</div>';
        }).join('');

        nodeListEl.querySelectorAll('.nodeItem').forEach((el) => {
          el.addEventListener('click', () => {
            const id = el.getAttribute('data-id');
            const node = (graph.nodes || []).find((n) => String(n.id) === String(id));
            selectNodeByData(node);
          });
        });
      }

      document.getElementById('focusBtn').addEventListener('click', () => {
        const q = qEl.value.trim();
        if (!q) return;
        statusEl.textContent = 'Loading focused graph...';
        vscode.postMessage({ type: 'focusedQuery', q });
      });

      document.getElementById('openNodeBtn').addEventListener('click', () => {
        const q = nodeQueryEl.value.trim();
        if (!q) return;
        const node = findNodeByQuery(q);
        if (!node) {
          statusEl.textContent = 'No matching node found for: ' + q;
          return;
        }
        selectNodeByData(node);
      });

      filterEl.addEventListener('input', renderNodeList);

      window.addEventListener('message', (event) => {
        const msg = event.data;
        if (msg.type === 'graphData') {
          graph = msg.payload;
          renderGraph();
          renderNodeList();
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
          const funcPills = funcs.length
            ? funcs.slice(0, 60).map((f) => '<span class="pill">' + esc((f.name || 'unknown') + (f.start_line ? (' @L' + f.start_line) : '')) + '</span>').join('')
            : '<span class="meta">No function/symbol map available for this node.</span>';

          detailEl.innerHTML = ''
            + '<div class="card">'
            + '<div><strong>Selected Node</strong></div>'
            + '<div class="meta">ID: ' + esc((p.node || {}).id) + '</div>'
            + '<div class="meta">Type: ' + esc((p.node || {}).type) + '</div>'
            + (meta.file_path ? '<div class="meta">File: ' + esc(meta.file_path) + '</div>' : '')
            + '</div>'
            + '<div class="card">'
            + '<div><strong>Code Map</strong></div>'
            + '<div>' + funcPills + '</div>'
            + '</div>'
            + '<div class="card">'
            + '<div><strong>Code Preview</strong></div>'
            + '<div class="code">' + esc(code || 'No code preview available.') + '</div>'
            + '</div>';
          statusEl.textContent = 'Node details loaded.';
        }
      });

      renderGraph();
      renderNodeList();
    </script>
  </body>
  </html>`;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
