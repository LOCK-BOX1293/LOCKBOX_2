import * as vscode from "vscode";
import { getJobs } from "../api/jobsApi";
import { healthCheck, indexFull } from "../api/indexApi";
import { detectRepoIdentityFromPath, getConfiguredOrWorkspaceRepoPath } from "../utils/repoDetect";
import { HackbiteStatusBar } from "../utils/statusBar";

export interface IndexContext {
  statusBar: HackbiteStatusBar;
}

export function createIndexWorkspaceCommand(ctx: IndexContext): () => Promise<void> {
  return async () => {
    const repoPath = getConfiguredOrWorkspaceRepoPath();
    if (!repoPath) {
      vscode.window.showWarningMessage("Hackbite: Open a workspace folder first.");
      return;
    }

    const identity = await detectRepoIdentityFromPath(repoPath);

    ctx.statusBar.setIndexing();

    try {
      await healthCheck();

      const indexResponse = await indexFull({
        repo_path: identity.repoPath,
        repo_id: identity.repoId,
        branch: identity.branch,
      });

      const jobs = await pollJobs(identity.repoId, 30, 1000);
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
      const message = error instanceof Error ? error.message : "Unknown error";
      const recoveredStatus = await recoverStatusAfterRequestFailure(identity.repoId, message);

      if (recoveredStatus === "success") {
        ctx.statusBar.setReady();
        vscode.window.showInformationMessage("Hackbite indexing completed (initial request dropped, recovered from job status).");
        return;
      }
      if (recoveredStatus === "partial-success") {
        ctx.statusBar.setReady("Partially Indexed");
        vscode.window.showWarningMessage("Hackbite indexing completed with partial success (recovered from job status).");
        return;
      }
      if (recoveredStatus === "running") {
        ctx.statusBar.setIndexing("Running in backend...");
        vscode.window.showInformationMessage("Hackbite indexing is still running in backend. Re-run command in a moment to refresh status.");
        return;
      }

      ctx.statusBar.setNotIndexed();
      vscode.window.showErrorMessage(`Hackbite index failed: ${message}`);
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

async function recoverStatusAfterRequestFailure(repoId: string, message: string): Promise<string | undefined> {
  if (!isRecoverableNetworkError(message)) {
    return undefined;
  }

  const jobs = await pollJobs(repoId, 90, 1000);
  return jobs?.jobs?.[0]?.status;
}

function isRecoverableNetworkError(message: string): boolean {
  const m = message.toLowerCase();
  return m.includes("fetch failed")
    || m.includes("timeout")
    || m.includes("network")
    || m.includes("socket")
    || m.includes("econnreset")
    || m.includes("terminated");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
