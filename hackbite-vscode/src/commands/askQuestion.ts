import * as vscode from "vscode";
import { retrieveQuery } from "../api/retrieveApi";
import { QAPanel } from "../panels/QAPanel";
import { detectRepoIdentity, getPrimaryWorkspaceFolder } from "../utils/repoDetect";

export function createAskQuestionCommand(extensionUri: vscode.Uri): (prefilledQuestion?: string) => Promise<void> {
  return async (prefilledQuestion?: string) => {
    const folder = getPrimaryWorkspaceFolder();
    if (!folder) {
      vscode.window.showWarningMessage("Hackbite: Open a workspace folder first.");
      return;
    }

    const identity = await detectRepoIdentity(folder);
    const editor = vscode.window.activeTextEditor;
    const selectedText = editor?.document.getText(editor.selection)?.trim();

    const selectedQuestion = selectedText
      ? `Explain this snippet in context:\n\n${selectedText}`
      : undefined;
    const initialQuestion = prefilledQuestion?.trim() || selectedQuestion;

    QAPanel.createOrShow(
      extensionUri,
      {
        ask: (ctx, question) =>
          retrieveQuery({
            repo_id: ctx.repoId,
            branch: ctx.branch,
            q: question,
            top_k: ctx.topK,
          }),
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
