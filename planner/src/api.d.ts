import type { PlannerNode, PlannerEdge, Workspace, ToolId } from './plannerCore';
export interface ChatMessagePayload {
    id: string;
    role: string;
    text: string;
    workspaceId: string;
    tools?: ToolId[];
}
export interface StreamPlanResult {
    action: 'stay' | 'split';
    workspaceLabel: string;
    drift: number;
    driftReason: string;
    tools: ToolId[];
    nodes: PlannerNode[];
    searchNodes: PlannerNode[];
    edges: PlannerEdge[];
    importedNodeIds: string[];
    summary: string;
}
export interface StreamResultEvent {
    type: 'result';
    assistantText: string;
    provider: string;
    latencyMs: number;
    plan: StreamPlanResult;
}
type StreamEvent = {
    type: 'status';
    message: string;
} | {
    type: 'tool';
    tool: string;
    message: string;
} | {
    type: 'assistant_delta';
    delta: string;
} | StreamResultEvent;
export declare function streamPlannerTurn(payload: {
    prompt: string;
    workspace: Workspace;
    messages: ChatMessagePayload[];
    allowNodes: boolean;
    allowLinks: boolean;
}, onEvent: (event: StreamEvent) => void): Promise<void>;
export {};
