import * as vscode from "vscode";
import { openGraphPanel } from "../panels/GraphPanel";
import { detectRepoIdentityFromPath, getConfiguredOrWorkspaceRepoPath } from "../utils/repoDetect";

export function createOpenGraphCommand(): () => Promise<void> {
  return async () => {
    const repoPath = getConfiguredOrWorkspaceRepoPath();
    if (!repoPath) {
      vscode.window.showWarningMessage("Hackbite: Open a workspace folder first.");
      return;
    }

    try {
      const identity = await detectRepoIdentityFromPath(repoPath);
      await openGraphPanel(identity.repoId, identity.branch);
    } catch (error) {
      vscode.window.showErrorMessage(`Hackbite graph failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  };
}
