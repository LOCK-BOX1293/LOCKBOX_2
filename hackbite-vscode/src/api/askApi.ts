import { apiRequest } from "./client";
import { AskAgentRequest, AskAgentResponse } from "./types";

export function askAgent(payload: AskAgentRequest): Promise<AskAgentResponse> {
  return apiRequest<AskAgentResponse>("/ask", {
    method: "POST",
    body: payload,
    timeoutMs: 90000,
  });
}
