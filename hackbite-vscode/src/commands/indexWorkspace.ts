import * as vscode from "vscode";
import { getJobs } from "../api/jobsApi";
import { healthCheck, indexFull } from "../api/indexApi";
import { detectRepoIdentity, getPrimaryWorkspaceFolder } from "../utils/repoDetect";
import { HackbiteStatusBar } from "../utils/statusBar";

export interface IndexContext {
  statusBar: HackbiteStatusBar;
}

export function createIndexWorkspaceCommand(ctx: IndexContext): () => Promise<void> {
  return async () => {
    const folder = getPrimaryWorkspaceFolder();
    if (!folder) {
      vscode.window.showWarningMessage("Hackbite: Open a workspace folder first.");
      return;
    }

    ctx.statusBar.setIndexing();

    try {
      await healthCheck();
      const identity = await detectRepoIdentity(folder);

      const indexResponse = await indexFull({
        repo_path: identity.repoPath,
        repo_id: identity.repoId,
        branch: identity.branch,
      });

      const jobs = await pollJobs(identity.repoId, 6, 1000);
      const latestStatus = jobs?.jobs?.[0]?.status ?? indexResponse.status;

      if (latestStatus === "failed") {
        ctx.statusBar.setNotIndexed();
        vscode.window.showErrorMessage("Hackbite indexing failed. Check backend logs for details.");
        return;
      }

      if (latestStatus === "partial-success") {
        ctx.statusBar.setReady("Partially Indexed");
        vscode.window.showWarningMessage("Hackbite indexing completed with partial success.");
        return;
      }

      ctx.statusBar.setReady();
      vscode.window.showInformationMessage("Hackbite indexing completed successfully.");
    } catch (error) {
      ctx.statusBar.setOffline();
      vscode.window.showErrorMessage(`Hackbite index failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  };
}

export async function hasSuccessfulIndex(repoId: string): Promise<boolean> {
  try {
    const jobs = await getJobs(repoId);
    return jobs.jobs.some((job) => job.status === "success" || job.status === "partial-success");
  } catch {
    return false;
  }
}

async function pollJobs(repoId: string, attempts: number, intervalMs: number) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const jobs = await getJobs(repoId);
      if (jobs.jobs.length > 0) {
        return jobs;
      }
    } catch {
      // Keep polling for transient backend issues.
    }
    await sleep(intervalMs);
  }
  return undefined;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
