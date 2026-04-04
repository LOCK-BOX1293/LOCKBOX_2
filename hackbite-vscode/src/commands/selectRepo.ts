import * as vscode from "vscode";

export function createSelectRepoCommand(): () => Promise<void> {
  return async () => {
    const picked = await vscode.window.showOpenDialog({
      canSelectFiles: false,
      canSelectFolders: true,
      canSelectMany: false,
      openLabel: "Select repository folder",
    });

    if (!picked || !picked.length) {
      return;
    }

    const selectedPath = picked[0].fsPath;
    await vscode.workspace.getConfiguration("hackbite").update(
      "targetRepoPath",
      selectedPath,
      vscode.ConfigurationTarget.Global
    );

    vscode.window.showInformationMessage(`Hackbite target repository set to: ${selectedPath}`);
  };
}

export function createClearRepoSelectionCommand(): () => Promise<void> {
  return async () => {
    await vscode.workspace.getConfiguration("hackbite").update(
      "targetRepoPath",
      "",
      vscode.ConfigurationTarget.Global
    );
    vscode.window.showInformationMessage("Hackbite target repository reset to current workspace folder.");
  };
}
