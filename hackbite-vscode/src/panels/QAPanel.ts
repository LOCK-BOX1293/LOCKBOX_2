import * as vscode from "vscode";
import { QAResponse } from "../api/types";

interface AskContext {
  repoId: string;
  branch: string;
  topK: number;
}

interface QAPanelDependencies {
  ask: (ctx: AskContext, question: string) => Promise<QAResponse>;
}

export class QAPanel {
  private static currentPanel: QAPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private readonly deps: QAPanelDependencies;
  private askContext: AskContext;

  static createOrShow(extensionUri: vscode.Uri, deps: QAPanelDependencies, askContext: AskContext, initialQuestion?: string): QAPanel {
    if (QAPanel.currentPanel) {
      QAPanel.currentPanel.askContext = askContext;
      QAPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
      if (initialQuestion && initialQuestion.trim()) {
        QAPanel.currentPanel.panel.webview.postMessage({ type: "prefill", question: initialQuestion.trim() });
      }
      return QAPanel.currentPanel;
    }

    QAPanel.currentPanel = new QAPanel(extensionUri, deps, askContext, initialQuestion);
    return QAPanel.currentPanel;
  }

  private constructor(extensionUri: vscode.Uri, deps: QAPanelDependencies, askContext: AskContext, initialQuestion?: string) {
    this.deps = deps;
    this.askContext = askContext;
    this.panel = vscode.window.createWebviewPanel("hackbite.qa", "Hackbite Q&A", vscode.ViewColumn.Beside, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(extensionUri, "media")],
    });

    this.panel.webview.html = this.getHtml(this.panel.webview);

    this.panel.onDidDispose(() => {
      if (QAPanel.currentPanel === this) {
        QAPanel.currentPanel = undefined;
      }
    });

    this.panel.webview.onDidReceiveMessage(async (message: { type: string; question?: string }) => {
      if (message.type !== "ask" || !message.question?.trim()) {
        return;
      }
      try {
        const result = await this.deps.ask(this.askContext, message.question.trim());
        this.panel.webview.postMessage({ type: "result", payload: result });
      } catch (error) {
        this.panel.webview.postMessage({
          type: "error",
          error: error instanceof Error ? error.message : "Unknown error",
        });
      }
    });

    if (initialQuestion && initialQuestion.trim()) {
      setTimeout(() => {
        this.panel.webview.postMessage({ type: "prefill", question: initialQuestion.trim() });
      }, 20);
    }
  }

  private getHtml(webview: vscode.Webview): string {
    const nonce = String(Date.now());
    const csp = `default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';`;

    return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="Content-Security-Policy" content="${csp}" />
    <title>Hackbite Q&A</title>
    <style>
      body { font-family: Segoe UI, sans-serif; padding: 16px; color: var(--vscode-foreground); }
      .row { display: flex; gap: 8px; }
      input { flex: 1; padding: 8px; border: 1px solid var(--vscode-input-border); background: var(--vscode-input-background); color: var(--vscode-input-foreground); }
      button { padding: 8px 12px; border: none; cursor: pointer; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
      .muted { color: var(--vscode-descriptionForeground); margin-top: 8px; }
      .chunk { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 10px; margin-top: 10px; }
      pre { white-space: pre-wrap; font-family: Consolas, monospace; font-size: 12px; }
      .meta { font-size: 12px; color: var(--vscode-descriptionForeground); margin-bottom: 6px; }
    </style>
  </head>
  <body>
    <h2>Hackbite Q&A</h2>
    <div class="row">
      <input id="q" placeholder="Ask about current codebase" />
      <button id="askBtn">Ask</button>
    </div>
    <div id="status" class="muted">Ready</div>
    <div id="answer"></div>
    <div id="results"></div>

    <script nonce="${nonce}">
      const vscode = acquireVsCodeApi();
      const askBtn = document.getElementById('askBtn');
      const qInput = document.getElementById('q');
      const statusEl = document.getElementById('status');
      const answerEl = document.getElementById('answer');
      const resultsEl = document.getElementById('results');

      function escapeHtml(value) {
        return String(value || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      }

      function ask() {
        const q = qInput.value.trim();
        if (!q) {
          return;
        }
        statusEl.textContent = 'Generating answer from indexed evidence...';
        answerEl.innerHTML = '';
        resultsEl.innerHTML = '';
        vscode.postMessage({ type: 'ask', question: q });
      }

      askBtn.addEventListener('click', ask);
      qInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          ask();
        }
      });

      window.addEventListener('message', (event) => {
        const msg = event.data;
        if (msg.type === 'prefill' && msg.question) {
          qInput.value = msg.question;
        }
        if (msg.type === 'error') {
          statusEl.textContent = 'Error: ' + msg.error;
          return;
        }
        if (msg.type === 'result') {
          const payload = msg.payload;
          const chunks = payload.chunks || [];
          const citations = payload.citations || [];
          const evidenceCount = (payload.source === 'ask-agent' ? citations.length : chunks.length);
          const answerText = String(payload.answer || '');
          const findingsSplit = answerText.split('\nFindings:');
          const directAnswer = findingsSplit[0] || answerText;
          const evidenceSummary = findingsSplit.length > 1 ? ('Findings:' + findingsSplit.slice(1).join('\nFindings:')) : '';

          statusEl.textContent = 'Confidence: ' + Number(payload.confidence || 0).toFixed(3)
            + ' | Evidence: ' + evidenceCount
            + ' | Source: ' + (payload.source || 'unknown');

          answerEl.innerHTML = '<div class="chunk">'
            + '<div class="meta">Direct Answer</div>'
            + '<pre>' + escapeHtml(directAnswer.trim()) + '</pre>'
            + '</div>';

          if (evidenceSummary.trim()) {
            answerEl.innerHTML += '<div class="chunk">'
              + '<div class="meta">Evidence Summary</div>'
              + '<pre>' + escapeHtml(evidenceSummary.trim()) + '</pre>'
              + '</div>';
          }

          if (citations.length) {
            const citationHtml = citations.map((c, i) => {
              const why = c.why_relevant ? (' - ' + escapeHtml(c.why_relevant)) : '';
              return '<div class="meta">[' + (i + 1) + '] '
                + escapeHtml(c.file_path) + ':' + escapeHtml(c.start_line) + '-' + escapeHtml(c.end_line)
                + why + '</div>';
            }).join('');
            answerEl.innerHTML += '<div class="chunk"><div class="meta">Citations</div>' + citationHtml + '</div>';
          }

          resultsEl.innerHTML = chunks.map((c) => {
            const scorePart = c.score ? (' | score=' + Number(c.score).toFixed(3)) : '';
            const content = c.content ? c.content : '[Referenced by citation]';
            return '<div class="chunk">'
              + '<div class="meta">'
              + escapeHtml(c.file_path) + ':' + escapeHtml(c.start_line) + '-' + escapeHtml(c.end_line) + scorePart
              + '</div>'
              + '<pre>' + escapeHtml(content) + '</pre>'
              + '</div>';
          }).join('');
        }
      });
    </script>
  </body>
</html>`;
  }
}
