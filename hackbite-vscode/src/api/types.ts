export interface IndexRequest {
  repo_path: string;
  repo_id: string;
  branch: string;
}

export interface RetrieveRequest {
  repo_id: string;
  branch: string;
  q: string;
  top_k: number;
  lang?: string;
  path_prefix?: string;
}

export interface RetrieveResponse {
  chunks: Array<{
    file_path: string;
    start_line: number;
    end_line: number;
    score?: number;
    reason?: string;
    content: string;
  }>;
  confidence: number;
}

export interface JobStatusItem {
  job_id: string;
  repo_id: string;
  mode: string;
  status: string;
  started_at?: string;
  finished_at?: string;
  stats?: Record<string, unknown>;
  errors?: string[];
}

export interface JobsResponse {
  repo_id: string;
  jobs: JobStatusItem[];
}
