import * as vscode from "vscode";
import { openGraphPanel } from "../panels/GraphPanel";
import { detectRepoIdentity, getPrimaryWorkspaceFolder } from "../utils/repoDetect";

export function createOpenGraphCommand(): () => Promise<void> {
  return async () => {
    const folder = getPrimaryWorkspaceFolder();
    if (!folder) {
      vscode.window.showWarningMessage("Hackbite: Open a workspace folder first.");
      return;
    }

    try {
      const identity = await detectRepoIdentity(folder);
      await openGraphPanel(identity.repoId, identity.branch);
    } catch (error) {
      vscode.window.showErrorMessage(`Hackbite graph failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  };
}
