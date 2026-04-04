import * as vscode from "vscode";
import { healthCheck, indexIncremental } from "./api/indexApi";
import { createAskQuestionCommand } from "./commands/askQuestion";
import { createIndexWorkspaceCommand, hasSuccessfulIndex } from "./commands/indexWorkspace";
import { createOpenGraphCommand } from "./commands/openGraph";
import { getHackbiteConfig } from "./config";
import { HackbiteCodeLensProvider } from "./providers/CodeLensProvider";
import { HackbiteHoverProvider } from "./providers/HoverProvider";
import { SymbolTreeProvider, revealSymbol } from "./providers/SymbolTreeProvider";
import { detectRepoIdentity, getPrimaryWorkspaceFolder } from "./utils/repoDetect";
import { HackbiteStatusBar } from "./utils/statusBar";

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const statusBar = new HackbiteStatusBar();
  context.subscriptions.push(statusBar);
  const askCommand = createAskQuestionCommand(context.extensionUri);

  context.subscriptions.push(
    vscode.commands.registerCommand("hackbite.indexWorkspace", createIndexWorkspaceCommand({ statusBar }))
  );
  context.subscriptions.push(vscode.commands.registerCommand("hackbite.ask", askCommand));
  context.subscriptions.push(
    vscode.commands.registerCommand("hackbite.askPrefilled", async (question?: string) => {
      await askCommand(question);
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("hackbite.openGraph", createOpenGraphCommand())
  );

  const codeLensProvider = new HackbiteCodeLensProvider();
  const hoverProvider = new HackbiteHoverProvider();
  const symbolTreeProvider = new SymbolTreeProvider();
  const selector: vscode.DocumentSelector = [
    { language: "python" },
    { language: "javascript" },
    { language: "typescript" },
    { language: "javascriptreact" },
    { language: "typescriptreact" },
  ];
  context.subscriptions.push(vscode.languages.registerCodeLensProvider(selector, codeLensProvider));
  context.subscriptions.push(vscode.languages.registerHoverProvider(selector, hoverProvider));

  const treeView = vscode.window.createTreeView("hackbite.symbolTree", {
    treeDataProvider: symbolTreeProvider,
    showCollapseAll: true,
  });
  context.subscriptions.push(treeView);
  context.subscriptions.push(vscode.commands.registerCommand("hackbite.refreshSymbolTree", async () => {
    await symbolTreeProvider.rebuild();
  }));
  context.subscriptions.push(vscode.commands.registerCommand("hackbite.revealSymbol", revealSymbol));
  await symbolTreeProvider.rebuild();

  const incrementalDebounceMs = 2000;
  let saveTimer: NodeJS.Timeout | undefined;
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const cfg = getHackbiteConfig();
      if (!cfg.autoIndex || doc.uri.scheme !== "file") {
        return;
      }
      if (saveTimer) {
        clearTimeout(saveTimer);
      }
      saveTimer = setTimeout(() => {
        void runIncrementalIndex(statusBar);
      }, incrementalDebounceMs);
    })
  );

  await initializeStatus(statusBar);

  const cfg = getHackbiteConfig();
  if (cfg.autoIndex) {
    await maybeAutoIndex(statusBar);
  }
}

export function deactivate(): void {
  // No-op.
}

async function initializeStatus(statusBar: HackbiteStatusBar): Promise<void> {
  try {
    await healthCheck();
    statusBar.setNotIndexed();
  } catch {
    statusBar.setOffline();
  }
}

async function maybeAutoIndex(statusBar: HackbiteStatusBar): Promise<void> {
  const folder = getPrimaryWorkspaceFolder();
  if (!folder) {
    return;
  }

  try {
    const identity = await detectRepoIdentity(folder);
    const hasIndex = await hasSuccessfulIndex(identity.repoId);
    if (!hasIndex) {
      await vscode.commands.executeCommand("hackbite.indexWorkspace");
    } else {
      statusBar.setReady();
    }
  } catch {
    statusBar.setNotIndexed();
  }
}

async function runIncrementalIndex(statusBar: HackbiteStatusBar): Promise<void> {
  const folder = getPrimaryWorkspaceFolder();
  if (!folder) {
    return;
  }

  try {
    const identity = await detectRepoIdentity(folder);
    statusBar.setIndexing("Incremental...");
    await indexIncremental({
      repo_path: identity.repoPath,
      repo_id: identity.repoId,
      branch: identity.branch,
    });
    statusBar.setReady();
  } catch {
    statusBar.setNotIndexed();
  }
}
