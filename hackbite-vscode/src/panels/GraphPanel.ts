import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import * as http from "http";
import { ChildProcess, spawn } from "child_process";
import { graphNode, graphOverview } from "../api/graphApi";

const FRONTEND_HOST = "127.0.0.1";
const FRONTEND_PORT = 4174;
const FRONTEND_URL = `http://${FRONTEND_HOST}:${FRONTEND_PORT}`;
let frontendDevProcess: ChildProcess | undefined;
let frontendStartPromise: Promise<void> | undefined;

export async function openGraphPanel(repoId: string, branch: string): Promise<void> {
  const panel = vscode.window.createWebviewPanel(
    "hackbite.graph",
    "Hackbite Code Map",
    vscode.ViewColumn.Beside,
    { enableScripts: true }
  );

  try {
    const frontendDir = resolveFrontendDir();
    if (frontendDir) {
      await ensureFrontendDevServer(frontendDir);
      panel.webview.html = getFrontendHostHtml(repoId, branch);
      return;
    }

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

function resolveFrontendDir(): string | null {
  const candidates: string[] = [];
  const workspaceFolders = vscode.workspace.workspaceFolders ?? [];

  for (const folder of workspaceFolders) {
    const root = folder.uri.fsPath;
    candidates.push(path.join(root, "frontend"));
    candidates.push(path.join(root, "LOCKBOX_2", "frontend"));
    candidates.push(path.join(root, "lockbox_2", "frontend"));
  }

  // Extension root fallback (hackbite-vscode sibling frontend)
  const extensionRoot = path.resolve(__dirname, "..", "..");
  candidates.push(path.resolve(extensionRoot, "..", "frontend"));

  for (const c of candidates) {
    if (fs.existsSync(path.join(c, "package.json"))) {
      return c;
    }
  }
  return null;
}

async function ensureFrontendDevServer(frontendDir: string): Promise<void> {
  if (await isFrontendReachable()) {
    return;
  }
  if (frontendStartPromise) {
    return frontendStartPromise;
  }

  frontendStartPromise = new Promise<void>((resolve, reject) => {
    const candidates: Array<{ cmd: string; args: string[] }> = [
      {
        cmd: process.platform === "win32" ? "corepack.cmd" : "corepack",
        args: [
          "pnpm",
          "dev",
          "--host",
          FRONTEND_HOST,
          "--port",
          String(FRONTEND_PORT),
          "--strictPort",
        ],
      },
      {
        cmd: process.platform === "win32" ? "npm.cmd" : "npm",
        args: [
          "run",
          "dev",
          "--",
          "--host",
          FRONTEND_HOST,
          "--port",
          String(FRONTEND_PORT),
          "--strictPort",
        ],
      },
    ];

    const tryNext = (idx: number) => {
      if (idx >= candidates.length) {
        frontendStartPromise = undefined;
        reject(new Error("Unable to start frontend dev server with pnpm or npm."));
        return;
      }

      const chosen = candidates[idx];
      const proc = spawn(chosen.cmd, chosen.args, {
        cwd: frontendDir,
        env: { ...process.env, BROWSER: "none" },
        windowsHide: true,
        shell: false,
        stdio: "ignore",
      });
      frontendDevProcess = proc;

      let finished = false;

      const cleanup = () => {
        proc.removeAllListeners("error");
        proc.removeAllListeners("exit");
      };

      const failAndNext = () => {
        if (finished) return;
        finished = true;
        cleanup();
        frontendDevProcess = undefined;
        tryNext(idx + 1);
      };

      proc.once("error", () => failAndNext());
      proc.once("exit", (code) => {
        frontendDevProcess = undefined;
        if (finished) {
          return;
        }
        finished = true;
        cleanup();
        if (code !== 0) {
          tryNext(idx + 1);
        }
      });

      waitForFrontend(35000)
        .then(() => {
          if (finished) {
            return;
          }
          finished = true;
          cleanup();
          frontendStartPromise = undefined;
          resolve();
        })
        .catch(() => failAndNext());
    };

    tryNext(0);
  });

  return frontendStartPromise;
}

function isFrontendReachable(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(FRONTEND_URL, (res) => {
      const ok = (res.statusCode || 0) >= 200 && (res.statusCode || 0) < 500;
      res.resume();
      resolve(ok);
    });
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
  });
}

