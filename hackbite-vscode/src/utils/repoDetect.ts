import { createHash } from "crypto";
import { execFile } from "child_process";
import { promisify } from "util";
import * as vscode from "vscode";
import { getHackbiteConfig } from "../config";

const execFileAsync = promisify(execFile);

export function getPrimaryWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
  return vscode.workspace.workspaceFolders?.[0];
}

export async function detectRepoIdentity(folder: vscode.WorkspaceFolder): Promise<{ repoId: string; branch: string; repoPath: string }> {
  const repoPath = folder.uri.fsPath;
  const fallbackBranch = getHackbiteConfig().repoBranch;

  const [remoteUrl, branch] = await Promise.all([
    tryGit(["remote", "get-url", "origin"], repoPath),
    tryGit(["rev-parse", "--abbrev-ref", "HEAD"], repoPath),
  ]);

  const seed = remoteUrl || folder.name;
  const digest = createHash("sha256").update(seed).digest("hex").slice(0, 16);

  return {
    repoId: `hb_${digest}`,
    branch: branch || fallbackBranch,
    repoPath,
  };
}

async function tryGit(args: string[], cwd: string): Promise<string | undefined> {
  try {
    const { stdout } = await execFileAsync("git", args, { cwd });
    const value = stdout.trim();
    return value.length > 0 ? value : undefined;
  } catch {
    return undefined;
  }
}
