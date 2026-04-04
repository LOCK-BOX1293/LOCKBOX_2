import * as vscode from "vscode";

class SymbolTreeItem extends vscode.TreeItem {
  constructor(
    public readonly kind: "file" | "symbol",
    public readonly labelText: string,
    public readonly fileUri: vscode.Uri,
    public readonly symbolRange?: vscode.Range,
    collapsibleState: vscode.TreeItemCollapsibleState = vscode.TreeItemCollapsibleState.None
  ) {
    super(labelText, collapsibleState);

    if (kind === "file") {
      this.contextValue = "hackbite-file";
      this.iconPath = vscode.ThemeIcon.File;
      this.resourceUri = fileUri;
    } else {
      this.contextValue = "hackbite-symbol";
      this.iconPath = new vscode.ThemeIcon("symbol-method");
      this.command = {
        command: "hackbite.revealSymbol",
        title: "Reveal Symbol",
        arguments: [this],
      };
      this.description = symbolRange ? `L${symbolRange.start.line + 1}` : undefined;
    }
  }
}

export class SymbolTreeProvider implements vscode.TreeDataProvider<SymbolTreeItem> {
  private readonly emitter = new vscode.EventEmitter<SymbolTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this.emitter.event;

  private readonly files = new Map<string, SymbolTreeItem[]>();

  refresh(): void {
    void this.rebuild();
  }

  async rebuild(): Promise<void> {
    this.files.clear();
    const folders = vscode.workspace.workspaceFolders ?? [];
    for (const folder of folders) {
      const uris = await vscode.workspace.findFiles(
        new vscode.RelativePattern(folder, "**/*.{py,ts,tsx,js,jsx}"),
        "**/{node_modules,venv,.venv,dist,out,build}/**",
        120
      );

      for (const uri of uris) {
        try {
          const doc = await vscode.workspace.openTextDocument(uri);
          const symbols = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
            "vscode.executeDocumentSymbolProvider",
            uri
          );
          if (!symbols || symbols.length === 0) {
            continue;
          }
          const symbolItems = flatten(symbols)
            .filter((s) => isSupported(s.kind))
            .slice(0, 80)
            .map((s) => new SymbolTreeItem("symbol", s.name, uri, s.selectionRange));
          if (symbolItems.length > 0) {
            this.files.set(uri.toString(), symbolItems);
          }
          void doc;
        } catch {
          // Ignore per-file symbol parsing errors.
        }
      }
    }

    this.emitter.fire();
  }

  getTreeItem(element: SymbolTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: SymbolTreeItem): vscode.ProviderResult<SymbolTreeItem[]> {
    if (!element) {
      const root: SymbolTreeItem[] = [];
      for (const key of this.files.keys()) {
        const uri = vscode.Uri.parse(key);
        const label = vscode.workspace.asRelativePath(uri, false).replace(/\\/g, "/");
        root.push(new SymbolTreeItem("file", label, uri, undefined, vscode.TreeItemCollapsibleState.Collapsed));
      }
      root.sort((a, b) => a.labelText.localeCompare(b.labelText));
      return root;
    }

    if (element.kind === "file") {
      return this.files.get(element.fileUri.toString()) ?? [];
    }

    return [];
  }
}

export async function revealSymbol(item: SymbolTreeItem): Promise<void> {
  const doc = await vscode.workspace.openTextDocument(item.fileUri);
  const editor = await vscode.window.showTextDocument(doc, { preview: false });
  if (item.symbolRange) {
    editor.selection = new vscode.Selection(item.symbolRange.start, item.symbolRange.end);
    editor.revealRange(item.symbolRange, vscode.TextEditorRevealType.InCenter);
  }
}

function isSupported(kind: vscode.SymbolKind): boolean {
  return kind === vscode.SymbolKind.Function
    || kind === vscode.SymbolKind.Method
    || kind === vscode.SymbolKind.Class
    || kind === vscode.SymbolKind.Interface;
}

function flatten(symbols: vscode.DocumentSymbol[]): vscode.DocumentSymbol[] {
  const out: vscode.DocumentSymbol[] = [];
  const stack = [...symbols];
  while (stack.length) {
    const item = stack.pop();
    if (!item) {
      continue;
    }
    out.push(item);
    for (const child of item.children) {
      stack.push(child);
    }
  }
  return out;
}
