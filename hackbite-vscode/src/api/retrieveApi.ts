import { apiRequest } from "./client";
import { RetrieveRequest, RetrieveResponse } from "./types";

export function retrieveQuery(payload: RetrieveRequest): Promise<RetrieveResponse> {
  return apiRequest<RetrieveResponse>("/retrieve/query", {
    method: "POST",
    body: payload,
    timeoutMs: 45000,
  });
}