async function waitForFrontend(timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isFrontendReachable()) {
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Frontend UI did not start on ${FRONTEND_URL} within ${timeoutMs}ms.`);
}

function getFrontendHostHtml(repoId: string, branch: string): string {
  const nonce = String(Date.now());
  return `<!doctype html>
  <html>
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'; frame-src ${FRONTEND_URL}; connect-src ${FRONTEND_URL} http://127.0.0.1:8081 http://localhost:8081;" />
    <style>
      html, body { margin: 0; height: 100%; background: var(--vscode-editor-background); color: var(--vscode-foreground); font-family: Segoe UI, sans-serif; }
      .top { padding: 8px 12px; border-bottom: 1px solid var(--vscode-panel-border); font-size: 12px; color: var(--vscode-descriptionForeground); }
      .top strong { color: var(--vscode-foreground); }
      #appFrame { width: 100%; height: calc(100% - 38px); border: 0; display: block; }
    </style>
  </head>
  <body>
    <div class="top"><strong>Hackbite Code Map</strong> (frontend mode) | repo: ${escapeHtml(repoId)} | branch: ${escapeHtml(branch)} | ui: ${FRONTEND_URL}</div>
    <iframe id="appFrame" src="${FRONTEND_URL}"></iframe>
    <script nonce="${nonce}">
      const frame = document.getElementById('appFrame');
      frame.addEventListener('error', () => {
        document.body.innerHTML = '<div style="padding:16px;">Failed to load frontend UI at ${FRONTEND_URL}. Make sure frontend dev server is running.</div>';
      });
    </script>
  </body>
  </html>`;
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
      #edgeLabelSvg { position: absolute; inset: 0; pointer-events: none; }
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
          <svg id="edgeLabelSvg"></svg>
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
      const edgeLabelSvg = document.getElementById('edgeLabelSvg');
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

      function nodeKey(id) {
        return String(id || '');
      }

      function selectNodeByData(n) {
        if (!n || !n.id) return;
        selectedNodeId = nodeKey(n.id);
        statusEl.textContent = 'Loading node details...';
        renderNodeList();
        updateActiveNodeStyles();
        vscode.postMessage({ type: 'selectNode', nodeId: nodeKey(n.id), nodeType: nodeType(n) === 'file' ? 'file' : 'symbol' });
      }

      function findNodeByQuery(q) {
        const query = norm(q).trim();
        if (!query) return null;
        const nodes = graph.nodes || [];
        const exact = nodes.find((n) => norm(nodeKey(n.id)) === query || norm(getDisplayLabel(n)) === query);
        if (exact) return exact;
        return nodes.find((n) => norm(nodeKey(n.id)).includes(query) || norm(getDisplayLabel(n)).includes(query));
      }

      function renderGraph() {
        mapEl.querySelectorAll('.node').forEach((n) => n.remove());
        edgeSvg.innerHTML = '';
        edgeLabelSvg.innerHTML = '';

        const nodes = (graph.nodes || []).slice(0, 260);
        const baseEdges = (graph.edges || []).slice(0, 700);
        const edges = [];
        const files = nodes.filter((n) => nodeType(n) === 'file');
        const symbols = nodes.filter((n) => nodeType(n) === 'symbol');
        const queryNodes = nodes.filter((n) => nodeType(n) === 'query');
        const focusNodes = nodes.filter((n) => nodeType(n) === 'focus');

        const FILE_X_START = 140;
        const FILE_X_GAP = 260;
        const QUERY_Y = 90;
        const FILE_Y = 220;
        const FOCUS_Y = 340;
        const SYMBOL_Y = 470;

        positions = new Map();
        const nodeById = new Map(nodes.map((n) => [nodeKey(n.id), n]));

        // Keep backend edges and synthesize missing file->symbol "contains" links
        // so mapping always has visible structure.
        const edgeSeen = new Set();
        baseEdges.forEach((e) => {
          const key = nodeKey(e.source) + '->' + nodeKey(e.target) + '::' + String(e.type || '');
          if (!edgeSeen.has(key)) {
            edgeSeen.add(key);
            edges.push(e);
          }
        });
        symbols.forEach((s) => {
          const sid = nodeKey(s.id);
          const fp = String(s.file_path || '');
          if (!fp || !nodeById.has(fp)) return;
          const hasContains = edges.some((e) => nodeKey(e.source) === fp && nodeKey(e.target) === sid && String(e.type || '').toLowerCase() === 'contains');
          if (!hasContains) {
            edges.push({ source: fp, target: sid, type: 'contains', weight: 1.0 });
          }
        });

        queryNodes.forEach((n, i) => {
          const x = FILE_X_START + (i * FILE_X_GAP * 1.2);
          const y = QUERY_Y;
          positions.set(nodeKey(n.id), { x, y });
        });

        files.forEach((n, i) => {
          const x = FILE_X_START + (i * FILE_X_GAP);
          const y = FILE_Y;
          positions.set(nodeKey(n.id), { x, y });
        });

        // Place focus nodes between query and symbols, near their mapped symbol if possible.
        focusNodes.forEach((n, i) => {
          const outgoing = edges.find((e) => nodeKey(e.source) === nodeKey(n.id) && String(e.type || '').toLowerCase() === 'maps_to');
          const mappedSymbolPos = outgoing ? positions.get(nodeKey(outgoing.target)) : undefined;
          const fallbackX = FILE_X_START + (i * 150);
          positions.set(nodeKey(n.id), { x: mappedSymbolPos ? mappedSymbolPos.x : fallbackX, y: FOCUS_Y });
        });

        // Build symbol groups under their parent file when contains edge exists.
        const fileToSymbols = new Map();
        const unparentedSymbols = [];
        symbols.forEach((s) => {
          const parentEdge = edges.find((e) => nodeKey(e.target) === nodeKey(s.id) && String(e.type || '').toLowerCase() === 'contains');
          if (parentEdge && parentEdge.source) {
            const key = String(parentEdge.source);
            const arr = fileToSymbols.get(key) || [];
            arr.push(s);
            fileToSymbols.set(key, arr);
          } else {
            unparentedSymbols.push(s);
          }
        });

        files.forEach((f) => {
          const parentPos = positions.get(nodeKey(f.id));
          if (!parentPos) return;
          const group = fileToSymbols.get(nodeKey(f.id)) || [];
          if (!group.length) return;
          const localGap = Math.max(70, Math.min(120, FILE_X_GAP / Math.max(2, group.length * 0.55)));
          const startX = parentPos.x - ((group.length - 1) * localGap) / 2;
          group.forEach((s, idx) => {
            positions.set(nodeKey(s.id), { x: startX + (idx * localGap), y: SYMBOL_Y });
          });
        });

        if (unparentedSymbols.length) {
          let baseX = FILE_X_START;
          unparentedSymbols.forEach((s, idx) => {
            positions.set(nodeKey(s.id), { x: baseX + ((idx % 12) * 72), y: SYMBOL_Y + 110 + Math.floor(idx / 12) * 80 });
          });
        }

        const allPos = Array.from(positions.values());
        const maxX = allPos.length ? Math.max(...allPos.map((p) => p.x)) : 1200;
        const maxY = allPos.length ? Math.max(...allPos.map((p) => p.y)) : 920;
        const canvasW = Math.max(1240, maxX + 180);
        const canvasH = Math.max(920, maxY + 200);
        mapEl.style.minWidth = canvasW + 'px';
        mapEl.style.minHeight = canvasH + 'px';

        edgeSvg.setAttribute('viewBox', '0 0 ' + canvasW + ' ' + canvasH);
        edgeSvg.setAttribute('width', String(canvasW));
        edgeSvg.setAttribute('height', String(canvasH));
        edgeLabelSvg.setAttribute('viewBox', '0 0 ' + canvasW + ' ' + canvasH);
        edgeLabelSvg.setAttribute('width', String(canvasW));
        edgeLabelSvg.setAttribute('height', String(canvasH));

        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', 'arrow-head');
        marker.setAttribute('viewBox', '0 0 10 10');
        marker.setAttribute('refX', '9');
        marker.setAttribute('refY', '5');
        marker.setAttribute('markerWidth', '7');
        marker.setAttribute('markerHeight', '7');
        marker.setAttribute('orient', 'auto-start-reverse');
        const markerPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        markerPath.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
        markerPath.setAttribute('fill', 'rgba(224,232,255,0.88)');
        marker.appendChild(markerPath);
        defs.appendChild(marker);

        const glow = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
        glow.setAttribute('id', 'edge-glow');
        const blur = document.createElementNS('http://www.w3.org/2000/svg', 'feGaussianBlur');
        blur.setAttribute('stdDeviation', '0.9');
        blur.setAttribute('result', 'blur');
        glow.appendChild(blur);
        defs.appendChild(glow);
        edgeSvg.appendChild(defs);

        edges.forEach((e) => {
          const p1 = positions.get(nodeKey(e.source));
          const p2 = positions.get(nodeKey(e.target));
          if (!p1 || !p2) return;

          const dx = p2.x - p1.x;
          const dy = p2.y - p1.y;
          const curve = Math.max(12, Math.min(70, Math.abs(dx) * 0.12));
          const cx = p1.x + (dx / 2);
          const cy = p1.y + (dy / 2) - (dy === 0 ? curve : curve * Math.sign(dy));

          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('d', 'M ' + p1.x + ' ' + p1.y + ' Q ' + cx + ' ' + cy + ' ' + p2.x + ' ' + p2.y);
          const relation = String(e.type || '').toLowerCase();
          path.setAttribute('stroke', relation === 'contains' ? 'rgba(181,199,255,0.92)' : 'rgba(235,242,255,0.74)');
          path.setAttribute('stroke-width', relation === 'contains' ? '2.4' : '1.8');
          path.setAttribute('fill', 'none');
          path.setAttribute('filter', 'url(#edge-glow)');
          path.setAttribute('marker-end', 'url(#arrow-head)');
          if (relation !== 'contains') {
            path.setAttribute('stroke-dasharray', '6 4');
          }
          edgeSvg.appendChild(path);

          if (relation) {
            const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            t.setAttribute('x', String(cx));
            t.setAttribute('y', String(cy - 8));
            t.setAttribute('fill', '#e6ecff');
            t.setAttribute('font-size', '10');
            t.setAttribute('font-weight', '600');
            t.setAttribute('text-anchor', 'middle');
            t.textContent = relation;
            const width = Math.max(44, relation.length * 7 + 12);
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', String(cx - (width / 2)));
            rect.setAttribute('y', String(cy - 19));
            rect.setAttribute('width', String(width));
            rect.setAttribute('height', '16');
            rect.setAttribute('rx', '4');
            rect.setAttribute('fill', 'rgba(14,24,40,0.92)');
            rect.setAttribute('stroke', 'rgba(186,205,255,0.45)');
            g.appendChild(rect);
            g.appendChild(t);
            edgeLabelSvg.appendChild(g);
          }
        });

        nodes.forEach((n) => {
          const pos = positions.get(nodeKey(n.id));
          if (!pos) return;
          const node = document.createElement('div');
          const t = nodeType(n);
          node.className = 'node ' + t;
          node.dataset.nodeId = nodeKey(n.id);
          node.style.left = pos.x + 'px';
          node.style.top = pos.y + 'px';
          node.title = esc(nodeKey(n.id) || '');
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
            return norm(nodeKey(n.id)).includes(q) || norm(getDisplayLabel(n)).includes(q);
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
          const active = nodeKey(n.id) === String(selectedNodeId || '');
          return '<div class="nodeItem ' + (active ? 'active' : '') + '" data-id="' + esc(nodeKey(n.id)) + '">'
            + '<div>' + esc(getDisplayLabel(n)) + '</div>'
            + '<div class="nodeType">' + esc(nodeType(n)) + '</div>'
            + '</div>';
        }).join('');

        nodeListEl.querySelectorAll('.nodeItem').forEach((el) => {
          el.addEventListener('click', () => {
            const id = el.getAttribute('data-id');
            const node = (graph.nodes || []).find((n) => nodeKey(n.id) === String(id));
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
