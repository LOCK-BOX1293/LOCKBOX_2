import { createHash } from "crypto";
import { execFile } from "child_process";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import { getHackbiteConfig } from "../config";

const execFileAsync = promisify(execFile);

export function getPrimaryWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
  return vscode.workspace.workspaceFolders?.[0];
}

export async function detectRepoIdentity(folder: vscode.WorkspaceFolder): Promise<{ repoId: string; branch: string; repoPath: string }> {
  return detectRepoIdentityFromPath(folder.uri.fsPath, folder.name);
}

export async function detectRepoIdentityFromPath(repoPath: string, fallbackName?: string): Promise<{ repoId: string; branch: string; repoPath: string }> {
  const fallbackBranch = getHackbiteConfig().repoBranch;

  const [remoteUrl, branch] = await Promise.all([
    tryGit(["remote", "get-url", "origin"], repoPath),
    tryGit(["rev-parse", "--abbrev-ref", "HEAD"], repoPath),
  ]);

  const seed = remoteUrl || fallbackName || path.basename(repoPath) || repoPath;
  const digest = createHash("sha256").update(seed).digest("hex").slice(0, 16);

  return {
    repoId: `hb_${digest}`,
    branch: branch || fallbackBranch,
    repoPath,
  };
}

export function getConfiguredOrWorkspaceRepoPath(): string | undefined {
  const cfg = getHackbiteConfig();
  if (cfg.targetRepoPath) {
    return cfg.targetRepoPath;
  }
  return getPrimaryWorkspaceFolder()?.uri.fsPath;
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
