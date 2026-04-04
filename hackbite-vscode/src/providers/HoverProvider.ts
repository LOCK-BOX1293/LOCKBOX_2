import * as vscode from "vscode";
import { retrieveQuery } from "../api/retrieveApi";
import { detectRepoIdentity } from "../utils/repoDetect";

interface CacheEntry {
  value: string;
  ts: number;
}

export class HackbiteHoverProvider implements vscode.HoverProvider {
  private readonly cache = new Map<string, CacheEntry>();
  private readonly ttlMs = 60_000;

  async provideHover(document: vscode.TextDocument, position: vscode.Position): Promise<vscode.Hover | undefined> {
    const range = document.getWordRangeAtPosition(position);
    if (!range) {
      return undefined;
    }

    const symbol = document.getText(range).trim();
    if (!symbol) {
      return undefined;
    }

    const key = `${document.uri.toString()}:${symbol}`;
    const now = Date.now();
    const cached = this.cache.get(key);
    if (cached && now - cached.ts < this.ttlMs) {
      return new vscode.Hover(new vscode.MarkdownString(cached.value, true), range);
    }

    const folder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (!folder) {
      return undefined;
    }

    try {
      const identity = await detectRepoIdentity(folder);
      const relPath = vscode.workspace.asRelativePath(document.uri, false).replace(/\\/g, "/");
      const q = `Give a one-line summary of symbol ${symbol} in file ${relPath}.`;
      const res = await retrieveQuery({
        repo_id: identity.repoId,
        branch: identity.branch,
        q,
        top_k: 3,
        path_prefix: relPath,
      });

      const top = res.chunks?.[0];
      if (!top?.content) {
        return undefined;
      }

      const firstLine = top.content.split(/\r?\n/).map((x) => x.trim()).find((x) => x.length > 0) ?? "No summary available.";
      const summary = `**Hackbite**: ${truncate(firstLine, 180)}`;
      this.cache.set(key, { value: summary, ts: now });
      return new vscode.Hover(new vscode.MarkdownString(summary, true), range);
    } catch {
      return undefined;
    }
  }
}

function truncate(value: string, maxLen: number): string {
  if (value.length <= maxLen) {
    return value;
  }
  return `${value.slice(0, maxLen - 3)}...`;
}
