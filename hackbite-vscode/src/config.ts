import * as vscode from "vscode";

export type HackbiteRole = "backend" | "frontend" | "security" | "devops";

export interface HackbiteConfig {
  backendUrl: string;
  repoBranch: string;
  targetRepoPath?: string;
  autoIndex: boolean;
  role: HackbiteRole;
  indexTimeoutMs: number;
  apiKey?: string;
}

export function getHackbiteConfig(): HackbiteConfig {
  const cfg = vscode.workspace.getConfiguration("hackbite");
  const apiKey = (cfg.get<string>("apiKey") ?? "").trim();
  const targetRepoPath = (cfg.get<string>("targetRepoPath") ?? "").trim();

  return {
    backendUrl: (cfg.get<string>("backendUrl") ?? "http://localhost:8081").replace(/\/$/, ""),
    repoBranch: cfg.get<string>("repoBranch") ?? "main",
    targetRepoPath: targetRepoPath.length ? targetRepoPath : undefined,
    autoIndex: cfg.get<boolean>("autoIndex") ?? true,
    role: (cfg.get<string>("role") as HackbiteRole) ?? "backend",
    indexTimeoutMs: Math.max(60_000, cfg.get<number>("indexTimeoutMs") ?? 600_000),
    apiKey: apiKey.length ? apiKey : undefined,
  };
}
