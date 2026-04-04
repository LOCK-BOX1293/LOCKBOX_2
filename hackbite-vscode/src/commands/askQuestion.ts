import * as vscode from "vscode";
import { askAgent } from "../api/askApi";
import { retrieveQuery } from "../api/retrieveApi";
import { QAResponse, RetrieveResponse } from "../api/types";
import { getHackbiteConfig } from "../config";
import { QAPanel } from "../panels/QAPanel";
import { detectRepoIdentityFromPath, getConfiguredOrWorkspaceRepoPath } from "../utils/repoDetect";

export function createAskQuestionCommand(extensionUri: vscode.Uri): (prefilledQuestion?: string) => Promise<void> {
  return async (prefilledQuestion?: string) => {
    const repoPath = getConfiguredOrWorkspaceRepoPath();
    if (!repoPath) {
      vscode.window.showWarningMessage("Hackbite: Open a workspace folder first.");
      return;
    }

    const identity = await detectRepoIdentityFromPath(repoPath);
    const editor = vscode.window.activeTextEditor;
    const selectedText = editor?.document.getText(editor.selection)?.trim();

    const selectedQuestion = selectedText
      ? `Explain this snippet in context:\n\n${selectedText}`
      : undefined;
    const initialQuestion = prefilledQuestion?.trim() || selectedQuestion;

    QAPanel.createOrShow(
      extensionUri,
      {
        ask: async (ctx, question) => {
          const cfg = getHackbiteConfig();
          try {
            const ask = await askAgent({
              project_id: ctx.repoId,
              session_id: `vscode-${ctx.repoId}-${ctx.branch}`,
              query: question,
              user_role: cfg.role,
              branch: ctx.branch,
              include_tests: false,
            });

            if (ask.answer?.trim().length) {
              return {
                answer: ask.answer,
                confidence: ask.confidence,
                intent: ask.intent,
                source: "ask-agent",
                citations: ask.citations ?? [],
                chunks: [],
              } as QAResponse;
            }
          } catch {
            // Fall through to retrieval-based local synthesis.
          }

          const retrieval = await retrieveQuery({
            repo_id: ctx.repoId,
            branch: ctx.branch,
            q: question,
            top_k: ctx.topK,
          });

          return buildRetrieveFallback(question, ctx, retrieval);
        },
      },
      {
        repoId: identity.repoId,
        branch: identity.branch,
        topK: 8,
      },
      initialQuestion
    );
  };
}

function buildRetrieveFallback(question: string, ctx: { repoId: string; branch: string }, retrieval: RetrieveResponse): QAResponse {
  if (!retrieval.chunks.length) {
    return {
      answer:
        "No indexed evidence found for this question on the current branch. "
        + `Run Hackbite: Index Workspace for branch '${ctx.branch}' and try again.`,
      confidence: retrieval.confidence ?? 0,
      source: "retrieve-fallback",
      citations: [],
      chunks: [],
    };
  }

  const top = retrieval.chunks.slice(0, 3);
  const bullets = top
    .map((c, i) => `${i + 1}. ${c.file_path}:${c.start_line}-${c.end_line} (score ${Number(c.score ?? 0).toFixed(3)})`)
    .join("\n");
  const firstSnippet = (top[0]?.content ?? "").replace(/\s+/g, " ").trim().slice(0, 280);

  return {
    answer:
      `Retrieved evidence for: "${question}"\n\n`
      + "Top relevant locations:\n"
      + `${bullets}\n\n`
      + (firstSnippet ? `Key snippet:\n${firstSnippet}` : ""),
    confidence: retrieval.confidence ?? 0,
    source: "retrieve-fallback",
    citations: top.map((c) => ({
      file_path: c.file_path,
      start_line: c.start_line,
      end_line: c.end_line,
      why_relevant: c.reason,
    })),
    chunks: retrieval.chunks,
  };
}
