import { apiRequest } from "./client";
import { JobsResponse } from "./types";

export function getJobs(repoId: string): Promise<JobsResponse> {
  return apiRequest<JobsResponse>(`/jobs/${encodeURIComponent(repoId)}`);
}
