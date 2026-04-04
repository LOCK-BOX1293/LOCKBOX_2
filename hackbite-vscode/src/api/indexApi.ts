import { apiRequest } from "./client";
import { IndexRequest } from "./types";
import { getHackbiteConfig } from "../config";

export function healthCheck(): Promise<{ status: string }> {
  return apiRequest<{ status: string }>("/health");
}

export function indexFull(payload: IndexRequest): Promise<{ job_id: string; status: string; stats?: Record<string, unknown>; errors?: string[] }> {
  const { indexTimeoutMs } = getHackbiteConfig();
  return apiRequest("/index/full", { method: "POST", body: payload, timeoutMs: indexTimeoutMs });
}

export function indexIncremental(payload: IndexRequest): Promise<{ job_id: string; status: string; stats?: Record<string, unknown>; errors?: string[] }> {
  const { indexTimeoutMs } = getHackbiteConfig();
  return apiRequest("/index/incremental", { method: "POST", body: payload, timeoutMs: indexTimeoutMs });
}
