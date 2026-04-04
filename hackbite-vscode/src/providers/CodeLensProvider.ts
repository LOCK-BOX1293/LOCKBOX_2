import * as vscode from "vscode";

const SUPPORTED_KINDS = new Set<vscode.SymbolKind>([
  vscode.SymbolKind.Function,
  vscode.SymbolKind.Method,
  vscode.SymbolKind.Class,
  vscode.SymbolKind.Interface,
]);

export class HackbiteCodeLensProvider implements vscode.CodeLensProvider {
  async provideCodeLenses(document: vscode.TextDocument): Promise<vscode.CodeLens[]> {
    const symbols = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
      "vscode.executeDocumentSymbolProvider",
      document.uri
    );

    if (!symbols || symbols.length === 0) {
      return [];
    }

    const flattened = flattenSymbols(symbols);
    const lenses: vscode.CodeLens[] = [];

    for (const symbol of flattened) {
      if (!SUPPORTED_KINDS.has(symbol.kind)) {
        continue;
      }

      const question = `Explain ${symbol.name} in context of this repository and include related files.`;

      lenses.push(
        new vscode.CodeLens(symbol.selectionRange, {
          title: "Ask Hackbite",
          command: "hackbite.askPrefilled",
          arguments: [question],
          tooltip: "Open Hackbite Q&A with a symbol-focused prompt",
        })
      );
    }

    return lenses;
  }
}

function flattenSymbols(symbols: vscode.DocumentSymbol[]): vscode.DocumentSymbol[] {
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
