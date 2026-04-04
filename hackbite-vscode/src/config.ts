import * as vscode from "vscode";

export type HackbiteRole = "backend" | "frontend" | "security" | "devops";

export interface HackbiteConfig {
  backendUrl: string;
  repoBranch: string;
  autoIndex: boolean;
  role: HackbiteRole;
  apiKey?: string;
}

export function getHackbiteConfig(): HackbiteConfig {
  const cfg = vscode.workspace.getConfiguration("hackbite");
  const apiKey = (cfg.get<string>("apiKey") ?? "").trim();

  return {
    backendUrl: (cfg.get<string>("backendUrl") ?? "http://localhost:8081").replace(/\/$/, ""),
    repoBranch: cfg.get<string>("repoBranch") ?? "main",
    autoIndex: cfg.get<boolean>("autoIndex") ?? true,
    role: (cfg.get<string>("role") as HackbiteRole) ?? "backend",
    apiKey: apiKey.length ? apiKey : undefined,
  };
}
